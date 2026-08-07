# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import builtins
import json
import os
import socket
import subprocess
from dataclasses import fields

import pytest

from jiuwenswarm.server.live_voice.product_p2_readiness import (
    PRODUCT_P2_READINESS_CONTRACT_VERSION,
    ProductP2ReadinessEvidenceScope,
    ProductP2ReadinessFact,
    ProductP2ReadinessGateClaim,
    ProductP2ReadinessInput,
    ProductP2ReadinessReason,
    ProductP2ReadinessResult,
    evaluate_product_p2_readiness,
)


FACT_FIELDS = tuple(field.name for field in fields(ProductP2ReadinessInput))

MISSING_CASES = (
    ("integrated_web_flag", ProductP2ReadinessReason.INTEGRATED_WEB_FLAG_OFF),
    (
        "product_composition_flag",
        ProductP2ReadinessReason.PRODUCT_COMPOSITION_FLAG_OFF,
    ),
    ("product_p2_flag", ProductP2ReadinessReason.PRODUCT_P2_FLAG_OFF),
    (
        "trusted_authority_flag",
        ProductP2ReadinessReason.TRUSTED_AUTHORITY_FLAG_OFF,
    ),
    (
        "credential_owner_flag",
        ProductP2ReadinessReason.CREDENTIAL_OWNER_FLAG_OFF,
    ),
    ("authorization", ProductP2ReadinessReason.AUTHORIZATION_INCOMPLETE),
    ("registered_project", ProductP2ReadinessReason.PROJECT_NOT_REGISTERED),
    (
        "project_bound_persisted_session",
        ProductP2ReadinessReason.PROJECT_BOUND_PERSISTED_SESSION_MISSING,
    ),
    ("model_runtime", ProductP2ReadinessReason.MODEL_RUNTIME_NOT_DECLARED),
    (
        "agent_tool_carrier",
        ProductP2ReadinessReason.AGENT_TOOL_CARRIER_UNAVAILABLE,
    ),
    (
        "agent_server_port",
        ProductP2ReadinessReason.AGENT_SERVER_PORT_NOT_LISTENING,
    ),
    (
        "web_channel_port",
        ProductP2ReadinessReason.WEB_CHANNEL_PORT_NOT_LISTENING,
    ),
    ("frontend_port", ProductP2ReadinessReason.FRONTEND_PORT_NOT_LISTENING),
    ("connection_ack", ProductP2ReadinessReason.CONNECTION_ACK_NOT_OBSERVED),
)

UNKNOWN_CASES = (
    ("integrated_web_flag", ProductP2ReadinessReason.INTEGRATED_WEB_FLAG_UNKNOWN),
    (
        "product_composition_flag",
        ProductP2ReadinessReason.PRODUCT_COMPOSITION_FLAG_UNKNOWN,
    ),
    ("product_p2_flag", ProductP2ReadinessReason.PRODUCT_P2_FLAG_UNKNOWN),
    (
        "trusted_authority_flag",
        ProductP2ReadinessReason.TRUSTED_AUTHORITY_FLAG_UNKNOWN,
    ),
    (
        "credential_owner_flag",
        ProductP2ReadinessReason.CREDENTIAL_OWNER_FLAG_UNKNOWN,
    ),
    ("authorization", ProductP2ReadinessReason.AUTHORIZATION_UNKNOWN),
    (
        "registered_project",
        ProductP2ReadinessReason.PROJECT_REGISTRATION_UNKNOWN,
    ),
    (
        "project_bound_persisted_session",
        ProductP2ReadinessReason.PROJECT_BOUND_PERSISTED_SESSION_UNKNOWN,
    ),
    ("model_runtime", ProductP2ReadinessReason.MODEL_RUNTIME_UNKNOWN),
    (
        "agent_tool_carrier",
        ProductP2ReadinessReason.AGENT_TOOL_CARRIER_UNKNOWN,
    ),
    (
        "agent_server_port",
        ProductP2ReadinessReason.AGENT_SERVER_PORT_UNKNOWN,
    ),
    ("web_channel_port", ProductP2ReadinessReason.WEB_CHANNEL_PORT_UNKNOWN),
    ("frontend_port", ProductP2ReadinessReason.FRONTEND_PORT_UNKNOWN),
    ("connection_ack", ProductP2ReadinessReason.CONNECTION_ACK_UNKNOWN),
)


def readiness(**overrides: object) -> ProductP2ReadinessInput:
    values: dict[str, object] = {
        name: ProductP2ReadinessFact.SATISFIED for name in FACT_FIELDS
    }
    values.update(overrides)
    return ProductP2ReadinessInput(**values)  # type: ignore[arg-type]


