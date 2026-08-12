# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded, credential-free runtime observation for a Live Voice deployment.

This module is intentionally separate from the pure configuration evaluator.
It can make at most three direct HTTPS requests to one explicitly supplied,
private origin.  It never follows redirects, reads response bodies, uses proxy
environment variables, or accepts caller supplied headers, credentials,
cookies, tokens, certificate material, or request bodies.

The result is a point-in-time runtime observation.  Even a fully satisfied
result does not grant formal deployment or Integrated Web Alpha acceptance.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from urllib.parse import SplitResult, urlsplit

from jiuwenswarm.channels.web.live_voice_deployment_preflight import (
    DeploymentPreflightFacts,
    DeploymentPreflightReason,
    TlsTerminationFact,
    evaluate_live_voice_deployment_preflight,
)


_MEDIA_SUBPROTOCOL = "live-voice.media.v1"
_WEBSOCKET_KEY = "dGhlIHNhbXBsZSBub25jZQ=="
_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_MAX_URL_UNITS = 2048
_MAX_PATH_UNITS = 512
_MAX_CSP_UNITS = 16_384
_MIN_TIMEOUT_MS = 100
_MAX_TIMEOUT_MS = 10_000
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=:@-]+")
_DIRECTIVE_NAME = re.compile(r"[a-z][a-z0-9-]*")
_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class DeploymentRuntimeTlsVersion(StrEnum):
    """Closed TLS versions retained by the observer."""

    TLS_1_2 = "TLSv1.2"
    TLS_1_3 = "TLSv1.3"
    MIXED_SUPPORTED = "mixed_supported"
    UNKNOWN = "unknown"


class DeploymentRuntimeReason(StrEnum):
    """Closed, content-free runtime observation outcomes."""

    RUNTIME_CHECKS_SATISFIED = "RUNTIME_CHECKS_SATISFIED"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    REQUEST_INVALID = "REQUEST_INVALID"
    INJECTED_TRANSPORT_UNTRUSTED = "INJECTED_TRANSPORT_UNTRUSTED"
    TARGET_NOT_PRIVATE = "TARGET_NOT_PRIVATE"
    DNS_UNOBSERVED = "DNS_UNOBSERVED"
    TLS_UNOBSERVED = "TLS_UNOBSERVED"
    TLS_VERSION_UNSUPPORTED = "TLS_VERSION_UNSUPPORTED"
    HEAD_UNOBSERVED = "HEAD_UNOBSERVED"
    HEAD_STATUS_MISMATCH = "HEAD_STATUS_MISMATCH"
    OPTIONS_UNOBSERVED = "OPTIONS_UNOBSERVED"
    OPTIONS_STATUS_MISMATCH = "OPTIONS_STATUS_MISMATCH"
    WEBSOCKET_UPGRADE_UNOBSERVED = "WEBSOCKET_UPGRADE_UNOBSERVED"
    REDIRECT_OBSERVED = "REDIRECT_OBSERVED"
    HSTS_MISSING_OR_INVALID = "HSTS_MISSING_OR_INVALID"
    NOSNIFF_MISSING_OR_INVALID = "NOSNIFF_MISSING_OR_INVALID"
    CSP_MISSING_OR_INVALID = "CSP_MISSING_OR_INVALID"
    CSP_BLOCKS_WEBSOCKET = "CSP_BLOCKS_WEBSOCKET"
    CORS_ORIGIN_MISMATCH = "CORS_ORIGIN_MISMATCH"
    CORS_CREDENTIALS_MISMATCH = "CORS_CREDENTIALS_MISMATCH"
    CORS_METHOD_MISMATCH = "CORS_METHOD_MISMATCH"
    WEBSOCKET_STATUS_MISMATCH = "WEBSOCKET_STATUS_MISMATCH"
    WEBSOCKET_HEADERS_MISMATCH = "WEBSOCKET_HEADERS_MISMATCH"
    WEBSOCKET_ACCEPT_MISMATCH = "WEBSOCKET_ACCEPT_MISMATCH"
    WEBSOCKET_SUBPROTOCOL_MISMATCH = "WEBSOCKET_SUBPROTOCOL_MISMATCH"
    TRANSPORT_UNAVAILABLE = "TRANSPORT_UNAVAILABLE"


class _TransportFailure(StrEnum):
    TARGET_NOT_PRIVATE = "target_not_private"
    DNS_UNOBSERVED = "dns_unobserved"
    TLS_UNOBSERVED = "tls_unobserved"
    HEAD_UNOBSERVED = "head_unobserved"
    OPTIONS_UNOBSERVED = "options_unobserved"
    UPGRADE_UNOBSERVED = "upgrade_unobserved"


