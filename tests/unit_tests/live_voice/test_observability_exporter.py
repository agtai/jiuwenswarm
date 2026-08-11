# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    LiveVoiceMetric,
    LiveVoiceObservation,
    LiveVoiceObservabilityCollector,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.observability_exporter import (
    ExportRecord,
    ExporterBackpressureError,
    ExporterCloseTimeoutError,
    ExporterClosedError,
    ExporterClosingError,
    ExporterFailedError,
    ExporterNotStartedError,
    InvalidExportRecordError,
    LiveVoiceObservabilityExporterBuffer,
    ReentrantExporterCloseError,
)


def _route() -> dict[str, object]:
    return {
        "implementation_class": "formal",
        "owner_module": "runtime.conversation",
        "capability_provider": "jiuwenswarm-runtime",
        "contract_version": LIVE_VOICE_CONTRACT_VERSION,
        "reason_code": None,
    }


def _observation(event_id: str) -> LiveVoiceObservation:
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": event_id,
            "event_name": "segment.started",
            "segment_name": "runtime.turn",
            "observed_at": "2026-08-06T09:00:00Z",
            "monotonic_ms": 1_000.0,
            "binding": {
                "correlation_id": "corr-exporter",
                "interaction_id": "interaction-exporter",
                "turn_id": "turn-exporter",
            },
            "route": _route(),
            "source_component": "observability.exporter.test",
        }
    )


def _metric(measurement_id: str) -> LiveVoiceMetric:
    return create_metric(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "measurement_id": measurement_id,
            "metric_name": "live_voice.queue_depth",
            "metric_kind": "gauge",
            "unit": "items",
            "value": 1,
            "observed_at": "2026-08-06T09:00:00Z",
            "binding": {"correlation_id": "corr-exporter"},
            "route": _route(),
            "segment_name": "runtime.queue",
            "implementation_class": "formal",
        }
    )


def _buffer(
    exporter: Callable[[ExportRecord], Awaitable[None]],
    **options: object,
) -> LiveVoiceObservabilityExporterBuffer:
    return LiveVoiceObservabilityExporterBuffer(exporter, **options)  # type: ignore[arg-type]


