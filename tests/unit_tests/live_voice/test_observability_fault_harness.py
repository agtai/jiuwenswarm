# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio

import pytest

from jiuwenswarm.server.live_voice.observability import (
    OBSERVABILITY_SCHEMA_VERSION,
    LiveVoiceMetric,
    LiveVoiceObservation,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.observability_fault_harness import (
    MAX_OBSERVABILITY_FAULT_STEPS,
    DisabledObservabilityFaultHarness,
    InjectedObservabilityExportError,
    LiveVoiceObservabilityFaultHarness,
    ObservabilityFaultAction,
    ObservabilityFaultHarnessState,
    ObservabilityFaultOutcome,
    ObservabilityFaultScriptExhaustedError,
    create_observability_fault_harness,
)
from jiuwenswarm.server.live_voice.product_composition_contract import (
    ProductEvidenceId,
    ProductRouteFact,
    ProductRouteReason,
    ProductRouteTruth,
    ProductSegment,
)
from jiuwenswarm.server.live_voice.product_composition_root import (
    ProductCompositionContext,
)
from jiuwenswarm.server.live_voice.product_observability_adapter import (
    ActiveProductObservabilityActivation,
    ProductObservabilityActivationEvidence,
    ProductObservabilityLeaseState,
    ProductObservabilityReason,
    activate_product_observability_adapter,
)


CONTEXT = ProductCompositionContext(
    session_id="session-xobs-fault",
    correlation_id="correlation-xobs-fault",
)


def _route(implementation_class: str = "fallback") -> dict[str, object]:
    reasons = {
        "fallback": "ROUTE_FALLBACK",
        "demo_substitute": "DEMO_SUBSTITUTE",
        "unsupported": "UNSUPPORTED_CAPABILITY",
        "unknown": "UNKNOWN_PROVENANCE",
    }
    return {
        "implementation_class": implementation_class,
        "owner_module": (
            None if implementation_class == "unknown" else "route.compatibility"
        ),
        "capability_provider": None,
        "contract_version": None,
        "reason_code": reasons[implementation_class],
    }


def _observation(
    event_id: str,
    *,
    correlation_id: str = CONTEXT.correlation_id,
    implementation_class: str = "fallback",
) -> LiveVoiceObservation:
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": event_id,
            "event_name": "route.selected",
            "segment_name": "route.fallback",
            "observed_at": "2026-08-07T09:00:00Z",
            "monotonic_ms": 100.0,
            "binding": {"correlation_id": correlation_id},
            "route": _route(implementation_class),
            "source_component": "xobs.fault.test",
            "reason_code": _route(implementation_class)["reason_code"],
        }
    )


def _metric(measurement_id: str) -> LiveVoiceMetric:
    return create_metric(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "measurement_id": measurement_id,
            "metric_name": "live_voice.degradation_total",
            "metric_kind": "counter",
            "unit": "count",
            "value": 1,
            "observed_at": "2026-08-07T09:00:00Z",
            "binding": {"correlation_id": CONTEXT.correlation_id},
            "route": _route(),
            "segment_name": "system.degradation",
            "implementation_class": "fallback",
            "reason_code": "DEGRADED",
        }
    )


def _formal_route_issuer(
    evidence: ProductObservabilityActivationEvidence,
) -> ProductRouteFact:
    # Contract-only stand-in for Main's authority-gated issuer.  This is not a
    # product registration, real backend, or runtime evidence claim.
    assert type(evidence) is ProductObservabilityActivationEvidence
    assert evidence.session_id == CONTEXT.session_id
    assert evidence.correlation_id == CONTEXT.correlation_id
    assert evidence.worker_started is evidence.lease_open is True
    return ProductRouteFact(
        segment=ProductSegment.OBSERVABILITY,
        truth=ProductRouteTruth.FORMAL,
        reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
        evidence_ids=(
            ProductEvidenceId.TRUSTED_AUTHORITY_RESOLVED,
            ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
            ProductEvidenceId.RUNTIME_PATH_OBSERVED,
        ),
        formal_runtime_observed=True,
    )


