# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContextRef,
    ErrorCode,
    ResponseRef,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.agent_conversation_runtime import (
    AgentConversationShutdownResult,
    AgentConversationShutdownStatus,
    AuthoritativePresentationHandle,
)
from jiuwenswarm.server.live_voice.interaction_engine import (
    InteractionAction,
    InteractionEnginePort,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityRouteContext,
    AuthorityRoutingClaim,
    P2AuthorityAdapter,
    ProductAuthorityService,
    TrustedAuthorityCandidate,
    TrustedAuthorityLookup,
)
from jiuwenswarm.server.live_voice.product_p2_interaction_adapter import (
    P2ActivationReason,
    P2ActivationResult,
    P2ActivationStatus,
    P2CancellationScope,
    P2FoundationEvidence,
    P2InteractionActivationRequest,
    P2InteractionBinding,
    P2LeaseCloseStatus,
    P2LeaseState,
    ProductP2AdapterViolation,
    ProductP2InteractionAdapter,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    PresentationSurface,
    PresentationUnit,
    TaskPresentationRuntimeReceipt,
)
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskProgressNotificationIntent,
    TaskProgressOriginKind,
)


NOW = datetime(2030, 1, 1, tzinfo=UTC)
SCOPE = ScopeRef(
    "principal-1",
    "project-1",
    "session-1",
    Assurance.AUTHENTICATED,
)


class RecordingResolver:
    def __init__(
        self,
        candidates: Sequence[TrustedAuthorityCandidate],
        *,
        failure: Exception | None = None,
        order: list[str] | None = None,
    ) -> None:
        self.candidates = candidates
        self.failure = failure
        self.calls: list[TrustedAuthorityLookup] = []
        self.order = order

    def resolve(
        self, lookup: TrustedAuthorityLookup
    ) -> Sequence[TrustedAuthorityCandidate]:
        self.calls.append(lookup)
        if self.order is not None:
            self.order.append("authority.bind")
        if self.failure is not None:
            raise self.failure
        return self.candidates


class FakeRuntime:
    def __init__(
        self,
        *,
        start_result: bool = True,
        start_failure: Exception | None = None,
        start_gate: asyncio.Event | None = None,
        open_failure: Exception | None = None,
        open_gate: asyncio.Event | None = None,
        close_failure: Exception | None = None,
        close_status: AgentConversationShutdownStatus = (
            AgentConversationShutdownStatus.CLOSED
        ),
        close_statuses: list[AgentConversationShutdownStatus] | None = None,
        close_gate: asyncio.Event | None = None,
        attach_failure: Exception | None = None,
        progress_result: bool = True,
        order: list[str] | None = None,
    ) -> None:
        self.start_result = start_result
        self.start_failure = start_failure
        self.start_gate = start_gate
        self.open_failure = open_failure
        self.open_gate = open_gate
        self.close_failure = close_failure
        self.close_status = close_status
        self.close_statuses = list(close_statuses or ())
        self.close_gate = close_gate
        self.attach_failure = attach_failure
        self.order = order
        self.progress_result = progress_result
        self.progress_intents: list[TaskProgressNotificationIntent] = []
        self.progress_responses: list[ResponseRef] = []
        self.task_notification_safe = True
        self.presentation_calls: list[dict[str, object]] = []
        self.presentation_reservations: dict[ResponseRef, tuple[str, bool]] = {}
        self.start_calls = 0
        self.open_calls: list[str] = []
        self.close_calls = 0
        self.closed = False

    async def accept_task_progress_notification(
        self, intent: TaskProgressNotificationIntent, *, response_ref: ResponseRef
    ) -> bool:
        self.progress_intents.append(intent)
        self.progress_responses.append(response_ref)
        return self.progress_result

    def task_notification_foreground_safe(self) -> bool:
        return self.task_notification_safe

    async def present_authoritative_text(self, **kwargs: object):
        before_publish = kwargs.pop("before_publish", None)
        self.presentation_calls.append(dict(kwargs))
        response_ref = ResponseRef("interaction-1", str(kwargs["response_id"]), 2)
        surface = kwargs.get("_presentation_surface", PresentationSurface.TEXT)
        assert isinstance(surface, PresentationSurface)
        unit = PresentationUnit(
            ref=response_ref,
            surface=surface,
            unit_id=f"unit-{kwargs['request_id']}",
            seq=0,
            source_start_utf8=0,
            source_end_utf8=4,
            content_ref="sha256:test",
        )
        handle = AuthoritativePresentationHandle(
            request_id=str(kwargs["request_id"]),
            round_id=f"authoritative:{kwargs['request_id']}",
            response_ref=response_ref,
            presentation_unit=unit,
        )
        if callable(before_publish):
            await before_publish(handle)
        return handle

    def task_presentation_runtime_authority(
        self, response_ref: ResponseRef, reservation_id: str | None, phase: str
    ) -> TaskPresentationRuntimeReceipt:
        retained = self.presentation_reservations.get(response_ref)
        if phase == "reserve":
            assert reservation_id is None
            if retained is None:
                retained = (f"reservation-{response_ref.response_id}", True)
                self.presentation_reservations[response_ref] = retained
        else:
            assert retained is not None and reservation_id == retained[0]
            if phase == "close":
                retained = (retained[0], False)
                self.presentation_reservations[response_ref] = retained
        assert retained is not None
        return TaskPresentationRuntimeReceipt(
            response_ref=response_ref,
            reservation_id=retained[0],
            phase=phase,
            active=retained[1],
        )

    def attach_notification_consumer(
        self, *, consumer_id: str, connection_epoch: int
    ) -> object | None:
        del consumer_id, connection_epoch
        if self.attach_failure is not None:
            raise self.attach_failure
        return None

    async def start(self) -> bool:
        self.start_calls += 1
        if self.order is not None:
            self.order.append("runtime.start")
        if self.start_gate is not None:
            await self.start_gate.wait()
        if self.start_failure is not None:
            raise self.start_failure
        return self.start_result

    async def open_interaction(self, interaction_id: str) -> None:
        self.open_calls.append(interaction_id)
        if self.order is not None:
            self.order.append("runtime.open")
        if self.open_gate is not None:
            await self.open_gate.wait()
        if self.open_failure is not None:
            raise self.open_failure

    async def close(self, *, timeout_seconds: float) -> AgentConversationShutdownResult:
        del timeout_seconds
        self.close_calls += 1
        if self.order is not None:
            self.order.append("runtime.close")
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.close_failure is not None:
            raise self.close_failure
        close_status = (
            self.close_statuses.pop(0) if self.close_statuses else self.close_status
        )
        self.closed = close_status is AgentConversationShutdownStatus.CLOSED
        return AgentConversationShutdownResult(
            close_status,
            "fake_close_result",
        )