def test_all_declared_dependencies_ready_never_claims_e2e_or_gate() -> None:
    result = evaluate_product_p2_readiness(readiness())

    assert result == ProductP2ReadinessResult(
        dependency_ready=True,
        reason_code=ProductP2ReadinessReason.DEPENDENCY_FACTS_SATISFIED,
    )
    assert result.contract_version == PRODUCT_P2_READINESS_CONTRACT_VERSION
    assert (
        result.evidence_scope
        is ProductP2ReadinessEvidenceScope.DECLARED_DEPENDENCIES_ONLY
    )
    assert result.real_e2e_observed is False
    assert result.gate_claim is ProductP2ReadinessGateClaim.NONE
    assert result.to_public_dict() == {
        "contract_version": "live-voice.product-p2-readiness.v1",
        "dependency_ready": True,
        "reason_code": "DEPENDENCY_FACTS_SATISFIED",
        "evidence_scope": "DECLARED_DEPENDENCIES_ONLY",
        "real_e2e_observed": False,
        "gate_claim": "NONE",
    }


@pytest.mark.parametrize(("field_name", "expected_reason"), MISSING_CASES)
def test_each_missing_fact_has_stable_priority_and_one_reason(
    field_name: str,
    expected_reason: ProductP2ReadinessReason,
) -> None:
    field_index = FACT_FIELDS.index(field_name)
    later_unknown = {
        name: ProductP2ReadinessFact.UNKNOWN for name in FACT_FIELDS[field_index + 1 :]
    }
    result = evaluate_product_p2_readiness(
        readiness(
            **later_unknown,
            **{field_name: ProductP2ReadinessFact.UNSATISFIED},
        )
    )

    assert result.dependency_ready is False
    assert result.reason_code is expected_reason


@pytest.mark.parametrize(("field_name", "expected_reason"), UNKNOWN_CASES)
def test_each_unknown_fact_fails_closed_with_stable_priority(
    field_name: str,
    expected_reason: ProductP2ReadinessReason,
) -> None:
    result = evaluate_product_p2_readiness(
        readiness(**{field_name: ProductP2ReadinessFact.UNKNOWN})
    )

    assert result.dependency_ready is False
    assert result.reason_code is expected_reason


@pytest.mark.parametrize("invalid", [None, True, "ready", {}, object()])
def test_invalid_input_shape_fails_closed_without_coercion(invalid: object) -> None:
    result = evaluate_product_p2_readiness(invalid)

    assert result.dependency_ready is False
    assert result.reason_code is ProductP2ReadinessReason.INVALID_INPUT


def test_invalid_field_type_fails_closed_and_never_leaks_its_value() -> None:
    secret_marker = "private-value-must-not-escape"
    invalid = readiness(authorization=secret_marker)

    result = evaluate_product_p2_readiness(invalid)
    serialized = json.dumps(result.to_public_dict(), sort_keys=True)

    assert result.reason_code is ProductP2ReadinessReason.INVALID_INPUT
    assert secret_marker not in serialized


def test_first_flag_off_does_not_inspect_or_reflect_later_facts() -> None:
    class ExplodingSecret:
        def __repr__(self) -> str:
            raise AssertionError("later secret was represented")

        def __str__(self) -> str:
            raise AssertionError("later secret was converted")

        def __eq__(self, _other: object) -> bool:
            raise AssertionError("later secret was compared")

    probe = readiness(integrated_web_flag=ProductP2ReadinessFact.UNSATISFIED)
    for name in FACT_FIELDS[1:]:
        object.__setattr__(probe, name, ExplodingSecret())

    result = evaluate_product_p2_readiness(probe)

    assert result.reason_code is ProductP2ReadinessReason.INTEGRATED_WEB_FLAG_OFF
    assert result.to_public_dict()["dependency_ready"] is False


def test_evaluator_performs_no_file_env_process_or_network_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("readiness evaluator attempted dependency discovery")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)

    first = evaluate_product_p2_readiness(readiness())
    second = evaluate_product_p2_readiness(readiness())

    assert first == second
    assert first.dependency_ready is True


def test_public_result_e2e_and_gate_fields_cannot_be_constructor_claims() -> None:
    with pytest.raises(TypeError):
        ProductP2ReadinessResult(
            dependency_ready=True,
            reason_code=ProductP2ReadinessReason.DEPENDENCY_FACTS_SATISFIED,
            real_e2e_observed=True,  # type: ignore[call-arg]
        )
    with pytest.raises(TypeError):
        ProductP2ReadinessResult(
            dependency_ready=True,
            reason_code=ProductP2ReadinessReason.DEPENDENCY_FACTS_SATISFIED,
            gate_claim="ALPHA",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("dependency_ready", "reason"),
    [
        (False, ProductP2ReadinessReason.DEPENDENCY_FACTS_SATISFIED),
        (True, ProductP2ReadinessReason.INVALID_INPUT),
        (1, ProductP2ReadinessReason.DEPENDENCY_FACTS_SATISFIED),
    ],
)
def test_result_rejects_inconsistent_or_non_boolean_readiness(
    dependency_ready: object,
    reason: ProductP2ReadinessReason,
) -> None:
    with pytest.raises(ValueError, match="inconsistent"):
        ProductP2ReadinessResult(
            dependency_ready=dependency_ready,  # type: ignore[arg-type]
            reason_code=reason,
        )


def test_result_rejects_non_enum_reason_code() -> None:
    with pytest.raises(ValueError, match="reason code"):
        ProductP2ReadinessResult(
            dependency_ready=False,
            reason_code="invalid",  # type: ignore[arg-type]
        )
