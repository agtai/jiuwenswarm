# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Package-only product consumer for governed Live Voice observability facts.

This module deliberately does not register an exporter or claim the product
observability route.  It only gives an explicitly activated product composition
context a bounded, retained lease over the existing diagnostic exporter buffer.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock
from typing import cast

from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceMetric,
    LiveVoiceObservation,
    RouteDescriptor,
    TraceBinding,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.observability_exporter import (
    ExporterBackpressureError,
    ExporterCloseTimeoutError,
    ExportRecord,
    ExporterSnapshot,
    LiveVoiceObservabilityExporterBuffer,
    ObservabilityExporterError,
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


ObservationExporter = Callable[[ExportRecord], Awaitable[None]]
_CONSTRUCTION_TOKEN = object()
_SCHEME_URL = re.compile(r"[a-z][a-z0-9+.-]{0,31}://", re.IGNORECASE)
_SCHEME_VALUE = re.compile(r"^[a-z][a-z0-9+.-]{0,31}:", re.IGNORECASE)
_NON_HIERARCHICAL_URL = re.compile(
    r"\b(?:blob|data|file|javascript|mailto|sftp|ssh|tel|urn):", re.IGNORECASE
)


class ProductObservabilityReason(StrEnum):
    """Closed diagnostic outcome vocabulary with no business authority."""

    ACCEPTED_FOR_EXPORT = "accepted_for_export"
    CONTEXT_BINDING_MISMATCH = "context_binding_mismatch"
    CORRELATION_MISMATCH = "correlation_mismatch"
    INVALID_FACT_TYPE = "invalid_fact_type"
    INVALID_PUBLIC_FACT = "invalid_public_fact"
    PRIVATE_CONTENT_REJECTED = "private_content_rejected"
    EXPORT_BACKPRESSURED = "export_backpressured"
    EXPORTER_UNAVAILABLE = "exporter_unavailable"
    ADAPTER_CLOSING = "adapter_closing"
    ADAPTER_CLOSED = "adapter_closed"


class ProductObservabilityLeaseState(StrEnum):
    """Retained exporter-worker lease state."""

    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProductObservabilityDisposition:
    """Content-free result of one diagnostic consumption attempt."""

    accepted_for_export: bool
    reason_id: ProductObservabilityReason
    business_result_changed: bool = False
    lifecycle_authority_exercised: bool = False
    cancel_authority_exercised: bool = False
    success_authority_exercised: bool = False

    def __post_init__(self) -> None:
        if type(self.accepted_for_export) is not bool:
            raise ValueError("accepted_for_export must be a boolean")
        if not isinstance(self.reason_id, ProductObservabilityReason):
            raise ValueError("reason_id must use ProductObservabilityReason")
        if self.accepted_for_export != (
            self.reason_id is ProductObservabilityReason.ACCEPTED_FOR_EXPORT
        ):
            raise ValueError("accepted_for_export must agree with reason_id")
        authority_facts = (
            self.business_result_changed,
            self.lifecycle_authority_exercised,
            self.cancel_authority_exercised,
            self.success_authority_exercised,
        )
        if any(type(value) is not bool or value for value in authority_facts):
            raise ValueError("product observability has no business authority")


@dataclass(frozen=True, slots=True)
class ProductObservabilityAdapterStats:
    """Aggregate counters only; never retained fact content."""

    accepted: int
    rejected_context: int
    rejected_correlation: int
    rejected_type: int
    rejected_invalid_fact: int
    rejected_private_content: int
    rejected_backpressure: int
    rejected_exporter: int
    rejected_closing: int
    rejected_closed: int


@dataclass(frozen=True, slots=True)
class ProductObservabilityAdapterSnapshot:
    """Content-free package state suitable for diagnostic assertions."""

    lease_state: ProductObservabilityLeaseState
    route_fact: ProductRouteFact
    stats: ProductObservabilityAdapterStats
    exporter: ExporterSnapshot
    business_result_changed: bool = False
    lifecycle_authority_exercised: bool = False
    cancel_authority_exercised: bool = False
    success_authority_exercised: bool = False

    def __post_init__(self) -> None:
        authority_facts = (
            self.business_result_changed,
            self.lifecycle_authority_exercised,
            self.cancel_authority_exercised,
            self.success_authority_exercised,
        )
        if any(type(value) is not bool or value for value in authority_facts):
            raise ValueError("product observability snapshot has no business authority")


@dataclass(frozen=True, slots=True)
class ProductObservabilityCloseResult:
    """Content-free close result; PENDING remains retryable and retained."""

    lease_state: ProductObservabilityLeaseState
    exporter: ExporterSnapshot
    retained_for_retry: bool

    def __post_init__(self) -> None:
        if not isinstance(self.lease_state, ProductObservabilityLeaseState):
            raise ValueError("close result requires a closed lease state")
        if self.lease_state is ProductObservabilityLeaseState.ACTIVE:
            raise ValueError("close result cannot report an active lease")
        if type(self.retained_for_retry) is not bool:
            raise ValueError("retained_for_retry must be a boolean")
        if self.lease_state is ProductObservabilityLeaseState.CLOSED:
            if self.retained_for_retry:
                raise ValueError("closed lease cannot be retained for retry")
        elif not self.retained_for_retry:
            raise ValueError("incomplete close must retain the lease")


@dataclass(frozen=True, slots=True)
class InactiveProductObservabilityActivation:
    """Feature-off result without an adapter, buffer, worker, or sink access."""

    route_fact: ProductRouteFact
    active: bool = False
    adapter: None = None
    lease: None = None

    def __post_init__(self) -> None:
        if (
            self.active is not False
            or self.adapter is not None
            or self.lease is not None
            or self.route_fact != _disabled_route_fact()
        ):
            raise ValueError("inactive product observability must be exactly off")


@dataclass(frozen=True, slots=True)
class ActiveProductObservabilityActivation:
    """Explicit package activation with one retained close lease."""

    route_fact: ProductRouteFact
    adapter: ProductObservabilityAdapter
    lease: ProductObservabilityLease
    active: bool = True
    _construction_token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._construction_token is not _CONSTRUCTION_TOKEN
            or self.active is not True
            or type(self.adapter) is not ProductObservabilityAdapter
            or type(self.lease) is not ProductObservabilityLease
            or self.route_fact != _package_only_route_fact()
            or self.adapter._route_fact is not self.route_fact
            or self.lease._adapter is not self.adapter
            or self.lease._exporter_buffer is not self.adapter._exporter_buffer
        ):
            raise ValueError(
                "active product observability requires explicit package activation"
            )


