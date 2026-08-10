from __future__ import annotations

from typing import Any, Mapping

from jiuwenswarm.server.live_voice.w2_fault_plan import (
    W2FaultClass,
    W2FaultPlane,
    derive_w2_product_fault_plan,
)


SCHEMA = "machine-private.w2-product-fault-plan.v1"


def derive_product_fault_plan_payload(
    *, policy_id: str, candidate_sha: str, evidence_set_id: str
) -> dict[str, Any]:
    """Serialize only the central authority's closed deterministic plan."""

    plan = derive_w2_product_fault_plan(
        policy_id=policy_id,
        candidate_sha=candidate_sha,
        evidence_set_id=evidence_set_id,
    )
    return {
        "schema": SCHEMA,
        "policy_id": plan.policy_id,
        "candidate_sha": plan.candidate_sha,
        "evidence_set_id": plan.evidence_set_id,
        "derivation_version": plan.derivation_version,
        "items": [
            {
                "pair": item.pair,
                "plane": item.plane.value,
                "class": item.fault_class.value,
                "operation": item.operation,
                "request_id": item.request_id,
                "source_record_id": item.source_record_id,
            }
            for item in plan.items
        ],
    }


def validate_product_fault_plan_payload(
    value: object,
    *,
    policy_id: str,
    candidate_sha: str,
    evidence_set_id: str,
) -> dict[str, Any]:
    expected = derive_product_fault_plan_payload(
        policy_id=policy_id,
        candidate_sha=candidate_sha,
        evidence_set_id=evidence_set_id,
    )
    if value != expected:
        raise RuntimeError(
            "runtime product fault plan is not exactly derived from signed policy"
        )
    return expected


def require_product_fault(
    payload: Mapping[str, object],
    *,
    pair: int,
    plane: W2FaultPlane | str,
    fault_class: W2FaultClass | str,
) -> dict[str, object]:
    exact_plane = W2FaultPlane(plane).value
    exact_class = W2FaultClass(fault_class).value
    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError("runtime product fault plan items are missing")
    matches = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("pair") == pair
        and item.get("plane") == exact_plane
        and item.get("class") == exact_class
    ]
    if len(matches) != 1:
        raise RuntimeError("runtime product fault identity is missing or duplicated")
    return matches[0]


__all__ = [
    "SCHEMA",
    "derive_product_fault_plan_payload",
    "require_product_fault",
    "validate_product_fault_plan_payload",
]
