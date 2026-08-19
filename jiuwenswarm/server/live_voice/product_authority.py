# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Server-owned authority foundation for formal Live Voice composition.

Caller-provided identity, scope, ContextRef, header, query, and client metadata
are routing or consistency claims only.  The injected ``TrustedAuthorityResolver``
is the sole grant source.  This module owns no authentication transport, token
store, timer, queue, service, Agent, Provider, Task, or confirmation ledger.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContextRef,
    ScopeRef,
)

from .formal_task_models import TaskAuthorizationGrant
from .p3_confirmation import P3ConfirmationBinding, VerifiedP3Confirmation

if TYPE_CHECKING:
    from .batch_speech import SpeechAuthorizationBinding


_MAX_ID_LENGTH = 256
_MAX_SOURCE_LENGTH = 128
_MAX_EVIDENCE_IDS = 16
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ROUTING_CLAIM_SOURCES = frozenset({"header", "query", "client_metadata"})
_P3_OPERATIONS = frozenset(
    {
        "task.create",
        "task.adjust",
        "task.get",
        "task.list",
        "task.status",
        "task.cancel",
        "task.retry",
        "task.events",
        "task.result",
    }
)
_P3_MUTATIONS = frozenset({"task.create", "task.adjust", "task.cancel", "task.retry"})
_P3_TARGETED_OPERATIONS = frozenset(
    {
        "task.get",
        "task.status",
        "task.adjust",
        "task.cancel",
        "task.retry",
        "task.events",
        "task.result",
    }
)
_P3_TASK_RESOURCE_KIND = "task"
_EVIDENCE_IDS = frozenset(
    {
        "authority.request.invalid",
        "authority.feature.disabled",
        "authority.feature.enabled",
        "authority.resolver.missing",
        "authority.resolver.failed",
        "authority.resolver.available",
        "authority.clock.failed",
        "authority.candidate.absent",
        "authority.candidate.ambiguous",
        "authority.candidate.invalid",
        "authority.candidate.unique",
        "authority.assurance.not_authenticated",
        "authority.assurance.authenticated",
        "authority.principal.mismatch",
        "authority.session.mismatch",
        "authority.project.mismatch",
        "authority.route_session.mismatch",
        "authority.route_principal.mismatch",
        "authority.route_project.mismatch",
        "authority.route_scope.mismatch",
        "authority.context.mismatch",
        "authority.context.expired",
        "authority.scope.exact",
        "authority.candidate.expired",
        "authority.expiry.active",
        "authority.operation.denied",
        "authority.operation.allowed",
        "authority.capability.denied",
        "authority.capability.allowed",
        "authority.correlation.mismatch",
        "authority.correlation.exact",
        "authority.resource.mismatch",
        "authority.resource.exact",
        "authority.confirmation.unrequested",
        "authority.confirmation.missing",
        "authority.confirmation.mismatch",
        "authority.confirmation.expired",
        "authority.confirmation.exact",
        "authority.confirmation.not_required",
    }
)


class AuthorityDecisionStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    UNAVAILABLE = "UNAVAILABLE"


