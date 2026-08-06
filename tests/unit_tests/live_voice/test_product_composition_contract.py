# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiuwenswarm.server.live_voice.product_composition_contract import (
    PRODUCT_COMPOSITION_CONTRACT_VERSION,
    ProductCompositionManifest,
    ProductCompositionContractViolation,
    ProductEvidenceId,
    ProductRouteFact,
    ProductRouteReason,
    ProductRouteTruth,
    ProductSegment,
    create_product_composition_manifest,
    route_fact_from_integrated_shell,
)


FIXTURE = (
    Path(__file__).parents[3]
    / "tests"
    / "fixtures"
    / "live_voice_product_composition_gate0_v1"
    / "contract.json"
)


class ExplodingIterable:
    def __iter__(self):
        raise AssertionError("feature-off inspected route facts")


def unavailable(segment: ProductSegment) -> ProductRouteFact:
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.UNAVAILABLE,
        reason_id=ProductRouteReason.ADAPTER_NOT_REGISTERED,
        evidence_ids=(ProductEvidenceId.GATE0_CONTRACT_ONLY,),
    )


def formal_evidence(
    segment: ProductSegment = ProductSegment.AUTHORITY,
) -> tuple[ProductEvidenceId, ...]:
    """Return synthetic contract-shape evidence; this is not runtime evidence."""

    evidence = (
        ProductEvidenceId.TRUSTED_AUTHORITY_RESOLVED,
        ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
        ProductEvidenceId.RUNTIME_PATH_OBSERVED,
    )
    stop_closure = {
        ProductSegment.P1_SPEECH_MEDIA: (
            ProductEvidenceId.MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED
        ),
        ProductSegment.P2_AGENT_INTERACTION: (
            ProductEvidenceId.P2_NOTIFICATION_BACKPRESSURE_CLOSED
        ),
    }.get(segment)
    return evidence if stop_closure is None else (*evidence, stop_closure)


def formal(segment: ProductSegment) -> ProductRouteFact:
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.FORMAL,
        reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
        evidence_ids=formal_evidence(segment),
        formal_runtime_observed=True,
    )


def test_fixture_matches_closed_gate0_vocabulary() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["contract_version"] == PRODUCT_COMPOSITION_CONTRACT_VERSION
    assert fixture["route_truth"] == [value.value for value in ProductRouteTruth]
    assert fixture["segments"] == [value.value for value in ProductSegment]
    assert fixture["reason_ids"] == [value.value for value in ProductRouteReason]
    assert fixture["evidence_ids"] == [value.value for value in ProductEvidenceId]


def test_feature_off_returns_before_inspecting_routes() -> None:
    manifest = create_product_composition_manifest(
        enabled=False, route_facts=ExplodingIterable()
    )
    assert manifest.enabled is False
    assert [route.segment for route in manifest.routes] == list(ProductSegment)
    assert {route.truth for route in manifest.routes} == {ProductRouteTruth.DISABLED}
    assert {route.reason_id for route in manifest.routes} == {
        ProductRouteReason.FEATURE_DISABLED
    }


def test_enabled_manifest_fills_missing_segments_as_unavailable() -> None:
    fallback = route_fact_from_integrated_shell(
        segment=ProductSegment.P1_SPEECH_MEDIA,
        feature_enabled=True,
        legacy_route_class="fallback",
    )
    substitute = route_fact_from_integrated_shell(
        segment=ProductSegment.P3_CONTROL,
        feature_enabled=True,
        legacy_route_class="demo_substitute",
    )
    manifest = create_product_composition_manifest(
        enabled=True, route_facts=(fallback, substitute)
    )
    assert manifest.routes[1] == fallback
    assert manifest.routes[4] == substitute
    assert manifest.routes[0] == unavailable(ProductSegment.AUTHORITY)
    assert all(
        route.truth is ProductRouteTruth.UNAVAILABLE
        for index, route in enumerate(manifest.routes)
        if index not in {1, 4}
    )


