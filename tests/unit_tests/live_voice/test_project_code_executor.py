# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import runpy
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

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
    PersistedExecutorSelection,
    PersistentOutboxItem,
    PersistentTaskRecord,
    ResolvedTaskContext,
    TaskAdjustmentRequest,
    TaskAdjustmentSettlement,
    TaskAdjustmentState,
)
from jiuwenswarm.server.live_voice.executor_capabilities import (
    TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
    ExecutorCapabilityProfile,
    TaskExecutionRequirements,
    select_executor,
)
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    AgentManagerProjectBindingResolver,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    AttemptProjectExecutorLease,
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
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.runtime.agent_adapter import interface as agent_interface
from jiuwenswarm.server.runtime.agent_manager import AgentManager
from scripts.live_voice.w2_rehearsal.w2_d069_runtime_diagnostic import (
    _P3_CANCEL_ENTRY_DELTA,
    _P3_FROZEN_ENTRY_COUNTS,
    _P3NonterminalBarrier,
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
            elif self.behavior == "observe_wait":
                yield AgentResponseChunk(
                    request.request_id,
                    request.channel_id,
                    payload={
                        "event_type": "chat.tool_call",
                        "tool_call": {
                            "tool_name": "read_file",
                            "tool_call_id": f"call-{request.request_id}",
                            "arguments": {"path": "PRIVATE_PATH_SENTINEL"},
                        },
                    },
                    is_complete=False,
                )
                yield AgentResponseChunk(
                    request.request_id,
                    request.channel_id,
                    payload={
                        "event_type": "chat.tool_result",
                        "tool_name": "read_file",
                        "tool_call_id": f"call-{request.request_id}",
                        "result": "PRIVATE_RESULT_SENTINEL",
                        "success": True,
                    },
                    is_complete=False,
                )
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


class _DemoItineraryProjectExecutor(_DirectProjectExecutor):
    def __init__(self, project: Path, *, extra_change: bool = False) -> None:
        super().__init__(project)
        self.extra_change = extra_change

    async def process_background_code_task_stream(self, request):
        self.requests.append(request)
        self.started.set()
        project = Path(request.params["project_dir"]).resolve()
        try:
            itinerary = (
                "# 三天行程\n\n"
                "## 第一天\n\n20:00–21:30 自由活动。\n\n"
                "## 第二天\n\n08:30 参观博物馆。\n\n"
                "## 第三天\n\n10:00 城市步行。\n"
            )
            (project / "itinerary.md").write_text(itinerary, encoding="utf-8")
            if self.extra_change:
                (project / "outside-fixture.txt").write_text(
                    "forbidden\n", encoding="utf-8"
                )
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={
                    "event_type": "chat.final",
                    "content": "第二天最早的固定安排是 08:30 参观博物馆。",
                },
                is_complete=True,
            )
        finally:
            self.finished.set()


class _AdjustableItineraryProjectExecutor(_DirectProjectExecutor):
    def __init__(self, project: Path) -> None:
        super().__init__(project)
        self.initial_complete = asyncio.Event()

    async def process_background_code_task_stream(self, request):
        self.requests.append(request)
        self.started.set()
        project = Path(request.params["project_dir"]).resolve()
        if request.params["source"] == "live_voice.formal_task.d0":
            (project / "itinerary.md").write_text(
                "# Itinerary\n\nMuseum at 08:30.\n",
                encoding="utf-8",
            )
            content = "Initial itinerary ready."
            self.initial_complete.set()
        else:
            query = request.params["query"]
            itinerary = (project / "itinerary.md").read_text(encoding="utf-8")
            if "09:30" in query:
                itinerary = itinerary.replace("08:30", "09:30")
                content = "Museum moved to 09:30."
            elif "vegetarian" in query:
                itinerary += "Vegetarian lunch.\n"
                content = "Vegetarian lunch added."
            else:
                content = "Adjustment could not be applied."
            (project / "itinerary.md").write_text(itinerary, encoding="utf-8")
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={"event_type": "chat.final", "content": content},
            is_complete=True,
        )


class _ObservedAdjustableProjectExecutor(_DirectProjectExecutor):
    """Emit realistic private tool payloads without crediting a real Agent/Tool."""

    sentinel = "PRIVATE_STREAM_SENTINEL"

    def __init__(self, project: Path) -> None:
        super().__init__(project)
        self.initial_complete = asyncio.Event()

    async def process_background_code_task_stream(self, request):
        self.requests.append(request)
        self.started.set()
        project = Path(request.params["project_dir"]).resolve()
        initial = request.params["source"] == "live_voice.formal_task.d0"
        tool_name = "write_file" if initial else "edit_file"
        call_id = f"call-{self.sentinel}-{'initial' if initial else 'adjustment'}"
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={
                "event_type": "chat.tool_call",
                "tool_call": {
                    "tool_name": tool_name,
                    "tool_call_id": call_id,
                    "arguments": {
                        "path": f"C:/private/{self.sentinel}.txt",
                        "content": self.sentinel,
                    },
                },
            },
            is_complete=False,
        )
        if initial:
            (project / "result.txt").write_text("initial\n", encoding="utf-8")
            self.initial_complete.set()
        else:
            (project / "result.txt").write_text("adjusted\n", encoding="utf-8")
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={
                "event_type": "chat.tool_result",
                "tool_name": tool_name,
                "tool_call_id": call_id,
                "result": self.sentinel,
                "raw_output": self.sentinel,
                "success": True,
            },
            is_complete=False,
        )
        yield AgentResponseChunk(
            request.request_id,
            request.channel_id,
            payload={"event_type": "chat.final", "content": self.sentinel},
            is_complete=True,
        )


class _ExactRootDirectProjectExecutor(_DirectProjectExecutor):
    async def process_background_code_task_stream(self, request):
        assert Path(request.params["project_dir"]).resolve() == self.project.resolve()
        async for chunk in super().process_background_code_task_stream(request):
            yield chunk


class _LfRewriteProjectExecutor(_DirectProjectExecutor):
    async def process_background_code_task_stream(self, request):
        self.requests.append(request)
        self.started.set()
        project = Path(request.params["project_dir"]).resolve()
        try:
            (project / "README.md").write_bytes(b"baseline\ncompleted\n")
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


class _MappedResolver:
    def __init__(self, bindings: dict[Path, ProjectExecutionBinding]) -> None:
        self.bindings = bindings
        self.calls: list[Path] = []

    async def resolve(self, spec, *, for_dispatch: bool):
        assert for_dispatch is True
        root = Path(spec.context.file_path).resolve()
        self.calls.append(root)
        return self.bindings[root]


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


def _direct_selection(
    profile: ExecutorCapabilityProfile | None = None,
) -> PersistedExecutorSelection:
    selected_profile = profile or DirectProjectCodeExecutorAdapter.capability_profile()
    requirements = TaskExecutionRequirements(
        schema_version=TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        operation_versions=(
            ("dispatch", "v1"),
            ("status", "v1"),
            ("cancel", "v1"),
            ("adjust.task-checkpoint", "v1"),
            ("reconcile.d0", "v1"),
        ),
        durability_level="D0",
        side_effect_class="project_mutation",
        project_serialization="exclusive",
    )
    selection = select_executor((selected_profile,), requirements)
    return PersistedExecutorSelection(
        adapter_id=selection.profile.adapter_id,
        capability_profile_json=selection.profile.canonical_bytes(),
        capability_profile_digest=selection.profile_digest,
        execution_requirements_json=selection.requirements.canonical_bytes(),
    )


def _foreign_adapter_selection() -> PersistedExecutorSelection:
    """Return a valid selection which is deliberately not owned by Direct."""

    foreign = replace(
        DirectProjectCodeExecutorAdapter.capability_profile(),
        profile_id="other.product-code.d0.v1",
        adapter_id="other.product-code",
        adapter_protocol_version="other.product-code.v1",
    )
    return _direct_selection(foreign)


def _forged_direct_capability_selection() -> PersistedExecutorSelection:
    """Return a self-consistent Direct identity with capabilities it never emitted."""

    direct = DirectProjectCodeExecutorAdapter.capability_profile()
    forged = replace(
        direct,
        operation_versions=direct.operation_versions + (("pause", "v1"),),
        enforcement_facts=direct.enforcement_facts + ("control.pause",),
    )
    return _direct_selection(forged)


def _store_effect_counts(database: Path) -> tuple[int, ...]:
    """Count every Store surface forbidden to a rejected Direct control."""

    with sqlite3.connect(database) as connection:
        return tuple(
            int(connection.execute(statement).fetchone()[0])
            for statement in (
                "SELECT COUNT(*) FROM tasks",
                "SELECT COUNT(*) FROM attempts",
                "SELECT COUNT(*) FROM task_events",
                "SELECT COUNT(*) FROM executor_events",
                "SELECT COUNT(*) FROM outbox",
            )
        )


def _adjustment_item(
    project: Path,
    *,
    command_id: str,
    adjustment: str,
    requested_seq: int,
) -> PersistentOutboxItem:
    return PersistentOutboxItem(
        outbox_id=f"outbox-{command_id}",
        kind=OutboxKind.ATTEMPT_ADJUST,
        task_id="task-1",
        attempt_id="attempt-1",
        command_id=command_id,
        scope=_scope(),
        spec=_spec(project),
        executor_ref="d0-project:attempt-1",
        source_seq=1,
        state=OutboxState.CLAIMED,
        delivery_count=1,
        claim_token=f"claim-{command_id}",
        adjustment=TaskAdjustmentRequest(
            command_id,
            adjustment,
            requested_seq,
        ),
    )


def _direct_task_attempt(
    project: Path,
    *,
    source_seq: int = 1,
    task_id: str = "task-1",
    attempt_id: str = "attempt-1",
    selection: PersistedExecutorSelection | None = None,
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
        "command-create-1",
        None,
        1,
    )
    attempt = PersistentAttemptRecord(
        attempt_id,
        task_id,
        FORMAL_PROJECT_EXECUTOR_ID,
        f"d0-project:{attempt_id}",
        FormalAttemptState.RUNNING,
        None,
        source_seq,
        selection=selection,
    )
    return task, attempt


async def _wait_direct_settled(
    adapter: DirectProjectCodeExecutorAdapter,
) -> None:
    # Await actual owned worker completion (including Git apply and cleanup),
    # not a five-second polling budget that is shorter than the combined
    # cleanup boundaries. This helper asserts settlement, not product latency.
    async def settled() -> None:
        while adapter._running:
            await asyncio.gather(
                *(asyncio.shield(task) for task in tuple(adapter._running.values())),
                return_exceptions=True,
            )
            await asyncio.sleep(0)

    try:
        await asyncio.wait_for(settled(), timeout=30)
    except TimeoutError as error:
        stacks = {
            attempt_id: [
                (frame.f_code.co_name, frame.f_lineno) for frame in task.get_stack()
            ]
            for attempt_id, task in adapter._running.items()
        }
        raise AssertionError(
            f"direct Executor worker did not settle: {stacks}"
        ) from error


async def _wait_direct_terminal(
    adapter: DirectProjectCodeExecutorAdapter,
    attempt_id: str = "attempt-1",
):
    for _ in range(500):
        record = adapter._journal.get(attempt_id)
        if record is not None and record.state is FormalAttemptState.TERMINAL:
            return record
        await asyncio.sleep(0.01)
    raise AssertionError("direct Executor attempt did not become terminal")


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
        "command-create-1",
        None,
        1,
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
        "command-create-1",
        None,
        1,
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
        "command-create-1",
        None,
        1,
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
        "command-create-1",
        None,
        1,
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


def test_chat_final_with_nul_is_never_publishable_result_content() -> None:
    assert (
        project_code_executor._bounded_chat_final(
            {"event_type": "chat.final", "content": "unsafe\x00result"}
        )
        is None
    )


@pytest.mark.asyncio
async def test_direct_capability_profile_is_stable_truthful_and_runtime_free(
    tmp_path: Path,
) -> None:
    project = tmp_path / "profile-project"
    _git_project(project)
    first = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        tmp_path / "first-private.sqlite3",
    )
    second = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        tmp_path / "second-private.sqlite3",
        attempt_timeout=60,
    )

    try:
        first_profile = first.capability_profile()
        second_profile = second.capability_profile()

        assert first_profile is second_profile
        assert first_profile.profile_id == "live-voice.direct-project-code.d0.v2"
        assert first_profile.executor_id == "jiuwenswarm_code_agent.project_code"
        assert first_profile.adapter_id == "live-voice.direct-project-code"
        assert (
            first_profile.adapter_protocol_version
            == "live-voice.direct-project-code.v1"
        )
        assert first_profile.operation_versions == (
            ("adjust.task-checkpoint", "v1"),
            ("cancel", "v1"),
            ("dispatch", "v1"),
            ("reconcile.d0", "v1"),
            ("status", "v1"),
        )
        assert first_profile.durability_level == "D0"
        assert first_profile.durability_version == "live-voice.direct-d0.v1"
        assert first_profile.project_serialization == "exclusive"
        assert first_profile.max_live_attempts == 32
        assert first_profile.enforcement_facts == (
            "direct-journal.d0",
            "direct-lease.generation",
            "direct-runtime-deadline.absolute",
            "os-ownership-lock.cross-process",
            "side-effect.project-mutation",
        )
        unsupported = {
            "checkpoint.d1",
            "pause",
            "provide_input",
            "reconcile.d2",
            "reprioritize.running",
            "resume",
            "update.generic-running",
        }
        assert unsupported.isdisjoint(
            operation for operation, _version in first_profile.operation_versions
        )
        assert not hasattr(ProjectCodeExecutorAdapter, "capability_profile")
        canonical = first_profile.canonical_bytes().decode("ascii")
        assert tmp_path.name not in canonical
        assert "sqlite" not in canonical
        assert first._owner_id not in canonical
        assert second._owner_id not in canonical
        assert "secret" not in canonical.casefold()
        assert len(first_profile.digest_sha256()) == 64
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_direct_d2_is_an_explicit_store_backed_candidate_only(
    tmp_path: Path,
) -> None:
    project = tmp_path / "candidate-project"
    _git_project(project)
    database = tmp_path / "candidate.sqlite3"
    resolver = _Resolver(_direct_binding(project, _DirectProjectExecutor(project)))
    legacy = DirectProjectCodeExecutorAdapter(resolver, database)
    store = SqliteTaskStore(database)
    durable = DirectProjectCodeExecutorAdapter(
        resolver,
        database,
        durability_store=store,
    )

    try:
        assert legacy.capability_profiles() == (legacy.capability_profile(),)
        candidates = durable.capability_profiles()
        assert candidates[0] is durable.capability_profile()
        assert tuple(profile.durability_level for profile in candidates) == (
            "D0",
            "D2",
        )
        assert candidates[1].profile_id == "live-voice.direct-project-code.d2.v2"
        with pytest.raises(ValueError, match="same canonical"):
            DirectProjectCodeExecutorAdapter(
                resolver,
                database,
                durability_store=SqliteTaskStore(tmp_path / "foreign.sqlite3"),
            )
    finally:
        await legacy.close()
        await durable.close()


@pytest.mark.asyncio
async def test_direct_candidates_derive_d0_from_current_profile_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "candidate-profile-authority-project"
    _git_project(project)
    database = tmp_path / "candidate-profile-authority.sqlite3"
    resolver = _Resolver(_direct_binding(project, _DirectProjectExecutor(project)))
    changed_legacy = replace(
        DirectProjectCodeExecutorAdapter.capability_profile(),
        profile_id="live-voice.direct-project-code.d0.v3",
    )
    monkeypatch.setattr(
        DirectProjectCodeExecutorAdapter,
        "capability_profile",
        classmethod(lambda cls: changed_legacy),
    )
    legacy = DirectProjectCodeExecutorAdapter(resolver, database)
    durable = DirectProjectCodeExecutorAdapter(
        resolver,
        database,
        durability_store=SqliteTaskStore(database),
    )

    try:
        assert legacy.capability_profiles() == (changed_legacy,)
        candidates = durable.capability_profiles()
        assert candidates[0] is changed_legacy
        assert candidates[1].profile_id == "live-voice.direct-project-code.d2.v2"
    finally:
        await legacy.close()
        await durable.close()


