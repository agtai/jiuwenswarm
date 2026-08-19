# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
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
    ExecutorRetryReadiness,
    FormalAttemptState,
    FormalTaskViolation,
    OutboxState,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskRecord,
    ReconciliationState,
    ResolvedTaskContext,
    TaskAdjustmentDeliveryResult,
    TaskAdjustmentSettlement,
    TaskAdjustmentState,
    utc_now,
)
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    AgentManagerProjectBindingResolver,
    AuthenticatedPrincipal,
    P3AuthenticatedComposition,
    P3_MUTATIONS,
    P3_OPERATIONS,
    P3_ROUTE_METHODS,
    P3_TARGETED_MUTATIONS,
    P3RouteTelemetry,
    ResolvedAuthority,
    ServerSessionProjectAuthorityResolver,
    StaticBearerAuthenticator,
    create_p3_composition_from_environment,
)
from jiuwenswarm.server.live_voice.p3_confirmation import (
    P3ConfirmationBinding,
    PreparedP3RetryFacts,
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
            raw_status=(outcome.value if outcome is not None else "running"),
        )
        for seq in range(item.source_seq + 1, target_seq + 1)
    )


class _Executor:
    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(self) -> None:
        self.dispatches: list[str] = []
        self.cancels: list[str] = []
        self.statuses: list[str] = []
        self.adjustments: list[str] = []
        self.adjustment_settlements: list[tuple[str, TaskAdjustmentState]] = []
        self.readiness: list[tuple[str, str]] = []
        self.retry_ready = True
        self.dispatch_outcome: TerminalOutcome | None = None

    def retry_readiness(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorRetryReadiness:
        self.readiness.append((task.task_id, attempt.attempt_id))
        assert attempt.outcome is not None
        return ExecutorRetryReadiness(
            task_id=task.task_id,
            previous_attempt_id=attempt.attempt_id,
            previous_outcome=attempt.outcome,
            previous_attempt_number=attempt.attempt_number,
            ready=self.retry_ready,
            reason=(
                "PREDECESSOR_QUIESCENT"
                if self.retry_ready
                else "ATTEMPT_CLEANUP_RETAINED"
            ),
        )

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.dispatches.append(item.attempt_id)
        return ExecutorDeliveryResult(
            f"carrier:{item.attempt_id}",
            _observations(item, outcome=self.dispatch_outcome),
        )

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.cancels.append(item.attempt_id)
        return ExecutorDeliveryResult(
            f"carrier:{item.attempt_id}",
            _observations(item, outcome=TerminalOutcome.CANCELLED),
        )

    async def adjust(self, item: PersistentOutboxItem) -> TaskAdjustmentDeliveryResult:
        assert item.adjustment is not None
        self.adjustments.append(item.adjustment.adjustment_id)
        return TaskAdjustmentDeliveryResult(
            f"carrier:{item.attempt_id}",
            item.adjustment.adjustment_id,
            TaskAdjustmentState.APPLIED,
        )

    async def settle_adjustment(
        self,
        item: PersistentOutboxItem,
        settlement: TaskAdjustmentSettlement,
    ) -> None:
        self.adjustment_settlements.append((item.command_id, settlement.state))

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


def _adjust_params(
    task_id: str, command_id: str = "command-adjust"
) -> dict[str, object]:
    return {
        **_base(),
        "command_id": command_id,
        "confirmation_id": f"forged:{command_id}",
        "issued_at": NOW,
        "correlation_id": f"correlation:{command_id}",
        "task_id": task_id,
        "instruction": "Change the dinner reservation to 19:00.",
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
    target_task_id = (
        str(params["task_id"]) if operation in P3_TARGETED_MUTATIONS else None
    )
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
                str(params["instruction"])
                if operation in {"task.create", "task.adjust"}
                else None
            ),
            model=model,
            source=str(params.get("source", "structured")),
            interaction_id=(
                str(params["interaction_id"]) if "interaction_id" in params else None
            ),
            turn_id=(str(params["turn_id"]) if "turn_id" in params else None),
            commit_id=(str(params["commit_id"]) if "commit_id" in params else None),
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


def test_p2_response_generation_owner_is_lazy_and_bound_to_the_task_store(
    tmp_path: Path,
) -> None:
    first = _harness(tmp_path)
    sidecar = tmp_path / "formal-tasks.sqlite3.p2-response-generations.sqlite3"

    assert first.composition._p2_response_generation_database == sidecar
    assert first.composition._p2_response_generation_owner is None
    assert sidecar.exists() is False
    assert (
        first.composition.next_product_p2_response_generation(
            "session-generation",
            "interaction-generation",
            -1,
        )
        == 0
    )
    assert sidecar.is_file()

    restarted = _harness(tmp_path)
    assert restarted.composition._p2_response_generation_owner is None
    assert (
        restarted.composition.next_product_p2_response_generation(
            "session-generation",
            "interaction-generation",
            -1,
        )
        == 1
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
        result_result = await harness.composition.handle(
            operation="task.result",
            params={**_base(), "task_id": task_id},
            request_id="request-result",
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
        assert result_result.ok is True
        assert result_result.payload["result"] == {
            "availability": "not_ready",
            "reason": "TASK_RESULT_NOT_READY",
            "task_id": task_id,
            "task_result": None,
        }

        wrong_scope = await harness.composition.handle(
            operation="task.get",
            params={**_base("session-2"), "task_id": task_id},
            request_id="request-wrong-scope",
            session_id="session-2",
        )
        wrong_scope_result = await harness.composition.handle(
            operation="task.result",
            params={**_base("session-2"), "task_id": task_id},
            request_id="request-wrong-scope-result",
            session_id="session-2",
        )
        assert wrong_scope_result.ok is False
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
        assert len(harness.telemetry.events) == 9
    finally:
        await harness.composition.stop()
    assert harness.closer.calls == 1


@pytest.mark.asyncio
async def test_authenticated_task_list_preserves_page_continuation_metadata(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_ids: set[str] = set()
        for suffix in ("one", "two"):
            created = await harness.composition.handle(
                operation="task.create",
                params=_issued_create_params(harness, f"command-page-{suffix}"),
                request_id=f"request-page-create-{suffix}",
                session_id="session-1",
            )
            assert created.ok is True
            task_ids.add(str(created.payload["result"]["task_id"]))

        first = await harness.composition.handle(
            operation="task.list",
            params={**_base(), "limit": 1},
            request_id="request-page-one",
            session_id="session-1",
        )
        assert first.ok is True
        first_page = first.payload["result"]
        assert first_page["cursor"] is None
        assert first_page["limit"] == 1
        assert first_page["has_more"] is True
        assert first_page["next_cursor"] == first_page["tasks"][0]["task_id"]

        second = await harness.composition.handle(
            operation="task.list",
            params={
                **_base(),
                "cursor": first_page["next_cursor"],
                "limit": 1,
            },
            request_id="request-page-two",
            session_id="session-1",
        )
        assert second.ok is True
        second_page = second.payload["result"]
        assert second_page["cursor"] == first_page["next_cursor"]
        assert second_page["limit"] == 1
        assert second_page["has_more"] is False
        assert second_page["next_cursor"] is None
        assert {
            first_page["tasks"][0]["task_id"],
            second_page["tasks"][0]["task_id"],
        } == task_ids
    finally:
        await harness.composition.stop()


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
async def test_trusted_demo_bypass_requires_unified_voice_current_binding(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    harness = _harness(tmp_path, commit_ledger=ledger)
    await harness.composition.start()
    try:
        structured = _create_params("command-structured-bypass")
        structured.pop("confirmation_id")
        forbidden = await harness.composition.handle(
            operation="task.create",
            params=structured,
            request_id="request-structured-bypass",
            session_id="session-1",
            trusted_demo_policy_bypass=True,
            current_background_session_id="session-1",
        )
        assert forbidden.ok is False
        assert forbidden.payload["error"]["reason"] == (
            "TRUSTED_DEMO_POLICY_BYPASS_FORBIDDEN"
        )
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)

        create_commit = TurnCommit.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "commit_id": "commit-demo-create",
                "turn_id": "turn-demo-create",
                "interaction_id": "interaction-demo",
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
        assert ledger.accept(create_commit) is True
        create_params = _create_params("command-demo-create")
        create_params.pop("confirmation_id")
        create_params.update(
            source="voice",
            interaction_id=create_commit.interaction_id,
            turn_id=create_commit.turn_id,
            commit_id=create_commit.commit_id,
            origin_commit_sha256=hashlib.sha256(
                create_commit.canonical_bytes()
            ).hexdigest(),
            source_start=0,
            source_end=len(create_commit.text),
        )
        created = await harness.composition.handle(
            operation="task.create",
            params=create_params,
            request_id="request-demo-create",
            session_id="session-1",
            trusted_demo_policy_bypass=True,
            current_background_session_id="session-1",
        )
        assert created.ok is True
        task_id = created.payload["result"]["task_id"]
        current = await harness.composition.read_current_background_task(
            bearer_token=TOKEN,
            session_id="session-1",
        )
        assert current is not None and current.task_id == task_id
        current_result = await harness.composition.handle(
            operation="task.result",
            params={**_base(), "task_id": task_id},
            request_id="request-demo-current-result",
            session_id="session-1",
        )
        assert current_result.ok is True
        assert current_result.payload["result"] == {
            "task_id": task_id,
            "availability": "not_ready",
            "reason": "TASK_RESULT_NOT_READY",
            "task_result": None,
        }

        cancel_commit = TurnCommit.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "commit_id": "commit-demo-cancel",
                "turn_id": "turn-demo-cancel",
                "interaction_id": "interaction-demo",
                "text": "停止刚才的后台任务。",
                "hypothesis_provenance": {
                    "provider": "product.web.voice",
                    "kind": "committed_text",
                },
                "scope": _scope().to_dict(),
                "context_refs": [],
                "committed_at": NOW,
            }
        )
        assert ledger.accept(cancel_commit) is True
        cancel_params = _mutation_params(task_id)
        cancel_params.pop("confirmation_id")
        cancel_params.update(
            source="voice",
            interaction_id=cancel_commit.interaction_id,
            turn_id=cancel_commit.turn_id,
            commit_id=cancel_commit.commit_id,
            origin_commit_sha256=hashlib.sha256(
                cancel_commit.canonical_bytes()
            ).hexdigest(),
            source_start=0,
            source_end=len(cancel_commit.text),
        )
        wrong_binding = await harness.composition.handle(
            operation="task.cancel",
            params=cancel_params,
            request_id="request-demo-cancel-wrong-target",
            session_id="session-1",
            trusted_demo_policy_bypass=True,
            trusted_current_task_id="task-wrong-current",
        )
        assert wrong_binding.ok is False
        assert wrong_binding.payload["error"]["reason"] == (
            "CURRENT_BACKGROUND_TASK_MISMATCH"
        )
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).cancel_requested
            is False
        )

        cancelled = await harness.composition.handle(
            operation="task.cancel",
            params=cancel_params,
            request_id="request-demo-cancel",
            session_id="session-1",
            trusted_demo_policy_bypass=True,
            trusted_current_task_id=task_id,
        )
        assert cancelled.ok is True
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).cancel_requested
            is True
        )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_authenticated_addressed_adjust_can_target_noncurrent_task(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_ids: list[str] = []
        for suffix in ("first", "current"):
            created = await harness.composition.handle(
                operation="task.create",
                params=_issued_create_params(
                    harness, f"command-create-adjust-{suffix}"
                ),
                request_id=f"request-create-adjust-{suffix}",
                session_id="session-1",
                current_background_session_id="session-1",
            )
            assert created.ok is True
            task_ids.append(str(created.payload["result"]["task_id"]))
        await _wait_until(lambda: len(harness.executor.dispatches) == 2)

        store = harness.composition._core.store
        noncurrent_task_id, current_task_id = task_ids
        selection = store.get_current_background_task(_scope(), session_id="session-1")
        assert selection is not None and selection.task_id == current_task_id
        current_before = store.get_task(current_task_id, _scope())
        assert current_before is not None

        params = _issue_confirmation(
            harness,
            _adjust_params(noncurrent_task_id, "command-adjust-addressed"),
            operation="task.adjust",
        )
        adjusted = await harness.composition.handle(
            operation="task.adjust",
            params=params,
            request_id="request-adjust-addressed",
            session_id="session-1",
        )

        assert adjusted.ok is True
        assert adjusted.payload["result"]["task_id"] == noncurrent_task_id
        await _wait_until(
            lambda: harness.executor.adjustments == ["command-adjust-addressed"]
        )
        noncurrent_events = store.events(noncurrent_task_id, _scope(), after_seq=-1)
        assert [
            event.event_type
            for event in noncurrent_events
            if event.event_type.startswith("task.adjust_")
        ] == ["task.adjust_requested", "task.adjust_applied"]
        current_after = store.get_task(current_task_id, _scope())
        assert current_after is not None
        assert current_after.event_head == current_before.event_head
        assert not any(
            event.event_type.startswith("task.adjust_")
            for event in store.events(current_task_id, _scope(), after_seq=-1)
        )
        selection = store.get_current_background_task(_scope(), session_id="session-1")
        assert selection is not None and selection.task_id == current_task_id
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_task_adjust_requires_exact_current_binding_and_reaches_core(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    harness = _harness(tmp_path, commit_ledger=ledger)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-create-for-adjust"),
            request_id="request-create-for-adjust",
            session_id="session-1",
            current_background_session_id="session-1",
        )
        assert created.ok is True
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        before_rejection = _store_counts(harness.database)

        oversized = _adjust_params(task_id, "command-adjust-oversized")
        oversized["instruction"] = "好" * 1_366
        oversized_result = await harness.composition.handle(
            operation="task.adjust",
            params=oversized,
            request_id="request-adjust-oversized",
            session_id="session-1",
            current_background_session_id="session-1",
            trusted_current_task_id=task_id,
        )
        assert oversized_result.ok is False
        assert oversized_result.payload["error"]["reason"] == (
            "INVALID_TASK_ADJUSTMENT"
        )
        assert _store_counts(harness.database) == before_rejection

        def voice_adjust(command_id: str) -> dict[str, object]:
            params = _adjust_params(task_id, command_id)
            commit = TurnCommit.from_dict(
                {
                    "contract_version": CONTRACT_VERSION,
                    "commit_id": f"commit:{command_id}",
                    "turn_id": f"turn:{command_id}",
                    "interaction_id": "interaction-adjust",
                    "text": params["instruction"],
                    "hypothesis_provenance": {
                        "provider": "product.web.voice",
                        "kind": "committed_text",
                    },
                    "scope": _scope().to_dict(),
                    "context_refs": [],
                    "committed_at": NOW,
                }
            )
            assert ledger.accept(commit) is True
            params.update(
                source="voice",
                interaction_id=commit.interaction_id,
                turn_id=commit.turn_id,
                commit_id=commit.commit_id,
                origin_commit_sha256=hashlib.sha256(
                    commit.canonical_bytes()
                ).hexdigest(),
                source_start=0,
                source_end=len(commit.text),
            )
            return _issue_confirmation(harness, params, operation="task.adjust")

        wrong_session_params = voice_adjust("command-adjust-wrong-session")
        wrong_session = await harness.composition.handle(
            operation="task.adjust",
            params=wrong_session_params,
            request_id="request-adjust-wrong-session",
            session_id="session-1",
            current_background_session_id="session-2",
            trusted_current_task_id=task_id,
        )
        assert wrong_session.ok is False
        assert wrong_session.payload["error"]["reason"] == (
            "CURRENT_BACKGROUND_TASK_BINDING_REQUIRED"
        )
        assert _store_counts(harness.database) == before_rejection

        wrong_task_params = voice_adjust("command-adjust-wrong-task")
        wrong_task = await harness.composition.handle(
            operation="task.adjust",
            params=wrong_task_params,
            request_id="request-adjust-wrong-task",
            session_id="session-1",
            current_background_session_id="session-1",
            trusted_current_task_id="task-not-current",
        )
        assert wrong_task.ok is False
        assert wrong_task.payload["error"]["reason"] == (
            "CURRENT_BACKGROUND_TASK_MISMATCH"
        )
        assert _store_counts(harness.database) == before_rejection

        exact_params = voice_adjust("command-adjust-exact")
        exact = await harness.composition.handle(
            operation="task.adjust",
            params=exact_params,
            request_id="request-adjust-exact",
            session_id="session-1",
            current_background_session_id="session-1",
            trusted_current_task_id=task_id,
        )
        assert exact.ok is True
        assert exact.payload["result"]["adjustment_state"] == "pending"
        await _wait_until(
            lambda: harness.executor.adjustments == ["command-adjust-exact"]
        )
        await _wait_until(
            lambda: (
                harness.executor.adjustment_settlements
                == [("command-adjust-exact", TaskAdjustmentState.APPLIED)]
            )
        )
        adjustment_events = [
            event
            for event in harness.composition._core.store.events(
                task_id, _scope(), after_seq=-1
            )
            if event.event_type.startswith("task.adjust_")
        ]
        assert [event.event_type for event in adjustment_events] == [
            "task.adjust_requested",
            "task.adjust_applied",
        ]
        assert all(
            event.causation_id == "command-adjust-exact" for event in adjustment_events
        )
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
            assert (
                connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[
                    0
                ]
                == 0
            )
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)
        assert harness.executor.dispatches == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", (TerminalOutcome.COMPLETED, TerminalOutcome.FAILED))
