# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from jiuwenswarm.server.runtime.agent_adapter import interface as agent_interface
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import (
    JiuWenSwarmDeepAdapter,
)
from jiuwenswarm.server.runtime.agent_manager import AgentManager


class _Agent:
    def __init__(self) -> None:
        self.cleanup_calls = 0
        self.strict_cleanup_calls = 0
        self.cancel_calls = 0
        self.session_runtime = False
        self.strict_cleanup_error: BaseException | None = None

    async def cleanup(self) -> None:
        self.cleanup_calls += 1

    async def cleanup_formal_project_task_agent(self) -> None:
        self.strict_cleanup_calls += 1
        if self.strict_cleanup_error is not None:
            raise self.strict_cleanup_error
        await self.cleanup()
        self.session_runtime = False

    def has_session_runtime(self) -> bool:
        return self.session_runtime

    async def cancel_inflight_work(self, _reason: str) -> None:
        self.cancel_calls += 1


def _fake_agent_create(
    manager: AgentManager,
    agent: _Agent,
    creates: list[dict[str, object]],
):
    async def create(
        agent_key,
        mode="agent",
        config=None,
        sub_mode=None,
        cache_key=None,
    ):
        creates.append(
            {
                "agent_key": agent_key,
                "mode": mode,
                "config": dict(config or {}),
                "sub_mode": sub_mode,
                "cache_key": cache_key,
            }
        )
        manager.agents.setdefault(agent_key, {})[cache_key] = agent
        manager._agent_create_params.setdefault(agent_key, {})[cache_key] = {
            "mode": mode,
            "sub_mode": sub_mode,
            "config": dict(config or {}),
            "cache_key": cache_key,
        }
        return agent

    return create


def _fake_attempt_agent_constructor(
    monkeypatch: pytest.MonkeyPatch,
    agent: _Agent,
    creates: list[dict[str, object]],
) -> None:
    async def create_instance(
        config,
        *,
        mode="agent",
        sub_mode=None,
    ) -> None:
        creates.append(
            {
                "agent_key": "live_voice_formal_task",
                "mode": mode,
                "config": dict(config or {}),
                "sub_mode": sub_mode,
                "cache_key": getattr(agent, "_jiuwenswarm_agent_cache_key"),
            }
        )

    monkeypatch.setattr(agent, "create_instance", create_instance, raising=False)
    monkeypatch.setattr(agent_interface, "JiuWenSwarm", lambda: agent)


@pytest.mark.asyncio
async def test_formal_task_agent_uses_dedicated_clean_profile_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = AgentManager()
    agent = _Agent()
    creates: list[dict[str, object]] = []

    monkeypatch.setattr(
        manager,
        "_create_agent",
        _fake_agent_create(manager, agent, creates),
    )

    first = await manager.get_live_voice_formal_task_agent(str(tmp_path))
    second = await manager.get_live_voice_formal_task_agent(str(tmp_path))

    assert first is agent
    assert second is agent
    assert len(creates) == 1
    assert creates[0]["agent_key"] == "live_voice_formal_task"
    assert creates[0]["mode"] == "code"
    assert creates[0]["config"] == {
        "project_dir": os.path.normcase(str(tmp_path.resolve())),
        "project_clean_runtime_support": True,
    }
    assert "formal_task" in str(creates[0]["cache_key"])

    await manager.cleanup_live_voice_formal_task_agents()
    await manager.cleanup_live_voice_formal_task_agents()

    assert agent.cleanup_calls == 1
    assert "live_voice_formal_task" not in manager.agents


@pytest.mark.asyncio
async def test_gateway_disconnect_never_cancels_formal_task_agent() -> None:
    manager = AgentManager()
    interactive = _Agent()
    formal = _Agent()
    manager.agents = {
        "web": {"agent": interactive},
        "live_voice_formal_task": {"formal": formal},
    }

    await manager.cancel_all_inflight_work("gateway disconnected")

    assert interactive.cancel_calls == 1
    assert formal.cancel_calls == 0


