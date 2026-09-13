# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from copy import copy
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContextRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.batch_speech import SpeechAuthorizationBinding
from jiuwenswarm.server.live_voice.p3_confirmation import VerifiedP3Confirmation
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityConfirmationBinding,
    AuthorityConfirmationRequest,
    AuthorityDecision,
    AuthorityDecisionReason,
    AuthorityDecisionStatus,
    AuthorityResourceBinding,
    AuthorityRouteContext,
    AuthorityRoutingClaim,
    P2AuthorityAdapter,
    P3AuthorityAdapter,
    ProductAuthorityInputError,
    ProductAuthorityRequest,
    ProductAuthorityService,
    ProductAuthorityUnavailable,
    SpeechAuthorityResolverAdapter,
    TrustedAuthorityCandidate,
    TrustedAuthorityLookup,
)


NOW = datetime(2030, 1, 1, tzinfo=UTC)
ACTIVE_EXPIRY = "2030-01-02T00:00:00Z"
SHORT_EXPIRY = "2030-01-01T12:00:00Z"
EXPIRED = "2029-12-31T23:59:59Z"
SCOPE = ScopeRef(
    "principal-1",
    "project-1",
    "session-1",
    Assurance.AUTHENTICATED,
)
RESOURCE = AuthorityResourceBinding(
    "agent.context",
    "context-1",
    hashlib.sha256(b"context-1").hexdigest(),
)