_PRIVATE_CONTENT_PATTERN = re.compile(
    r"\bbearer\s+[a-z0-9._~+/-]+"
    r"|\b(?:sk|ghp|glpat)-?[a-z0-9_-]{8,}\b"
    r"|\beyj[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+\b"
    r"|(?:^|[._:@/-])(?:transcript|raw[-_]?audio|audio[-_]?bytes|data[-_]?base64"
    r"|authorization|credential|password|passwd|secret|api[-_]?key"
    r"|device[-_]?id|hardware[-_]?id|microphone[-_]?id)(?:$|[._:@/=?#-])",
    re.IGNORECASE,
)


def _disabled_route_fact() -> ProductRouteFact:
    return ProductRouteFact(
        segment=ProductSegment.OBSERVABILITY,
        truth=ProductRouteTruth.DISABLED,
        reason_id=ProductRouteReason.FEATURE_DISABLED,
        evidence_ids=(ProductEvidenceId.FEATURE_FLAG_OFF,),
    )


def _package_only_route_fact() -> ProductRouteFact:
    return ProductRouteFact(
        segment=ProductSegment.OBSERVABILITY,
        truth=ProductRouteTruth.UNAVAILABLE,
        reason_id=ProductRouteReason.OBSERVABILITY_CONSUMER_UNAVAILABLE,
        evidence_ids=(
            ProductEvidenceId.OBSERVABILITY_FOUNDATION,
            ProductEvidenceId.PACKAGE_CONTRACT_ONLY,
            ProductEvidenceId.NO_RUNTIME_EVIDENCE,
        ),
    )


