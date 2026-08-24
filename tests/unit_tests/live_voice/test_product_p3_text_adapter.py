# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import threading
from collections import deque
from collections.abc import Sequence
from copy import copy
from dataclasses import dataclass
from datetime import datetime
from typing import cast

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ProducerRef,
    QueryEnvelope,
    ResultEnvelope,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    PersistentTaskEvent,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityResourceBinding,
    AuthorityRouteContext,
    P3AuthorityAdapter,
    ProductAuthorityService,
    TrustedAuthorityCandidate,
    TrustedAuthorityLookup,
)
from jiuwenswarm.server.live_voice.product_p3_text_adapter import (
    ProductP3AuthorizedQuery,
    ProductP3CleanupReason,
    ProductP3CleanupState,
    ProductP3ProgressActivation,
    ProductP3ProgressCleanupHandle,
    ProductP3ProgressRequest,
    ProductP3QueryRequest,
    ProductP3TextAdapter,
    ProductP3TextReason,
)
from jiuwenswarm.server.live_voice.progress_notification_arbiter import (
    ForegroundFact,
    ForegroundSnapshot,
    ProgressNotificationArbiter,
    SpeechPolicy,
)
from jiuwenswarm.server.live_voice.task_event_subscription import (
    TaskEventSubscription,
)
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
    TaskProgressReturnActivation,
    TaskProgressReturnBridge,
    TaskProgressReturnLease,
    TaskProgressReturnReason,
    TaskProgressReturnState,
    TaskProgressSourceDecision,
    TaskProgressTextEvent,
)

NOW = "2030-01-01T00:00:00Z"
EXPIRY = "2035-01-01T00:00:00Z"
SCOPE = ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def _resource(task_id: str) -> AuthorityResourceBinding:
    return AuthorityResourceBinding(
        "task", task_id, hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    )


def _route(
    *,
    session_id: str = "session-1",
    correlation_id: str = "correlation-1",
    claimed_scope: ScopeRef | None = SCOPE,
) -> AuthorityRouteContext:
    return AuthorityRouteContext(
        session_id=session_id,
        correlation_id=correlation_id,
        claimed_user_id="principal-1",
        claimed_project_id="project-1",
        claimed_scope=claimed_scope,
    )


def _candidate(
    operation: str,
    *,
    task_id: str | None,
    correlation_id: str = "correlation-1",
) -> TrustedAuthorityCandidate:
    return TrustedAuthorityCandidate(
        principal_id="principal-1",
        session_id="session-1",
        project_id="project-1",
        scope=SCOPE,
        allowed_operations=frozenset({operation}),
        allowed_capabilities=frozenset({operation}),
        expires_at=EXPIRY,
        assurance=Assurance.AUTHENTICATED,
        source="server.auth.session",
        correlation_id=correlation_id,
        resource=None if task_id is None else _resource(task_id),
    )


class _Resolver:
    def __init__(self, candidates: Sequence[TrustedAuthorityCandidate]) -> None:
        self.candidates = candidates
        self.calls: list[TrustedAuthorityLookup] = []

    def resolve(
        self, lookup: TrustedAuthorityLookup
    ) -> Sequence[TrustedAuthorityCandidate]:
        self.calls.append(lookup)
        return self.candidates


class _QueryOwner:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[ProductP3AuthorizedQuery, str | None]] = []
        self.thread_ids: list[int] = []

    def query(self, query: ProductP3AuthorizedQuery, *, now=None) -> ResultEnvelope:
        assert isinstance(query.envelope, QueryEnvelope)
        self.calls.append((query, now))
        self.thread_ids.append(threading.get_ident())
        if self.fail:
            raise RuntimeError("query backend secret")
        return ResultEnvelope.success(
            owner=query.envelope,
            result={"query_type": query.envelope.query_type},
            observed_at=now,
        )