class RecordingResolver:
    def __init__(
        self,
        candidates: Sequence[TrustedAuthorityCandidate],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.candidates = candidates
        self.failure = failure
        self.calls: list[TrustedAuthorityLookup] = []

    def resolve(
        self, lookup: TrustedAuthorityLookup
    ) -> Sequence[TrustedAuthorityCandidate]:
        self.calls.append(lookup)
        if self.failure is not None:
            raise self.failure
        return self.candidates


class ExplodingSingleSequence(Sequence[TrustedAuthorityCandidate]):
    def __len__(self) -> int:
        return 1

    def __getitem__(self, index):
        raise RuntimeError("resolver-index-secret")


def _route(
    *,
    claimed_user_id: str | None = "principal-1",
    claimed_project_id: str | None = "project-1",
    claimed_scope: ScopeRef | None = SCOPE,
    claimed_context_ref: ContextRef | None = None,
    correlation_id: str = "correlation-1",
    routing_claims: tuple[AuthorityRoutingClaim, ...] = (),
) -> AuthorityRouteContext:
    return AuthorityRouteContext(
        session_id="session-1",
        correlation_id=correlation_id,
        claimed_user_id=claimed_user_id,
        claimed_project_id=claimed_project_id,
        claimed_scope=claimed_scope,
        claimed_context_ref=claimed_context_ref,
        routing_claims=routing_claims,
    )


def _candidate(
    *,
    operation: str = "agent.chat",
    capabilities: frozenset[str] = frozenset({"agent.chat", "agent.context.read"}),
    resource: AuthorityResourceBinding | None = RESOURCE,
    confirmation: AuthorityConfirmationBinding | None = None,
    expires_at: str = ACTIVE_EXPIRY,
    scope: ScopeRef = SCOPE,
    principal_id: str = "principal-1",
    session_id: str = "session-1",
    project_id: str | None = "project-1",
    assurance: Assurance = Assurance.AUTHENTICATED,
    correlation_id: str = "correlation-1",
) -> TrustedAuthorityCandidate:
    return TrustedAuthorityCandidate(
        principal_id=principal_id,
        session_id=session_id,
        project_id=project_id,
        scope=scope,
        allowed_operations=frozenset({operation}),
        allowed_capabilities=capabilities,
        expires_at=expires_at,
        assurance=assurance,
        source="server.auth.session",
        correlation_id=correlation_id,
        resource=resource,
        confirmation=confirmation,
    )


def _request(
    *,
    route: AuthorityRouteContext | None = None,
    operation: str = "agent.chat",
    capabilities: frozenset[str] = frozenset({"agent.chat"}),
    resource: AuthorityResourceBinding | None = RESOURCE,
    confirmation: AuthorityConfirmationRequest | None = None,
) -> ProductAuthorityRequest:
    return ProductAuthorityRequest(
        route=route or _route(),
        operation=operation,
        required_capabilities=capabilities,
        resource=resource,
        confirmation=confirmation,
    )


def _service(
    resolver: RecordingResolver | None,
    *,
    enabled: bool = True,
) -> ProductAuthorityService:
    return ProductAuthorityService(
        enabled=enabled,
        resolver=resolver,
        clock=lambda: NOW,
    )


def _context_ref(
    *,
    scope: ScopeRef = SCOPE,
    expires_at: str | None = ACTIVE_EXPIRY,
    redacted: bool = False,
) -> ContextRef:
    return ContextRef.from_dict(
        {
            "source": "server.project",
            "stable_id": "context-1",
            "uri": "file:///workspace/project",
            "revision": {"kind": "version", "value": "revision-1"},
            "scope": scope.to_dict(),
            "permissions": ["agent.context.read"],
            "expires_at": expires_at,
            "redaction": {
                "policy_id": "live_voice.context.v1",
                "redacted": redacted,
                "fields": ["content"] if redacted else [],
            },
            "extensions": {},
        }
    )


def _attempt_downstream(decision, calls: list[str]) -> None:
    if decision.status is AuthorityDecisionStatus.AUTHORIZED:
        calls.append("downstream")


def test_positive_resolution_is_server_owned_narrowed_and_safely_presented() -> None:
    secrets = ("Bearer raw-secret", "query-secret", "client-secret")
    claims = (
        AuthorityRoutingClaim("header", "Authorization", secrets[0]),
        AuthorityRoutingClaim("query", "user_id", secrets[1]),
        AuthorityRoutingClaim("client_metadata", "token", secrets[2]),
    )
    resolver = RecordingResolver([_candidate()])

    decision = _service(resolver).resolve(_request(route=_route(routing_claims=claims)))

    assert decision.status is AuthorityDecisionStatus.AUTHORIZED
    assert decision.reason is AuthorityDecisionReason.AUTHORIZED
    assert decision.authority is not None
    assert decision.authority.principal_id == "principal-1"
    assert decision.authority.session_id == "session-1"
    assert decision.authority.project_id == "project-1"
    assert decision.authority.scope == SCOPE
    assert decision.authority.operation == "agent.chat"
    assert decision.authority.capabilities == frozenset({"agent.chat"})
    assert decision.authority.expires_at == ACTIVE_EXPIRY
    assert decision.authority.assurance is Assurance.AUTHENTICATED
    assert decision.authority.source == "server.auth.session"
    assert decision.authority.correlation_id == "correlation-1"
    assert decision.authority.resource == RESOURCE
    assert 1 <= len(decision.evidence_ids) <= 16
    lookup = resolver.calls[0]
    assert lookup == TrustedAuthorityLookup(
        session_id="session-1",
        correlation_id="correlation-1",
        operation="agent.chat",
        required_capabilities=frozenset({"agent.chat"}),
        resource_kind="agent.context",
        resource_id="context-1",
    )
    assert not hasattr(lookup, "claimed_user_id")
    assert not hasattr(lookup, "routing_claims")
    rendered = repr(decision) + json.dumps(decision.to_presentable_dict())
    for secret in secrets:
        assert secret not in rendered
    assert "[redacted]" in rendered
    assert isinstance(decision.to_presentable_dict()["evidence_ids"], tuple)


@pytest.mark.parametrize(
    ("service_factory", "expected_status", "expected_reason", "resolver_calls"),
    [
        (
            lambda resolver: _service(resolver, enabled=False),
            AuthorityDecisionStatus.UNAVAILABLE,
            AuthorityDecisionReason.FEATURE_DISABLED,
            0,
        ),
        (
            lambda _resolver: _service(None),
            AuthorityDecisionStatus.UNAVAILABLE,
            AuthorityDecisionReason.RESOLVER_UNAVAILABLE,
            0,
        ),
        (
            lambda resolver: _service(resolver),
            AuthorityDecisionStatus.DENIED,
            AuthorityDecisionReason.AUTHORITY_ABSENT,
            1,
        ),
    ],
)
def test_feature_missing_and_absent_authority_fail_before_downstream(
    service_factory,
    expected_status: AuthorityDecisionStatus,
    expected_reason: AuthorityDecisionReason,
    resolver_calls: int,
) -> None:
    resolver = RecordingResolver([])
    downstream: list[str] = []

    decision = service_factory(resolver).resolve(_request())
    _attempt_downstream(decision, downstream)

    assert decision.status is expected_status
    assert decision.reason is expected_reason
    assert decision.authority is None
    assert len(resolver.calls) == resolver_calls
    assert downstream == []


def test_ambiguous_and_failed_resolver_fail_closed_without_downstream() -> None:
    ambiguous = RecordingResolver([_candidate(), _candidate()])
    failure_secret = "resolver-token-must-not-leak"
    failed = RecordingResolver([], failure=RuntimeError(failure_secret))
    downstream: list[str] = []

    ambiguous_decision = _service(ambiguous).resolve(_request())
    failed_decision = _service(failed).resolve(_request())
    _attempt_downstream(ambiguous_decision, downstream)
    _attempt_downstream(failed_decision, downstream)

    assert ambiguous_decision.reason is AuthorityDecisionReason.AUTHORITY_AMBIGUOUS
    assert ambiguous_decision.status is AuthorityDecisionStatus.DENIED
    assert failed_decision.reason is AuthorityDecisionReason.RESOLVER_FAILURE
    assert failed_decision.status is AuthorityDecisionStatus.UNAVAILABLE
    assert failure_secret not in repr(failed_decision)
    assert downstream == []


def test_candidate_index_failure_is_unavailable_and_safe() -> None:
    resolver = RecordingResolver(ExplodingSingleSequence())

    decision = _service(resolver).resolve(_request())

    assert decision.status is AuthorityDecisionStatus.UNAVAILABLE
    assert decision.reason is AuthorityDecisionReason.RESOLVER_FAILURE
    assert decision.authority is None
    assert "resolver-index-secret" not in repr(decision)


def test_clock_dependency_failure_is_unavailable_safe_and_has_no_downstream() -> None:
    resolver = RecordingResolver([_candidate()])
    clock_secret = "clock-runtime-secret"
    downstream: list[str] = []

    def exploding_clock() -> datetime:
        raise RuntimeError(clock_secret)

    decision = ProductAuthorityService(
        enabled=True,
        resolver=resolver,
        clock=exploding_clock,
    ).resolve(_request())
    _attempt_downstream(decision, downstream)

    assert decision.status is AuthorityDecisionStatus.UNAVAILABLE
    assert decision.reason is AuthorityDecisionReason.RESOLVER_FAILURE
    assert decision.authority is None
    assert decision.evidence_ids == (
        "authority.feature.enabled",
        "authority.resolver.available",
        "authority.candidate.unique",
        "authority.clock.failed",
    )
    assert len(resolver.calls) == 1
    assert downstream == []
    rendered = repr(decision) + json.dumps(decision.to_presentable_dict())
    assert clock_secret not in rendered


def test_decision_rejects_unapproved_evidence_and_inconsistent_status() -> None:
    with pytest.raises(ProductAuthorityInputError):
        AuthorityDecision(
            AuthorityDecisionStatus.DENIED,
            AuthorityDecisionReason.AUTHORITY_ABSENT,
            None,
            ("provider.production.ready",),
        )
    with pytest.raises(ProductAuthorityInputError):
        AuthorityDecision(
            AuthorityDecisionStatus.DENIED,
            AuthorityDecisionReason.AUTHORIZED,
            None,
            ("authority.candidate.absent",),
        )


@pytest.mark.parametrize(
    ("candidate", "authority_request", "reason"),
    [
        (
            _candidate(),
            _request(route=_route(claimed_user_id="principal-other")),
            AuthorityDecisionReason.PRINCIPAL_MISMATCH,
        ),
        (
            _candidate(
                scope=ScopeRef(
                    "principal-1",
                    "project-1",
                    "session-other",
                    Assurance.AUTHENTICATED,
                )
            ),
            _request(),
            AuthorityDecisionReason.SESSION_MISMATCH,
        ),
        (
            _candidate(),
            _request(route=_route(claimed_project_id="project-other")),
            AuthorityDecisionReason.PROJECT_MISMATCH,
        ),
        (
            _candidate(),
            _request(
                route=_route(
                    claimed_scope=ScopeRef(
                        "principal-1",
                        "project-other",
                        "session-1",
                        Assurance.AUTHENTICATED,
                    )
                )
            ),
            AuthorityDecisionReason.SCOPE_MISMATCH,
        ),
        (
            _candidate(operation="agent.status"),
            _request(),
            AuthorityDecisionReason.OPERATION_DENIED,
        ),
        (
            _candidate(capabilities=frozenset({"agent.context.read"})),
            _request(),
            AuthorityDecisionReason.CAPABILITY_DENIED,
        ),
        (
            _candidate(correlation_id="correlation-other"),
            _request(),
            AuthorityDecisionReason.CORRELATION_MISMATCH,
        ),
        (
            _candidate(
                resource=AuthorityResourceBinding(
                    "agent.context",
                    "context-other",
                    hashlib.sha256(b"context-other").hexdigest(),
                )
            ),
            _request(),
            AuthorityDecisionReason.RESOURCE_BINDING_MISMATCH,
        ),
        (
            _candidate(expires_at=EXPIRED),
            _request(),
            AuthorityDecisionReason.AUTHORITY_EXPIRED,
        ),
        (
            _candidate(assurance=Assurance.REQUEST_ASSERTED),
            _request(),
            AuthorityDecisionReason.PRINCIPAL_MISMATCH,
        ),
    ],
)
def test_exact_principal_scope_project_operation_capability_and_expiry_are_required(
    candidate: TrustedAuthorityCandidate,
    authority_request: ProductAuthorityRequest,
    reason: AuthorityDecisionReason,
) -> None:
    resolver = RecordingResolver([candidate])
    downstream: list[str] = []

    decision = _service(resolver).resolve(authority_request)
    _attempt_downstream(decision, downstream)

    assert decision.status is AuthorityDecisionStatus.DENIED
    assert decision.reason is reason
    assert decision.authority is None
    assert len(resolver.calls) == 1
    assert downstream == []


@pytest.mark.parametrize(
    ("context", "reason"),
    [
        (
            _context_ref(
                scope=ScopeRef(
                    "principal-1",
                    "project-other",
                    "session-1",
                    Assurance.AUTHENTICATED,
                )
            ),
            AuthorityDecisionReason.SCOPE_MISMATCH,
        ),
        (_context_ref(expires_at=EXPIRED), AuthorityDecisionReason.AUTHORITY_EXPIRED),
        (_context_ref(redacted=True), AuthorityDecisionReason.SCOPE_MISMATCH),
    ],
)
def test_client_context_ref_never_grants_and_unsafe_context_fails_closed(
    context: ContextRef, reason: AuthorityDecisionReason
) -> None:
    resolver = RecordingResolver([_candidate()])

    decision = _service(resolver).resolve(
        _request(route=_route(claimed_context_ref=context))
    )

    assert decision.status is AuthorityDecisionStatus.DENIED
    assert decision.reason is reason
    assert decision.authority is None


def _confirmation(
    *,
    confirmation_id: str = "confirmation-1",
    operation: str = "task.cancel",
    command_id: str = "command-1",
    target_id: str | None = "task-1",
    intent_sha256: str | None = None,
    expires_at: str = SHORT_EXPIRY,
) -> AuthorityConfirmationBinding:
    return AuthorityConfirmationBinding(
        confirmation_id=confirmation_id,
        operation=operation,
        command_id=command_id,
        target_id=target_id,
        intent_sha256=intent_sha256 or hashlib.sha256(b"intent-1").hexdigest(),
        expires_at=expires_at,
        source="server.confirmation.ledger",
    )


def _confirmation_request(
    *,
    confirmation_id: str = "confirmation-1",
    command_id: str = "command-1",
    target_id: str | None = "task-1",
    intent_sha256: str | None = None,
) -> AuthorityConfirmationRequest:
    return AuthorityConfirmationRequest(
        confirmation_id=confirmation_id,
        command_id=command_id,
        target_id=target_id,
        intent_sha256=intent_sha256 or hashlib.sha256(b"intent-1").hexdigest(),
    )


@pytest.mark.parametrize(
    ("resolved", "requested", "reason"),
    [
        (
            None,
            _confirmation_request(),
            AuthorityDecisionReason.CONFIRMATION_REQUIRED,
        ),
        (
            _confirmation(confirmation_id="confirmation-other"),
            _confirmation_request(),
            AuthorityDecisionReason.CONFIRMATION_MISMATCH,
        ),
        (
            _confirmation(expires_at=EXPIRED),
            _confirmation_request(),
            AuthorityDecisionReason.CONFIRMATION_EXPIRED,
        ),
    ],
)
def test_confirmation_is_exact_server_owned_and_active(
    resolved: AuthorityConfirmationBinding | None,
    requested: AuthorityConfirmationRequest,
    reason: AuthorityDecisionReason,
) -> None:
    task_resource = _task_resource("task-1")
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.cancel",
                capabilities=frozenset({"task.cancel"}),
                resource=task_resource,
                confirmation=resolved,
            )
        ]
    )

    decision = _service(resolver).resolve(
        _request(
            operation="task.cancel",
            capabilities=frozenset({"task.cancel"}),
            resource=task_resource,
            confirmation=requested,
        )
    )

    assert decision.status is AuthorityDecisionStatus.DENIED
    assert decision.reason is reason
    assert decision.authority is None


