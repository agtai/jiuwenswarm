# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping, cast

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContractViolation,
    ErrorCode,
    MAX_SAFE_INTEGER,
    OriginRef,
    ResultEnvelope,
    ScopeRef,
    TurnCommitLedger,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskViolation,
    PersistentTaskEvent,
    ResolvedTaskContext,
)
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    P3AuthenticatedComposition,
    P3RouteResult,
    PreparedP3MutationConfirmation,
)
from jiuwenswarm.server.live_voice.p3_confirmation import (
    BoundedP3ConfirmationOwner,
    P3ConfirmationBinding,
    P3ConfirmationOwnerContext,
)
from jiuwenswarm.server.live_voice.p3_product_confirmation import (
    ProductP3ConfirmationForwarder,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityResourceBinding,
    TrustedAuthorityCandidate,
)
from jiuwenswarm.server.live_voice.product_composition_registry import (
    AgentServerProductCompositionRegistry,
    PRODUCT_COMPOSITION_ENABLE_ENV,
    PRODUCT_P2_ENABLE_ENV,
    PRODUCT_P2_RETRIABLE_FAULT_OPERATION_ENV,
    PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID_ENV,
    PRODUCT_P3_TEXT_ENABLE_ENV,
    ProductCompositionSettings,
    ProductP2RetriableFaultPlan,
    _ProgressDelivery,
    create_product_composition_registry_from_environment,
)
from jiuwenswarm.server.live_voice.product_p3_text_adapter import (
    ProductP3AuthorizedQuery,
)
from jiuwenswarm.server.live_voice.task_event_subscription import (
    TaskEventSubscription,
)
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskProgressOriginBinding,
)


NOW = "2030-01-01T00:00:00Z"
EXPIRY = "2035-01-01T00:00:00Z"
SCOPE = ScopeRef(
    "principal-product",
    "project-product",
    "session-product",
    Assurance.AUTHENTICATED,
)


def _resource(task_id: str) -> AuthorityResourceBinding:
    return AuthorityResourceBinding(
        "task",
        task_id,
        hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
    )


class _Facade:
    def __init__(self) -> None:
        self.calls = 0

    def supports_formal_live_voice(self) -> bool:
        return True

    async def process_formal_live_voice_stream(self, execution):
        self.calls += 1
        yield AgentResponseChunk(
            request_id=execution.request_id,
            channel_id=execution.channel_id,
            payload={"event_type": "chat.final", "content": "formal result"},
            is_complete=True,
        )


class _BlockingFacade(_Facade):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def process_formal_live_voice_stream(self, execution):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        yield AgentResponseChunk(
            request_id=execution.request_id,
            channel_id=execution.channel_id,
            payload={"event_type": "chat.final", "content": "formal result"},
            is_complete=True,
        )


class _HistoryWriter:
    def __init__(self) -> None:
        self.users: list[object] = []
        self.assistants: list[object] = []

    async def persist_user(self, commit, *, channel_id: str) -> bool:
        self.users.append((commit, channel_id))
        return True

    async def persist_assistant(
        self, intent, *, session_id: str, channel_id: str
    ) -> tuple[bool, ...]:
        self.assistants.append((intent, session_id, channel_id))
        return tuple(True for _ in intent.contents)


class _AgentManager:
    def __init__(self) -> None:
        self.agent = _Facade()
        self.get_calls: list[tuple[object, ...]] = []
        self.pins = 0
        self.unpins = 0

    async def get_agent(self, *args):
        self.get_calls.append(args)
        return self.agent

    def pin_agent(self, agent) -> None:
        assert agent is self.agent
        self.pins += 1

    def unpin_agent(self, agent) -> None:
        assert agent is self.agent
        self.unpins += 1


@dataclass(frozen=True, slots=True)
class _SubscriptionSnapshot:
    task_id: str


class _Subscription:
    def __init__(
        self,
        binding: TaskProgressOriginBinding,
        *,
        event: PersistentTaskEvent | None,
        close_failures: int = 0,
    ) -> None:
        self.binding = binding
        self.events = deque(() if event is None else (event,))
        self.close_failures = close_failures
        self.start_calls = 0
        self.close_calls = 0
        self._closed = asyncio.Event()

    def snapshot(self) -> _SubscriptionSnapshot:
        return _SubscriptionSnapshot(self.binding.task_id)

    async def start(self) -> bool:
        self.start_calls += 1
        return True

    async def next_event(self) -> PersistentTaskEvent:
        if self.events:
            return self.events.popleft()
        await self._closed.wait()
        raise StopAsyncIteration

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("injected close failure")
        self._closed.set()


class _P3Composition(P3AuthenticatedComposition):
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.authority_calls: list[dict[str, object]] = []
        self.query_calls: list[ProductP3AuthorizedQuery] = []
        self.subscription_calls: list[TaskProgressOriginBinding] = []
        self.fail_authority: FormalTaskViolation | None = None
        self.correlation_override: str | None = None
        self.subscription_event = True
        self.subscription_event_type = "task.running"
        self.subscription_close_failures = 0

    def resolve_product_authority_candidate(self, **kwargs):
        self.authority_calls.append(dict(kwargs))
        if self.fail_authority is not None:
            raise self.fail_authority
        if kwargs["bearer_token"] != "trusted-token":
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        operation = str(kwargs["operation"])
        task_id = cast(str | None, kwargs.get("task_id"))
        capabilities = cast(frozenset[str], kwargs["required_capabilities"])
        correlation_id = self.correlation_override or str(kwargs["correlation_id"])
        context = ResolvedTaskContext(
            source="test.server.project",
            stable_id=SCOPE.project_id or "",
            uri=self.project_dir.as_uri(),
            revision_kind="version",
            revision_value="revision-1",
            scope=SCOPE,
            permissions=("project.write", "task.execute"),
            expires_at=EXPIRY,
            redaction_policy_id="test-policy",
            redacted=False,
            redacted_fields=(),
        )
        return (
            TrustedAuthorityCandidate(
                principal_id=SCOPE.subject_id,
                session_id=SCOPE.session_id or "",
                project_id=SCOPE.project_id,
                scope=SCOPE,
                allowed_operations=frozenset({operation}),
                allowed_capabilities=capabilities,
                expires_at=EXPIRY,
                assurance=Assurance.AUTHENTICATED,
                source="test.server.product",
                correlation_id=correlation_id,
                resource=None if task_id is None else _resource(task_id),
            ),
            context,
        )

    def query(
        self,
        query: ProductP3AuthorizedQuery,
        *,
        now: str | None = None,
    ) -> ResultEnvelope:
        self.query_calls.append(query)
        return ResultEnvelope.success(
            owner=query.envelope,
            result={"query_type": query.envelope.query_type},
            observed_at=now or NOW,
        )

    def create_product_subscription(
        self,
        _authorization,
        binding: TaskProgressOriginBinding,
    ) -> TaskEventSubscription:
        self.subscription_calls.append(binding)
        event = (
            PersistentTaskEvent(
                event_id="event-running-1",
                task_id=binding.task_id,
                attempt_id="attempt-1",
                scope=binding.scope,
                seq=7,
                event_type=self.subscription_event_type,
                state=(
                    "terminal"
                    if self.subscription_event_type == "task.terminal"
                    else "running"
                ),
                outcome=(
                    "completed"
                    if self.subscription_event_type == "task.terminal"
                    else None
                ),
                producer="task_core",
                source_event_id=None,
                causation_id="cause-running-1",
                correlation_id=binding.correlation_id,
                occurred_at=NOW,
                details={},
            )
            if self.subscription_event
            else None
        )
        return cast(
            TaskEventSubscription,
            _Subscription(
                binding,
                event=event,
                close_failures=self.subscription_close_failures,
            ),
        )


class _MutationP3Composition(_P3Composition):
    def __init__(
        self,
        project_dir: Path,
        verifier: ProductP3ConfirmationForwarder,
    ) -> None:
        super().__init__(project_dir)
        self.verifier = verifier
        self.prepare_calls: list[tuple[str, dict[str, object]]] = []
        self.mutation_calls: list[tuple[str, dict[str, object]]] = []
        self.replay_authority_revoked = False

    async def prepare_mutation_confirmation(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        session_id: str | None,
    ) -> PreparedP3MutationConfirmation:
        if params.get("auth_token") != "trusted-token":
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        if session_id != SCOPE.session_id or params.get("session_id") != session_id:
            raise FormalTaskViolation(
                "FORMAL_TASK_SESSION_MISMATCH",
                "formal task session does not match",
                ErrorCode.PERMISSION_DENIED,
            )
        self.prepare_calls.append((operation, dict(params)))
        target = str(params["task_id"]) if operation == "task.cancel" else None
        intent = hashlib.sha256(
            repr(
                (
                    operation,
                    params.get("command_id"),
                    target,
                    params.get("name"),
                    params.get("instruction"),
                    params.get("model_intent"),
                )
            ).encode("utf-8")
        ).hexdigest()
        return PreparedP3MutationConfirmation(
            binding=P3ConfirmationBinding(
                principal_id=SCOPE.subject_id,
                scope=SCOPE,
                operation=operation,
                command_id=str(params["command_id"]),
                target_task_id=target,
                intent_fingerprint=intent,
            ),
            correlation_id=str(params["correlation_id"]),
            issued_at=str(params["issued_at"]),
            observed_at=NOW,
        )

    async def reauthorize_mutation_replay(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        session_id: str | None,
        expected_binding: P3ConfirmationBinding,
    ) -> None:
        if self.replay_authority_revoked:
            raise FormalTaskViolation(
                "TASK_CONTEXT_PERMISSION_MISSING",
                "formal task authority was revoked",
                ErrorCode.PERMISSION_DENIED,
            )
        prepared = await self.prepare_mutation_confirmation(
            operation=operation,
            params=params,
            session_id=session_id,
        )
        if prepared.binding != expected_binding:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_BINDING_MISMATCH",
                "formal task replay binding changed",
                ErrorCode.PERMISSION_DENIED,
            )

    async def handle(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        prepared = await self.prepare_mutation_confirmation(
            operation=operation,
            params=params,
            session_id=session_id,
        )
        self.verifier.verify_and_consume(
            str(params["confirmation_id"]),
            prepared.binding,
            now=NOW,
        )
        self.mutation_calls.append((operation, dict(params)))
        return P3RouteResult(
            True,
            {
                "request_id": request_id,
                "ok": True,
                "result": {"accepted": True, "operation": operation},
                "error": None,
            },
        )


def _registry(
    tmp_path: Path,
    *,
    p2: bool = True,
    p3: bool = True,
    push_success: bool = True,
    commit_ledger: TurnCommitLedger | None = None,
    p2_retriable_fault_plan: ProductP2RetriableFaultPlan | None = None,
):
    p3_composition = _P3Composition(tmp_path)
    manager = _AgentManager()
    pushed: list[dict[str, object]] = []

    async def push(message: dict[str, object]) -> bool:
        pushed.append(message)
        return push_success

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=p2,
            p3_text_enabled=p3,
            p2_retriable_fault_plan=p2_retriable_fault_plan,
        ),
        p3_composition=p3_composition,
        agent_manager=manager,
        push_text_event=push,
        commit_ledger=commit_ledger,
    )
    return registry, p3_composition, manager, pushed


