# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure dependency-readiness evaluator for the product P2 browser journey.

The caller supplies only closed, non-sensitive facts.  This module does not
discover those facts: it never reads environment variables, configuration,
credentials, paths, identities, ports, or services.  A positive result means
only that the declared dependency facts are satisfied; it is not runtime,
browser, Agent/Tool, acceptance, or Gate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


PRODUCT_P2_READINESS_CONTRACT_VERSION = "live-voice.product-p2-readiness.v1"


class ProductP2ReadinessFact(StrEnum):
    """Closed truth supplied by an external, separately authorized observer."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNKNOWN = "unknown"


class ProductP2ReadinessReason(StrEnum):
    """Stable single-cause result vocabulary in evaluator priority order."""

    INVALID_INPUT = "INVALID_INPUT"

    INTEGRATED_WEB_FLAG_OFF = "INTEGRATED_WEB_FLAG_OFF"
    INTEGRATED_WEB_FLAG_UNKNOWN = "INTEGRATED_WEB_FLAG_UNKNOWN"
    PRODUCT_COMPOSITION_FLAG_OFF = "PRODUCT_COMPOSITION_FLAG_OFF"
    PRODUCT_COMPOSITION_FLAG_UNKNOWN = "PRODUCT_COMPOSITION_FLAG_UNKNOWN"
    PRODUCT_P2_FLAG_OFF = "PRODUCT_P2_FLAG_OFF"
    PRODUCT_P2_FLAG_UNKNOWN = "PRODUCT_P2_FLAG_UNKNOWN"
    TRUSTED_AUTHORITY_FLAG_OFF = "TRUSTED_AUTHORITY_FLAG_OFF"
    TRUSTED_AUTHORITY_FLAG_UNKNOWN = "TRUSTED_AUTHORITY_FLAG_UNKNOWN"
    CREDENTIAL_OWNER_FLAG_OFF = "CREDENTIAL_OWNER_FLAG_OFF"
    CREDENTIAL_OWNER_FLAG_UNKNOWN = "CREDENTIAL_OWNER_FLAG_UNKNOWN"

    AUTHORIZATION_INCOMPLETE = "AUTHORIZATION_INCOMPLETE"
    AUTHORIZATION_UNKNOWN = "AUTHORIZATION_UNKNOWN"
    PROJECT_NOT_REGISTERED = "PROJECT_NOT_REGISTERED"
    PROJECT_REGISTRATION_UNKNOWN = "PROJECT_REGISTRATION_UNKNOWN"
    PROJECT_BOUND_PERSISTED_SESSION_MISSING = "PROJECT_BOUND_PERSISTED_SESSION_MISSING"
    PROJECT_BOUND_PERSISTED_SESSION_UNKNOWN = "PROJECT_BOUND_PERSISTED_SESSION_UNKNOWN"
    MODEL_RUNTIME_NOT_DECLARED = "MODEL_RUNTIME_NOT_DECLARED"
    MODEL_RUNTIME_UNKNOWN = "MODEL_RUNTIME_UNKNOWN"
    AGENT_TOOL_CARRIER_UNAVAILABLE = "AGENT_TOOL_CARRIER_UNAVAILABLE"
    AGENT_TOOL_CARRIER_UNKNOWN = "AGENT_TOOL_CARRIER_UNKNOWN"

    AGENT_SERVER_PORT_NOT_LISTENING = "AGENT_SERVER_PORT_NOT_LISTENING"
    AGENT_SERVER_PORT_UNKNOWN = "AGENT_SERVER_PORT_UNKNOWN"
    WEB_CHANNEL_PORT_NOT_LISTENING = "WEB_CHANNEL_PORT_NOT_LISTENING"
    WEB_CHANNEL_PORT_UNKNOWN = "WEB_CHANNEL_PORT_UNKNOWN"
    FRONTEND_PORT_NOT_LISTENING = "FRONTEND_PORT_NOT_LISTENING"
    FRONTEND_PORT_UNKNOWN = "FRONTEND_PORT_UNKNOWN"
    CONNECTION_ACK_NOT_OBSERVED = "CONNECTION_ACK_NOT_OBSERVED"
    CONNECTION_ACK_UNKNOWN = "CONNECTION_ACK_UNKNOWN"

    DEPENDENCY_FACTS_SATISFIED = "DEPENDENCY_FACTS_SATISFIED"


class ProductP2ReadinessEvidenceScope(StrEnum):
    DECLARED_DEPENDENCIES_ONLY = "DECLARED_DEPENDENCIES_ONLY"


class ProductP2ReadinessGateClaim(StrEnum):
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class ProductP2ReadinessInput:
    """Closed facts only; no secret, identity, path, model, or port values."""

    integrated_web_flag: ProductP2ReadinessFact
    product_composition_flag: ProductP2ReadinessFact
    product_p2_flag: ProductP2ReadinessFact
    trusted_authority_flag: ProductP2ReadinessFact
    credential_owner_flag: ProductP2ReadinessFact
    authorization: ProductP2ReadinessFact
    registered_project: ProductP2ReadinessFact
    project_bound_persisted_session: ProductP2ReadinessFact
    model_runtime: ProductP2ReadinessFact
    agent_tool_carrier: ProductP2ReadinessFact
    agent_server_port: ProductP2ReadinessFact
    web_channel_port: ProductP2ReadinessFact
    frontend_port: ProductP2ReadinessFact
    connection_ack: ProductP2ReadinessFact


@dataclass(frozen=True, slots=True)
class ProductP2ReadinessResult:
    """Sanitized preflight result that cannot claim runtime or Gate evidence."""

    dependency_ready: bool
    reason_code: ProductP2ReadinessReason
    contract_version: str = field(
        init=False, default=PRODUCT_P2_READINESS_CONTRACT_VERSION
    )
    evidence_scope: ProductP2ReadinessEvidenceScope = field(
        init=False,
        default=ProductP2ReadinessEvidenceScope.DECLARED_DEPENDENCIES_ONLY,
    )
    real_e2e_observed: bool = field(init=False, default=False)
    gate_claim: ProductP2ReadinessGateClaim = field(
        init=False, default=ProductP2ReadinessGateClaim.NONE
    )

    def __post_init__(self) -> None:
        if type(self.reason_code) is not ProductP2ReadinessReason:
            raise ValueError("readiness reason code must be a ProductP2ReadinessReason")
        expected_ready = (
            self.reason_code is ProductP2ReadinessReason.DEPENDENCY_FACTS_SATISFIED
        )
        if (
            type(self.dependency_ready) is not bool
            or self.dependency_ready != expected_ready
        ):
            raise ValueError("dependency readiness and reason code are inconsistent")

    def to_public_dict(self) -> dict[str, str | bool]:
        """Return the complete bounded output without reflecting any input."""

        return {
            "contract_version": self.contract_version,
            "dependency_ready": self.dependency_ready,
            "reason_code": self.reason_code.value,
            "evidence_scope": self.evidence_scope.value,
            "real_e2e_observed": self.real_e2e_observed,
            "gate_claim": self.gate_claim.value,
        }


@dataclass(frozen=True, slots=True)
class _ReadinessCheck:
    field_name: str
    unsatisfied_reason: ProductP2ReadinessReason
    unknown_reason: ProductP2ReadinessReason


_READINESS_CHECKS = (
    _ReadinessCheck(
        "integrated_web_flag",
        ProductP2ReadinessReason.INTEGRATED_WEB_FLAG_OFF,
        ProductP2ReadinessReason.INTEGRATED_WEB_FLAG_UNKNOWN,
    ),
    _ReadinessCheck(
        "product_composition_flag",
        ProductP2ReadinessReason.PRODUCT_COMPOSITION_FLAG_OFF,
        ProductP2ReadinessReason.PRODUCT_COMPOSITION_FLAG_UNKNOWN,
    ),
    _ReadinessCheck(
        "product_p2_flag",
        ProductP2ReadinessReason.PRODUCT_P2_FLAG_OFF,
        ProductP2ReadinessReason.PRODUCT_P2_FLAG_UNKNOWN,
    ),
    _ReadinessCheck(
        "trusted_authority_flag",
        ProductP2ReadinessReason.TRUSTED_AUTHORITY_FLAG_OFF,
        ProductP2ReadinessReason.TRUSTED_AUTHORITY_FLAG_UNKNOWN,
    ),
    _ReadinessCheck(
        "credential_owner_flag",
        ProductP2ReadinessReason.CREDENTIAL_OWNER_FLAG_OFF,
        ProductP2ReadinessReason.CREDENTIAL_OWNER_FLAG_UNKNOWN,
    ),
    _ReadinessCheck(
        "authorization",
        ProductP2ReadinessReason.AUTHORIZATION_INCOMPLETE,
        ProductP2ReadinessReason.AUTHORIZATION_UNKNOWN,
    ),
    _ReadinessCheck(
        "registered_project",
        ProductP2ReadinessReason.PROJECT_NOT_REGISTERED,
        ProductP2ReadinessReason.PROJECT_REGISTRATION_UNKNOWN,
    ),
    _ReadinessCheck(
        "project_bound_persisted_session",
        ProductP2ReadinessReason.PROJECT_BOUND_PERSISTED_SESSION_MISSING,
        ProductP2ReadinessReason.PROJECT_BOUND_PERSISTED_SESSION_UNKNOWN,
    ),
    _ReadinessCheck(
        "model_runtime",
        ProductP2ReadinessReason.MODEL_RUNTIME_NOT_DECLARED,
        ProductP2ReadinessReason.MODEL_RUNTIME_UNKNOWN,
    ),
    _ReadinessCheck(
        "agent_tool_carrier",
        ProductP2ReadinessReason.AGENT_TOOL_CARRIER_UNAVAILABLE,
        ProductP2ReadinessReason.AGENT_TOOL_CARRIER_UNKNOWN,
    ),
    _ReadinessCheck(
        "agent_server_port",
        ProductP2ReadinessReason.AGENT_SERVER_PORT_NOT_LISTENING,
        ProductP2ReadinessReason.AGENT_SERVER_PORT_UNKNOWN,
    ),
    _ReadinessCheck(
        "web_channel_port",
        ProductP2ReadinessReason.WEB_CHANNEL_PORT_NOT_LISTENING,
        ProductP2ReadinessReason.WEB_CHANNEL_PORT_UNKNOWN,
    ),
    _ReadinessCheck(
        "frontend_port",
        ProductP2ReadinessReason.FRONTEND_PORT_NOT_LISTENING,
        ProductP2ReadinessReason.FRONTEND_PORT_UNKNOWN,
    ),
    _ReadinessCheck(
        "connection_ack",
        ProductP2ReadinessReason.CONNECTION_ACK_NOT_OBSERVED,
        ProductP2ReadinessReason.CONNECTION_ACK_UNKNOWN,
    ),
)


def _result(reason: ProductP2ReadinessReason) -> ProductP2ReadinessResult:
    return ProductP2ReadinessResult(
        dependency_ready=(
            reason is ProductP2ReadinessReason.DEPENDENCY_FACTS_SATISFIED
        ),
        reason_code=reason,
    )


def evaluate_product_p2_readiness(
    readiness: object,
) -> ProductP2ReadinessResult:
    """Evaluate explicit facts in stable order and fail closed on unknown input.

    Evaluation short-circuits at the first failed fact.  In particular, an
    earlier flag-off result does not inspect later dependency facts.
    """

    if type(readiness) is not ProductP2ReadinessInput:
        return _result(ProductP2ReadinessReason.INVALID_INPUT)

    for check in _READINESS_CHECKS:
        fact = object.__getattribute__(readiness, check.field_name)
        if type(fact) is not ProductP2ReadinessFact:
            return _result(ProductP2ReadinessReason.INVALID_INPUT)
        if fact is ProductP2ReadinessFact.UNSATISFIED:
            return _result(check.unsatisfied_reason)
        if fact is ProductP2ReadinessFact.UNKNOWN:
            return _result(check.unknown_reason)

    return _result(ProductP2ReadinessReason.DEPENDENCY_FACTS_SATISFIED)


__all__ = [
    "PRODUCT_P2_READINESS_CONTRACT_VERSION",
    "ProductP2ReadinessEvidenceScope",
    "ProductP2ReadinessFact",
    "ProductP2ReadinessGateClaim",
    "ProductP2ReadinessInput",
    "ProductP2ReadinessReason",
    "ProductP2ReadinessResult",
    "evaluate_product_p2_readiness",
]
