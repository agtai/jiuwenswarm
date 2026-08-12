# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
import ssl

import pytest

import jiuwenswarm.channels.web.live_voice_deployment_observer as observer_module
from jiuwenswarm.channels.web.live_voice_deployment_observer import (
    DeploymentRuntimeFacts,
    DeploymentRuntimeReason,
    DeploymentRuntimeTlsVersion,
    LiveVoiceDeploymentObservationRequest,
    LiveVoiceDeploymentObservationResult,
    observe_live_voice_deployment_runtime,
)


def _request(**overrides: object) -> LiveVoiceDeploymentObservationRequest:
    values: dict[str, object] = {
        "https_url": "https://voice.example.test/app",
        "expected_origin": "https://voice.example.test",
        "websocket_path": "/ws/live-voice/media",
        "timeout_ms": 2_000,
    }
    values.update(overrides)
    return LiveVoiceDeploymentObservationRequest(**values)  # type: ignore[arg-type]


def _complete_facts(**overrides: object) -> DeploymentRuntimeFacts:
    values: dict[str, object] = {
        "request_count": 3,
        "tls_verified": True,
        "tls_version": DeploymentRuntimeTlsVersion.TLS_1_3,
        "head_observed": True,
        "head_status_success": True,
        "options_observed": True,
        "options_status_success": True,
        "websocket_upgrade_observed": True,
        "redirect_observed": False,
        "hsts_valid": True,
        "nosniff_valid": True,
        "csp_present_and_valid": True,
        "csp_allows_websocket": True,
        "cors_origin_exact": True,
        "cors_credentials_allowed": True,
        "cors_get_allowed": True,
        "websocket_status_switching_protocols": True,
        "websocket_upgrade_headers_valid": True,
        "websocket_accept_valid": True,
        "websocket_subprotocol_valid": True,
    }
    values.update(overrides)
    return DeploymentRuntimeFacts(**values)  # type: ignore[arg-type]


class _FakeTransport:
    def __init__(self, facts: DeploymentRuntimeFacts) -> None:
        self.calls = 0
        self.facts = facts

    def observe(
        self, request: observer_module._ValidatedRequest
    ) -> observer_module._TransportObservation:
        self.calls += 1
        assert request.origin == "https://voice.example.test"
        return observer_module._TransportObservation(facts=self.facts)


def test_feature_off_reads_neither_request_nor_transport() -> None:
    class _Exploding:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(name)

    result = observe_live_voice_deployment_runtime(
        enabled=False,
        request=_Exploding(),
        transport=_Exploding(),  # type: ignore[arg-type]
    )

    assert result.reason_codes == (DeploymentRuntimeReason.FEATURE_DISABLED,)
    assert result.facts.request_count == 0
    assert result.real_runtime_observed is False
    assert result.formal_deployment_ready is False
    assert result.alpha_accepted is False


@pytest.mark.parametrize(
    "target_request",
    [
        _request(https_url="http://voice.example.test/app"),
        _request(https_url="https://user@voice.example.test/app"),
        _request(https_url="https://voice.example.test/app?credential=x"),
        _request(https_url="https://voice.example.test/app#fragment"),
        _request(https_url="https://127.0.0.1/app"),
        _request(
            https_url="https://localhost/app", expected_origin="https://localhost"
        ),
        _request(
            https_url="https://voice_example.test/app",
            expected_origin="https://voice_example.test",
        ),
        _request(
            https_url="https://voice.example.123/app",
            expected_origin="https://voice.example.123",
        ),
        _request(
            https_url="https://voice.example.test.:443/app",
            expected_origin="https://voice.example.test.:443",
        ),
        _request(https_url="https://voice.example.test:443/app"),
        _request(https_url="https://VOICE.example.test/app"),
        _request(https_url="https://["),
        _request(https_url="https://[]/app"),
        _request(https_url="https://voice.example.test\uff0f@evil.example/app"),
        _request(https_url="https://voice" + chr(1) + ".example.test/app"),
        _request(expected_origin="https://other.example.test"),
        _request(expected_origin="https://voice.example.test/other"),
        _request(websocket_path="ws/live-voice/media"),
        _request(websocket_path="/ws/%6cive-voice/media"),
        _request(websocket_path="/ws/live-voice/media?ticket=secret"),
        _request(websocket_path="/ws/../media"),
        _request(websocket_path="/ws/line\r\nbreak"),
        _request(timeout_ms=True),
        _request(timeout_ms=99),
        _request(timeout_ms=10_001),
    ],
)
def test_invalid_or_unsafe_targets_fail_before_transport(
    target_request: LiveVoiceDeploymentObservationRequest,
) -> None:
    transport = _FakeTransport(_complete_facts())

    result = observe_live_voice_deployment_runtime(
        enabled=True,
        request=target_request,
        transport=transport,
    )

    assert result.reason_codes == (DeploymentRuntimeReason.REQUEST_INVALID,)
    assert transport.calls == 0
    assert result.real_runtime_observed is False