def test_confirmation_narrows_authority_expiry_and_is_redacted() -> None:
    task_resource = _task_resource("task-1")
    confirmation = _confirmation()
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.cancel",
                capabilities=frozenset({"task.cancel"}),
                resource=task_resource,
                confirmation=confirmation,
            )
        ]
    )

    decision = _service(resolver).resolve(
        _request(
            operation="task.cancel",
            capabilities=frozenset({"task.cancel"}),
            resource=task_resource,
            confirmation=_confirmation_request(),
        )
    )

    assert decision.status is AuthorityDecisionStatus.AUTHORIZED
    assert decision.authority is not None
    assert decision.authority.expires_at == SHORT_EXPIRY
    rendered = repr(decision)
    assert "confirmation-1" not in rendered
    assert hashlib.sha256(b"intent-1").hexdigest() not in rendered


def _speech_binding(
    *,
    content_sha256: str | None = None,
) -> SpeechAuthorizationBinding:
    return SpeechAuthorizationBinding(
        subject_id="principal-1",
        scope=SCOPE,
        operation="speech.recognize.batch",
        operation_id="speech-operation-1",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=1,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256=content_sha256 or hashlib.sha256(b"speech").hexdigest(),
    )


def _speech_candidate(binding: SpeechAuthorizationBinding) -> TrustedAuthorityCandidate:
    return _candidate(
        operation=binding.operation,
        capabilities=frozenset({binding.operation}),
        resource=AuthorityResourceBinding(
            "speech.authorization",
            binding.operation_id,
            binding.content_sha256,
        ),
    )