@pytest.mark.asyncio
async def test_attempt_agent_uses_exact_isolated_cache_without_borrower_and_strictly_releases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = AgentManager()
    agent = _Agent()
    creates: list[dict[str, object]] = []
    _fake_attempt_agent_constructor(monkeypatch, agent, creates)
    attempt_root = tmp_path / "attempt-checkout"
    attempt_root.mkdir()

    acquired = await manager.acquire_live_voice_formal_task_attempt_agent(
        str(attempt_root)
    )
    duplicate = await manager.acquire_live_voice_formal_task_attempt_agent(
        str(attempt_root)
    )

    assert acquired is not None
    assert acquired.agent is agent
    assert acquired.initialization_error is None
    assert duplicate is None
    assert len(creates) == 1
    assert creates[0]["agent_key"] == "live_voice_formal_task"
    assert creates[0]["mode"] == "code"
    assert creates[0]["sub_mode"] is None
    assert creates[0]["config"] == {
        "project_dir": os.path.normcase(str(attempt_root.resolve())),
        "project_clean_runtime_support": True,
    }
    cache_key = str(creates[0]["cache_key"])
    assert cache_key == (
        f"code:formal_attempt:{os.path.normcase(str(attempt_root.resolve()))}"
    )
    assert manager.agents["live_voice_formal_task"] == {cache_key: agent}
    assert set(manager._agent_create_params["live_voice_formal_task"]) == {cache_key}
    assert manager._agent_pins == {id(agent): 1}
    assert id(agent) not in manager._agent_borrowers
    agent.session_runtime = True

    released = await manager.release_live_voice_formal_task_attempt_agent(
        str(attempt_root),
        expected_agent=agent,  # type: ignore[arg-type]
    )

    assert released is True
    assert agent.strict_cleanup_calls == 1
    assert agent.cleanup_calls == 1
    assert agent.session_runtime is False
    assert "live_voice_formal_task" not in manager.agents
    assert "live_voice_formal_task" not in manager._agent_create_params
    assert id(agent) not in manager._agent_pins
    assert id(agent) not in manager._agent_borrowers


