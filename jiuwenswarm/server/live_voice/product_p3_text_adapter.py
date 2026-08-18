# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Default-off trusted P3 query and truthful text-progress composition seam.

This package does not authenticate a request, issue confirmations, register a
route, mutate a Task, write Chat/history, or activate voice progress.  The
server-owned :class:`P3AuthorityAdapter` must resolve one exact query grant
before the injected context-revalidating query owner or subscription factory
is touched.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    InputCommitState,
    ProducerRef,
    QueryEnvelope,
    ResultEnvelope,
)

from .formal_task_models import FormalTaskViolation, TaskAuthorizationGrant, utc_now
from .product_authority import (
    AuthorityResourceBinding,
    AuthorityRouteContext,
    P3AuthorityAdapter,
    P3AuthorityContext,
    ProductAuthorityUnavailable,
)
from .progress_notification_arbiter import ProgressNotificationArbiter
from .task_event_subscription import TaskEventSubscription
from .task_progress_return import (
    ForegroundSupplier,
    GenerationIsCurrent,
    PreparedTaskProgressSource,
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
    TaskProgressNotificationIntent,
    TaskProgressReturnActivation,
    TaskProgressReturnBridge,
    TaskProgressReturnLease,
    TaskProgressReturnReason,
    TaskProgressTextEvent,
    TextEventSink,
    VoiceIntentSink,
)
from .voice_task_policy import FormalTaskPolicyAdapter, FormalTaskPolicyInput


_QUERY_OPERATIONS = frozenset({"task.get", "task.list", "task.status", "task.events"})
_MUTATION_OPERATIONS = frozenset({"task.create", "task.adjust", "task.cancel"})


class ProductP3TextReason(StrEnum):
    FEATURE_DISABLED = "PRODUCT_P3_TEXT_FEATURE_DISABLED"
    INVALID_REQUEST = "PRODUCT_P3_TEXT_INVALID_REQUEST"
    UNSUPPORTED_OPERATION = "PRODUCT_P3_TEXT_UNSUPPORTED_OPERATION"
    MUTATION_CONFIRMATION_UNAVAILABLE = (
        "PRODUCT_P3_MUTATION_CONFIRMATION_ISSUER_UNAVAILABLE"
    )
    AUTHORITY_DENIED = "PRODUCT_P3_TEXT_AUTHORITY_DENIED"
    AUTHORITY_UNAVAILABLE = "PRODUCT_P3_TEXT_AUTHORITY_UNAVAILABLE"
    QUERY_ACCEPTED = "PRODUCT_P3_QUERY_ACCEPTED"
    QUERY_REJECTED = "PRODUCT_P3_QUERY_REJECTED"
    QUERY_FAILED = "PRODUCT_P3_QUERY_FAILED"
    PROGRESS_ACTIVATED = "PRODUCT_P3_TEXT_PROGRESS_ACTIVATED"
    PROGRESS_ACTIVATION_FAILED = "PRODUCT_P3_TEXT_PROGRESS_ACTIVATION_FAILED"
    PROGRESS_CLEANUP_CAPACITY = "PRODUCT_P3_TEXT_CLEANUP_CAPACITY_EXHAUSTED"


class ProductP3CleanupState(StrEnum):
    NEW = "new"
    DETACHING = "detaching"
    FAILED = "failed"
    CLOSED = "closed"


class ProductP3CleanupReason(StrEnum):
    RETAINED = "PRODUCT_P3_TEXT_CLEANUP_RETAINED"
    DETACHING = "PRODUCT_P3_TEXT_CLEANUP_DETACHING"
    DETACH_FAILED = "PRODUCT_P3_TEXT_CLEANUP_DETACH_FAILED"
    DETACHED = "PRODUCT_P3_TEXT_CLEANUP_DETACHED"


_NO_CLEANUP_PROGRESS_REASONS = frozenset(
    {
        ProductP3TextReason.FEATURE_DISABLED.value,
        ProductP3TextReason.INVALID_REQUEST.value,
        ProductP3TextReason.AUTHORITY_DENIED.value,
        ProductP3TextReason.AUTHORITY_UNAVAILABLE.value,
        ProductP3TextReason.PROGRESS_CLEANUP_CAPACITY.value,
        TaskProgressReturnReason.FEATURE_DISABLED.value,
        TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE.value,
    }
)

_OPTIONAL_CLEANUP_PROGRESS_REASONS = frozenset(
    {ProductP3TextReason.PROGRESS_ACTIVATION_FAILED.value}
)