def _contains_private_content(value: object, *, field_name: str | None = None) -> bool:
    if isinstance(value, str):
        # Governed tokens, opaque IDs, timestamps, and closed facts need none of
        # these free-text carriers.  Reject them before the injected exporter.
        return (
            any(delimiter in value for delimiter in ("=", "?", "#"))
            or _SCHEME_URL.search(value) is not None
            or _NON_HIERARCHICAL_URL.search(value) is not None
            or (
                field_name == "contract_version"
                and _SCHEME_VALUE.search(value) is not None
            )
            or _PRIVATE_CONTENT_PATTERN.search(value) is not None
        )
    if isinstance(value, dict):
        return any(
            _contains_private_content(key)
            or _contains_private_content(
                item, field_name=key if isinstance(key, str) else None
            )
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_private_content(item) for item in value)
    return False


class ProductObservabilityAdapter:
    """Exact-context consumer of already-authoritative public facts."""

    def __init__(
        self,
        *,
        context: ProductCompositionContext,
        exporter_buffer: LiveVoiceObservabilityExporterBuffer,
        route_fact: ProductRouteFact,
        construction_token: object,
    ) -> None:
        if construction_token is not _CONSTRUCTION_TOKEN:
            raise ValueError(
                "product observability adapter requires explicit activation"
            )
        self._context = context
        self._session_id = context.session_id
        self._correlation_id = context.correlation_id
        self._exporter_buffer = exporter_buffer
        self._route_fact = route_fact
        self._lock = Lock()
        self._lease_state = ProductObservabilityLeaseState.ACTIVE
        self._accepted = 0
        self._rejected_context = 0
        self._rejected_correlation = 0
        self._rejected_type = 0
        self._rejected_invalid_fact = 0
        self._rejected_private_content = 0
        self._rejected_backpressure = 0
        self._rejected_exporter = 0
        self._rejected_closing = 0
        self._rejected_closed = 0

    def consume_observation(
        self,
        *,
        context: ProductCompositionContext,
        observation: object,
    ) -> ProductObservabilityDisposition:
        """Validate and enqueue one public observation without business effects."""

        if type(observation) is not LiveVoiceObservation:
            return self._reject(ProductObservabilityReason.INVALID_FACT_TYPE)
        return self._consume(context=context, fact=observation)

    def consume_metric(
        self,
        *,
        context: ProductCompositionContext,
        metric: object,
    ) -> ProductObservabilityDisposition:
        """Validate and enqueue one public metric without business effects."""

        if type(metric) is not LiveVoiceMetric:
            return self._reject(ProductObservabilityReason.INVALID_FACT_TYPE)
        return self._consume(context=context, fact=metric)

    def snapshot(self) -> ProductObservabilityAdapterSnapshot:
        with self._lock:
            lease_state = self._lease_state
            stats = self._stats_locked()
        return ProductObservabilityAdapterSnapshot(
            lease_state=lease_state,
            route_fact=self._route_fact,
            stats=stats,
            exporter=self._exporter_buffer.snapshot(),
        )

    def _consume(
        self,
        *,
        context: ProductCompositionContext,
        fact: LiveVoiceObservation | LiveVoiceMetric,
    ) -> ProductObservabilityDisposition:
        if (
            context is not self._context
            or context.session_id != self._session_id
            or context.correlation_id != self._correlation_id
        ):
            return self._reject(ProductObservabilityReason.CONTEXT_BINDING_MISMATCH)
        try:
            if (
                type(fact.binding) is not TraceBinding
                or type(fact.route) is not RouteDescriptor
            ):
                return self._reject(ProductObservabilityReason.INVALID_PUBLIC_FACT)
            raw_fact = fact.to_dict()
            if _contains_private_content(raw_fact):
                return self._reject(ProductObservabilityReason.PRIVATE_CONTENT_REJECTED)
            public_fact: LiveVoiceObservation | LiveVoiceMetric
            if type(fact) is LiveVoiceObservation:
                public_fact = create_observation(fact)
            else:
                public_fact = create_metric(fact)
        except Exception:
            # A forged diagnostic fact must never escape into the business path.
            return self._reject(ProductObservabilityReason.INVALID_PUBLIC_FACT)
        if public_fact.binding.correlation_id != self._correlation_id:
            return self._reject(ProductObservabilityReason.CORRELATION_MISMATCH)

        with self._lock:
            if self._lease_state is ProductObservabilityLeaseState.CLOSING:
                return self._reject_locked(ProductObservabilityReason.ADAPTER_CLOSING)
            if self._lease_state in {
                ProductObservabilityLeaseState.CLOSED,
                ProductObservabilityLeaseState.FAILED,
            }:
                return self._reject_locked(ProductObservabilityReason.ADAPTER_CLOSED)
            try:
                if type(public_fact) is LiveVoiceObservation:
                    self._exporter_buffer.emit_observation(public_fact)
                else:
                    self._exporter_buffer.emit_metric(public_fact)
            except ExporterBackpressureError:
                return self._reject_locked(
                    ProductObservabilityReason.EXPORT_BACKPRESSURED
                )
            except ObservabilityExporterError:
                return self._reject_locked(
                    ProductObservabilityReason.EXPORTER_UNAVAILABLE
                )
            self._accepted += 1
        return ProductObservabilityDisposition(
            accepted_for_export=True,
            reason_id=ProductObservabilityReason.ACCEPTED_FOR_EXPORT,
        )

    def _reject(
        self, reason: ProductObservabilityReason
    ) -> ProductObservabilityDisposition:
        with self._lock:
            return self._reject_locked(reason)

    def _reject_locked(
        self, reason: ProductObservabilityReason
    ) -> ProductObservabilityDisposition:
        if reason is ProductObservabilityReason.CONTEXT_BINDING_MISMATCH:
            self._rejected_context += 1
        elif reason is ProductObservabilityReason.CORRELATION_MISMATCH:
            self._rejected_correlation += 1
        elif reason is ProductObservabilityReason.INVALID_FACT_TYPE:
            self._rejected_type += 1
        elif reason is ProductObservabilityReason.INVALID_PUBLIC_FACT:
            self._rejected_invalid_fact += 1
        elif reason is ProductObservabilityReason.PRIVATE_CONTENT_REJECTED:
            self._rejected_private_content += 1
        elif reason is ProductObservabilityReason.EXPORT_BACKPRESSURED:
            self._rejected_backpressure += 1
        elif reason is ProductObservabilityReason.ADAPTER_CLOSING:
            self._rejected_closing += 1
        elif reason is ProductObservabilityReason.ADAPTER_CLOSED:
            self._rejected_closed += 1
        else:
            self._rejected_exporter += 1
        return ProductObservabilityDisposition(
            accepted_for_export=False,
            reason_id=reason,
        )

    def _stats_locked(self) -> ProductObservabilityAdapterStats:
        return ProductObservabilityAdapterStats(
            accepted=self._accepted,
            rejected_context=self._rejected_context,
            rejected_correlation=self._rejected_correlation,
            rejected_type=self._rejected_type,
            rejected_invalid_fact=self._rejected_invalid_fact,
            rejected_private_content=self._rejected_private_content,
            rejected_backpressure=self._rejected_backpressure,
            rejected_exporter=self._rejected_exporter,
            rejected_closing=self._rejected_closing,
            rejected_closed=self._rejected_closed,
        )

    def _begin_close(self) -> None:
        with self._lock:
            if self._lease_state is ProductObservabilityLeaseState.ACTIVE:
                self._lease_state = ProductObservabilityLeaseState.CLOSING

    def _finish_close(self, state: ProductObservabilityLeaseState) -> None:
        with self._lock:
            self._lease_state = state


