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
import secrets
from array import array
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    ErrorCode,
    MAX_SAFE_INTEGER,
    OriginRef,
    ProducerRef,
    ResponseRef,
    TurnCommit,
    TurnCommitLedger,
    canonical_json_bytes,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)

from .agent_conversation_runtime import AgentConversationRuntime
from .formal_task_models import FormalTaskViolation, ResolvedTaskContext
from .interaction_engine import InteractionEnginePort
from .p3_authenticated_composition import (
    P3_MUTATIONS,
    P3AuthenticatedComposition,
    P3RouteResult,
)
from .p3_confirmation import (
    BoundedP3ConfirmationOwner,
    P3_CONFIRMATION_MAX_TTL,
    P3ConfirmationBinding,
    P3ConfirmationOwnerContext,
    TrustedP3ConfirmationIssue,
)
from .p3_product_confirmation import ProductP3ConfirmationForwarder
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
    create_product_composition_manifest,
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
    P2LeaseState,
    P2LeaseCloseStatus,
    ProductP2InteractionAdapter,
)
from .product_p3_text_adapter import (
    ProductP3ProgressCleanupHandle,
    ProductP3ProgressRequest,
    ProductP3QueryRequest,
    ProductP3TextAdapter,
)
from .presentation_ledger import PresentationAck, PresentationSurface
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

PRODUCT_COMPOSITION_ENABLE_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED"
PRODUCT_P2_ENABLE_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED"
PRODUCT_P3_TEXT_ENABLE_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED"
PRODUCT_P3_MUTATION_ENABLE_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED"
PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID_ENV = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID"
)
PRODUCT_P2_RETRIABLE_FAULT_OPERATION_ENV = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_RETRIABLE_FAULT_OPERATION"
)
PRODUCT_P3_STALE_FAULT_REQUEST_ID_ENV = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_STALE_FAULT_REQUEST_ID"
)
PRODUCT_P3_STALE_FAULT_OPERATION_ENV = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_STALE_FAULT_OPERATION"
)
_PRODUCT_P2_PRESENTATION_ACK_OPERATION = "live_voice.composition.p2.presentation.ack"
_PRODUCT_P3_RETRY_OPERATION = "task.retry"

