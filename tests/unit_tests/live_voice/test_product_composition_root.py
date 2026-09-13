# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from jiuwenswarm.server.live_voice.product_composition_contract import (
    ProductEvidenceId,
    ProductRouteFact,
    ProductRouteReason,
    ProductRouteTruth,
    ProductSegment,
)
from jiuwenswarm.server.live_voice.product_composition_root import (
    ProductCompositionActivationError,
    ProductCompositionContext,
    ProductCompositionLeaseCloseError,
    ProductCompositionRegistration,
    ProductCompositionRoot,
    ProductCompositionRootViolation,
    ProductSegmentActivation,
    ProductSegmentActivationError,
)


CONTEXT = ProductCompositionContext("session-product", "correlation-product")


@dataclass
class _Lease:
    name: str
    events: list[str]
    failures_remaining: int = 0

    async def close(self) -> None:
        self.events.append(f"close:{self.name}")
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("injected close failure")


class _PoisonRegistrations:
    def __iter__(self) -> Any:
        raise AssertionError("feature-off inspected registrations")


def _unavailable(segment: ProductSegment) -> ProductRouteFact:
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.UNAVAILABLE,
        reason_id=ProductRouteReason.ADAPTER_NOT_REGISTERED,
        evidence_ids=(ProductEvidenceId.PACKAGE_CONTRACT_ONLY,),
    )


def _formal(segment: ProductSegment) -> ProductRouteFact:
    evidence = [
        ProductEvidenceId.TRUSTED_AUTHORITY_RESOLVED,
        ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
        ProductEvidenceId.RUNTIME_PATH_OBSERVED,
    ]
    if segment is ProductSegment.P1_SPEECH_MEDIA:
        evidence.append(ProductEvidenceId.MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED)
    if segment is ProductSegment.P2_AGENT_INTERACTION:
        evidence.append(ProductEvidenceId.P2_NOTIFICATION_BACKPRESSURE_CLOSED)
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.FORMAL,
        reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
        evidence_ids=tuple(evidence),
        formal_runtime_observed=True,
    )


def _registration(
    segment: ProductSegment,
    callback: Any,
) -> ProductCompositionRegistration:
    return ProductCompositionRegistration(
        segment=segment,
        adapter_id=f"adapter.{segment.value}",
        activate=callback,
    )


@pytest.mark.asyncio
async def test_feature_off_returns_before_context_or_registration_inspection() -> None:
    root = ProductCompositionRoot(
        enabled=False,
        registrations=_PoisonRegistrations(),
    )

    preview = root.preview()
    activation = await root.activate(object())

    assert preview.enabled is False
    assert activation.manifest == preview
    assert activation.activated_adapter_ids == ()
    assert activation.lease is None
    assert all(route.truth is ProductRouteTruth.DISABLED for route in preview.routes)


def test_enabled_preview_is_manifest_only_and_never_calls_adapters() -> None:
    calls = 0

    async def activate(_: ProductCompositionContext) -> ProductSegmentActivation:
        nonlocal calls
        calls += 1
        return ProductSegmentActivation(_unavailable(ProductSegment.AUTHORITY), None)

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(_registration(ProductSegment.AUTHORITY, activate),),
    )
    preview = root.preview()

    assert calls == 0
    authority = preview.routes[0]
    assert authority.truth is ProductRouteTruth.UNAVAILABLE
    assert authority.reason_id is ProductRouteReason.FORMAL_ACTIVATION_EVIDENCE_MISSING
    assert authority.evidence_ids == (
        ProductEvidenceId.PACKAGE_CONTRACT_ONLY,
        ProductEvidenceId.NO_RUNTIME_EVIDENCE,
    )


