from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from jiuwenswarm.agents.harness.common.auto_harness.run_log_status import (
    TERMINAL_STATUSES,
)
from jiuwenswarm.agents.harness.common.auto_harness.scheduler import Scheduler
from jiuwenswarm.agents.harness.common.auto_harness.service import (
    AutoHarnessService,
    ScheduledTaskExecutionContext,
    _build_schedule_run_fingerprint,
)
from jiuwenswarm.agents.harness.common.auto_harness.task_store import (
    TaskStore as PersistentTaskStore,
)
from jiuwenswarm.common.schema.agent import AgentResponseChunk


_PROTOCOL_TERMINAL_STATUSES = (
    "success",
    "failed",
    "cancelled",
    "pr_created",
    "completed",
    "completed_without_pr",
    "skipped",
    "needs_human",
)
_UNKNOWN_EXECUTION_TARGET = {
    "project_dir": "unknown",
    "project_id": "unknown",
    "origin_session_id": "unknown",
    "origin_channel_id": "unknown",
}
_EXECUTION_TARGET = {
    "project_dir": "D:/work/project-a",
    "project_id": "project-a",
    "origin_session_id": "session-a",
    "origin_channel_id": "web",
}
_OWNER_SCOPE = {
    "channel_id": "web",
    "session_id": "session-a",
    "app_id": "desktop",
}


def _assert_unknown_response_metadata(
    result: dict[str, Any],
    *,
    access: str = "legacy_unscoped",
    legacy_unscoped: bool = True,
) -> None:
    assert result["execution_target"] == _UNKNOWN_EXECUTION_TARGET
    assert result["provenance"] == {
        "owner_scope": {
            "channel_id": "unknown",
            "session_id": "unknown",
            "app_id": "unknown",
        },
        "origin_namespace": "unknown",
        "idempotency_key": "unknown",
        "legacy_unscoped": legacy_unscoped,
        "access": access,
    }


class _TaskStore:
    def __init__(self, tasks: list[dict[str, Any]] | None = None) -> None:
        self.tasks = {task["task_id"]: dict(task) for task in tasks or []}
        self.added: list[dict[str, Any]] = []
        self.updates: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[str] = []
        self.log_reads: list[tuple[Any, ...]] = []

    async def add_task(self, task: dict[str, Any]) -> None:
        stored = dict(task)
        self.tasks[stored["task_id"]] = stored
        self.added.append(stored)

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> None:
        self.updates.append((task_id, dict(updates)))
        self.tasks[task_id].update(updates)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self.tasks.get(task_id)

    async def delete_task(self, task_id: str) -> bool:
        if task_id not in self.tasks:
            return False
        self.deleted.append(task_id)
        del self.tasks[task_id]
        return True

    async def get_logs(self, *args) -> dict[str, Any]:
        self.log_reads.append(args)
        return {"logs": []}


class _Scheduler:
    def __init__(
        self,
        *,
        trigger_result: bool = True,
        cancel_result: bool = True,
        execution_active: bool = False,
        trigger_error: Exception | None = None,
        on_trigger=None,
        on_cancel=None,
    ) -> None:
        self.trigger_result = trigger_result
        self.cancel_result = cancel_result
        self.execution_active = execution_active
        self.trigger_error = trigger_error
        self.on_trigger = on_trigger
        self.on_cancel = on_cancel
        self.triggered: list[str] = []
        self.cancelled: list[str] = []

    async def trigger_immediate(self, task_id: str) -> bool:
        self.triggered.append(task_id)
        if self.on_trigger is not None:
            self.on_trigger(task_id)
        if self.trigger_error is not None:
            raise self.trigger_error
        return self.trigger_result

    async def cancel_execution(self, task_id: str) -> bool:
        self.cancelled.append(task_id)
        if self.on_cancel is not None:
            self.on_cancel(task_id)
        return self.cancel_result

    def is_execution_active(self, _task_id: str) -> bool:
        return self.execution_active


def _service(task_store: _TaskStore, scheduler: _Scheduler) -> AutoHarnessService:
    service = AutoHarnessService.__new__(AutoHarnessService)
    service._task_store = task_store
    service._scheduler = scheduler
    service._agent = None
    service._stream_event_rail = None
    service._scheduled_task_execution_contexts = {}
    return service


def test_schedule_run_fingerprint_normalizes_intent_and_detects_changes() -> None:
    baseline = _build_schedule_run_fingerprint(
        "任务\r\n目标",
        "extended_evolve_pipeline",
        "demo-model",
        _EXECUTION_TARGET,
    )
    assert baseline == _build_schedule_run_fingerprint(
        " 任务\n目标 ",
        " extended_evolve_pipeline ",
        " demo-model ",
        {**_EXECUTION_TARGET, "project_dir": "D:\\work\\project-a"},
    )
    assert baseline != _build_schedule_run_fingerprint(
        "不同任务",
        "extended_evolve_pipeline",
        "demo-model",
        _EXECUTION_TARGET,
    )
    assert baseline != _build_schedule_run_fingerprint(
        "任务\n目标",
        "meta_evolve_pipeline",
        "demo-model",
        _EXECUTION_TARGET,
    )
    assert baseline != _build_schedule_run_fingerprint(
        "任务\n目标",
        "extended_evolve_pipeline",
        "other-model",
        _EXECUTION_TARGET,
    )
    assert baseline != _build_schedule_run_fingerprint(
        "任务\n目标",
        "extended_evolve_pipeline",
        "demo-model",
        {**_EXECUTION_TARGET, "project_dir": "D:/work/project-b"},
    )
    extended = _build_schedule_run_fingerprint(
        "任务\n目标",
        "extended_evolve_pipeline",
        "demo-model",
        _EXECUTION_TARGET,
        {"topic": "demo", "files": ["a.py"]},
        " https://example.test/repo.git ",
    )
    assert extended == _build_schedule_run_fingerprint(
        "任务\n目标",
        "extended_evolve_pipeline",
        "demo-model",
        _EXECUTION_TARGET,
        {"files": ["a.py"], "topic": "demo"},
        "https://example.test/repo.git",
    )
    assert extended != _build_schedule_run_fingerprint(
        "任务\n目标",
        "extended_evolve_pipeline",
        "demo-model",
        _EXECUTION_TARGET,
        {"topic": "changed", "files": ["a.py"]},
        "https://example.test/repo.git",
    )
    assert extended != _build_schedule_run_fingerprint(
        "任务\n目标",
        "extended_evolve_pipeline",
        "demo-model",
        _EXECUTION_TARGET,
        {"topic": "demo", "files": ["a.py"]},
        "https://example.test/other.git",
    )


@pytest.mark.asyncio
async def test_run_task_rejects_empty_query_without_creating_task() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()

    result = await _service(task_store, scheduler).run_task("  \n\t")

    assert result == {"error": "任务内容不能为空"}
    assert task_store.added == []
    assert scheduler.triggered == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "run"])
