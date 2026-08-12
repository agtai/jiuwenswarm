# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import subprocess
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    ErrorCode,
    InputCommitState,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
    WorkProgressEventV2,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskViolation,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
)
from jiuwenswarm.server.live_voice.persistent_task_core import (
    PersistentTaskCore,
    project_task_event,
)
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    AuthenticatedPrincipal,
    P3AuthenticatedComposition,
    P3_OPERATIONS,
    ResolvedAuthority,
    StaticBearerAuthenticator,
)
from jiuwenswarm.server.live_voice.p3_confirmation import (
    BoundedP3ConfirmationOwner,
)
from jiuwenswarm.server.live_voice.p3_model_resolution import ResolvedP3Model
from jiuwenswarm.server.live_voice.p3_product_confirmation import (
    ProductP3ConfirmationForwarder,
)
from jiuwenswarm.server.live_voice.product_composition_registry import (
    AgentServerProductCompositionRegistry,
    ProductCompositionSettings,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    ProjectExecutionBinding,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.live_voice.voice_task_policy import (
    FormalTaskInvocation,
    FormalTaskPolicyAdapter,
    FormalTaskPolicyInput,
)
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm

NOW = "2026-08-07T12:00:00Z"
EXPIRY = "2100-01-01T00:00:00Z"
PRODUCT_TOKEN = "test-only-product-token-000000000000"


def _git(project: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _project(project: Path) -> str:
    project.mkdir()
    _git(project, "init")
    _git(project, "config", "user.name", "Live Voice Integration")
    _git(project, "config", "user.email", "live-voice@example.invalid")
    (project / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(project, "add", "README.md")
    _git(project, "commit", "-m", "baseline")
    return _git(project, "rev-parse", "HEAD")


def _scope() -> ScopeRef:
    return ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def _grant(
    operation: str,
    *,
    command_id: str | None,
    target_task_id: str | None,
    confirmed: bool = False,
) -> TaskAuthorizationGrant:
    return TaskAuthorizationGrant(
        principal_id="principal-1",
        scope=_scope(),
        operation=operation,
        command_id=command_id,
        target_task_id=target_task_id,
        allowed_capabilities=frozenset({operation}),
        confirmation_id=("confirmation-1" if confirmed else None),
        confirmed=confirmed,
        expires_at=EXPIRY,
    )


def _context(project: Path, revision: str) -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="gateway.project_registry",
        stable_id="project-1",
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value=revision,
        scope=_scope(),
        permissions=("task.execute", "project.write"),
        expires_at=EXPIRY,
        redaction_policy_id="live_voice.project.v1",
    )


def _voice_create(
    project: Path,
    revision: str,
    *,
    suffix: str,
    confirmed: bool = True,
) -> FormalTaskInvocation:
    interaction_id = f"interaction-{suffix}"
    turn_id = f"turn-{suffix}"
    commit_id = f"commit-{suffix}"
    command_id = f"command-{suffix}"
    instruction = f"Create RESULT-{suffix}.md with one bounded result."
    commits = TurnCommitLedger()
    commits.accept(
        TurnCommit.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "commit_id": commit_id,
                "turn_id": turn_id,
                "interaction_id": interaction_id,
                "text": instruction,
                "hypothesis_provenance": {"provider": "integration"},
                "scope": _scope().to_dict(),
                "context_refs": [],
                "committed_at": NOW,
            }
        )
    )
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="voice",
        operation="task.create",
        request_id=f"request-{suffix}",
        issued_at=NOW,
        scope=_scope(),
        correlation_id=f"correlation-{suffix}",
        authorization=_grant(
            "task.create",
            command_id=command_id,
            target_task_id=None,
            confirmed=confirmed,
        ),
        command_id=command_id,
        interaction_id=interaction_id,
        turn_id=turn_id,
        commit_id=commit_id,
        name=f"Formal task {suffix}",
        instruction=instruction,
        context=_context(project, revision),
        attributes={
            "model_identity": "default#0",
            "model_config_version": "catalog-v1",
        },
        destructive=True,
        confirmed=confirmed,
        confirmation_id=("confirmation-1" if confirmed else None),
    )
    return FormalTaskPolicyAdapter(commits).map(intent)