@pytest.mark.asyncio
async def test_canonical_activation_and_reverse_close_preserve_exact_context() -> None:
    events: list[str] = []

    def registration(segment: ProductSegment) -> ProductCompositionRegistration:
        async def activate(
            context: ProductCompositionContext,
        ) -> ProductSegmentActivation:
            assert context is CONTEXT
            events.append(f"activate:{segment.value}")
            return ProductSegmentActivation(
                _formal(segment),
                _Lease(segment.value, events),
            )

        return _registration(segment, activate)

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(
            registration(ProductSegment.P3_PROGRESS),
            registration(ProductSegment.P2_AGENT_INTERACTION),
            registration(ProductSegment.AUTHORITY),
            registration(ProductSegment.P3_QUERY),
        ),
    )
    activation = await root.activate(CONTEXT)

    assert events == [
        "activate:authority",
        "activate:p2.agent_interaction",
        "activate:p3.query",
        "activate:p3.progress",
    ]
    assert activation.activated_adapter_ids == (
        "adapter.authority",
        "adapter.p2.agent_interaction",
        "adapter.p3.query",
        "adapter.p3.progress",
    )
    assert activation.manifest.routes[0].truth is ProductRouteTruth.FORMAL
    assert activation.lease is not None

    await activation.lease.close()
    await activation.lease.close()
    assert events[-4:] == [
        "close:p3.progress",
        "close:p3.query",
        "close:p2.agent_interaction",
        "close:authority",
    ]
    assert activation.lease.closed is True


@pytest.mark.asyncio
async def test_unavailable_package_has_no_lease_and_remains_truthful() -> None:
    calls = 0

    async def activate(_: ProductCompositionContext) -> ProductSegmentActivation:
        nonlocal calls
        calls += 1
        return ProductSegmentActivation(_unavailable(ProductSegment.P3_QUERY), None)

    result = await ProductCompositionRoot(
        enabled=True,
        registrations=(_registration(ProductSegment.P3_QUERY, activate),),
    ).activate(CONTEXT)

    assert result.lease is None
    assert result.activated_adapter_ids == ()
    assert calls == 0
    assert (
        result.manifest.routes[
            tuple(ProductSegment).index(ProductSegment.P3_QUERY)
        ].reason_id
        is ProductRouteReason.TRUSTED_AUTHORITY_UNAVAILABLE
    )


@pytest.mark.asyncio
async def test_unavailable_authority_prevents_every_downstream_call() -> None:
    events: list[str] = []

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        events.append("authority")
        return ProductSegmentActivation(_unavailable(ProductSegment.AUTHORITY), None)

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        events.append("forbidden:p2")
        return ProductSegmentActivation(
            _formal(ProductSegment.P2_AGENT_INTERACTION),
            _Lease("p2", events),
        )

    result = await ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
        ),
    ).activate(CONTEXT)

    assert events == ["authority"]
    assert result.lease is None
    assert all(
        route.truth is not ProductRouteTruth.FORMAL for route in result.manifest.routes
    )
    assert (
        result.manifest.routes[
            tuple(ProductSegment).index(ProductSegment.P2_AGENT_INTERACTION)
        ].reason_id
        is ProductRouteReason.TRUSTED_AUTHORITY_UNAVAILABLE
    )


@pytest.mark.asyncio
async def test_later_adapter_failure_rolls_back_prior_lease() -> None:
    events: list[str] = []

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        events.append("activate:authority")
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY),
            _Lease("authority", events),
        )

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        events.append("activate:p2")
        raise RuntimeError("injected activation failure")

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
        ),
    )

    with pytest.raises(ProductCompositionActivationError) as caught:
        await root.activate(CONTEXT)
    assert caught.value.reason == "ADAPTER_ACTIVATION_FAILED"
    assert caught.value.cleanup_lease is None
    assert events == ["activate:authority", "activate:p2", "close:authority"]


@pytest.mark.asyncio
async def test_failed_rollback_is_retained_and_retryable() -> None:
    events: list[str] = []
    authority_lease = _Lease("authority", events, failures_remaining=1)

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY), authority_lease
        )

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        raise RuntimeError("injected activation failure")

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
        ),
    )

    with pytest.raises(ProductCompositionActivationError) as caught:
        await root.activate(CONTEXT)
    cleanup = caught.value.cleanup_lease
    assert caught.value.reason == "ACTIVATION_ROLLBACK_INCOMPLETE"
    assert cleanup is not None
    assert cleanup.pending_adapter_ids == ("adapter.authority",)

    await cleanup.close()
    assert cleanup.closed is True
    assert events == ["close:authority", "close:authority"]


