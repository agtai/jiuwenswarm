# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import json
import os
import runpy
import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from jiuwenswarm.server.live_voice import project_code_executor

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ErrorCode,
    OriginRef,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.common.utils import get_agent_workspace_dir
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskSpec,
    FormalTaskState,
    FormalTaskViolation,
    OutboxKind,
    OutboxState,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskRecord,
    ResolvedTaskContext,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    FORMAL_PROJECT_EXECUTOR_ID,
    FORMAL_RUNTIME_SUPPORT_POLICY,
    PROJECT_CODE_ARTIFACT_KIND,
    PROJECT_CODE_EFFECT_POLICY,
    PROJECT_CODE_EXECUTOR,
    PROJECT_CODE_PIPELINE,
    ProjectCodeExecutorAdapter,
    ProjectExecutionBinding,
)


class _ProjectExecutor:
    async def process_background_code_task_stream(self, *_args, **_kwargs):
        if False:
            yield None


class _DirectProjectExecutor:
    def __init__(self, project: Path, behavior: str = "success") -> None:
        self.project = project
        self.behavior = behavior
        self.requests = []
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def process_background_code_task_stream(self, request):
        self.requests.append(request)
        self.started.set()
        project = Path(request.params["project_dir"]).resolve()
        try:
            if self.behavior == "wait":
                await asyncio.Event().wait()
            elif self.behavior == "agent_error":
                yield AgentResponseChunk(
                    request.request_id,
                    request.channel_id,
                    payload={"event_type": "chat.error", "error": "private"},
                    is_complete=True,
                )
            elif self.behavior == "incomplete":
                yield AgentResponseChunk(
                    request.request_id,
                    request.channel_id,
                    payload={"event_type": "chat.delta", "content": "partial"},
                    is_complete=False,
                )
            else:
                if self.behavior == "head_change":
                    (project / "forbidden.txt").write_text(
                        "forbidden", encoding="utf-8"
                    )
                    _git(project, "add", "forbidden.txt")
                    _git(project, "commit", "-m", "forbidden")
                elif self.behavior == "support_change":
                    (project / ".gitignore").write_text("runtime/\n", encoding="utf-8")
                elif self.behavior == "ignored_only":
                    (project / "ignored.txt").write_text("ignored", encoding="utf-8")
                elif self.behavior == "lf_success":
                    (project / "result.txt").write_bytes(b"done\n")
                else:
                    (project / "result.txt").write_text("done", encoding="utf-8")
                yield AgentResponseChunk(
                    request.request_id,
                    request.channel_id,
                    payload={"event_type": "chat.final", "content": "done"},
                    is_complete=True,
                )
        finally:
            self.finished.set()


class _AttributionExecutor:
    def __init__(self) -> None:
        self.requests = []
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()

    async def process_background_code_task_stream(self, request):
        self.requests.append(request)
        attempt_id = request.metadata["formal_attempt_id"]
        if attempt_id == "attempt-1":
            self.first_started.set()
            await self.release_first.wait()
            (Path(request.params["project_dir"]) / "only-attempt-1.txt").write_text(
                "attempt-1\n", encoding="utf-8"
            )
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={"event_type": "chat.final", "content": "completed"},
            is_complete=True,
        )


class _NonCooperativeExecutor:
    def __init__(self) -> None:
        self.requests = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancel_signals = 0

    async def process_background_code_task_stream(self, request):
        self.requests.append(request)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancel_signals += 1
            await self.release.wait()
        (Path(request.params["project_dir"]) / "late-effect.txt").write_text(
            "late\n", encoding="utf-8"
        )
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={"event_type": "chat.final", "content": "late completed"},
            is_complete=True,
        )


def _git(project: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _git_project(project: Path, *, ignore: str | None = None) -> None:
    project.mkdir(parents=True, exist_ok=True)
    _git(project, "init")
    _git(project, "config", "user.name", "Live Voice Test")
    _git(project, "config", "user.email", "live-voice-test@example.invalid")
    (project / "README.md").write_text("baseline\n", encoding="utf-8")
    if ignore is not None:
        (project / ".gitignore").write_text(ignore, encoding="utf-8")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "baseline")