async def test_product_registry_replays_terminal_p3_authority_after_clean_checkpoint(
    tmp_path: Path,
    outcome: TerminalOutcome,
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
    harness.executor.dispatch_outcome = outcome
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
        await _wait_until(
            lambda: (
                harness.composition._core.store.get_task(task_id, _scope()).state.value
                == "terminal"
            )
        )
        harness.authority.contexts["session-1"] = replace(
            authorized_context,
            revision_value="clean-checkpoint-revision",
        )
        counts_before_progress = harness.composition._core.store.counts()

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
        assert queried.ok is True
        assert activated.ok is True
        await _wait_until(
            lambda: any(
                message["payload"]["source_event"]["event_type"] == "task.terminal"
                for message in pushed
            )
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
        assert closed.ok is True
        assert activated.payload["result"]["voice_progress"] == "unavailable"
        assert [
            message["payload"]["source_event"]["event_type"] for message in pushed
        ] == ["task.accepted", "task.running", "task.terminal"]
        assert pushed[-1]["payload"]["source_event"]["payload"] == {
            "state": "terminal",
            "outcome": outcome.value,
        }
        assert harness.composition._core.store.counts() == counts_before_progress
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
        assert [
            require_clean for _session, require_clean in harness.authority.calls
        ] == [
            True,
            False,
            False,
            False,
            True,
            False,
            False,
            True,
        ]
        assert harness.authority.calls[-1] == ("session-1", True)
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_read_queries_survive_clean_checkpoint_revision_but_cancel_fails_closed(
    tmp_path: Path,
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
        harness.authority.contexts["session-1"] = replace(
            harness.authority.contexts["session-1"],
            revision_value="clean-checkpoint-revision",
        )
        before = _store_counts(harness.database)

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
                request_id=f"request-checkpoint-{operation}",
                session_id="session-1",
            )
            assert result.ok is True, operation

        cancel = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-drift-cancel",
            session_id="session-1",
        )

        assert (
            cancel.payload["error"]["reason"] == "EXECUTION_CONTEXT_REVISION_MISMATCH"
        )
        assert _store_counts(harness.database) == before
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_read_and_cancel_still_fail_closed_on_redacted_context(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create-redacted-context",
            session_id="session-1",
        )
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        harness.authority.contexts["session-1"] = replace(
            harness.authority.contexts["session-1"],
            redacted=True,
            redacted_fields=("secret",),
        )
        before = _store_counts(harness.database)

        operations = {
            "task.get": {**_base(), "task_id": task_id},
            "task.list": _base(),
            "task.status": {**_base(), "task_id": task_id},
            "task.events": {**_base(), "task_id": task_id, "after_seq": -1},
            "task.cancel": _issued_cancel_params(harness, task_id),
        }
        for operation, params in operations.items():
            result = await harness.composition.handle(
                operation=operation,
                params=params,
                request_id=f"request-redacted-{operation}",
                session_id="session-1",
            )
            assert result.payload["error"]["reason"] == "TASK_CONTEXT_REDACTED"

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


@pytest.mark.parametrize(
    ("demo_policy", "fixture_enabled"), [("0", False), ("1", True)]
)
def test_factory_gates_itinerary_fixture_with_trusted_demo_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    demo_policy: str,
    fixture_enabled: bool,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED",
        demo_policy,
    )
    database = tmp_path / f"demo-policy-{demo_policy}.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )

    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )

    assert composition is not None
    assert type(composition._core.executor) is DirectProjectCodeExecutorAdapter
    assert composition._core.executor._demo_itinerary_fixture_enabled is fixture_enabled