@pytest.mark.parametrize(
    "invalid_owner_scope",
    [
        None,
        {},
        {"channel_id": "web", "session_id": "", "app_id": "desktop"},
        {"channel_id": "", "session_id": "session-a", "app_id": "desktop"},
    ],
)
async def test_new_task_fails_closed_for_explicit_invalid_owner_scope(
    action: str,
    invalid_owner_scope: Any,
) -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)

    if action == "create":
        result = await service.create_scheduled_task(
            "invalid owner task",
            4,
            owner_scope=invalid_owner_scope,
        )
    else:
        result = await service.run_task(
            "invalid owner task",
            owner_scope=invalid_owner_scope,
        )

    assert result["code"] == "TASK_SCOPE_REQUIRED"
    assert "task_id" not in result
    assert task_store.tasks == {}
    assert task_store.added == []
    assert scheduler.triggered == []


@pytest.mark.asyncio
async def test_run_task_keeps_agent_out_of_serialized_task_data() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    agent = object()

    result = await service.run_task("受控任务", execution_agent=agent)

    task_id = result["task_id"]
    context = service.get_scheduled_task_execution_context(task_id)
    assert context is not None
    assert context.agent is agent
    assert "execution_context" not in task_store.tasks[task_id]
    assert "agent" not in task_store.tasks[task_id]
    json.dumps(task_store.tasks[task_id])


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "run"])
async def test_new_internal_task_is_scoped_and_not_marked_legacy(
    tmp_path,
    action: str,
) -> None:
    task_store = PersistentTaskStore(tmp_path)
    service = _service(task_store, _Scheduler())

    if action == "create":
        created = await service.create_scheduled_task("internal task", 4)
    else:
        created = await service.run_task("internal task")

    raw_task = task_store.get_task(created["task_id"])
    assert raw_task is not None
    owner_scope = raw_task["owner_scope"]
    assert all(owner_scope[field] for field in ("channel_id", "session_id", "app_id"))
    status = await service.get_scheduled_task_status(
        created["task_id"],
        requester_owner_scope=owner_scope,
    )
    assert status["provenance"]["owner_scope"] == owner_scope
    assert status["provenance"]["legacy_unscoped"] is False


@pytest.mark.asyncio
async def test_idempotent_run_concurrency_creates_and_triggers_once(tmp_path) -> None:
    task_store = PersistentTaskStore(tmp_path)
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    releases: list[str] = []

    first, second = await asyncio.gather(
        service.run_task(
            "受控任务",
            execution_agent=object(),
            context_release=lambda: releases.append("first"),
            owner_scope=_OWNER_SCOPE,
            origin_namespace="live_voice",
            idempotency_key="command-1",
            model_intent=" demo-model ",
        ),
        service.run_task(
            "受控任务",
            execution_agent=object(),
            context_release=lambda: releases.append("second"),
            owner_scope=dict(_OWNER_SCOPE),
            origin_namespace=" live_voice ",
            idempotency_key=" command-1 ",
            model_intent="demo-model",
        ),
    )

    assert first["task_id"] == second["task_id"]
    assert sorted([first["idempotent_replay"], second["idempotent_replay"]]) == [
        False,
        True,
    ]
    assert scheduler.triggered == [first["task_id"]]
    assert len(task_store.list_tasks()) == 1
    assert len(service._scheduled_task_execution_contexts) == 1
    assert len(releases) == 1

    reloaded_data = json.loads(
        (tmp_path / "scheduled-tasks.json").read_text(encoding="utf-8")
    )
    assert len(reloaded_data["tasks"]) == 1
    assert len(reloaded_data["create_commands"]) == 1


@pytest.mark.asyncio
async def test_idempotent_run_coordinates_multiple_store_instances_for_same_path(
    tmp_path,
) -> None:
    first_store = PersistentTaskStore(tmp_path)
    second_store = PersistentTaskStore(tmp_path)
    first_scheduler = _Scheduler()
    second_scheduler = _Scheduler()
    first_service = _service(first_store, first_scheduler)
    second_service = _service(second_store, second_scheduler)

    first, second = await asyncio.gather(
        first_service.run_task(
            "multi-store task",
            execution_agent=object(),
            execution_target=_EXECUTION_TARGET,
            owner_scope=_OWNER_SCOPE,
            origin_namespace="live_voice",
            idempotency_key="multi-store-command",
        ),
        second_service.run_task(
            "multi-store task",
            execution_agent=object(),
            execution_target=_EXECUTION_TARGET,
            owner_scope=_OWNER_SCOPE,
            origin_namespace="live_voice",
            idempotency_key="multi-store-command",
        ),
    )

    assert first["task_id"] == second["task_id"]
    assert sorted(
        [first.get("idempotent_replay", False), second.get("idempotent_replay", False)]
    ) == [False, True]
    assert len(first_scheduler.triggered) + len(second_scheduler.triggered) == 1
    persisted = json.loads(
        (tmp_path / "scheduled-tasks.json").read_text(encoding="utf-8")
    )
    assert [task["task_id"] for task in persisted["tasks"]] == [first["task_id"]]
    assert len(persisted["create_commands"]) == 1


@pytest.mark.asyncio
async def test_stale_store_writer_preserves_task_and_idempotency_ledger(
    tmp_path,
) -> None:
    winning_store = PersistentTaskStore(tmp_path)
    stale_store = PersistentTaskStore(tmp_path)
    assert stale_store.list_tasks() == []  # Prime an empty per-instance cache.

    winner = await _service(winning_store, _Scheduler()).run_task(
        "multi-store task",
        execution_agent=object(),
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="stale-writer-command",
    )
    await stale_store.add_task(
        {
            "task_id": "sch_unrelated",
            "query": "unrelated",
            "status": "pending",
            "execution_history": [],
        }
    )

    persisted = json.loads(
        (tmp_path / "scheduled-tasks.json").read_text(encoding="utf-8")
    )
    assert {task["task_id"] for task in persisted["tasks"]} == {
        winner["task_id"],
        "sch_unrelated",
    }
    assert len(persisted["create_commands"]) == 1

    replay_scheduler = _Scheduler()
    replay = await _service(
        PersistentTaskStore(tmp_path),
        replay_scheduler,
    ).run_task(
        "multi-store task",
        execution_agent=object(),
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="stale-writer-command",
    )
    assert replay["task_id"] == winner["task_id"]
    assert replay["idempotent_replay"] is True
    assert replay_scheduler.triggered == []


@pytest.mark.asyncio
async def test_idempotent_run_replays_after_json_reload_without_trigger(tmp_path) -> None:
    first_store = PersistentTaskStore(tmp_path)
    first_scheduler = _Scheduler()
    first_service = _service(first_store, first_scheduler)
    first = await first_service.run_task(
        "任务\r\n目标",
        execution_agent=object(),
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="reload-command",
        model_intent="demo-model",
    )

    replay_store = PersistentTaskStore(tmp_path)
    replay_scheduler = _Scheduler()
    replay_service = _service(replay_store, replay_scheduler)
    released: list[str] = []
    replay = await replay_service.run_task(
        "任务\n目标",
        execution_agent=object(),
        context_release=lambda: released.append("candidate"),
        owner_scope=dict(_OWNER_SCOPE),
        origin_namespace="live_voice",
        idempotency_key="reload-command",
        model_intent=" demo-model ",
    )

    assert replay["task_id"] == first["task_id"]
    assert replay["idempotent_replay"] is True
    assert replay_scheduler.triggered == []
    assert released == ["candidate"]
    assert replay_service._scheduled_task_execution_contexts == {}