def test_request_repr_and_invalid_result_do_not_echo_sensitive_input() -> None:
    sentinel = "PRIVATE-DEPLOYMENT-TOKEN"
    request = _request(https_url=f"https://user:{sentinel}@voice.example.test/app")

    result = observe_live_voice_deployment_runtime(enabled=True, request=request)

    assert sentinel not in repr(request)
    assert sentinel not in repr(result)
    assert result.reason_codes == (DeploymentRuntimeReason.REQUEST_INVALID,)


def test_injected_transport_can_exercise_facts_but_never_grants_provenance() -> None:
    transport = _FakeTransport(_complete_facts())

    result = observe_live_voice_deployment_runtime(
        enabled=True,
        request=_request(),
        transport=transport,
    )

    assert transport.calls == 1
    assert result.runtime_checks_satisfied is False
    assert result.real_runtime_observed is False
    assert result.reason_codes == (
        DeploymentRuntimeReason.INJECTED_TRANSPORT_UNTRUSTED,
    )
    assert result.configuration_evaluated is False
    assert result.formal_deployment_ready is False
    assert result.alpha_accepted is False


def test_only_default_real_transport_can_report_satisfied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport(_complete_facts())
    monkeypatch.setattr(
        observer_module,
        "_StdlibDeploymentRuntimeTransport",
        lambda: transport,
    )

    result = observe_live_voice_deployment_runtime(enabled=True, request=_request())

    assert result.runtime_checks_satisfied is True
    assert result.reason_codes == (DeploymentRuntimeReason.RUNTIME_CHECKS_SATISFIED,)
    assert result.real_runtime_observed is True
    assert result.formal_deployment_ready is False


def test_transport_exception_is_content_free_and_does_not_claim_observation() -> None:
    sentinel = "PRIVATE-TRANSPORT-ERROR"

    class _FailingTransport:
        def observe(self, request: observer_module._ValidatedRequest) -> object:
            del request
            raise RuntimeError(sentinel)

    result = observe_live_voice_deployment_runtime(
        enabled=True,
        request=_request(),
        transport=_FailingTransport(),  # type: ignore[arg-type]
    )

    assert result.reason_codes == (DeploymentRuntimeReason.TRANSPORT_UNAVAILABLE,)
    assert sentinel not in repr(result)
    assert result.real_runtime_observed is False


def test_injected_transport_private_failure_value_is_rejected_content_free() -> None:
    sentinel = "PRIVATE-FAILURE-ENUM"

    class _ForgedTransport:
        def observe(
            self, request: observer_module._ValidatedRequest
        ) -> observer_module._TransportObservation:
            del request
            return observer_module._TransportObservation(
                facts=DeploymentRuntimeFacts(),
                failure=sentinel,  # type: ignore[arg-type]
            )

    result = observe_live_voice_deployment_runtime(
        enabled=True,
        request=_request(),
        transport=_ForgedTransport(),
    )

    assert result.reason_codes == (DeploymentRuntimeReason.TRANSPORT_UNAVAILABLE,)
    assert result.real_runtime_observed is False
    assert sentinel not in repr(result)


def test_sanitized_facts_report_each_failed_runtime_boundary() -> None:
    facts = _complete_facts(
        redirect_observed=True,
        hsts_valid=False,
        csp_allows_websocket=False,
        cors_origin_exact=False,
        websocket_accept_valid=False,
    )

    result = observe_live_voice_deployment_runtime(
        enabled=True,
        request=_request(),
        transport=_FakeTransport(facts),
    )

    assert result.reason_codes == (
        DeploymentRuntimeReason.INJECTED_TRANSPORT_UNTRUSTED,
        DeploymentRuntimeReason.REDIRECT_OBSERVED,
        DeploymentRuntimeReason.HSTS_MISSING_OR_INVALID,
        DeploymentRuntimeReason.CSP_BLOCKS_WEBSOCKET,
        DeploymentRuntimeReason.CORS_ORIGIN_MISMATCH,
        DeploymentRuntimeReason.WEBSOCKET_ACCEPT_MISMATCH,
    )


