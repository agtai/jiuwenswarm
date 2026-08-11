# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import functools
import inspect
import math
from collections.abc import Awaitable, Callable

import pytest

from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    LiveVoiceMetric,
    LiveVoiceObservation,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.observability_exporter import (
    ExportRecord,
    LiveVoiceObservabilityExporterBuffer,
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
    ProductCompositionLeaseCloseError,
    ProductCompositionRegistration,
    ProductCompositionRoot,
    ProductSegmentActivation,
)
from jiuwenswarm.server.live_voice.product_observability_adapter import (
    ActiveProductObservabilityActivation,
    InactiveProductObservabilityActivation,
    ProductObservabilityActivationError,
    ProductObservabilityActivationEvidence,
    ProductObservabilityAdapter,
    ProductObservabilityCloseResult,
    ProductObservabilityLease,
    ProductObservabilityLeaseCloseError,
    ProductObservabilityLeaseState,
    ProductObservabilityReason,
    UnavailableProductObservabilityActivation,
    activate_product_observability_adapter,
)

CONTEXT = ProductCompositionContext("session-observability", "corr-observability")


def _route(implementation_class: str = "formal") -> dict[str, object]:
    if implementation_class == "formal":
        return {
            "implementation_class": "formal",
            "owner_module": "runtime.conversation",
            "capability_provider": "jiuwenswarm-runtime",
            "contract_version": LIVE_VOICE_CONTRACT_VERSION,
            "reason_code": None,
        }
    reason = {
        "fallback": "ROUTE_FALLBACK",
        "demo_substitute": "DEMO_SUBSTITUTE",
        "unsupported": "UNSUPPORTED_CAPABILITY",
        "unknown": "UNKNOWN_PROVENANCE",
    }[implementation_class]
    return {
        "implementation_class": implementation_class,
        "owner_module": (
            None if implementation_class == "unknown" else "route.compatibility"
        ),
        "capability_provider": None,
        "contract_version": None,
        "reason_code": reason,
    }


def _formal_observability_route_fact() -> ProductRouteFact:
    # Contract-only issuer output; this is not real product runtime evidence.
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


def _formal_observability_route_issuer(
    evidence: ProductObservabilityActivationEvidence,
) -> ProductRouteFact:
    # Simulates Main's authority-gated issuer after leaf-owned worker/lease proof.
    assert type(evidence) is ProductObservabilityActivationEvidence
    assert evidence.session_id
    assert evidence.correlation_id
    assert type(evidence.lease) is ProductObservabilityLease
    assert evidence.lease._exporter_buffer.snapshot().state == "running"
    assert evidence.lease._exporter_buffer.snapshot().worker_running is True
    assert evidence.segment is ProductSegment.OBSERVABILITY
    assert evidence.worker_started is evidence.lease_open is True
    return _formal_observability_route_fact()


def _formal_authority_route_fact() -> ProductRouteFact:
    return ProductRouteFact(
        segment=ProductSegment.AUTHORITY,
        truth=ProductRouteTruth.FORMAL,
        reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
        evidence_ids=(
            ProductEvidenceId.TRUSTED_AUTHORITY_RESOLVED,
            ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
            ProductEvidenceId.RUNTIME_PATH_OBSERVED,
        ),
        formal_runtime_observed=True,
    )


def _observation(
    event_id: str,
    *,
    correlation_id: str = CONTEXT.correlation_id,
    implementation_class: str = "formal",
) -> LiveVoiceObservation:
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": event_id,
            "event_name": "segment.started",
            "segment_name": "runtime.turn",
            "observed_at": "2026-08-06T09:00:00Z",
            "monotonic_ms": 1_000.0,
            "binding": {
                "correlation_id": correlation_id,
                "interaction_id": "interaction-observability",
                "turn_id": "turn-observability",
            },
            "route": _route(implementation_class),
            "source_component": "product.observability.test",
        }
    )


def _metric(
    measurement_id: str, *, correlation_id: str = CONTEXT.correlation_id
) -> LiveVoiceMetric:
    return create_metric(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "measurement_id": measurement_id,
            "metric_name": "live_voice.queue_depth",
            "metric_kind": "gauge",
            "unit": "items",
            "value": 1,
            "observed_at": "2026-08-06T09:00:00Z",
            "binding": {"correlation_id": correlation_id},
            "route": _route(),
            "segment_name": "runtime.queue",
            "implementation_class": "formal",
        }
    )


