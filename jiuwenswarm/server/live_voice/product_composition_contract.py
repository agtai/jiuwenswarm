# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure Gate-0 contract for Live Voice product composition.

This module is intentionally not a composition root.  It validates bounded route
facts and maps the older Web-shell diagnostic vocabulary into the product truth
vocabulary without importing, constructing, starting, or calling any Adapter.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


PRODUCT_COMPOSITION_CONTRACT_VERSION = "live-voice.product-composition.gate0.v1"


class ProductCompositionContractViolation(ValueError):
    """Raised when a route fact would overstate composition truth."""


class ProductRouteTruth(StrEnum):
    FORMAL = "formal"
    FALLBACK = "fallback"
    DEMO_SUBSTITUTE = "demo_substitute"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class ProductSegment(StrEnum):
    AUTHORITY = "authority"
    P1_SPEECH_MEDIA = "p1.speech_media"
    P2_AGENT_INTERACTION = "p2.agent_interaction"
    P3_QUERY = "p3.query"
    P3_CONTROL = "p3.control"
    P3_PROGRESS = "p3.progress"
    BROWSER_AUDIO = "browser.audio"
    OBSERVABILITY = "observability"


class ProductRouteReason(StrEnum):
    FORMAL_ROUTE_OBSERVED = "FORMAL_ROUTE_OBSERVED"
    EXPLICIT_FALLBACK_ACTIVE = "EXPLICIT_FALLBACK_ACTIVE"
    D047_DEMO_SUBSTITUTE_ACTIVE = "D047_DEMO_SUBSTITUTE_ACTIVE"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    ADAPTER_NOT_REGISTERED = "ADAPTER_NOT_REGISTERED"
    REQUESTED_ROUTE_UNAVAILABLE = "REQUESTED_ROUTE_UNAVAILABLE"
    FORMAL_ACTIVATION_EVIDENCE_MISSING = "FORMAL_ACTIVATION_EVIDENCE_MISSING"
    TRUSTED_AUTHORITY_UNAVAILABLE = "TRUSTED_AUTHORITY_UNAVAILABLE"
    SPEECH_AUTHORIZATION_UNAVAILABLE = "SPEECH_AUTHORIZATION_UNAVAILABLE"
    MEDIA_AUTHORITY_UNAVAILABLE = "MEDIA_AUTHORITY_UNAVAILABLE"
    MEDIA_PROVIDER_UNAVAILABLE = "MEDIA_PROVIDER_UNAVAILABLE"
    MEDIA_TRANSPORT_UNAVAILABLE = "MEDIA_TRANSPORT_UNAVAILABLE"
    MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN = "MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN"
    P2_AUTHORITY_UNAVAILABLE = "P2_AUTHORITY_UNAVAILABLE"
    P2_RUNTIME_UNAVAILABLE = "P2_RUNTIME_UNAVAILABLE"
    P2_NOTIFICATION_BACKPRESSURE_UNRESOLVED = "P2_NOTIFICATION_BACKPRESSURE_UNRESOLVED"
    P3_QUERY_AUTHORITY_UNAVAILABLE = "P3_QUERY_AUTHORITY_UNAVAILABLE"
    P3_CONFIRMATION_ISSUER_UNAVAILABLE = "P3_CONFIRMATION_ISSUER_UNAVAILABLE"
    TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE = (
        "TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE"
    )
    BROWSER_AUDIO_UNAVAILABLE = "BROWSER_AUDIO_UNAVAILABLE"
    OBSERVABILITY_CONSUMER_UNAVAILABLE = "OBSERVABILITY_CONSUMER_UNAVAILABLE"
    ACTIVATION_FAILED = "ACTIVATION_FAILED"


