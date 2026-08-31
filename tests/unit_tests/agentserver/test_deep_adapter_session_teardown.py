# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio

import pytest

from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter


def _make_adapter(**state: object) -> JiuWenSwarmDeepAdapter:
    """Create a bare adapter with internal state set via setattr."""
    adapter = object.__new__(JiuWenSwarmDeepAdapter)
    for name, value in state.items():
        setattr(adapter, name, value)
    return adapter


class _IdleChildAdapter:
    def __init__(self) -> None:
        self.cleaned = False

    @staticmethod
    def is_session_active(_session_id: str) -> bool:
        return False

    @staticmethod
    def is_deep_agent_executing_for_session(_session_id: str) -> bool:
        return False

    async def cleanup(self) -> None:
        self.cleaned = True


class _BlockingCleanupChildAdapter(_IdleChildAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.cleanup_started = asyncio.Event()
        self.cleanup_can_finish = asyncio.Event()

    async def cleanup(self) -> None:
        self.cleanup_started.set()
        await self.cleanup_can_finish.wait()
        await super().cleanup()


def test_other_active_sessions_treats_subagent_as_related() -> None:
    adapter = _make_adapter(
        _active_session_ids={
            "tui_main": 1,
            "tui_main_sub_explore": 1,
        },
    )

    assert getattr(adapter, "_other_active_sessions")("tui_main") == 0
    assert getattr(adapter, "_other_active_sessions")("tui_main_sub_explore") == 0


def test_other_active_sessions_counts_unrelated_sessions() -> None:
    adapter = _make_adapter(
        _active_session_ids={
            "tui_a": 1,
            "tui_b": 1,
        },
    )

    assert getattr(adapter, "_other_active_sessions")("tui_a") == 1


@pytest.mark.asyncio
async def test_cancel_session_agent_tasks_cancels_registered_task() -> None:
    adapter = _make_adapter(_session_agent_tasks={})
    cancelled = asyncio.Event()

    async def worker() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(worker())
    getattr(adapter, "_session_agent_tasks")["sess_x"] = {task}
    await asyncio.sleep(0)

    cancelled_count = await getattr(adapter, "_cancel_session_agent_tasks")("sess_x")
    assert cancelled_count == 1
    await asyncio.wait_for(cancelled.wait(), timeout=2)


def test_is_session_live_when_deep_agent_stream_task_running() -> None:
    from unittest.mock import MagicMock

    instance = MagicMock()
    setattr(instance, "_invoke_active", True)
    stream_task = MagicMock()
    stream_task.done.return_value = False
    setattr(instance, "_stream_process_task", stream_task)
    loop_session = MagicMock()
    loop_session.get_session_id.return_value = "tui_main"
    setattr(instance, "_loop_session", loop_session)
    adapter = _make_adapter(
        _active_session_ids={},
        _session_agent_tasks={},
        _instance=instance,
    )

    assert getattr(adapter, "_is_session_live")("tui_main") is True
    assert getattr(adapter, "_other_active_sessions")("tui_other") == 1


@pytest.mark.asyncio
async def test_cleanup_session_adapter_removes_idle_child_adapter() -> None:
    child = _IdleChildAdapter()
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={"sess_exit": child},
        _session_adapter_locks={"sess_exit": asyncio.Lock()},
        _session_adapter_last_used={"sess_exit": 1.0},
        _session_adapter_versions={"sess_exit": 1},
        _session_adapter_reload_failures={"sess_exit": (1, 1.0)},
    )

    removed = await getattr(parent, "cleanup_session_adapter")("sess_exit")

    assert removed is True
    assert child.cleaned is True
    assert getattr(parent, "_session_adapters") == {}
    assert getattr(parent, "_session_adapter_locks") == {}
    assert getattr(parent, "_session_adapter_last_used") == {}
    assert getattr(parent, "_session_adapter_versions") == {}
    assert getattr(parent, "_session_adapter_reload_failures") == {}