def _observation_with_unreviewed_contract(
    event_id: str, contract_version: str
) -> LiveVoiceObservation:
    route = {
        "implementation_class": "fallback",
        "owner_module": "route.compatibility",
        "capability_provider": None,
        "contract_version": contract_version,
        "reason_code": "ROUTE_FALLBACK",
    }
    value = _observation(event_id).to_dict()
    value["route"] = route
    return create_observation(value)


async def _activate(
    exporter: Callable[[ExportRecord], Awaitable[None]],
    **options: object,
) -> ActiveProductObservabilityActivation:
    activation = await activate_product_observability_adapter(
        enabled=True,
        context=CONTEXT,
        exporter=exporter,
        formal_route_fact_issuer=_formal_observability_route_issuer,
        **options,  # type: ignore[arg-type]
    )
    assert isinstance(activation, ActiveProductObservabilityActivation)
    return activation


@pytest.mark.asyncio
async def test_positive_public_facts_are_copied_into_one_explicit_worker() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    activation = await _activate(exporter, capacity=2)
    segment_activation = ProductSegmentActivation(
        activation.route_fact, activation.lease
    )
    observation = _observation("event-product-positive")
    metric = _metric("metric-product-positive")

    observation_result = activation.adapter.consume_observation(
        context=CONTEXT, observation=observation
    )
    metric_result = activation.adapter.consume_metric(context=CONTEXT, metric=metric)
    closed = await activation.lease.close_with_result()

    assert (
        observation_result.reason_id is ProductObservabilityReason.ACCEPTED_FOR_EXPORT
    )
    assert metric_result.accepted_for_export is True
    assert all(
        not result.business_result_changed
        and not result.lifecycle_authority_exercised
        and not result.cancel_authority_exercised
        and not result.success_authority_exercised
        for result in (observation_result, metric_result)
    )
    assert exported == [observation, metric]
    assert exported[0] is not observation
    assert exported[1] is not metric
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.retained_for_retry is False
    assert activation.route_fact.segment is ProductSegment.OBSERVABILITY
    assert activation.route_fact.truth is ProductRouteTruth.FORMAL
    assert activation.route_fact.reason_id is ProductRouteReason.FORMAL_ROUTE_OBSERVED
    assert activation.route_fact.evidence_ids == (
        ProductEvidenceId.TRUSTED_AUTHORITY_RESOLVED,
        ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
        ProductEvidenceId.RUNTIME_PATH_OBSERVED,
    )
    assert activation.route_fact.formal_runtime_observed is True
    assert activation.worker_started is True
    assert segment_activation.lease is activation.lease


@pytest.mark.asyncio
async def test_async_callable_object_is_an_explicit_supported_exporter() -> None:
    class AsyncCallableExporter:
        def __init__(self) -> None:
            self.records: list[ExportRecord] = []

        async def __call__(self, record: ExportRecord) -> None:
            self.records.append(record)

    exporter = AsyncCallableExporter()
    activation = await _activate(exporter)
    observation = _observation("event-async-callable-exporter")

    disposition = activation.adapter.consume_observation(
        context=CONTEXT, observation=observation
    )
    closed = await activation.lease.close_with_result()

    assert disposition.accepted_for_export is True
    assert exporter.records == [observation]
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED


@pytest.mark.asyncio
async def test_bound_async_method_and_partial_remain_supported_exporters() -> None:
    class ExporterOwner:
        def __init__(self) -> None:
            self.records: list[ExportRecord] = []

        async def export(self, record: ExportRecord) -> None:
            self.records.append(record)

    owner = ExporterOwner()
    exporters = (owner.export, functools.partial(owner.export))

    for index, exporter in enumerate(exporters):
        activation = await _activate(exporter)
        result = activation.adapter.consume_observation(
            context=CONTEXT,
            observation=_observation(f"event-async-exporter-form-{index}"),
        )
        closed = await activation.lease.close_with_result()
        assert result.accepted_for_export is True
        assert closed.lease_state is ProductObservabilityLeaseState.CLOSED

    assert len(owner.records) == len(exporters)


@pytest.mark.asyncio
async def test_formal_observer_preserves_nonformal_source_route_identity() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    activation = await _activate(exporter)
    source_classes = ("fallback", "demo_substitute", "unsupported", "unknown")

    results = tuple(
        activation.adapter.consume_observation(
            context=CONTEXT,
            observation=_observation(
                f"event-source-route-{route_class}",
                implementation_class=route_class,
            ),
        )
        for route_class in source_classes
    )
    closed = await activation.lease.close_with_result()

    assert all(result.accepted_for_export for result in results)
    assert tuple(record.route.implementation_class for record in exported) == (
        source_classes
    )
    assert all(record.route.implementation_class != "formal" for record in exported)
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED


@pytest.mark.asyncio
async def test_feature_off_inspects_calls_and_allocates_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Poison:
        def __getattribute__(self, _: str) -> object:
            raise AssertionError("feature-off inspected an injected object")

        def __call__(self, _: object) -> object:
            raise AssertionError("feature-off called the exporter")

    def reject_allocation(*_: object, **__: object) -> object:
        raise AssertionError("feature-off allocated an exporter buffer")

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_observability_adapter."
        "LiveVoiceObservabilityExporterBuffer",
        reject_allocation,
    )

    activation = await activate_product_observability_adapter(
        enabled=False,
        context=_Poison(),
        exporter=_Poison(),
        formal_route_fact_issuer=_Poison(),
    )

    assert isinstance(activation, InactiveProductObservabilityActivation)
    assert activation.active is False
    assert activation.adapter is activation.lease is None
    assert activation.worker_started is False
    assert activation.route_fact.truth is ProductRouteTruth.DISABLED
    assert activation.route_fact.reason_id is ProductRouteReason.FEATURE_DISABLED
    assert activation.route_fact.evidence_ids == (ProductEvidenceId.FEATURE_FLAG_OFF,)

    default_activation = await activate_product_observability_adapter()
    assert isinstance(default_activation, InactiveProductObservabilityActivation)


@pytest.mark.asyncio
async def test_missing_issuer_or_incompatible_dependencies_start_no_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Poison:
        def __getattribute__(self, _: str) -> object:
            raise AssertionError("unavailable activation inspected a dependency")

        def __call__(self, _: object) -> object:
            raise AssertionError("unavailable activation called a dependency")

    class _SyncPoisonExporter:
        calls = 0

        def __call__(self, _: ExportRecord) -> Awaitable[None]:
            self.calls += 1
            raise AssertionError("sync exporter was invoked")

    async def async_issuer(
        _: ProductObservabilityActivationEvidence,
    ) -> ProductRouteFact:
        raise AssertionError("unsupported async issuer was invoked")

    async def async_exporter(_: ExportRecord) -> None:
        raise AssertionError("pre-allocation exporter was invoked")

    def reject_allocation(*_: object, **__: object) -> object:
        raise AssertionError("unavailable activation allocated an exporter buffer")

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_observability_adapter."
        "LiveVoiceObservabilityExporterBuffer",
        reject_allocation,
    )
    sync_poison = _SyncPoisonExporter()

    missing = await activate_product_observability_adapter(
        enabled=True,
        context=_Poison(),
        exporter=_Poison(),
    )
    async_issuer_result = await activate_product_observability_adapter(
        enabled=True,
        context=_Poison(),
        exporter=_Poison(),
        formal_route_fact_issuer=async_issuer,
    )
    preissued_final_fact = await activate_product_observability_adapter(
        enabled=True,
        context=_Poison(),
        exporter=_Poison(),
        formal_route_fact_issuer=_formal_observability_route_fact(),
    )
    sync_exporter_result = await activate_product_observability_adapter(
        enabled=True,
        context=_Poison(),
        exporter=sync_poison,
        formal_route_fact_issuer=_formal_observability_route_issuer,
    )
    invalid_context = await activate_product_observability_adapter(
        enabled=True,
        context=object(),
        exporter=async_exporter,
        formal_route_fact_issuer=_formal_observability_route_issuer,
    )
    missing_exporter = await activate_product_observability_adapter(
        enabled=True,
        context=_Poison(),
        exporter=None,
        formal_route_fact_issuer=_formal_observability_route_issuer,
    )

    for activation in (
        missing,
        async_issuer_result,
        preissued_final_fact,
        sync_exporter_result,
        invalid_context,
        missing_exporter,
    ):
        assert isinstance(activation, UnavailableProductObservabilityActivation)
        assert activation.active is False
        assert activation.adapter is activation.lease is None
        assert activation.worker_started is False
        assert activation.route_fact.truth is ProductRouteTruth.UNAVAILABLE
        assert (
            activation.route_fact.reason_id
            is ProductRouteReason.OBSERVABILITY_CONSUMER_UNAVAILABLE
        )
        # The result can enter ProductCompositionRoot without violating the
        # invariant that nonformal segments retain no effects.
        segment = ProductSegmentActivation(activation.route_fact, activation.lease)
        assert segment.lease is None
    assert sync_poison.calls == 0