def test_speech_adapter_returns_identical_binding_only_when_authorized() -> None:
    binding = _speech_binding()
    resolver = RecordingResolver([_speech_candidate(binding)])
    adapter = SpeechAuthorityResolverAdapter(_service(resolver))

    authorized = adapter.authorize(binding)

    assert authorized is binding
    assert len(resolver.calls) == 1


def test_speech_denial_has_zero_provider_effect_and_unavailable_is_safe() -> None:
    binding = _speech_binding()
    denied_resolver = RecordingResolver(
        [
            _candidate(
                operation=binding.operation,
                capabilities=frozenset(),
                resource=AuthorityResourceBinding(
                    "speech.authorization",
                    binding.operation_id,
                    binding.content_sha256,
                ),
            )
        ]
    )
    provider_calls: list[str] = []
    denied_adapter = SpeechAuthorityResolverAdapter(_service(denied_resolver))

    if denied_adapter.authorize(binding) is not None:
        provider_calls.append("provider")

    assert provider_calls == []
    unavailable_adapter = SpeechAuthorityResolverAdapter(_service(None))
    with pytest.raises(ProductAuthorityUnavailable) as caught:
        unavailable_adapter.authorize(binding)
    assert str(caught.value) == "product authority is unavailable"
    assert binding.content_sha256 not in str(caught.value)