def test_direct_stream_observer_defaults_off_and_never_changes_profile(
    tmp_path: Path,
) -> None:
    project = tmp_path / "observer-profile-project"
    _git_project(project)
    resolver = _Resolver(_direct_binding(project, _DirectProjectExecutor(project)))
    baseline = DirectProjectCodeExecutorAdapter(resolver, tmp_path / "baseline.sqlite3")
    observed = DirectProjectCodeExecutorAdapter(
        resolver,
        tmp_path / "observed.sqlite3",
        stream_observer=lambda _observation: None,
    )

    assert baseline._stream_observer is None
    assert baseline.stream_observer_failure_count == 0
    assert baseline.capability_profile() is observed.capability_profile()
    assert (
        baseline.capability_profile().digest_sha256()
        == observed.capability_profile().digest_sha256()
    )


@pytest.mark.asyncio
async def test_direct_stream_observer_is_content_free_immutable_and_pairs_each_stream(
    tmp_path: Path,
) -> None:
    project = tmp_path / "observed-adjustable-project"
    _git_project(project)
    executor = _ObservedAdjustableProjectExecutor(project)
    checkpoint_open = asyncio.Event()
    release_checkpoint = asyncio.Event()
    observations: list[object] = []
    observer_health_reads: list[int] = []
    adapter: DirectProjectCodeExecutorAdapter | None = None

    async def checkpoint_barrier(_attempt_id: str) -> None:
        checkpoint_open.set()
        await release_checkpoint.wait()

    def observe(observation: object) -> None:
        assert adapter is not None
        observer_health_reads.append(adapter.stream_observer_failure_count)
        observations.append(observation)

    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "observed.sqlite3",
        clock=lambda: "2026-08-05T12:00:00Z",
        adjustment_checkpoint_barrier=checkpoint_barrier,
        stream_observer=observe,
    )
    try:
        await adapter.dispatch(_item(project))
        await asyncio.wait_for(checkpoint_open.wait(), timeout=2)
        adjustment = _adjustment_item(
            project,
            command_id="adjust-1",
            adjustment="Apply one bounded private adjustment.",
            requested_seq=4,
        )
        delivery_task = asyncio.create_task(adapter.adjust(adjustment))
        await asyncio.wait_for(
            adapter._adjustment_checkpoints["attempt-1"].changed.wait(), timeout=2
        )
        release_checkpoint.set()
        delivery = await asyncio.wait_for(delivery_task, timeout=2)
        assert delivery.state is TaskAdjustmentState.APPLIED
        await adapter.settle_adjustment(
            adjustment,
            TaskAdjustmentSettlement(TaskAdjustmentState.APPLIED, False),
        )
        await _wait_direct_settled(adapter)

        assert all(
            isinstance(item, project_code_executor.DirectStreamObservation)
            for item in observations
        )
        assert [item.sequence for item in observations] == [1, 2, 1, 2]
        assert [item.stream_kind for item in observations] == [
            "initial",
            "initial",
            "adjustment",
            "adjustment",
        ]
        assert [item.event_kind for item in observations] == [
            "tool_call",
            "tool_result",
            "tool_call",
            "tool_result",
        ]
        assert [item.file_tool_kind for item in observations] == [
            "write",
            "write",
            "edit",
            "edit",
        ]
        assert [item.result_status for item in observations] == [
            "not_applicable",
            "success",
            "not_applicable",
            "success",
        ]
        assert {item.task_ref for item in observations} == {"task-1"}
        assert {item.attempt_ref for item in observations} == {"attempt-1"}
        assert [item.run_ref for item in observations] == [
            "d0-project:attempt-1",
            "d0-project:attempt-1",
            "d0-project:attempt-1:adjust:adjust-1",
            "d0-project:attempt-1:adjust:adjust-1",
        ]
        assert {item.observed_at for item in observations} == {"2026-08-05T12:00:00Z"}
        assert observer_health_reads == [0, 0, 0, 0]
        assert all(item.tool_name_digest.startswith("sha256:") for item in observations)
        assert all(item.call_id_digest.startswith("sha256:") for item in observations)
        assert observations[0].tool_name_digest == observations[1].tool_name_digest
        assert observations[0].call_id_digest == observations[1].call_id_digest
        assert observations[2].tool_name_digest == observations[3].tool_name_digest
        assert observations[2].call_id_digest == observations[3].call_id_digest

        rendered = repr(observations)
        encoded = json.dumps([asdict(item) for item in observations])
        assert _ObservedAdjustableProjectExecutor.sentinel not in rendered
        assert _ObservedAdjustableProjectExecutor.sentinel not in encoded
        with pytest.raises(FrozenInstanceError):
            observations[0].sequence = 99
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_direct_stream_observer_maps_unknown_tool_and_error_without_raw_fields(
    tmp_path: Path,
) -> None:
    sentinel = "PRIVATE_UNKNOWN_TOOL_SENTINEL"
    project = tmp_path / "unknown-tool-project"
    _git_project(project)

    class UnknownToolExecutor(_DirectProjectExecutor):
        async def process_background_code_task_stream(self, request):
            project_root = Path(request.params["project_dir"])
            (project_root / "result.txt").write_text("done", encoding="utf-8")
            tool_name = f"private-{sentinel}"
            call_id = f"call-{sentinel}"
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={
                    "event_type": "chat.tool_call",
                    "tool_call": {
                        "tool_name": tool_name,
                        "tool_call_id": call_id,
                        "arguments": {"private": sentinel},
                    },
                },
                is_complete=False,
            )
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={
                    "event_type": "chat.tool_result",
                    "tool_name": tool_name,
                    "tool_call_id": call_id,
                    "result": sentinel,
                    "error": sentinel,
                    "is_error": True,
                },
                is_complete=False,
            )
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={"event_type": "chat.final", "content": sentinel},
                is_complete=True,
            )

    observations: list[object] = []
    executor = UnknownToolExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "unknown.sqlite3",
        stream_observer=observations.append,
    )
    try:
        await adapter.dispatch(_item(project))
        await _wait_direct_settled(adapter)

        assert [item.file_tool_kind for item in observations] == ["unknown", "unknown"]
        assert [item.result_status for item in observations] == [
            "not_applicable",
            "error",
        ]
        assert sentinel not in repr(observations)
        assert sentinel not in json.dumps([asdict(item) for item in observations])
    finally:
        await adapter.close()


@pytest.mark.parametrize("invalid", [None, "", 7, "bad\x00id", "x" * 257])
def test_direct_stream_observer_marks_every_invalid_call_identity_closed(
    invalid: object,
) -> None:
    expected = (
        "sha256:" + hashlib.sha256(b"live-voice.invalid-tool-call-id").hexdigest()
    )

    observation = project_code_executor._closed_direct_stream_observation(
        {
            "event_type": "chat.tool_call",
            "tool_call": {"tool_name": "write_file", "tool_call_id": invalid},
        },
        task_ref="task-1",
        attempt_ref="attempt-1",
        run_ref="run-1",
        sequence=1,
        stream_kind="initial",
        observed_at="2026-08-20T10:00:00Z",
    )

    assert observation is not None
    assert observation.file_tool_kind == "write"
    assert observation.call_id_digest == expected


@pytest.mark.parametrize("invalid", [None, "", 7, "bad\x00name", "x" * 65])
def test_direct_stream_observer_marks_every_invalid_tool_identity_unknown(
    invalid: object,
) -> None:
    expected = "sha256:" + hashlib.sha256(b"live-voice.invalid-tool-name").hexdigest()

    observation = project_code_executor._closed_direct_stream_observation(
        {
            "event_type": "chat.tool_call",
            "tool_call": {"tool_name": invalid, "tool_call_id": "call-1"},
        },
        task_ref="task-1",
        attempt_ref="attempt-1",
        run_ref="run-1",
        sequence=1,
        stream_kind="initial",
        observed_at="2026-08-20T10:00:00Z",
    )

    assert observation is not None
    assert observation.file_tool_kind == "unknown"
    assert observation.tool_name_digest == expected