@pytest.mark.asyncio
async def test_attempt_agent_release_identity_and_borrower_checks_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = AgentManager()
    agent = _Agent()
    imposter = _Agent()
    creates: list[dict[str, object]] = []
    _fake_attempt_agent_constructor(monkeypatch, agent, creates)
    attempt_root = tmp_path / "attempt-checkout"
    attempt_root.mkdir()
    await manager.acquire_live_voice_formal_task_attempt_agent(str(attempt_root))
    cache_key = str(creates[0]["cache_key"])

    wrong_identity = await manager.release_live_voice_formal_task_attempt_agent(
        str(attempt_root),
        expected_agent=imposter,  # type: ignore[arg-type]
    )
    assert wrong_identity is False
    assert manager.agents["live_voice_formal_task"][cache_key] is agent
    assert manager._agent_pins[id(agent)] == 1
    assert agent.strict_cleanup_calls == 0

    borrower = asyncio.current_task()
    assert borrower is not None
    manager._agent_borrowers[id(agent)] = {borrower}
    borrowed = await manager.release_live_voice_formal_task_attempt_agent(
        str(attempt_root),
        expected_agent=agent,  # type: ignore[arg-type]
    )
    assert borrowed is False
    assert manager.agents["live_voice_formal_task"][cache_key] is agent
    assert manager._agent_pins[id(agent)] == 1
    assert agent.strict_cleanup_calls == 0

    manager._agent_borrowers.pop(id(agent))
    assert await manager.release_live_voice_formal_task_attempt_agent(
        str(attempt_root),
        expected_agent=agent,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_attempt_agent_strict_cleanup_failure_restores_exact_cache_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = AgentManager()
    agent = _Agent()
    agent.strict_cleanup_error = RuntimeError("injected strict cleanup failure")
    creates: list[dict[str, object]] = []
    _fake_attempt_agent_constructor(monkeypatch, agent, creates)
    attempt_root = tmp_path / "attempt-checkout"
    attempt_root.mkdir()
    await manager.acquire_live_voice_formal_task_attempt_agent(str(attempt_root))
    cache_key = str(creates[0]["cache_key"])
    create_params = dict(
        manager._agent_create_params["live_voice_formal_task"][cache_key]
    )

    with pytest.raises(RuntimeError, match="injected strict cleanup failure"):
        await manager.release_live_voice_formal_task_attempt_agent(
            str(attempt_root),
            expected_agent=agent,  # type: ignore[arg-type]
        )

    assert manager.agents["live_voice_formal_task"] == {cache_key: agent}
    assert manager._agent_create_params["live_voice_formal_task"] == {
        cache_key: create_params
    }
    assert manager._agent_pins == {id(agent): 1}
    assert id(agent) not in manager._agent_borrowers
    assert agent.strict_cleanup_calls == 1
    assert agent.cleanup_calls == 0

    agent.strict_cleanup_error = None
    assert await manager.release_live_voice_formal_task_attempt_agent(
        str(attempt_root),
        expected_agent=agent,  # type: ignore[arg-type]
    )
    assert agent.strict_cleanup_calls == 2
    assert agent.cleanup_calls == 1


@pytest.mark.asyncio
async def test_attempt_agent_without_formal_cleanup_seam_retains_exact_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LegacyAgent:
        def __init__(self) -> None:
            self.cleanup_calls = 0
            self.hidden_runtime = True

        async def cleanup(self) -> None:
            self.cleanup_calls += 1

        def has_session_runtime(self) -> bool:
            return False

    manager = AgentManager()
    agent = LegacyAgent()
    creates: list[dict[str, object]] = []
    _fake_attempt_agent_constructor(monkeypatch, agent, creates)  # type: ignore[arg-type]
    attempt_root = tmp_path / "attempt-checkout"
    attempt_root.mkdir()
    acquired = await manager.acquire_live_voice_formal_task_attempt_agent(
        str(attempt_root)
    )
    assert acquired is not None
    cache_key = str(creates[0]["cache_key"])

    released = await manager.release_live_voice_formal_task_attempt_agent(
        str(attempt_root),
        expected_agent=agent,  # type: ignore[arg-type]
    )

    assert released is False
    assert agent.cleanup_calls == 0
    assert agent.hidden_runtime is True
    assert manager.agents["live_voice_formal_task"] == {cache_key: agent}
    assert cache_key in manager._agent_create_params["live_voice_formal_task"]
    assert manager._agent_pins == {id(agent): 1}

    with pytest.raises(RuntimeError, match="FORMAL_TASK_AGENT_CLEANUP_PENDING"):
        await manager.cleanup_live_voice_formal_task_agents()

    assert agent.cleanup_calls == 0
    assert manager.agents["live_voice_formal_task"] == {cache_key: agent}
    assert cache_key in manager._agent_create_params["live_voice_formal_task"]
    assert manager._agent_pins == {id(agent): 1}


@pytest.mark.asyncio
async def test_attempt_agent_release_cancellation_retains_exact_cache_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = AgentManager()
    agent = _Agent()
    creates: list[dict[str, object]] = []
    _fake_attempt_agent_constructor(monkeypatch, agent, creates)
    attempt_root = tmp_path / "attempt-checkout"
    attempt_root.mkdir()
    await manager.acquire_live_voice_formal_task_attempt_agent(str(attempt_root))
    cache_key = str(creates[0]["cache_key"])
    create_params = dict(
        manager._agent_create_params["live_voice_formal_task"][cache_key]
    )
    agent.strict_cleanup_error = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await manager.release_live_voice_formal_task_attempt_agent(
            str(attempt_root),
            expected_agent=agent,  # type: ignore[arg-type]
        )

    assert manager.agents["live_voice_formal_task"] == {cache_key: agent}
    assert manager._agent_create_params["live_voice_formal_task"] == {
        cache_key: create_params
    }
    assert manager._agent_pins == {id(agent): 1}
    agent.strict_cleanup_error = None
    assert await manager.release_live_voice_formal_task_attempt_agent(
        str(attempt_root),
        expected_agent=agent,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_channel_cleanup_failure_remains_visible_and_retryable() -> None:
    manager = AgentManager()
    agent = _Agent()
    agent.strict_cleanup_error = RuntimeError("injected channel cleanup failure")
    cache_key = "code:formal_task:project"
    manager.agents = {"live_voice_formal_task": {cache_key: agent}}  # type: ignore[dict-item]
    manager._agent_create_params = {
        "live_voice_formal_task": {cache_key: {"cache_key": cache_key}}
    }

    with pytest.raises(RuntimeError, match="FORMAL_TASK_AGENT_CLEANUP_PENDING"):
        await manager.cleanup_live_voice_formal_task_agents()

    assert manager.agents["live_voice_formal_task"] == {cache_key: agent}
    assert cache_key in manager._agent_create_params["live_voice_formal_task"]
    agent.strict_cleanup_error = None
    await manager.cleanup_live_voice_formal_task_agents()
    assert "live_voice_formal_task" not in manager.agents
    assert "live_voice_formal_task" not in manager._agent_create_params


@pytest.mark.asyncio
async def test_real_facade_strict_cleanup_retains_adapter_until_quiescent() -> None:
    class Sessions:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close_all_sessions(self) -> None:
            self.close_calls += 1

        def has_session_runtime(self, _session_id=None) -> bool:
            return False

    class Adapter:
        def __init__(self) -> None:
            self.runtime = True
            self.cleanup_calls = 0

        async def cleanup_formal_project_task_agent(self) -> None:
            self.cleanup_calls += 1

        def has_session_runtime(self, _session_id=None) -> bool:
            return self.runtime

    facade = object.__new__(JiuWenSwarm)
    sessions = Sessions()
    adapter = Adapter()
    facade._session_manager = sessions
    facade._adapter = adapter

    with pytest.raises(RuntimeError, match="PROJECT_AGENT_CLEANUP_PENDING"):
        await facade.cleanup_formal_project_task_agent()

    assert facade._adapter is adapter
    adapter.runtime = False
    await facade.cleanup_formal_project_task_agent()
    assert facade._adapter is None
    assert adapter.cleanup_calls == 2
    assert sessions.close_calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["runtime_error", "cancelled_error"])
async def test_real_deep_adapter_retains_partial_child_until_strict_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    parent = JiuWenSwarmDeepAdapter()
    child = JiuWenSwarmDeepAdapter()
    child.mark_as_session_scoped("formal-session")
    parent._session_instance_config = {"project_clean_runtime_support": True}

    class Instance:
        async def stop(self) -> None:
            return None

    async def partial_create(*_args, **_kwargs) -> None:
        child._instance = Instance()  # type: ignore[assignment]
        if failure_kind == "runtime_error":
            raise RuntimeError("injected partial initialization")
        raise asyncio.CancelledError()

    monkeypatch.setattr(parent, "_new_session_scoped_adapter", lambda _sid: child)
    monkeypatch.setattr(child, "create_instance", partial_create)

    expected = RuntimeError if failure_kind == "runtime_error" else asyncio.CancelledError
    with pytest.raises(expected):
        await parent._get_or_create_session_adapter("formal-session")

    assert parent._session_adapters == {"formal-session": child}
    assert parent._session_adapter_initializing == {"formal-session"}
    assert parent.has_session_runtime()
    with pytest.raises(RuntimeError, match="SESSION_ADAPTER_INITIALIZATION_PENDING"):
        await parent._get_or_create_session_adapter("formal-session")

    await parent.cleanup_formal_project_task_agent()
    assert parent._session_adapters == {}
    assert parent._session_adapter_initializing == set()
    assert parent.has_session_runtime() is False


@pytest.mark.asyncio
async def test_real_deep_adapter_public_start_preserves_develop_failure_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = JiuWenSwarmDeepAdapter()
    calls: list[tuple[str, bool]] = []

    async def start(*, session_id: str, strict: bool) -> None:
        calls.append((session_id, strict))
        raise RuntimeError("injected interaction startup failure")

    monkeypatch.setattr(adapter, "_start_interaction", start)

    with pytest.raises(RuntimeError, match="injected interaction startup failure"):
        await adapter.start_interaction("ordinary-session")

    assert calls == [("ordinary-session", True)]


@pytest.mark.asyncio
async def test_real_deep_adapter_preserves_public_start_for_nonformal_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = JiuWenSwarmDeepAdapter()
    child = JiuWenSwarmDeepAdapter()
    child.mark_as_session_scoped("ordinary-session")
    parent._session_instance_config = {"project_clean_runtime_support": False}
    calls: list[str] = []

    async def create_instance(*_args, **_kwargs) -> None:
        calls.append("create")

    async def strict_start(*_args, **_kwargs) -> None:
        calls.append("strict")
        raise RuntimeError("strict start must not own ordinary TUI semantics")

    async def public_start(*_args, **_kwargs) -> None:
        calls.append("public")

    monkeypatch.setattr(parent, "_new_session_scoped_adapter", lambda _sid: child)
    monkeypatch.setattr(child, "create_instance", create_instance)
    monkeypatch.setattr(child, "_start_interaction", strict_start)
    monkeypatch.setattr(child, "start_interaction", public_start)

    resolved = await parent._get_or_create_session_adapter("ordinary-session")

    assert resolved is child
    assert calls == ["create", "public"]
    assert parent._session_adapters == {"ordinary-session": child}
    assert parent._session_adapter_initializing == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["runtime_error", "cancelled_error"])