def _p2_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": "correlation-p2",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }
    params.update(changes)
    return params


def _progress_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "task_id": "task-1",
        "correlation_id": "correlation-task-1",
        "origin_id": "web-surface-1",
        "generation_id": "web-session-generation-1",
        "generation": 1,
    }
    params.update(changes)
    return params


def _progress_ack_params(
    event: Mapping[str, object], **changes: object
) -> dict[str, object]:
    source = cast(Mapping[str, object], event["source_event"])
    progress = cast(Mapping[str, object], event["progress_event"])
    params = _progress_params(
        session_id=event["session_id"],
        task_id=event["task_id"],
        correlation_id=event["correlation_id"],
        origin_id=event["origin_id"],
        generation_id=event["generation_id"],
        generation=event["generation"],
        delivery_id=event["delivery_id"],
        source_event_id=source["event_id"],
        progress_event_id=progress["event_id"],
        seq=source["seq"],
        evidence_id=event["evidence_id"],
    )
    params.update(changes)
    return params


def _route(payload: dict[str, object], segment: str) -> dict[str, object]:
    manifest = cast(dict[str, object], payload["product_composition"])
    routes = cast(list[dict[str, object]], manifest["routes"])
    return next(item for item in routes if item["segment"] == segment)


def test_master_flag_off_constructs_no_registry_or_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PRODUCT_COMPOSITION_ENABLE_ENV, raising=False)
    monkeypatch.setenv(
        PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID_ENV,
        "ignored-with-master-off",
    )

    class _Poison:
        def __getattribute__(self, _name):
            raise AssertionError("feature-off inspected P3 composition")

    result = create_product_composition_registry_from_environment(
        p3_composition=cast(P3AuthenticatedComposition, _Poison()),
        agent_manager=_Poison(),
        push_text_event=cast(object, _Poison()),
    )

    assert result is None


def test_p2_retriable_fault_plan_is_default_off_and_requires_exact_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID_ENV, raising=False)
    monkeypatch.delenv(PRODUCT_P2_RETRIABLE_FAULT_OPERATION_ENV, raising=False)

    assert ProductCompositionSettings.from_environment().p2_retriable_fault_plan is None

    monkeypatch.setenv(
        PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID_ENV,
        "request-p2-retriable-fault",
    )
    with pytest.raises(ValueError, match="requires exact request_id and operation"):
        ProductCompositionSettings.from_environment()

    monkeypatch.setenv(
        PRODUCT_P2_RETRIABLE_FAULT_OPERATION_ENV,
        "live_voice.composition.p2.submit",
    )
    with pytest.raises(ValueError, match="exact presentation ACK"):
        ProductCompositionSettings.from_environment()

    monkeypatch.setenv(
        PRODUCT_P2_RETRIABLE_FAULT_OPERATION_ENV,
        "live_voice.composition.p2.presentation.ack",
    )
    settings = ProductCompositionSettings.from_environment()

    assert settings.p2_retriable_fault_plan == ProductP2RetriableFaultPlan(
        request_id="request-p2-retriable-fault",
        operation="live_voice.composition.p2.presentation.ack",
    )


def test_factory_requires_real_authenticated_authority_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PRODUCT_COMPOSITION_ENABLE_ENV, "1")
    monkeypatch.setenv(PRODUCT_P2_ENABLE_ENV, "0")
    monkeypatch.setenv(PRODUCT_P3_TEXT_ENABLE_ENV, "0")

    with pytest.raises(FormalTaskViolation) as caught:
        create_product_composition_registry_from_environment(
            p3_composition=None,
            agent_manager=object(),
            push_text_event=cast(object, lambda _message: None),
        )

    assert caught.value.reason == "PRODUCT_TRUSTED_AUTHORITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_p2_authority_first_activation_replay_and_exact_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("code", "normal"),
    )

    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-1",
        session_id="session-product",
        channel_id="web",
    )
    denied_replay = await registry.handle_p2_activate(
        params=_p2_params(auth_token="wrong-token"),
        request_id="request-p2-denied-replay",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True
    assert denied_replay.ok is False
    assert replayed.ok is True
    assert cast(dict, replayed.payload["result"])["replayed"] is True
    assert [call["operation"] for call in p3.authority_calls] == [
        "agent.chat",
        "agent.chat",
        "agent.chat",
    ]
    assert len(manager.get_calls) == 1
    assert manager.pins == 1
    assert _route(activated.payload, "authority")["truth"] == "formal"
    assert _route(activated.payload, "p1.speech_media")["reason_id"] == (
        "MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN"
    )
    assert _route(activated.payload, "p2.agent_interaction")["truth"] == ("formal")
    assert _route(activated.payload, "p3.control")["reason_id"] == (
        "P3_CONFIRMATION_ISSUER_UNAVAILABLE"
    )
    assert _route(activated.payload, "observability")["reason_id"] == (
        "ADAPTER_NOT_REGISTERED"
    )

    mismatched = await registry.handle_p2_close(
        params=_p2_params(correlation_id="wrong-correlation"),
        request_id="request-p2-bad-close",
        session_id="session-product",
    )
    assert mismatched.ok is False
    assert manager.unpins == 0

    denied_close = await registry.handle_p2_close(
        params=_p2_params(auth_token="wrong-token"),
        request_id="request-p2-denied-close",
        session_id="session-product",
    )
    assert denied_close.ok is False
    assert manager.unpins == 0

    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-close",
        session_id="session-product",
    )
    assert closed.ok is True
    assert manager.unpins == 1
    replayed_close = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-close-replay",
        session_id="session-product",
    )
    assert replayed_close.ok is True
    assert cast(dict, replayed_close.payload["result"])["replayed"] is True
    assert manager.unpins == 1
    assert [call["operation"] for call in p3.authority_calls] == [
        "agent.chat",
        "agent.chat",
        "agent.chat",
        "agent.chat",
        "agent.chat",
        "agent.chat",
        "agent.chat",
    ]


@pytest.mark.asyncio
async def test_p2_denied_or_unavailable_authority_has_zero_downstream_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("agent", None),
    )

    denied = await registry.handle_p2_activate(
        params=_p2_params(auth_token="wrong-token"),
        request_id="request-p2-denied",
        session_id="session-product",
        channel_id="web",
    )
    p3.fail_authority = FormalTaskViolation(
        "TASK_CONTEXT_REVISION_UNAVAILABLE",
        "project revision unavailable",
        ErrorCode.UNAVAILABLE,
    )
    unavailable = await registry.handle_p2_activate(
        params=_p2_params(interaction_id="interaction-2"),
        request_id="request-p2-unavailable",
        session_id="session-product",
        channel_id="web",
    )

    assert denied.ok is False
    assert unavailable.ok is False
    assert manager.get_calls == []
    assert manager.pins == 0


@pytest.mark.asyncio
async def test_p2_candidate_correlation_mismatch_allocates_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)
    p3.correlation_override = "other-correlation"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("agent", None),
    )

    result = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-mismatch",
        session_id="session-product",
        channel_id="web",
    )

    assert result.ok is False
    assert manager.get_calls == []
    assert manager.pins == 0


@pytest.mark.asyncio
async def test_p3_query_uses_central_authority_and_real_query_owner(
    tmp_path: Path,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)

    result = await registry.handle_p3_query(
        operation="task.get",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
        },
        request_id="request-query-1",
        session_id="session-product",
    )

    assert result.ok is True
    assert len(p3.authority_calls) == 1
    assert len(p3.query_calls) == 1
    assert manager.get_calls == []
    assert _route(result.payload, "authority")["truth"] == "formal"
    assert _route(result.payload, "p3.query")["truth"] == "formal"
    assert _route(result.payload, "p3.progress")["truth"] == "unavailable"