@pytest.mark.parametrize(
    ("demo_policy", "checkpoint_policy", "checkpoint_enabled"),
    [
        ("0", "0", False),
        ("0", "1", False),
        ("1", "0", False),
        ("1", "1", True),
    ],
)
def test_factory_gates_demo_adjustment_checkpoint_behind_both_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    demo_policy: str,
    checkpoint_policy: str,
    checkpoint_enabled: bool,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED",
        demo_policy,
    )
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_DEMO_ADJUSTMENT_CHECKPOINT_ENABLED",
        checkpoint_policy,
    )
    database = tmp_path / f"demo-checkpoint-{demo_policy}-{checkpoint_policy}.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )

    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )

    assert composition is not None
    assert type(composition._core.executor) is DirectProjectCodeExecutorAdapter
    assert (
        composition._core.executor._demo_itinerary_adjustment_checkpoint_enabled
        is checkpoint_enabled
    )


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

    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"


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


def test_default_server_revision_preserves_dirty_worktree_reason(
    tmp_path: Path,
) -> None:
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

    # Authentication and the exact project allow-list were already verified,
    # so the D-069 retry contract keeps the server-derived Context reason.
    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"
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
    assert dispatch.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"


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
async def test_dispatch_handoff_fence_rechecks_clean_state_after_agent_setup(
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

        async def ensure_instance(self):
            # A formal dispatch runs outside the chat path and awaits
            # this rather than reading the bare accessor.
            return object()

        async def process_background_code_task_stream(self):
            return None

    class Manager:
        def __init__(self) -> None:
            self.agent = Agent()
            self.pins = 0
            self.unpins = 0

        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            return self.agent

        def pin_agent(self, _agent) -> None:
            self.pins += 1

        def unpin_agent(self, _agent) -> None:
            self.unpins += 1

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
    assert manager.pins == 1
    assert binding.context_release is not None
    binding.context_release()
    assert manager.unpins == 1


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
            self.stop_calls = 0

        async def stop_scheduler(self, *, interrupt_running: bool = False) -> None:
            assert interrupt_running is True
            self.stop_calls += 1
            if self.stop_calls == 1:
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

    with pytest.raises(
        RuntimeError,
        match="FORMAL_PROJECT_BINDING_CLEANUP_PENDING",
    ):
        await resolver.close()
    assert resolver._closed is False
    assert resolver._close_requested is True
    assert service.stop_calls == 1
    assert service.clear_calls == 1
    assert manager.cleanup_calls == 1

    await resolver.close()
    await resolver.close()

    assert resolver._closed is True
    assert service.stop_calls == 2
    assert service.clear_calls == 1
    assert manager.cleanup_calls == 2


# --- D-069 bounded same-task task.retry product reachability -----------------


def _retry_params(
    task_id: str,
    *,
    command_id: str = "command-retry",
    session_id: str = "session-1",
    correlation_id: str | None = None,
) -> dict[str, object]:
    return {
        **_base(session_id),
        "command_id": command_id,
        "confirmation_id": f"forged:{command_id}",
        "issued_at": NOW,
        "correlation_id": correlation_id or f"correlation:{command_id}",
        "task_id": task_id,
    }


async def _issued_retry_params(
    harness: _Harness,
    params: dict[str, object],
    *,
    expires_at: str = EXPIRY,
    now: str = NOW,
) -> dict[str, object]:
    """Issue the exact confirmation the production issue route would freeze."""

    prepared = await harness.composition.prepare_mutation_confirmation(
        operation="task.retry",
        params=params,
        session_id=str(params["session_id"]),
    )
    params["confirmation_id"] = harness.confirmations.issue(
        prepared.binding, expires_at=expires_at, now=now
    )
    return params


def _outbox_snapshot(database: Path) -> tuple[tuple[object, ...], ...]:
    with sqlite3.connect(database) as connection:
        return tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT outbox_id, kind, state, claimed_by FROM outbox"
                " ORDER BY outbox_id"
            ).fetchall()
        )


