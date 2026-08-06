# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Default-off lifecycle owner for Live Voice product composition.

The root is intentionally transport- and Provider-neutral.  Package owners
contribute exact activation callbacks; this module only preserves canonical
segment order, validates truthful route facts, and retains cleanup.  It does not
resolve browser claims, register a Gateway route, or turn package evidence into
runtime evidence.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from .product_composition_contract import (
    ProductCompositionContractViolation,
    ProductCompositionManifest,
    ProductEvidenceId,
    ProductRouteFact,
    ProductRouteReason,
    ProductRouteTruth,
    ProductSegment,
    create_product_composition_manifest,
)


class ProductCompositionRootViolation(ValueError):
    """Raised when composition input or an Adapter result is invalid."""


class ProductCompositionActivationError(RuntimeError):
    """Raised after an activation failed or could not be rolled back cleanly."""

    def __init__(
        self,
        reason: str,
        *,
        cleanup_lease: ProductCompositionLease | None = None,
    ) -> None:
        super().__init__("Live Voice product composition activation failed")
        self.reason = reason
        self.cleanup_lease = cleanup_lease


class ProductCompositionLeaseCloseError(RuntimeError):
    """Raised while failed segment leases remain retained for another close."""

    def __init__(self, lease: ProductCompositionLease) -> None:
        super().__init__("Live Voice product composition cleanup is incomplete")
        self.lease = lease


class ProductSegmentActivationError(RuntimeError):
    """Safe Adapter failure which can transfer partial cleanup ownership."""

    def __init__(
        self,
        reason: str,
        *,
        cleanup_lease: SegmentLease | None = None,
    ) -> None:
        _required_text(reason, "segment_failure.reason")
        if cleanup_lease is not None and not callable(
            getattr(cleanup_lease, "close", None)
        ):
            raise ProductCompositionRootViolation(
                "segment failure cleanup lease must expose close"
            )
        super().__init__("Live Voice product segment activation failed")
        self.reason = reason
        self.cleanup_lease = cleanup_lease


class SegmentLease(Protocol):
    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ProductCompositionContext:
    session_id: str
    correlation_id: str

    def __post_init__(self) -> None:
        _required_text(self.session_id, "context.session_id")
        _required_text(self.correlation_id, "context.correlation_id")


@dataclass(frozen=True, slots=True)
class ProductSegmentActivation:
    route_fact: ProductRouteFact
    lease: SegmentLease | None

    def __post_init__(self) -> None:
        if not isinstance(self.route_fact, ProductRouteFact):
            raise ProductCompositionRootViolation(
                "segment activation requires a ProductRouteFact"
            )
        is_formal = self.route_fact.truth is ProductRouteTruth.FORMAL
        if is_formal and self.lease is None:
            raise ProductCompositionRootViolation(
                "formal segment activation requires a retained lease"
            )
        if not is_formal and self.lease is not None:
            raise ProductCompositionRootViolation(
                "non-formal segment activation cannot retain product effects"
            )
        if self.lease is not None and not callable(getattr(self.lease, "close", None)):
            raise ProductCompositionRootViolation(
                "segment activation lease must expose close"
            )


SegmentActivationCallback = Callable[
    [ProductCompositionContext],
    Awaitable[ProductSegmentActivation],
]


@dataclass(frozen=True, slots=True)
class ProductCompositionRegistration:
    segment: ProductSegment
    adapter_id: str
    activate: SegmentActivationCallback

    def __post_init__(self) -> None:
        if not isinstance(self.segment, ProductSegment):
            raise ProductCompositionRootViolation(
                "registration.segment must be a ProductSegment"
            )
        _required_text(self.adapter_id, "registration.adapter_id")
        if not callable(self.activate):
            raise ProductCompositionRootViolation(
                "registration.activate must be callable"
            )


@dataclass(frozen=True, slots=True)
class ProductCompositionActivation:
    manifest: ProductCompositionManifest
    activated_adapter_ids: tuple[str, ...]
    lease: ProductCompositionLease | None


@dataclass(slots=True)
class _RetainedSegmentLease:
    adapter_id: str
    lease: SegmentLease