@dataclass(frozen=True, slots=True, repr=False)
class LiveVoiceDeploymentObservationRequest:
    """Explicit private target for a bounded runtime observation."""

    https_url: str
    expected_origin: str
    websocket_path: str
    timeout_ms: int = 2_000

    def __repr__(self) -> str:
        return "LiveVoiceDeploymentObservationRequest(<redacted>)"


@dataclass(frozen=True, slots=True)
class DeploymentRuntimeFacts:
    """Sanitized facts retained after transport-local header classification."""

    request_count: int = 0
    tls_verified: bool = False
    tls_version: DeploymentRuntimeTlsVersion = DeploymentRuntimeTlsVersion.UNKNOWN
    head_observed: bool = False
    head_status_success: bool = False
    options_observed: bool = False
    options_status_success: bool = False
    websocket_upgrade_observed: bool = False
    redirect_observed: bool = False
    hsts_valid: bool = False
    nosniff_valid: bool = False
    csp_present_and_valid: bool = False
    csp_allows_websocket: bool = False
    cors_origin_exact: bool = False
    cors_credentials_allowed: bool = False
    cors_get_allowed: bool = False
    websocket_status_switching_protocols: bool = False
    websocket_upgrade_headers_valid: bool = False
    websocket_accept_valid: bool = False
    websocket_subprotocol_valid: bool = False

    def __post_init__(self) -> None:
        if type(self.request_count) is not int or not 0 <= self.request_count <= 3:
            raise ValueError("request_count must be an integer from zero through three")
        for name in (
            "tls_verified",
            "head_observed",
            "head_status_success",
            "options_observed",
            "options_status_success",
            "websocket_upgrade_observed",
            "redirect_observed",
            "hsts_valid",
            "nosniff_valid",
            "csp_present_and_valid",
            "csp_allows_websocket",
            "cors_origin_exact",
            "cors_credentials_allowed",
            "cors_get_allowed",
            "websocket_status_switching_protocols",
            "websocket_upgrade_headers_valid",
            "websocket_accept_valid",
            "websocket_subprotocol_valid",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if type(self.tls_version) is not DeploymentRuntimeTlsVersion:
            raise ValueError("tls_version must use the closed TLS vocabulary")
        if self.tls_verified != (
            self.tls_version
            in {
                DeploymentRuntimeTlsVersion.TLS_1_2,
                DeploymentRuntimeTlsVersion.TLS_1_3,
                DeploymentRuntimeTlsVersion.MIXED_SUPPORTED,
            }
        ):
            raise ValueError("TLS verification and version facts must agree")
        if self.tls_verified and self.request_count == 0:
            raise ValueError("TLS cannot be verified without a request")
        if (
            sum(
                (
                    self.head_observed,
                    self.options_observed,
                    self.websocket_upgrade_observed,
                )
            )
            > self.request_count
        ):
            raise ValueError("observed responses cannot exceed request count")
        if self.options_observed and not self.head_observed:
            raise ValueError("OPTIONS observation requires the preceding HEAD")
        if self.websocket_upgrade_observed and not self.options_observed:
            raise ValueError("Upgrade observation requires the preceding OPTIONS")
        if self.head_status_success and not self.head_observed:
            raise ValueError("HEAD status requires an observed response")
        if self.options_status_success and not self.options_observed:
            raise ValueError("OPTIONS status requires an observed response")
        if (
            any(
                (
                    self.hsts_valid,
                    self.nosniff_valid,
                    self.csp_present_and_valid,
                    self.csp_allows_websocket,
                )
            )
            and not self.head_observed
        ):
            raise ValueError("security-header facts require an observed HEAD")
        if self.csp_allows_websocket and not self.csp_present_and_valid:
            raise ValueError("CSP allow truth requires a valid CSP")
        if (
            any(
                (
                    self.cors_origin_exact,
                    self.cors_credentials_allowed,
                    self.cors_get_allowed,
                )
            )
            and not self.options_observed
        ):
            raise ValueError("CORS facts require an observed OPTIONS response")
        if (
            any(
                (
                    self.websocket_status_switching_protocols,
                    self.websocket_upgrade_headers_valid,
                    self.websocket_accept_valid,
                    self.websocket_subprotocol_valid,
                )
            )
            and not self.websocket_upgrade_observed
        ):
            raise ValueError("WebSocket facts require an observed Upgrade response")


@dataclass(frozen=True, slots=True)
class LiveVoiceDeploymentObservationResult:
    """Point-in-time runtime result without configuration or release authority."""

    runtime_checks_satisfied: bool
    reason_codes: tuple[DeploymentRuntimeReason, ...]
    facts: DeploymentRuntimeFacts
    real_runtime_observed: bool
    evidence_scope: str = field(default="runtime_observation_only", init=False)
    configuration_evaluated: bool = field(default=False, init=False)
    formal_deployment_ready: bool = field(default=False, init=False)
    alpha_accepted: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if type(self.runtime_checks_satisfied) is not bool:
            raise ValueError("runtime_checks_satisfied must be a boolean")
        if type(self.real_runtime_observed) is not bool:
            raise ValueError("real_runtime_observed must be a boolean")
        if type(self.facts) is not DeploymentRuntimeFacts:
            raise ValueError("facts must be sanitized runtime facts")
        if (
            type(self.reason_codes) is not tuple
            or not self.reason_codes
            or any(
                type(reason) is not DeploymentRuntimeReason
                for reason in self.reason_codes
            )
            or len(set(self.reason_codes)) != len(self.reason_codes)
        ):
            raise ValueError("reason_codes must be unique closed reasons")
        satisfied = (DeploymentRuntimeReason.RUNTIME_CHECKS_SATISFIED,)
        if self.runtime_checks_satisfied != (self.reason_codes == satisfied):
            raise ValueError("runtime result and reasons must agree")
        if (
            DeploymentRuntimeReason.RUNTIME_CHECKS_SATISFIED in self.reason_codes
            and self.reason_codes != satisfied
        ):
            raise ValueError("satisfied cannot be combined with another reason")
        if self.runtime_checks_satisfied and not self.real_runtime_observed:
            raise ValueError("only a real runtime observation can satisfy checks")
        complete_facts = (
            self.facts.request_count == 3
            and self.facts.tls_verified
            and self.facts.head_observed
            and self.facts.head_status_success
            and self.facts.options_observed
            and self.facts.options_status_success
            and self.facts.websocket_upgrade_observed
            and not self.facts.redirect_observed
            and self.facts.hsts_valid
            and self.facts.nosniff_valid
            and self.facts.csp_present_and_valid
            and self.facts.csp_allows_websocket
            and self.facts.cors_origin_exact
            and self.facts.cors_credentials_allowed
            and self.facts.cors_get_allowed
            and self.facts.websocket_status_switching_protocols
            and self.facts.websocket_upgrade_headers_valid
            and self.facts.websocket_accept_valid
            and self.facts.websocket_subprotocol_valid
        )
        if self.runtime_checks_satisfied and not complete_facts:
            raise ValueError("satisfied result requires every bounded runtime fact")
        if self.real_runtime_observed and not (
            self.facts.request_count > 0 and self.facts.tls_verified
        ):
            raise ValueError("real observation requires a verified TLS response")


@dataclass(frozen=True, slots=True)
class _ValidatedRequest:
    host: str
    port: int
    origin: str
    head_path: str
    websocket_path: str
    websocket_url: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class _SafeHttpResponse:
    status: int
    tls_version: DeploymentRuntimeTlsVersion
    headers: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _TransportObservation:
    facts: DeploymentRuntimeFacts
    failure: _TransportFailure | None = None


class DeploymentRuntimeTransport(Protocol):
    """Injectable test transport; injected instances never grant real provenance."""

    def observe(self, request: _ValidatedRequest) -> _TransportObservation: ...


def _canonical_path(value: str, *, limit: int) -> str | None:
    if (
        type(value) is not str
        or not value
        or len(value) > limit
        or not value.isascii()
        or not value.startswith("/")
        or "//" in value
        or "\\" in value
        or "%" in value
        or "?" in value
        or "#" in value
        or any(ord(character) < 0x20 or character.isspace() for character in value)
    ):
        return None
    if value == "/":
        return value
    segments = value[1:].split("/")
    if any(
        not segment
        or segment in {".", ".."}
        or _PATH_SEGMENT.fullmatch(segment) is None
        for segment in segments
    ):
        return None
    return value


def _canonical_https(
    parsed: SplitResult, *, require_origin: bool
) -> tuple[str, int, str] | None:
    try:
        port = parsed.port or 443
    except ValueError:
        return None
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or hostname != hostname.lower()
        or not hostname.isascii()
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not 1 <= port <= 65_535
    ):
        return None
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return None
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return None
    labels = hostname.split(".")
    if (
        len(hostname) > 253
        or len(labels) < 2
        or any(_DOMAIN_LABEL.fullmatch(label) is None for label in labels)
        or not any(character.isalpha() for character in labels[-1])
    ):
        return None
    authority = hostname if port == 443 else f"{hostname}:{port}"
    if parsed.netloc != authority:
        return None
    path = parsed.path or "/"
    if require_origin and path != "/":
        return None
    canonical = _canonical_path(path, limit=_MAX_PATH_UNITS)
    if canonical is None:
        return None
    return hostname, port, canonical


