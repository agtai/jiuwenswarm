# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping, NoReturn, cast

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContractViolation,
    ErrorCode,
    MAX_SAFE_INTEGER,
    OriginRef,
    ProducerRef,
    ResponseRef,
    ResultEnvelope,
    ScopeRef,
    TurnCommit,
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
from jiuwenswarm.server.live_voice.p2_response_generation_store import (
    SqliteP2ResponseGenerationOwner,
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
    PRODUCT_CRITICAL_INPUT_ENABLE_ENV,
    PRODUCT_P2_ENABLE_ENV,
    PRODUCT_P3_TEXT_ENABLE_ENV,
    ProductCompositionSettings,
    _ProgressDelivery,
    _VoiceTaskOrigin,
    create_product_composition_registry_from_environment,
)
from jiuwenswarm.server.live_voice.product_p3_text_adapter import (
    ProductP3AuthorizedQuery,
)
from jiuwenswarm.server.live_voice.task_event_subscription import (
    TaskEventSubscription,
)
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskProgressNotificationIntent,
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
    _evidence_id,
    project_task_progress_event,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import (
    VoiceTaskBridgeViolation,
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
    def __init__(self, *, formal_live_voice: bool = True) -> None:
        self.calls = 0
        self._formal_live_voice = formal_live_voice

    def supports_formal_live_voice(self) -> bool:
        return self._formal_live_voice

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
    """Honors the real profile contract instead of one always-capable facade.

    ``JiuWenSwarm.supports_formal_live_voice`` refuses an already bound Code
    adapter, so a Code-profile request can only return a facade without the
    formal Live Voice seam. A fake that reports the capability for every
    profile hides which profile the caller actually asked for.
    """

    def __init__(self) -> None:
        self.agent = _Facade()
        self.code_agent = _Facade(formal_live_voice=False)
        self.get_calls: list[tuple[object, ...]] = []
        self.pins = 0
        self.unpins = 0

    async def get_agent(self, *args):
        self.get_calls.append(args)
        mode = str(args[1]) if len(args) > 1 else "agent"
        return self.code_agent if mode == "code" else self.agent

    def pin_agent(self, agent) -> None:
        assert agent in (self.agent, self.code_agent)
        self.pins += 1

    def unpin_agent(self, agent) -> None:
        assert agent in (self.agent, self.code_agent)
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
        target = (
            str(params["task_id"])
            if operation in {"task.cancel", "task.retry"}
            else None
        )
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
        task_id = (
            "task-created-natural-1"
            if operation == "task.create"
            else params.get("task_id")
        )
        return P3RouteResult(
            True,
            {
                "request_id": request_id,
                "ok": True,
                "result": {
                    "accepted": True,
                    "operation": operation,
                    "task_id": task_id,
                },
                "error": None,
            },
        )


def _voice_mutation_registry(
    tmp_path: Path,
    *,
    commit_ledger: TurnCommitLedger,
) -> tuple[
    AgentServerProductCompositionRegistry,
    _MutationP3Composition,
    BoundedP3ConfirmationOwner,
]:
    owner = BoundedP3ConfirmationOwner(
        tmp_path / "voice-confirmations.sqlite3", enabled=True
    )
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=True,
            p3_text_enabled=False,
            p3_mutation_enabled=True,
        ),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commit_ledger,
    )
    return registry, composition, owner


def _registry(
    tmp_path: Path,
    *,
    p2: bool = True,
    p3: bool = True,
    push_success: bool = True,
    commit_ledger: TurnCommitLedger | None = None,
    critical_input: bool = False,
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
            critical_input_enabled=critical_input,
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


def _p2_task_origin_params(*, stem: str, text: str) -> dict[str, object]:
    commit_id = f"commit-{stem}"
    turn_id = f"turn-{stem}"
    return _p2_params(
        commit_id=commit_id,
        turn_id=turn_id,
        committed_at=NOW,
        text=text,
        dispatch_target="task",
        gateway_voice_claim={
            "kind": "formal_speech_recognition",
            "speech_operation_id": f"speech-operation-{stem}",
            "capture_id": f"capture-{stem}",
            "capture_generation": 1,
            "session_id": "session-product",
            "correlation_id": "correlation-p2",
            "interaction_id": "interaction-1",
            "turn_id": turn_id,
            "commit_id": commit_id,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "critical_policy": "eligible",
        },
    )


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

    class _Poison:
        def __getattribute__(self, _name):
            raise AssertionError("feature-off inspected P3 composition")

    result = create_product_composition_registry_from_environment(
        p3_composition=cast(P3AuthenticatedComposition, _Poison()),
        agent_manager=_Poison(),
        push_text_event=cast(object, _Poison()),
    )

    assert result is None


def test_critical_input_product_composition_flag_is_default_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PRODUCT_CRITICAL_INPUT_ENABLE_ENV, raising=False)
    assert ProductCompositionSettings.from_environment().critical_input_enabled is False
    monkeypatch.setenv(PRODUCT_CRITICAL_INPUT_ENABLE_ENV, "1")
    assert ProductCompositionSettings.from_environment().critical_input_enabled is True


