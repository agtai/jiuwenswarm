# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import math
import sqlite3
import subprocess
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CONTRACT_VERSION,
    ErrorCode,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskViolation,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskRecord,
    ResolvedTaskContext,
    utc_now,
)
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    AgentManagerProjectBindingResolver,
    AuthenticatedPrincipal,
    P3AuthenticatedComposition,
    P3_OPERATIONS,
    P3RouteTelemetry,
    ResolvedAuthority,
    ServerSessionProjectAuthorityResolver,
    StaticBearerAuthenticator,
    create_p3_composition_from_environment,
)
from jiuwenswarm.server.live_voice.p3_confirmation import (
    P3ConfirmationBinding,
    SqliteP3ConfirmationLedger,
    p3_confirmation_intent_fingerprint,
)
from jiuwenswarm.server.live_voice.p3_model_resolution import (
    ResolvedP3Model,
    ServerModelCatalogResolver,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    FORMAL_PROJECT_EXECUTOR_ID,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.live_voice.voice_task_policy import FormalTaskPolicyAdapter

NOW = "2026-08-05T12:00:00Z"
EXPIRY = "2026-08-05T13:00:00Z"
TOKEN = "test-only-p3-bearer-token-000000000000"


def _scope(*, project_id: str = "project-1", session_id: str = "session-1") -> ScopeRef:
    return ScopeRef("user-1", project_id, session_id, Assurance.AUTHENTICATED)


def _context(
    project: Path,
    *,
    project_id: str = "project-1",
    session_id: str = "session-1",
    expires_at: str = EXPIRY,
    redacted: bool = False,
) -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="agent_server.session_project_registry",
        stable_id=project_id,
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value="a77516a0",
        scope=_scope(project_id=project_id, session_id=session_id),
        permissions=("task.execute", "project.write"),
        expires_at=expires_at,
        redaction_policy_id="live_voice.p3alpha.project.v1",
        redacted=redacted,
        redacted_fields=(("secret",) if redacted else ()),
    )


class _AuthorityResolver:
    def __init__(self, contexts: dict[str, ResolvedTaskContext]) -> None:
        self.contexts = contexts
        self.calls: list[tuple[str, bool]] = []
        self.dirty = False

    def resolve(self, principal, *, session_id: str, now: str, require_clean: bool):
        del now
        self.calls.append((session_id, require_clean))
        if require_clean and self.dirty:
            raise FormalTaskViolation(
                "TASK_CONTEXT_WORKTREE_DIRTY",
                "formal task project must have a clean worktree",
                ErrorCode.PERMISSION_DENIED,
            )
        context = self.contexts.get(session_id)
        if (
            context is None
            or context.scope.project_id not in principal.allowed_project_ids
        ):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal task scope is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        return ResolvedAuthority(principal, context.scope, context)


def _observations(
    item: PersistentOutboxItem,
    *,
    outcome: TerminalOutcome | None = None,
) -> tuple[ExecutorObservation, ...]:
    target_seq = 2 if outcome is not None else 1
    states = (
        (FormalAttemptState.ACCEPTED, None),
        (FormalAttemptState.RUNNING, None),
        (FormalAttemptState.TERMINAL, outcome),
    )
    return tuple(
        ExecutorObservation(
            resolution=ExecutorResolution.KNOWN,
            executor_id=FORMAL_PROJECT_EXECUTOR_ID,
            executor_ref=f"carrier:{item.attempt_id}",
            task_id=item.task_id,
            attempt_id=item.attempt_id,
            source_event_id=f"carrier:{item.attempt_id}:{seq}",
            source_seq=seq,
            attempt_state=states[seq][0],
            attempt_outcome=states[seq][1],
            occurred_at=utc_now(),
            raw_status=("cancelled" if outcome else "running"),
        )
        for seq in range(item.source_seq + 1, target_seq + 1)
    )


class _Executor:
    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(self) -> None:
        self.dispatches: list[str] = []
        self.cancels: list[str] = []
        self.statuses: list[str] = []

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.dispatches.append(item.attempt_id)
        return ExecutorDeliveryResult(f"carrier:{item.attempt_id}", _observations(item))

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.cancels.append(item.attempt_id)
        return ExecutorDeliveryResult(
            f"carrier:{item.attempt_id}",
            _observations(item, outcome=TerminalOutcome.CANCELLED),
        )

    async def status(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorDeliveryResult:
        self.statuses.append(task.task_id)
        return ExecutorDeliveryResult(attempt.executor_ref or "", ())


class _CloseRecorder:
    def __init__(self) -> None:
        self.calls = 0

    async def close(self) -> None:
        self.calls += 1


class _Telemetry:
    def __init__(self) -> None:
        self.events: list[P3RouteTelemetry] = []

    def emit(self, event: P3RouteTelemetry) -> None:
        self.events.append(event)


class _ModelResolver:
    def __init__(self) -> None:
        self.identity = "default#0"
        self.config_version = "catalog-v1"
        self.calls: list[str | None] = []

    def resolve(
        self,
        model_intent: str | None,
        *,
        expected_identity: str | None = None,
        expected_config_version: str | None = None,
        instantiate: bool = False,
    ) -> ResolvedP3Model:
        self.calls.append(model_intent)
        if model_intent not in {None, "default", self.identity}:
            raise FormalTaskViolation(
                "P3_MODEL_INTENT_UNKNOWN",
                "unknown model",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if (expected_identity is not None and expected_identity != self.identity) or (
            expected_config_version is not None
            and expected_config_version != self.config_version
        ):
            raise FormalTaskViolation(
                "EXECUTOR_MODEL_BINDING_DRIFT",
                "model drift",
                ErrorCode.PERMISSION_DENIED,
            )
        return ResolvedP3Model(
            object() if instantiate else None,
            self.identity,
            self.config_version,
        )


@dataclass
class _Harness:
    composition: P3AuthenticatedComposition
    database: Path
    executor: _Executor
    authority: _AuthorityResolver
    closer: _CloseRecorder
    telemetry: _Telemetry
    confirmations: SqliteP3ConfirmationLedger
    models: _ModelResolver


def _principal(
    *,
    expires_at: str = EXPIRY,
    allowed_project_ids: frozenset[str] = frozenset({"project-1", "project-2"}),
    allowed_operations: frozenset[str] = P3_OPERATIONS,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="user-1",
        allowed_project_ids=allowed_project_ids,
        allowed_operations=allowed_operations,
        expires_at=expires_at,
    )


def _harness(
    tmp_path: Path,
    *,
    contexts=None,
    expires_at: str = EXPIRY,
    allowed_project_ids: frozenset[str] = frozenset({"project-1", "project-2"}),
    allowed_operations: frozenset[str] = P3_OPERATIONS,
    commit_ledger: TurnCommitLedger | None = None,
) -> _Harness:
    database = tmp_path / "formal-tasks.sqlite3"
    executor = _Executor()
    authority = _AuthorityResolver(
        contexts
        or {
            "session-1": _context(tmp_path),
            "session-2": _context(
                tmp_path, project_id="project-2", session_id="session-2"
            ),
        }
    )
    closer = _CloseRecorder()
    telemetry = _Telemetry()
    confirmations = SqliteP3ConfirmationLedger(database)
    models = _ModelResolver()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(
            token=TOKEN,
            principal=_principal(
                expires_at=expires_at,
                allowed_project_ids=allowed_project_ids,
                allowed_operations=allowed_operations,
            ),
        ),
        authority_resolver=authority,
        core=PersistentTaskCore(SqliteTaskStore(database), executor),
        confirmation_verifier=confirmations,
        model_resolver=models,
        binding_resolver=closer,
        telemetry=telemetry,
        policy=FormalTaskPolicyAdapter(commit_ledger),
        reconcile_interval=3600,
        clock=lambda: NOW,
    )
    return _Harness(
        composition,
        database,
        executor,
        authority,
        closer,
        telemetry,
        confirmations,
        models,
    )


def _base(session_id: str = "session-1") -> dict[str, object]:
    return {"auth_token": TOKEN, "session_id": session_id}


def _create_params(command_id: str = "command-create") -> dict[str, object]:
    return {
        **_base(),
        "command_id": command_id,
        "confirmation_id": f"forged:{command_id}",
        "issued_at": NOW,
        "correlation_id": f"correlation:{command_id}",
        "name": "Formal project task",
        "instruction": "Create one bounded project change.",
        "model_intent": "default",
    }


def _mutation_params(task_id: str) -> dict[str, object]:
    return {
        **_base(),
        "command_id": "command-cancel",
        "confirmation_id": "forged:command-cancel",
        "issued_at": NOW,
        "correlation_id": "correlation:command-cancel",
        "task_id": task_id,
    }


def _issue_confirmation(
    harness: _Harness,
    params: dict[str, object],
    *,
    operation: str,
    principal_id: str = "user-1",
    scope: ScopeRef | None = None,
    expires_at: str = EXPIRY,
    now: str = NOW,
) -> dict[str, object]:
    target_task_id = str(params["task_id"]) if operation == "task.cancel" else None
    context = (
        harness.authority.contexts[str(params["session_id"])]
        if operation == "task.create"
        else None
    )
    model = (
        ResolvedP3Model(
            object(), harness.models.identity, harness.models.config_version
        )
        if operation == "task.create"
        else None
    )
    command_id = str(params["command_id"])
    binding = P3ConfirmationBinding(
        principal_id=principal_id,
        scope=scope or context.scope if context is not None else scope or _scope(),
        operation=operation,
        command_id=command_id,
        target_task_id=target_task_id,
        intent_fingerprint=p3_confirmation_intent_fingerprint(
            operation=operation,
            command_id=command_id,
            target_task_id=target_task_id,
            context=context,
            name=(str(params["name"]) if operation == "task.create" else None),
            instruction=(
                str(params["instruction"]) if operation == "task.create" else None
            ),
            model=model,
            source=str(params.get("source", "structured")),
            interaction_id=(
                str(params["interaction_id"])
                if "interaction_id" in params
                else None
            ),
            turn_id=(str(params["turn_id"]) if "turn_id" in params else None),
            commit_id=(
                str(params["commit_id"]) if "commit_id" in params else None
            ),
        ),
    )
    params["confirmation_id"] = harness.confirmations.issue(
        binding, expires_at=expires_at, now=now
    )
    return params


def _issued_create_params(
    harness: _Harness, command_id: str = "command-create"
) -> dict[str, object]:
    return _issue_confirmation(
        harness, _create_params(command_id), operation="task.create"
    )


def _issued_cancel_params(harness: _Harness, task_id: str) -> dict[str, object]:
    return _issue_confirmation(
        harness, _mutation_params(task_id), operation="task.cancel"
    )


def _store_counts(database: Path) -> tuple[int, ...]:
    with sqlite3.connect(database) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("tasks", "attempts", "task_events", "outbox", "commands")
        )


