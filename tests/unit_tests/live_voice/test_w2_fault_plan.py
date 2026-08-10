# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib

import pytest

from jiuwenswarm.server.live_voice.w2_fault_plan import (
    W2_FAULT_DERIVATION_VERSION,
    W2FaultClass,
    W2FaultPlanError,
    W2FaultPlane,
    derive_w2_fault_identity,
    derive_w2_product_fault_plan,
)


_CANDIDATE = "a" * 40


def test_product_fault_plan_is_closed_deterministic_and_observer_exact() -> None:
    first = derive_w2_product_fault_plan(
        policy_id="w2-policy-attempt-1",
        candidate_sha=_CANDIDATE,
        evidence_set_id="w2-evidence-attempt-1",
    )
    second = derive_w2_product_fault_plan(
        policy_id="w2-policy-attempt-1",
        candidate_sha=_CANDIDATE,
        evidence_set_id="w2-evidence-attempt-1",
    )

    assert first == second
    assert first.derivation_version == W2_FAULT_DERIVATION_VERSION
    assert len(first.items) == 9
    assert len({item.request_id for item in first.items}) == 9
    assert len({item.source_record_id for item in first.items}) == 9
    assert [item.pair for item in first.items] == [1, 2, 3] * 3
    assert [item.fault_class for item in first.items] == [
        W2FaultClass.RETRIABLE,
        W2FaultClass.NON_RETRIABLE,
        W2FaultClass.ZERO_EFFECT,
    ] * 3
    assert [item.operation for item in first.items] == [
        "speech.recognize.batch",
        "speech.recognize.batch",
        "speech.recognize.batch",
        "live_voice.composition.p2.presentation.ack",
        "live_voice.composition.p2.presentation.ack",
        "live_voice.composition.p2.presentation.ack",
        "live_voice.composition.p3.progress.ack",
        "live_voice.composition.p3.mutate",
        "live_voice.composition.p3.mutate",
    ]
    assert all(
        item.source_record_id
        == "w2-request-"
        + hashlib.sha256(item.request_id.encode("utf-8")).hexdigest()[:32]
        for item in first.items
    )
    assert first.require(
        W2FaultPlane.P2_CONVERSATION, W2FaultClass.ZERO_EFFECT
    ).pair == 3


def test_fault_identity_binds_every_public_authority_field() -> None:
    baseline = derive_w2_fault_identity(
        policy_id="policy-a",
        candidate_sha=_CANDIDATE,
        evidence_set_id="evidence-a",
        pair=1,
        plane=W2FaultPlane.P1_SPEECH_MEDIA,
        fault_class=W2FaultClass.RETRIABLE,
        operation="speech.recognize.batch",
    )
    variants = (
        {"policy_id": "policy-b"},
        {"candidate_sha": "b" * 40},
        {"evidence_set_id": "evidence-b"},
    )
    for changed in variants:
        values = {
            "policy_id": "policy-a",
            "candidate_sha": _CANDIDATE,
            "evidence_set_id": "evidence-a",
            "pair": 1,
            "plane": W2FaultPlane.P1_SPEECH_MEDIA,
            "fault_class": W2FaultClass.RETRIABLE,
            "operation": "speech.recognize.batch",
            **changed,
        }
        assert derive_w2_fault_identity(**values).request_id != baseline.request_id


@pytest.mark.parametrize(
    "changed",
    [
        {"pair": 2},
        {"operation": "speech.synthesize.batch"},
        {"derivation_version": "w2.product-fault-plan.v2"},
        {"candidate_sha": "A" * 40},
        {"policy_id": "policy with spaces"},
        {"evidence_set_id": ""},
    ],
)
def test_fault_identity_rejects_open_or_mismatched_authority(
    changed: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "policy_id": "policy-a",
        "candidate_sha": _CANDIDATE,
        "evidence_set_id": "evidence-a",
        "pair": 1,
        "plane": W2FaultPlane.P1_SPEECH_MEDIA,
        "fault_class": W2FaultClass.RETRIABLE,
        "operation": "speech.recognize.batch",
        **changed,
    }
    with pytest.raises(W2FaultPlanError):
        derive_w2_fault_identity(**values)  # type: ignore[arg-type]


def test_fault_plan_lookup_rejects_unknown_or_missing_identity() -> None:
    plan = derive_w2_product_fault_plan(
        policy_id="policy-a",
        candidate_sha=_CANDIDATE,
        evidence_set_id="evidence-a",
    )

    with pytest.raises(W2FaultPlanError):
        plan.require("observability", W2FaultClass.RETRIABLE)
    with pytest.raises(W2FaultPlanError):
        plan.require(W2FaultPlane.P1_SPEECH_MEDIA, "unknown")