@pytest.mark.asyncio
async def test_cleanup_session_adapter_without_child_keeps_runtime_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runtime_state_path = tmp_path / "sess_missing.yaml"
    runtime_state_path.write_text("mode: agent.plan\n", encoding="utf-8")
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.agent_adapter.interface_deep.get_runtime_state_path",
        lambda _session_id: runtime_state_path,
    )
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={},
        _session_adapter_locks={"sess_missing": asyncio.Lock()},
        _session_adapter_last_used={"sess_missing": 1.0},
        _session_adapter_versions={"sess_missing": 1},
        _session_adapter_reload_failures={"sess_missing": (1, 1.0)},
    )

    removed = await getattr(parent, "cleanup_session_adapter")("sess_missing")

    assert removed is False
    assert runtime_state_path.exists()
    assert getattr(parent, "_session_adapter_locks") == {}


@pytest.mark.asyncio
async def test_cleanup_session_adapter_defers_inflight_child_creation() -> None:
    lock = asyncio.Lock()
    await lock.acquire()
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={},
        _session_adapter_locks={"sess_race": lock},
        _session_adapter_last_used={"sess_race": 1.0},
        _session_adapter_versions={"sess_race": 1},
        _session_adapter_reload_failures={},
    )

    cleanup_task = asyncio.create_task(
        getattr(parent, "cleanup_session_adapter")("sess_race")
    )
    await asyncio.sleep(0)
    assert cleanup_task.done() is False

    child = _IdleChildAdapter()
    getattr(parent, "_session_adapters")["sess_race"] = child
    lock.release()

    removed = await asyncio.wait_for(cleanup_task, timeout=2)

    assert removed is False
    assert child.cleaned is False
    assert getattr(parent, "_session_adapters") == {"sess_race": child}


@pytest.mark.asyncio
async def test_cleanup_session_adapter_defers_locked_cached_child_adapter() -> None:
    lock = asyncio.Lock()
    await lock.acquire()
    child = _IdleChildAdapter()
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={"sess_locked": child},
        _session_adapter_locks={"sess_locked": lock},
        _session_adapter_last_used={"sess_locked": 1.0},
        _session_adapter_versions={"sess_locked": 1},
        _session_adapter_reload_failures={},
    )

    cleanup_task = asyncio.create_task(
        getattr(parent, "cleanup_session_adapter")("sess_locked")
    )
    await asyncio.sleep(0)

    assert cleanup_task.done() is False
    assert child.cleaned is False

    lock.release()
    removed = await asyncio.wait_for(cleanup_task, timeout=2)

    assert removed is False
    assert child.cleaned is False
    assert getattr(parent, "_session_adapters") == {"sess_locked": child}


@pytest.mark.asyncio
async def test_cleanup_session_adapter_prunes_lock_after_failed_inflight_creation() -> None:
    lock = asyncio.Lock()
    await lock.acquire()
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={},
        _session_adapter_locks={"sess_failed_create": lock},
        _session_adapter_last_used={"sess_failed_create": 1.0},
        _session_adapter_versions={"sess_failed_create": 1},
        _session_adapter_reload_failures={},
    )

    cleanup_task = asyncio.create_task(
        getattr(parent, "cleanup_session_adapter")("sess_failed_create")
    )
    await asyncio.sleep(0)
    assert cleanup_task.done() is False

    lock.release()
    removed = await asyncio.wait_for(cleanup_task, timeout=2)

    assert removed is False
    assert getattr(parent, "_session_adapter_locks") == {}
    assert getattr(parent, "_session_adapter_last_used") == {}
    assert getattr(parent, "_session_adapter_versions") == {}