@pytest.mark.asyncio
async def test_p3_query_denied_and_mutation_have_zero_query_effect(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, _pushed = _registry(tmp_path)

    denied = await registry.handle_p3_query(
        operation="task.get",
        params={
            "auth_token": "wrong-token",
            "session_id": "session-product",
            "task_id": "task-1",
        },
        request_id="request-query-denied",
        session_id="session-product",
    )
    mutation = await registry.handle_p3_query(
        operation="task.create",
        params={},
        request_id="request-query-mutation",
        session_id="session-product",
    )
    wrong_claim = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "claimed_project_id": "project-other",
        },
        request_id="request-query-wrong-claim",
        session_id="session-product",
    )
    authority_calls = len(p3.authority_calls)
    unknown_field = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "browser_is_admin": True,
        },
        request_id="request-query-unknown-field",
        session_id="session-product",
    )
    ignored_list_target = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
        },
        request_id="request-query-list-target",
        session_id="session-product",
    )
    ignored_get_cursor = await registry.handle_p3_query(
        operation="task.get",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
            "after_seq": 0,
        },
        request_id="request-query-get-cursor",
        session_id="session-product",
    )

    assert denied.ok is False
    assert mutation.ok is False
    assert wrong_claim.ok is False
    assert unknown_field.ok is False
    assert ignored_list_target.ok is False
    assert ignored_get_cursor.ok is False
    assert len(p3.authority_calls) == authority_calls
    assert p3.query_calls == []


@pytest.mark.asyncio
async def test_text_progress_reaches_web_sink_and_preserves_generation_cleanup(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path)

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-1",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert activated.ok is True
    assert len(p3.subscription_calls) == 1
    assert len(pushed) == 1
    event_payload = cast(dict, pushed[0]["payload"])
    assert event_payload["event_type"] == "live_voice.task.progress"
    assert len(cast(str, event_payload["delivery_id"])) == 64
    assert event_payload["task_id"] == "task-1"
    assert event_payload["correlation_id"] == "correlation-task-1"
    assert event_payload["generation"] == 1
    assert _route(activated.payload, "p3.progress")["truth"] == "formal"
    assert cast(dict, activated.payload["result"])["voice_progress"] == ("unavailable")

    denied_replay = await registry.handle_p3_progress_activate(
        params=_progress_params(auth_token="wrong-token"),
        request_id="request-progress-denied-replay",
        session_id="session-product",
        channel_id="web",
    )
    assert denied_replay.ok is False
    assert len(p3.subscription_calls) == 1

    stale = await registry.handle_p3_progress_activate(
        params=_progress_params(correlation_id="other-correlation"),
        request_id="request-progress-stale",
        session_id="session-product",
        channel_id="web",
    )
    assert stale.ok is False
    assert len(p3.subscription_calls) == 1

    denied_close = await registry.handle_p3_progress_close(
        params=_progress_params(auth_token="wrong-token"),
        request_id="request-progress-denied-close",
        session_id="session-product",
    )
    assert denied_close.ok is False
    assert len(p3.subscription_calls) == 1

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-close",
        session_id="session-product",
    )
    assert closed.ok is True
    replayed_close = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-ack-close-replay",
        session_id="session-product",
    )
    assert replayed_close.ok is True
    assert cast(dict, replayed_close.payload["result"])["replayed"] is True
    assert len(p3.authority_calls) == 6


@pytest.mark.asyncio
async def test_text_progress_web_ack_is_exact_authorized_and_idempotent(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path)
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-ack-activate",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert activated.ok is True
    event = cast(Mapping[str, object], pushed[0]["payload"])

    denied = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event, auth_token="wrong-token"),
        request_id="request-progress-ack-denied",
        session_id="session-product",
        channel_id="web",
    )
    mismatched = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event, progress_event_id="wrong-progress"),
        request_id="request-progress-ack-mismatch",
        session_id="session-product",
        channel_id="web",
    )
    wrong_channel = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-ack-channel",
        session_id="session-product",
        channel_id="tui",
    )
    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-ack",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-ack-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert denied.ok is False
    assert mismatched.ok is False
    assert wrong_channel.ok is False
    assert acknowledged.ok is True
    assert replayed.ok is True
    assert cast(dict, acknowledged.payload["result"])["replayed"] is False
    assert cast(dict, replayed.payload["result"])["replayed"] is True
    assert cast(dict, acknowledged.payload["result"])["acknowledgement"] == (
        "web_ui_text_consumed"
    )
    assert len(p3.subscription_calls) == 1

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-ack-close",
        session_id="session-product",
    )
    assert closed.ok is True


@pytest.mark.asyncio
async def test_progress_ack_response_loss_is_stale_after_newer_generation(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-lost-ack-activate",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert activated.ok is True
    event = cast(Mapping[str, object], pushed[0]["payload"])

    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-lost-ack",
        session_id="session-product",
        channel_id="web",
    )
    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-lost-ack-close",
        session_id="session-product",
    )
    stale = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-lost-ack-stale-reactivate",
        session_id="session-product",
        channel_id="web",
    )
    reactivated = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id="request-progress-lost-ack-reactivate",
        session_id="session-product",
        channel_id="web",
    )
    replayed_after_newer_generation = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-lost-ack-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert acknowledged.ok is True
    assert closed.ok is True
    assert stale.ok is False
    assert cast(dict, stale.payload["error"])["reason"] == (
        "TASK_PROGRESS_ROUTE_SETTLED"
    )
    assert reactivated.ok is True
    assert replayed_after_newer_generation.ok is False
    replay_error = cast(dict, replayed_after_newer_generation.payload["error"])
    assert replay_error["code"] == ErrorCode.STALE.value
    assert replay_error["reason"] == "TASK_PROGRESS_STALE_GENERATION"
    await registry.close_active_routes()


@pytest.mark.asyncio
@pytest.mark.parametrize("current_route_state", ["active", "closed"])
async def test_progress_ack_generation_ordering_is_identity_bound_and_effect_free(
    tmp_path: Path,
    current_route_state: str,
) -> None:
    registry, p3, manager, pushed = _registry(tmp_path)
    first = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id=f"request-progress-stale-{current_route_state}-first",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert first.ok is True
    first_event = cast(Mapping[str, object], pushed[0]["payload"])
    first_closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id=f"request-progress-stale-{current_route_state}-first-close",
        session_id="session-product",
    )
    second = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id=f"request-progress-stale-{current_route_state}-second",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert first_closed.ok is True
    assert second.ok is True
    assert len(pushed) == 2
    second_event = cast(Mapping[str, object], pushed[1]["payload"])

    if current_route_state == "closed":
        second_closed = await registry.handle_p3_progress_close(
            params=_progress_params(generation=2),
            request_id="request-progress-stale-second-close",
            session_id="session-product",
        )
        assert second_closed.ok is True

    key = (
        "session-product",
        "task-1",
        "web-surface-1",
        "web-session-generation-1",
    )
    first_delivery_id = cast(str, first_event["delivery_id"])
    second_delivery_id = cast(str, second_event["delivery_id"])
    first_delivery = registry._closed_progress_routes[(*key, 1)].deliveries[
        first_delivery_id
    ]
    if current_route_state == "active":
        second_delivery = registry._progress_deliveries[key][second_delivery_id]
    else:
        second_delivery = registry._closed_progress_routes[(*key, 2)].deliveries[
            second_delivery_id
        ]
    effect_snapshot = (
        len(p3.subscription_calls),
        len(p3.query_calls),
        len(pushed),
        len(manager.get_calls),
        manager.agent.calls,
        first_delivery.acknowledged,
        second_delivery.acknowledged,
    )

    stale = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(first_event),
        request_id=f"request-progress-stale-{current_route_state}-old-ack",
        session_id="session-product",
        channel_id="web",
    )

    assert stale.ok is False
    stale_error = cast(dict, stale.payload["error"])
    assert stale_error["code"] == ErrorCode.STALE.value
    assert stale_error["reason"] == "TASK_PROGRESS_STALE_GENERATION"
    assert (
        len(p3.subscription_calls),
        len(p3.query_calls),
        len(pushed),
        len(manager.get_calls),
        manager.agent.calls,
        first_delivery.acknowledged,
        second_delivery.acknowledged,
    ) == effect_snapshot

    wrong_identity = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(first_event),
        request_id=f"request-progress-stale-{current_route_state}-wrong-channel",
        session_id="session-product",
        channel_id="tui",
    )
    wrong_correlation = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(
            first_event,
            correlation_id="wrong-progress-correlation",
        ),
        request_id=f"request-progress-stale-{current_route_state}-wrong-correlation",
        session_id="session-product",
        channel_id="web",
    )
    future_generation = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(second_event, generation=3),
        request_id=f"request-progress-stale-{current_route_state}-future",
        session_id="session-product",
        channel_id="web",
    )
    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(second_event),
        request_id=f"request-progress-stale-{current_route_state}-current",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(second_event),
        request_id=f"request-progress-stale-{current_route_state}-current-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert wrong_identity.ok is False
    wrong_identity_error = cast(dict, wrong_identity.payload["error"])
    assert wrong_identity_error["code"] == ErrorCode.PERMISSION_DENIED.value
    assert wrong_identity_error["reason"] == "TASK_PROGRESS_BINDING_MISMATCH"
    assert wrong_correlation.ok is False
    wrong_correlation_error = cast(dict, wrong_correlation.payload["error"])
    assert wrong_correlation_error["code"] == ErrorCode.PERMISSION_DENIED.value
    assert wrong_correlation_error["reason"] == "TASK_PROGRESS_BINDING_MISMATCH"
    assert future_generation.ok is False
    future_error = cast(dict, future_generation.payload["error"])
    assert future_error["code"] != ErrorCode.STALE.value
    assert future_error["reason"] != "TASK_PROGRESS_STALE_GENERATION"
    assert acknowledged.ok is True
    assert replayed.ok is True
    assert cast(dict, acknowledged.payload["result"])["replayed"] is False
    assert cast(dict, replayed.payload["result"])["replayed"] is True
    await registry.close_active_routes()


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_kind", ["close", "disconnect"])
async def test_progress_push_cleanup_race_retains_exact_ack_owner(
    tmp_path: Path,
    cleanup_kind: str,
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    push_entered = asyncio.Event()
    push_release = asyncio.Event()

    async def blocked_push(message: dict[str, object]) -> bool:
        push_entered.set()
        await push_release.wait()
        pushed.append(message)
        return True

    registry._push_text_event = blocked_push
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id=f"request-progress-race-{cleanup_kind}-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    await asyncio.wait_for(push_entered.wait(), timeout=1)

    if cleanup_kind == "close":
        cleanup = asyncio.create_task(
            registry.handle_p3_progress_close(
                params=_progress_params(),
                request_id="request-progress-race-close",
                session_id="session-product",
            )
        )
    else:
        cleanup = asyncio.create_task(registry.close_active_routes())
    await asyncio.sleep(0)
    push_release.set()
    cleanup_result = await cleanup
    if cleanup_kind == "close":
        assert cleanup_result.ok is True
    assert len(pushed) == 1

    event = cast(Mapping[str, object], pushed[0]["payload"])
    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id=f"request-progress-race-{cleanup_kind}-ack",
        session_id="session-product",
        channel_id="web",
    )
    assert acknowledged.ok is True
    assert cast(dict, acknowledged.payload["result"])["replayed"] is False