def _validate_request(value: object) -> _ValidatedRequest | None:
    if type(value) is not LiveVoiceDeploymentObservationRequest:
        return None
    if (
        type(value.https_url) is not str
        or type(value.expected_origin) is not str
        or type(value.websocket_path) is not str
        or len(value.https_url) > _MAX_URL_UNITS
        or len(value.expected_origin) > _MAX_URL_UNITS
        or type(value.timeout_ms) is not int
        or not _MIN_TIMEOUT_MS <= value.timeout_ms <= _MAX_TIMEOUT_MS
    ):
        return None
    try:
        parsed_target = urlsplit(value.https_url)
        parsed_expected = urlsplit(value.expected_origin)
    except ValueError:
        return None
    target = _canonical_https(parsed_target, require_origin=False)
    expected = _canonical_https(parsed_expected, require_origin=True)
    websocket_path = _canonical_path(value.websocket_path, limit=_MAX_PATH_UNITS)
    if target is None or expected is None or websocket_path is None:
        return None
    host, port, head_path = target
    expected_host, expected_port, _ = expected
    if (host, port) != (expected_host, expected_port):
        return None
    authority = host if port == 443 else f"{host}:{port}"
    origin = f"https://{authority}"
    if value.expected_origin != origin:
        return None
    websocket_url = f"wss://{authority}{websocket_path}"
    return _ValidatedRequest(
        host=host,
        port=port,
        origin=origin,
        head_path=head_path,
        websocket_path=websocket_path,
        websocket_url=websocket_url,
        timeout_seconds=value.timeout_ms / 1_000,
    )