@pytest.mark.asyncio
async def test_adapter_transfers_partial_cleanup_ownership_to_root() -> None:
    events: list[str] = []
    partial = _Lease("p2-partial", events, failures_remaining=1)

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY), _Lease("authority", events)
        )

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        raise ProductSegmentActivationError(
            "P2_PARTIAL_ACTIVATION_FAILED",
            cleanup_lease=partial,
        )

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
        ),
    )

    with pytest.raises(ProductCompositionActivationError) as caught:
        await root.activate(CONTEXT)
    cleanup = caught.value.cleanup_lease
    assert caught.value.reason == "ACTIVATION_ROLLBACK_INCOMPLETE"
    assert cleanup is not None
    assert cleanup.pending_adapter_ids == ("adapter.p2.agent_interaction",)
    assert events == ["close:p2-partial", "close:authority"]

    await cleanup.close()
    assert cleanup.closed is True
    assert events == ["close:p2-partial", "close:authority", "close:p2-partial"]


@pytest.mark.asyncio
async def test_self_cancelled_rollback_is_retained_and_retryable() -> None:
    events: list[str] = []

    @dataclass
    class SelfCancellingLease:
        cancelled: bool = False

        async def close(self) -> None:
            events.append("close:authority")
            if not self.cancelled:
                self.cancelled = True
                raise asyncio.CancelledError

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY), SelfCancellingLease()
        )

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        raise RuntimeError("injected activation failure")

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
        ),
    )

    with pytest.raises(ProductCompositionActivationError) as caught:
        await root.activate(CONTEXT)
    cleanup = caught.value.cleanup_lease
    assert caught.value.reason == "ACTIVATION_ROLLBACK_INCOMPLETE"
    assert cleanup is not None
    assert cleanup.pending_adapter_ids == ("adapter.authority",)

    await cleanup.close()
    assert cleanup.closed is True
    assert events == ["close:authority", "close:authority"]


@pytest.mark.asyncio
async def test_successful_close_retains_only_failures_in_acquisition_order() -> None:
    events: list[str] = []
    authority_lease = _Lease("authority", events)
    p2_lease = _Lease("p2", events, failures_remaining=1)

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY), authority_lease
        )

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.P2_AGENT_INTERACTION), p2_lease
        )

    activation = await ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
        ),
    ).activate(CONTEXT)
    assert activation.lease is not None

    with pytest.raises(ProductCompositionLeaseCloseError):
        await activation.lease.close()
    assert activation.lease.pending_adapter_ids == ("adapter.p2.agent_interaction",)
    await activation.lease.close()
    assert events == ["close:p2", "close:authority", "close:p2"]


@pytest.mark.asyncio
async def test_invalid_activation_result_rolls_back_without_truth_upgrade() -> None:
    events: list[str] = []

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY),
            _Lease("authority", events),
        )

    async def p2(_: ProductCompositionContext) -> object:
        return object()

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
        ),
    )
    with pytest.raises(ProductCompositionActivationError) as caught:
        await root.activate(CONTEXT)
    assert caught.value.reason == "INVALID_ADAPTER_ACTIVATION"
    assert events == ["close:authority"]


@pytest.mark.asyncio
async def test_wrong_segment_activation_retains_current_lease_before_rejection() -> (
    None
):
    events: list[str] = []
    wrong_segment_lease = _Lease("wrong-p3", events, failures_remaining=1)

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY), _Lease("authority", events)
        )

    async def p3_query(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.P3_PROGRESS), wrong_segment_lease
        )

    root = ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P3_QUERY, p3_query),
        ),
    )

    with pytest.raises(ProductCompositionActivationError) as caught:
        await root.activate(CONTEXT)
    cleanup = caught.value.cleanup_lease
    assert caught.value.reason == "ACTIVATION_ROLLBACK_INCOMPLETE"
    assert cleanup is not None
    assert cleanup.pending_adapter_ids == ("adapter.p3.query",)
    assert events == ["close:wrong-p3", "close:authority"]

    await cleanup.close()
    assert cleanup.closed is True
    assert events == ["close:wrong-p3", "close:authority", "close:wrong-p3"]


