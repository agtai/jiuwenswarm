# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""AgentServer-owned registration boundary for Live Voice product composition.

The boundary is deliberately absent while the master flag is off.  When it is
enabled, every request resolves the existing authenticated P3 Alpha authority
before allocating or invoking P2/P3 owners.  Existing fallback and D-047 Demo
routes are not selected, replaced, or reclassified by this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ProducerRef,
    canonical_json_bytes,
)

from .agent_conversation_runtime import AgentConversationRuntime
from .formal_task_models import FormalTaskViolation, ResolvedTaskContext
from .interaction_engine import InteractionEnginePort
from .p3_authenticated_composition import P3AuthenticatedComposition, P3RouteResult
from .product_authority import (
    AuthorityDecisionStatus,
    AuthorityRouteContext,
    P2AuthenticatedContext,
    P2AuthorityAdapter,
    P3AuthorityAdapter,
    P3AuthorityContext,
    ProductAuthorityRequest,
    ProductAuthorityService,
    ResolvedProductAuthority,
    TrustedAuthorityCandidate,
    TrustedAuthorityLookup,
)
from .product_composition_contract import (
    ProductCompositionManifest,
    ProductEvidenceId,
    ProductRouteFact,
    ProductRouteReason,
    ProductRouteTruth,
    ProductSegment,
)
from .product_composition_root import (
    ProductCompositionActivationError,
    ProductCompositionContext,
    ProductCompositionLease,
    ProductCompositionLeaseCloseError,
    ProductCompositionRegistration,
    ProductCompositionRoot,
    ProductSegmentActivation,
    ProductSegmentActivationError,
)
from .product_p2_interaction_adapter import (
    P2ActivationLease,
    P2ActivationReason,
    P2ActivationStatus,
    P2FailedActivationCleanup,
    P2InteractionActivationRequest,
    P2InteractionBinding,
    P2LeaseCloseStatus,
    ProductP2InteractionAdapter,
)
from .product_p3_text_adapter import (
    ProductP3ProgressCleanupHandle,
    ProductP3ProgressRequest,
    ProductP3QueryRequest,
    ProductP3TextAdapter,
)
from .progress_notification_arbiter import (
    ForegroundFact,
    ForegroundSnapshot,
    ProgressNotificationArbiter,
    SpeechPolicy,
)
from .task_progress_return import (
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
    TaskProgressReturnLease,
    TaskProgressReturnState,
    TaskProgressTextEvent,
)

logger = logging.getLogger(__name__)

PRODUCT_COMPOSITION_ENABLE_ENV = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED"
)
PRODUCT_P2_ENABLE_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED"
PRODUCT_P3_TEXT_ENABLE_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED"

PRODUCT_COMPOSITION_METHODS = frozenset(
    {
        "live_voice.composition.p2.activate",
        "live_voice.composition.p2.close",
        "live_voice.composition.p3.progress.activate",
        "live_voice.composition.p3.progress.close",
    }
)
PRODUCT_P3_QUERY_OPERATIONS = frozenset(
    {"task.get", "task.list", "task.status", "task.events"}
)


def _is_enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _require_exact_params(
    params: Mapping[str, object], allowed: frozenset[str]
) -> None:
    keys = set(params)
    if any(type(key) is not str for key in keys) or keys - allowed:
        raise FormalTaskViolation(
            "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
            "product request fields are incomplete or unknown",
            ErrorCode.INVALID_ARGUMENT,
        )


def product_composition_enabled_from_environment() -> bool:
    """Read only the master gate; callers use this before importing factories."""

    return _is_enabled(os.getenv(PRODUCT_COMPOSITION_ENABLE_ENV))


@dataclass(frozen=True, slots=True)
class ProductCompositionSettings:
    p2_enabled: bool
    p3_text_enabled: bool

    @classmethod
    def from_environment(cls) -> ProductCompositionSettings:
        return cls(
            p2_enabled=_is_enabled(os.getenv(PRODUCT_P2_ENABLE_ENV)),
            p3_text_enabled=_is_enabled(os.getenv(PRODUCT_P3_TEXT_ENABLE_ENV)),
        )


class _SingleCandidateResolver:
    def __init__(self, candidate: TrustedAuthorityCandidate) -> None:
        self._candidate = candidate
        self.calls: list[TrustedAuthorityLookup] = []

    def resolve(
        self, lookup: TrustedAuthorityLookup
    ) -> Sequence[TrustedAuthorityCandidate]:
        self.calls.append(lookup)
        return (self._candidate,)


class _NoopLease:
    async def close(self) -> None:
        return None


@dataclass(slots=True)
class _AuthorityState:
    canonical: ResolvedProductAuthority | None = None
    context: ResolvedTaskContext | None = None
    service: ProductAuthorityService | None = None
    reason: str | None = None


class _AuthorityLease:
    def __init__(self, state: _AuthorityState) -> None:
        self._state = state

    async def close(self) -> None:
        self._state.canonical = None
        self._state.context = None
        self._state.service = None


class _P2RootLease:
    def __init__(
        self,
        *,
        lease: P2ActivationLease,
        binding: P2InteractionBinding,
        agent_manager: Any,
        agent: Any,
    ) -> None:
        self._lease = lease
        self._binding = binding
        self._agent_manager = agent_manager
        self._agent = agent
        self._released = False

    async def close(self) -> None:
        result = await self._lease.close(self._binding, timeout_seconds=0.5)
        if result.status is not P2LeaseCloseStatus.CLOSED:
            raise RuntimeError("P2 product teardown remains incomplete")
        if not self._released:
            self._released = True
            unpin = getattr(self._agent_manager, "unpin_agent", None)
            if callable(unpin):
                unpin(self._agent)


class _P2FailedCleanupLease:
    def __init__(
        self,
        *,
        cleanup: P2FailedActivationCleanup,
        agent_manager: Any,
        agent: Any,
    ) -> None:
        self._cleanup = cleanup
        self._agent_manager = agent_manager
        self._agent = agent
        self._released = False

    async def close(self) -> None:
        result = await self._cleanup.cleanup(
            self._cleanup.binding,
            timeout_seconds=0.5,
            retry_failed=True,
        )
        if result.status is not P2LeaseCloseStatus.CLOSED:
            raise RuntimeError("P2 failed activation cleanup remains incomplete")
        if not self._released:
            self._released = True
            unpin = getattr(self._agent_manager, "unpin_agent", None)
            if callable(unpin):
                unpin(self._agent)


class _P3FailedCleanupLease:
    def __init__(self, cleanup: ProductP3ProgressCleanupHandle) -> None:
        self._cleanup = cleanup

    async def close(self) -> None:
        snapshot = await self._cleanup.close(timeout=0.5)
        if snapshot.state.value != "closed":
            raise RuntimeError("P3 progress cleanup remains incomplete")


@dataclass(slots=True)
class _P2Route:
    binding: P2InteractionBinding
    lease: ProductCompositionLease
    manifest: ProductCompositionManifest