def test_non_success_head_and_options_statuses_cannot_satisfy_runtime() -> None:
    result = observe_live_voice_deployment_runtime(
        enabled=True,
        request=_request(),
        transport=_FakeTransport(
            _complete_facts(
                head_status_success=False,
                options_status_success=False,
            )
        ),
    )

    assert DeploymentRuntimeReason.HEAD_STATUS_MISMATCH in result.reason_codes
    assert DeploymentRuntimeReason.OPTIONS_STATUS_MISMATCH in result.reason_codes


def _response(
    *,
    status: int,
    headers: dict[str, tuple[str, ...]],
    tls: DeploymentRuntimeTlsVersion = DeploymentRuntimeTlsVersion.TLS_1_3,
) -> observer_module._SafeHttpResponse:
    return observer_module._SafeHttpResponse(
        status=status,
        tls_version=tls,
        headers=headers,
    )


def test_stdlib_transport_makes_three_bounded_credential_free_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, str]]] = []

    def requester(
        request: observer_module._ValidatedRequest,
        address: str,
        method: str,
        path: str,
        headers: Mapping[str, str],
    ) -> observer_module._SafeHttpResponse:
        assert address == "10.0.0.10"
        retained = dict(headers)
        calls.append((method, path, retained))
        assert not {"Authorization", "Cookie", "Proxy-Authorization"} & retained.keys()
        if method == "HEAD":
            return _response(
                status=200,
                headers={
                    "strict-transport-security": ("max-age=31536000",),
                    "x-content-type-options": ("nosniff",),
                    "content-security-policy": (
                        "default-src 'self'; connect-src 'self'",
                    ),
                },
            )
        if method == "OPTIONS":
            return _response(
                status=204,
                headers={
                    "access-control-allow-origin": (request.origin,),
                    "access-control-allow-credentials": ("true",),
                    "access-control-allow-methods": ("GET, OPTIONS",),
                },
            )
        return _response(
            status=101,
            headers={
                "upgrade": ("websocket",),
                "connection": ("keep-alive, Upgrade",),
                "sec-websocket-accept": (observer_module._accept_value(),),
                "sec-websocket-protocol": ("live-voice.media.v1",),
            },
        )

    monkeypatch.setattr(
        observer_module,
        "_resolve_private_address",
        lambda host, port: "10.0.0.10",
    )
    validated = observer_module._validate_request(_request())
    assert validated is not None

    observation = observer_module._StdlibDeploymentRuntimeTransport(
        requester=requester
    ).observe(validated)

    assert observation.failure is None
    assert observation.facts == _complete_facts()
    assert calls == [
        ("HEAD", "/app", {}),
        (
            "OPTIONS",
            "/ws/live-voice/media",
            {
                "Origin": "https://voice.example.test",
                "Access-Control-Request-Method": "GET",
            },
        ),
        (
            "GET",
            "/ws/live-voice/media",
            {
                "Origin": "https://voice.example.test",
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Protocol": "live-voice.media.v1",
            },
        ),
    ]


def test_supported_tls_versions_may_vary_across_the_three_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            _response(
                status=200,
                tls=DeploymentRuntimeTlsVersion.TLS_1_2,
                headers={
                    "strict-transport-security": ("max-age=31536000",),
                    "x-content-type-options": ("nosniff",),
                    "content-security-policy": ("connect-src 'self'",),
                },
            ),
            _response(
                status=204,
                headers={
                    "access-control-allow-origin": ("https://voice.example.test",),
                    "access-control-allow-credentials": ("true",),
                    "access-control-allow-methods": ("GET",),
                },
            ),
            _response(
                status=101,
                tls=DeploymentRuntimeTlsVersion.TLS_1_2,
                headers={
                    "upgrade": ("websocket",),
                    "connection": ("Upgrade",),
                    "sec-websocket-accept": (observer_module._accept_value(),),
                    "sec-websocket-protocol": ("live-voice.media.v1",),
                },
            ),
        )
    )
    monkeypatch.setattr(
        observer_module,
        "_resolve_private_address",
        lambda host, port: "10.0.0.10",
    )
    validated = observer_module._validate_request(_request())
    assert validated is not None
    observation = observer_module._StdlibDeploymentRuntimeTransport(
        requester=lambda *args: next(responses)
    ).observe(validated)

    assert observation.facts.tls_verified is True
    assert observation.facts.tls_version is DeploymentRuntimeTlsVersion.MIXED_SUPPORTED