class ProductCompositionLease:
    """Idempotent, retryable LIFO cleanup for one cumulative activation."""

    def __init__(self, leases: Iterable[_RetainedSegmentLease]) -> None:
        self._leases = list(leases)
        self._lock = asyncio.Lock()

    @property
    def pending_adapter_ids(self) -> tuple[str, ...]:
        return tuple(item.adapter_id for item in self._leases)

    @property
    def closed(self) -> bool:
        return not self._leases

    async def close(self) -> None:
        async with self._lock:
            if not self._leases:
                return
            failed: set[int] = set()
            for index in range(len(self._leases) - 1, -1, -1):
                retained = self._leases[index]
                try:
                    result = retained.lease.close()
                    if not inspect.isawaitable(result):
                        raise TypeError("segment close must return an awaitable")
                    await result
                except asyncio.CancelledError:
                    # Retain the cancelled owner, every lower owner that has not
                    # been attempted, and any higher owner that already failed.
                    failed.update(range(index + 1))
                    self._leases = [
                        item
                        for item_index, item in enumerate(self._leases)
                        if item_index in failed
                    ]
                    raise
                except Exception:  # retain every failed owner for explicit retry
                    failed.add(index)
            self._leases = [
                retained
                for index, retained in enumerate(self._leases)
                if index in failed
            ]
            if self._leases:
                raise ProductCompositionLeaseCloseError(self)


class ProductCompositionRoot:
    """Compose injected product Adapters without owning their business effects."""

    def __init__(
        self,
        *,
        enabled: bool,
        registrations: Iterable[ProductCompositionRegistration] | object = (),
    ) -> None:
        if type(enabled) is not bool:
            raise ProductCompositionRootViolation("enabled must be a boolean")
        self._enabled = enabled
        # Preserve the exact feature-off rule: do not iterate or inspect package
        # registrations until an enabled preview or activation is requested.
        self._registration_input = registrations
        self._registrations: tuple[ProductCompositionRegistration, ...] | None = None

    def preview(self) -> ProductCompositionManifest:
        if not self._enabled:
            return create_product_composition_manifest(enabled=False)
        registrations = self._normalize_registrations()
        return create_product_composition_manifest(
            enabled=True,
            route_facts=tuple(
                _registered_but_inactive(registration.segment)
                for registration in registrations
            ),
        )

    async def activate(
        self, context: ProductCompositionContext | object
    ) -> ProductCompositionActivation:
        if not self._enabled:
            return ProductCompositionActivation(
                manifest=create_product_composition_manifest(enabled=False),
                activated_adapter_ids=(),
                lease=None,
            )
        if not isinstance(context, ProductCompositionContext):
            raise ProductCompositionRootViolation(
                "activation requires ProductCompositionContext"
            )
        registrations = self._normalize_registrations()
        facts: list[ProductRouteFact] = []
        retained: list[_RetainedSegmentLease] = []
        activated_ids: list[str] = []
        try:
            authority_registration = next(
                (
                    registration
                    for registration in registrations
                    if registration.segment is ProductSegment.AUTHORITY
                ),
                None,
            )
            if authority_registration is None:
                facts.extend(
                    _authority_unavailable(registration.segment)
                    for registration in registrations
                )
                return ProductCompositionActivation(
                    manifest=create_product_composition_manifest(
                        enabled=True, route_facts=facts
                    ),
                    activated_adapter_ids=(),
                    lease=None,
                )

            ordered_activation = (
                authority_registration,
                *(
                    registration
                    for registration in registrations
                    if registration is not authority_registration
                ),
            )
            for registration_index, registration in enumerate(ordered_activation):
                try:
                    callback_result = registration.activate(context)
                    if not inspect.isawaitable(callback_result):
                        raise ProductCompositionRootViolation(
                            "registration.activate must return an awaitable"
                        )
                    activation = await callback_result
                except ProductSegmentActivationError as segment_error:
                    if segment_error.cleanup_lease is not None:
                        retained.append(
                            _RetainedSegmentLease(
                                adapter_id=registration.adapter_id,
                                lease=segment_error.cleanup_lease,
                            )
                        )
                    raise
                if not isinstance(activation, ProductSegmentActivation):
                    raise ProductCompositionRootViolation(
                        "registration returned an invalid segment activation"
                    )
                if activation.lease is not None:
                    # Take cleanup ownership before validating the returned
                    # route identity.  A malformed Adapter may already have
                    # opened effects; rejecting its fact must still roll them
                    # back and retain any failed teardown.
                    retained.append(
                        _RetainedSegmentLease(
                            adapter_id=registration.adapter_id,
                            lease=activation.lease,
                        )
                    )
                if activation.route_fact.segment is not registration.segment:
                    raise ProductCompositionRootViolation(
                        "registration returned a route fact for another segment"
                    )
                facts.append(activation.route_fact)
                if activation.lease is not None:
                    activated_ids.append(registration.adapter_id)

                if (
                    registration_index == 0
                    and activation.route_fact.truth is not ProductRouteTruth.FORMAL
                ):
                    # An unavailable authority means zero downstream Adapter
                    # calls for this activation attempt.
                    facts.extend(
                        _authority_unavailable(item.segment)
                        for item in ordered_activation[1:]
                    )
                    break

            manifest = create_product_composition_manifest(
                enabled=True, route_facts=facts
            )
        except asyncio.CancelledError:
            cleanup = ProductCompositionLease(retained) if retained else None
            if cleanup is not None:
                try:
                    await asyncio.shield(cleanup.close())
                except (
                    ProductCompositionLeaseCloseError,
                    asyncio.CancelledError,
                ) as cleanup_error:
                    raise ProductCompositionActivationError(
                        "ACTIVATION_CANCELLED_ROLLBACK_INCOMPLETE",
                        cleanup_lease=cleanup,
                    ) from cleanup_error
            raise
        except Exception as error:
            cleanup = ProductCompositionLease(retained) if retained else None
            if cleanup is not None:
                try:
                    await cleanup.close()
                except (
                    ProductCompositionLeaseCloseError,
                    asyncio.CancelledError,
                ) as cleanup_error:
                    raise ProductCompositionActivationError(
                        "ACTIVATION_ROLLBACK_INCOMPLETE",
                        cleanup_lease=cleanup,
                    ) from cleanup_error
            if isinstance(
                error,
                (
                    ProductCompositionRootViolation,
                    ProductCompositionContractViolation,
                ),
            ):
                reason = "INVALID_ADAPTER_ACTIVATION"
            else:
                reason = "ADAPTER_ACTIVATION_FAILED"
            raise ProductCompositionActivationError(reason) from error

        lease = ProductCompositionLease(retained) if retained else None
        return ProductCompositionActivation(
            manifest=manifest,
            activated_adapter_ids=tuple(activated_ids),
            lease=lease,
        )

    def _normalize_registrations(
        self,
    ) -> tuple[ProductCompositionRegistration, ...]:
        if self._registrations is not None:
            return self._registrations
        value = self._registration_input
        if not isinstance(value, Iterable):
            raise ProductCompositionRootViolation("registrations must be iterable")
        registrations = tuple(value)
        if any(
            not isinstance(item, ProductCompositionRegistration)
            for item in registrations
        ):
            raise ProductCompositionRootViolation(
                "registrations must contain ProductCompositionRegistration values"
            )
        segments = tuple(item.segment for item in registrations)
        if len(set(segments)) != len(segments):
            raise ProductCompositionRootViolation(
                "registrations must not contain duplicate segments"
            )
        adapter_ids = tuple(item.adapter_id for item in registrations)
        if len(set(adapter_ids)) != len(adapter_ids):
            raise ProductCompositionRootViolation(
                "registrations must not contain duplicate adapter IDs"
            )
        ordered = tuple(
            sorted(
                registrations,
                key=lambda item: tuple(ProductSegment).index(item.segment),
            )
        )
        self._registrations = ordered
        return ordered


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductCompositionRootViolation(f"{field_name} must be non-empty")
    return value