def candidate(
    *,
    scope: ScopeRef = SCOPE,
    correlation_id: str = "correlation-1",
    capabilities: frozenset[str] = frozenset({"agent.chat"}),
) -> TrustedAuthorityCandidate:
    return TrustedAuthorityCandidate(
        principal_id=scope.subject_id,
        session_id=scope.session_id,
        project_id=scope.project_id,
        scope=scope,
        allowed_operations=frozenset({"agent.chat"}),
        allowed_capabilities=capabilities,
        expires_at="2030-01-02T00:00:00Z",
        assurance=Assurance.AUTHENTICATED,
        source="server.auth.session",
        correlation_id=correlation_id,
    )


def route(
    *,
    scope: ScopeRef = SCOPE,
    correlation_id: str = "correlation-1",
) -> AuthorityRouteContext:
    return AuthorityRouteContext(
        session_id=scope.session_id,
        correlation_id=correlation_id,
        claimed_user_id=scope.subject_id,
        claimed_project_id=scope.project_id,
        claimed_scope=scope,
    )


def context_ref(
    *,
    scope: ScopeRef = SCOPE,
    redacted: bool = False,
    expires_at: str | None = "2030-01-02T00:00:00Z",
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
                "policy_id": "policy-1",
                "redacted": redacted,
                "fields": [],
            },
            "extensions": {},
        }
    )


def request(
    *,
    route_context: AuthorityRouteContext | None = None,
    interaction_id: str = "interaction-1",
    activation_id: str = "activation-1",
    generation: int = 1,
) -> P2InteractionActivationRequest:
    return P2InteractionActivationRequest(
        route=route_context or route(),
        interaction_id=interaction_id,
        activation_id=activation_id,
        activation_generation=generation,
    )


def authority_adapter(
    resolver: RecordingResolver | None,
    *,
    enabled: bool = True,
) -> P2AuthorityAdapter:
    return P2AuthorityAdapter(
        ProductAuthorityService(
            enabled=enabled,
            resolver=resolver,
            clock=lambda: NOW,
        )
    )


def engine_factory(
    _context,
    _binding,
) -> InteractionEnginePort:
    return InteractionEnginePort(
        frozenset(
            {
                "interaction.respond",
                "barge_in",
                "playback.stop",
                "response.cancel",
                "round.cancel",
                "task.cancel",
            }
        )
    )


def adapter_for(
    resolver: RecordingResolver,
    runtime_factory,
    *,
    enabled: bool = True,
    interaction_engine_factory=engine_factory,
) -> ProductP2InteractionAdapter:
    return ProductP2InteractionAdapter(
        enabled=enabled,
        authority_adapter=authority_adapter(resolver),
        runtime_factory=runtime_factory,
        interaction_engine_factory=interaction_engine_factory,
        cleanup_timeout_seconds=0.02,
        close_poll_seconds=0.01,
    )


@pytest.mark.asyncio
async def test_authority_succeeds_before_any_factory_or_runtime_effect() -> None:
    order: list[str] = []
    resolver = RecordingResolver((candidate(),), order=order)
    runtime = FakeRuntime(order=order)
    seen = []

    def make_runtime(context, binding):
        order.append("runtime.factory")
        seen.append((context, binding))
        return runtime

    def make_engine(context, binding):
        order.append("engine.factory")
        seen.append((context, binding))
        return engine_factory(context, binding)

    result = await adapter_for(
        resolver,
        make_runtime,
        interaction_engine_factory=make_engine,
    ).activate(request())

    assert result.status is P2ActivationStatus.ACTIVE
    assert result.reason is P2ActivationReason.ACTIVATION_LEASE_OPEN
    assert result.lease is not None
    assert order == [
        "authority.bind",
        "runtime.factory",
        "engine.factory",
        "runtime.start",
        "runtime.open",
    ]
    assert runtime.open_calls == ["interaction-1"]
    assert seen[0][0] is seen[1][0]
    assert seen[0][1] is seen[1][1]
    binding = result.lease.binding
    assert binding.session_id == "session-1"
    assert binding.correlation_id == "correlation-1"
    assert binding.scope == SCOPE
    assert result.evidence.notification_backpressure_closed is True
    assert result.evidence.evidence_scope == "package_only"
    assert result.evidence.formal_route_ready is False
    assert result.evidence.real_runtime_path_observed is False