class _AsyncQueryOwner:
    def __init__(
        self,
        *,
        fail: bool = False,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.fail = fail
        self.gate = gate
        self.started = asyncio.Event()
        self.calls: list[tuple[ProductP3AuthorizedQuery, str | None]] = []
        self.tasks: list[asyncio.Task[object] | None] = []

    async def query(
        self,
        query: ProductP3AuthorizedQuery,
        *,
        now=None,
    ) -> ResultEnvelope:
        self.calls.append((query, now))
        self.tasks.append(asyncio.current_task())
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("async query backend secret")
        return ResultEnvelope.success(
            owner=query.envelope,
            result={"query_type": query.envelope.query_type, "mode": "async"},
            observed_at=now,
        )


@dataclass(frozen=True, slots=True)
class _SubscriptionSnapshot:
    task_id: str


class _Subscription:
    def __init__(
        self,
        events: list[PersistentTaskEvent] | None = None,
        *,
        task_id: str = "task-1",
        start_result: bool = True,
        start_error: Exception | None = None,
        start_gate: asyncio.Event | None = None,
        close_gate: asyncio.Event | None = None,
        close_errors: list[Exception] | None = None,
    ) -> None:
        self.events = deque(events or [])
        self.task_id = task_id
        self.start_result = start_result
        self.start_error = start_error
        self.start_gate = start_gate
        self.close_gate = close_gate
        self.close_errors = deque(close_errors or [])
        self.start_calls = 0
        self.close_calls = 0
        self.start_entered = asyncio.Event()
        self._closed = asyncio.Event()

    def snapshot(self) -> _SubscriptionSnapshot:
        return _SubscriptionSnapshot(self.task_id)

    async def start(self) -> bool:
        self.start_calls += 1
        self.start_entered.set()
        if self.start_gate is not None:
            await self.start_gate.wait()
        if self.start_error is not None:
            raise self.start_error
        return self.start_result

    async def next_event(self) -> PersistentTaskEvent:
        if self.events:
            return self.events.popleft()
        await self._closed.wait()
        raise StopAsyncIteration

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.close_errors:
            raise self.close_errors.popleft()
        self._closed.set()


class _SubscriptionFactory:
    def __init__(self, subscription: _Subscription | None = None) -> None:
        self.subscription = subscription or _Subscription()
        self.calls: list[tuple[object, object]] = []

    def __call__(self, authorization, binding) -> TaskEventSubscription:
        self.calls.append((authorization, binding))
        return cast(TaskEventSubscription, self.subscription)


def _event(
    seq: int,
    event_type: str,
    state: str,
    *,
    event_id: str | None = None,
    task_id: str = "task-1",
    correlation_id: str = "correlation-1",
    scope: ScopeRef = SCOPE,
    outcome: str | None = None,
) -> PersistentTaskEvent:
    return PersistentTaskEvent(
        event_id=event_id or f"event-{seq}",
        task_id=task_id,
        attempt_id="attempt-1",
        scope=scope,
        seq=seq,
        event_type=event_type,
        state=state,
        outcome=outcome,
        producer="task_core",
        source_event_id=None,
        causation_id=f"cause-{seq}",
        correlation_id=correlation_id,
        occurred_at=NOW,
        details={},
    )


def _progress_request(
    *,
    route: AuthorityRouteContext | None = None,
    task_id: str = "task-1",
    origin_kind: TaskProgressOriginKind = TaskProgressOriginKind.TEXT,
    generation: int = 7,
    resource: AuthorityResourceBinding | None = None,
) -> ProductP3ProgressRequest:
    return ProductP3ProgressRequest(
        route=route or _route(),
        task_id=task_id,
        origin_kind=origin_kind,
        origin_id="surface-1",
        generation_kind="web_session_generation",
        generation_id="web-session-1",
        generation=generation,
        source_instance_id="task-core-1",
        progress_producer=ProducerRef(
            component="product_p3_text",
            instance_id="product-p3-text-1",
            authority="adapter",
        ),
        progress_adapter="product_p3_text.v1",
        resource=resource,
    )


def _progress_binding() -> TaskProgressOriginBinding:
    request = _progress_request()
    return TaskProgressOriginBinding(
        scope=SCOPE,
        task_id=request.task_id,
        session_id="session-1",
        project_id="project-1",
        correlation_id="correlation-1",
        origin_kind=TaskProgressOriginKind.TEXT,
        origin_id=request.origin_id,
        generation_kind=request.generation_kind,
        generation_id=request.generation_id,
        generation=request.generation,
        source_instance_id=request.source_instance_id,
        progress_producer=request.progress_producer,
        progress_adapter=request.progress_adapter,
    )


def _foreground() -> ForegroundSnapshot:
    return ForegroundSnapshot(
        interaction=ForegroundFact.SAFE,
        response=ForegroundFact.SAFE,
        presentation=ForegroundFact.SAFE,
        speech_policy=SpeechPolicy.ALLOW_CANDIDATE,
    )


def _adapter(
    resolver: _Resolver | None,
    *,
    authority: P3AuthorityAdapter | None = None,
    enabled: bool = True,
    owner: _QueryOwner | None = None,
    async_owner: _AsyncQueryOwner | None = None,
    factory: _SubscriptionFactory | None = None,
    current_generation: int = 7,
    generation_is_current=None,
    cleanup_capacity: int = 64,
    text_events: list[TaskProgressTextEvent] | None = None,
    voice_effects: list[object] | None = None,
) -> tuple[
    ProductP3TextAdapter,
    _QueryOwner | _AsyncQueryOwner,
    _SubscriptionFactory,
]:
    query_owner = None if async_owner is not None else (owner or _QueryOwner())
    subscription_factory = factory or _SubscriptionFactory()
    collected_text = text_events if text_events is not None else []
    collected_voice = voice_effects if voice_effects is not None else []

    async def text_sink(event: TaskProgressTextEvent) -> None:
        collected_text.append(event)

    async def voice_sink(event) -> None:
        collected_voice.append(event)

    authority_adapter = authority or _authority_adapter(resolver)
    return (
        ProductP3TextAdapter(
            enabled=enabled,
            authority=authority_adapter,
            query_owner=query_owner,
            async_query_owner=async_owner,
            subscription_factory=subscription_factory,
            generation_is_current=(
                generation_is_current
                if generation_is_current is not None
                else lambda binding: binding.generation == current_generation
            ),
            arbiter=ProgressNotificationArbiter(),
            foreground=_foreground,
            text_sink=text_sink,
            voice_sink=voice_sink,
            cleanup_capacity=cleanup_capacity,
            clock=lambda: NOW,
        ),
        async_owner if async_owner is not None else query_owner,
        subscription_factory,
    )


def _authority_adapter(resolver: _Resolver | None) -> P3AuthorityAdapter:
    return P3AuthorityAdapter(
        ProductAuthorityService(
            enabled=True,
            resolver=resolver,
            clock=lambda: datetime.fromisoformat(NOW.replace("Z", "+00:00")),
        )
    )


async def _wait_settled(lease) -> None:
    for _ in range(100):
        if not lease.snapshot().worker_pending:
            return
        await asyncio.sleep(0.001)
    raise AssertionError("progress worker did not settle")


async def _wait_cleanup_state(cleanup, state: ProductP3CleanupState) -> None:
    for _ in range(100):
        if cleanup.snapshot().state is state:
            return
        await asyncio.sleep(0.001)
    raise AssertionError(f"cleanup did not reach {state.value}")


@pytest.mark.asyncio
async def test_query_resolves_exact_authority_before_read_only_core() -> None:
    resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    adapter, owner, factory = _adapter(resolver)
    caller_thread = threading.get_ident()

    result = await adapter.query(
        ProductP3QueryRequest(_route(), "task.get", "request-1", "task-1")
    )

    assert result.ok is True
    assert result.reason_id is ProductP3TextReason.QUERY_ACCEPTED
    assert result.result is not None
    assert result.result.result == {"query_type": "task.get"}
    assert len(resolver.calls) == 1
    assert len(owner.calls) == 1
    assert isinstance(owner, _QueryOwner)
    query, observed_at = owner.calls[0]
    assert query.envelope.scope == SCOPE
    assert query.envelope.correlation_id == "correlation-1"
    assert query.envelope.target_ref.id == "task-1"
    assert query.authorization.scope == SCOPE
    assert query.authority.authority.scope == SCOPE
    assert query.authority.resource == _resource("task-1")
    assert observed_at == NOW
    assert len(owner.thread_ids) == 1
    assert owner.thread_ids[0] != caller_thread
    assert factory.calls == []


@pytest.mark.asyncio
async def test_prepared_query_uses_exact_grant_without_second_resolution() -> None:
    resolver = _Resolver([_candidate("task.events", task_id="task-1")])
    authority = _authority_adapter(resolver)
    adapter, owner, factory = _adapter(resolver, authority=authority)
    request = ProductP3QueryRequest(
        _route(), "task.events", "request-events", "task-1", after_seq=5
    )
    context = authority.resolve(
        request.route,
        operation=request.operation,
        required_capabilities=frozenset({request.operation}),
        target_task_id=request.task_id,
        resource=request.resource,
    )
    assert context is not None
    grant = authority.to_task_grant(context, None)
    assert grant is not None
    assert len(resolver.calls) == 1

    result = await adapter.activate_prepared_query(request, context, grant)

    assert result.reason_id is ProductP3TextReason.QUERY_ACCEPTED
    assert len(resolver.calls) == 1
    assert len(owner.calls) == 1
    prepared, _ = owner.calls[0]
    assert prepared.envelope.payload == {"after_seq": 5, "limit": 100}
    assert prepared.authority is context
    assert prepared.authorization is grant
    assert factory.calls == []


@pytest.mark.asyncio
async def test_prepared_query_awaits_exact_async_owner_on_caller_task() -> None:
    resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    async_owner = _AsyncQueryOwner()
    adapter, owner, factory = _adapter(resolver, async_owner=async_owner)
    caller = asyncio.current_task()

    result = await adapter.query(
        ProductP3QueryRequest(_route(), "task.get", "request-async", "task-1")
    )

    assert owner is async_owner
    assert result.reason_id is ProductP3TextReason.QUERY_ACCEPTED
    assert result.result is not None
    assert result.result.result == {"query_type": "task.get", "mode": "async"}
    assert async_owner.tasks == [caller]
    assert len(async_owner.calls) == 1
    assert factory.calls == []


@pytest.mark.asyncio
async def test_async_query_failure_is_stable_and_has_no_progress_effect() -> None:
    resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    async_owner = _AsyncQueryOwner(fail=True)
    adapter, _, factory = _adapter(resolver, async_owner=async_owner)

    result = await adapter.query(
        ProductP3QueryRequest(
            _route(),
            "task.get",
            "request-async-failed",
            "task-1",
        )
    )

    assert result.ok is False
    assert result.reason_id is ProductP3TextReason.QUERY_FAILED
    assert result.result is None
    assert len(async_owner.calls) == 1
    assert factory.calls == []


@pytest.mark.asyncio
async def test_async_query_caller_cancellation_propagates() -> None:
    resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    gate = asyncio.Event()
    async_owner = _AsyncQueryOwner(gate=gate)
    adapter, _, factory = _adapter(resolver, async_owner=async_owner)
    pending = asyncio.create_task(
        adapter.query(
            ProductP3QueryRequest(
                _route(),
                "task.get",
                "request-async-cancel",
                "task-1",
            )
        )
    )
    await async_owner.started.wait()

    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    assert len(async_owner.calls) == 1
    assert factory.calls == []


def test_query_owner_modes_are_exactly_one() -> None:
    resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    authority = _authority_adapter(resolver)
    subscription = _SubscriptionFactory()

    with pytest.raises(ValueError, match="exactly one query owner"):
        ProductP3TextAdapter(
            enabled=True,
            authority=authority,
            query_owner=None,
            async_query_owner=None,
            subscription_factory=subscription,
            generation_is_current=lambda _binding: True,
            arbiter=ProgressNotificationArbiter(),
            foreground=_foreground,
            text_sink=lambda _event: None,
            voice_sink=lambda _event: None,
        )

    import jiuwenswarm.server.live_voice.product_p3_text_adapter as module

    assert "AsyncProductP3QueryOwner" in module.__all__
    with pytest.raises(ValueError, match="exactly one query owner"):
        ProductP3TextAdapter(
            enabled=True,
            authority=authority,
            query_owner=_QueryOwner(),
            async_query_owner=_AsyncQueryOwner(),
            subscription_factory=subscription,
            generation_is_current=lambda _binding: True,
            arbiter=ProgressNotificationArbiter(),
            foreground=_foreground,
            text_sink=lambda _event: None,
            voice_sink=lambda _event: None,
        )


@pytest.mark.asyncio
async def test_prepared_text_progress_uses_exact_grant_without_second_resolution() -> (
    None
):
    resolver = _Resolver([_candidate("task.events", task_id="task-1")])
    authority = _authority_adapter(resolver)
    subscription = _Subscription()
    factory = _SubscriptionFactory(subscription)
    adapter, owner, _ = _adapter(resolver, authority=authority, factory=factory)
    request = _progress_request()
    context = authority.resolve(
        request.route,
        operation="task.events",
        required_capabilities=frozenset({"task.events"}),
        target_task_id=request.task_id,
        resource=request.resource,
    )
    assert context is not None
    grant = authority.to_task_grant(context, None)
    assert grant is not None
    assert len(resolver.calls) == 1

    activation = await adapter.activate_prepared_text_progress(request, context, grant)

    assert activation.active is True
    assert len(resolver.calls) == 1
    assert len(factory.calls) == 1
    assert owner.calls == []
    assert activation.lease is not None
    await activation.lease.close()
    assert subscription.close_calls == 1


@pytest.mark.asyncio
async def test_prepared_authority_cannot_be_rebound_to_another_request() -> None:
    resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    authority = _authority_adapter(resolver)
    adapter, owner, factory = _adapter(resolver, authority=authority)
    original = ProductP3QueryRequest(_route(), "task.get", "request-1", "task-1")
    context = authority.resolve(
        original.route,
        operation="task.get",
        required_capabilities=frozenset({"task.get"}),
        target_task_id="task-1",
    )
    assert context is not None
    grant = authority.to_task_grant(context, None)
    assert grant is not None

    rebound = await adapter.activate_prepared_query(
        ProductP3QueryRequest(
            _route(correlation_id="correlation-other"),
            "task.get",
            "request-other",
            "task-1",
        ),
        context,
        grant,
    )

    assert rebound.reason_id is ProductP3TextReason.AUTHORITY_DENIED
    assert len(resolver.calls) == 1
    assert owner.calls == []
    assert factory.calls == []


@pytest.mark.asyncio
async def test_corrupt_prepared_context_fails_closed_without_downstream() -> None:
    resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    authority = _authority_adapter(resolver)
    adapter, owner, factory = _adapter(resolver, authority=authority)
    request = ProductP3QueryRequest(_route(), "task.get", "request-1", "task-1")
    context = authority.resolve(
        request.route,
        operation="task.get",
        required_capabilities=frozenset({"task.get"}),
        target_task_id="task-1",
    )
    assert context is not None
    grant = authority.to_task_grant(context, None)
    assert grant is not None
    corrupt = copy(context)
    object.__setattr__(corrupt, "authority", None)

    result = await adapter.activate_prepared_query(request, corrupt, grant)

    assert result.reason_id is ProductP3TextReason.AUTHORITY_DENIED
    assert owner.calls == []
    assert factory.calls == []


@pytest.mark.asyncio
async def test_query_denied_unavailable_and_backend_failure_have_zero_false_success() -> (
    None
):
    denied = _Resolver([])
    denied_adapter, denied_owner, _ = _adapter(denied)
    unavailable_adapter, unavailable_owner, _ = _adapter(None)
    failed_owner = _QueryOwner(fail=True)
    failed_resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    failed_adapter, _, _ = _adapter(failed_resolver, owner=failed_owner)
    request = ProductP3QueryRequest(_route(), "task.get", "request-1", "task-1")

    denied_result = await denied_adapter.query(request)
    unavailable_result = await unavailable_adapter.query(request)
    failed_result = await failed_adapter.query(request)

    assert denied_result.reason_id is ProductP3TextReason.AUTHORITY_DENIED
    assert unavailable_result.reason_id is ProductP3TextReason.AUTHORITY_UNAVAILABLE
    assert failed_result.reason_id is ProductP3TextReason.QUERY_FAILED
    assert denied_owner.calls == []
    assert unavailable_owner.calls == []
    assert len(failed_owner.calls) == 1


@pytest.mark.asyncio
async def test_mutation_and_feature_off_touch_no_authority_query_or_subscription() -> (
    None
):
    resolver = _Resolver([_candidate("task.get", task_id="task-1")])
    adapter, owner, factory = _adapter(resolver, enabled=False)

    off_query = await adapter.query(object())
    off_progress = await adapter.activate_progress(object())

    assert off_query.reason_id is ProductP3TextReason.FEATURE_DISABLED
    assert off_progress.reason_id == TaskProgressReturnReason.FEATURE_DISABLED.value
    assert resolver.calls == []
    assert owner.calls == []
    assert factory.calls == []

    enabled_adapter, enabled_owner, enabled_factory = _adapter(resolver)
    mutation = await enabled_adapter.query(
        ProductP3QueryRequest(_route(), "task.cancel", "request-2", "task-1")
    )
    assert mutation.reason_id is ProductP3TextReason.MUTATION_CONFIRMATION_UNAVAILABLE
    assert resolver.calls == []
    assert enabled_owner.calls == []
    assert enabled_factory.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "progress_request",
    [
        _progress_request(task_id="task-other"),
        _progress_request(resource=_resource("task-other")),
        _progress_request(
            route=_route(
                claimed_scope=ScopeRef(
                    "principal-1",
                    "project-other",
                    "session-1",
                    Assurance.AUTHENTICATED,
                )
            )
        ),
        _progress_request(route=_route(correlation_id="correlation-other")),
        _progress_request(route=_route(session_id="session-other")),
    ],
)
async def test_progress_wrong_task_resource_scope_correlation_or_session_fails_closed(
    progress_request: ProductP3ProgressRequest,
) -> None:
    resolver = _Resolver([_candidate("task.events", task_id="task-1")])
    adapter, owner, factory = _adapter(resolver)

    activation = await adapter.activate_progress(progress_request)

    assert activation.active is False
    assert activation.reason_id == ProductP3TextReason.AUTHORITY_DENIED.value
    assert owner.calls == []
    assert factory.calls == []