class ProductObservabilityLease:
    """Retained, retryable owner of the existing exporter worker."""

    def __init__(
        self,
        *,
        adapter: ProductObservabilityAdapter,
        exporter_buffer: LiveVoiceObservabilityExporterBuffer,
        construction_token: object,
    ) -> None:
        if construction_token is not _CONSTRUCTION_TOKEN:
            raise ValueError("product observability lease requires explicit activation")
        self._adapter = adapter
        self._exporter_buffer = exporter_buffer
        self._close_lock = asyncio.Lock()

    async def close(
        self, *, timeout_seconds: float | None = None
    ) -> ProductObservabilityCloseResult:
        validated_timeout = _close_timeout(timeout_seconds)
        async with self._close_lock:
            self._adapter._begin_close()
            try:
                exporter = await self._exporter_buffer.close(
                    timeout_seconds=validated_timeout
                )
            except ExporterCloseTimeoutError:
                exporter = self._exporter_buffer.snapshot()
                return ProductObservabilityCloseResult(
                    lease_state=ProductObservabilityLeaseState.CLOSING,
                    exporter=exporter,
                    retained_for_retry=True,
                )
            except asyncio.CancelledError:
                raise
            except ObservabilityExporterError:
                exporter = self._exporter_buffer.snapshot()
                self._adapter._finish_close(ProductObservabilityLeaseState.FAILED)
                return ProductObservabilityCloseResult(
                    lease_state=ProductObservabilityLeaseState.FAILED,
                    exporter=exporter,
                    retained_for_retry=True,
                )

            state = (
                ProductObservabilityLeaseState.CLOSED
                if exporter.state == "closed"
                else ProductObservabilityLeaseState.FAILED
            )
            self._adapter._finish_close(state)
            return ProductObservabilityCloseResult(
                lease_state=state,
                exporter=exporter,
                retained_for_retry=state is not ProductObservabilityLeaseState.CLOSED,
            )