def _confirmation_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        return int(
            connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[0]
        )


async def _effects(harness: _Harness) -> tuple[object, ...]:
    """Every D-069 forbidden effect a rejection or replay must leave untouched.

    The snapshot is taken only once every durable delivery has settled so an
    earlier step's asynchronous tail can never be mistaken for a rejection's
    side effect.

    ``Executor.status`` is deliberately excluded.  An accepted mutation wakes
    the periodic reconciliation worker, whose status query is a read-only
    audit of an already dispatched attempt; the zero-effect oracle forbids
    ``dispatch``/``cancel``, not that audit.  Every mutating surface —
    task/spec/current-attempt rows, attempt/event/outbox/command rows, outbox
    claim state, Executor dispatch/cancel, retry readiness and binding
    resolver ownership — is covered here.
    """

    await _wait_until(
        lambda: all(
            row[2] not in {"pending", "claimed"}
            for row in _outbox_snapshot(harness.database)
        )
    )
    return (
        _store_counts(harness.database),
        _outbox_snapshot(harness.database),
        tuple(harness.executor.dispatches),
        tuple(harness.executor.cancels),
        tuple(harness.executor.readiness),
        harness.closer.calls,
    )


async def _cancel_current(harness: _Harness, task_id: str, *, command_id: str) -> None:
    params = _issue_confirmation(
        harness,
        {
            **_mutation_params(task_id),
            "command_id": command_id,
            "confirmation_id": f"forged:{command_id}",
            "correlation_id": f"correlation:{command_id}",
        },
        operation="task.cancel",
    )
    cancelled = await harness.composition.handle(
        operation="task.cancel",
        params=params,
        request_id=f"request-{command_id}",
        session_id="session-1",
    )
    assert cancelled.ok is True, cancelled.payload
    await _wait_until(
        lambda: (
            harness.composition._core.store.get_task(task_id, _scope()).state.value
            == "terminal"
        )
    )


async def _terminal_task(
    harness: _Harness,
    *,
    command_id: str = "command-create",
    cancel_command_id: str = "command-cancel",
    cancel: bool = True,
) -> str:
    """Drive one exact task to a terminal current attempt through the route."""

    created = await harness.composition.handle(
        operation="task.create",
        params=_issued_create_params(harness, command_id),
        request_id=f"request-{command_id}",
        session_id="session-1",
    )
    assert created.ok is True, created.payload
    task_id = str(created.payload["result"]["task_id"])
    await _wait_until(lambda: len(harness.executor.dispatches) >= 1)
    if cancel:
        await _cancel_current(harness, task_id, command_id=cancel_command_id)
    else:
        await _wait_until(
            lambda: (
                harness.composition._core.store.get_task(task_id, _scope()).state.value
                == "terminal"
            )
        )
    return task_id


@pytest.mark.asyncio
async def test_status_retry_admission_rejects_dirty_context_without_mutation(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        clean = await harness.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-retry-admission-clean",
            session_id="session-1",
        )
        assert clean.ok is True, clean.payload
        attempt = clean.payload["result"]["attempt"]
        assert clean.payload["result"]["retry_admission"] == {
            "eligible": True,
            "reason": "TASK_RETRY_ELIGIBLE",
            "task_id": task_id,
            "attempt_id": attempt["attempt_id"],
            "attempt_number": attempt["attempt_number"] + 1,
        }
        assert (
            await harness.composition.read_product_status_retry_admission(
                bearer_token=TOKEN,
                session_id="session-1",
                task_id=task_id,
            )
            == clean.payload["result"]["retry_admission"]
        )

        counts = _store_counts(harness.database)
        dispatches = list(harness.executor.dispatches)
        confirmations = _confirmation_count(harness.database)
        harness.authority.dirty = True
        dirty = await harness.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-retry-admission-dirty",
            session_id="session-1",
        )

        assert dirty.ok is True, dirty.payload
        assert dirty.payload["result"]["retry_admission"] == {
            "eligible": False,
            "reason": "TASK_CONTEXT_WORKTREE_DIRTY",
            "task_id": task_id,
            "attempt_id": None,
            "attempt_number": None,
        }
        assert (
            await harness.composition.read_product_status_retry_admission(
                bearer_token=TOKEN,
                session_id="session-1",
                task_id=task_id,
            )
            == dirty.payload["result"]["retry_admission"]
        )
        with pytest.raises(FormalTaskViolation) as invalid_bearer:
            await harness.composition.read_product_status_retry_admission(
                bearer_token="wrong-token",
                session_id="session-1",
                task_id=task_id,
            )
        assert invalid_bearer.value.reason == "FORMAL_TASK_AUTHENTICATION_REQUIRED"
        assert _store_counts(harness.database) == counts
        assert harness.executor.dispatches == dispatches
        assert _confirmation_count(harness.database) == confirmations
    finally:
        await harness.composition.stop()