def test_duplicate_and_invalid_registrations_fail_only_when_enabled() -> None:
    async def activate(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(_unavailable(ProductSegment.AUTHORITY), None)

    duplicate = _registration(ProductSegment.AUTHORITY, activate)
    root = ProductCompositionRoot(
        enabled=True,
        registrations=(duplicate, duplicate),
    )
    with pytest.raises(ProductCompositionRootViolation):
        root.preview()

    invalid = ProductCompositionRoot(enabled=True, registrations=object())
    with pytest.raises(ProductCompositionRootViolation):
        invalid.preview()

    duplicate_id = ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, activate),
            ProductCompositionRegistration(
                segment=ProductSegment.P3_QUERY,
                adapter_id="adapter.authority",
                activate=activate,
            ),
        ),
    )
    with pytest.raises(ProductCompositionRootViolation):
        duplicate_id.preview()


def test_formal_activation_requires_lease_and_nonformal_forbids_one() -> None:
    with pytest.raises(ProductCompositionRootViolation):
        ProductSegmentActivation(_formal(ProductSegment.AUTHORITY), None)
    with pytest.raises(ProductCompositionRootViolation):
        ProductSegmentActivation(
            _unavailable(ProductSegment.AUTHORITY), _Lease("hidden", [])
        )


@pytest.mark.asyncio
async def test_cancelled_close_retains_current_and_unattempted_leases() -> None:
    events: list[str] = []
    close_entered = asyncio.Event()
    release_close = asyncio.Event()

    @dataclass
    class BlockingLease:
        name: str

        async def close(self) -> None:
            events.append(f"close:{self.name}")
            close_entered.set()
            await release_close.wait()

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY), BlockingLease("authority")
        )

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.P2_AGENT_INTERACTION), BlockingLease("p2")
        )

    activation = await ProductCompositionRoot(
        enabled=True,
        registrations=(
            _registration(ProductSegment.AUTHORITY, authority),
            _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
        ),
    ).activate(CONTEXT)
    assert activation.lease is not None

    closing = asyncio.create_task(activation.lease.close())
    await close_entered.wait()
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert activation.lease.pending_adapter_ids == (
        "adapter.authority",
        "adapter.p2.agent_interaction",
    )

    release_close.set()
    await activation.lease.close()
    assert activation.lease.closed is True


@pytest.mark.asyncio
async def test_cancelled_activation_rolls_back_open_authority_before_propagating() -> (
    None
):
    events: list[str] = []
    p2_entered = asyncio.Event()
    never_release = asyncio.Event()

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY), _Lease("authority", events)
        )

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        p2_entered.set()
        await never_release.wait()
        raise AssertionError("cancelled activation resumed unexpectedly")

    activating = asyncio.create_task(
        ProductCompositionRoot(
            enabled=True,
            registrations=(
                _registration(ProductSegment.AUTHORITY, authority),
                _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
            ),
        ).activate(CONTEXT)
    )
    await p2_entered.wait()
    activating.cancel()

    with pytest.raises(asyncio.CancelledError):
        await activating
    assert events == ["close:authority"]


@pytest.mark.asyncio
async def test_cancelled_activation_surfaces_retained_self_cancelled_rollback() -> None:
    p2_entered = asyncio.Event()
    never_release = asyncio.Event()

    @dataclass
    class SelfCancellingLease:
        cancelled: bool = False

        async def close(self) -> None:
            if not self.cancelled:
                self.cancelled = True
                raise asyncio.CancelledError

    async def authority(_: ProductCompositionContext) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _formal(ProductSegment.AUTHORITY), SelfCancellingLease()
        )

    async def p2(_: ProductCompositionContext) -> ProductSegmentActivation:
        p2_entered.set()
        await never_release.wait()
        raise AssertionError("cancelled activation resumed unexpectedly")

    activating = asyncio.create_task(
        ProductCompositionRoot(
            enabled=True,
            registrations=(
                _registration(ProductSegment.AUTHORITY, authority),
                _registration(ProductSegment.P2_AGENT_INTERACTION, p2),
            ),
        ).activate(CONTEXT)
    )
    await p2_entered.wait()
    activating.cancel()

    with pytest.raises(ProductCompositionActivationError) as caught:
        await activating
    cleanup = caught.value.cleanup_lease
    assert caught.value.reason == "ACTIVATION_CANCELLED_ROLLBACK_INCOMPLETE"
    assert cleanup is not None
    assert cleanup.pending_adapter_ids == ("adapter.authority",)

    await cleanup.close()
    assert cleanup.closed is True