@dataclass(slots=True)
class _ProgressRoute:
    binding: TaskProgressOriginBinding
    progress_lease: TaskProgressReturnLease
    lease: ProductCompositionLease
    manifest: ProductCompositionManifest
    channel_id: str
    request_id: str


@dataclass(frozen=True, slots=True)
class _ProgressTarget:
    channel_id: str
    request_id: str
    correlation_id: str
    generation: int


def _formal_fact(segment: ProductSegment) -> ProductRouteFact:
    evidence = [
        ProductEvidenceId.TRUSTED_AUTHORITY_RESOLVED,
        ProductEvidenceId.FORMAL_ACTIVATION_LEASE_OPEN,
        ProductEvidenceId.RUNTIME_PATH_OBSERVED,
    ]
    if segment is ProductSegment.P2_AGENT_INTERACTION:
        evidence.append(ProductEvidenceId.P2_NOTIFICATION_BACKPRESSURE_CLOSED)
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.FORMAL,
        reason_id=ProductRouteReason.FORMAL_ROUTE_OBSERVED,
        evidence_ids=tuple(evidence),
        formal_runtime_observed=True,
    )


def _unavailable_fact(
    segment: ProductSegment,
    reason: ProductRouteReason,
) -> ProductRouteFact:
    return ProductRouteFact(
        segment=segment,
        truth=ProductRouteTruth.UNAVAILABLE,
        reason_id=reason,
        evidence_ids=(
            ProductEvidenceId.PACKAGE_CONTRACT_ONLY,
            ProductEvidenceId.NO_RUNTIME_EVIDENCE,
        ),
    )


def _serialize_manifest(manifest: ProductCompositionManifest) -> dict[str, object]:
    return {
        "contract_version": manifest.contract_version,
        "enabled": manifest.enabled,
        "routes": [
            {
                "segment": route.segment.value,
                "truth": route.truth.value,
                "reason_id": route.reason_id.value,
                "evidence_ids": [item.value for item in route.evidence_ids],
                "formal_runtime_observed": route.formal_runtime_observed,
            }
            for route in manifest.routes
        ],
    }


def _required_text(value: object, field: str, *, maximum: int = 256) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise FormalTaskViolation(
            "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
            f"{field} must be a non-empty bounded string",
            ErrorCode.INVALID_ARGUMENT,
        )
    return value.strip()