async def _activate(
    harness: LiveVoiceObservabilityFaultHarness,
    *,
    capacity: int = 4,
    export_timeout_seconds: float = 1.0,
) -> ActiveProductObservabilityActivation:
    activation = await activate_product_observability_adapter(
        enabled=True,
        context=CONTEXT,
        exporter=harness.exporter,
        formal_route_fact_issuer=_formal_route_issuer,
        capacity=capacity,
        export_timeout_seconds=export_timeout_seconds,
        close_timeout_seconds=1.0,
    )
    assert type(activation) is ActiveProductObservabilityActivation
    return activation


async def _wait_for_stalls(
    harness: LiveVoiceObservabilityFaultHarness, count: int = 1
) -> None:
    for _ in range(100):
        if harness.snapshot().active_stalls == count:
            return
        await asyncio.sleep(0)
    raise AssertionError("fault harness did not reach the expected stalled state")


@pytest.mark.asyncio
async def test_feature_off_ignores_injected_input_and_creates_no_async_resource() -> (
    None
):
    class ExplosiveScript:
        def __iter__(self) -> object:
            raise AssertionError("disabled harness inspected injected script")

        def __len__(self) -> int:
            raise AssertionError("disabled harness inspected injected script")

    before = set(asyncio.all_tasks())
    first = create_observability_fault_harness(enabled=False, script=ExplosiveScript())
    second = create_observability_fault_harness(script=object())

    assert first is second
    assert type(first) is DisabledObservabilityFaultHarness
    assert first.exporter is None
    assert first.snapshot().state is ObservabilityFaultHarnessState.DISABLED
    assert first.snapshot().retained_attempts == 0
    assert set(asyncio.all_tasks()) == before


def test_enabled_script_is_exact_fixed_and_bounded() -> None:
    with pytest.raises(TypeError, match="exact tuple"):
        create_observability_fault_harness(
            enabled=True, script=[ObservabilityFaultAction.DELIVER]
        )
    with pytest.raises(TypeError, match="ObservabilityFaultAction"):
        create_observability_fault_harness(enabled=True, script=("deliver",))
    with pytest.raises(ValueError, match="between one and sixteen"):
        create_observability_fault_harness(enabled=True, script=())
    with pytest.raises(ValueError, match="between one and sixteen"):
        create_observability_fault_harness(
            enabled=True,
            script=(ObservabilityFaultAction.DELIVER,)
            * (MAX_OBSERVABILITY_FAULT_STEPS + 1),
        )