PRODUCT_COMPOSITION_METHODS = frozenset(
    {
        "live_voice.composition.p2.activate",
        "live_voice.composition.p2.close",
        "live_voice.composition.p2.submit",
        "live_voice.composition.p2.notification.next",
        _PRODUCT_P2_PRESENTATION_ACK_OPERATION,
        "live_voice.composition.p2.barge_in",
        "live_voice.composition.p3.confirmation.issue",
        "live_voice.composition.p3.mutate",
        "live_voice.composition.p3.progress.activate",
        "live_voice.composition.p3.progress.close",
        "live_voice.composition.p3.progress.ack",
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
class ProductP2RetriableFaultPlan:
    """One immutable externally selected W2 fault, never a client claim."""

    request_id: str
    operation: str

    def __post_init__(self) -> None:
        request_id = self.request_id
        if (
            type(request_id) is not str
            or not request_id
            or request_id != request_id.strip()
            or len(request_id) > 256
            or any(character.isspace() for character in request_id)
        ):
            raise ValueError("P2 retriable fault request_id must be an opaque label")
        try:
            request_id.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ValueError(
                "P2 retriable fault request_id must contain Unicode scalar values"
            ) from exc
        if self.operation != _PRODUCT_P2_PRESENTATION_ACK_OPERATION:
            raise ValueError(
                "P2 retriable fault operation must be the exact presentation ACK"
            )


def _p2_retriable_fault_plan_from_environment() -> ProductP2RetriableFaultPlan | None:
    request_id = os.getenv(PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID_ENV)
    operation = os.getenv(PRODUCT_P2_RETRIABLE_FAULT_OPERATION_ENV)
    if request_id is None and operation is None:
        return None
    if request_id is None or operation is None:
        raise ValueError(
            "P2 retriable fault plan requires exact request_id and operation"
        )
    return ProductP2RetriableFaultPlan(request_id=request_id, operation=operation)


@dataclass(frozen=True, slots=True)
class ProductP3StaleFaultPlan:
    """One immutable server-owned W2 stale retry, never a client claim."""

    request_id: str
    operation: str

    def __post_init__(self) -> None:
        request_id = self.request_id
        if (
            type(request_id) is not str
            or not request_id
            or request_id != request_id.strip()
            or len(request_id) > 256
            or any(character.isspace() for character in request_id)
        ):
            raise ValueError("P3 stale fault request_id must be an opaque label")
        try:
            request_id.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ValueError(
                "P3 stale fault request_id must contain Unicode scalar values"
            ) from exc
        if self.operation != _PRODUCT_P3_RETRY_OPERATION:
            raise ValueError("P3 stale fault operation must be the exact task.retry")


def _p3_stale_fault_plan_from_environment() -> ProductP3StaleFaultPlan | None:
    request_id = os.getenv(PRODUCT_P3_STALE_FAULT_REQUEST_ID_ENV)
    operation = os.getenv(PRODUCT_P3_STALE_FAULT_OPERATION_ENV)
    if request_id is None and operation is None:
        return None
    if request_id is None or operation is None:
        raise ValueError("P3 stale fault plan requires exact request_id and operation")
    return ProductP3StaleFaultPlan(request_id=request_id, operation=operation)


@dataclass(frozen=True, slots=True)
class ProductCompositionSettings:
    p2_enabled: bool
    p3_text_enabled: bool
    p3_mutation_enabled: bool = False
    p2_retriable_fault_plan: ProductP2RetriableFaultPlan | None = None
    p3_stale_fault_plan: ProductP3StaleFaultPlan | None = None

    @classmethod
    def from_environment(cls) -> ProductCompositionSettings:
        return cls(
            p2_enabled=_is_enabled(os.getenv(PRODUCT_P2_ENABLE_ENV)),
            p3_text_enabled=_is_enabled(os.getenv(PRODUCT_P3_TEXT_ENABLE_ENV)),
            p3_mutation_enabled=_is_enabled(os.getenv(PRODUCT_P3_MUTATION_ENABLE_ENV)),
            p2_retriable_fault_plan=_p2_retriable_fault_plan_from_environment(),
            p3_stale_fault_plan=_p3_stale_fault_plan_from_environment(),
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
    activation_lease: P2ActivationLease
    lease: ProductCompositionLease
    manifest: ProductCompositionManifest
    notification_replay_floor: int = 0
    notification_admitted_sequence: int = 0


@dataclass(frozen=True, slots=True)
class _ClosedP2Route:
    binding: P2InteractionBinding
    manifest: ProductCompositionManifest
    notification_replay_floor: int = 0


@dataclass(slots=True)
class _ProgressRoute:
    binding: TaskProgressOriginBinding
    progress_lease: TaskProgressReturnLease
    lease: ProductCompositionLease
    manifest: ProductCompositionManifest
    channel_id: str
    request_id: str


@dataclass(frozen=True, slots=True)
class _ClosedProgressRoute:
    binding: TaskProgressOriginBinding
    channel_id: str
    manifest: ProductCompositionManifest
    deliveries: dict[str, _ProgressDelivery]


@dataclass(frozen=True, slots=True)
class _ProgressTarget:
    channel_id: str
    request_id: str
    correlation_id: str
    generation: int


@dataclass(slots=True)
class _ProgressDelivery:
    delivery_id: str
    attempt_id: str
    source_event_id: str
    progress_event_id: str
    seq: int
    evidence_id: str
    delivered: bool = False
    acknowledged: bool = False


@dataclass(slots=True)
class _RetainedProductOperation:
    fingerprint: bytes
    task: asyncio.Task[P3RouteResult]
    p2_binding: P2InteractionBinding | None = None
    p3_binding: P3ConfirmationBinding | None = None
    operation_sequence: int | None = None


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


def _required_content(value: object, field: str, *, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise FormalTaskViolation(
            "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
            f"{field} must be non-empty bounded text",
            ErrorCode.INVALID_ARGUMENT,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise FormalTaskViolation(
            "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
            f"{field} must contain Unicode scalar values",
            ErrorCode.INVALID_ARGUMENT,
        ) from exc
    return value


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

    _CLOSED_ROUTE_CAPACITY = 128
    _PROGRESS_DELIVERY_CAPACITY = 128
    _PROGRESS_GENERATION_CAPACITY = 128
    _PRODUCT_OPERATION_CAPACITY = 128
    _TURN_COMMIT_CAPACITY = 128
    _TURN_COMMIT_CAPACITY_PER_ROUTE = 32

    def __init__(
        self,
        *,
        settings: ProductCompositionSettings,
        p3_composition: P3AuthenticatedComposition,
        agent_manager: Any,
        push_text_event: Callable[[dict[str, object]], Awaitable[bool]],
        p3_confirmation_owner: BoundedP3ConfirmationOwner | None = None,
        p3_confirmation_forwarder: ProductP3ConfirmationForwarder | None = None,
        commit_ledger: TurnCommitLedger | None = None,
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
        self._p3_confirmation_owner = p3_confirmation_owner
        self._p3_confirmation_forwarder = p3_confirmation_forwarder
        self._commit_ledger = commit_ledger or TurnCommitLedger(
            capacity=self._TURN_COMMIT_CAPACITY
        )
        self._p3_confirmation_generation = (
            secrets.randbits(52) + 1
            if settings.p3_mutation_enabled
            and p3_confirmation_owner is not None
            and p3_confirmation_forwarder is not None
            else None
        )
        self._lock = asyncio.Lock()
        self._p3_operation_lock = asyncio.Lock()
        self._stopped = False
        self._p2_routes: dict[tuple[str, str], _P2Route] = {}
        self._closed_p2_routes: dict[tuple[str, str], _ClosedP2Route] = {}
        self._progress_routes: dict[tuple[str, str, str, str], _ProgressRoute] = {}
        self._closed_progress_routes: dict[
            tuple[str, str, str, str, int], _ClosedProgressRoute
        ] = {}
        self._progress_generations: dict[tuple[str, str, str, str], int] = {}
        self._progress_targets: dict[tuple[str, str, str, str], _ProgressTarget] = {}
        self._progress_deliveries: dict[
            tuple[str, str, str, str], dict[str, _ProgressDelivery]
        ] = {}
        self._pending_p2_agents: dict[tuple[str, str, str, int], Any] = {}
        self._p2_orphan_cleanups: list[_P2FailedCleanupLease] = []
        self._root_orphan_cleanups: list[ProductCompositionLease] = []
        self._p2_submit_operations: dict[str, _RetainedProductOperation] = {}
        self._pending_turn_commits_by_commit: dict[str, TurnCommit] = {}
        self._pending_turn_commits_by_turn: dict[str, TurnCommit] = {}
        self._pending_voice_commit_routes: dict[str, tuple[str, str]] = {}
        self._accepted_turn_commits_by_commit: dict[str, TurnCommit] = {}
        self._accepted_turn_commits_by_turn: dict[str, TurnCommit] = {}
        self._accepted_voice_commit_routes: dict[str, tuple[str, str]] = {}
        self._p2_notification_operations: dict[str, _RetainedProductOperation] = {}
        self._p2_ack_operations: dict[str, _RetainedProductOperation] = {}
        self._p2_barge_operations: dict[str, _RetainedProductOperation] = {}
        self._p2_retriable_fault_consumed = False
        self._p3_stale_fault_consumed = False
        self._p3_issue_operations: dict[str, _RetainedProductOperation] = {}
        self._p3_mutation_operations: dict[str, _RetainedProductOperation] = {}
        # Fixed-size fail-closed membership fence: evicted request IDs can be
        # rejected forever during this registry lifetime without unbounded RAM.
        self._evicted_operation_replay_fence = bytearray(1 << 20)
        # Conservative max sketches preserve closed-generation high-water after
        # exact tombstones are evicted. Collisions can only fail closed.
        self._closed_p2_generation_fence = tuple(
            array("Q", [0]) * (1 << 15) for _ in range(4)
        )

        disabled_service = ProductAuthorityService(enabled=False, resolver=None)
        self._p2_adapter = ProductP2InteractionAdapter(
            enabled=settings.p2_enabled,
            authority_adapter=P2AuthorityAdapter(disabled_service),
            runtime_factory=self._create_p2_runtime,
            interaction_engine_factory=lambda _context, _binding: InteractionEnginePort(
                frozenset(
                    {
                        "playback.stop",
                        "response.cancel",
                        "round.cancel",
                        "task.cancel",
                    }
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

    @property
    def p3_mutation_enabled(self) -> bool:
        return self._settings.p3_mutation_enabled

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

    def _retain_root_cleanup(self, cleanup: ProductCompositionLease | None) -> None:
        if cleanup is not None and all(
            retained is not cleanup for retained in self._root_orphan_cleanups
        ):
            self._root_orphan_cleanups.append(cleanup)

    def _retain_closed_p2_route(
        self,
        key: tuple[str, str],
        route: _ClosedP2Route,
    ) -> None:
        self._record_closed_p2_generation(key, route.binding.activation_generation)
        if (
            key not in self._closed_p2_routes
            and len(self._closed_p2_routes) >= self._CLOSED_ROUTE_CAPACITY
        ):
            self._closed_p2_routes.pop(next(iter(self._closed_p2_routes)))
        self._closed_p2_routes[key] = route

    def _closed_p2_generation_indices(
        self,
        key: tuple[str, str],
    ) -> tuple[int, int, int, int]:
        digest = hashlib.sha256(f"{key[0]}\0{key[1]}".encode("utf-8")).digest()
        capacity = len(self._closed_p2_generation_fence[0])
        return (
            int.from_bytes(digest[0:4], "big") % capacity,
            int.from_bytes(digest[4:8], "big") % capacity,
            int.from_bytes(digest[8:12], "big") % capacity,
            int.from_bytes(digest[12:16], "big") % capacity,
        )

    def _record_closed_p2_generation(
        self,
        key: tuple[str, str],
        generation: int,
    ) -> None:
        bounded_generation = min(generation, (1 << 64) - 1)
        for fence, index in zip(
            self._closed_p2_generation_fence,
            self._closed_p2_generation_indices(key),
            strict=True,
        ):
            fence[index] = max(fence[index], bounded_generation)

    def _closed_p2_generation_high_water(self, key: tuple[str, str]) -> int:
        return min(
            fence[index]
            for fence, index in zip(
                self._closed_p2_generation_fence,
                self._closed_p2_generation_indices(key),
                strict=True,
            )
        )

    def _retain_closed_progress_route(
        self,
        key: tuple[str, str, str, str, int],
        route: _ClosedProgressRoute,
    ) -> None:
        if (
            key not in self._closed_progress_routes
            and len(self._closed_progress_routes) >= self._CLOSED_ROUTE_CAPACITY
        ):
            evictable_key = next(
                (
                    retained_key
                    for retained_key, retained in self._closed_progress_routes.items()
                    if all(
                        delivery.acknowledged
                        for delivery in retained.deliveries.values()
                    )
                ),
                None,
            )
            if evictable_key is None:
                raise RuntimeError(
                    "closed progress route capacity has no safe eviction"
                )
            self._closed_progress_routes.pop(evictable_key)
        self._closed_progress_routes[key] = route

    def _archive_progress_route(
        self,
        key: tuple[str, str, str, str],
        retained: _ProgressRoute,
    ) -> bool:
        deliveries = self._progress_deliveries.get(key, {})
        closed_key = (*key, retained.binding.generation)
        try:
            self._retain_closed_progress_route(
                closed_key,
                _ClosedProgressRoute(
                    binding=retained.binding,
                    channel_id=retained.channel_id,
                    manifest=retained.manifest,
                    deliveries=deliveries,
                ),
            )
        except RuntimeError:
            return False
        self._progress_routes.pop(key, None)
        self._progress_targets.pop(key, None)
        self._progress_deliveries.pop(key, None)
        return True

    def _admit_progress_generation_key(
        self,
        key: tuple[str, str, str, str],
    ) -> bool:
        if key in self._progress_generations:
            return True
        if len(self._progress_generations) < self._PROGRESS_GENERATION_CAPACITY:
            return True
        for retained_key in tuple(self._progress_generations):
            if retained_key in self._progress_routes:
                continue
            closed_keys = tuple(
                closed_key
                for closed_key in self._closed_progress_routes
                if closed_key[:4] == retained_key
            )
            if any(
                not all(
                    delivery.acknowledged
                    for delivery in self._closed_progress_routes[
                        closed_key
                    ].deliveries.values()
                )
                for closed_key in closed_keys
            ):
                continue
            for closed_key in closed_keys:
                self._closed_progress_routes.pop(closed_key, None)
            self._progress_generations.pop(retained_key, None)
            return True
        return False

    @classmethod
    def _reserve_progress_delivery(
        cls,
        deliveries: dict[str, _ProgressDelivery],
        delivery: _ProgressDelivery,
    ) -> _ProgressDelivery:
        existing = deliveries.get(delivery.delivery_id)
        if existing is not None:
            return existing
        if len(deliveries) >= cls._PROGRESS_DELIVERY_CAPACITY:
            acknowledged_id = next(
                (
                    delivery_id
                    for delivery_id, retained in deliveries.items()
                    if retained.acknowledged
                ),
                None,
            )
            if acknowledged_id is None:
                raise RuntimeError(
                    "text progress delivery capacity has no safe eviction"
                )
            deliveries.pop(acknowledged_id)
        deliveries[delivery.delivery_id] = delivery
        return delivery

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
        source_event = event.source_event.to_dict()
        progress_event = event.progress_event.to_dict()
        source_event_id = _required_text(
            source_event.get("event_id"), "source_event.event_id"
        )
        progress_event_id = _required_text(
            progress_event.get("event_id"), "progress_event.event_id"
        )
        seq = source_event.get("seq")
        if type(seq) is not int or seq < 0 or progress_event.get("seq") != seq:
            raise RuntimeError("text progress delivery sequence is invalid")
        delivery_id = hashlib.sha256(
            canonical_json_bytes(
                {
                    "session_id": binding.session_id,
                    "task_id": binding.task_id,
                    "attempt_id": event.task_event.attempt_id,
                    "correlation_id": binding.correlation_id,
                    "origin_id": binding.origin_id,
                    "generation_id": binding.generation_id,
                    "generation": binding.generation,
                    "source_event_id": source_event_id,
                    "progress_event_id": progress_event_id,
                    "seq": seq,
                    "evidence_id": event.evidence_id,
                }
            )
        ).hexdigest()
        deliveries = self._progress_deliveries.setdefault(key, {})
        previously_delivered = bool(
            deliveries.get(delivery_id) and deliveries[delivery_id].delivered
        )
        delivery = self._reserve_progress_delivery(
            deliveries,
            _ProgressDelivery(
                delivery_id=delivery_id,
                attempt_id=event.task_event.attempt_id,
                source_event_id=source_event_id,
                progress_event_id=progress_event_id,
                seq=seq,
                evidence_id=event.evidence_id,
            ),
        )
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
                    "delivery_id": delivery_id,
                    "source_event": source_event,
                    "progress_event": progress_event,
                    "evidence_id": event.evidence_id,
                },
                "is_complete": False,
            }
        )
        if delivered is not True:
            if not previously_delivered and deliveries.get(delivery_id) is delivery:
                deliveries.pop(delivery_id, None)
            raise RuntimeError("text progress Web sink is unavailable")
        delivery.delivered = True

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

    def _advance_notification_replay_floor(
        self,
        entry: _RetainedProductOperation,
    ) -> None:
        """Fence an evicted notification poll from consuming a later result."""

        binding = entry.p2_binding
        sequence = entry.operation_sequence
        if binding is None or sequence is None:
            return
        key = (binding.session_id, binding.interaction_id)
        active = self._p2_routes.get(key)
        if active is not None and active.binding == binding:
            active.notification_replay_floor = max(
                active.notification_replay_floor,
                sequence,
            )
        closed = self._closed_p2_routes.get(key)
        if closed is not None and closed.binding == binding:
            self._closed_p2_routes[key] = _ClosedP2Route(
                closed.binding,
                closed.manifest,
                max(closed.notification_replay_floor, sequence),
            )

    def _evict_completed_product_operation(
        self,
        ledger: dict[str, _RetainedProductOperation],
        *,
        notification: bool = False,
        namespace: str | None = None,
    ) -> bool:
        """Reclaim one completed entry without duplicating an in-flight effect."""

        for retained_request_id, entry in tuple(ledger.items()):
            if not entry.task.done():
                continue
            ledger.pop(retained_request_id, None)
            if notification:
                self._advance_notification_replay_floor(entry)
            elif namespace is not None:
                self._mark_evicted_product_request(namespace, retained_request_id)
            return True
        return False

    def _evicted_product_request_indices(
        self,
        namespace: str,
        request_id: str,
    ) -> tuple[int, int, int, int]:
        digest = hashlib.sha256(f"{namespace}\0{request_id}".encode("utf-8")).digest()
        bit_capacity = len(self._evicted_operation_replay_fence) * 8
        return (
            int.from_bytes(digest[0:4], "big") % bit_capacity,
            int.from_bytes(digest[4:8], "big") % bit_capacity,
            int.from_bytes(digest[8:12], "big") % bit_capacity,
            int.from_bytes(digest[12:16], "big") % bit_capacity,
        )

    def _mark_evicted_product_request(self, namespace: str, request_id: str) -> None:
        for index in self._evicted_product_request_indices(namespace, request_id):
            self._evicted_operation_replay_fence[index >> 3] |= 1 << (index & 7)

    def _require_product_request_not_evicted(
        self,
        namespace: str,
        request_id: str,
    ) -> None:
        if all(
            self._evicted_operation_replay_fence[index >> 3] & (1 << (index & 7))
            for index in self._evicted_product_request_indices(namespace, request_id)
        ):
            raise FormalTaskViolation(
                "PRODUCT_OPERATION_REPLAY_EXPIRED",
                "the completed operation replay has expired",
                ErrorCode.CONFLICT,
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
            activation_id = _required_text(params.get("activation_id"), "activation_id")
            generation = params.get("activation_generation")
            if (
                type(generation) is not int
                or generation <= 0
                or generation > MAX_SAFE_INTEGER
            ):
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "activation_generation must be a positive safe integer",
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
                return _error_result(request_id, reason="PRODUCT_COMPOSITION_STOPPED")
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
                if replay_authority.route_fact.truth is not ProductRouteTruth.FORMAL:
                    return _error_result(
                        request_id,
                        reason=(replay_state.reason or "TRUSTED_AUTHORITY_UNAVAILABLE"),
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
                if existing.activation_lease.snapshot().state is P2LeaseState.OPEN:
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
                                "session_id": routed_session,
                                "correlation_id": correlation_id,
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
                if replay_authority.lease is not None:
                    await replay_authority.lease.close()
                try:
                    await existing.lease.close()
                except ProductCompositionLeaseCloseError as exc:
                    self._retain_root_cleanup(exc.lease)
                    return _error_result(
                        request_id,
                        reason="PRODUCT_P2_CLEANUP_PENDING",
                        code=ErrorCode.UNAVAILABLE,
                        manifest=existing.manifest,
                    )
                self._p2_routes.pop(key, None)
                self._retain_closed_p2_route(
                    key,
                    _ClosedP2Route(
                        existing.binding,
                        existing.manifest,
                        existing.notification_replay_floor,
                    ),
                )

            closed = self._closed_p2_routes.get(key)
            if generation <= self._closed_p2_generation_high_water(key):
                return _error_result(
                    request_id,
                    reason="ACTIVATION_GENERATION_STALE",
                    code=ErrorCode.CONFLICT,
                    manifest=None if closed is None else closed.manifest,
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
                            unpin = getattr(self._agent_manager, "unpin_agent", None)
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
                    holder["activation_lease"] = result.lease
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
            activation_lease = holder.get("activation_lease")
            if (
                not isinstance(binding, P2InteractionBinding)
                or not isinstance(activation_lease, P2ActivationLease)
                or activation.lease is None
            ):
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
                activation_lease=activation_lease,
                lease=activation.lease,
                manifest=activation.manifest,
            )
            self._closed_p2_routes.pop(key, None)
            return _success_result(
                request_id,
                {
                    "status": "active",
                    "replayed": False,
                    "session_id": routed_session,
                    "correlation_id": correlation_id,
                    "interaction_id": binding.interaction_id,
                    "activation_id": binding.activation_id,
                    "activation_generation": binding.activation_generation,
                },
                activation.manifest,
            )

    @staticmethod
    def _parse_p2_route_binding(
        params: Mapping[str, object],
        *,
        session_id: str | None,
    ) -> tuple[str, str, str, str, int, AuthorityRouteContext]:
        routed_session = _required_text(session_id, "routed_session_id")
        if _required_text(params.get("session_id"), "session_id") != routed_session:
            raise FormalTaskViolation(
                "PRODUCT_COMPOSITION_SESSION_MISMATCH",
                "product request does not match its routed session",
                ErrorCode.PERMISSION_DENIED,
            )
        correlation_id = _required_text(params.get("correlation_id"), "correlation_id")
        interaction_id = _required_text(params.get("interaction_id"), "interaction_id")
        activation_id = _required_text(params.get("activation_id"), "activation_id")
        generation = params.get("activation_generation")
        if (
            type(generation) is not int
            or generation <= 0
            or generation > MAX_SAFE_INTEGER
        ):
            raise FormalTaskViolation(
                "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                "activation_generation must be a positive safe integer",
                ErrorCode.INVALID_ARGUMENT,
            )
        route = AgentServerProductCompositionRegistry._route_context(
            session_id=routed_session,
            correlation_id=correlation_id,
            params=params,
        )
        return (
            routed_session,
            correlation_id,
            interaction_id,
            activation_id,
            generation,
            route,
        )

    async def _require_active_p2_route_locked(
        self,
        *,
        params: Mapping[str, object],
        routed_session: str,
        correlation_id: str,
        interaction_id: str,
        activation_id: str,
        generation: int,
        route: AuthorityRouteContext,
    ) -> _P2Route:
        retained = self._p2_routes.get((routed_session, interaction_id))
        if retained is None:
            raise FormalTaskViolation(
                "PRODUCT_P2_ROUTE_NOT_FOUND",
                "product P2 route is not active",
                ErrorCode.NOT_FOUND,
            )
        await self._require_p2_binding_authority_locked(
            params=params,
            routed_session=routed_session,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            activation_id=activation_id,
            generation=generation,
            route=route,
            binding=retained.binding,
        )
        return retained

    async def _require_p2_binding_authority_locked(
        self,
        *,
        params: Mapping[str, object],
        routed_session: str,
        correlation_id: str,
        interaction_id: str,
        activation_id: str,
        generation: int,
        route: AuthorityRouteContext,
        binding: P2InteractionBinding,
    ) -> None:
        """Reauthenticate an exact active or tombstoned operation binding."""

        state = _AuthorityState()
        authority = await self._authority_registration(
            state=state,
            bearer_token=params.get("auth_token"),
            route=route,
            operation="agent.chat",
            task_id=None,
        )
        try:
            if authority.route_fact.truth is not ProductRouteTruth.FORMAL:
                raise FormalTaskViolation(
                    state.reason or "TRUSTED_AUTHORITY_UNAVAILABLE",
                    "trusted P2 authority is unavailable",
                    ErrorCode.PERMISSION_DENIED,
                )
            assert state.canonical is not None
            if (
                binding.session_id != routed_session
                or binding.interaction_id != interaction_id
                or binding.correlation_id != correlation_id
                or binding.activation_id != activation_id
                or binding.activation_generation != generation
                or binding.scope != state.canonical.scope
            ):
                raise FormalTaskViolation(
                    "ACTIVATION_BINDING_MISMATCH",
                    "product P2 request does not match the current activation",
                    ErrorCode.PERMISSION_DENIED,
                )
        finally:
            if authority.lease is not None:
                await authority.lease.close()

    async def _run_p2_submit(
        self,
        *,
        retained: _P2Route,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        channel_id: str,
        dispatch_target: str,
        route_key: tuple[str, str],
    ) -> P3RouteResult:
        try:
            common = {
                "session_id": retained.binding.session_id,
                "correlation_id": retained.binding.correlation_id,
                "interaction_id": retained.binding.interaction_id,
                "activation_id": retained.binding.activation_id,
                "activation_generation": retained.binding.activation_generation,
            }
            if dispatch_target == "task":
                async with self._lock:
                    if self._p2_routes.get(route_key) is not retained:
                        raise FormalTaskViolation(
                            "PRODUCT_P2_ROUTE_CLOSED",
                            "voice task origin cannot outlive its exact P2 route",
                            ErrorCode.PERMISSION_DENIED,
                        )
                    if self._commit_ledger.accept(commit) is not True:
                        raise FormalTaskViolation(
                            "TURN_COMMIT_ALREADY_SUBMITTED",
                            "a committed turn cannot be submitted under a second request",
                            ErrorCode.CONFLICT,
                        )
                try:
                    response_ref = await retained.activation_lease.accept_task_origin(
                        retained.binding,
                        request_id=request_id,
                        response_id=response_id,
                        correlation_id=correlation_id,
                        commit=commit,
                    )
                except asyncio.CancelledError:
                    return _error_result(
                        request_id,
                        reason="TASK_ORIGIN_RESULT_UNKNOWN",
                        code=ErrorCode.RESULT_UNKNOWN,
                        message=(
                            "Task-origin acceptance was interrupted after admission"
                        ),
                        manifest=retained.manifest,
                    )
                except Exception as exc:
                    if getattr(exc, "code", None) is not ErrorCode.RESULT_UNKNOWN:
                        self._commit_ledger.release_origin(
                            OriginRef(
                                "committed_turn", commit.turn_id, commit.commit_id
                            ),
                            commit.scope,
                        )
                    raise
                # accept_task_origin linearizes under the lease operation lock.
                # Once it returns, a concurrent close may be waiting for that
                # lock but cannot have closed the runtime. Complete these
                # event-loop-owned maps synchronously, before yielding, so close
                # observes and retires the accepted origin normally instead of
                # rewriting an irreversible canonical success as route-closed.
                self._accepted_turn_commits_by_commit[commit.commit_id] = commit
                self._accepted_turn_commits_by_turn[commit.turn_id] = commit
                self._accepted_voice_commit_routes[commit.commit_id] = route_key
                if self._pending_turn_commits_by_commit.get(commit.commit_id) is commit:
                    self._pending_turn_commits_by_commit.pop(commit.commit_id, None)
                if self._pending_turn_commits_by_turn.get(commit.turn_id) is commit:
                    self._pending_turn_commits_by_turn.pop(commit.turn_id, None)
                self._pending_voice_commit_routes.pop(commit.commit_id, None)
                return _success_result(
                    request_id,
                    {
                        "status": "task_origin_accepted",
                        **common,
                        "turn_id": commit.turn_id,
                        "commit_id": commit.commit_id,
                        "response": {
                            "interaction_id": response_ref.interaction_id,
                            "response_id": response_ref.response_id,
                            "response_generation": response_ref.response_generation,
                        },
                    },
                    retained.manifest,
                )
            handle = await retained.activation_lease.submit_committed_turn(
                retained.binding,
                request_id=request_id,
                response_id=response_id,
                correlation_id=correlation_id,
                commit=commit,
                context=FormalContextSnapshot(retained.binding.scope),
                channel_id=channel_id,
            )
            return _success_result(
                request_id,
                {
                    "status": "round_accepted",
                    **common,
                    "request_id": handle.request_id,
                    "round_id": handle.round_id,
                    "response": {
                        "interaction_id": handle.response_ref.interaction_id,
                        "response_id": handle.response_ref.response_id,
                        "response_generation": handle.response_ref.response_generation,
                    },
                },
                retained.manifest,
            )
        except Exception as exc:  # noqa: BLE001 - retained stable outcome
            return _error_result(
                request_id,
                reason=getattr(exc, "reason", "PRODUCT_P2_SUBMISSION_FAILED"),
                code=getattr(exc, "code", ErrorCode.UNAVAILABLE),
                message=str(exc),
                manifest=retained.manifest,
            )
        finally:
            async with self._lock:
                if self._pending_turn_commits_by_commit.get(commit.commit_id) is commit:
                    self._pending_turn_commits_by_commit.pop(commit.commit_id, None)
                if self._pending_turn_commits_by_turn.get(commit.turn_id) is commit:
                    self._pending_turn_commits_by_turn.pop(commit.turn_id, None)
                self._pending_voice_commit_routes.pop(commit.commit_id, None)

    def _reserve_turn_commit_locked(
        self, commit: TurnCommit, route_key: tuple[str, str]
    ) -> None:
        existing = (
            self._pending_turn_commits_by_commit.get(commit.commit_id)
            or self._pending_turn_commits_by_turn.get(commit.turn_id)
            or self._accepted_turn_commits_by_commit.get(commit.commit_id)
            or self._accepted_turn_commits_by_turn.get(commit.turn_id)
        )
        if existing is not None:
            reason = (
                "TURN_COMMIT_ALREADY_SUBMITTED"
                if existing.canonical_bytes() == commit.canonical_bytes()
                else "TURN_COMMIT_CONFLICT"
            )
            raise FormalTaskViolation(
                reason,
                "commit_id and turn_id are immutable and may submit only once",
                ErrorCode.CONFLICT,
            )
        retained_count = len(self._pending_turn_commits_by_commit) + len(
            self._accepted_turn_commits_by_commit
        )
        if retained_count >= self._TURN_COMMIT_CAPACITY:
            raise FormalTaskViolation(
                "PRODUCT_TURN_COMMIT_LEDGER_FULL",
                "bounded committed-turn authority is full",
                ErrorCode.UNAVAILABLE,
            )
        retained_for_route = sum(
            retained_route == route_key
            for retained_route in self._pending_voice_commit_routes.values()
        ) + sum(
            retained_route == route_key
            for retained_route in self._accepted_voice_commit_routes.values()
        )
        if retained_for_route >= self._TURN_COMMIT_CAPACITY_PER_ROUTE:
            raise FormalTaskViolation(
                "PRODUCT_ROUTE_TURN_COMMIT_LEDGER_FULL",
                "bounded committed-turn authority for this route is full",
                ErrorCode.UNAVAILABLE,
            )
        self._pending_turn_commits_by_commit[commit.commit_id] = commit
        self._pending_turn_commits_by_turn[commit.turn_id] = commit
        self._pending_voice_commit_routes[commit.commit_id] = route_key

    def _release_voice_origin_locked(self, commit: TurnCommit) -> None:
        self._accepted_turn_commits_by_commit.pop(commit.commit_id, None)
        self._accepted_turn_commits_by_turn.pop(commit.turn_id, None)
        self._accepted_voice_commit_routes.pop(commit.commit_id, None)
        self._commit_ledger.release_origin(
            OriginRef("committed_turn", commit.turn_id, commit.commit_id),
            commit.scope,
        )

    def _release_voice_origins_for_route_locked(
        self, route_key: tuple[str, str]
    ) -> None:
        for commit_id, retained_route in tuple(
            self._accepted_voice_commit_routes.items()
        ):
            if retained_route != route_key:
                continue
            commit = self._accepted_turn_commits_by_commit.get(commit_id)
            if commit is not None:
                self._release_voice_origin_locked(commit)

    @staticmethod
    def _gateway_voice_provenance(
        claim: object,
        *,
        session_id: str,
        correlation_id: str,
        interaction_id: str,
        turn_id: str,
        commit_id: str,
        text: str,
        channel_id: str,
    ) -> dict[str, object]:
        if not isinstance(claim, Mapping) or set(claim) != {
            "kind",
            "speech_operation_id",
            "capture_id",
            "capture_generation",
            "session_id",
            "correlation_id",
            "interaction_id",
            "turn_id",
            "commit_id",
            "text_sha256",
            "critical_policy",
        }:
            raise FormalTaskViolation(
                "FORMAL_SPEECH_RECEIPT_REQUIRED",
                "voice dispatch requires a Gateway-owned formal speech claim",
                ErrorCode.PERMISSION_DENIED,
            )
        expected = {
            "kind": "formal_speech_recognition",
            "session_id": session_id,
            "correlation_id": correlation_id,
            "interaction_id": interaction_id,
            "turn_id": turn_id,
            "commit_id": commit_id,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
        if channel_id != "web" or any(claim.get(key) != value for key, value in expected.items()):
            raise FormalTaskViolation(
                "FORMAL_SPEECH_RECEIPT_MISMATCH",
                "voice dispatch does not match its Gateway speech claim",
                ErrorCode.PERMISSION_DENIED,
            )
        operation_id = _required_text(
            claim.get("speech_operation_id"), "speech_operation_id"
        )
        capture_id = _required_text(claim.get("capture_id"), "capture_id")
        critical_policy = claim.get("critical_policy")
        if critical_policy not in {"eligible", "confirmed"}:
            raise FormalTaskViolation(
                "CRITICAL_TOKEN_POLICY_REQUIRED",
                "voice dispatch did not pass the Gateway critical-token policy",
                ErrorCode.PERMISSION_DENIED,
            )
        generation = claim.get("capture_generation")
        if type(generation) is not int or generation < 0 or generation > MAX_SAFE_INTEGER:
            raise FormalTaskViolation(
                "FORMAL_SPEECH_RECEIPT_MISMATCH",
                "voice dispatch has an invalid capture generation",
                ErrorCode.PERMISSION_DENIED,
            )
        return {
            "provider": "formal-batch-speech",
            "kind": "committed_speech",
            "speech_operation_id": operation_id,
            "capture_id": capture_id,
            "capture_generation": generation,
            "critical_token_policy": critical_policy,
        }

    async def handle_p2_submit(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
        channel_id: str,
    ) -> P3RouteResult:
        """Submit browser text as a server-scoped canonical TurnCommit."""

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
                        "commit_id",
                        "turn_id",
                        "response_id",
                        "committed_at",
                        "text",
                        "dispatch_target",
                        "gateway_voice_claim",
                    }
                ),
            )
            self._ensure_running()
            parsed = self._parse_p2_route_binding(params, session_id=session_id)
            commit_id = _required_text(params.get("commit_id"), "commit_id")
            turn_id = _required_text(params.get("turn_id"), "turn_id")
            response_id = _required_text(params.get("response_id"), "response_id")
            committed_at = _required_text(
                params.get("committed_at"), "committed_at", maximum=64
            )
            text_value = _required_content(params.get("text"), "text", maximum=100_000)
            routed_session, correlation_id, interaction_id, _, _, _ = parsed
            dispatch_target = str(params.get("dispatch_target") or "agent")
            if dispatch_target not in {"agent", "task"}:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_DISPATCH_TARGET",
                    "product committed input must target Agent or Task exactly once",
                    ErrorCode.INVALID_ARGUMENT,
                )
            voice_claim = params.get("gateway_voice_claim")
            if dispatch_target == "task" and voice_claim is None:
                raise FormalTaskViolation(
                    "FORMAL_SPEECH_RECEIPT_REQUIRED",
                    "Task-bound voice input requires formal Speech provenance",
                    ErrorCode.PERMISSION_DENIED,
                )
            provenance = (
                self._gateway_voice_provenance(
                    voice_claim,
                    session_id=routed_session,
                    correlation_id=correlation_id,
                    interaction_id=interaction_id,
                    turn_id=turn_id,
                    commit_id=commit_id,
                    text=text_value,
                    channel_id=channel_id,
                )
                if voice_claim is not None
                else {"provider": "product.web.text", "kind": "committed_text"}
            )
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )

        try:
            fingerprint = hashlib.sha256(
                canonical_json_bytes(
                    {
                        **{
                            key: value
                            for key, value in params.items()
                            if key != "auth_token"
                        },
                        "channel_id": channel_id,
                    }
                )
            ).digest()
            async with self._lock:
                existing = self._p2_submit_operations.get(request_id)
                if existing is not None:
                    if existing.p2_binding is None:
                        raise RuntimeError("retained P2 submission lost its binding")
                    await self._require_p2_binding_authority_locked(
                        params=params,
                        routed_session=parsed[0],
                        correlation_id=parsed[1],
                        interaction_id=parsed[2],
                        activation_id=parsed[3],
                        generation=parsed[4],
                        route=parsed[5],
                        binding=existing.p2_binding,
                    )
                    if existing.fingerprint != fingerprint:
                        raise FormalTaskViolation(
                            "PRODUCT_REQUEST_ID_CONFLICT",
                            "submission request_id cannot change binding",
                            ErrorCode.CONFLICT,
                        )
                else:
                    retained = await self._require_active_p2_route_locked(
                        params=params,
                        routed_session=parsed[0],
                        correlation_id=parsed[1],
                        interaction_id=parsed[2],
                        activation_id=parsed[3],
                        generation=parsed[4],
                        route=parsed[5],
                    )
                    self._require_product_request_not_evicted("p2.submit", request_id)
                    if (
                        len(self._p2_submit_operations)
                        >= self._PRODUCT_OPERATION_CAPACITY
                        and not self._evict_completed_product_operation(
                            self._p2_submit_operations,
                            namespace="p2.submit",
                        )
                    ):
                        raise FormalTaskViolation(
                            "PRODUCT_OPERATION_LEDGER_FULL",
                            "bounded submission replay ledger is full",
                            ErrorCode.UNAVAILABLE,
                        )
                    commit = TurnCommit.from_dict(
                        {
                            "contract_version": CONTRACT_VERSION,
                            "commit_id": commit_id,
                            "turn_id": turn_id,
                            "interaction_id": interaction_id,
                            "text": text_value,
                            "hypothesis_provenance": provenance,
                            "scope": retained.binding.scope.to_dict(),
                            "context_refs": [],
                            "committed_at": committed_at,
                        }
                    )
                    if dispatch_target == "task":
                        self._reserve_turn_commit_locked(
                            commit, (routed_session, interaction_id)
                        )
                    task = asyncio.create_task(
                        self._run_p2_submit(
                            retained=retained,
                            request_id=request_id,
                            response_id=response_id,
                            correlation_id=correlation_id,
                            commit=commit,
                            channel_id=channel_id,
                            dispatch_target=dispatch_target,
                            route_key=(routed_session, interaction_id),
                        ),
                        name=f"live-voice-product-p2-submit:{request_id}",
                    )
                    existing = _RetainedProductOperation(
                        fingerprint,
                        task,
                        p2_binding=retained.binding,
                    )
                    self._p2_submit_operations[request_id] = existing
            return await asyncio.shield(existing.task)
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 - stable product failure
            return _error_result(
                request_id,
                reason=getattr(exc, "reason", "PRODUCT_P2_SUBMISSION_FAILED"),
                code=getattr(exc, "code", ErrorCode.UNAVAILABLE),
                message=str(exc),
            )

    @staticmethod
    def _serialize_p2_notification(notification: Any) -> dict[str, object]:
        ref = notification.response_ref
        unit = notification.presentation_unit
        agent_event = notification.agent_event
        return {
            "status": "notification",
            "kind": notification.kind,
            "request_id": notification.request_id,
            "round_id": notification.round_id,
            "response": {
                "interaction_id": ref.interaction_id,
                "response_id": ref.response_id,
                "response_generation": ref.response_generation,
            },
            "agent_event": (
                None
                if agent_event is None
                else {
                    "seq": agent_event.seq,
                    "event_type": agent_event.event_type,
                    "text": agent_event.text,
                    "capability": agent_event.capability,
                    "error_reason": agent_event.error_reason,
                }
            ),
            "source_event": (
                None
                if notification.source_event is None
                else notification.source_event.to_dict()
            ),
            "progress_event": (
                None
                if notification.progress_event is None
                else notification.progress_event.to_dict()
            ),
            "presentation_unit": (
                None
                if unit is None
                else {
                    "surface": unit.surface.value,
                    "unit_id": unit.unit_id,
                    "seq": unit.seq,
                    "source_start_utf8": unit.source_start_utf8,
                    "source_end_utf8": unit.source_end_utf8,
                    "content_ref": unit.content_ref,
                }
            ),
            "error_reason": notification.error_reason,
            "publish_seq": notification.publish_seq,
        }

    async def _next_p2_notification(
        self,
        retained: _P2Route,
        request_id: str,
    ) -> P3RouteResult:
        try:
            notification = await retained.activation_lease.next_notification(
                retained.binding
            )
            return _success_result(
                request_id,
                {
                    **self._serialize_p2_notification(notification),
                    "session_id": retained.binding.session_id,
                    "correlation_id": retained.binding.correlation_id,
                    "interaction_id": retained.binding.interaction_id,
                    "activation_id": retained.binding.activation_id,
                    "activation_generation": (retained.binding.activation_generation),
                },
                retained.manifest,
            )
        except Exception as exc:  # noqa: BLE001 - retained stable outcome
            return _error_result(
                request_id,
                reason=getattr(exc, "reason", "PRODUCT_P2_NOTIFICATION_FAILED"),
                code=getattr(exc, "code", ErrorCode.UNAVAILABLE),
                message=str(exc),
                manifest=retained.manifest,
            )

    async def handle_p2_notification_next(
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
                        "notification_sequence",
                    }
                ),
            )
            self._ensure_running()
            parsed = self._parse_p2_route_binding(params, session_id=session_id)
            notification_sequence = params.get("notification_sequence")
            if (
                type(notification_sequence) is not int
                or notification_sequence <= 0
                or notification_sequence > MAX_SAFE_INTEGER
            ):
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "notification_sequence must be a positive safe integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            fingerprint = canonical_json_bytes(
                {key: value for key, value in params.items() if key != "auth_token"}
            )
            async with self._lock:
                entry = self._p2_notification_operations.get(request_id)
                if entry is not None:
                    if entry.p2_binding is None:
                        raise RuntimeError("retained P2 notification lost its binding")
                    await self._require_p2_binding_authority_locked(
                        params=params,
                        routed_session=parsed[0],
                        correlation_id=parsed[1],
                        interaction_id=parsed[2],
                        activation_id=parsed[3],
                        generation=parsed[4],
                        route=parsed[5],
                        binding=entry.p2_binding,
                    )
                    if entry.fingerprint != fingerprint:
                        raise FormalTaskViolation(
                            "PRODUCT_REQUEST_ID_CONFLICT",
                            "notification request_id cannot change binding",
                            ErrorCode.CONFLICT,
                        )
                else:
                    retained = await self._require_active_p2_route_locked(
                        params=params,
                        routed_session=parsed[0],
                        correlation_id=parsed[1],
                        interaction_id=parsed[2],
                        activation_id=parsed[3],
                        generation=parsed[4],
                        route=parsed[5],
                    )
                    if notification_sequence <= retained.notification_replay_floor:
                        raise FormalTaskViolation(
                            "PRODUCT_NOTIFICATION_REPLAY_EXPIRED",
                            "the completed notification replay has expired",
                            ErrorCode.CONFLICT,
                        )
                    expected_sequence = retained.notification_admitted_sequence + 1
                    if notification_sequence != expected_sequence:
                        raise FormalTaskViolation(
                            "PRODUCT_NOTIFICATION_SEQUENCE_MISMATCH",
                            "notification polls must use the next exact sequence",
                            ErrorCode.CONFLICT,
                        )
                    if retained.notification_admitted_sequence > 0:
                        previous = next(
                            (
                                candidate
                                for candidate in self._p2_notification_operations.values()
                                if candidate.p2_binding == retained.binding
                                and candidate.operation_sequence
                                == retained.notification_admitted_sequence
                            ),
                            None,
                        )
                        if previous is not None and not previous.task.done():
                            raise FormalTaskViolation(
                                "PRODUCT_NOTIFICATION_POLL_PENDING",
                                "the previous notification poll is still pending",
                                ErrorCode.CONFLICT,
                            )
                    if (
                        len(self._p2_notification_operations)
                        >= self._PRODUCT_OPERATION_CAPACITY
                        and not self._evict_completed_product_operation(
                            self._p2_notification_operations,
                            notification=True,
                        )
                    ):
                        raise FormalTaskViolation(
                            "PRODUCT_OPERATION_LEDGER_FULL",
                            "bounded notification replay ledger is full",
                            ErrorCode.UNAVAILABLE,
                        )
                    if notification_sequence <= retained.notification_replay_floor:
                        raise FormalTaskViolation(
                            "PRODUCT_NOTIFICATION_REPLAY_EXPIRED",
                            "the completed notification replay has expired",
                            ErrorCode.CONFLICT,
                        )
                    task = asyncio.create_task(
                        self._next_p2_notification(retained, request_id),
                        name=f"live-voice-product-p2-notification:{request_id}",
                    )
                    entry = _RetainedProductOperation(
                        fingerprint,
                        task,
                        p2_binding=retained.binding,
                        operation_sequence=notification_sequence,
                    )
                    self._p2_notification_operations[request_id] = entry
                    retained.notification_admitted_sequence = notification_sequence
            return await asyncio.shield(entry.task)
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )

    async def handle_p2_presentation_ack(
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
                        "response_id",
                        "response_generation",
                        "surface",
                        "unit_id",
                        "contiguous_cursor",
                        "presented_at",
                    }
                ),
            )
            self._ensure_running()
            parsed = self._parse_p2_route_binding(params, session_id=session_id)
            response_id = _required_text(params.get("response_id"), "response_id")
            unit_id = _required_text(params.get("unit_id"), "unit_id")
            presented_at = _required_text(
                params.get("presented_at"), "presented_at", maximum=64
            )
            response_generation = params.get("response_generation")
            cursor = params.get("contiguous_cursor")
            if (
                type(response_generation) is not int
                or response_generation < 0
                or response_generation > MAX_SAFE_INTEGER
            ):
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "response_generation must be a non-negative safe integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if type(cursor) is not int or cursor < 0 or cursor > MAX_SAFE_INTEGER:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "contiguous_cursor must be a non-negative safe integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            try:
                surface = PresentationSurface(str(params.get("surface")))
            except ValueError as exc:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "surface must be text or audio",
                    ErrorCode.INVALID_ARGUMENT,
                ) from exc
            fingerprint = canonical_json_bytes(
                {key: value for key, value in params.items() if key != "auth_token"}
            )
            async with self._lock:
                entry = self._p2_ack_operations.get(request_id)
                if entry is not None:
                    if entry.p2_binding is None:
                        raise RuntimeError("retained P2 ACK lost its binding")
                    await self._require_p2_binding_authority_locked(
                        params=params,
                        routed_session=parsed[0],
                        correlation_id=parsed[1],
                        interaction_id=parsed[2],
                        activation_id=parsed[3],
                        generation=parsed[4],
                        route=parsed[5],
                        binding=entry.p2_binding,
                    )
                    if entry.fingerprint != fingerprint:
                        raise FormalTaskViolation(
                            "PRODUCT_REQUEST_ID_CONFLICT",
                            "presentation ACK request_id cannot change binding",
                            ErrorCode.CONFLICT,
                        )
                else:
                    retained = await self._require_active_p2_route_locked(
                        params=params,
                        routed_session=parsed[0],
                        correlation_id=parsed[1],
                        interaction_id=parsed[2],
                        activation_id=parsed[3],
                        generation=parsed[4],
                        route=parsed[5],
                    )
                    self._require_product_request_not_evicted("p2.ack", request_id)
                    fault_plan = self._settings.p2_retriable_fault_plan
                    if (
                        fault_plan is not None
                        and not self._p2_retriable_fault_consumed
                        and fault_plan.request_id == request_id
                        and fault_plan.operation
                        == _PRODUCT_P2_PRESENTATION_ACK_OPERATION
                    ):
                        self._p2_retriable_fault_consumed = True
                        return _error_result(
                            request_id,
                            reason="PRODUCT_W2_RETRIABLE_FAULT_INJECTED",
                            code=ErrorCode.UNAVAILABLE,
                            message=(
                                "the externally frozen W2 plan injected a "
                                "retriable presentation fault"
                            ),
                            manifest=retained.manifest,
                        )
                    if (
                        len(self._p2_ack_operations) >= self._PRODUCT_OPERATION_CAPACITY
                        and not self._evict_completed_product_operation(
                            self._p2_ack_operations,
                            namespace="p2.ack",
                        )
                    ):
                        raise FormalTaskViolation(
                            "PRODUCT_OPERATION_LEDGER_FULL",
                            "bounded presentation ACK replay ledger is full",
                            ErrorCode.UNAVAILABLE,
                        )
                    ack = PresentationAck(
                        ref=ResponseRef(parsed[2], response_id, response_generation),
                        surface=surface,
                        unit_id=unit_id,
                        contiguous_cursor=cursor,
                        presented_at=presented_at,
                    )

                    async def acknowledge() -> P3RouteResult:
                        try:
                            outcome = await retained.activation_lease.acknowledge_presentation(
                                retained.binding, ack
                            )
                            return _success_result(
                                request_id,
                                {
                                    "status": "presentation_acknowledged",
                                    "session_id": retained.binding.session_id,
                                    "correlation_id": (retained.binding.correlation_id),
                                    "interaction_id": (retained.binding.interaction_id),
                                    "activation_id": retained.binding.activation_id,
                                    "activation_generation": (
                                        retained.binding.activation_generation
                                    ),
                                    "accepted": outcome.accepted,
                                    "replayed": outcome.replayed,
                                    "history_records_written": (
                                        outcome.history_records_written
                                    ),
                                    "history_pending": outcome.history_pending,
                                },
                                retained.manifest,
                            )
                        except Exception as exc:  # noqa: BLE001
                            return _error_result(
                                request_id,
                                reason=getattr(
                                    exc,
                                    "reason",
                                    "PRODUCT_P2_PRESENTATION_ACK_FAILED",
                                ),
                                code=getattr(exc, "code", ErrorCode.UNAVAILABLE),
                                message=str(exc),
                                manifest=retained.manifest,
                            )

                    task = asyncio.create_task(
                        acknowledge(),
                        name=f"live-voice-product-p2-ack:{request_id}",
                    )
                    entry = _RetainedProductOperation(
                        fingerprint,
                        task,
                        p2_binding=retained.binding,
                    )
                    self._p2_ack_operations[request_id] = entry
            return await asyncio.shield(entry.task)
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )

    async def handle_p2_barge_in(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        """Apply an exact playback-only or playback-plus-response interruption."""

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
                        "action_id",
                        "response_id",
                        "response_generation",
                        "cancel_response",
                    }
                ),
            )
            self._ensure_running()
            parsed = self._parse_p2_route_binding(params, session_id=session_id)
            action_id = _required_text(params.get("action_id"), "action_id")
            response_id = _required_text(params.get("response_id"), "response_id")
            response_generation = params.get("response_generation")
            cancel_response = params.get("cancel_response")
            if (
                type(response_generation) is not int
                or response_generation < 0
                or response_generation > MAX_SAFE_INTEGER
                or type(cancel_response) is not bool
            ):
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "barge-in generation and policy are invalid",
                    ErrorCode.INVALID_ARGUMENT,
                )
            fingerprint = canonical_json_bytes(
                {key: value for key, value in params.items() if key != "auth_token"}
            )
            async with self._lock:
                entry = self._p2_barge_operations.get(request_id)
                if entry is not None:
                    if entry.p2_binding is None:
                        raise RuntimeError("retained P2 barge-in lost its binding")
                    await self._require_p2_binding_authority_locked(
                        params=params,
                        routed_session=parsed[0],
                        correlation_id=parsed[1],
                        interaction_id=parsed[2],
                        activation_id=parsed[3],
                        generation=parsed[4],
                        route=parsed[5],
                        binding=entry.p2_binding,
                    )
                    if entry.fingerprint != fingerprint:
                        raise FormalTaskViolation(
                            "PRODUCT_REQUEST_ID_CONFLICT",
                            "barge-in request_id cannot change binding",
                            ErrorCode.CONFLICT,
                        )
                else:
                    retained = await self._require_active_p2_route_locked(
                        params=params,
                        routed_session=parsed[0],
                        correlation_id=parsed[1],
                        interaction_id=parsed[2],
                        activation_id=parsed[3],
                        generation=parsed[4],
                        route=parsed[5],
                    )
                    self._require_product_request_not_evicted("p2.barge", request_id)
                    if (
                        len(self._p2_barge_operations)
                        >= self._PRODUCT_OPERATION_CAPACITY
                        and not self._evict_completed_product_operation(
                            self._p2_barge_operations,
                            namespace="p2.barge",
                        )
                    ):
                        raise FormalTaskViolation(
                            "PRODUCT_OPERATION_LEDGER_FULL",
                            "bounded barge-in replay ledger is full",
                            ErrorCode.UNAVAILABLE,
                        )
                    response = ResponseRef(
                        parsed[2], response_id, response_generation
                    )

                    async def interrupt() -> P3RouteResult:
                        try:
                            outcome = await retained.activation_lease.barge_in(
                                retained.binding,
                                action_id=action_id,
                                response=response,
                                cancel_response=cancel_response,
                            )
                            return _success_result(
                                request_id,
                                {
                                    "status": "barge_in_applied",
                                    "session_id": retained.binding.session_id,
                                    "correlation_id": retained.binding.correlation_id,
                                    "interaction_id": retained.binding.interaction_id,
                                    "activation_id": retained.binding.activation_id,
                                    "activation_generation": (
                                        retained.binding.activation_generation
                                    ),
                                    "action_id": outcome.action_id,
                                    "response_id": response.response_id,
                                    "response_generation": (
                                        response.response_generation
                                    ),
                                    "cancel_response": cancel_response,
                                    "applied": outcome.applied,
                                    "replayed": outcome.replayed,
                                    "effect_ids": list(outcome.effect_ids),
                                },
                                retained.manifest,
                            )
                        except Exception as exc:  # noqa: BLE001
                            return _error_result(
                                request_id,
                                reason=getattr(
                                    exc, "reason", "PRODUCT_P2_BARGE_IN_FAILED"
                                ),
                                code=getattr(exc, "code", ErrorCode.UNAVAILABLE),
                                message=str(exc),
                                manifest=retained.manifest,
                            )

                    task = asyncio.create_task(
                        interrupt(),
                        name=f"live-voice-product-p2-barge:{request_id}",
                    )
                    entry = _RetainedProductOperation(
                        fingerprint,
                        task,
                        p2_binding=retained.binding,
                    )
                    self._p2_barge_operations[request_id] = entry
            return await asyncio.shield(entry.task)
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
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
            activation_id = _required_text(params.get("activation_id"), "activation_id")
            generation = params.get("activation_generation")
            if (
                type(generation) is not int
                or generation <= 0
                or generation > MAX_SAFE_INTEGER
            ):
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "activation_generation must be a positive safe integer",
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
                return _error_result(request_id, reason="PRODUCT_COMPOSITION_STOPPED")
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
                closed = self._closed_p2_routes.get((routed_session, interaction_id))
                if closed is None:
                    if authority.lease is not None:
                        await authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="PRODUCT_P2_ROUTE_NOT_FOUND",
                        code=ErrorCode.NOT_FOUND,
                    )
                if (
                    closed.binding.correlation_id != correlation_id
                    or closed.binding.activation_id != activation_id
                    or closed.binding.activation_generation != generation
                    or state.canonical.scope != closed.binding.scope
                ):
                    if authority.lease is not None:
                        await authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="ACTIVATION_BINDING_MISMATCH",
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                if authority.lease is not None:
                    await authority.lease.close()
                return _success_result(
                    request_id,
                    {
                        "status": "closed",
                        "replayed": True,
                        "session_id": routed_session,
                        "correlation_id": correlation_id,
                        "interaction_id": interaction_id,
                        "activation_id": activation_id,
                        "activation_generation": generation,
                    },
                    closed.manifest,
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
            key = (routed_session, interaction_id)
            self._release_voice_origins_for_route_locked(key)
            self._p2_routes.pop(key, None)
            self._retain_closed_p2_route(
                key,
                _ClosedP2Route(
                    retained.binding,
                    retained.manifest,
                    retained.notification_replay_floor,
                ),
            )
            return _success_result(
                request_id,
                {
                    "status": "closed",
                    "replayed": False,
                    "session_id": routed_session,
                    "correlation_id": correlation_id,
                    "interaction_id": interaction_id,
                    "activation_id": activation_id,
                    "activation_generation": generation,
                },
                retained.manifest,
            )

    def _p3_control_ready(self) -> bool:
        return bool(
            self._settings.p3_mutation_enabled
            and self._p3_confirmation_owner is not None
            and self._p3_confirmation_forwarder is not None
            and self._p3_confirmation_generation is not None
        )

    @staticmethod
    def _p3_control_manifest() -> ProductCompositionManifest:
        return create_product_composition_manifest(
            enabled=True,
            route_facts=(
                _formal_fact(ProductSegment.AUTHORITY),
                _formal_fact(ProductSegment.P3_CONTROL),
            ),
        )

    @staticmethod
    def _validate_product_p3_mutation_params(
        params: Mapping[str, object],
        *,
        issue: bool,
        session_id: str | None,
    ) -> tuple[str, dict[str, object]]:
        operation = _required_text(params.get("operation"), "operation")
        if operation not in P3_MUTATIONS:
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION_OPERATION",
                "product mutation must be task.create, task.cancel or task.retry",
                ErrorCode.UNSUPPORTED,
            )
        required = {
            "auth_token",
            "session_id",
            "operation",
            "command_id",
            "issued_at",
            "correlation_id",
        }
        optional: set[str] = set()
        if not issue:
            required.add("confirmation_id")
        if operation == "task.create":
            required.update({"name", "instruction"})
            optional.update(
                {"model_intent", "source", "interaction_id", "turn_id", "commit_id"}
            )
        elif operation == "task.retry":
            # A bounded retry submits its target task only; predecessor,
            # attempt ordinal, outcome, context and readiness are server-owned
            # and a voice-committed origin cannot be claimed for it.
            required.add("task_id")
        else:
            required.add("task_id")
            optional.add("source")
        _require_exact_params(params, frozenset(required | optional))
        # ``_require_exact_params`` only rejects non-string or unknown keys.
        # Proving the remaining required fields are present keeps every P3
        # mutation fail closed with one stable reason instead of letting a
        # missing field surface later as an unhandled lookup.  ``auth_token``
        # stays an allowed field but is deliberately excluded here: a missing
        # or invalid bearer is an authentication fact, and the existing
        # authenticator must keep classifying it as
        # FORMAL_TASK_AUTHENTICATION_REQUIRED / UNAUTHENTICATED.
        if (required - {"auth_token"}) - set(params):
            raise FormalTaskViolation(
                "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                "product request fields are incomplete or unknown",
                ErrorCode.INVALID_ARGUMENT,
            )
        routed_session = _required_text(session_id, "routed_session_id")
        if _required_text(params.get("session_id"), "session_id") != routed_session:
            raise FormalTaskViolation(
                "PRODUCT_COMPOSITION_SESSION_MISMATCH",
                "product request does not match its routed session",
                ErrorCode.PERMISSION_DENIED,
            )
        forwarded = {key: value for key, value in params.items() if key != "operation"}
        return operation, forwarded

    async def _run_p3_confirmation_issue(
        self,
        *,
        operation: str,
        forwarded: dict[str, object],
        request_id: str,
        session_id: str,
    ) -> P3RouteResult:
        manifest = self._p3_control_manifest()
        owner = self._p3_confirmation_owner
        generation = self._p3_confirmation_generation
        if owner is None or generation is None:
            return _error_result(
                request_id,
                reason="P3_CONFIRMATION_ISSUER_UNAVAILABLE",
                manifest=manifest,
            )
        async with self._p3_operation_lock:
            try:
                await self._require_current_voice_origin_route(
                    forwarded=forwarded,
                    session_id=session_id,
                )
                confirmation_id = hashlib.sha256(
                    f"{generation}:{request_id}".encode("utf-8")
                ).hexdigest()
                mutation_params = dict(forwarded)
                mutation_params["confirmation_id"] = confirmation_id
                prepared = await self._p3_composition.prepare_mutation_confirmation(
                    operation=operation,
                    params=mutation_params,
                    session_id=session_id,
                )
                owner_context = P3ConfirmationOwnerContext(
                    session_id=session_id,
                    correlation_id=prepared.correlation_id,
                    owner_generation=generation,
                )
                observed = datetime.fromisoformat(
                    prepared.observed_at.replace("Z", "+00:00")
                ).astimezone(UTC)
                expires_at = (
                    (observed + P3_CONFIRMATION_MAX_TTL)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
                receipt = await asyncio.to_thread(
                    owner.issue,
                    TrustedP3ConfirmationIssue(
                        binding=prepared.binding,
                        owner=owner_context,
                        expires_at=expires_at,
                        confirmation_id=confirmation_id,
                    ),
                    now=prepared.observed_at,
                )
                return _success_result(
                    request_id,
                    {
                        "status": "confirmation_issued",
                        "confirmation_id": receipt.confirmation_id,
                        "expires_at": receipt.expires_at,
                        "replayed": receipt.replayed,
                        "operation": operation,
                        "command_id": prepared.binding.command_id,
                        "target_task_id": prepared.binding.target_task_id,
                        "task_control_binding": {
                            "subject_id": prepared.binding.scope.subject_id,
                            "session_id": prepared.binding.scope.session_id,
                            "project_id": prepared.binding.scope.project_id,
                            "correlation_id": prepared.correlation_id,
                            "generation": generation,
                        },
                    },
                    manifest,
                )
            except Exception as exc:  # noqa: BLE001 - retained stable outcome
                return _error_result(
                    request_id,
                    reason=getattr(exc, "reason", "P3_CONFIRMATION_ISSUE_FAILED"),
                    code=getattr(exc, "code", ErrorCode.UNAVAILABLE),
                    message=str(exc),
                    manifest=manifest,
                )

    async def _preflight_p3_confirmation_issue(
        self,
        *,
        operation: str,
        forwarded: dict[str, object],
        session_id: str,
    ) -> P3ConfirmationBinding:
        """Reject untrusted issue attempts before reserving replay capacity."""

        async with self._p3_operation_lock:
            mutation_params = dict(forwarded)
            mutation_params["confirmation_id"] = secrets.token_urlsafe(24)
            prepared = await self._p3_composition.prepare_mutation_confirmation(
                operation=operation,
                params=mutation_params,
                session_id=session_id,
            )
            return prepared.binding

    async def handle_p3_confirmation_issue(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        if not self._p3_control_ready():
            return _error_result(
                request_id, reason="P3_CONFIRMATION_ISSUER_UNAVAILABLE"
            )
        try:
            self._ensure_running()
            operation, forwarded = self._validate_product_p3_mutation_params(
                params, issue=True, session_id=session_id
            )
            routed_session = _required_text(session_id, "routed_session_id")
            fingerprint = hashlib.sha256(
                canonical_json_bytes(
                    {key: value for key, value in params.items() if key != "auth_token"}
                )
            ).digest()
            async with self._lock:
                existing = self._p3_issue_operations.get(request_id)
            if existing is not None:
                if existing.p3_binding is None:
                    raise RuntimeError("retained P3 issue lost its authority binding")
                await self._p3_composition.reauthorize_mutation_replay(
                    operation=operation,
                    params={**forwarded, "confirmation_id": "retained-replay"},
                    session_id=routed_session,
                    expected_binding=existing.p3_binding,
                )
                if existing.fingerprint != fingerprint:
                    raise FormalTaskViolation(
                        "PRODUCT_REQUEST_ID_CONFLICT",
                        "confirmation request_id cannot change binding",
                        ErrorCode.CONFLICT,
                    )
            else:
                p3_binding = await self._preflight_p3_confirmation_issue(
                    operation=operation,
                    forwarded=forwarded,
                    session_id=routed_session,
                )
                async with self._lock:
                    # ``stop()`` sets the flag before snapshotting retained work.
                    # Recheck in the admission critical section so a request that
                    # was awaiting authority cannot appear after that snapshot.
                    self._ensure_running()
                    existing = self._p3_issue_operations.get(request_id)
                    if existing is not None:
                        if existing.fingerprint != fingerprint:
                            raise FormalTaskViolation(
                                "PRODUCT_REQUEST_ID_CONFLICT",
                                "confirmation request_id cannot change binding",
                                ErrorCode.CONFLICT,
                            )
                        if existing.p3_binding != p3_binding:
                            raise FormalTaskViolation(
                                "P3_CONFIRMATION_BINDING_MISMATCH",
                                "confirmation replay no longer matches current authority",
                                ErrorCode.PERMISSION_DENIED,
                            )
                    else:
                        self._require_product_request_not_evicted(
                            "p3.issue", request_id
                        )
                        if (
                            len(self._p3_issue_operations)
                            >= self._PRODUCT_OPERATION_CAPACITY
                            and not self._evict_completed_product_operation(
                                self._p3_issue_operations,
                                namespace="p3.issue",
                            )
                        ):
                            raise FormalTaskViolation(
                                "PRODUCT_OPERATION_LEDGER_FULL",
                                "bounded confirmation replay ledger is full",
                                ErrorCode.UNAVAILABLE,
                            )
                        task = asyncio.create_task(
                            self._run_p3_confirmation_issue(
                                operation=operation,
                                forwarded=forwarded,
                                request_id=request_id,
                                session_id=routed_session,
                            ),
                            name=f"live-voice-product-p3-confirmation:{request_id}",
                        )
                        existing = _RetainedProductOperation(
                            fingerprint, task, p3_binding=p3_binding
                        )
                        self._p3_issue_operations[request_id] = existing
            assert existing is not None
            return await asyncio.shield(existing.task)
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
            )

    async def _run_p3_mutation(
        self,
        *,
        operation: str,
        forwarded: dict[str, object],
        request_id: str,
        session_id: str,
    ) -> P3RouteResult:
        manifest = self._p3_control_manifest()
        owner = self._p3_confirmation_owner
        forwarder = self._p3_confirmation_forwarder
        generation = self._p3_confirmation_generation
        if owner is None or forwarder is None or generation is None:
            return _error_result(
                request_id,
                reason="P3_CONFIRMATION_ISSUER_UNAVAILABLE",
                manifest=manifest,
            )
        async with self._p3_operation_lock:
            try:
                prepared = await self._p3_composition.prepare_mutation_confirmation(
                    operation=operation,
                    params=forwarded,
                    session_id=session_id,
                )
                owner_context = P3ConfirmationOwnerContext(
                    session_id=session_id,
                    correlation_id=prepared.correlation_id,
                    owner_generation=generation,
                )
                confirmation_id = _required_text(
                    forwarded.get("confirmation_id"), "confirmation_id"
                )
                validated = await asyncio.to_thread(
                    owner.validate_for_forwarding,
                    confirmation_id,
                    prepared.binding,
                    owner_context,
                    now=prepared.observed_at,
                )
                with forwarder.permit(validated):
                    result = await self._p3_composition.handle(
                        operation=operation,
                        params=forwarded,
                        request_id=request_id,
                        session_id=session_id,
                    )
                if not result.ok:
                    error = result.payload.get("error")
                    if isinstance(error, Mapping):
                        reason = str(
                            error.get("reason") or "PRODUCT_P3_MUTATION_FAILED"
                        )
                        message = str(
                            error.get("message")
                            or "formal product P3 mutation failed closed"
                        )
                        try:
                            code = ErrorCode(str(error.get("code")))
                        except ValueError:
                            code = ErrorCode.UNAVAILABLE
                    else:
                        reason = "PRODUCT_P3_MUTATION_FAILED"
                        message = "formal product P3 mutation failed closed"
                        code = ErrorCode.UNAVAILABLE
                    return _error_result(
                        request_id,
                        reason=reason,
                        code=code,
                        message=message,
                        manifest=manifest,
                    )
                if operation == "task.create" and forwarded.get("source") == "voice":
                    commit_id = str(forwarded.get("commit_id") or "")
                    turn_id = str(forwarded.get("turn_id") or "")
                    async with self._lock:
                        commit = self._accepted_turn_commits_by_commit.get(commit_id)
                        if commit is not None and commit.turn_id == turn_id:
                            self._release_voice_origin_locked(commit)
                return _success_result(
                    request_id,
                    {
                        "status": "mutation_processed",
                        "operation": operation,
                        "command_id": prepared.binding.command_id,
                        "target_task_id": prepared.binding.target_task_id,
                        "formal_task_result": result.payload.get("result"),
                    },
                    manifest,
                )
            except Exception as exc:  # noqa: BLE001 - retained stable outcome
                return _error_result(
                    request_id,
                    reason=getattr(exc, "reason", "PRODUCT_P3_MUTATION_FAILED"),
                    code=getattr(exc, "code", ErrorCode.UNAVAILABLE),
                    message=str(exc),
                    manifest=manifest,
                )

    async def _run_p3_stale_fault(self, *, request_id: str) -> P3RouteResult:
        return _error_result(
            request_id,
            reason="PRODUCT_W2_STALE_FAULT_INJECTED",
            code=ErrorCode.STALE,
            message="the externally frozen W2 plan injected a stale retry fault",
            manifest=self._p3_control_manifest(),
        )

    async def _preflight_p3_mutation(
        self,
        *,
        operation: str,
        forwarded: dict[str, object],
        session_id: str,
    ) -> P3ConfirmationBinding:
        """Validate current authority and owner binding before ledger admission."""

        owner = self._p3_confirmation_owner
        generation = self._p3_confirmation_generation
        if owner is None or generation is None:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_ISSUER_UNAVAILABLE",
                "the product confirmation owner is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        async with self._p3_operation_lock:
            await self._require_current_voice_origin_route(
                forwarded=forwarded,
                session_id=session_id,
            )
            prepared = await self._p3_composition.prepare_mutation_confirmation(
                operation=operation,
                params=forwarded,
                session_id=session_id,
            )
            confirmation_id = _required_text(
                forwarded.get("confirmation_id"), "confirmation_id"
            )
            await asyncio.to_thread(
                owner.validate_for_forwarding,
                confirmation_id,
                prepared.binding,
                P3ConfirmationOwnerContext(
                    session_id=session_id,
                    correlation_id=prepared.correlation_id,
                    owner_generation=generation,
                ),
                now=prepared.observed_at,
            )
            return prepared.binding

    async def _require_current_voice_origin_route(
        self, *, forwarded: Mapping[str, object], session_id: str
    ) -> None:
        if forwarded.get("source") != "voice":
            return
        interaction_id = _required_text(
            forwarded.get("interaction_id"), "interaction_id"
        )
        commit_id = _required_text(forwarded.get("commit_id"), "commit_id")
        turn_id = _required_text(forwarded.get("turn_id"), "turn_id")
        route_key = (session_id, interaction_id)
        async with self._lock:
            commit = self._accepted_turn_commits_by_commit.get(commit_id)
            if (
                self._accepted_voice_commit_routes.get(commit_id) != route_key
                or self._p2_routes.get(route_key) is None
                or commit is None
                or commit.turn_id != turn_id
                or commit.interaction_id != interaction_id
            ):
                raise FormalTaskViolation(
                    "VOICE_TASK_ROUTE_MISMATCH",
                    "voice task origin must belong to the exact active P2 interaction",
                    ErrorCode.PERMISSION_DENIED,
                )

    async def handle_p3_mutation(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        if not self._p3_control_ready():
            return _error_result(
                request_id, reason="P3_CONFIRMATION_ISSUER_UNAVAILABLE"
            )
        try:
            self._ensure_running()
            operation, forwarded = self._validate_product_p3_mutation_params(
                params, issue=False, session_id=session_id
            )
            routed_session = _required_text(session_id, "routed_session_id")
            fingerprint = hashlib.sha256(
                canonical_json_bytes(
                    {key: value for key, value in params.items() if key != "auth_token"}
                )
            ).digest()
            async with self._lock:
                existing = self._p3_mutation_operations.get(request_id)
            if existing is not None:
                if existing.p3_binding is None:
                    raise RuntimeError(
                        "retained P3 mutation lost its authority binding"
                    )
                await self._p3_composition.reauthorize_mutation_replay(
                    operation=operation,
                    params=forwarded,
                    session_id=routed_session,
                    expected_binding=existing.p3_binding,
                )
                if existing.fingerprint != fingerprint:
                    raise FormalTaskViolation(
                        "PRODUCT_REQUEST_ID_CONFLICT",
                        "mutation request_id cannot change binding",
                        ErrorCode.CONFLICT,
                    )
            else:
                p3_binding = await self._preflight_p3_mutation(
                    operation=operation,
                    forwarded=forwarded,
                    session_id=routed_session,
                )
                async with self._lock:
                    # Keep stop/admission atomic with respect to the retained
                    # task snapshot; no mutation may be admitted after stop.
                    self._ensure_running()
                    existing = self._p3_mutation_operations.get(request_id)
                    if existing is not None:
                        if existing.fingerprint != fingerprint:
                            raise FormalTaskViolation(
                                "PRODUCT_REQUEST_ID_CONFLICT",
                                "mutation request_id cannot change binding",
                                ErrorCode.CONFLICT,
                            )
                        if existing.p3_binding != p3_binding:
                            raise FormalTaskViolation(
                                "P3_CONFIRMATION_BINDING_MISMATCH",
                                "mutation replay no longer matches current authority",
                                ErrorCode.PERMISSION_DENIED,
                            )
                    else:
                        self._require_product_request_not_evicted(
                            "p3.mutate", request_id
                        )
                        if (
                            len(self._p3_mutation_operations)
                            >= self._PRODUCT_OPERATION_CAPACITY
                            and not self._evict_completed_product_operation(
                                self._p3_mutation_operations,
                                namespace="p3.mutate",
                            )
                        ):
                            raise FormalTaskViolation(
                                "PRODUCT_OPERATION_LEDGER_FULL",
                                "bounded mutation replay ledger is full",
                                ErrorCode.UNAVAILABLE,
                            )
                        fault_plan = self._settings.p3_stale_fault_plan
                        inject_stale = (
                            fault_plan is not None
                            and not self._p3_stale_fault_consumed
                            and fault_plan.request_id == request_id
                            and fault_plan.operation == operation
                        )
                        if inject_stale:
                            self._p3_stale_fault_consumed = True
                            task = asyncio.create_task(
                                self._run_p3_stale_fault(request_id=request_id),
                                name=f"live-voice-product-p3-stale-fault:{request_id}",
                            )
                        else:
                            task = asyncio.create_task(
                                self._run_p3_mutation(
                                    operation=operation,
                                    forwarded=forwarded,
                                    request_id=request_id,
                                    session_id=routed_session,
                                ),
                                name=f"live-voice-product-p3-mutation:{request_id}",
                            )
                        existing = _RetainedProductOperation(
                            fingerprint, task, p3_binding=p3_binding
                        )
                        self._p3_mutation_operations[request_id] = existing
            assert existing is not None
            return await asyncio.shield(existing.task)
        except FormalTaskViolation as exc:
            return _error_result(
                request_id, reason=exc.reason, code=exc.code, message=str(exc)
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
            payload["product_composition"] = _serialize_manifest(activation.manifest)
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
            generation_id = _required_text(params.get("generation_id"), "generation_id")
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
                return _error_result(request_id, reason="PRODUCT_COMPOSITION_STOPPED")
            key = (routed_session, task_id, origin_id, generation_id)
            existing = self._progress_routes.get(key)
            previous_generation = self._progress_generations.get(key)
            state = _AuthorityState()
            preauthorized_authority: ProductSegmentActivation | None = None
            if (
                existing is None
                and previous_generation is not None
                and generation <= previous_generation
            ):
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
                closed = self._closed_progress_routes.get((*key, previous_generation))
                if closed is not None and state.canonical.scope != closed.binding.scope:
                    if preauthorized_authority.lease is not None:
                        await preauthorized_authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_BINDING_MISMATCH",
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                settled_replay = (
                    closed is not None
                    and generation == previous_generation
                    and closed.binding.correlation_id == correlation_id
                )
                if preauthorized_authority.lease is not None:
                    await preauthorized_authority.lease.close()
                return _error_result(
                    request_id,
                    reason=(
                        "TASK_PROGRESS_ROUTE_SETTLED"
                        if settled_replay
                        else "TASK_PROGRESS_STALE_GENERATION"
                    ),
                    code=ErrorCode.CONFLICT,
                )
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
                    if not self._archive_progress_route(key, existing):
                        if preauthorized_authority.lease is not None:
                            await preauthorized_authority.lease.close()
                        return _error_result(
                            request_id,
                            reason="TASK_PROGRESS_SETTLED_CLEANUP_PENDING",
                        )
                    if generation <= existing.binding.generation:
                        if preauthorized_authority.lease is not None:
                            await preauthorized_authority.lease.close()
                        return _error_result(
                            request_id,
                            reason="TASK_PROGRESS_ROUTE_SETTLED",
                            code=ErrorCode.CONFLICT,
                        )
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
                            "session_id": routed_session,
                            "correlation_id": correlation_id,
                            "task_id": task_id,
                            "origin_id": origin_id,
                            "generation_id": generation_id,
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
                if route_is_active and not self._archive_progress_route(key, existing):
                    if preauthorized_authority.lease is not None:
                        await preauthorized_authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_REPLACEMENT_CLEANUP_PENDING",
                    )
            if preauthorized_authority is None:
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
            if not self._admit_progress_generation_key(key):
                if preauthorized_authority is not None:
                    if preauthorized_authority.lease is not None:
                        await preauthorized_authority.lease.close()
                return _error_result(
                    request_id,
                    reason="TASK_PROGRESS_ROUTE_CAPACITY_UNAVAILABLE",
                )
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
                grant = P3AuthorityAdapter(service).to_task_grant(p3_authority, None)
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
                            instance_id=(f"{routed_session}:{origin_id}:{generation}"),
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
                if previous_generation is None:
                    self._progress_generations.pop(key, None)
                else:
                    self._progress_generations[key] = previous_generation
                self._progress_targets.pop(key, None)
                self._progress_deliveries.pop(key, None)
                self._retain_root_cleanup(exc.cleanup_lease)
                logger.exception("[LiveVoiceProduct] P3 progress failed closed")
                return _error_result(
                    request_id,
                    reason="PRODUCT_P3_PROGRESS_ACTIVATION_FAILED",
                )
            except Exception:
                if previous_generation is None:
                    self._progress_generations.pop(key, None)
                else:
                    self._progress_generations[key] = previous_generation
                self._progress_targets.pop(key, None)
                self._progress_deliveries.pop(key, None)
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
                if previous_generation is None:
                    self._progress_generations.pop(key, None)
                else:
                    self._progress_generations[key] = previous_generation
                self._progress_targets.pop(key, None)
                self._progress_deliveries.pop(key, None)
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
                    "session_id": routed_session,
                    "correlation_id": correlation_id,
                    "task_id": task_id,
                    "origin_id": origin_id,
                    "generation_id": generation_id,
                    "generation": generation,
                    "voice_progress": "unavailable",
                    "voice_reason": "TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE",
                },
                activation.manifest,
            )

    async def handle_p3_progress_ack(
        self,
        *,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
        channel_id: str,
    ) -> P3RouteResult:
        """Accept an exact Web UI-consumption acknowledgement.

        This acknowledgement proves only that the validated text-progress fact
        reached the stock Web consumer.  It is not a PresentationAck, history
        authority, task transition, voice delivery, or proof that a person saw
        the UI.
        """

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
                        "delivery_id",
                        "source_event_id",
                        "progress_event_id",
                        "seq",
                        "evidence_id",
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
            generation_id = _required_text(params.get("generation_id"), "generation_id")
            generation = params.get("generation")
            seq = params.get("seq")
            if type(generation) is not int or generation <= 0:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "generation must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if type(seq) is not int or seq < 0:
                raise FormalTaskViolation(
                    "INVALID_PRODUCT_COMPOSITION_ARGUMENT",
                    "seq must be a non-negative integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            delivery_id = _required_text(params.get("delivery_id"), "delivery_id")
            source_event_id = _required_text(
                params.get("source_event_id"), "source_event_id"
            )
            progress_event_id = _required_text(
                params.get("progress_event_id"), "progress_event_id"
            )
            evidence_id = _required_text(params.get("evidence_id"), "evidence_id")
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
                return _error_result(request_id, reason="PRODUCT_COMPOSITION_STOPPED")
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
            try:
                assert state.canonical is not None
                key = (routed_session, task_id, origin_id, generation_id)
                retained = self._progress_routes.get(key)
                closed = self._closed_progress_routes.get((*key, generation))
                active_identity_matches = retained is not None and (
                    retained.channel_id == channel_id
                    and retained.binding.correlation_id == correlation_id
                    and state.canonical.scope == retained.binding.scope
                )
                closed_identity_matches = closed is not None and (
                    closed.channel_id == channel_id
                    and closed.binding.correlation_id == correlation_id
                    and state.canonical.scope == closed.binding.scope
                )
                current_generation = self._progress_generations.get(key)
                # A newer generation fences even an exact closed-delivery replay,
                # but only after the caller proves the retained/closed identity.
                if (
                    current_generation is not None
                    and generation < current_generation
                    and (active_identity_matches or closed_identity_matches)
                ):
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_STALE_GENERATION",
                        code=ErrorCode.STALE,
                    )
                active_matches = (
                    retained is not None
                    and active_identity_matches
                    and retained.binding.generation == generation
                )
                closed_matches = (
                    closed is not None
                    and closed_identity_matches
                    and closed.binding.generation == generation
                )
                if active_matches:
                    assert retained is not None
                    deliveries = self._progress_deliveries.get(key, {})
                    manifest = retained.manifest
                elif closed_matches:
                    assert closed is not None
                    deliveries = closed.deliveries
                    manifest = closed.manifest
                elif retained is None and closed is None:
                    return _error_result(
                        request_id,
                        reason="PRODUCT_P3_PROGRESS_ROUTE_NOT_FOUND",
                        code=ErrorCode.NOT_FOUND,
                    )
                else:
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_BINDING_MISMATCH",
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                delivery = deliveries.get(delivery_id)
                if delivery is None or not delivery.delivered:
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_DELIVERY_UNAVAILABLE",
                        code=ErrorCode.UNAVAILABLE,
                    )
                if (
                    delivery.source_event_id != source_event_id
                    or delivery.progress_event_id != progress_event_id
                    or delivery.seq != seq
                    or delivery.evidence_id != evidence_id
                ):
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_DELIVERY_MISMATCH",
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                replayed = delivery.acknowledged
                delivery.acknowledged = True
                return _success_result(
                    request_id,
                    {
                        "status": "acknowledged",
                        "replayed": replayed,
                        "session_id": routed_session,
                        "task_id": task_id,
                        "attempt_id": delivery.attempt_id,
                        "correlation_id": correlation_id,
                        "origin_id": origin_id,
                        "generation_id": generation_id,
                        "generation": generation,
                        "delivery_id": delivery_id,
                        "source_event_id": source_event_id,
                        "progress_event_id": progress_event_id,
                        "seq": seq,
                        "evidence_id": evidence_id,
                        "acknowledgement": "web_ui_text_consumed",
                    },
                    manifest,
                )
            finally:
                if authority.lease is not None:
                    await authority.lease.close()

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
            generation_id = _required_text(params.get("generation_id"), "generation_id")
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
                return _error_result(request_id, reason="PRODUCT_COMPOSITION_STOPPED")
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
                closed = self._closed_progress_routes.get((*key, generation))
                if closed is None:
                    if authority.lease is not None:
                        await authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="PRODUCT_P3_PROGRESS_ROUTE_NOT_FOUND",
                        code=ErrorCode.NOT_FOUND,
                    )
                if (
                    closed.binding.correlation_id != correlation_id
                    or closed.binding.generation != generation
                    or state.canonical.scope != closed.binding.scope
                ):
                    if authority.lease is not None:
                        await authority.lease.close()
                    return _error_result(
                        request_id,
                        reason="TASK_PROGRESS_BINDING_MISMATCH",
                        code=ErrorCode.PERMISSION_DENIED,
                    )
                if authority.lease is not None:
                    await authority.lease.close()
                return _success_result(
                    request_id,
                    {
                        "status": "closed",
                        "replayed": True,
                        "session_id": routed_session,
                        "correlation_id": correlation_id,
                        "task_id": task_id,
                        "origin_id": origin_id,
                        "generation_id": generation_id,
                        "generation": generation,
                    },
                    closed.manifest,
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
            if not self._archive_progress_route(key, retained):
                return _error_result(
                    request_id,
                    reason="PRODUCT_P3_PROGRESS_CLEANUP_PENDING",
                )
            return _success_result(
                request_id,
                {
                    "status": "closed",
                    "replayed": False,
                    "session_id": routed_session,
                    "correlation_id": correlation_id,
                    "task_id": task_id,
                    "origin_id": origin_id,
                    "generation_id": generation_id,
                    "generation": generation,
                },
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
                if not self._archive_progress_route(progress_key, progress_retained):
                    failures = True
                    logger.error(
                        "[LiveVoiceProduct] progress tombstone capacity pending"
                    )
            for p2_key, p2_retained in reversed(tuple(self._p2_routes.items())):
                try:
                    await p2_retained.lease.close()
                except Exception:
                    failures = True
                    logger.exception("[LiveVoiceProduct] P2 disconnect cleanup pending")
                    continue
                self._p2_routes.pop(p2_key, None)
                self._release_voice_origins_for_route_locked(p2_key)
                self._retain_closed_p2_route(
                    p2_key,
                    _ClosedP2Route(
                        p2_retained.binding,
                        p2_retained.manifest,
                        p2_retained.notification_replay_floor,
                    ),
                )
            remaining_orphans: list[_P2FailedCleanupLease] = []
            for cleanup in self._p2_orphan_cleanups:
                try:
                    await cleanup.close()
                except Exception:
                    failures = True
                    remaining_orphans.append(cleanup)
                    logger.exception("[LiveVoiceProduct] orphan P2 cleanup pending")
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
        retained_tasks = tuple(
            entry.task
            for ledger in (
                self._p2_submit_operations,
                self._p2_notification_operations,
                self._p2_ack_operations,
                self._p2_barge_operations,
                self._p3_issue_operations,
                self._p3_mutation_operations,
            )
            for entry in ledger.values()
        )
        if retained_tasks:
            await asyncio.shield(
                asyncio.gather(*retained_tasks, return_exceptions=True)
            )


def create_product_composition_registry_from_environment(
    *,
    p3_composition: P3AuthenticatedComposition | None,
    agent_manager: Any,
    push_text_event: Callable[[dict[str, object]], Awaitable[bool]],
    p3_confirmation_owner: BoundedP3ConfirmationOwner | None = None,
    p3_confirmation_forwarder: ProductP3ConfirmationForwarder | None = None,
    commit_ledger: TurnCommitLedger | None = None,
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
        p3_confirmation_owner=p3_confirmation_owner,
        p3_confirmation_forwarder=p3_confirmation_forwarder,
        commit_ledger=commit_ledger,
    )


__all__ = [
    "AgentServerProductCompositionRegistry",
    "PRODUCT_COMPOSITION_ENABLE_ENV",
    "PRODUCT_COMPOSITION_METHODS",
    "PRODUCT_P2_ENABLE_ENV",
    "PRODUCT_P2_RETRIABLE_FAULT_OPERATION_ENV",
    "PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID_ENV",
    "PRODUCT_P3_STALE_FAULT_OPERATION_ENV",
    "PRODUCT_P3_STALE_FAULT_REQUEST_ID_ENV",
    "PRODUCT_P3_QUERY_OPERATIONS",
    "PRODUCT_P3_MUTATION_ENABLE_ENV",
    "PRODUCT_P3_TEXT_ENABLE_ENV",
    "ProductCompositionSettings",
    "ProductP2RetriableFaultPlan",
    "ProductP3StaleFaultPlan",
    "create_product_composition_registry_from_environment",
    "product_composition_enabled_from_environment",
]