def _closed_tls_version(value: str | None) -> DeploymentRuntimeTlsVersion:
    if value == DeploymentRuntimeTlsVersion.TLS_1_2.value:
        return DeploymentRuntimeTlsVersion.TLS_1_2
    if value == DeploymentRuntimeTlsVersion.TLS_1_3.value:
        return DeploymentRuntimeTlsVersion.TLS_1_3
    return DeploymentRuntimeTlsVersion.UNKNOWN


def _resolve_private_address(host: str, port: int) -> str:
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if item[0] in {socket.AF_INET, socket.AF_INET6}
    }
    if not addresses:
        raise OSError("DNS resolution returned no address")
    parsed = tuple(ipaddress.ip_address(address) for address in sorted(addresses))
    if any(
        not address.is_private
        or address.is_multicast
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        for address in parsed
    ):
        raise PermissionError("deployment target is not private")
    return str(parsed[0])


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        address: str,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host=host, port=port, timeout=timeout, context=context)
        self._address = address
        self._runtime_context = context

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._address, self.port),
            timeout=self.timeout,
        )
        try:
            self.sock = self._runtime_context.wrap_socket(
                raw_socket,
                server_hostname=self.host,
            )
        except BaseException:  # noqa: BLE001 - preserve process-control after closing raw socket
            raw_socket.close()
            raise


def _tls_context() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    context.set_alpn_protocols(["http/1.1"])
    return context


def _perform_request(
    request: _ValidatedRequest,
    address: str,
    method: str,
    path: str,
    headers: Mapping[str, str],
) -> _SafeHttpResponse:
    connection = _PinnedHTTPSConnection(
        host=request.host,
        port=request.port,
        address=address,
        timeout=request.timeout_seconds,
        context=_tls_context(),
    )
    response: http.client.HTTPResponse | None = None
    try:
        connection.request(method, path, body=None, headers=dict(headers))
        response = connection.getresponse()
        tls_version = _closed_tls_version(
            connection.sock.version() if connection.sock is not None else None
        )
        retained: dict[str, list[str]] = {}
        allowed = {
            "strict-transport-security",
            "x-content-type-options",
            "content-security-policy",
            "access-control-allow-origin",
            "access-control-allow-credentials",
            "access-control-allow-methods",
            "upgrade",
            "connection",
            "sec-websocket-accept",
            "sec-websocket-protocol",
        }
        for raw_name, raw_value in response.getheaders():
            name = raw_name.lower()
            if name in allowed:
                retained.setdefault(name, []).append(raw_value)
        return _SafeHttpResponse(
            status=response.status,
            tls_version=tls_version,
            headers={name: tuple(values) for name, values in retained.items()},
        )
    finally:
        try:
            if response is not None:
                response.close()
        finally:
            connection.close()