def test_enabled_manifest_without_supplied_facts_defaults_unavailable() -> None:
    manifest = create_product_composition_manifest(enabled=True)
    assert len(manifest.routes) == len(ProductSegment)
    assert all(
        route.truth is ProductRouteTruth.UNAVAILABLE
        and route.reason_id is ProductRouteReason.ADAPTER_NOT_REGISTERED
        for route in manifest.routes
    )


@pytest.mark.parametrize("legacy", ["unsupported", "unknown"])
def test_old_unsupported_and_unknown_map_to_unavailable(legacy: str) -> None:
    fact = route_fact_from_integrated_shell(
        segment=ProductSegment.P2_AGENT_INTERACTION,
        feature_enabled=True,
        legacy_route_class=legacy,
    )
    assert fact.truth is ProductRouteTruth.UNAVAILABLE
    assert fact.reason_id is ProductRouteReason.REQUESTED_ROUTE_UNAVAILABLE
    assert fact.formal_runtime_observed is False


def test_manifest_only_formal_seam_cannot_become_formal_truth() -> None:
    fact = route_fact_from_integrated_shell(
        segment=ProductSegment.P2_AGENT_INTERACTION,
        feature_enabled=True,
        legacy_route_class="formal",
    )
    assert fact.truth is ProductRouteTruth.UNAVAILABLE
    assert fact.reason_id is ProductRouteReason.FORMAL_ACTIVATION_EVIDENCE_MISSING
    assert ProductEvidenceId.NO_RUNTIME_EVIDENCE in fact.evidence_ids


def test_formal_requires_all_three_runtime_evidence_identifiers() -> None:
    with pytest.raises(
        ProductCompositionContractViolation,
        match="formal truth requires trusted authority",
    ):
        route_fact_from_integrated_shell(
            segment=ProductSegment.AUTHORITY,
            feature_enabled=True,
            legacy_route_class="formal",
            formal_runtime_observed=True,
            formal_evidence_ids=(ProductEvidenceId.RUNTIME_PATH_OBSERVED,),
        )

    fact = route_fact_from_integrated_shell(
        segment=ProductSegment.AUTHORITY,
        feature_enabled=True,
        legacy_route_class="formal",
        formal_runtime_observed=True,
        formal_evidence_ids=(*formal_evidence(),),
    )
    assert fact.truth is ProductRouteTruth.FORMAL
    assert fact.formal_runtime_observed is True


@pytest.mark.parametrize(
    ("segment", "required"),
    [
        (
            ProductSegment.P1_SPEECH_MEDIA,
            ProductEvidenceId.MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED,
        ),
        (
            ProductSegment.P2_AGENT_INTERACTION,
            ProductEvidenceId.P2_NOTIFICATION_BACKPRESSURE_CLOSED,
        ),
    ],
)
def test_formal_requires_its_segment_specific_activation_stop_closure(
    segment: ProductSegment,
    required: ProductEvidenceId,
) -> None:
    with pytest.raises(
        ProductCompositionContractViolation,
        match="affirmative activation-stop closure evidence",
    ):
        route_fact_from_integrated_shell(
            segment=segment,
            feature_enabled=True,
            legacy_route_class="formal",
            formal_runtime_observed=True,
            formal_evidence_ids=tuple(
                evidence
                for evidence in formal_evidence(segment)
                if evidence is not required
            ),
        )

    fact = route_fact_from_integrated_shell(
        segment=segment,
        feature_enabled=True,
        legacy_route_class="formal",
        formal_runtime_observed=True,
        formal_evidence_ids=formal_evidence(segment),
    )
    assert fact.truth is ProductRouteTruth.FORMAL


