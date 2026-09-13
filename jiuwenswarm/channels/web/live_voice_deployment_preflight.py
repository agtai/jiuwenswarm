# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure configuration preflight for a Live Voice Web deployment.

The evaluator in this module consumes only explicit, non-sensitive deployment
facts.  It does not read environment variables, inspect a running server, open a
socket, write a file or log, or grant product-composition authority.  A ready
result therefore means only that the supplied configuration facts are mutually
consistent; it is never evidence that a real deployment was observed.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeGuard
from urllib.parse import SplitResult, urlsplit


class TlsTerminationFact(StrEnum):
    """Explicit public-edge TLS configuration fact."""

    DECLARED = "declared"
    LOCALHOST_CONTROLLED_EXCEPTION = "localhost_controlled_exception"
    UNKNOWN = "unknown"


class DeploymentPreflightReason(StrEnum):
    """Closed, content-free deployment configuration outcomes."""

    CONFIGURATION_READY = "CONFIGURATION_READY"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    FACTS_INVALID = "FACTS_INVALID"
    PUBLIC_ORIGIN_UNKNOWN = "PUBLIC_ORIGIN_UNKNOWN"
    PUBLIC_ORIGIN_INVALID = "PUBLIC_ORIGIN_INVALID"
    PUBLIC_ORIGIN_INSECURE = "PUBLIC_ORIGIN_INSECURE"
    PUBLIC_WEBSOCKET_URL_UNKNOWN = "PUBLIC_WEBSOCKET_URL_UNKNOWN"
    PUBLIC_WEBSOCKET_URL_INVALID = "PUBLIC_WEBSOCKET_URL_INVALID"
    PUBLIC_WEBSOCKET_INSECURE = "PUBLIC_WEBSOCKET_INSECURE"
    PUBLIC_WEBSOCKET_ORIGIN_MISMATCH = "PUBLIC_WEBSOCKET_ORIGIN_MISMATCH"
    ALLOWED_ORIGINS_UNKNOWN = "ALLOWED_ORIGINS_UNKNOWN"
    ALLOWED_ORIGINS_INVALID = "ALLOWED_ORIGINS_INVALID"
    ALLOWED_ORIGINS_NOT_EXACT = "ALLOWED_ORIGINS_NOT_EXACT"
    CORS_CREDENTIAL_POLICY_UNKNOWN = "CORS_CREDENTIAL_POLICY_UNKNOWN"
    CORS_CREDENTIAL_POLICY_INVALID = "CORS_CREDENTIAL_POLICY_INVALID"
    CORS_WILDCARD_WITH_CREDENTIALS = "CORS_WILDCARD_WITH_CREDENTIALS"
    CSP_CONNECT_SRC_UNKNOWN = "CSP_CONNECT_SRC_UNKNOWN"
    CSP_CONNECT_SRC_INVALID = "CSP_CONNECT_SRC_INVALID"
    CSP_CONNECT_SRC_OVERBROAD = "CSP_CONNECT_SRC_OVERBROAD"
    CSP_CONNECT_SRC_BLOCKS_WEBSOCKET = "CSP_CONNECT_SRC_BLOCKS_WEBSOCKET"
    PROXY_WEBSOCKET_UPGRADE_UNKNOWN = "PROXY_WEBSOCKET_UPGRADE_UNKNOWN"
    PROXY_WEBSOCKET_UPGRADE_INVALID = "PROXY_WEBSOCKET_UPGRADE_INVALID"
    PROXY_WEBSOCKET_UPGRADE_DISABLED = "PROXY_WEBSOCKET_UPGRADE_DISABLED"
    TLS_TERMINATION_UNKNOWN = "TLS_TERMINATION_UNKNOWN"
    TLS_TERMINATION_CONTEXT_MISMATCH = "TLS_TERMINATION_CONTEXT_MISMATCH"
    TLS_OWNER_UNKNOWN = "TLS_OWNER_UNKNOWN"
    TLS_OWNER_INVALID = "TLS_OWNER_INVALID"
    LOCALHOST_CONTROLLED_EXCEPTION = "LOCALHOST_CONTROLLED_EXCEPTION"