@pytest.mark.asyncio
async def test_text_progress_projects_exact_events_and_duplicate_once() -> None:
    accepted = _event(5, "task.accepted", "accepted")
    terminal = _event(6, "task.terminal", "terminal", outcome="completed")
    subscription = _Subscription([accepted, accepted, terminal])
    factory = _SubscriptionFactory(subscription)
    text_events: list[TaskProgressTextEvent] = []
    voice_effects: list[object] = []
    resolver = _Resolver([_candidate("task.events", task_id="task-1")])
    adapter, _, _ = _adapter(
        resolver,
        factory=factory,
        text_events=text_events,
        voice_effects=voice_effects,
    )

    activation = await adapter.activate_progress(_progress_request())

    assert activation.active is True
    assert activation.lease is not None
    await _wait_settled(activation.lease)
    snapshot = activation.lease.snapshot()
    assert snapshot.state is TaskProgressReturnState.CLOSED
    assert snapshot.reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert snapshot.source_events == 3
    assert snapshot.projected_events == 2
    assert snapshot.duplicate_events == 1
    assert [item.task_event.event_id for item in text_events] == [
        accepted.event_id,
        terminal.event_id,
    ]
    assert all(item.origin.scope == SCOPE for item in text_events)
    assert all(item.origin.correlation_id == "correlation-1" for item in text_events)
    assert voice_effects == []
    assert subscription.close_calls == 1