@pytest.mark.asyncio
async def test_idempotency_conflict_releases_candidate_without_overwriting_winner(
    tmp_path,
) -> None:
    task_store = PersistentTaskStore(tmp_path)
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    winner_agent = object()
    loser_releases: list[str] = []
    winner = await service.run_task(
        "任务 A",
        execution_agent=winner_agent,
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="shared-command",
        model_intent="model-a",
    )

    conflict = await service.run_task(
        "任务 B",
        execution_agent=object(),
        context_release=lambda: loser_releases.append("loser"),
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="shared-command",
        model_intent="model-a",
    )

    assert conflict == {
        "error": "idempotency_key 已用于不同的任务意图",
        "code": "IDEMPOTENCY_CONFLICT",
        "existing_task_id": winner["task_id"],
        "origin_namespace": "live_voice",
    }
    assert "task_id" not in conflict
    assert scheduler.triggered == [winner["task_id"]]
    assert loser_releases == ["loser"]
    winner_context = service.get_scheduled_task_execution_context(winner["task_id"])
    assert winner_context is not None
    assert winner_context.agent is winner_agent


@pytest.mark.asyncio
async def test_same_idempotency_key_and_query_conflict_when_target_changes(
    tmp_path,
) -> None:
    task_store = PersistentTaskStore(tmp_path)
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    target_b = {
        **_EXECUTION_TARGET,
        "project_dir": "D:/work/project-b",
        "project_id": "project-b",
    }
    winner = await service.run_task(
        "相同任务",
        execution_agent=object(),
        execution_target=_EXECUTION_TARGET,
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="target-command",
        model_intent="model-a",
    )

    conflict = await service.run_task(
        "相同任务",
        execution_agent=object(),
        execution_target=target_b,
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="target-command",
        model_intent="model-a",
    )

    assert conflict["code"] == "IDEMPOTENCY_CONFLICT"
    assert conflict["existing_task_id"] == winner["task_id"]
    assert "task_id" not in conflict
    assert scheduler.triggered == [winner["task_id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("winner_extra", "conflict_extra"),
    [
        (
            {"repo_url": "https://example.test/repo-a.git"},
            {"repo_url": "https://example.test/repo-b.git"},
        ),
        (
            {"optimization_task": {"topic": "task-a", "files": ["a.py"]}},
            {"optimization_task": {"topic": "task-b", "files": ["a.py"]}},
        ),
    ],
)
async def test_same_idempotency_key_conflicts_when_execution_inputs_change(
    tmp_path,
    winner_extra: dict[str, Any],
    conflict_extra: dict[str, Any],
) -> None:
    task_store = PersistentTaskStore(tmp_path)
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    winner = await service.run_task(
        "same task",
        execution_agent=object(),
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="execution-input-command",
        **winner_extra,
    )

    conflict = await service.run_task(
        "same task",
        execution_agent=object(),
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="execution-input-command",
        **conflict_extra,
    )

    assert conflict["code"] == "IDEMPOTENCY_CONFLICT"
    assert conflict["existing_task_id"] == winner["task_id"]
    assert scheduler.triggered == [winner["task_id"]]


@pytest.mark.asyncio
async def test_task_provenance_survives_reload_list_status_and_replay(tmp_path) -> None:
    task_store = PersistentTaskStore(tmp_path)
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    created = await service.run_task(
        "受控任务",
        execution_agent=object(),
        execution_target=_EXECUTION_TARGET,
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="persisted-command",
    )

    reloaded_store = PersistentTaskStore(tmp_path)
    raw_task = reloaded_store.get_task(created["task_id"])
    assert raw_task is not None
    assert raw_task["owner_scope"] == _OWNER_SCOPE
    assert raw_task["origin_namespace"] == "live_voice"
    assert raw_task["idempotency_key"] == "persisted-command"
    assert raw_task["execution_target"] == _EXECUTION_TARGET

    reloaded_service = _service(reloaded_store, _Scheduler())
    status = await reloaded_service.get_scheduled_task_status(
        created["task_id"],
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=_EXECUTION_TARGET,
    )
    listed = await reloaded_service.list_scheduled_tasks(
        owner_scope=_OWNER_SCOPE,
        requester_execution_target=_EXECUTION_TARGET,
        origin_namespace="live_voice",
        idempotency_key="persisted-command",
    )
    replay = await reloaded_service.run_task(
        "受控任务",
        execution_agent=object(),
        execution_target=_EXECUTION_TARGET,
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="persisted-command",
    )

    for projection in (status, listed[0], replay):
        assert projection["execution_target"] == _EXECUTION_TARGET
        assert projection["provenance"]["owner_scope"] == _OWNER_SCOPE
        assert projection["provenance"]["origin_namespace"] == "live_voice"
        assert (
            projection["provenance"]["idempotency_key"]
            == "persisted-command"
        )
        assert projection["provenance"]["legacy_unscoped"] is False
    assert replay["task_id"] == created["task_id"]
    assert replay["idempotent_replay"] is True
    cancelled = await reloaded_service.cancel_scheduled_task(
        created["task_id"],
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=_EXECUTION_TARGET,
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["execution_target"] == _EXECUTION_TARGET
    assert cancelled["provenance"]["owner_scope"] == _OWNER_SCOPE


@pytest.mark.asyncio
async def test_idempotency_ledger_tombstone_blocks_recreation_after_delete(
    tmp_path,
) -> None:
    task_store = PersistentTaskStore(tmp_path)
    first_service = _service(task_store, _Scheduler())
    first = await first_service.run_task(
        "受控任务",
        execution_agent=object(),
        execution_target=_EXECUTION_TARGET,
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="deleted-command",
    )
    assert await task_store.delete_task(first["task_id"]) is True

    replay_store = PersistentTaskStore(tmp_path)
    replay_scheduler = _Scheduler()
    replay = await _service(replay_store, replay_scheduler).run_task(
        "受控任务",
        execution_agent=object(),
        execution_target=_EXECUTION_TARGET,
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="deleted-command",
    )

    assert replay["task_id"] == first["task_id"]
    assert replay["status"] == "deleted"
    assert replay["idempotent_replay"] is True
    assert replay["deleted_at"]
    assert replay["execution_target"] == _EXECUTION_TARGET
    assert replay["provenance"] == {
        "owner_scope": _OWNER_SCOPE,
        "origin_namespace": "live_voice",
        "idempotency_key": "deleted-command",
        "legacy_unscoped": False,
        "access": "authorized",
    }
    assert replay_scheduler.triggered == []
    persisted = json.loads(
        (tmp_path / "scheduled-tasks.json").read_text(encoding="utf-8")
    )
    assert persisted["tasks"] == []
    assert persisted["create_commands"][0]["deleted_at"]
    assert persisted["create_commands"][0]["execution_target"] == _EXECUTION_TARGET


@pytest.mark.asyncio
async def test_scoped_list_filters_exact_owner_namespace_and_key(tmp_path) -> None:
    task_store = PersistentTaskStore(tmp_path)
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    owner_b = {**_OWNER_SCOPE, "session_id": "session-b"}

    task_a = await service.run_task(
        "任务 A",
        execution_agent=object(),
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="command-a",
    )
    await service.run_task(
        "任务 B",
        execution_agent=object(),
        owner_scope=owner_b,
        origin_namespace="live_voice",
        idempotency_key="command-a",
    )
    await service.run_task(
        "任务 C",
        execution_agent=object(),
        owner_scope=_OWNER_SCOPE,
        origin_namespace="other",
        idempotency_key="command-c",
    )

    exact = await service.list_scheduled_tasks(
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
        idempotency_key="command-a",
    )
    namespace = await service.list_scheduled_tasks(
        owner_scope=_OWNER_SCOPE,
        origin_namespace="live_voice",
    )

    assert [task["task_id"] for task in exact] == [task_a["task_id"]]
    assert [task["task_id"] for task in namespace] == [task_a["task_id"]]
    assert "session-b" not in json.dumps(exact, ensure_ascii=False)


@pytest.mark.asyncio
async def test_task_context_release_callback_is_idempotent() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    released: list[str] = []

    result = await service.create_scheduled_task(
        "受控任务",
        4,
        execution_agent=object(),
        context_release=lambda: released.append("released"),
    )

    service.release_scheduled_task_execution_context(result["task_id"])
    service.release_scheduled_task_execution_context(result["task_id"])

    assert released == ["released"]


@pytest.mark.asyncio
async def test_stop_scheduler_releases_all_task_contexts() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()
    scheduler.stopped = False

    async def stop() -> None:
        scheduler.stopped = True

    scheduler.stop = stop
    service = _service(task_store, scheduler)
    released: list[str] = []
    for task_id in ("sch_a", "sch_b"):
        service._bind_scheduled_task_execution_context(
            task_id,
            ScheduledTaskExecutionContext(
                object(),
                object(),
                lambda current_id=task_id: released.append(current_id),
            ),
        )

    await service.stop_scheduler()

    assert scheduler.stopped is True
    assert sorted(released) == ["sch_a", "sch_b"]
    assert service._scheduled_task_execution_contexts == {}


@pytest.mark.asyncio
async def test_run_task_reports_failure_when_immediate_trigger_is_rejected() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler(trigger_result=False)

    result = await _service(task_store, scheduler).run_task(" 受控任务 ")

    task_id = result["task_id"]
    assert result == {
        "error": "一次性任务启动失败",
        "task_id": task_id,
        "status": "failed",
        "execution_target": _UNKNOWN_EXECUTION_TARGET,
    }
    assert scheduler.triggered == [task_id]
    assert task_store.tasks[task_id]["query"] == "受控任务"
    assert task_store.tasks[task_id]["status"] == "failed"
    assert task_store.tasks[task_id]["last_error"] == "一次性任务启动失败"
    assert task_store.tasks[task_id]["completed_at"]


@pytest.mark.asyncio
async def test_run_task_trigger_exception_fails_task_and_releases_owned_context() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler(trigger_error=RuntimeError("trigger exploded"))
    service = _service(task_store, scheduler)
    releases: list[str] = []

    result = await service.run_task(
        "受控任务",
        execution_agent=object(),
        context_release=lambda: releases.append("released"),
    )

    task_id = result["task_id"]
    assert result == {
        "error": "一次性任务启动异常: trigger exploded",
        "task_id": task_id,
        "status": "failed",
        "execution_target": _UNKNOWN_EXECUTION_TARGET,
    }
    assert task_store.tasks[task_id]["status"] == "failed"
    assert task_store.tasks[task_id]["current_execution_id"] is None
    assert releases == ["released"]
    assert service._scheduled_task_execution_contexts == {}


@pytest.mark.asyncio
async def test_run_task_trigger_exception_preserves_context_after_scheduler_claim() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler(
        trigger_error=RuntimeError("late trigger error"),
        execution_active=True,
    )
    service = _service(task_store, scheduler)
    releases: list[str] = []

    result = await service.run_task(
        "受控任务",
        execution_agent=object(),
        context_release=lambda: releases.append("released"),
    )

    assert result["status"] == "pending"
    assert result["message"] == "一次性任务已由调度器接管"
    assert releases == []
    assert service.get_scheduled_task_execution_context(result["task_id"]) is not None


@pytest.mark.asyncio
async def test_recurring_trigger_exception_keeps_pending_task_and_context() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler(trigger_error=RuntimeError("trigger exploded"))
    service = _service(task_store, scheduler)
    releases: list[str] = []

    result = await service.create_scheduled_task(
        "受控任务",
        4,
        run_immediately=True,
        execution_agent=object(),
        context_release=lambda: releases.append("released"),
    )

    task_id = result["task_id"]
    assert result["status"] == "pending"
    assert "立即启动失败" in result["warning"]
    assert task_store.tasks[task_id]["status"] == "pending"
    assert releases == []
    assert service.get_scheduled_task_execution_context(task_id) is not None


@pytest.mark.asyncio
async def test_run_task_start_failure_survives_task_store_reload(tmp_path) -> None:
    task_store = PersistentTaskStore(tmp_path)
    scheduler = _Scheduler(trigger_result=False)

    result = await _service(task_store, scheduler).run_task("受控任务")

    reloaded = PersistentTaskStore(tmp_path).get_task(result["task_id"])
    assert reloaded is not None
    assert reloaded["status"] == "failed"
    assert reloaded["last_error"] == "一次性任务启动失败"
    assert reloaded["completed_at"]


@pytest.mark.asyncio
async def test_run_task_does_not_fail_task_claimed_by_schedule_loop() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler(trigger_result=False, execution_active=True)

    result = await _service(task_store, scheduler).run_task("受控任务")

    task_id = result["task_id"]
    assert result == {
        "task_id": task_id,
        "status": "pending",
        "message": "一次性任务已由调度器接管",
        "execution_target": _UNKNOWN_EXECUTION_TARGET,
    }
    assert task_store.tasks[task_id]["status"] == "pending"
    assert task_store.updates == []


@pytest.mark.asyncio
async def test_run_task_preserves_status_changed_while_trigger_was_rejected() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler(
        trigger_result=False,
        on_trigger=lambda task_id: task_store.tasks[task_id].update(status="running"),
    )

    result = await _service(task_store, scheduler).run_task("受控任务")

    task_id = result["task_id"]
    assert result["status"] == "running"
    assert task_store.tasks[task_id]["status"] == "running"
    assert task_store.updates == []


@pytest.mark.asyncio
async def test_run_task_reports_fast_failure_instead_of_claim_success() -> None:
    task_store = _TaskStore()

    def fail_task(task_id: str) -> None:
        task_store.tasks[task_id].update(
            status="failed",
            execution_history=[{"execution_id": "exec_fast", "error": "真实执行失败"}],
        )

    scheduler = _Scheduler(trigger_result=False, on_trigger=fail_task)

    result = await _service(task_store, scheduler).run_task("受控任务")

    assert result == {
        "error": "真实执行失败",
        "task_id": result["task_id"],
        "status": "failed",
        "execution_target": _UNKNOWN_EXECUTION_TARGET,
    }


@pytest.mark.asyncio
async def test_run_task_reports_fast_cancellation_instead_of_claim_success() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler(
        trigger_result=False,
        on_trigger=lambda task_id: task_store.tasks[task_id].update(status="cancelled"),
    )

    result = await _service(task_store, scheduler).run_task("受控任务")

    assert result == {
        "error": "一次性任务已取消",
        "task_id": result["task_id"],
        "status": "cancelled",
        "execution_target": _UNKNOWN_EXECUTION_TARGET,
    }


@pytest.mark.asyncio
async def test_run_task_reports_fast_success_as_completed() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler(
        trigger_result=False,
        on_trigger=lambda task_id: task_store.tasks[task_id].update(status="success"),
    )

    result = await _service(task_store, scheduler).run_task("受控任务")

    assert result == {
        "task_id": result["task_id"],
        "status": "success",
        "message": "一次性任务已结束",
        "execution_target": _UNKNOWN_EXECUTION_TARGET,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "run"])
async def test_schedule_mutation_persists_execution_target_across_json_reload(
    tmp_path,
    action: str,
) -> None:
    task_store = PersistentTaskStore(tmp_path)
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)

    if action == "create":
        result = await service.create_scheduled_task(
            "受控任务",
            4,
            execution_target=_EXECUTION_TARGET,
        )
    else:
        result = await service.run_task(
            "受控任务",
            execution_target=_EXECUTION_TARGET,
        )

    reloaded = PersistentTaskStore(tmp_path).get_task(result["task_id"])
    assert result["execution_target"] == _EXECUTION_TARGET
    assert reloaded is not None
    assert reloaded["execution_target"] == _EXECUTION_TARGET
    json.dumps(reloaded)