@pytest.mark.parametrize(
    "unresolved",
    [
        ProductEvidenceId.P2_NOTIFICATION_QUEUE_BLOCKING_RISK,
        ProductEvidenceId.DEV_AUDIO_LOG_PERSISTENCE_RISK,
    ],
)
def test_formal_rejects_unresolved_activation_stop_evidence(
    unresolved: ProductEvidenceId,
) -> None:
    with pytest.raises(
        ProductCompositionContractViolation,
        match="contradictory evidence",
    ):
        ProductRouteFact(
            segment=ProductSegment.AUTHORITY,
            truth=ProductRouteTruth.FORMAL,
            reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
            evidence_ids=(*formal_evidence(ProductSegment.AUTHORITY), unresolved),
            formal_runtime_observed=True,
        )


def test_dependent_formal_segment_requires_formal_authority() -> None:
    dependent = formal(ProductSegment.P1_SPEECH_MEDIA)
    with pytest.raises(
        ProductCompositionContractViolation,
        match="require a formal authority segment",
    ):
        create_product_composition_manifest(
            enabled=True,
            route_facts=(dependent,),
        )

    manifest = create_product_composition_manifest(
        enabled=True,
        route_facts=(formal(ProductSegment.AUTHORITY), dependent),
    )
    assert manifest.routes[0].truth is ProductRouteTruth.FORMAL
    assert manifest.routes[1].truth is ProductRouteTruth.FORMAL


def test_feature_off_mapping_does_not_inspect_legacy_fact() -> None:
    fact = route_fact_from_integrated_shell(
        segment=ProductSegment.P1_SPEECH_MEDIA,
        feature_enabled=False,
        legacy_route_class=object(),
    )
    assert fact.truth is ProductRouteTruth.DISABLED


def test_invalid_formal_observation_type_fails_closed() -> None:
    with pytest.raises(
        ProductCompositionContractViolation,
        match="formal_runtime_observed must be a boolean",
    ):
        route_fact_from_integrated_shell(
            segment=ProductSegment.P2_AGENT_INTERACTION,
            feature_enabled=True,
            legacy_route_class="formal",
            formal_runtime_observed="yes",  # type: ignore[arg-type]
        )


def test_truth_reason_and_evidence_mismatches_fail_closed() -> None:
    with pytest.raises(
        ProductCompositionContractViolation,
        match="reason_id is incompatible",
    ):
        ProductRouteFact(
            segment=ProductSegment.P3_PROGRESS,
            truth=ProductRouteTruth.UNAVAILABLE,
            reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
            evidence_ids=(ProductEvidenceId.GATE0_CONTRACT_ONLY,),
        )

    with pytest.raises(
        ProductCompositionContractViolation,
        match="contradictory evidence",
    ):
        ProductRouteFact(
            segment=ProductSegment.P1_SPEECH_MEDIA,
            truth=ProductRouteTruth.FALLBACK,
            reason_id=ProductRouteReason.EXPLICIT_FALLBACK_ACTIVE,
            evidence_ids=(
                ProductEvidenceId.FALLBACK_ROUTE_SELECTED,
                ProductEvidenceId.RUNTIME_PATH_OBSERVED,
            ),
        )


def test_disabled_manifest_rejects_non_route_values_stably() -> None:
    with pytest.raises(
        ProductCompositionContractViolation,
        match="routes must contain ProductRouteFact values",
    ):
        ProductCompositionManifest(
            contract_version=PRODUCT_COMPOSITION_CONTRACT_VERSION,
            enabled=False,
            routes=(object(),),  # type: ignore[arg-type]
        )
    with pytest.raises(
        ProductCompositionContractViolation,
        match="missing its required evidence",
    ):
        ProductRouteFact(
            segment=ProductSegment.P3_CONTROL,
            truth=ProductRouteTruth.DEMO_SUBSTITUTE,
            reason_id=ProductRouteReason.D047_DEMO_SUBSTITUTE_ACTIVE,
            evidence_ids=(ProductEvidenceId.GATE0_CONTRACT_ONLY,),
        )


def test_duplicate_segments_are_rejected() -> None:
    fact = unavailable(ProductSegment.AUTHORITY)
    with pytest.raises(
        ProductCompositionContractViolation,
        match="duplicate segments",
    ):
        create_product_composition_manifest(enabled=True, route_facts=(fact, fact))