@pytest.mark.asyncio
async def test_source_gap_fails_closed_without_text_or_voice_for_gapped_event() -> None:
    subscription = _Subscription(
        [
            _event(5, "task.accepted", "accepted"),
            _event(7, "task.terminal", "terminal", outcome="completed"),
        ]
    )
    text_events: list[TaskProgressTextEvent] = []
    voice_effects: list[object] = []
    adapter, _, _ = _adapter(
        _Resolver([_candidate("task.events", task_id="task-1")]),
        factory=_SubscriptionFactory(subscription),
        text_events=text_events,
        voice_effects=voice_effects,
    )

    activation = await adapter.activate_progress(_progress_request())
    assert activation.lease is not None
    await _wait_settled(activation.lease)
    snapshot = activation.lease.snapshot()

    assert snapshot.state is TaskProgressReturnState.FAILED
    assert snapshot.reason_id is TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION
    assert snapshot.last_source_decision_id is TaskProgressSourceDecision.SEQUENCE_GAP
    assert [item.task_event.seq for item in text_events] == [5]
    assert voice_effects == []


@pytest.mark.asyncio
async def test_voice_is_hard_unavailable_with_zero_authority_source_or_sink_effect() -> (
    None
):
    resolver = _Resolver([_candidate("task.events", task_id="task-1")])
    voice_effects: list[object] = []
    text_events: list[TaskProgressTextEvent] = []
    adapter, owner, factory = _adapter(
        resolver, text_events=text_events, voice_effects=voice_effects
    )

    activation = await adapter.activate_progress(
        _progress_request(origin_kind=TaskProgressOriginKind.VOICE)
    )

    assert activation.active is False
    assert (
        activation.reason_id
        == TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE.value
    )
    assert resolver.calls == []
    assert owner.calls == []
    assert factory.calls == []
    assert text_events == []
    assert voice_effects == []