def _structured(
    operation: str,
    *,
    task_id: str | None,
    command_id: str | None = None,
    after_seq: int = -1,
) -> FormalTaskInvocation:
    mutation = command_id is not None
    return FormalTaskPolicyAdapter().map(
        FormalTaskPolicyInput(
            state=InputCommitState.COMMITTED,
            source="structured",
            operation=operation,
            request_id=f"request-{operation}-{command_id or 'query'}",
            issued_at=NOW,
            scope=_scope(),
            correlation_id="correlation-structured",
            authorization=_grant(
                operation,
                command_id=command_id,
                target_task_id=task_id,
                confirmed=mutation,
            ),
            command_id=command_id,
            task_id=task_id,
            destructive=mutation,
            confirmed=mutation,
            confirmation_id=("confirmation-1" if mutation else None),
            after_seq=after_seq,
        )
    )


class _DirectAgentFacade:
    def __init__(self, project: Path) -> None:
        self.project = project
        self.started: dict[str, asyncio.Event] = {}
        self.release: dict[str, asyncio.Event] = {}
        self.requests = []

    async def process_background_code_task_stream(self, request):
        suffix = request.params["query"].split("RESULT-", 1)[1].split(".md", 1)[0]
        self.requests.append(request)
        self.started.setdefault(suffix, asyncio.Event()).set()
        await self.release.setdefault(suffix, asyncio.Event()).wait()
        (Path(request.params["project_dir"]) / f"RESULT-{suffix}.md").write_text(
            f"completed {suffix}\n", encoding="utf-8"
        )
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={"event_type": "chat.final", "content": "completed"},
            is_complete=True,
        )


class _SlowConversationAdapter:
    _is_session_scoped_adapter = False

    def __init__(self) -> None:
        self.entered: dict[str, asyncio.Event] = {}
        self.release: dict[str, asyncio.Event] = {}

    async def process_formal_live_voice_stream_impl(
        self, request, _inputs
    ) -> AsyncIterator[AgentResponseChunk]:
        self.entered.setdefault(request.request_id, asyncio.Event()).set()
        await self.release.setdefault(request.request_id, asyncio.Event()).wait()
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={
                "event_type": "chat.final",
                "content": f"joint:{request.request_id}",
            },
            is_complete=True,
        )

    async def process_message_stream_impl(self, *_args, **_kwargs):
        raise AssertionError("joint scenario must not use the legacy Chat stream")
        yield  # pragma: no cover


class _Resolver:
    def __init__(self, binding: ProjectExecutionBinding) -> None:
        self.binding = binding
        self.calls = 0

    async def resolve(self, _spec, *, for_dispatch: bool):
        assert for_dispatch is True
        self.calls += 1
        return self.binding


class _ProductAuthorityResolver:
    def __init__(self, context: ResolvedTaskContext, project: Path) -> None:
        self.context = context
        self.project = project
        self.calls: list[tuple[str, bool]] = []

    def resolve(
        self,
        principal: AuthenticatedPrincipal,
        *,
        session_id: str,
        now: str,
        require_clean: bool,
    ) -> ResolvedAuthority:
        del now
        self.calls.append((session_id, require_clean))
        if (
            session_id != self.context.scope.session_id
            or self.context.scope.project_id not in principal.allowed_project_ids
        ):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal task scope is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        if require_clean and _git(self.project, "status", "--porcelain"):
            raise FormalTaskViolation(
                "TASK_CONTEXT_WORKTREE_DIRTY",
                "formal task project must have a clean worktree",
                ErrorCode.PERMISSION_DENIED,
            )
        return ResolvedAuthority(principal, self.context.scope, self.context)