def _scope() -> ScopeRef:
    return ScopeRef("user-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def _spec(project: Path) -> FormalTaskSpec:
    return FormalTaskSpec(
        name="Formal project task",
        instruction="Create one bounded source change.",
        origin=OriginRef("structured", None, None),
        context=ResolvedTaskContext(
            source="gateway.project_registry",
            stable_id="project-1",
            uri=project.resolve().as_uri(),
            revision_kind="version",
            revision_value="a77516a0",
            scope=_scope(),
            permissions=("task.execute", "project.write"),
            expires_at="2026-08-05T13:00:00Z",
            redaction_policy_id="live_voice.project.v1",
        ),
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        required_capabilities=("task.create",),
        side_effect_class="project_mutation",
        attributes=(
            ("model_config_version", "catalog-v1"),
            ("model_identity", "default#0"),
        ),
    )


def _contract(project: Path) -> dict[str, object]:
    return {
        "effective_execution_root": str(project.resolve()),
        "artifact_kind": PROJECT_CODE_ARTIFACT_KIND,
        "executor": PROJECT_CODE_EXECUTOR,
        "pipeline": PROJECT_CODE_PIPELINE,
        "effect_policy": dict(PROJECT_CODE_EFFECT_POLICY),
    }


class _Service:
    def __init__(self, project: Path) -> None:
        self.project = project
        self.run_calls: list[dict[str, object]] = []
        self.cancel_calls: list[tuple[str, dict[str, object]]] = []
        self.status_payload: dict[str, object] = self.payload("running")

    def payload(self, status: str) -> dict[str, object]:
        return {
            "task_id": "sch-1",
            "status": status,
            "execution_target": {
                "project_dir": str(self.project.resolve()),
                "project_id": "project-1",
                "origin_session_id": "session-1",
                "origin_channel_id": "web",
            },
            "execution_contract": _contract(self.project),
            "provenance": {
                "owner_scope": {
                    "channel_id": "formal-task-core",
                    "session_id": "session-1",
                    "app_id": "live-voice",
                },
                "origin_namespace": "live_voice",
                "idempotency_key": "attempt-1",
                "legacy_unscoped": False,
                "access": "authorized",
            },
        }

    async def run_task(self, query, model=None, pipeline=None, **kwargs):
        self.run_calls.append(
            {"query": query, "model": model, "pipeline": pipeline, **kwargs}
        )
        return self.payload("running")

    async def get_scheduled_task_status(self, task_id, **_kwargs):
        result = dict(self.status_payload)
        result.setdefault("task_id", task_id)
        return result

    async def cancel_scheduled_task(self, task_id, **kwargs):
        self.cancel_calls.append((task_id, kwargs))
        return self.payload("cancelled")


class _Resolver:
    def __init__(self, binding: ProjectExecutionBinding) -> None:
        self.binding = binding
        self.calls: list[bool] = []

    async def resolve(self, _spec, *, for_dispatch: bool):
        self.calls.append(for_dispatch)
        return self.binding


async def _clean_dispatch_fence() -> None:
    return None


def _binding(project: Path, service: _Service) -> ProjectExecutionBinding:
    return ProjectExecutionBinding(
        service=service,
        execution_agent=object(),
        project_executor=_ProjectExecutor(),
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
        resolved_revision_value="a77516a0",
        model_identity="default#0",
        model_config_version="catalog-v1",
        dispatch_fence=_clean_dispatch_fence,
    )


def _direct_binding(
    project: Path,
    executor: _DirectProjectExecutor,
    *,
    releases: list[str] | None = None,
) -> ProjectExecutionBinding:
    return ProjectExecutionBinding(
        service=None,
        execution_agent=object(),
        project_executor=executor,
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
        resolved_revision_value="a77516a0",
        model_identity="default#0",
        model_config_version="catalog-v1",
        context_release=(
            None if releases is None else lambda: releases.append("released")
        ),
        dispatch_fence=_clean_dispatch_fence,
    )


def _item(project: Path, *, kind=OutboxKind.ATTEMPT_DISPATCH, source_seq=-1):
    return PersistentOutboxItem(
        outbox_id="outbox-1",
        kind=kind,
        task_id="task-1",
        attempt_id="attempt-1",
        command_id="command-1",
        scope=_scope(),
        spec=_spec(project),
        executor_ref=(None if kind is OutboxKind.ATTEMPT_DISPATCH else "sch-1"),
        source_seq=source_seq,
        state=OutboxState.CLAIMED,
        delivery_count=1,
    )


def _direct_task_attempt(
    project: Path,
    *,
    source_seq: int = 1,
    task_id: str = "task-1",
    attempt_id: str = "attempt-1",
) -> tuple[PersistentTaskRecord, PersistentAttemptRecord]:
    task = PersistentTaskRecord(
        task_id,
        _scope(),
        _spec(project),
        FormalTaskState.RUNNING,
        attempt_id,
        "correlation-1",
        False,
        False,
        None,
        None,
        None,
    )
    attempt = PersistentAttemptRecord(
        attempt_id,
        task_id,
        FORMAL_PROJECT_EXECUTOR_ID,
        f"d0-project:{attempt_id}",
        FormalAttemptState.RUNNING,
        None,
        source_seq,
    )
    return task, attempt


async def _wait_direct_settled(
    adapter: DirectProjectCodeExecutorAdapter,
) -> None:
    # Windows worktree removal can occasionally exceed two seconds while Git
    # and filesystem scanners release handles. Keep this bounded, but do not
    # turn platform cleanup latency into a product-state failure.
    for _ in range(500):
        if not adapter._running:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("direct Executor worker did not settle")


@pytest.mark.asyncio
async def test_dispatch_uses_formal_attempt_as_legacy_idempotency_key(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    resolver = _Resolver(_binding(tmp_path, service))
    adapter = ProjectCodeExecutorAdapter(resolver)

    result = await adapter.dispatch(_item(tmp_path))

    assert result.executor_ref == "sch-1"
    assert [event.source_seq for event in result.observations] == [0, 1]
    call = service.run_calls[0]
    assert call["pipeline"] == PROJECT_CODE_PIPELINE
    assert call["origin_namespace"] == "live_voice"
    assert call["idempotency_key"] == "attempt-1"
    assert call["effective_execution_root"] == str(tmp_path.resolve())
    assert resolver.calls == [True]


@pytest.mark.asyncio
async def test_cancel_targets_only_bound_original_attempt(tmp_path: Path) -> None:
    service = _Service(tmp_path)
    releases: list[str] = []
    binding = replace(
        _binding(tmp_path, service),
        context_release=lambda: releases.append("released"),
    )
    adapter = ProjectCodeExecutorAdapter(_Resolver(binding))

    result = await adapter.cancel(
        _item(tmp_path, kind=OutboxKind.ATTEMPT_CANCEL, source_seq=1)
    )

    assert service.cancel_calls[0][0] == "sch-1"
    assert len(result.observations) == 1
    assert result.observations[0].attempt_state is FormalAttemptState.TERMINAL
    assert releases == ["released"]


@pytest.mark.asyncio
async def test_reconciliation_reports_unchanged_lost_and_unavailable_without_retry(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    adapter = ProjectCodeExecutorAdapter(_Resolver(_binding(tmp_path, service)))
    spec = _spec(tmp_path)
    task = PersistentTaskRecord(
        "task-1",
        _scope(),
        spec,
        FormalTaskState.RUNNING,
        "attempt-1",
        "correlation-1",
        False,
        False,
        None,
        None,
        None,
    )
    attempt = PersistentAttemptRecord(
        "attempt-1",
        "task-1",
        FORMAL_PROJECT_EXECUTOR_ID,
        "sch-1",
        FormalAttemptState.RUNNING,
        None,
        1,
    )

    unchanged = await adapter.status(task, attempt)
    assert isinstance(unchanged, ExecutorDeliveryResult)
    assert unchanged.observations == ()

    service.status_payload = {
        "task_id": "sch-1",
        "code": "TASK_NOT_FOUND",
        "error": "not found",
    }
    lost = await adapter.status(task, attempt)
    assert isinstance(lost, ExecutorObservation)
    assert lost.resolution is ExecutorResolution.LOST

    service.status_payload = {
        "task_id": "sch-1",
        "code": "TASK_STORE_UNAVAILABLE",
        "error": "offline",
    }
    unavailable = await adapter.status(task, attempt)
    assert isinstance(unavailable, ExecutorObservation)
    assert unavailable.resolution is ExecutorResolution.UNAVAILABLE


@pytest.mark.asyncio
async def test_mismatched_project_projection_fails_closed(tmp_path: Path) -> None:
    service = _Service(tmp_path)
    wrong = tmp_path / "wrong"
    wrong.mkdir()

    async def mismatched(*_args, **_kwargs):
        payload = service.payload("running")
        payload["execution_target"] = {"project_dir": str(wrong)}
        return payload

    service.run_task = mismatched  # type: ignore[method-assign]
    adapter = ProjectCodeExecutorAdapter(_Resolver(_binding(tmp_path, service)))

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(tmp_path))

    assert raised.value.reason == "EXECUTION_TARGET_MISMATCH"


@pytest.mark.asyncio
async def test_dispatch_rejects_mismatched_persisted_attempt_provenance(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    provenance = dict(service.status_payload["provenance"])
    provenance["idempotency_key"] = "attempt-other"
    service.status_payload["provenance"] = provenance
    adapter = ProjectCodeExecutorAdapter(_Resolver(_binding(tmp_path, service)))

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(tmp_path))

    assert raised.value.reason == "EXECUTOR_PROVENANCE_MISMATCH"
    assert raised.value.code.value == "RESULT_UNKNOWN"
    assert len(service.run_calls) == 1


@pytest.mark.asyncio
async def test_dispatch_applies_a_newer_persisted_terminal_state(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    service.status_payload = service.payload("completed")
    adapter = ProjectCodeExecutorAdapter(_Resolver(_binding(tmp_path, service)))

    delivered = await adapter.dispatch(_item(tmp_path))

    assert [event.source_seq for event in delivered.observations] == [0, 1, 2]
    assert delivered.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED


@pytest.mark.asyncio
async def test_runtime_revision_drift_rejects_before_legacy_service_call(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    releases: list[str] = []
    binding = replace(
        _binding(tmp_path, service),
        resolved_revision_value="newer-revision",
        context_release=lambda: releases.append("released"),
    )
    adapter = ProjectCodeExecutorAdapter(_Resolver(binding))

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(tmp_path))

    assert raised.value.reason == "EXECUTION_CONTEXT_REVISION_MISMATCH"
    assert service.run_calls == []
    assert releases == ["released"]


@pytest.mark.asyncio
async def test_dispatch_handoff_fence_rejects_new_dirty_state_before_carrier_call(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    releases: list[str] = []

    async def dirty_fence() -> None:
        raise FormalTaskViolation(
            "TASK_CONTEXT_WORKTREE_DIRTY",
            "formal task project became dirty before handoff",
            ErrorCode.PERMISSION_DENIED,
        )

    binding = replace(
        _binding(tmp_path, service),
        context_release=lambda: releases.append("released"),
        dispatch_fence=dirty_fence,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        await ProjectCodeExecutorAdapter(_Resolver(binding)).dispatch(_item(tmp_path))

    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"
    assert service.run_calls == []
    assert releases == ["released"]


@pytest.mark.asyncio
async def test_dispatch_failure_before_carrier_ownership_releases_binding_once(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    releases: list[str] = []

    async def fail_before_ownership(*_args, **_kwargs):
        raise RuntimeError("carrier unavailable")

    service.run_task = fail_before_ownership  # type: ignore[method-assign]
    binding = replace(
        _binding(tmp_path, service),
        context_release=lambda: releases.append("released"),
    )

    with pytest.raises(RuntimeError, match="carrier unavailable"):
        await ProjectCodeExecutorAdapter(_Resolver(binding)).dispatch(_item(tmp_path))

    assert releases == ["released"]


@pytest.mark.asyncio
async def test_dispatch_transfers_idempotent_release_callback_to_carrier(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    releases: list[str] = []
    binding = replace(
        _binding(tmp_path, service),
        context_release=lambda: releases.append("released"),
    )

    await ProjectCodeExecutorAdapter(_Resolver(binding)).dispatch(_item(tmp_path))

    release = service.run_calls[0]["context_release"]
    assert callable(release)
    release()
    release()
    assert releases == ["released"]


@pytest.mark.asyncio
async def test_status_uses_immutable_binding_after_revision_and_path_change(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = _Service(project)
    binding = replace(
        _binding(project, service),
        execution_agent=None,
        project_executor=None,
        resolved_revision_value="newer-revision",
    )
    adapter = ProjectCodeExecutorAdapter(_Resolver(binding))
    task = PersistentTaskRecord(
        "task-1",
        _scope(),
        _spec(project),
        FormalTaskState.RUNNING,
        "attempt-1",
        "correlation-1",
        False,
        False,
        None,
        None,
        None,
    )
    attempt = PersistentAttemptRecord(
        "attempt-1",
        "task-1",
        FORMAL_PROJECT_EXECUTOR_ID,
        "sch-1",
        FormalAttemptState.RUNNING,
        None,
        1,
    )
    project.rmdir()

    result = await adapter.status(task, attempt)

    assert isinstance(result, ExecutorDeliveryResult)
    assert result.observations == ()


@pytest.mark.asyncio
async def test_model_binding_drift_rejects_before_legacy_service_call(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    adapter = ProjectCodeExecutorAdapter(
        _Resolver(replace(_binding(tmp_path, service), model_identity="other-model#0"))
    )

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(tmp_path))

    assert raised.value.reason == "EXECUTOR_MODEL_BINDING_MISMATCH"
    assert service.run_calls == []


@pytest.mark.asyncio
async def test_session_scope_drift_rejects_before_legacy_service_call(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    binding = _binding(tmp_path, service)
    target = dict(binding.execution_target)
    target["origin_session_id"] = "other-session"
    adapter = ProjectCodeExecutorAdapter(
        _Resolver(replace(binding, execution_target=target))
    )

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(tmp_path))

    assert raised.value.reason == "EXECUTION_CONTEXT_SCOPE_MISMATCH"
    assert service.run_calls == []


@pytest.mark.asyncio
async def test_status_rejects_a_different_legacy_attempt_reference(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    service.status_payload = {"task_id": "sch-other", "status": "running"}
    releases: list[str] = []
    binding = replace(
        _binding(tmp_path, service),
        context_release=lambda: releases.append("released"),
    )
    adapter = ProjectCodeExecutorAdapter(_Resolver(binding))
    task = PersistentTaskRecord(
        "task-1",
        _scope(),
        _spec(tmp_path),
        FormalTaskState.RUNNING,
        "attempt-1",
        "correlation-1",
        False,
        False,
        None,
        None,
        None,
    )
    attempt = PersistentAttemptRecord(
        "attempt-1",
        "task-1",
        FORMAL_PROJECT_EXECUTOR_ID,
        "sch-1",
        FormalAttemptState.RUNNING,
        None,
        1,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.status(task, attempt)

    assert raised.value.reason == "LEGACY_EXECUTOR_REFERENCE_MISMATCH"
    assert releases == ["released"]


@pytest.mark.asyncio
async def test_status_rejects_mismatched_persisted_attempt_provenance(
    tmp_path: Path,
) -> None:
    service = _Service(tmp_path)
    service.status_payload = service.payload("running")
    provenance = dict(service.status_payload["provenance"])
    provenance["idempotency_key"] = "attempt-other"
    service.status_payload["provenance"] = provenance
    adapter = ProjectCodeExecutorAdapter(_Resolver(_binding(tmp_path, service)))
    task = PersistentTaskRecord(
        "task-1",
        _scope(),
        _spec(tmp_path),
        FormalTaskState.RUNNING,
        "attempt-1",
        "correlation-1",
        False,
        False,
        None,
        None,
        None,
    )
    attempt = PersistentAttemptRecord(
        "attempt-1",
        "task-1",
        FORMAL_PROJECT_EXECUTOR_ID,
        "sch-1",
        FormalAttemptState.RUNNING,
        None,
        1,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.status(task, attempt)

    assert raised.value.reason == "EXECUTOR_PROVENANCE_MISMATCH"


def test_ed_carrier_contract_matches_legacy_compatibility_module() -> None:
    contract_path = (
        Path(__file__).parents[3]
        / "jiuwenswarm"
        / "agents"
        / "harness"
        / "common"
        / "auto_harness"
        / "project_execution.py"
    )
    legacy = runpy.run_path(str(contract_path))

    assert legacy["PROJECT_CODE_PIPELINE"] == PROJECT_CODE_PIPELINE
    assert legacy["PROJECT_CODE_EXECUTOR"] == PROJECT_CODE_EXECUTOR
    assert legacy["PROJECT_CODE_ARTIFACT_KIND"] == PROJECT_CODE_ARTIFACT_KIND
    assert legacy["PROJECT_CODE_EFFECT_POLICY"] == PROJECT_CODE_EFFECT_POLICY


def test_shutdown_interruption_is_not_projected_as_user_cancellation() -> None:
    state, outcome = ProjectCodeExecutorAdapter._map_status("interrupted")

    assert state is FormalAttemptState.TERMINAL
    assert outcome is TerminalOutcome.INTERRUPTED


@pytest.mark.asyncio
async def test_direct_d0_executor_persists_exact_lifecycle_without_schedule_carrier(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    database = tmp_path / "runtime" / "p3.sqlite3"
    adapter = DirectProjectCodeExecutorAdapter(resolver, database)

    delivered = await adapter.dispatch(_item(project))
    await asyncio.wait_for(executor.finished.wait(), timeout=2)
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert delivered.executor_ref == "d0-project:attempt-1"
    assert [event.source_seq for event in delivered.observations] == [0, 1]
    assert isinstance(terminal, ExecutorDeliveryResult)
    assert [event.source_seq for event in terminal.observations] == [2]
    assert terminal.observations[0].attempt_outcome is TerminalOutcome.COMPLETED
    assert resolver.calls == [True]
    assert len(executor.requests) == 1
    request = executor.requests[0]
    assert request.metadata["enable_memory"] is False
    assert request.metadata["project_task_file_tools_only"] is True
    assert request.params["source"] == "live_voice.formal_task.d0"
    assert (
        Path(request.params["workspace_dir"]).resolve()
        == get_agent_workspace_dir().resolve()
    )
    assert _git(project, "rev-list", "--count", "HEAD") == "1"

    with sqlite3.connect(database) as connection:
        governance_json = connection.execute(
            "SELECT governance_json FROM live_voice_formal_project_attempts_v1"
        ).fetchone()[0]
    governance = json.loads(governance_json)
    assert governance["policy"] == dict(FORMAL_RUNTIME_SUPPORT_POLICY)
    assert all(
        not Path(path).resolve().is_relative_to(project.resolve())
        for path in governance["application_paths"].values()
    )


@pytest.mark.asyncio
async def test_direct_executor_preserves_authority_checkout_line_endings(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    baseline = (project / "README.md").read_bytes()
    _git(project, "config", "core.autocrlf", "true")
    executor = _DirectProjectExecutor(project, "lf_success")
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await asyncio.wait_for(executor.finished.wait(), timeout=2)
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert (project / "README.md").read_bytes() == baseline
    assert (project / "result.txt").read_bytes() == b"done\n"


def test_attempt_apply_attribution_failure_restores_exact_authority_bytes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    attempt = tmp_path / "attempt"
    _git_project(project)
    _git_project(attempt)
    _git(project, "config", "core.autocrlf", "true")
    baseline = (project / "README.md").read_bytes()
    before_tree = project_code_executor._project_tree_fingerprint(project)
    before_head = _git(project, "rev-parse", "HEAD")
    protected_support = project_code_executor._target_support_fingerprints(project)

    (attempt / "README.md").write_bytes(b"attempt-only-lf\n")
    patch, _expected_tree, changed_paths = project_code_executor._attempt_patch(
        attempt
    )

    with pytest.raises(RuntimeError, match="PROJECT_CHANGE_ATTRIBUTION_FAILED"):
        project_code_executor._apply_attempt_patch(
            project,
            patch,
            source_worktree=attempt,
            changed_paths=changed_paths,
            expected_tree="forced-mismatch",
            before_tree=before_tree,
            before_head=before_head,
            protected_support=protected_support,
        )

    assert (project / "README.md").read_bytes() == baseline
    assert project_code_executor._project_tree_fingerprint(project) == before_tree


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
@pytest.mark.parametrize("authority_file_exists", [True, False])
def test_attempt_content_mirror_rejects_junction_before_external_effect(
    tmp_path: Path, authority_file_exists: bool
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    tracked = project / "nested" / "tracked.txt"
    tracked.parent.mkdir()
    tracked.write_text("authority\n", encoding="utf-8")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "nested baseline")
    if not authority_file_exists:
        tracked.unlink()

    attempt = tmp_path / "attempt"
    attempt.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "tracked.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    junction = attempt / "nested"
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(external)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("host cannot create a Windows junction")

    try:
        with pytest.raises(RuntimeError, match="PROJECT_WORKTREE_BASELINE_MISMATCH"):
            project_code_executor._mirror_git_visible_content(project, attempt)
        assert sentinel.read_text(encoding="utf-8") == "outside\n"
    finally:
        junction.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_attempt_seed_rejects_untracked_junction_before_external_effect(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    untracked = project / "nested" / "untracked.txt"
    untracked.parent.mkdir()
    untracked.write_text("untracked-authority\n", encoding="utf-8")
    parent, worktree = project_code_executor._create_attempt_worktree(
        project, "attempt-untracked-junction", _git(project, "rev-parse", "HEAD")
    )
    external = tmp_path / "external-untracked"
    external.mkdir()
    junction = worktree / "nested"
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(external)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if created.returncode != 0:
        project_code_executor._remove_attempt_worktree(project, parent, worktree)
        pytest.skip("host cannot create a Windows junction")

    try:
        with pytest.raises(RuntimeError, match="PROJECT_WORKTREE_BASELINE_MISMATCH"):
            project_code_executor._seed_attempt_worktree(
                project,
                worktree,
                project_code_executor._project_content_fingerprint(project),
            )
        assert not (external / "untracked.txt").exists()
    finally:
        junction.rmdir()
        project_code_executor._remove_attempt_worktree(project, parent, worktree)


@pytest.mark.asyncio
async def test_direct_executor_serializes_one_project_and_cannot_borrow_another_attempt_diff(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _AttributionExecutor()
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),  # type: ignore[arg-type]
        tmp_path / "p3.sqlite3",
    )
    first_item = _item(project)
    second_item = replace(
        _item(project),
        outbox_id="outbox-2",
        task_id="task-2",
        attempt_id="attempt-2",
        command_id="command-2",
    )

    await adapter.dispatch(first_item)
    await asyncio.wait_for(executor.first_started.wait(), timeout=2)
    with pytest.raises(FormalTaskViolation) as busy:
        await adapter.dispatch(second_item)
    assert busy.value.reason == "EXECUTOR_PROJECT_BUSY"
    assert [request.metadata["formal_attempt_id"] for request in executor.requests] == [
        "attempt-1"
    ]

    executor.release_first.set()
    await _wait_direct_settled(adapter)
    assert (project / "only-attempt-1.txt").read_text(encoding="utf-8") == "attempt-1\n"

    await adapter.dispatch(second_item)
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(
        project,
        task_id="task-2",
        attempt_id="attempt-2",
    )
    second = await adapter.status(task, attempt)
    assert isinstance(second, ExecutorDeliveryResult)
    assert second.observations[-1].attempt_outcome is TerminalOutcome.FAILED
    assert second.observations[-1].error == "NO_EFFECTIVE_TARGET_CHANGE"
    assert [request.metadata["formal_attempt_id"] for request in executor.requests] == [
        "attempt-1",
        "attempt-2",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["cancel", "close"])
async def test_noncooperative_agent_cleanup_is_bounded_and_late_writes_stay_isolated(
    tmp_path: Path,
    operation: str,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _NonCooperativeExecutor()
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),  # type: ignore[arg-type]
        tmp_path / "p3.sqlite3",
        heartbeat_interval=0.5,
        cancel_timeout=0.01,
        close_timeout=0.01,
    )
    delivered = await adapter.dispatch(_item(project))
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    started = asyncio.get_running_loop().time()

    if operation == "cancel":
        result = await adapter.cancel(
            replace(
                _item(project, kind=OutboxKind.ATTEMPT_CANCEL, source_seq=1),
                executor_ref=delivered.executor_ref,
            )
        )
        assert result.observations[-1].attempt_outcome is TerminalOutcome.CANCELLED
        assert (
            result.observations[-1].error == "TASK_CANCEL_ACKNOWLEDGED_CLEANUP_PENDING"
        )
    else:
        await adapter.close(interrupt_running=True)
    assert asyncio.get_running_loop().time() - started < 0.2
    assert not (project / "late-effect.txt").exists()
    assert executor.cancel_signals == 1

    task, attempt = _direct_task_attempt(project)
    terminal_before_release = await adapter.status(task, attempt)
    assert isinstance(terminal_before_release, ExecutorDeliveryResult)
    assert terminal_before_release.observations[-1].attempt_outcome is (
        TerminalOutcome.CANCELLED
        if operation == "cancel"
        else TerminalOutcome.INTERRUPTED
    )

    executor.release.set()
    await _wait_direct_settled(adapter)
    terminal_after_release = await adapter.status(task, attempt)
    assert terminal_after_release == terminal_before_release
    assert not (project / "late-effect.txt").exists()
    isolated_root = Path(executor.requests[0].params["project_dir"])
    assert isolated_root != project.resolve()
    assert not isolated_root.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_close", [False, True])
async def test_close_is_bounded_and_retains_cleanup_while_patch_is_applying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cancel_close: bool,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    entered = Event()
    release = Event()
    real_apply = project_code_executor._apply_attempt_patch

    def blocked_apply(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", blocked_apply)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        tmp_path / "p3.sqlite3",
        close_timeout=0.01,
    )
    await adapter.dispatch(_item(project))
    assert await asyncio.to_thread(entered.wait, 5)

    closing = asyncio.create_task(adapter.close(interrupt_running=True))
    if cancel_close:
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
    else:
        with pytest.raises(FormalTaskViolation) as captured:
            await closing
        assert captured.value.reason == "EXECUTOR_CLOSE_CLEANUP_PENDING"
    assert not (project / "result.txt").exists()

    release.set()
    await _wait_direct_settled(adapter)
    await adapter.close(interrupt_running=True)
    assert (project / "result.txt").read_text("utf-8") == "done"
    settled = _git(project, "status", "--porcelain=v2")
    await asyncio.sleep(0.03)
    assert _git(project, "status", "--porcelain=v2") == settled
    assert adapter._running == {}


@pytest.mark.parametrize("field", ["cancel_timeout", "close_timeout"])
@pytest.mark.parametrize("value", [False, 0, float("inf"), 5.01])
def test_direct_executor_cleanup_timeouts_are_closed_and_bounded(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    with pytest.raises(ValueError, match=field):
        DirectProjectCodeExecutorAdapter(
            _Resolver(_direct_binding(project, executor)),
            tmp_path / f"{field}.sqlite3",
            **{field: value},
        )


@pytest.mark.asyncio
async def test_direct_dispatch_retry_reuses_attempt_and_task_cancel_is_exact(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project, "wait")
    releases: list[str] = []
    resolver = _Resolver(_direct_binding(project, executor, releases=releases))
    adapter = DirectProjectCodeExecutorAdapter(resolver, tmp_path / "p3.sqlite3")
    item = _item(project)

    first = await adapter.dispatch(item)
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    retried = await adapter.dispatch(item)
    cancel_item = replace(
        _item(project, kind=OutboxKind.ATTEMPT_CANCEL, source_seq=1),
        executor_ref=first.executor_ref,
    )
    cancelled = await adapter.cancel(cancel_item)

    assert first.executor_ref == retried.executor_ref
    assert resolver.calls == [True]
    assert len(executor.requests) == 1
    assert cancelled.observations[-1].attempt_outcome is TerminalOutcome.CANCELLED
    assert releases == ["released"]


@pytest.mark.asyncio
async def test_direct_cancel_binding_mismatch_has_zero_attempt_side_effect(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project, "wait")
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )
    delivered = await adapter.dispatch(_item(project))
    cancel_item = replace(
        _item(project, kind=OutboxKind.ATTEMPT_CANCEL, source_seq=1),
        executor_ref=delivered.executor_ref,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.cancel(replace(cancel_item, task_id="task-other"))

    assert raised.value.reason == "ATTEMPT_DELIVERY_CONFLICT"
    assert adapter._journal.get("attempt-1").cancel_requested is False
    assert len(executor.requests) == 1
    await adapter.cancel(cancel_item)


@pytest.mark.asyncio
async def test_direct_cancel_flag_crosses_process_lease_without_widening(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project, "wait")
    database = tmp_path / "p3.sqlite3"
    owner = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        database,
        heartbeat_interval=0.01,
    )
    observer = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        database,
        heartbeat_interval=0.01,
    )
    delivered = await owner.dispatch(_item(project))
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    cancel_item = replace(
        _item(project, kind=OutboxKind.ATTEMPT_CANCEL, source_seq=1),
        executor_ref=delivered.executor_ref,
    )

    with pytest.raises(FormalTaskViolation) as pending:
        await observer.cancel(cancel_item)
    assert pending.value.reason == "EXECUTOR_CANCEL_PENDING"
    await _wait_direct_settled(owner)
    cancelled = await observer.cancel(cancel_item)

    assert cancelled.observations[-1].attempt_outcome is TerminalOutcome.CANCELLED
    assert len(executor.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("behavior", "expected_error"),
    [
        ("agent_error", "PROJECT_EXECUTOR_AGENT_ERROR"),
        ("incomplete", "PROJECT_EXECUTOR_INCOMPLETE"),
        ("head_change", "FORBIDDEN_GIT_HEAD_CHANGE"),
        ("support_change", "RUNTIME_SUPPORT_PATH_MUTATED"),
        ("ignored_only", "NO_EFFECTIVE_TARGET_CHANGE"),
    ],
)
async def test_direct_executor_faults_fail_closed_with_stable_terminal_truth(
    tmp_path: Path,
    behavior: str,
    expected_error: str,
) -> None:
    project = tmp_path / "project"
    _git_project(
        project, ignore="ignored.txt\n" if behavior == "ignored_only" else None
    )
    executor = _DirectProjectExecutor(project, behavior)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await asyncio.wait_for(executor.finished.wait(), timeout=2)
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert len(terminal.observations) == 1
    assert terminal.observations[0].attempt_outcome is TerminalOutcome.FAILED
    assert terminal.observations[0].error == expected_error


@pytest.mark.asyncio
async def test_direct_executor_retains_failed_worktree_cleanup_and_never_completes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )
    real_remove = project_code_executor._remove_attempt_worktree
    removals = 0

    def fail_once(root: Path, parent: Path, worktree: Path) -> None:
        nonlocal removals
        removals += 1
        if removals == 1:
            raise RuntimeError("injected cleanup lock")
        real_remove(root, parent, worktree)

    monkeypatch.setattr(
        project_code_executor, "_remove_attempt_worktree", fail_once
    )
    await adapter.dispatch(_item(project))
    await asyncio.wait_for(executor.finished.wait(), timeout=2)
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert terminal.observations[-1].error is None
    assert terminal.observations[-1].raw_status == "completed_cleanup_pending"
    assert adapter.retained_cleanup_attempt_ids() == ("attempt-1",)
    isolated_root = Path(executor.requests[0].params["project_dir"])
    assert isolated_root.exists()
    restarted = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )
    await restarted.prepare_startup()
    assert restarted.retained_cleanup_attempt_ids() == ()
    assert not isolated_root.exists()
    resolved = await restarted.status(task, attempt)
    assert isinstance(resolved, ExecutorDeliveryResult)
    assert resolved.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert resolved.observations[-1].raw_status == "completed_cleanup_resolved"
    await restarted.close()


@pytest.mark.asyncio
async def test_failed_attempt_exposes_independent_cleanup_pending_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project, "agent_error")
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )
    real_remove = project_code_executor._remove_attempt_worktree
    monkeypatch.setattr(
        project_code_executor,
        "_remove_attempt_worktree",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("injected lock")),
    )
    await adapter.dispatch(_item(project))
    await asyncio.wait_for(executor.finished.wait(), timeout=2)
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.FAILED
    assert terminal.observations[-1].error == "PROJECT_EXECUTOR_AGENT_ERROR"
    assert terminal.observations[-1].raw_status == "failed_cleanup_pending"
    assert adapter.retained_cleanup_attempt_ids() == ("attempt-1",)

    monkeypatch.setattr(
        project_code_executor, "_remove_attempt_worktree", real_remove
    )
    await adapter.close()
    assert adapter.retained_cleanup_attempt_ids() == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("target_is_directory", [False, True])
async def test_direct_executor_rejects_git_visible_symlink_before_agent_effects(
    tmp_path: Path,
    target_is_directory: bool,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    external = tmp_path / ("external-dir" if target_is_directory else "external.txt")
    if target_is_directory:
        external.mkdir()
        marker = external / "marker.txt"
    else:
        marker = external
    marker.write_text("unchanged\n", encoding="utf-8")
    link = project / ("unsafe-dir" if target_is_directory else "unsafe-file")
    try:
        link.symlink_to(external, target_is_directory=target_is_directory)
    except OSError as error:
        pytest.skip(f"host cannot create symlinks: {error}")
    _git(project, "add", ".")
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    adapter = DirectProjectCodeExecutorAdapter(resolver, tmp_path / "p3.sqlite3")

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(project))

    assert raised.value.reason == "EXECUTION_TARGET_SYMLINK_UNSAFE"
    assert marker.read_text("utf-8") == "unchanged\n"
    assert resolver.calls == []
    assert executor.requests == []


@pytest.mark.asyncio
async def test_direct_executor_rechecks_symlinks_after_agent_before_target_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )
    real_reject = project_code_executor._reject_git_visible_symlinks
    post_agent_checks: list[Path] = []

    def reject_after_agent(root: Path) -> None:
        real_reject(root)
        if executor.finished.is_set() and root.resolve() != project.resolve():
            post_agent_checks.append(root.resolve())
            raise FormalTaskViolation(
                "EXECUTION_TARGET_SYMLINK_UNSAFE",
                "simulated post-Agent reparse discovery",
                ErrorCode.PERMISSION_DENIED,
            )

    monkeypatch.setattr(
        project_code_executor, "_reject_git_visible_symlinks", reject_after_agent
    )
    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert post_agent_checks
    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.FAILED
    assert terminal.observations[-1].error == "EXECUTION_TARGET_SYMLINK_UNSAFE"
    assert not (project / "result.txt").exists()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
async def test_direct_executor_rejects_git_visible_windows_junction(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    external = tmp_path / "external-junction-target"
    external.mkdir()
    marker = external / "marker.txt"
    marker.write_text("unchanged\n", encoding="utf-8")
    junction = project / "unsafe-junction"
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(external)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("host cannot create a Windows junction")
    _git(project, "add", ".")
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    adapter = DirectProjectCodeExecutorAdapter(resolver, tmp_path / "p3.sqlite3")

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(project))

    assert raised.value.reason == "EXECUTION_TARGET_SYMLINK_UNSAFE"
    assert marker.read_text("utf-8") == "unchanged\n"
    assert resolver.calls == []
    assert executor.requests == []


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_attempt_worktree_rejects_preplanted_temp_junction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    external = tmp_path / "external-attempt-root"
    external.mkdir()
    base = temp_root / "jiuwenswarm-live-voice-d0"
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(base), str(external)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("host cannot create a Windows junction")
    monkeypatch.setattr(
        project_code_executor.tempfile, "gettempdir", lambda: str(temp_root)
    )

    try:
        with pytest.raises(RuntimeError, match="PROJECT_WORKTREE_UNAVAILABLE"):
            project_code_executor._create_attempt_worktree(
                project, "attempt-preplanted", _git(project, "rev-parse", "HEAD")
            )
    finally:
        base.rmdir()

    assert list(external.iterdir()) == []


@pytest.mark.asyncio
async def test_direct_executor_feature_off_allocates_no_binding_or_agent_work(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    adapter = DirectProjectCodeExecutorAdapter(resolver, tmp_path / "p3.sqlite3")
    await adapter.close()

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(project))

    assert raised.value.reason == "EXECUTOR_CAPABILITY_UNAVAILABLE"
    assert resolver.calls == []
    assert executor.requests == []


@pytest.mark.asyncio
async def test_direct_executor_rejects_runtime_support_inside_target_before_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.project_code_executor.get_agent_workspace_dir",
        lambda: project / "runtime",
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.project_code_executor.get_prompt_attachment_dir",
        lambda: project / "runtime" / "prompt_attachment",
    )
    adapter = DirectProjectCodeExecutorAdapter(resolver, tmp_path / "p3.sqlite3")

    with pytest.raises(FormalTaskViolation) as raised:
        await adapter.dispatch(_item(project))

    assert raised.value.reason == "RUNTIME_SUPPORT_PATH_INSIDE_TARGET"
    assert resolver.calls == []
    assert executor.requests == []


@pytest.mark.asyncio
async def test_direct_executor_shutdown_is_interrupted_not_user_cancelled(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project, "wait")
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )
    await adapter.dispatch(_item(project))
    await asyncio.wait_for(executor.started.wait(), timeout=2)

    await adapter.close(interrupt_running=True)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[0].attempt_outcome is TerminalOutcome.INTERRUPTED
    assert terminal.observations[0].error == "EXECUTOR_SHUTDOWN_INTERRUPTED"


@pytest.mark.asyncio
async def test_direct_executor_immediate_shutdown_cannot_strand_prestart_attempt(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project, "wait")
    releases: list[str] = []
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor, releases=releases)),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await adapter.close(interrupt_running=True)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[0].attempt_outcome is TerminalOutcome.INTERRUPTED
    assert terminal.observations[0].error == "EXECUTOR_SHUTDOWN_INTERRUPTED"
    assert releases == ["released"]


@pytest.mark.asyncio
async def test_direct_executor_close_waits_for_inflight_dispatch_handoff(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project, "wait")
    binding = _direct_binding(project, executor)
    resolving = asyncio.Event()
    resolved = asyncio.Event()

    class DelayedResolver:
        async def resolve(self, _spec, *, for_dispatch: bool):
            assert for_dispatch is True
            resolving.set()
            await resolved.wait()
            return binding

    adapter = DirectProjectCodeExecutorAdapter(
        DelayedResolver(),
        tmp_path / "p3.sqlite3",
    )
    dispatch = asyncio.create_task(adapter.dispatch(_item(project)))
    await asyncio.wait_for(resolving.wait(), timeout=2)
    closing = asyncio.create_task(adapter.close(interrupt_running=True))
    await asyncio.sleep(0)
    resolved.set()

    await dispatch
    await asyncio.wait_for(closing, timeout=2)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[0].attempt_outcome is TerminalOutcome.INTERRUPTED
    assert terminal.observations[0].error == "EXECUTOR_SHUTDOWN_INTERRUPTED"
    assert adapter._running == {}


@pytest.mark.asyncio
async def test_direct_executor_heartbeat_failure_interrupts_and_releases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project, "wait")
    releases: list[str] = []
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor, releases=releases)),
        tmp_path / "p3.sqlite3",
        heartbeat_interval=0.01,
    )

    def fail_heartbeat(*_args, **_kwargs):
        raise RuntimeError("private heartbeat failure")

    monkeypatch.setattr(adapter._journal, "heartbeat", fail_heartbeat)
    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[0].attempt_outcome is TerminalOutcome.INTERRUPTED
    assert terminal.observations[0].error == "EXECUTOR_HEARTBEAT_FAILED"
    assert releases == ["released"]


