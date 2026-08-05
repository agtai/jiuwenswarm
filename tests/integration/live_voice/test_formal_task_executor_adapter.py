# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jiuwenswarm.agents.harness.common.auto_harness.service import AutoHarnessService
from jiuwenswarm.agents.harness.common.auto_harness.task_store import (
    TaskStore as LegacyTaskStore,
)
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    OriginRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskSpec,
    OutboxKind,
    OutboxState,
    PersistentOutboxItem,
    ResolvedTaskContext,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    FORMAL_PROJECT_EXECUTOR_ID,
    PROJECT_CODE_PIPELINE,
    ProjectCodeExecutorAdapter,
    ProjectExecutionBinding,
)


class _ProjectExecutor:
    async def process_background_code_task_stream(self, *_args, **_kwargs):
        if False:
            yield None


class _Scheduler:
    def __init__(self) -> None:
        self.triggered: list[str] = []

    async def trigger_immediate(self, task_id: str) -> bool:
        self.triggered.append(task_id)
        return True

    def is_execution_active(self, _task_id: str) -> bool:
        return True


class _Resolver:
    def __init__(self, binding: ProjectExecutionBinding) -> None:
        self.binding = binding

    async def resolve(self, _spec: FormalTaskSpec, *, for_dispatch: bool):
        assert for_dispatch is True
        return self.binding


def _legacy_service(
    store: LegacyTaskStore, scheduler: _Scheduler
) -> AutoHarnessService:
    service = AutoHarnessService.__new__(AutoHarnessService)
    service._task_store = store
    service._scheduler = scheduler
    service._agent = None
    service._stream_event_rail = None
    service._scheduled_task_execution_contexts = {}
    return service


@pytest.mark.asyncio
async def test_formal_ed_dispatches_through_real_project_bound_legacy_carrier(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    process = await asyncio.create_subprocess_exec("git", "init", "-q", str(project))
    assert await process.wait() == 0
    scope = ScopeRef("user-1", "project-1", "session-1", Assurance.AUTHENTICATED)
    context = ResolvedTaskContext(
        source="gateway.project_registry",
        stable_id="project-1",
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value="a77516a0",
        scope=scope,
        permissions=("task.execute", "project.write"),
        expires_at="2026-08-05T13:00:00Z",
        redaction_policy_id="live_voice.project.v1",
    )
    spec = FormalTaskSpec(
        name="Formal project task",
        instruction="Create one bounded source change without running commands.",
        origin=OriginRef("structured", None, None),
        context=context,
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        required_capabilities=("task.create",),
        side_effect_class="project_mutation",
    )
    item = PersistentOutboxItem(
        outbox_id="outbox-1",
        kind=OutboxKind.ATTEMPT_DISPATCH,
        task_id="task-1",
        attempt_id="attempt-1",
        command_id="command-1",
        scope=scope,
        spec=spec,
        executor_ref=None,
        source_seq=-1,
        state=OutboxState.CLAIMED,
        delivery_count=1,
    )
    scheduler = _Scheduler()
    service = _legacy_service(LegacyTaskStore(tmp_path / "legacy-store"), scheduler)
    project_executor = _ProjectExecutor()
    binding = ProjectExecutionBinding(
        service=service,
        execution_agent=object(),
        project_executor=project_executor,
        effective_execution_root=str(project.resolve()),
        execution_target={
            "project_dir": str(project.resolve()),
            "project_id": "project-1",
            "origin_session_id": "session-1",
            "origin_channel_id": "web",
        },
        owner_scope={
            "channel_id": "web",
            "session_id": "session-1",
            "app_id": "desktop",
        },
        resolved_revision_kind="version",
        resolved_revision_value="a77516a0",
    )

    delivered = await ProjectCodeExecutorAdapter(_Resolver(binding)).dispatch(item)

    assert delivered.executor_ref.startswith("sch_")
    assert [event.source_seq for event in delivered.observations] == [0, 1]
    assert scheduler.triggered == [delivered.executor_ref]
    persisted = service._task_store.get_task(delivered.executor_ref)
    assert persisted is not None
    assert persisted["pipeline"] == PROJECT_CODE_PIPELINE
    assert persisted["origin_namespace"] == "live_voice"
    assert persisted["idempotency_key"] == "attempt-1"
    assert persisted["execution_contract"]["effective_execution_root"] == str(
        project.resolve()
    )
