# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import builtins
import logging
import os
import socket
from dataclasses import FrozenInstanceError, replace

import pytest

from jiuwenswarm.channels.web.live_voice_deployment_preflight import (
    DeploymentPreflightFacts,
    DeploymentPreflightReason,
    DeploymentPreflightResult,
    TlsTerminationFact,
    evaluate_live_voice_deployment_preflight,
)


def _deployed_facts(**overrides: object) -> DeploymentPreflightFacts:
    values: dict[str, object] = {
        "public_origin": "https://voice.example.test",
        "public_websocket_url": "wss://voice.example.test/ws",
        "allowed_origins": ("https://voice.example.test",),
        "csp_connect_src": ("'self'",),
        "cors_credentials_allowed": True,
        "proxy_websocket_upgrade": True,
        "tls_termination": TlsTerminationFact.DECLARED,
        "tls_owner": "edge-platform",
    }
    values.update(overrides)
    return DeploymentPreflightFacts(**values)  # type: ignore[arg-type]


def _reasons(**overrides: object) -> tuple[DeploymentPreflightReason, ...]:
    result = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts=_deployed_facts(**overrides),
    )
    assert result.configuration_ready is False
    assert result.real_deployment_observed is False
    assert result.formal_deployment_ready is False
    return result.reason_codes


def test_secure_same_origin_configuration_is_ready_without_runtime_claims() -> None:
    result = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts=_deployed_facts(),
    )

    assert result.configuration_ready is True
    assert result.reason_codes == (DeploymentPreflightReason.CONFIGURATION_READY,)
    assert result.evidence_scope == "configuration_only"
    assert result.real_deployment_observed is False
    assert result.formal_deployment_ready is False


def test_localhost_http_ws_requires_an_explicit_controlled_exception() -> None:
    facts = _deployed_facts(
        public_origin="http://localhost:5173",
        public_websocket_url="ws://localhost:5173/ws",
        allowed_origins=("http://localhost:5173",),
        tls_termination=TlsTerminationFact.LOCALHOST_CONTROLLED_EXCEPTION,
        tls_owner="local-test-owner",
    )

    result = evaluate_live_voice_deployment_preflight(enabled=True, facts=facts)

    assert result.configuration_ready is True
    assert result.reason_codes == (
        DeploymentPreflightReason.LOCALHOST_CONTROLLED_EXCEPTION,
        DeploymentPreflightReason.CONFIGURATION_READY,
    )
    mismatch = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts=replace(facts, tls_termination=TlsTerminationFact.DECLARED),
    )
    assert mismatch.configuration_ready is False
    assert mismatch.reason_codes == (
        DeploymentPreflightReason.TLS_TERMINATION_CONTEXT_MISMATCH,
    )
    blocked = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts=replace(facts, proxy_websocket_upgrade=False),
    )
    assert blocked.configuration_ready is False
    assert blocked.reason_codes == (
        DeploymentPreflightReason.PROXY_WEBSOCKET_UPGRADE_DISABLED,
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "public_origin": "http://voice.example.test",
                "public_websocket_url": "ws://voice.example.test/ws",
                "allowed_origins": ("http://voice.example.test",),
            },
            {
                DeploymentPreflightReason.PUBLIC_ORIGIN_INSECURE,
                DeploymentPreflightReason.PUBLIC_WEBSOCKET_INSECURE,
            },
        ),
        (
            {"public_websocket_url": "wss://media.example.test/ws"},
            {DeploymentPreflightReason.PUBLIC_WEBSOCKET_ORIGIN_MISMATCH},
        ),
        (
            {"public_websocket_url": "wss://voice.example.test:444/ws"},
            {DeploymentPreflightReason.PUBLIC_WEBSOCKET_ORIGIN_MISMATCH},
        ),
        (
            {"public_websocket_url": "wss://user@voice.example.test/ws"},
            {DeploymentPreflightReason.PUBLIC_WEBSOCKET_URL_INVALID},
        ),
        (
            {"public_websocket_url": "wss://voice.example.test/ws?"},
            {DeploymentPreflightReason.PUBLIC_WEBSOCKET_URL_INVALID},
        ),
    ],
)
def test_insecure_or_cross_origin_public_websocket_fails_closed(
    overrides: dict[str, object],
    expected: set[DeploymentPreflightReason],
) -> None:
    reasons = set(_reasons(**overrides))
    assert expected <= reasons