@pytest.mark.asyncio
async def test_voice_task_progress_requires_exact_open_p2_binding_and_cr_acceptance() -> (
    None
):
    resolver = RecordingResolver((candidate(),))
    runtime = FakeRuntime()
    result = await adapter_for(resolver, lambda _context, _binding: runtime).activate(
        request()
    )
    assert result.lease is not None
    binding = result.lease.binding
    intent = TaskProgressNotificationIntent(
        origin=SimpleNamespace(
            scope=binding.scope,
            session_id=binding.session_id,
            origin_id=binding.interaction_id,
            origin_kind=TaskProgressOriginKind.VOICE,
        ),
        task_event=None,
        source_event=None,
        progress_event=None,
        decision=None,
        evidence_id="progress-evidence-1",
    )
    response = ResponseRef(binding.interaction_id, "response-progress-1", 0)

    assert await result.lease.deliver_task_progress(binding, intent, response) is True
    assert runtime.progress_intents == [intent]
    assert runtime.progress_responses == [response]

    foreign = replace(
        intent,
        origin=SimpleNamespace(
            scope=binding.scope,
            session_id=binding.session_id,
            origin_id="interaction-foreign",
            origin_kind=TaskProgressOriginKind.VOICE,
        ),
    )
    with pytest.raises(ProductP2AdapterViolation) as rejected:
        await result.lease.deliver_task_progress(binding, foreign, response)
    assert rejected.value.reason == "TASK_PROGRESS_ORIGIN_MISMATCH"
    assert runtime.progress_intents == [intent]

    runtime.progress_result = False
    with pytest.raises(ProductP2AdapterViolation) as unavailable:
        await result.lease.deliver_task_progress(binding, intent, response)
    assert unavailable.value.reason == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    assert runtime.progress_intents == [intent, intent]


@pytest.mark.asyncio
async def test_task_notification_waits_for_safe_foreground_and_skips_user_history() -> (
    None
):
    resolver = RecordingResolver((candidate(),))
    runtime = FakeRuntime()
    result = await adapter_for(resolver, lambda _context, _binding: runtime).activate(
        request()
    )
    assert result.lease is not None
    binding = result.lease.binding
    notification_commit = TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": "commit-task-notification-1",
            "turn_id": "turn-task-notification-1",
            "interaction_id": binding.interaction_id,
            "text": "Task notification for task-1",
            "hypothesis_provenance": {
                "source": "task_event",
                "event_id": "event-terminal-1",
            },
            "scope": binding.scope.to_dict(),
            "context_refs": [],
            "committed_at": "2030-01-01T00:00:00Z",
        }
    )

    runtime.task_notification_safe = False
    with pytest.raises(ProductP2AdapterViolation) as busy:
        await result.lease.present_task_notification(
            binding,
            request_id="task-notification-event-terminal-1",
            response_id="response-task-notification-event-terminal-1",
            correlation_id=binding.correlation_id,
            commit=notification_commit,
            text="The background task is complete and its result is ready.",
        )
    assert busy.value.reason == "PRODUCT_TASK_NOTIFICATION_FOREGROUND_BUSY"
    assert runtime.presentation_calls == []

    runtime.task_notification_safe = True
    before_publish_refs: list[ResponseRef] = []

    async def before_publish(handle: AuthoritativePresentationHandle) -> None:
        before_publish_refs.append(handle.response_ref)

    handle = await result.lease.present_task_notification(
        binding,
        request_id="task-notification-event-terminal-1",
        response_id="response-task-notification-event-terminal-1",
        correlation_id=binding.correlation_id,
        commit=notification_commit,
        text="The background task is complete and its result is ready.",
        before_publish=before_publish,
    )
    assert handle.response_ref.response_generation == 2
    assert before_publish_refs == [handle.response_ref]
    assert runtime.presentation_calls == [
        {
            "request_id": "task-notification-event-terminal-1",
            "response_id": "response-task-notification-event-terminal-1",
            "correlation_id": binding.correlation_id,
            "commit": notification_commit,
            "text": "The background task is complete and its result is ready.",
            "channel_id": "web",
            "_persist_user_history": False,
            "_source_provenance": "server.task_notification",
            "_presentation_surface": PresentationSurface.TEXT,
            "_publish_notification": True,
        }
    ]

    audio_receipts: list[TaskPresentationRuntimeReceipt] = []

    async def reserve_audio(handle: AuthoritativePresentationHandle) -> None:
        audio_receipts.append(
            result.lease.task_presentation_runtime_authority(
                binding, handle.response_ref, None, "reserve"
            )
        )

    audio = await result.lease.present_task_notification(
        binding,
        request_id="task-notification-event-audio-1",
        response_id="response-task-notification-event-audio-1",
        correlation_id=binding.correlation_id,
        commit=replace(
            notification_commit,
            commit_id="commit-task-notification-audio-1",
            turn_id="turn-task-notification-audio-1",
        ),
        text="The background task is complete.",
        presentation_surface=PresentationSurface.AUDIO,
        before_publish=reserve_audio,
    )
    assert audio.presentation_unit.surface is PresentationSurface.AUDIO
    assert len(audio_receipts) == 1
    assert audio_receipts[0].response_ref == audio.response_ref
    assert audio_receipts[0].phase == "reserve"
    assert runtime.presentation_calls[-1]["_presentation_surface"] is (
        PresentationSurface.AUDIO
    )


@pytest.mark.asyncio
async def test_prepared_activation_uses_exactly_one_io_authority_resolution() -> None:
    order: list[str] = []
    resolver = RecordingResolver((candidate(),), order=order)
    p2_authority = authority_adapter(resolver)
    activation_request = request()
    context = p2_authority.bind(activation_request.route)
    assert context is not None
    runtime = FakeRuntime(order=order)

    def make_runtime(_context, _binding):
        order.append("runtime.factory")
        return runtime

    adapter = ProductP2InteractionAdapter(
        enabled=True,
        authority_adapter=p2_authority,
        runtime_factory=make_runtime,
        interaction_engine_factory=engine_factory,
    )
    prepared = adapter.prepare_activation(context, activation_request)
    result = await adapter.activate_prepared(prepared)

    assert result.status is P2ActivationStatus.ACTIVE
    assert len(resolver.calls) == 1
    assert order == [
        "authority.bind",
        "runtime.factory",
        "runtime.start",
        "runtime.open",
    ]