class _ProductModelResolver:
    def resolve(
        self,
        model_intent: str | None,
        *,
        expected_identity: str | None = None,
        expected_config_version: str | None = None,
        instantiate: bool = False,
    ) -> ResolvedP3Model:
        if model_intent not in {None, "default", "default#0"}:
            raise FormalTaskViolation(
                "P3_MODEL_INTENT_UNKNOWN",
                "formal task model is unavailable",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if expected_identity not in {
            None,
            "default#0",
        } or expected_config_version not in {
            None,
            "catalog-v1",
        }:
            raise FormalTaskViolation(
                "EXECUTOR_MODEL_BINDING_DRIFT",
                "formal task model binding changed",
                ErrorCode.PERMISSION_DENIED,
            )
        return ResolvedP3Model(
            object() if instantiate else None,
            "default#0",
            "catalog-v1",
        )


class _JointProductAgentManager:
    def __init__(self, adapter: _SlowConversationAdapter) -> None:
        self.agent = JiuWenSwarm()
        self.agent._adapter = adapter  # type: ignore[assignment]
        self.pins = 0
        self.unpins = 0

    async def get_agent(self, *_args: object) -> JiuWenSwarm:
        return self.agent

    def pin_agent(self, agent: JiuWenSwarm) -> None:
        assert agent is self.agent
        self.pins += 1

    def unpin_agent(self, agent: JiuWenSwarm) -> None:
        assert agent is self.agent
        self.unpins += 1


def _joint_product_p2_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": PRODUCT_TOKEN,
        "session_id": "session-1",
        "correlation_id": "correlation-joint",
        "interaction_id": "interaction-joint",
        "activation_id": "activation-joint",
        "activation_generation": 1,
    }
    params.update(changes)
    return params


def _joint_product_task_commit(*, stem: str, text: str) -> dict[str, object]:
    commit_id = f"commit-{stem}"
    turn_id = f"turn-{stem}"
    return _joint_product_p2_params(
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
            "session_id": "session-1",
            "correlation_id": "correlation-joint",
            "interaction_id": "interaction-joint",
            "turn_id": turn_id,
            "commit_id": commit_id,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "critical_policy": "confirmed",
        },
    )


def _joint_product_voice_intent(
    *, stem: str, operation: str, task_id: str | None = None
) -> dict[str, object]:
    params = _joint_product_p2_params(
        source="voice",
        operation_hint=operation,
        turn_id=f"turn-{stem}",
        commit_id=f"commit-{stem}",
    )
    params.pop("activation_id")
    params.pop("activation_generation")
    if task_id is not None:
        params["task_id_hint"] = task_id
    return params


async def _wait(predicate, *, attempts: int = 500) -> None:
    # Test-only Windows scheduling allowance; this is not a product deadline or SLO.
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not reached")