@pytest.mark.asyncio
async def test_concurrent_cleanup_prunes_empty_session_lock() -> None:
    lock = asyncio.Lock()
    child = _BlockingCleanupChildAdapter()
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={"sess_concurrent_cleanup": child},
        _session_adapter_locks={"sess_concurrent_cleanup": lock},
        _session_adapter_last_used={"sess_concurrent_cleanup": 1.0},
        _session_adapter_versions={"sess_concurrent_cleanup": 1},
        _session_adapter_reload_failures={
            "sess_concurrent_cleanup": (1, 1.0),
        },
    )

    first = asyncio.create_task(
        getattr(parent, "cleanup_session_adapter")("sess_concurrent_cleanup")
    )
    await asyncio.wait_for(child.cleanup_started.wait(), timeout=2)
    second = asyncio.create_task(
        getattr(parent, "cleanup_session_adapter")("sess_concurrent_cleanup")
    )
    await asyncio.sleep(0)

    child.cleanup_can_finish.set()
    assert await asyncio.wait_for(first, timeout=2) is True
    assert await asyncio.wait_for(second, timeout=2) is False

    assert child.cleaned is True
    assert getattr(parent, "_session_adapters") == {}
    assert getattr(parent, "_session_adapter_locks") == {}
    assert getattr(parent, "_session_adapter_last_used") == {}
    assert getattr(parent, "_session_adapter_versions") == {}
    assert getattr(parent, "_session_adapter_reload_failures") == {}


@pytest.mark.asyncio
async def test_cleanup_session_adapter_keeps_queued_reconnect_adapter() -> None:
    lock = asyncio.Lock()
    child = _BlockingCleanupChildAdapter()
    replacement = _IdleChildAdapter()
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={"sess_reconnect": child},
        _session_adapter_locks={"sess_reconnect": lock},
        _session_adapter_last_used={"sess_reconnect": 1.0},
        _session_adapter_versions={"sess_reconnect": 1},
        _session_adapter_reload_failures={},
    )

    cleanup_task = asyncio.create_task(
        getattr(parent, "cleanup_session_adapter")("sess_reconnect")
    )
    await asyncio.wait_for(child.cleanup_started.wait(), timeout=2)

    async def queued_reconnect() -> None:
        async with lock:
            getattr(parent, "_session_adapters")["sess_reconnect"] = replacement

    reconnect_task = asyncio.create_task(queued_reconnect())
    await asyncio.sleep(0)
    assert reconnect_task.done() is False

    child.cleanup_can_finish.set()
    removed = await asyncio.wait_for(cleanup_task, timeout=2)
    await asyncio.wait_for(reconnect_task, timeout=2)

    assert removed is True
    assert child.cleaned is True
    assert getattr(parent, "_session_adapters") == {"sess_reconnect": replacement}
    assert getattr(parent, "_session_adapter_locks")["sess_reconnect"] is lock


@pytest.mark.asyncio
async def test_idle_eviction_keeps_queued_reconnect_adapter() -> None:
    lock = asyncio.Lock()
    child = _BlockingCleanupChildAdapter()
    replacement = _IdleChildAdapter()
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={"sess_idle_reconnect": child},
        _session_adapter_locks={"sess_idle_reconnect": lock},
        _session_adapter_last_used={"sess_idle_reconnect": 1.0},
        _session_adapter_versions={"sess_idle_reconnect": 1},
        _session_adapter_reload_failures={},
        SESSION_ADAPTER_EVICT_BATCH_SIZE=8,
        SESSION_ADAPTER_IDLE_TTL_SEC=1.0,
    )

    eviction_task = asyncio.create_task(
        getattr(parent, "_evict_idle_session_adapters")()
    )
    await asyncio.wait_for(child.cleanup_started.wait(), timeout=2)

    async def queued_reconnect() -> None:
        async with lock:
            getattr(parent, "_session_adapters")["sess_idle_reconnect"] = replacement

    reconnect_task = asyncio.create_task(queued_reconnect())
    await asyncio.sleep(0)
    assert reconnect_task.done() is False

    child.cleanup_can_finish.set()
    await asyncio.wait_for(eviction_task, timeout=2)
    await asyncio.wait_for(reconnect_task, timeout=2)

    assert child.cleaned is True
    assert getattr(parent, "_session_adapters") == {
        "sess_idle_reconnect": replacement
    }
    assert getattr(parent, "_session_adapter_locks")["sess_idle_reconnect"] is lock