@pytest.mark.asyncio
async def test_direct_executor_restart_recovers_only_expired_attempt_lease(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    clock_values = iter(
        [
            "2026-08-07T10:00:00Z",
            "2026-08-07T10:00:00Z",
            "2026-08-07T10:00:00Z",
        ]
    )
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
        clock=lambda: next(clock_values),
    )
    item = _item(project)
    before_tree = _git(project, "status", "--porcelain=v2")
    created, _ = adapter._journal.create(
        item=item,
        project_root=str(project),
        before_tree=before_tree,
        before_content=project_code_executor._project_content_fingerprint(project),
        before_head=_git(project, "rev-parse", "HEAD"),
        protected_support={name: "baseline" for name in FORMAL_RUNTIME_SUPPORT_POLICY},
        governance={"policy": dict(FORMAL_RUNTIME_SUPPORT_POLICY)},
        owner_id="dead-process",
        now="2026-08-07T10:00:00Z",
    )
    assert created is True
    adapter._journal.start(
        item.attempt_id,
        owner_id="dead-process",
        now="2026-08-07T10:00:00Z",
    )

    live = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
        clock=lambda: "2026-08-07T10:04:59Z",
    )
    expired = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
        clock=lambda: "2026-08-07T10:05:01Z",
    )

    assert await live.prepare_startup() == 0
    assert await expired.prepare_startup() == 1
    task, attempt = _direct_task_attempt(project)
    terminal = await expired.status(task, attempt)
    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.INTERRUPTED
    assert terminal.observations[-1].error == "EXECUTOR_PROCESS_RESTARTED"