def test_configuration_is_strictly_bounded() -> None:
    async def exporter(_: ExportRecord) -> None:
        return None

    with pytest.raises(ValueError, match="capacity"):
        LiveVoiceObservabilityExporterBuffer(exporter, capacity=0)
    with pytest.raises(ValueError, match="export_timeout_seconds"):
        LiveVoiceObservabilityExporterBuffer(exporter, export_timeout_seconds=0)
    with pytest.raises(ValueError, match="close_timeout_seconds"):
        LiveVoiceObservabilityExporterBuffer(
            exporter, close_timeout_seconds=float("inf")
        )
    with pytest.raises(TypeError, match="callable"):
        LiveVoiceObservabilityExporterBuffer(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_disabled_returns_before_payload_and_creates_no_worker_or_export() -> (
    None
):
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    buffer = _buffer(exporter, enabled=False)

    buffer.emit_observation(object())  # type: ignore[arg-type]
    buffer.emit_metric(object())  # type: ignore[arg-type]
    started = await buffer.start()
    closed = await buffer.close()

    assert started.state == closed.state == "disabled"
    assert started.queued_records == started.retained_records == 0
    assert started.worker_running is started.attempt_running is False
    assert started.stats.accepted_records == 0
    assert started.stats.rejected_invalid == 0
    assert exported == []


@pytest.mark.asyncio
async def test_explicit_start_and_typed_immutable_records_are_required() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    buffer = _buffer(exporter)
    event = _observation("event-start")

    with pytest.raises(ExporterNotStartedError):
        buffer.emit_observation(event)
    await buffer.start()
    with pytest.raises(InvalidExportRecordError):
        buffer.emit_observation(event.to_dict())  # type: ignore[arg-type]
    with pytest.raises(InvalidExportRecordError):
        buffer.emit_observation(_metric("metric-wrong-kind"))  # type: ignore[arg-type]

    closed = await buffer.close()
    assert closed.closed
    assert closed.stats.rejected_not_started == 1
    assert closed.stats.rejected_invalid == 2
    assert exported == []


@pytest.mark.asyncio
async def test_unified_fifo_preserves_exact_type_identity_and_drains_on_close() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    buffer = _buffer(exporter, capacity=3)
    records: list[ExportRecord] = [
        _observation("event-fifo-1"),
        _metric("metric-fifo-1"),
        _observation("event-fifo-2"),
    ]
    await buffer.start()
    buffer.emit_observation(records[0])  # type: ignore[arg-type]
    buffer.emit_metric(records[1])  # type: ignore[arg-type]
    buffer.emit_observation(records[2])  # type: ignore[arg-type]

    accepted = buffer.snapshot()
    assert accepted.stats.accepted_records == 3
    assert accepted.stats.delivered_records == 0
    assert accepted.retained_records == 3

    closed = await buffer.close()
    assert all(actual is expected for actual, expected in zip(exported, records))
    assert closed.closed
    assert closed.retained_records == 0
    assert closed.stats.attempted_records == 3
    assert closed.stats.delivered_records == 3
    assert closed.stats.failed_records == 0
    assert closed.stats.high_watermark == 3


@pytest.mark.asyncio
async def test_slow_exporter_isolated_from_collector_and_full_is_explicit() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        entered.set()
        await release.wait()
        exported.append(record)

    buffer = _buffer(exporter, capacity=1)
    await buffer.start()
    collector = LiveVoiceObservabilityCollector(
        observation_sink=buffer.emit_observation
    )

    assert collector.emit_observation(_observation("event-slow-1"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    with pytest.raises(ExporterBackpressureError):
        buffer.emit_metric(_metric("metric-direct-backpressure"))
    assert collector.emit_observation(_observation("event-slow-2"))

    snapshot = buffer.snapshot()
    assert snapshot.inflight_kind == "observation"
    assert snapshot.stats.accepted_records == 1
    assert snapshot.stats.rejected_full == 2
    assert collector.stats().accepted_observations == 2
    assert collector.stats().sink_failures == 1
    assert exported == []

    release.set()
    closed = await buffer.close()
    assert closed.stats.delivered_records == 1
    assert len(exported) == 1


@pytest.mark.asyncio
async def test_export_exception_is_one_failed_attempt_and_next_record_delivers() -> (
    None
):
    attempts: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        attempts.append(record)
        if len(attempts) == 1:
            raise RuntimeError("backend unavailable")

    buffer = _buffer(exporter, capacity=2)
    records = [_observation("event-failure"), _metric("metric-after-failure")]
    await buffer.start()
    collector = LiveVoiceObservabilityCollector(
        observation_sink=buffer.emit_observation,
        metric_sink=buffer.emit_metric,
    )
    assert collector.emit_observation(records[0])
    assert collector.emit_metric(records[1])

    closed = await buffer.close()
    assert attempts == records
    assert collector.stats().accepted_observations == 1
    assert collector.stats().accepted_metrics == 1
    assert collector.stats().sink_failures == 0
    assert closed.last_failure_kind == "exception"
    assert closed.stats.attempted_records == 2
    assert closed.stats.failed_observations == 1
    assert closed.stats.delivered_metrics == 1
    assert closed.stats.failed_records == 1


@pytest.mark.asyncio
async def test_export_timeout_is_failed_once_without_retry_or_business_effect() -> None:
    attempts: list[ExportRecord] = []
    cancelled = asyncio.Event()

    async def exporter(record: ExportRecord) -> None:
        attempts.append(record)
        if len(attempts) == 1:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    buffer = _buffer(exporter, capacity=2, export_timeout_seconds=0.01)
    records = [_observation("event-timeout"), _metric("metric-after-timeout")]
    await buffer.start()
    buffer.emit_observation(records[0])
    buffer.emit_metric(records[1])

    closed = await buffer.close(timeout_seconds=1)
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert attempts == records
    assert closed.stats.attempted_records == 2
    assert closed.stats.failed_records == 1
    assert closed.stats.timed_out_observations == 1
    assert closed.stats.deadline_exceeded_observations == 1
    assert closed.stats.delivered_metrics == 1


@pytest.mark.asyncio
async def test_close_timeout_retains_worker_until_inflight_delivery_settles() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    exporter_cancelled = False

    async def exporter(_: ExportRecord) -> None:
        nonlocal exporter_cancelled
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            exporter_cancelled = True
            raise

    buffer = _buffer(
        exporter,
        capacity=1,
        export_timeout_seconds=10,
        close_timeout_seconds=0.01,
    )
    await buffer.start()
    buffer.emit_observation(_observation("event-retained-timeout"))
    await asyncio.wait_for(entered.wait(), timeout=1)

    with pytest.raises(ExporterCloseTimeoutError) as raised:
        await buffer.close()

    timed_out = raised.value.snapshot
    assert timed_out.state == "closing"
    assert timed_out.inflight_kind == "observation"
    assert timed_out.worker_running and timed_out.attempt_running
    assert timed_out.stats.close_timeouts == 1
    assert exporter_cancelled is False

    release.set()
    closed = await buffer.close(timeout_seconds=1)
    assert closed.closed
    assert closed.stats.delivered_records == 1
    assert exporter_cancelled is False


@pytest.mark.asyncio
async def test_timed_out_attempt_is_classified_after_callback_cancellation_settles() -> (
    None
):
    entered = asyncio.Event()
    cancellation_seen = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    async def stubborn_exporter(_: ExportRecord) -> None:
        nonlocal attempts
        attempts += 1
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellation_seen.set()
            await release.wait()

    buffer = _buffer(
        stubborn_exporter,
        capacity=1,
        export_timeout_seconds=0.01,
        close_timeout_seconds=0.05,
    )
    await buffer.start()
    buffer.emit_observation(_observation("event-stubborn-timeout"))
    await asyncio.wait_for(entered.wait(), timeout=1)

    with pytest.raises(ExporterCloseTimeoutError) as raised:
        await buffer.close()

    await asyncio.wait_for(cancellation_seen.wait(), timeout=1)
    timed_out = raised.value.snapshot
    assert timed_out.state == "closing"
    assert timed_out.inflight_kind == "observation"
    assert timed_out.worker_running and timed_out.attempt_running
    assert timed_out.inflight_deadline_exceeded is True
    assert timed_out.last_failure_kind is None
    assert timed_out.stats.failed_records == 0
    assert timed_out.stats.timed_out_records == 0
    assert timed_out.stats.deadline_exceeded_records == 1

    release.set()
    closed = await buffer.close(timeout_seconds=1)
    assert attempts == 1
    assert closed.closed
    assert closed.stats.failed_records == 1
    assert closed.stats.timed_out_records == 1
    assert closed.stats.deadline_exceeded_records == 1
    assert closed.stats.delivered_records == 0


@pytest.mark.asyncio
async def test_cancelled_close_waiter_does_not_cancel_retained_worker() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    exporter_cancelled = False

    async def exporter(_: ExportRecord) -> None:
        nonlocal exporter_cancelled
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            exporter_cancelled = True
            raise

    buffer = _buffer(exporter, capacity=1, export_timeout_seconds=10)
    await buffer.start()
    buffer.emit_metric(_metric("metric-retained-cancel"))
    await asyncio.wait_for(entered.wait(), timeout=1)

    waiter = asyncio.create_task(buffer.close(timeout_seconds=1))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    retained = buffer.snapshot()
    assert retained.state == "closing"
    assert retained.worker_running and retained.attempt_running
    assert retained.stats.close_cancellations == 1
    assert exporter_cancelled is False

    release.set()
    closed = await buffer.close(timeout_seconds=1)
    assert closed.closed
    assert closed.stats.delivered_metrics == 1
    assert exporter_cancelled is False


@pytest.mark.asyncio
async def test_enqueue_during_and_after_close_rejects_without_export() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        entered.set()
        await release.wait()
        exported.append(record)

    buffer = _buffer(exporter, capacity=2, export_timeout_seconds=10)
    await buffer.start()
    buffer.emit_observation(_observation("event-close-owned"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    closing = asyncio.create_task(buffer.close(timeout_seconds=1))
    await asyncio.sleep(0)

    with pytest.raises(ExporterClosingError):
        buffer.emit_metric(_metric("metric-during-close"))
    release.set()
    closed = await closing
    with pytest.raises(ExporterClosedError):
        buffer.emit_observation(_observation("event-after-close"))

    assert closed.closed
    assert len(exported) == 1
    assert buffer.stats().rejected_closing == 1
    assert buffer.stats().rejected_closed == 1


@pytest.mark.asyncio
async def test_reentrant_exporter_can_enqueue_but_cannot_deadlock_on_close() -> None:
    exported: list[ExportRecord] = []
    followup = _metric("metric-reentrant")
    reentrant_close_rejected = False
    reentrant_done = asyncio.Event()
    buffer: LiveVoiceObservabilityExporterBuffer

    async def exporter(record: ExportRecord) -> None:
        nonlocal reentrant_close_rejected
        exported.append(record)
        if isinstance(record, LiveVoiceObservation):
            buffer.emit_metric(followup)
            with pytest.raises(ReentrantExporterCloseError):
                await buffer.close(timeout_seconds=0.1)
            reentrant_close_rejected = True
            reentrant_done.set()

    buffer = _buffer(exporter, capacity=2)
    first = _observation("event-reentrant")
    await buffer.start()
    buffer.emit_observation(first)
    await asyncio.wait_for(reentrant_done.wait(), timeout=1)

    closed = await buffer.close()
    assert exported == [first, followup]
    assert reentrant_close_rejected
    assert closed.closed
    assert closed.stats.delivered_records == 2


@pytest.mark.asyncio
async def test_concurrent_start_and_close_share_one_worker_and_cannot_restart() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    buffer = _buffer(exporter, capacity=1)
    starts = await asyncio.gather(*(buffer.start() for _ in range(8)))
    assert all(snapshot.state == "running" for snapshot in starts)
    buffer.emit_observation(_observation("event-concurrent-lifecycle"))

    closes = await asyncio.gather(*(buffer.close(timeout_seconds=1) for _ in range(8)))
    assert all(snapshot.closed for snapshot in closes)
    assert len(exported) == 1
    assert buffer.stats().attempted_records == 1
    with pytest.raises(ExporterClosedError):
        await buffer.start()


@pytest.mark.asyncio
async def test_start_close_race_converges_without_orphan_worker() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    start_first = _buffer(exporter, capacity=1)
    started, closed = await asyncio.gather(start_first.start(), start_first.close())
    assert started.state == "running"
    assert closed.closed
    assert closed.worker_running is False

    close_first = _buffer(exporter, capacity=1)
    close_task = asyncio.create_task(close_first.close())
    start_task = asyncio.create_task(close_first.start())
    close_result, start_result = await asyncio.gather(
        close_task, start_task, return_exceptions=True
    )
    assert not isinstance(close_result, BaseException)
    assert close_result.closed
    assert isinstance(start_result, ExporterClosedError)
    assert close_first.snapshot().worker_running is False
    assert exported == []


@pytest.mark.asyncio
async def test_cross_thread_sink_wakes_worker_and_preserves_producer_fifo() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    buffer = _buffer(exporter, capacity=6)
    records: list[ExportRecord] = [
        _observation("event-thread-1"),
        _metric("metric-thread-1"),
        _observation("event-thread-2"),
        _metric("metric-thread-2"),
        _observation("event-thread-3"),
        _metric("metric-thread-3"),
    ]
    await buffer.start()

    def produce() -> None:
        for record in records:
            if isinstance(record, LiveVoiceObservation):
                buffer.emit_observation(record)
            else:
                buffer.emit_metric(record)

    await asyncio.to_thread(produce)
    closed = await buffer.close()

    assert exported == records
    assert closed.closed
    assert closed.stats.delivered_records == len(records)


def test_unavailable_owner_loop_rejects_enqueue_without_retained_record_or_task() -> (
    None
):
    export_attempts: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        export_attempts.append(record)

    loop = asyncio.new_event_loop()
    buffer = _buffer(exporter, capacity=1)
    original_call_soon_threadsafe = loop.call_soon_threadsafe
    wake_calls = 0

    def unavailable_once(*args: object, **kwargs: object) -> object:
        nonlocal wake_calls
        wake_calls += 1
        if wake_calls == 1:
            raise RuntimeError("owner loop became unavailable")
        return original_call_soon_threadsafe(*args, **kwargs)  # type: ignore[arg-type]

    try:
        loop.run_until_complete(buffer.start())
        loop.call_soon_threadsafe = unavailable_once  # type: ignore[method-assign]

        with pytest.raises(ExporterFailedError, match="event loop is unavailable"):
            buffer.emit_observation(_observation("event-loop-unavailable"))

        loop.call_soon_threadsafe = original_call_soon_threadsafe  # type: ignore[method-assign]
        loop.run_until_complete(asyncio.sleep(0))
        loop.run_until_complete(asyncio.sleep(0))
        snapshot = buffer.snapshot()
        assert snapshot.state == "failed"
        assert snapshot.worker_running is snapshot.attempt_running is False
        assert snapshot.retained_records == 0
        assert snapshot.stats.accepted_records == 0
        assert snapshot.stats.attempted_records == 0
        assert snapshot.stats.delivered_records == 0
        assert snapshot.stats.failed_records == 0
        assert snapshot.stats.rejected_failed == 1
        assert snapshot.stats.worker_failures == 1
        assert snapshot.stats.high_watermark == 0
        assert export_attempts == []
        assert [task for task in asyncio.all_tasks(loop) if not task.done()] == []
    finally:
        loop.call_soon_threadsafe = original_call_soon_threadsafe  # type: ignore[method-assign]
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


@pytest.mark.asyncio
async def test_non_awaitable_failure_does_not_stop_later_delivery() -> None:
    calls: list[ExportRecord] = []
    delivered: list[ExportRecord] = []

    async def valid_result(record: ExportRecord) -> None:
        delivered.append(record)

    def mixed_exporter(record: ExportRecord) -> Awaitable[None] | None:
        calls.append(record)
        if len(calls) == 1:
            return None
        return valid_result(record)

    buffer = LiveVoiceObservabilityExporterBuffer(
        mixed_exporter,
        capacity=2,  # type: ignore[arg-type]
    )
    records: list[ExportRecord] = [
        _observation("event-invalid-exporter"),
        _metric("metric-after-invalid-exporter"),
    ]
    await buffer.start()
    buffer.emit_observation(records[0])  # type: ignore[arg-type]
    buffer.emit_metric(records[1])  # type: ignore[arg-type]

    closed = await buffer.close()
    assert calls == records
    assert delivered == [records[1]]
    assert closed.last_failure_kind == "invalid_awaitable"
    assert closed.stats.attempted_records == 2
    assert closed.stats.failed_records == 1
    assert closed.stats.delivered_records == 1
    assert closed.stats.failed_observations == 1
    assert closed.stats.delivered_metrics == 1