@pytest.mark.asyncio
async def test_legacy_task_status_and_list_show_unknown_execution_target(
    tmp_path,
) -> None:
    task_store = PersistentTaskStore(tmp_path)
    await task_store.add_task(
        {
            "task_id": "sch_legacy",
            "query": "旧任务",
            "status": "pending",
            "execution_history": [],
        }
    )
    service = _service(task_store, _Scheduler())

    status = await service.get_scheduled_task_status("sch_legacy")
    tasks = await service.list_scheduled_tasks()

    assert status is not None
    assert status["execution_target"] == _UNKNOWN_EXECUTION_TARGET
    assert tasks[0]["execution_target"] == _UNKNOWN_EXECUTION_TARGET
    assert status["provenance"]["legacy_unscoped"] is True
    assert status["provenance"]["owner_scope"]["session_id"] == "unknown"
    assert tasks[0]["provenance"]["legacy_unscoped"] is True
    assert "execution_target" not in PersistentTaskStore(tmp_path).get_task(
        "sch_legacy"
    )


@pytest.mark.asyncio
async def test_wrong_owner_status_and_cancel_are_side_effect_free() -> None:
    task_id = "sch_scoped"
    task_store = _TaskStore(
        [
            {
                "task_id": task_id,
                "status": "pending",
                "owner_scope": _OWNER_SCOPE,
                "origin_namespace": "live_voice",
                "idempotency_key": "command-a",
                "execution_target": _EXECUTION_TARGET,
            }
        ]
    )
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    context = ScheduledTaskExecutionContext(object(), object())
    service._bind_scheduled_task_execution_context(task_id, context)
    wrong_owner = {**_OWNER_SCOPE, "session_id": "session-b"}

    status = await service.get_scheduled_task_status(
        task_id,
        requester_owner_scope=wrong_owner,
        requester_execution_target=_EXECUTION_TARGET,
    )
    cancel = await service.cancel_scheduled_task(
        task_id,
        requester_owner_scope=wrong_owner,
        requester_execution_target=_EXECUTION_TARGET,
    )
    logs = await service.get_scheduled_task_logs(
        task_id,
        requester_owner_scope=wrong_owner,
        requester_execution_target=_EXECUTION_TARGET,
    )
    delete = await service.delete_scheduled_task(
        task_id,
        requester_owner_scope=wrong_owner,
        requester_execution_target=_EXECUTION_TARGET,
    )

    for result in (status, cancel, logs, delete):
        assert result["code"] == "TASK_SCOPE_MISMATCH"
        assert result["execution_target"] == _UNKNOWN_EXECUTION_TARGET
        assert result["provenance"]["access"] == "denied"
        assert result["provenance"]["owner_scope"]["session_id"] == "unknown"
    assert scheduler.cancelled == []
    assert task_store.updates == []
    assert task_store.deleted == []
    assert task_store.log_reads == []
    assert task_store.tasks[task_id]["status"] == "pending"
    assert service.get_scheduled_task_execution_context(task_id) is context