async def _wait_until(predicate, *, attempts: int = 100) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not reached")


@pytest.mark.asyncio
async def test_authenticated_six_operation_journey_is_exactly_scoped_and_idempotent(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create",
            session_id="session-1",
        )
        assert created.ok is True
        task_id = created.payload["result"]["task_id"]
        persisted = harness.composition._core.store.get_task(task_id, _scope())
        assert dict(persisted.spec.attributes) == {
            "model_identity": "default#0",
            "model_config_version": "catalog-v1",
        }
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)

        get_result = await harness.composition.handle(
            operation="task.get",
            params={**_base(), "task_id": task_id},
            request_id="request-get",
            session_id="session-1",
        )
        list_result = await harness.composition.handle(
            operation="task.list",
            params=_base(),
            request_id="request-list",
            session_id="session-1",
        )
        status_result = await harness.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-status",
            session_id="session-1",
        )
        events_result = await harness.composition.handle(
            operation="task.events",
            params={**_base(), "task_id": task_id, "after_seq": -1},
            request_id="request-events",
            session_id="session-1",
        )

        assert get_result.payload["result"]["task"]["task_id"] == task_id
        assert [item["task_id"] for item in list_result.payload["result"]["tasks"]] == [
            task_id
        ]
        assert status_result.payload["result"]["attempt"]["executor_ref"].startswith(
            "carrier:"
        )
        assert [
            event["seq"] for event in events_result.payload["result"]["events"]
        ] == [
            0,
            1,
            2,
            3,
        ]

        wrong_scope = await harness.composition.handle(
            operation="task.get",
            params={**_base("session-2"), "task_id": task_id},
            request_id="request-wrong-scope",
            session_id="session-2",
        )
        assert wrong_scope.ok is False
        assert wrong_scope.payload["error"]["code"] == "NOT_FOUND"
        assert task_id not in str(wrong_scope.payload["error"])

        cancelled = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-cancel",
            session_id="session-1",
        )
        assert cancelled.ok is True
        await _wait_until(lambda: len(harness.executor.cancels) == 1)
        await harness.composition.reconcile_once()
        await harness.composition.reconcile_once()
        assert len(harness.executor.dispatches) == 1
        assert len(harness.executor.cancels) == 1
        assert len(harness.telemetry.events) == 7
    finally:
        await harness.composition.stop()
    assert harness.closer.calls == 1