@pytest.mark.asyncio
async def test_progress_delivery_capacity_never_evicts_unacknowledged_on_failed_send(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-capacity-activate",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert activated.ok is True
    assert len(pushed) == 1

    key = next(iter(registry._progress_deliveries))
    deliveries = registry._progress_deliveries[key]
    first_id = next(iter(deliveries))
    for index in range(1, registry._PROGRESS_DELIVERY_CAPACITY):
        delivery_id = f"retained-unacknowledged-{index}"
        deliveries[delivery_id] = _ProgressDelivery(
            delivery_id=delivery_id,
            source_event_id=f"source-{index}",
            progress_event_id=f"progress-{index}",
            seq=index,
            evidence_id=f"evidence-{index}",
            delivered=True,
        )
    original_ids = set(deliveries)
    route = registry._progress_routes[key]
    event = SimpleNamespace(
        origin=route.binding,
        source_event=SimpleNamespace(
            to_dict=lambda: {"event_id": "source-capacity", "seq": 1000}
        ),
        progress_event=SimpleNamespace(
            to_dict=lambda: {"event_id": "progress-capacity", "seq": 1000}
        ),
        evidence_id="evidence-capacity",
    )

    with pytest.raises(RuntimeError, match="no safe eviction"):
        await registry._emit_text_progress(event)
    assert set(deliveries) == original_ids
    assert len(pushed) == 1

    deliveries[first_id].acknowledged = True
    failed_pushes = 0

    async def fail_push(_message: dict[str, object]) -> bool:
        nonlocal failed_pushes
        failed_pushes += 1
        return False

    registry._push_text_event = fail_push
    with pytest.raises(RuntimeError, match="sink is unavailable"):
        await registry._emit_text_progress(event)

    assert failed_pushes == 1
    assert first_id not in deliveries
    assert set(deliveries) == original_ids - {first_id}


@pytest.mark.asyncio
async def test_progress_generation_admission_is_bounded_without_unsafe_eviction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    monkeypatch.setattr(registry, "_PROGRESS_GENERATION_CAPACITY", 2)
    first_params = _progress_params(
        origin_id="web-surface-1",
        generation_id="web-generation-1",
    )
    second_params = _progress_params(
        origin_id="web-surface-2",
        generation_id="web-generation-2",
    )
    third_params = _progress_params(
        origin_id="web-surface-3",
        generation_id="web-generation-3",
    )

    first = await registry.handle_p3_progress_activate(
        params=first_params,
        request_id="request-progress-capacity-first",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert first.ok is True
    first_event = cast(Mapping[str, object], pushed[0]["payload"])
    first_closed = await registry.handle_p3_progress_close(
        params=first_params,
        request_id="request-progress-capacity-first-close",
        session_id="session-product",
    )
    second = await registry.handle_p3_progress_activate(
        params=second_params,
        request_id="request-progress-capacity-second",
        session_id="session-product",
        channel_id="web",
    )
    denied = await registry.handle_p3_progress_activate(
        params=third_params,
        request_id="request-progress-capacity-denied",
        session_id="session-product",
        channel_id="web",
    )

    assert first_closed.ok is True
    assert second.ok is True
    assert denied.ok is False
    assert cast(dict, denied.payload["error"])["reason"] == (
        "TASK_PROGRESS_ROUTE_CAPACITY_UNAVAILABLE"
    )
    assert len(registry._progress_generations) == 2
    assert any(key[2] == "web-surface-1" for key in registry._closed_progress_routes)
    assert any(key[2] == "web-surface-2" for key in registry._progress_routes)

    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(first_event),
        request_id="request-progress-capacity-first-ack",
        session_id="session-product",
        channel_id="web",
    )
    unauthorized = await registry.handle_p3_progress_activate(
        params={**third_params, "auth_token": "wrong-token"},
        request_id="request-progress-capacity-unauthorized",
        session_id="session-product",
        channel_id="web",
    )
    assert unauthorized.ok is False
    assert any(key[2] == "web-surface-1" for key in registry._progress_generations)
    assert any(key[2] == "web-surface-1" for key in registry._closed_progress_routes)
    admitted = await registry.handle_p3_progress_activate(
        params=third_params,
        request_id="request-progress-capacity-admitted",
        session_id="session-product",
        channel_id="web",
    )

    assert acknowledged.ok is True
    assert admitted.ok is True
    assert len(registry._progress_generations) == 2
    assert all(key[2] != "web-surface-1" for key in registry._progress_generations)
    assert any(key[2] == "web-surface-2" for key in registry._progress_routes)
    assert any(key[2] == "web-surface-3" for key in registry._progress_routes)
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_progress_authority_failure_allocates_no_subscription_or_sink(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path)
    p3.fail_authority = FormalTaskViolation(
        "FORMAL_TASK_AUTHORIZATION_DENIED",
        "scope denied",
        ErrorCode.PERMISSION_DENIED,
    )

    result = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-denied",
        session_id="session-product",
        channel_id="web",
    )

    assert result.ok is False
    assert p3.subscription_calls == []
    assert pushed == []


@pytest.mark.asyncio
async def test_terminal_progress_route_cannot_replay_as_active(tmp_path: Path) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path)
    p3.subscription_event_type = "task.terminal"

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-terminal",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    replayed = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-terminal-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True
    assert len(pushed) == 1
    assert replayed.ok is False
    assert cast(dict, replayed.payload["error"])["reason"] == (
        "TASK_PROGRESS_ROUTE_SETTLED"
    )
    assert len(p3.subscription_calls) == 1

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-terminal-close",
        session_id="session-product",
    )
    assert closed.ok is True


@pytest.mark.asyncio
async def test_failed_progress_sink_cannot_replay_as_active(tmp_path: Path) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path, push_success=False)

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-sink-failure",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    replayed = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-sink-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True
    assert len(pushed) == 1
    assert replayed.ok is False
    assert cast(dict, replayed.payload["error"])["reason"] == (
        "TASK_PROGRESS_ROUTE_SETTLED"
    )
    assert len(p3.subscription_calls) == 1

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-sink-close",
        session_id="session-product",
    )
    assert closed.ok is True


@pytest.mark.asyncio
async def test_disconnect_cleanup_closes_p2_and_progress_without_stopping_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("agent", None),
    )
    await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2",
        session_id="session-product",
        channel_id="web",
    )
    await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress",
        session_id="session-product",
        channel_id="web",
    )

    await registry.close_active_routes()

    assert manager.unpins == 1
    p2_reconciled = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-disconnect-close-replay",
        session_id="session-product",
    )
    progress_reconciled = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-disconnect-close-replay",
        session_id="session-product",
    )
    assert p2_reconciled.ok is True
    assert progress_reconciled.ok is True
    assert cast(dict, p2_reconciled.payload["result"])["replayed"] is True
    assert cast(dict, progress_reconciled.payload["result"])["replayed"] is True
    assert manager.unpins == 1

    p2_reactivated = await registry.handle_p2_activate(
        params=_p2_params(activation_id="activation-2", activation_generation=2),
        request_id="request-p2-after-disconnect",
        session_id="session-product",
        channel_id="web",
    )
    progress_reactivated = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id="request-progress-after-disconnect",
        session_id="session-product",
        channel_id="web",
    )
    assert p2_reactivated.ok is True
    assert progress_reactivated.ok is True
    second = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
        },
        request_id="request-after-disconnect",
        session_id="session-product",
    )
    assert second.ok is True
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_progress_close_failure_is_retained_and_exact_retry_succeeds(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, _pushed = _registry(tmp_path)
    p3.subscription_event = False
    p3.subscription_close_failures = 1
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-retry-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    first = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-retry-first",
        session_id="session-product",
    )
    second = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-retry-second",
        session_id="session-product",
    )

    assert first.ok is False
    assert cast(dict, first.payload["error"])["reason"] == (
        "PRODUCT_P3_PROGRESS_CLEANUP_PENDING"
    )
    assert second.ok is True
    assert len(p3.authority_calls) == 3


@pytest.mark.asyncio
async def test_registry_stop_remains_retryable_after_cleanup_failure(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, _pushed = _registry(tmp_path)
    p3.subscription_event = False
    p3.subscription_close_failures = 1
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-stop-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    with pytest.raises(RuntimeError, match="cleanup remains pending"):
        await registry.stop()
    await registry.stop()

    rejected = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id="request-progress-after-stop",
        session_id="session-product",
        channel_id="web",
    )
    assert rejected.ok is False
    assert cast(dict, rejected.payload["error"])["reason"] == (
        "PRODUCT_COMPOSITION_STOPPED"
    )


