# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded asynchronous export isolation for Live Voice observations.

The buffer is deliberately an in-process delivery seam, not a telemetry backend
or a durability boundary.  A successful synchronous ``emit_*`` call means only
that the exact immutable record is retained for one export attempt.  It does not
mean that the record was exported, acknowledged, or made durable.
"""

from __future__ import annotations

import asyncio
import inspect
import math
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import Lock
from typing import Final, Literal, Protocol, TypeAlias

from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceMetric,
    LiveVoiceObservation,
)


DEFAULT_EXPORT_BUFFER_CAPACITY: Final = 2_048
DEFAULT_EXPORT_TIMEOUT_SECONDS: Final = 1.0
DEFAULT_CLOSE_TIMEOUT_SECONDS: Final = 5.0

ExportRecord: TypeAlias = LiveVoiceObservation | LiveVoiceMetric
ExportRecordKind: TypeAlias = Literal["observation", "metric"]
ExporterState: TypeAlias = Literal[
    "disabled", "not_started", "running", "closing", "closed", "failed"
]
FailureKind: TypeAlias = Literal[
    "exception", "timeout", "cancelled", "invalid_awaitable"
]


class AsyncLiveVoiceExporter(Protocol):
    """Injected owner of any external export side effect."""

    def __call__(self, record: ExportRecord) -> Awaitable[None]: ...


class ObservabilityExporterError(RuntimeError):
    """Base class for stable exporter-buffer failures."""


class ExporterNotStartedError(ObservabilityExporterError):
    """Raised when an enabled buffer has not been explicitly started."""


class ExporterBackpressureError(ObservabilityExporterError):
    """Raised synchronously when the bounded retained capacity is full."""


class ExporterClosingError(ObservabilityExporterError):
    """Raised when a new record arrives after retained close has begun."""


class ExporterClosedError(ObservabilityExporterError):
    """Raised when a new record arrives after the buffer has closed."""


class ExporterFailedError(ObservabilityExporterError):
    """Raised when the unique retained worker is no longer available."""


class InvalidExportRecordError(ObservabilityExporterError, TypeError):
    """Raised when a sink receives a raw or wrong-kind object."""


class ReentrantExporterCloseError(ObservabilityExporterError):
    """Raised when an exporter attempt tries to await its own worker."""


@dataclass(frozen=True, slots=True)
class ExporterStats:
    accepted_observations: int
    accepted_metrics: int
    attempted_observations: int
    attempted_metrics: int
    delivered_observations: int
    delivered_metrics: int
    failed_observations: int
    failed_metrics: int
    timed_out_observations: int
    timed_out_metrics: int
    rejected_full: int
    rejected_not_started: int
    rejected_closing: int
    rejected_closed: int
    rejected_failed: int
    rejected_invalid: int
    close_timeouts: int
    close_cancellations: int
    worker_failures: int
    high_watermark: int

    @property
    def accepted_records(self) -> int:
        return self.accepted_observations + self.accepted_metrics

    @property
    def attempted_records(self) -> int:
        return self.attempted_observations + self.attempted_metrics

    @property
    def delivered_records(self) -> int:
        return self.delivered_observations + self.delivered_metrics

    @property
    def failed_records(self) -> int:
        return self.failed_observations + self.failed_metrics

    @property
    def timed_out_records(self) -> int:
        return self.timed_out_observations + self.timed_out_metrics


@dataclass(frozen=True, slots=True)
class ExporterSnapshot:
    enabled: bool
    state: ExporterState
    capacity: int
    queued_records: int
    queued_observations: int
    queued_metrics: int
    inflight_kind: ExportRecordKind | None
    worker_running: bool
    attempt_running: bool
    last_failure_kind: FailureKind | None
    stats: ExporterStats

    @property
    def retained_records(self) -> int:
        return self.queued_records + int(self.inflight_kind is not None)

    @property
    def closed(self) -> bool:
        return self.state == "closed"


class ExporterCloseTimeoutError(ObservabilityExporterError, TimeoutError):
    """A close waiter timed out while retained teardown kept running."""

    def __init__(self, snapshot: ExporterSnapshot) -> None:
        super().__init__("retained observability exporter close is still running")
        self.snapshot = snapshot


@dataclass(frozen=True, slots=True)
class _BufferedRecord:
    sequence: int
    kind: ExportRecordKind
    record: ExportRecord


@dataclass(frozen=True, slots=True)
class _AttemptResult:
    delivered: bool
    failure_kind: FailureKind | None = None
    accounted: bool = False


ExporterCallback: TypeAlias = Callable[[ExportRecord], Awaitable[None]]


def _positive_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _positive_timeout(value: object, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{field_name} must be a positive finite number")
    return float(value)


class LiveVoiceObservabilityExporterBuffer:
    """One-worker bounded FIFO with synchronous non-blocking collector sinks.

    ``capacity`` is the strict total number of retained records, including the
    current in-flight attempt.  The worker makes exactly one attempt per accepted
    record and never retries.  Exporter failures are diagnostics only and cannot
    rewrite collector acceptance or a business result.  A timed-out attempt is
    counted as failed at its deadline but remains visibly in-flight until callback
    cancellation settles; only then can draining reach ``closed``.

    The owning event loop must be kept alive through ``close``.  If an integrator
    destroys it first, a later enqueue rolls back before acceptance and reports a
    failed, non-running worker.  Python cannot execute cleanup for a task whose
    loop was already closed, so that externally broken lifecycle is not reported
    as cleanly closed.
    """

    def __init__(
        self,
        exporter: AsyncLiveVoiceExporter | ExporterCallback,
        *,
        enabled: bool = True,
        capacity: int = DEFAULT_EXPORT_BUFFER_CAPACITY,
        export_timeout_seconds: float = DEFAULT_EXPORT_TIMEOUT_SECONDS,
        close_timeout_seconds: float = DEFAULT_CLOSE_TIMEOUT_SECONDS,
    ) -> None:
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        if not callable(exporter):
            raise TypeError("exporter must be callable")
        self._capacity = _positive_integer(capacity, "capacity")
        self._export_timeout_seconds = _positive_timeout(
            export_timeout_seconds, "export_timeout_seconds"
        )
        self._close_timeout_seconds = _positive_timeout(
            close_timeout_seconds, "close_timeout_seconds"
        )
        self._exporter = exporter
        self._enabled = enabled
        self._state: ExporterState = "not_started" if enabled else "disabled"
        self._lock = Lock()
        self._pending: deque[_BufferedRecord] | None = deque() if enabled else None
        self._inflight: _BufferedRecord | None = None
        self._next_sequence = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wakeup: asyncio.Event | None = None
        self._worker: asyncio.Task[bool] | None = None
        self._attempt_task: asyncio.Task[None] | None = None
        self._worker_running = False
        self._attempt_running = False
        self._last_failure_kind: FailureKind | None = None

        self._accepted_observations = 0
        self._accepted_metrics = 0
        self._attempted_observations = 0
        self._attempted_metrics = 0
        self._delivered_observations = 0
        self._delivered_metrics = 0
        self._failed_observations = 0
        self._failed_metrics = 0
        self._timed_out_observations = 0
        self._timed_out_metrics = 0
        self._rejected_full = 0
        self._rejected_not_started = 0
        self._rejected_closing = 0
        self._rejected_closed = 0
        self._rejected_failed = 0
        self._rejected_invalid = 0
        self._close_timeouts = 0
        self._close_cancellations = 0
        self._worker_failures = 0
        self._high_watermark = 0

    async def start(self) -> ExporterSnapshot:
        """Start the unique retained worker on the current event loop."""

        if not self._enabled:
            return self.snapshot()
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._state == "running":
                if self._loop is not loop:
                    raise ExporterFailedError(
                        "observability exporter buffer belongs to another event loop"
                    )
            elif self._state == "not_started":
                self._loop = loop
                self._wakeup = asyncio.Event()
                self._state = "running"
                worker = loop.create_task(
                    self._run_worker(), name="live-voice-observability-exporter"
                )
                self._worker = worker
                self._worker_running = True
                worker.add_done_callback(self._worker_done)
            elif self._state == "closing":
                raise ExporterClosingError("observability exporter buffer is closing")
            elif self._state == "closed":
                raise ExporterClosedError("a closed exporter buffer cannot restart")
            else:
                raise ExporterFailedError("a failed exporter buffer cannot restart")
        return self.snapshot()

    def emit_observation(self, record: LiveVoiceObservation) -> None:
        """Synchronously retain one typed observation or reject immediately."""

        if not self._enabled:
            return
        if not isinstance(record, LiveVoiceObservation):
            self._reject_invalid()
            raise InvalidExportRecordError(
                "observation sink accepts only LiveVoiceObservation"
            )
        self._enqueue(record, "observation")

    def emit_metric(self, record: LiveVoiceMetric) -> None:
        """Synchronously retain one typed metric or reject immediately."""

        if not self._enabled:
            return
        if not isinstance(record, LiveVoiceMetric):
            self._reject_invalid()
            raise InvalidExportRecordError("metric sink accepts only LiveVoiceMetric")
        self._enqueue(record, "metric")

    async def close(self, *, timeout_seconds: float | None = None) -> ExporterSnapshot:
        """Drain and stop without letting this waiter's timeout cancel the worker."""

        if not self._enabled:
            return self.snapshot()
        timeout = (
            self._close_timeout_seconds
            if timeout_seconds is None
            else _positive_timeout(timeout_seconds, "timeout_seconds")
        )
        current_task = asyncio.current_task()
        with self._lock:
            if current_task is not None and current_task is self._attempt_task:
                raise ReentrantExporterCloseError(
                    "an exporter attempt cannot await its own retained worker"
                )
            if self._state == "not_started":
                self._state = "closed"
                worker = None
                wakeup = None
                owner_loop = None
            elif self._state == "running":
                owner_loop = self._loop
                if owner_loop is not asyncio.get_running_loop():
                    raise ExporterFailedError(
                        "observability exporter buffer belongs to another event loop"
                    )
                self._state = "closing"
                worker = self._worker
                wakeup = self._wakeup
            elif self._state == "closing":
                owner_loop = self._loop
                if owner_loop is not asyncio.get_running_loop():
                    raise ExporterFailedError(
                        "observability exporter buffer belongs to another event loop"
                    )
                worker = self._worker
                wakeup = self._wakeup
            elif self._state in {"closed", "failed"}:
                worker = None
                wakeup = None
                owner_loop = self._loop
            else:
                worker = self._worker
                wakeup = None
                owner_loop = self._loop

        if wakeup is not None and owner_loop is not None:
            owner_loop.call_soon_threadsafe(wakeup.set)
        if worker is None or worker.done():
            if worker is not None:
                self._finalize_worker(worker)
            return self.snapshot()

        try:
            await asyncio.wait_for(asyncio.shield(worker), timeout=timeout)
        except TimeoutError as exc:
            with self._lock:
                self._close_timeouts += 1
            raise ExporterCloseTimeoutError(self.snapshot()) from exc
        except asyncio.CancelledError:
            with self._lock:
                self._close_cancellations += 1
            raise
        self._finalize_worker(worker)
        return self.snapshot()

    def snapshot(self) -> ExporterSnapshot:
        """Return immutable delivery and lifecycle truth without exposing payloads."""

        with self._lock:
            pending = self._pending
            queued_observations = (
                sum(item.kind == "observation" for item in pending)
                if pending is not None
                else 0
            )
            queued_metrics = (
                sum(item.kind == "metric" for item in pending)
                if pending is not None
                else 0
            )
            return ExporterSnapshot(
                enabled=self._enabled,
                state=self._state,
                capacity=self._capacity,
                queued_records=queued_observations + queued_metrics,
                queued_observations=queued_observations,
                queued_metrics=queued_metrics,
                inflight_kind=(
                    self._inflight.kind if self._inflight is not None else None
                ),
                worker_running=self._worker_running,
                attempt_running=self._attempt_running,
                last_failure_kind=self._last_failure_kind,
                stats=self._stats_locked(),
            )

    def stats(self) -> ExporterStats:
        with self._lock:
            return self._stats_locked()

    def _enqueue(self, record: ExportRecord, kind: ExportRecordKind) -> None:
        with self._lock:
            state = self._state
            if state != "running":
                self._reject_state_locked(state)
            pending = self._pending
            loop = self._loop
            wakeup = self._wakeup
            if pending is None or loop is None or wakeup is None:
                self._rejected_failed += 1
                raise ExporterFailedError("exporter worker is unavailable")
            retained = len(pending) + int(self._inflight is not None)
            if retained >= self._capacity:
                self._rejected_full += 1
                raise ExporterBackpressureError(
                    "observability export buffer capacity is full"
                )
            item = _BufferedRecord(
                sequence=self._next_sequence, kind=kind, record=record
            )
            pending.append(item)
            try:
                loop.call_soon_threadsafe(wakeup.set)
            except RuntimeError as exc:
                pending.pop()
                self._state = "failed"
                self._worker_running = False
                self._attempt_running = False
                self._rejected_failed += 1
                self._worker_failures += 1
                try:
                    loop.call_soon_threadsafe(wakeup.set)
                except RuntimeError:
                    pass
                raise ExporterFailedError("exporter event loop is unavailable") from exc

            self._next_sequence += 1
            if kind == "observation":
                self._accepted_observations += 1
            else:
                self._accepted_metrics += 1
            self._high_watermark = max(self._high_watermark, retained + 1)

    def _reject_invalid(self) -> None:
        with self._lock:
            self._rejected_invalid += 1

    def _reject_state_locked(self, state: ExporterState) -> None:
        if state == "not_started":
            self._rejected_not_started += 1
            raise ExporterNotStartedError(
                "observability exporter buffer must be started explicitly"
            )
        if state == "closing":
            self._rejected_closing += 1
            raise ExporterClosingError("observability exporter buffer is closing")
        if state == "closed":
            self._rejected_closed += 1
            raise ExporterClosedError("observability exporter buffer is closed")
        self._rejected_failed += 1
        raise ExporterFailedError("observability exporter buffer worker failed")

    async def _run_worker(self) -> bool:
        try:
            while True:
                item = self._take_next()
                if item is None:
                    with self._lock:
                        if self._state == "closing":
                            return True
                        if self._state != "running":
                            return False
                        wakeup = self._wakeup
                    if wakeup is None:
                        return False
                    wakeup.clear()
                    with self._lock:
                        pending = self._pending
                        should_wait = (
                            self._state == "running"
                            and pending is not None
                            and not pending
                        )
                    if should_wait:
                        await wakeup.wait()
                    continue

                result = await self._attempt_export(item)
                self._complete_attempt(item, result)
        except asyncio.CancelledError:
            return False
        except BaseException:
            return False

    def _take_next(self) -> _BufferedRecord | None:
        with self._lock:
            pending = self._pending
            if pending is None or not pending:
                return None
            item = pending.popleft()
            self._inflight = item
            if item.kind == "observation":
                self._attempted_observations += 1
            else:
                self._attempted_metrics += 1
            return item

    async def _attempt_export(self, item: _BufferedRecord) -> _AttemptResult:
        attempt = asyncio.create_task(
            self._invoke_exporter(item.record),
            name=f"live-voice-observability-export-{item.sequence}",
        )
        with self._lock:
            self._attempt_task = attempt
            self._attempt_running = True
        try:
            done, _ = await asyncio.wait(
                {attempt}, timeout=self._export_timeout_seconds
            )
            if not done:
                self._record_timed_out_attempt(item)
                attempt.cancel()
                try:
                    await asyncio.shield(attempt)
                except asyncio.CancelledError:
                    if not attempt.done():
                        raise
                except BaseException:
                    pass
                return _AttemptResult(
                    delivered=False, failure_kind="timeout", accounted=True
                )
            try:
                attempt.result()
            except asyncio.CancelledError:
                return _AttemptResult(delivered=False, failure_kind="cancelled")
            except _InvalidAwaitableError:
                return _AttemptResult(delivered=False, failure_kind="invalid_awaitable")
            except BaseException:
                return _AttemptResult(delivered=False, failure_kind="exception")
            return _AttemptResult(delivered=True)
        finally:
            if attempt.done():
                with self._lock:
                    if self._attempt_task is attempt:
                        self._attempt_task = None
                        self._attempt_running = False

    async def _invoke_exporter(self, record: ExportRecord) -> None:
        result = self._exporter(record)
        if not inspect.isawaitable(result):
            raise _InvalidAwaitableError
        await result

    def _complete_attempt(self, item: _BufferedRecord, result: _AttemptResult) -> None:
        with self._lock:
            if self._inflight is not item:
                return
            self._inflight = None
            if result.delivered:
                if item.kind == "observation":
                    self._delivered_observations += 1
                else:
                    self._delivered_metrics += 1
                return

            if result.accounted:
                return

            failure_kind = result.failure_kind
            self._last_failure_kind = failure_kind
            if item.kind == "observation":
                self._failed_observations += 1
                if failure_kind == "timeout":
                    self._timed_out_observations += 1
            else:
                self._failed_metrics += 1
                if failure_kind == "timeout":
                    self._timed_out_metrics += 1

    def _record_timed_out_attempt(self, item: _BufferedRecord) -> None:
        with self._lock:
            self._last_failure_kind = "timeout"
            if item.kind == "observation":
                self._failed_observations += 1
                self._timed_out_observations += 1
            else:
                self._failed_metrics += 1
                self._timed_out_metrics += 1

    def _worker_done(self, worker: asyncio.Task[bool]) -> None:
        self._finalize_worker(worker)

    def _finalize_worker(self, worker: asyncio.Task[bool]) -> None:
        if not worker.done():
            return
        try:
            graceful = worker.result()
        except BaseException:
            graceful = False
        with self._lock:
            self._worker_running = False
            pending = self._pending
            settled = pending is not None and not pending and self._inflight is None
            if graceful and self._state == "closing" and settled:
                self._state = "closed"
            elif self._state not in {"closed", "failed"}:
                self._state = "failed"
                self._worker_failures += 1

    def _stats_locked(self) -> ExporterStats:
        return ExporterStats(
            accepted_observations=self._accepted_observations,
            accepted_metrics=self._accepted_metrics,
            attempted_observations=self._attempted_observations,
            attempted_metrics=self._attempted_metrics,
            delivered_observations=self._delivered_observations,
            delivered_metrics=self._delivered_metrics,
            failed_observations=self._failed_observations,
            failed_metrics=self._failed_metrics,
            timed_out_observations=self._timed_out_observations,
            timed_out_metrics=self._timed_out_metrics,
            rejected_full=self._rejected_full,
            rejected_not_started=self._rejected_not_started,
            rejected_closing=self._rejected_closing,
            rejected_closed=self._rejected_closed,
            rejected_failed=self._rejected_failed,
            rejected_invalid=self._rejected_invalid,
            close_timeouts=self._close_timeouts,
            close_cancellations=self._close_cancellations,
            worker_failures=self._worker_failures,
            high_watermark=self._high_watermark,
        )


class _InvalidAwaitableError(TypeError):
    pass


__all__ = [
    "DEFAULT_CLOSE_TIMEOUT_SECONDS",
    "DEFAULT_EXPORT_BUFFER_CAPACITY",
    "DEFAULT_EXPORT_TIMEOUT_SECONDS",
    "AsyncLiveVoiceExporter",
    "ExportRecord",
    "ExportRecordKind",
    "ExporterBackpressureError",
    "ExporterCloseTimeoutError",
    "ExporterClosedError",
    "ExporterClosingError",
    "ExporterFailedError",
    "ExporterNotStartedError",
    "ExporterSnapshot",
    "ExporterStats",
    "ExporterState",
    "FailureKind",
    "InvalidExportRecordError",
    "LiveVoiceObservabilityExporterBuffer",
    "ObservabilityExporterError",
    "ReentrantExporterCloseError",
]