@pytest.mark.asyncio
async def test_wrong_project_status_and_cancel_are_side_effect_free() -> None:
    task_id = "sch_scoped"
    task_store = _TaskStore(
        [
            {
                "task_id": task_id,
                "status": "pending",
                "owner_scope": _OWNER_SCOPE,
                "origin_namespace": "live_voice",
                "idempotency_key": "command-a",
                "execution_target": _EXECUTION_TARGET,
            }
        ]
    )
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    context = ScheduledTaskExecutionContext(object(), object())
    service._bind_scheduled_task_execution_context(task_id, context)
    wrong_project = {
        **_EXECUTION_TARGET,
        "project_dir": "D:/work/project-b",
        "project_id": "project-b",
    }

    status = await service.get_scheduled_task_status(
        task_id,
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=wrong_project,
    )
    cancel = await service.cancel_scheduled_task(
        task_id,
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=wrong_project,
    )
    logs = await service.get_scheduled_task_logs(
        task_id,
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=wrong_project,
    )
    delete = await service.delete_scheduled_task(
        task_id,
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=wrong_project,
    )

    for result in (status, cancel, logs, delete):
        assert result["code"] == "TASK_PROJECT_MISMATCH"
        assert result["execution_target"] == _EXECUTION_TARGET
        assert result["provenance"]["owner_scope"] == _OWNER_SCOPE
        assert result["provenance"]["access"] == "denied"
    assert scheduler.cancelled == []
    assert task_store.updates == []
    assert task_store.deleted == []
    assert task_store.log_reads == []
    assert task_store.tasks[task_id]["status"] == "pending"
    assert service.get_scheduled_task_execution_context(task_id) is context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_provided", "requester_target"),
    [
        (False, None),
        (True, None),
        (True, {}),
        (
            True,
            {
                **_EXECUTION_TARGET,
                "project_dir": "D:/work/project-b",
                "project_id": "project-b",
            },
        ),
    ],
    ids=["missing", "none", "invalid", "wrong-project"],
)
async def test_list_scheduled_tasks_filters_project_before_progress_read(
    tmp_path,
    monkeypatch,
    target_provided: bool,
    requester_target: Any,
) -> None:
    task_store = PersistentTaskStore(tmp_path)
    await task_store.add_task(
        {
            "task_id": "sch_scoped",
            "status": "pending",
            "owner_scope": _OWNER_SCOPE,
            "execution_target": _EXECUTION_TARGET,
            "execution_history": [],
        }
    )

    progress_reads: list[str] = []

    async def observe_progress_read(task: dict[str, Any]) -> dict[str, Any]:
        progress_reads.append(str(task.get("task_id") or ""))
        return {}

    monkeypatch.setattr(
        task_store,
        "summarize_task_progress",
        observe_progress_read,
    )
    kwargs: dict[str, Any] = {"owner_scope": _OWNER_SCOPE}
    if target_provided:
        kwargs["requester_execution_target"] = requester_target

    listed = await _service(task_store, _Scheduler()).list_scheduled_tasks(
        **kwargs,
    )

    assert listed == []
    assert progress_reads == []