def _registered_but_inactive(segment: ProductSegment) -> ProductRouteFact:
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.UNAVAILABLE,
        reason_id=ProductRouteReason.FORMAL_ACTIVATION_EVIDENCE_MISSING,
        evidence_ids=(
            ProductEvidenceId.PACKAGE_CONTRACT_ONLY,
            ProductEvidenceId.NO_RUNTIME_EVIDENCE,
        ),
    )


def _authority_unavailable(segment: ProductSegment) -> ProductRouteFact:
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.UNAVAILABLE,
        reason_id=ProductRouteReason.TRUSTED_AUTHORITY_UNAVAILABLE,
        evidence_ids=(
            ProductEvidenceId.PACKAGE_CONTRACT_ONLY,
            ProductEvidenceId.NO_RUNTIME_EVIDENCE,
        ),
    )


__all__ = [
    "ProductCompositionActivation",
    "ProductCompositionActivationError",
    "ProductCompositionContext",
    "ProductCompositionLease",
    "ProductCompositionLeaseCloseError",
    "ProductCompositionRegistration",
    "ProductCompositionRoot",
    "ProductCompositionRootViolation",
    "ProductSegmentActivation",
    "ProductSegmentActivationError",
    "SegmentActivationCallback",
    "SegmentLease",
]