@pytest.mark.asyncio
async def test_marked_sync_exporter_is_rejected_before_every_activation_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter_calls: list[ExportRecord] = []
    issuer_calls: list[ProductObservabilityActivationEvidence] = []

    def marked_sync_exporter(record: ExportRecord) -> Awaitable[None]:
        exporter_calls.append(record)

        async def completion() -> None:
            return None

        return completion()

    marker = getattr(inspect, "markcoroutinefunction", None)
    if marker is not None:
        marked_sync_exporter = marker(marked_sync_exporter)
        marker_detector = inspect.iscoroutinefunction
    else:
        # Python 3.11 supports the legacy marker through asyncio while
        # ``inspect.markcoroutinefunction`` is only available from 3.12.
        setattr(marked_sync_exporter, "_is_coroutine", asyncio.coroutines._is_coroutine)
        marker_detector = asyncio.iscoroutinefunction

    def issuer(evidence: ProductObservabilityActivationEvidence) -> ProductRouteFact:
        issuer_calls.append(evidence)
        return _formal_observability_route_fact()

    def reject_allocation(*_: object, **__: object) -> object:
        raise AssertionError("marked sync exporter allocated a buffer or worker")

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_observability_adapter."
        "LiveVoiceObservabilityExporterBuffer",
        reject_allocation,
    )

    assert marker_detector(marked_sync_exporter) is True
    assert marked_sync_exporter.__code__.co_flags & inspect.CO_COROUTINE == 0

    activation = await activate_product_observability_adapter(
        enabled=True,
        context=CONTEXT,
        exporter=marked_sync_exporter,
        formal_route_fact_issuer=issuer,
    )

    assert isinstance(activation, UnavailableProductObservabilityActivation)
    assert activation.adapter is activation.lease is None
    assert activation.worker_started is False
    assert activation.route_fact.truth is ProductRouteTruth.UNAVAILABLE
    assert exporter_calls == []
    assert issuer_calls == []


@pytest.mark.asyncio
async def test_spoofed_instance_code_is_rejected_before_every_activation_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def native_async_template(_: ExportRecord) -> None:
        return None

    class SpoofedSyncExporter:
        __code__ = native_async_template.__code__

        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, _: ExportRecord) -> Awaitable[None]:
            self.calls += 1

            async def completion() -> None:
                return None

            return completion()

    issuer_calls: list[ProductObservabilityActivationEvidence] = []
    exporter = SpoofedSyncExporter()

    def issuer(evidence: ProductObservabilityActivationEvidence) -> ProductRouteFact:
        issuer_calls.append(evidence)
        return _formal_observability_route_fact()

    def reject_allocation(*_: object, **__: object) -> object:
        raise AssertionError("spoofed sync exporter allocated a buffer or worker")

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_observability_adapter."
        "LiveVoiceObservabilityExporterBuffer",
        reject_allocation,
    )

    assert exporter.__code__ is native_async_template.__code__
    assert exporter.__code__.co_flags & inspect.CO_COROUTINE

    activation = await activate_product_observability_adapter(
        enabled=True,
        context=CONTEXT,
        exporter=exporter,
        formal_route_fact_issuer=issuer,
    )

    assert isinstance(activation, UnavailableProductObservabilityActivation)
    assert activation.adapter is activation.lease is None
    assert activation.worker_started is False
    assert activation.route_fact.truth is ProductRouteTruth.UNAVAILABLE
    assert exporter.calls == 0
    assert issuer_calls == []