@pytest.mark.asyncio
async def test_prepared_activation_rejects_mismatch_before_factories() -> None:
    resolver = RecordingResolver((candidate(),))
    p2_authority = authority_adapter(resolver)
    context = p2_authority.bind(route())
    assert context is not None
    allocations = 0

    def forbidden_factory(_context, _binding):
        nonlocal allocations
        allocations += 1
        return FakeRuntime()

    adapter = ProductP2InteractionAdapter(
        enabled=True,
        authority_adapter=p2_authority,
        runtime_factory=forbidden_factory,
        interaction_engine_factory=engine_factory,
    )

    with pytest.raises(ProductP2AdapterViolation) as raised:
        adapter.prepare_activation(
            context,
            request(route_context=route(correlation_id="other-correlation")),
        )
    assert raised.value.reason == "AUTHORITY_BINDING_MISMATCH"
    assert len(resolver.calls) == 1
    assert allocations == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tampered_route",
    [
        replace(route(), claimed_user_id="other-principal"),
        replace(route(), claimed_project_id="other-project"),
        replace(
            route(),
            claimed_scope=ScopeRef(
                "other-principal",
                "project-1",
                "session-1",
                Assurance.AUTHENTICATED,
            ),
        ),
        replace(
            route(),
            claimed_context_ref=context_ref(
                scope=ScopeRef(
                    "other-principal",
                    "project-1",
                    "session-1",
                    Assurance.AUTHENTICATED,
                )
            ),
        ),
        replace(route(), claimed_context_ref=context_ref(redacted=True)),
        replace(
            route(),
            claimed_context_ref=context_ref(expires_at="2029-12-31T23:59:59Z"),
        ),
    ],
)
async def test_prepared_comparison_claim_tamper_allocates_nothing(
    tampered_route: AuthorityRouteContext,
) -> None:
    resolver = RecordingResolver((candidate(),))
    p2_authority = authority_adapter(resolver)
    context = p2_authority.bind(route())
    assert context is not None
    allocations = 0

    def forbidden_factory(_context, _binding):
        nonlocal allocations
        allocations += 1
        return FakeRuntime()

    adapter = ProductP2InteractionAdapter(
        enabled=True,
        authority_adapter=p2_authority,
        runtime_factory=forbidden_factory,
        interaction_engine_factory=engine_factory,
        clock=lambda: NOW,
    )

    with pytest.raises(ProductP2AdapterViolation) as raised:
        adapter.prepare_activation(context, request(route_context=tampered_route))
    assert raised.value.reason == "AUTHORITY_BINDING_MISMATCH"
    assert allocations == 0


@pytest.mark.asyncio
async def test_immutable_prepared_route_rejects_routing_claim_tamper() -> None:
    original_claim = AuthorityRoutingClaim(
        source="header",
        name="x-route-hint",
        value="original",
    )
    original_route = replace(route(), routing_claims=(original_claim,))
    resolver = RecordingResolver((candidate(),))
    p2_authority = authority_adapter(resolver)
    context = p2_authority.bind(original_route)
    assert context is not None
    allocations = 0

    def forbidden_factory(_context, _binding):
        nonlocal allocations
        allocations += 1
        return FakeRuntime()

    adapter = ProductP2InteractionAdapter(
        enabled=True,
        authority_adapter=p2_authority,
        runtime_factory=forbidden_factory,
        interaction_engine_factory=engine_factory,
        clock=lambda: NOW,
    )
    prepared = adapter.prepare_activation(
        context,
        request(route_context=original_route),
    )
    tampered_route = replace(
        original_route,
        routing_claims=(replace(original_claim, value="tampered"),),
    )
    object.__setattr__(
        prepared,
        "request",
        request(route_context=tampered_route),
    )

    with pytest.raises(ProductP2AdapterViolation) as raised:
        await adapter.activate_prepared(prepared)
    assert raised.value.reason == "PREPARED_ACTIVATION_TAMPERED"
    assert allocations == 0


@pytest.mark.asyncio
async def test_exact_context_and_routing_claims_survive_prepared_binding() -> None:
    exact_route = replace(
        route(),
        claimed_context_ref=context_ref(),
        routing_claims=(
            AuthorityRoutingClaim(
                source="client_metadata",
                name="route-hint",
                value="comparison-only",
            ),
        ),
    )
    resolver = RecordingResolver((candidate(),))
    p2_authority = authority_adapter(resolver)
    context = p2_authority.bind(exact_route)
    assert context is not None
    adapter = ProductP2InteractionAdapter(
        enabled=True,
        authority_adapter=p2_authority,
        runtime_factory=lambda _context, _binding: FakeRuntime(),
        interaction_engine_factory=engine_factory,
        clock=lambda: NOW,
    )
    prepared = adapter.prepare_activation(
        context,
        request(route_context=exact_route),
    )

    result = await adapter.activate_prepared(prepared)

    assert result.status is P2ActivationStatus.ACTIVE
    assert len(resolver.calls) == 1


@pytest.mark.asyncio
async def test_prepared_or_open_lease_expiry_has_zero_downstream_effect() -> None:
    resolver = RecordingResolver((candidate(),))
    p2_authority = authority_adapter(resolver)
    context = p2_authority.bind(route())
    assert context is not None
    current = [NOW]
    runtime = FakeRuntime()
    engine_allocations = 0

    def make_engine(context, binding):
        nonlocal engine_allocations
        engine_allocations += 1
        return engine_factory(context, binding)

    adapter = ProductP2InteractionAdapter(
        enabled=True,
        authority_adapter=p2_authority,
        runtime_factory=lambda _context, _binding: runtime,
        interaction_engine_factory=make_engine,
        clock=lambda: current[0],
    )
    prepared = adapter.prepare_activation(context, request())
    next_prepared = adapter.prepare_activation(
        context,
        request(interaction_id="interaction-2", activation_id="activation-2"),
    )
    active = await adapter.activate_prepared(prepared)
    assert active.lease is not None
    assert engine_allocations == 1

    current[0] = datetime(2030, 1, 3, tzinfo=UTC)
    with pytest.raises(ProductP2AdapterViolation) as raised:
        active.lease.propose_action(
            active.lease.binding,
            InteractionAction("expired", "interaction.respond", "interaction-1", SCOPE),
        )
    expired_activation = await adapter.activate_prepared(next_prepared)

    assert raised.value.reason == "ACTIVATION_AUTHORITY_EXPIRED"
    assert expired_activation.status is P2ActivationStatus.DENIED
    assert expired_activation.reason is P2ActivationReason.AUTHORITY_DENIED
    assert active.lease.snapshot().accepted_intents == 0
    assert engine_allocations == 1
    assert runtime.close_calls == 0