_INACTIVE_PRODUCT_PROGRESS_REASONS = frozenset(
    {
        ProductP3TextReason.FEATURE_DISABLED.value,
        ProductP3TextReason.INVALID_REQUEST.value,
        ProductP3TextReason.AUTHORITY_DENIED.value,
        ProductP3TextReason.AUTHORITY_UNAVAILABLE.value,
        ProductP3TextReason.PROGRESS_ACTIVATION_FAILED.value,
        ProductP3TextReason.PROGRESS_CLEANUP_CAPACITY.value,
    }
)

_INACTIVE_TASK_PROGRESS_REASONS = frozenset(
    {
        TaskProgressReturnReason.FEATURE_DISABLED.value,
        TaskProgressReturnReason.AUTHORIZATION_REJECTED.value,
        TaskProgressReturnReason.INVALID_BINDING.value,
        TaskProgressReturnReason.STALE_GENERATION.value,
        TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE.value,
        TaskProgressReturnReason.HANDOFF_REJECTED.value,
        TaskProgressReturnReason.SOURCE_FAILED.value,
        TaskProgressReturnReason.CLOSED_BEFORE_ACTIVATION.value,
        TaskProgressReturnReason.ALREADY_SETTLED.value,
    }
)

_INACTIVE_PROGRESS_REASONS = (
    _INACTIVE_PRODUCT_PROGRESS_REASONS | _INACTIVE_TASK_PROGRESS_REASONS
)


@dataclass(frozen=True, slots=True)
class ProductP3QueryRequest:
    route: AuthorityRouteContext
    operation: str
    request_id: str
    task_id: str | None = None
    after_seq: int = -1
    resource: AuthorityResourceBinding | None = None


@dataclass(frozen=True, slots=True)
class ProductP3QueryResult:
    ok: bool
    reason_id: ProductP3TextReason
    result: ResultEnvelope | None


@dataclass(frozen=True, slots=True)
class ProductP3AuthorizedQuery:
    """Exact trusted input for the injected project-context query owner.

    The owner must revalidate the persisted Task's project Context against its
    current server-owned project snapshot before it invokes Task Core.  A bare
    ``PersistentTaskCore.query`` is intentionally not this interface.
    """

    authority: P3AuthorityContext
    envelope: QueryEnvelope
    authorization: TaskAuthorizationGrant


@dataclass(frozen=True, slots=True)
class ProductP3ProgressRequest:
    route: AuthorityRouteContext
    task_id: str
    origin_kind: TaskProgressOriginKind
    origin_id: str
    generation_kind: str
    generation_id: str
    generation: int
    source_instance_id: str
    progress_producer: ProducerRef
    progress_adapter: str
    resource: AuthorityResourceBinding | None = None


@dataclass(frozen=True, slots=True)
class ProductP3CleanupSnapshot:
    cleanup_id: str
    binding: TaskProgressOriginBinding
    state: ProductP3CleanupState
    reason_id: ProductP3CleanupReason
    attempts: int
    task_pending: bool
    activation_pending: bool
    activation_active: bool | None
    active_lease_closed: bool
    effects_committed: bool
    effects_fenced: bool
    effect_waiters: int
    wait_timeouts: int
    cancelled_waiters: int