@pytest.mark.asyncio
async def test_stop_waits_for_inflight_query_before_closing_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    original = registry._p3_adapter.activate_prepared_query

    async def blocked_query(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(
        registry._p3_adapter,
        "activate_prepared_query",
        blocked_query,
    )
    query_task = asyncio.create_task(
        registry.handle_p3_query(
            operation="task.list",
            params={
                "auth_token": "trusted-token",
                "session_id": "session-product",
            },
            request_id="request-blocked-query",
            session_id="session-product",
        )
    )
    await entered.wait()
    stop_task = asyncio.create_task(registry.stop())
    await asyncio.sleep(0)

    assert stop_task.done() is False
    release.set()
    result = await query_task
    await stop_task

    assert result.ok is True


@pytest.mark.asyncio
async def test_activation_queued_before_stop_rechecks_state_before_authority(
    tmp_path: Path,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)
    await registry._lock.acquire()
    activation_task = asyncio.create_task(
        registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-queued-before-stop",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.sleep(0)
    stop_task = asyncio.create_task(registry.stop())
    await asyncio.sleep(0)
    registry._lock.release()

    result = await activation_task
    await stop_task

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "PRODUCT_COMPOSITION_STOPPED"
    )
    assert p3.authority_calls == []
    assert manager.get_calls == []


@pytest.mark.asyncio
async def test_segment_flags_fail_before_authority_or_downstream(
    tmp_path: Path,
) -> None:
    registry, p3, manager, pushed = _registry(tmp_path, p2=False, p3=False)

    p2 = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-off",
        session_id="session-product",
        channel_id="web",
    )
    query = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
        },
        request_id="request-p3-off",
        session_id="session-product",
    )
    progress_ack = await registry.handle_p3_progress_ack(
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
            "correlation_id": "correlation-task-1",
            "origin_id": "web-surface",
            "generation_id": "web-generation",
            "generation": 1,
            "delivery_id": "delivery-1",
            "source_event_id": "event-1",
            "progress_event_id": "progress-1",
            "seq": 1,
            "evidence_id": "evidence-1",
        },
        request_id="request-p3-ack-off",
        session_id="session-product",
        channel_id="web",
    )

    assert p2.ok is False
    assert query.ok is False
    assert progress_ack.ok is False
    assert p3.authority_calls == []
    assert p3.query_calls == []
    assert p3.subscription_calls == []
    assert manager.get_calls == []
    assert pushed == []


@pytest.mark.asyncio
async def test_p2_text_submit_notification_and_exact_presentation_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("code", "normal"),
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    history = _HistoryWriter()
    route.activation_lease._runtime._history_writer = history
    submit_params = _p2_params(
        commit_id="commit-1",
        turn_id="turn-1",
        response_id="response-1",
        committed_at=NOW,
        text="hello product agent",
    )

    wrong_generation = await registry.handle_p2_submit(
        params={**submit_params, "activation_generation": 2},
        request_id="request-submit-wrong-generation",
        session_id="session-product",
        channel_id="web",
    )
    submitted = await registry.handle_p2_submit(
        params=submit_params,
        request_id="request-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p2_submit(
        params=submit_params,
        request_id="request-submit-1",
        session_id="session-product",
        channel_id="web",
    )

    assert wrong_generation.ok is False
    assert cast(dict, wrong_generation.payload["error"])["reason"] == (
        "ACTIVATION_BINDING_MISMATCH"
    )
    assert submitted.ok is True
    assert replayed.payload == submitted.payload
    assert manager.agent.calls == 1
    presentation: dict[str, object] | None = None
    response: dict[str, object] | None = None
    presentation_notification_request_id: str | None = None
    for index in range(4):
        notification_request_id = f"request-notification-{index}"
        polled = await asyncio.wait_for(
            registry.handle_p2_notification_next(
                params=_p2_params(notification_sequence=index + 1),
                request_id=notification_request_id,
                session_id="session-product",
            ),
            timeout=1,
        )
        assert polled.ok is True
        notification = cast(dict[str, object], polled.payload["result"])
        candidate = notification["presentation_unit"]
        if isinstance(candidate, dict):
            presentation = cast(dict[str, object], candidate)
            response = cast(dict[str, object], notification["response"])
            presentation_notification_request_id = notification_request_id
            break
    assert presentation is not None
    assert response is not None
    assert presentation_notification_request_id is not None

    ack_params = _p2_params(
        response_id=response["response_id"],
        response_generation=response["response_generation"],
        surface=presentation["surface"],
        unit_id=presentation["unit_id"],
        contiguous_cursor=presentation["seq"],
        presented_at=NOW,
    )
    acknowledged = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id="request-ack-1",
        session_id="session-product",
    )
    ack_replay = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id="request-ack-1",
        session_id="session-product",
    )

    assert acknowledged.ok is True
    assert ack_replay.payload == acknowledged.payload
    assert cast(dict, acknowledged.payload["result"])["accepted"] is True
    assert len(history.assistants) == 1
    await registry.close_active_routes()
    submit_after_disconnect = await registry.handle_p2_submit(
        params=submit_params,
        request_id="request-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    notification_after_disconnect = await registry.handle_p2_notification_next(
        params=_p2_params(
            notification_sequence=int(
                presentation_notification_request_id.rpartition("-")[2]
            )
            + 1
        ),
        request_id=presentation_notification_request_id,
        session_id="session-product",
    )
    ack_after_disconnect = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id="request-ack-1",
        session_id="session-product",
    )
    submit_conflict_after_disconnect = await registry.handle_p2_submit(
        params={**submit_params, "commit_id": "commit-conflict"},
        request_id="request-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    new_submit_after_disconnect = await registry.handle_p2_submit(
        params={**submit_params, "commit_id": "commit-new"},
        request_id="request-submit-new",
        session_id="session-product",
        channel_id="web",
    )

    assert submit_after_disconnect.payload == submitted.payload
    assert notification_after_disconnect.payload == polled.payload
    assert ack_after_disconnect.payload == acknowledged.payload
    assert submit_conflict_after_disconnect.ok is False
    assert (
        cast(dict, submit_conflict_after_disconnect.payload["error"])["reason"]
        == "PRODUCT_REQUEST_ID_CONFLICT"
    )
    assert new_submit_after_disconnect.ok is False
    assert cast(dict, new_submit_after_disconnect.payload["error"])["reason"] == (
        "PRODUCT_P2_ROUTE_NOT_FOUND"
    )
    assert manager.agent.calls == 1
    assert len(history.assistants) == 1