@pytest.mark.asyncio
async def test_invalid_post_start_evidence_closes_worker_before_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffers: list[LiveVoiceObservabilityExporterBuffer] = []
    exported: list[ExportRecord] = []

    def tracking_buffer(**options: object) -> LiveVoiceObservabilityExporterBuffer:
        buffer = LiveVoiceObservabilityExporterBuffer(**options)  # type: ignore[arg-type]
        buffers.append(buffer)
        return buffer

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    nonformal = ProductRouteFact(
        segment=ProductSegment.OBSERVABILITY,
        truth=ProductRouteTruth.UNAVAILABLE,
        reason_id=ProductRouteReason.OBSERVABILITY_CONSUMER_UNAVAILABLE,
        evidence_ids=(
            ProductEvidenceId.OBSERVABILITY_FOUNDATION,
            ProductEvidenceId.PACKAGE_CONTRACT_ONLY,
            ProductEvidenceId.NO_RUNTIME_EVIDENCE,
        ),
    )
    corrupted = _formal_observability_route_fact()
    object.__setattr__(corrupted, "evidence_ids", ())

    def raise_issuer(_: ProductObservabilityActivationEvidence) -> ProductRouteFact:
        raise RuntimeError("injected authority issuer failure")

    issuers = (
        lambda _: nonformal,
        lambda _: _formal_authority_route_fact(),
        lambda _: corrupted,
        raise_issuer,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_observability_adapter."
        "LiveVoiceObservabilityExporterBuffer",
        tracking_buffer,
    )

    activations = tuple(
        [
            await activate_product_observability_adapter(
                enabled=True,
                context=CONTEXT,
                exporter=exporter,
                formal_route_fact_issuer=issuer,
            )
            for issuer in issuers
        ]
    )

    assert all(
        isinstance(item, UnavailableProductObservabilityActivation)
        and item.lease is None
        and item.worker_started is False
        for item in activations
    )
    assert len(buffers) == len(issuers)
    assert all(
        buffer.snapshot().state == "closed"
        and buffer.snapshot().worker_running is False
        for buffer in buffers
    )
    assert exported == []


@pytest.mark.asyncio
async def test_invalid_evidence_surfaces_retained_owner_when_cleanup_is_incomplete() -> (
    None
):
    entered = asyncio.Event()
    release = asyncio.Event()
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        entered.set()
        await release.wait()
        exported.append(record)

    def invalid_issuer(
        evidence: ProductObservabilityActivationEvidence,
    ) -> ProductRouteFact:
        evidence.lease._exporter_buffer.emit_observation(
            _observation("event-invalid-evidence-cleanup")
        )
        return _formal_authority_route_fact()

    with pytest.raises(ProductObservabilityActivationError) as caught:
        await activate_product_observability_adapter(
            enabled=True,
            context=CONTEXT,
            exporter=exporter,
            formal_route_fact_issuer=invalid_issuer,
            export_timeout_seconds=1,
            close_timeout_seconds=0.02,
        )

    await asyncio.wait_for(entered.wait(), timeout=1)
    assert caught.value.cleanup_result is not None
    assert (
        caught.value.cleanup_result.lease_state
        is ProductObservabilityLeaseState.CLOSING
    )
    assert caught.value.cleanup_result.retained_for_retry is True
    assert caught.value.cleanup_result.exporter.worker_running is True
    assert caught.value.cleanup_result.exporter.state == "closing"

    release.set()
    closed = await caught.value.cleanup_lease.close_with_result(timeout_seconds=1)
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert len(exported) == 1


@pytest.mark.asyncio
async def test_explicit_activation_objects_cannot_be_forged() -> None:
    async def exporter(_: ExportRecord) -> None:
        return None

    activation = await _activate(exporter)

    with pytest.raises(ValueError, match="explicit package activation"):
        ActiveProductObservabilityActivation(
            route_fact=activation.route_fact,
            adapter=activation.adapter,
            lease=activation.lease,
            active=False,
        )
    with pytest.raises(ValueError, match="exactly off"):
        InactiveProductObservabilityActivation(route_fact=activation.route_fact)
    with pytest.raises(ValueError, match="cannot retain product effects"):
        UnavailableProductObservabilityActivation(route_fact=activation.route_fact)
    with pytest.raises(ValueError, match="exact running X-OBS lease"):
        ProductObservabilityActivationEvidence(
            session_id=CONTEXT.session_id,
            correlation_id=CONTEXT.correlation_id,
            lease=activation.lease,
        )
    with pytest.raises(ValueError, match="requires explicit activation"):
        ProductObservabilityAdapter(  # type: ignore[arg-type]
            context=CONTEXT,
            exporter_buffer=object(),
            route_fact=activation.route_fact,
            construction_token=object(),
        )
    with pytest.raises(ValueError, match="requires explicit activation"):
        ProductObservabilityLease(  # type: ignore[arg-type]
            adapter=activation.adapter,
            exporter_buffer=object(),
            construction_token=object(),
        )

    await activation.lease.close_with_result()