def _single_header(headers: Mapping[str, tuple[str, ...]], name: str) -> str | None:
    values = headers.get(name, ())
    if len(values) != 1:
        return None
    value = values[0]
    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_CSP_UNITS
        or not value.isascii()
        or "\r" in value
        or "\n" in value
    ):
        return None
    return value.strip()


def _hsts_valid(headers: Mapping[str, tuple[str, ...]]) -> bool:
    value = _single_header(headers, "strict-transport-security")
    if value is None:
        return False
    directives: dict[str, str | None] = {}
    for item in value.split(";"):
        parts = item.strip().split("=", 1)
        name = parts[0].lower()
        if not name or name in directives:
            return False
        directives[name] = parts[1].strip() if len(parts) == 2 else None
    max_age = directives.get("max-age")
    return max_age is not None and max_age.isdecimal() and int(max_age) > 0


def _csp_sources(policy: str) -> tuple[str, ...] | None:
    directives: dict[str, tuple[str, ...]] = {}
    for raw_directive in policy.split(";"):
        raw_directive = raw_directive.strip()
        if not raw_directive:
            continue
        parts = raw_directive.split()
        name = parts[0].lower()
        if _DIRECTIVE_NAME.fullmatch(name) is None or name in directives:
            return None
        directives[name] = tuple(parts[1:])
    return directives.get("connect-src", directives.get("default-src"))


def _csp_status(
    headers: Mapping[str, tuple[str, ...]],
    *,
    origin: str,
    websocket_url: str,
    websocket_path: str,
) -> tuple[bool, bool]:
    values = headers.get("content-security-policy", ())
    if not values:
        return False, False
    policies: list[str] = []
    for value in values:
        if (
            type(value) is not str
            or not value
            or len(value) > _MAX_CSP_UNITS
            or not value.isascii()
            or "\r" in value
            or "\n" in value
        ):
            return False, False
        policies.extend(part.strip() for part in value.split(","))
    if not policies or any(not policy for policy in policies):
        return False, False
    websocket = urlsplit(websocket_url)
    websocket_origin = f"{websocket.scheme}://{websocket.netloc}"
    for policy in policies:
        sources = _csp_sources(policy)
        if sources is None or not sources:
            return False, False
        # The current deployment preflight deliberately accepts only a
        # websocket origin. A CSP host-source may narrow that origin with the
        # exact product path; validate the exact endpoint here, then project
        # only that already-proven source into the preflight contract.
        normalized_sources = tuple(
            websocket_origin if source == websocket_url else source
            for source in sources
        )
        result = evaluate_live_voice_deployment_preflight(
            enabled=True,
            facts=DeploymentPreflightFacts(
                public_origin=origin,
                public_websocket_url=websocket_url,
                allowed_origins=(origin,),
                csp_connect_src=normalized_sources,
                cors_credentials_allowed=True,
                proxy_websocket_upgrade=True,
                tls_termination=TlsTerminationFact.DECLARED,
                tls_owner="runtime-observer",
            ),
        )
        csp_reasons = {
            DeploymentPreflightReason.CSP_CONNECT_SRC_UNKNOWN,
            DeploymentPreflightReason.CSP_CONNECT_SRC_INVALID,
            DeploymentPreflightReason.CSP_CONNECT_SRC_OVERBROAD,
            DeploymentPreflightReason.CSP_CONNECT_SRC_BLOCKS_WEBSOCKET,
        }
        if any(reason in csp_reasons for reason in result.reason_codes):
            return True, False
    return True, True


def _comma_tokens(value: str | None) -> set[str]:
    if value is None:
        return set()
    return {token.strip().lower() for token in value.split(",") if token.strip()}


def _accept_value() -> str:
    digest = hashlib.sha1(  # noqa: S324 - mandated by RFC 6455 handshake
        f"{_WEBSOCKET_KEY}{_WEBSOCKET_GUID}".encode("ascii")
    ).digest()
    return base64.b64encode(digest).decode("ascii")


_Requester = Callable[
    [_ValidatedRequest, str, str, str, Mapping[str, str]],
    _SafeHttpResponse,
]