class AuthorityDecisionReason(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    RESOLVER_UNAVAILABLE = "RESOLVER_UNAVAILABLE"
    AUTHORITY_ABSENT = "AUTHORITY_ABSENT"
    AUTHORITY_AMBIGUOUS = "AUTHORITY_AMBIGUOUS"
    AUTHORITY_EXPIRED = "AUTHORITY_EXPIRED"
    PRINCIPAL_MISMATCH = "PRINCIPAL_MISMATCH"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    PROJECT_MISMATCH = "PROJECT_MISMATCH"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    OPERATION_DENIED = "OPERATION_DENIED"
    CAPABILITY_DENIED = "CAPABILITY_DENIED"
    CORRELATION_MISMATCH = "CORRELATION_MISMATCH"
    RESOURCE_BINDING_MISMATCH = "RESOURCE_BINDING_MISMATCH"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFIRMATION_MISMATCH = "CONFIRMATION_MISMATCH"
    CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED"
    RESOLVER_FAILURE = "RESOLVER_FAILURE"


class ProductAuthorityInputError(ValueError):
    """Safe construction failure for malformed authority contract values."""


class ProductAuthorityUnavailable(RuntimeError):
    """Constant safe Adapter error for an unavailable authority source."""

    def __init__(self, reason: AuthorityDecisionReason) -> None:
        super().__init__("product authority is unavailable")
        self.reason = reason


def _input_error(field_name: str) -> ProductAuthorityInputError:
    return ProductAuthorityInputError(f"invalid product authority field: {field_name}")


def _require_text(
    value: object, field_name: str, *, maximum: int = _MAX_ID_LENGTH
) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise _input_error(field_name)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _input_error(field_name) from None
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _require_sha256(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _input_error(field_name)
    return value


def _require_source(value: object, field_name: str) -> str:
    value = _require_text(value, field_name, maximum=_MAX_SOURCE_LENGTH)
    if _SOURCE_RE.fullmatch(value) is None:
        raise _input_error(field_name)
    return value


def _parse_utc(value: object, field_name: str) -> datetime:
    value = _require_text(value, field_name, maximum=64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _input_error(field_name) from None
    if parsed.tzinfo is None:
        raise _input_error(field_name)
    return parsed.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_now(clock: Callable[[], datetime]) -> datetime:
    now = clock()
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ProductAuthorityInputError("authority clock must return aware datetime")
    return now.astimezone(UTC)


def _require_string_set(value: object, field_name: str) -> frozenset[str]:
    if type(value) is not frozenset:
        raise _input_error(field_name)
    for item in value:
        _require_text(item, field_name)
    return value


def _normalize_scope(value: object, field_name: str) -> ScopeRef:
    if not isinstance(value, ScopeRef):
        raise _input_error(field_name)
    try:
        return ScopeRef.from_dict(value.to_dict())
    except Exception:  # closed contract; never surface parser text
        raise _input_error(field_name) from None


def _normalize_context_ref(value: object, field_name: str) -> ContextRef:
    if not isinstance(value, ContextRef):
        raise _input_error(field_name)
    try:
        return ContextRef.from_dict(value.to_dict())
    except Exception:  # closed contract; never surface parser text
        raise _input_error(field_name) from None


@dataclass(frozen=True, slots=True, repr=False)
class AuthorityRoutingClaim:
    source: str
    name: str
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.source not in _ROUTING_CLAIM_SOURCES:
            raise _input_error("routing_claim.source")
        _require_text(self.name, "routing_claim.name")
        _require_text(self.value, "routing_claim.value", maximum=4096)

    def __repr__(self) -> str:
        return f"AuthorityRoutingClaim(source={self.source!r}, value='[redacted]')"


@dataclass(frozen=True, slots=True, repr=False)
class AuthorityRouteContext:
    session_id: str
    correlation_id: str
    claimed_user_id: str | None = None
    claimed_project_id: str | None = None
    claimed_scope: ScopeRef | None = None
    claimed_context_ref: ContextRef | None = None
    routing_claims: tuple[AuthorityRoutingClaim, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.session_id, "route.session_id")
        _require_text(self.correlation_id, "route.correlation_id")
        _optional_text(self.claimed_user_id, "route.claimed_user_id")
        _optional_text(self.claimed_project_id, "route.claimed_project_id")
        if self.claimed_scope is not None:
            _normalize_scope(self.claimed_scope, "route.claimed_scope")
        if self.claimed_context_ref is not None:
            _normalize_context_ref(
                self.claimed_context_ref, "route.claimed_context_ref"
            )
        if type(self.routing_claims) is not tuple or any(
            not isinstance(item, AuthorityRoutingClaim) for item in self.routing_claims
        ):
            raise _input_error("route.routing_claims")

    def __repr__(self) -> str:
        return (
            "AuthorityRouteContext("
            f"session_id={self.session_id!r}, correlation_id={self.correlation_id!r}, "
            f"routing_claim_count={len(self.routing_claims)})"
        )


@dataclass(frozen=True, slots=True)
class AuthorityResourceBinding:
    kind: str
    resource_id: str
    fingerprint_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_source(self.kind, "resource.kind")
        _require_text(self.resource_id, "resource.resource_id")
        _require_sha256(self.fingerprint_sha256, "resource.fingerprint_sha256")

    def __repr__(self) -> str:
        return (
            "AuthorityResourceBinding("
            f"kind={self.kind!r}, resource_id={self.resource_id!r}, "
            "fingerprint_sha256='[redacted]')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class AuthorityConfirmationRequest:
    confirmation_id: str
    command_id: str
    target_id: str | None
    intent_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_text(self.confirmation_id, "confirmation_request.confirmation_id")
        _require_text(self.command_id, "confirmation_request.command_id")
        _optional_text(self.target_id, "confirmation_request.target_id")
        _require_sha256(self.intent_sha256, "confirmation_request.intent_sha256")

    def __repr__(self) -> str:
        return "AuthorityConfirmationRequest(confirmation_id='[redacted]')"


@dataclass(frozen=True, slots=True, repr=False)
class ProductAuthorityRequest:
    route: AuthorityRouteContext
    operation: str
    required_capabilities: frozenset[str]
    resource: AuthorityResourceBinding | None = None
    confirmation: AuthorityConfirmationRequest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.route, AuthorityRouteContext):
            raise _input_error("request.route")
        _require_text(self.operation, "request.operation")
        _require_string_set(self.required_capabilities, "request.required_capabilities")
        if self.resource is not None and not isinstance(
            self.resource, AuthorityResourceBinding
        ):
            raise _input_error("request.resource")
        if self.confirmation is not None and not isinstance(
            self.confirmation, AuthorityConfirmationRequest
        ):
            raise _input_error("request.confirmation")

    def __repr__(self) -> str:
        return (
            "ProductAuthorityRequest("
            f"operation={self.operation!r}, session_id={self.route.session_id!r})"
        )


@dataclass(frozen=True, slots=True)
class TrustedAuthorityLookup:
    """Only non-grant routing keys visible to the trusted resolver."""

    session_id: str
    correlation_id: str
    operation: str
    required_capabilities: frozenset[str]
    resource_kind: str | None
    resource_id: str | None

    def __post_init__(self) -> None:
        _require_text(self.session_id, "lookup.session_id")
        _require_text(self.correlation_id, "lookup.correlation_id")
        _require_text(self.operation, "lookup.operation")
        _require_string_set(self.required_capabilities, "lookup.required_capabilities")
        if (self.resource_kind is None) != (self.resource_id is None):
            raise _input_error("lookup.resource")
        if self.resource_kind is not None:
            _require_source(self.resource_kind, "lookup.resource_kind")
            _require_text(self.resource_id, "lookup.resource_id")


@dataclass(frozen=True, slots=True, repr=False)
class AuthorityConfirmationBinding:
    confirmation_id: str
    operation: str
    command_id: str
    target_id: str | None
    intent_sha256: str = field(repr=False)
    expires_at: str
    source: str

    def __post_init__(self) -> None:
        _require_text(self.confirmation_id, "confirmation.confirmation_id")
        _require_text(self.operation, "confirmation.operation")
        _require_text(self.command_id, "confirmation.command_id")
        _optional_text(self.target_id, "confirmation.target_id")
        _require_sha256(self.intent_sha256, "confirmation.intent_sha256")
        _parse_utc(self.expires_at, "confirmation.expires_at")
        _require_source(self.source, "confirmation.source")

    def __repr__(self) -> str:
        return (
            "AuthorityConfirmationBinding(confirmation_id='[redacted]', "
            f"operation={self.operation!r}, expires_at={self.expires_at!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class TrustedAuthorityCandidate:
    """One server-owned candidate.  It is not a grant until service validation."""

    principal_id: str
    session_id: str
    project_id: str | None
    scope: ScopeRef
    allowed_operations: frozenset[str]
    allowed_capabilities: frozenset[str]
    expires_at: str
    assurance: Assurance
    source: str
    correlation_id: str
    resource: AuthorityResourceBinding | None = None
    confirmation: AuthorityConfirmationBinding | None = None

    def __post_init__(self) -> None:
        _require_text(self.principal_id, "candidate.principal_id")
        _require_text(self.session_id, "candidate.session_id")
        _optional_text(self.project_id, "candidate.project_id")
        _normalize_scope(self.scope, "candidate.scope")
        _require_string_set(self.allowed_operations, "candidate.allowed_operations")
        _require_string_set(self.allowed_capabilities, "candidate.allowed_capabilities")
        _parse_utc(self.expires_at, "candidate.expires_at")
        if not isinstance(self.assurance, Assurance):
            raise _input_error("candidate.assurance")
        _require_source(self.source, "candidate.source")
        _require_text(self.correlation_id, "candidate.correlation_id")
        if self.resource is not None and not isinstance(
            self.resource, AuthorityResourceBinding
        ):
            raise _input_error("candidate.resource")
        if self.confirmation is not None and not isinstance(
            self.confirmation, AuthorityConfirmationBinding
        ):
            raise _input_error("candidate.confirmation")

    def __repr__(self) -> str:
        return (
            "TrustedAuthorityCandidate("
            f"principal_id={self.principal_id!r}, session_id={self.session_id!r}, "
            f"source={self.source!r})"
        )


class TrustedAuthorityResolver(Protocol):
    def resolve(
        self, lookup: TrustedAuthorityLookup
    ) -> Sequence[TrustedAuthorityCandidate]: ...


@dataclass(frozen=True, slots=True, repr=False)
class ResolvedProductAuthority:
    """The single canonical immutable grant consumed by every Adapter."""

    principal_id: str
    session_id: str
    project_id: str | None
    scope: ScopeRef
    operation: str
    capabilities: frozenset[str]
    expires_at: str
    assurance: Assurance
    source: str
    correlation_id: str
    resource: AuthorityResourceBinding | None = None
    confirmation: AuthorityConfirmationBinding | None = None

    def __post_init__(self) -> None:
        _require_text(self.principal_id, "authority.principal_id")
        _require_text(self.session_id, "authority.session_id")
        _optional_text(self.project_id, "authority.project_id")
        scope = _normalize_scope(self.scope, "authority.scope")
        _require_text(self.operation, "authority.operation")
        _require_string_set(self.capabilities, "authority.capabilities")
        authority_expiry = _parse_utc(self.expires_at, "authority.expires_at")
        if self.assurance is not Assurance.AUTHENTICATED:
            raise _input_error("authority.assurance")
        _require_source(self.source, "authority.source")
        _require_text(self.correlation_id, "authority.correlation_id")
        if (
            scope.assurance is not Assurance.AUTHENTICATED
            or scope.subject_id != self.principal_id
            or scope.session_id != self.session_id
            or scope.project_id != self.project_id
        ):
            raise _input_error("authority.scope")
        if self.resource is not None and not isinstance(
            self.resource, AuthorityResourceBinding
        ):
            raise _input_error("authority.resource")
        if self.confirmation is not None and not isinstance(
            self.confirmation, AuthorityConfirmationBinding
        ):
            raise _input_error("authority.confirmation")
        if self.confirmation is not None and (
            self.confirmation.operation != self.operation
            or authority_expiry
            > _parse_utc(
                self.confirmation.expires_at, "authority.confirmation.expires_at"
            )
        ):
            raise _input_error("authority.confirmation")

    def to_presentable_dict(self) -> dict[str, object]:
        return {
            "principal_id": self.principal_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "scope": self.scope.to_dict(),
            "operation": self.operation,
            "capabilities": tuple(sorted(self.capabilities)),
            "expires_at": self.expires_at,
            "assurance": self.assurance.value,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "resource": (
                None
                if self.resource is None
                else {
                    "kind": self.resource.kind,
                    "resource_id": self.resource.resource_id,
                    "fingerprint_sha256": "[redacted]",
                }
            ),
            "confirmation": (
                None
                if self.confirmation is None
                else {
                    "bound": True,
                    "confirmation_id": "[redacted]",
                    "operation": self.confirmation.operation,
                    "command_id": "[redacted]",
                    "target_id": self.confirmation.target_id,
                    "intent_sha256": "[redacted]",
                    "expires_at": self.confirmation.expires_at,
                    "source": self.confirmation.source,
                }
            ),
        }

    def __repr__(self) -> str:
        return f"ResolvedProductAuthority({self.to_presentable_dict()!r})"


@dataclass(frozen=True, slots=True, repr=False)
class AuthorityDecision:
    status: AuthorityDecisionStatus
    reason: AuthorityDecisionReason
    authority: ResolvedProductAuthority | None
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, AuthorityDecisionStatus):
            raise _input_error("decision.status")
        if not isinstance(self.reason, AuthorityDecisionReason):
            raise _input_error("decision.reason")
        if (self.status is AuthorityDecisionStatus.AUTHORIZED) != (
            self.authority is not None
        ):
            raise _input_error("decision.authority")
        if (self.status is AuthorityDecisionStatus.AUTHORIZED) != (
            self.reason is AuthorityDecisionReason.AUTHORIZED
        ):
            raise _input_error("decision.reason")
        unavailable_reasons = {
            AuthorityDecisionReason.FEATURE_DISABLED,
            AuthorityDecisionReason.RESOLVER_UNAVAILABLE,
            AuthorityDecisionReason.RESOLVER_FAILURE,
        }
        if (self.status is AuthorityDecisionStatus.UNAVAILABLE) != (
            self.reason in unavailable_reasons
        ):
            raise _input_error("decision.reason")
        if self.status is AuthorityDecisionStatus.AUTHORIZED and not isinstance(
            self.authority, ResolvedProductAuthority
        ):
            raise _input_error("decision.authority")
        if (
            type(self.evidence_ids) is not tuple
            or not self.evidence_ids
            or len(self.evidence_ids) > _MAX_EVIDENCE_IDS
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
        ):
            raise _input_error("decision.evidence_ids")
        for evidence_id in self.evidence_ids:
            _require_source(evidence_id, "decision.evidence_ids")
            if evidence_id not in _EVIDENCE_IDS:
                raise _input_error("decision.evidence_ids")

    def to_presentable_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "reason": self.reason.value,
            "evidence_ids": self.evidence_ids,
            "authority": (
                None if self.authority is None else self.authority.to_presentable_dict()
            ),
        }

    def __repr__(self) -> str:
        return f"AuthorityDecision({self.to_presentable_dict()!r})"


def _decision(
    status: AuthorityDecisionStatus,
    reason: AuthorityDecisionReason,
    evidence_ids: tuple[str, ...],
    authority: ResolvedProductAuthority | None = None,
) -> AuthorityDecision:
    return AuthorityDecision(status, reason, authority, evidence_ids)


class ProductAuthorityService:
    """Validate one resolver candidate and narrow it to one exact invocation."""

    def __init__(
        self,
        *,
        enabled: bool,
        resolver: TrustedAuthorityResolver | None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if type(enabled) is not bool:
            raise _input_error("service.enabled")
        if not callable(clock):
            raise _input_error("service.clock")
        self._enabled = enabled
        self._resolver = resolver
        self._clock = clock

    def resolve(self, request: ProductAuthorityRequest) -> AuthorityDecision:
        if not self._enabled:
            return _decision(
                AuthorityDecisionStatus.UNAVAILABLE,
                AuthorityDecisionReason.FEATURE_DISABLED,
                ("authority.feature.disabled",),
            )
        resolver = self._resolver
        if resolver is None:
            return _decision(
                AuthorityDecisionStatus.UNAVAILABLE,
                AuthorityDecisionReason.RESOLVER_UNAVAILABLE,
                ("authority.feature.enabled", "authority.resolver.missing"),
            )
        if not isinstance(request, ProductAuthorityRequest):
            return _decision(
                AuthorityDecisionStatus.DENIED,
                AuthorityDecisionReason.AUTHORITY_ABSENT,
                ("authority.request.invalid",),
            )
        resource = request.resource
        lookup = TrustedAuthorityLookup(
            session_id=request.route.session_id,
            correlation_id=request.route.correlation_id,
            operation=request.operation,
            required_capabilities=request.required_capabilities,
            resource_kind=None if resource is None else resource.kind,
            resource_id=None if resource is None else resource.resource_id,
        )
        try:
            candidates = resolver.resolve(lookup)
            if not isinstance(candidates, Sequence) or isinstance(
                candidates, (str, bytes, bytearray)
            ):
                raise ProductAuthorityInputError("resolver returned invalid candidates")
            candidate_count = len(candidates)
            candidate = candidates[0] if candidate_count == 1 else None
        except Exception:  # trusted dependency failure is safe and non-semantic
            return _decision(
                AuthorityDecisionStatus.UNAVAILABLE,
                AuthorityDecisionReason.RESOLVER_FAILURE,
                ("authority.feature.enabled", "authority.resolver.failed"),
            )
        if candidate_count == 0:
            return _decision(
                AuthorityDecisionStatus.DENIED,
                AuthorityDecisionReason.AUTHORITY_ABSENT,
                (
                    "authority.feature.enabled",
                    "authority.resolver.available",
                    "authority.candidate.absent",
                ),
            )
        if candidate_count != 1:
            return _decision(
                AuthorityDecisionStatus.DENIED,
                AuthorityDecisionReason.AUTHORITY_AMBIGUOUS,
                (
                    "authority.feature.enabled",
                    "authority.resolver.available",
                    "authority.candidate.ambiguous",
                ),
            )
        if not isinstance(candidate, TrustedAuthorityCandidate):
            return _decision(
                AuthorityDecisionStatus.UNAVAILABLE,
                AuthorityDecisionReason.RESOLVER_FAILURE,
                (
                    "authority.feature.enabled",
                    "authority.resolver.available",
                    "authority.candidate.invalid",
                ),
            )
        try:
            now = _normalize_now(self._clock)
        except Exception:  # trusted dependency failure must not expose clock text
            return _decision(
                AuthorityDecisionStatus.UNAVAILABLE,
                AuthorityDecisionReason.RESOLVER_FAILURE,
                (
                    "authority.feature.enabled",
                    "authority.resolver.available",
                    "authority.candidate.unique",
                    "authority.clock.failed",
                ),
            )
        try:
            return self._resolve_candidate(request, candidate, now)
        except ProductAuthorityInputError:
            return _decision(
                AuthorityDecisionStatus.UNAVAILABLE,
                AuthorityDecisionReason.RESOLVER_FAILURE,
                (
                    "authority.feature.enabled",
                    "authority.resolver.available",
                    "authority.candidate.invalid",
                ),
            )

    @staticmethod
    def _deny(reason: AuthorityDecisionReason, *evidence_ids: str) -> AuthorityDecision:
        return _decision(
            AuthorityDecisionStatus.DENIED,
            reason,
            ("authority.candidate.unique", *evidence_ids),
        )

    @classmethod
    def _resolve_candidate(
        cls,
        request: ProductAuthorityRequest,
        candidate: TrustedAuthorityCandidate,
        now: datetime,
    ) -> AuthorityDecision:
        scope = _normalize_scope(candidate.scope, "candidate.scope")
        if (
            candidate.assurance is not Assurance.AUTHENTICATED
            or scope.assurance is not Assurance.AUTHENTICATED
        ):
            return cls._deny(
                AuthorityDecisionReason.PRINCIPAL_MISMATCH,
                "authority.assurance.not_authenticated",
            )
        if scope.subject_id != candidate.principal_id:
            return cls._deny(
                AuthorityDecisionReason.PRINCIPAL_MISMATCH,
                "authority.principal.mismatch",
            )
        if scope.session_id != candidate.session_id:
            return cls._deny(
                AuthorityDecisionReason.SESSION_MISMATCH,
                "authority.session.mismatch",
            )
        if scope.project_id != candidate.project_id:
            return cls._deny(
                AuthorityDecisionReason.PROJECT_MISMATCH,
                "authority.project.mismatch",
            )
        route = request.route
        if route.session_id != candidate.session_id:
            return cls._deny(
                AuthorityDecisionReason.SESSION_MISMATCH,
                "authority.route_session.mismatch",
            )
        if (
            route.claimed_user_id is not None
            and route.claimed_user_id != candidate.principal_id
        ):
            return cls._deny(
                AuthorityDecisionReason.PRINCIPAL_MISMATCH,
                "authority.route_principal.mismatch",
            )
        if (
            route.claimed_project_id is not None
            and route.claimed_project_id != candidate.project_id
        ):
            return cls._deny(
                AuthorityDecisionReason.PROJECT_MISMATCH,
                "authority.route_project.mismatch",
            )
        if (
            route.claimed_scope is not None
            and _normalize_scope(route.claimed_scope, "route.claimed_scope") != scope
        ):
            return cls._deny(
                AuthorityDecisionReason.SCOPE_MISMATCH,
                "authority.route_scope.mismatch",
            )
        claimed_context = route.claimed_context_ref
        if claimed_context is not None:
            context = _normalize_context_ref(
                claimed_context, "route.claimed_context_ref"
            )
            if context.scope != scope or context.redaction.redacted:
                return cls._deny(
                    AuthorityDecisionReason.SCOPE_MISMATCH,
                    "authority.context.mismatch",
                )
            if (
                context.expires_at is not None
                and _parse_utc(context.expires_at, "route.context.expires_at") <= now
            ):
                return cls._deny(
                    AuthorityDecisionReason.AUTHORITY_EXPIRED,
                    "authority.context.expired",
                )
        if _parse_utc(candidate.expires_at, "candidate.expires_at") <= now:
            return cls._deny(
                AuthorityDecisionReason.AUTHORITY_EXPIRED,
                "authority.candidate.expired",
            )
        if request.operation not in candidate.allowed_operations:
            return cls._deny(
                AuthorityDecisionReason.OPERATION_DENIED,
                "authority.operation.denied",
            )
        if not request.required_capabilities.issubset(candidate.allowed_capabilities):
            return cls._deny(
                AuthorityDecisionReason.CAPABILITY_DENIED,
                "authority.capability.denied",
            )
        if request.route.correlation_id != candidate.correlation_id:
            return cls._deny(
                AuthorityDecisionReason.CORRELATION_MISMATCH,
                "authority.correlation.mismatch",
            )
        if request.resource != candidate.resource:
            return cls._deny(
                AuthorityDecisionReason.RESOURCE_BINDING_MISMATCH,
                "authority.resource.mismatch",
            )
        confirmation = cls._validate_confirmation(request, candidate, now)
        if isinstance(confirmation, AuthorityDecision):
            return confirmation
        expires_at = candidate.expires_at
        if confirmation is not None and _parse_utc(
            confirmation.expires_at, "confirmation.expires_at"
        ) < _parse_utc(expires_at, "candidate.expires_at"):
            expires_at = confirmation.expires_at
        authority = ResolvedProductAuthority(
            principal_id=candidate.principal_id,
            session_id=candidate.session_id,
            project_id=candidate.project_id,
            scope=scope,
            operation=request.operation,
            capabilities=request.required_capabilities,
            expires_at=expires_at,
            assurance=Assurance.AUTHENTICATED,
            source=candidate.source,
            correlation_id=candidate.correlation_id,
            resource=request.resource,
            confirmation=confirmation,
        )
        evidence = [
            "authority.candidate.unique",
            "authority.assurance.authenticated",
            "authority.scope.exact",
            "authority.expiry.active",
            "authority.operation.allowed",
            "authority.capability.allowed",
            "authority.correlation.exact",
            "authority.resource.exact",
        ]
        evidence.append(
            "authority.confirmation.exact"
            if confirmation is not None
            else "authority.confirmation.not_required"
        )
        return _decision(
            AuthorityDecisionStatus.AUTHORIZED,
            AuthorityDecisionReason.AUTHORIZED,
            tuple(evidence),
            authority,
        )

    @classmethod
    def _validate_confirmation(
        cls,
        request: ProductAuthorityRequest,
        candidate: TrustedAuthorityCandidate,
        now: datetime,
    ) -> AuthorityConfirmationBinding | AuthorityDecision | None:
        requested = request.confirmation
        resolved = candidate.confirmation
        if requested is None:
            if resolved is not None:
                return cls._deny(
                    AuthorityDecisionReason.CONFIRMATION_MISMATCH,
                    "authority.confirmation.unrequested",
                )
            return None
        if resolved is None:
            return cls._deny(
                AuthorityDecisionReason.CONFIRMATION_REQUIRED,
                "authority.confirmation.missing",
            )
        if (
            resolved.confirmation_id != requested.confirmation_id
            or resolved.operation != request.operation
            or resolved.command_id != requested.command_id
            or resolved.target_id != requested.target_id
            or resolved.intent_sha256 != requested.intent_sha256
        ):
            return cls._deny(
                AuthorityDecisionReason.CONFIRMATION_MISMATCH,
                "authority.confirmation.mismatch",
            )
        if _parse_utc(resolved.expires_at, "confirmation.expires_at") <= now:
            return cls._deny(
                AuthorityDecisionReason.CONFIRMATION_EXPIRED,
                "authority.confirmation.expired",
            )
        return resolved


def _authorized_or_none(
    decision: AuthorityDecision,
) -> ResolvedProductAuthority | None:
    if decision.status is AuthorityDecisionStatus.UNAVAILABLE:
        raise ProductAuthorityUnavailable(decision.reason)
    if decision.status is AuthorityDecisionStatus.DENIED:
        return None
    assert decision.authority is not None
    return decision.authority


class SpeechAuthorityResolverAdapter:
    """Implement the existing Speech resolver without accepting browser grants."""

    def __init__(self, service: ProductAuthorityService) -> None:
        if not isinstance(service, ProductAuthorityService):
            raise _input_error("speech_adapter.service")
        self._service = service

    def authorize(
        self, binding: SpeechAuthorizationBinding
    ) -> SpeechAuthorizationBinding | None:
        try:
            scope = _normalize_scope(binding.scope, "speech.scope")
            operation = _require_text(binding.operation, "speech.operation")
            resource = AuthorityResourceBinding(
                kind="speech.authorization",
                resource_id=_require_text(binding.operation_id, "speech.operation_id"),
                fingerprint_sha256=_require_sha256(
                    binding.content_sha256, "speech.content_sha256"
                ),
            )
            route = AuthorityRouteContext(
                session_id=_require_text(scope.session_id, "speech.session_id"),
                correlation_id=_require_text(
                    binding.correlation_id, "speech.correlation_id"
                ),
                claimed_user_id=_require_text(binding.subject_id, "speech.subject_id"),
                claimed_project_id=scope.project_id,
                claimed_scope=scope,
            )
            request = ProductAuthorityRequest(
                route=route,
                operation=operation,
                required_capabilities=frozenset({operation}),
                resource=resource,
            )
        except (AttributeError, ProductAuthorityInputError, TypeError):
            return None
        authority = _authorized_or_none(self._service.resolve(request))
        if authority is None:
            return None
        return binding


@dataclass(frozen=True, slots=True, repr=False)
class P2AuthenticatedContext:
    authority: ResolvedProductAuthority
    scope: ScopeRef

    def __post_init__(self) -> None:
        if not isinstance(self.authority, ResolvedProductAuthority):
            raise _input_error("p2_context.authority")
        scope = _normalize_scope(self.scope, "p2_context.scope")
        if scope != self.authority.scope:
            raise _input_error("p2_context.scope")

    def __repr__(self) -> str:
        return (
            "P2AuthenticatedContext("
            f"authority={self.authority.to_presentable_dict()!r})"
        )


class P2AuthorityAdapter:
    """Resolve only the authority/context needed before P2 owner allocation."""

    def __init__(self, service: ProductAuthorityService) -> None:
        if not isinstance(service, ProductAuthorityService):
            raise _input_error("p2_adapter.service")
        self._service = service

    def bind(
        self,
        route: AuthorityRouteContext,
        *,
        operation: str = "agent.chat",
        required_capabilities: frozenset[str] = frozenset({"agent.chat"}),
        resource: AuthorityResourceBinding | None = None,
    ) -> P2AuthenticatedContext | None:
        try:
            request = ProductAuthorityRequest(
                route=route,
                operation=operation,
                required_capabilities=required_capabilities,
                resource=resource,
            )
        except ProductAuthorityInputError:
            return None
        authority = _authorized_or_none(self._service.resolve(request))
        if authority is None:
            return None
        return P2AuthenticatedContext(authority=authority, scope=authority.scope)


@dataclass(frozen=True, slots=True, repr=False)
class P3AuthorityContext:
    authority: ResolvedProductAuthority
    resource: AuthorityResourceBinding | None = field(repr=False)
    command_id: str | None
    target_task_id: str | None
    intent_sha256: str | None = field(repr=False)
    confirmation_id: str | None = field(repr=False)
    confirmation_binding: P3ConfirmationBinding | None = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.authority, ResolvedProductAuthority):
            raise _input_error("p3_context.authority")
        if self.resource is not None and not isinstance(
            self.resource, AuthorityResourceBinding
        ):
            raise _input_error("p3_context.resource")
        if self.resource != self.authority.resource:
            raise _input_error("p3_context.resource")
        _optional_text(self.command_id, "p3_context.command_id")
        _optional_text(self.target_task_id, "p3_context.target_task_id")
        if self.intent_sha256 is not None:
            _require_sha256(self.intent_sha256, "p3_context.intent_sha256")
        _optional_text(self.confirmation_id, "p3_context.confirmation_id")
        if self.confirmation_binding is not None and not isinstance(
            self.confirmation_binding, P3ConfirmationBinding
        ):
            raise _input_error("p3_context.confirmation_binding")

    def __repr__(self) -> str:
        return (
            "P3AuthorityContext("
            f"authority={self.authority.to_presentable_dict()!r}, "
            f"confirmation_bound={self.confirmation_binding is not None})"
        )


class P3AuthorityAdapter:
    """Bridge canonical authority to existing P3 grant/confirmation owners."""

    def __init__(self, service: ProductAuthorityService) -> None:
        if not isinstance(service, ProductAuthorityService):
            raise _input_error("p3_adapter.service")
        self._service = service

    def resolve(
        self,
        route: AuthorityRouteContext,
        *,
        operation: str,
        required_capabilities: frozenset[str],
        command_id: str | None = None,
        target_task_id: str | None = None,
        intent_sha256: str | None = None,
        confirmation_id: str | None = None,
        resource: AuthorityResourceBinding | None = None,
    ) -> P3AuthorityContext | None:
        try:
            operation = _require_text(operation, "p3.operation")
            if operation not in _P3_OPERATIONS:
                return None
            if required_capabilities != frozenset({operation}):
                return None
            mutation = operation in _P3_MUTATIONS
            if mutation:
                command_id = _require_text(command_id, "p3.command_id")
                intent_sha256 = _require_sha256(intent_sha256, "p3.intent_sha256")
                confirmation_id = _require_text(confirmation_id, "p3.confirmation_id")
                if operation in _P3_TARGETED_OPERATIONS:
                    target_task_id = _require_text(target_task_id, "p3.target_task_id")
            elif any(
                item is not None
                for item in (command_id, intent_sha256, confirmation_id)
            ):
                return None
            target_task_id = _optional_text(target_task_id, "p3.target_task_id")
            if (operation in _P3_TARGETED_OPERATIONS) != (target_task_id is not None):
                return None
            if target_task_id is not None:
                expected_resource = AuthorityResourceBinding(
                    kind=_P3_TASK_RESOURCE_KIND,
                    resource_id=target_task_id,
                    fingerprint_sha256=hashlib.sha256(
                        target_task_id.encode("utf-8")
                    ).hexdigest(),
                )
                if resource is None:
                    resource = expected_resource
                elif resource != expected_resource:
                    return None
            confirmation_request = (
                AuthorityConfirmationRequest(
                    confirmation_id=_require_text(
                        confirmation_id, "p3.confirmation_id"
                    ),
                    command_id=_require_text(command_id, "p3.command_id"),
                    target_id=target_task_id,
                    intent_sha256=_require_sha256(intent_sha256, "p3.intent_sha256"),
                )
                if mutation
                else None
            )
            request = ProductAuthorityRequest(
                route=route,
                operation=operation,
                required_capabilities=required_capabilities,
                resource=resource,
                confirmation=confirmation_request,
            )
        except (ProductAuthorityInputError, TypeError):
            return None
        authority = _authorized_or_none(self._service.resolve(request))
        if authority is None:
            return None
        confirmation = authority.confirmation
        confirmation_binding = (
            None
            if confirmation is None
            else P3ConfirmationBinding(
                principal_id=authority.principal_id,
                scope=authority.scope,
                operation=confirmation.operation,
                command_id=confirmation.command_id,
                target_task_id=confirmation.target_id,
                intent_fingerprint=confirmation.intent_sha256,
            )
        )
        return P3AuthorityContext(
            authority=authority,
            resource=authority.resource,
            command_id=command_id,
            target_task_id=target_task_id,
            intent_sha256=intent_sha256,
            confirmation_id=confirmation_id,
            confirmation_binding=confirmation_binding,
        )

    @staticmethod
    def to_task_grant(
        context: P3AuthorityContext,
        verified_confirmation: VerifiedP3Confirmation | None,
    ) -> TaskAuthorizationGrant | None:
        if not isinstance(context, P3AuthorityContext):
            return None
        authority = context.authority
        if context.resource != authority.resource:
            return None
        try:
            now = datetime.now(UTC)
            authority_expiry = _parse_utc(authority.expires_at, "authority.expires_at")
            if authority_expiry <= now:
                return None
        except ProductAuthorityInputError:
            return None
        if (
            authority.operation not in _P3_OPERATIONS
            or authority.capabilities != frozenset({authority.operation})
        ):
            return None
        if (authority.operation in _P3_TARGETED_OPERATIONS) != (
            context.target_task_id is not None
        ):
            return None
        if context.target_task_id is not None:
            expected_resource = AuthorityResourceBinding(
                kind=_P3_TASK_RESOURCE_KIND,
                resource_id=context.target_task_id,
                fingerprint_sha256=hashlib.sha256(
                    context.target_task_id.encode("utf-8")
                ).hexdigest(),
            )
            if authority.resource != expected_resource:
                return None
        mutation = authority.operation in _P3_MUTATIONS
        confirmation = authority.confirmation
        binding = context.confirmation_binding
        if mutation:
            if (
                confirmation is None
                or binding is None
                or not isinstance(verified_confirmation, VerifiedP3Confirmation)
                or confirmation.operation != authority.operation
                or verified_confirmation.confirmation_id != confirmation.confirmation_id
                or verified_confirmation.expires_at != confirmation.expires_at
                or context.confirmation_id != confirmation.confirmation_id
                or context.command_id != confirmation.command_id
                or context.target_task_id != confirmation.target_id
                or context.intent_sha256 != confirmation.intent_sha256
                or binding.principal_id != authority.principal_id
                or binding.scope != authority.scope
                or binding.operation != authority.operation
                or binding.command_id != context.command_id
                or binding.target_task_id != context.target_task_id
                or binding.intent_fingerprint != context.intent_sha256
            ):
                return None
            try:
                confirmation_expiry = _parse_utc(
                    verified_confirmation.expires_at, "verified.expires_at"
                )
                if confirmation_expiry <= now or authority_expiry > confirmation_expiry:
                    return None
            except ProductAuthorityInputError:
                return None
            confirmed = True
            grant_confirmation_id = verified_confirmation.confirmation_id
        else:
            if (
                verified_confirmation is not None
                or confirmation is not None
                or binding is not None
                or context.command_id is not None
                or context.confirmation_id is not None
                or context.intent_sha256 is not None
            ):
                return None
            confirmed = False
            grant_confirmation_id = None
        return TaskAuthorizationGrant(
            principal_id=authority.principal_id,
            scope=authority.scope,
            operation=authority.operation,
            command_id=context.command_id,
            target_task_id=context.target_task_id,
            allowed_capabilities=authority.capabilities,
            confirmation_id=grant_confirmation_id,
            confirmed=confirmed,
            expires_at=authority.expires_at,
        )


__all__ = [
    "AuthorityConfirmationBinding",
    "AuthorityConfirmationRequest",
    "AuthorityDecision",
    "AuthorityDecisionReason",
    "AuthorityDecisionStatus",
    "AuthorityResourceBinding",
    "AuthorityRouteContext",
    "AuthorityRoutingClaim",
    "P2AuthenticatedContext",
    "P2AuthorityAdapter",
    "P3AuthorityAdapter",
    "P3AuthorityContext",
    "ProductAuthorityInputError",
    "ProductAuthorityRequest",
    "ProductAuthorityService",
    "ProductAuthorityUnavailable",
    "ResolvedProductAuthority",
    "SpeechAuthorityResolverAdapter",
    "TrustedAuthorityCandidate",
    "TrustedAuthorityLookup",
    "TrustedAuthorityResolver",
]