@pytest.mark.asyncio
async def test_voice_task_create_requires_exact_accepted_commit_and_text(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    harness = _harness(tmp_path, commit_ledger=ledger)
    voice_commit = TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": "commit-voice-task",
            "turn_id": "turn-voice-task",
            "interaction_id": "interaction-voice-task",
            "text": "Create one bounded project change.",
            "hypothesis_provenance": {
                "provider": "product.web.voice",
                "kind": "committed_text",
            },
            "scope": _scope().to_dict(),
            "context_refs": [],
            "committed_at": NOW,
        }
    )
    await harness.composition.start()
    try:
        unaccepted = _create_params("command-unaccepted-voice")
        unaccepted.update(
            source="voice",
            interaction_id=voice_commit.interaction_id,
            turn_id=voice_commit.turn_id,
            commit_id=voice_commit.commit_id,
        )
        rejected = await harness.composition.handle(
            operation="task.create",
            params=_issue_confirmation(harness, unaccepted, operation="task.create"),
            request_id="request-unaccepted-voice",
            session_id="session-1",
        )
        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == "TURN_COMMIT_NOT_ACCEPTED"
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)
        assert harness.executor.dispatches == []

        assert ledger.accept(voice_commit) is True
        changed = _create_params("command-changed-voice")
        changed.update(
            source="voice",
            interaction_id=voice_commit.interaction_id,
            turn_id=voice_commit.turn_id,
            commit_id=voice_commit.commit_id,
            instruction="A different instruction must not borrow the commit.",
        )
        changed_result = await harness.composition.handle(
            operation="task.create",
            params=_issue_confirmation(harness, changed, operation="task.create"),
            request_id="request-changed-voice",
            session_id="session-1",
        )
        assert changed_result.ok is False
        assert changed_result.payload["error"]["reason"] == (
            "VOICE_TASK_INSTRUCTION_MISMATCH"
        )
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)
        assert harness.executor.dispatches == []

        exact = _create_params("command-exact-voice")
        exact.update(
            source="voice",
            interaction_id=voice_commit.interaction_id,
            turn_id=voice_commit.turn_id,
            commit_id=voice_commit.commit_id,
        )
        accepted = await harness.composition.handle(
            operation="task.create",
            params=_issue_confirmation(harness, exact, operation="task.create"),
            request_id="request-exact-voice",
            session_id="session-1",
        )
        assert accepted.ok is True
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_invalid_voice_origin_is_rejected_before_durable_confirmation(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    harness = _harness(tmp_path, commit_ledger=ledger)
    params = _create_params("command-invalid-voice-confirmation")
    params.update(
        source="voice",
        interaction_id="interaction-not-accepted",
        turn_id="turn-not-accepted",
        commit_id="commit-not-accepted",
    )
    await harness.composition.start()
    try:
        with pytest.raises(FormalTaskViolation) as raised:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.create",
                params=params,
                session_id="session-1",
            )
        assert raised.value.reason == "TURN_COMMIT_NOT_ACCEPTED"
        with sqlite3.connect(harness.database) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM p3_confirmations"
            ).fetchone()[0] == 0
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)
        assert harness.executor.dispatches == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_registry_uses_real_p3_authority_query_and_subscription_owner(
    tmp_path: Path,
) -> None:
    from jiuwenswarm.server.live_voice.product_composition_registry import (
        AgentServerProductCompositionRegistry,
        ProductCompositionSettings,
    )

    future_expiry = "2100-01-01T00:00:00Z"
    authorized_context = _context(tmp_path, expires_at=future_expiry)
    harness = _harness(
        tmp_path,
        expires_at=future_expiry,
        contexts={
            "session-1": authorized_context,
        },
    )
    pushed: list[dict[str, object]] = []

    async def push(message: dict[str, object]) -> bool:
        pushed.append(message)
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(p2_enabled=False, p3_text_enabled=True),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
    )
    await harness.composition.start()
    try:
        create_params = _issued_create_params(harness, "command-product-owner")
        created = await harness.composition.handle(
            operation="task.create",
            params=create_params,
            request_id="request-product-create",
            session_id="session-1",
        )
        assert created.ok is True
        task_id = str(created.payload["result"]["task_id"])

        queried = await registry.handle_p3_query(
            operation="task.list",
            params=_base(),
            request_id="request-product-list",
            session_id="session-1",
        )
        activated = await registry.handle_p3_progress_activate(
            params={
                **_base(),
                "task_id": task_id,
                "correlation_id": str(create_params["correlation_id"]),
                "origin_id": "web-product-owner",
                "generation_id": "web-product-generation",
                "generation": 1,
            },
            request_id="request-product-progress",
            session_id="session-1",
            channel_id="web",
        )
        closed = await registry.handle_p3_progress_close(
            params={
                **_base(),
                "task_id": task_id,
                "correlation_id": str(create_params["correlation_id"]),
                "origin_id": "web-product-owner",
                "generation_id": "web-product-generation",
                "generation": 1,
            },
            request_id="request-product-progress-close",
            session_id="session-1",
        )

        assert queried.ok is True
        assert activated.ok is True
        assert closed.ok is True
        assert activated.payload["result"]["voice_progress"] == "unavailable"
        assert pushed == []
    finally:
        await registry.stop()
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_registry_uses_real_authority_and_agent_runtime_for_p2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jiuwenswarm.server.live_voice.product_composition_registry import (
        AgentServerProductCompositionRegistry,
        ProductCompositionSettings,
    )

    class Facade:
        def supports_formal_live_voice(self) -> bool:
            return True

        async def process_formal_live_voice_stream(self, _execution):
            if False:
                yield None

    class Manager:
        def __init__(self) -> None:
            self.facade = Facade()
            self.get_calls: list[tuple[object, ...]] = []
            self.pins = 0
            self.unpins = 0

        async def get_agent(self, *args):
            self.get_calls.append(args)
            return self.facade

        def pin_agent(self, agent) -> None:
            assert agent is self.facade
            self.pins += 1

        def unpin_agent(self, agent) -> None:
            assert agent is self.facade
            self.unpins += 1

    future_expiry = "2100-01-01T00:00:00Z"
    authorized_context = _context(tmp_path, expires_at=future_expiry)
    harness = _harness(
        tmp_path,
        expires_at=future_expiry,
        contexts={
            "session-1": authorized_context,
        },
        allowed_operations=P3_OPERATIONS | frozenset({"agent.chat"}),
    )
    manager = Manager()
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("agent", None),
    )

    async def push(_message: dict[str, object]) -> bool:
        raise AssertionError("P2 activation must not use the P3 progress sink")

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(p2_enabled=True, p3_text_enabled=False),
        p3_composition=harness.composition,
        agent_manager=manager,
        push_text_event=push,
    )
    params = {
        **_base(),
        "correlation_id": "correlation-product-p2",
        "interaction_id": "interaction-product-p2",
        "activation_id": "activation-product-p2",
        "activation_generation": 1,
    }
    await harness.composition.start()
    try:
        harness.authority.contexts["session-1"] = replace(
            authorized_context, permissions=()
        )
        denied = await registry.handle_p2_activate(
            params=params,
            request_id="request-product-p2-denied",
            session_id="session-1",
            channel_id="web",
        )
        assert denied.ok is False
        assert manager.get_calls == []

        harness.authority.contexts["session-1"] = authorized_context
        activated = await registry.handle_p2_activate(
            params=params,
            request_id="request-product-p2",
            session_id="session-1",
            channel_id="web",
        )
        closed = await registry.handle_p2_close(
            params=params,
            request_id="request-product-p2-close",
            session_id="session-1",
        )

        assert activated.ok is True
        assert closed.ok is True
        assert len(manager.get_calls) == 1
        assert manager.pins == 1
        assert manager.unpins == 1
    finally:
        await registry.stop()
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_task_dirty_worktree_allows_reads_and_exact_cancel_but_blocks_new_create(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-clean-create",
            session_id="session-1",
        )
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        harness.authority.dirty = True

        operations = {
            "task.get": {**_base(), "task_id": task_id},
            "task.list": _base(),
            "task.status": {**_base(), "task_id": task_id},
            "task.events": {**_base(), "task_id": task_id, "after_seq": -1},
        }
        for operation, params in operations.items():
            result = await harness.composition.handle(
                operation=operation,
                params=params,
                request_id=f"request-dirty-{operation}",
                session_id="session-1",
            )
            assert result.ok is True

        cancelled = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-dirty-cancel",
            session_id="session-1",
        )
        assert cancelled.ok is True
        await _wait_until(lambda: len(harness.executor.cancels) == 1)
        before_new_create = _store_counts(harness.database)

        denied = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-after-dirty"),
            request_id="request-dirty-create",
            session_id="session-1",
        )

        assert denied.payload["error"]["reason"] == "TASK_CONTEXT_WORKTREE_DIRTY"
        assert _store_counts(harness.database) == before_new_create
        assert len(harness.executor.dispatches) == 1
        assert len(harness.executor.cancels) == 1
        assert harness.authority.calls[0] == ("session-1", True)
        assert all(
            require_clean is False
            for _session, require_clean in harness.authority.calls[1:-1]
        )
        assert harness.authority.calls[-1] == ("session-1", True)
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            {"revision_value": "different-revision"},
            "EXECUTION_CONTEXT_REVISION_MISMATCH",
        ),
        ({"redacted": True, "redacted_fields": ("secret",)}, "TASK_CONTEXT_REDACTED"),
    ],
)
async def test_dirty_read_and_cancel_still_fail_closed_on_context_drift(
    tmp_path: Path,
    change: dict[str, object],
    reason: str,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create-context-drift",
            session_id="session-1",
        )
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        harness.authority.dirty = True
        harness.authority.contexts["session-1"] = replace(
            harness.authority.contexts["session-1"], **change
        )
        before = _store_counts(harness.database)

        read = await harness.composition.handle(
            operation="task.get",
            params={**_base(), "task_id": task_id},
            request_id="request-drift-read",
            session_id="session-1",
        )
        listed = await harness.composition.handle(
            operation="task.list",
            params=_base(),
            request_id="request-drift-list",
            session_id="session-1",
        )
        cancel = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-drift-cancel",
            session_id="session-1",
        )

        assert read.payload["error"]["reason"] == reason
        assert listed.payload["error"]["reason"] == reason
        assert cancel.payload["error"]["reason"] == reason
        assert _store_counts(harness.database) == before
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_restart_runs_startup_reconciliation_without_duplicate_dispatch(
    tmp_path: Path,
) -> None:
    first = _harness(tmp_path)
    await first.composition.start()
    created = await first.composition.handle(
        operation="task.create",
        params=_issued_create_params(first),
        request_id="request-create",
        session_id="session-1",
    )
    task_id = created.payload["result"]["task_id"]
    await _wait_until(lambda: len(first.executor.dispatches) == 1)
    await first.composition.stop()

    restarted = _harness(tmp_path)
    await restarted.composition.start()
    try:
        status = await restarted.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-after-restart",
            session_id="session-1",
        )
        await restarted.composition.reconcile_once()
        assert status.ok is True
        assert restarted.executor.dispatches == []
        assert restarted.executor.statuses == [task_id, task_id]
        assert _store_counts(restarted.database)[0] == 1
    finally:
        await restarted.composition.stop()