@pytest.mark.asyncio
async def test_legacy_unscoped_task_rejects_external_scope_before_side_effects(
    tmp_path,
) -> None:
    task_id = "sch_legacy"
    task_store = PersistentTaskStore(tmp_path)
    await task_store.add_task({"task_id": task_id, "status": "pending"})
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)

    status = await service.get_scheduled_task_status(
        task_id,
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=_EXECUTION_TARGET,
    )
    cancel = await service.cancel_scheduled_task(
        task_id,
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=_EXECUTION_TARGET,
    )
    logs = await service.get_scheduled_task_logs(
        task_id,
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=_EXECUTION_TARGET,
    )
    delete = await service.delete_scheduled_task(
        task_id,
        requester_owner_scope=_OWNER_SCOPE,
        requester_execution_target=_EXECUTION_TARGET,
    )
    listed = await service.list_scheduled_tasks(owner_scope=_OWNER_SCOPE)

    for result in (status, cancel, logs, delete):
        assert result["code"] == "TASK_SCOPE_MISMATCH"
        assert result["provenance"]["legacy_unscoped"] is True
        assert result["provenance"]["access"] == "denied"
    assert listed == []
    assert scheduler.cancelled == []
    assert task_store.get_task(task_id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_scope", [None, {}])
async def test_list_scheduled_tasks_rejects_explicit_invalid_external_scope(
    invalid_scope: Any,
) -> None:
    service = _service(_TaskStore(), _Scheduler())

    with pytest.raises(ValueError, match="TASK_SCOPE_REQUIRED"):
        await service.list_scheduled_tasks(owner_scope=invalid_scope)


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["unknown_pipeline", 123, object()])
async def test_run_task_rejects_invalid_pipeline_without_creating_task(
    pipeline: Any,
) -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()

    result = await _service(task_store, scheduler).run_task(
        "受控任务", pipeline=pipeline
    )

    assert result == {"error": "任务流水线无效"}
    assert task_store.added == []
    assert scheduler.triggered == []


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "  \n", None, 123])
async def test_create_scheduled_task_rejects_empty_query(query: Any) -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()

    result = await _service(task_store, scheduler).create_scheduled_task(query, 4)

    assert result == {"error": "任务内容不能为空"}
    assert task_store.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interval_hours",
    [
        0,
        -1,
        float("nan"),
        float("inf"),
        float("-inf"),
        1e308,
        10**1000,
        True,
        "4",
    ],
)
async def test_create_scheduled_task_rejects_non_positive_or_non_finite_interval(
    interval_hours: Any,
) -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()

    result = await _service(task_store, scheduler).create_scheduled_task(
        "受控任务",
        interval_hours,
    )

    assert result == {"error": "执行间隔必须是有限正数"}
    assert task_store.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["unknown_pipeline", 123])
async def test_create_scheduled_task_rejects_invalid_pipeline(pipeline: Any) -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()

    result = await _service(task_store, scheduler).create_scheduled_task(
        "受控任务",
        4,
        pipeline=pipeline,
    )

    assert result == {"error": "任务流水线无效"}
    assert task_store.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pipeline", ["extended_evolve_pipeline", "meta_evolve_pipeline"]
)
async def test_create_scheduled_task_normalizes_valid_input(pipeline: str) -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()

    result = await _service(task_store, scheduler).create_scheduled_task(
        " 受控任务 ",
        0.5,
        pipeline=f" {pipeline} ",
    )

    task = task_store.tasks[result["task_id"]]
    assert task["query"] == "受控任务"
    assert task["interval_hours"] == 0.5
    assert task["pipeline"] == pipeline


@pytest.mark.asyncio
async def test_cancel_scheduled_task_rejects_unknown_task_id() -> None:
    task_store = _TaskStore()
    scheduler = _Scheduler()

    result = await _service(task_store, scheduler).cancel_scheduled_task("sch_missing")

    assert result["error"] == "任务不存在"
    assert result["task_id"] == "sch_missing"
    _assert_unknown_response_metadata(
        result,
        access="unknown",
        legacy_unscoped=False,
    )
    assert scheduler.cancelled == []
    assert task_store.updates == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", _PROTOCOL_TERMINAL_STATUSES)
async def test_cancel_scheduled_task_does_not_overwrite_terminal_status(
    status: str,
) -> None:
    task_id = "sch_terminal"
    task_store = _TaskStore([{"task_id": task_id, "status": status}])
    scheduler = _Scheduler()

    result = await _service(task_store, scheduler).cancel_scheduled_task(task_id)

    assert result["task_id"] == task_id
    assert result["status"] == status
    assert ("error" not in result) is (status == "cancelled")
    _assert_unknown_response_metadata(result)
    assert task_store.tasks[task_id]["status"] == status
    assert scheduler.cancelled == []
    assert task_store.updates == []


def test_schedule_protocol_terminal_statuses_match_backend_definition() -> None:
    assert TERMINAL_STATUSES == set(_PROTOCOL_TERMINAL_STATUSES)


@pytest.mark.asyncio
async def test_cancel_scheduled_task_cancels_non_terminal_task() -> None:
    task_id = "sch_pending"
    task_store = _TaskStore([{"task_id": task_id, "status": "pending"}])
    scheduler = _Scheduler()
    service = _service(task_store, scheduler)
    service._bind_scheduled_task_execution_context(
        task_id,
        ScheduledTaskExecutionContext(object(), object()),
    )

    result = await service.cancel_scheduled_task(task_id)

    assert result["task_id"] == task_id
    assert result["status"] == "cancelled"
    _assert_unknown_response_metadata(result)
    assert scheduler.cancelled == [task_id]
    assert task_store.tasks[task_id]["status"] == "cancelled"
    assert service.get_scheduled_task_execution_context(task_id) is None


@pytest.mark.asyncio
async def test_cancel_scheduled_task_preserves_success_that_wins_cancel_race() -> None:
    task_id = "sch_running"
    task_store = _TaskStore([{"task_id": task_id, "status": "running"}])
    scheduler = _Scheduler(
        cancel_result=False,
        on_cancel=lambda current_id: task_store.tasks[current_id].update(
            status="success"
        ),
    )

    result = await _service(task_store, scheduler).cancel_scheduled_task(task_id)

    assert result["error"] == "任务已结束，无法取消"
    assert result["task_id"] == task_id
    assert result["status"] == "success"
    _assert_unknown_response_metadata(result)
    assert task_store.tasks[task_id]["status"] == "success"
    assert task_store.updates == []