@pytest.mark.asyncio
async def test_d90_formal_direct_voice_task_survives_disconnect_and_restarts_truthfully(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    revision = _project(project)
    database = tmp_path / "isolated-data" / "formal-task.sqlite3"
    facade = _DirectAgentFacade(project)

    async def fence() -> None:
        assert _git(project, "rev-parse", "HEAD") == revision

    binding = ProjectExecutionBinding(
        service=None,
        execution_agent=object(),
        project_executor=facade,
        effective_execution_root=str(project.resolve()),
        execution_target={
            "project_dir": str(project.resolve()),
            "project_id": "project-1",
            "origin_session_id": "session-1",
            "origin_channel_id": "web",
        },
        owner_scope={
            "channel_id": "formal-task-core",
            "session_id": "session-1",
            "app_id": "live-voice",
        },
        resolved_revision_kind="version",
        resolved_revision_value=revision,
        model_identity="default#0",
        model_config_version="catalog-v1",
        dispatch_fence=fence,
    )
    resolver = _Resolver(binding)
    executor = DirectProjectCodeExecutorAdapter(resolver, database)
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, executor)

    counts_before = store.counts()
    with pytest.raises(FormalTaskViolation) as unconfirmed:
        _voice_create(project, revision, suffix="unconfirmed", confirmed=False)
    assert unconfirmed.value.reason == "TASK_CONFIRMATION_REQUIRED"
    assert store.counts() == counts_before

    invocation = _voice_create(project, revision, suffix="survive")
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok is True
    task_id = str(created.result["task_id"])
    assert store.counts()["tasks"] == 1
    assert await core.drain_outbox_once(worker_id="integration") is True
    await _wait(lambda: facade.started.get("survive", asyncio.Event()).is_set())

    # Dropping the voice/Web owner performs no Executor or Task cancellation.
    running = core.query(
        _structured("task.status", task_id=task_id).envelope,
        _structured("task.status", task_id=task_id).authorization,
        now=NOW,
    )
    assert running.ok is True
    assert running.result["task"]["state"] == "running"
    assert facade.requests[0].session_id.startswith("formal-task-")

    facade.release["survive"].set()
    await _wait(lambda: not executor._running)
    reconciled = await core.reconcile()
    assert reconciled["known"] == 1

    results = {}
    for operation in ("task.get", "task.list", "task.status", "task.events"):
        invocation = _structured(
            operation,
            task_id=None if operation == "task.list" else task_id,
            after_seq=-1,
        )
        results[operation] = core.query(
            invocation.envelope, invocation.authorization, now=NOW
        )
        assert results[operation].ok is True
    assert results["task.get"].result["task"]["outcome"] == "completed"
    assert [task["task_id"] for task in results["task.list"].result["tasks"]] == [
        task_id
    ]
    assert (
        results["task.status"]
        .result["attempt"]["executor_ref"]
        .startswith("d0-project:")
    )
    events = results["task.events"].result["events"]
    assert [event["seq"] for event in events] == list(range(len(events)))
    assert events[-1]["event_type"] == "task.terminal"
    assert events[-1]["outcome"] == "completed"

    task = store.get_task(task_id, _scope())
    assert task.spec.origin.turn_id == "turn-survive"
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=10_000)
    progress = WorkProgressEventV2.from_dict(project_task_event(snapshot.events[-1]))
    assert progress.work_ref.kind == "task"
    assert progress.work_ref.id == task_id
    assert progress.source.event_id == snapshot.events[-1].event_id
    assert progress.seq == snapshot.events[-1].seq
    assert _git(project, "rev-parse", "HEAD") == revision
    assert (project / "RESULT-survive.md").read_text(encoding="utf-8") == (
        "completed survive\n"
    )

    # A fresh Core/Executor sees the same terminal attempt and creates none.
    restarted_executor = DirectProjectCodeExecutorAdapter(_Resolver(binding), database)
    restarted = PersistentTaskCore(SqliteTaskStore(database), restarted_executor)
    summary = await restarted.reconcile()
    assert summary["known"] == 0
    assert restarted.store.counts()["attempts"] == 1
    assert resolver.calls == 1


@pytest.mark.asyncio
async def test_only_confirmed_task_cancel_mutates_direct_task_and_other_cancels_are_zero(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    revision = _project(project)
    database = tmp_path / "isolated-data" / "formal-task.sqlite3"
    facade = _DirectAgentFacade(project)

    async def fence() -> None:
        return None

    binding = ProjectExecutionBinding(
        service=None,
        execution_agent=object(),
        project_executor=facade,
        effective_execution_root=str(project.resolve()),
        execution_target={
            "project_dir": str(project.resolve()),
            "project_id": "project-1",
            "origin_session_id": "session-1",
            "origin_channel_id": "web",
        },
        owner_scope={
            "channel_id": "formal-task-core",
            "session_id": "session-1",
            "app_id": "live-voice",
        },
        resolved_revision_kind="version",
        resolved_revision_value=revision,
        model_identity="default#0",
        model_config_version="catalog-v1",
        dispatch_fence=fence,
    )
    executor = DirectProjectCodeExecutorAdapter(_Resolver(binding), database)
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, executor)
    create = _voice_create(project, revision, suffix="cancel")
    created = core.execute(
        create.envelope, create.authorization, context=create.context, now=NOW
    )
    task_id = str(created.result["task_id"])
    await core.drain_outbox_once(worker_id="integration")
    await _wait(lambda: facade.started.get("cancel", asyncio.Event()).is_set())
    counts = store.counts()

    for operation in ("response.cancel", "round.cancel"):
        denied = replace(
            _structured("task.status", task_id=task_id).envelope,
            query_type=operation,
            required_capabilities=(operation,),
        )
        result = core.query(
            denied,
            _grant(operation, command_id=None, target_task_id=task_id),
            now=NOW,
        )
        assert result.ok is False
        assert result.error.reason == "UNSUPPORTED_FORMAL_TASK_QUERY"
    assert store.counts() == counts
    assert not facade.release["cancel"].is_set()

    cancel = _structured(
        "task.cancel", task_id=task_id, command_id="command-cancel-task"
    )
    accepted = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert accepted.ok is True
    await core.drain_outbox_once(worker_id="integration")
    terminal = store.get_task(task_id, _scope())
    assert terminal.outcome is TerminalOutcome.CANCELLED
    assert not (project / "RESULT-cancel.md").exists()
    assert _git(project, "rev-parse", "HEAD") == revision