@pytest.mark.asyncio
async def test_concurrent_cancel_replay_produces_one_carrier_effect(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create",
            session_id="session-1",
        )
        task_id = created.payload["result"]["task_id"]
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)

        cancel_params = _issued_cancel_params(harness, task_id)
        first, replay = await asyncio.gather(
            harness.composition.handle(
                operation="task.cancel",
                params=dict(cancel_params),
                request_id="request-cancel-1",
                session_id="session-1",
            ),
            harness.composition.handle(
                operation="task.cancel",
                params=dict(cancel_params),
                request_id="request-cancel-2",
                session_id="session-1",
            ),
        )
        assert first.ok is True
        assert replay.ok is True
        await _wait_until(lambda: len(harness.executor.cancels) == 1)
        await harness.composition.reconcile_once()
        assert harness.executor.cancels == [harness.executor.dispatches[0]]
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "params", "session_id", "contexts", "expiry", "expected"),
    [
        (
            "unauthenticated",
            {**_create_params(), "auth_token": "wrong"},
            "session-1",
            None,
            EXPIRY,
            "FORMAL_TASK_AUTHENTICATION_REQUIRED",
        ),
        (
            "session-mismatch",
            _create_params(),
            "session-other",
            None,
            EXPIRY,
            "FORMAL_TASK_SESSION_MISMATCH",
        ),
        (
            "expired",
            _create_params(),
            "session-1",
            None,
            "2026-08-05T11:59:59Z",
            "FORMAL_TASK_AUTHORIZATION_EXPIRED",
        ),
        (
            "redacted",
            _create_params(),
            "session-1",
            {"session-1": _context(Path.cwd(), redacted=True)},
            EXPIRY,
            "TASK_CONTEXT_REDACTED",
        ),
    ],
)
async def test_authority_failures_have_zero_persistence_and_executor_effects(
    tmp_path: Path,
    case: str,
    params: dict[str, object],
    session_id: str,
    contexts: dict[str, ResolvedTaskContext] | None,
    expiry: str,
    expected: str,
) -> None:
    del case
    if contexts is not None:
        contexts = {
            key: replace(value, uri=tmp_path.resolve().as_uri())
            for key, value in contexts.items()
        }
    harness = _harness(tmp_path, contexts=contexts, expires_at=expiry)
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        result = await harness.composition.handle(
            operation="task.create",
            params=params,
            request_id="request-rejected",
            session_id=session_id,
        )
        await asyncio.sleep(0)
        assert result.ok is False
        assert result.payload["error"]["reason"] == expected
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_authenticated_wrong_project_scope_fails_before_store_and_executor(
    tmp_path: Path,
) -> None:
    harness = _harness(
        tmp_path,
        allowed_project_ids=frozenset({"project-1"}),
    )
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        denied_create = await harness.composition.handle(
            operation="task.create",
            params={**_create_params(), "session_id": "session-2"},
            request_id="request-wrong-project-create",
            session_id="session-2",
        )
        denied_list = await harness.composition.handle(
            operation="task.list",
            params=_base("session-2"),
            request_id="request-wrong-project-list",
            session_id="session-2",
        )

        assert denied_create.payload["error"]["reason"] == (
            "FORMAL_TASK_AUTHORIZATION_DENIED"
        )
        assert denied_list.payload["error"]["reason"] == (
            "FORMAL_TASK_AUTHORIZATION_DENIED"
        )
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_browser_authority_fields_and_unconfirmed_cancel_fail_before_core(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        claimed = await harness.composition.handle(
            operation="task.create",
            params={**_create_params(), "principal_id": "admin", "project_id": "other"},
            request_id="request-claimed-authority",
            session_id="session-1",
        )
        unconfirmed = await harness.composition.handle(
            operation="task.cancel",
            params={**_mutation_params("task-does-not-exist"), "confirmed": False},
            request_id="request-unconfirmed",
            session_id="session-1",
        )
        assert claimed.payload["error"]["reason"] == "INVALID_P3_ROUTE_ARGUMENT"
        assert unconfirmed.payload["error"]["reason"] == "INVALID_P3_ROUTE_ARGUMENT"
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_confirmation_forgery_cross_binding_and_expiry_have_zero_effects(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        forged_claim = await harness.composition.handle(
            operation="task.create",
            params={**_create_params(), "confirmed": True},
            request_id="request-forged-claim",
            session_id="session-1",
        )
        forged_id = await harness.composition.handle(
            operation="task.create",
            params=_create_params(),
            request_id="request-forged-id",
            session_id="session-1",
        )

        command_bound = _issued_create_params(harness, "command-bound")
        cross_command = await harness.composition.handle(
            operation="task.create",
            params={**command_bound, "command_id": "command-other"},
            request_id="request-cross-command",
            session_id="session-1",
        )

        principal_bound = _issue_confirmation(
            harness,
            _create_params("command-principal"),
            operation="task.create",
            principal_id="user-other",
        )
        cross_principal = await harness.composition.handle(
            operation="task.create",
            params=principal_bound,
            request_id="request-cross-principal",
            session_id="session-1",
        )

        scope_bound = _issue_confirmation(
            harness,
            _create_params("command-scope"),
            operation="task.create",
            scope=_scope(project_id="project-2", session_id="session-2"),
        )
        cross_scope = await harness.composition.handle(
            operation="task.create",
            params=scope_bound,
            request_id="request-cross-scope",
            session_id="session-1",
        )

        expired = _issue_confirmation(
            harness,
            _create_params("command-expired"),
            operation="task.create",
            expires_at="2026-08-05T11:30:00Z",
            now="2026-08-05T11:00:00Z",
        )
        expired_result = await harness.composition.handle(
            operation="task.create",
            params=expired,
            request_id="request-expired-confirmation",
            session_id="session-1",
        )

        assert forged_claim.payload["error"]["reason"] == "INVALID_P3_ROUTE_ARGUMENT"
        assert forged_id.payload["error"]["reason"] == "P3_CONFIRMATION_INVALID"
        for result in (cross_command, cross_principal, cross_scope):
            assert result.payload["error"]["reason"] == (
                "P3_CONFIRMATION_BINDING_MISMATCH"
            )
        assert expired_result.payload["error"]["reason"] == "P3_CONFIRMATION_EXPIRED"
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_confirmation_is_single_use_with_exact_idempotent_replay_only(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        params = _issued_create_params(harness)
        first = await harness.composition.handle(
            operation="task.create",
            params=dict(params),
            request_id="request-create-first",
            session_id="session-1",
        )
        replay = await harness.composition.handle(
            operation="task.create",
            params=dict(params),
            request_id="request-create-replay",
            session_id="session-1",
        )
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        before_conflict = _store_counts(harness.database)
        conflict = await harness.composition.handle(
            operation="task.create",
            params={**params, "command_id": "command-reuse-other"},
            request_id="request-create-reuse-conflict",
            session_id="session-1",
        )

        assert first.ok is True and replay.ok is True
        assert first.payload["result"]["task_id"] == replay.payload["result"]["task_id"]
        assert conflict.payload["error"]["reason"] == (
            "P3_CONFIRMATION_BINDING_MISMATCH"
        )
        assert _store_counts(harness.database) == before_conflict
        assert len(harness.executor.dispatches) == 1
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


def test_confirmation_consumption_and_exact_replay_survive_ledger_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmation-restart.sqlite3"
    binding = P3ConfirmationBinding(
        principal_id="user-1",
        scope=_scope(),
        operation="task.cancel",
        command_id="command-cancel",
        target_task_id="task-1",
        intent_fingerprint=p3_confirmation_intent_fingerprint(
            operation="task.cancel",
            command_id="command-cancel",
            target_task_id="task-1",
            context=None,
        ),
    )
    ledger = SqliteP3ConfirmationLedger(database)
    confirmation_id = ledger.issue(binding, expires_at=EXPIRY, now=NOW)

    first = ledger.verify_and_consume(confirmation_id, binding, now=NOW)
    replay = SqliteP3ConfirmationLedger(database).verify_and_consume(
        confirmation_id, binding, now=NOW
    )

    assert first.replayed is False
    assert replay.replayed is True


@pytest.mark.asyncio
async def test_real_mutation_replay_reauthorizes_current_scope_without_reexecution(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        params = _create_params("command-authorized-replay")
        prepared = await harness.composition.prepare_mutation_confirmation(
            operation="task.create",
            params=params,
            session_id="session-1",
        )
        params["confirmation_id"] = harness.confirmations.issue(
            prepared.binding, expires_at=EXPIRY, now=NOW
        )
        result = await harness.composition.handle(
            operation="task.create",
            params=params,
            request_id="request-authorized-replay",
            session_id="session-1",
        )
        assert result.ok is True
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        before_counts = _store_counts(harness.database)
        before_dispatches = list(harness.executor.dispatches)
        with sqlite3.connect(harness.database) as connection:
            before_confirmations = connection.execute(
                "SELECT COUNT(*) FROM p3_confirmations"
            ).fetchone()[0]

        original_context = harness.authority.contexts["session-1"]
        harness.authority.contexts["session-1"] = replace(
            original_context,
            revision_value="revision-after-task-output",
        )
        await harness.composition.reauthorize_mutation_replay(
            operation="task.create",
            params=params,
            session_id="session-1",
            expected_binding=prepared.binding,
        )

        negative_calls = [
            ("task.create", {**params, "auth_token": "revoked"}, "session-1"),
            ("task.create", {**params, "command_id": "command-drift"}, "session-1"),
            ("task.create", {**params, "session_id": "session-2"}, "session-2"),
        ]
        for operation, changed, session_id in negative_calls:
            with pytest.raises(FormalTaskViolation):
                await harness.composition.reauthorize_mutation_replay(
                    operation=operation,
                    params=changed,
                    session_id=session_id,
                    expected_binding=prepared.binding,
                )

        harness.authority.contexts["session-1"] = _context(
            tmp_path,
            project_id="project-2",
            session_id="session-1",
        )
        with pytest.raises(FormalTaskViolation, match="current authority"):
            await harness.composition.reauthorize_mutation_replay(
                operation="task.create",
                params=params,
                session_id="session-1",
                expected_binding=prepared.binding,
            )
        harness.authority.contexts["session-1"] = original_context

        cancel_binding = replace(
            prepared.binding,
            operation="task.cancel",
            command_id="command-cancel",
            target_task_id="task-1",
        )
        with pytest.raises(FormalTaskViolation, match="current authority"):
            await harness.composition.reauthorize_mutation_replay(
                operation="task.cancel",
                params=_mutation_params("task-2"),
                session_id="session-1",
                expected_binding=cancel_binding,
            )

        assert _store_counts(harness.database) == before_counts
        assert harness.executor.dispatches == before_dispatches
        assert harness.executor.cancels == []
        with sqlite3.connect(harness.database) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM p3_confirmations"
            ).fetchone()[0] == before_confirmations
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_cross_task_confirmation_rejected_without_cancel_effect(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = []
        for suffix in ("one", "two"):
            result = await harness.composition.handle(
                operation="task.create",
                params=_issued_create_params(harness, f"command-{suffix}"),
                request_id=f"request-{suffix}",
                session_id="session-1",
            )
            created.append(str(result.payload["result"]["task_id"]))
        await _wait_until(lambda: len(harness.executor.dispatches) == 2)
        cancel_one = _issued_cancel_params(harness, created[0])
        before = _store_counts(harness.database)

        result = await harness.composition.handle(
            operation="task.cancel",
            params={**cancel_one, "task_id": created[1]},
            request_id="request-cross-task",
            session_id="session-1",
        )

        assert result.payload["error"]["reason"] == ("P3_CONFIRMATION_BINDING_MISMATCH")
        assert _store_counts(harness.database) == before
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_mutation_without_trusted_confirmation_owner_fails_closed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "no-confirmation-owner.sqlite3"
    executor = _Executor()
    authority = _AuthorityResolver({"session-1": _context(tmp_path)})
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=authority,
        core=PersistentTaskCore(SqliteTaskStore(database), executor),
        model_resolver=_ModelResolver(),
        reconcile_interval=3600,
        clock=lambda: NOW,
    )
    await composition.start()
    before = _store_counts(database)
    try:
        result = await composition.handle(
            operation="task.create",
            params=_create_params(),
            request_id="request-no-confirmation-owner",
            session_id="session-1",
        )
        await asyncio.sleep(0)
        assert result.payload["error"]["reason"] == (
            "FORMAL_TASK_CONFIRMATION_REQUIRED"
        )
        assert _store_counts(database) == before
        assert executor.dispatches == []
        assert executor.cancels == []
    finally:
        await composition.stop()


class _ExplodingCore:
    async def reconcile(self):
        return {}

    def query(self, *_args, **_kwargs):
        raise RuntimeError("corrupt store details must not escape")


@pytest.mark.asyncio
async def test_startup_recovers_carrier_before_core_reconciliation() -> None:
    order: list[str] = []

    class Binding:
        async def prepare_startup(self) -> int:
            order.append("carrier")
            return 1

        async def close(self) -> None:
            order.append("close")

    class Core:
        async def reconcile(self):
            if order == ["carrier"]:
                order.append("core")
            else:
                assert order == ["carrier", "core"]
                order.append("shutdown-core")
            return {"reconciled": 1}

    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=Core(),
        binding_resolver=Binding(),
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    summary = await composition.start()
    await composition.stop()

    assert summary == {"reconciled": 1}
    assert order == ["carrier", "core", "shutdown-core", "close"]


@pytest.mark.asyncio
async def test_concurrent_starts_create_one_worker_and_one_startup_reconciliation() -> (
    None
):
    prepare_entered = asyncio.Event()
    prepare_release = asyncio.Event()

    class Binding:
        def __init__(self) -> None:
            self.prepare_calls = 0
            self.close_calls = 0

        async def prepare_startup(self) -> int:
            self.prepare_calls += 1
            prepare_entered.set()
            await prepare_release.wait()
            return 1

        async def close(self) -> None:
            self.close_calls += 1

    class Core:
        def __init__(self) -> None:
            self.reconcile_calls = 0

        async def reconcile(self):
            self.reconcile_calls += 1
            return {"reconciled": self.reconcile_calls}

    binding = Binding()
    core = Core()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=core,
        binding_resolver=binding,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    first = asyncio.create_task(composition.start())
    await prepare_entered.wait()
    second = asyncio.create_task(composition.start())
    prepare_release.set()
    first_result, second_result = await asyncio.gather(first, second)
    worker = composition._worker
    await composition.stop()

    assert first_result == {"reconciled": 1}
    assert second_result == {}
    assert binding.prepare_calls == 1
    assert binding.close_calls == 1
    assert core.reconcile_calls == 2  # startup plus the final shutdown drain
    assert worker is not None and worker.done()


@pytest.mark.asyncio
async def test_stop_wakes_periodic_reconciler_without_cancelling_child_waiter() -> None:
    class Core:
        def __init__(self) -> None:
            self.reconcile_calls = 0

        async def reconcile(self):
            self.reconcile_calls += 1
            return {"reconciled": self.reconcile_calls}

    core = Core()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=core,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    await composition.start()
    worker = composition._worker
    await asyncio.wait_for(composition.stop(), timeout=1)

    assert core.reconcile_calls == 2  # startup plus final shutdown drain
    assert worker is not None and worker.done() and worker.cancelled() is False


@pytest.mark.asyncio
async def test_stop_waits_for_start_and_prevents_post_stop_reactivation() -> None:
    prepare_entered = asyncio.Event()
    prepare_release = asyncio.Event()

    class Binding:
        def __init__(self) -> None:
            self.close_calls = 0

        async def prepare_startup(self) -> int:
            prepare_entered.set()
            await prepare_release.wait()
            return 0

        async def close(self) -> None:
            self.close_calls += 1

    class Core:
        async def reconcile(self):
            return {}

    binding = Binding()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=Core(),
        binding_resolver=binding,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    starting = asyncio.create_task(composition.start())
    await prepare_entered.wait()
    stopping = asyncio.create_task(composition.stop())
    await asyncio.sleep(0)
    assert stopping.done() is False
    prepare_release.set()
    await starting
    await stopping

    assert composition.accepting is False
    assert composition._worker is None
    assert binding.close_calls == 1
    with pytest.raises(FormalTaskViolation) as closed:
        await composition.start()
    assert closed.value.reason == "FORMAL_TASK_ROUTE_DISABLED"


@pytest.mark.asyncio
async def test_shutdown_drains_cancelled_mutation_thread_before_carrier_close(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    original_execute = harness.composition._core.execute
    execute_entered = threading.Event()
    execute_release = threading.Event()

    def blocking_execute(*args, **kwargs):
        execute_entered.set()
        assert execute_release.wait(timeout=5)
        return original_execute(*args, **kwargs)

    harness.composition._core.execute = blocking_execute  # type: ignore[method-assign]
    await harness.composition.start()
    route = asyncio.create_task(
        harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-cancelled-during-store",
            session_id="session-1",
        )
    )
    assert await asyncio.to_thread(execute_entered.wait, 2)
    route.cancel()
    stopping = asyncio.create_task(harness.composition.stop())
    await asyncio.sleep(0)

    assert route.done() is False
    assert stopping.done() is False
    assert harness.closer.calls == 0
    execute_release.set()
    with pytest.raises(asyncio.CancelledError):
        await route
    await stopping

    assert len(harness.executor.dispatches) == 1
    assert harness.closer.calls == 1


@pytest.mark.asyncio
async def test_corruption_fails_closed_without_executor_or_sensitive_error() -> None:
    project = Path.cwd()
    authority = _AuthorityResolver({"session-1": _context(project)})
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=authority,
        core=_ExplodingCore(),
        reconcile_interval=3600,
        clock=lambda: NOW,
    )
    await composition.start()
    try:
        result = await composition.handle(
            operation="task.list",
            params=_base(),
            request_id="request-corrupt",
            session_id="session-1",
        )
        assert result.ok is False
        assert result.payload["error"] == {
            "code": "INTERNAL",
            "reason": "FORMAL_TASK_ROUTE_INTERNAL",
            "message": "formal task route failed closed",
        }
    finally:
        await composition.stop()


def test_flag_off_constructs_no_store_scheduler_or_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "must-not-exist.sqlite3"
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_ENABLED", "0")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_DATABASE", str(database))

    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=lambda _name: None
    )

    assert composition is None
    assert not database.exists()


