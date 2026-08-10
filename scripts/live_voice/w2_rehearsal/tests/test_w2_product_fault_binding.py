from __future__ import annotations

import copy

import pytest

from jiuwenswarm.server.live_voice.w2_fault_plan import (
    W2FaultClass,
    W2FaultPlane,
)
from w2_product_fault_binding import (
    derive_product_fault_plan_payload,
    require_product_fault,
    validate_product_fault_plan_payload,
)


_AUTHORITY = {
    "policy_id": "w2-policy-test",
    "candidate_sha": "a" * 40,
    "evidence_set_id": "w2-evidence-test",
}


def test_runtime_payload_is_the_complete_closed_authority_plan() -> None:
    payload = derive_product_fault_plan_payload(**_AUTHORITY)

    assert payload["policy_id"] == _AUTHORITY["policy_id"]
    assert payload["candidate_sha"] == _AUTHORITY["candidate_sha"]
    assert payload["evidence_set_id"] == _AUTHORITY["evidence_set_id"]
    assert len(payload["items"]) == 9
    assert len({item["request_id"] for item in payload["items"]}) == 9
    assert len({item["source_record_id"] for item in payload["items"]}) == 9
    assert require_product_fault(
        payload,
        pair=3,
        plane=W2FaultPlane.P3_TASK,
        fault_class=W2FaultClass.ZERO_EFFECT,
    )["operation"] == "live_voice.composition.p3.mutate"


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["items"].pop(),
        lambda value: value["items"][0].__setitem__("request_id", "foreign"),
        lambda value: value["items"][0].__setitem__("plane", "p3.task"),
        lambda value: value.__setitem__("extra", True),
    ),
)
def test_runtime_payload_tampering_fails_closed(mutate: object) -> None:
    payload = derive_product_fault_plan_payload(**_AUTHORITY)
    changed = copy.deepcopy(payload)
    mutate(changed)

    with pytest.raises(RuntimeError, match="exactly derived"):
        validate_product_fault_plan_payload(changed, **_AUTHORITY)