def _close_timeout(value: object) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("timeout_seconds must be a positive finite number")
    return float(value)


async def activate_product_observability_adapter(
    *,
    enabled: bool = False,
    context: object = None,
    exporter: object = None,
    capacity: int = 256,
    export_timeout_seconds: float = 1.0,
    close_timeout_seconds: float = 5.0,
) -> InactiveProductObservabilityActivation | ActiveProductObservabilityActivation:
    """Explicitly start the bounded package consumer when the feature is on.

    The feature-off return precedes validation or access of context, exporter,
    buffer, worker, and sink state.
    """

    if enabled is not True:
        return InactiveProductObservabilityActivation(route_fact=_disabled_route_fact())

    if type(context) is not ProductCompositionContext:
        raise ValueError("context must be an exact ProductCompositionContext")
    if not callable(exporter):
        raise ValueError("exporter must be an already-constructed callable")

    exporter_buffer = LiveVoiceObservabilityExporterBuffer(
        exporter=cast(ObservationExporter, exporter),
        enabled=True,
        capacity=capacity,
        export_timeout_seconds=export_timeout_seconds,
        close_timeout_seconds=close_timeout_seconds,
    )
    await exporter_buffer.start()
    route_fact = _package_only_route_fact()
    adapter = ProductObservabilityAdapter(
        context=context,
        exporter_buffer=exporter_buffer,
        route_fact=route_fact,
        construction_token=_CONSTRUCTION_TOKEN,
    )
    lease = ProductObservabilityLease(
        adapter=adapter,
        exporter_buffer=exporter_buffer,
        construction_token=_CONSTRUCTION_TOKEN,
    )
    return ActiveProductObservabilityActivation(
        route_fact=route_fact,
        adapter=adapter,
        lease=lease,
        _construction_token=_CONSTRUCTION_TOKEN,
    )


__all__ = [
    "ActiveProductObservabilityActivation",
    "InactiveProductObservabilityActivation",
    "ProductObservabilityAdapter",
    "ProductObservabilityAdapterSnapshot",
    "ProductObservabilityAdapterStats",
    "ProductObservabilityCloseResult",
    "ProductObservabilityDisposition",
    "ProductObservabilityLease",
    "ProductObservabilityLeaseState",
    "ProductObservabilityReason",
    "activate_product_observability_adapter",
]