@pytest.mark.parametrize(
    "interval",
    [math.nan, math.inf, -math.inf, 0.0, -1.0, 3600.0001],
)
def test_composition_rejects_non_finite_or_out_of_range_interval(
    tmp_path: Path, interval: float
) -> None:
    with pytest.raises(ValueError, match=r"\(0, 3600\]"):
        P3AuthenticatedComposition(
            authenticator=StaticBearerAuthenticator(
                token=TOKEN, principal=_principal()
            ),
            authority_resolver=_AuthorityResolver({}),
            core=PersistentTaskCore(
                SqliteTaskStore(tmp_path / f"interval-{repr(interval)}.sqlite3"),
                _Executor(),
            ),
            reconcile_interval=interval,
            clock=lambda: NOW,
        )


@pytest.mark.parametrize("interval", [1e-9, 3600.0])
def test_composition_accepts_reconciliation_interval_boundaries(
    tmp_path: Path, interval: float
) -> None:
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=PersistentTaskCore(
            SqliteTaskStore(tmp_path / f"valid-interval-{interval}.sqlite3"),
            _Executor(),
        ),
        reconcile_interval=interval,
        clock=lambda: NOW,
    )
    assert composition._reconcile_interval == interval


def _configure_enabled_factory(
    monkeypatch: pytest.MonkeyPatch, interval: object
) -> None:
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_ENABLED", "1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID", "user-1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS", "project-1")
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT", "2100-01-01T00:00:00Z"
    )
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS", str(interval))