@pytest.mark.asyncio
async def test_stale_generation_and_start_failure_rollback_exact_subscription() -> None:
    resolver = _Resolver([_candidate("task.events", task_id="task-1")])
    stale_subscription = _Subscription()
    stale_factory = _SubscriptionFactory(stale_subscription)
    stale_adapter, _, _ = _adapter(
        resolver, factory=stale_factory, current_generation=8
    )

    stale = await stale_adapter.activate_progress(_progress_request(generation=7))

    assert stale.active is False
    assert stale.reason_id == TaskProgressReturnReason.STALE_GENERATION.value
    assert stale.cleanup is not None
    stale_cleanup = await stale.cleanup.close()
    assert stale_cleanup.state is ProductP3CleanupState.CLOSED
    with pytest.raises(ValueError):
        ProductP3ProgressActivation(
            False,
            TaskProgressReturnReason.FEATURE_DISABLED.value,
            stale.binding,
            None,
            stale.cleanup,
        )
    with pytest.raises(ValueError):
        ProductP3ProgressActivation(
            False,
            TaskProgressReturnReason.STALE_GENERATION.value,
            None,
            None,
            stale.cleanup,
        )
    assert stale_subscription.start_calls == 0
    assert stale_subscription.close_calls == 1

    failed_subscription = _Subscription(start_error=RuntimeError("source secret"))
    failed_factory = _SubscriptionFactory(failed_subscription)
    failed_adapter, _, _ = _adapter(resolver, factory=failed_factory)
    failed = await failed_adapter.activate_progress(_progress_request())

    assert failed.active is False
    assert failed.reason_id == TaskProgressReturnReason.SOURCE_FAILED.value
    assert failed.cleanup is not None
    assert (await failed.cleanup.close()).state is ProductP3CleanupState.CLOSED
    assert failed_subscription.start_calls == 1
    assert failed_subscription.close_calls >= 1