def test_p2_context_carries_authority_without_allocating_runtime() -> None:
    resolver = RecordingResolver([_candidate()])
    adapter = P2AuthorityAdapter(_service(resolver))
    allocations: list[str] = []

    context = adapter.bind(_route(), resource=RESOURCE)
    if context is not None:
        allocations.append("caller-owned-after-authority")

    assert context is not None
    assert context.scope == SCOPE
    assert context.authority.scope == SCOPE
    assert context.authority.principal_id == "principal-1"
    assert context.authority.session_id == "session-1"
    assert context.authority.project_id == "project-1"
    assert context.authority.correlation_id == "correlation-1"
    assert allocations == ["caller-owned-after-authority"]


def test_p2_denial_occurs_before_caller_runtime_allocation() -> None:
    resolver = RecordingResolver([])
    adapter = P2AuthorityAdapter(_service(resolver))
    allocations: list[str] = []

    context = adapter.bind(_route(), resource=RESOURCE)
    if context is not None:
        allocations.append("runtime")

    assert context is None
    assert allocations == []


def _task_resource(task_id: str) -> AuthorityResourceBinding:
    return AuthorityResourceBinding(
        "task", task_id, hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    )


def _tamper_p3_authority(context, authority):
    tampered = copy(context)
    object.__setattr__(tampered, "authority", authority)
    return tampered


def _tamper_authority(authority, field_name: str, value):
    tampered = copy(authority)
    object.__setattr__(tampered, field_name, value)
    return tampered


def test_p3_query_needs_no_confirmation_and_emits_existing_grant() -> None:
    resource = _task_resource("task-1")
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.get",
                capabilities=frozenset({"task.get"}),
                resource=resource,
            )
        ]
    )
    adapter = P3AuthorityAdapter(_service(resolver))

    context = adapter.resolve(
        _route(),
        operation="task.get",
        required_capabilities=frozenset({"task.get"}),
        target_task_id="task-1",
    )
    assert context is not None
    assert context.confirmation_binding is None
    grant = adapter.to_task_grant(context, None)

    assert grant is not None
    grant.authorize(
        scope=SCOPE,
        operation="task.get",
        command_id=None,
        target_task_id="task-1",
        required_capabilities=frozenset({"task.get"}),
        destructive=False,
        now="2030-01-01T00:00:00Z",
    )


def test_p3_query_rejects_confirmation_claim_before_resolver() -> None:
    resolver = RecordingResolver([])
    adapter = P3AuthorityAdapter(_service(resolver))

    context = adapter.resolve(
        _route(),
        operation="task.get",
        required_capabilities=frozenset({"task.get"}),
        target_task_id="task-1",
        confirmation_id="confirmation-forged",
    )

    assert context is None
    assert resolver.calls == []


def test_p3_invalid_operation_fails_before_resolver() -> None:
    resolver = RecordingResolver([])
    adapter = P3AuthorityAdapter(_service(resolver))

    assert (
        adapter.resolve(
            _route(),
            operation=[],  # type: ignore[arg-type]
            required_capabilities=frozenset({"task.get"}),
        )
        is None
    )
    assert (
        adapter.resolve(
            _route(),
            operation="task.delete",
            required_capabilities=frozenset({"task.delete"}),
        )
        is None
    )
    assert (
        adapter.resolve(
            _route(),
            operation="task.get",
            required_capabilities=frozenset({"task.list"}),
            target_task_id="task-1",
        )
        is None
    )
    assert (
        adapter.resolve(
            _route(),
            operation="task.get",
            required_capabilities=frozenset({"task.get"}),
        )
        is None
    )
    assert (
        adapter.resolve(
            _route(),
            operation="task.create",
            required_capabilities=frozenset({"task.create"}),
            target_task_id="task-1",
            command_id="command-1",
            intent_sha256=hashlib.sha256(b"intent-1").hexdigest(),
            confirmation_id="confirmation-1",
        )
        is None
    )
    assert resolver.calls == []