def test_allowed_origin_must_be_one_exact_public_origin() -> None:
    assert _reasons(allowed_origins=None) == (
        DeploymentPreflightReason.ALLOWED_ORIGINS_UNKNOWN,
    )
    assert _reasons(
        allowed_origins=(
            "https://voice.example.test",
            "https://other.example.test",
        )
    ) == (DeploymentPreflightReason.ALLOWED_ORIGINS_NOT_EXACT,)
    assert _reasons(allowed_origins=("https://voice.example.test/path",)) == (
        DeploymentPreflightReason.ALLOWED_ORIGINS_INVALID,
        DeploymentPreflightReason.ALLOWED_ORIGINS_NOT_EXACT,
    )
    assert _reasons(
        allowed_origins=(
            "https://voice.example.test",
            "https://voice.example.test",
        )
    ) == (DeploymentPreflightReason.ALLOWED_ORIGINS_NOT_EXACT,)
    assert _reasons(allowed_origins=["https://voice.example.test"]) == (
        DeploymentPreflightReason.ALLOWED_ORIGINS_INVALID,
        DeploymentPreflightReason.ALLOWED_ORIGINS_NOT_EXACT,
    )


def test_cors_wildcard_with_credentials_has_a_specific_stable_blocker() -> None:
    reasons = _reasons(allowed_origins=("*",), cors_credentials_allowed=True)

    assert reasons == (
        DeploymentPreflightReason.ALLOWED_ORIGINS_NOT_EXACT,
        DeploymentPreflightReason.CORS_WILDCARD_WITH_CREDENTIALS,
    )
    assert _reasons(allowed_origins=("*",), cors_credentials_allowed=False) == (
        DeploymentPreflightReason.ALLOWED_ORIGINS_NOT_EXACT,
    )
    assert _reasons(cors_credentials_allowed=None) == (
        DeploymentPreflightReason.CORS_CREDENTIAL_POLICY_UNKNOWN,
    )
    assert _reasons(cors_credentials_allowed="yes") == (
        DeploymentPreflightReason.CORS_CREDENTIAL_POLICY_INVALID,
    )


def test_csp_connect_src_requires_self_or_the_exact_websocket_origin() -> None:
    explicit = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts=_deployed_facts(
            csp_connect_src=("https://api.example.test", "wss://voice.example.test")
        ),
    )
    assert explicit.configuration_ready is True
    assert explicit.reason_codes == (DeploymentPreflightReason.CONFIGURATION_READY,)
    assert _reasons(csp_connect_src=None) == (
        DeploymentPreflightReason.CSP_CONNECT_SRC_UNKNOWN,
    )
    assert _reasons(csp_connect_src=("https://api.example.test",)) == (
        DeploymentPreflightReason.CSP_CONNECT_SRC_BLOCKS_WEBSOCKET,
    )
    assert _reasons(csp_connect_src=("wss:",)) == (
        DeploymentPreflightReason.CSP_CONNECT_SRC_OVERBROAD,
        DeploymentPreflightReason.CSP_CONNECT_SRC_BLOCKS_WEBSOCKET,
    )
    assert _reasons(csp_connect_src=("'self'", "*")) == (
        DeploymentPreflightReason.CSP_CONNECT_SRC_OVERBROAD,
    )


def test_proxy_upgrade_and_tls_ownership_are_explicit_fail_closed_facts() -> None:
    assert _reasons(proxy_websocket_upgrade=None) == (
        DeploymentPreflightReason.PROXY_WEBSOCKET_UPGRADE_UNKNOWN,
    )
    assert _reasons(proxy_websocket_upgrade=False) == (
        DeploymentPreflightReason.PROXY_WEBSOCKET_UPGRADE_DISABLED,
    )
    assert _reasons(proxy_websocket_upgrade="yes") == (
        DeploymentPreflightReason.PROXY_WEBSOCKET_UPGRADE_INVALID,
    )
    assert _reasons(tls_termination=TlsTerminationFact.UNKNOWN) == (
        DeploymentPreflightReason.TLS_TERMINATION_UNKNOWN,
    )
    assert _reasons(
        tls_termination=TlsTerminationFact.LOCALHOST_CONTROLLED_EXCEPTION
    ) == (DeploymentPreflightReason.TLS_TERMINATION_CONTEXT_MISMATCH,)
    assert _reasons(tls_owner=None) == (DeploymentPreflightReason.TLS_OWNER_UNKNOWN,)
    assert _reasons(tls_owner="https://private-edge.example/key=secret") == (
        DeploymentPreflightReason.TLS_OWNER_INVALID,
    )


def test_every_unknown_fact_remains_content_free_and_not_ready() -> None:
    facts = DeploymentPreflightFacts(
        public_origin=None,
        public_websocket_url=None,
        allowed_origins=None,
        csp_connect_src=None,
        cors_credentials_allowed=None,
        proxy_websocket_upgrade=None,
        tls_termination=TlsTerminationFact.UNKNOWN,
        tls_owner=None,
    )

    result = evaluate_live_voice_deployment_preflight(enabled=True, facts=facts)

    assert result.configuration_ready is False
    assert result.reason_codes == (
        DeploymentPreflightReason.PUBLIC_ORIGIN_UNKNOWN,
        DeploymentPreflightReason.PUBLIC_WEBSOCKET_URL_UNKNOWN,
        DeploymentPreflightReason.ALLOWED_ORIGINS_UNKNOWN,
        DeploymentPreflightReason.CORS_CREDENTIAL_POLICY_UNKNOWN,
        DeploymentPreflightReason.CSP_CONNECT_SRC_UNKNOWN,
        DeploymentPreflightReason.PROXY_WEBSOCKET_UPGRADE_UNKNOWN,
        DeploymentPreflightReason.TLS_TERMINATION_UNKNOWN,
        DeploymentPreflightReason.TLS_OWNER_UNKNOWN,
    )
    assert "CONFIGURATION_READY" not in {reason.value for reason in result.reason_codes}