class ProductP3ProgressCleanupHandle:
    """Retained, retryable ownership of one inactive subscription detach."""

    __slots__ = (
        "_attempts",
        "_activation_task",
        "_activation_active",
        "_active_lease_closed",
        "_binding",
        "_cancelled_waiters",
        "_cleanup_id",
        "_effect_decision",
        "_effects_committed",
        "_effects_fenced",
        "_effect_waiters",
        "_owner_loop",
        "_reason",
        "_state",
        "_subscription",
        "_task",
        "_wait_timeouts",
    )

    def __init__(
        self,
        *,
        cleanup_id: str,
        binding: TaskProgressOriginBinding,
        subscription: object,
    ) -> None:
        if not _valid_text(cleanup_id):
            raise ValueError("product P3 cleanup id must be non-empty")
        if not isinstance(binding, TaskProgressOriginBinding):
            raise ValueError("product P3 cleanup binding is required")
        self._cleanup_id = cleanup_id
        self._binding = binding
        self._subscription = subscription
        self._activation_task: asyncio.Task[TaskProgressReturnActivation] | None = None
        self._activation_active: bool | None = None
        self._active_lease_closed = False
        self._effect_decision = asyncio.Event()
        self._effects_committed = False
        self._effects_fenced = False
        self._effect_waiters = 0
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._state = ProductP3CleanupState.NEW
        self._reason = ProductP3CleanupReason.RETAINED
        self._attempts = 0
        self._wait_timeouts = 0
        self._cancelled_waiters = 0

    @property
    def cleanup_id(self) -> str:
        return self._cleanup_id

    @property
    def binding(self) -> TaskProgressOriginBinding:
        return self._binding

    def start(self) -> ProductP3CleanupSnapshot:
        """Start or retain one detach attempt without coupling it to a waiter."""

        loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = loop
        elif self._owner_loop is not loop:
            raise RuntimeError("product P3 cleanup belongs to another event loop")
        # A cleanup owner exists only when no active result can safely be exposed.
        # Fence product sinks synchronously before the retained detach task can race
        # an activation that finishes after its original caller was cancelled.
        if self._effects_committed:
            raise RuntimeError("product P3 activation effects are already committed")
        self._effects_fenced = True
        self._effect_decision.set()
        task = self._task
        if self._state is ProductP3CleanupState.CLOSED:
            return self.snapshot()
        if task is not None and not task.done():
            return self.snapshot()
        self._attempts += 1
        self._state = ProductP3CleanupState.DETACHING
        self._reason = ProductP3CleanupReason.DETACHING
        self._task = loop.create_task(
            self._detach_once(), name=f"live-voice-p3-cleanup:{self._cleanup_id}"
        )
        return self.snapshot()

    def attach_activation_task(
        self, task: asyncio.Task[TaskProgressReturnActivation]
    ) -> None:
        """Retain the only in-flight activation before any caller can cancel."""

        if not isinstance(task, asyncio.Task):
            raise ValueError("product P3 cleanup activation task is required")
        if self._activation_task is not None:
            raise RuntimeError("product P3 cleanup activation task is already retained")
        task_loop = task.get_loop()
        if self._owner_loop is None:
            self._owner_loop = task_loop
        elif self._owner_loop is not task_loop:
            raise RuntimeError("product P3 cleanup belongs to another event loop")
        self._activation_task = task

    def commit_effects(self) -> None:
        """Expose sinks only after the active lease can be returned to its caller."""

        loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = loop
        elif self._owner_loop is not loop:
            raise RuntimeError("product P3 cleanup belongs to another event loop")
        if self._effects_fenced or self._state is not ProductP3CleanupState.NEW:
            raise RuntimeError("product P3 cleanup already fenced activation effects")
        self._effects_committed = True
        self._effect_decision.set()

    async def wait_effect_permission(self, binding: TaskProgressOriginBinding) -> bool:
        """Wait for exact activation commit or cleanup fencing."""

        if binding != self._binding:
            return False
        loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = loop
        elif self._owner_loop is not loop:
            return False
        self._effect_waiters += 1
        try:
            await self._effect_decision.wait()
        finally:
            self._effect_waiters -= 1
        return self._effects_committed and not self._effects_fenced

    async def close(self, *, timeout: float | None = None) -> ProductP3CleanupSnapshot:
        """Observe retained detach; timeout/cancellation never cancels ownership."""

        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("product P3 cleanup timeout must be positive and finite")
        self.start()
        task = self._task
        if task is None:
            return self.snapshot()
        try:
            if timeout is None:
                await asyncio.shield(task)
            else:
                await asyncio.wait_for(asyncio.shield(task), float(timeout))
        except TimeoutError:
            self._wait_timeouts += 1
        except asyncio.CancelledError:
            self._cancelled_waiters += 1
            raise
        return self.snapshot()

    def snapshot(self) -> ProductP3CleanupSnapshot:
        task = self._task
        activation_task = self._activation_task
        return ProductP3CleanupSnapshot(
            cleanup_id=self._cleanup_id,
            binding=self._binding,
            state=self._state,
            reason_id=self._reason,
            attempts=self._attempts,
            task_pending=task is not None and not task.done(),
            activation_pending=(
                activation_task is not None and not activation_task.done()
            ),
            activation_active=self._activation_active,
            active_lease_closed=self._active_lease_closed,
            effects_committed=self._effects_committed,
            effects_fenced=self._effects_fenced,
            effect_waiters=self._effect_waiters,
            wait_timeouts=self._wait_timeouts,
            cancelled_waiters=self._cancelled_waiters,
        )

    async def _detach_once(self) -> None:
        close = getattr(self._subscription, "close", None)
        raw_close_resolved = False
        try:
            if not callable(close):
                raise TypeError("subscription has no close owner")
            await cast(Callable[[], Awaitable[None]], close)()
            raw_close_resolved = True
        except asyncio.CancelledError:
            pass
        except Exception:  # retained handle reports and permits an exact retry
            pass
        activation = await self._settle_activation()
        if activation is False:
            self._state = ProductP3CleanupState.FAILED
            self._reason = ProductP3CleanupReason.DETACH_FAILED
            return
        lease_close_resolved = False
        if isinstance(activation, TaskProgressReturnActivation):
            self._activation_active = activation.active
            lease = activation.lease
            if activation.active and lease is not None:
                try:
                    await lease.close()
                    self._active_lease_closed = True
                    lease_close_resolved = True
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
            elif activation.active:
                self._state = ProductP3CleanupState.FAILED
                self._reason = ProductP3CleanupReason.DETACH_FAILED
                return
        detach_resolved = (
            lease_close_resolved
            if isinstance(activation, TaskProgressReturnActivation)
            and activation.active
            else raw_close_resolved
        )
        if not detach_resolved:
            self._state = ProductP3CleanupState.FAILED
            self._reason = ProductP3CleanupReason.DETACH_FAILED
            return
        self._state = ProductP3CleanupState.CLOSED
        self._reason = ProductP3CleanupReason.DETACHED

    async def _settle_activation(self) -> TaskProgressReturnActivation | None | bool:
        task = self._activation_task
        if task is None:
            return None
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                return None
            if task.done():
                try:
                    return task.result()
                except asyncio.CancelledError:
                    return None
                except Exception:
                    return None
            return False
        except Exception:
            return None