@pytest.mark.asyncio
async def test_s6_joint_slow_conversation_detached_task_and_exact_cancel_domains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "joint-project"
    revision = _project(project)
    database = tmp_path / "joint-isolated-data" / "formal-task.sqlite3"
    task_facade = _DirectAgentFacade(project)

    async def fence() -> None:
        assert _git(project, "rev-parse", "HEAD") == revision

    binding = ProjectExecutionBinding(
        service=None,
        execution_agent=object(),
        project_executor=task_facade,
        effective_execution_root=str(project.resolve()),
        execution_target={
            "project_dir": str(project.resolve()),
            "project_id": "project-1",
            "origin_session_id": "session-1",
            "origin_channel_id": "web",
        },
        owner_scope={
            "channel_id": "formal-task-core",
            "session_id": "session-1",
            "app_id": "live-voice",
        },
        resolved_revision_kind="version",
        resolved_revision_value=revision,
        model_identity="default#0",
        model_config_version="catalog-v1",
        dispatch_fence=fence,
    )
    executor = DirectProjectCodeExecutorAdapter(_Resolver(binding), database)
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, executor)
    conversation_adapter = _SlowConversationAdapter()
    manager = _JointProductAgentManager(conversation_adapter)
    commit_ledger = TurnCommitLedger(capacity=128)
    confirmation_owner = BoundedP3ConfirmationOwner(
        database,
        enabled=True,
    )
    confirmation_forwarder = ProductP3ConfirmationForwarder(confirmation_owner)
    p3_composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(
            token=PRODUCT_TOKEN,
            principal=AuthenticatedPrincipal(
                principal_id="principal-1",
                allowed_project_ids=frozenset({"project-1"}),
                allowed_operations=P3_OPERATIONS | {"agent.chat"},
                expires_at=EXPIRY,
            ),
        ),
        authority_resolver=_ProductAuthorityResolver(
            _context(project, revision), project
        ),
        core=core,
        confirmation_verifier=confirmation_forwarder,
        model_resolver=_ProductModelResolver(),
        policy=FormalTaskPolicyAdapter(commit_ledger),
        reconcile_interval=3600,
        clock=lambda: NOW,
    )
    pushed: list[dict[str, object]] = []

    async def push_text_event(message: dict[str, object]) -> bool:
        pushed.append(message)
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=True,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
            critical_input_enabled=True,
        ),
        p3_composition=p3_composition,
        agent_manager=manager,
        push_text_event=push_text_event,
        p3_confirmation_owner=confirmation_owner,
        p3_confirmation_forwarder=confirmation_forwarder,
        commit_ledger=commit_ledger,
    )
    await p3_composition.start()
    activated = await registry.handle_p2_activate(
        params=_joint_product_p2_params(),
        request_id="request-joint-activate",
        session_id="session-1",
        channel_id="web",
    )
    assert activated.ok is True, activated.payload

    first = await registry.handle_p2_submit(
        params=_joint_product_p2_params(
            commit_id="commit-joint-text",
            turn_id="turn-joint-text",
            response_id="response-joint-text",
            committed_at=NOW,
            text="review the current state slowly",
            dispatch_target="agent",
        ),
        request_id="request-joint-text",
        session_id="session-1",
        channel_id="web",
    )
    assert first.ok is True, first.payload
    await _wait(lambda: "request-joint-text" in conversation_adapter.entered)
    await asyncio.wait_for(
        conversation_adapter.entered["request-joint-text"].wait(), timeout=1
    )

    create_text = "create task: Create RESULT-joint.md with one bounded result."
    create_origin = await registry.handle_p2_submit(
        params=_joint_product_task_commit(
            stem="joint-task-create",
            text=create_text,
        ),
        request_id="request-joint-task-create-origin",
        session_id="session-1",
        channel_id="web",
    )
    assert create_origin.ok is True, create_origin.payload
    create_pending = await registry.handle_p3_intent(
        params=_joint_product_voice_intent(
            stem="joint-task-create",
            operation="task.create",
        ),
        request_id="request-joint-task-create-intent",
        session_id="session-1",
    )
    assert create_pending.ok is True, create_pending.payload
    pending_result = cast(dict[str, object], create_pending.payload["result"])
    assert pending_result["status"] == "clarification"
    confirmation_token = cast(str, pending_result["confirmation_token"])
    create_confirmation_text = f"confirm task request {confirmation_token}"
    create_confirmation_origin = await registry.handle_p2_submit(
        params=_joint_product_task_commit(
            stem="joint-task-create-confirm",
            text=create_confirmation_text,
        ),
        request_id="request-joint-task-create-confirm-origin",
        session_id="session-1",
        channel_id="web",
    )
    assert create_confirmation_origin.ok is True, create_confirmation_origin.payload
    created = await registry.handle_p3_intent(
        params=_joint_product_voice_intent(
            stem="joint-task-create-confirm",
            operation="task.create",
        ),
        request_id="request-joint-task-create-confirm-intent",
        session_id="session-1",
    )
    assert created.ok is True, created.payload
    create_result = cast(dict[str, object], created.payload["result"])
    assert create_result["status"] == "dispatched"
    assert create_result["origin_kind"] == "voice"
    assert create_result["origin_id"] == "interaction-joint"
    task_id = cast(str, create_result["task_id"])
    assert registry._voice_task_origins[task_id].interaction_id == ("interaction-joint")
    await _wait(lambda: task_facade.started.get("joint", asyncio.Event()).is_set())

    second_route = _joint_product_p2_params(
        correlation_id="correlation-joint-response",
        interaction_id="interaction-joint-response",
        activation_id="activation-joint-response",
        activation_generation=1,
    )
    second_activated = await registry.handle_p2_activate(
        params=second_route,
        request_id="request-joint-response-activate",
        session_id="session-1",
        channel_id="web",
    )
    assert second_activated.ok is True, second_activated.payload

    status_text = f"task status {task_id}"
    status_origin = await registry.handle_p2_submit(
        params=_joint_product_task_commit(
            stem="joint-task-status",
            text=status_text,
        ),
        request_id="request-joint-task-status-origin",
        session_id="session-1",
        channel_id="web",
    )
    assert status_origin.ok is True, status_origin.payload
    # ``accepted`` -> ``running`` is owned by the dispatch worker, so the query
    # must wait for that transition instead of relying on an incidental
    # scheduling gap somewhere else in the activation path.
    def _task_is_running() -> bool:
        probe = _structured("task.status", task_id=task_id)
        observed = core.query(probe.envelope, probe.authorization, now=NOW)
        return bool(
            observed.ok and observed.result["task"]["state"] == "running"
        )

    await _wait(_task_is_running)
    status = await registry.handle_p3_intent(
        params=_joint_product_voice_intent(
            stem="joint-task-status",
            operation="task.status",
            task_id=task_id,
        ),
        request_id="request-joint-task-status-intent",
        session_id="session-1",
    )
    assert status.ok is True, status.payload
    status_result = cast(dict[str, object], status.payload["result"])
    assert status_result["status"] == "dispatched"
    formal_status = cast(dict[str, object], status_result["formal_task_result"])
    assert cast(dict, formal_status["task"])["state"] == "running"

    revised = await registry.handle_p2_submit(
        params={
            **second_route,
            "commit_id": "commit-joint-voice-revision",
            "turn_id": "turn-joint-voice-revision",
            "response_id": "response-joint-voice-revision",
            "committed_at": NOW,
            "text": "revise the answer while detached work continues",
            "dispatch_target": "agent",
        },
        request_id="request-joint-voice-revision",
        session_id="session-1",
        channel_id="web",
    )
    assert revised.ok is True, revised.payload
    await _wait(lambda: "request-joint-voice-revision" in conversation_adapter.entered)
    await asyncio.wait_for(
        conversation_adapter.entered["request-joint-voice-revision"].wait(),
        timeout=1,
    )
    revised_response = cast(
        dict[str, object],
        cast(dict[str, object], revised.payload["result"])["response"],
    )
    interrupted = await registry.handle_p2_barge_in(
        params={
            **second_route,
            "action_id": "joint-response-interruption",
            "response_id": revised_response["response_id"],
            "response_generation": revised_response["response_generation"],
            "cancel_response": True,
        },
        request_id="request-joint-barge-in",
        session_id="session-1",
    )
    assert interrupted.ok is True, interrupted.payload
    assert cast(dict, interrupted.payload["result"])["applied"] is True
    post_barge = await registry.handle_p2_submit(
        params={
            **second_route,
            "commit_id": "commit-joint-post-barge",
            "turn_id": "turn-joint-post-barge",
            "response_id": "response-joint-post-barge",
            "committed_at": NOW,
            "text": "continue the revised answer while detached work remains active",
            "dispatch_target": "agent",
        },
        request_id="request-joint-post-barge",
        session_id="session-1",
        channel_id="web",
    )
    assert post_barge.ok is True, post_barge.payload
    await _wait(lambda: "request-joint-post-barge" in conversation_adapter.entered)
    post_barge_response = cast(
        dict[str, object],
        cast(dict[str, object], post_barge.payload["result"])["response"],
    )
    assert cast(int, post_barge_response["response_generation"]) > cast(
        int, revised_response["response_generation"]
    )

    progress = await registry.handle_p3_progress_activate(
        params={
            "auth_token": PRODUCT_TOKEN,
            "session_id": "session-1",
            "task_id": task_id,
            "correlation_id": "correlation-joint",
            "origin_id": "interaction-joint",
            "generation_id": "joint-task-progress-generation",
            "generation": 1,
            "origin_kind": "voice",
        },
        request_id="request-joint-task-progress",
        session_id="session-1",
        channel_id="web",
    )
    assert progress.ok is True, progress.payload
    progress_result = cast(dict[str, object], progress.payload["result"])
    assert progress_result["requested_origin_kind"] == "voice"
    assert progress_result["origin_kind"] == "text"
    assert progress_result["fallback_reason"] == (
        "TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE"
    )

    counts_before_rejections = store.counts()
    stale = await registry.handle_p3_intent(
        params=_joint_product_voice_intent(
            stem="joint-stale-missing",
            operation="task.status",
            task_id=task_id,
        ),
        request_id="request-joint-stale-intent",
        session_id="session-1",
    )
    wrong_scope = await registry.handle_p3_query(
        operation="task.status",
        params={
            "auth_token": PRODUCT_TOKEN,
            "session_id": "session-1",
            "task_id": task_id,
            "claimed_project_id": "project-foreign",
        },
        request_id="request-joint-wrong-scope",
        session_id="session-1",
    )
    partial = await registry.handle_p3_intent(
        params={
            "auth_token": PRODUCT_TOKEN,
            "session_id": "session-1",
            "correlation_id": "correlation-joint-partial",
            "source": "text",
            "operation_hint": "task.create",
            "interaction_id": "interaction-joint-partial",
            "turn_id": "turn-joint-partial",
            "commit_id": "commit-joint-partial",
            "committed_at": NOW,
            "text": "create task:",
        },
        request_id="request-joint-partial-intent",
        session_id="session-1",
    )
    assert stale.ok is False
    assert wrong_scope.ok is False
    assert partial.ok is False or cast(dict, partial.payload["result"])["status"] == (
        "clarification"
    )
    assert store.counts() == counts_before_rejections

    cancel_text = f"cancel task {task_id}"
    cancel_origin = await registry.handle_p2_submit(
        params=_joint_product_task_commit(
            stem="joint-task-cancel",
            text=cancel_text,
        ),
        request_id="request-joint-task-cancel-origin",
        session_id="session-1",
        channel_id="web",
    )
    assert cancel_origin.ok is True, cancel_origin.payload
    cancel_pending = await registry.handle_p3_intent(
        params=_joint_product_voice_intent(
            stem="joint-task-cancel",
            operation="task.cancel",
            task_id=task_id,
        ),
        request_id="request-joint-task-cancel-intent",
        session_id="session-1",
    )
    assert cancel_pending.ok is True, cancel_pending.payload
    cancel_token = cast(
        str,
        cast(dict[str, object], cancel_pending.payload["result"])["confirmation_token"],
    )
    cancel_confirmation = await registry.handle_p2_submit(
        params=_joint_product_task_commit(
            stem="joint-task-cancel-confirm",
            text=f"confirm task request {cancel_token}",
        ),
        request_id="request-joint-task-cancel-confirm-origin",
        session_id="session-1",
        channel_id="web",
    )
    assert cancel_confirmation.ok is True, cancel_confirmation.payload
    cancelled = await registry.handle_p3_intent(
        params=_joint_product_voice_intent(
            stem="joint-task-cancel-confirm",
            operation="task.cancel",
            task_id=task_id,
        ),
        request_id="request-joint-task-cancel-confirm-intent",
        session_id="session-1",
    )
    assert cancelled.ok is True, cancelled.payload
    assert cast(dict, cancelled.payload["result"])["status"] == "dispatched"
    await _wait(
        lambda: store.get_task(task_id, _scope()).outcome is TerminalOutcome.CANCELLED
    )
    assert conversation_adapter.release["request-joint-post-barge"].is_set() is False

    def terminal_progress() -> dict[str, Any] | None:
        for message in reversed(pushed):
            payload = message.get("payload")
            if not isinstance(payload, dict) or payload.get("event_type") != (
                "live_voice.task.progress"
            ):
                continue
            progress_event = payload.get("progress_event")
            if isinstance(progress_event, dict):
                projected = WorkProgressEventV2.from_dict(
                    cast(dict[str, object], progress_event["payload"])
                )
                if projected.state.value == "terminal":
                    return cast(dict[str, Any], payload)
        return None

    await _wait(lambda: terminal_progress() is not None)
    terminal_payload = cast(dict[str, Any], terminal_progress())
    returned = WorkProgressEventV2.from_dict(
        cast(dict[str, object], terminal_payload["progress_event"])["payload"]
    )
    assert returned.work_ref.id == task_id
    assert returned.state.value == "terminal"
    assert returned.outcome is TerminalOutcome.CANCELLED
    assert create_text not in repr(pushed)
    source_event = cast(dict[str, object], terminal_payload["source_event"])
    progress_event = cast(dict[str, object], terminal_payload["progress_event"])
    acknowledged = await registry.handle_p3_progress_ack(
        params={
            "auth_token": PRODUCT_TOKEN,
            "session_id": "session-1",
            "task_id": task_id,
            "correlation_id": "correlation-joint",
            "origin_id": "interaction-joint",
            "generation_id": "joint-task-progress-generation",
            "generation": 1,
            "delivery_id": terminal_payload["delivery_id"],
            "source_event_id": source_event["event_id"],
            "progress_event_id": progress_event["event_id"],
            "seq": source_event["seq"],
            "evidence_id": terminal_payload["evidence_id"],
        },
        request_id="request-joint-task-progress-ack",
        session_id="session-1",
        channel_id="web",
    )
    assert acknowledged.ok is True, acknowledged.payload

    conversation_adapter.release["request-joint-text"].set()
    conversation_adapter.release["request-joint-voice-revision"].set()
    conversation_adapter.release["request-joint-post-barge"].set()
    await registry.stop()
    assert manager.pins == manager.unpins
    assert not (project / "RESULT-joint.md").exists()
    assert _git(project, "rev-parse", "HEAD") == revision
    await p3_composition.stop()
