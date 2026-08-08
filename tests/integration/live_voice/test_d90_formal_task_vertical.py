# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
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

NOW = "2026-08-07T12:00:00Z"
EXPIRY = "2100-01-01T00:00:00Z"


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


class _Resolver:
    def __init__(self, binding: ProjectExecutionBinding) -> None:
        self.binding = binding
        self.calls = 0

    async def resolve(self, _spec, *, for_dispatch: bool):
        assert for_dispatch is True
        self.calls += 1
        return self.binding


async def _wait(predicate, *, attempts: int = 200) -> None:
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