@pytest.mark.asyncio
async def test_wrong_context_correlation_type_and_invalid_fact_fail_closed() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    activation = await _activate(exporter)
    equal_but_distinct = ProductCompositionContext(
        CONTEXT.session_id, CONTEXT.correlation_id
    )
    wrong_session = ProductCompositionContext("session-other", CONTEXT.correlation_id)
    corrupted = _observation("event-corrupted")
    object.__setattr__(corrupted, "binding", object())

    results = (
        activation.adapter.consume_observation(
            context=equal_but_distinct, observation=_observation("event-context")
        ),
        activation.adapter.consume_metric(
            context=wrong_session, metric=_metric("metric-session")
        ),
        activation.adapter.consume_observation(
            context=CONTEXT,
            observation=_observation("event-correlation", correlation_id="corr-other"),
        ),
        activation.adapter.consume_observation(
            context=CONTEXT, observation={"transcript": "private"}
        ),
        activation.adapter.consume_observation(context=CONTEXT, observation=corrupted),
    )
    closed = await activation.lease.close_with_result()

    assert tuple(result.reason_id for result in results) == (
        ProductObservabilityReason.CONTEXT_BINDING_MISMATCH,
        ProductObservabilityReason.CONTEXT_BINDING_MISMATCH,
        ProductObservabilityReason.CORRELATION_MISMATCH,
        ProductObservabilityReason.INVALID_FACT_TYPE,
        ProductObservabilityReason.INVALID_PUBLIC_FACT,
    )
    assert all(not result.accepted_for_export for result in results)
    assert exported == []
    assert closed.exporter.stats.accepted_records == 0

    mutable_context = ProductCompositionContext(
        "session-mutation-test", CONTEXT.correlation_id
    )
    mutation_activation = await activate_product_observability_adapter(
        enabled=True,
        context=mutable_context,
        exporter=exporter,
        formal_route_fact_issuer=_formal_observability_route_issuer,
    )
    assert isinstance(mutation_activation, ActiveProductObservabilityActivation)
    object.__setattr__(mutable_context, "session_id", "session-mutated")
    mutated = mutation_activation.adapter.consume_observation(
        context=mutable_context, observation=_observation("event-mutated-context")
    )
    mutation_closed = await mutation_activation.lease.close_with_result()
    assert mutated.reason_id is ProductObservabilityReason.CONTEXT_BINDING_MISMATCH
    assert mutation_closed.exporter.stats.accepted_records == 0


@pytest.mark.asyncio
async def test_credentials_urls_device_identity_and_unreviewed_content_are_rejected() -> (
    None
):
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    activation = await _activate(exporter)
    credential = _observation("event-redact-a")
    object.__setattr__(credential, "source_component", "sk-secretvalue")
    url = _observation("event-redact-b")
    object.__setattr__(
        url.route, "capability_provider", "https://telemetry.invalid/upload"
    )
    device = _observation("event-redact-c")
    object.__setattr__(device, "source_event_id", "device_id:microphone-serial")
    transcript = _observation("event-redact-d")
    object.__setattr__(transcript, "source_component", "transcript")
    raw_audio = _observation("event-redact-e")
    object.__setattr__(raw_audio, "source_event_id", "raw_audio:frame")

    results = tuple(
        activation.adapter.consume_observation(context=CONTEXT, observation=record)
        for record in (credential, url, device, transcript, raw_audio)
    )
    closed = await activation.lease.close_with_result()

    assert all(
        result.reason_id is ProductObservabilityReason.PRIVATE_CONTENT_REJECTED
        for result in results
    )
    assert exported == []
    assert closed.exporter.stats.accepted_records == 0


@pytest.mark.asyncio
async def test_schema_valid_url_query_and_equal_delimited_carriers_export_zero() -> (
    None
):
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    activation = await _activate(exporter)
    carriers = (
        "ftp://telemetry.invalid/upload",
        "secret=value",
        "transcript=hello",
        "raw_audio=AAAA",
        "device_id=microphone-serial",
        "version?credential=value",
        "mailto:private@example.invalid",
        "data:audio/wav;base64,AAAA",
    )
    records = tuple(
        _observation_with_unreviewed_contract(f"event-carrier-{index}", carrier)
        for index, carrier in enumerate(carriers)
    )

    results = tuple(
        activation.adapter.consume_observation(context=CONTEXT, observation=record)
        for record in records
    )
    closed = await activation.lease.close_with_result()

    assert all(
        result.reason_id is ProductObservabilityReason.PRIVATE_CONTENT_REJECTED
        for result in results
    )
    assert exported == []
    assert closed.exporter.stats.accepted_records == 0