def _optional_claim(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _error_result(
    request_id: str,
    *,
    reason: str,
    code: ErrorCode = ErrorCode.UNAVAILABLE,
    message: str = "Live Voice product composition is unavailable",
    manifest: ProductCompositionManifest | None = None,
) -> P3RouteResult:
    payload: dict[str, object] = {
        "request_id": request_id,
        "ok": False,
        "result": None,
        "error": {
            "code": code.value,
            "reason": reason,
            "message": message,
        },
    }
    if manifest is not None:
        payload["product_composition"] = _serialize_manifest(manifest)
    return P3RouteResult(False, payload)


def _success_result(
    request_id: str,
    result: Mapping[str, object],
    manifest: ProductCompositionManifest,
) -> P3RouteResult:
    return P3RouteResult(
        True,
        {
            "request_id": request_id,
            "ok": True,
            "result": dict(result),
            "error": None,
            "product_composition": _serialize_manifest(manifest),
        },
    )


def _server_agent_mode(session_id: str) -> tuple[str, str | None]:
    from jiuwenswarm.server.runtime.session.session_metadata import (
        get_session_metadata,
    )

    metadata = get_session_metadata(
        session_id,
        cache_bust=True,
        enable_writeback=False,
    )
    if not isinstance(metadata, Mapping):
        return "agent", None
    raw = str(metadata.get("mode") or "").strip().lower()
    if not raw:
        raw = "code" if str(metadata.get("work_mode") or "") == "code" else "agent"
    if raw in {"plan", "fast"} or raw.startswith("agent"):
        return "agent", None
    if raw == "team.plan":
        return "code", "team"
    if raw.startswith("team"):
        return "team", None
    if raw.startswith("code"):
        suffix = raw.partition(".")[2]
        return "code", suffix if suffix in {"plan", "normal", "team"} else "normal"
    return "agent", None


class AgentServerProductCompositionRegistry:
    """Central default-off registrations and retained route leases."""

    def __init__(
        self,
        *,
        settings: ProductCompositionSettings,
        p3_composition: P3AuthenticatedComposition,
        agent_manager: Any,
        push_text_event: Callable[[dict[str, object]], Awaitable[bool]],
    ) -> None:
        if not isinstance(settings, ProductCompositionSettings):
            raise ValueError("product composition settings are required")
        if not isinstance(p3_composition, P3AuthenticatedComposition):
            raise ValueError("authenticated P3 composition is required")
        if not callable(push_text_event):
            raise ValueError("product text event sink is required")
        self._settings = settings
        self._p3_composition = p3_composition
        self._agent_manager = agent_manager
        self._push_text_event = push_text_event
        self._lock = asyncio.Lock()
        self._stopped = False
        self._p2_routes: dict[tuple[str, str], _P2Route] = {}
        self._progress_routes: dict[
            tuple[str, str, str, str], _ProgressRoute
        ] = {}
        self._progress_generations: dict[tuple[str, str, str, str], int] = {}
        self._progress_targets: dict[
            tuple[str, str, str, str], _ProgressTarget
        ] = {}
        self._pending_p2_agents: dict[tuple[str, str, str, int], Any] = {}
        self._p2_orphan_cleanups: list[_P2FailedCleanupLease] = []
        self._root_orphan_cleanups: list[ProductCompositionLease] = []

        disabled_service = ProductAuthorityService(enabled=False, resolver=None)
        self._p2_adapter = ProductP2InteractionAdapter(
            enabled=settings.p2_enabled,
            authority_adapter=P2AuthorityAdapter(disabled_service),
            runtime_factory=self._create_p2_runtime,
            interaction_engine_factory=lambda _context, _binding: (
                InteractionEnginePort(
                    frozenset(
                        {
                            "playback.stop",
                            "response.cancel",
                            "round.cancel",
                            "task.cancel",
                        }
                    )
                )
            ),
        )
        self._p3_adapter = ProductP3TextAdapter(
            enabled=settings.p3_text_enabled,
            authority=P3AuthorityAdapter(disabled_service),
            query_owner=p3_composition,
            subscription_factory=p3_composition.create_product_subscription,
            generation_is_current=self._generation_is_current,
            arbiter=ProgressNotificationArbiter(enabled=True),
            foreground=lambda: ForegroundSnapshot(
                interaction=ForegroundFact.UNKNOWN,
                response=ForegroundFact.UNKNOWN,
                presentation=ForegroundFact.UNKNOWN,
                speech_policy=SpeechPolicy.DISPLAY_ONLY,
            ),
            text_sink=self._emit_text_progress,
            voice_sink=self._reject_voice_progress,
        )

    @property
    def p3_text_enabled(self) -> bool:
        return self._settings.p3_text_enabled

    @property
    def p2_enabled(self) -> bool:
        return self._settings.p2_enabled

    def _create_p2_runtime(
        self,
        context: P2AuthenticatedContext,
        binding: P2InteractionBinding,
    ) -> AgentConversationRuntime:
        key = (
            binding.session_id,
            binding.interaction_id,
            binding.activation_id,
            binding.activation_generation,
        )
        facade = self._pending_p2_agents.get(key)
        if facade is None:
            raise RuntimeError("P2 facade allocation was not authorized")
        instance_fingerprint = hashlib.sha256(
            canonical_json_bytes(
                {
                    "session_id": binding.session_id,
                    "interaction_id": binding.interaction_id,
                    "activation_id": binding.activation_id,
                    "activation_generation": binding.activation_generation,
                }
            )
        ).hexdigest()
        return AgentConversationRuntime(
            context.scope,
            instance_id=f"product-p2:{instance_fingerprint}",
            facade=facade,
            enabled=True,
        )

    def _generation_is_current(self, binding: TaskProgressOriginBinding) -> bool:
        key = (
            binding.session_id,
            binding.task_id,
            binding.origin_id,
            binding.generation_id,
        )
        return self._progress_generations.get(key) == binding.generation

    def _retain_root_cleanup(
        self, cleanup: ProductCompositionLease | None
    ) -> None:
        if cleanup is not None and all(
            retained is not cleanup for retained in self._root_orphan_cleanups
        ):
            self._root_orphan_cleanups.append(cleanup)

    async def _emit_text_progress(self, event: TaskProgressTextEvent) -> None:
        binding = event.origin
        key = (
            binding.session_id,
            binding.task_id,
            binding.origin_id,
            binding.generation_id,
        )
        target = self._progress_targets.get(key)
        if (
            target is None
            or target.correlation_id != binding.correlation_id
            or target.generation != binding.generation
        ):
            raise RuntimeError("text progress route is no longer current")
        delivered = await self._push_text_event(
            {
                "request_id": target.request_id,
                "channel_id": target.channel_id,
                "session_id": binding.session_id,
                "payload": {
                    "event_type": "live_voice.task.progress",
                    "session_id": binding.session_id,
                    "task_id": binding.task_id,
                    "project_id": binding.project_id,
                    "correlation_id": binding.correlation_id,
                    "origin_id": binding.origin_id,
                    "generation_kind": binding.generation_kind,
                    "generation_id": binding.generation_id,
                    "generation": binding.generation,
                    "source_event": event.source_event.to_dict(),
                    "progress_event": event.progress_event.to_dict(),
                    "evidence_id": event.evidence_id,
                },
                "is_complete": False,
            }
        )
        if delivered is not True:
            raise RuntimeError("text progress Web sink is unavailable")

    @staticmethod
    async def _reject_voice_progress(_event: object) -> None:
        raise RuntimeError("formal voice progress is unavailable")

    async def _authority_registration(
        self,
        *,
        state: _AuthorityState,
        bearer_token: object,
        route: AuthorityRouteContext,
        operation: str,
        task_id: str | None,
    ) -> ProductSegmentActivation:
        try:
            candidate, resolved_context = await asyncio.to_thread(
                self._p3_composition.resolve_product_authority_candidate,
                bearer_token=bearer_token,
                operation=operation,
                session_id=route.session_id,
                correlation_id=route.correlation_id,
                required_capabilities=frozenset({operation}),
                task_id=task_id,
            )
        except FormalTaskViolation as exc:
            state.reason = exc.reason
            return ProductSegmentActivation(
                _unavailable_fact(
                    ProductSegment.AUTHORITY,
                    ProductRouteReason.TRUSTED_AUTHORITY_UNAVAILABLE,
                ),
                None,
            )
        except Exception:
            state.reason = "TRUSTED_AUTHORITY_RESOLVER_FAILURE"
            return ProductSegmentActivation(
                _unavailable_fact(
                    ProductSegment.AUTHORITY,
                    ProductRouteReason.TRUSTED_AUTHORITY_UNAVAILABLE,
                ),
                None,
            )

        resolver = _SingleCandidateResolver(candidate)
        service = ProductAuthorityService(enabled=True, resolver=resolver)
        decision = service.resolve(
            ProductAuthorityRequest(
                route=route,
                operation=operation,
                required_capabilities=frozenset({operation}),
                resource=candidate.resource,
            )
        )
        if decision.status is not AuthorityDecisionStatus.AUTHORIZED:
            state.reason = decision.reason.value
            return ProductSegmentActivation(
                _unavailable_fact(
                    ProductSegment.AUTHORITY,
                    ProductRouteReason.TRUSTED_AUTHORITY_UNAVAILABLE,
                ),
                None,
            )
        assert decision.authority is not None
        state.canonical = decision.authority
        state.context = resolved_context
        state.service = service
        return ProductSegmentActivation(
            _formal_fact(ProductSegment.AUTHORITY),
            _AuthorityLease(state),
        )

    @staticmethod
    async def _media_unavailable(
        _context: ProductCompositionContext,
    ) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _unavailable_fact(
                ProductSegment.P1_SPEECH_MEDIA,
                ProductRouteReason.MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN,
            ),
            None,
        )

    @staticmethod
    async def _control_unavailable(
        _context: ProductCompositionContext,
    ) -> ProductSegmentActivation:
        return ProductSegmentActivation(
            _unavailable_fact(
                ProductSegment.P3_CONTROL,
                ProductRouteReason.P3_CONFIRMATION_ISSUER_UNAVAILABLE,
            ),
            None,
        )

    @staticmethod
    def _registration(
        segment: ProductSegment,
        adapter_id: str,
        callback: Callable[
            [ProductCompositionContext], Awaitable[ProductSegmentActivation]
        ],
    ) -> ProductCompositionRegistration:
        return ProductCompositionRegistration(segment, adapter_id, callback)

    def _base_registrations(
        self,
        authority: Callable[
            [ProductCompositionContext], Awaitable[ProductSegmentActivation]
        ],
    ) -> list[ProductCompositionRegistration]:
        return [
            self._registration(
                ProductSegment.AUTHORITY,
                "agent_server.trusted_authority.v1",
                authority,
            ),
            self._registration(
                ProductSegment.P1_SPEECH_MEDIA,
                "agent_server.media_unavailable.v1",
                self._media_unavailable,
            ),
            self._registration(
                ProductSegment.P3_CONTROL,
                "agent_server.p3_control_unavailable.v1",
                self._control_unavailable,
            ),
        ]

    @staticmethod
    def _route_context(
        *,
        session_id: str,
        correlation_id: str,
        params: Mapping[str, object],
    ) -> AuthorityRouteContext:
        return AuthorityRouteContext(
            session_id=session_id,
            correlation_id=correlation_id,
            claimed_user_id=_optional_claim(
                params.get("claimed_user_id"), "claimed_user_id"
            ),
            claimed_project_id=_optional_claim(
                params.get("claimed_project_id"), "claimed_project_id"
            ),
        )

    def _ensure_running(self) -> None:
        if self._stopped:
            raise FormalTaskViolation(
                "PRODUCT_COMPOSITION_STOPPED",
                "Live Voice product composition is stopped",
                ErrorCode.UNAVAILABLE,
            )

    async def handle_p2_activate(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
        channel_id: str,
    ) -> P3RouteResult:
        del channel_id
        if not self._settings.p2_enabled:
            return _error_result(request_id, reason="PRODUCT_P2_DISABLED")
        try:
            _require_exact_params(
                params,
                frozenset(
                    {
                        "auth_token",
                        "session_id",
                        "correlation_id",
                        "interaction_id",
                        "activation_id",
                        "activation_generation",
                        "claimed_user_id",
                        "claimed_project_id",
                    }
                ),
            )
            self._ensure_running()
            routed_session = _required_text(session_id, "routed_session_id")
            if _required_text(params.get("session_id"), "session_id") != routed_session:
                raise FormalTaskViolation(
                    "PRODUCT_COMPOSITION_SESSION_MISMATCH",
                    "product request does not match its routed session",
                    ErrorCode.PERMISSION_DENIED,
                )
            correlation_id = _required_text(
                params.get("correlation_id"), "correlation_id"
            )
            interaction_id = _required_text(
                params.get("interaction_id"), "interaction_id"
            )
            activation_id = _required_text(
                params.get("activation_id"), "activation_id"
            )
            generation = params.get("activation_generation")
            if type(generation) is not int or generation <= 0:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "activation_generation must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            route = self._route_context(
                session_id=routed_session,
                correlation_id=correlation_id,
                params=params,
            )
        except FormalTaskViolation as exc:
            return _error_result(
                request_id,
                reason=exc.reason,
                code=exc.code,
                message=str(exc),
            )

        async with self._lock:
            if self._stopped:
                return _error_result(
                    request_id, reason="PRODUCT_COMPOSITION_STOPPED"
                )
            key = (routed_session, interaction_id)
            existing = self._p2_routes.get(key)
            if existing is not None:
                replay_state = _AuthorityState()
                replay_authority = await self._authority_registration(
                    state=replay_state,
                    bearer_token=params.get("auth_token"),
                    route=route,
                    operation="agent.chat",
                    task_id=None,
                )
                if (
                    replay_authority.route_fact.truth
                    is not ProductRouteTruth.FORMAL
                ):
                    return _error_result(
                        request_id,
                        reason=(
                            replay_state.reason or "TRUSTED_AUTHORITY_UNAVAILABLE"
                        ),
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                assert replay_state.canonical is not None
                expected = existing.binding
                if replay_state.canonical.scope != expected.scope:
                    if replay_authority.lease is not None:
                        await replay_authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="ACTIVATION_BINDING_MISMATCH",
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                if (
                    expected.correlation_id == correlation_id
                    and expected.activation_id == activation_id
                    and expected.activation_generation == generation
                ):
                    if replay_authority.lease is not None:
                        await replay_authority.lease.close()
                    return _success_result(
                        request_id,
                        {
                            "status": "active",
                            "replayed": True,
                            "interaction_id": interaction_id,
                            "activation_id": activation_id,
                            "activation_generation": generation,
                        },
                        existing.manifest,
                    )
                if replay_authority.lease is not None:
                    await replay_authority.lease.close()
                return _error_result(
                    request_id,
                    reason="ACTIVATION_BINDING_CONFLICT",
                    code=ErrorCode.CONFLICT,
                )

            state = _AuthorityState()

            async def activate_authority(
                _context: ProductCompositionContext,
            ) -> ProductSegmentActivation:
                return await self._authority_registration(
                    state=state,
                    bearer_token=params.get("auth_token"),
                    route=route,
                    operation="agent.chat",
                    task_id=None,
                )

            holder: dict[str, object] = {}

            async def activate_p2(
                _context: ProductCompositionContext,
            ) -> ProductSegmentActivation:
                canonical = state.canonical
                resolved_context = state.context
                if canonical is None or resolved_context is None:
                    raise ProductSegmentActivationError("P2_AUTHORITY_MISSING")
                request = P2InteractionActivationRequest(
                    route=route,
                    interaction_id=interaction_id,
                    activation_id=activation_id,
                    activation_generation=generation,
                )
                prepared = self._p2_adapter.prepare_activation(
                    P2AuthenticatedContext(canonical, canonical.scope),
                    request,
                )
                project_dir = resolved_context.file_path
                if not project_dir:
                    return ProductSegmentActivation(
                        _unavailable_fact(
                            ProductSegment.P2_AGENT_INTERACTION,
                            ProductRouteReason.P2_RUNTIME_UNAVAILABLE,
                        ),
                        None,
                    )
                mode, sub_mode = await asyncio.to_thread(
                    _server_agent_mode, routed_session
                )
                agent = await self._agent_manager.get_agent(
                    "web",
                    mode,
                    project_dir,
                    sub_mode,
                )
                if agent is None:
                    return ProductSegmentActivation(
                        _unavailable_fact(
                            ProductSegment.P2_AGENT_INTERACTION,
                            ProductRouteReason.P2_RUNTIME_UNAVAILABLE,
                        ),
                        None,
                    )
                pin = getattr(self._agent_manager, "pin_agent", None)
                if callable(pin):
                    pin(agent)
                pending_key = (
                    routed_session,
                    interaction_id,
                    activation_id,
                    generation,
                )
                self._pending_p2_agents[pending_key] = agent
                try:
                    try:
                        result = await self._p2_adapter.activate_prepared(prepared)
                    except BaseException:
                        cleanup = next(
                            (
                                item
                                for item in self._p2_adapter.retained_failed_cleanups()
                                if item.binding == prepared.binding
                            ),
                            None,
                        )
                        if cleanup is None:
                            unpin = getattr(
                                self._agent_manager, "unpin_agent", None
                            )
                            if callable(unpin):
                                unpin(agent)
                        else:
                            self._p2_orphan_cleanups.append(
                                _P2FailedCleanupLease(
                                    cleanup=cleanup,
                                    agent_manager=self._agent_manager,
                                    agent=agent,
                                )
                            )
                        raise
                finally:
                    self._pending_p2_agents.pop(pending_key, None)
                if result.status is P2ActivationStatus.ACTIVE:
                    assert result.lease is not None
                    wrapper = _P2RootLease(
                        lease=result.lease,
                        binding=result.lease.binding,
                        agent_manager=self._agent_manager,
                        agent=agent,
                    )
                    holder["binding"] = result.lease.binding
                    return ProductSegmentActivation(
                        _formal_fact(ProductSegment.P2_AGENT_INTERACTION),
                        wrapper,
                    )
                if result.cleanup is not None:
                    raise ProductSegmentActivationError(
                        result.reason.value,
                        cleanup_lease=_P2FailedCleanupLease(
                            cleanup=result.cleanup,
                            agent_manager=self._agent_manager,
                            agent=agent,
                        ),
                    )
                if callable(getattr(self._agent_manager, "unpin_agent", None)):
                    self._agent_manager.unpin_agent(agent)
                reason = (
                    ProductRouteReason.P2_AUTHORITY_UNAVAILABLE
                    if result.reason
                    in {
                        P2ActivationReason.AUTHORITY_DENIED,
                        P2ActivationReason.AUTHORITY_UNAVAILABLE,
                    }
                    else ProductRouteReason.P2_RUNTIME_UNAVAILABLE
                )
                return ProductSegmentActivation(
                    _unavailable_fact(ProductSegment.P2_AGENT_INTERACTION, reason),
                    None,
                )

            registrations = self._base_registrations(activate_authority)
            registrations.append(
                self._registration(
                    ProductSegment.P2_AGENT_INTERACTION,
                    "agent_server.product_p2.v1",
                    activate_p2,
                )
            )
            try:
                activation = await ProductCompositionRoot(
                    enabled=True,
                    registrations=registrations,
                ).activate(ProductCompositionContext(routed_session, correlation_id))
            except ProductCompositionActivationError as exc:
                self._retain_root_cleanup(exc.cleanup_lease)
                logger.exception("[LiveVoiceProduct] P2 activation failed closed")
                return _error_result(
                    request_id,
                    reason="PRODUCT_P2_ACTIVATION_FAILED",
                )
            except Exception:
                logger.exception("[LiveVoiceProduct] P2 activation failed closed")
                return _error_result(
                    request_id,
                    reason="PRODUCT_P2_ACTIVATION_FAILED",
                )
            binding = holder.get("binding")
            if not isinstance(binding, P2InteractionBinding) or activation.lease is None:
                reason = state.reason or "PRODUCT_P2_UNAVAILABLE"
                if activation.lease is not None:
                    try:
                        await activation.lease.close()
                    except ProductCompositionLeaseCloseError as exc:
                        self._retain_root_cleanup(exc.lease)
                        logger.exception(
                            "[LiveVoiceProduct] inactive P2 cleanup failed"
                        )
                return _error_result(
                    request_id,
                    reason=reason,
                    manifest=activation.manifest,
                )
            self._p2_routes[key] = _P2Route(
                binding=binding,
                lease=activation.lease,
                manifest=activation.manifest,
            )
            return _success_result(
                request_id,
                {
                    "status": "active",
                    "replayed": False,
                    "interaction_id": binding.interaction_id,
                    "activation_id": binding.activation_id,
                    "activation_generation": binding.activation_generation,
                },
                activation.manifest,
            )

    async def handle_p2_close(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        if not self._settings.p2_enabled:
            return _error_result(request_id, reason="PRODUCT_P2_DISABLED")
        try:
            _require_exact_params(
                params,
                frozenset(
                    {
                        "auth_token",
                        "session_id",
                        "correlation_id",
                        "interaction_id",
                        "activation_id",
                        "activation_generation",
                        "claimed_user_id",
                        "claimed_project_id",
                    }
                ),
            )
            self._ensure_running()
            routed_session = _required_text(session_id, "routed_session_id")
            if _required_text(params.get("session_id"), "session_id") != routed_session:
                raise FormalTaskViolation(
                    "PRODUCT_COMPOSITION_SESSION_MISMATCH",
                    "product request does not match its routed session",
                    ErrorCode.PERMISSION_DENIED,
                )
            correlation_id = _required_text(
                params.get("correlation_id"), "correlation_id"
            )
            interaction_id = _required_text(
                params.get("interaction_id"), "interaction_id"
            )
            activation_id = _required_text(
                params.get("activation_id"), "activation_id"
            )
            generation = params.get("activation_generation")
            if type(generation) is not int or generation <= 0:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "activation_generation must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            route = self._route_context(
                session_id=routed_session,
                correlation_id=correlation_id,
                params=params,
            )
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )

        async with self._lock:
            if self._stopped:
                return _error_result(
                    request_id, reason="PRODUCT_COMPOSITION_STOPPED"
                )
            state = _AuthorityState()
            authority = await self._authority_registration(
                state=state,
                bearer_token=params.get("auth_token"),
                route=route,
                operation="agent.chat",
                task_id=None,
            )
            if authority.route_fact.truth is not ProductRouteTruth.FORMAL:
                return _error_result(
                    request_id,
                    reason=state.reason or "TRUSTED_AUTHORITY_UNAVAILABLE",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            assert state.canonical is not None
            retained = self._p2_routes.get((routed_session, interaction_id))
            if retained is None:
                if authority.lease is not None:
                    await authority.lease.close()
                return _error_result(
                    request_id,
                    reason="PRODUCT_P2_ROUTE_NOT_FOUND",
                    code=ErrorCode.NOT_FOUND,
                )
            if (
                retained.binding.correlation_id != correlation_id
                or retained.binding.activation_id != activation_id
                or retained.binding.activation_generation != generation
            ):
                if authority.lease is not None:
                    await authority.lease.close()
                return _error_result(
                    request_id,
                    reason="ACTIVATION_BINDING_MISMATCH",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            if state.canonical.scope != retained.binding.scope:
                if authority.lease is not None:
                    await authority.lease.close()
                return _error_result(
                    request_id,
                    reason="ACTIVATION_BINDING_MISMATCH",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            try:
                await retained.lease.close()
            except ProductCompositionLeaseCloseError:
                return _error_result(
                    request_id,
                    reason="PRODUCT_P2_CLEANUP_PENDING",
                )
            finally:
                if authority.lease is not None:
                    await authority.lease.close()
            self._p2_routes.pop((routed_session, interaction_id), None)
            return _success_result(
                request_id,
                {"status": "closed", "interaction_id": interaction_id},
                retained.manifest,
            )

    async def handle_p3_query(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        if not self._settings.p3_text_enabled:
            return _error_result(request_id, reason="PRODUCT_P3_TEXT_DISABLED")
        if operation not in PRODUCT_P3_QUERY_OPERATIONS:
            return _error_result(
                request_id,
                reason="PRODUCT_P3_MUTATION_UNAVAILABLE",
                code=ErrorCode.UNSUPPORTED,
            )
        async with self._lock:
            return await self._handle_p3_query_locked(
                operation=operation,
                params=params,
                request_id=request_id,
                session_id=session_id,
            )

    async def _handle_p3_query_locked(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        if not self._settings.p3_text_enabled:
            return _error_result(request_id, reason="PRODUCT_P3_TEXT_DISABLED")
        if operation not in PRODUCT_P3_QUERY_OPERATIONS:
            return _error_result(
                request_id,
                reason="PRODUCT_P3_MUTATION_UNAVAILABLE",
                code=ErrorCode.UNSUPPORTED,
            )
        try:
            allowed_fields = {
                "auth_token",
                "session_id",
                "claimed_user_id",
                "claimed_project_id",
            }
            if operation != "task.list":
                allowed_fields.add("task_id")
            if operation == "task.events":
                allowed_fields.add("after_seq")
            _require_exact_params(
                params,
                frozenset(allowed_fields),
            )
            self._ensure_running()
            routed_session = _required_text(session_id, "routed_session_id")
            if _required_text(params.get("session_id"), "session_id") != routed_session:
                raise FormalTaskViolation(
                    "PRODUCT_COMPOSITION_SESSION_MISMATCH",
                    "product request does not match its routed session",
                    ErrorCode.PERMISSION_DENIED,
                )
            task_id = (
                None
                if operation == "task.list"
                else _required_text(params.get("task_id"), "task_id")
            )
            after_seq = params.get("after_seq", -1)
            if type(after_seq) is not int or after_seq < -1:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "after_seq must be an integer at least -1",
                    ErrorCode.INVALID_ARGUMENT,
                )
            correlation_id = request_id
            route = self._route_context(
                session_id=routed_session,
                correlation_id=correlation_id,
                params=params,
            )
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )

        state = _AuthorityState()

        async def activate_authority(
            _context: ProductCompositionContext,
        ) -> ProductSegmentActivation:
            return await self._authority_registration(
                state=state,
                bearer_token=params.get("auth_token"),
                route=route,
                operation=operation,
                task_id=task_id,
            )

        holder: dict[str, object] = {}

        async def activate_query(
            _context: ProductCompositionContext,
        ) -> ProductSegmentActivation:
            canonical = state.canonical
            service = state.service
            if canonical is None or service is None:
                raise ProductSegmentActivationError("P3_AUTHORITY_MISSING")
            p3_authority = P3AuthorityContext(
                authority=canonical,
                resource=canonical.resource,
                command_id=None,
                target_task_id=task_id,
                intent_sha256=None,
                confirmation_id=None,
                confirmation_binding=None,
            )
            grant = P3AuthorityAdapter(service).to_task_grant(p3_authority, None)
            if grant is None:
                return ProductSegmentActivation(
                    _unavailable_fact(
                        ProductSegment.P3_QUERY,
                        ProductRouteReason.P3_QUERY_AUTHORITY_UNAVAILABLE,
                    ),
                    None,
                )
            result = await self._p3_adapter.activate_prepared_query(
                ProductP3QueryRequest(
                    route=route,
                    operation=operation,
                    request_id=request_id,
                    task_id=task_id,
                    after_seq=after_seq,
                    resource=canonical.resource,
                ),
                p3_authority,
                grant,
            )
            holder["result"] = result
            if result.result is None:
                return ProductSegmentActivation(
                    _unavailable_fact(
                        ProductSegment.P3_QUERY,
                        ProductRouteReason.REQUESTED_ROUTE_UNAVAILABLE,
                    ),
                    None,
                )
            return ProductSegmentActivation(
                _formal_fact(ProductSegment.P3_QUERY),
                _NoopLease(),
            )

        registrations = self._base_registrations(activate_authority)
        registrations.append(
            self._registration(
                ProductSegment.P3_QUERY,
                "agent_server.product_p3_query.v1",
                activate_query,
            )
        )
        try:
            activation = await ProductCompositionRoot(
                enabled=True,
                registrations=registrations,
            ).activate(ProductCompositionContext(routed_session, correlation_id))
        except ProductCompositionActivationError as exc:
            self._retain_root_cleanup(exc.cleanup_lease)
            logger.exception("[LiveVoiceProduct] P3 query failed closed")
            return _error_result(request_id, reason="PRODUCT_P3_QUERY_FAILED")
        except Exception:
            logger.exception("[LiveVoiceProduct] P3 query failed closed")
            return _error_result(request_id, reason="PRODUCT_P3_QUERY_FAILED")
        try:
            result = holder.get("result")
            envelope = getattr(result, "result", None)
            if envelope is None:
                adapter_reason = getattr(
                    getattr(result, "reason_id", None), "value", None
                )
                return _error_result(
                    request_id,
                    reason=(
                        state.reason
                        or (
                            adapter_reason
                            if isinstance(adapter_reason, str)
                            else "PRODUCT_P3_QUERY_UNAVAILABLE"
                        )
                    ),
                    manifest=activation.manifest,
                )
            payload = envelope.to_dict()
            payload["product_composition"] = _serialize_manifest(
                activation.manifest
            )
            return P3RouteResult(bool(envelope.ok), payload)
        finally:
            if activation.lease is not None:
                try:
                    await activation.lease.close()
                except ProductCompositionLeaseCloseError as exc:
                    self._retain_root_cleanup(exc.lease)
                    logger.exception("[LiveVoiceProduct] P3 query cleanup failed")

    async def handle_p3_progress_activate(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
        channel_id: str,
    ) -> P3RouteResult:
        if not self._settings.p3_text_enabled:
            return _error_result(request_id, reason="PRODUCT_P3_TEXT_DISABLED")
        try:
            _require_exact_params(
                params,
                frozenset(
                    {
                        "auth_token",
                        "session_id",
                        "task_id",
                        "correlation_id",
                        "origin_id",
                        "generation_id",
                        "generation",
                        "claimed_user_id",
                        "claimed_project_id",
                    }
                ),
            )
            self._ensure_running()
            routed_session = _required_text(session_id, "routed_session_id")
            if _required_text(params.get("session_id"), "session_id") != routed_session:
                raise FormalTaskViolation(
                    "PRODUCT_COMPOSITION_SESSION_MISMATCH",
                    "product request does not match its routed session",
                    ErrorCode.PERMISSION_DENIED,
                )
            task_id = _required_text(params.get("task_id"), "task_id")
            correlation_id = _required_text(
                params.get("correlation_id"), "correlation_id"
            )
            origin_id = _required_text(params.get("origin_id"), "origin_id")
            generation_id = _required_text(
                params.get("generation_id"), "generation_id"
            )
            generation = params.get("generation")
            if type(generation) is not int or generation <= 0:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "generation must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            route = self._route_context(
                session_id=routed_session,
                correlation_id=correlation_id,
                params=params,
            )
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )

        async with self._lock:
            if self._stopped:
                return _error_result(
                    request_id, reason="PRODUCT_COMPOSITION_STOPPED"
                )
            key = (routed_session, task_id, origin_id, generation_id)
            existing = self._progress_routes.get(key)
            state = _AuthorityState()
            preauthorized_authority: ProductSegmentActivation | None = None
            if existing is not None:
                preauthorized_authority = await self._authority_registration(
                    state=state,
                    bearer_token=params.get("auth_token"),
                    route=route,
                    operation="task.events",
                    task_id=task_id,
                )
                if (
                    preauthorized_authority.route_fact.truth
                    is not ProductRouteTruth.FORMAL
                ):
                    return _error_result(
                        request_id,
                        reason=state.reason or "TRUSTED_AUTHORITY_UNAVAILABLE",
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                assert state.canonical is not None
                if state.canonical.scope != existing.binding.scope:
                    if preauthorized_authority.lease is not None:
                        await preauthorized_authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_BINDING_MISMATCH",
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                progress_snapshot = existing.progress_lease.snapshot()
                route_is_active = (
                    progress_snapshot.state is TaskProgressReturnState.ACTIVE
                    and progress_snapshot.worker_pending
                )
                if not route_is_active:
                    try:
                        await existing.lease.close()
                    except ProductCompositionLeaseCloseError:
                        if preauthorized_authority.lease is not None:
                            await preauthorized_authority.lease.close()
                        return _error_result(
                            request_id,
                            reason="TASK_PROGRESS_SETTLED_CLEANUP_PENDING",
                        )
                    self._progress_targets.pop(key, None)
                    if generation <= existing.binding.generation:
                        if preauthorized_authority.lease is not None:
                            await preauthorized_authority.lease.close()
                        return _error_result(
                            request_id,
                            reason="TASK_PROGRESS_ROUTE_SETTLED",
                            code=ErrorCode.CONFLICT,
                        )
                    self._progress_routes.pop(key, None)
                if (
                    route_is_active
                    and existing.binding.generation == generation
                    and existing.binding.correlation_id == correlation_id
                ):
                    if preauthorized_authority.lease is not None:
                        await preauthorized_authority.lease.close()
                    return _success_result(
                        request_id,
                        {
                            "status": "active",
                            "replayed": True,
                            "task_id": task_id,
                            "generation": generation,
                        },
                        existing.manifest,
                    )
                if route_is_active and generation <= existing.binding.generation:
                    if preauthorized_authority.lease is not None:
                        await preauthorized_authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_STALE_GENERATION",
                        code=ErrorCode.CONFLICT,
                    )
                try:
                    if route_is_active:
                        await existing.lease.close()
                except ProductCompositionLeaseCloseError:
                    if preauthorized_authority.lease is not None:
                        await preauthorized_authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_REPLACEMENT_CLEANUP_PENDING",
                    )
                self._progress_routes.pop(key, None)
            self._progress_generations[key] = generation
            self._progress_targets[key] = _ProgressTarget(
                channel_id=channel_id,
                request_id=request_id,
                correlation_id=correlation_id,
                generation=generation,
            )

            async def activate_authority(
                _context: ProductCompositionContext,
            ) -> ProductSegmentActivation:
                if preauthorized_authority is not None:
                    return preauthorized_authority
                return await self._authority_registration(
                    state=state,
                    bearer_token=params.get("auth_token"),
                    route=route,
                    operation="task.events",
                    task_id=task_id,
                )

            holder: dict[str, object] = {}

            async def activate_progress(
                _context: ProductCompositionContext,
            ) -> ProductSegmentActivation:
                canonical = state.canonical
                service = state.service
                if canonical is None or service is None:
                    raise ProductSegmentActivationError("P3_AUTHORITY_MISSING")
                p3_authority = P3AuthorityContext(
                    authority=canonical,
                    resource=canonical.resource,
                    command_id=None,
                    target_task_id=task_id,
                    intent_sha256=None,
                    confirmation_id=None,
                    confirmation_binding=None,
                )
                grant = P3AuthorityAdapter(service).to_task_grant(
                    p3_authority, None
                )
                if grant is None:
                    return ProductSegmentActivation(
                        _unavailable_fact(
                            ProductSegment.P3_PROGRESS,
                            ProductRouteReason.P3_QUERY_AUTHORITY_UNAVAILABLE,
                        ),
                        None,
                    )
                result = await self._p3_adapter.activate_prepared_text_progress(
                    ProductP3ProgressRequest(
                        route=route,
                        task_id=task_id,
                        origin_kind=TaskProgressOriginKind.TEXT,
                        origin_id=origin_id,
                        generation_kind="web_task_progress_generation",
                        generation_id=generation_id,
                        generation=generation,
                        source_instance_id="agent_server.p3_core",
                        progress_producer=ProducerRef(
                            component="product_p3_text",
                            instance_id=(
                                f"{routed_session}:{origin_id}:{generation}"
                            ),
                            authority="adapter",
                        ),
                        progress_adapter="agent_server.product_p3_text.v1",
                        resource=canonical.resource,
                    ),
                    p3_authority,
                    grant,
                )
                if result.active and result.lease is not None:
                    assert result.binding is not None
                    holder["binding"] = result.binding
                    holder["progress_lease"] = result.lease
                    return ProductSegmentActivation(
                        _formal_fact(ProductSegment.P3_PROGRESS),
                        result.lease,
                    )
                if result.cleanup is not None:
                    raise ProductSegmentActivationError(
                        result.reason_id,
                        cleanup_lease=_P3FailedCleanupLease(result.cleanup),
                    )
                return ProductSegmentActivation(
                    _unavailable_fact(
                        ProductSegment.P3_PROGRESS,
                        ProductRouteReason.TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE,
                    ),
                    None,
                )

            registrations = self._base_registrations(activate_authority)
            registrations.append(
                self._registration(
                    ProductSegment.P3_PROGRESS,
                    "agent_server.product_p3_text_progress.v1",
                    activate_progress,
                )
            )
            try:
                activation = await ProductCompositionRoot(
                    enabled=True,
                    registrations=registrations,
                ).activate(ProductCompositionContext(routed_session, correlation_id))
            except ProductCompositionActivationError as exc:
                self._progress_generations.pop(key, None)
                self._progress_targets.pop(key, None)
                self._retain_root_cleanup(exc.cleanup_lease)
                logger.exception("[LiveVoiceProduct] P3 progress failed closed")
                return _error_result(
                    request_id,
                    reason="PRODUCT_P3_PROGRESS_ACTIVATION_FAILED",
                )
            except Exception:
                self._progress_generations.pop(key, None)
                self._progress_targets.pop(key, None)
                logger.exception("[LiveVoiceProduct] P3 progress failed closed")
                return _error_result(
                    request_id,
                    reason="PRODUCT_P3_PROGRESS_ACTIVATION_FAILED",
                )
            binding = holder.get("binding")
            progress_lease = holder.get("progress_lease")
            if (
                not isinstance(binding, TaskProgressOriginBinding)
                or not isinstance(progress_lease, TaskProgressReturnLease)
                or activation.lease is None
            ):
                self._progress_generations.pop(key, None)
                self._progress_targets.pop(key, None)
                if activation.lease is not None:
                    try:
                        await activation.lease.close()
                    except ProductCompositionLeaseCloseError as exc:
                        self._retain_root_cleanup(exc.lease)
                        logger.exception(
                            "[LiveVoiceProduct] inactive P3 progress cleanup failed"
                        )
                return _error_result(
                    request_id,
                    reason=state.reason or "PRODUCT_P3_PROGRESS_UNAVAILABLE",
                    manifest=activation.manifest,
                )
            retained = _ProgressRoute(
                binding=binding,
                progress_lease=progress_lease,
                lease=activation.lease,
                manifest=activation.manifest,
                channel_id=channel_id,
                request_id=request_id,
            )
            self._progress_routes[key] = retained
            return _success_result(
                request_id,
                {
                    "status": "active",
                    "replayed": False,
                    "task_id": task_id,
                    "origin_id": origin_id,
                    "generation_id": generation_id,
                    "generation": generation,
                    "voice_progress": "unavailable",
                    "voice_reason": "TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE",
                },
                activation.manifest,
            )

    async def handle_p3_progress_close(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        if not self._settings.p3_text_enabled:
            return _error_result(request_id, reason="PRODUCT_P3_TEXT_DISABLED")
        try:
            _require_exact_params(
                params,
                frozenset(
                    {
                        "auth_token",
                        "session_id",
                        "task_id",
                        "correlation_id",
                        "origin_id",
                        "generation_id",
                        "generation",
                        "claimed_user_id",
                        "claimed_project_id",
                    }
                ),
            )
            self._ensure_running()
            routed_session = _required_text(session_id, "routed_session_id")
            if _required_text(params.get("session_id"), "session_id") != routed_session:
                raise FormalTaskViolation(
                    "PRODUCT_COMPOSITION_SESSION_MISMATCH",
                    "product request does not match its routed session",
                    ErrorCode.PERMISSION_DENIED,
                )
            task_id = _required_text(params.get("task_id"), "task_id")
            correlation_id = _required_text(
                params.get("correlation_id"), "correlation_id"
            )
            origin_id = _required_text(params.get("origin_id"), "origin_id")
            generation_id = _required_text(
                params.get("generation_id"), "generation_id"
            )
            generation = params.get("generation")
            if type(generation) is not int or generation <= 0:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "generation must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            route = self._route_context(
                session_id=routed_session,
                correlation_id=correlation_id,
                params=params,
            )
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )

        async with self._lock:
            if self._stopped:
                return _error_result(
                    request_id, reason="PRODUCT_COMPOSITION_STOPPED"
                )
            key = (routed_session, task_id, origin_id, generation_id)
            state = _AuthorityState()
            authority = await self._authority_registration(
                state=state,
                bearer_token=params.get("auth_token"),
                route=route,
                operation="task.events",
                task_id=task_id,
            )
            if authority.route_fact.truth is not ProductRouteTruth.FORMAL:
                return _error_result(
                    request_id,
                    reason=state.reason or "TRUSTED_AUTHORITY_UNAVAILABLE",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            assert state.canonical is not None
            retained = self._progress_routes.get(key)
            if retained is None:
                if authority.lease is not None:
                    await authority.lease.close()
                return _error_result(
                    request_id,
                    reason="PRODUCT_P3_PROGRESS_ROUTE_NOT_FOUND",
                    code=ErrorCode.NOT_FOUND,
                )
            if (
                retained.binding.correlation_id != correlation_id
                or retained.binding.generation != generation
            ):
                if authority.lease is not None:
                    await authority.lease.close()
                return _error_result(
                    request_id,
                    reason="TASK_PROGRESS_BINDING_MISMATCH",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            if state.canonical.scope != retained.binding.scope:
                if authority.lease is not None:
                    await authority.lease.close()
                return _error_result(
                    request_id,
                    reason="TASK_PROGRESS_BINDING_MISMATCH",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            try:
                await retained.lease.close()
            except ProductCompositionLeaseCloseError:
                return _error_result(
                    request_id,
                    reason="PRODUCT_P3_PROGRESS_CLEANUP_PENDING",
                )
            finally:
                if authority.lease is not None:
                    await authority.lease.close()
            self._progress_routes.pop(key, None)
            self._progress_generations.pop(key, None)
            self._progress_targets.pop(key, None)
            return _success_result(
                request_id,
                {"status": "closed", "task_id": task_id},
                retained.manifest,
            )

    async def close_active_routes(self) -> None:
        """Best-effort reverse cleanup for Gateway loss without stopping registry."""

        async with self._lock:
            failures = False
            for progress_key, progress_retained in reversed(
                tuple(self._progress_routes.items())
            ):
                try:
                    await progress_retained.lease.close()
                except Exception:
                    failures = True
                    logger.exception(
                        "[LiveVoiceProduct] progress disconnect cleanup pending"
                    )
                    continue
                self._progress_routes.pop(progress_key, None)
                self._progress_generations.pop(progress_key, None)
                self._progress_targets.pop(progress_key, None)
            for p2_key, p2_retained in reversed(tuple(self._p2_routes.items())):
                try:
                    await p2_retained.lease.close()
                except Exception:
                    failures = True
                    logger.exception(
                        "[LiveVoiceProduct] P2 disconnect cleanup pending"
                    )
                    continue
                self._p2_routes.pop(p2_key, None)
            remaining_orphans: list[_P2FailedCleanupLease] = []
            for cleanup in self._p2_orphan_cleanups:
                try:
                    await cleanup.close()
                except Exception:
                    failures = True
                    remaining_orphans.append(cleanup)
                    logger.exception(
                        "[LiveVoiceProduct] orphan P2 cleanup pending"
                    )
            self._p2_orphan_cleanups = remaining_orphans
            remaining_roots: list[ProductCompositionLease] = []
            for cleanup in self._root_orphan_cleanups:
                try:
                    await cleanup.close()
                except Exception:
                    failures = True
                    remaining_roots.append(cleanup)
                    logger.exception(
                        "[LiveVoiceProduct] composition root cleanup pending"
                    )
            self._root_orphan_cleanups = remaining_roots
            if failures:
                raise RuntimeError("Live Voice product route cleanup remains pending")

    async def stop(self) -> None:
        self._stopped = True
        await self.close_active_routes()


def create_product_composition_registry_from_environment(
    *,
    p3_composition: P3AuthenticatedComposition | None,
    agent_manager: Any,
    push_text_event: Callable[[dict[str, object]], Awaitable[bool]],
) -> AgentServerProductCompositionRegistry | None:
    """Construct no registry or Adapter unless the master gate is explicit."""

    if not product_composition_enabled_from_environment():
        return None
    if p3_composition is None:
        raise FormalTaskViolation(
            "PRODUCT_TRUSTED_AUTHORITY_UNAVAILABLE",
            "enabled product composition requires authenticated P3 authority",
            ErrorCode.UNAVAILABLE,
        )
    return AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings.from_environment(),
        p3_composition=p3_composition,
        agent_manager=agent_manager,
        push_text_event=push_text_event,
    )


__all__ = [
    "AgentServerProductCompositionRegistry",
    "PRODUCT_COMPOSITION_ENABLE_ENV",
    "PRODUCT_COMPOSITION_METHODS",
    "PRODUCT_P2_ENABLE_ENV",
    "PRODUCT_P3_QUERY_OPERATIONS",
    "PRODUCT_P3_TEXT_ENABLE_ENV",
    "ProductCompositionSettings",
    "create_product_composition_registry_from_environment",
    "product_composition_enabled_from_environment",
]