def test_p3_create_binds_confirmation_and_context_resource_without_consuming_it() -> (
    None
):
    intent = hashlib.sha256(b"intent-1").hexdigest()
    confirmation = _confirmation(
        operation="task.create",
        target_id=None,
        intent_sha256=intent,
    )
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.create",
                capabilities=frozenset({"task.create"}),
                resource=RESOURCE,
                confirmation=confirmation,
            )
        ]
    )
    adapter = P3AuthorityAdapter(_service(resolver))

    context = adapter.resolve(
        _route(),
        operation="task.create",
        required_capabilities=frozenset({"task.create"}),
        command_id="command-1",
        intent_sha256=intent,
        confirmation_id="confirmation-1",
        resource=RESOURCE,
    )

    assert context is not None
    assert context.target_task_id is None
    assert context.authority.resource == RESOURCE
    assert context.confirmation_binding is not None
    assert context.confirmation_binding.target_task_id is None
    rendered = repr(context)
    assert RESOURCE.fingerprint_sha256 not in rendered
    assert "[redacted]" in rendered
    verified = VerifiedP3Confirmation("confirmation-1", SHORT_EXPIRY, False)
    grant = adapter.to_task_grant(context, verified)
    assert grant is not None
    grant.authorize(
        scope=SCOPE,
        operation="task.create",
        command_id="command-1",
        target_task_id=None,
        required_capabilities=frozenset({"task.create"}),
        destructive=True,
        now="2030-01-01T00:00:00Z",
    )
    replacement = replace(
        context.authority,
        resource=AuthorityResourceBinding(
            "agent.context",
            "context-other",
            hashlib.sha256(b"context-other").hexdigest(),
        ),
    )
    dropped = replace(context.authority, resource=None)
    with pytest.raises(ProductAuthorityInputError):
        replace(context, authority=replacement)
    with pytest.raises(ProductAuthorityInputError):
        replace(context, authority=dropped)
    assert (
        adapter.to_task_grant(_tamper_p3_authority(context, replacement), verified)
        is None
    )
    assert (
        adapter.to_task_grant(_tamper_p3_authority(context, dropped), verified) is None
    )


def test_p3_mutation_keeps_durable_verifier_and_checks_exact_verified_binding() -> None:
    intent = hashlib.sha256(b"intent-1").hexdigest()
    confirmation = _confirmation(intent_sha256=intent)
    resource = _task_resource("task-1")
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.cancel",
                capabilities=frozenset({"task.cancel"}),
                resource=resource,
                confirmation=confirmation,
            )
        ]
    )
    adapter = P3AuthorityAdapter(_service(resolver))
    verifier_calls: list[object] = []

    context = adapter.resolve(
        _route(),
        operation="task.cancel",
        required_capabilities=frozenset({"task.cancel"}),
        command_id="command-1",
        target_task_id="task-1",
        intent_sha256=intent,
        confirmation_id="confirmation-1",
    )
    assert context is not None
    assert context.confirmation_binding is not None
    assert verifier_calls == []  # Adapter does not consume the durable confirmation.
    verifier_calls.append(context.confirmation_binding)
    verified = VerifiedP3Confirmation(
        confirmation_id="confirmation-1",
        expires_at=SHORT_EXPIRY,
        replayed=False,
    )
    grant = adapter.to_task_grant(context, verified)

    assert len(verifier_calls) == 1
    assert grant is not None
    grant.authorize(
        scope=SCOPE,
        operation="task.cancel",
        command_id="command-1",
        target_task_id="task-1",
        required_capabilities=frozenset({"task.cancel"}),
        destructive=True,
        now="2030-01-01T00:00:00Z",
    )


@pytest.mark.parametrize(
    "verified",
    [
        None,
        VerifiedP3Confirmation("confirmation-other", SHORT_EXPIRY, False),
        VerifiedP3Confirmation("confirmation-1", ACTIVE_EXPIRY, False),
        VerifiedP3Confirmation("confirmation-1", EXPIRED, False),
    ],
)
def test_p3_mutation_never_grants_from_missing_or_mismatched_verification(
    verified: VerifiedP3Confirmation | None,
) -> None:
    intent = hashlib.sha256(b"intent-1").hexdigest()
    resource = _task_resource("task-1")
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.cancel",
                capabilities=frozenset({"task.cancel"}),
                resource=resource,
                confirmation=_confirmation(intent_sha256=intent),
            )
        ]
    )
    adapter = P3AuthorityAdapter(_service(resolver))
    core_calls: list[str] = []
    context = adapter.resolve(
        _route(),
        operation="task.cancel",
        required_capabilities=frozenset({"task.cancel"}),
        command_id="command-1",
        target_task_id="task-1",
        intent_sha256=intent,
        confirmation_id="confirmation-1",
    )
    assert context is not None

    grant = adapter.to_task_grant(context, verified)
    if grant is not None:
        core_calls.append("core")

    assert grant is None
    assert core_calls == []