@pytest.mark.parametrize("interval", ["nan", "inf", "-inf", "0", "-1", "3600.1"])
def test_factory_rejects_non_finite_or_out_of_range_interval(
    monkeypatch: pytest.MonkeyPatch, interval: str
) -> None:
    _configure_enabled_factory(monkeypatch, interval)
    with pytest.raises(FormalTaskViolation) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=_ModelResolver()
        )
    assert raised.value.reason == "INVALID_P3_AUTH_CONFIGURATION"


@pytest.mark.parametrize("interval", [1e-9, 3600.0])
def test_factory_accepts_reconciliation_interval_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interval: float,
) -> None:
    _configure_enabled_factory(monkeypatch, interval)
    database = tmp_path / f"factory-{interval}.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )
    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )

    assert composition is not None
    assert composition._reconcile_interval == interval
    assert type(composition._core.executor) is DirectProjectCodeExecutorAdapter


@pytest.mark.asyncio
async def test_factory_direct_executor_lifecycle_releases_agent_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    database = tmp_path / "direct-lifecycle.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )

    class Manager:
        def __init__(self) -> None:
            self.cleanup_calls = 0

        async def cleanup_live_voice_formal_task_agents(self) -> None:
            self.cleanup_calls += 1

    manager = Manager()
    composition = create_p3_composition_from_environment(
        agent_manager=manager,
        model_resolver=_ModelResolver(),
    )

    assert composition is not None
    await composition.start()
    await composition.stop()
    await composition.stop()

    assert type(composition._core.executor) is DirectProjectCodeExecutorAdapter
    assert manager.cleanup_calls == 1


@pytest.mark.parametrize(
    ("master_enabled", "p2_enabled", "authorized"),
    [(False, True, False), (True, False, False), (True, True, True)],
)
def test_factory_widens_alpha_principal_to_p2_only_behind_both_product_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    master_enabled: bool,
    p2_enabled: bool,
    authorized: bool,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED",
        "1" if master_enabled else "0",
    )
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED",
        "1" if p2_enabled else "0",
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: tmp_path / "product-p2-authority.sqlite3",
    )
    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )
    assert composition is not None

    if authorized:
        principal = composition._authenticator.authenticate(
            TOKEN, operation="agent.chat", now=NOW
        )
        assert principal.allowed_operations >= frozenset({"agent.chat"})
    else:
        with pytest.raises(FormalTaskViolation) as denied:
            composition._authenticator.authenticate(
                TOKEN, operation="agent.chat", now=NOW
            )
        assert denied.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"


def test_incomplete_enabled_gate_fails_before_store_or_carrier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "must-not-exist.sqlite3"
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_ENABLED", "1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_DATABASE", str(database))
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID", raising=False)
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS", raising=False)
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT", raising=False)

    with pytest.raises(FormalTaskViolation) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=lambda _name: None
        )

    assert raised.value.reason == "INVALID_P3_AUTH_CONFIGURATION"
    assert not database.exists()


def test_enabled_gate_rejects_store_artifact_outside_application_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "target-project" / "formal-tasks.sqlite3"
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_ENABLED", "1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID", "user-1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS", "project-1")
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT", "2100-01-01T00:00:00Z"
    )
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_DATABASE", str(database))

    with pytest.raises(FormalTaskViolation) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=lambda _name: None
        )

    assert raised.value.reason == "INVALID_P3_AUTH_CONFIGURATION"
    assert not database.exists()


def test_server_resolver_checks_allow_list_before_project_storage(
    tmp_path: Path,
) -> None:
    project_calls: list[str] = []

    def project_reader(project_id: str):
        project_calls.append(project_id)
        return SimpleNamespace(
            project_id=project_id,
            project_dir=str(tmp_path),
            hidden=False,
            work_mode="code",
        )

    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(tmp_path),
        },
        project_reader=project_reader,
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        worktree_clean_reader=lambda _project_dir: True,
    )
    denied = replace(_principal(), allowed_project_ids=frozenset({"project-2"}))

    with pytest.raises(FormalTaskViolation) as raised:
        resolver.resolve(denied, session_id="session-1", now=NOW, require_clean=False)

    assert raised.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"
    assert project_calls == []

    resolved = resolver.resolve(
        _principal(), session_id="session-1", now=NOW, require_clean=False
    )
    assert resolved.scope == _scope()
    assert resolved.context.revision_value == "a77516a0"
    assert project_calls == ["project-1"]


def test_server_resolver_rejects_false_clean_reader_result(tmp_path: Path) -> None:
    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(tmp_path),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id,
            project_dir=str(tmp_path),
            hidden=False,
            work_mode="code",
        ),
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        worktree_clean_reader=lambda _project_dir: False,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        resolver.resolve(
            _principal(), session_id="session-1", now=NOW, require_clean=True
        )

    assert raised.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"