@pytest.mark.asyncio
async def test_full_buffer_is_diagnostic_only_and_does_not_block_business_result() -> (
    None
):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def exporter(_: ExportRecord) -> None:
        entered.set()
        await release.wait()

    activation = await _activate(exporter, capacity=1)
    business_result = {"accepted": True, "owner": "agent"}
    before = business_result.copy()

    first = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-full-1")
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    second = activation.adapter.consume_metric(
        context=CONTEXT, metric=_metric("metric-full-2")
    )

    assert first.accepted_for_export is True
    assert second.reason_id is ProductObservabilityReason.EXPORT_BACKPRESSURED
    assert business_result == before
    release.set()
    closed = await activation.lease.close_with_result()
    assert closed.exporter.stats.delivered_records == 1
    assert closed.exporter.stats.rejected_full == 1


@pytest.mark.asyncio
async def test_failing_exporter_cannot_rewrite_business_or_acceptance() -> None:
    async def exporter(_: ExportRecord) -> None:
        raise RuntimeError("injected exporter failure")

    activation = await _activate(exporter)
    business_result = ("completed", "agent-owned")

    result = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-export-failure")
    )
    closed = await activation.lease.close_with_result()

    assert result.accepted_for_export is True
    assert business_result == ("completed", "agent-owned")
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.exporter.stats.attempted_records == 1
    assert closed.exporter.stats.failed_records == 1
    assert closed.exporter.stats.delivered_records == 0


@pytest.mark.asyncio
async def test_export_timeout_retains_close_for_retry_without_business_effect() -> None:
    entered = asyncio.Event()
    cancellation_seen = asyncio.Event()
    release = asyncio.Event()

    async def exporter(_: ExportRecord) -> None:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancellation_seen.set()
            await release.wait()

    activation = await _activate(
        exporter,
        export_timeout_seconds=0.01,
        close_timeout_seconds=0.02,
    )
    business_result = {"status": "completed"}
    result = activation.adapter.consume_metric(
        context=CONTEXT, metric=_metric("metric-export-timeout")
    )
    await asyncio.wait_for(entered.wait(), timeout=1)

    pending = await activation.lease.close_with_result(timeout_seconds=0.02)

    assert result.accepted_for_export is True
    assert business_result == {"status": "completed"}
    assert pending.lease_state is ProductObservabilityLeaseState.CLOSING
    assert pending.retained_for_retry is True
    assert pending.exporter.worker_running is True
    assert cancellation_seen.is_set()

    release.set()
    closed = await activation.lease.close_with_result(timeout_seconds=1)
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.exporter.stats.timed_out_records == 1
    assert closed.exporter.stats.close_timeouts == 1


@pytest.mark.asyncio
async def test_composition_close_raises_until_retained_worker_is_terminal() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def exporter(_: ExportRecord) -> None:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    activation = await _activate(
        exporter,
        export_timeout_seconds=0.01,
        close_timeout_seconds=0.02,
    )
    activation.adapter.consume_observation(
        context=CONTEXT,
        observation=_observation("event-composition-close-retained"),
    )
    await asyncio.wait_for(entered.wait(), timeout=1)

    with pytest.raises(ProductObservabilityLeaseCloseError) as caught:
        await activation.lease.close()

    assert caught.value.result.lease_state is ProductObservabilityLeaseState.CLOSING
    assert caught.value.result.retained_for_retry is True
    assert caught.value.result.exporter.worker_running is True

    release.set()
    assert await activation.lease.close() is None
    assert (
        activation.adapter.snapshot().lease_state
        is ProductObservabilityLeaseState.CLOSED
    )


@pytest.mark.asyncio
async def test_root_retains_xobs_lease_until_worker_retry_reaches_closed() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    holder: dict[str, ActiveProductObservabilityActivation] = {}

    async def exporter(_: ExportRecord) -> None:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    class _AuthorityLease:
        async def close(self) -> None:
            return None

    async def activate_authority(
        _: ProductCompositionContext,
    ) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal_authority_route_fact(), _AuthorityLease()
        )

    async def activate_observability(
        context: ProductCompositionContext,
    ) -> ProductSegmentActivation:
        activation = await activate_product_observability_adapter(
            enabled=True,
            context=context,
            exporter=exporter,
            formal_route_fact_issuer=_formal_observability_route_issuer,
            export_timeout_seconds=0.01,
            close_timeout_seconds=0.02,
        )
        assert isinstance(activation, ActiveProductObservabilityActivation)
        holder["activation"] = activation
        return ProductSegmentActivation(activation.route_fact, activation.lease)

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(
            ProductCompositionRegistration(
                ProductSegment.AUTHORITY,
                "adapter.authority.test",
                activate_authority,
            ),
            ProductCompositionRegistration(
                ProductSegment.OBSERVABILITY,
                "adapter.observability.test",
                activate_observability,
            ),
        ),
    )
    composition = await root.activate(CONTEXT)
    assert composition.lease is not None
    activation = holder["activation"]
    activation.adapter.consume_observation(
        context=CONTEXT,
        observation=_observation("event-root-retained-worker"),
    )
    await asyncio.wait_for(entered.wait(), timeout=1)

    with pytest.raises(ProductCompositionLeaseCloseError):
        await composition.lease.close()

    assert composition.lease.pending_adapter_ids == ("adapter.observability.test",)
    release.set()
    await composition.lease.close()
    assert composition.lease.closed is True
    assert (
        activation.adapter.snapshot().lease_state
        is ProductObservabilityLeaseState.CLOSED
    )