class ProductEvidenceId(StrEnum):
    GATE0_CONTRACT_ONLY = "GATE0_CONTRACT_ONLY"
    FEATURE_FLAG_OFF = "FEATURE_FLAG_OFF"
    TRUSTED_AUTHORITY_RESOLVED = "TRUSTED_AUTHORITY_RESOLVED"
    FORMAL_ACTIVATION_LEASE_OPEN = "FORMAL_ACTIVATION_LEASE_OPEN"
    RUNTIME_PATH_OBSERVED = "RUNTIME_PATH_OBSERVED"
    P2_NOTIFICATION_BACKPRESSURE_CLOSED = "P2_NOTIFICATION_BACKPRESSURE_CLOSED"
    MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED = "MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED"
    FALLBACK_ROUTE_SELECTED = "FALLBACK_ROUTE_SELECTED"
    D047_LEGACY_ROUTE_SELECTED = "D047_LEGACY_ROUTE_SELECTED"
    FORMAL_BATCH_SPEECH_FOUNDATION = "FORMAL_BATCH_SPEECH_FOUNDATION"
    D059_AGENT_CR_FOUNDATION = "D059_AGENT_CR_FOUNDATION"
    P3_QUERY_FOUNDATION = "P3_QUERY_FOUNDATION"
    TASK_EVENT_LIVE_ONLY = "TASK_EVENT_LIVE_ONLY"
    PROGRESS_ARBITER_CONTIGUOUS_SEQUENCE_REQUIRED = (
        "PROGRESS_ARBITER_CONTIGUOUS_SEQUENCE_REQUIRED"
    )
    BROWSER_AUDIO_FOUNDATION = "BROWSER_AUDIO_FOUNDATION"
    OBSERVABILITY_FOUNDATION = "OBSERVABILITY_FOUNDATION"
    P2_NOTIFICATION_QUEUE_BLOCKING_RISK = "P2_NOTIFICATION_QUEUE_BLOCKING_RISK"
    DEV_AUDIO_LOG_PERSISTENCE_RISK = "DEV_AUDIO_LOG_PERSISTENCE_RISK"
    PREINTEGRATION_STATIC_AUDIT_ONLY = "PREINTEGRATION_STATIC_AUDIT_ONLY"
    PACKAGE_CONTRACT_ONLY = "PACKAGE_CONTRACT_ONLY"
    NO_RUNTIME_EVIDENCE = "NO_RUNTIME_EVIDENCE"


_REASON_BY_TRUTH = {
    ProductRouteTruth.FORMAL: frozenset({ProductRouteReason.FORMAL_ROUTE_OBSERVED}),
    ProductRouteTruth.FALLBACK: frozenset(
        {ProductRouteReason.EXPLICIT_FALLBACK_ACTIVE}
    ),
    ProductRouteTruth.DEMO_SUBSTITUTE: frozenset(
        {ProductRouteReason.D047_DEMO_SUBSTITUTE_ACTIVE}
    ),
    ProductRouteTruth.DISABLED: frozenset({ProductRouteReason.FEATURE_DISABLED}),
    ProductRouteTruth.UNAVAILABLE: frozenset(
        reason
        for reason in ProductRouteReason
        if reason
        not in {
            ProductRouteReason.FORMAL_ROUTE_OBSERVED,
            ProductRouteReason.EXPLICIT_FALLBACK_ACTIVE,
            ProductRouteReason.D047_DEMO_SUBSTITUTE_ACTIVE,
            ProductRouteReason.FEATURE_DISABLED,
        }
    ),
}

_FORMAL_EVIDENCE = frozenset(
    {
        ProductEvidenceId.TRUSTED_AUTHORITY_RESOLVED,
        ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
        ProductEvidenceId.RUNTIME_PATH_OBSERVED,
    }
)

_FORMAL_STOP_CLOSURE_BY_SEGMENT = {
    ProductSegment.P1_SPEECH_MEDIA: (
        ProductEvidenceId.MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED
    ),
    ProductSegment.P2_AGENT_INTERACTION: (
        ProductEvidenceId.P2_NOTIFICATION_BACKPRESSURE_CLOSED
    ),
}

_FORBIDDEN_EVIDENCE_BY_TRUTH = {
    ProductRouteTruth.FORMAL: frozenset(
        {
            ProductEvidenceId.GATE0_CONTRACT_ONLY,
            ProductEvidenceId.FEATURE_FLAG_OFF,
            ProductEvidenceId.FALLBACK_ROUTE_SELECTED,
            ProductEvidenceId.D047_LEGACY_ROUTE_SELECTED,
            ProductEvidenceId.P2_NOTIFICATION_QUEUE_BLOCKING_RISK,
            ProductEvidenceId.DEV_AUDIO_LOG_PERSISTENCE_RISK,
            ProductEvidenceId.NO_RUNTIME_EVIDENCE,
        }
    ),
    ProductRouteTruth.FALLBACK: frozenset(
        _FORMAL_EVIDENCE
        | {
            ProductEvidenceId.FEATURE_FLAG_OFF,
            ProductEvidenceId.D047_LEGACY_ROUTE_SELECTED,
        }
    ),
    ProductRouteTruth.DEMO_SUBSTITUTE: frozenset(
        _FORMAL_EVIDENCE
        | {
            ProductEvidenceId.FEATURE_FLAG_OFF,
            ProductEvidenceId.FALLBACK_ROUTE_SELECTED,
        }
    ),
    ProductRouteTruth.UNAVAILABLE: frozenset(
        {
            ProductEvidenceId.FEATURE_FLAG_OFF,
            ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
            ProductEvidenceId.RUNTIME_PATH_OBSERVED,
            ProductEvidenceId.FALLBACK_ROUTE_SELECTED,
            ProductEvidenceId.D047_LEGACY_ROUTE_SELECTED,
        }
    ),
    ProductRouteTruth.DISABLED: frozenset(
        evidence
        for evidence in ProductEvidenceId
        if evidence is not ProductEvidenceId.FEATURE_FLAG_OFF
    ),
}