@pytest.mark.asyncio
async def test_enabled_critical_gate_blocks_unconfirmed_voice_before_task_authority(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(
        tmp_path,
        commit_ledger=ledger,
        critical_input=True,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-critical-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    text = "create task 42 on feature/safe"
    blocked_params = _p2_task_origin_params(stem="critical-blocked", text=text)
    blocked = await registry.handle_p2_submit(
        params=blocked_params,
        request_id="request-critical-blocked",
        session_id="session-product",
        channel_id="web",
    )

    assert blocked.ok is False
    assert cast(dict, blocked.payload["error"])["reason"] == (
        "CRITICAL_TOKEN_CLARIFICATION_REQUIRED"
    )
    assert manager.agent.calls == 0
    assert registry._pending_turn_commits_by_commit == {}
    assert registry._accepted_turn_commits_by_commit == {}
    assert registry._unknown_turn_commits_by_commit == {}
    assert registry._critical_input_commit_generations == {}
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-critical-blocked",
                "commit-critical-blocked",
            ),
            SCOPE,
        )

    confirmed_params = _p2_task_origin_params(
        stem="critical-confirmed",
        text=text,
    )
    cast(dict[str, object], confirmed_params["gateway_voice_claim"])[
        "critical_policy"
    ] = "confirmed"
    confirmed = await registry.handle_p2_submit(
        params=confirmed_params,
        request_id="request-critical-confirmed",
        session_id="session-product",
        channel_id="web",
    )
    assert confirmed.ok is True
    assert "commit-critical-confirmed" in registry._accepted_turn_commits_by_commit
    await registry.stop()


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
async def test_p2_activation_requests_the_formal_live_voice_agent_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Code-mode Session must still activate P2 on the formal Agent profile.

    ``process_formal_live_voice_stream`` drives ``_ensure_adapter(mode="agent")``
    and ``supports_formal_live_voice`` refuses an already bound Code adapter, so
    asking for the Session's own work mode made every project-bound Code Session
    fail closed with ``P2_RUNTIME_UNAVAILABLE``. The route owns no Chat history
    and always runs an Agent-profile turn, so the work mode is not its input.
    """

    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata",
        lambda *_args, **_kwargs: {"mode": "code", "work_mode": "code"},
    )

    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-profile",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True, activated.payload
    assert _route(activated.payload, "p2.agent_interaction")["truth"] == "formal"
    assert len(manager.get_calls) == 1
    channel_id, mode, project_dir, sub_mode = manager.get_calls[0]
    assert (channel_id, mode, sub_mode) == (
        "live_voice_formal_p2",
        "agent",
        None,
    )
    assert Path(str(project_dir)) == tmp_path
    assert manager.pins == 1


@pytest.mark.asyncio
async def test_p2_activation_without_the_formal_seam_fails_closed(
    tmp_path: Path,
) -> None:
    """A facade that does not own the formal seam allocates nothing."""

    registry, _p3, manager, _pushed = _registry(tmp_path)
    manager.agent = _Facade(formal_live_voice=False)

    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-no-seam",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is False
    assert _route(activated.payload, "p2.agent_interaction")["reason_id"] == (
        "P2_RUNTIME_UNAVAILABLE"
    )
    assert len(manager.get_calls) == 1
    assert manager.pins == 0
    assert manager.unpins == 0

    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-no-seam-close",
        session_id="session-product",
    )
    assert closed.ok is False


@pytest.mark.asyncio
async def test_p2_authority_first_activation_replay_and_exact_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)

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
async def test_requested_voice_progress_without_exact_origin_is_explicit_text_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[dict[str, object]] = []

    def capture_log(_message: str, **kwargs: object) -> None:
        logged.append(cast(dict[str, object], kwargs["extra"]))

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.info",
        capture_log,
    )
    registry, p3, _manager, pushed = _registry(tmp_path)

    denied = await registry.handle_p3_progress_activate(
        params=_progress_params(auth_token="wrong-token", origin_kind="voice"),
        request_id="request-progress-voice-fallback-denied",
        session_id="session-product",
        channel_id="web",
    )
    assert denied.ok is False
    assert pushed == []
    assert not any(
        record.get("live_voice_event") == "task_progress_activation_fallback"
        for record in logged
    )

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(origin_kind="voice"),
        request_id="request-progress-voice-fallback",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert activated.ok is True
    result = cast(dict[str, object], activated.payload["result"])
    assert result["requested_origin_kind"] == "voice"
    assert result["origin_kind"] == "text"
    assert result["fallback_reason"] == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    assert result["voice_reason"] == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    assert len(p3.subscription_calls) == 1
    assert len(pushed) == 1
    payload = cast(dict[str, object], pushed[0]["payload"])
    assert payload["origin_kind"] == "voice"
    assert payload["requested_origin_kind"] == "voice"
    assert payload["effective_origin_kind"] == "text"
    assert payload["delivery_mode"] == "text_fallback"
    assert payload["fallback_reason"] == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    fallback = next(
        record
        for record in logged
        if record.get("live_voice_event") == "task_progress_activation_fallback"
    )
    assert fallback["reason"] == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    assert fallback["requested_origin_kind"] == "voice"
    assert fallback["effective_origin_kind"] == "text"
    await registry.stop()


@pytest.mark.asyncio
async def test_exact_voice_origin_is_visible_text_when_no_audible_consumer_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[dict[str, object]] = []

    def capture_log(_message: str, **kwargs: object) -> None:
        logged.append(cast(dict[str, object], kwargs["extra"]))

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.info",
        capture_log,
    )
    registry, _p3, _manager, pushed = _registry(tmp_path)
    activated_p2 = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-progress-voice-p2",
        session_id="session-product",
        channel_id="web",
    )
    assert activated_p2.ok is True
    retained = registry._p2_routes[("session-product", "interaction-1")]
    registry._voice_task_origins["task-1"] = _VoiceTaskOrigin(
        session_id="session-product",
        interaction_id="interaction-1",
        activation_id=retained.binding.activation_id,
        activation_generation=retained.binding.activation_generation,
        correlation_id=retained.binding.correlation_id,
        response_ref=ResponseRef("interaction-1", "response-origin-1", 0),
    )

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(
            origin_kind="voice",
            origin_id="interaction-1",
            correlation_id="correlation-p2",
        ),
        request_id="request-progress-voice-visible-fallback",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert activated.ok is True
    result = cast(dict[str, object], activated.payload["result"])
    assert result["requested_origin_kind"] == "voice"
    assert result["origin_kind"] == "text"
    assert result["fallback_reason"] == ("TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE")
    assert result["voice_progress"] == "unavailable"
    payload = cast(dict[str, object], pushed[-1]["payload"])
    assert payload["delivery_mode"] == "text_fallback"
    assert payload["fallback_reason"] == ("TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE")
    record = next(
        item
        for item in logged
        if item.get("live_voice_event") == "task_progress_activation_fallback"
        and item.get("reason") == "TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE"
    )
    assert record["effective_origin_kind"] == "text"
    await registry.stop()


@pytest.mark.asyncio
async def test_superseded_cr_voice_response_projects_visible_text_with_stable_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    logged: list[dict[str, object]] = []

    def capture_log(_message: str, **kwargs: object) -> None:
        logged.append(cast(dict[str, object], kwargs["extra"]))

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.info",
        capture_log,
    )
    binding = TaskProgressOriginBinding(
        scope=SCOPE,
        task_id="task-1",
        session_id="session-product",
        project_id="project-product",
        correlation_id="correlation-p2",
        origin_kind=TaskProgressOriginKind.VOICE,
        origin_id="interaction-1",
        generation_kind="web_task_progress_generation",
        generation_id="web-session-generation-superseded",
        generation=1,
        source_instance_id="task-core-superseded",
        progress_producer=ProducerRef(
            component="task_progress_return",
            instance_id="task-progress-return-superseded",
            authority="adapter",
        ),
        progress_adapter="task_progress_return.v1",
    )
    task_event = PersistentTaskEvent(
        event_id="event-superseded-0",
        task_id=binding.task_id,
        attempt_id="attempt-superseded-1",
        scope=SCOPE,
        seq=0,
        event_type="task.accepted",
        state="accepted",
        outcome=None,
        producer="task_core",
        source_event_id=None,
        causation_id="command-superseded-1",
        correlation_id=binding.correlation_id,
        occurred_at=NOW,
        details={},
    )
    projection = project_task_progress_event(task_event, binding)
    intent = TaskProgressNotificationIntent(
        origin=binding,
        task_event=task_event,
        source_event=projection.source_event,
        progress_event=projection.progress_event,
        decision=cast(object, None),
        evidence_id=_evidence_id(binding, task_event),
    )

    class _Superseded(RuntimeError):
        reason = "TASK_PROGRESS_RESPONSE_SUPERSEDED"

    class _Lease:
        async def deliver_task_progress(self, *_args: object) -> None:
            raise _Superseded("old response generation")

    registry._voice_task_origins[binding.task_id] = _VoiceTaskOrigin(
        session_id=binding.session_id,
        interaction_id=binding.origin_id,
        activation_id="activation-superseded",
        activation_generation=1,
        correlation_id=binding.correlation_id,
        response_ref=ResponseRef(binding.origin_id, "response-old", 0),
    )
    registry._p2_routes[(binding.session_id, binding.origin_id)] = cast(
        object,
        SimpleNamespace(
            binding=SimpleNamespace(
                activation_id="activation-superseded",
                activation_generation=1,
                scope=SCOPE,
            ),
            activation_lease=_Lease(),
        ),
    )
    registry._progress_targets[
        (
            binding.session_id,
            binding.task_id,
            binding.origin_id,
            binding.generation_id,
        )
    ] = cast(
        object,
        SimpleNamespace(
            channel_id="web",
            request_id="request-superseded-fallback",
            correlation_id=binding.correlation_id,
            generation=binding.generation,
            requested_origin_kind=TaskProgressOriginKind.VOICE,
            fallback_reason=None,
        ),
    )

    await registry._emit_voice_progress(intent)

    assert len(pushed) == 1
    payload = cast(dict[str, object], pushed[0]["payload"])
    assert payload["delivery_mode"] == "text_fallback"
    assert payload["fallback_reason"] == ("TASK_PROGRESS_VOICE_RESPONSE_SUPERSEDED")
    assert any(
        record.get("reason") == "TASK_PROGRESS_VOICE_RESPONSE_SUPERSEDED"
        for record in logged
    )


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
    forged_attempt = await registry.handle_p3_progress_ack(
        params={**_progress_ack_params(event), "attempt_id": "attempt-forged"},
        request_id="request-progress-ack-forged-attempt",
        session_id="session-product",
        channel_id="web",
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
    assert forged_attempt.ok is False
    assert cast(dict, forged_attempt.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert acknowledged.ok is True
    assert replayed.ok is True
    assert cast(dict, acknowledged.payload["result"])["replayed"] is False
    assert cast(dict, replayed.payload["result"])["replayed"] is True
    assert cast(dict, acknowledged.payload["result"])["attempt_id"] == "attempt-1"
    assert cast(dict, replayed.payload["result"])["attempt_id"] == "attempt-1"
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
    assert cast(dict, acknowledged.payload["result"])["attempt_id"] == "attempt-1"
    assert cast(dict, replayed.payload["result"])["attempt_id"] == "attempt-1"
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
            attempt_id="attempt-1",
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
        task_event=SimpleNamespace(attempt_id="attempt-1"),
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
    await asyncio.sleep(0)
    runtime_before_rejection = route.activation_lease._runtime.snapshot()
    rejected_ack_params = {
        **ack_params,
        "contiguous_cursor": MAX_SAFE_INTEGER,
    }
    rejected = await registry.handle_p2_presentation_ack(
        params=rejected_ack_params,
        request_id="request-ack-beyond-produced",
        session_id="session-product",
    )
    rejected_replay = await registry.handle_p2_presentation_ack(
        params=rejected_ack_params,
        request_id="request-ack-beyond-produced",
        session_id="session-product",
    )

    assert rejected.ok is False
    assert rejected_replay.payload == rejected.payload
    assert cast(dict, rejected.payload["error"])["code"] == "PROTOCOL_VIOLATION"
    assert cast(dict, rejected.payload["error"])["reason"] == (
        "ACK_BEYOND_PRODUCED_CURSOR"
    )
    assert route.activation_lease._runtime.snapshot() == runtime_before_rejection
    assert history.assistants == []
    assert tuple(registry._p2_ack_operations) == ("request-ack-beyond-produced",)

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
async def test_p2_accepts_voice_origin_only_after_exact_success(tmp_path: Path) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
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
    voice_origin_params = _p2_task_origin_params(stem="voice-origin", text=voice_text)
    submitted = await registry.handle_p2_submit(
        params=voice_origin_params,
        request_id="request-submit-voice-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert submitted.ok is True
    assert cast(dict, submitted.payload["result"])["status"] == ("task_origin_accepted")
    response = cast(dict, submitted.payload["result"])["response"]
    assert response["interaction_id"] == "interaction-1"
    assert cast(str, response["response_id"]).strip()
    assert response["response_generation"] == 0
    runtime = registry._p2_routes[
        ("session-product", "interaction-1")
    ].activation_lease._runtime
    response_records = runtime.snapshot().conversation.conversation.responses
    canonical = next(
        item
        for item in response_records
        if item.ref.response_id == response["response_id"]
    )
    assert canonical.ref.response_generation == response["response_generation"]
    assert canonical.state.value == "terminal"
    assert canonical.outcome.value == "completed"
    replayed = await registry.handle_p2_submit(
        params=voice_origin_params,
        request_id="request-submit-voice-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert replayed.payload == submitted.payload
    assert (
        sum(
            item.ref.response_id == response["response_id"]
            for item in runtime.snapshot().conversation.conversation.responses
        )
        == 1
    )
    accepted = ledger.require_origin(
        OriginRef("committed_turn", "turn-voice-origin", "commit-voice-origin"),
        SCOPE,
    )
    assert accepted.text == voice_text
    assert manager.agent.calls == 0

    agent_params = _p2_params(
        commit_id="commit-agent-chat",
        turn_id="turn-agent-chat",
        response_id="response-agent-chat",
        committed_at=NOW,
        text="answer this ordinary voice chat",
        dispatch_target="agent",
    )
    ordinary = await registry.handle_p2_submit(
        params=agent_params,
        request_id="request-submit-agent-chat",
        session_id="session-product",
        channel_id="web",
    )
    assert ordinary.ok is True
    ordinary_result = cast(dict[str, object], ordinary.payload["result"])
    assert ordinary_result["turn_id"] == "turn-agent-chat"
    assert ordinary_result["commit_id"] == "commit-agent-chat"
    ordinary_replay = await registry.handle_p2_submit(
        params=agent_params,
        request_id="request-submit-agent-chat",
        session_id="session-product",
        channel_id="web",
    )
    assert ordinary_replay.payload == ordinary.payload
    assert manager.agent.calls == 1
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef("committed_turn", "turn-agent-chat", "commit-agent-chat"),
            SCOPE,
        )
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_response_generation_continues_across_activation_successor(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    first_binding = _p2_params()
    first_activation = await registry.handle_p2_activate(
        params=first_binding,
        request_id="request-response-generation-activate-1",
        session_id="session-product",
        channel_id="web",
    )
    assert first_activation.ok is True
    first_submit = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-response-generation-1",
            turn_id="turn-response-generation-1",
            response_id="response-generation-1",
            committed_at=NOW,
            text="first activation response",
            dispatch_target="agent",
        ),
        request_id="request-response-generation-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    assert first_submit.ok is True
    first_response = cast(dict, first_submit.payload["result"])["response"]
    assert first_response["response_generation"] == 0

    first_close = await registry.handle_p2_close(
        params=first_binding,
        request_id="request-response-generation-close-1",
        session_id="session-product",
    )
    assert first_close.ok is True

    successor_binding = _p2_params(
        activation_id="activation-2",
        activation_generation=2,
    )
    successor_activation = await registry.handle_p2_activate(
        params=successor_binding,
        request_id="request-response-generation-activate-2",
        session_id="session-product",
        channel_id="web",
    )
    assert successor_activation.ok is True
    successor_submit_params = {
        **successor_binding,
        "commit_id": "commit-response-generation-2",
        "turn_id": "turn-response-generation-2",
        "response_id": "response-generation-2",
        "committed_at": NOW,
        "text": "successor activation response",
        "dispatch_target": "agent",
    }
    successor_submit = await registry.handle_p2_submit(
        params=successor_submit_params,
        request_id="request-response-generation-submit-2",
        session_id="session-product",
        channel_id="web",
    )
    assert successor_submit.ok is True
    successor_response = cast(dict, successor_submit.payload["result"])["response"]
    assert successor_response["response_generation"] == 1

    replayed = await registry.handle_p2_submit(
        params=successor_submit_params,
        request_id="request-response-generation-submit-2",
        session_id="session-product",
        channel_id="web",
    )
    assert replayed.payload == successor_submit.payload
    assert manager.agent.calls == 2
    assert registry._p2_response_generations[("session-product", "interaction-1")] == 1
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_response_generation_continues_across_registry_restart(
    tmp_path: Path,
) -> None:
    generation_database = tmp_path / "durable-response-generations.sqlite3"
    first, first_p3, _manager, _pushed = _registry(tmp_path)
    first_p3._p2_response_generation_owner = SqliteP2ResponseGenerationOwner(
        generation_database
    )
    first_binding = _p2_params()
    assert (
        await first.handle_p2_activate(
            params=first_binding,
            request_id="request-restart-generation-activate-1",
            session_id="session-product",
            channel_id="web",
        )
    ).ok is True
    first_submit = await first.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-restart-generation-1",
            turn_id="turn-restart-generation-1",
            response_id="response-restart-generation-1",
            committed_at=NOW,
            text="response before restart",
            dispatch_target="agent",
        ),
        request_id="request-restart-generation-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    assert first_submit.ok is True
    assert (
        cast(dict, first_submit.payload["result"])["response"]["response_generation"]
        == 0
    )
    await first.close_active_routes()

    restarted, restarted_p3, _manager, _pushed = _registry(tmp_path)
    restarted_p3._p2_response_generation_owner = SqliteP2ResponseGenerationOwner(
        generation_database
    )
    successor_binding = _p2_params(
        activation_id="activation-after-restart",
        activation_generation=2,
    )
    assert (
        await restarted.handle_p2_activate(
            params=successor_binding,
            request_id="request-restart-generation-activate-2",
            session_id="session-product",
            channel_id="web",
        )
    ).ok is True
    successor = await restarted.handle_p2_submit(
        params={
            **successor_binding,
            "commit_id": "commit-restart-generation-2",
            "turn_id": "turn-restart-generation-2",
            "response_id": "response-restart-generation-2",
            "committed_at": NOW,
            "text": "response after restart",
            "dispatch_target": "agent",
        },
        request_id="request-restart-generation-submit-2",
        session_id="session-product",
        channel_id="web",
    )
    assert successor.ok is True
    assert (
        cast(dict, successor.payload["result"])["response"]["response_generation"] == 1
    )
    await restarted.close_active_routes()


def test_durable_p2_response_generation_owner_keeps_memory_exact_set_bounded(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, _pushed = _registry(tmp_path)
    p3._p2_response_generation_owner = SqliteP2ResponseGenerationOwner(
        tmp_path / "bounded-durable-response-generations.sqlite3"
    )
    first_key = ("session-product", "interaction-durable-0")
    assert registry._next_p2_response_generation(first_key, -1) == 0
    for index in range(1, registry._P2_RESPONSE_GENERATION_CAPACITY + 1):
        registry._next_p2_response_generation(
            ("session-product", f"interaction-durable-{index}"),
            -1,
        )

    assert len(registry._p2_response_generations) == (
        registry._P2_RESPONSE_GENERATION_CAPACITY
    )
    assert first_key not in registry._p2_response_generations
    assert registry._next_p2_response_generation(first_key, -1) >= 1


def test_p2_response_generation_fence_survives_exact_high_water_eviction(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    first_key = ("session-product", "interaction-generation-0")
    assert registry._next_p2_response_generation(first_key, -1) == 0
    for index in range(1, registry._P2_RESPONSE_GENERATION_CAPACITY + 1):
        assert (
            registry._next_p2_response_generation(
                ("session-product", f"interaction-generation-{index}"), -1
            )
            == 0
        )

    assert first_key not in registry._p2_response_generations
    assert registry._next_p2_response_generation(first_key, -1) >= 1


def test_p2_response_generation_owner_serializes_concurrent_allocations(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    key = ("session-product", "interaction-concurrent-generation")
    worker_count = 32
    barrier = threading.Barrier(worker_count)

    def allocate() -> int:
        barrier.wait(timeout=5)
        return registry._next_p2_response_generation(key, -1)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        generations = list(executor.map(lambda _index: allocate(), range(worker_count)))

    assert sorted(generations) == list(range(worker_count))
    assert registry._p2_response_generations[key] == worker_count - 1


def test_p2_response_generation_exhaustion_preserves_owner_state(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    key = ("session-product", "interaction-exhausted-generation")
    registry._p2_response_generations[key] = MAX_SAFE_INTEGER
    exact_before = dict(registry._p2_response_generations)
    fence_before = tuple(
        row.tobytes() for row in registry._p2_response_generation_fence
    )

    with pytest.raises(FormalTaskViolation, match="generation is exhausted") as caught:
        registry._next_p2_response_generation(key, MAX_SAFE_INTEGER - 1)

    assert caught.value.reason == "RESPONSE_GENERATION_EXHAUSTED"
    assert registry._p2_response_generations == exact_before
    assert (
        tuple(row.tobytes() for row in registry._p2_response_generation_fence)
        == fence_before
    )


@pytest.mark.asyncio
async def test_p2_task_origin_caller_cancellation_retains_exact_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-cancel",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    original_accept = route.activation_lease.accept_task_origin
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_accept(*args: object, **kwargs: object):
        entered.set()
        await release.wait()
        return await original_accept(*args, **kwargs)

    monkeypatch.setattr(route.activation_lease, "accept_task_origin", blocked_accept)
    text = "retain the exact voice task origin"
    params = _p2_task_origin_params(stem="task-origin-cancel", text=text)
    caller = asyncio.create_task(
        registry.handle_p2_submit(
            params=params,
            request_id="request-submit-task-origin-cancel",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    release.set()
    retained = registry._p2_submit_operations["request-submit-task-origin-cancel"]
    first = await asyncio.wait_for(asyncio.shield(retained.task), timeout=1)
    replayed = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-cancel",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is True
    assert replayed.payload == first.payload
    assert manager.agent.calls == 0
    assert (
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-task-origin-cancel",
                "commit-task-origin-cancel",
            ),
            SCOPE,
        ).text
        == text
    )
    runtime = route.activation_lease._runtime
    response_id = cast(dict, first.payload["result"])["response"]["response_id"]
    assert (
        sum(
            item.ref.response_id == response_id
            for item in runtime.snapshot().conversation.conversation.responses
        )
        == 1
    )
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_task_origin_canonical_accept_wins_concurrent_route_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-close-race",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    runtime = route.activation_lease._runtime
    original_accept = runtime.accept_task_origin
    canonical_accepted = asyncio.Event()
    release = asyncio.Event()

    async def blocked_after_canonical_accept(**kwargs: object):
        response_ref = await original_accept(**kwargs)
        canonical_accepted.set()
        await release.wait()
        return response_ref

    monkeypatch.setattr(runtime, "accept_task_origin", blocked_after_canonical_accept)
    text = "canonical acceptance must win the close race"
    params = _p2_task_origin_params(stem="task-origin-close-race", text=text)
    submit = asyncio.create_task(
        registry.handle_p2_submit(
            params=params,
            request_id="request-submit-task-origin-close-race",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.wait_for(canonical_accepted.wait(), timeout=1)
    close = asyncio.create_task(
        registry.handle_p2_close(
            params=_p2_params(),
            request_id="request-close-task-origin-close-race",
            session_id="session-product",
        )
    )

    async def wait_for_closing() -> None:
        while route.activation_lease.snapshot().state.value != "closing":
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_closing(), timeout=1)
    release.set()
    submitted, closed = await asyncio.gather(submit, close)
    replayed = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-close-race",
        session_id="session-product",
        channel_id="web",
    )

    assert submitted.ok is True
    assert cast(dict, submitted.payload["result"])["status"] == ("task_origin_accepted")
    assert closed.ok is True
    assert replayed.payload == submitted.payload
    assert manager.agent.calls == 0
    assert "commit-task-origin-close-race" in (
        registry._accepted_turn_commits_by_commit
    )
    assert (
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-task-origin-close-race",
                "commit-task-origin-close-race",
            ),
            SCOPE,
        ).text
        == text
    )


@pytest.mark.asyncio
async def test_closed_p2_voice_origin_is_consumed_once_by_exact_p3_create(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-closed-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    text = "create exactly one task after the P2 route closes"
    origin_params = _p2_task_origin_params(stem="closed-origin", text=text)
    accepted = await registry.handle_p2_submit(
        params=origin_params,
        request_id="request-submit-closed-origin",
        session_id="session-product",
        channel_id="web",
    )
    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-close-closed-origin",
        session_id="session-product",
    )
    replayed_origin = await registry.handle_p2_submit(
        params=origin_params,
        request_id="request-submit-closed-origin",
        session_id="session-product",
        channel_id="web",
    )
    create = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.create",
        "command_id": "command-create-closed-origin",
        "issued_at": NOW,
        "correlation_id": "correlation-create-closed-origin",
        "name": "Closed origin task",
        "instruction": text,
        "source": "voice",
        "interaction_id": "interaction-1",
        "turn_id": "turn-closed-origin",
        "commit_id": "commit-closed-origin",
    }
    issued = await registry.handle_p3_confirmation_issue(
        params=create,
        request_id="request-issue-closed-origin",
        session_id="session-product",
    )
    assert accepted.ok is True
    assert closed.ok is True
    assert replayed_origin.payload == accepted.payload
    assert issued.ok is True
    receipt = cast(dict[str, object], issued.payload["result"])
    mutation = {**create, "confirmation_id": receipt["confirmation_id"]}
    created = await registry.handle_p3_mutation(
        params=mutation,
        request_id="request-mutate-closed-origin",
        session_id="session-product",
    )
    replayed_create = await registry.handle_p3_mutation(
        params=mutation,
        request_id="request-mutate-closed-origin",
        session_id="session-product",
    )
    duplicate = await registry.handle_p3_confirmation_issue(
        params={**create, "command_id": "command-create-closed-origin-duplicate"},
        request_id="request-issue-closed-origin-duplicate",
        session_id="session-product",
    )
    foreign = await registry.handle_p3_confirmation_issue(
        params={
            **create,
            "command_id": "command-create-closed-origin-foreign",
            "interaction_id": "interaction-foreign",
        },
        request_id="request-issue-closed-origin-foreign",
        session_id="session-product",
    )

    assert created.ok is True
    assert replayed_create.payload == created.payload
    assert duplicate.ok is False
    assert foreign.ok is False
    assert len(composition.mutation_calls) == 1
    await registry.stop()
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-closed-origin",
                "commit-closed-origin",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_concurrent_p3_creates_reserve_one_exact_voice_origin(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-concurrent-create",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    text = "create one task despite concurrent requests"
    accepted = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem="concurrent-create", text=text),
        request_id="request-submit-concurrent-create",
        session_id="session-product",
        channel_id="web",
    )
    assert accepted.ok is True
    create = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.create",
        "issued_at": NOW,
        "correlation_id": "correlation-concurrent-create",
        "name": "Concurrent origin task",
        "instruction": text,
        "source": "voice",
        "interaction_id": "interaction-1",
        "turn_id": "turn-concurrent-create",
        "commit_id": "commit-concurrent-create",
    }
    first_issue = await registry.handle_p3_confirmation_issue(
        params={**create, "command_id": "command-concurrent-create-a"},
        request_id="request-issue-concurrent-create-a",
        session_id="session-product",
    )
    second_issue = await registry.handle_p3_confirmation_issue(
        params={**create, "command_id": "command-concurrent-create-b"},
        request_id="request-issue-concurrent-create-b",
        session_id="session-product",
    )
    assert first_issue.ok is True
    assert second_issue.ok is True
    first_receipt = cast(dict[str, object], first_issue.payload["result"])
    second_receipt = cast(dict[str, object], second_issue.payload["result"])

    first, second = await asyncio.gather(
        registry.handle_p3_mutation(
            params={
                **create,
                "command_id": "command-concurrent-create-a",
                "confirmation_id": first_receipt["confirmation_id"],
            },
            request_id="request-mutate-concurrent-create-a",
            session_id="session-product",
        ),
        registry.handle_p3_mutation(
            params={
                **create,
                "command_id": "command-concurrent-create-b",
                "confirmation_id": second_receipt["confirmation_id"],
            },
            request_id="request-mutate-concurrent-create-b",
            session_id="session-product",
        ),
    )

    assert sum(result.ok for result in (first, second)) == 1
    assert len(composition.mutation_calls) == 1
    rejected = second if first.ok else first
    assert cast(dict, rejected.payload["error"])["code"] == (
        ErrorCode.PERMISSION_DENIED.value
    )
    await registry.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_mode", ["failed", "cancelled"])
async def test_failed_voice_create_eviction_retires_exact_reserved_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_mode: str,
) -> None:
    ledger = TurnCommitLedger(capacity=1)
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    monkeypatch.setattr(registry, "_TURN_COMMIT_CAPACITY", 1)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id=f"request-activate-create-{terminal_mode}",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    text = f"retire {terminal_mode} voice create without leaking capacity"
    origin = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem=f"create-{terminal_mode}", text=text),
        request_id=f"request-submit-create-{terminal_mode}",
        session_id="session-product",
        channel_id="web",
    )
    assert origin.ok is True
    create = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.create",
        "command_id": f"command-create-{terminal_mode}",
        "issued_at": NOW,
        "correlation_id": f"correlation-create-{terminal_mode}",
        "name": f"{terminal_mode} task",
        "instruction": text,
        "source": "voice",
        "interaction_id": "interaction-1",
        "turn_id": f"turn-create-{terminal_mode}",
        "commit_id": f"commit-create-{terminal_mode}",
    }
    issued = await registry.handle_p3_confirmation_issue(
        params=create,
        request_id=f"request-issue-create-{terminal_mode}",
        session_id="session-product",
    )
    assert issued.ok is True
    receipt = cast(dict[str, object], issued.payload["result"])
    mutation_request_id = f"request-mutate-create-{terminal_mode}"

    async def terminal_handle(**_kwargs: object) -> P3RouteResult:
        if terminal_mode == "cancelled":
            raise asyncio.CancelledError
        return P3RouteResult(
            False,
            {
                "request_id": mutation_request_id,
                "ok": False,
                "result": None,
                "error": {
                    "code": ErrorCode.UNAVAILABLE.value,
                    "reason": "INJECTED_CREATE_FAILURE",
                    "message": "injected create failure",
                },
            },
        )

    monkeypatch.setattr(composition, "handle", terminal_handle)
    mutation = registry.handle_p3_mutation(
        params={**create, "confirmation_id": receipt["confirmation_id"]},
        request_id=mutation_request_id,
        session_id="session-product",
    )
    if terminal_mode == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await mutation
    else:
        failed = await mutation
        assert failed.ok is False

    assert (
        registry._reserved_voice_origin_requests[f"commit-create-{terminal_mode}"]
        == mutation_request_id
    )
    async with registry._lock:
        assert (
            registry._evict_completed_product_operation(
                registry._p3_mutation_operations,
                namespace="p3.mutate",
            )
            is True
        )

    assert registry._reserved_voice_origin_requests == {}
    assert registry._accepted_turn_commits_by_commit == {}
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                f"turn-create-{terminal_mode}",
                f"commit-create-{terminal_mode}",
            ),
            SCOPE,
        )
    retired = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem=f"create-{terminal_mode}", text=text),
        request_id=f"request-submit-create-{terminal_mode}-duplicate",
        session_id="session-product",
        channel_id="web",
    )
    assert retired.ok is False
    assert cast(dict, retired.payload["error"])["reason"] == "TURN_COMMIT_RETIRED"

    fresh = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem=f"create-{terminal_mode}-fresh",
            text="fresh voice origin proves bounded capacity was released",
        ),
        request_id=f"request-submit-create-{terminal_mode}-fresh",
        session_id="session-product",
        channel_id="web",
    )
    assert fresh.ok is True
    await registry.stop()


@pytest.mark.asyncio
async def test_p2_task_origin_partial_cr_failure_is_stable_result_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-unknown",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    runtime = route.activation_lease._runtime

    async def fail_terminal_transition(*_args: object, **_kwargs: object):
        raise RuntimeError("injected transition loss")

    monkeypatch.setattr(runtime._cr, "transition_response", fail_terminal_transition)
    text = "retain unknown after partial canonical write"
    params = _p2_task_origin_params(stem="task-origin-unknown", text=text)
    first = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-unknown",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-unknown",
        session_id="session-product",
        channel_id="web",
    )
    second_request = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-unknown-second",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is False
    assert cast(dict, first.payload["error"])["code"] == (
        ErrorCode.RESULT_UNKNOWN.value
    )
    assert replayed.payload == first.payload
    assert second_request.ok is False
    assert cast(dict, second_request.payload["error"])["reason"] == (
        "TURN_COMMIT_ALREADY_SUBMITTED"
    )
    assert manager.agent.calls == 0
    assert (
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-task-origin-unknown",
                "commit-task-origin-unknown",
            ),
            SCOPE,
        ).text
        == text
    )
    assert (
        registry._unknown_turn_commits_by_commit["commit-task-origin-unknown"].turn_id
        == "turn-task-origin-unknown"
    )
    assert len(runtime.snapshot().conversation.conversation.responses) == 1
    await registry.stop()
    assert registry._unknown_turn_commits_by_commit == {}
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-task-origin-unknown",
                "commit-task-origin-unknown",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_p2_task_origin_unknown_eviction_retires_identity_and_frees_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = TurnCommitLedger(capacity=2)
    registry, _p3, _manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    monkeypatch.setattr(registry, "_TURN_COMMIT_CAPACITY", 2)
    monkeypatch.setattr(registry, "_TURN_COMMIT_CAPACITY_PER_ROUTE", 1)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-unknown-eviction",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    runtime = registry._p2_routes[
        ("session-product", "interaction-1")
    ].activation_lease._runtime
    original_transition = runtime._cr.transition_response

    async def fail_terminal_transition(*_args: object, **_kwargs: object):
        raise RuntimeError("injected transition loss")

    monkeypatch.setattr(runtime._cr, "transition_response", fail_terminal_transition)
    text = "retire an unknown canonical response without reopening it"
    params = _p2_task_origin_params(stem="unknown-eviction", text=text)
    unknown = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-unknown-eviction",
        session_id="session-product",
        channel_id="web",
    )
    assert unknown.ok is False
    assert cast(dict, unknown.payload["error"])["code"] == (
        ErrorCode.RESULT_UNKNOWN.value
    )
    assert (
        registry._unknown_turn_commits_by_commit["commit-unknown-eviction"].turn_id
        == "turn-unknown-eviction"
    )
    monkeypatch.setattr(runtime._cr, "transition_response", original_transition)
    fresh = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem="unknown-eviction-fresh",
            text="fresh origin after bounded unknown eviction",
        ),
        request_id="request-submit-unknown-eviction-fresh",
        session_id="session-product",
        channel_id="web",
    )
    assert fresh.ok is True
    assert registry._unknown_turn_commits_by_commit == {}
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-unknown-eviction",
                "commit-unknown-eviction",
            ),
            SCOPE,
        )
    retired = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-unknown-eviction-retry",
        session_id="session-product",
        channel_id="web",
    )
    assert retired.ok is False
    assert cast(dict, retired.payload["error"])["reason"] == "TURN_COMMIT_RETIRED"
    await registry.stop()


@pytest.mark.asyncio
async def test_p2_task_origin_reconciles_terminal_write_before_response_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-terminal-loss",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    runtime = route.activation_lease._runtime
    original_transition = runtime._cr.transition_response

    async def mutate_then_lose(*args: object, **kwargs: object):
        await original_transition(*args, **kwargs)
        raise RuntimeError("response lost after canonical terminal write")

    monkeypatch.setattr(runtime._cr, "transition_response", mutate_then_lose)
    params = _p2_task_origin_params(
        stem="task-origin-terminal-loss",
        text="recover the exact terminal task origin",
    )
    first = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-terminal-loss",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-terminal-loss",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is True
    assert replayed.payload == first.payload
    response = cast(dict, first.payload["result"])["response"]
    canonical = next(
        item
        for item in runtime.snapshot().conversation.conversation.responses
        if item.ref.response_id == response["response_id"]
    )
    assert canonical.turn_id == "turn-task-origin-terminal-loss"
    assert canonical.state.value == "terminal"
    assert canonical.outcome.value == "completed"
    assert manager.agent.calls == 0


@pytest.mark.asyncio
async def test_p2_task_origin_rejects_client_declared_canonical_response_id(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-client-response",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    rejected = await registry.handle_p2_submit(
        params={
            **_p2_task_origin_params(
                stem="task-origin-client-response",
                text="do not trust a browser response identity",
            ),
            "response_id": "response-browser-declared",
        },
        request_id="request-submit-task-origin-client-response",
        session_id="session-product",
        channel_id="web",
    )

    assert rejected.ok is False
    assert cast(dict, rejected.payload["error"])["code"] == (
        ErrorCode.INVALID_ARGUMENT.value
    )
    assert registry._p2_submit_operations == {}
    assert manager.agent.calls == 0


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
    assert not {"response.cancel", "round.cancel", "task.cancel"} & set(effect_types)

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


def _text_intent_params(
    *, stem: str, text: str, operation: str, task_id: str | None = None
) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": f"correlation-{stem}",
        "source": "text",
        "operation_hint": operation,
        "interaction_id": "chat-task-intent-1",
        "turn_id": f"turn-{stem}",
        "commit_id": f"commit-{stem}",
        "committed_at": NOW,
        "text": text,
    }
    if task_id is not None:
        params["task_id_hint"] = task_id
    return params


def _voice_intent_params(
    *, stem: str, operation: str, task_id: str | None = None
) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": "correlation-p2",
        "source": "voice",
        "operation_hint": operation,
        "interaction_id": "interaction-1",
        "turn_id": f"turn-{stem}",
        "commit_id": f"commit-{stem}",
    }
    if task_id is not None:
        params["task_id_hint"] = task_id
    return params


@pytest.mark.asyncio
async def test_voice_intent_create_uses_two_exact_p2_commits_and_retains_live_progress_origin(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-natural-voice-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    first_text = "create task: inspect the repository"
    first_commit = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem="natural-voice", text=first_text),
        request_id="request-natural-voice-commit",
        session_id="session-product",
        channel_id="web",
    )
    assert first_commit.ok is True
    first = await registry.handle_p3_intent(
        params=_voice_intent_params(
            stem="natural-voice",
            operation="task.create",
        ),
        request_id="request-natural-voice-intent",
        session_id="session-product",
    )
    assert first.ok is True, first.payload
    first_result = cast(dict[str, object], first.payload["result"])
    assert first_result["status"] == "clarification"
    token = cast(str, first_result["confirmation_token"])
    assert composition.mutation_calls == []

    confirmation_text = f"confirm task request {token}"
    confirmation_commit = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem="natural-voice-confirm",
            text=confirmation_text,
        ),
        request_id="request-natural-voice-confirm-commit",
        session_id="session-product",
        channel_id="web",
    )
    assert confirmation_commit.ok is True
    confirmed = await registry.handle_p3_intent(
        params=_voice_intent_params(
            stem="natural-voice-confirm",
            operation="task.create",
        ),
        request_id="request-natural-voice-confirm-intent",
        session_id="session-product",
    )

    assert confirmed.ok is True, confirmed.payload
    result = cast(dict[str, object], confirmed.payload["result"])
    assert result["status"] == "dispatched"
    assert result["task_id"] == "task-created-natural-1"
    assert result["origin_kind"] == "voice"
    assert result["origin_id"] == "interaction-1"
    assert result["confirmation_commit_id"] == "commit-natural-voice-confirm"
    assert len(composition.mutation_calls) == 1
    assert registry._voice_task_origins["task-created-natural-1"].interaction_id == (
        "interaction-1"
    )
    assert registry._voice_task_origins["task-created-natural-1"].correlation_id == (
        "correlation-p2"
    )
    assert (
        registry._voice_task_origins[
            "task-created-natural-1"
        ].response_ref.interaction_id
        == "interaction-1"
    )
    await registry.stop()


@pytest.mark.asyncio
async def test_voice_pending_confirmation_is_released_when_exact_route_closes(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-pending-close-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    sentinel = "create task: SENTINEL_PENDING_VOICE_TEXT"
    committed = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem="pending-close", text=sentinel),
        request_id="request-pending-close-commit",
        session_id="session-product",
        channel_id="web",
    )
    assert committed.ok is True
    pending = await registry.handle_p3_intent(
        params=_voice_intent_params(
            stem="pending-close",
            operation="task.create",
        ),
        request_id="request-pending-close-intent",
        session_id="session-product",
    )
    token = cast(dict[str, object], pending.payload["result"])["confirmation_token"]
    assert token in registry._pending_task_intents
    assert (
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-pending-close",
                "commit-pending-close",
            ),
            SCOPE,
        ).text
        == sentinel
    )

    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-pending-close-route",
        session_id="session-product",
    )
    replayed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-pending-close-route-replay",
        session_id="session-product",
    )
    registry._drop_voice_task_origins_for_route_locked(
        ("session-foreign", "interaction-foreign")
    )

    assert closed.ok is True
    assert replayed.ok is True
    assert registry._pending_task_intents == {}
    assert "commit-pending-close" not in registry._accepted_turn_commits_by_commit
    assert "commit-pending-close" not in registry._accepted_voice_commit_routes
    assert sentinel not in repr(registry._pending_task_intents)
    assert composition.mutation_calls == []
    with pytest.raises(ContractViolation):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-pending-close",
                "commit-pending-close",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_voice_intent_obtain_then_close_race_releases_unstored_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-obtain-close-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    committed = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem="obtain-close",
            text="create task: bounded race request",
        ),
        request_id="request-obtain-close-commit",
        session_id="session-product",
        channel_id="web",
    )
    assert committed.ok is True
    original_obtain = registry._obtain_task_intent_commit
    obtained = asyncio.Event()
    release = asyncio.Event()

    async def blocked_obtain(**kwargs: object) -> TurnCommit:
        commit = await original_obtain(**kwargs)
        obtained.set()
        await release.wait()
        return commit

    monkeypatch.setattr(registry, "_obtain_task_intent_commit", blocked_obtain)
    intent = asyncio.create_task(
        registry.handle_p3_intent(
            params=_voice_intent_params(
                stem="obtain-close",
                operation="task.create",
            ),
            request_id="request-obtain-close-intent",
            session_id="session-product",
        )
    )
    await asyncio.wait_for(obtained.wait(), timeout=1)
    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-obtain-close-route",
        session_id="session-product",
    )
    release.set()
    rejected = await asyncio.wait_for(intent, timeout=1)

    assert closed.ok is True
    assert rejected.ok is False
    assert cast(dict, rejected.payload["error"])["reason"] == (
        "VOICE_TASK_ROUTE_MISMATCH"
    )
    assert registry._pending_task_intents == {}
    assert "commit-obtain-close" not in registry._accepted_turn_commits_by_commit
    assert "commit-obtain-close" not in registry._accepted_voice_commit_routes
    assert composition.mutation_calls == []
    with pytest.raises(ContractViolation):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-obtain-close",
                "commit-obtain-close",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_text_intent_create_requires_later_exact_committed_confirmation(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-create",
            text="create task: inspect the repository",
            operation="task.create",
        ),
        request_id="request-natural-create",
        session_id="session-product",
    )

    assert first.ok is True, first.payload
    clarification = cast(dict[str, object], first.payload["result"])
    assert clarification["status"] == "clarification"
    token = cast(str, clarification["confirmation_token"])
    assert len(token) == 32
    assert composition.prepare_calls == []
    assert composition.mutation_calls == []

    confirmed = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-create-confirm",
            text=f"confirm task request {token}",
            operation="task.create",
        ),
        request_id="request-natural-create-confirm",
        session_id="session-product",
    )

    assert confirmed.ok is True, confirmed.payload
    result = cast(dict[str, object], confirmed.payload["result"])
    assert result["status"] == "dispatched"
    assert result["confirmation_commit_id"] == "commit-natural-create-confirm"
    assert len(composition.mutation_calls) == 1
    operation, forwarded = composition.mutation_calls[0]
    assert operation == "task.create"
    assert forwarded["instruction"] == "inspect the repository"
    assert forwarded["commit_id"] == "commit-natural-create"
    assert forwarded["origin_commit_sha256"] == clarification["commit_sha256"]
    assert registry._pending_task_intents == {}


@pytest.mark.asyncio
async def test_completed_text_intent_recovers_content_free_without_replaying_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    secret_instruction = "inspect SENTINEL_PROVIDER_SECRET without retaining this text"
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-recovery",
            text=f"create task: {secret_instruction}",
            operation="task.create",
        ),
        request_id="request-natural-recovery",
        session_id="session-product",
    )
    token = cast(dict[str, object], first.payload["result"])["confirmation_token"]
    confirmed_request_id = "request-natural-recovery-confirm"
    confirmed = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-recovery-confirm",
            text=f"confirm task request {token}",
            operation="task.create",
        ),
        request_id=confirmed_request_id,
        session_id="session-product",
    )
    assert confirmed.ok is True
    assert len(composition.mutation_calls) == 1

    status_params = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": "correlation-natural-recovery-confirm",
        "intent_request_id": confirmed_request_id,
    }
    recovered = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-recovery-status",
        session_id="session-product",
    )
    replayed = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-recovery-status-replay",
        session_id="session-product",
    )

    assert recovered.ok is True, recovered.payload
    assert replayed.ok is True, replayed.payload
    assert recovered.payload["result"] == replayed.payload["result"]
    assert cast(dict, recovered.payload["result"])["status"] == "settled"
    assert cast(dict, recovered.payload["result"])["phase"] == "final"
    recovered_wire = repr(recovered.payload)
    assert secret_instruction not in recovered_wire
    assert "SENTINEL_PROVIDER_SECRET" not in recovered_wire
    assert "confirm task request" not in recovered_wire
    intent = cast(dict[str, object], cast(dict, recovered.payload["result"])["intent"])
    assert intent["status"] == "dispatched"
    assert intent["formal_task_result"] == {
        "recovered": True,
        "task_id": "task-created-natural-1",
    }
    assert len(composition.mutation_calls) == 1

    wrong_scope = await registry.handle_p3_intent_status(
        params={**status_params, "correlation_id": "correlation-foreign"},
        request_id="request-natural-recovery-wrong-scope",
        session_id="session-product",
    )
    unknown = await registry.handle_p3_intent_status(
        params={**status_params, "intent_request_id": "request-unknown"},
        request_id="request-natural-recovery-unknown",
        session_id="session-product",
    )
    assert wrong_scope.ok is False
    assert unknown.ok is False
    assert len(composition.mutation_calls) == 1

    exception_canary = "SENTINEL_RECOVERY_AUTHORITY_SECRET"

    async def fail_authority(**_kwargs: object) -> NoReturn:
        raise RuntimeError(exception_canary)

    monkeypatch.setattr(registry, "_preauthorize_task_intent", fail_authority)
    failed = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-recovery-authority-failed",
        session_id="session-product",
    )
    assert failed.ok is False
    assert failed.payload["error"] == {
        "reason": "TASK_INTENT_RECOVERY_FAILED",
        "code": ErrorCode.UNAVAILABLE.value,
        "message": "task intent recovery failed closed",
    }
    assert exception_canary not in repr(failed.payload)
    assert len(composition.mutation_calls) == 1


@pytest.mark.asyncio
async def test_pending_intent_status_recovers_exact_phase_then_expires_without_mutation(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    request_id = "request-natural-pending-status"
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-pending-status",
            text="create task: bounded pending status",
            operation="task.create",
        ),
        request_id=request_id,
        session_id="session-product",
    )
    first_result = cast(dict[str, object], first.payload["result"])
    token = cast(str, first_result["confirmation_token"])
    status_params = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": "correlation-natural-pending-status",
        "intent_request_id": request_id,
    }

    pending = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-pending-status-query",
        session_id="session-product",
    )
    replayed = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-pending-status-replay",
        session_id="session-product",
    )
    assert pending.ok is True and replayed.ok is True
    pending_result = cast(dict[str, object], pending.payload["result"])
    assert pending_result["status"] == "pending"
    assert pending_result["phase"] == "awaiting_confirmation"
    assert cast(dict, pending_result["intent"])["confirmation_token"] == token
    assert pending_result == replayed.payload["result"]
    assert composition.mutation_calls == []

    assert registry._evict_oldest_pending_task_intent_locked() is True
    expired = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-pending-status-expired",
        session_id="session-product",
    )
    assert expired.ok is True
    assert expired.payload["result"] == {
        "status": "expired",
        "phase": "expired",
        "intent_request_id": request_id,
        "source": "text",
        "intent": None,
    }
    assert composition.mutation_calls == []


@pytest.mark.asyncio
async def test_non_destructive_clarification_status_remains_content_free_pending(
    tmp_path: Path,
) -> None:
    registry, composition, _manager, _pushed = _registry(tmp_path, p2=False, p3=True)
    request_id = "request-natural-unclear-status"
    unclear = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-unclear-status",
            text="what is its task status",
            operation="task.status",
            task_id="task-alpha",
        ),
        request_id=request_id,
        session_id="session-product",
    )
    assert unclear.ok is True
    recovered = await registry.handle_p3_intent_status(
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "correlation_id": "correlation-natural-unclear-status",
            "intent_request_id": request_id,
        },
        request_id="request-natural-unclear-status-query",
        session_id="session-product",
    )
    assert recovered.ok is True
    result = cast(dict[str, object], recovered.payload["result"])
    assert result["status"] == "pending"
    assert result["phase"] == "clarification"
    intent = cast(dict[str, object], result["intent"])
    assert intent["confirmation_token"] is None
    assert intent["confirmation_form"] is None
    assert "what is its task status" not in repr(recovered.payload)
    assert composition.query_calls == []


@pytest.mark.asyncio
async def test_natural_task_intent_rejects_client_model_intent_before_authority(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    result = await registry.handle_p3_intent(
        params={
            **_text_intent_params(
                stem="natural-model-tamper",
                text="create task: bounded request",
                operation="task.create",
            ),
            "model_intent": "client-selected-provider",
        },
        request_id="request-natural-model-tamper",
        session_id="session-product",
    )

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert composition.authority_calls == []
    assert composition.prepare_calls == []
    assert composition.mutation_calls == []


@pytest.mark.asyncio
async def test_resolver_exception_is_content_free_on_wire_and_in_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    sentinel = "SENTINEL_PROVIDER_SECRET_TRANSCRIPT"
    logged: list[tuple[str, dict[str, object]]] = []

    def capture_warning(message: str, **kwargs: object) -> None:
        logged.append((message, cast(dict[str, object], kwargs["extra"])))

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.warning",
        capture_warning,
    )

    class _LeakingResolver:
        def resolve(self, *_args: object) -> object:
            raise VoiceTaskBridgeViolation(
                "SENTINEL_PROVIDER_REASON",
                sentinel,
                ErrorCode.PERMISSION_DENIED,
            )

    registry._task_intent_bridge = cast(object, _LeakingResolver())
    result = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-resolver-canary",
            text="create task: bounded resolver canary",
            operation="task.create",
        ),
        request_id="request-natural-resolver-canary",
        session_id="session-product",
    )

    assert result.ok is False
    error = cast(dict[str, object], result.payload["error"])
    assert error == {
        "code": ErrorCode.PERMISSION_DENIED.value,
        "reason": "TASK_INTENT_RESOLUTION_REJECTED",
        "message": "task intent resolution was rejected",
    }
    rendered = repr(result.payload) + repr(logged)
    assert sentinel not in rendered
    assert "SENTINEL_PROVIDER_REASON" not in rendered
    _message, record = next(
        item
        for item in logged
        if item[1].get("live_voice_event") == "task_intent_resolution_rejected"
    )
    assert record["exception_class"] == "VoiceTaskBridgeViolation"
    assert len(cast(str, record["request_digest"])) == 16
    assert composition.query_calls == []
    with pytest.raises(ContractViolation):
        registry._commit_ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-natural-resolver-canary",
                "commit-natural-resolver-canary",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_untyped_resolver_exception_is_content_free_and_releases_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    sentinel = "SENTINEL_UNTYPED_PROVIDER_SECRET"
    logged: list[tuple[str, dict[str, object]]] = []

    def capture_warning(message: str, **kwargs: object) -> None:
        logged.append((message, cast(dict[str, object], kwargs["extra"])))

    class _FailingResolver:
        def resolve(self, *_args: object) -> object:
            raise RuntimeError(sentinel)

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.warning",
        capture_warning,
    )
    registry._task_intent_bridge = cast(object, _FailingResolver())
    result = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-resolver-untyped",
            text="create task: bounded resolver failure",
            operation="task.create",
        ),
        request_id="request-natural-resolver-untyped",
        session_id="session-product",
    )

    assert result.ok is False
    assert cast(dict[str, object], result.payload["error"]) == {
        "code": ErrorCode.UNAVAILABLE.value,
        "reason": "TASK_INTENT_RESOLUTION_FAILED",
        "message": "task intent resolver failed closed",
    }
    assert sentinel not in repr(result.payload) + repr(logged)
    _message, record = next(
        item
        for item in logged
        if item[1].get("live_voice_event") == "task_intent_resolution_failed"
    )
    assert record["exception_class"] == "RuntimeError"
    assert composition.mutation_calls == []
    with pytest.raises(ContractViolation):
        registry._commit_ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-natural-resolver-untyped",
                "commit-natural-resolver-untyped",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_abandoned_pending_intent_evicts_oldest_exact_commit_at_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _composition, _owner = _mutation_registry(tmp_path)
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-abandoned-first",
            text="create task: first bounded request",
            operation="task.create",
        ),
        request_id="request-natural-abandoned-first",
        session_id="session-product",
    )
    second = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-abandoned-second",
            text="create task: second bounded request",
            operation="task.create",
        ),
        request_id="request-natural-abandoned-second",
        session_id="session-product",
    )

    first_token = cast(dict[str, object], first.payload["result"])["confirmation_token"]
    second_token = cast(dict[str, object], second.payload["result"])[
        "confirmation_token"
    ]
    assert first.ok is True and second.ok is True
    assert first_token not in registry._pending_task_intents
    assert second_token in registry._pending_task_intents
    with pytest.raises(ContractViolation):
        registry._commit_ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-natural-abandoned-first",
                "commit-natural-abandoned-first",
            ),
            SCOPE,
        )
    await registry.stop()


@pytest.mark.asyncio
async def test_cancel_confirmation_wrong_task_and_scope_have_zero_effect(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-cancel",
            text="cancel task task-alpha",
            operation="task.cancel",
            task_id="task-alpha",
        ),
        request_id="request-natural-cancel",
        session_id="session-product",
    )
    token = cast(dict[str, object], first.payload["result"])["confirmation_token"]

    wrong_task = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-cancel-wrong",
            text=f"confirm task request {token}",
            operation="task.cancel",
            task_id="task-beta",
        ),
        request_id="request-natural-cancel-wrong",
        session_id="session-product",
    )

    assert wrong_task.ok is False
    assert cast(dict, wrong_task.payload["error"])["reason"] == (
        "TASK_CONFIRMATION_BINDING_MISMATCH"
    )
    assert composition.prepare_calls == []
    assert composition.mutation_calls == []
    assert token in registry._pending_task_intents


@pytest.mark.asyncio
async def test_text_status_dispatches_formal_query_and_partial_like_form_clarifies(
    tmp_path: Path,
) -> None:
    registry, composition, _manager, _pushed = _registry(tmp_path, p2=False, p3=True)
    status = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-status",
            text="task status task-alpha",
            operation="task.status",
            task_id="task-alpha",
        ),
        request_id="request-natural-status",
        session_id="session-product",
    )
    assert status.ok is True, status.payload
    assert cast(dict, status.payload["result"])["status"] == "dispatched"
    assert len(composition.query_calls) == 1

    unclear = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-unclear",
            text="what is its task status",
            operation="task.status",
            task_id="task-alpha",
        ),
        request_id="request-natural-unclear",
        session_id="session-product",
    )
    assert unclear.ok is True
    assert cast(dict, unclear.payload["result"])["status"] == "clarification"
    assert len(composition.query_calls) == 1


@pytest.mark.asyncio
async def test_task_intent_flag_off_has_zero_authority_or_commit_effect(
    tmp_path: Path,
) -> None:
    composition = _P3Composition(tmp_path)
    ledger = TurnCommitLedger()
    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, False),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=cast(object, lambda _message: None),
        commit_ledger=ledger,
    )
    result = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-off",
            text="task status task-alpha",
            operation="task.status",
            task_id="task-alpha",
        ),
        request_id="request-natural-off",
        session_id="session-product",
    )
    assert result.ok is False
    assert composition.authority_calls == []
    with pytest.raises(ContractViolation):
        ledger.require_origin(
            OriginRef("committed_turn", "turn-natural-off", "commit-natural-off"),
            SCOPE,
        )


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


# --- D-069 bounded task.retry product mutation route ------------------------


def _retry_mutation_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.retry",
        "command_id": "command-retry-1",
        "issued_at": NOW,
        "correlation_id": "correlation-retry-1",
        "task_id": "task-1",
    }
    params.update(changes)
    return params


def _mutation_registry(
    tmp_path: Path,
) -> tuple[
    AgentServerProductCompositionRegistry,
    _MutationP3Composition,
    BoundedP3ConfirmationOwner,
]:
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
    return registry, composition, owner


@pytest.mark.asyncio
async def test_product_retry_mutation_issues_and_forwards_one_exact_target(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)

    issued = await registry.handle_p3_confirmation_issue(
        params=_retry_mutation_params(),
        request_id="request-retry-confirmation",
        session_id="session-product",
    )
    assert issued.ok is True, issued.payload
    receipt = cast(dict[str, object], issued.payload["result"])
    assert receipt["operation"] == "task.retry"
    assert receipt["command_id"] == "command-retry-1"
    assert receipt["target_task_id"] == "task-1"

    mutated = await registry.handle_p3_mutation(
        params=_retry_mutation_params(
            confirmation_id=cast(str, receipt["confirmation_id"])
        ),
        request_id="request-retry-mutation",
        session_id="session-product",
    )
    assert mutated.ok is True, mutated.payload
    result = cast(dict[str, object], mutated.payload["result"])
    assert result["status"] == "mutation_processed"
    assert result["operation"] == "task.retry"
    assert result["target_task_id"] == "task-1"

    # The registry forwards the operation verbatim and never invents lineage.
    assert [operation for operation, _ in composition.mutation_calls] == ["task.retry"]
    forwarded = composition.mutation_calls[0][1]
    assert "operation" not in forwarded
    assert forwarded["task_id"] == "task-1"
    assert "previous_attempt_id" not in forwarded
    assert "attempt_number" not in forwarded


@pytest.mark.asyncio
async def test_product_retry_rejects_extra_missing_or_unknown_mutation_fields(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)

    # A bounded retry carries no voice-committed origin and no create content.
    for extra in (
        {"source": "voice"},
        {"source": "structured"},
        {"name": "renamed"},
        {"instruction": "replaced"},
        {"model_intent": "default"},
        {"interaction_id": "interaction-1"},
        {"previous_attempt_id": "attempt-client-declared"},
        {"attempt_number": 2},
    ):
        rejected = await registry.handle_p3_confirmation_issue(
            params=_retry_mutation_params(**extra),
            request_id=f"request-retry-extra-{next(iter(extra))}",
            session_id="session-product",
        )
        assert rejected.ok is False, extra
        assert cast(dict, rejected.payload["error"])["reason"] == (
            "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
        ), extra

    # The exact target task is mandatory.
    without_target = _retry_mutation_params()
    without_target.pop("task_id")
    missing = await registry.handle_p3_confirmation_issue(
        params=without_target,
        request_id="request-retry-missing-target",
        session_id="session-product",
    )
    assert missing.ok is False
    assert cast(dict, missing.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )

    # An unnegotiated same-task operation still fails closed.
    unsupported = await registry.handle_p3_confirmation_issue(
        params=_retry_mutation_params(operation="task.resume"),
        request_id="request-retry-unsupported",
        session_id="session-product",
    )
    assert unsupported.ok is False
    assert cast(dict, unsupported.payload["error"])["reason"] == (
        "INVALID_P3_CONFIRMATION_OPERATION"
    )

    # Nothing above ever reached the mutation route.
    assert composition.mutation_calls == []


def _create_mutation_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.create",
        "command_id": "command-create-1",
        "issued_at": NOW,
        "correlation_id": "correlation-create-1",
        "name": "Formal project task",
        "instruction": "Create one bounded project change.",
    }
    params.update(changes)
    return params


@pytest.mark.asyncio
async def test_every_p3_mutation_rejects_missing_required_fields_fail_closed(
    tmp_path: Path,
) -> None:
    """A missing required field is one stable rejection, never a stray lookup.

    ``_require_exact_params`` only rejects non-string or unknown keys, so each
    P3 mutation additionally proves its required fields are present.  Without
    that proof a missing ``task_id`` escaped as an unhandled ``KeyError`` from
    the downstream confirmation preparation instead of failing closed.
    """

    registry, composition, owner = _mutation_registry(tmp_path)

    cancel_without_target = _mutation_params()
    cancel_without_target.pop("task_id")
    create_without_name = _create_mutation_params()
    create_without_name.pop("name")
    create_without_instruction = _create_mutation_params()
    create_without_instruction.pop("instruction")
    retry_without_target = _retry_mutation_params()
    retry_without_target.pop("task_id")

    for label, params in (
        ("task.cancel missing task_id", cancel_without_target),
        ("task.create missing name", create_without_name),
        ("task.create missing instruction", create_without_instruction),
        ("task.retry missing task_id", retry_without_target),
    ):
        issued = await registry.handle_p3_confirmation_issue(
            params=params,
            request_id=f"request-issue-{label.replace(' ', '-')}",
            session_id="session-product",
        )
        assert issued.ok is False, label
        error = cast(dict, issued.payload["error"])
        assert error["reason"] == "INVALID_PRODUCT_COMPOSITION_ARGUMENT", label
        assert error["code"] == "INVALID_ARGUMENT", label

    # ``mutate`` additionally requires the confirmation it must forward.
    mutate_without_confirmation = _retry_mutation_params()
    mutated = await registry.handle_p3_mutation(
        params=mutate_without_confirmation,
        request_id="request-mutate-missing-confirmation",
        session_id="session-product",
    )
    assert mutated.ok is False
    mutate_error = cast(dict, mutated.payload["error"])
    assert mutate_error["reason"] == "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    assert mutate_error["code"] == "INVALID_ARGUMENT"

    # None of the rejections reached authority resolution, the confirmation
    # forwarder or the mutation route, and none consumed a confirmation.
    assert composition.prepare_calls == []
    assert composition.mutation_calls == []
    assert composition.authority_calls == []
    assert owner.raw_verifier is not None
    with sqlite3.connect(tmp_path / "confirmations.sqlite3") as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[0]
            == 0
        )


@pytest.mark.asyncio
async def test_missing_bearer_stays_an_authentication_failure_for_every_mutation(
    tmp_path: Path,
) -> None:
    """A missing bearer is an authentication fact, not a structural one.

    ``auth_token`` remains an allowed field and is deliberately excluded from
    the structural required-field check, so the existing authenticator keeps
    classifying it.  Folding it into the argument check would have silently
    reclassified every unauthenticated create/cancel/retry.
    """

    registry, composition, owner = _mutation_registry(tmp_path)

    for label, builder in (
        ("task.create", _create_mutation_params),
        ("task.cancel", _mutation_params),
        ("task.retry", _retry_mutation_params),
    ):
        without_bearer = builder()
        without_bearer.pop("auth_token")

        issued = await registry.handle_p3_confirmation_issue(
            params=without_bearer,
            request_id=f"request-issue-no-bearer-{label}",
            session_id="session-product",
        )
        assert issued.ok is False, label
        issue_error = cast(dict, issued.payload["error"])
        assert issue_error["reason"] == "FORMAL_TASK_AUTHENTICATION_REQUIRED", label
        assert issue_error["code"] == "UNAUTHENTICATED", label

        mutate_without_bearer = dict(without_bearer)
        mutate_without_bearer["confirmation_id"] = "confirmation-never-issued"
        mutated = await registry.handle_p3_mutation(
            params=mutate_without_bearer,
            request_id=f"request-mutate-no-bearer-{label}",
            session_id="session-product",
        )
        assert mutated.ok is False, label
        mutate_error = cast(dict, mutated.payload["error"])
        assert mutate_error["reason"] == "FORMAL_TASK_AUTHENTICATION_REQUIRED", label
        assert mutate_error["code"] == "UNAUTHENTICATED", label

    # No rejection reached the mutation route or consumed a confirmation, and
    # the remaining required-field checks are untouched for every operation.
    assert composition.mutation_calls == []
    assert composition.authority_calls == []
    with sqlite3.connect(tmp_path / "confirmations.sqlite3") as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[0]
            == 0
        )
    still_structural = _retry_mutation_params()
    still_structural.pop("task_id")
    structural = await registry.handle_p3_confirmation_issue(
        params=still_structural,
        request_id="request-issue-still-structural",
        session_id="session-product",
    )
    assert structural.ok is False
    assert cast(dict, structural.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