@dataclass(frozen=True, slots=True)
class DeploymentPreflightFacts:
    """Caller-authored, non-sensitive configuration facts.

    ``tls_owner`` is a short operational label, not a person name, endpoint,
    credential, certificate value, or arbitrary free text.  The validation here
    bounds that carrier but cannot classify every possible opaque secret; callers
    remain responsible for supplying only non-sensitive facts.
    """

    public_origin: str | None
    public_websocket_url: str | None
    allowed_origins: tuple[str, ...] | None
    csp_connect_src: tuple[str, ...] | None
    cors_credentials_allowed: bool | None
    proxy_websocket_upgrade: bool | None
    tls_termination: TlsTerminationFact
    tls_owner: str | None


@dataclass(frozen=True, slots=True)
class DeploymentPreflightResult:
    """Content-free configuration result without runtime or formal authority."""

    configuration_ready: bool
    reason_codes: tuple[DeploymentPreflightReason, ...]
    evidence_scope: str = field(default="configuration_only", init=False)
    real_deployment_observed: bool = field(default=False, init=False)
    formal_deployment_ready: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if type(self.configuration_ready) is not bool:
            raise ValueError("configuration_ready must be a boolean")
        if (
            type(self.reason_codes) is not tuple
            or not self.reason_codes
            or any(
                type(reason) is not DeploymentPreflightReason
                for reason in self.reason_codes
            )
            or len(set(self.reason_codes)) != len(self.reason_codes)
        ):
            raise ValueError("reason_codes must be unique closed reasons")
        ready_reason = DeploymentPreflightReason.CONFIGURATION_READY
        localhost_reason = DeploymentPreflightReason.LOCALHOST_CONTROLLED_EXCEPTION
        ready_reasons = {
            (ready_reason,),
            (localhost_reason, ready_reason),
        }
        if self.configuration_ready:
            valid = self.reason_codes in ready_reasons
        else:
            valid = not any(
                reason in {ready_reason, localhost_reason}
                for reason in self.reason_codes
            )
        if not valid:
            raise ValueError("configuration readiness and final reason must agree")


@dataclass(frozen=True, slots=True)
class _Origin:
    scheme: str
    hostname: str
    port: int
    localhost: bool


@dataclass(frozen=True, slots=True)
class _WebSocketEndpoint:
    scheme: str
    hostname: str
    port: int


_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_OWNER_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?")
_CSP_BROAD_SOURCES = frozenset({"*", "ws:", "wss:"})


def _safe_ascii(value: object) -> TypeGuard[str]:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value.isascii()
        and not any(character.isspace() or ord(character) < 0x20 for character in value)
    )


def _validated_host(parsed: SplitResult) -> tuple[str, bool] | None:
    try:
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return None
    if (
        hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.netloc.endswith(":")
    ):
        return None
    normalized = hostname.lower()
    if not normalized or normalized.endswith(".") or "%" in normalized:
        return None
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        if len(normalized) > 253 or any(
            _DOMAIN_LABEL.fullmatch(label) is None for label in normalized.split(".")
        ):
            return None
        localhost = normalized == "localhost"
    else:
        localhost = address in {
            ipaddress.ip_address("127.0.0.1"),
            ipaddress.ip_address("::1"),
        }
    return normalized, localhost


def _parse_origin(value: object) -> _Origin | None:
    if not _safe_ascii(value) or "?" in value or "#" in value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    validated_host = _validated_host(parsed)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or validated_host is None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    scheme = parsed.scheme.lower()
    hostname, localhost = validated_host
    port = parsed.port or (443 if scheme == "https" else 80)
    if not 1 <= port <= 65_535:
        return None
    return _Origin(scheme, hostname, port, localhost)


def _parse_websocket(value: object) -> _WebSocketEndpoint | None:
    if not _safe_ascii(value) or "?" in value or "#" in value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    validated_host = _validated_host(parsed)
    if (
        parsed.scheme.lower() not in {"ws", "wss"}
        or validated_host is None
        or parsed.query
        or parsed.fragment
    ):
        return None
    scheme = parsed.scheme.lower()
    hostname, _ = validated_host
    port = parsed.port or (443 if scheme == "wss" else 80)
    if not 1 <= port <= 65_535:
        return None
    return _WebSocketEndpoint(scheme, hostname, port)