@pytest.mark.asyncio
async def test_cancel_scheduled_task_does_not_claim_cancel_when_running_execution_is_missing() -> (
    None
):
    task_id = "sch_running"
    task_store = _TaskStore([{"task_id": task_id, "status": "running"}])
    scheduler = _Scheduler(cancel_result=False)

    result = await _service(task_store, scheduler).cancel_scheduled_task(task_id)

    assert result["error"] == "任务仍在运行，取消未生效"
    assert result["task_id"] == task_id
    assert result["status"] == "running"
    _assert_unknown_response_metadata(result)
    assert task_store.tasks[task_id]["status"] == "running"
    assert task_store.updates == []


@pytest.mark.asyncio
async def test_delete_scheduled_task_always_cancels_pending_claim_before_delete() -> (
    None
):
    task_id = "sch_pending"
    task_store = _TaskStore([{"task_id": task_id, "status": "pending"}])
    scheduler = _Scheduler(cancel_result=True)
    service = _service(task_store, scheduler)
    service._bind_scheduled_task_execution_context(
        task_id,
        ScheduledTaskExecutionContext(object(), object()),
    )

    result = await service.delete_scheduled_task(task_id)

    assert result == {"task_id": task_id}
    assert scheduler.cancelled == [task_id]
    assert task_store.deleted == [task_id]
    assert service.get_scheduled_task_execution_context(task_id) is None


@pytest.mark.asyncio
async def test_delete_scheduled_task_preserves_running_task_when_cancel_did_not_take_effect() -> (
    None
):
    task_id = "sch_running"
    task_store = _TaskStore([{"task_id": task_id, "status": "running"}])
    scheduler = _Scheduler(cancel_result=False)

    result = await _service(task_store, scheduler).delete_scheduled_task(task_id)

    assert result == {
        "error": "任务仍在运行，无法安全删除",
        "task_id": task_id,
        "status": "running",
    }
    assert scheduler.cancelled == [task_id]
    assert task_store.deleted == []


class _SchedulerService:
    def __init__(self) -> None:
        self.cancelled_sessions: list[str] = []

    def cancel_session_run(self, session_id: str) -> None:
        self.cancelled_sessions.append(session_id)


class _BoundExecutionService(_SchedulerService):
    def __init__(
        self,
        contexts: dict[str, ScheduledTaskExecutionContext],
        *,
        expected_starts: int = 2,
    ) -> None:
        super().__init__()
        self._contexts = contexts
        self._expected_starts = expected_starts
        self.mutable_agent: Any = None
        self.started: list[tuple[str, Any, Any]] = []
        self.released: list[str] = []
        self._both_started = asyncio.Event()

    def get_scheduled_task_execution_context(
        self,
        task_id: str,
    ) -> ScheduledTaskExecutionContext | None:
        return self._contexts.get(task_id)

    def release_scheduled_task_execution_context(self, task_id: str) -> None:
        self.released.append(task_id)
        self._contexts.pop(task_id, None)

    async def run(
        self,
        request,
        _session_id: str,
        _request_id: str,
        *,
        execution_agent: Any,
        stream_event_rail: Any,
        **_kwargs,
    ):
        self.started.append((request.session_id, execution_agent, stream_event_rail))
        if len(self.started) >= self._expected_starts:
            self._both_started.set()
        await self._both_started.wait()
        yield AgentResponseChunk(
            request_id=request.request_id,
            channel_id=request.channel_id,
            payload={
                "event_type": "harness.session_finished",
                "is_terminal": True,
            },
            is_complete=False,
        )


@pytest.mark.asyncio
async def test_concurrent_session_tasks_use_their_own_bound_agents(tmp_path) -> None:
    task_store = PersistentTaskStore(tmp_path)
    task_a = {
        "task_id": "sch_session_a",
        "query": "任务 A",
        "interval_hours": 0,
        "is_one_time": True,
        "status": "pending",
        "execution_history": [],
    }
    task_b = {
        "task_id": "sch_session_b",
        "query": "任务 B",
        "interval_hours": 0,
        "is_one_time": True,
        "status": "pending",
        "execution_history": [],
    }
    await task_store.add_task(task_a)
    await task_store.add_task(task_b)
    agent_a = object()
    agent_b = object()
    rail_a = object()
    rail_b = object()
    service = _BoundExecutionService(
        {
            task_a["task_id"]: ScheduledTaskExecutionContext(agent_a, rail_a),
            task_b["task_id"]: ScheduledTaskExecutionContext(agent_b, rail_b),
        }
    )
    scheduler = Scheduler(service, task_store)
    scheduler._resolve_model = lambda _model_name=None: None

    assert await scheduler.trigger_immediate(task_a["task_id"]) is True
    service.mutable_agent = agent_b
    assert await scheduler.trigger_immediate(task_b["task_id"]) is True
    executions = list(scheduler._running_executions.values())
    await asyncio.gather(*executions)

    assert {
        session_id: (agent, rail) for session_id, agent, rail in service.started
    } == {
        next(item[0] for item in service.started if "sch_session_a" in item[0]): (
            agent_a,
            rail_a,
        ),
        next(item[0] for item in service.started if "sch_session_b" in item[0]): (
            agent_b,
            rail_b,
        ),
    }
    assert sorted(service.released) == ["sch_session_a", "sch_session_b"]
    assert service._contexts == {}


@pytest.mark.asyncio
async def test_recurring_task_retains_one_context_across_executions(tmp_path) -> None:
    task_id = "sch_recurring"
    task_store = PersistentTaskStore(tmp_path)
    await task_store.add_task(
        {
            "task_id": task_id,
            "query": "周期任务",
            "interval_hours": 1,
            "status": "pending",
            "execution_history": [],
            "execution_target": _EXECUTION_TARGET,
        }
    )
    agent = object()
    rail = object()
    context = ScheduledTaskExecutionContext(agent, rail)
    service = _BoundExecutionService(
        {task_id: context},
        expected_starts=1,
    )
    scheduler = Scheduler(service, task_store)
    scheduler._resolve_model = lambda _model_name=None: None

    for _ in range(2):
        assert await scheduler.trigger_immediate(task_id) is True
        execution = scheduler._running_executions[task_id]
        await execution
        assert task_store.get_task(task_id)["status"] == "pending"
        assert task_store.get_task(task_id)["execution_target"] == _EXECUTION_TARGET
        assert service.get_scheduled_task_execution_context(task_id) is context

    assert [(agent_arg, rail_arg) for _, agent_arg, rail_arg in service.started] == [
        (agent, rail),
        (agent, rail),
    ]
    assert service.released == []
    assert PersistentTaskStore(tmp_path).get_task(task_id)["execution_target"] == (
        _EXECUTION_TARGET
    )