async def _apply_retry(
    harness: _Harness, task_id: str, *, command_id: str
) -> dict[str, object]:
    params = await _issued_retry_params(
        harness, _retry_params(task_id, command_id=command_id)
    )
    applied = await harness.composition.handle(
        operation="task.retry",
        params=params,
        request_id=f"request-{command_id}",
        session_id="session-1",
    )
    assert applied.ok is True, applied.payload
    return dict(applied.payload["result"])


@pytest.mark.asyncio
async def test_retry_creates_one_successor_attempt_from_server_derived_lineage(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        predecessor = harness.composition._core.store.get_task(task_id, _scope())
        attempt_a = predecessor.attempt_id
        before = _store_counts(harness.database)

        result = await _apply_retry(harness, task_id, command_id="command-retry-b")

        assert result["task_id"] == task_id
        assert result["previous_attempt_id"] == attempt_a
        assert result["attempt_id"] != attempt_a
        assert result["attempt_number"] == 2
        assert result["applied"] is True
        assert result["state"] == "accepted"

        after = _store_counts(harness.database)
        # No new task row; exactly one new attempt, dispatch outbox row and
        # admission command.  The event count only grows further once the
        # successor is delivered, so it is bounded from below.
        assert after[0] == before[0]
        assert after[1] == before[1] + 1
        assert after[2] >= before[2] + 1
        assert after[3] == before[3] + 1
        assert after[4] == before[4] + 1

        # Executor readiness is proved only at Store apply, after confirmation.
        assert harness.executor.readiness == [(task_id, attempt_a)]

        current = harness.composition._core.store.get_task(task_id, _scope())
        assert current.attempt_id == result["attempt_id"]
        assert current.state.value == "accepted"
        assert current.outcome is None
        # The stable specification, executor and model binding are preserved.
        assert current.spec.name == predecessor.spec.name
        assert current.spec.instruction == predecessor.spec.instruction
        assert current.spec.executor_id == predecessor.spec.executor_id
        assert current.spec.attributes == predecessor.spec.attributes

        boundary = harness.composition._core.store.events(
            task_id, _scope(), after_seq=current.event_head - 1
        )[0]
        assert boundary.event_type == "task.retry_accepted"
        assert boundary.state == "accepted"
        assert boundary.outcome is None
        assert boundary.attempt_id == result["attempt_id"]
        assert boundary.details["retry_of_attempt_id"] == attempt_a
        assert boundary.details["previous_outcome"] == "cancelled"
        assert boundary.details["attempt_number"] == 2
        assert boundary.details["command_id"] == "command-retry-b"

        await _wait_until(lambda: result["attempt_id"] in harness.executor.dispatches)
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_applied_retry_replays_exactly_after_the_task_advanced(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        applied_params = await _issued_retry_params(
            harness, _retry_params(task_id, command_id="command-retry-b")
        )
        first_confirmation = str(applied_params["confirmation_id"])
        applied = await harness.composition.handle(
            operation="task.retry",
            params=applied_params,
            request_id="request-retry-b",
            session_id="session-1",
        )
        assert applied.ok is True, applied.payload
        original = dict(applied.payload["result"])
        await _wait_until(lambda: original["attempt_id"] in harness.executor.dispatches)
        before = await _effects(harness)

        # 1. Durable replay never bypasses confirmation.  The already consumed
        #    credential still verifies, because the ledger deliberately allows
        #    an exact single-use record to be replayed rather than re-issued,
        #    but it is not an entry point for a second attempt: the command
        #    ledger returns the same applied result with zero new effect.
        consumed_replay = await harness.composition.handle(
            operation="task.retry",
            params={
                **_retry_params(task_id, command_id="command-retry-b"),
                "confirmation_id": first_confirmation,
            },
            request_id="request-retry-b-consumed",
            session_id="session-1",
        )
        assert consumed_replay.ok is True, consumed_replay.payload
        assert consumed_replay.payload["result"] == original
        assert await _effects(harness) == before

        # An expired credential with an otherwise exact binding is refused, and
        # a forged binding is refused before expiry is even considered.
        exact = await harness.composition.prepare_mutation_confirmation(
            operation="task.retry",
            params=_retry_params(task_id, command_id="command-retry-b"),
            session_id="session-1",
        )
        stale_credentials = (
            (
                "expired",
                harness.confirmations.issue(
                    exact.binding,
                    expires_at="2026-08-05T11:30:00Z",
                    now="2026-08-05T11:00:00Z",
                ),
                "P3_CONFIRMATION_EXPIRED",
            ),
            (
                "forged",
                harness.confirmations.issue(
                    P3ConfirmationBinding(
                        principal_id="user-1",
                        scope=_scope(),
                        operation="task.retry",
                        command_id="command-retry-b",
                        target_task_id=task_id,
                        intent_fingerprint="forged-intent",
                    ),
                    expires_at=EXPIRY,
                    now=NOW,
                ),
                "P3_CONFIRMATION_BINDING_MISMATCH",
            ),
        )
        for label, stale, expected in stale_credentials:
            refused = await harness.composition.handle(
                operation="task.retry",
                params={
                    **_retry_params(task_id, command_id="command-retry-b"),
                    "confirmation_id": stale,
                },
                request_id=f"request-retry-b-{label}",
                session_id="session-1",
            )
            assert refused.ok is False, label
            assert refused.payload["error"]["reason"] == expected, label
            assert refused.payload["error"]["code"] == "PERMISSION_DENIED", label
            assert await _effects(harness) == before, label

        # 2. A reopened process re-issues its own confirmation because that
        #    ledger is single-use and short lived.  The new credential is
        #    normally issued, verified and consumed; the durable command ledger
        #    still owns the outcome, so the applied result replays exactly.
        replay_params = await _issued_retry_params(
            harness, _retry_params(task_id, command_id="command-retry-b")
        )
        assert replay_params["confirmation_id"] != first_confirmation
        replayed = await harness.composition.handle(
            operation="task.retry",
            params=replay_params,
            request_id="request-retry-b-replayed",
            session_id="session-1",
        )

        assert replayed.ok is True, replayed.payload
        assert replayed.payload["result"] == original
        assert replayed.payload["request_id"] == "request-retry-b-replayed"
        # Exact replay: zero new durable rows, zero outbox claim change, zero
        # Executor work and — proving replay precedes current admission — zero
        # additional readiness evaluations.
        assert await _effects(harness) == before

        # 3. A fresh valid confirmation does not launder a changed immutable
        #    product fact.  Each one still conflicts or is refused earlier.
        for changed in (
            {"command_id": "command-retry-other"},
            {"correlation_id": "correlation:tampered"},
            {"issued_at": "2026-08-05T11:59:00Z"},
        ):
            tampered = _retry_params(task_id, command_id="command-retry-b")
            tampered.update(changed)
            with pytest.raises(FormalTaskViolation) as conflicted:
                await _issued_retry_params(harness, tampered)
            assert conflicted.value.reason in {
                "IDEMPOTENCY_CONFLICT",
                "TASK_RETRY_REQUIRES_TERMINAL",
            }, changed
            assert await _effects(harness) == before, changed

        # The confirmation ledger may grow — D-069 keeps it an independent
        # authorization record — but it never produced a second attempt.
        assert _confirmation_count(harness.database) > 1
        current = harness.composition._core.store.get_task(task_id, _scope())
        assert current.attempt_id == original["attempt_id"]
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_changed_product_request_facts_conflict_on_the_same_command_id(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        await _apply_retry(harness, task_id, command_id="command-retry-b")
        before = await _effects(harness)

        confirmations_before = _confirmation_count(harness.database)
        conflicting = _retry_params(
            task_id,
            command_id="command-retry-b",
            correlation_id="correlation:tampered",
        )

        # The conflict is deterministic, so it is decided before any
        # confirmation is issued and long before the route could re-admit.
        with pytest.raises(FormalTaskViolation) as prepared:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=conflicting,
                session_id="session-1",
            )
        assert prepared.value.reason == "IDEMPOTENCY_CONFLICT"
        assert prepared.value.code is ErrorCode.CONFLICT

        routed = await harness.composition.handle(
            operation="task.retry",
            params=conflicting,
            request_id="request-retry-conflict",
            session_id="session-1",
        )
        assert routed.ok is False
        assert routed.payload["error"]["reason"] == "IDEMPOTENCY_CONFLICT"
        assert routed.payload["error"]["code"] == "CONFLICT"

        assert await _effects(harness) == before
        assert _confirmation_count(harness.database) == confirmations_before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_nonterminal_predecessor_with_zero_effect(
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
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        before = await _effects(harness)
        confirmations_before = _confirmation_count(harness.database)

        with pytest.raises(FormalTaskViolation) as rejected:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )

        assert rejected.value.reason == "TASK_RETRY_REQUIRES_TERMINAL"
        assert rejected.value.code is ErrorCode.CONFLICT
        assert await _effects(harness) == before
        # A deterministic rejection never reserves confirmation capacity.
        assert _confirmation_count(harness.database) == confirmations_before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_ineligible_terminal_outcome_with_zero_effect(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    harness.executor.dispatch_outcome = TerminalOutcome.FAILED
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness, cancel=False)
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).outcome
            is TerminalOutcome.FAILED
        )
        before = await _effects(harness)

        with pytest.raises(FormalTaskViolation) as rejected:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )

        assert rejected.value.reason == "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"
        assert rejected.value.code is ErrorCode.CONFLICT
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_budget_stops_at_three_total_attempts(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        second = await _apply_retry(harness, task_id, command_id="command-retry-b")
        assert second["attempt_number"] == 2
        await _cancel_current(harness, task_id, command_id="command-cancel-b")

        third = await _apply_retry(harness, task_id, command_id="command-retry-c")
        assert third["attempt_number"] == 3
        await _cancel_current(harness, task_id, command_id="command-cancel-c")

        before = await _effects(harness)
        with pytest.raises(FormalTaskViolation) as rejected:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id, command_id="command-retry-d"),
                session_id="session-1",
            )

        assert rejected.value.reason == "TASK_RETRY_LIMIT_EXCEEDED"
        assert rejected.value.code is ErrorCode.CONFLICT
        assert await _effects(harness) == before
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).attempt_id
            == third["attempt_id"]
        )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_fails_closed_while_executor_cleanup_is_pending(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        params = await _issued_retry_params(harness, _retry_params(task_id))
        harness.executor.retry_ready = False
        before = await _effects(harness)

        rejected = await harness.composition.handle(
            operation="task.retry",
            params=params,
            request_id="request-retry-cleanup-pending",
            session_id="session-1",
        )

        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == (
            "TASK_RETRY_EXECUTOR_CLEANUP_PENDING"
        )
        assert rejected.payload["error"]["code"] == "UNAVAILABLE"
        after = await _effects(harness)
        # Readiness itself was evaluated once and nothing else moved.
        assert after[:4] == before[:4]
        assert len(after[4]) == len(before[4]) + 1
        assert after[5] == before[5]
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_forged_predecessor_lineage_confirmation(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        prepared = await harness.composition.prepare_mutation_confirmation(
            operation="task.retry",
            params=_retry_params(task_id),
            session_id="session-1",
        )
        honest = harness.authority.contexts["session-1"]
        persisted = harness.composition._core.store.get_task(task_id, _scope()).spec
        forged = PreparedP3RetryFacts(
            previous_attempt_id="attempt-forged",
            previous_outcome="completed",
            attempt_number=3,
            name=persisted.name,
            instruction=persisted.instruction,
            executor_id=persisted.executor_id,
            required_capabilities=tuple(persisted.required_capabilities),
            side_effect_class=persisted.side_effect_class,
            attributes=tuple(persisted.attributes),
        )
        forged_binding = P3ConfirmationBinding(
            principal_id=prepared.binding.principal_id,
            scope=prepared.binding.scope,
            operation="task.retry",
            command_id=prepared.binding.command_id,
            target_task_id=task_id,
            intent_fingerprint=p3_confirmation_intent_fingerprint(
                operation="task.retry",
                command_id=prepared.binding.command_id,
                target_task_id=task_id,
                context=honest,
                retry=forged,
            ),
        )
        assert forged_binding.intent_fingerprint != prepared.binding.intent_fingerprint
        params = _retry_params(task_id)
        params["confirmation_id"] = harness.confirmations.issue(
            forged_binding, expires_at=EXPIRY, now=NOW
        )
        before = await _effects(harness)

        rejected = await harness.composition.handle(
            operation="task.retry",
            params=params,
            request_id="request-retry-forged",
            session_id="session-1",
        )

        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == "P3_CONFIRMATION_BINDING_MISMATCH"
        assert rejected.payload["error"]["code"] == "PERMISSION_DENIED"
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_requires_a_clean_checkout_and_performs_no_git_operation(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        before = await _effects(harness)
        harness.authority.dirty = True
        harness.authority.calls.clear()

        with pytest.raises(FormalTaskViolation) as prepared:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )
        assert prepared.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"
        assert prepared.value.code is ErrorCode.PERMISSION_DENIED

        routed = await harness.composition.handle(
            operation="task.retry",
            params=_retry_params(task_id),
            request_id="request-retry-dirty",
            session_id="session-1",
        )
        assert routed.ok is False
        assert routed.payload["error"]["reason"] == "TASK_CONTEXT_WORKTREE_DIRTY"

        # Every retry authority resolution demanded the clean-worktree guard.
        assert harness.authority.calls == [("session-1", True), ("session-1", True)]
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_expired_confirmation_foreign_scope_and_bad_bearer(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        # Issue against an earlier clock so the record is already expired at NOW.
        expired = await _issued_retry_params(
            harness,
            _retry_params(task_id, command_id="command-retry-expired"),
            expires_at="2026-08-05T11:30:00Z",
            now="2026-08-05T11:00:00Z",
        )
        before = await _effects(harness)

        stale = await harness.composition.handle(
            operation="task.retry",
            params=expired,
            request_id="request-retry-expired",
            session_id="session-1",
        )
        assert stale.ok is False
        assert stale.payload["error"]["reason"] == "P3_CONFIRMATION_EXPIRED"
        assert stale.payload["error"]["code"] == "PERMISSION_DENIED"

        foreign = await harness.composition.handle(
            operation="task.retry",
            params=_retry_params(
                task_id,
                command_id="command-retry-foreign",
                session_id="session-2",
            ),
            request_id="request-retry-foreign",
            session_id="session-2",
        )
        assert foreign.ok is False
        assert foreign.payload["error"]["code"] == "NOT_FOUND"
        assert task_id not in str(foreign.payload["error"])

        unauthorized = await harness.composition.handle(
            operation="task.retry",
            params={**_retry_params(task_id), "auth_token": "wrong-token"},
            request_id="request-retry-unauthorized",
            session_id="session-1",
        )
        assert unauthorized.ok is False
        assert unauthorized.payload["error"]["code"] == "UNAUTHENTICATED"
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_fails_closed_while_predecessor_authority_is_unsettled(
    tmp_path: Path,
) -> None:
    """Unsettled outbox or reconciliation ownership blocks admission upstream.

    Both facts are Store-owned, so the product route must surface their exact
    stable reason rather than folding them into a generic retry error.  The
    snapshots below are taken directly instead of through ``_effects`` because
    the injected pending outbox row would otherwise never appear settled.
    """

    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        attempt_id = harness.composition._core.store.get_task(
            task_id, _scope()
        ).attempt_id

        with sqlite3.connect(harness.database) as connection:
            connection.execute(
                "UPDATE tasks SET reconciliation_state=? WHERE task_id=?",
                (ReconciliationState.PENDING.value, task_id),
            )
        before = _store_counts(harness.database)
        readiness_before = len(harness.executor.readiness)

        with pytest.raises(FormalTaskViolation) as reconciliation:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )
        assert reconciliation.value.reason == "TASK_RETRY_RECONCILIATION_PENDING"
        assert reconciliation.value.code is ErrorCode.UNAVAILABLE

        with sqlite3.connect(harness.database) as connection:
            connection.execute(
                "UPDATE tasks SET reconciliation_state=NULL WHERE task_id=?",
                (task_id,),
            )
            connection.execute(
                "UPDATE outbox SET state=? WHERE task_id=? AND attempt_id=?",
                (OutboxState.PENDING.value, task_id, attempt_id),
            )

        with pytest.raises(FormalTaskViolation) as outbox:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )
        assert outbox.value.reason == "TASK_RETRY_OUTBOX_PENDING"
        assert outbox.value.code is ErrorCode.UNAVAILABLE

        # Neither deterministic rejection admitted an attempt, appended an
        # event, claimed an outbox row, issued a command or reached the
        # Executor readiness seam.
        assert _store_counts(harness.database) == before
        assert len(harness.executor.readiness) == readiness_before
        assert harness.executor.dispatches == [attempt_id]
        assert harness.executor.cancels == [attempt_id]
        with sqlite3.connect(harness.database) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM outbox WHERE claimed_by IS NOT NULL"
                ).fetchone()[0]
                == 0
            )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_an_unsupported_legacy_executor(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        before = await _effects(harness)
        harness.executor.executor_id = "legacy.demo_substitute"

        with pytest.raises(FormalTaskViolation) as rejected:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )

        assert rejected.value.reason == "EXECUTOR_CAPABILITY_UNAVAILABLE"
        assert rejected.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
        assert await _effects(harness) == before
    finally:
        harness.executor.executor_id = FORMAL_PROJECT_EXECUTOR_ID
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_concurrent_retry_admits_exactly_one_successor_attempt(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        first = await _issued_retry_params(
            harness, _retry_params(task_id, command_id="command-retry-x")
        )
        second = await _issued_retry_params(
            harness, _retry_params(task_id, command_id="command-retry-y")
        )
        before = _store_counts(harness.database)

        results = await asyncio.gather(
            harness.composition.handle(
                operation="task.retry",
                params=first,
                request_id="request-retry-x",
                session_id="session-1",
            ),
            harness.composition.handle(
                operation="task.retry",
                params=second,
                request_id="request-retry-y",
                session_id="session-1",
            ),
        )

        accepted = [item for item in results if item.ok]
        refused = [item for item in results if not item.ok]
        assert len(accepted) == 1
        assert len(refused) == 1
        assert refused[0].payload["error"]["reason"] in {
            "TASK_RETRY_PRECONDITION_STALE",
            "TASK_RETRY_REQUIRES_TERMINAL",
        }
        after = _store_counts(harness.database)
        # Exactly one successor attempt and one dispatch outbox row.  The loser
        # contributes no durable row at all; delivery of the winner may still
        # append lifecycle events, so that count is bounded from below.
        assert after[1] == before[1] + 1
        assert after[2] >= before[2] + 1
        assert after[3] == before[3] + 1
        assert accepted[0].payload["result"]["attempt_number"] == 2
        assert harness.executor.readiness[-1][0] == task_id
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_route_surface_rejects_client_declared_or_extra_facts(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        before = await _effects(harness)

        for extra in (
            {"source": "voice"},
            {"previous_attempt_id": "attempt-client-declared"},
            {"attempt_number": 2},
            {"after_seq": 0},
            {"name": "renamed"},
        ):
            rejected = await harness.composition.handle(
                operation="task.retry",
                params={**_retry_params(task_id), **extra},
                request_id=f"request-retry-extra-{next(iter(extra))}",
                session_id="session-1",
            )
            assert rejected.ok is False, extra
            assert rejected.payload["error"]["reason"] == "INVALID_P3_ROUTE_ARGUMENT"

        # Query-style authority registration can never resolve a retry grant.
        with pytest.raises(FormalTaskViolation) as denied:
            harness.composition.resolve_product_authority_candidate(
                bearer_token=TOKEN,
                operation="task.retry",
                session_id="session-1",
                correlation_id="correlation:retry",
                required_capabilities=frozenset({"task.retry"}),
                task_id=task_id,
            )
        assert denied.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"
        assert denied.value.code is ErrorCode.PERMISSION_DENIED
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_authority_candidate_requires_exact_cancel_target(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        candidate, context = harness.composition.resolve_product_authority_candidate(
            bearer_token=TOKEN,
            operation="task.cancel",
            session_id="session-1",
            correlation_id="correlation:product-cancel",
            required_capabilities=frozenset({"task.cancel"}),
            task_id=task_id,
        )

        assert candidate.resource is not None
        assert candidate.resource.resource_id == task_id
        assert context.scope == _scope()
        with pytest.raises(FormalTaskViolation) as missing:
            harness.composition.resolve_product_authority_candidate(
                bearer_token=TOKEN,
                operation="task.cancel",
                session_id="session-1",
                correlation_id="correlation:product-cancel-missing",
                required_capabilities=frozenset({"task.cancel"}),
                task_id=None,
            )
        assert missing.value.reason == "INVALID_P3_ROUTE_ARGUMENT"
    finally:
        await harness.composition.stop()


def test_retry_has_no_direct_transport_route_but_stays_a_p3_mutation() -> None:
    """W2 reaches retry only through the product composition mutate route.

    Removing the direct transport method must not silently demote
    ``task.retry`` to an unknown operation: every admission in ``handle`` and
    ``prepare_mutation_confirmation`` gates on these sets, so losing the
    operation here would disable retry validation instead of disabling retry.
    """

    from jiuwenswarm.common.schema.message import ReqMethod

    assert "live_voice.task.retry" not in P3_ROUTE_METHODS
    assert "task.retry" not in set(P3_ROUTE_METHODS.values())
    assert all(item.value != "live_voice.task.retry" for item in ReqMethod)

    assert "task.retry" in P3_OPERATIONS
    assert "task.retry" in P3_MUTATIONS
    assert "task.retry" in P3_TARGETED_MUTATIONS
    # Every directly routed operation keeps its transport method.
    assert P3_OPERATIONS - P3_MUTATIONS == set(P3_ROUTE_METHODS.values()) - {
        "task.create",
        "task.cancel",
    }


@pytest.mark.asyncio
async def test_unrouted_transport_method_cannot_reach_the_retry_admission(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        before = await _effects(harness)

        # AgentServer resolves an operation through P3_ROUTE_METHODS; an
        # unrouted method yields the empty operation and must fail closed.
        unrouted = P3_ROUTE_METHODS.get("live_voice.task.retry", "")
        assert unrouted == ""
        rejected = await harness.composition.handle(
            operation=unrouted,
            params=_retry_params(task_id),
            request_id="request-retry-unrouted",
            session_id="session-1",
        )

        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == "UNSUPPORTED_FORMAL_TASK_INTENT"
        assert rejected.payload["error"]["code"] == "UNSUPPORTED"
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_cancel_before_dispatch_predecessor_admits_exactly_one_successor(
    tmp_path: Path,
) -> None:
    """The canonical cancel-before-dispatch shape is retry eligible end to end.

    Admission is opened without the periodic reconciliation worker so the
    create dispatch outbox is never claimed.  That is exactly how a task
    cancelled before dispatch looks: the Direct Executor was never called, so
    it owns no journal row for the predecessor, yet D-069 still makes a
    cancelled terminal attempt retry eligible.
    """

    harness = _harness(tmp_path)
    async with harness.composition._active_condition:
        harness.composition._accepting = True
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create",
            session_id="session-1",
        )
        assert created.ok is True, created.payload
        task_id = str(created.payload["result"]["task_id"])
        assert harness.executor.dispatches == []

        cancelled = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-cancel",
            session_id="session-1",
        )
        assert cancelled.ok is True, cancelled.payload

        store = harness.composition._core.store
        predecessor = store.get_task(task_id, _scope())
        attempt_a = predecessor.attempt_id
        assert predecessor.state.value == "terminal"
        assert predecessor.outcome is TerminalOutcome.CANCELLED
        assert predecessor.cancel_requested is True
        assert predecessor.dispatch_fenced is True
        assert store.get_attempt(attempt_a).executor_ref is None
        # The Executor was never engaged, so it holds no journal for A.
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
        before = _store_counts(harness.database)

        result = await _apply_retry(harness, task_id, command_id="command-retry-b")

        assert result["previous_attempt_id"] == attempt_a
        assert result["attempt_number"] == 2
        assert result["applied"] is True
        # Readiness is proved at Store apply from Store facts against exactly A.
        assert harness.executor.readiness == [(task_id, attempt_a)]

        after = _store_counts(harness.database)
        # Exactly one successor attempt, one boundary event, one dispatch
        # outbox row and one admission command; the task row is not duplicated.
        assert after[0] == before[0]
        assert after[1] == before[1] + 1
        assert after[2] == before[2] + 1
        assert after[3] == before[3] + 1
        assert after[4] == before[4] + 1
        current = store.get_task(task_id, _scope())
        assert current.attempt_id == result["attempt_id"]
        assert current.state.value == "accepted"
        assert current.outcome is None
        # No worker ran, so nothing was dispatched or cancelled for B either.
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


def test_p3_model_builder_uses_the_shared_module_level_entry_builder() -> None:
    """P3 must build its model through the function the runtime actually exports.

    ``build_model_from_entry`` is the module-level function the deep adapter,
    the model cache and the modality warmup all share; it has never been an
    attribute of ``JiuWenSwarmDeepAdapter``.  Calling it as a class method
    raised AttributeError inside model resolution, which the Task Core could
    only report as ``P3_MODEL_UNAVAILABLE``.  Every real attempt dispatch then
    failed with a suppressed outbox item and no project effect, while fake
    resolvers in tests never constructed a model at all.
    """

    from jiuwenswarm.server.runtime.agent_adapter import interface_deep
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    assert hasattr(interface_deep, "build_model_from_entry")
    assert not hasattr(interface_deep.JiuWenSwarmDeepAdapter, "_build_model_from_entry")

    seen: list[tuple[dict, dict]] = []
    sentinel = object()
    original = interface_deep.build_model_from_entry
    interface_deep.build_model_from_entry = (  # type: ignore[assignment]
        lambda mcc, mco: (seen.append((mcc, mco)), sentinel)[1]
    )
    try:
        built = AgentWebSocketServer._build_live_voice_p3_model(
            {"model_name": "probe-model", "client_provider": "probe"},
            {"temperature": 0.0},
        )
    finally:
        interface_deep.build_model_from_entry = original  # type: ignore[assignment]

    assert built is sentinel
    assert seen == [
        (
            {"model_name": "probe-model", "client_provider": "probe"},
            {"temperature": 0.0},
        )
    ]


@pytest.mark.asyncio
async def test_dispatch_builds_the_agent_handle_instead_of_reading_the_accessor(
    tmp_path: Path,
) -> None:
    """A formal dispatch must build the DeepAgent, not read the bare accessor.

    ``JiuWenSwarm.get_instance`` is a plain accessor that returns None until the
    chat path has built the root DeepAgent.  A formal task dispatches outside
    that path onto a freshly created project Agent, so reading the accessor left
    ``execution_agent`` None and every real attempt failed closed with
    EXECUTOR_CAPABILITY_UNAVAILABLE and no project effect.
    """

    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(tmp_path),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    built = object()

    class Agent:
        def __init__(self) -> None:
            self.ensure_calls = 0

        def get_instance(self):
            # The root DeepAgent does not exist yet outside the chat path.
            return None

        async def ensure_instance(self):
            self.ensure_calls += 1
            return built

        def get_project_execution_root(self) -> str:
            return str(tmp_path)

    agent = Agent()

    class Manager:
        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            return agent

        def pin_agent(self, _agent) -> None:
            return None

        def unpin_agent(self, _agent) -> None:
            return None

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

    assert binding.execution_agent is built
    assert agent.ensure_calls == 1
    assert binding.project_executor is agent