@pytest.mark.asyncio
async def test_p2_retriable_fault_requires_schema_authority_and_exact_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fault_request_id = "request-p2-retriable-presentation-fault"
    registry, p3, manager, pushed = _registry(
        tmp_path,
        p2_retriable_fault_plan=ProductP2RetriableFaultPlan(
            request_id=fault_request_id,
            operation="live_voice.composition.p2.presentation.ack",
        ),
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("code", "normal"),
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-fault-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    history = _HistoryWriter()
    route.activation_lease._runtime._history_writer = history
    acknowledgement_calls: list[object] = []
    original_acknowledge = route.activation_lease.acknowledge_presentation

    async def track_acknowledgement(*args: object) -> object:
        acknowledgement_calls.append(args)
        return await original_acknowledge(*args)

    monkeypatch.setattr(
        route.activation_lease,
        "acknowledge_presentation",
        track_acknowledgement,
    )
    submitted = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-fault-1",
            turn_id="turn-fault-1",
            response_id="response-fault-1",
            committed_at=NOW,
            text="fault recovery turn",
        ),
        request_id="request-p2-fault-submit",
        session_id="session-product",
        channel_id="web",
    )
    assert submitted.ok is True
    presentation: dict[str, object] | None = None
    response: dict[str, object] | None = None
    for index in range(4):
        notification = await asyncio.wait_for(
            registry.handle_p2_notification_next(
                params=_p2_params(notification_sequence=index + 1),
                request_id=f"request-p2-fault-notification-{index}",
                session_id="session-product",
            ),
            timeout=1,
        )
        assert notification.ok is True
        notification_result = cast(dict[str, object], notification.payload["result"])
        candidate = notification_result["presentation_unit"]
        if isinstance(candidate, dict):
            presentation = cast(dict[str, object], candidate)
            response = cast(dict[str, object], notification_result["response"])
            break
    assert presentation is not None
    assert response is not None
    ack_params = _p2_params(
        response_id=response["response_id"],
        response_generation=response["response_generation"],
        surface=presentation["surface"],
        unit_id=presentation["unit_id"],
        contiguous_cursor=presentation["seq"],
        presented_at=NOW,
    )
    await asyncio.sleep(0)
    authority_calls_before_fault = len(p3.authority_calls)
    runtime_before = route.activation_lease._runtime.snapshot()
    manager_before = (
        tuple(manager.get_calls),
        manager.pins,
        manager.unpins,
        manager.agent.calls,
    )

    invalid_schema = await registry.handle_p2_presentation_ack(
        params={**ack_params, "fault": "client-claim"},
        request_id=fault_request_id,
        session_id="session-product",
    )
    wrong_binding = await registry.handle_p2_presentation_ack(
        params={**ack_params, "activation_generation": 2},
        request_id=fault_request_id,
        session_id="session-product",
    )
    injected = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id=fault_request_id,
        session_id="session-product",
    )

    assert invalid_schema.ok is False
    assert cast(dict, invalid_schema.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert len(p3.authority_calls) == authority_calls_before_fault + 2
    assert wrong_binding.ok is False
    assert cast(dict, wrong_binding.payload["error"])["reason"] == (
        "ACTIVATION_BINDING_MISMATCH"
    )
    assert injected.ok is False
    assert cast(dict, injected.payload["error"]) == {
        "code": "UNAVAILABLE",
        "reason": "PRODUCT_W2_RETRIABLE_FAULT_INJECTED",
        "message": (
            "the externally frozen W2 plan injected a retriable presentation fault"
        ),
    }
    assert _route(injected.payload, "p2.agent_interaction")["truth"] == "formal"

    # The fault is after schema/authority/binding validation but before every
    # ACK or protected business effect. Authority lookup is the sole delta.
    assert acknowledgement_calls == []
    assert registry._p2_ack_operations == {}
    assert route.activation_lease._runtime.snapshot() == runtime_before
    assert (
        tuple(manager.get_calls),
        manager.pins,
        manager.unpins,
        manager.agent.calls,
    ) == manager_before
    assert history.assistants == []
    assert p3.query_calls == []
    assert p3.subscription_calls == []
    assert pushed == []

    recovered = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id=fault_request_id,
        session_id="session-product",
    )
    replayed_recovery = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id=fault_request_id,
        session_id="session-product",
    )
    non_plan = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id="request-p2-non-plan-ack",
        session_id="session-product",
    )

    assert recovered.ok is True
    assert replayed_recovery.payload == recovered.payload
    assert non_plan.ok is True
    assert cast(dict, recovered.payload["result"])["accepted"] is True
    assert cast(dict, non_plan.payload["result"])["replayed"] is True
    assert len(acknowledgement_calls) == 2
    assert len(history.assistants) == 1
    assert manager.agent.calls == manager_before[3]
    assert p3.query_calls == []
    assert p3.subscription_calls == []
    assert pushed == []
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_retriable_fault_concurrency_consumes_exact_plan_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fault_request_id = "request-p2-concurrent-retriable-fault"
    registry, p3, manager, pushed = _registry(
        tmp_path,
        p2_retriable_fault_plan=ProductP2RetriableFaultPlan(
            request_id=fault_request_id,
            operation="live_voice.composition.p2.presentation.ack",
        ),
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("code", "normal"),
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-concurrent-fault-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    history = _HistoryWriter()
    route.activation_lease._runtime._history_writer = history
    acknowledgement_calls: list[object] = []
    acknowledgement_entered = asyncio.Event()
    release_acknowledgement = asyncio.Event()

    async def blocked_acknowledgement(*args: object) -> object:
        acknowledgement_calls.append(args)
        acknowledgement_entered.set()
        await release_acknowledgement.wait()
        return SimpleNamespace(
            accepted=False,
            replayed=False,
            history_records_written=0,
            history_pending=False,
        )

    monkeypatch.setattr(
        route.activation_lease,
        "acknowledge_presentation",
        blocked_acknowledgement,
    )
    params = _p2_params(
        response_id="response-concurrent-fault",
        response_generation=1,
        surface="text",
        unit_id="unit-concurrent-fault",
        contiguous_cursor=1,
        presented_at=NOW,
    )
    calls = tuple(
        asyncio.create_task(
            registry.handle_p2_presentation_ack(
                params=params,
                request_id=fault_request_id,
                session_id="session-product",
            )
        )
        for _ in range(2)
    )
    await asyncio.wait_for(acknowledgement_entered.wait(), timeout=1)
    await asyncio.sleep(0)

    completed_before_release = [call.result() for call in calls if call.done()]
    assert len(completed_before_release) == 1
    assert completed_before_release[0].ok is False
    assert cast(dict, completed_before_release[0].payload["error"])["reason"] == (
        "PRODUCT_W2_RETRIABLE_FAULT_INJECTED"
    )
    assert len(acknowledgement_calls) == 1
    assert len(registry._p2_ack_operations) == 1
    assert len(p3.authority_calls) == 3
    assert manager.agent.calls == 0
    assert history.users == []
    assert history.assistants == []
    assert p3.query_calls == []
    assert p3.subscription_calls == []
    assert pushed == []

    release_acknowledgement.set()
    results = await asyncio.gather(*calls)

    assert sum(result.ok for result in results) == 1
    assert len(acknowledgement_calls) == 1
    assert manager.agent.calls == 0
    assert history.users == []
    assert history.assistants == []
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_accepts_voice_origin_only_after_exact_success(tmp_path: Path) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(
        tmp_path, commit_ledger=ledger
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-voice-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    rejected = await registry.handle_p2_submit(
        params=_p2_params(
            activation_generation=2,
            commit_id="commit-rejected",
            turn_id="turn-rejected",
            response_id="response-rejected",
            committed_at=NOW,
            text="must never acquire task authority",
        ),
        request_id="request-submit-rejected-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert rejected.ok is False
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef("committed_turn", "turn-rejected", "commit-rejected"),
            SCOPE,
        )

    voice_text = "create the bounded voice task"
    submitted = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-voice-origin",
            turn_id="turn-voice-origin",
            response_id="response-voice-origin",
            committed_at=NOW,
            text=voice_text,
            dispatch_target="task",
            gateway_voice_claim={
                "kind": "formal_speech_recognition",
                "speech_operation_id": "speech-operation-1",
                "capture_id": "capture-1",
                "capture_generation": 1,
                "session_id": "session-product",
                "correlation_id": "correlation-p2",
                "interaction_id": "interaction-1",
                "turn_id": "turn-voice-origin",
                "commit_id": "commit-voice-origin",
                "text_sha256": hashlib.sha256(voice_text.encode("utf-8")).hexdigest(),
                "critical_policy": "eligible",
            },
        ),
        request_id="request-submit-voice-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert submitted.ok is True
    assert cast(dict, submitted.payload["result"])["status"] == (
        "task_origin_accepted"
    )
    accepted = ledger.require_origin(
        OriginRef("committed_turn", "turn-voice-origin", "commit-voice-origin"),
        SCOPE,
    )
    assert accepted.text == voice_text
    assert manager.agent.calls == 0

    ordinary = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-agent-chat",
            turn_id="turn-agent-chat",
            response_id="response-agent-chat",
            committed_at=NOW,
            text="answer this ordinary voice chat",
            dispatch_target="agent",
        ),
        request_id="request-submit-agent-chat",
        session_id="session-product",
        channel_id="web",
    )
    assert ordinary.ok is True
    assert manager.agent.calls == 1
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef("committed_turn", "turn-agent-chat", "commit-agent-chat"),
            SCOPE,
        )
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_product_p2_barge_in_is_exact_replayable_and_playback_scoped(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    blocking = _BlockingFacade()
    manager.agent = blocking
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-barge",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    submitted = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-barge",
            turn_id="turn-barge",
            response_id="response-barge",
            committed_at=NOW,
            text="keep this response active",
            dispatch_target="agent",
        ),
        request_id="request-submit-barge",
        session_id="session-product",
        channel_id="web",
    )
    assert submitted.ok is True
    await asyncio.wait_for(blocking.started.wait(), timeout=1)

    params = _p2_params(
        action_id="barge-action-1",
        response_id="response-barge",
        response_generation=0,
        cancel_response=False,
    )
    interrupted = await registry.handle_p2_barge_in(
        params=params,
        request_id="request-barge-1",
        session_id="session-product",
    )
    replayed = await registry.handle_p2_barge_in(
        params=params,
        request_id="request-barge-1",
        session_id="session-product",
    )
    conflict = await registry.handle_p2_barge_in(
        params={**params, "cancel_response": True},
        request_id="request-barge-1",
        session_id="session-product",
    )

    assert interrupted.ok is True
    assert replayed.payload == interrupted.payload
    assert conflict.ok is False
    assert cast(dict, conflict.payload["error"])["reason"] == (
        "PRODUCT_REQUEST_ID_CONFLICT"
    )
    result = cast(dict, interrupted.payload["result"])
    assert result["status"] == "barge_in_applied"
    assert result["cancel_response"] is False
    assert result["applied"] is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    effects = route.activation_lease._runtime._cr.snapshot().effects
    effect_types = [record.effect.effect_type for record in effects]
    assert effect_types.count("playback.stop") == 1
    assert not {"response.cancel", "round.cancel", "task.cancel"} & set(
        effect_types
    )

    blocking.release.set()
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_submit_caller_cancellation_retains_exact_disconnect_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    blocking = _BlockingFacade()
    manager.agent = blocking
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("code", "normal"),
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-activate-cancel",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    submit_params = _p2_params(
        commit_id="commit-cancel",
        turn_id="turn-cancel",
        response_id="response-cancel",
        committed_at=NOW,
        text="retained after caller cancellation",
    )

    caller = asyncio.create_task(
        registry.handle_p2_submit(
            params=submit_params,
            request_id="request-submit-cancel",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.wait_for(blocking.started.wait(), timeout=1)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    blocking.release.set()
    retained = registry._p2_submit_operations["request-submit-cancel"]
    first = await asyncio.wait_for(asyncio.shield(retained.task), timeout=1)
    try:
        await registry.close_active_routes()
    except RuntimeError:
        # The bounded disconnect close may report retained cleanup pending;
        # exact operation replay must remain available in either state.
        pass

    replay = await registry.handle_p2_submit(
        params=submit_params,
        request_id="request-submit-cancel",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is True
    assert replay.payload == first.payload
    assert blocking.calls == 1
    for _ in range(3):
        try:
            await registry.close_active_routes()
            break
        except RuntimeError:
            await asyncio.sleep(0)


def _mutation_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.cancel",
        "command_id": "command-cancel-1",
        "issued_at": NOW,
        "correlation_id": "correlation-cancel-1",
        "task_id": "task-1",
    }
    params.update(changes)
    return params


@pytest.mark.asyncio
async def test_p3_confirmation_issue_and_mutation_use_current_owner_permit(
    tmp_path: Path,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=False,
            p3_mutation_enabled=True,
        ),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issue_params = _mutation_params()

    issued = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-1",
        session_id="session-product",
    )
    replayed_issue = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-1",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])
    confirmation_id = cast(str, receipt["confirmation_id"])
    mutation_params = _mutation_params(confirmation_id=confirmation_id)

    prepared = await composition.prepare_mutation_confirmation(
        operation="task.cancel",
        params={
            key: value for key, value in mutation_params.items() if key != "operation"
        },
        session_id="session-product",
    )
    with pytest.raises(FormalTaskViolation) as direct:
        forwarder.verify_and_consume(confirmation_id, prepared.binding, now=NOW)

    mutated = await registry.handle_p3_mutation(
        params=mutation_params,
        request_id="request-mutation-1",
        session_id="session-product",
    )
    replayed_mutation = await registry.handle_p3_mutation(
        params=mutation_params,
        request_id="request-mutation-1",
        session_id="session-product",
    )

    assert issued.ok is True
    assert replayed_issue.payload == issued.payload
    assert receipt["status"] == "confirmation_issued"
    assert receipt["command_id"] == "command-cancel-1"
    assert receipt["target_task_id"] == "task-1"
    assert receipt["task_control_binding"] == {
        "subject_id": SCOPE.subject_id,
        "session_id": SCOPE.session_id,
        "project_id": SCOPE.project_id,
        "correlation_id": "correlation-cancel-1",
        "generation": registry._p3_confirmation_generation,
    }
    assert direct.value.reason == "P3_CONFIRMATION_FORWARDING_REQUIRED"
    assert mutated.ok is True
    assert replayed_mutation.payload == mutated.payload
    mutation_result = cast(dict[str, object], mutated.payload["result"])
    assert mutation_result["command_id"] == "command-cancel-1"
    assert mutation_result["target_task_id"] == "task-1"
    assert len(composition.mutation_calls) == 1
    assert _route(mutated.payload, "authority")["truth"] == "formal"
    assert _route(mutated.payload, "p3.control")["truth"] == "formal"


@pytest.mark.asyncio
async def test_p3_confirmation_owner_mismatch_and_request_conflict_fail_closed(
    tmp_path: Path,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issue_params = _mutation_params()
    issued = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-1",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])

    conflict = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(command_id="command-other"),
        request_id="request-confirmation-1",
        session_id="session-product",
    )
    mismatch = await registry.handle_p3_mutation(
        params=_mutation_params(
            confirmation_id=receipt["confirmation_id"],
            correlation_id="correlation-other",
        ),
        request_id="request-mutation-mismatch",
        session_id="session-product",
    )

    assert conflict.ok is False
    assert cast(dict, conflict.payload["error"])["reason"] == (
        "P3_CONFIRMATION_BINDING_MISMATCH"
    )
    assert mismatch.ok is False
    assert cast(dict, mismatch.payload["error"])["reason"] == (
        "P3_CONFIRMATION_BINDING_MISMATCH"
    )


@pytest.mark.asyncio
async def test_denied_p3_requests_do_not_reserve_replay_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)

    denied_issue = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(auth_token="invalid-token"),
        request_id="request-confirmation-denied-capacity",
        session_id="session-product",
    )
    issued = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-confirmation-valid-capacity",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])

    denied_mutation = await registry.handle_p3_mutation(
        params=_mutation_params(
            auth_token="invalid-token",
            confirmation_id=receipt["confirmation_id"],
        ),
        request_id="request-mutation-denied-capacity",
        session_id="session-product",
    )
    mutated = await registry.handle_p3_mutation(
        params=_mutation_params(confirmation_id=receipt["confirmation_id"]),
        request_id="request-mutation-valid-capacity",
        session_id="session-product",
    )

    assert denied_issue.ok is False
    assert cast(dict, denied_issue.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert issued.ok is True
    assert len(registry._p3_issue_operations) == 1
    assert denied_mutation.ok is False
    assert cast(dict, denied_mutation.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert mutated.ok is True
    assert len(registry._p3_mutation_operations) == 1
    assert len(composition.mutation_calls) == 1


@pytest.mark.asyncio
async def test_retained_p3_results_require_current_authority(
    tmp_path: Path,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issue_params = _mutation_params()
    issued = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-revoked",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])
    mutation_params = _mutation_params(confirmation_id=receipt["confirmation_id"])
    mutated = await registry.handle_p3_mutation(
        params=mutation_params,
        request_id="request-mutation-revoked",
        session_id="session-product",
    )

    composition.replay_authority_revoked = True
    denied_issue_replay = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-revoked",
        session_id="session-product",
    )
    denied_mutation_replay = await registry.handle_p3_mutation(
        params=mutation_params,
        request_id="request-mutation-revoked",
        session_id="session-product",
    )

    assert issued.ok is True
    assert mutated.ok is True
    assert denied_issue_replay.ok is False
    assert cast(dict, denied_issue_replay.payload["error"])["reason"] == (
        "TASK_CONTEXT_PERMISSION_MISSING"
    )
    assert denied_mutation_replay.ok is False
    assert cast(dict, denied_mutation_replay.payload["error"])["reason"] == (
        "TASK_CONTEXT_PERMISSION_MISSING"
    )
    assert len(composition.mutation_calls) == 1


@pytest.mark.asyncio
async def test_product_operation_capacity_recovers_with_fail_closed_old_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-capacity",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    first_params = _p2_params(
        commit_id="commit-capacity-1",
        turn_id="turn-capacity-1",
        response_id="response-capacity-1",
        committed_at=NOW,
        text="first capacity turn",
    )
    second_params = _p2_params(
        commit_id="commit-capacity-2",
        turn_id="turn-capacity-2",
        response_id="response-capacity-2",
        committed_at=NOW,
        text="second capacity turn",
    )
    first = await registry.handle_p2_submit(
        params=first_params,
        request_id="request-submit-capacity-1",
        session_id="session-product",
        channel_id="web",
    )
    second = await registry.handle_p2_submit(
        params=second_params,
        request_id="request-submit-capacity-2",
        session_id="session-product",
        channel_id="web",
    )
    expired = await registry.handle_p2_submit(
        params=first_params,
        request_id="request-submit-capacity-1",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is True
    assert second.ok is True
    assert expired.ok is False
    assert cast(dict, expired.payload["error"])["reason"] == (
        "PRODUCT_OPERATION_REPLAY_EXPIRED"
    )
    assert manager.agent.calls == 2


@pytest.mark.asyncio
async def test_notification_polls_require_exact_serial_sequence(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-notification-sequence",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    gap = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=2),
        request_id="request-notification-gap",
        session_id="session-product",
    )
    first_waiter = asyncio.create_task(
        registry.handle_p2_notification_next(
            params=_p2_params(notification_sequence=1),
            request_id="request-notification-sequence-1",
            session_id="session-product",
        )
    )
    for _ in range(20):
        if "request-notification-sequence-1" in registry._p2_notification_operations:
            break
        await asyncio.sleep(0)
    concurrent = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=2),
        request_id="request-notification-sequence-2",
        session_id="session-product",
    )
    reordered = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=1),
        request_id="request-notification-reordered",
        session_id="session-product",
    )

    assert gap.ok is False
    assert cast(dict, gap.payload["error"])["reason"] == (
        "PRODUCT_NOTIFICATION_SEQUENCE_MISMATCH"
    )
    assert concurrent.ok is False
    assert cast(dict, concurrent.payload["error"])["reason"] == (
        "PRODUCT_NOTIFICATION_POLL_PENDING"
    )
    assert reordered.ok is False
    assert cast(dict, reordered.payload["error"])["reason"] == (
        "PRODUCT_NOTIFICATION_SEQUENCE_MISMATCH"
    )
    assert len(registry._p2_notification_operations) == 1

    await registry.close_active_routes()
    await asyncio.wait_for(first_waiter, timeout=1)