def _websocket_matches_origin(origin: _Origin, endpoint: _WebSocketEndpoint) -> bool:
    expected_scheme = "wss" if origin.scheme == "https" else "ws"
    return (
        endpoint.scheme == expected_scheme
        and endpoint.hostname == origin.hostname
        and endpoint.port == origin.port
    )


def _validate_allowed_origins(
    value: object,
) -> tuple[tuple[_Origin, ...] | None, bool, bool]:
    if value is None:
        return None, False, False
    if type(value) is not tuple or not value:
        return (), False, True
    origins: list[_Origin] = []
    wildcard = False
    invalid = False
    for item in value:
        if type(item) is not str:
            invalid = True
            continue
        if item == "*":
            wildcard = True
            continue
        parsed = _parse_origin(item)
        if parsed is None:
            invalid = True
        else:
            origins.append(parsed)
    return tuple(origins), wildcard, invalid


def _csp_allows_websocket(
    value: object,
    *,
    origin_matches: bool,
    endpoint: _WebSocketEndpoint | None,
) -> tuple[bool, bool, bool]:
    if value is None:
        return False, False, False
    if type(value) is not tuple:
        return False, True, False
    invalid = False
    overbroad = False
    allowed = False
    for source in value:
        if not _safe_ascii(source):
            invalid = True
            continue
        normalized = source.lower()
        if normalized in _CSP_BROAD_SOURCES:
            overbroad = True
            continue
        if normalized == "'self'" and origin_matches:
            allowed = True
            continue
        candidate = _parse_websocket(source)
        if (
            endpoint is not None
            and candidate is not None
            and candidate == endpoint
            and urlsplit(source).path in {"", "/"}
        ):
            allowed = True
    return allowed, invalid, overbroad


def _owner_label_valid(value: object) -> bool:
    return type(value) is str and _OWNER_LABEL.fullmatch(value) is not None


def _result(
    reasons: list[DeploymentPreflightReason],
    *,
    ready: bool = False,
) -> DeploymentPreflightResult:
    unique_reasons = tuple(dict.fromkeys(reasons))
    if ready:
        unique_reasons += (DeploymentPreflightReason.CONFIGURATION_READY,)
    return DeploymentPreflightResult(
        configuration_ready=ready,
        reason_codes=unique_reasons,
    )