@pytest.mark.asyncio
async def test_prepared_activation_clock_failure_is_unavailable_before_factory() -> (
    None
):
    resolver = RecordingResolver((candidate(),))
    p2_authority = authority_adapter(resolver)
    context = p2_authority.bind(route())
    assert context is not None
    allocations = 0

    def forbidden_factory(_context, _binding):
        nonlocal allocations
        allocations += 1
        return FakeRuntime()

    def failing_clock():
        raise RuntimeError("clock-secret")

    adapter = ProductP2InteractionAdapter(
        enabled=True,
        authority_adapter=p2_authority,
        runtime_factory=forbidden_factory,
        interaction_engine_factory=engine_factory,
        clock=failing_clock,
    )
    prepared = adapter.prepare_activation(context, request())
    result = await adapter.activate_prepared(prepared)

    assert result.status is P2ActivationStatus.UNAVAILABLE
    assert result.reason is P2ActivationReason.AUTHORITY_UNAVAILABLE
    assert result.lease is None
    assert allocations == 0
    assert "secret" not in repr(result)


@pytest.mark.asyncio
async def test_feature_off_returns_before_request_authority_and_allocations() -> None:
    resolver = RecordingResolver((candidate(),))
    allocations = 0

    def forbidden_factory(_context, _binding):
        nonlocal allocations
        allocations += 1
        raise AssertionError("feature-off allocated downstream P2")

    adapter = adapter_for(resolver, forbidden_factory, enabled=False)
    result = await adapter.activate(object())

    assert result.status is P2ActivationStatus.DISABLED
    assert result.reason is P2ActivationReason.FEATURE_DISABLED
    assert result.lease is None
    assert resolver.calls == []
    assert allocations == 0

    prepared = await adapter.activate_prepared(object())
    assert prepared.status is P2ActivationStatus.DISABLED
    with pytest.raises(ProductP2AdapterViolation) as raised:
        adapter.prepare_activation(object(), object())
    assert raised.value.reason == "FEATURE_DISABLED"
    assert resolver.calls == []
    assert allocations == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resolver", "expected_status", "expected_reason"),
    [
        (
            RecordingResolver(()),
            P2ActivationStatus.DENIED,
            P2ActivationReason.AUTHORITY_DENIED,
        ),
        (
            RecordingResolver((candidate(),), failure=RuntimeError("secret")),
            P2ActivationStatus.UNAVAILABLE,
            P2ActivationReason.AUTHORITY_UNAVAILABLE,
        ),
    ],
)
async def test_absent_denied_or_unavailable_authority_allocates_nothing(
    resolver: RecordingResolver,
    expected_status: P2ActivationStatus,
    expected_reason: P2ActivationReason,
) -> None:
    allocations = 0

    def forbidden_factory(_context, _binding):
        nonlocal allocations
        allocations += 1
        raise AssertionError("unauthorized allocation")

    result = await adapter_for(resolver, forbidden_factory).activate(request())

    assert result.status is expected_status
    assert result.reason is expected_reason
    assert result.lease is None
    assert allocations == 0


@pytest.mark.asyncio
async def test_disabled_authority_is_unavailable_and_allocates_nothing() -> None:
    resolver = RecordingResolver((candidate(),))
    allocations = 0

    def forbidden_factory(_context, _binding):
        nonlocal allocations
        allocations += 1
        return FakeRuntime()

    adapter = ProductP2InteractionAdapter(
        enabled=True,
        authority_adapter=authority_adapter(resolver, enabled=False),
        runtime_factory=forbidden_factory,
        interaction_engine_factory=engine_factory,
    )
    result = await adapter.activate(request())

    assert result.status is P2ActivationStatus.UNAVAILABLE
    assert result.reason is P2ActivationReason.AUTHORITY_UNAVAILABLE
    assert resolver.calls == []
    assert allocations == 0


@pytest.mark.asyncio
async def test_cross_correlation_or_scope_authority_claim_allocates_nothing() -> None:
    resolver = RecordingResolver((candidate(),))
    allocations = 0

    def forbidden_factory(_context, _binding):
        nonlocal allocations
        allocations += 1
        return FakeRuntime()

    adapter = adapter_for(resolver, forbidden_factory)
    wrong_correlation = await adapter.activate(
        request(route_context=route(correlation_id="other-correlation"))
    )
    wrong_scope = ScopeRef(
        "principal-2", "project-1", "session-1", Assurance.AUTHENTICATED
    )
    wrong_authority_scope = await adapter.activate(
        request(route_context=route(scope=wrong_scope))
    )

    assert wrong_correlation.status is P2ActivationStatus.DENIED
    assert wrong_authority_scope.status is P2ActivationStatus.DENIED
    assert allocations == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_point", "expected_reason"),
    [
        ("engine", P2ActivationReason.INTERACTION_ENGINE_FACTORY_FAILED),
        ("start_false", P2ActivationReason.RUNTIME_START_FAILED),
        ("start_raise", P2ActivationReason.RUNTIME_START_FAILED),
        ("open", P2ActivationReason.INTERACTION_OPEN_FAILED),
    ],
)
async def test_partial_activation_failure_rolls_back_runtime(
    failure_point: str,
    expected_reason: P2ActivationReason,
) -> None:
    resolver = RecordingResolver((candidate(),))
    runtime = FakeRuntime(
        start_result=failure_point != "start_false",
        start_failure=(
            RuntimeError("start-secret") if failure_point == "start_raise" else None
        ),
        open_failure=(RuntimeError("open-secret") if failure_point == "open" else None),
    )

    def make_engine(context, binding):
        if failure_point == "engine":
            raise RuntimeError("engine-secret")
        return engine_factory(context, binding)

    result = await adapter_for(
        resolver,
        lambda _context, _binding: runtime,
        interaction_engine_factory=make_engine,
    ).activate(request())

    assert result.status is P2ActivationStatus.FAILED
    assert result.reason is expected_reason
    assert result.lease is None
    assert runtime.close_calls == 1
    assert runtime.closed is True