def test_public_dns_answer_fails_before_any_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        observer_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                observer_module.socket.AF_INET,
                observer_module.socket.SOCK_STREAM,
                6,
                "",
                ("8.8.8.8", 443),
            )
        ],
    )
    called = False

    def requester(*args: object, **kwargs: object) -> observer_module._SafeHttpResponse:
        nonlocal called
        called = True
        raise AssertionError((args, kwargs))

    validated = observer_module._validate_request(_request())
    assert validated is not None
    observation = observer_module._StdlibDeploymentRuntimeTransport(
        requester=requester  # type: ignore[arg-type]
    ).observe(validated)

    assert observation.failure is observer_module._TransportFailure.TARGET_NOT_PRIVATE
    assert observation.facts.request_count == 0
    assert called is False


def test_private_dns_answer_is_pinned_for_the_declared_candidate_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        observer_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                observer_module.socket.AF_INET,
                observer_module.socket.SOCK_STREAM,
                6,
                "",
                ("10.20.30.40", 443),
            )
        ],
    )

    assert (
        observer_module._resolve_private_address("voice.example.test", 443)
        == "10.20.30.40"
    )


@pytest.mark.parametrize("address", ("224.0.0.1", "ff0e::1"))
def test_multicast_dns_answer_is_not_a_private_deployment_target(
    monkeypatch: pytest.MonkeyPatch,
    address: str,
) -> None:
    family = (
        observer_module.socket.AF_INET6
        if ":" in address
        else observer_module.socket.AF_INET
    )
    monkeypatch.setattr(
        observer_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (family, observer_module.socket.SOCK_STREAM, 6, "", (address, 443))
        ],
    )

    validated = observer_module._validate_request(_request())
    assert validated is not None
    observation = observer_module._StdlibDeploymentRuntimeTransport().observe(validated)

    assert observation.failure is observer_module._TransportFailure.TARGET_NOT_PRIVATE
    assert observation.facts.request_count == 0


@pytest.mark.parametrize(
    ("failure_method", "expected_count"),
    (("HEAD", 1), ("OPTIONS", 2), ("GET", 3)),
)
def test_request_count_includes_the_failed_bounded_attempt(
    monkeypatch: pytest.MonkeyPatch,
    failure_method: str,
    expected_count: int,
) -> None:
    def requester(
        request: observer_module._ValidatedRequest,
        address: str,
        method: str,
        path: str,
        headers: Mapping[str, str],
    ) -> observer_module._SafeHttpResponse:
        del address, path, headers
        if method == failure_method:
            raise OSError("content-free transport failure")
        if method == "HEAD":
            return _response(
                status=200,
                headers={
                    "strict-transport-security": ("max-age=10",),
                    "x-content-type-options": ("nosniff",),
                    "content-security-policy": ("connect-src 'self'",),
                },
            )
        return _response(
            status=204,
            headers={
                "access-control-allow-origin": (request.origin,),
                "access-control-allow-credentials": ("true",),
                "access-control-allow-methods": ("GET",),
            },
        )

    monkeypatch.setattr(
        observer_module,
        "_resolve_private_address",
        lambda host, port: "10.0.0.10",
    )
    validated = observer_module._validate_request(_request())
    assert validated is not None
    observation = observer_module._StdlibDeploymentRuntimeTransport(
        requester=requester
    ).observe(validated)

    assert observation.facts.request_count == expected_count


def test_csp_requires_every_policy_to_allow_exact_websocket_without_broad_source() -> (
    None
):
    request = observer_module._validate_request(_request())
    assert request is not None
    valid, allowed = observer_module._csp_status(
        {
            "content-security-policy": (
                "default-src 'self'; connect-src 'self'",
                "connect-src wss://voice.example.test/ws/live-voice/media",
            )
        },
        origin=request.origin,
        websocket_url=request.websocket_url,
        websocket_path=request.websocket_path,
    )
    assert (valid, allowed) == (True, True)

    for value in (
        "connect-src *",
        "connect-src wss:",
        "default-src 'none'",
        "connect-src 'self'; connect-src 'self'",
        "script-src 'self'",
    ):
        valid, allowed = observer_module._csp_status(
            {"content-security-policy": (value,)},
            origin=request.origin,
            websocket_url=request.websocket_url,
            websocket_path=request.websocket_path,
        )
        assert allowed is False, value