@pytest.mark.asyncio
async def test_idle_eviction_skips_locked_adapter_without_waiting() -> None:
    lock = asyncio.Lock()
    await lock.acquire()
    child = _IdleChildAdapter()
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _session_adapters={"sess_locked_idle": child},
        _session_adapter_locks={"sess_locked_idle": lock},
        _session_adapter_last_used={"sess_locked_idle": 1.0},
        _session_adapter_versions={"sess_locked_idle": 1},
        _session_adapter_reload_failures={},
        SESSION_ADAPTER_EVICT_BATCH_SIZE=8,
        SESSION_ADAPTER_IDLE_TTL_SEC=1.0,
    )

    eviction_task = asyncio.create_task(
        getattr(parent, "_evict_idle_session_adapters")()
    )
    await asyncio.sleep(0)

    assert eviction_task.done() is True
    assert child.cleaned is False
    assert getattr(parent, "_session_adapters") == {"sess_locked_idle": child}
    assert getattr(parent, "_session_adapter_locks")["sess_locked_idle"] is lock

    lock.release()


class _ReadyChildAdapter(_IdleChildAdapter):
    async def create_instance(self, _config, *, mode, sub_mode) -> None:
        return None

    async def start_interaction(self, *, session_id) -> None:
        return None


class _FailingCreateChildAdapter(_IdleChildAdapter):
    """create_instance fails; cleanup behavior is scenario-controlled."""

    def __init__(self, *, cleanup_error: BaseException | None = None) -> None:
        super().__init__()
        self.cleanup_error = cleanup_error
        self.cleanup_calls = 0

    async def create_instance(self, _config, *, mode, sub_mode) -> None:
        raise RuntimeError("CHILD_CREATE_FAILED")

    async def start_interaction(self, *, session_id) -> None:  # pragma: no cover
        raise AssertionError("start_interaction must not run after failed create")

    async def cleanup(self) -> None:
        self.cleanup_calls += 1
        if self.cleanup_error is not None:
            error = self.cleanup_error
            self.cleanup_error = None
            raise error
        await super().cleanup()


class _ParkedCreateChildAdapter(_IdleChildAdapter):
    """create_instance parks until cancelled; cleanup blocks on a gate."""

    def __init__(self) -> None:
        super().__init__()
        self.create_entered = asyncio.Event()
        self.cleanup_started = asyncio.Event()
        self.cleanup_can_finish = asyncio.Event()

    async def create_instance(self, _config, *, mode, sub_mode) -> None:
        self.create_entered.set()
        await asyncio.Event().wait()

    async def cleanup(self) -> None:
        self.cleanup_started.set()
        await self.cleanup_can_finish.wait()
        await super().cleanup()


def _initialization_parent(children: list[object]) -> JiuWenSwarmDeepAdapter:
    queue = list(children)
    parent = _make_adapter(
        _is_session_scoped_adapter=False,
        _parent_session_id=None,
        _session_adapters={},
        _session_adapter_initializing=set(),
        _session_adapter_locks={},
        _session_adapter_last_used={},
        _session_adapter_config_version=0,
        _session_adapter_versions={},
        _session_adapter_reload_failures={},
        _session_adapter_generations={},
        _session_adapter_failed_cleaning=set(),
        _pending_session_reload_config_base=None,
        _pending_session_reload_env_overrides=None,
        _session_instance_config=None,
        _session_instance_mode="agent",
        _session_instance_sub_mode=None,
    )
    setattr(parent, "_new_session_scoped_adapter", lambda _sid: queue.pop(0))
    return parent


@pytest.mark.asyncio
async def test_failed_init_with_failing_cleanup_recovers_on_retry() -> None:
    """F18: 非正式档初始化失败且清理也失败时,Session 不得永久卡死——
    下一次调用先补清理,清理证明完成后重新初始化必须成功。"""
    first = _FailingCreateChildAdapter(cleanup_error=RuntimeError("CLEANUP_FAILED"))
    second = _ReadyChildAdapter()
    parent = _initialization_parent([first, second])

    with pytest.raises(RuntimeError, match="CHILD_CREATE_FAILED"):
        await getattr(parent, "_get_or_create_session_adapter")("sess-retry")
    assert first.cleanup_calls == 1
    assert getattr(parent, "_session_adapters").get("sess-retry") is first

    resolved = await getattr(parent, "_get_or_create_session_adapter")("sess-retry")

    assert resolved is second
    assert first.cleanup_calls == 2
    assert first.cleaned is True
    assert getattr(parent, "_session_adapters").get("sess-retry") is second