@pytest.mark.asyncio
async def test_notification_consumer_attach_failure_rolls_back_open_runtime() -> None:
    resolver = RecordingResolver((candidate(),))
    runtime = FakeRuntime(attach_failure=RuntimeError("attach-secret"))
    adapter = adapter_for(resolver, lambda _context, _binding: runtime)

    result = await adapter.activate(request())

    assert result.status is P2ActivationStatus.FAILED
    assert result.reason is P2ActivationReason.NOTIFICATION_CONSUMER_ATTACH_FAILED
    assert result.lease is None
    assert runtime.start_calls == 1
    assert runtime.open_calls == ["interaction-1"]
    assert runtime.close_calls == 1
    assert runtime.closed is True
    assert adapter.retained_failed_cleanups() == ()
    assert "secret" not in repr(result)


@pytest.mark.asyncio
async def test_runtime_factory_failure_is_safe_and_has_no_engine_allocation() -> None:
    resolver = RecordingResolver((candidate(),))
    engine_allocations = 0

    def fail_runtime(_context, _binding):
        raise RuntimeError("factory-secret")

    def count_engine(context, binding):
        nonlocal engine_allocations
        engine_allocations += 1
        return engine_factory(context, binding)

    result = await adapter_for(
        resolver,
        fail_runtime,
        interaction_engine_factory=count_engine,
    ).activate(request())

    assert result.status is P2ActivationStatus.FAILED
    assert result.reason is P2ActivationReason.RUNTIME_FACTORY_FAILED
    assert result.lease is None
    assert engine_allocations == 0
    assert "secret" not in repr(result)


@pytest.mark.asyncio
async def test_partial_failure_reports_rollback_failure_without_leaking_error() -> None:
    resolver = RecordingResolver((candidate(),))
    runtime = FakeRuntime(
        close_statuses=[
            AgentConversationShutdownStatus.FAILED,
            AgentConversationShutdownStatus.CLOSED,
        ]
    )

    def fail_engine(_context, _binding):
        raise RuntimeError("engine-secret")

    adapter = adapter_for(
        resolver,
        lambda _context, _binding: runtime,
        interaction_engine_factory=fail_engine,
    )
    result = await adapter.activate(request())

    assert result.status is P2ActivationStatus.FAILED
    assert result.reason is P2ActivationReason.ROLLBACK_FAILED
    assert result.lease is None
    assert result.cleanup is not None
    assert runtime.close_calls == 1
    assert "secret" not in repr(result)
    assert result.cleanup.snapshot().status is P2LeaseCloseStatus.FAILED
    blocked = await adapter.activate(request())
    assert blocked.cleanup is result.cleanup
    retried = await result.cleanup.cleanup(
        result.cleanup.binding,
        timeout_seconds=1.0,
        retry_failed=True,
    )
    assert retried.status is P2LeaseCloseStatus.CLOSED
    assert result.cleanup.snapshot().attempts == 2


@pytest.mark.asyncio
async def test_pending_rollback_returns_discoverable_cleanup_owner() -> None:
    resolver = RecordingResolver((candidate(),))
    close_gate = asyncio.Event()
    runtime = FakeRuntime(close_gate=close_gate)

    def fail_engine(_context, _binding):
        raise RuntimeError("engine-secret")

    adapter = adapter_for(
        resolver,
        lambda _context, _binding: runtime,
        interaction_engine_factory=fail_engine,
    )
    result = await adapter.activate(request())

    assert result.status is P2ActivationStatus.FAILED
    assert result.reason is P2ActivationReason.ROLLBACK_FAILED
    assert result.cleanup is not None
    assert adapter.retained_failed_cleanups() == (result.cleanup,)
    assert result.cleanup.snapshot().status is P2LeaseCloseStatus.PENDING
    close_gate.set()
    closed = await result.cleanup.cleanup(
        result.cleanup.binding,
        timeout_seconds=1.0,
    )
    assert closed.status is P2LeaseCloseStatus.CLOSED


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_point", ["start", "open"])
async def test_start_or_open_cancellation_propagates_with_retained_cleanup(
    cancel_point: str,
) -> None:
    resolver = RecordingResolver((candidate(),))
    start_gate = asyncio.Event() if cancel_point == "start" else None
    open_gate = asyncio.Event() if cancel_point == "open" else None
    close_gate = asyncio.Event()
    runtime = FakeRuntime(
        start_gate=start_gate,
        open_gate=open_gate,
        close_gate=close_gate,
    )
    adapter = adapter_for(resolver, lambda _context, _binding: runtime)
    activation = asyncio.create_task(adapter.activate(request()))
    for _ in range(100):
        reached = (
            runtime.start_calls == 1
            if cancel_point == "start"
            else runtime.open_calls == ["interaction-1"]
        )
        if reached:
            break
        await asyncio.sleep(0)
    assert reached

    activation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await activation

    cleanups = adapter.retained_failed_cleanups()
    assert len(cleanups) == 1
    cleanup = cleanups[0]
    assert cleanup.snapshot().status is P2LeaseCloseStatus.PENDING
    assert runtime.close_calls == 1
    close_gate.set()
    closed = await cleanup.cleanup(cleanup.binding, timeout_seconds=1.0)
    assert closed.status is P2LeaseCloseStatus.CLOSED