def test_low_level_request_never_reads_body_and_discards_unapproved_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = "PRIVATE-SET-COOKIE"

    class _Socket:
        def version(self) -> str:
            return "TLSv1.3"

    class _Response:
        status = 200

        def getheaders(self) -> list[tuple[str, str]]:
            return [
                ("Strict-Transport-Security", "max-age=10"),
                ("Set-Cookie", sentinel),
            ]

        def read(self, *args: object) -> bytes:
            raise AssertionError(args)

        def close(self) -> None:
            captured["response_closed"] = True

    class _Connection:
        sock = _Socket()

        def request(
            self,
            method: str,
            path: str,
            body: object,
            headers: dict[str, str],
        ) -> None:
            captured.update(method=method, path=path, body=body, headers=headers)

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            captured["connection_closed"] = True

    def connection_factory(**kwargs: object) -> _Connection:
        captured["connection_kwargs"] = kwargs
        return _Connection()

    context = object()
    monkeypatch.setattr(observer_module, "_PinnedHTTPSConnection", connection_factory)
    monkeypatch.setattr(observer_module, "_tls_context", lambda: context)
    request = observer_module._validate_request(_request())
    assert request is not None

    response = observer_module._perform_request(
        request,
        "10.0.0.10",
        "HEAD",
        "/app",
        {},
    )

    assert response.headers == {"strict-transport-security": ("max-age=10",)}
    assert sentinel not in repr(response)
    assert captured["body"] is None
    assert captured["headers"] == {}
    assert captured["response_closed"] is True
    assert captured["connection_closed"] is True
    kwargs = captured["connection_kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["context"] is context


def test_low_level_request_closes_connection_when_response_close_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = False

    class _Socket:
        def version(self) -> str:
            return "TLSv1.3"

    class _Response:
        status = 200

        def getheaders(self) -> list[tuple[str, str]]:
            return []

        def close(self) -> None:
            raise OSError("content-free close failure")

    class _Connection:
        sock = _Socket()

        def request(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr(
        observer_module,
        "_PinnedHTTPSConnection",
        lambda **kwargs: _Connection(),
    )
    request = observer_module._validate_request(_request())
    assert request is not None

    with pytest.raises(OSError, match="content-free close failure"):
        observer_module._perform_request(request, "10.0.0.10", "HEAD", "/app", {})

    assert closed is True


def test_tls_context_ignores_keylog_environment_and_requires_verified_tls12(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SSLKEYLOGFILE", "PRIVATE-KEYLOG-PATH")

    context = observer_module._tls_context()

    assert context.check_hostname is True
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.minimum_version is ssl.TLSVersion.TLSv1_2
    assert context.keylog_filename is None


def test_results_and_facts_are_closed_and_immutable() -> None:
    facts = _complete_facts()
    result = LiveVoiceDeploymentObservationResult(
        runtime_checks_satisfied=False,
        reason_codes=(DeploymentRuntimeReason.INJECTED_TRANSPORT_UNTRUSTED,),
        facts=facts,
        real_runtime_observed=False,
    )

    with pytest.raises(FrozenInstanceError):
        result.real_runtime_observed = True  # type: ignore[misc]
    with pytest.raises(ValueError):
        DeploymentRuntimeFacts(
            request_count=4,
        )
    with pytest.raises(ValueError):
        DeploymentRuntimeFacts(
            tls_verified=True,
            tls_version=DeploymentRuntimeTlsVersion.UNKNOWN,
        )
    with pytest.raises(ValueError):
        LiveVoiceDeploymentObservationResult(
            runtime_checks_satisfied=True,
            reason_codes=(DeploymentRuntimeReason.RUNTIME_CHECKS_SATISFIED,),
            facts=facts,
            real_runtime_observed=False,
        )
    with pytest.raises(ValueError):
        LiveVoiceDeploymentObservationResult(
            runtime_checks_satisfied=True,
            reason_codes=(DeploymentRuntimeReason.RUNTIME_CHECKS_SATISFIED,),
            facts=DeploymentRuntimeFacts(),
            real_runtime_observed=True,
        )
    with pytest.raises(ValueError):
        LiveVoiceDeploymentObservationResult(
            runtime_checks_satisfied=False,
            reason_codes=(
                DeploymentRuntimeReason.RUNTIME_CHECKS_SATISFIED,
                DeploymentRuntimeReason.HSTS_MISSING_OR_INVALID,
            ),
            facts=facts,
            real_runtime_observed=True,
        )