@pytest.mark.parametrize(
    ("root_state", "expected_outcome", "expected_status", "expected_error"),
    [
        (
            "before",
            TerminalOutcome.INTERRUPTED,
            "restart_before_apply",
            "EXECUTOR_PROCESS_RESTARTED",
        ),
        (
            "applied",
            TerminalOutcome.COMPLETED,
            "restart_apply_completed",
            None,
        ),
        (
            "unknown",
            TerminalOutcome.UNKNOWN,
            "restart_apply_result_unknown",
            "EXECUTOR_RESTART_APPLY_RESULT_UNKNOWN",
        ),
    ],
)
def test_direct_executor_restart_classifies_atomic_apply_crash_window(
    tmp_path: Path,
    root_state: str,
    expected_outcome: TerminalOutcome,
    expected_status: str,
    expected_error: str | None,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    journal = project_code_executor._DirectProjectAttemptJournal(
        tmp_path / "p3.sqlite3"
    )
    item = _item(project)
    before_content = project_code_executor._project_content_fingerprint(project)
    before_head = _git(project, "rev-parse", "HEAD")
    protected_support = project_code_executor._target_support_fingerprints(project)
    created, _ = journal.create(
        item=item,
        project_root=str(project),
        before_tree=_git(project, "status", "--porcelain=v2"),
        before_content=before_content,
        before_head=before_head,
        protected_support=protected_support,
        governance={"policy": dict(FORMAL_RUNTIME_SUPPORT_POLICY)},
        owner_id="dead-process",
        now="2026-08-07T10:00:00Z",
    )
    assert created is True
    journal.start(
        item.attempt_id,
        owner_id="dead-process",
        now="2026-08-07T10:00:00Z",
    )

    readme = project / "README.md"
    readme.write_text("expected change\n", encoding="utf-8")
    expected_content = project_code_executor._project_content_fingerprint(project)
    readme.write_text("baseline\n", encoding="utf-8")
    reserved, _ = journal.reserve_completion(
        item.attempt_id,
        owner_id="dead-process",
        expected_tree=expected_content,
        now="2026-08-07T10:00:00Z",
    )
    assert reserved is True
    if root_state == "applied":
        readme.write_text("expected change\n", encoding="utf-8")
    elif root_state == "unknown":
        readme.write_text("unexpected change\n", encoding="utf-8")

    assert journal.recover_expired(now="2026-08-07T10:05:01Z") == 1
    recovered = journal.get(item.attempt_id)
    assert recovered is not None
    assert recovered.state is FormalAttemptState.TERMINAL
    assert recovered.outcome is expected_outcome
    assert recovered.raw_status == expected_status
    assert recovered.error == expected_error