def evaluate_live_voice_deployment_preflight(
    *,
    enabled: bool = False,
    facts: object = None,
) -> DeploymentPreflightResult:
    """Evaluate explicit configuration facts without performing I/O.

    Feature-off returns before inspecting ``facts``.  Every enabled unknown,
    invalid, insecure, overbroad, or mismatched fact fails closed.  A ready
    result remains configuration-only and cannot be promoted to runtime or
    formal deployment evidence.
    """

    if type(enabled) is not bool:
        return _result([DeploymentPreflightReason.FACTS_INVALID])
    if enabled is False:
        return _result([DeploymentPreflightReason.FEATURE_DISABLED])
    if type(facts) is not DeploymentPreflightFacts:
        return _result([DeploymentPreflightReason.FACTS_INVALID])

    reasons: list[DeploymentPreflightReason] = []
    origin = _parse_origin(facts.public_origin)
    if facts.public_origin is None:
        reasons.append(DeploymentPreflightReason.PUBLIC_ORIGIN_UNKNOWN)
    elif origin is None:
        reasons.append(DeploymentPreflightReason.PUBLIC_ORIGIN_INVALID)
    elif not origin.localhost and origin.scheme != "https":
        reasons.append(DeploymentPreflightReason.PUBLIC_ORIGIN_INSECURE)

    websocket = _parse_websocket(facts.public_websocket_url)
    if facts.public_websocket_url is None:
        reasons.append(DeploymentPreflightReason.PUBLIC_WEBSOCKET_URL_UNKNOWN)
    elif websocket is None:
        reasons.append(DeploymentPreflightReason.PUBLIC_WEBSOCKET_URL_INVALID)
    else:
        if origin is not None and not origin.localhost and websocket.scheme != "wss":
            reasons.append(DeploymentPreflightReason.PUBLIC_WEBSOCKET_INSECURE)
        if origin is not None and not _websocket_matches_origin(origin, websocket):
            reasons.append(DeploymentPreflightReason.PUBLIC_WEBSOCKET_ORIGIN_MISMATCH)

    allowed_origins, wildcard_origin, invalid_allowed_origin = (
        _validate_allowed_origins(facts.allowed_origins)
    )
    if facts.allowed_origins is None:
        reasons.append(DeploymentPreflightReason.ALLOWED_ORIGINS_UNKNOWN)
    else:
        if invalid_allowed_origin:
            reasons.append(DeploymentPreflightReason.ALLOWED_ORIGINS_INVALID)
        if (
            wildcard_origin
            or origin is None
            or allowed_origins is None
            or allowed_origins != (origin,)
        ):
            reasons.append(DeploymentPreflightReason.ALLOWED_ORIGINS_NOT_EXACT)

    if facts.cors_credentials_allowed is None:
        reasons.append(DeploymentPreflightReason.CORS_CREDENTIAL_POLICY_UNKNOWN)
    elif type(facts.cors_credentials_allowed) is not bool:
        reasons.append(DeploymentPreflightReason.CORS_CREDENTIAL_POLICY_INVALID)
    elif wildcard_origin and facts.cors_credentials_allowed:
        reasons.append(DeploymentPreflightReason.CORS_WILDCARD_WITH_CREDENTIALS)

    websocket_origin_matches = (
        origin is not None
        and websocket is not None
        and _websocket_matches_origin(origin, websocket)
    )
    csp_allowed, csp_invalid, csp_overbroad = _csp_allows_websocket(
        facts.csp_connect_src,
        origin_matches=websocket_origin_matches,
        endpoint=websocket,
    )
    if facts.csp_connect_src is None:
        reasons.append(DeploymentPreflightReason.CSP_CONNECT_SRC_UNKNOWN)
    else:
        if csp_invalid:
            reasons.append(DeploymentPreflightReason.CSP_CONNECT_SRC_INVALID)
        if csp_overbroad:
            reasons.append(DeploymentPreflightReason.CSP_CONNECT_SRC_OVERBROAD)
        if not csp_allowed:
            reasons.append(DeploymentPreflightReason.CSP_CONNECT_SRC_BLOCKS_WEBSOCKET)

    if facts.proxy_websocket_upgrade is None:
        reasons.append(DeploymentPreflightReason.PROXY_WEBSOCKET_UPGRADE_UNKNOWN)
    elif type(facts.proxy_websocket_upgrade) is not bool:
        reasons.append(DeploymentPreflightReason.PROXY_WEBSOCKET_UPGRADE_INVALID)
    elif not facts.proxy_websocket_upgrade:
        reasons.append(DeploymentPreflightReason.PROXY_WEBSOCKET_UPGRADE_DISABLED)

    tls_termination = facts.tls_termination
    if (
        type(tls_termination) is not TlsTerminationFact
        or tls_termination is TlsTerminationFact.UNKNOWN
    ):
        reasons.append(DeploymentPreflightReason.TLS_TERMINATION_UNKNOWN)
    elif origin is not None:
        expected_tls_fact = (
            TlsTerminationFact.LOCALHOST_CONTROLLED_EXCEPTION
            if origin.localhost and origin.scheme == "http"
            else TlsTerminationFact.DECLARED
        )
        if tls_termination is not expected_tls_fact:
            reasons.append(DeploymentPreflightReason.TLS_TERMINATION_CONTEXT_MISMATCH)

    if facts.tls_owner is None:
        reasons.append(DeploymentPreflightReason.TLS_OWNER_UNKNOWN)
    elif not _owner_label_valid(facts.tls_owner):
        reasons.append(DeploymentPreflightReason.TLS_OWNER_INVALID)

    localhost_exception = (
        origin is not None
        and origin.localhost
        and origin.scheme == "http"
        and websocket is not None
        and websocket.scheme == "ws"
        and tls_termination is TlsTerminationFact.LOCALHOST_CONTROLLED_EXCEPTION
    )
    configuration_ready = not reasons
    if configuration_ready and localhost_exception:
        reasons.append(DeploymentPreflightReason.LOCALHOST_CONTROLLED_EXCEPTION)
    return _result(reasons, ready=configuration_ready)


__all__ = [
    "DeploymentPreflightFacts",
    "DeploymentPreflightReason",
    "DeploymentPreflightResult",
    "TlsTerminationFact",
    "evaluate_live_voice_deployment_preflight",
]