def test_feature_off_returns_before_inspecting_facts() -> None:
    class Poison:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"feature-off inspected {name}")

    result = evaluate_live_voice_deployment_preflight(enabled=False, facts=Poison())

    assert result.configuration_ready is False
    assert result.reason_codes == (DeploymentPreflightReason.FEATURE_DISABLED,)


@pytest.mark.parametrize("enabled", [1, None, "true"])
def test_non_boolean_enabled_is_invalid_not_feature_disabled(enabled: object) -> None:
    result = evaluate_live_voice_deployment_preflight(
        enabled=enabled,  # type: ignore[arg-type]
        facts=_deployed_facts(),
    )

    assert result.configuration_ready is False
    assert result.reason_codes == (DeploymentPreflightReason.FACTS_INVALID,)


def test_evaluation_has_no_environment_network_file_or_log_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("deployment preflight performed a forbidden side effect")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(logging.Logger, "_log", forbidden)

    result = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts=_deployed_facts(),
    )

    assert result.configuration_ready is True


def test_results_are_immutable_and_never_echo_input_values() -> None:
    private_value = "https://private-edge.example/key=credential-material"
    result = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts=_deployed_facts(tls_owner=private_value),
    )

    assert result.reason_codes == (DeploymentPreflightReason.TLS_OWNER_INVALID,)
    assert private_value not in repr(result)
    assert "credential-material" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.configuration_ready = True  # type: ignore[misc]


def test_result_contract_rejects_blockers_combined_with_ready() -> None:
    with pytest.raises(ValueError, match="readiness"):
        DeploymentPreflightResult(
            configuration_ready=True,
            reason_codes=(
                DeploymentPreflightReason.PUBLIC_ORIGIN_INSECURE,
                DeploymentPreflightReason.CONFIGURATION_READY,
            ),
        )
    with pytest.raises(ValueError, match="readiness"):
        DeploymentPreflightResult(
            configuration_ready=False,
            reason_codes=(DeploymentPreflightReason.LOCALHOST_CONTROLLED_EXCEPTION,),
        )


def test_result_contract_requires_exact_tuple_and_enum_items() -> None:
    with pytest.raises(ValueError, match="reason_codes"):
        DeploymentPreflightResult(
            configuration_ready=False,
            reason_codes=[  # type: ignore[arg-type]
                DeploymentPreflightReason.FEATURE_DISABLED,
            ],
        )
    with pytest.raises(ValueError, match="reason_codes"):
        DeploymentPreflightResult(
            configuration_ready=False,
            reason_codes=("FEATURE_DISABLED",),  # type: ignore[arg-type]
        )


def test_external_fact_subclasses_and_comparison_objects_fail_without_dispatch() -> (
    None
):
    class PoisonString(str):
        def __eq__(self, other: object) -> bool:
            raise AssertionError(f"compared poison string with {other!r}")

        def strip(self, chars: str | None = None) -> str:
            raise AssertionError(f"stripped poison string with {chars!r}")

        def isascii(self) -> bool:
            raise AssertionError("inspected poison string")

    class PoisonComparison:
        def __eq__(self, other: object) -> bool:
            raise AssertionError(f"compared poison object with {other!r}")

    poison_string = PoisonString("https://voice.example.test")
    result = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts=_deployed_facts(
            public_origin=poison_string,
            allowed_origins=(poison_string,),
            csp_connect_src=(poison_string,),
            tls_termination=PoisonComparison(),
            tls_owner=poison_string,
        ),
    )

    assert result.configuration_ready is False
    assert set(result.reason_codes) >= {
        DeploymentPreflightReason.PUBLIC_ORIGIN_INVALID,
        DeploymentPreflightReason.ALLOWED_ORIGINS_INVALID,
        DeploymentPreflightReason.ALLOWED_ORIGINS_NOT_EXACT,
        DeploymentPreflightReason.CSP_CONNECT_SRC_INVALID,
        DeploymentPreflightReason.CSP_CONNECT_SRC_BLOCKS_WEBSOCKET,
        DeploymentPreflightReason.TLS_TERMINATION_UNKNOWN,
        DeploymentPreflightReason.TLS_OWNER_INVALID,
    }


def test_invalid_enabled_facts_object_fails_closed_without_reflection() -> None:
    result = evaluate_live_voice_deployment_preflight(
        enabled=True,
        facts={"public_origin": "https://voice.example.test"},
    )

    assert result.configuration_ready is False
    assert result.reason_codes == (DeploymentPreflightReason.FACTS_INVALID,)