@pytest.mark.asyncio
async def test_cancellation_during_rollback_propagates_and_keeps_owner() -> None:
    resolver = RecordingResolver((candidate(),))
    close_gate = asyncio.Event()
    runtime = FakeRuntime(close_gate=close_gate)

    def fail_engine(_context, _binding):
        raise RuntimeError("engine-secret")

    adapter = adapter_for(
        resolver,
        lambda _context, _binding: runtime,
        interaction_engine_factory=fail_engine,
    )
    activation = asyncio.create_task(adapter.activate(request()))
    for _ in range(100):
        if runtime.close_calls == 1:
            break
        await asyncio.sleep(0)
    assert runtime.close_calls == 1

    activation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await activation

    cleanups = adapter.retained_failed_cleanups()
    assert len(cleanups) == 1
    cleanup = cleanups[0]
    assert cleanup.snapshot().status is P2LeaseCloseStatus.PENDING
    close_gate.set()
    closed = await cleanup.cleanup(cleanup.binding, timeout_seconds=1.0)
    assert closed.status is P2LeaseCloseStatus.CLOSED


@pytest.mark.asyncio
async def test_exact_replay_reuses_lease_and_generation_conflict_is_rejected() -> None:
    resolver = RecordingResolver((candidate(),))
    runtimes: list[FakeRuntime] = []

    def make_runtime(_context, _binding):
        runtime = FakeRuntime()
        runtimes.append(runtime)
        return runtime

    adapter = adapter_for(resolver, make_runtime)
    first = await adapter.activate(request())
    replay = await adapter.activate(request())
    conflict = await adapter.activate(
        request(activation_id="activation-2", generation=2)
    )

    assert first.status is P2ActivationStatus.ACTIVE
    assert replay.status is P2ActivationStatus.ACTIVE
    assert replay.replayed is True
    assert replay.lease is first.lease
    assert conflict.status is P2ActivationStatus.DENIED
    assert conflict.reason is P2ActivationReason.ACTIVATION_BINDING_CONFLICT
    assert len(runtimes) == 1


@pytest.mark.asyncio
async def test_closed_lease_allows_only_a_newer_authorized_generation() -> None:
    resolver = RecordingResolver((candidate(),))
    runtimes: list[FakeRuntime] = []

    def make_runtime(_context, _binding):
        runtime = FakeRuntime()
        runtimes.append(runtime)
        return runtime

    adapter = adapter_for(resolver, make_runtime)
    first = await adapter.activate(request())
    assert first.lease is not None
    closed = await first.lease.close(first.lease.binding, timeout_seconds=1.0)
    same_generation = await adapter.activate(request())
    next_generation = await adapter.activate(
        request(activation_id="activation-2", generation=2)
    )
    stale_after_replacement = await adapter.activate(request())

    assert closed.status is P2LeaseCloseStatus.CLOSED
    assert same_generation.status is P2ActivationStatus.DENIED
    assert same_generation.reason is P2ActivationReason.ACTIVATION_BINDING_CONFLICT
    assert next_generation.status is P2ActivationStatus.ACTIVE
    assert next_generation.lease is not None
    assert next_generation.lease is not first.lease
    assert stale_after_replacement.status is P2ActivationStatus.DENIED
    assert len(runtimes) == 2


@pytest.mark.asyncio
async def test_wrong_or_stale_lease_binding_has_zero_engine_and_close_effect() -> None:
    resolver = RecordingResolver((candidate(),))
    runtime = FakeRuntime()
    result = await adapter_for(resolver, lambda _context, _binding: runtime).activate(
        request()
    )
    assert result.lease is not None
    lease = result.lease
    wrong = replace(lease.binding, activation_generation=2)
    action = InteractionAction(
        "action-1", "interaction.respond", "interaction-1", SCOPE
    )

    with pytest.raises(ProductP2AdapterViolation) as raised:
        lease.propose_action(wrong, action)
    assert raised.value.reason == "ACTIVATION_BINDING_MISMATCH"
    with pytest.raises(ProductP2AdapterViolation) as raised:
        await lease.close(wrong, timeout_seconds=0.1)
    assert raised.value.reason == "ACTIVATION_BINDING_MISMATCH"
    assert lease.snapshot().accepted_intents == 0
    assert runtime.close_calls == 0


@pytest.mark.asyncio
async def test_cross_scope_or_interaction_action_has_zero_engine_effect() -> None:
    resolver = RecordingResolver((candidate(),))
    result = await adapter_for(
        resolver, lambda _context, _binding: FakeRuntime()
    ).activate(request())
    assert result.lease is not None
    lease = result.lease
    other_scope = ScopeRef(
        "principal-2", "project-1", "session-1", Assurance.AUTHENTICATED
    )

    for action in (
        InteractionAction(
            "wrong-scope", "interaction.respond", "interaction-1", other_scope
        ),
        InteractionAction(
            "wrong-interaction", "interaction.respond", "interaction-2", SCOPE
        ),
    ):
        with pytest.raises(ProductP2AdapterViolation) as raised:
            lease.propose_action(lease.binding, action)
        assert raised.value.reason == "INTERACTION_ACTION_BINDING_MISMATCH"
    assert lease.snapshot().accepted_intents == 0