def test_p3_task_grant_rechecks_command_target_intent_operation_and_resource() -> None:
    intent = hashlib.sha256(b"intent-1").hexdigest()
    resource = _task_resource("task-1")
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.cancel",
                capabilities=frozenset({"task.cancel"}),
                resource=resource,
                confirmation=_confirmation(intent_sha256=intent),
            )
        ]
    )
    adapter = P3AuthorityAdapter(_service(resolver))
    context = adapter.resolve(
        _route(),
        operation="task.cancel",
        required_capabilities=frozenset({"task.cancel"}),
        command_id="command-1",
        target_task_id="task-1",
        intent_sha256=intent,
        confirmation_id="confirmation-1",
    )
    assert context is not None
    verified = VerifiedP3Confirmation("confirmation-1", SHORT_EXPIRY, False)

    assert (
        adapter.to_task_grant(replace(context, command_id="command-other"), verified)
        is None
    )
    assert (
        adapter.to_task_grant(replace(context, target_task_id="task-other"), verified)
        is None
    )
    assert (
        adapter.to_task_grant(
            replace(context, intent_sha256=hashlib.sha256(b"other").hexdigest()),
            verified,
        )
        is None
    )
    wrong_resource = replace(
        context.authority,
        resource=_task_resource("task-other"),
    )
    assert (
        adapter.to_task_grant(_tamper_p3_authority(context, wrong_resource), verified)
        is None
    )
    wrong_fingerprint = replace(
        context.authority,
        resource=AuthorityResourceBinding(
            "task", "task-1", hashlib.sha256(b"wrong").hexdigest()
        ),
    )
    assert (
        adapter.to_task_grant(
            _tamper_p3_authority(context, wrong_fingerprint), verified
        )
        is None
    )
    expired_authority = replace(
        context.authority,
        expires_at="2020-01-01T00:00:00Z",
    )
    assert (
        adapter.to_task_grant(
            _tamper_p3_authority(context, expired_authority), verified
        )
        is None
    )
    assert context.authority.confirmation is not None
    wrong_confirmation = replace(
        context.authority.confirmation,
        operation="task.create",
    )
    with pytest.raises(ProductAuthorityInputError):
        replace(context.authority, confirmation=wrong_confirmation)
    forged_confirmation_authority = _tamper_authority(
        context.authority,
        "confirmation",
        wrong_confirmation,
    )
    assert (
        adapter.to_task_grant(
            _tamper_p3_authority(context, forged_confirmation_authority), verified
        )
        is None
    )
    with pytest.raises(ProductAuthorityInputError):
        replace(context.authority, expires_at=ACTIVE_EXPIRY)
    widened_expiry_authority = _tamper_authority(
        context.authority,
        "expires_at",
        ACTIVE_EXPIRY,
    )
    assert (
        adapter.to_task_grant(
            _tamper_p3_authority(context, widened_expiry_authority), verified
        )
        is None
    )


def test_raw_routing_and_confirmation_values_never_appear_in_repr_or_errors() -> None:
    secrets = {
        "raw-bearer-secret",
        "raw-query-secret",
        "raw-client-token",
        "confirmation-1",
        hashlib.sha256(b"intent-1").hexdigest(),
    }
    claims = (
        AuthorityRoutingClaim("header", "Authorization", "raw-bearer-secret"),
        AuthorityRoutingClaim("query", "token", "raw-query-secret"),
        AuthorityRoutingClaim("client_metadata", "token", "raw-client-token"),
    )
    task_resource = _task_resource("task-1")
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.cancel",
                capabilities=frozenset({"task.cancel"}),
                resource=task_resource,
                confirmation=_confirmation(),
            )
        ]
    )
    request = _request(
        route=_route(routing_claims=claims),
        operation="task.cancel",
        capabilities=frozenset({"task.cancel"}),
        resource=task_resource,
        confirmation=_confirmation_request(),
    )
    decision = _service(resolver).resolve(request)

    rendered = "\n".join(
        (
            repr(claims),
            repr(request.route),
            repr(request),
            repr(resolver.candidates[0]),
            repr(decision),
            json.dumps(decision.to_presentable_dict()),
        )
    )
    for secret in secrets:
        assert secret not in rendered

    malformed_secret = "raw-token-in-malformed-timestamp"
    with pytest.raises(ProductAuthorityInputError) as caught:
        AuthorityConfirmationBinding(
            confirmation_id="confirmation-safe",
            operation="task.cancel",
            command_id="command-safe",
            target_id="task-safe",
            intent_sha256=hashlib.sha256(b"safe").hexdigest(),
            expires_at=malformed_secret,
            source="server.confirmation.ledger",
        )
    assert malformed_secret not in str(caught.value)
    assert malformed_secret not in repr(caught.value)
    assert caught.value.__cause__ is None