@pytest.mark.asyncio
async def test_scheduler_refuses_mutable_agent_fallback_after_context_loss() -> None:
    task_id = "sch_after_restart"
    task_store = _TaskStore(
        [
            {
                "task_id": task_id,
                "query": "受控任务",
                "status": "pending",
            }
        ]
    )
    service = _SchedulerService()
    service._agent = object()
    scheduler = Scheduler(service, task_store)

    execution = asyncio.create_task(
        scheduler._execute_scheduled_task(task_store.tasks[task_id])
    )
    scheduler._running_executions[task_id] = execution
    await execution

    assert task_store.tasks[task_id]["status"] == "failed"
    assert task_store.tasks[task_id]["last_error"] == (
        "任务执行上下文不可用；服务重启后请重新创建任务"
    )
    assert task_id not in scheduler._running_executions


@pytest.mark.asyncio
async def test_scheduler_cancel_execution_preserves_success_that_wins_race() -> None:
    task_id = "sch_running"
    execution_id = "exec_current"
    task_store = _TaskStore(
        [
            {
                "task_id": task_id,
                "status": "running",
                "current_execution_id": execution_id,
                "execution_history": [],
            }
        ]
    )
    scheduler = Scheduler(_SchedulerService(), task_store)

    async def complete_successfully_when_cancelled() -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            task_store.tasks[task_id].update(
                status="success",
                current_execution_id=None,
            )

    execution = asyncio.create_task(complete_successfully_when_cancelled())
    scheduler._running_executions[task_id] = execution
    await asyncio.sleep(0)

    cancelled = await scheduler.cancel_execution(task_id)

    assert cancelled is False
    assert task_store.tasks[task_id]["status"] == "success"
    assert task_store.updates == []


@pytest.mark.asyncio
async def test_scheduler_coalesces_concurrent_cancellations() -> None:
    task_id = "sch_running"
    execution_id = "exec_current"
    task_store = _TaskStore(
        [
            {
                "task_id": task_id,
                "status": "running",
                "current_execution_id": execution_id,
                "execution_history": [],
            }
        ]
    )
    scheduler_service = _SchedulerService()
    scheduler = Scheduler(scheduler_service, task_store)

    async def finish_as_cancelled() -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            await asyncio.sleep(0)
            task_store.tasks[task_id].update(
                status="cancelled",
                current_execution_id=None,
            )

    execution = asyncio.create_task(finish_as_cancelled())
    scheduler._running_executions[task_id] = execution
    await asyncio.sleep(0)

    results = await asyncio.gather(
        scheduler.cancel_execution(task_id),
        scheduler.cancel_execution(task_id),
    )

    assert results == [True, True]
    assert scheduler_service.cancelled_sessions == [f"sched_{task_id}_{execution_id}"]
    assert task_store.tasks[task_id]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_and_delete_share_one_execution_cancellation() -> None:
    task_id = "sch_running"
    execution_id = "exec_current"
    task_store = _TaskStore(
        [
            {
                "task_id": task_id,
                "status": "running",
                "current_execution_id": execution_id,
                "execution_history": [],
            }
        ]
    )
    scheduler_service = _SchedulerService()
    scheduler = Scheduler(scheduler_service, task_store)
    service = _service(task_store, scheduler)

    async def finish_as_cancelled() -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            await asyncio.sleep(0)
            task_store.tasks[task_id].update(
                status="cancelled",
                current_execution_id=None,
            )

    execution = asyncio.create_task(finish_as_cancelled())
    scheduler._running_executions[task_id] = execution
    await asyncio.sleep(0)

    cancel_result, delete_result = await asyncio.gather(
        service.cancel_scheduled_task(task_id),
        service.delete_scheduled_task(task_id),
    )

    assert cancel_result["task_id"] == task_id
    assert cancel_result["status"] == "cancelled"
    _assert_unknown_response_metadata(cancel_result)
    assert delete_result == {"task_id": task_id}
    assert scheduler_service.cancelled_sessions == [f"sched_{task_id}_{execution_id}"]
    assert task_store.deleted == [task_id]


@pytest.mark.asyncio
async def test_scheduler_does_not_execute_task_deleted_after_claim() -> None:
    task_id = "sch_claimed"
    claimed_task = {
        "task_id": task_id,
        "query": "受控任务",
        "status": "pending",
    }
    task_store = _TaskStore([claimed_task])
    scheduler = Scheduler(_SchedulerService(), task_store)
    del task_store.tasks[task_id]

    execution = asyncio.create_task(scheduler._execute_scheduled_task(claimed_task))
    scheduler._running_executions[task_id] = execution
    await execution

    assert task_id not in scheduler._running_executions
    assert task_store.updates == []


@pytest.mark.asyncio
async def test_scheduler_marks_legacy_empty_query_failed_and_discards_claim() -> None:
    task_id = "sch_invalid"
    invalid_task = {
        "task_id": task_id,
        "query": "",
        "status": "pending",
    }
    task_store = _TaskStore([invalid_task])
    scheduler = Scheduler(_SchedulerService(), task_store)

    execution = asyncio.create_task(scheduler._execute_scheduled_task(invalid_task))
    scheduler._running_executions[task_id] = execution
    await execution

    assert task_id not in scheduler._running_executions
    assert task_store.tasks[task_id]["status"] == "failed"
    assert task_store.tasks[task_id]["last_error"] == "任务内容不能为空"


@pytest.mark.asyncio
async def test_task_store_upserts_execution_history_by_execution_id(tmp_path) -> None:
    task_store = PersistentTaskStore(tmp_path)
    task_id = "sch_history"
    await task_store.add_task(
        {
            "task_id": task_id,
            "status": "running",
            "execution_history": [],
        }
    )
    await task_store.add_execution_record(
        task_id,
        {
            "execution_id": "exec_same",
            "started_at": "start",
            "status": "running",
        },
    )
    await task_store.add_execution_record(
        task_id,
        {
            "execution_id": "exec_same",
            "completed_at": "end",
            "status": "cancelled",
        },
    )

    reloaded = PersistentTaskStore(tmp_path).get_task(task_id)
    assert reloaded is not None
    assert reloaded["execution_history"] == [
        {
            "execution_id": "exec_same",
            "started_at": "start",
            "completed_at": "end",
            "status": "cancelled",
        }
    ]


@pytest.mark.asyncio
async def test_task_store_reconciles_restart_orphan_running_as_failed(
    tmp_path,
) -> None:
    task_id = "sch_orphan"
    task_store = PersistentTaskStore(tmp_path)
    await task_store.add_task(
        {
            "task_id": task_id,
            "query": "orphaned task",
            "status": "running",
            "created_at": "2026-08-01T00:00:00+00:00",
            "current_execution_id": "exec_orphan",
            "execution_history": [
                {
                    "execution_id": "exec_orphan",
                    "started_at": "2026-08-01T00:00:01+00:00",
                    "status": "running",
                }
            ],
        }
    )

    corrected = await PersistentTaskStore(tmp_path).reconcile_task_statuses()

    assert corrected == 1
    reloaded = PersistentTaskStore(tmp_path).get_task(task_id)
    assert reloaded is not None
    assert reloaded["status"] == "failed"
    assert reloaded["current_execution_id"] is None
    assert reloaded["last_error"] == "任务执行在服务重启后失去运行上下文"
    assert reloaded["execution_history"][-1]["status"] == "failed"
    assert reloaded["execution_history"][-1]["error"] == reloaded["last_error"]
    assert reloaded["execution_history"][-1]["completed_at"]