@pytest.mark.asyncio
async def test_cancelled_close_waiter_cannot_cancel_the_retained_worker() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def exporter(_: ExportRecord) -> None:
        entered.set()
        await release.wait()

    activation = await _activate(exporter, export_timeout_seconds=1)
    result = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-close-cancel")
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    close_waiter = asyncio.create_task(activation.lease.close_with_result())
    await asyncio.sleep(0)
    close_waiter.cancel()

    with pytest.raises(asyncio.CancelledError):
        await close_waiter
    pending = activation.adapter.snapshot()
    assert result.accepted_for_export is True
    assert pending.lease_state is ProductObservabilityLeaseState.CLOSING
    assert pending.exporter.worker_running is True
    assert pending.exporter.stats.close_cancellations == 1

    release.set()
    closed = await activation.lease.close_with_result(timeout_seconds=1)
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert closed.exporter.stats.delivered_records == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_timeout", [0, True, math.nan, math.inf, -1])
async def test_invalid_close_timeout_preserves_active_adapter_and_valid_close(
    invalid_timeout: object,
) -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    activation = await _activate(exporter)

    with pytest.raises(ValueError, match="positive finite"):
        await activation.lease.close_with_result(
            timeout_seconds=invalid_timeout  # type: ignore[arg-type]
        )

    still_active = activation.adapter.snapshot()
    result = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-after-invalid-timeout")
    )
    closed = await activation.lease.close_with_result(timeout_seconds=1)

    assert still_active.lease_state is ProductObservabilityLeaseState.ACTIVE
    assert still_active.exporter.state == "running"
    assert result.accepted_for_export is True
    assert closed.lease_state is ProductObservabilityLeaseState.CLOSED
    assert len(exported) == 1


@pytest.mark.asyncio
async def test_close_result_rejects_active_state() -> None:
    async def exporter(_: ExportRecord) -> None:
        return None

    activation = await _activate(exporter)
    exporter_snapshot = activation.adapter.snapshot().exporter
    with pytest.raises(ValueError, match="cannot report an active lease"):
        ProductObservabilityCloseResult(
            lease_state=ProductObservabilityLeaseState.ACTIVE,
            exporter=exporter_snapshot,
            retained_for_retry=True,
        )
    await activation.lease.close_with_result()


@pytest.mark.asyncio
async def test_concurrent_consumers_and_closers_have_one_retained_lease() -> None:
    exported: list[ExportRecord] = []

    async def exporter(record: ExportRecord) -> None:
        exported.append(record)

    activation = await _activate(exporter, capacity=64)
    records = tuple(_observation(f"event-concurrent-{index}") for index in range(40))

    results = await asyncio.gather(
        *(
            asyncio.to_thread(
                activation.adapter.consume_observation,
                context=CONTEXT,
                observation=record,
            )
            for record in records
        )
    )
    closed_one, closed_two = await asyncio.gather(
        activation.lease.close_with_result(), activation.lease.close_with_result()
    )
    late = activation.adapter.consume_observation(
        context=CONTEXT, observation=_observation("event-after-close")
    )

    assert all(result.accepted_for_export for result in results)
    assert len(exported) == len(records)
    assert closed_one.lease_state is closed_two.lease_state
    assert closed_one.lease_state is ProductObservabilityLeaseState.CLOSED
    assert late.reason_id is ProductObservabilityReason.ADAPTER_CLOSED
    snapshot = activation.adapter.snapshot()
    assert snapshot.stats.accepted == len(records)
    assert snapshot.stats.rejected_closed == 1
    assert snapshot.business_result_changed is False
    assert snapshot.lifecycle_authority_exercised is False
    assert snapshot.cancel_authority_exercised is False
    assert snapshot.success_authority_exercised is False