@dataclass(frozen=True, slots=True)
class ProductRouteFact:
    segment: ProductSegment
    truth: ProductRouteTruth
    reason_id: ProductRouteReason
    evidence_ids: tuple[ProductEvidenceId, ...]
    formal_runtime_observed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.segment, ProductSegment):
            raise ProductCompositionContractViolation(
                "segment must be a ProductSegment"
            )
        if not isinstance(self.truth, ProductRouteTruth):
            raise ProductCompositionContractViolation(
                "truth must be a ProductRouteTruth"
            )
        if not isinstance(self.reason_id, ProductRouteReason):
            raise ProductCompositionContractViolation(
                "reason_id must be a ProductRouteReason"
            )
        if self.reason_id not in _REASON_BY_TRUTH[self.truth]:
            raise ProductCompositionContractViolation(
                "reason_id is incompatible with route truth"
            )
        if type(self.evidence_ids) is not tuple or not self.evidence_ids:
            raise ProductCompositionContractViolation(
                "evidence_ids must be a non-empty tuple"
            )
        if any(
            not isinstance(evidence_id, ProductEvidenceId)
            for evidence_id in self.evidence_ids
        ):
            raise ProductCompositionContractViolation(
                "evidence_ids must contain ProductEvidenceId values"
            )
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ProductCompositionContractViolation(
                "evidence_ids must not contain duplicates"
            )
        if type(self.formal_runtime_observed) is not bool:
            raise ProductCompositionContractViolation(
                "formal_runtime_observed must be a boolean"
            )

        evidence = frozenset(self.evidence_ids)
        if evidence & _FORBIDDEN_EVIDENCE_BY_TRUTH[self.truth]:
            raise ProductCompositionContractViolation(
                "route truth contains contradictory evidence"
            )
        if self.truth is ProductRouteTruth.FORMAL:
            if not self.formal_runtime_observed or not _FORMAL_EVIDENCE.issubset(
                evidence
            ):
                raise ProductCompositionContractViolation(
                    "formal truth requires trusted authority, an open activation "
                    "lease, and observed runtime-path evidence"
                )
            required_stop_closure = _FORMAL_STOP_CLOSURE_BY_SEGMENT.get(self.segment)
            if (
                required_stop_closure is not None
                and required_stop_closure not in evidence
            ):
                raise ProductCompositionContractViolation(
                    "formal segment is missing its affirmative activation-stop "
                    "closure evidence"
                )
        elif self.formal_runtime_observed:
            raise ProductCompositionContractViolation(
                "non-formal truth cannot claim formal runtime observation"
            )

        required_evidence = {
            ProductRouteTruth.FALLBACK: ProductEvidenceId.FALLBACK_ROUTE_SELECTED,
            ProductRouteTruth.DEMO_SUBSTITUTE: (
                ProductEvidenceId.D047_LEGACY_ROUTE_SELECTED
            ),
            ProductRouteTruth.DISABLED: ProductEvidenceId.FEATURE_FLAG_OFF,
        }.get(self.truth)
        if required_evidence is not None and required_evidence not in evidence:
            raise ProductCompositionContractViolation(
                "route truth is missing its required evidence identifier"
            )


@dataclass(frozen=True, slots=True)
class ProductCompositionManifest:
    contract_version: str
    enabled: bool
    routes: tuple[ProductRouteFact, ...]

    def __post_init__(self) -> None:
        if self.contract_version != PRODUCT_COMPOSITION_CONTRACT_VERSION:
            raise ProductCompositionContractViolation(
                "unsupported product composition contract version"
            )
        if type(self.enabled) is not bool:
            raise ProductCompositionContractViolation("enabled must be a boolean")
        if type(self.routes) is not tuple:
            raise ProductCompositionContractViolation("routes must be a tuple")
        if any(not isinstance(route, ProductRouteFact) for route in self.routes):
            raise ProductCompositionContractViolation(
                "routes must contain ProductRouteFact values"
            )
        if tuple(route.segment for route in self.routes) != tuple(ProductSegment):
            raise ProductCompositionContractViolation(
                "manifest routes must contain every segment in canonical order"
            )
        if not self.enabled and any(
            route.truth is not ProductRouteTruth.DISABLED for route in self.routes
        ):
            raise ProductCompositionContractViolation(
                "disabled manifest must report every segment disabled"
            )
        authority = self.routes[0]
        if (
            any(route.truth is ProductRouteTruth.FORMAL for route in self.routes[1:])
            and authority.truth is not ProductRouteTruth.FORMAL
        ):
            raise ProductCompositionContractViolation(
                "formal product segments require a formal authority segment"
            )