class _StdlibDeploymentRuntimeTransport:
    def __init__(self, requester: _Requester = _perform_request) -> None:
        self._requester = requester

    def observe(self, request: _ValidatedRequest) -> _TransportObservation:
        try:
            address = _resolve_private_address(request.host, request.port)
        except PermissionError:
            return _TransportObservation(
                facts=DeploymentRuntimeFacts(),
                failure=_TransportFailure.TARGET_NOT_PRIVATE,
            )
        except Exception:  # noqa: BLE001 - DNS failures are content-free
            return _TransportObservation(
                facts=DeploymentRuntimeFacts(),
                failure=_TransportFailure.DNS_UNOBSERVED,
            )

        count = 0
        tls_versions: list[DeploymentRuntimeTlsVersion] = []
        redirect = False
        try:
            count += 1
            head = self._requester(request, address, "HEAD", request.head_path, {})
            tls_versions.append(head.tls_version)
        except Exception:  # noqa: BLE001 - transport failures are content-free
            return _TransportObservation(
                facts=DeploymentRuntimeFacts(request_count=count),
                failure=_TransportFailure.HEAD_UNOBSERVED,
            )
        redirect = redirect or 300 <= head.status <= 399
        csp_valid, csp_allows = _csp_status(
            head.headers,
            origin=request.origin,
            websocket_url=request.websocket_url,
            websocket_path=request.websocket_path,
        )

        try:
            count += 1
            options = self._requester(
                request,
                address,
                "OPTIONS",
                request.websocket_path,
                {
                    "Origin": request.origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            tls_versions.append(options.tls_version)
        except Exception:  # noqa: BLE001 - transport failures are content-free
            return _TransportObservation(
                facts=DeploymentRuntimeFacts(
                    request_count=count,
                    tls_verified=all(
                        version is not DeploymentRuntimeTlsVersion.UNKNOWN
                        for version in tls_versions
                    ),
                    tls_version=(
                        tls_versions[0]
                        if len(set(tls_versions)) == 1
                        else DeploymentRuntimeTlsVersion.UNKNOWN
                    ),
                    head_observed=True,
                    head_status_success=200 <= head.status <= 299,
                    redirect_observed=redirect,
                    hsts_valid=_hsts_valid(head.headers),
                    nosniff_valid=(
                        _single_header(head.headers, "x-content-type-options") or ""
                    ).lower()
                    == "nosniff",
                    csp_present_and_valid=csp_valid,
                    csp_allows_websocket=csp_allows,
                ),
                failure=_TransportFailure.OPTIONS_UNOBSERVED,
            )
        redirect = redirect or 300 <= options.status <= 399

        try:
            count += 1
            upgrade = self._requester(
                request,
                address,
                "GET",
                request.websocket_path,
                {
                    "Origin": request.origin,
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Key": _WEBSOCKET_KEY,
                    "Sec-WebSocket-Version": "13",
                    "Sec-WebSocket-Protocol": _MEDIA_SUBPROTOCOL,
                },
            )
            tls_versions.append(upgrade.tls_version)
        except Exception:  # noqa: BLE001 - transport failures are content-free
            return _TransportObservation(
                facts=_facts_from_responses(
                    count=count,
                    tls_versions=tls_versions,
                    head=head,
                    options=options,
                    upgrade=None,
                    request=request,
                    redirect=redirect,
                ),
                failure=_TransportFailure.UPGRADE_UNOBSERVED,
            )
        redirect = redirect or 300 <= upgrade.status <= 399
        return _TransportObservation(
            facts=_facts_from_responses(
                count=count,
                tls_versions=tls_versions,
                head=head,
                options=options,
                upgrade=upgrade,
                request=request,
                redirect=redirect,
            )
        )


def _facts_from_responses(
    *,
    count: int,
    tls_versions: list[DeploymentRuntimeTlsVersion],
    head: _SafeHttpResponse,
    options: _SafeHttpResponse,
    upgrade: _SafeHttpResponse | None,
    request: _ValidatedRequest,
    redirect: bool,
) -> DeploymentRuntimeFacts:
    supported_versions = {
        DeploymentRuntimeTlsVersion.TLS_1_2,
        DeploymentRuntimeTlsVersion.TLS_1_3,
    }
    tls_verified = bool(tls_versions) and all(
        version in supported_versions for version in tls_versions
    )
    if tls_verified and len(set(tls_versions)) == 1:
        tls_version = tls_versions[0]
    elif tls_verified:
        tls_version = DeploymentRuntimeTlsVersion.MIXED_SUPPORTED
    else:
        tls_version = DeploymentRuntimeTlsVersion.UNKNOWN
    csp_valid, csp_allows = _csp_status(
        head.headers,
        origin=request.origin,
        websocket_url=request.websocket_url,
        websocket_path=request.websocket_path,
    )
    allow_origin = _single_header(options.headers, "access-control-allow-origin")
    allow_credentials = _single_header(
        options.headers, "access-control-allow-credentials"
    )
    allow_methods = _comma_tokens(
        _single_header(options.headers, "access-control-allow-methods")
    )
    upgrade_headers = upgrade.headers if upgrade is not None else {}
    return DeploymentRuntimeFacts(
        request_count=count,
        tls_verified=tls_verified,
        tls_version=tls_version,
        head_observed=True,
        head_status_success=200 <= head.status <= 299,
        options_observed=True,
        options_status_success=200 <= options.status <= 299,
        websocket_upgrade_observed=upgrade is not None,
        redirect_observed=redirect,
        hsts_valid=_hsts_valid(head.headers),
        nosniff_valid=(
            _single_header(head.headers, "x-content-type-options") or ""
        ).lower()
        == "nosniff",
        csp_present_and_valid=csp_valid,
        csp_allows_websocket=csp_allows,
        cors_origin_exact=allow_origin == request.origin,
        cors_credentials_allowed=(allow_credentials or "").lower() == "true",
        cors_get_allowed="get" in allow_methods,
        websocket_status_switching_protocols=(
            upgrade is not None and upgrade.status == 101
        ),
        websocket_upgrade_headers_valid=(
            _single_header(upgrade_headers, "upgrade") or ""
        ).lower()
        == "websocket"
        and "upgrade" in _comma_tokens(_single_header(upgrade_headers, "connection")),
        websocket_accept_valid=(
            _single_header(upgrade_headers, "sec-websocket-accept") == _accept_value()
        ),
        websocket_subprotocol_valid=(
            _single_header(upgrade_headers, "sec-websocket-protocol")
            == _MEDIA_SUBPROTOCOL
        ),
    )


def _reason_for_transport_failure(
    failure: _TransportFailure | None,
) -> DeploymentRuntimeReason | None:
    return {
        _TransportFailure.TARGET_NOT_PRIVATE: DeploymentRuntimeReason.TARGET_NOT_PRIVATE,
        _TransportFailure.DNS_UNOBSERVED: DeploymentRuntimeReason.DNS_UNOBSERVED,
        _TransportFailure.TLS_UNOBSERVED: DeploymentRuntimeReason.TLS_UNOBSERVED,
        _TransportFailure.HEAD_UNOBSERVED: DeploymentRuntimeReason.HEAD_UNOBSERVED,
        _TransportFailure.OPTIONS_UNOBSERVED: DeploymentRuntimeReason.OPTIONS_UNOBSERVED,
        _TransportFailure.UPGRADE_UNOBSERVED: DeploymentRuntimeReason.WEBSOCKET_UPGRADE_UNOBSERVED,
        None: None,
    }[failure]


def _fact_reasons(facts: DeploymentRuntimeFacts) -> tuple[DeploymentRuntimeReason, ...]:
    reasons: list[DeploymentRuntimeReason] = []
    if not facts.tls_verified:
        reasons.append(DeploymentRuntimeReason.TLS_UNOBSERVED)
    elif facts.tls_version not in {
        DeploymentRuntimeTlsVersion.TLS_1_2,
        DeploymentRuntimeTlsVersion.TLS_1_3,
        DeploymentRuntimeTlsVersion.MIXED_SUPPORTED,
    }:
        reasons.append(DeploymentRuntimeReason.TLS_VERSION_UNSUPPORTED)
    if not facts.head_observed:
        reasons.append(DeploymentRuntimeReason.HEAD_UNOBSERVED)
    elif not facts.head_status_success:
        reasons.append(DeploymentRuntimeReason.HEAD_STATUS_MISMATCH)
    if not facts.options_observed:
        reasons.append(DeploymentRuntimeReason.OPTIONS_UNOBSERVED)
    elif not facts.options_status_success:
        reasons.append(DeploymentRuntimeReason.OPTIONS_STATUS_MISMATCH)
    if not facts.websocket_upgrade_observed:
        reasons.append(DeploymentRuntimeReason.WEBSOCKET_UPGRADE_UNOBSERVED)
    if facts.redirect_observed:
        reasons.append(DeploymentRuntimeReason.REDIRECT_OBSERVED)
    if not facts.hsts_valid:
        reasons.append(DeploymentRuntimeReason.HSTS_MISSING_OR_INVALID)
    if not facts.nosniff_valid:
        reasons.append(DeploymentRuntimeReason.NOSNIFF_MISSING_OR_INVALID)
    if not facts.csp_present_and_valid:
        reasons.append(DeploymentRuntimeReason.CSP_MISSING_OR_INVALID)
    elif not facts.csp_allows_websocket:
        reasons.append(DeploymentRuntimeReason.CSP_BLOCKS_WEBSOCKET)
    if not facts.cors_origin_exact:
        reasons.append(DeploymentRuntimeReason.CORS_ORIGIN_MISMATCH)
    if not facts.cors_credentials_allowed:
        reasons.append(DeploymentRuntimeReason.CORS_CREDENTIALS_MISMATCH)
    if not facts.cors_get_allowed:
        reasons.append(DeploymentRuntimeReason.CORS_METHOD_MISMATCH)
    if not facts.websocket_status_switching_protocols:
        reasons.append(DeploymentRuntimeReason.WEBSOCKET_STATUS_MISMATCH)
    if not facts.websocket_upgrade_headers_valid:
        reasons.append(DeploymentRuntimeReason.WEBSOCKET_HEADERS_MISMATCH)
    if not facts.websocket_accept_valid:
        reasons.append(DeploymentRuntimeReason.WEBSOCKET_ACCEPT_MISMATCH)
    if not facts.websocket_subprotocol_valid:
        reasons.append(DeploymentRuntimeReason.WEBSOCKET_SUBPROTOCOL_MISMATCH)
    return tuple(reasons)


def _disabled_result() -> LiveVoiceDeploymentObservationResult:
    return LiveVoiceDeploymentObservationResult(
        runtime_checks_satisfied=False,
        reason_codes=(DeploymentRuntimeReason.FEATURE_DISABLED,),
        facts=DeploymentRuntimeFacts(),
        real_runtime_observed=False,
    )


def observe_live_voice_deployment_runtime(
    *,
    enabled: bool,
    request: object,
    transport: DeploymentRuntimeTransport | None = None,
) -> LiveVoiceDeploymentObservationResult:
    """Observe one explicit deployment target without credentials or bodies."""

    if enabled is False:
        return _disabled_result()
    if enabled is not True:
        return LiveVoiceDeploymentObservationResult(
            runtime_checks_satisfied=False,
            reason_codes=(DeploymentRuntimeReason.REQUEST_INVALID,),
            facts=DeploymentRuntimeFacts(),
            real_runtime_observed=False,
        )
    validated = _validate_request(request)
    if validated is None:
        return LiveVoiceDeploymentObservationResult(
            runtime_checks_satisfied=False,
            reason_codes=(DeploymentRuntimeReason.REQUEST_INVALID,),
            facts=DeploymentRuntimeFacts(),
            real_runtime_observed=False,
        )

    real_transport = transport is None
    selected: DeploymentRuntimeTransport = (
        _StdlibDeploymentRuntimeTransport() if transport is None else transport
    )
    try:
        observation = selected.observe(validated)
        if type(observation) is not _TransportObservation:
            raise ValueError("transport returned an invalid observation")
        facts = observation.facts
        if type(facts) is not DeploymentRuntimeFacts:
            raise ValueError("transport returned invalid facts")
        if (
            observation.failure is not None
            and type(observation.failure) is not _TransportFailure
        ):
            raise ValueError("transport returned an invalid failure classification")
    except Exception:  # noqa: BLE001 - injected transport is an untrusted seam
        return LiveVoiceDeploymentObservationResult(
            runtime_checks_satisfied=False,
            reason_codes=(DeploymentRuntimeReason.TRANSPORT_UNAVAILABLE,),
            facts=DeploymentRuntimeFacts(),
            real_runtime_observed=False,
        )

    reasons = list(_fact_reasons(facts))
    failure_reason = _reason_for_transport_failure(observation.failure)
    if failure_reason is not None and failure_reason not in reasons:
        reasons.insert(0, failure_reason)
    if not real_transport:
        reasons.insert(0, DeploymentRuntimeReason.INJECTED_TRANSPORT_UNTRUSTED)
    real_observed = real_transport and facts.request_count > 0 and facts.tls_verified
    satisfied = real_transport and not reasons
    return LiveVoiceDeploymentObservationResult(
        runtime_checks_satisfied=satisfied,
        reason_codes=(
            (DeploymentRuntimeReason.RUNTIME_CHECKS_SATISFIED,)
            if satisfied
            else tuple(reasons)
        ),
        facts=facts,
        real_runtime_observed=real_observed,
    )


__all__ = [
    "DeploymentRuntimeFacts",
    "DeploymentRuntimeReason",
    "DeploymentRuntimeTlsVersion",
    "DeploymentRuntimeTransport",
    "LiveVoiceDeploymentObservationRequest",
    "LiveVoiceDeploymentObservationResult",
    "observe_live_voice_deployment_runtime",
]