@pytest.mark.asyncio
async def test_deliver_raise_release_and_cancel_use_one_script_step_each() -> None:
    created = create_observability_fault_harness(
        enabled=True,
        script=(
            ObservabilityFaultAction.DELIVER,
            ObservabilityFaultAction.RAISE,
            ObservabilityFaultAction.STALL,
            ObservabilityFaultAction.STALL,
        ),
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    harness = created

    await harness(_observation("event-delivered"))
    with pytest.raises(InjectedObservabilityExportError, match="was injected"):
        await harness(_metric("metric-raised"))

    released = asyncio.create_task(harness(_observation("event-released")))
    await _wait_for_stalls(harness)
    release_id = harness.snapshot().attempts[-1].attempt_id
    assert harness.release_stall(release_id) is True
    assert harness.release_stall(release_id) is False
    await released

    cancelled = asyncio.create_task(harness(_observation("event-cancelled")))
    await _wait_for_stalls(harness)
    cancel_id = harness.snapshot().attempts[-1].attempt_id
    assert harness.cancel_stall(cancel_id) is True
    assert harness.cancel_stall(cancel_id) is False
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    snapshot = harness.snapshot()
    assert snapshot.state is ObservabilityFaultHarnessState.EXHAUSTED
    assert snapshot.consumed_steps == snapshot.retained_attempts == 4
    assert snapshot.delivered_attempts == 2
    assert snapshot.raised_attempts == 1
    assert snapshot.cancelled_attempts == 1
    assert snapshot.active_stalls == 0
    assert tuple(attempt.outcome for attempt in snapshot.attempts) == (
        ObservabilityFaultOutcome.DELIVERED,
        ObservabilityFaultOutcome.RAISED,
        ObservabilityFaultOutcome.DELIVERED,
        ObservabilityFaultOutcome.CANCELLED,
    )
    assert snapshot.business_result_changed is False
    assert snapshot.lifecycle_authority_exercised is False
    assert snapshot.cancel_authority_exercised is False
    assert snapshot.success_authority_exercised is False


@pytest.mark.asyncio
async def test_sixteen_concurrent_stalls_keep_unique_non_evicting_attempt_facts() -> (
    None
):
    created = create_observability_fault_harness(
        enabled=True,
        script=(ObservabilityFaultAction.STALL,) * MAX_OBSERVABILITY_FAULT_STEPS,
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    harness = created
    attempts = tuple(
        asyncio.create_task(harness(_observation(f"event-concurrent-{index}")))
        for index in range(MAX_OBSERVABILITY_FAULT_STEPS)
    )
    await _wait_for_stalls(harness, MAX_OBSERVABILITY_FAULT_STEPS)

    before_overflow = harness.snapshot()
    attempt_ids = tuple(attempt.attempt_id for attempt in before_overflow.attempts)
    assert len(attempt_ids) == len(set(attempt_ids)) == MAX_OBSERVABILITY_FAULT_STEPS
    assert before_overflow.retained_attempts == MAX_OBSERVABILITY_FAULT_STEPS
    assert before_overflow.active_stalls == MAX_OBSERVABILITY_FAULT_STEPS

    with pytest.raises(ObservabilityFaultScriptExhaustedError, match="exhausted"):
        await harness(_observation("event-concurrent-overflow"))
    after_overflow = harness.snapshot()
    assert after_overflow.attempts == before_overflow.attempts
    assert after_overflow.consumed_steps == MAX_OBSERVABILITY_FAULT_STEPS
    assert after_overflow.retained_attempts == MAX_OBSERVABILITY_FAULT_STEPS
    assert after_overflow.rejected_exhausted == 1

    for index, attempt_id in enumerate(attempt_ids):
        if index % 2 == 0:
            assert harness.release_stall(attempt_id) is True
        else:
            assert harness.cancel_stall(attempt_id) is True
    results = await asyncio.gather(*attempts, return_exceptions=True)

    assert sum(result is None for result in results) == 8
    assert sum(isinstance(result, asyncio.CancelledError) for result in results) == 8
    settled = harness.snapshot()
    assert settled.state is ObservabilityFaultHarnessState.EXHAUSTED
    assert settled.active_stalls == 0
    assert settled.retained_attempts == MAX_OBSERVABILITY_FAULT_STEPS
    assert settled.delivered_attempts == 8
    assert settled.cancelled_attempts == 8
    assert settled.raised_attempts == 0
    assert tuple(attempt.attempt_id for attempt in settled.attempts) == attempt_ids


@pytest.mark.asyncio
async def test_capacity_exhaustion_does_not_evict_overwrite_or_retry() -> None:
    created = create_observability_fault_harness(
        enabled=True,
        script=(ObservabilityFaultAction.DELIVER,) * MAX_OBSERVABILITY_FAULT_STEPS,
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    harness = created

    for index in range(MAX_OBSERVABILITY_FAULT_STEPS):
        await harness(_observation(f"event-capacity-{index}"))
    before = harness.snapshot()
    with pytest.raises(ObservabilityFaultScriptExhaustedError, match="exhausted"):
        await harness(_observation("event-overflow"))
    after = harness.snapshot()

    assert after.retained_attempts == MAX_OBSERVABILITY_FAULT_STEPS
    assert after.attempts == before.attempts
    assert after.rejected_exhausted == 1
    assert tuple(attempt.attempt_id for attempt in after.attempts) == tuple(
        f"xobs-fault-attempt-{index:02d}"
        for index in range(MAX_OBSERVABILITY_FAULT_STEPS)
    )


@pytest.mark.asyncio
async def test_invalid_record_rejects_without_consuming_a_script_step() -> None:
    created = create_observability_fault_harness(
        enabled=True, script=(ObservabilityFaultAction.DELIVER,)
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness

    with pytest.raises(TypeError, match="exact observability records"):
        await created(object())  # type: ignore[arg-type]
    rejected = created.snapshot()
    assert rejected.consumed_steps == rejected.retained_attempts == 0
    assert rejected.rejected_invalid_records == 1

    await created(_observation("event-after-invalid"))
    assert created.snapshot().delivered_attempts == 1


@pytest.mark.asyncio
async def test_adapter_rejects_context_correlation_and_private_fact_before_harness() -> (
    None
):
    created = create_observability_fault_harness(
        enabled=True, script=(ObservabilityFaultAction.DELIVER,)
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    activation = await _activate(created)
    equal_but_unowned_context = ProductCompositionContext(
        session_id=CONTEXT.session_id,
        correlation_id=CONTEXT.correlation_id,
    )

    wrong_context = activation.adapter.consume_observation(
        context=equal_but_unowned_context,
        observation=_observation("event-wrong-context"),
    )
    wrong_correlation = activation.adapter.consume_observation(
        context=CONTEXT,
        observation=_observation(
            "event-wrong-correlation", correlation_id="correlation-other"
        ),
    )
    private_observation = _observation("event-private")
    object.__setattr__(private_observation, "source_component", "transcript")
    private_fact = activation.adapter.consume_observation(
        context=CONTEXT,
        observation=private_observation,
    )

    assert (
        wrong_context.reason_id is ProductObservabilityReason.CONTEXT_BINDING_MISMATCH
    )
    assert (
        wrong_correlation.reason_id is ProductObservabilityReason.CORRELATION_MISMATCH
    )
    assert private_fact.reason_id is ProductObservabilityReason.PRIVATE_CONTENT_REJECTED
    assert created.snapshot().retained_attempts == 0

    accepted = activation.adapter.consume_observation(
        context=CONTEXT,
        observation=_observation("event-public"),
    )
    assert accepted.reason_id is ProductObservabilityReason.ACCEPTED_FOR_EXPORT
    closed = await activation.lease.close_with_result()
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert created.snapshot().retained_attempts == 1


@pytest.mark.asyncio
async def test_nonformal_source_route_is_not_retained_or_upgraded_by_harness() -> None:
    for implementation_class in (
        "fallback",
        "demo_substitute",
        "unsupported",
        "unknown",
    ):
        created = create_observability_fault_harness(
            enabled=True, script=(ObservabilityFaultAction.DELIVER,)
        )
        assert type(created) is LiveVoiceObservabilityFaultHarness
        activation = await _activate(created)
        event_id = f"event-source-{implementation_class}"
        observation = _observation(event_id, implementation_class=implementation_class)

        accepted = activation.adapter.consume_observation(
            context=CONTEXT, observation=observation
        )
        assert accepted.accepted_for_export is True
        closed = await activation.lease.close_with_result()
        assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
        assert observation.route.implementation_class == implementation_class

        snapshot = created.snapshot()
        rendered = repr(snapshot)
        assert snapshot.retained_attempts == snapshot.delivered_attempts == 1
        assert snapshot.attempts[0].record_kind == "observation"
        assert event_id not in rendered
        assert CONTEXT.session_id not in rendered
        assert CONTEXT.correlation_id not in rendered
        assert implementation_class not in rendered


@pytest.mark.asyncio
async def test_slow_export_keeps_backpressure_diagnostic_and_has_no_hidden_retry() -> (
    None
):
    created = create_observability_fault_harness(
        enabled=True, script=(ObservabilityFaultAction.STALL,)
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    activation = await _activate(created, capacity=1)

    first = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-inflight")
    )
    assert first.accepted_for_export is True
    await _wait_for_stalls(created)
    second = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-backpressured")
    )
    assert second.reason_id is ProductObservabilityReason.EXPORT_BACKPRESSURED
    assert created.snapshot().retained_attempts == 1

    attempt_id = created.snapshot().attempts[0].attempt_id
    assert created.release_stall(attempt_id) is True
    closed = await activation.lease.close_with_result()
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.exporter.stats.attempted_records == 1
    assert closed.exporter.stats.delivered_records == 1
    assert created.snapshot().retained_attempts == 1


@pytest.mark.asyncio
async def test_injected_raise_is_one_failed_attempt_without_business_rewrite() -> None:
    created = create_observability_fault_harness(
        enabled=True, script=(ObservabilityFaultAction.RAISE,)
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    activation = await _activate(created)

    accepted = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-raised-on-export")
    )
    assert accepted.accepted_for_export is True
    closed = await activation.lease.close_with_result()

    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.exporter.stats.accepted_records == 1
    assert closed.exporter.stats.attempted_records == 1
    assert closed.exporter.stats.failed_records == 1
    assert closed.exporter.stats.delivered_records == 0
    assert created.snapshot().raised_attempts == 1
    assert activation.adapter.snapshot().business_result_changed is False


@pytest.mark.asyncio
async def test_stall_uses_existing_export_timeout_without_retry_or_payload_retention() -> (
    None
):
    created = create_observability_fault_harness(
        enabled=True, script=(ObservabilityFaultAction.STALL,)
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    activation = await _activate(created, export_timeout_seconds=0.01)

    accepted = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-export-timeout")
    )
    assert accepted.accepted_for_export is True
    closed = await activation.lease.close_with_result(timeout_seconds=1.0)

    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.exporter.stats.accepted_records == 1
    assert closed.exporter.stats.attempted_records == 1
    assert closed.exporter.stats.failed_records == 1
    assert closed.exporter.stats.timed_out_records == 1
    assert closed.exporter.stats.delivered_records == 0
    snapshot = created.snapshot()
    assert snapshot.retained_attempts == snapshot.cancelled_attempts == 1
    assert "event-export-timeout" not in repr(snapshot)


@pytest.mark.asyncio
async def test_explicit_stall_cancel_after_close_begins_finishes_worker_cleanly() -> (
    None
):
    created = create_observability_fault_harness(
        enabled=True, script=(ObservabilityFaultAction.STALL,)
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    activation = await _activate(created)
    accepted = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-explicit-cancel")
    )
    assert accepted.accepted_for_export is True
    await _wait_for_stalls(created)
    attempt_id = created.snapshot().attempts[0].attempt_id

    close = asyncio.create_task(activation.lease.close_with_result(timeout_seconds=1.0))
    for _ in range(100):
        closing = activation.adapter.snapshot()
        if (
            closing.lease_state is ProductObservabilityLeaseState.CLOSING
            and closing.exporter.state == "closing"
        ):
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("product observability lease did not begin closing")

    assert created.cancel_stall(attempt_id) is True
    closed = await close
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.exporter.state == "closed"
    assert closed.exporter.worker_running is False
    assert closed.exporter.attempt_running is False
    assert closed.exporter.last_failure_kind == "cancelled"
    assert closed.exporter.stats.accepted_records == 1
    assert closed.exporter.stats.attempted_records == 1
    assert closed.exporter.stats.failed_records == 1
    assert closed.exporter.stats.delivered_records == 0
    assert closed.exporter.stats.worker_failures == 0

    harness_snapshot = created.snapshot()
    assert harness_snapshot.retained_attempts == 1
    assert harness_snapshot.cancelled_attempts == 1
    assert harness_snapshot.active_stalls == 0
    assert harness_snapshot.business_result_changed is False
    assert harness_snapshot.lifecycle_authority_exercised is False
    assert harness_snapshot.cancel_authority_exercised is False
    assert harness_snapshot.success_authority_exercised is False
    adapter_snapshot = activation.adapter.snapshot()
    assert adapter_snapshot.lease_state is ProductObservabilityLeaseState.CLOSED
    assert adapter_snapshot.business_result_changed is False
    assert adapter_snapshot.lifecycle_authority_exercised is False
    assert adapter_snapshot.cancel_authority_exercised is False
    assert adapter_snapshot.success_authority_exercised is False


@pytest.mark.asyncio
async def test_cancelled_close_waiter_preserves_stalled_attempt_and_retained_worker() -> (
    None
):
    created = create_observability_fault_harness(
        enabled=True, script=(ObservabilityFaultAction.STALL,)
    )
    assert type(created) is LiveVoiceObservabilityFaultHarness
    activation = await _activate(created)
    accepted = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-retained-stall")
    )
    assert accepted.accepted_for_export is True
    await _wait_for_stalls(created)
    attempt = created.snapshot().attempts[0]

    close_waiter = asyncio.create_task(
        activation.lease.close_with_result(timeout_seconds=10.0)
    )
    await asyncio.sleep(0)
    close_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_waiter

    retained = activation.adapter.snapshot()
    assert retained.lease_state is ProductObservabilityLeaseState.CLOSING
    assert retained.exporter.state == "closing"
    assert retained.exporter.worker_running is True
    assert created.snapshot().attempts == (attempt,)
    assert created.snapshot().active_stalls == 1

    assert created.release_stall(attempt.attempt_id) is True
    closed = await activation.lease.close_with_result(timeout_seconds=1.0)
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.retained_for_retry is False
    assert created.snapshot().retained_attempts == 1
    assert created.snapshot().delivered_attempts == 1