@pytest.mark.asyncio
async def test_second_cancellation_cannot_abandon_partial_cleanup() -> None:
    """F18: 初始化被取消后,清理必须与调用方取消隔离——再次取消调用方
    不得把清理丢在半路;清理最终完成时,该 Session 必须回到可用状态。"""
    parked = _ParkedCreateChildAdapter()
    replacement = _ReadyChildAdapter()
    parent = _initialization_parent([parked, replacement])

    initialize = asyncio.create_task(
        getattr(parent, "_get_or_create_session_adapter")("sess-cancel")
    )
    await asyncio.wait_for(parked.create_entered.wait(), timeout=2)
    initialize.cancel()
    await asyncio.wait_for(parked.cleanup_started.wait(), timeout=2)
    # 清理还没完成时第二次取消调用方。
    initialize.cancel()
    with pytest.raises(asyncio.CancelledError):
        await initialize

    parked.cleanup_can_finish.set()
    for _ in range(10):
        await asyncio.sleep(0)
    assert parked.cleaned is True

    resolved = await asyncio.wait_for(
        getattr(parent, "_get_or_create_session_adapter")("sess-cancel"), timeout=2
    )
    assert resolved is replacement


@pytest.mark.asyncio
async def test_stale_detached_cleanup_cannot_drop_a_successor_adapter() -> None:
    """F18: 迟到的旧代清理只能释放自己那一代——继任 adapter 不受影响。"""
    parked = _ParkedCreateChildAdapter()
    replacement = _ReadyChildAdapter()
    parent = _initialization_parent([parked, replacement])

    initialize = asyncio.create_task(
        getattr(parent, "_get_or_create_session_adapter")("sess-stale")
    )
    await asyncio.wait_for(parked.create_entered.wait(), timeout=2)
    initialize.cancel()
    await asyncio.wait_for(parked.cleanup_started.wait(), timeout=2)
    initialize.cancel()
    with pytest.raises(asyncio.CancelledError):
        await initialize

    # 旧清理仍挂着;手动腾出缓存位并让继任初始化成功。
    getattr(parent, "_session_adapters").pop("sess-stale", None)
    getattr(parent, "_session_adapter_initializing").discard("sess-stale")
    successor = await asyncio.wait_for(
        getattr(parent, "_get_or_create_session_adapter")("sess-stale"), timeout=2
    )
    assert successor is replacement

    parked.cleanup_can_finish.set()
    for _ in range(10):
        await asyncio.sleep(0)
    assert getattr(parent, "_session_adapters").get("sess-stale") is replacement


# ---------------------------------------------------------------------------
# F18 验收矩阵:在 create/start/reload 每个 await 注入失败与取消。
# 断言:无孤儿残留(缓存清空、initializing 摘除、cleanup 实际执行),
# 且同一 Session 的下一次调用成功拿到新 child。
# reload 的"异常"档按既有契约被吞掉(记录 reload_failures、初始化照常成功)。
# ---------------------------------------------------------------------------


class _MatrixChildAdapter(_IdleChildAdapter):
    """按位点注入 raise/park 的矩阵子适配器。"""

    def __init__(self, behaviors: dict) -> None:
        super().__init__()
        self.behaviors = behaviors
        self.entered: dict[str, asyncio.Event] = {
            site: asyncio.Event() for site in ("create", "start", "reload")
        }

    async def _at(self, site: str) -> None:
        self.entered[site].set()
        behavior = self.behaviors.get(site)
        if behavior is None:
            return
        kind, payload = behavior
        if kind == "raise":
            raise payload
        if kind == "park":
            await payload.wait()
            raise asyncio.CancelledError()

    async def create_instance(self, _config, *, mode, sub_mode) -> None:
        await self._at("create")

    async def start_interaction(self, *, session_id) -> None:
        await self._at("start")

    async def reload_agent_config(self, _config_base, _env, *, target_session_id) -> None:
        await self._at("reload")