@pytest.mark.asyncio
async def test_four_cancel_scopes_remain_distinct_intents_and_never_execute() -> None:
    resolver = RecordingResolver((candidate(),))
    runtime = FakeRuntime()
    result = await adapter_for(resolver, lambda _context, _binding: runtime).activate(
        request()
    )
    assert result.lease is not None
    lease = result.lease

    expected = (
        P2CancellationScope.PLAYBACK_STOP,
        P2CancellationScope.RESPONSE_CANCEL,
        P2CancellationScope.ROUND_CANCEL,
        P2CancellationScope.TASK_CANCEL,
    )
    observed = []
    for index, scope in enumerate(expected):
        intent = lease.propose_action(
            lease.binding,
            InteractionAction(f"cancel-{index}", scope.value, "interaction-1", SCOPE),
        )
        observed.append(intent.cancellation_scope)
        assert intent.effect_owner == "none_intent_only"
        assert intent.accepted is True
    barge_in = lease.propose_action(
        lease.binding,
        InteractionAction("barge-in", "barge_in", "interaction-1", SCOPE),
    )

    assert tuple(observed) == expected
    assert barge_in.cancellation_scope is None
    assert runtime.close_calls == 0
    assert runtime.open_calls == ["interaction-1"]


@pytest.mark.asyncio
async def test_close_is_retained_shielded_and_bounded_for_concurrent_waiters() -> None:
    resolver = RecordingResolver((candidate(),))
    gate = asyncio.Event()
    runtime = FakeRuntime(close_gate=gate)
    result = await adapter_for(resolver, lambda _context, _binding: runtime).activate(
        request()
    )
    assert result.lease is not None
    lease = result.lease

    timed = await lease.close(lease.binding, timeout_seconds=0.001)
    assert timed.status is P2LeaseCloseStatus.PENDING
    assert lease.snapshot().state is P2LeaseState.CLOSING
    waiter = asyncio.create_task(lease.close(lease.binding, timeout_seconds=1.0))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert runtime.close_calls == 1

    gate.set()
    final = await lease.close(lease.binding, timeout_seconds=1.0)
    replay = await lease.close(lease.binding, timeout_seconds=1.0)

    assert final.status is P2LeaseCloseStatus.CLOSED
    assert replay == final
    assert runtime.close_calls == 1
    assert lease.snapshot().state is P2LeaseState.CLOSED
    with pytest.raises(ProductP2AdapterViolation) as raised:
        lease.propose_action(
            lease.binding,
            InteractionAction("late", "interaction.respond", "interaction-1", SCOPE),
        )
    assert raised.value.reason == "ACTIVATION_LEASE_NOT_OPEN"


@pytest.mark.asyncio
async def test_runtime_close_failure_is_retained_as_failed_truth() -> None:
    resolver = RecordingResolver((candidate(),))
    runtime = FakeRuntime(close_status=AgentConversationShutdownStatus.FAILED)
    result = await adapter_for(resolver, lambda _context, _binding: runtime).activate(
        request()
    )
    assert result.lease is not None

    closed = await result.lease.close(
        result.lease.binding,
        timeout_seconds=1.0,
    )
    replay = await result.lease.close(
        result.lease.binding,
        timeout_seconds=1.0,
    )

    assert closed.status is P2LeaseCloseStatus.FAILED
    assert replay == closed
    assert runtime.close_calls == 1
    assert result.lease.snapshot().state is P2LeaseState.FAILED


@pytest.mark.asyncio
async def test_concurrent_exact_activation_allocates_once() -> None:
    resolver = RecordingResolver((candidate(),))
    allocations = 0

    def make_runtime(_context, _binding):
        nonlocal allocations
        allocations += 1
        return FakeRuntime()

    adapter = adapter_for(resolver, make_runtime)
    first, second = await asyncio.gather(
        adapter.activate(request()),
        adapter.activate(request()),
    )

    assert first.status is P2ActivationStatus.ACTIVE
    assert second.status is P2ActivationStatus.ACTIVE
    assert first.lease is second.lease
    assert {first.replayed, second.replayed} == {False, True}
    assert allocations == 1


def test_request_and_binding_validation_is_stable_and_scoped() -> None:
    with pytest.raises(ProductP2AdapterViolation) as raised:
        P2InteractionActivationRequest(route(), "interaction", "activation", 0)
    assert raised.value.reason == "INVALID_ACTIVATION_BINDING"
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT

    evidence = P2FoundationEvidence()
    assert evidence.evidence_scope == "package_only"
    assert evidence.notification_backpressure_closed is True
    assert evidence.formal_route_ready is False
    assert evidence.real_runtime_path_observed is False
    with pytest.raises(TypeError):
        P2FoundationEvidence(formal_route_ready=True)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        replace(evidence, formal_route_ready=True)

    with pytest.raises(ProductP2AdapterViolation) as raised:
        P2InteractionBinding(
            session_id="other-session",
            correlation_id="correlation",
            interaction_id="interaction",
            activation_id="activation",
            activation_generation=1,
            scope=SCOPE,
        )
    assert raised.value.reason == "INVALID_ACTIVATION_BINDING"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: P2ActivationResult(
            P2ActivationStatus.DISABLED,
            P2ActivationReason.AUTHORITY_DENIED,
            evidence=object(),  # type: ignore[arg-type]
        ),
        lambda: P2ActivationResult(
            P2ActivationStatus.DISABLED,
            P2ActivationReason.FEATURE_DISABLED,
            evidence=object(),  # type: ignore[arg-type]
        ),
        lambda: P2ActivationResult(
            P2ActivationStatus.DISABLED,
            P2ActivationReason.FEATURE_DISABLED,
            evidence=P2FoundationEvidence(),
        ),
        lambda: P2ActivationResult(
            P2ActivationStatus.DISABLED,
            P2ActivationReason.FEATURE_DISABLED,
            replayed=True,
        ),
        lambda: P2ActivationResult(
            P2ActivationStatus.DISABLED,
            P2ActivationReason.FEATURE_DISABLED,
            replayed=1,  # type: ignore[arg-type]
        ),
        lambda: P2ActivationResult(
            P2ActivationStatus.FAILED,
            P2ActivationReason.ROLLBACK_FAILED,
        ),
    ],
)
def test_activation_result_rejects_contradictory_public_construction(factory) -> None:
    with pytest.raises(ProductP2AdapterViolation) as raised:
        factory()
    assert raised.value.reason == "INVALID_ACTIVATION_RESULT"