@pytest.mark.asyncio
async def test_p2_activation_generation_never_resurrects_an_older_id(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    first_params = _p2_params(activation_id="activation-a", activation_generation=1)
    second_params = _p2_params(activation_id="activation-b", activation_generation=2)
    assert (
        await registry.handle_p2_activate(
            params=first_params,
            request_id="request-activate-a1",
            session_id="session-product",
            channel_id="web",
        )
    ).ok
    assert (
        await registry.handle_p2_close(
            params=first_params,
            request_id="request-close-a1",
            session_id="session-product",
        )
    ).ok
    assert (
        await registry.handle_p2_activate(
            params=second_params,
            request_id="request-activate-b2",
            session_id="session-product",
            channel_id="web",
        )
    ).ok
    assert (
        await registry.handle_p2_close(
            params=second_params,
            request_id="request-close-b2",
            session_id="session-product",
        )
    ).ok
    allocations_before = len(manager.get_calls)

    stale = await registry.handle_p2_activate(
        params=first_params,
        request_id="request-delayed-activate-a1",
        session_id="session-product",
        channel_id="web",
    )

    assert stale.ok is False
    assert cast(dict, stale.payload["error"])["reason"] == (
        "ACTIVATION_GENERATION_STALE"
    )
    assert len(manager.get_calls) == allocations_before
    assert registry._p2_routes == {}


@pytest.mark.asyncio
async def test_p2_generation_fence_survives_exact_tombstone_eviction(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    first_params: dict[str, object] | None = None
    for index in range(registry._CLOSED_ROUTE_CAPACITY + 1):
        params = _p2_params(
            correlation_id=f"correlation-capacity-{index}",
            interaction_id=f"interaction-capacity-{index}",
            activation_id=f"activation-capacity-{index}",
            activation_generation=1,
        )
        if first_params is None:
            first_params = params
        activated = await registry.handle_p2_activate(
            params=params,
            request_id=f"request-activate-capacity-{index}",
            session_id="session-product",
            channel_id="web",
        )
        closed = await registry.handle_p2_close(
            params=params,
            request_id=f"request-close-capacity-{index}",
            session_id="session-product",
        )
        assert activated.ok is True
        assert closed.ok is True

    assert first_params is not None
    assert (
        "session-product",
        "interaction-capacity-0",
    ) not in registry._closed_p2_routes
    allocations_before = len(manager.get_calls)
    stale = await registry.handle_p2_activate(
        params=first_params,
        request_id="request-delayed-after-tombstone-eviction",
        session_id="session-product",
        channel_id="web",
    )

    assert stale.ok is False
    assert cast(dict, stale.payload["error"])["reason"] == (
        "ACTIVATION_GENERATION_STALE"
    )
    assert len(manager.get_calls) == allocations_before


@pytest.mark.asyncio
async def test_p2_oversized_generation_allocates_nothing(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)

    result = await registry.handle_p2_activate(
        params=_p2_params(activation_generation=2**64),
        request_id="request-oversized-generation",
        session_id="session-product",
        channel_id="web",
    )

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert manager.get_calls == []


@pytest.mark.asyncio
async def test_p3_issue_preflight_cannot_admit_after_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original = composition.prepare_mutation_confirmation

    async def blocked_prepare(**kwargs: object) -> PreparedP3MutationConfirmation:
        entered.set()
        await release.wait()
        return await original(**kwargs)

    monkeypatch.setattr(composition, "prepare_mutation_confirmation", blocked_prepare)
    issue_task = asyncio.create_task(
        registry.handle_p3_confirmation_issue(
            params=_mutation_params(),
            request_id="request-issue-preflight-stop",
            session_id="session-product",
        )
    )
    await entered.wait()
    await registry.stop()
    release.set()
    result = await issue_task

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "PRODUCT_COMPOSITION_STOPPED"
    )
    assert registry._p3_issue_operations == {}
    assert composition.mutation_calls == []


@pytest.mark.asyncio
async def test_p3_mutation_preflight_cannot_admit_or_consume_after_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issued = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-mutation-preflight-issue",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])
    mutation_params = _mutation_params(confirmation_id=receipt["confirmation_id"])
    prepared = await composition.prepare_mutation_confirmation(
        operation="task.cancel",
        params=mutation_params,
        session_id="session-product",
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original = composition.prepare_mutation_confirmation

    async def blocked_prepare(**kwargs: object) -> PreparedP3MutationConfirmation:
        entered.set()
        await release.wait()
        return await original(**kwargs)

    monkeypatch.setattr(composition, "prepare_mutation_confirmation", blocked_prepare)
    mutation_task = asyncio.create_task(
        registry.handle_p3_mutation(
            params=mutation_params,
            request_id="request-mutation-preflight-stop",
            session_id="session-product",
        )
    )
    await entered.wait()
    await registry.stop()
    release.set()
    result = await mutation_task

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "PRODUCT_COMPOSITION_STOPPED"
    )
    assert registry._p3_mutation_operations == {}
    assert composition.mutation_calls == []
    owner.validate_for_forwarding(
        str(receipt["confirmation_id"]),
        prepared.binding,
        P3ConfirmationOwnerContext(
            session_id="session-product",
            correlation_id=prepared.correlation_id,
            owner_generation=registry._p3_confirmation_generation,
        ),
        now=prepared.observed_at,
    )
    assert registry._p2_routes == {}


@pytest.mark.asyncio
async def test_p2_oversized_notification_cursor_allocates_no_business_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("code", "normal"),
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-oversized-operation-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    notification = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=MAX_SAFE_INTEGER + 1),
        request_id="request-oversized-notification",
        session_id="session-product",
    )

    assert notification.ok is False
    assert cast(dict, notification.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert registry._p2_notification_operations == {}
    assert manager.agent.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_generation", "contiguous_cursor"),
    (
        (MAX_SAFE_INTEGER + 1, 1),
        (1, MAX_SAFE_INTEGER + 1),
    ),
)
async def test_p2_oversized_ack_cursor_allocates_no_business_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response_generation: int,
    contiguous_cursor: int,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("code", "normal"),
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-oversized-ack-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    history = _HistoryWriter()
    route = registry._p2_routes[("session-product", "interaction-1")]
    route.activation_lease._runtime._history_writer = history

    acknowledgement = await registry.handle_p2_presentation_ack(
        params=_p2_params(
            response_id="response-oversized",
            response_generation=response_generation,
            surface="text",
            unit_id="unit-oversized",
            contiguous_cursor=contiguous_cursor,
            presented_at=NOW,
        ),
        request_id="request-oversized-ack",
        session_id="session-product",
    )

    assert acknowledgement.ok is False
    assert cast(dict, acknowledgement.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert registry._p2_ack_operations == {}
    assert manager.agent.calls == 0
    assert history.users == []
    assert history.assistants == []


@pytest.mark.asyncio
async def test_p3_capacity_recovery_rejects_evicted_exact_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)
    issue_one_params = _mutation_params()
    issue_two_params = _mutation_params(
        command_id="command-cancel-2",
        correlation_id="correlation-cancel-2",
        task_id="task-2",
    )
    issue_one = await registry.handle_p3_confirmation_issue(
        params=issue_one_params,
        request_id="request-confirmation-capacity-1",
        session_id="session-product",
    )
    issue_two = await registry.handle_p3_confirmation_issue(
        params=issue_two_params,
        request_id="request-confirmation-capacity-2",
        session_id="session-product",
    )
    expired_issue = await registry.handle_p3_confirmation_issue(
        params=issue_one_params,
        request_id="request-confirmation-capacity-1",
        session_id="session-product",
    )
    receipt_one = cast(dict[str, object], issue_one.payload["result"])
    receipt_two = cast(dict[str, object], issue_two.payload["result"])
    mutation_one_params = _mutation_params(
        confirmation_id=receipt_one["confirmation_id"]
    )
    mutation_two_params = _mutation_params(
        command_id="command-cancel-2",
        correlation_id="correlation-cancel-2",
        task_id="task-2",
        confirmation_id=receipt_two["confirmation_id"],
    )
    mutation_one = await registry.handle_p3_mutation(
        params=mutation_one_params,
        request_id="request-mutation-capacity-1",
        session_id="session-product",
    )
    mutation_two = await registry.handle_p3_mutation(
        params=mutation_two_params,
        request_id="request-mutation-capacity-2",
        session_id="session-product",
    )
    expired_mutation = await registry.handle_p3_mutation(
        params=mutation_one_params,
        request_id="request-mutation-capacity-1",
        session_id="session-product",
    )

    assert issue_one.ok is True
    assert issue_two.ok is True
    assert expired_issue.ok is False
    assert cast(dict, expired_issue.payload["error"])["reason"] == (
        "PRODUCT_OPERATION_REPLAY_EXPIRED"
    )
    assert mutation_one.ok is True
    assert mutation_two.ok is True
    assert expired_mutation.ok is False
    assert cast(dict, expired_mutation.payload["error"])["reason"] == (
        "PRODUCT_OPERATION_REPLAY_EXPIRED"
    )
    assert len(composition.mutation_calls) == 2