@dataclass(frozen=True, slots=True)
class ProductP3ProgressActivation:
    """Typed activation truth; cleanup is non-formal inactive ownership only."""

    active: bool
    reason_id: str
    binding: TaskProgressOriginBinding | None
    lease: TaskProgressReturnLease | None
    cleanup: ProductP3ProgressCleanupHandle | None = None

    def __post_init__(self) -> None:
        if type(self.active) is not bool or not _valid_text(self.reason_id):
            raise ValueError("invalid product P3 progress activation")
        if self.active:
            if (
                self.reason_id != ProductP3TextReason.PROGRESS_ACTIVATED.value
                or not isinstance(self.binding, TaskProgressOriginBinding)
                or not isinstance(self.lease, TaskProgressReturnLease)
                or self.cleanup is not None
            ):
                raise ValueError("active product P3 progress requires its exact lease")
            return
        if self.reason_id not in _INACTIVE_PROGRESS_REASONS:
            raise ValueError("inactive product P3 progress reason is not allowed")
        if self.lease is not None:
            raise ValueError(
                "inactive product P3 progress cannot carry an active lease"
            )
        if self.cleanup is None:
            if self.binding is not None:
                raise ValueError(
                    "inactive product P3 binding requires cleanup ownership"
                )
            if self.reason_id not in (
                _NO_CLEANUP_PROGRESS_REASONS | _OPTIONAL_CLEANUP_PROGRESS_REASONS
            ):
                raise ValueError(
                    "inactive product P3 progress reason requires cleanup ownership"
                )
            return
        if (
            not isinstance(self.cleanup, ProductP3ProgressCleanupHandle)
            or self.binding != self.cleanup.binding
            or self.reason_id in _NO_CLEANUP_PROGRESS_REASONS
            or self.cleanup.snapshot().state is ProductP3CleanupState.NEW
        ):
            raise ValueError("product P3 cleanup must retain the exact binding")


class ProductP3QueryOwner(Protocol):
    """Read-only context-revalidating owner; it must never dispatch mutation."""

    def query(
        self,
        query: ProductP3AuthorizedQuery,
        *,
        now: str | None = None,
    ) -> ResultEnvelope: ...


class ProductP3SubscriptionFactory(Protocol):
    """Allocate an exact live subscription only after trusted authorization."""

    def __call__(
        self,
        authorization: TaskAuthorizationGrant,
        binding: TaskProgressOriginBinding,
    ) -> TaskEventSubscription: ...


class ProductP3PreparedSourceFactory(Protocol):
    def __call__(
        self,
        authorization: TaskAuthorizationGrant,
        binding: TaskProgressOriginBinding,
    ) -> PreparedTaskProgressSource: ...


def _valid_text(value: object) -> bool:
    if type(value) is not str or not value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