def _matrix_parent(children: list[object], *, pending_reload: bool = False):
    parent = _initialization_parent(children)
    if pending_reload:
        parent._session_adapter_config_version = 1
        parent._pending_session_reload_config_base = {"reload": True}
    return parent


async def _settle_ticks(count: int = 10) -> None:
    for _ in range(count):
        await asyncio.sleep(0)


def _assert_no_orphan(parent, sid: str) -> None:
    assert getattr(parent, "_session_adapters").get(sid) is None
    assert sid not in getattr(parent, "_session_adapter_initializing")
    assert sid not in getattr(parent, "_session_adapter_failed_cleaning")


@pytest.mark.asyncio
@pytest.mark.parametrize("site", ["create", "start"])
async def test_matrix_exception_at_each_init_await_cleans_and_recovers(site) -> None:
    failing = _MatrixChildAdapter({site: ("raise", RuntimeError(f"{site}_failed"))})
    replacement = _ReadyChildAdapter()
    parent = _matrix_parent([failing, replacement])

    with pytest.raises(RuntimeError, match=f"{site}_failed"):
        await getattr(parent, "_get_or_create_session_adapter")(f"sess-{site}-exc")

    assert failing.cleaned is True
    _assert_no_orphan(parent, f"sess-{site}-exc")

    resolved = await getattr(parent, "_get_or_create_session_adapter")(
        f"sess-{site}-exc"
    )
    assert resolved is replacement


@pytest.mark.asyncio
@pytest.mark.parametrize("site", ["create", "start"])
async def test_matrix_cancellation_at_each_init_await_cleans_and_recovers(site) -> None:
    gate = asyncio.Event()
    parked = _MatrixChildAdapter({site: ("park", gate)})
    replacement = _ReadyChildAdapter()
    parent = _matrix_parent([parked, replacement])
    sid = f"sess-{site}-cancel"

    initialize = asyncio.create_task(
        getattr(parent, "_get_or_create_session_adapter")(sid)
    )
    await asyncio.wait_for(parked.entered[site].wait(), timeout=2)
    initialize.cancel()
    with pytest.raises(asyncio.CancelledError):
        await initialize
    await _settle_ticks()

    assert parked.cleaned is True
    _assert_no_orphan(parent, sid)

    resolved = await asyncio.wait_for(
        getattr(parent, "_get_or_create_session_adapter")(sid), timeout=2
    )
    assert resolved is replacement


@pytest.mark.asyncio
async def test_matrix_reload_exception_is_swallowed_and_adapter_stays_ready() -> None:
    """reload 异常按既有契约不失败初始化:记录 reload_failures,child 就绪。"""
    child = _MatrixChildAdapter({"reload": ("raise", RuntimeError("reload_failed"))})
    parent = _matrix_parent([child], pending_reload=True)
    sid = "sess-reload-exc"

    resolved = await getattr(parent, "_get_or_create_session_adapter")(sid)

    assert resolved is child
    assert child.cleaned is False
    assert sid in getattr(parent, "_session_adapter_reload_failures")
    assert getattr(parent, "_session_adapters").get(sid) is child
    again = await getattr(parent, "_get_or_create_session_adapter")(sid)
    assert again is child


@pytest.mark.asyncio
async def test_matrix_reload_cancellation_cleans_and_recovers() -> None:
    gate = asyncio.Event()
    parked = _MatrixChildAdapter({"reload": ("park", gate)})
    replacement = _ReadyChildAdapter()
    parent = _matrix_parent([parked, replacement], pending_reload=True)
    sid = "sess-reload-cancel"

    initialize = asyncio.create_task(
        getattr(parent, "_get_or_create_session_adapter")(sid)
    )
    await asyncio.wait_for(parked.entered["reload"].wait(), timeout=2)
    initialize.cancel()
    with pytest.raises(asyncio.CancelledError):
        await initialize
    await _settle_ticks()

    assert parked.cleaned is True
    _assert_no_orphan(parent, sid)

    resolved = await asyncio.wait_for(
        getattr(parent, "_get_or_create_session_adapter")(sid), timeout=2
    )
    assert resolved is replacement