@pytest.mark.asyncio
async def test_p3_conflict_is_not_revealed_before_reauthentication(
    tmp_path: Path,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issued = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-private-conflict",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])
    mutated = await registry.handle_p3_mutation(
        params=_mutation_params(confirmation_id=receipt["confirmation_id"]),
        request_id="request-private-mutation-conflict",
        session_id="session-product",
    )

    denied_issue = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(
            auth_token="invalid-token", command_id="changed-command"
        ),
        request_id="request-private-conflict",
        session_id="session-product",
    )
    denied_mutation = await registry.handle_p3_mutation(
        params=_mutation_params(
            auth_token="invalid-token",
            confirmation_id=receipt["confirmation_id"],
            task_id="changed-task",
        ),
        request_id="request-private-mutation-conflict",
        session_id="session-product",
    )

    assert issued.ok is True
    assert mutated.ok is True
    assert cast(dict, denied_issue.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert cast(dict, denied_mutation.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert len(composition.mutation_calls) == 1


@pytest.mark.asyncio
async def test_p3_product_mutation_preserves_formal_failure_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issued = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-confirmation-denied",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])

    async def deny_mutation(**_kwargs: object) -> P3RouteResult:
        return P3RouteResult(
            False,
            {
                "ok": False,
                "result": None,
                "error": {
                    "code": ErrorCode.PERMISSION_DENIED.value,
                    "reason": "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                    "message": "formal task authority changed",
                },
            },
        )

    monkeypatch.setattr(composition, "handle", deny_mutation)
    result = await registry.handle_p3_mutation(
        params=_mutation_params(confirmation_id=receipt["confirmation_id"]),
        request_id="request-mutation-denied",
        session_id="session-product",
    )

    assert result.ok is False
    assert result.payload["error"] == {
        "code": ErrorCode.PERMISSION_DENIED.value,
        "reason": "EXECUTION_CONTEXT_SCOPE_MISMATCH",
        "message": "formal task authority changed",
    }
    assert composition.mutation_calls == []


@pytest.mark.asyncio
async def test_p3_mutation_flag_off_has_zero_composition_effect(tmp_path: Path) -> None:
    composition = _P3Composition(tmp_path)
    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, False),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=cast(object, lambda _message: None),
    )

    result = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-confirmation-off",
        session_id="session-product",
    )

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "P3_CONFIRMATION_ISSUER_UNAVAILABLE"
    )
    assert composition.authority_calls == []