def test_persisted_context_revalidation_uses_current_grant_expiry_and_redaction(
    tmp_path: Path,
) -> None:
    redacted = False

    def redaction_reader(_session, _project):
        return redacted, (("secret",) if redacted else ())

    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(tmp_path),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id,
            project_dir=str(tmp_path),
            hidden=False,
            work_mode="code",
        ),
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        worktree_clean_reader=lambda _project_dir: True,
        redaction_reader=redaction_reader,
    )
    context = _context(tmp_path)

    assert (
        resolver.revalidate(
            context,
            principal=_principal(),
            now=NOW,
            for_dispatch=True,
        ).project_id
        == "project-1"
    )

    persisted_redacted = replace(
        context,
        redacted=True,
        redacted_fields=("persisted-secret",),
    )
    with pytest.raises(FormalTaskViolation) as persisted_hidden:
        resolver.revalidate(
            persisted_redacted,
            principal=_principal(),
            now=NOW,
            for_dispatch=True,
        )
    assert persisted_hidden.value.reason == "TASK_CONTEXT_REDACTED"

    revoked = replace(_principal(), allowed_project_ids=frozenset({"project-2"}))
    with pytest.raises(FormalTaskViolation) as denied:
        resolver.revalidate(context, principal=revoked, now=NOW, for_dispatch=True)
    assert denied.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"

    expired = replace(_principal(), expires_at="2026-08-05T11:59:59Z")
    with pytest.raises(FormalTaskViolation) as expiry:
        resolver.revalidate(context, principal=expired, now=NOW, for_dispatch=True)
    assert expiry.value.reason == "FORMAL_TASK_AUTHORIZATION_EXPIRED"

    redacted = True
    with pytest.raises(FormalTaskViolation) as hidden:
        resolver.revalidate(context, principal=_principal(), now=NOW, for_dispatch=True)
    assert hidden.value.reason == "TASK_CONTEXT_REDACTED"


def test_default_server_revision_rejects_dirty_worktree(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=project, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=P3 Test",
            "-c",
            "user.email=p3@example.invalid",
            "commit",
            "-qm",
            "seed",
        ],
        cwd=project,
        check=True,
    )
    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(project),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id,
            project_dir=str(project),
            hidden=False,
            work_mode="code",
        ),
    )
    clean_context = resolver.resolve(
        _principal(), session_id="session-1", now=NOW, require_clean=True
    ).context
    (project / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(FormalTaskViolation) as raised:
        resolver.resolve(
            _principal(), session_id="session-1", now=NOW, require_clean=True
        )

    # Source-specific Git state remains existence-hidden at the route boundary.
    assert raised.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"
    assert (
        resolver.revalidate(
            clean_context,
            principal=_principal(),
            now=NOW,
            for_dispatch=False,
        ).project_id
        == "project-1"
    )
    with pytest.raises(FormalTaskViolation) as dispatch:
        resolver.revalidate(
            clean_context,
            principal=_principal(),
            now=NOW,
            for_dispatch=True,
        )
    assert dispatch.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"


@pytest.mark.asyncio
async def test_route_resolves_blocking_authority_off_event_loop(tmp_path: Path) -> None:
    main_thread = threading.get_ident()
    authority = _AuthorityResolver({"session-1": _context(tmp_path)})
    original_resolve = authority.resolve

    def resolve(*args, **kwargs):
        assert threading.get_ident() != main_thread
        return original_resolve(*args, **kwargs)

    authority.resolve = resolve  # type: ignore[method-assign]
    harness = _harness(tmp_path)
    harness.composition._authority_resolver = authority
    await harness.composition.start()
    try:
        result = await harness.composition.handle(
            operation="task.list",
            params=_base(),
            request_id="request-threaded-authority",
            session_id="session-1",
        )
    finally:
        await harness.composition.stop()

    assert result.ok is True


@pytest.mark.asyncio
async def test_non_dispatch_binding_has_no_agent_or_model_side_effects(
    tmp_path: Path,
) -> None:
    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(tmp_path),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Manager:
        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            raise AssertionError("non-dispatch binding must not create an Agent")

    models = _ModelResolver()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=Manager(),
        service=object(),
        model_resolver=models,
        principal=_principal(),
        clock=lambda: NOW,
    )

    binding = await resolver.resolve(
        SimpleNamespace(
            context=object(),
            attributes=(
                ("model_identity", "demo#0"),
                ("model_config_version", "catalog-demo"),
            ),
        ),
        for_dispatch=False,
    )

    assert binding.model is None
    assert binding.model_identity == "demo#0"
    assert binding.model_config_version == "catalog-demo"
    assert binding.execution_agent is None
    assert binding.project_executor is None
    assert models.calls == []


@pytest.mark.asyncio
async def test_dirty_dispatch_fails_before_model_agent_or_carrier(
    tmp_path: Path,
) -> None:
    class Authority:
        def revalidate(self, _context, **kwargs):
            assert kwargs["for_dispatch"] is True
            raise FormalTaskViolation(
                "TASK_CONTEXT_WORKTREE_DIRTY",
                "formal task project must have a clean worktree",
                ErrorCode.PERMISSION_DENIED,
            )

    class Manager:
        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            raise AssertionError("dirty dispatch must fail before Agent creation")

    class Models:
        def resolve(self, *_args, **_kwargs):
            raise AssertionError("dirty dispatch must fail before model resolution")

    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=Manager(),
        service=object(),
        model_resolver=Models(),
        principal=_principal(),
        clock=lambda: NOW,
    )
    spec = SimpleNamespace(
        context=object(),
        attributes=(
            ("model_identity", "default#0"),
            ("model_config_version", "catalog-v1"),
        ),
    )

    with pytest.raises(FormalTaskViolation) as raised:
        await resolver.resolve(spec, for_dispatch=True)

    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"


@pytest.mark.asyncio
async def test_dispatch_handoff_fence_rechecks_clean_state_before_attempt_agent_setup(
    tmp_path: Path,
) -> None:
    class Authority:
        def __init__(self) -> None:
            self.calls = 0

        def revalidate(self, _context, **kwargs):
            assert kwargs["for_dispatch"] is True
            self.calls += 1
            if self.calls == 2:
                raise FormalTaskViolation(
                    "TASK_CONTEXT_WORKTREE_DIRTY",
                    "formal task project became dirty before handoff",
                    ErrorCode.PERMISSION_DENIED,
                )
            return SimpleNamespace(
                project_dir=str(tmp_path),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Agent:
        def get_project_execution_root(self) -> str:
            return str(tmp_path)

        def get_instance(self):
            return object()

        async def process_background_code_task_stream(self):
            return None

    class Manager:
        def __init__(self) -> None:
            self.calls = 0

        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            self.calls += 1
            return Agent()

    authority = Authority()
    manager = Manager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=authority,
        agent_manager=manager,
        service=object(),
        model_resolver=_ModelResolver(),
        principal=_principal(),
        clock=lambda: NOW,
    )
    binding = await resolver.resolve(
        SimpleNamespace(
            context=object(),
            attributes=(
                ("model_identity", "default#0"),
                ("model_config_version", "catalog-v1"),
            ),
        ),
        for_dispatch=True,
    )

    assert binding.dispatch_fence is not None
    with pytest.raises(FormalTaskViolation) as raised:
        await binding.dispatch_fence()
    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"
    assert authority.calls == 2
    assert manager.calls == 0
    assert binding.context_release is None