@pytest.mark.asyncio
async def test_active_progress_lease_close_is_retained_and_detach_only() -> None:
    subscription = _Subscription()
    adapter, owner, _ = _adapter(
        _Resolver([_candidate("task.events", task_id="task-1")]),
        factory=_SubscriptionFactory(subscription),
    )

    activation = await adapter.activate_progress(_progress_request())
    assert activation.active is True
    assert activation.lease is not None
    with pytest.raises(ValueError):
        ProductP3ProgressActivation(
            True,
            ProductP3TextReason.PROGRESS_ACTIVATION_FAILED.value,
            activation.binding,
            activation.lease,
        )

    await asyncio.gather(activation.lease.close(), activation.lease.close())

    assert activation.lease.snapshot().state is TaskProgressReturnState.CLOSED
    assert (
        activation.lease.snapshot().reason_id
        is TaskProgressReturnReason.CONSUMER_DETACHED
    )
    assert subscription.close_calls == 1
    assert owner.calls == []


@pytest.mark.asyncio
async def test_cleanup_failure_retains_exact_owner_and_allows_retry() -> None:
    subscription = _Subscription(
        start_error=RuntimeError("start secret"),
        close_errors=[RuntimeError("bridge close"), RuntimeError("retry close")],
    )
    text_events: list[TaskProgressTextEvent] = []
    voice_effects: list[object] = []
    adapter, _, _ = _adapter(
        _Resolver([_candidate("task.events", task_id="task-1")]),
        factory=_SubscriptionFactory(subscription),
        text_events=text_events,
        voice_effects=voice_effects,
    )

    activation = await adapter.activate_progress(_progress_request())

    assert activation.active is False
    assert activation.reason_id == ProductP3TextReason.PROGRESS_ACTIVATION_FAILED.value
    assert activation.cleanup is not None
    assert activation.binding == activation.cleanup.binding
    assert adapter.retained_cleanup(activation.cleanup.cleanup_id) is activation.cleanup
    await _wait_cleanup_state(activation.cleanup, ProductP3CleanupState.FAILED)
    first = activation.cleanup.snapshot()
    assert first.state is ProductP3CleanupState.FAILED
    assert first.reason_id is ProductP3CleanupReason.DETACH_FAILED
    assert first.attempts == 1
    assert adapter.forget_cleanup(first.cleanup_id) is False

    retried = await activation.cleanup.close()
    assert retried.state is ProductP3CleanupState.CLOSED
    assert retried.reason_id is ProductP3CleanupReason.DETACHED
    assert retried.attempts == 2
    assert retried.binding == activation.binding
    assert text_events == []
    assert voice_effects == []
    assert adapter.forget_cleanup(retried.cleanup_id) is True
    assert adapter.retained_cleanups() == ()