@pytest.mark.asyncio
async def test_direct_stream_observer_failure_and_awaitable_never_change_execution(
    tmp_path: Path,
) -> None:
    project = tmp_path / "observer-failure-project"
    _git_project(project)
    executor = _ObservedAdjustableProjectExecutor(project)
    calls = 0

    async def forbidden_awaitable() -> None:
        raise AssertionError("observer awaitables must never execute")

    def failing_observer(_observation):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("PRIVATE_OBSERVER_FAILURE")
        return forbidden_awaitable()

    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "observer-failure.sqlite3",
        stream_observer=failing_observer,
    )
    try:
        await adapter.dispatch(_item(project))
        await _wait_direct_settled(adapter)
        task, attempt = _direct_task_attempt(project)
        terminal = await adapter.status(task, attempt)

        assert calls == 2
        assert adapter.stream_observer_failure_count == 2
        assert isinstance(terminal, ExecutorDeliveryResult)
        assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
        assert (project / "result.txt").read_text(encoding="utf-8") == "initial\n"
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_selected_direct_delivery_and_status_bind_the_persisted_selection(
    tmp_path: Path,
) -> None:
    """Catches selected lifecycle observations losing their immutable profile."""

    project = tmp_path / "selected-project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "selected.sqlite3",
    )
    selection = _direct_selection()
    item = replace(_item(project), selection=selection)

    try:
        delivered = await adapter.dispatch(item)
        assert delivered.observations
        assert {
            (event.adapter_id, event.capability_profile_digest)
            for event in delivered.observations
        } == {(selection.adapter_id, selection.capability_profile_digest)}

        await asyncio.wait_for(executor.finished.wait(), timeout=2)
        await _wait_direct_settled(adapter)
        task, attempt = _direct_task_attempt(project, selection=selection)
        terminal = await adapter.status(task, attempt)

        assert isinstance(terminal, ExecutorDeliveryResult)
        assert terminal.observations
        assert {
            (event.adapter_id, event.capability_profile_digest)
            for event in terminal.observations
        } == {(selection.adapter_id, selection.capability_profile_digest)}
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_selected_direct_dispatch_rejects_profile_drift_before_any_effect(
    tmp_path: Path,
) -> None:
    """Catches a new Attempt running under a profile other than its selection."""

    project = tmp_path / "mismatched-profile-project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    adapter = DirectProjectCodeExecutorAdapter(
        resolver,
        tmp_path / "mismatched-profile.sqlite3",
    )
    changed_profile = replace(
        DirectProjectCodeExecutorAdapter.capability_profile(),
        profile_id="live-voice.direct-project-code.d0.v3",
    )
    item = replace(_item(project), selection=_direct_selection(changed_profile))
    before_status = _git(project, "status", "--short")

    try:
        with pytest.raises(FormalTaskViolation) as rejected:
            await adapter.dispatch(item)

        assert rejected.value.reason == "EXECUTOR_SELECTION_PROFILE_MISMATCH"
        assert rejected.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
        assert resolver.calls == []
        assert executor.requests == []
        assert adapter._journal.get(item.attempt_id) is None
        assert _git(project, "status", "--short") == before_status
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_selected_direct_status_reports_profile_drift_under_old_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches restart drift rewriting history or appearing as known truth."""

    project = tmp_path / "status-profile-drift-project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "status-profile-drift.sqlite3",
    )
    selection = _direct_selection()
    item = replace(_item(project), selection=selection)

    try:
        await adapter.dispatch(item)
        await asyncio.wait_for(executor.finished.wait(), timeout=2)
        await _wait_direct_settled(adapter)
        changed_profile = replace(
            DirectProjectCodeExecutorAdapter.capability_profile(),
            profile_id="live-voice.direct-project-code.d0.v3",
        )
        monkeypatch.setattr(
            DirectProjectCodeExecutorAdapter,
            "capability_profile",
            classmethod(lambda cls: changed_profile),
        )
        task, attempt = _direct_task_attempt(project, selection=selection)
        before_status = _git(project, "status", "--short")

        observed = await adapter.status(task, attempt)

        assert isinstance(observed, ExecutorObservation)
        assert observed.resolution is ExecutorResolution.UNAVAILABLE
        assert observed.error == "EXECUTOR_SELECTION_PROFILE_DRIFT"
        assert observed.adapter_id == selection.adapter_id
        assert observed.capability_profile_digest == selection.capability_profile_digest
        assert adapter._journal.get(item.attempt_id) is not None
        assert _git(project, "status", "--short") == before_status
    finally:
        await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_selection",
    (_foreign_adapter_selection, _forged_direct_capability_selection),
    ids=("foreign-adapter", "forged-direct-capability"),
)
async def test_selected_direct_cancel_rejects_foreign_adapter_before_any_effect(
    tmp_path: Path,
    invalid_selection: Callable[[], PersistedExecutorSelection],
) -> None:
    """Catches a self-consistent foreign selection mutating Direct cancel truth."""

    project = tmp_path / "foreign-selected-cancel"
    _git_project(project)
    executor = _DirectProjectExecutor(project, behavior="wait")
    resolver = _Resolver(_direct_binding(project, executor))
    database = tmp_path / "foreign-selected-cancel.sqlite3"
    adapter = DirectProjectCodeExecutorAdapter(
        resolver,
        database,
    )
    SqliteTaskStore(database)
    dispatch = replace(_item(project), selection=_direct_selection())

    try:
        await adapter.dispatch(dispatch)
        await asyncio.wait_for(executor.started.wait(), timeout=2)
        cancel = replace(
            _item(
                project,
                kind=OutboxKind.ATTEMPT_CANCEL,
                source_seq=1,
            ),
            executor_ref="d0-project:attempt-1",
            selection=invalid_selection(),
        )
        before_record = adapter._journal.get("attempt-1")
        before_requests = tuple(executor.requests)
        before_resolves = tuple(resolver.calls)
        before_status = _git(project, "status", "--short")
        before_database = _journal_dump(adapter)
        before_store = _store_effect_counts(database)
        assert before_store == (0, 0, 0, 0, 0)

        with pytest.raises(FormalTaskViolation) as rejected:
            await adapter.cancel(cancel)

        assert rejected.value.reason == "EXECUTOR_SELECTION_ADAPTER_MISMATCH"
        assert rejected.value.code is ErrorCode.PROTOCOL_VIOLATION
        assert adapter._journal.get("attempt-1") == before_record
        assert tuple(executor.requests) == before_requests
        assert tuple(resolver.calls) == before_resolves
        assert adapter._running["attempt-1"].done() is False
        assert adapter._journal.all_adjustments("attempt-1") == ()
        assert _git(project, "status", "--short") == before_status
        assert _journal_dump(adapter) == before_database
        assert _store_effect_counts(database) == before_store
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_selected_direct_adjust_rejects_foreign_adapter_before_any_effect(
    tmp_path: Path,
) -> None:
    """Catches a self-consistent foreign selection writing Direct adjustment truth."""

    project = tmp_path / "foreign-selected-adjust"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    database = tmp_path / "foreign-selected-adjust.sqlite3"
    adapter = DirectProjectCodeExecutorAdapter(
        resolver,
        database,
    )
    SqliteTaskStore(database)

    try:
        await adapter.dispatch(replace(_item(project), selection=_direct_selection()))
        await asyncio.wait_for(executor.finished.wait(), timeout=2)
        await _wait_direct_settled(adapter)
        adjustment = replace(
            _adjustment_item(
                project,
                command_id="foreign-adjust",
                adjustment="This must never reach Direct.",
                requested_seq=4,
            ),
            selection=_foreign_adapter_selection(),
        )
        before_record = adapter._journal.get("attempt-1")
        before_requests = tuple(executor.requests)
        before_resolves = tuple(resolver.calls)
        before_status = _git(project, "status", "--short")
        before_database = _journal_dump(adapter)
        before_store = _store_effect_counts(database)
        assert before_store == (0, 0, 0, 0, 0)

        with pytest.raises(FormalTaskViolation) as rejected:
            await adapter.adjust(adjustment)

        assert rejected.value.reason == "EXECUTOR_SELECTION_ADAPTER_MISMATCH"
        assert rejected.value.code is ErrorCode.PROTOCOL_VIOLATION
        assert adapter._journal.get("attempt-1") == before_record
        assert adapter._journal.all_adjustments("attempt-1") == ()
        assert tuple(executor.requests) == before_requests
        assert tuple(resolver.calls) == before_resolves
        assert _git(project, "status", "--short") == before_status
        assert _journal_dump(adapter) == before_database
        assert _store_effect_counts(database) == before_store
    finally:
        await adapter.close()


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
    assert terminal.observations[0].result_text == "done"
    assert [
        artifact.relative_path for artifact in terminal.observations[0].result_artifacts
    ] == ["result.txt"]
    assert (
        terminal.observations[0].result_artifacts[0].sha256
        == hashlib.sha256(b"done").hexdigest()
    )
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
async def test_direct_preserves_user_instruction_and_seals_actual_artifact(
    tmp_path: Path,
) -> None:
    project = tmp_path / "isolated-itinerary-project"
    _git_project(project)
    executor = _DemoItineraryProjectExecutor(project)
    spec = replace(
        _spec(project),
        name="Three-day itinerary",
        instruction="帮我根据这些要求制定三天的行程。",
    )
    item = replace(_item(project), spec=spec)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(item)
    await asyncio.wait_for(executor.finished.wait(), timeout=2)
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(replace(task, spec=spec), attempt)

    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert terminal.observations[-1].result_text == (
        "第二天最早的固定安排是 08:30 参观博物馆。"
    )
    assert len(terminal.observations[-1].result_artifacts) == 1
    artifact = terminal.observations[-1].result_artifacts[0]
    assert artifact.relative_path == "itinerary.md"
    itinerary = (project / "itinerary.md").read_bytes()
    assert artifact.sha256 == hashlib.sha256(itinerary).hexdigest()
    assert "08:30 参观博物馆" in itinerary.decode("utf-8")
    query = executor.requests[0].params["query"]
    assert query == spec.instruction
    assert "<itinerary_requirements>" not in query
    assert _git(project, "status", "--porcelain") == "?? itinerary.md"


@pytest.mark.asyncio
async def test_direct_result_relocates_exact_artifact_paths_before_checkout_cleanup(tmp_path: Path) -> None:
    project = tmp_path / "retained project"
    _git_project(project)
    filename = "《计算结果.md》"

    class PathReportingAgent(_DirectProjectExecutor):
        async def process_background_code_task_stream(self, request):
            self.requests.append(request)
            root = Path(request.params["project_dir"]).resolve()
            (root / filename).write_text("verified content", encoding="utf-8")
            self.reported_root = root
            yield AgentResponseChunk(
                request.request_id, request.channel_id,
                payload={"event_type": "chat.final", "content": f"Written: `{root / filename}`"},
                is_complete=True,
            )

    executor = PathReportingAgent(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)), tmp_path / "paths.sqlite3",
    )
    try:
        await adapter.dispatch(_item(project))
        await _wait_direct_settled(adapter)
        task, attempt = _direct_task_attempt(project)
        terminal = await adapter.status(task, attempt)
        observation = terminal.observations[-1]
        assert observation.attempt_outcome is TerminalOutcome.COMPLETED
        assert observation.result_text == f"Written: `{project / filename}`"
        assert not executor.reported_root.exists()
        assert (project / filename).read_text(encoding="utf-8") == "verified content"
        assert observation.result_artifacts[0].relative_path == filename
        assert observation.result_artifacts[0].sha256 == hashlib.sha256(b"verified content").hexdigest()
        # Re-reading the durable journal cannot restore the disposable path.
        assert adapter._journal.get("attempt-1").result_text == observation.result_text
    finally:
        await adapter.close()


def test_result_path_relocation_preserves_unrelated_paths_and_literal_text(tmp_path: Path) -> None:
    from jiuwenswarm.server.live_voice.formal_task_models import TaskResultArtifact

    source, target = tmp_path / "checkout", tmp_path / "retained project"
    artifact = TaskResultArtifact("nested/《result.md》", "a" * 64)
    path, final = source / artifact.relative_path, target / artifact.relative_path
    unrelated = f"{path}.bak {source / 'missing.md'} 650+240+100"
    text = f"`{path}` [{artifact.relative_path}]({path.as_uri()})\n{path.as_posix()}\n{unrelated}"
    expected = f"`{final}` [{artifact.relative_path}]({final.as_uri()})\n{final.as_posix()}\n{unrelated}"
    assert project_code_executor._relocate_result_artifact_paths(text, source, target, (artifact,)) == expected
    assert project_code_executor._relocate_result_artifact_paths(f"文件:{path}", source, target, (artifact,)) == f"文件:{final}"
    assert project_code_executor._relocate_result_artifact_paths(text, source, target, ()) == text
    assert project_code_executor._relocate_result_artifact_paths(None, source, target, (artifact,)) is None


@pytest.mark.parametrize("lose_settlement", [False, True])
@pytest.mark.asyncio
async def test_real_direct_core_adjustment_does_not_block_other_running_cancel(
    tmp_path: Path,
    lose_settlement: bool,
) -> None:
    """Real Direct/Core/files; controlled Agent streams, not Provider evidence."""
    from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
    from tests.unit_tests.live_voice.test_persistent_task_core import (
        NOW,
        _adjust,
        _cancel,
        _create,
    )

    class ControlledReportAgent(_DirectProjectExecutor):
        def __init__(self, project):
            super().__init__(project)
            self.release = asyncio.Event()
            self.adjusted = []

        async def process_background_code_task_stream(self, request):
            self.requests.append(request)
            root = Path(request.params["project_dir"])
            adjustment_id = request.metadata.get("formal_adjustment_id")
            if adjustment_id is None:
                self.started.set()
                await self.release.wait()
            else:
                self.adjusted.append(adjustment_id)
            (root / "measurements.md").write_text(
                f"verified revision {len(self.adjusted)}\n",
                encoding="utf-8",
            )
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={
                    "event_type": "chat.final",
                    "content": "Saved the verified measurements.",
                },
                is_complete=True,
            )

    class SettlementStore(SqliteTaskStore):
        def complete_adjustment_outbox(self, item, delivery, **kwargs):
            if lose_settlement:
                assert self.release_outbox(item, "test-injected-claim-loss")
            return super().complete_adjustment_outbox(item, delivery, **kwargs)

    project_a, project_b = tmp_path / "a", tmp_path / "b"
    _git_project(project_a)
    _git_project(project_b)
    agent_a, agent_b = (
        ControlledReportAgent(project_a),
        ControlledReportAgent(project_b),
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _MappedResolver(
            {
                project_a.resolve(): _direct_binding(project_a, agent_a),
                project_b.resolve(): _direct_binding(project_b, agent_b),
            }
        ),
        tmp_path / "direct.sqlite3",
    )
    store = SettlementStore(tmp_path / "core.sqlite3")
    core = PersistentTaskCore(store, adapter)
    identities = []
    try:
        for project, suffix in ((project_a, "-a"), (project_b, "-b")):
            invocation = _create(project, identity_suffix=suffix)
            created = core.execute(
                invocation.envelope,
                invocation.authorization,
                context=invocation.context,
                now=NOW,
            )
            assert created.ok and created.result is not None
            identities.append(
                (str(created.result["task_id"]), str(created.result["attempt_id"]))
            )
            assert await core.drain_outbox_once()
        await asyncio.wait_for(agent_a.started.wait(), 5)
        await asyncio.wait_for(agent_b.started.wait(), 5)
        (task_a, attempt_a), (task_b, _attempt_b) = identities
        command_ids = (
            ["measurement-adjust-1"]
            if lose_settlement
            else ["measurement-adjust-1", "measurement-adjust-2"]
        )
        for command_id in command_ids:
            command, grant = _adjust(
                task_a,
                "Verify the measurements without overwriting source data.",
                command_id=command_id,
                request_id=f"request-{command_id}",
            )
            assert core.execute(command, grant, now=NOW).ok
        await core.reconcile()
        checkpoint = adapter._adjustment_checkpoints[attempt_a]
        await asyncio.wait_for(checkpoint.changed.wait(), 5)
        cancel = _cancel(task_b)
        assert core.execute(cancel.envelope, cancel.authorization, now=NOW).ok
        await asyncio.wait_for(core.reconcile(), 5)
        assert store.get_task(task_b, _scope()).outcome is TerminalOutcome.CANCELLED
        assert store.get_task(task_a, _scope()).state is FormalTaskState.RUNNING
        assert agent_a.adjusted == []
        assert not (project_b / "measurements.md").exists()
        agent_a.release.set()
        if lose_settlement:
            with pytest.raises(FormalTaskViolation):
                await core.drain_inflight_adjustments(timeout=5)
        else:
            await core.drain_inflight_adjustments(timeout=5)
            assert agent_a.adjusted == command_ids[:1]
            await core.reconcile()
            await core.drain_inflight_adjustments(timeout=5)
        await _wait_direct_settled(adapter)
        await core.reconcile_status()
        task = store.get_task(task_a, _scope())
        if lose_settlement:
            assert task.outcome is not TerminalOutcome.COMPLETED
            assert not (project_a / "measurements.md").exists()
            assert store.task_result(task_a, _scope())[1] is None
        else:
            assert task.outcome is TerminalOutcome.COMPLETED
            assert agent_a.adjusted == command_ids
            events = store.events(task_a, _scope(), after_seq=-1)
            applied = [
                event for event in events if event.event_type == "task.adjust_applied"
            ]
            assert [event.causation_id for event in applied] == command_ids
            assert applied[-1].seq < next(
                event.seq for event in events if event.event_type == "task.terminal"
            )
            result = store.task_result(task_a, _scope())[1]
            assert result is not None
            content = (project_a / "measurements.md").read_bytes()
            assert content.decode("utf-8").splitlines() == ["verified revision 2"]
            assert result.artifacts[0].sha256 == hashlib.sha256(content).hexdigest()
    finally:
        agent_a.release.set()
        agent_b.release.set()
        await adapter.close(interrupt_running=True)
        await core.drain_inflight_adjustments()
    assert adapter._running == {}
    assert adapter._adjustment_checkpoints == {}


@pytest.mark.asyncio
async def test_generic_checkpoint_keeps_admitted_adjustment_pending_until_settlement(
    tmp_path: Path,
) -> None:
    project = tmp_path / "adjustable-demo-itinerary"
    _git_project(project)
    executor = _AdjustableItineraryProjectExecutor(project)
    spec = replace(
        _spec(project),
        name="Three-day itinerary",
        instruction="Create a three-day itinerary.",
    )
    item = replace(_item(project), spec=spec)
    checkpoint_open = asyncio.Event()
    release_checkpoint = asyncio.Event()

    async def checkpoint_barrier(_attempt_id: str) -> None:
        checkpoint_open.set()
        await release_checkpoint.wait()

    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
        adjustment_checkpoint_barrier=checkpoint_barrier,
    )

    await adapter.dispatch(item)
    await asyncio.wait_for(checkpoint_open.wait(), timeout=5)
    task, attempt = _direct_task_attempt(project)
    before_adjustment = await adapter.status(replace(task, spec=spec), attempt)

    assert before_adjustment.observations == ()
    assert adapter._adjustment_checkpoints["attempt-1"].accepting is True

    adjustment = replace(
        _adjustment_item(
            project,
            command_id="adjust-1",
            adjustment="Move the museum visit to 09:30.",
            requested_seq=4,
        ),
        spec=spec,
    )
    delivery_task = asyncio.create_task(adapter.adjust(adjustment))
    await asyncio.wait_for(
        adapter._adjustment_checkpoints["attempt-1"].changed.wait(), 5
    )
    release_checkpoint.set()
    delivery = await asyncio.wait_for(delivery_task, timeout=5)

    assert delivery.state is TaskAdjustmentState.APPLIED
    assert len(executor.requests) == 2
    before_store_ack = await adapter.status(replace(task, spec=spec), attempt)
    assert before_store_ack.observations == ()

    await adapter.settle_adjustment(
        adjustment,
        TaskAdjustmentSettlement(TaskAdjustmentState.APPLIED, False),
    )
    await _wait_direct_settled(adapter)
    terminal = await adapter.status(replace(task, spec=spec), attempt)

    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert "09:30" in (project / "itinerary.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_generic_checkpoint_close_interrupts_without_target_mutation(
    tmp_path: Path,
) -> None:
    project = tmp_path / "closed-demo-itinerary"
    _git_project(project)
    executor = _AdjustableItineraryProjectExecutor(project)
    spec = replace(
        _spec(project),
        name="Three-day itinerary",
        instruction="Create a three-day itinerary.",
    )
    checkpoint_open = asyncio.Event()

    async def checkpoint_barrier(_attempt_id: str) -> None:
        checkpoint_open.set()
        await asyncio.Future()

    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
        adjustment_checkpoint_barrier=checkpoint_barrier,
    )

    await adapter.dispatch(replace(_item(project), spec=spec))
    await asyncio.wait_for(checkpoint_open.wait(), timeout=5)
    isolated_root = Path(executor.requests[0].params["project_dir"])

    await adapter.close(interrupt_running=True)

    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(replace(task, spec=spec), attempt)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.INTERRUPTED
    assert adapter._running == {}
    assert adapter._adjustment_checkpoints == {}
    assert not isolated_root.exists()
    assert not (project / "itinerary.md").exists()
    assert _git(project, "status", "--porcelain") == ""


@pytest.mark.asyncio
async def test_direct_adjustments_are_ordered_durable_and_fence_terminal_result(
    tmp_path: Path,
) -> None:
    project = tmp_path / "adjustable-itinerary"
    _git_project(project)
    executor = _AdjustableItineraryProjectExecutor(project)
    checkpoint_open = asyncio.Event()
    release_checkpoint = asyncio.Event()

    async def checkpoint_barrier(attempt_id: str) -> None:
        assert attempt_id == "attempt-1"
        checkpoint_open.set()
        await release_checkpoint.wait()

    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
        adjustment_checkpoint_barrier=checkpoint_barrier,
    )
    await adapter.dispatch(_item(project))
    await asyncio.wait_for(checkpoint_open.wait(), timeout=2)
    first = _adjustment_item(
        project,
        command_id="adjust-1",
        adjustment="Move the museum visit to 09:30.",
        requested_seq=4,
    )
    second = _adjustment_item(
        project,
        command_id="adjust-2",
        adjustment="Make lunch vegetarian.",
        requested_seq=5,
    )
    checkpoint = adapter._adjustment_checkpoints["attempt-1"]
    first_delivery_task = asyncio.create_task(adapter.adjust(first))
    await asyncio.wait_for(checkpoint.changed.wait(), timeout=2)
    checkpoint.changed.clear()
    second_delivery_task = asyncio.create_task(adapter.adjust(second))
    await asyncio.wait_for(checkpoint.changed.wait(), timeout=2)
    assert len(checkpoint.pending) == 2
    release_checkpoint.set()

    first_delivery = await asyncio.wait_for(first_delivery_task, timeout=2)
    assert first_delivery.state is TaskAdjustmentState.APPLIED
    replay = await adapter.adjust(
        replace(first, outbox_id="outbox-adjust-1-replay", claim_token="replay")
    )
    assert replay == first_delivery
    assert len(executor.requests) == 2
    successor_executor = _AdjustableItineraryProjectExecutor(project)
    successor = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, successor_executor)),
        tmp_path / "p3.sqlite3",
    )
    restart_replay = await successor.adjust(
        replace(first, outbox_id="outbox-adjust-1-restart", claim_token="restart")
    )
    assert restart_replay == first_delivery
    assert successor_executor.requests == []
    task, attempt = _direct_task_attempt(project)
    before_store_ack = await adapter.status(task, attempt)
    assert isinstance(before_store_ack, ExecutorDeliveryResult)
    assert before_store_ack.observations == ()

    await adapter.settle_adjustment(
        first,
        TaskAdjustmentSettlement(TaskAdjustmentState.APPLIED, True),
    )
    second_delivery = await asyncio.wait_for(second_delivery_task, timeout=2)
    assert second_delivery.state is TaskAdjustmentState.APPLIED
    await adapter.settle_adjustment(
        second,
        TaskAdjustmentSettlement(TaskAdjustmentState.APPLIED, False),
    )
    await _wait_direct_settled(adapter)

    terminal = await adapter.status(task, attempt)
    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert terminal.observations[-1].result_text == "Vegetarian lunch added."
    itinerary = (project / "itinerary.md").read_text(encoding="utf-8")
    assert "Museum at 09:30." in itinerary
    assert "Vegetarian lunch." in itinerary
    adjustment_requests = executor.requests[1:]
    assert [
        request.metadata["formal_adjustment_id"] for request in adjustment_requests
    ] == ["adjust-1", "adjust-2"]
    assert [
        record.state for record in adapter._journal.all_adjustments("attempt-1")
    ] == [TaskAdjustmentState.APPLIED, TaskAdjustmentState.APPLIED]

    before = (project / "itinerary.md").read_bytes()
    late = _adjustment_item(
        project,
        command_id="adjust-late",
        adjustment="Delete the itinerary.",
        requested_seq=6,
    )
    late_result = await adapter.adjust(late)
    assert late_result.state is TaskAdjustmentState.REJECTED
    assert late_result.reason == "ADJUSTMENT_CHECKPOINT_CLOSED"
    assert (project / "itinerary.md").read_bytes() == before
    assert len(executor.requests) == 3


@pytest.mark.asyncio
async def test_generic_task_can_seal_multiple_artifacts_without_a_fixed_filename(
    tmp_path: Path,
) -> None:
    project = tmp_path / "isolated-itinerary-project"
    _git_project(project)
    executor = _DemoItineraryProjectExecutor(project, extra_change=True)
    spec = replace(
        _spec(project),
        name="Three-day itinerary",
        instruction="保存 itinerary.md 和 outside-fixture.txt 两份报告。",
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(replace(_item(project), spec=spec))
    await asyncio.wait_for(executor.finished.wait(), timeout=2)
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(replace(task, spec=spec), attempt)

    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    record = adapter._journal.get("attempt-1")
    assert record is not None
    assert record.error is None
    artifacts = terminal.observations[-1].result_artifacts
    assert {artifact.relative_path for artifact in artifacts} == {
        "itinerary.md",
        "outside-fixture.txt",
    }
    for artifact in artifacts:
        assert (
            artifact.sha256
            == hashlib.sha256(
                (project / artifact.relative_path).read_bytes()
            ).hexdigest()
        )
    assert executor.requests[0].params["query"] == spec.instruction


@pytest.mark.parametrize("flag_value", [False, True, 1])
def test_retired_fixture_and_wait_flags_cannot_be_reenabled(
    tmp_path: Path,
    flag_value: object,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    with pytest.raises(TypeError, match="unexpected keyword"):
        DirectProjectCodeExecutorAdapter(
            _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
            tmp_path / "p3.sqlite3",
            demo_itinerary_fixture_enabled=flag_value,  # type: ignore[call-arg]
        )
    with pytest.raises(TypeError, match="unexpected keyword"):
        DirectProjectCodeExecutorAdapter(
            _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
            tmp_path / "p3.sqlite3",
            demo_itinerary_adjustment_checkpoint_enabled=flag_value,  # type: ignore[call-arg]
        )
    with pytest.raises(TypeError, match="unexpected keyword"):
        DirectProjectCodeExecutorAdapter(
            _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
            tmp_path / "p3.sqlite3",
            demo_itinerary_adjustment_checkpoint_enabled=True,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("durability", ["D0", "D2"])
async def test_legacy_direct_snapshot_is_readable_but_cannot_dispatch(
    tmp_path: Path,
    durability: str,
) -> None:
    legacy = (
        project_code_executor._LEGACY_DIRECT_D0_CAPABILITY_PROFILE
        if durability == "D0"
        else project_code_executor._LEGACY_DIRECT_D2_CAPABILITY_PROFILE
    )
    frozen = legacy.canonical_bytes()
    requirements = TaskExecutionRequirements(
        schema_version=TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        operation_versions=legacy.operation_versions,
        durability_level=durability,
        side_effect_class="project_mutation",
        project_serialization="exclusive",
    )
    selection = PersistedExecutorSelection(
        adapter_id=legacy.adapter_id,
        capability_profile_json=frozen,
        capability_profile_digest=legacy.digest_sha256(),
        execution_requirements_json=requirements.canonical_bytes(),
    )
    project = tmp_path / "legacy-read-only"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    adapter = DirectProjectCodeExecutorAdapter(resolver, tmp_path / "direct.sqlite3")
    try:
        parsed = adapter._parsed_selection(selection)
        assert parsed is not None and parsed.profile.canonical_bytes() == frozen
        assert adapter._selection_binding(selection, require_current_profile=False) == (
            legacy.adapter_id,
            legacy.digest_sha256(),
        )
        with pytest.raises(FormalTaskViolation, match="frozen Direct capability"):
            await adapter.dispatch(replace(_item(project), selection=selection))
        task, attempt = _direct_task_attempt(project, selection=selection)
        observed = await adapter.status(task, attempt)
        assert isinstance(observed, ExecutorObservation)
        assert observed.resolution is ExecutorResolution.UNAVAILABLE
        assert observed.error == "EXECUTOR_SELECTION_PROFILE_DRIFT"
        assert observed.adapter_id == selection.adapter_id
        assert observed.capability_profile_digest == selection.capability_profile_digest
        assert resolver.calls == []
        assert executor.requests == []
        assert adapter._journal.get("attempt-1") is None
        assert _git(project, "status", "--porcelain") == ""
        assert selection.capability_profile_json == frozen
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_direct_d0_attempt_executor_binds_exact_worktree_and_releases_before_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    canonical_executor = _DirectProjectExecutor(project)
    attempt_executors: list[_ExactRootDirectProjectExecutor] = []
    attempt_roots: list[Path] = []
    events: list[str] = []

    async def acquire_attempt(attempt_root: str) -> AttemptProjectExecutorLease:
        root = Path(attempt_root).resolve()
        attempt_roots.append(root)
        executor = _ExactRootDirectProjectExecutor(root)
        attempt_executors.append(executor)

        async def release_attempt() -> None:
            assert root.exists()
            assert not (project / "result.txt").exists()
            events.append("release")

        return AttemptProjectExecutorLease(executor, str(root), release_attempt)

    binding = replace(
        _direct_binding(project, canonical_executor),
        attempt_executor_factory=acquire_attempt,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / "p3.sqlite3",
    )
    real_apply = project_code_executor._apply_attempt_patch
    real_remove = project_code_executor._remove_attempt_worktree

    def observed_apply(root: Path, patch: bytes, **kwargs) -> None:
        assert events == ["release"]
        assert root.resolve() == project.resolve()
        events.append("apply")
        real_apply(root, patch, **kwargs)

    def observed_remove(root: Path, parent: Path, worktree: Path) -> None:
        assert events == ["release", "apply"]
        assert worktree.resolve() == attempt_roots[0]
        events.append("remove")
        real_remove(root, parent, worktree)

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", observed_apply)
    monkeypatch.setattr(
        project_code_executor,
        "_remove_attempt_worktree",
        observed_remove,
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert canonical_executor.requests == []
    assert len(attempt_executors) == 1
    assert len(attempt_executors[0].requests) == 1
    request_root = Path(
        attempt_executors[0].requests[0].params["project_dir"]
    ).resolve()
    assert request_root == attempt_roots[0]
    assert events == ["release", "apply", "remove"]
    assert not attempt_roots[0].exists()
    assert (project / "result.txt").read_text(encoding="utf-8") == "done"
    assert _git(project, "rev-list", "--count", "HEAD") == "1"
    assert _git(project, "status", "--porcelain") == "?? result.txt"


@pytest.mark.asyncio
async def test_direct_d0_second_attempt_seeds_predecessor_untracked_result(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    attempt_roots: list[Path] = []

    class AttemptExecutor:
        def __init__(self, root: Path) -> None:
            self.root = root

        def get_project_execution_root(self) -> str:
            return str(self.root)

        async def process_background_code_task_stream(self, request):
            attempt_id = request.metadata["formal_attempt_id"]
            (self.root / f"{attempt_id}.txt").write_text(
                f"{attempt_id}\n", encoding="utf-8"
            )
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={"event_type": "chat.final", "content": attempt_id},
                is_complete=True,
            )

    async def acquire(attempt_root: str) -> AttemptProjectExecutorLease:
        root = Path(attempt_root).resolve()
        attempt_roots.append(root)

        async def release() -> None:
            return None

        return AttemptProjectExecutorLease(AttemptExecutor(root), str(root), release)

    binding = replace(
        _direct_binding(project, _DirectProjectExecutor(project)),
        attempt_executor_factory=acquire,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    first_task, first_attempt = _direct_task_attempt(project)
    first = await adapter.status(first_task, first_attempt)
    assert first.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert _git(project, "status", "--porcelain") == "?? attempt-1.txt"

    second_item = replace(
        _item(project),
        outbox_id="outbox-2",
        task_id="task-2",
        attempt_id="attempt-2",
        command_id="command-2",
    )
    await adapter.dispatch(second_item)
    await _wait_direct_settled(adapter)
    second_task, second_attempt = _direct_task_attempt(
        project, task_id="task-2", attempt_id="attempt-2"
    )
    second = await adapter.status(second_task, second_attempt)

    assert second.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert (project / "attempt-1.txt").read_text(encoding="utf-8") == "attempt-1\n"
    assert (project / "attempt-2.txt").read_text(encoding="utf-8") == "attempt-2\n"
    assert len(attempt_roots) == 2
    assert all(not root.exists() for root in attempt_roots)


@pytest.mark.asyncio
async def test_direct_d0_rejects_real_attempt_initializer_mutation(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)

    async def acquire(attempt_root: str) -> AttemptProjectExecutorLease:
        root = Path(attempt_root).resolve()
        (root / "initializer-side-effect.txt").write_text(
            "forbidden\n", encoding="utf-8"
        )
        executor = _ExactRootDirectProjectExecutor(root)

        async def release() -> None:
            return None

        return AttemptProjectExecutorLease(executor, str(root), release)

    binding = replace(
        _direct_binding(project, _DirectProjectExecutor(project)),
        attempt_executor_factory=acquire,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.FAILED
    assert terminal.observations[-1].error == "EXECUTOR_INITIALIZATION_MUTATED_TARGET"
    assert not (project / "initializer-side-effect.txt").exists()
    assert _git(project, "status", "--porcelain") == ""


@pytest.mark.asyncio
async def test_direct_d0_accepts_exact_patch_when_autocrlf_changes_raw_bytes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    _git(project, "config", "core.autocrlf", "true")
    readme = project / "README.md"
    readme.write_bytes(b"baseline\r\n")
    assert _git(project, "status", "--porcelain") == ""

    executor = _LfRewriteProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert readme.read_bytes() == b"baseline\r\ncompleted\r\n"
    assert terminal.observations[-1].result_artifacts == (
        project_code_executor.TaskResultArtifact(
            relative_path="README.md",
            sha256=hashlib.sha256(readme.read_bytes()).hexdigest(),
        ),
    )
    record = adapter._journal.get("attempt-1")
    assert record is not None
    assert record.expected_tree is not None
    expected_parts = record.expected_tree.split(":")
    assert expected_parts[0] == "content-v2"
    assert (
        project_code_executor._project_content_fingerprint(project) != expected_parts[1]
    )
    assert project_code_executor._expected_project_state_matches(
        project, record.expected_tree
    )

    (project / "foreign.txt").write_text("foreign\n", encoding="utf-8")
    assert not project_code_executor._expected_project_state_matches(
        project, record.expected_tree
    )
    assert _git(project, "diff", "--cached", "--name-only") == ""
    assert not project_code_executor._expected_project_state_matches(
        project, "malformed"
    )


@pytest.mark.asyncio
async def test_direct_d0_wrong_attempt_root_fails_closed_without_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve\n", encoding="utf-8")
    canonical_executor = _DirectProjectExecutor(project)
    wrong_executor = _ExactRootDirectProjectExecutor(external)
    attempt_roots: list[Path] = []
    events: list[str] = []

    async def acquire_wrong_root(attempt_root: str) -> AttemptProjectExecutorLease:
        root = Path(attempt_root).resolve()
        attempt_roots.append(root)

        async def release_attempt() -> None:
            assert root.exists()
            assert _git(project, "status", "--porcelain") == ""
            assert sentinel.read_text(encoding="utf-8") == "preserve\n"
            events.append("release")

        return AttemptProjectExecutorLease(
            wrong_executor,
            str(external.resolve()),
            release_attempt,
        )

    binding = replace(
        _direct_binding(project, canonical_executor),
        attempt_executor_factory=acquire_wrong_root,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / "p3.sqlite3",
    )
    real_remove = project_code_executor._remove_attempt_worktree

    def forbidden_apply(*_args, **_kwargs) -> None:
        raise AssertionError("wrong-root attempt must never apply a target patch")

    def observed_remove(root: Path, parent: Path, worktree: Path) -> None:
        assert events == ["release"]
        events.append("remove")
        real_remove(root, parent, worktree)

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", forbidden_apply)
    monkeypatch.setattr(
        project_code_executor,
        "_remove_attempt_worktree",
        observed_remove,
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.FAILED
    assert terminal.observations[-1].error == "EXECUTION_TARGET_NOT_BOUND"
    assert canonical_executor.requests == []
    assert wrong_executor.requests == []
    assert events == ["release", "remove"]
    assert len(attempt_roots) == 1
    assert not attempt_roots[0].exists()
    assert _git(project, "status", "--porcelain") == ""
    assert _git(project, "rev-list", "--count", "HEAD") == "1"
    assert sentinel.read_text(encoding="utf-8") == "preserve\n"
    assert sorted(path.name for path in external.iterdir()) == ["sentinel.txt"]


@pytest.mark.asyncio
async def test_attempt_root_getter_failure_releases_lease_before_worktree_cleanup(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    events: list[str] = []
    attempt_roots: list[Path] = []

    class FailingRootExecutor:
        def get_project_execution_root(self) -> str:
            raise RuntimeError("injected root getter failure")

        async def process_background_code_task_stream(self, _request):
            raise AssertionError("an unverified root must never execute")
            yield  # pragma: no cover

    async def acquire(attempt_root: str) -> AttemptProjectExecutorLease:
        root = Path(attempt_root).resolve()
        attempt_roots.append(root)

        async def release() -> None:
            assert root.exists()
            events.append("release")

        return AttemptProjectExecutorLease(
            FailingRootExecutor(),
            str(root),
            release,
        )

    binding = replace(
        _direct_binding(project, _DirectProjectExecutor(project)),
        attempt_executor_factory=acquire,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].error == "EXECUTION_TARGET_NOT_BOUND"
    assert events == ["release"]
    assert len(attempt_roots) == 1
    assert not attempt_roots[0].exists()
    assert _git(project, "status", "--porcelain") == ""


@pytest.mark.asyncio
async def test_attempt_capability_failure_keeps_stable_error_and_releases_lease(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    releases = 0
    attempt_roots: list[Path] = []

    async def acquire(attempt_root: str) -> AttemptProjectExecutorLease:
        nonlocal releases
        root = Path(attempt_root).resolve()
        attempt_roots.append(root)

        async def release() -> None:
            nonlocal releases
            assert root.exists()
            releases += 1

        return AttemptProjectExecutorLease(object(), str(root), release)

    binding = replace(
        _direct_binding(project, _DirectProjectExecutor(project)),
        attempt_executor_factory=acquire,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].error == "EXECUTOR_CAPABILITY_UNAVAILABLE"
    assert releases == 1
    assert len(attempt_roots) == 1
    assert not attempt_roots[0].exists()
    assert _git(project, "status", "--porcelain") == ""


@pytest.mark.asyncio
async def test_cancelled_attempt_acquire_retains_lease_and_bounds_close(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    acquire_entered = asyncio.Event()
    acquire_release = asyncio.Event()
    attempt_roots: list[Path] = []
    releases = 0

    async def acquire(attempt_root: str) -> AttemptProjectExecutorLease:
        nonlocal releases
        root = Path(attempt_root).resolve()
        attempt_roots.append(root)
        acquire_entered.set()
        await acquire_release.wait()
        executor = _ExactRootDirectProjectExecutor(root)

        async def release() -> None:
            nonlocal releases
            assert root.exists()
            releases += 1

        return AttemptProjectExecutorLease(executor, str(root), release)

    binding = replace(
        _direct_binding(project, _DirectProjectExecutor(project)),
        attempt_executor_factory=acquire,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / "p3.sqlite3",
        cancel_timeout=0.01,
        close_timeout=0.01,
    )
    dispatch = asyncio.create_task(adapter.dispatch(_item(project)))
    # Creating the disposable Git worktree can exceed two seconds on a busy
    # Windows runner; the assertion is about ownership, not startup latency.
    await asyncio.wait_for(acquire_entered.wait(), timeout=5)
    assert len(attempt_roots) == 1
    assert attempt_roots[0].exists()

    dispatch.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(dispatch, timeout=1)
    for _ in range(100):
        if adapter.retained_cleanup_attempt_ids() == ("attempt-1",):
            break
        await asyncio.sleep(0.01)
    assert adapter.retained_cleanup_attempt_ids() == ("attempt-1",)
    assert attempt_roots[0].exists()

    started = asyncio.get_running_loop().time()
    with pytest.raises(RuntimeError, match="PROJECT_WORKTREE_CLEANUP_PENDING"):
        await adapter.close(interrupt_running=True)
    assert asyncio.get_running_loop().time() - started < 0.2
    assert attempt_roots[0].exists()
    assert releases == 0

    acquire_release.set()
    await _wait_direct_settled(adapter)
    await adapter.close(interrupt_running=True)
    assert releases == 1
    assert adapter.retained_cleanup_attempt_ids() == ()
    assert not attempt_roots[0].exists()
    assert _git(project, "status", "--porcelain") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_failure", ["exception", "cancelled"])
async def test_attempt_factory_without_owner_evidence_never_deletes_checkout(
    tmp_path: Path,
    factory_failure: str,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    attempt_roots: list[Path] = []

    async def acquire(attempt_root: str) -> AttemptProjectExecutorLease:
        attempt_roots.append(Path(attempt_root).resolve())
        if factory_failure == "exception":
            raise RuntimeError("factory failed without ownership evidence")
        raise asyncio.CancelledError()

    binding = replace(
        _direct_binding(project, _DirectProjectExecutor(project)),
        attempt_executor_factory=acquire,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / f"factory-{factory_failure}.sqlite3",
        close_timeout=0.01,
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)

    assert len(attempt_roots) == 1
    assert attempt_roots[0].exists()
    assert adapter.retained_cleanup_attempt_ids() == ("attempt-1",)
    with pytest.raises(RuntimeError, match="PROJECT_WORKTREE_CLEANUP_PENDING"):
        await adapter.close()
    assert attempt_roots[0].exists()
    assert _git(project, "status", "--porcelain") == ""

    # This test intentionally supplies a protocol-violating factory with no
    # releasable evidence. Simulate an external recovery owner only after the
    # fail-closed assertions so the temporary Git worktree does not leak.
    cleanup = adapter._retained_worktree_cleanups.pop("attempt-1")
    await asyncio.to_thread(
        project_code_executor._remove_attempt_worktree,
        cleanup.root,
        cleanup.parent,
        cleanup.worktree,
    )
    await adapter.close()


@pytest.mark.asyncio
async def test_production_resolver_manager_real_facade_executes_exact_d0_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    created_adapters: list[object] = []

    class ControlledCodeAdapter:
        _is_code_agent = True
        _is_session_scoped_adapter = False

        def __init__(self) -> None:
            self._instance = object()
            self._project_dir = ""
            self.sessions: set[str] = set()
            self.sub_mode: str | None = "unset"
            self.ensure_calls = 0
            created_adapters.append(self)

        async def create_instance(
            self,
            config,
            *,
            mode: str = "agent",
            sub_mode: str | None = None,
        ) -> None:
            assert mode == "code"
            self.sub_mode = sub_mode
            self._project_dir = str(Path(config["project_dir"]).resolve())

        async def ensure_instance(self):
            self.ensure_calls += 1
            (Path(self._project_dir) / "root-agent-side-effect.txt").write_text(
                "forbidden",
                encoding="utf-8",
            )
            return self._instance

        async def prepare_background_project_session(self, session_id: str) -> None:
            self.sessions.add(session_id)

        async def process_message_stream_impl(self, request, inputs):
            requested = Path(request.params["project_dir"]).resolve()
            assert requested == Path(self._project_dir).resolve()
            assert Path(inputs["project_dir"]).resolve() == requested
            (requested / "result.txt").write_text("done", encoding="utf-8")
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={"event_type": "chat.final", "content": "done"},
                is_complete=True,
            )

        async def cleanup_session_adapter(self, session_id: str) -> bool:
            existed = session_id in self.sessions
            self.sessions.discard(session_id)
            return existed

        def has_session_runtime(self, session_id: str | None = None) -> bool:
            if session_id is None:
                return bool(self.sessions)
            return session_id in self.sessions

        async def cleanup(self) -> None:
            self.sessions.clear()

        async def cleanup_formal_project_task_agent(self) -> None:
            self.sessions.clear()

    monkeypatch.setattr(agent_interface, "resolve_sdk_choice", lambda: "harness")
    monkeypatch.setattr(
        agent_interface,
        "create_adapter",
        lambda _sdk_name, *, mode="agent": ControlledCodeAdapter(),
    )

    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(project.resolve()),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Models:
        def resolve(self, _intent, **kwargs):
            return SimpleNamespace(
                model=(object() if kwargs.get("instantiate") else None),
                identity="default#0",
                config_version="catalog-v1",
            )

    manager = AgentManager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),  # type: ignore[arg-type]
        agent_manager=manager,
        service=None,
        model_resolver=Models(),  # type: ignore[arg-type]
        principal=object(),  # type: ignore[arg-type]
    )
    adapter = DirectProjectCodeExecutorAdapter(
        resolver,
        tmp_path / "p3.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    assert (project / "result.txt").read_text(encoding="utf-8") == "done"
    assert len(created_adapters) == 2
    canonical, isolated = created_adapters
    assert Path(canonical._project_dir).resolve() == project.resolve()  # type: ignore[attr-defined]
    assert Path(isolated._project_dir).resolve() != project.resolve()  # type: ignore[attr-defined]
    assert canonical.sub_mode is None  # type: ignore[attr-defined]
    assert isolated.sub_mode is None  # type: ignore[attr-defined]
    assert canonical.ensure_calls == 0  # type: ignore[attr-defined]
    assert isolated.ensure_calls == 0  # type: ignore[attr-defined]
    assert not (project / "root-agent-side-effect.txt").exists()
    assert manager._agent_pins == {}
    assert adapter.retained_cleanup_attempt_ids() == ()

    await adapter.close()
    await resolver.close()
    assert "live_voice_formal_task" not in manager.agents


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["runtime_error", "cancelled_error"])
async def test_production_partial_attempt_initialization_releases_before_worktree_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    attempt_roots: list[Path] = []
    cleanup_roots: list[Path] = []

    class PartialCodeAdapter:
        _is_code_agent = True
        _is_session_scoped_adapter = False

        def __init__(self) -> None:
            self._instance = object()
            self._project_dir = ""
            self.runtime = False

        async def ensure_instance(self):
            # Mirrors the real adapter: a formal dispatch runs outside the
            # chat path and awaits this rather than reading the accessor.
            return self._instance

        async def create_instance(
            self,
            config,
            *,
            mode: str = "agent",
            sub_mode: str | None = None,
        ) -> None:
            assert mode == "code"
            assert sub_mode is None
            root = Path(config["project_dir"]).resolve()
            self._project_dir = str(root)
            if root == project.resolve():
                return
            attempt_roots.append(root)
            self.runtime = True
            attempt_agents = {
                key: agent
                for key, agent in manager.agents.get(
                    "live_voice_formal_task", {}
                ).items()
                if "formal_attempt" in key
            }
            assert len(attempt_agents) == 1
            owner = next(iter(attempt_agents.values()))
            assert owner._adapter is self  # type: ignore[attr-defined]
            assert manager._agent_pins == {id(owner): 1}
            assert set(
                manager._agent_create_params["live_voice_formal_task"]
            ).issuperset(attempt_agents)
            if failure_kind == "runtime_error":
                raise RuntimeError("injected partial initialization")
            raise asyncio.CancelledError()

        async def process_message_stream_impl(self, _request, _inputs):
            raise AssertionError("a partially initialized Agent must never execute")
            if False:
                yield None

        def has_session_runtime(self, _session_id=None) -> bool:
            return self.runtime

        async def cleanup(self) -> None:
            root = Path(self._project_dir).resolve()
            if root != project.resolve():
                assert root.exists()
                cleanup_roots.append(root)
            self.runtime = False

        async def cleanup_formal_project_task_agent(self) -> None:
            await self.cleanup()

    monkeypatch.setattr(agent_interface, "resolve_sdk_choice", lambda: "harness")
    monkeypatch.setattr(
        agent_interface,
        "create_adapter",
        lambda _sdk_name, *, mode="agent": PartialCodeAdapter(),
    )

    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(project.resolve()),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Models:
        def resolve(self, _intent, **kwargs):
            return SimpleNamespace(
                model=(object() if kwargs.get("instantiate") else None),
                identity="default#0",
                config_version="catalog-v1",
            )

    manager = AgentManager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),  # type: ignore[arg-type]
        agent_manager=manager,
        service=None,
        model_resolver=Models(),  # type: ignore[arg-type]
        principal=object(),  # type: ignore[arg-type]
    )
    adapter = DirectProjectCodeExecutorAdapter(
        resolver,
        tmp_path / f"{failure_kind}.sqlite3",
    )

    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)

    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.FAILED
    assert terminal.observations[-1].error == "EXECUTOR_INITIALIZATION_FAILED"
    assert len(attempt_roots) == 1
    assert cleanup_roots == attempt_roots
    assert not attempt_roots[0].exists()
    assert manager._agent_pins == {}
    formal_agents = manager.agents.get("live_voice_formal_task", {})
    assert all("formal_attempt" not in key for key in formal_agents)
    assert _git(project, "status", "--porcelain") == ""

    await adapter.close()
    await resolver.close()
    assert "live_voice_formal_task" not in manager.agents


@pytest.mark.asyncio
async def test_binding_resolver_close_failure_fences_resolve_and_retries_cleanup(
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
        def __init__(self) -> None:
            self.cleanup_calls = 0

        async def cleanup_live_voice_formal_task_agents(self) -> None:
            self.cleanup_calls += 1
            if self.cleanup_calls == 1:
                raise RuntimeError("injected retained cleanup")

    manager = Manager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),  # type: ignore[arg-type]
        agent_manager=manager,
        service=None,
        model_resolver=object(),  # type: ignore[arg-type]
        principal=object(),  # type: ignore[arg-type]
    )

    with pytest.raises(
        RuntimeError,
        match="FORMAL_PROJECT_BINDING_CLEANUP_PENDING",
    ):
        await resolver.close()
    assert resolver._close_requested is True
    assert resolver._closed is False
    with pytest.raises(FormalTaskViolation) as fenced:
        await resolver.resolve(_spec(tmp_path), for_dispatch=False)
    assert fenced.value.reason == "EXECUTOR_CAPABILITY_UNAVAILABLE"

    await resolver.close()
    await resolver.close()
    assert resolver._closed is True
    assert manager.cleanup_calls == 2


@pytest.mark.asyncio
async def test_binding_resolve_close_race_releases_owner_before_closed(
    tmp_path: Path,
) -> None:
    entered = Event()
    allow_revalidate = Event()

    class Authority:
        def revalidate(self, _context, **_kwargs):
            entered.set()
            assert allow_revalidate.wait(2)
            return SimpleNamespace(
                project_dir=str(tmp_path.resolve()),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Models:
        def resolve(self, _intent, **kwargs):
            return SimpleNamespace(
                model=(object() if kwargs.get("instantiate") else None),
                identity="default#0",
                config_version="catalog-v1",
            )

    class Agent:
        def get_project_execution_root(self) -> str:
            return str(tmp_path.resolve())

        def get_instance(self) -> object:
            return object()

        async def ensure_instance(self) -> object:
            # A formal dispatch runs outside the chat path and awaits
            # this rather than reading the bare accessor.
            return object()

    class Manager:
        def __init__(self) -> None:
            self.agent = Agent()
            self.pins = 0
            self.get_calls = 0
            self.cleanup_calls = 0

        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            self.get_calls += 1
            return self.agent

        def pin_agent(self, expected: Agent) -> None:
            assert expected is self.agent
            self.pins += 1

        def unpin_agent(self, expected: Agent) -> None:
            assert expected is self.agent
            self.pins -= 1

        async def cleanup_live_voice_formal_task_agents(self) -> None:
            assert self.pins == 0
            self.cleanup_calls += 1

    manager = Manager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),  # type: ignore[arg-type]
        agent_manager=manager,
        service=None,
        model_resolver=Models(),  # type: ignore[arg-type]
        principal=object(),  # type: ignore[arg-type]
    )

    resolving = asyncio.create_task(
        resolver.resolve(_spec(tmp_path), for_dispatch=True)
    )
    assert await asyncio.to_thread(entered.wait, 2)
    closing = asyncio.create_task(resolver.close())
    await asyncio.sleep(0)
    assert resolver._close_requested is True
    allow_revalidate.set()

    with pytest.raises(FormalTaskViolation) as fenced:
        await resolving
    assert fenced.value.reason == "EXECUTOR_CAPABILITY_UNAVAILABLE"
    await closing

    assert resolver._closed is True
    assert manager.pins == 0
    assert manager.get_calls == 1
    assert manager.cleanup_calls == 1
    with pytest.raises(FormalTaskViolation):
        await resolver.resolve(_spec(tmp_path), for_dispatch=True)
    assert manager.get_calls == 1


@pytest.mark.asyncio
async def test_binding_resolver_clear_failure_is_visible_and_retryable(
    tmp_path: Path,
) -> None:
    class Authority:
        def revalidate(self, _context, **_kwargs):
            raise AssertionError("closed resolver must not revalidate")

    class Service:
        def __init__(self) -> None:
            self.clear_calls = 0

        def clear_scheduled_task_execution_contexts(self) -> None:
            self.clear_calls += 1
            if self.clear_calls == 1:
                raise RuntimeError("injected context cleanup failure")

    class Manager:
        def __init__(self) -> None:
            self.cleanup_calls = 0

        async def cleanup_live_voice_formal_task_agents(self) -> None:
            self.cleanup_calls += 1

    service = Service()
    manager = Manager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),  # type: ignore[arg-type]
        agent_manager=manager,
        service=service,
        model_resolver=object(),  # type: ignore[arg-type]
        principal=object(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="FORMAL_PROJECT_BINDING_CLEANUP_PENDING"):
        await resolver.close()
    assert resolver._closed is False
    assert resolver._close_requested is True
    assert service.clear_calls == 1
    assert manager.cleanup_calls == 1

    await resolver.close()
    assert resolver._closed is True
    assert service.clear_calls == 2
    assert manager.cleanup_calls == 2


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
async def test_direct_executor_runs_two_distinct_projects_concurrently(
    tmp_path: Path,
) -> None:
    first_project = tmp_path / "first-project"
    second_project = tmp_path / "second-project"
    _git_project(first_project)
    _git_project(second_project)
    first_executor = _DirectProjectExecutor(first_project, behavior="observe_wait")
    second_executor = _DirectProjectExecutor(second_project, behavior="observe_wait")
    first_binding = _direct_binding(first_project, first_executor)
    second_binding = replace(
        _direct_binding(second_project, second_executor),
        execution_target={
            "project_dir": str(second_project.resolve()),
            "project_id": "project-2",
            "origin_session_id": "session-1",
            "origin_channel_id": "web",
        },
    )
    resolver = _MappedResolver(
        {
            first_project.resolve(): first_binding,
            second_project.resolve(): second_binding,
        }
    )
    observations: list[object] = []
    adapter = DirectProjectCodeExecutorAdapter(
        resolver,  # type: ignore[arg-type]
        tmp_path / "p3.sqlite3",
        stream_observer=observations.append,
    )
    first_item = _item(first_project)
    second_scope = ScopeRef(
        "user-1",
        "project-2",
        "session-1",
        Assurance.AUTHENTICATED,
    )
    second_spec = _spec(second_project)
    second_spec = replace(
        second_spec,
        context=replace(
            second_spec.context,
            stable_id="project-2",
            scope=second_scope,
        ),
    )
    second_item = replace(
        _item(second_project),
        outbox_id="outbox-2",
        task_id="task-2",
        attempt_id="attempt-2",
        command_id="command-2",
        scope=second_scope,
        spec=second_spec,
    )

    first_delivery = await adapter.dispatch(first_item)
    second_delivery = await adapter.dispatch(second_item)
    await asyncio.wait_for(first_executor.started.wait(), timeout=2)
    await asyncio.wait_for(second_executor.started.wait(), timeout=2)
    for _ in range(100):
        if len(observations) == 4:
            break
        await asyncio.sleep(0.01)

    assert set(adapter._running) == {"attempt-1", "attempt-2"}
    assert resolver.calls == [first_project.resolve(), second_project.resolve()]
    assert len(first_executor.requests) == 1
    assert len(second_executor.requests) == 1
    assert {
        (item.task_ref, item.attempt_ref, item.run_ref) for item in observations
    } == {
        ("task-1", "attempt-1", "d0-project:attempt-1"),
        ("task-2", "attempt-2", "d0-project:attempt-2"),
    }
    assert [
        item.sequence for item in observations if item.attempt_ref == "attempt-1"
    ] == [1, 2]
    assert [
        item.sequence for item in observations if item.attempt_ref == "attempt-2"
    ] == [1, 2]
    assert "PRIVATE_PATH_SENTINEL" not in repr(observations)
    assert "PRIVATE_RESULT_SENTINEL" not in repr(observations)

    await adapter.cancel(
        replace(
            first_item,
            outbox_id="outbox-cancel-1",
            kind=OutboxKind.ATTEMPT_CANCEL,
            executor_ref=first_delivery.executor_ref,
            source_seq=1,
        )
    )
    await adapter.cancel(
        replace(
            second_item,
            outbox_id="outbox-cancel-2",
            kind=OutboxKind.ATTEMPT_CANCEL,
            executor_ref=second_delivery.executor_ref,
            source_seq=1,
        )
    )
    await _wait_direct_settled(adapter)

    assert _git(first_project, "status", "--porcelain") == ""
    assert _git(second_project, "status", "--porcelain") == ""
    await adapter.close()


@pytest.mark.asyncio
async def test_direct_executor_capacity_exhaustion_precedes_resolver_and_project_effect(
    tmp_path: Path,
) -> None:
    project = tmp_path / "capacity-project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    resolver = _Resolver(_direct_binding(project, executor))
    adapter = DirectProjectCodeExecutorAdapter(resolver, tmp_path / "p3.sqlite3")
    blocker = asyncio.Event()
    retained = {
        f"retained-{index}": asyncio.create_task(blocker.wait())
        for index in range(adapter.capability_profile().max_live_attempts)
    }
    adapter._running.update(retained)
    before = _git(project, "status", "--porcelain")

    try:
        with pytest.raises(FormalTaskViolation) as exhausted:
            await adapter.dispatch(_item(project))

        assert exhausted.value.reason == "EXECUTOR_CAPACITY_EXHAUSTED"
        assert exhausted.value.code is ErrorCode.UNAVAILABLE
        assert resolver.calls == []
        assert executor.requests == []
        assert adapter._journal.get("attempt-1") is None
        assert _git(project, "status", "--porcelain") == before
    finally:
        for worker in retained.values():
            worker.cancel()
        await asyncio.gather(*retained.values(), return_exceptions=True)
        adapter._running.clear()
        await adapter.close()


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
    assert isinstance(terminal_after_release, ExecutorDeliveryResult)
    assert terminal_after_release.observations[-1].attempt_outcome is (
        terminal_before_release.observations[-1].attempt_outcome
    )
    assert terminal_after_release.observations[-1].error == (
        terminal_before_release.observations[-1].error
    )
    assert terminal_after_release.observations[-1].raw_status.endswith(
        "cleanup_resolved"
    )
    assert not (project / "late-effect.txt").exists()
    isolated_root = Path(executor.requests[0].params["project_dir"])
    assert isolated_root != project.resolve()
    assert not isolated_root.exists()


@pytest.mark.asyncio
async def test_attempt_deadline_terminalizes_noncooperative_agent_without_target_effect(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    before_head = _git(project, "rev-parse", "HEAD")
    before_tree = _git(project, "status", "--porcelain=v2")
    executor = _NonCooperativeExecutor()
    resolver = _Resolver(_direct_binding(project, executor))  # type: ignore[arg-type]
    adapter = DirectProjectCodeExecutorAdapter(
        resolver,
        tmp_path / "p3.sqlite3",
        heartbeat_interval=0.005,
        attempt_timeout=0.5,
        clock=lambda: (
            "2026-08-18T10:00:01Z"
            if executor.started.is_set()
            else "2026-08-18T10:00:00Z"
        ),
    )

    try:
        delivered = await adapter.dispatch(_item(project))
        await asyncio.wait_for(executor.started.wait(), timeout=2)
        timed_out = await _wait_direct_terminal(adapter)
        for _ in range(100):
            if executor.cancel_signals:
                break
            await asyncio.sleep(0.001)
        target_head_at_timeout = _git(project, "rev-parse", "HEAD")
        target_tree_at_timeout = _git(project, "status", "--porcelain=v2")
        target_effect_at_timeout = (project / "late-effect.txt").exists()
    finally:
        # Cleanup must not release the Agent before the cancellation window is
        # observed. A wall-clock timer racing Git setup invalidated this test.
        executor.release.set()
        await _wait_direct_settled(adapter)

    assert delivered.executor_ref == "d0-project:attempt-1"
    assert timed_out.outcome is TerminalOutcome.INTERRUPTED
    assert timed_out.error == "EXECUTOR_ATTEMPT_TIMEOUT"
    assert timed_out.raw_status == "attempt_timeout_cleanup_pending"
    assert timed_out.owner_id is None
    assert timed_out.lease_expires_at is None
    assert timed_out.expected_tree is None
    assert timed_out.result_text is None
    assert timed_out.artifacts_json is None
    assert executor.cancel_signals == 1
    assert resolver.calls == [True]
    assert len(executor.requests) == 1
    assert len(adapter._journal.all_attempts()) == 1
    assert target_head_at_timeout == before_head
    assert target_tree_at_timeout == before_tree
    assert not target_effect_at_timeout

    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(task, attempt)
    assert isinstance(terminal, ExecutorDeliveryResult)
    observation = terminal.observations[-1]
    assert observation.attempt_outcome is TerminalOutcome.INTERRUPTED
    assert observation.error == "EXECUTOR_ATTEMPT_TIMEOUT"
    assert observation.result_text is None
    assert observation.result_artifacts == ()
    retried = await adapter.dispatch(_item(project))
    assert retried.observations[-1].error == "EXECUTOR_ATTEMPT_TIMEOUT"
    assert resolver.calls == [True]
    assert len(executor.requests) == 1

    resolved = adapter._journal.get("attempt-1")
    assert resolved is not None
    assert resolved.outcome is TerminalOutcome.INTERRUPTED
    assert resolved.error == "EXECUTOR_ATTEMPT_TIMEOUT"
    assert resolved.raw_status == "attempt_timeout_cleanup_resolved"
    assert _git(project, "rev-parse", "HEAD") == before_head
    assert _git(project, "status", "--porcelain=v2") == before_tree
    assert not (project / "late-effect.txt").exists()
    await adapter.close()


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


@pytest.mark.asyncio
async def test_cancel_and_deadline_cannot_interrupt_applying_itinerary_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "isolated-itinerary-project"
    _git_project(project)
    entered = Event()
    release = Event()
    real_apply = project_code_executor._apply_attempt_patch

    def blocked_apply(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", blocked_apply)
    executor = _DemoItineraryProjectExecutor(project)
    clock = {"now": "2026-08-18T10:00:00Z"}
    spec = replace(
        _spec(project),
        name="Three-day itinerary",
        instruction="帮我根据这些要求制定三天的行程。",
    )
    dispatch_item = replace(_item(project), spec=spec)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
        heartbeat_interval=0.005,
        cancel_timeout=0.01,
        attempt_timeout=1,
        clock=lambda: clock["now"],
    )
    delivered = await adapter.dispatch(dispatch_item)
    assert await asyncio.to_thread(entered.wait, 5)
    cancel_item = replace(
        _item(project, kind=OutboxKind.ATTEMPT_CANCEL, source_seq=1),
        spec=spec,
        executor_ref=delivered.executor_ref,
    )

    with pytest.raises(FormalTaskViolation) as pending:
        await adapter.cancel(cancel_item)
    assert pending.value.reason == "EXECUTOR_CANCEL_PENDING"
    clock["now"] = "2026-08-18T10:00:02Z"
    await asyncio.sleep(0.03)
    record = adapter._journal.get("attempt-1")
    assert record is not None
    assert record.raw_status == "applying"
    assert record.state is FormalAttemptState.RUNNING
    assert record.runtime_deadline_at == "2026-08-18T10:00:01Z"
    assert record.owner_id == adapter._owner_id
    assert record.lease_expires_at is not None
    assert "attempt-1" in adapter._running
    assert not (project / "itinerary.md").exists()

    release.set()
    await _wait_direct_settled(adapter)
    task, attempt = _direct_task_attempt(project)
    terminal = await adapter.status(replace(task, spec=spec), attempt)
    observation = terminal.observations[-1]
    assert observation.attempt_outcome is TerminalOutcome.COMPLETED
    assert observation.result_text == ("第二天最早的固定安排是 08:30 参观博物馆。")
    assert len(observation.result_artifacts) == 1
    artifact = observation.result_artifacts[0]
    assert artifact.relative_path == "itinerary.md"
    itinerary = (project / "itinerary.md").read_bytes()
    assert artifact.sha256 == hashlib.sha256(itinerary).hexdigest()
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


@pytest.mark.parametrize(
    "value",
    [
        False,
        0,
        float("inf"),
        project_code_executor._MAX_DIRECT_ATTEMPT_TIMEOUT_SECONDS + 0.01,
    ],
)
def test_direct_executor_attempt_timeout_is_closed_and_bounded(
    tmp_path: Path,
    value: object,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    with pytest.raises(ValueError, match="attempt_timeout"):
        DirectProjectCodeExecutorAdapter(
            _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
            tmp_path / "p3.sqlite3",
            attempt_timeout=value,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("failing_pragma", "expected_statements"),
    [
        (1, ("PRAGMA busy_timeout=30000",)),
        (2, ("PRAGMA busy_timeout=30000", "PRAGMA foreign_keys=ON")),
    ],
)
@pytest.mark.parametrize("close_fails", [False, True], ids=["close-ok", "close-fails"])
def test_direct_journal_setup_failure_closes_its_real_sqlite_handle_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_pragma: int,
    expected_statements: tuple[str, ...],
    close_fails: bool,
) -> None:
    """Catches a setup PRAGMA escaping the connection cleanup boundary."""

    database = tmp_path / "setup-failure.sqlite3"
    primary_failure = RuntimeError("PRIVATE_PRAGMA_PRIMARY_SENTINEL")
    close_failure = RuntimeError("PRIVATE_SQLITE_CLOSE_SENTINEL")
    real_connect = sqlite3.connect
    proxies: list[RealConnectionProxy] = []
    warnings: list[tuple[str, tuple[object, ...]]] = []

    class RealConnectionProxy:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.connection = connection
            self.statements: list[str] = []
            self.close_calls = 0

        @property
        def row_factory(self):
            return self.connection.row_factory

        @row_factory.setter
        def row_factory(self, value) -> None:
            self.connection.row_factory = value

        def execute(self, statement: str) -> sqlite3.Cursor:
            if statement.startswith("PRAGMA"):
                self.statements.append(statement)
                if len(self.statements) == failing_pragma:
                    raise primary_failure
            return self.connection.execute(statement)

        def close(self) -> None:
            self.close_calls += 1
            self.connection.close()
            if close_fails:
                raise close_failure

    def connect(*args, **kwargs) -> RealConnectionProxy:
        proxy = RealConnectionProxy(real_connect(*args, **kwargs))
        proxies.append(proxy)
        return proxy

    def capture_warning(message: str, *args: object) -> None:
        warnings.append((message, args))

    monkeypatch.setattr(
        logging.getLogger(project_code_executor.__name__),
        "warning",
        capture_warning,
    )
    monkeypatch.setattr(project_code_executor.sqlite3, "connect", connect)

    with pytest.raises(RuntimeError) as raised:
        DirectProjectCodeExecutorAdapter(
            object(),  # type: ignore[arg-type] -- setup never consults the resolver
            database,
        )

    assert raised.value is primary_failure
    assert len(proxies) == 1
    proxy = proxies[0]
    assert tuple(proxy.statements) == expected_statements
    assert proxy.close_calls == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        proxy.connection.execute("SELECT 1")

    assert database.exists()
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()
    moved_database = tmp_path / "released.sqlite3"
    database.replace(moved_database)
    moved_database.replace(database)
    probe = real_connect(database, timeout=0.0)
    try:
        probe.execute("BEGIN EXCLUSIVE")
        probe.rollback()
    finally:
        probe.close()

    assert warnings == (
        [("[LiveVoiceP3] direct journal connection cleanup failed", ())]
        if close_fails
        else []
    )
    rendered_messages = repr(warnings)
    assert "PRIVATE_PRAGMA_PRIMARY_SENTINEL" not in rendered_messages
    assert "PRIVATE_SQLITE_CLOSE_SENTINEL" not in rendered_messages


def test_direct_journal_connect_failure_has_no_handle_to_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches cleanup being invented when SQLite never returned a handle."""

    database = tmp_path / "connect-failure.sqlite3"
    primary_failure = RuntimeError("connect failed before ownership")
    connect_calls = 0

    def fail_connect(*_args, **_kwargs):
        nonlocal connect_calls
        connect_calls += 1
        raise primary_failure

    monkeypatch.setattr(project_code_executor.sqlite3, "connect", fail_connect)

    with pytest.raises(RuntimeError) as raised:
        DirectProjectCodeExecutorAdapter(
            object(),  # type: ignore[arg-type] -- setup never consults the resolver
            database,
        )

    assert raised.value is primary_failure
    assert connect_calls == 1
    assert not database.exists()