def _disabled_fact(segment: ProductSegment) -> ProductRouteFact:
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.DISABLED,
        reason_id=ProductRouteReason.FEATURE_DISABLED,
        evidence_ids=(ProductEvidenceId.FEATURE_FLAG_OFF,),
    )


def create_product_composition_manifest(
    *, enabled: bool, route_facts: Iterable[ProductRouteFact] | object = ()
) -> ProductCompositionManifest:
    """Build a pure manifest; feature-off returns before inspecting route facts."""

    if type(enabled) is not bool:
        raise ProductCompositionContractViolation("enabled must be a boolean")
    if not enabled:
        return ProductCompositionManifest(
            contract_version=PRODUCT_COMPOSITION_CONTRACT_VERSION,
            enabled=False,
            routes=tuple(_disabled_fact(segment) for segment in ProductSegment),
        )

    if not isinstance(route_facts, Iterable):
        raise ProductCompositionContractViolation("route_facts must be iterable")
    facts = tuple(route_facts)
    if any(not isinstance(fact, ProductRouteFact) for fact in facts):
        raise ProductCompositionContractViolation(
            "route_facts must contain ProductRouteFact values"
        )
    by_segment: dict[ProductSegment, ProductRouteFact] = {}
    for fact in facts:
        if fact.segment in by_segment:
            raise ProductCompositionContractViolation(
                "route_facts must not contain duplicate segments"
            )
        by_segment[fact.segment] = fact

    routes = tuple(
        by_segment.get(
            segment,
            ProductRouteFact(
                segment=segment,
                truth=ProductRouteTruth.UNAVAILABLE,
                reason_id=ProductRouteReason.ADAPTER_NOT_REGISTERED,
                evidence_ids=(ProductEvidenceId.GATE0_CONTRACT_ONLY,),
            ),
        )
        for segment in ProductSegment
    )
    return ProductCompositionManifest(
        contract_version=PRODUCT_COMPOSITION_CONTRACT_VERSION,
        enabled=True,
        routes=routes,
    )


def route_fact_from_integrated_shell(
    *,
    segment: ProductSegment,
    feature_enabled: bool,
    legacy_route_class: object,
    formal_runtime_observed: bool = False,
    formal_evidence_ids: tuple[ProductEvidenceId, ...] = (),
) -> ProductRouteFact:
    """Map existing shell diagnostics without upgrading manifests to formal truth."""

    if type(feature_enabled) is not bool:
        raise ProductCompositionContractViolation("feature_enabled must be a boolean")
    if not feature_enabled:
        return _disabled_fact(segment)
    if not isinstance(segment, ProductSegment):
        raise ProductCompositionContractViolation("segment must be a ProductSegment")
    if type(formal_runtime_observed) is not bool:
        raise ProductCompositionContractViolation(
            "formal_runtime_observed must be a boolean"
        )
    if type(legacy_route_class) is not str:
        raise ProductCompositionContractViolation("legacy_route_class must be a string")

    if legacy_route_class == "fallback":
        return ProductRouteFact(
            segment=segment,
            truth=ProductRouteTruth.FALLBACK,
            reason_id=ProductRouteReason.EXPLICIT_FALLBACK_ACTIVE,
            evidence_ids=(ProductEvidenceId.FALLBACK_ROUTE_SELECTED,),
        )
    if legacy_route_class == "demo_substitute":
        return ProductRouteFact(
            segment=segment,
            truth=ProductRouteTruth.DEMO_SUBSTITUTE,
            reason_id=ProductRouteReason.D047_DEMO_SUBSTITUTE_ACTIVE,
            evidence_ids=(ProductEvidenceId.D047_LEGACY_ROUTE_SELECTED,),
        )
    if legacy_route_class == "formal":
        if not formal_runtime_observed:
            return ProductRouteFact(
                segment=segment,
                truth=ProductRouteTruth.UNAVAILABLE,
                reason_id=(ProductRouteReason.FORMAL_ACTIVATION_EVIDENCE_MISSING),
                evidence_ids=(
                    ProductEvidenceId.GATE0_CONTRACT_ONLY,
                    ProductEvidenceId.NO_RUNTIME_EVIDENCE,
                ),
            )
        return ProductRouteFact(
            segment=segment,
            truth=ProductRouteTruth.FORMAL,
            reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
            evidence_ids=formal_evidence_ids,
            formal_runtime_observed=True,
        )
    if legacy_route_class in {"unsupported", "unknown"}:
        return ProductRouteFact(
            segment=segment,
            truth=ProductRouteTruth.UNAVAILABLE,
            reason_id=ProductRouteReason.REQUESTED_ROUTE_UNAVAILABLE,
            evidence_ids=(
                ProductEvidenceId.GATE0_CONTRACT_ONLY,
                ProductEvidenceId.NO_RUNTIME_EVIDENCE,
            ),
        )
    raise ProductCompositionContractViolation("unknown legacy route class")