class ProductP3TextAdapter:
    """Authority-first product seam for P3 queries and text/UI progress."""

    def __init__(
        self,
        *,
        enabled: bool,
        authority: P3AuthorityAdapter,
        query_owner: ProductP3QueryOwner,
        subscription_factory: ProductP3SubscriptionFactory,
        prepared_source_factory: ProductP3PreparedSourceFactory | None = None,
        replay_text_from_prepared_source: bool = False,
        generation_is_current: GenerationIsCurrent,
        arbiter: ProgressNotificationArbiter,
        foreground: ForegroundSupplier,
        text_sink: TextEventSink,
        voice_sink: VoiceIntentSink,
        policy: FormalTaskPolicyAdapter | None = None,
        cleanup_capacity: int = 64,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        if (
            type(enabled) is not bool
            or type(replay_text_from_prepared_source) is not bool
        ):
            raise ValueError("product P3 text flag must be boolean")
        if not isinstance(authority, P3AuthorityAdapter):
            raise ValueError("product P3 authority adapter is required")
        if not callable(getattr(query_owner, "query", None)):
            raise ValueError("product P3 query owner is required")
        for name, dependency in (
            ("subscription_factory", subscription_factory),
            ("generation_is_current", generation_is_current),
            ("foreground", foreground),
            ("text_sink", text_sink),
            ("voice_sink", voice_sink),
            ("clock", clock),
        ):
            if not callable(dependency):
                raise ValueError(f"product P3 {name} is required")
        if not isinstance(arbiter, ProgressNotificationArbiter):
            raise ValueError("product P3 progress arbiter is required")
        if policy is not None and not isinstance(policy, FormalTaskPolicyAdapter):
            raise ValueError("product P3 task policy is invalid")
        if type(cleanup_capacity) is not int or cleanup_capacity <= 0:
            raise ValueError("product P3 cleanup capacity must be positive")
        self._enabled = enabled
        self._authority = authority
        self._query_owner = query_owner
        self._subscription_factory = subscription_factory
        if prepared_source_factory is not None and not callable(
            prepared_source_factory
        ):
            raise ValueError("product P3 prepared source factory is invalid")
        self._prepared_source_factory = prepared_source_factory
        self._replay_text_from_prepared_source = replay_text_from_prepared_source
        self._generation_is_current = generation_is_current
        self._arbiter = arbiter
        self._foreground = foreground
        self._text_sink = text_sink
        self._voice_sink = voice_sink
        self._policy = policy or FormalTaskPolicyAdapter()
        self._cleanup_capacity = cleanup_capacity
        self._cleanup_sequence = 0
        self._cleanups: dict[str, ProductP3ProgressCleanupHandle] = {}
        self._clock = clock

    def retained_cleanups(self) -> tuple[ProductP3ProgressCleanupHandle, ...]:
        """Return typed retained cleanup owners, including failed retries."""

        return tuple(
            handle
            for handle in self._cleanups.values()
            if handle.snapshot().state is not ProductP3CleanupState.NEW
        )

    def retained_cleanup(
        self, cleanup_id: str
    ) -> ProductP3ProgressCleanupHandle | None:
        handle = self._cleanups.get(cleanup_id)
        if handle is None or handle.snapshot().state is ProductP3CleanupState.NEW:
            return None
        return handle

    def forget_cleanup(self, cleanup_id: str) -> bool:
        """Release only an observed, successfully detached cleanup owner."""

        handle = self._cleanups.get(cleanup_id)
        if (
            handle is None
            or handle.snapshot().state is not ProductP3CleanupState.CLOSED
        ):
            return False
        del self._cleanups[cleanup_id]
        return True

    async def query(self, request: object) -> ProductP3QueryResult:
        """One-shot convenience path: resolve once, then use the prepared seam."""

        if not self._enabled:
            return ProductP3QueryResult(
                False, ProductP3TextReason.FEATURE_DISABLED, None
            )
        if not isinstance(request, ProductP3QueryRequest):
            return ProductP3QueryResult(
                False, ProductP3TextReason.INVALID_REQUEST, None
            )
        if request.operation in _MUTATION_OPERATIONS:
            return ProductP3QueryResult(
                False,
                ProductP3TextReason.MUTATION_CONFIRMATION_UNAVAILABLE,
                None,
            )
        if request.operation not in _QUERY_OPERATIONS:
            return ProductP3QueryResult(
                False, ProductP3TextReason.UNSUPPORTED_OPERATION, None
            )
        if not self._valid_query_request(request):
            return ProductP3QueryResult(
                False, ProductP3TextReason.INVALID_REQUEST, None
            )

        try:
            context = self._authority.resolve(
                request.route,
                operation=request.operation,
                required_capabilities=frozenset({request.operation}),
                target_task_id=request.task_id,
                resource=request.resource,
            )
        except ProductAuthorityUnavailable:
            return ProductP3QueryResult(
                False, ProductP3TextReason.AUTHORITY_UNAVAILABLE, None
            )
        if context is None:
            return ProductP3QueryResult(
                False, ProductP3TextReason.AUTHORITY_DENIED, None
            )
        grant = self._authority.to_task_grant(context, None)
        if grant is None:
            return ProductP3QueryResult(
                False, ProductP3TextReason.AUTHORITY_DENIED, None
            )
        return await self.activate_prepared_query(request, context, grant)

    async def activate_prepared_query(
        self,
        request: object,
        context: object,
        grant: object,
    ) -> ProductP3QueryResult:
        """Invoke the read-only owner from one already-resolved exact grant."""

        if not self._enabled:
            return ProductP3QueryResult(
                False, ProductP3TextReason.FEATURE_DISABLED, None
            )
        if not isinstance(request, ProductP3QueryRequest):
            return ProductP3QueryResult(
                False, ProductP3TextReason.INVALID_REQUEST, None
            )
        if request.operation in _MUTATION_OPERATIONS:
            return ProductP3QueryResult(
                False,
                ProductP3TextReason.MUTATION_CONFIRMATION_UNAVAILABLE,
                None,
            )
        if request.operation not in _QUERY_OPERATIONS:
            return ProductP3QueryResult(
                False, ProductP3TextReason.UNSUPPORTED_OPERATION, None
            )
        if not self._valid_query_request(request):
            return ProductP3QueryResult(
                False, ProductP3TextReason.INVALID_REQUEST, None
            )
        if not self._prepared_authority_matches(
            request.route,
            operation=request.operation,
            task_id=request.task_id,
            resource=request.resource,
            context=context,
            grant=grant,
        ):
            return ProductP3QueryResult(
                False, ProductP3TextReason.AUTHORITY_DENIED, None
            )
        assert isinstance(context, P3AuthorityContext)
        assert isinstance(grant, TaskAuthorizationGrant)

        try:
            now = self._clock()
            if not _valid_text(now):
                raise ValueError("invalid product P3 clock")
            invocation = self._policy.map(
                FormalTaskPolicyInput(
                    state=InputCommitState.COMMITTED,
                    source="structured",
                    operation=request.operation,
                    request_id=request.request_id,
                    issued_at=now,
                    scope=grant.scope,
                    correlation_id=context.authority.correlation_id,
                    authorization=grant,
                    task_id=request.task_id,
                    after_seq=request.after_seq,
                )
            )
            if not isinstance(invocation.envelope, QueryEnvelope):
                raise TypeError("query policy emitted a command")
            result = await asyncio.to_thread(
                self._query_owner.query,
                ProductP3AuthorizedQuery(
                    authority=context,
                    envelope=invocation.envelope,
                    authorization=invocation.authorization,
                ),
                now=now,
            )
            if not isinstance(result, ResultEnvelope):
                raise TypeError("query owner returned a non-result")
            result = ResultEnvelope.from_dict(
                result.to_dict(), owner=invocation.envelope
            )
        except (FormalTaskViolation, TypeError, ValueError):
            return ProductP3QueryResult(False, ProductP3TextReason.QUERY_FAILED, None)
        except Exception:
            return ProductP3QueryResult(False, ProductP3TextReason.QUERY_FAILED, None)
        return ProductP3QueryResult(
            result.ok,
            (
                ProductP3TextReason.QUERY_ACCEPTED
                if result.ok
                else ProductP3TextReason.QUERY_REJECTED
            ),
            result,
        )

    async def activate_progress(self, request: object) -> ProductP3ProgressActivation:
        """One-shot convenience path: resolve once, then activate prepared text."""

        if not self._enabled:
            return ProductP3ProgressActivation(
                False,
                TaskProgressReturnReason.FEATURE_DISABLED.value,
                None,
                None,
            )
        if not isinstance(request, ProductP3ProgressRequest):
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.INVALID_REQUEST.value, None, None
            )
        if (
            request.origin_kind is TaskProgressOriginKind.VOICE
            and self._prepared_source_factory is None
        ):
            return ProductP3ProgressActivation(
                False,
                TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE.value,
                None,
                None,
            )
        if not self._valid_progress_request(request):
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.INVALID_REQUEST.value, None, None
            )

        try:
            context = self._authority.resolve(
                request.route,
                operation="task.events",
                required_capabilities=frozenset({"task.events"}),
                target_task_id=request.task_id,
                resource=request.resource,
            )
        except ProductAuthorityUnavailable:
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.AUTHORITY_UNAVAILABLE.value, None, None
            )
        if context is None:
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.AUTHORITY_DENIED.value, None, None
            )
        grant = self._authority.to_task_grant(context, None)
        if grant is None:
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.AUTHORITY_DENIED.value, None, None
            )
        return await self.activate_prepared_text_progress(request, context, grant)

    async def activate_prepared_text_progress(
        self,
        request: object,
        context: object,
        grant: object,
    ) -> ProductP3ProgressActivation:
        """Activate exact text/UI projection without resolving authority again."""

        if not self._enabled:
            return ProductP3ProgressActivation(
                False,
                TaskProgressReturnReason.FEATURE_DISABLED.value,
                None,
                None,
            )
        if not isinstance(request, ProductP3ProgressRequest):
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.INVALID_REQUEST.value, None, None
            )
        if (
            request.origin_kind is TaskProgressOriginKind.VOICE
            and self._prepared_source_factory is None
        ):
            return ProductP3ProgressActivation(
                False,
                TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE.value,
                None,
                None,
            )
        if not self._valid_progress_request(request):
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.INVALID_REQUEST.value, None, None
            )
        if not self._prepared_authority_matches(
            request.route,
            operation="task.events",
            task_id=request.task_id,
            resource=request.resource,
            context=context,
            grant=grant,
        ):
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.AUTHORITY_DENIED.value, None, None
            )
        assert isinstance(context, P3AuthorityContext)
        assert isinstance(grant, TaskAuthorizationGrant)
        authority = context.authority
        if authority.project_id is None:
            return ProductP3ProgressActivation(
                False, ProductP3TextReason.AUTHORITY_DENIED.value, None, None
            )
        binding = TaskProgressOriginBinding(
            scope=grant.scope,
            task_id=request.task_id,
            session_id=authority.session_id,
            project_id=authority.project_id,
            correlation_id=authority.correlation_id,
            origin_kind=request.origin_kind,
            origin_id=request.origin_id,
            generation_kind=request.generation_kind,
            generation_id=request.generation_id,
            generation=request.generation,
            source_instance_id=request.source_instance_id,
            progress_producer=request.progress_producer,
            progress_adapter=request.progress_adapter,
        )

        if not self._cleanup_slot_available():
            return ProductP3ProgressActivation(
                False,
                ProductP3TextReason.PROGRESS_CLEANUP_CAPACITY.value,
                None,
                None,
            )

        subscription: TaskEventSubscription | None = None
        prepared_source: PreparedTaskProgressSource | None = None
        cleanup: ProductP3ProgressCleanupHandle | None = None
        try:
            if request.origin_kind is TaskProgressOriginKind.VOICE or (
                self._replay_text_from_prepared_source
                and self._prepared_source_factory is not None
            ):
                assert self._prepared_source_factory is not None
                prepared_source = self._prepared_source_factory(grant, binding)
                subscription = prepared_source.subscription
            else:
                subscription = self._subscription_factory(grant, binding)
            cleanup = self._retain_cleanup(binding, subscription)
            if not self._subscription_surface_valid(subscription):
                raise TypeError("invalid product P3 subscription")
            bridge = TaskProgressReturnBridge(
                enabled=True,
                subscription=subscription,
                prepared_source=prepared_source,
                authorization=grant,
                binding=binding,
                generation_is_current=self._generation_is_current,
                arbiter=self._arbiter,
                foreground=self._foreground,
                voice_sink=self._cleanup_guarded_voice_sink(cleanup),
                text_sink=self._cleanup_guarded_text_sink(cleanup),
            )
            activation_task = asyncio.create_task(
                bridge.activate(),
                name=f"live-voice-p3-text-activate:{binding.task_id}",
            )
            cleanup.attach_activation_task(activation_task)
            activation = await asyncio.shield(activation_task)
        except asyncio.CancelledError:
            if cleanup is not None:
                try:
                    cleanup.start()
                except Exception:
                    # Ownership remains discoverable for an explicit later retry.
                    pass
            raise
        except Exception:
            if cleanup is not None:
                cleanup.start()
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise asyncio.CancelledError
            return ProductP3ProgressActivation(
                False,
                ProductP3TextReason.PROGRESS_ACTIVATION_FAILED.value,
                binding if cleanup is not None else None,
                None,
                cleanup,
            )
        if not activation.active or activation.lease is None:
            assert cleanup is not None
            cleanup.start()
            return ProductP3ProgressActivation(
                False, activation.reason_id.value, binding, None, cleanup
            )
        assert cleanup is not None
        cleanup.commit_effects()
        self._cleanups.pop(cleanup.cleanup_id, None)
        return ProductP3ProgressActivation(
            True,
            ProductP3TextReason.PROGRESS_ACTIVATED.value,
            binding,
            activation.lease,
        )

    def _cleanup_guarded_text_sink(
        self, cleanup: ProductP3ProgressCleanupHandle
    ) -> TextEventSink:
        async def deliver(event: TaskProgressTextEvent) -> None:
            if not await cleanup.wait_effect_permission(event.origin):
                raise RuntimeError("product P3 text activation effects are fenced")
            await self._text_sink(event)

        return deliver

    def _cleanup_guarded_voice_sink(
        self, cleanup: ProductP3ProgressCleanupHandle
    ) -> VoiceIntentSink:
        async def deliver(intent: TaskProgressNotificationIntent) -> None:
            if not await cleanup.wait_effect_permission(intent.origin):
                raise RuntimeError("product P3 voice activation effects are fenced")
            await self._voice_sink(intent)

        return deliver

    @staticmethod
    def _valid_query_request(request: ProductP3QueryRequest) -> bool:
        if (
            not isinstance(request.route, AuthorityRouteContext)
            or not _valid_text(request.request_id)
            or not _valid_text(request.operation)
        ):
            return False
        targeted = request.operation != "task.list"
        if targeted != _valid_text(request.task_id):
            return False
        if request.resource is not None and not isinstance(
            request.resource, AuthorityResourceBinding
        ):
            return False
        if request.operation == "task.events":
            return type(request.after_seq) is int and request.after_seq >= -1
        return request.after_seq == -1

    @staticmethod
    def _valid_progress_request(request: ProductP3ProgressRequest) -> bool:
        return (
            request.origin_kind
            in {TaskProgressOriginKind.TEXT, TaskProgressOriginKind.VOICE}
            and isinstance(request.route, AuthorityRouteContext)
            and all(
                (
                    _valid_text(request.task_id),
                    _valid_text(request.origin_id),
                    _valid_text(request.generation_kind),
                    _valid_text(request.generation_id),
                    _valid_text(request.source_instance_id),
                    _valid_text(request.progress_adapter),
                    type(request.generation) is int and request.generation >= 0,
                    isinstance(request.progress_producer, ProducerRef),
                    request.resource is None
                    or isinstance(request.resource, AuthorityResourceBinding),
                )
            )
        )

    def _prepared_authority_matches(
        self,
        route: AuthorityRouteContext,
        *,
        operation: str,
        task_id: str | None,
        resource: AuthorityResourceBinding | None,
        context: object,
        grant: object,
    ) -> bool:
        if not isinstance(context, P3AuthorityContext) or not isinstance(
            grant, TaskAuthorizationGrant
        ):
            return False
        try:
            canonical_grant = self._authority.to_task_grant(context, None)
            if canonical_grant is None or canonical_grant != grant:
                return False
            authority = context.authority
            if (
                authority.operation != operation
                or authority.capabilities != frozenset({operation})
                or context.target_task_id != task_id
                or context.resource != authority.resource
                or (resource is not None and resource != authority.resource)
                or route.session_id != authority.session_id
                or route.correlation_id != authority.correlation_id
                or grant.scope != authority.scope
            ):
                return False
            if (
                route.claimed_user_id is not None
                and route.claimed_user_id != authority.principal_id
            ):
                return False
            if (
                route.claimed_project_id is not None
                and route.claimed_project_id != authority.project_id
            ):
                return False
            if (
                route.claimed_scope is not None
                and route.claimed_scope != authority.scope
            ):
                return False
            claimed_context = route.claimed_context_ref
            return claimed_context is None or (
                claimed_context.scope == authority.scope
                and not claimed_context.redaction.redacted
            )
        except Exception:
            return False

    @staticmethod
    def _subscription_surface_valid(subscription: object) -> bool:
        return all(
            callable(getattr(subscription, member, None))
            for member in ("snapshot", "start", "next_event", "close")
        )

    def _cleanup_slot_available(self) -> bool:
        if len(self._cleanups) < self._cleanup_capacity:
            return True
        for cleanup_id, handle in tuple(self._cleanups.items()):
            if handle.snapshot().state is ProductP3CleanupState.CLOSED:
                del self._cleanups[cleanup_id]
                if len(self._cleanups) < self._cleanup_capacity:
                    return True
        return False

    def _retain_cleanup(
        self, binding: TaskProgressOriginBinding, subscription: object
    ) -> ProductP3ProgressCleanupHandle:
        self._cleanup_sequence += 1
        fingerprint = hashlib.sha256(
            "\0".join(
                (
                    binding.session_id,
                    binding.task_id,
                    binding.generation_kind,
                    binding.generation_id,
                    str(binding.generation),
                    str(self._cleanup_sequence),
                )
            ).encode("utf-8")
        ).hexdigest()
        cleanup_id = f"p3-text-cleanup:{self._cleanup_sequence}:{fingerprint[:24]}"
        handle = ProductP3ProgressCleanupHandle(
            cleanup_id=cleanup_id,
            binding=binding,
            subscription=subscription,
        )
        self._cleanups[cleanup_id] = handle
        return handle


__all__ = [
    "ProductP3AuthorizedQuery",
    "ProductP3CleanupReason",
    "ProductP3CleanupSnapshot",
    "ProductP3CleanupState",
    "ProductP3ProgressActivation",
    "ProductP3ProgressCleanupHandle",
    "ProductP3ProgressRequest",
    "ProductP3QueryOwner",
    "ProductP3QueryRequest",
    "ProductP3QueryResult",
    "ProductP3SubscriptionFactory",
    "ProductP3TextAdapter",
    "ProductP3TextReason",
]