def test_attempt_deadline_is_absolute_and_heartbeat_expires_at_exact_boundary(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    journal = project_code_executor._DirectProjectAttemptJournal(
        tmp_path / "p3.sqlite3"
    )
    item = _item(project)
    accepted_at = "2026-08-18T10:00:00Z"
    deadline = "2026-08-18T10:00:01Z"
    created, record = journal.create(
        item=item,
        project_root=str(project),
        before_tree=project_code_executor._project_tree_fingerprint(project),
        before_content=project_code_executor._project_content_fingerprint(project),
        before_head=_git(project, "rev-parse", "HEAD"),
        protected_support=project_code_executor._target_support_fingerprints(project),
        governance=project_code_executor._runtime_support_governance(project),
        owner_id="owner-1",
        now=accepted_at,
        runtime_deadline_at=deadline,
    )
    assert created
    assert record.runtime_deadline_at == deadline
    journal.start(item.attempt_id, owner_id="owner-1", now=accepted_at)

    assert journal.heartbeat(
        item.attempt_id,
        owner_id="owner-1",
        now="2026-08-18T10:00:00.999999Z",
    ) == (True, False, False)
    before_boundary = journal.get(item.attempt_id)
    assert before_boundary is not None
    assert before_boundary.runtime_deadline_at == deadline
    assert before_boundary.state is FormalAttemptState.RUNNING

    assert journal.heartbeat(
        item.attempt_id,
        owner_id="owner-1",
        now=deadline,
    ) == (False, False, True)
    terminal = journal.get(item.attempt_id)
    assert terminal is not None
    assert terminal.state is FormalAttemptState.TERMINAL
    assert terminal.outcome is TerminalOutcome.INTERRUPTED
    assert terminal.error == "EXECUTOR_ATTEMPT_TIMEOUT"
    assert terminal.owner_id is None
    assert terminal.lease_expires_at is None
    assert terminal.runtime_deadline_at == deadline
    assert terminal.result_text is None
    assert terminal.artifacts_json is None
    assert journal.heartbeat(
        item.attempt_id,
        owner_id="owner-1",
        now="2026-08-18T10:00:02Z",
    ) == (False, False, False)


def test_attempt_deadline_migrates_from_last_durable_legacy_lease(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "p3.sqlite3"
    journal = project_code_executor._DirectProjectAttemptJournal(database)
    item = _item(project)
    created, _ = journal.create(
        item=item,
        project_root=str(project),
        before_tree=project_code_executor._project_tree_fingerprint(project),
        before_content=project_code_executor._project_content_fingerprint(project),
        before_head=_git(project, "rev-parse", "HEAD"),
        protected_support=project_code_executor._target_support_fingerprints(project),
        governance=project_code_executor._runtime_support_governance(project),
        owner_id="legacy-owner",
        now="2026-08-18T10:00:00Z",
    )
    assert created
    journal.start(
        item.attempt_id,
        owner_id="legacy-owner",
        now="2026-08-18T10:00:00Z",
    )
    assert journal.heartbeat(
        item.attempt_id,
        owner_id="legacy-owner",
        now="2026-08-18T10:01:00Z",
    ) == (True, False, False)
    legacy = journal.get(item.attempt_id)
    assert legacy is not None
    legacy_lease = legacy.lease_expires_at
    assert legacy_lease == "2026-08-18T10:06:00Z"

    with sqlite3.connect(database) as connection:
        connection.execute(
            f"ALTER TABLE {project_code_executor._DIRECT_EXECUTOR_TABLE} "
            "DROP COLUMN runtime_deadline_at"
        )

    migrated_journal = project_code_executor._DirectProjectAttemptJournal(database)
    migrated = migrated_journal.get(item.attempt_id)
    assert migrated is not None
    assert migrated.runtime_deadline_at == legacy_lease
    assert migrated_journal.recover_expired(now=legacy_lease) == 1
    terminal = migrated_journal.get(item.attempt_id)
    assert terminal is not None
    assert terminal.outcome is TerminalOutcome.INTERRUPTED
    assert terminal.error == "EXECUTOR_ATTEMPT_TIMEOUT"
    assert terminal.owner_id is None
    assert terminal.lease_expires_at is None


def test_reserve_completion_at_deadline_cannot_publish_or_apply_result(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    journal = project_code_executor._DirectProjectAttemptJournal(
        tmp_path / "p3.sqlite3"
    )
    item = _item(project)
    before_tree = project_code_executor._project_tree_fingerprint(project)
    before_head = _git(project, "rev-parse", "HEAD")
    deadline = "2026-08-18T10:00:01Z"
    created, _ = journal.create(
        item=item,
        project_root=str(project),
        before_tree=before_tree,
        before_content=project_code_executor._project_content_fingerprint(project),
        before_head=before_head,
        protected_support=project_code_executor._target_support_fingerprints(project),
        governance=project_code_executor._runtime_support_governance(project),
        owner_id="owner-1",
        now="2026-08-18T10:00:00Z",
        runtime_deadline_at=deadline,
    )
    assert created
    journal.start(
        item.attempt_id,
        owner_id="owner-1",
        now="2026-08-18T10:00:00Z",
    )

    reserved, terminal = journal.reserve_completion(
        item.attempt_id,
        owner_id="owner-1",
        expected_tree="late-expected-tree",
        now=deadline,
        result_text="late result",
        result_artifacts=(
            project_code_executor.TaskResultArtifact(
                relative_path="README.md",
                sha256=hashlib.sha256((project / "README.md").read_bytes()).hexdigest(),
            ),
        ),
    )

    assert not reserved
    assert terminal.outcome is TerminalOutcome.INTERRUPTED
    assert terminal.error == "EXECUTOR_ATTEMPT_TIMEOUT"
    assert terminal.raw_status == "attempt_timeout_cleanup_pending"
    assert terminal.expected_tree is None
    assert terminal.result_text is None
    assert terminal.artifacts_json is None
    assert terminal.owner_id is None
    assert terminal.lease_expires_at is None
    assert _git(project, "rev-parse", "HEAD") == before_head
    assert project_code_executor._project_tree_fingerprint(project) == before_tree


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
async def test_d069_barrier_uses_real_direct_checkout_cancel_and_stop(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    attempt_roots: list[Path] = []
    releases: list[str] = []

    class ToolManager:
        async def execute(self, *_args, **_kwargs):
            return None

    class AttemptAgent:
        def __init__(self, root: Path) -> None:
            self.root = root
            self.child = None

            async def prepare(_session_id: str) -> None:
                self.child = SimpleNamespace(
                    _instance=SimpleNamespace(ability_manager=ToolManager())
                )

            self._adapter = SimpleNamespace(
                prepare_background_project_session=prepare,
                _get_cached_session_adapter=lambda _session_id: self.child,
            )

        def get_project_execution_root(self) -> str:
            return str(self.root)

        async def process_background_code_task_stream(self, request):
            await self._adapter.prepare_background_project_session(request.session_id)
            if False:
                yield None

    async def acquire(attempt_root: str) -> AttemptProjectExecutorLease:
        root = Path(attempt_root).resolve()
        attempt_roots.append(root)

        async def release() -> None:
            releases.append("released")

        return AttemptProjectExecutorLease(AttemptAgent(root), str(root), release)

    binding = replace(
        _direct_binding(project, _DirectProjectExecutor(project)),
        attempt_executor_factory=acquire,
    )
    direct = DirectProjectCodeExecutorAdapter(
        _Resolver(binding), tmp_path / "p3.sqlite3"
    )
    core = SimpleNamespace(executor=direct)
    barrier = _P3NonterminalBarrier(core)
    barrier.install()
    try:
        delivered = await core.executor.dispatch(_item(project))
        await barrier.wait_frozen(timeout=2)
        assert attempt_roots[0].is_dir()
        assert barrier.snapshot() == _P3_FROZEN_ENTRY_COUNTS
        before_cancel = barrier.snapshot()
        cancel_item = replace(
            _item(project, kind=OutboxKind.ATTEMPT_CANCEL, source_seq=1),
            executor_ref=delivered.executor_ref,
        )
        cancelled = await core.executor.cancel(cancel_item)
        await barrier.wait_agent_stopped(timeout=2)
        assert barrier.delta(before_cancel) == _P3_CANCEL_ENTRY_DELTA
        assert cancelled.observations[-1].attempt_outcome is TerminalOutcome.CANCELLED
        assert releases == ["released"]
        assert not attempt_roots[0].exists()
    finally:
        barrier.restore()
        await direct.close(interrupt_running=True)
    assert direct.has_live_workers is False


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

    try:
        immediate = await observer.cancel(cancel_item)
    except FormalTaskViolation as pending:
        assert pending.reason == "EXECUTOR_CANCEL_PENDING"
    else:
        assert immediate.observations[-1].attempt_outcome is TerminalOutcome.CANCELLED
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

    monkeypatch.setattr(project_code_executor, "_remove_attempt_worktree", fail_once)
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
    # A live predecessor retains the OS ownership lock across cleanup
    # failure, so a successor must not delete its checkout.
    assert await restarted.prepare_startup() == 0
    assert restarted.retained_cleanup_attempt_ids() == ()
    assert isolated_root.exists()
    await adapter.close()
    await restarted.prepare_startup()
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

    monkeypatch.setattr(project_code_executor, "_remove_attempt_worktree", real_remove)
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
    worktree_parent, worktree = project_code_executor._create_attempt_worktree(
        project,
        item.attempt_id,
        _git(project, "rev-parse", "HEAD"),
    )
    assert worktree.exists()
    assert project_code_executor._worktree_registered(project, worktree)

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
    live_record = live._journal.get(item.attempt_id)
    assert live_record is not None
    assert live_record.state is FormalAttemptState.RUNNING
    assert worktree.exists()
    assert worktree_parent.exists()
    assert project_code_executor._worktree_registered(project, worktree)
    assert live.retained_cleanup_attempt_ids() == ()

    assert await expired.prepare_startup() == 1
    assert not worktree.exists()
    assert not project_code_executor._worktree_registered(project, worktree)
    assert expired.retained_cleanup_attempt_ids() == ()
    task, attempt = _direct_task_attempt(project)
    terminal = await expired.status(task, attempt)
    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.INTERRUPTED
    assert terminal.observations[-1].error == "EXECUTOR_PROCESS_RESTARTED"


@pytest.mark.asyncio
async def test_restart_reuses_deadline_even_when_heartbeat_renewed_later_lease(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "p3.sqlite3"
    journal = project_code_executor._DirectProjectAttemptJournal(database)
    item = _item(project)
    before_head = _git(project, "rev-parse", "HEAD")
    before_tree = project_code_executor._project_tree_fingerprint(project)
    deadline = "2026-08-18T10:00:10Z"
    created, _ = journal.create(
        item=item,
        project_root=str(project),
        before_tree=before_tree,
        before_content=project_code_executor._project_content_fingerprint(project),
        before_head=before_head,
        protected_support=project_code_executor._target_support_fingerprints(project),
        governance=project_code_executor._runtime_support_governance(project),
        owner_id="dead-process",
        now="2026-08-18T10:00:00Z",
        runtime_deadline_at=deadline,
    )
    assert created
    journal.start(
        item.attempt_id,
        owner_id="dead-process",
        now="2026-08-18T10:00:00Z",
    )
    assert journal.heartbeat(
        item.attempt_id,
        owner_id="dead-process",
        now="2026-08-18T10:00:09Z",
    ) == (True, False, False)
    renewed = journal.get(item.attempt_id)
    assert renewed is not None
    assert renewed.runtime_deadline_at == deadline
    assert renewed.lease_expires_at == "2026-08-18T10:05:09Z"

    successor = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        database,
        clock=lambda: deadline,
    )
    assert await successor.prepare_startup() == 1
    terminal = successor._journal.get(item.attempt_id)
    assert terminal is not None
    assert terminal.outcome is TerminalOutcome.INTERRUPTED
    assert terminal.error == "EXECUTOR_ATTEMPT_TIMEOUT"
    assert terminal.runtime_deadline_at == deadline
    assert terminal.owner_id is None
    assert terminal.lease_expires_at is None
    assert terminal.result_text is None
    assert terminal.artifacts_json is None
    assert _git(project, "rev-parse", "HEAD") == before_head
    assert project_code_executor._project_tree_fingerprint(project) == before_tree
    await successor.close()


@pytest.mark.asyncio
async def test_successor_never_recovers_or_deletes_while_predecessor_process_owns_lock(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "p3.sqlite3"
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        database,
    )
    item = _item(project)
    before_head = _git(project, "rev-parse", "HEAD")
    created, original = adapter._journal.create(
        item=item,
        project_root=str(project),
        before_tree=project_code_executor._project_tree_fingerprint(project),
        before_content=project_code_executor._project_content_fingerprint(project),
        before_head=before_head,
        protected_support=project_code_executor._target_support_fingerprints(project),
        governance=project_code_executor._runtime_support_governance(project),
        owner_id="predecessor-process",
        now="2020-01-01T00:00:00.000000Z",
    )
    assert created
    adapter._journal.start(
        item.attempt_id,
        owner_id="predecessor-process",
        now="2020-01-01T00:00:00.000000Z",
    )

    script = "\n".join(
        (
            "import sys",
            "from pathlib import Path",
            "from jiuwenswarm.server.live_voice.project_code_executor import (",
            "    _AttemptOwnershipLock, _create_attempt_worktree",
            ")",
            "root = Path(sys.argv[1])",
            "attempt_id = sys.argv[2]",
            "before_head = sys.argv[3]",
            "ownership = _AttemptOwnershipLock.try_acquire(root, attempt_id)",
            "assert ownership is not None",
            "_parent, checkout = _create_attempt_worktree(root, attempt_id, before_head)",
            "print('D0_LOCK_READY:' + str(checkout), flush=True)",
            "sys.stdin.readline()",
            "ownership.release()",
        )
    )
    predecessor = subprocess.Popen(
        [sys.executable, "-c", script, str(project), item.attempt_id, before_head],
        cwd=str(Path.cwd()),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert predecessor.stdout is not None
    assert predecessor.stdin is not None
    try:
        checkout_line = ""
        while line := predecessor.stdout.readline():
            if line.startswith("D0_LOCK_READY:"):
                checkout_line = line.removeprefix("D0_LOCK_READY:").strip()
                break
        assert checkout_line
        checkout = Path(checkout_line)
        assert checkout.exists()

        successor = DirectProjectCodeExecutorAdapter(
            _Resolver(_direct_binding(project, executor)),
            database,
        )
        assert await successor.prepare_startup() == 0
        still_running = adapter._journal.get(item.attempt_id)
        assert still_running is not None
        assert still_running.state is not FormalAttemptState.TERMINAL
        assert still_running.runtime_deadline_at == original.runtime_deadline_at
        assert checkout.exists()

        predecessor.stdin.write("release\n")
        predecessor.stdin.flush()
        assert predecessor.wait(timeout=10) == 0
        predecessor.stdin.close()
        predecessor.stdout.close()
        if predecessor.stderr is not None:
            predecessor.stderr.close()

        assert await successor.prepare_startup() == 1
        recovered = adapter._journal.get(item.attempt_id)
        assert recovered is not None
        assert recovered.state is FormalAttemptState.TERMINAL
        assert recovered.outcome is TerminalOutcome.INTERRUPTED
        assert recovered.error == "EXECUTOR_ATTEMPT_TIMEOUT"
        assert recovered.runtime_deadline_at == original.runtime_deadline_at
        assert recovered.owner_id is None
        assert recovered.lease_expires_at is None
        assert not checkout.exists()
        await successor.close()
    finally:
        if predecessor.poll() is None:
            predecessor.kill()
            predecessor.wait(timeout=10)
        for stream in (predecessor.stdin, predecessor.stdout, predecessor.stderr):
            if stream is not None and not stream.closed:
                stream.close()


@pytest.mark.asyncio
async def test_successor_cannot_recover_between_apply_and_completed_journal_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "p3.sqlite3"
    executor = _DirectProjectExecutor(project)
    predecessor = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        database,
        clock=lambda: "2020-01-01T00:00:00.000000Z",
    )
    completion_started = Event()
    allow_completion = Event()
    real_finish = predecessor._journal.finish

    def block_completed_truth(*args, **kwargs):
        if kwargs.get("outcome") is TerminalOutcome.COMPLETED:
            completion_started.set()
            assert allow_completion.wait(timeout=10)
        return real_finish(*args, **kwargs)

    monkeypatch.setattr(predecessor._journal, "finish", block_completed_truth)
    await predecessor.dispatch(_item(project))
    assert await asyncio.to_thread(completion_started.wait, 10)
    checkout = Path(executor.requests[0].params["project_dir"])
    assert checkout.exists()

    successor = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        database,
        clock=lambda: "2030-01-01T00:00:00.000000Z",
    )
    assert await successor.prepare_startup() == 0
    unresolved = predecessor._journal.get("attempt-1")
    assert unresolved is not None
    assert unresolved.state is not FormalAttemptState.TERMINAL
    assert checkout.exists()

    allow_completion.set()
    await _wait_direct_settled(predecessor)
    terminal = predecessor._journal.get("attempt-1")
    assert terminal is not None
    assert terminal.outcome is TerminalOutcome.COMPLETED
    assert await successor.prepare_startup() == 0
    assert not checkout.exists()
    await predecessor.close()
    await successor.close()


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
    expected_artifact_hash = hashlib.sha256(readme.read_bytes()).hexdigest()
    readme.write_text("baseline\n", encoding="utf-8")
    reserved, _ = journal.reserve_completion(
        item.attempt_id,
        owner_id="dead-process",
        expected_tree=expected_content,
        now="2026-08-07T10:00:00Z",
        result_text="generated result",
        result_artifacts=(
            project_code_executor.TaskResultArtifact(
                relative_path="README.md",
                sha256=expected_artifact_hash,
            ),
        ),
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
    assert recovered.result_text == "generated result"
    assert json.loads(recovered.artifacts_json or "[]") == [
        {
            "relative_path": "README.md",
            "sha256": expected_artifact_hash,
        }
    ]


def test_direct_executor_restart_recognizes_exact_autocrlf_patch(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    _git(project, "config", "core.autocrlf", "true")
    readme = project / "README.md"
    readme.write_bytes(b"baseline\r\n")
    assert _git(project, "status", "--porcelain") == ""

    journal = project_code_executor._DirectProjectAttemptJournal(
        tmp_path / "p3.sqlite3"
    )
    item = _item(project)
    before_tree = project_code_executor._project_tree_fingerprint(project)
    before_content = project_code_executor._project_content_fingerprint(project)
    before_head = _git(project, "rev-parse", "HEAD")
    protected_support = project_code_executor._target_support_fingerprints(project)
    created, _ = journal.create(
        item=item,
        project_root=str(project),
        before_tree=before_tree,
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

    worktree = tmp_path / "attempt-worktree"
    _git(project, "worktree", "add", "--detach", str(worktree), before_head)
    try:
        (worktree / "README.md").write_bytes(b"baseline\ncompleted\n")
        patch, expected_content = project_code_executor._attempt_patch(worktree)
    finally:
        _git(project, "worktree", "remove", "--force", str(worktree))
    expected_state = project_code_executor._encode_expected_project_state(
        expected_content,
        patch=patch,
    )
    reserved, _ = journal.reserve_completion(
        item.attempt_id,
        owner_id="dead-process",
        expected_tree=expected_state,
        now="2026-08-07T10:00:00Z",
    )
    assert reserved is True
    project_code_executor._git_run_with_input(
        project,
        ("apply", "--binary", "-"),
        patch,
    )
    assert (
        project_code_executor._project_content_fingerprint(project) != expected_content
    )

    assert journal.recover_expired(now="2026-08-07T10:05:01Z") == 1
    recovered = journal.get(item.attempt_id)
    assert recovered is not None
    assert recovered.outcome is TerminalOutcome.COMPLETED
    assert recovered.raw_status == "restart_apply_completed"
    assert recovered.error is None


# --- D-069 Executor retry readiness seam ------------------------------------


def _terminal_direct_attempt(
    project: Path,
    *,
    outcome: TerminalOutcome = TerminalOutcome.COMPLETED,
    attempt_number: int = 1,
    task_id: str = "task-1",
    attempt_id: str = "attempt-1",
) -> tuple[PersistentTaskRecord, PersistentAttemptRecord]:
    task, attempt = _direct_task_attempt(
        project, task_id=task_id, attempt_id=attempt_id
    )
    return (
        replace(task, state=FormalTaskState.TERMINAL, outcome=outcome),
        replace(
            attempt,
            state=FormalAttemptState.TERMINAL,
            outcome=outcome,
            attempt_number=attempt_number,
        ),
    )


def _readiness_environment(project: Path) -> tuple[str, str]:
    """Capture the Git surfaces a read-only readiness proof must not disturb."""

    return (
        _git(project, "status", "--porcelain"),
        _git(project, "rev-parse", "HEAD"),
    )


def _journal_dump(adapter: DirectProjectCodeExecutorAdapter) -> tuple[str, ...]:
    """Logical journal content, which a read-only readiness proof must preserve.

    Raw file bytes are not a sound oracle here: opening and closing a SQLite
    connection maintains the header change counter and page count even for a
    pure read, so byte equality would report a difference that carries no data.
    """

    with sqlite3.connect(adapter._journal.database) as connection:
        return tuple(connection.iterdump())


async def _completed_direct_attempt(
    tmp_path: Path,
) -> tuple[DirectProjectCodeExecutorAdapter, Path]:
    """Drive one real exact-root attempt to a completed terminal journal row."""

    project = tmp_path / "project"
    _git_project(project)

    async def acquire_attempt(attempt_root: str) -> AttemptProjectExecutorLease:
        root = Path(attempt_root).resolve()
        attempt_executor = _ExactRootDirectProjectExecutor(root)

        async def release_attempt() -> None:
            return None

        return AttemptProjectExecutorLease(attempt_executor, str(root), release_attempt)

    binding = replace(
        _direct_binding(project, _DirectProjectExecutor(project)),
        attempt_executor_factory=acquire_attempt,
    )
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(binding),
        tmp_path / "p3.sqlite3",
    )
    await adapter.dispatch(_item(project))
    await _wait_direct_settled(adapter)
    record = adapter._journal.get("attempt-1")
    assert record is not None
    assert record.state is FormalAttemptState.TERMINAL
    assert record.outcome is TerminalOutcome.COMPLETED, record.error
    return adapter, project


@pytest.mark.asyncio
async def test_retry_readiness_proves_a_quiescent_predecessor(
    tmp_path: Path,
) -> None:
    adapter, project = await _completed_direct_attempt(tmp_path)
    task, attempt = _terminal_direct_attempt(project)
    before_environment = _readiness_environment(project)
    before_journal = _journal_dump(adapter)

    readiness = adapter.retry_readiness(task, attempt)

    assert readiness.ready is True
    assert readiness.reason == "PREDECESSOR_QUIESCENT"
    # The proof binds the exact predecessor Core will re-check.
    assert readiness.task_id == task.task_id
    assert readiness.previous_attempt_id == attempt.attempt_id
    assert readiness.previous_outcome is TerminalOutcome.COMPLETED
    assert readiness.previous_attempt_number == 1
    # Read-only: no journal write, no Git mutation, no retained worktree.
    assert _journal_dump(adapter) == before_journal
    assert _readiness_environment(project) == before_environment
    assert adapter._retained_worktree_cleanups == {}
    assert adapter._running == {}


@pytest.mark.asyncio
async def test_retry_readiness_is_synchronous_and_never_awaits(
    tmp_path: Path,
) -> None:
    adapter, project = await _completed_direct_attempt(tmp_path)
    # The Core seam is deliberately synchronous so its snapshot stays atomic
    # with respect to the event loop that owns the attempt lifecycle.
    assert not inspect.iscoroutinefunction(adapter.retry_readiness)
    assert not inspect.isasyncgenfunction(adapter.retry_readiness)
    task, attempt = _terminal_direct_attempt(project)
    assert adapter.retry_readiness(task, attempt).ready is True


@pytest.mark.asyncio
async def test_retry_readiness_rejects_a_nonterminal_predecessor_outcome(
    tmp_path: Path,
) -> None:
    adapter, project = await _completed_direct_attempt(tmp_path)
    task, attempt = _direct_task_attempt(project)
    before_journal = _journal_dump(adapter)

    with pytest.raises(FormalTaskViolation) as rejected:
        adapter.retry_readiness(task, attempt)

    assert rejected.value.reason == "TASK_RETRY_EXECUTOR_READINESS_MISMATCH"
    assert rejected.value.code is ErrorCode.PROTOCOL_VIOLATION
    assert _journal_dump(adapter) == before_journal


@pytest.mark.asyncio
async def test_retry_readiness_reports_every_retained_executor_state(
    tmp_path: Path,
) -> None:
    adapter, project = await _completed_direct_attempt(tmp_path)
    task, attempt = _terminal_direct_attempt(project)
    before_environment = _readiness_environment(project)
    before_journal = _journal_dump(adapter)

    def _assert_not_ready(expected_reason: str) -> None:
        readiness = adapter.retry_readiness(task, attempt)
        assert readiness.ready is False, expected_reason
        assert readiness.reason == expected_reason
        # Even a not-ready verdict binds the exact predecessor so Core can
        # separate "not yet quiescent" from "evidence for another attempt".
        assert readiness.task_id == task.task_id
        assert readiness.previous_attempt_id == attempt.attempt_id
        assert readiness.previous_outcome is TerminalOutcome.COMPLETED
        assert readiness.previous_attempt_number == 1
        assert _journal_dump(adapter) == before_journal
        assert _readiness_environment(project) == before_environment

    live: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    worker = asyncio.ensure_future(live)
    try:
        adapter._running["attempt-1"] = worker
        _assert_not_ready("ATTEMPT_WORKER_LIVE")
    finally:
        adapter._running.pop("attempt-1", None)
        live.set_result(None)
        await worker

    adapter._applying.add("attempt-1")
    _assert_not_ready("ATTEMPT_APPLY_IN_PROGRESS")
    adapter._applying.discard("attempt-1")

    adapter._interruptions["attempt-1"] = ("shutdown", "retained")
    _assert_not_ready("ATTEMPT_INTERRUPTION_PENDING")
    adapter._interruptions.pop("attempt-1", None)

    retained = project_code_executor._RetainedAttemptCleanup(
        root=project,
        parent=project,
        worktree=project / "attempt-worktree",
        ownership=SimpleNamespace(release=lambda: None),
    )
    adapter._retained_worktree_cleanups["attempt-1"] = retained
    _assert_not_ready("ATTEMPT_CLEANUP_RETAINED")
    retained.completion_pending = True
    _assert_not_ready("ATTEMPT_CLEANUP_COMPLETION_PENDING")
    adapter._retained_worktree_cleanups.pop("attempt-1", None)

    adapter._closed = True
    _assert_not_ready("EXECUTOR_CLOSED")
    adapter._closed = False

    # The verdict is ready again once every retained surface is released.
    assert adapter.retry_readiness(task, attempt).ready is True


@pytest.mark.asyncio
async def test_retry_readiness_rejects_journal_lineage_divergence(
    tmp_path: Path,
) -> None:
    adapter, project = await _completed_direct_attempt(tmp_path)
    before_journal = _journal_dump(adapter)

    unknown_task, unknown_attempt = _terminal_direct_attempt(
        project, attempt_id="attempt-never-dispatched"
    )
    missing = adapter.retry_readiness(unknown_task, unknown_attempt)
    assert missing.ready is False
    assert missing.reason == "ATTEMPT_JOURNAL_MISSING"
    assert missing.previous_attempt_id == "attempt-never-dispatched"

    foreign_task, foreign_attempt = _terminal_direct_attempt(
        project, task_id="task-other"
    )
    mismatched = adapter.retry_readiness(foreign_task, foreign_attempt)
    assert mismatched.ready is False
    assert mismatched.reason == "ATTEMPT_JOURNAL_TASK_MISMATCH"
    assert mismatched.task_id == "task-other"

    diverged_task, diverged_attempt = _terminal_direct_attempt(
        project, outcome=TerminalOutcome.CANCELLED
    )
    diverged = adapter.retry_readiness(diverged_task, diverged_attempt)
    assert diverged.ready is False
    assert diverged.reason == "ATTEMPT_OUTCOME_DIVERGED"
    assert diverged.previous_outcome is TerminalOutcome.CANCELLED

    assert _journal_dump(adapter) == before_journal


@pytest.mark.asyncio
async def test_retry_readiness_reports_retained_journal_cleanup_and_lease(
    tmp_path: Path,
) -> None:
    adapter, project = await _completed_direct_attempt(tmp_path)
    task, attempt = _terminal_direct_attempt(project)
    before_environment = _readiness_environment(project)
    assert adapter.retry_readiness(task, attempt).ready is True

    # Retained cleanup truth is journal-owned and must block a retry even
    # though the business terminal outcome is already durable.
    adapter._journal.mark_cleanup_pending("attempt-1")
    pending = adapter.retry_readiness(task, attempt)
    assert pending.ready is False
    assert pending.reason == "ATTEMPT_CLEANUP_PENDING"
    assert pending.previous_attempt_id == "attempt-1"
    adapter._journal.mark_cleanup_resolved("attempt-1")
    assert adapter.retry_readiness(task, attempt).ready is True

    # A retained owner/lease means another process may still touch the exact
    # attempt, so the predecessor is not proven quiescent here.
    with sqlite3.connect(adapter._journal.database) as connection:
        connection.execute(
            f"UPDATE {project_code_executor._DIRECT_EXECUTOR_TABLE} "
            "SET owner_id=?, lease_expires_at=? WHERE attempt_id=?",
            ("foreign-process", "2026-08-07T10:05:00Z", "attempt-1"),
        )
    retained = adapter.retry_readiness(task, attempt)
    assert retained.ready is False
    assert retained.reason == "ATTEMPT_LEASE_RETAINED"

    # A journal row that never reached terminal is equally not retry-ready.
    with sqlite3.connect(adapter._journal.database) as connection:
        connection.execute(
            f"UPDATE {project_code_executor._DIRECT_EXECUTOR_TABLE} "
            "SET owner_id=NULL, lease_expires_at=NULL, state=?, outcome=NULL "
            "WHERE attempt_id=?",
            (FormalAttemptState.RUNNING.value, "attempt-1"),
        )
    nonterminal = adapter.retry_readiness(task, attempt)
    assert nonterminal.ready is False
    assert nonterminal.reason == "ATTEMPT_JOURNAL_NONTERMINAL"

    # None of these read-only verdicts touched the canonical project.
    assert _readiness_environment(project) == before_environment


def _cancelled_before_dispatch(
    project: Path,
    *,
    task_id: str = "task-1",
    attempt_id: str = "attempt-1",
) -> tuple[PersistentTaskRecord, PersistentAttemptRecord]:
    """The exact Store shape of a task cancelled before its dispatch claim.

    ``task.cancel`` fences dispatch and resolves the attempt without the
    Direct Executor ever being called, so no journal row exists for it.
    """

    task = PersistentTaskRecord(
        task_id,
        _scope(),
        _spec(project),
        FormalTaskState.TERMINAL,
        attempt_id,
        "correlation-1",
        True,
        True,
        TerminalOutcome.CANCELLED,
        None,
        None,
        "command-create-1",
        None,
        1,
    )
    attempt = PersistentAttemptRecord(
        attempt_id,
        task_id,
        FORMAL_PROJECT_EXECUTOR_ID,
        None,
        FormalAttemptState.TERMINAL,
        TerminalOutcome.CANCELLED,
        -1,
    )
    return task, attempt


@pytest.mark.asyncio
async def test_retry_readiness_accepts_a_cancelled_before_dispatch_predecessor(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        tmp_path / "p3.sqlite3",
    )
    task, attempt = _cancelled_before_dispatch(project)
    before_environment = _readiness_environment(project)
    before_journal = _journal_dump(adapter)

    readiness = adapter.retry_readiness(task, attempt)

    assert readiness.ready is True
    assert readiness.reason == "PREDECESSOR_CANCELLED_BEFORE_DISPATCH"
    assert readiness.task_id == task.task_id
    assert readiness.previous_attempt_id == attempt.attempt_id
    assert readiness.previous_outcome is TerminalOutcome.CANCELLED
    assert readiness.previous_attempt_number == 1
    # The adapter was never called for this attempt and stays untouched.
    assert executor.requests == []
    assert adapter._running == {}
    assert adapter._retained_worktree_cleanups == {}
    assert adapter._journal.get("attempt-1") is None
    assert _journal_dump(adapter) == before_journal
    assert _readiness_environment(project) == before_environment


@pytest.mark.asyncio
async def test_missing_journal_stays_fail_closed_without_every_exact_fact(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        tmp_path / "p3.sqlite3",
    )
    task, attempt = _cancelled_before_dispatch(project)
    before_journal = _journal_dump(adapter)
    before_environment = _readiness_environment(project)

    # Each single missing or contradictory fact keeps the verdict not ready.
    degraded: tuple[tuple[str, PersistentTaskRecord, PersistentAttemptRecord], ...] = (
        ("cancel not requested", replace(task, cancel_requested=False), attempt),
        ("dispatch not fenced", replace(task, dispatch_fenced=False), attempt),
        (
            "task not terminal",
            replace(task, state=FormalTaskState.RUNNING, outcome=None),
            attempt,
        ),
        (
            "completed rather than cancelled",
            replace(task, outcome=TerminalOutcome.COMPLETED),
            replace(attempt, outcome=TerminalOutcome.COMPLETED),
        ),
        (
            "attempt not terminal",
            task,
            replace(attempt, state=FormalAttemptState.RUNNING, outcome=None),
        ),
        (
            "executor_ref already bound",
            task,
            replace(attempt, executor_ref="d0-project:attempt-1"),
        ),
        (
            "foreign executor",
            task,
            replace(attempt, executor_id="legacy.demo_substitute"),
        ),
        (
            "task points at another attempt",
            replace(task, attempt_id="attempt-other"),
            attempt,
        ),
        (
            "attempt belongs to another task",
            task,
            replace(attempt, task_id="task-other"),
        ),
    )
    for label, degraded_task, degraded_attempt in degraded:
        if degraded_attempt.outcome is None:
            # A non-terminal outcome is refused earlier, by contract.
            with pytest.raises(FormalTaskViolation) as rejected:
                adapter.retry_readiness(degraded_task, degraded_attempt)
            assert rejected.value.reason == (
                "TASK_RETRY_EXECUTOR_READINESS_MISMATCH"
            ), label
        else:
            readiness = adapter.retry_readiness(degraded_task, degraded_attempt)
            assert readiness.ready is False, label
            assert readiness.reason == "ATTEMPT_JOURNAL_MISSING", label
        assert _journal_dump(adapter) == before_journal, label
        assert _readiness_environment(project) == before_environment, label