@pytest.mark.asyncio
async def test_stale_after_start_close_failure_retains_cleanup_without_sink_effect() -> (
    None
):
    checks = iter((True, False))
    subscription = _Subscription(close_errors=[RuntimeError("bridge close")])
    text_events: list[TaskProgressTextEvent] = []
    voice_effects: list[object] = []
    adapter, _, _ = _adapter(
        _Resolver([_candidate("task.events", task_id="task-1")]),
        factory=_SubscriptionFactory(subscription),
        generation_is_current=lambda _binding: next(checks, False),
        text_events=text_events,
        voice_effects=voice_effects,
    )

    activation = await adapter.activate_progress(_progress_request())

    assert activation.active is False
    assert activation.cleanup is not None
    assert activation.binding == activation.cleanup.binding
    assert subscription.start_calls == 1
    assert text_events == []
    assert voice_effects == []
    assert (await activation.cleanup.close()).state is ProductP3CleanupState.CLOSED


@pytest.mark.asyncio
async def test_cancellation_during_start_preserves_cancellation_and_cleanup_owner() -> (
    None
):
    start_gate = asyncio.Event()
    close_gate = asyncio.Event()
    subscription = _Subscription(start_gate=start_gate, close_gate=close_gate)
    text_events: list[TaskProgressTextEvent] = []
    voice_effects: list[object] = []
    adapter, _, _ = _adapter(
        _Resolver([_candidate("task.events", task_id="task-1")]),
        factory=_SubscriptionFactory(subscription),
        text_events=text_events,
        voice_effects=voice_effects,
    )
    activation_task = asyncio.create_task(
        adapter.activate_progress(_progress_request())
    )
    await subscription.start_entered.wait()
    assert adapter.retained_cleanups() == ()

    activation_task.cancel("caller-cancel")
    await asyncio.sleep(0)
    retained = adapter.retained_cleanups()
    assert len(retained) == 1
    assert retained[0].binding.task_id == "task-1"
    close_gate.set()
    start_gate.set()

    with pytest.raises(asyncio.CancelledError) as cancellation:
        await activation_task
    assert cancellation.value.args == ("caller-cancel",)
    assert text_events == []
    assert voice_effects == []
    assert (await retained[0].close()).state is ProductP3CleanupState.CLOSED


@pytest.mark.asyncio
async def test_cancelled_activation_first_close_failure_still_closes_late_lease() -> (
    None
):
    start_gate = asyncio.Event()
    subscription = _Subscription(
        [_event(5, "task.progress", "running")],
        start_gate=start_gate,
        close_errors=[RuntimeError("first close secret")],
    )
    text_events: list[TaskProgressTextEvent] = []
    voice_effects: list[object] = []
    adapter, _, _ = _adapter(
        _Resolver([_candidate("task.events", task_id="task-1")]),
        factory=_SubscriptionFactory(subscription),
        text_events=text_events,
        voice_effects=voice_effects,
    )
    activation_task = asyncio.create_task(
        adapter.activate_progress(_progress_request())
    )
    await subscription.start_entered.wait()

    activation_task.cancel("caller-cancel")
    with pytest.raises(asyncio.CancelledError) as cancellation:
        await activation_task
    assert cancellation.value.args == ("caller-cancel",)
    retained = adapter.retained_cleanups()
    assert len(retained) == 1
    for _ in range(100):
        if subscription.close_calls == 1:
            break
        await asyncio.sleep(0.001)
    assert subscription.close_calls == 1
    assert retained[0].snapshot().state is ProductP3CleanupState.DETACHING
    assert retained[0].snapshot().effects_fenced is True
    assert retained[0].snapshot().effects_committed is False

    start_gate.set()
    settled = await retained[0].close()

    assert settled.state is ProductP3CleanupState.CLOSED
    assert settled.activation_active is True
    assert settled.active_lease_closed is True
    assert settled.effects_committed is False
    assert subscription.close_calls >= 2
    assert text_events == []
    assert voice_effects == []


@pytest.mark.asyncio
async def test_late_active_lease_close_failure_remains_retained_until_retry() -> None:
    class _RetryableLeaseOwner:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1
            if self.close_calls == 1:
                raise RuntimeError("lease close secret")

    binding = _progress_binding()
    subscription = _Subscription()
    lease_owner = _RetryableLeaseOwner()
    lease = TaskProgressReturnLease(cast(TaskProgressReturnBridge, lease_owner))
    activation_gate = asyncio.Event()

    async def late_activation() -> TaskProgressReturnActivation:
        await activation_gate.wait()
        return TaskProgressReturnActivation(
            active=True,
            reason_id=TaskProgressReturnReason.ACTIVATED,
            evidence_id="late-active-evidence",
            handoff_kind=None,
            handoff_evidence_id=None,
            lease=lease,
        )

    activation_task = asyncio.create_task(late_activation())
    cleanup = ProductP3ProgressCleanupHandle(
        cleanup_id="cleanup-late-active",
        binding=binding,
        subscription=subscription,
    )
    cleanup.attach_activation_task(activation_task)
    cleanup.start()
    activation_gate.set()
    await _wait_cleanup_state(cleanup, ProductP3CleanupState.FAILED)

    failed = cleanup.snapshot()
    assert failed.state is ProductP3CleanupState.FAILED
    assert failed.activation_active is True
    assert failed.active_lease_closed is False
    assert failed.effects_fenced is True
    assert subscription.close_calls == 1
    assert lease_owner.close_calls == 1

    retried = await cleanup.close()
    assert retried.state is ProductP3CleanupState.CLOSED
    assert retried.active_lease_closed is True
    assert retried.attempts == 2
    assert subscription.close_calls == 2
    assert lease_owner.close_calls == 2


