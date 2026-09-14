# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Host Runner -> native Task -> real D2 SQLite journal and project write."""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from jiuwenswarm.runtime.service import AgentRuntime
from jiuwenswarm.runtime import service as runtime_module
from jiuwenswarm.server.runtime.agent_adapter import interface_deep
from jiuwenswarm.server.runtime.formal_tasks.project_code_executor import DirectProjectCodeExecutorAdapter
from openjiuwen.core.application.tasks.persistent_task_core import PersistentTaskCore
from openjiuwen.core.application.tasks.task_store import SqliteTaskStore
from openjiuwen.core.common.task_manager.manager import TaskManager, get_task_manager
from openjiuwen.core.runner import Runner
from tests.unit_tests.live_voice.test_p3_4_durability_runtime import _create_selected_task, _durability_binding
from tests.unit_tests.live_voice.test_persistent_task_core import NOW
from tests.unit_tests.live_voice.test_project_code_executor import _DirectProjectExecutor, _Resolver, _direct_binding, _git_project


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_attempt", [False, True])
async def test_host_native_d2_survives_caller_close_and_honors_cancel_before_apply(
    tmp_path, monkeypatch, cancel_attempt,
):
    runner_module = importlib.import_module("openjiuwen.core.runner.runner")
    isolated = runner_module._RunnerImpl(runner_id="host-formal-owner-probe", config=Runner.get_config())
    monkeypatch.setattr(runner_module, "GLOBAL_RUNNER", isolated)
    monkeypatch.setattr(TaskManager, "_instance", None)
    monkeypatch.setattr(runtime_module, "_initialize_runtime_dependencies", AsyncMock())
    monkeypatch.setattr(interface_deep, "close_persistent_checkpointer", AsyncMock())
    monkeypatch.setattr(AgentRuntime, "_ensure_extensions", AsyncMock())
    monkeypatch.setattr(runtime_module, "_PROCESS_RUNTIME_DEPENDENCY_USERS", 0)
    runtime = AgentRuntime(agent_manager=SimpleNamespace(
        cancel_all_inflight_work=AsyncMock(), cleanup=AsyncMock(), unpin_agent=Mock(),
    ))
    project = tmp_path / "project"
    _git_project(project)
    original = (project / "README.md").read_bytes()
    database = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(database)
    agent = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, agent)), database, durability_store=store,
        task_group_provider=runtime.ensure_background_task_group,
    )
    core = PersistentTaskCore(store, adapter)
    _, task = _create_selected_task(store, core, project, adapter)
    prepared, release = asyncio.Event(), asyncio.Event()
    prepare = adapter._prepare_d2_project_effect

    async def gated_prepare(**kwargs):
        binding = await prepare(**kwargs)
        assert binding is not None  # Actual D2, not the D0 no-op preparation.
        prepared.set()
        await release.wait()
        return binding

    monkeypatch.setattr(adapter, "_prepare_d2_project_effect", gated_prepare)
    try:
        async with get_task_manager().task_group() as caller:
            assert await core.drain_outbox_once(worker_id="host-native-probe", observed_at=NOW)
            await asyncio.wait_for(prepared.wait(), 30)
            native = adapter._running[task.attempt_id]
            assert native.group == "application-project" and native.parent_task_id is None
            assert runtime.get_background_task_group() is isolated.get_root_task_group()
            caller.cancel_scope.cancel()
        assert not native.is_settled
        assert not native.get_cancel_scope().cancel_called
        binding = _durability_binding(store, task.task_id, task.attempt_id)
        assert store.read_durability_checkpoints(binding).head == 1
        assert len(store.read_durability_effects(binding).records) == 2
        assert adapter._journal.get(task.attempt_id).raw_status != "applying"
        if cancel_attempt:
            assert native.abort(reason="controlled_owner_cancel")
        release.set()
        await adapter._wait_workers({native}, timeout=30)
        assert native.is_settled
        await core.reconcile()
        expected = "interrupted" if cancel_attempt else "completed"
        assert adapter._journal.get(task.attempt_id).outcome.value == expected
        assert (project / "result.txt").exists() is not cancel_attempt
        assert (project / "README.md").read_bytes() == original
        assert len(agent.requests) == 1
        if cancel_attempt:
            assert len(store.read_durability_effects(binding).records) == 2
        else:
            assert (project / "result.txt").read_text(encoding="utf-8") == "done"
            assert len(store.read_durability_effects(binding).records) == 5
        await core.reconcile()
        assert len(agent.requests) == 1
    finally:
        release.set()
        await adapter.close()
        await runtime.close()
