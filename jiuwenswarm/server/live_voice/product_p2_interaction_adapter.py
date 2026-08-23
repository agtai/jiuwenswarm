# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Authority-first product activation seam for P2 and Interaction Intelligence.

This package is deliberately not a product composition root.  It allocates the
injected runtime and Interaction Engine only after ``P2AuthorityAdapter.bind``
has returned an exact authenticated context.  An active lease is package-level
truth only: it does not claim a formal product route or real Agent/Tool/browser
observation.

``InteractionAction`` values remain intentions.  This module never performs an
Agent, Tool, Task, history, presentation, playback, response, round, or task
cancellation effect on behalf of an Interaction Engine.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ResponseRef,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)

from .agent_conversation_runtime import (
    AgentConversationHandle,
    AgentConversationNotification,
    AgentGenerationInterruption,
    AgentConversationShutdownResult,
    AgentConversationShutdownStatus,
    AuthoritativePresentationHandle,
    PresentationAckResult,
)
from .conversation_runtime_loop import BargeInResult
from .interaction_engine import InteractionAction, InteractionEnginePort
from .presentation_ledger import (
    PresentationAck,
    PresentationSurface,
    TaskPresentationRuntimeReceipt,
)
from .product_authority import (
    AuthorityRouteContext,
    P2AuthenticatedContext,
    P2AuthorityAdapter,
    ProductAuthorityUnavailable,
)
from .task_progress_return import TaskProgressNotificationIntent


_P2_OPERATION = "agent.chat"
_P2_CAPABILITIES = frozenset({_P2_OPERATION})
_MAX_NOTIFICATION_BATCH = 16


class ProductP2AdapterViolation(ValueError):
    """Stable, content-free rejection from the package activation boundary."""

    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


def _violation(reason: str, message: str, code: ErrorCode) -> ProductP2AdapterViolation:
    return ProductP2AdapterViolation(reason, message, code)