@pytest.mark.asyncio
async def test_cleanup_fence_wakes_waiting_effect_before_bounded_detach() -> None:
    binding = _progress_binding()
    subscription = _Subscription()
    cleanup = ProductP3ProgressCleanupHandle(
        cleanup_id="cleanup-waiting-effect",
        binding=binding,
        subscription=subscription,
    )
    downstream_effects: list[str] = []

    async def guarded_delivery() -> None:
        if await cleanup.wait_effect_permission(binding):
            downstream_effects.append("forbidden")

    waiter = asyncio.create_task(guarded_delivery())
    for _ in range(100):
        if cleanup.snapshot().effect_waiters == 1:
            break
        await asyncio.sleep(0.001)
    assert cleanup.snapshot().effect_waiters == 1

    cleanup.start()
    await asyncio.wait_for(waiter, timeout=0.1)
    settled = await asyncio.wait_for(cleanup.close(), timeout=0.1)

    assert settled.state is ProductP3CleanupState.CLOSED
    assert settled.effects_fenced is True
    assert settled.effect_waiters == 0
    assert downstream_effects == []
    assert subscription.close_calls == 1


@pytest.mark.asyncio
async def test_cancelled_and_timed_out_cleanup_waiters_do_not_cancel_detach() -> None:
    close_gate = asyncio.Event()
    subscription = _Subscription(close_gate=close_gate)
    adapter, _, _ = _adapter(
        _Resolver([_candidate("task.events", task_id="task-1")]),
        factory=_SubscriptionFactory(subscription),
        current_generation=8,
    )
    activation = await adapter.activate_progress(_progress_request(generation=7))
    assert activation.cleanup is not None
    cleanup = activation.cleanup

    timed = await cleanup.close(timeout=0.001)
    assert timed.state is ProductP3CleanupState.DETACHING
    assert timed.task_pending is True
    assert timed.wait_timeouts == 1
    waiter = asyncio.create_task(cleanup.close())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert cleanup.snapshot().task_pending is True
    assert cleanup.snapshot().cancelled_waiters == 1

    close_gate.set()
    settled = await cleanup.close()
    assert settled.state is ProductP3CleanupState.CLOSED
    assert settled.attempts == 1


@pytest.mark.asyncio
async def test_cleanup_capacity_rejects_before_second_subscription_allocation() -> None:
    close_gate = asyncio.Event()
    subscription = _Subscription(close_gate=close_gate)
    factory = _SubscriptionFactory(subscription)
    adapter, _, _ = _adapter(
        _Resolver([_candidate("task.events", task_id="task-1")]),
        factory=factory,
        current_generation=8,
        cleanup_capacity=1,
    )

    first = await adapter.activate_progress(_progress_request(generation=7))
    assert first.cleanup is not None
    assert first.cleanup.snapshot().task_pending is True
    second = await adapter.activate_progress(_progress_request(generation=7))

    assert second.active is False
    assert second.reason_id == ProductP3TextReason.PROGRESS_CLEANUP_CAPACITY.value
    assert second.binding is None
    assert second.cleanup is None
    assert len(factory.calls) == 1
    close_gate.set()
    assert (await first.cleanup.close()).state is ProductP3CleanupState.CLOSED


def test_progress_activation_rejects_contradictory_public_states() -> None:
    binding = _progress_request()
    assert binding.task_id == "task-1"
    with pytest.raises(ValueError):
        ProductP3ProgressActivation(
            True,
            ProductP3TextReason.PROGRESS_ACTIVATED.value,
            None,
            None,
        )
    with pytest.raises(ValueError):
        ProductP3ProgressActivation(
            False,
            ProductP3TextReason.PROGRESS_ACTIVATION_FAILED.value,
            cast(object, binding),
            None,
        )
    with pytest.raises(ValueError):
        ProductP3ProgressActivation(
            False,
            ProductP3TextReason.PROGRESS_ACTIVATED.value,
            None,
            None,
        )
    for forged_reason in (
        "FORMAL_ROUTE_OBSERVED",
        "PRODUCT_P3_UNKNOWN_REASON",
        ProductP3TextReason.QUERY_ACCEPTED.value,
        TaskProgressReturnReason.ACTIVATED.value,
    ):
        with pytest.raises(ValueError):
            ProductP3ProgressActivation(False, forged_reason, None, None)
    with pytest.raises(ValueError):
        ProductP3ProgressActivation(
            False,
            TaskProgressReturnReason.STALE_GENERATION.value,
            None,
            None,
        )