async def test_nonformal_start_failure_cleans_child_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    parent = JiuWenSwarmDeepAdapter()
    failed_child = JiuWenSwarmDeepAdapter()
    failed_child.mark_as_session_scoped("ordinary-session")
    replacement = JiuWenSwarmDeepAdapter()
    replacement.mark_as_session_scoped("ordinary-session")
    parent._session_instance_config = {"project_clean_runtime_support": False}
    children = iter((failed_child, replacement))
    cleanup_calls = 0

    async def create_instance(*_args, **_kwargs) -> None:
        return None

    async def failed_start(*_args, **_kwargs) -> None:
        if failure_kind == "runtime_error":
            raise RuntimeError("injected ordinary start failure")
        raise asyncio.CancelledError()

    async def cleanup() -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1

    async def replacement_start(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(parent, "_new_session_scoped_adapter", lambda _sid: next(children))
    monkeypatch.setattr(failed_child, "create_instance", create_instance)
    monkeypatch.setattr(failed_child, "start_interaction", failed_start)
    monkeypatch.setattr(failed_child, "cleanup", cleanup)
    monkeypatch.setattr(replacement, "create_instance", create_instance)
    monkeypatch.setattr(replacement, "start_interaction", replacement_start)

    expected = RuntimeError if failure_kind == "runtime_error" else asyncio.CancelledError
    with pytest.raises(expected):
        await parent._get_or_create_session_adapter("ordinary-session")

    assert cleanup_calls == 1
    assert parent._session_adapters == {}
    assert parent._session_adapter_initializing == set()
    assert parent._session_adapter_locks == {}
    assert parent.has_session_runtime() is False

    assert await parent._get_or_create_session_adapter("ordinary-session") is replacement


@pytest.mark.asyncio
async def test_nonformal_start_cleanup_failure_retains_exact_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = JiuWenSwarmDeepAdapter()
    child = JiuWenSwarmDeepAdapter()
    child.mark_as_session_scoped("ordinary-session")
    parent._session_instance_config = {"project_clean_runtime_support": False}

    async def create_instance(*_args, **_kwargs) -> None:
        return None

    async def failed_start(*_args, **_kwargs) -> None:
        raise RuntimeError("injected ordinary start failure")

    async def failed_cleanup() -> None:
        raise RuntimeError("injected cleanup failure")

    monkeypatch.setattr(parent, "_new_session_scoped_adapter", lambda _sid: child)
    monkeypatch.setattr(child, "create_instance", create_instance)
    monkeypatch.setattr(child, "start_interaction", failed_start)
    monkeypatch.setattr(child, "cleanup", failed_cleanup)

    with pytest.raises(RuntimeError, match="injected ordinary start failure"):
        await parent._get_or_create_session_adapter("ordinary-session")

    assert parent._session_adapters == {"ordinary-session": child}
    assert parent._session_adapter_initializing == {"ordinary-session"}
    assert parent.has_session_runtime("ordinary-session")


@pytest.mark.asyncio
@pytest.mark.parametrize("strict_failure", ["runtime_error", "missing"])
async def test_real_deep_adapter_formal_start_failure_retains_preannounced_owner(
    monkeypatch: pytest.MonkeyPatch,
    strict_failure: str,
) -> None:
    parent = JiuWenSwarmDeepAdapter()
    child = JiuWenSwarmDeepAdapter()
    child.mark_as_session_scoped("formal-session")
    parent._session_instance_config = {"project_clean_runtime_support": True}
    public_calls = 0

    async def create_instance(*_args, **_kwargs) -> None:
        return None

    async def public_start(*_args, **_kwargs) -> None:
        nonlocal public_calls
        public_calls += 1

    async def strict_start(*_args, **_kwargs) -> None:
        raise RuntimeError("injected strict formal start failure")

    monkeypatch.setattr(parent, "_new_session_scoped_adapter", lambda _sid: child)
    monkeypatch.setattr(child, "create_instance", create_instance)
    monkeypatch.setattr(child, "start_interaction", public_start)
    monkeypatch.setattr(
        child,
        "_start_interaction",
        None if strict_failure == "missing" else strict_start,
    )

    expected = (
        "SESSION_ADAPTER_INITIALIZATION_PENDING"
        if strict_failure == "missing"
        else "injected strict formal start failure"
    )
    with pytest.raises(RuntimeError, match=expected):
        await parent._get_or_create_session_adapter("formal-session")

    assert public_calls == 0
    assert parent._session_adapters == {"formal-session": child}
    assert parent._session_adapter_initializing == {"formal-session"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["runtime_error", "cancelled_error"])
async def test_real_deep_adapter_strict_child_cleanup_failure_retries_exact_owner(
    failure_kind: str,
) -> None:
    parent = JiuWenSwarmDeepAdapter()
    child = JiuWenSwarmDeepAdapter()
    child.mark_as_session_scoped("formal-session")

    class Instance:
        def __init__(self) -> None:
            self.calls = 0

        async def stop(self) -> None:
            self.calls += 1
            if self.calls == 1:
                if failure_kind == "runtime_error":
                    raise RuntimeError("injected cleanup failure")
                raise asyncio.CancelledError()

    instance = Instance()
    child._instance = instance  # type: ignore[assignment]
    parent._session_adapters["formal-session"] = child
    parent._session_adapter_locks["formal-session"] = asyncio.Lock()

    with pytest.raises(RuntimeError, match="PROJECT_AGENT_CLEANUP_PENDING"):
        await parent.cleanup_formal_project_task_agent()

    assert parent._session_adapters == {"formal-session": child}
    assert child._instance is instance
    assert parent.has_session_runtime()

    await parent.cleanup_formal_project_task_agent()
    assert instance.calls == 2
    assert parent._session_adapters == {}
    assert parent.has_session_runtime() is False


@pytest.mark.asyncio
async def test_real_deep_adapter_caller_cancellation_retains_late_cleanup_task() -> None:
    adapter = JiuWenSwarmDeepAdapter()
    adapter.mark_as_session_scoped("formal-session")
    cancellation_observed = asyncio.Event()
    allow_settle = asyncio.Event()

    async def late_work() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellation_observed.set()
            await allow_settle.wait()

    late = asyncio.create_task(late_work())
    adapter._session_agent_tasks["formal-session"] = {late}
    caller = asyncio.create_task(adapter.cleanup_formal_project_task_agent())
    await asyncio.wait_for(cancellation_observed.wait(), timeout=2)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    assert adapter._formal_cleanup_task is not None
    assert not adapter._formal_cleanup_task.done()
    assert adapter.has_session_runtime()
    allow_settle.set()
    await adapter.cleanup_formal_project_task_agent()
    assert late.done()
    assert adapter.has_session_runtime() is False


@pytest.mark.asyncio
async def test_real_facade_and_deep_strict_cleanup_retain_child_then_retry() -> None:
    class Sessions:
        async def close_all_sessions(self) -> None:
            return None

        def has_session_runtime(self, _session_id=None) -> bool:
            return False

    class Instance:
        def __init__(self) -> None:
            self.calls = 0

        async def stop(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("injected real lower cleanup failure")

    root = JiuWenSwarmDeepAdapter()
    child = JiuWenSwarmDeepAdapter()
    child.mark_as_session_scoped("formal-session")
    instance = Instance()
    child._instance = instance  # type: ignore[assignment]
    root._session_adapters["formal-session"] = child
    root._session_adapter_locks["formal-session"] = asyncio.Lock()
    facade = object.__new__(JiuWenSwarm)
    facade._session_manager = Sessions()
    facade._adapter = root

    with pytest.raises(RuntimeError, match="PROJECT_AGENT_CLEANUP_PENDING"):
        await facade.cleanup_formal_project_task_agent()
    assert facade._adapter is root
    assert root._session_adapters == {"formal-session": child}
    assert child._instance is instance

    await facade.cleanup_formal_project_task_agent()
    assert instance.calls == 2
    assert root.has_session_runtime() is False
    assert facade._adapter is None


@pytest.mark.asyncio
async def test_real_deep_strict_cleanup_retains_a2x_client_until_retry() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = 0

        async def aclose(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("injected A2X close failure")

    adapter = JiuWenSwarmDeepAdapter()
    adapter.mark_as_session_scoped("formal-session")
    client = Client()
    adapter._a2x_client = client

    with pytest.raises(RuntimeError, match="PROJECT_AGENT_CLEANUP_PENDING"):
        await adapter.cleanup_formal_project_task_agent()
    assert adapter._a2x_client is client
    assert adapter.has_session_runtime()

    await adapter.cleanup_formal_project_task_agent()
    assert client.calls == 2
    assert adapter._a2x_client is None
    assert adapter.has_session_runtime() is False