def _require_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise _violation(
            "INVALID_ACTIVATION_BINDING",
            f"{field_name} must be a non-empty bounded string",
            ErrorCode.INVALID_ARGUMENT,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _violation(
            "INVALID_ACTIVATION_BINDING",
            f"{field_name} must contain Unicode scalar values",
            ErrorCode.INVALID_ARGUMENT,
        ) from None
    return value


def _require_generation(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise _violation(
            "INVALID_ACTIVATION_BINDING",
            "activation_generation must be a positive integer",
            ErrorCode.INVALID_ARGUMENT,
        )
    return value


def _require_timeout(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise _violation(
            "INVALID_CLOSE_TIMEOUT",
            "close timeout must be positive and finite",
            ErrorCode.INVALID_ARGUMENT,
        )
    return float(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _authority_activity(
    context: P2AuthenticatedContext,
    clock: Callable[[], datetime],
) -> bool | None:
    try:
        expires_at = datetime.fromisoformat(
            context.authority.expires_at.replace("Z", "+00:00")
        )
        now = clock()
    except Exception:
        return None
    return (
        expires_at.tzinfo is not None
        and isinstance(now, datetime)
        and now.tzinfo is not None
        and expires_at.astimezone(UTC) > now.astimezone(UTC)
    )


def _route_fingerprint(request: P2InteractionActivationRequest) -> str:
    route = request.route
    payload = {
        "session_id": route.session_id,
        "correlation_id": route.correlation_id,
        "claimed_user_id": route.claimed_user_id,
        "claimed_project_id": route.claimed_project_id,
        "claimed_scope": (
            None if route.claimed_scope is None else route.claimed_scope.to_dict()
        ),
        "claimed_context_ref": (
            None
            if route.claimed_context_ref is None
            else route.claimed_context_ref.to_dict()
        ),
        "routing_claims": [
            {"source": item.source, "name": item.name, "value": item.value}
            for item in route.routing_claims
        ],
        "interaction_id": request.interaction_id,
        "activation_id": request.activation_id,
        "activation_generation": request.activation_generation,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class P2InteractionActivationRequest:
    """Untrusted product-route inputs; none of these values grants authority."""

    route: AuthorityRouteContext
    interaction_id: str
    activation_id: str
    activation_generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.route, AuthorityRouteContext):
            raise _violation(
                "INVALID_ACTIVATION_REQUEST",
                "route must be an AuthorityRouteContext",
                ErrorCode.INVALID_ARGUMENT,
            )
        _require_text(self.interaction_id, "interaction_id")
        _require_text(self.activation_id, "activation_id")
        _require_generation(self.activation_generation)

    def __repr__(self) -> str:
        return (
            "P2InteractionActivationRequest("
            f"interaction_id={self.interaction_id!r}, "
            f"activation_id={self.activation_id!r}, "
            f"activation_generation={self.activation_generation})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class P2InteractionBinding:
    """Exact immutable authority-derived binding retained for the lease."""

    session_id: str
    correlation_id: str
    interaction_id: str
    activation_id: str
    activation_generation: int
    scope: ScopeRef = field(repr=False)

    def __post_init__(self) -> None:
        _require_text(self.session_id, "session_id")
        _require_text(self.correlation_id, "correlation_id")
        _require_text(self.interaction_id, "interaction_id")
        _require_text(self.activation_id, "activation_id")
        _require_generation(self.activation_generation)
        if (
            not isinstance(self.scope, ScopeRef)
            or self.scope.session_id != self.session_id
        ):
            raise _violation(
                "INVALID_ACTIVATION_BINDING",
                "scope must exactly bind the persisted session",
                ErrorCode.INVALID_ARGUMENT,
            )

    def __repr__(self) -> str:
        return (
            "P2InteractionBinding("
            f"session_id={self.session_id!r}, "
            f"correlation_id={self.correlation_id!r}, "
            f"interaction_id={self.interaction_id!r}, "
            f"activation_id={self.activation_id!r}, "
            f"activation_generation={self.activation_generation})"
        )


class P2ActivationStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class P2ActivationReason(StrEnum):
    ACTIVATION_LEASE_OPEN = "ACTIVATION_LEASE_OPEN"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    AUTHORITY_DENIED = "AUTHORITY_DENIED"
    AUTHORITY_UNAVAILABLE = "AUTHORITY_UNAVAILABLE"
    ACTIVATION_BINDING_CONFLICT = "ACTIVATION_BINDING_CONFLICT"
    RUNTIME_FACTORY_FAILED = "RUNTIME_FACTORY_FAILED"
    INTERACTION_ENGINE_FACTORY_FAILED = "INTERACTION_ENGINE_FACTORY_FAILED"
    RUNTIME_START_FAILED = "RUNTIME_START_FAILED"
    INTERACTION_OPEN_FAILED = "INTERACTION_OPEN_FAILED"
    NOTIFICATION_CONSUMER_ATTACH_FAILED = "NOTIFICATION_CONSUMER_ATTACH_FAILED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


@dataclass(frozen=True, slots=True, init=False)
class P2FoundationEvidence:
    """Honest source/package evidence; never product route evidence."""

    evidence_scope: str
    evidence_ids: tuple[str, ...]
    notification_backpressure_closed: bool
    formal_route_ready: bool
    real_runtime_path_observed: bool

    def __init__(self) -> None:
        object.__setattr__(self, "evidence_scope", "package_only")
        object.__setattr__(
            self,
            "evidence_ids",
            ("P2_NOTIFICATION_BACKPRESSURE_CLOSED",),
        )
        object.__setattr__(self, "notification_backpressure_closed", True)
        object.__setattr__(self, "formal_route_ready", False)
        object.__setattr__(self, "real_runtime_path_observed", False)


P2_FOUNDATION_EVIDENCE = P2FoundationEvidence()
_PREPARED_ACTIVATION_TOKEN = object()


class P2CancellationScope(StrEnum):
    PLAYBACK_STOP = "playback.stop"
    RESPONSE_CANCEL = "response.cancel"
    ROUND_CANCEL = "round.cancel"
    TASK_CANCEL = "task.cancel"


_CANCELLATION_SCOPES = {
    item.value: item
    for item in (
        P2CancellationScope.PLAYBACK_STOP,
        P2CancellationScope.RESPONSE_CANCEL,
        P2CancellationScope.ROUND_CANCEL,
        P2CancellationScope.TASK_CANCEL,
    )
}


@dataclass(frozen=True, slots=True)
class P2InteractionIntent:
    """One accepted or replayed Engine proposal with zero executed effect."""

    action: InteractionAction
    accepted: bool
    cancellation_scope: P2CancellationScope | None
    effect_owner: str = "none_intent_only"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class P2PreparedActivation:
    """Immutable authority/request comparison created before allocation."""

    context: P2AuthenticatedContext
    request: P2InteractionActivationRequest
    binding: P2InteractionBinding
    route_fingerprint_sha256: str = field(repr=False)

    def __init__(
        self,
        context: P2AuthenticatedContext,
        request: P2InteractionActivationRequest,
        binding: P2InteractionBinding,
        route_fingerprint_sha256: str,
        *,
        _token: object,
    ) -> None:
        if _token is not _PREPARED_ACTIVATION_TOKEN:
            raise _violation(
                "INVALID_PREPARED_ACTIVATION",
                "prepared activation must be created by its owning Adapter",
                ErrorCode.PERMISSION_DENIED,
            )
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "binding", binding)
        object.__setattr__(
            self,
            "route_fingerprint_sha256",
            route_fingerprint_sha256,
        )

    def __repr__(self) -> str:
        return f"P2PreparedActivation(binding={self.binding!r})"


class P2LeaseState(StrEnum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


class P2LeaseCloseStatus(StrEnum):
    CLOSED = "closed"
    PENDING = "pending"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class P2LeaseCloseResult:
    status: P2LeaseCloseStatus
    detail: str


@dataclass(frozen=True, slots=True)
class P2FailedActivationCleanupSnapshot:
    binding: P2InteractionBinding
    status: P2LeaseCloseStatus
    attempts: int


@dataclass(frozen=True, slots=True)
class P2ActivationLeaseSnapshot:
    binding: P2InteractionBinding
    state: P2LeaseState
    accepted_intents: int
    evidence: P2FoundationEvidence


@runtime_checkable
class _P2RuntimePort(Protocol):
    async def start(self) -> bool: ...

    async def open_interaction(self, interaction_id: str) -> None: ...

    async def close(
        self, *, timeout_seconds: float
    ) -> AgentConversationShutdownResult: ...


P2RuntimeFactory = Callable[
    [P2AuthenticatedContext, P2InteractionBinding], _P2RuntimePort
]
P2InteractionEngineFactory = Callable[
    [P2AuthenticatedContext, P2InteractionBinding], InteractionEnginePort
]


class P2FailedActivationCleanup:
    """Retained teardown owner for a runtime that never became an active lease."""

    def __init__(
        self,
        *,
        binding: P2InteractionBinding,
        runtime: _P2RuntimePort,
        close_poll_seconds: float,
    ) -> None:
        self._binding = binding
        self._runtime = runtime
        self._close_poll_seconds = close_poll_seconds
        self._lock = threading.RLock()
        self._status = P2LeaseCloseStatus.PENDING
        self._attempts = 0
        self._coordinator: asyncio.Task[P2LeaseCloseResult] | None = None

    @property
    def binding(self) -> P2InteractionBinding:
        return self._binding

    async def cleanup(
        self,
        binding: P2InteractionBinding,
        *,
        timeout_seconds: float,
        retry_failed: bool = False,
    ) -> P2LeaseCloseResult:
        """Retry or observe teardown without transferring coordinator ownership."""

        self._require_exact_binding(binding)
        timeout = _require_timeout(timeout_seconds)
        if type(retry_failed) is not bool:
            raise _violation(
                "INVALID_CLEANUP_RETRY",
                "retry_failed must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        coordinator = self._ensure_coordinator(retry_failed=retry_failed)
        try:
            return await asyncio.wait_for(asyncio.shield(coordinator), timeout=timeout)
        except TimeoutError:
            return P2LeaseCloseResult(
                P2LeaseCloseStatus.PENDING,
                "retained_failed_activation_teardown_running",
            )

    def snapshot(self) -> P2FailedActivationCleanupSnapshot:
        with self._lock:
            return P2FailedActivationCleanupSnapshot(
                binding=self._binding,
                status=self._status,
                attempts=self._attempts,
            )

    def _ensure_coordinator(
        self, *, retry_failed: bool
    ) -> asyncio.Task[P2LeaseCloseResult]:
        with self._lock:
            if self._status is P2LeaseCloseStatus.CLOSED:
                assert self._coordinator is not None
                return self._coordinator
            if self._coordinator is None or (
                retry_failed
                and self._status is P2LeaseCloseStatus.FAILED
                and self._coordinator.done()
            ):
                self._status = P2LeaseCloseStatus.PENDING
                self._attempts += 1
                self._coordinator = asyncio.create_task(
                    self._run_cleanup(),
                    name=(
                        "live-voice-p2-failed-activation-cleanup:"
                        f"{self._binding.activation_id}:{self._attempts}"
                    ),
                )
            return self._coordinator

    def _require_exact_binding(self, binding: P2InteractionBinding) -> None:
        if not isinstance(binding, P2InteractionBinding) or binding != self._binding:
            raise _violation(
                "ACTIVATION_BINDING_MISMATCH",
                "cleanup requires the exact retained activation binding",
                ErrorCode.PERMISSION_DENIED,
            )

    async def _run_cleanup(self) -> P2LeaseCloseResult:
        try:
            while True:
                result = await self._runtime.close(
                    timeout_seconds=self._close_poll_seconds
                )
                if result.status is AgentConversationShutdownStatus.PENDING:
                    await asyncio.sleep(self._close_poll_seconds)
                    continue
                if result.status is AgentConversationShutdownStatus.CLOSED:
                    with self._lock:
                        self._status = P2LeaseCloseStatus.CLOSED
                    return P2LeaseCloseResult(
                        P2LeaseCloseStatus.CLOSED,
                        "failed_activation_teardown_complete",
                    )
                with self._lock:
                    self._status = P2LeaseCloseStatus.FAILED
                return P2LeaseCloseResult(
                    P2LeaseCloseStatus.FAILED,
                    "failed_activation_teardown_failed",
                )
        except asyncio.CancelledError:
            with self._lock:
                self._status = P2LeaseCloseStatus.PENDING
            raise
        except Exception:
            with self._lock:
                self._status = P2LeaseCloseStatus.FAILED
            return P2LeaseCloseResult(
                P2LeaseCloseStatus.FAILED,
                "failed_activation_teardown_failed",
            )


class P2ActivationLease:
    """Exact-binding package lease with retained, shielded close ownership."""

    def __init__(
        self,
        *,
        context: P2AuthenticatedContext,
        binding: P2InteractionBinding,
        runtime: _P2RuntimePort,
        interaction_engine: InteractionEnginePort,
        close_poll_seconds: float,
        clock: Callable[[], datetime],
    ) -> None:
        self._context = context
        self._binding = binding
        self._runtime = runtime
        self._interaction_engine = interaction_engine
        self._close_poll_seconds = close_poll_seconds
        self._clock = clock
        self._state = P2LeaseState.OPEN
        self._state_lock = threading.RLock()
        self._operation_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._close_coordinator: asyncio.Task[P2LeaseCloseResult] | None = None
        attach_consumer = getattr(runtime, "attach_notification_consumer", None)
        self._notification_lease = (
            attach_consumer(
                consumer_id=f"product-p2:{binding.activation_id}",
                connection_epoch=binding.activation_generation,
            )
            if callable(attach_consumer)
            else None
        )
        self._notification_detached = False

    @property
    def binding(self) -> P2InteractionBinding:
        return self._binding

    @property
    def authenticated_context(self) -> P2AuthenticatedContext:
        return self._context

    def propose_action(
        self, binding: P2InteractionBinding, action: InteractionAction
    ) -> P2InteractionIntent:
        """Validate and retain an intent without executing any owned effect."""

        with self._state_lock:
            self._require_open_exact_binding(binding)
            if not isinstance(action, InteractionAction):
                raise _violation(
                    "INVALID_INTERACTION_ACTION",
                    "action must be a typed InteractionAction",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if (
                action.scope != self._binding.scope
                or action.interaction_id != self._binding.interaction_id
            ):
                raise _violation(
                    "INTERACTION_ACTION_BINDING_MISMATCH",
                    "action must match the exact activation scope and interaction",
                    ErrorCode.PERMISSION_DENIED,
                )
            accepted, retained = self._interaction_engine.propose(action)
            return P2InteractionIntent(
                action=retained,
                accepted=accepted,
                cancellation_scope=_CANCELLATION_SCOPES.get(retained.operation),
            )

    async def submit_committed_turn(
        self,
        binding: P2InteractionBinding,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        context: FormalContextSnapshot,
        channel_id: str = "web",
        before_dispatch: Callable[[ResponseRef, str], Awaitable[None]] | None = None,
        after_dispatch: Callable[[AgentConversationHandle], None] | None = None,
        allow_tools: bool = True,
        supersedes: ResponseRef | None = None,
    ) -> AgentConversationHandle:
        """Forward one exact committed turn through the retained runtime owner.

        ``supersedes`` carries the exact response this committed speech
        replaces.  It must belong to the activated interaction, so one browser
        activation can never fence another interaction response.
        """

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            if (
                supersedes is not None
                and supersedes.interaction_id != binding.interaction_id
            ):
                raise _violation(
                    "SUPERSEDED_RESPONSE_BINDING_MISMATCH",
                    "a replacement turn must supersede its own activated interaction",
                    ErrorCode.PERMISSION_DENIED,
                )
            submit = getattr(self._runtime, "submit_committed_turn", None)
            if not callable(submit):
                raise _violation(
                    "PRODUCT_TURN_SUBMISSION_UNAVAILABLE",
                    "retained runtime has no product TurnCommit owner",
                    ErrorCode.UNAVAILABLE,
                )
            outcome = await submit(
                request_id=request_id,
                response_id=response_id,
                correlation_id=correlation_id,
                commit=commit,
                context=context,
                channel_id=channel_id,
                before_dispatch=before_dispatch,
                after_dispatch=after_dispatch,
                allow_tools=allow_tools,
                supersedes=supersedes,
            )
            if not isinstance(outcome, AgentConversationHandle):
                raise _violation(
                    "PRODUCT_TURN_SUBMISSION_UNAVAILABLE",
                    "retained runtime returned no canonical Agent handle",
                    ErrorCode.UNAVAILABLE,
                )
            return outcome

    async def select_formal_context(
        self, binding: P2InteractionBinding
    ) -> FormalContextSnapshot:
        """Read one immutable CR-selected context snapshot under lease authority."""

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            select = getattr(self._runtime, "select_formal_context", None)
            if not callable(select):
                raise _violation(
                    "PRODUCT_FORMAL_CONTEXT_UNAVAILABLE",
                    "retained runtime has no formal context selector",
                    ErrorCode.UNAVAILABLE,
                )
            outcome = select(binding.interaction_id)
            if (
                not isinstance(outcome, FormalContextSnapshot)
                or outcome.scope != binding.scope
            ):
                raise _violation(
                    "PRODUCT_FORMAL_CONTEXT_UNAVAILABLE",
                    "retained runtime returned no exact formal context snapshot",
                    ErrorCode.UNAVAILABLE,
                )
            return outcome

    async def accept_task_origin(
        self,
        binding: P2InteractionBinding,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
    ) -> ResponseRef:
        """Bind a Task-bound commit to one canonical CR response without dispatch."""

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            accept = getattr(self._runtime, "accept_task_origin", None)
            if not callable(accept):
                raise _violation(
                    "PRODUCT_TASK_ORIGIN_UNAVAILABLE",
                    "retained runtime has no canonical Task-origin response owner",
                    ErrorCode.UNAVAILABLE,
                )
            outcome = await accept(
                request_id=request_id,
                response_id=response_id,
                correlation_id=correlation_id,
                commit=commit,
            )
            if not isinstance(outcome, ResponseRef):
                raise _violation(
                    "PRODUCT_TASK_ORIGIN_UNAVAILABLE",
                    "retained runtime returned no canonical Task-origin response",
                    ErrorCode.UNAVAILABLE,
                )
            return outcome

    async def present_authoritative_text(
        self,
        binding: P2InteractionBinding,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        text: str,
        channel_id: str = "web",
        response_generation: int | None = None,
        source_provenance: str = "server.authoritative",
        before_publish: Callable[[AuthoritativePresentationHandle], Awaitable[None]]
        | None = None,
    ) -> AuthoritativePresentationHandle:
        """Publish server-owned text through the retained CR presentation path."""

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            present = getattr(self._runtime, "present_authoritative_text", None)
            if not callable(present):
                raise _violation(
                    "PRODUCT_AUTHORITATIVE_PRESENTATION_UNAVAILABLE",
                    "retained runtime has no authoritative presentation owner",
                    ErrorCode.UNAVAILABLE,
                )
            outcome = await present(
                request_id=request_id,
                response_id=response_id,
                correlation_id=correlation_id,
                commit=commit,
                text=text,
                channel_id=channel_id,
                response_generation=response_generation,
                before_publish=before_publish,
                _source_provenance=source_provenance,
            )
            if not isinstance(outcome, AuthoritativePresentationHandle):
                raise _violation(
                    "PRODUCT_AUTHORITATIVE_PRESENTATION_UNAVAILABLE",
                    "retained runtime returned no canonical presentation handle",
                    ErrorCode.UNAVAILABLE,
                )
            return outcome

    async def present_task_notification(
        self,
        binding: P2InteractionBinding,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        text: str,
        channel_id: str = "web",
        presentation_surface: PresentationSurface = PresentationSurface.TEXT,
        publish_notification: bool = True,
        before_publish: Callable[[AuthoritativePresentationHandle], Awaitable[None]]
        | None = None,
    ) -> AuthoritativePresentationHandle:
        """Present TaskEvent-derived text without inventing user-history input."""

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            foreground_safe = getattr(
                self._runtime, "task_notification_foreground_safe", None
            )
            if not callable(foreground_safe) or foreground_safe() is not True:
                raise _violation(
                    "PRODUCT_TASK_NOTIFICATION_FOREGROUND_BUSY",
                    "Task notification must wait for the current response presentation",
                    ErrorCode.UNAVAILABLE,
                )
            present = getattr(self._runtime, "present_authoritative_text", None)
            if not callable(present):
                raise _violation(
                    "PRODUCT_TASK_NOTIFICATION_UNAVAILABLE",
                    "retained runtime has no Task notification presentation owner",
                    ErrorCode.UNAVAILABLE,
                )
            outcome = await present(
                request_id=request_id,
                response_id=response_id,
                correlation_id=correlation_id,
                commit=commit,
                text=text,
                channel_id=channel_id,
                before_publish=before_publish,
                _persist_user_history=False,
                _source_provenance="server.task_notification",
                _presentation_surface=presentation_surface,
                _publish_notification=publish_notification,
            )
            if not isinstance(outcome, AuthoritativePresentationHandle):
                raise _violation(
                    "PRODUCT_TASK_NOTIFICATION_UNAVAILABLE",
                    "retained runtime returned no canonical Task notification handle",
                    ErrorCode.UNAVAILABLE,
                )
            return outcome

    def task_notification_foreground_safe(self, binding: P2InteractionBinding) -> bool:
        """Return the exact retained Runtime foreground fence for Task audio."""

        with self._state_lock:
            self._require_open_exact_binding(binding)
        foreground_safe = getattr(
            self._runtime, "task_notification_foreground_safe", None
        )
        return callable(foreground_safe) and foreground_safe() is True

    def task_presentation_runtime_authority(
        self,
        binding: P2InteractionBinding,
        response_ref: ResponseRef,
        reservation_id: str | None,
        phase: str,
    ) -> TaskPresentationRuntimeReceipt:
        """Forward one exact active Task-presentation phase to Runtime ownership."""

        with self._state_lock:
            self._require_open_exact_binding(binding)
        if (
            not isinstance(response_ref, ResponseRef)
            or response_ref.interaction_id != binding.interaction_id
        ):
            raise _violation(
                "PRODUCT_TASK_PRESENTATION_BINDING_MISMATCH",
                "Task presentation must bind the active interaction response",
                ErrorCode.PERMISSION_DENIED,
            )
        authorize = getattr(self._runtime, "task_presentation_runtime_authority", None)
        if not callable(authorize):
            raise _violation(
                "PRODUCT_TASK_PRESENTATION_AUTHORITY_UNAVAILABLE",
                "retained Runtime has no Task presentation authority",
                ErrorCode.UNAVAILABLE,
            )
        receipt = authorize(response_ref, reservation_id, phase)
        if (
            not isinstance(receipt, TaskPresentationRuntimeReceipt)
            or receipt.response_ref != response_ref
            or receipt.phase != phase
            or (reservation_id is not None and receipt.reservation_id != reservation_id)
        ):
            raise _violation(
                "PRODUCT_TASK_PRESENTATION_AUTHORITY_UNAVAILABLE",
                "retained Runtime returned no exact Task presentation receipt",
                ErrorCode.UNAVAILABLE,
            )
        return receipt

    async def fail_task_presentation(
        self,
        binding: P2InteractionBinding,
        response_ref: ResponseRef,
        reservation_id: str,
        *,
        reason: str,
    ) -> bool:
        """Forward one exact browser playout failure to the Runtime owner."""

        with self._state_lock:
            self._require_open_exact_binding(binding)
        fail = getattr(self._runtime, "fail_task_presentation", None)
        if not callable(fail):
            raise _violation(
                "PRODUCT_TASK_NOTIFICATION_UNAVAILABLE",
                "retained Runtime has no Task presentation failure owner",
                ErrorCode.UNAVAILABLE,
            )
        outcome = await fail(
            response_ref,
            reservation_id,
            reason=reason,
        )
        if type(outcome) is not bool:
            raise _violation(
                "PRODUCT_TASK_NOTIFICATION_UNAVAILABLE",
                "Runtime returned no canonical Task presentation failure result",
                ErrorCode.UNAVAILABLE,
            )
        return outcome

    async def deliver_task_progress(
        self,
        binding: P2InteractionBinding,
        intent: TaskProgressNotificationIntent,
        response_ref: ResponseRef,
    ) -> bool:
        """Deliver one exact voice-origin progress intent through CR ownership."""

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            if (
                not isinstance(intent, TaskProgressNotificationIntent)
                or intent.origin.scope != binding.scope
                or intent.origin.session_id != binding.session_id
                or intent.origin.origin_id != binding.interaction_id
                or not isinstance(response_ref, ResponseRef)
                or response_ref.interaction_id != binding.interaction_id
            ):
                raise _violation(
                    "TASK_PROGRESS_ORIGIN_MISMATCH",
                    "progress intent does not bind the exact active P2 route",
                    ErrorCode.PERMISSION_DENIED,
                )
            deliver = getattr(self._runtime, "accept_task_progress_notification", None)
            if not callable(deliver):
                raise _violation(
                    "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE",
                    "retained runtime has no CR progress notification owner",
                    ErrorCode.UNAVAILABLE,
                )
            delivered = await deliver(intent, response_ref=response_ref)
            if delivered is not True:
                raise _violation(
                    "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE",
                    "Conversation Runtime rejected the progress notification",
                    ErrorCode.UNAVAILABLE,
                )
            return True

    async def next_notification(
        self, binding: P2InteractionBinding
    ) -> AgentConversationNotification:
        """Read one notification only for the current exact activation owner."""

        with self._state_lock:
            self._require_open_exact_binding(binding)
        read = (
            getattr(self._runtime, "next_notification_for", None)
            if self._notification_lease is not None
            else getattr(self._runtime, "next_notification", None)
        )
        if not callable(read):
            raise _violation(
                "PRODUCT_NOTIFICATION_UNAVAILABLE",
                "retained runtime has no product notification owner",
                ErrorCode.UNAVAILABLE,
            )
        notification = (
            await read(self._notification_lease)
            if self._notification_lease is not None
            else await read()
        )
        if not isinstance(notification, AgentConversationNotification):
            raise _violation(
                "PRODUCT_NOTIFICATION_UNAVAILABLE",
                "retained runtime returned no canonical notification",
                ErrorCode.UNAVAILABLE,
            )
        return notification

    async def next_notifications(
        self,
        binding: P2InteractionBinding,
        *,
        limit: int,
        continue_after: Callable[[AgentConversationNotification], bool] | None = None,
    ) -> tuple[AgentConversationNotification, ...]:
        """Wait for one notification, then drain only the already-queued tail."""

        if type(limit) is not int or not 1 <= limit <= _MAX_NOTIFICATION_BATCH:
            raise _violation(
                "INVALID_NOTIFICATION_BATCH_LIMIT",
                "notification batch limit must be an integer from 1 to 16",
                ErrorCode.INVALID_ARGUMENT,
            )
        first = await self.next_notification(binding)
        if limit == 1 or (continue_after is not None and not continue_after(first)):
            return (first,)
        drain = getattr(self._runtime, "drain_notifications_for", None)
        if not callable(drain) or self._notification_lease is None:
            return (first,)
        notifications = [first]
        while len(notifications) < limit:
            tail = await drain(self._notification_lease, limit=1)
            if not isinstance(tail, tuple) or any(
                not isinstance(item, AgentConversationNotification) for item in tail
            ):
                raise _violation(
                    "PRODUCT_NOTIFICATION_UNAVAILABLE",
                    "retained runtime returned no canonical notification batch",
                    ErrorCode.UNAVAILABLE,
                )
            if not tail:
                break
            notification = tail[0]
            notifications.append(notification)
            if continue_after is not None and not continue_after(notification):
                break
        return tuple(notifications)

    async def acknowledge_presentation(
        self,
        binding: P2InteractionBinding,
        ack: PresentationAck,
    ) -> PresentationAckResult:
        """Forward an exact presentation ACK to the retained history owner."""

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            acknowledge = getattr(self._runtime, "acknowledge_presentation", None)
            if not callable(acknowledge):
                raise _violation(
                    "PRODUCT_PRESENTATION_ACK_UNAVAILABLE",
                    "retained runtime has no presentation ACK owner",
                    ErrorCode.UNAVAILABLE,
                )
            outcome = await acknowledge(ack)
            if not isinstance(outcome, PresentationAckResult):
                raise _violation(
                    "PRODUCT_PRESENTATION_ACK_UNAVAILABLE",
                    "retained runtime returned no canonical ACK outcome",
                    ErrorCode.UNAVAILABLE,
                )
            return outcome

    async def barge_in(
        self,
        binding: P2InteractionBinding,
        *,
        action_id: str,
        response: ResponseRef,
        cancel_response: bool,
    ) -> BargeInResult:
        """Interrupt only the exact response owned by this activation."""

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            if response.interaction_id != binding.interaction_id:
                raise _violation(
                    "BARGE_IN_BINDING_MISMATCH",
                    "barge-in must target the exact activated interaction",
                    ErrorCode.PERMISSION_DENIED,
                )
            interrupt = getattr(self._runtime, "barge_in", None)
            if not callable(interrupt):
                raise _violation(
                    "PRODUCT_BARGE_IN_UNAVAILABLE",
                    "retained runtime has no barge-in owner",
                    ErrorCode.UNAVAILABLE,
                )
            outcome = await interrupt(
                action_id,
                response,
                cancel_response=cancel_response,
            )
            if not isinstance(outcome, BargeInResult):
                raise _violation(
                    "PRODUCT_BARGE_IN_UNAVAILABLE",
                    "retained runtime returned no canonical barge-in result",
                    ErrorCode.UNAVAILABLE,
                )
            return outcome

    async def interrupt_generation(
        self,
        binding: P2InteractionBinding,
        *,
        action_id: str,
        response: ResponseRef,
    ) -> AgentGenerationInterruption:
        """Fence one unfinished response owned by this exact activation.

        This never widens beyond ``round.cancel``: the lease exposes no
        cancellation scope at all, so a caller cannot ask it to reach a
        background Task.
        """

        async with self._operation_lock:
            with self._state_lock:
                self._require_open_exact_binding(binding)
            if response.interaction_id != binding.interaction_id:
                raise _violation(
                    "GENERATION_INTERRUPT_BINDING_MISMATCH",
                    "generation interruption must target the exact activated interaction",
                    ErrorCode.PERMISSION_DENIED,
                )
            interrupt = getattr(self._runtime, "interrupt_generation", None)
            if not callable(interrupt):
                raise _violation(
                    "PRODUCT_GENERATION_INTERRUPT_UNAVAILABLE",
                    "retained runtime has no generation interruption owner",
                    ErrorCode.UNAVAILABLE,
                )
            outcome = await interrupt(action_id=action_id, ref=response)
            if not isinstance(outcome, AgentGenerationInterruption):
                raise _violation(
                    "PRODUCT_GENERATION_INTERRUPT_UNAVAILABLE",
                    "retained runtime returned no canonical interruption result",
                    ErrorCode.UNAVAILABLE,
                )
            return outcome

    async def close(
        self, binding: P2InteractionBinding, *, timeout_seconds: float
    ) -> P2LeaseCloseResult:
        """Observe one retained close coordinator through a bounded shielded wait."""

        self._require_exact_binding(binding)
        timeout = _require_timeout(timeout_seconds)
        async with self._close_lock:
            if self._close_coordinator is None:
                with self._state_lock:
                    if self._state is P2LeaseState.OPEN:
                        self._state = P2LeaseState.CLOSING
                self._close_coordinator = asyncio.create_task(
                    self._run_close(),
                    name=f"live-voice-p2-activation-close:{self._binding.activation_id}",
                )
            coordinator = self._close_coordinator
        try:
            return await asyncio.wait_for(asyncio.shield(coordinator), timeout=timeout)
        except TimeoutError:
            return P2LeaseCloseResult(
                P2LeaseCloseStatus.PENDING,
                "retained_activation_teardown_running",
            )

    def snapshot(self) -> P2ActivationLeaseSnapshot:
        with self._state_lock:
            return P2ActivationLeaseSnapshot(
                binding=self._binding,
                state=self._state,
                accepted_intents=len(self._interaction_engine.accepted()),
                evidence=P2_FOUNDATION_EVIDENCE,
            )

    def _require_open_exact_binding(self, binding: P2InteractionBinding) -> None:
        self._require_exact_binding(binding)
        if self._state is not P2LeaseState.OPEN:
            raise _violation(
                "ACTIVATION_LEASE_NOT_OPEN",
                "interaction intent requires an open activation lease",
                ErrorCode.CONFLICT,
            )
        authority_active = _authority_activity(self._context, self._clock)
        if authority_active is None:
            raise _violation(
                "ACTIVATION_AUTHORITY_UNAVAILABLE",
                "interaction intent cannot verify retained authority",
                ErrorCode.UNAVAILABLE,
            )
        if not authority_active:
            raise _violation(
                "ACTIVATION_AUTHORITY_EXPIRED",
                "interaction intent requires active retained authority",
                ErrorCode.PERMISSION_DENIED,
            )

    def _require_exact_binding(self, binding: P2InteractionBinding) -> None:
        if not isinstance(binding, P2InteractionBinding) or binding != self._binding:
            raise _violation(
                "ACTIVATION_BINDING_MISMATCH",
                "operation requires the exact retained activation binding",
                ErrorCode.PERMISSION_DENIED,
            )

    async def _run_close(self) -> P2LeaseCloseResult:
        try:
            async with self._operation_lock:
                if (
                    self._notification_lease is not None
                    and not self._notification_detached
                ):
                    detach = getattr(
                        self._runtime, "detach_notification_consumer", None
                    )
                    if not callable(detach):
                        raise RuntimeError(
                            "retained runtime lost its notification detach owner"
                        )
                    detach(self._notification_lease)
                    self._notification_detached = True
                while True:
                    result = await self._runtime.close(
                        timeout_seconds=self._close_poll_seconds
                    )
                    if result.status is AgentConversationShutdownStatus.PENDING:
                        await asyncio.sleep(self._close_poll_seconds)
                        continue
                    if result.status is AgentConversationShutdownStatus.CLOSED:
                        with self._state_lock:
                            self._state = P2LeaseState.CLOSED
                        return P2LeaseCloseResult(
                            P2LeaseCloseStatus.CLOSED, "activation_teardown_complete"
                        )
                    with self._state_lock:
                        self._state = P2LeaseState.FAILED
                    return P2LeaseCloseResult(
                        P2LeaseCloseStatus.FAILED, "runtime_teardown_failed"
                    )
        except BaseException:  # noqa: BLE001 - retain safe, content-free truth
            with self._state_lock:
                self._state = P2LeaseState.FAILED
            return P2LeaseCloseResult(
                P2LeaseCloseStatus.FAILED, "runtime_teardown_failed"
            )


@dataclass(frozen=True, slots=True, repr=False)
class P2ActivationResult:
    status: P2ActivationStatus
    reason: P2ActivationReason
    lease: P2ActivationLease | None = field(default=None, repr=False)
    cleanup: P2FailedActivationCleanup | None = field(default=None, repr=False)
    replayed: bool = False
    evidence: P2FoundationEvidence = P2_FOUNDATION_EVIDENCE

    def __post_init__(self) -> None:
        valid_reasons = {
            P2ActivationStatus.ACTIVE: frozenset(
                {P2ActivationReason.ACTIVATION_LEASE_OPEN}
            ),
            P2ActivationStatus.DISABLED: frozenset(
                {P2ActivationReason.FEATURE_DISABLED}
            ),
            P2ActivationStatus.DENIED: frozenset(
                {
                    P2ActivationReason.AUTHORITY_DENIED,
                    P2ActivationReason.ACTIVATION_BINDING_CONFLICT,
                }
            ),
            P2ActivationStatus.UNAVAILABLE: frozenset(
                {P2ActivationReason.AUTHORITY_UNAVAILABLE}
            ),
            P2ActivationStatus.FAILED: frozenset(
                {
                    P2ActivationReason.RUNTIME_FACTORY_FAILED,
                    P2ActivationReason.INTERACTION_ENGINE_FACTORY_FAILED,
                    P2ActivationReason.RUNTIME_START_FAILED,
                    P2ActivationReason.INTERACTION_OPEN_FAILED,
                    P2ActivationReason.NOTIFICATION_CONSUMER_ATTACH_FAILED,
                    P2ActivationReason.ROLLBACK_FAILED,
                }
            ),
        }
        if (
            type(self.status) is not P2ActivationStatus
            or type(self.reason) is not P2ActivationReason
            or self.reason not in valid_reasons[self.status]
        ):
            raise _violation(
                "INVALID_ACTIVATION_RESULT",
                "activation status and reason must use one closed combination",
                ErrorCode.INVALID_ARGUMENT,
            )
        if type(self.replayed) is not bool or (
            self.replayed
            and (
                self.status is not P2ActivationStatus.ACTIVE
                or self.reason is not P2ActivationReason.ACTIVATION_LEASE_OPEN
            )
        ):
            raise _violation(
                "INVALID_ACTIVATION_RESULT",
                "replayed is a strict boolean valid only for an active lease",
                ErrorCode.INVALID_ARGUMENT,
            )
        if self.evidence is not P2_FOUNDATION_EVIDENCE:
            raise _violation(
                "INVALID_ACTIVATION_RESULT",
                "activation result requires exact locked package evidence",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (self.status is P2ActivationStatus.ACTIVE) != (self.lease is not None):
            raise _violation(
                "INVALID_ACTIVATION_RESULT",
                "only an active result may carry an activation lease",
                ErrorCode.INVALID_ARGUMENT,
            )
        if self.lease is not None and not isinstance(self.lease, P2ActivationLease):
            raise _violation(
                "INVALID_ACTIVATION_RESULT",
                "active result requires a typed activation lease",
                ErrorCode.INVALID_ARGUMENT,
            )
        if self.cleanup is not None and not isinstance(
            self.cleanup, P2FailedActivationCleanup
        ):
            raise _violation(
                "INVALID_ACTIVATION_RESULT",
                "rollback failure requires a typed retained cleanup owner",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (self.cleanup is not None) != (
            self.status is P2ActivationStatus.FAILED
            and self.reason is P2ActivationReason.ROLLBACK_FAILED
            and self.lease is None
        ):
            raise _violation(
                "INVALID_ACTIVATION_RESULT",
                "retained cleanup belongs only to failed rollback truth",
                ErrorCode.INVALID_ARGUMENT,
            )

    def __repr__(self) -> str:
        return (
            "P2ActivationResult("
            f"status={self.status.value!r}, reason={self.reason.value!r}, "
            f"replayed={self.replayed})"
        )


class ProductP2InteractionAdapter:
    """Default-off authority-first allocator for one exact P2 interaction."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        authority_adapter: P2AuthorityAdapter,
        runtime_factory: P2RuntimeFactory,
        interaction_engine_factory: P2InteractionEngineFactory,
        cleanup_timeout_seconds: float = 0.1,
        close_poll_seconds: float = 0.05,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if type(enabled) is not bool:
            raise _violation(
                "INVALID_FEATURE_FLAG",
                "enabled must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not isinstance(authority_adapter, P2AuthorityAdapter):
            raise _violation(
                "INVALID_AUTHORITY_ADAPTER",
                "authority_adapter must be P2AuthorityAdapter",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not callable(runtime_factory) or not callable(interaction_engine_factory):
            raise _violation(
                "INVALID_ACTIVATION_FACTORY",
                "activation factories must be callable",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not callable(clock):
            raise _violation(
                "INVALID_ACTIVATION_CLOCK",
                "activation clock must be callable",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._enabled = enabled
        self._authority_adapter = authority_adapter
        self._runtime_factory = runtime_factory
        self._interaction_engine_factory = interaction_engine_factory
        self._cleanup_timeout_seconds = _require_timeout(cleanup_timeout_seconds)
        self._close_poll_seconds = _require_timeout(close_poll_seconds)
        self._clock = clock
        self._activation_lock = asyncio.Lock()
        self._leases: dict[tuple[str, str], P2ActivationLease] = {}
        self._failed_cleanups: dict[
            tuple[str, str, str, str, int], P2FailedActivationCleanup
        ] = {}

    def retained_failed_cleanups(self) -> tuple[P2FailedActivationCleanup, ...]:
        """Return typed teardown owners retained after incomplete rollback."""

        return tuple(self._failed_cleanups.values())

    async def activate(self, request: object) -> P2ActivationResult:
        """Standalone path: bind once before allocation and runtime effects."""

        if not self._enabled:
            return P2ActivationResult(
                P2ActivationStatus.DISABLED,
                P2ActivationReason.FEATURE_DISABLED,
            )
        if not isinstance(request, P2InteractionActivationRequest):
            raise _violation(
                "INVALID_ACTIVATION_REQUEST",
                "activation requires a typed request",
                ErrorCode.INVALID_ARGUMENT,
            )
        async with self._activation_lock:
            try:
                context = self._authority_adapter.bind(
                    request.route,
                    operation=_P2_OPERATION,
                    required_capabilities=_P2_CAPABILITIES,
                )
            except ProductAuthorityUnavailable:
                return P2ActivationResult(
                    P2ActivationStatus.UNAVAILABLE,
                    P2ActivationReason.AUTHORITY_UNAVAILABLE,
                )
            if context is None:
                return P2ActivationResult(
                    P2ActivationStatus.DENIED,
                    P2ActivationReason.AUTHORITY_DENIED,
                )
            prepared = self._prepare_activation(context, request)
            return await self._activate_prepared_locked(prepared)

    def prepare_activation(
        self,
        context: object,
        request: object,
    ) -> P2PreparedActivation:
        """Immutably bind one IO-resolved authority context to its request."""

        if not self._enabled:
            raise _violation(
                "FEATURE_DISABLED",
                "P2 activation preparation is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if not isinstance(context, P2AuthenticatedContext) or not isinstance(
            request, P2InteractionActivationRequest
        ):
            raise _violation(
                "INVALID_PREPARED_ACTIVATION",
                "preparation requires an authenticated context and request",
                ErrorCode.INVALID_ARGUMENT,
            )
        return self._prepare_activation(context, request)

    async def activate_prepared(
        self,
        prepared: object,
    ) -> P2ActivationResult:
        """Allocate from one authority context already resolved by the IO root.

        This path never invokes ``P2AuthorityAdapter.bind``.  It allows the
        product composition owner to resolve canonical Authority exactly once,
        establish its own route truth, and only then invoke the downstream P2
        allocator.
        """

        if not self._enabled:
            return P2ActivationResult(
                P2ActivationStatus.DISABLED,
                P2ActivationReason.FEATURE_DISABLED,
            )
        if not isinstance(prepared, P2PreparedActivation):
            raise _violation(
                "INVALID_PREPARED_ACTIVATION",
                "activation requires an immutable prepared authority request",
                ErrorCode.INVALID_ARGUMENT,
            )
        async with self._activation_lock:
            return await self._activate_prepared_locked(prepared)

    def _prepare_activation(
        self,
        context: P2AuthenticatedContext,
        request: P2InteractionActivationRequest,
    ) -> P2PreparedActivation:
        binding = self._binding_from(context, request)
        return P2PreparedActivation(
            context,
            request,
            binding,
            _route_fingerprint(request),
            _token=_PREPARED_ACTIVATION_TOKEN,
        )

    async def _activate_prepared_locked(
        self,
        prepared: P2PreparedActivation,
    ) -> P2ActivationResult:
        context = prepared.context
        request = prepared.request
        binding = self._binding_from(context, request)
        if (
            binding != prepared.binding
            or _route_fingerprint(request) != prepared.route_fingerprint_sha256
        ):
            raise _violation(
                "PREPARED_ACTIVATION_TAMPERED",
                "prepared activation changed after authority comparison",
                ErrorCode.PERMISSION_DENIED,
            )
        authority_active = _authority_activity(context, self._clock)
        if authority_active is None:
            return P2ActivationResult(
                P2ActivationStatus.UNAVAILABLE,
                P2ActivationReason.AUTHORITY_UNAVAILABLE,
            )
        if not authority_active:
            return P2ActivationResult(
                P2ActivationStatus.DENIED,
                P2ActivationReason.AUTHORITY_DENIED,
            )
        lease_key = (binding.session_id, binding.interaction_id)
        for cleanup_key, cleanup in tuple(self._failed_cleanups.items()):
            snapshot = cleanup.snapshot()
            if snapshot.status is P2LeaseCloseStatus.CLOSED:
                self._failed_cleanups.pop(cleanup_key, None)
                continue
            if (
                snapshot.binding.session_id == binding.session_id
                and snapshot.binding.interaction_id == binding.interaction_id
            ):
                return P2ActivationResult(
                    P2ActivationStatus.FAILED,
                    P2ActivationReason.ROLLBACK_FAILED,
                    cleanup=cleanup,
                )
        existing = self._leases.get(lease_key)
        if existing is not None:
            existing_state = existing.snapshot().state
            if existing.binding == binding and existing_state is P2LeaseState.OPEN:
                return P2ActivationResult(
                    P2ActivationStatus.ACTIVE,
                    P2ActivationReason.ACTIVATION_LEASE_OPEN,
                    lease=existing,
                    replayed=True,
                )
            if (
                existing_state in {P2LeaseState.CLOSING, P2LeaseState.CLOSED}
                and binding.activation_generation
                > existing.binding.activation_generation
            ):
                # Close publishes its lifecycle fence synchronously before the
                # retained Runtime waits for an already accepted Agent turn.
                # A newer transport generation may therefore allocate without
                # reviving or polling the predecessor.  Its shielded close
                # coordinator remains the sole owner of predecessor teardown.
                self._leases.pop(lease_key)
                return await self._allocate(context, binding, lease_key)
            return P2ActivationResult(
                P2ActivationStatus.DENIED,
                P2ActivationReason.ACTIVATION_BINDING_CONFLICT,
            )
        return await self._allocate(context, binding, lease_key)

    def _binding_from(
        self,
        context: P2AuthenticatedContext,
        request: P2InteractionActivationRequest,
    ) -> P2InteractionBinding:
        authority = context.authority
        route = request.route
        if (
            context.scope != authority.scope
            or authority.session_id != route.session_id
            or authority.correlation_id != route.correlation_id
            or authority.operation != _P2_OPERATION
            or authority.capabilities != _P2_CAPABILITIES
            or (
                route.claimed_user_id is not None
                and route.claimed_user_id != authority.principal_id
            )
            or (
                route.claimed_project_id is not None
                and route.claimed_project_id != authority.project_id
            )
            or (
                route.claimed_scope is not None
                and route.claimed_scope != authority.scope
            )
        ):
            raise _violation(
                "AUTHORITY_BINDING_MISMATCH",
                "authority did not return the exact requested P2 binding",
                ErrorCode.PERMISSION_DENIED,
            )
        claimed_context = route.claimed_context_ref
        if claimed_context is not None:
            if (
                claimed_context.scope != authority.scope
                or claimed_context.redaction.redacted
            ):
                raise _violation(
                    "AUTHORITY_BINDING_MISMATCH",
                    "prepared ContextRef must match exact unredacted authority scope",
                    ErrorCode.PERMISSION_DENIED,
                )
            if claimed_context.expires_at is not None:
                try:
                    expires_at = datetime.fromisoformat(
                        claimed_context.expires_at.replace("Z", "+00:00")
                    )
                    now = self._clock()
                except Exception:
                    raise _violation(
                        "AUTHORITY_BINDING_UNAVAILABLE",
                        "prepared ContextRef activity cannot be verified",
                        ErrorCode.UNAVAILABLE,
                    ) from None
                if (
                    expires_at.tzinfo is None
                    or not isinstance(now, datetime)
                    or now.tzinfo is None
                ):
                    raise _violation(
                        "AUTHORITY_BINDING_UNAVAILABLE",
                        "prepared ContextRef activity cannot be verified",
                        ErrorCode.UNAVAILABLE,
                    )
                if expires_at.astimezone(UTC) <= now.astimezone(UTC):
                    raise _violation(
                        "AUTHORITY_BINDING_MISMATCH",
                        "prepared ContextRef must remain active",
                        ErrorCode.PERMISSION_DENIED,
                    )
        return P2InteractionBinding(
            session_id=authority.session_id,
            correlation_id=authority.correlation_id,
            interaction_id=request.interaction_id,
            activation_id=request.activation_id,
            activation_generation=request.activation_generation,
            scope=context.scope,
        )

    async def _allocate(
        self,
        context: P2AuthenticatedContext,
        binding: P2InteractionBinding,
        lease_key: tuple[str, str],
    ) -> P2ActivationResult:
        runtime: _P2RuntimePort | None = None
        try:
            runtime = self._runtime_factory(context, binding)
        except asyncio.CancelledError:
            raise
        except Exception:  # factory text is never presented
            return P2ActivationResult(
                P2ActivationStatus.FAILED,
                P2ActivationReason.RUNTIME_FACTORY_FAILED,
            )
        if not isinstance(runtime, _P2RuntimePort):
            return P2ActivationResult(
                P2ActivationStatus.FAILED,
                P2ActivationReason.RUNTIME_FACTORY_FAILED,
            )
        try:
            engine = self._interaction_engine_factory(context, binding)
        except asyncio.CancelledError:
            await self._cleanup_before_reraise(runtime, binding)
            raise
        except Exception:
            return await self._settle_partial_failure(
                runtime,
                binding,
                P2ActivationReason.INTERACTION_ENGINE_FACTORY_FAILED,
            )
        except BaseException:
            await self._cleanup_before_reraise(runtime, binding)
            raise
        if not isinstance(engine, InteractionEnginePort):
            return await self._settle_partial_failure(
                runtime,
                binding,
                P2ActivationReason.INTERACTION_ENGINE_FACTORY_FAILED,
            )
        try:
            started = await runtime.start()
        except asyncio.CancelledError:
            await self._cleanup_before_reraise(runtime, binding)
            raise
        except Exception:
            return await self._settle_partial_failure(
                runtime,
                binding,
                P2ActivationReason.RUNTIME_START_FAILED,
            )
        except BaseException:
            await self._cleanup_before_reraise(runtime, binding)
            raise
        if not started:
            return await self._settle_partial_failure(
                runtime,
                binding,
                P2ActivationReason.RUNTIME_START_FAILED,
            )
        try:
            await runtime.open_interaction(binding.interaction_id)
        except asyncio.CancelledError:
            await self._cleanup_before_reraise(runtime, binding)
            raise
        except Exception:
            return await self._settle_partial_failure(
                runtime,
                binding,
                P2ActivationReason.INTERACTION_OPEN_FAILED,
            )
        except BaseException:
            await self._cleanup_before_reraise(runtime, binding)
            raise
        try:
            lease = P2ActivationLease(
                context=context,
                binding=binding,
                runtime=runtime,
                interaction_engine=engine,
                close_poll_seconds=self._close_poll_seconds,
                clock=self._clock,
            )
        except asyncio.CancelledError:
            await self._cleanup_before_reraise(runtime, binding)
            raise
        except Exception:
            return await self._settle_partial_failure(
                runtime,
                binding,
                P2ActivationReason.NOTIFICATION_CONSUMER_ATTACH_FAILED,
            )
        except BaseException:
            await self._cleanup_before_reraise(runtime, binding)
            raise
        self._leases[lease_key] = lease
        return P2ActivationResult(
            P2ActivationStatus.ACTIVE,
            P2ActivationReason.ACTIVATION_LEASE_OPEN,
            lease=lease,
        )

    async def _settle_partial_failure(
        self,
        runtime: _P2RuntimePort,
        binding: P2InteractionBinding,
        reason: P2ActivationReason,
    ) -> P2ActivationResult:
        cleanup = self._retain_cleanup(runtime, binding)
        result = await cleanup.cleanup(
            binding,
            timeout_seconds=self._cleanup_timeout_seconds,
        )
        if result.status is P2LeaseCloseStatus.CLOSED:
            self._failed_cleanups.pop(self._cleanup_key(binding), None)
            return P2ActivationResult(P2ActivationStatus.FAILED, reason)
        return P2ActivationResult(
            P2ActivationStatus.FAILED,
            P2ActivationReason.ROLLBACK_FAILED,
            cleanup=cleanup,
        )

    async def _cleanup_before_reraise(
        self,
        runtime: _P2RuntimePort,
        binding: P2InteractionBinding,
    ) -> None:
        cleanup = self._retain_cleanup(runtime, binding)
        try:
            result = await cleanup.cleanup(
                binding,
                timeout_seconds=self._cleanup_timeout_seconds,
            )
        except asyncio.CancelledError:
            return
        if result.status is P2LeaseCloseStatus.CLOSED:
            self._failed_cleanups.pop(self._cleanup_key(binding), None)

    def _retain_cleanup(
        self,
        runtime: _P2RuntimePort,
        binding: P2InteractionBinding,
    ) -> P2FailedActivationCleanup:
        cleanup = P2FailedActivationCleanup(
            binding=binding,
            runtime=runtime,
            close_poll_seconds=self._close_poll_seconds,
        )
        self._failed_cleanups[self._cleanup_key(binding)] = cleanup
        return cleanup

    @staticmethod
    def _cleanup_key(
        binding: P2InteractionBinding,
    ) -> tuple[str, str, str, str, int]:
        return (
            binding.session_id,
            binding.correlation_id,
            binding.interaction_id,
            binding.activation_id,
            binding.activation_generation,
        )


__all__ = [
    "P2ActivationLease",
    "P2ActivationLeaseSnapshot",
    "P2ActivationReason",
    "P2ActivationResult",
    "P2ActivationStatus",
    "P2CancellationScope",
    "P2FailedActivationCleanup",
    "P2FailedActivationCleanupSnapshot",
    "P2FoundationEvidence",
    "P2InteractionActivationRequest",
    "P2InteractionBinding",
    "P2InteractionIntent",
    "P2LeaseCloseResult",
    "P2LeaseCloseStatus",
    "P2LeaseState",
    "P2PreparedActivation",
    "ProductP2AdapterViolation",
    "ProductP2InteractionAdapter",
]
