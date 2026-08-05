# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import runpy
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ErrorCode,
    OriginRef,
    ScopeRef,
    TerminalOutcome,
)
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
    FORMAL_PROJECT_EXECUTOR_ID,
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