@pytest.mark.asyncio
async def test_dispatch_creates_and_retires_agent_at_exact_attempt_root(
    tmp_path: Path,
) -> None:
    authority_root = tmp_path / "authority"
    attempt_root = tmp_path / "attempt"
    for root in (authority_root, attempt_root):
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=P3 Test", "-c",
                "user.email=p3@example.invalid", "commit", "-qm", "seed",
            ],
            cwd=root,
            check=True,
        )

    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(authority_root),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Agent:
        def get_project_execution_root(self) -> str:
            return str(attempt_root)

        def get_instance(self):
            return object()

        async def process_background_code_task_stream(self, request):
            assert request.params["project_dir"] == str(attempt_root)
            yield SimpleNamespace(is_complete=True, value="completed")

    class Manager:
        def __init__(self) -> None:
            self.agent = Agent()
            self.created: list[str] = []
            self.cleaned: list[tuple[str, object]] = []

        async def get_live_voice_formal_task_agent(self, project_dir: str):
            self.created.append(project_dir)
            return self.agent

        async def cleanup_live_voice_formal_task_agent(
            self, project_dir: str, *, expected_agent: object
        ) -> bool:
            self.cleaned.append((project_dir, expected_agent))
            return True

    manager = Manager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=manager,
        service=object(),
        model_resolver=_ModelResolver(),
        principal=_principal(),
        clock=lambda: NOW,
    )
    binding = await resolver.resolve(
        SimpleNamespace(
            context=object(),
            attributes=(
                ("model_identity", "default#0"),
                ("model_config_version", "catalog-v1"),
            ),
        ),
        for_dispatch=True,
    )
    request = SimpleNamespace(params={"project_dir": str(attempt_root)})

    chunks = [
        chunk
        async for chunk in binding.project_executor.process_background_code_task_stream(
            request
        )
    ]

    assert [chunk.value for chunk in chunks] == ["completed"]
    assert manager.created == [str(attempt_root)]
    assert manager.cleaned == [(str(attempt_root), manager.agent)]
    assert binding.effective_execution_root == str(authority_root)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation_phase", "expected_reason"),
    [
        ("setup", "PROJECT_EXECUTOR_AGENT_SETUP_MUTATED_TARGET"),
        ("post_terminal", "PROJECT_EXECUTOR_AGENT_POST_TERMINAL_MUTATION"),
        ("cleanup", "PROJECT_EXECUTOR_AGENT_CLEANUP_MUTATED_TARGET"),
    ],
)
async def test_attempt_agent_lifecycle_changes_never_become_authority_output(
    tmp_path: Path,
    mutation_phase: str,
    expected_reason: str,
) -> None:
    authority_root = tmp_path / "authority"
    attempt_root = tmp_path / "attempt"
    for root in (authority_root, attempt_root):
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / "tracked.txt").write_bytes(b"baseline\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=P3 Test", "-c",
                "user.email=p3@example.invalid", "commit", "-qm", "seed",
            ],
            cwd=root,
            check=True,
        )
    authority_bytes = (authority_root / "tracked.txt").read_bytes()
    authority_status = subprocess.run(
        ["git", "status", "--porcelain=v2", "-z"],
        cwd=authority_root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout

    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(authority_root),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Agent:
        def get_project_execution_root(self) -> str:
            return str(attempt_root)

        def get_instance(self):
            if mutation_phase == "setup":
                (attempt_root / "setup.txt").write_text("setup\n", encoding="utf-8")
            return object()

        async def process_background_code_task_stream(self, _request):
            (attempt_root / "result.txt").write_text("task\n", encoding="utf-8")
            yield SimpleNamespace(is_complete=True)
            if mutation_phase == "post_terminal":
                (attempt_root / "late.txt").write_text("late\n", encoding="utf-8")

    class Manager:
        def __init__(self) -> None:
            self.agent = Agent()

        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            return self.agent

        async def cleanup_live_voice_formal_task_agent(
            self, _project_dir: str, *, expected_agent: object
        ) -> bool:
            assert expected_agent is self.agent
            if mutation_phase == "cleanup":
                (attempt_root / "cleanup.txt").write_text(
                    "cleanup\n", encoding="utf-8"
                )
            return True

    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=Manager(),
        service=object(),
        model_resolver=_ModelResolver(),
        principal=_principal(),
        clock=lambda: NOW,
    )
    binding = await resolver.resolve(
        SimpleNamespace(
            context=object(),
            attributes=(
                ("model_identity", "default#0"),
                ("model_config_version", "catalog-v1"),
            ),
        ),
        for_dispatch=True,
    )
    chunks = []
    with pytest.raises(RuntimeError, match=expected_reason):
        async for chunk in binding.project_executor.process_background_code_task_stream(
            SimpleNamespace(params={"project_dir": str(attempt_root)})
        ):
            chunks.append(chunk)

    assert len(chunks) == (0 if mutation_phase == "setup" else 1)
    assert (authority_root / "tracked.txt").read_bytes() == authority_bytes
    assert subprocess.run(
        ["git", "status", "--porcelain=v2", "-z"],
        cwd=authority_root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout == authority_status


@pytest.mark.asyncio
async def test_unknown_model_fails_before_store_executor_or_agent(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        result = await harness.composition.handle(
            operation="task.create",
            params={**_create_params(), "model_intent": "missing-model"},
            request_id="request-unknown-model",
            session_id="session-1",
        )
        await asyncio.sleep(0)
        assert result.payload["error"]["reason"] == "P3_MODEL_INTENT_UNKNOWN"
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


def test_exact_model_catalog_rejects_unknown_and_ambiguous_without_building() -> None:
    build_calls: list[str] = []

    def build_model(client, _config):
        build_calls.append(str(client["model_name"]))
        return object()

    catalog = [
        {
            "model_client_config": {"model_name": "same"},
            "model_config_obj": {"temperature": 0.1},
            "is_default": True,
        },
        {
            "model_client_config": {"model_name": "same"},
            "model_config_obj": {"temperature": 0.2},
        },
    ]
    resolver = ServerModelCatalogResolver(
        catalog_reader=lambda: catalog,
        model_builder=build_model,
    )

    with pytest.raises(FormalTaskViolation) as unknown:
        resolver.resolve("missing")
    with pytest.raises(FormalTaskViolation) as ambiguous:
        resolver.resolve("same")

    assert unknown.value.reason == "P3_MODEL_INTENT_UNKNOWN"
    assert ambiguous.value.reason == "P3_MODEL_INTENT_AMBIGUOUS"
    assert build_calls == []

    metadata = resolver.resolve("same#0")
    resolved = resolver.resolve(
        metadata.identity,
        expected_identity=metadata.identity,
        expected_config_version=metadata.config_version,
        instantiate=True,
    )
    assert metadata.model is None
    assert resolved.model is not None
    assert build_calls == ["same"]


def test_multi_model_catalog_uses_first_server_model_group_default() -> None:
    catalog = [
        {
            "model_client_config": {"model_name": "alpha", "variant": "secondary"},
            "is_default": False,
        },
        {
            "model_client_config": {"model_name": "alpha", "variant": "primary"},
            "is_default": True,
        },
        {
            "model_client_config": {"model_name": "beta"},
            "is_default": True,
        },
    ]
    resolver = ServerModelCatalogResolver(
        catalog_reader=lambda: catalog,
        model_builder=lambda client, _config: dict(client),
    )

    resolved = resolver.resolve(None, instantiate=True)

    assert resolved.identity == "alpha#1"
    assert resolved.model == {"model_name": "alpha", "variant": "primary"}


@pytest.mark.asyncio
@pytest.mark.parametrize("drift_kind", ["default", "config"])
async def test_default_change_and_model_config_drift_fail_before_agent_or_carrier(
    tmp_path: Path,
    drift_kind: str,
) -> None:
    catalog = [
        {
            "model_client_config": {"model_name": "alpha"},
            "model_config_obj": {"temperature": 0.1},
            "is_default": True,
        },
        {
            "model_client_config": {"model_name": "beta"},
            "model_config_obj": {"temperature": 0.2},
        },
    ]
    model_builds: list[str] = []

    def build_model(client, config):
        model_builds.append(str(client["model_name"]))
        return dict(client), dict(config)

    resolver = ServerModelCatalogResolver(
        catalog_reader=lambda: catalog,
        model_builder=build_model,
    )
    admitted = resolver.resolve(None)
    if drift_kind == "default":
        catalog[0]["is_default"] = False
        catalog[1]["is_default"] = True
    else:
        catalog[0]["model_config_obj"] = {"temperature": 0.9}

    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(tmp_path),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Manager:
        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            raise AssertionError("model drift must fail before Agent creation")

    binding_resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=Manager(),
        service=object(),
        model_resolver=resolver,
        principal=_principal(),
        clock=lambda: NOW,
    )
    spec = SimpleNamespace(
        context=object(),
        attributes=(
            ("model_identity", admitted.identity),
            ("model_config_version", admitted.config_version),
        ),
    )

    with pytest.raises(FormalTaskViolation) as drift:
        await binding_resolver.resolve(spec, for_dispatch=True)

    assert drift.value.reason == "EXECUTOR_MODEL_BINDING_DRIFT"
    assert model_builds == []


@pytest.mark.asyncio
async def test_binding_shutdown_releases_contexts_and_agents_after_scheduler_failure() -> (
    None
):
    class FailingService:
        def __init__(self) -> None:
            self.clear_calls = 0

        async def stop_scheduler(self, *, interrupt_running: bool = False) -> None:
            assert interrupt_running is True
            raise RuntimeError("scheduler stop failed")

        def clear_scheduled_task_execution_contexts(self) -> None:
            self.clear_calls += 1

    class Manager:
        def __init__(self) -> None:
            self.cleanup_calls = 0

        async def cleanup_live_voice_formal_task_agents(self) -> None:
            self.cleanup_calls += 1

    service = FailingService()
    manager = Manager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=ServerSessionProjectAuthorityResolver(
            session_reader=lambda _session_id: None
        ),
        agent_manager=manager,
        service=service,
        model_resolver=_ModelResolver(),
        principal=_principal(),
        clock=lambda: NOW,
    )

    await resolver.close()
    await resolver.close()

    assert service.clear_calls == 1
    assert manager.cleanup_calls == 1