# --- D-069 bounded task.retry authority -------------------------------------


_RETRY_TASK_RESOURCE = AuthorityResourceBinding(
    "task",
    "task-1",
    hashlib.sha256(b"task-1").hexdigest(),
)


def _retry_adapter(intent: str) -> P3AuthorityAdapter:
    resolver = RecordingResolver(
        [
            _candidate(
                operation="task.retry",
                capabilities=frozenset({"task.retry"}),
                resource=_RETRY_TASK_RESOURCE,
                confirmation=_confirmation(
                    operation="task.retry",
                    target_id="task-1",
                    intent_sha256=intent,
                ),
            )
        ]
    )
    return P3AuthorityAdapter(_service(resolver))


def test_p3_retry_is_a_targeted_confirmed_mutation() -> None:
    intent = hashlib.sha256(b"retry-intent").hexdigest()
    adapter = _retry_adapter(intent)

    context = adapter.resolve(
        _route(),
        operation="task.retry",
        required_capabilities=frozenset({"task.retry"}),
        command_id="command-1",
        target_task_id="task-1",
        intent_sha256=intent,
        confirmation_id="confirmation-1",
    )

    assert context is not None
    assert context.target_task_id == "task-1"
    # The task resource binding is derived, not accepted from the caller.
    assert context.authority.resource == _RETRY_TASK_RESOURCE
    assert context.confirmation_binding is not None
    assert context.confirmation_binding.operation == "task.retry"
    assert context.confirmation_binding.target_task_id == "task-1"

    grant = adapter.to_task_grant(
        context, VerifiedP3Confirmation("confirmation-1", SHORT_EXPIRY, False)
    )
    assert grant is not None
    assert grant.operation == "task.retry"
    assert grant.target_task_id == "task-1"
    assert grant.confirmed is True
    grant.authorize(
        scope=SCOPE,
        operation="task.retry",
        command_id="command-1",
        target_task_id="task-1",
        required_capabilities=frozenset({"task.retry"}),
        destructive=True,
        now="2030-01-01T00:00:00Z",
    )


def test_p3_retry_requires_target_command_intent_and_confirmation() -> None:
    intent = hashlib.sha256(b"retry-intent").hexdigest()

    # A retry without its exact target task never resolves.
    assert (
        _retry_adapter(intent).resolve(
            _route(),
            operation="task.retry",
            required_capabilities=frozenset({"task.retry"}),
            command_id="command-1",
            target_task_id=None,
            intent_sha256=intent,
            confirmation_id="confirmation-1",
        )
        is None
    )
    # A retry is destructive, so an unconfirmed request never resolves either.
    for omitted in ("command_id", "intent_sha256", "confirmation_id"):
        arguments: dict[str, object] = {
            "command_id": "command-1",
            "intent_sha256": intent,
            "confirmation_id": "confirmation-1",
        }
        arguments[omitted] = None
        assert (
            _retry_adapter(intent).resolve(
                _route(),
                operation="task.retry",
                required_capabilities=frozenset({"task.retry"}),
                target_task_id="task-1",
                **arguments,  # type: ignore[arg-type]
            )
            is None
        ), omitted
    # A forged task resource can never replace the derived binding.
    assert (
        _retry_adapter(intent).resolve(
            _route(),
            operation="task.retry",
            required_capabilities=frozenset({"task.retry"}),
            command_id="command-1",
            target_task_id="task-1",
            intent_sha256=intent,
            confirmation_id="confirmation-1",
            resource=AuthorityResourceBinding(
                "task", "task-other", hashlib.sha256(b"task-other").hexdigest()
            ),
        )
        is None
    )


def test_p3_retry_never_grants_without_the_exact_verified_confirmation() -> None:
    intent = hashlib.sha256(b"retry-intent").hexdigest()
    adapter = _retry_adapter(intent)
    context = adapter.resolve(
        _route(),
        operation="task.retry",
        required_capabilities=frozenset({"task.retry"}),
        command_id="command-1",
        target_task_id="task-1",
        intent_sha256=intent,
        confirmation_id="confirmation-1",
    )
    assert context is not None

    assert adapter.to_task_grant(context, None) is None
    assert (
        adapter.to_task_grant(
            context, VerifiedP3Confirmation("confirmation-other", SHORT_EXPIRY, False)
        )
        is None
    )
    assert (
        adapter.to_task_grant(
            context, VerifiedP3Confirmation("confirmation-1", ACTIVE_EXPIRY, False)
        )
        is None
    )
    assert (
        adapter.to_task_grant(
            context, VerifiedP3Confirmation("confirmation-1", EXPIRED, False)
        )
        is None
    )
