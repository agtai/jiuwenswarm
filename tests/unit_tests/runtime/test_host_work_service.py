# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""The Host retains Work across channel release, with unchanged SQLite recovery."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.runtime.service import AgentRuntime, RuntimeStateError
from jiuwenswarm.server.runtime.formal_tasks.unified_committed_input import SqliteUnifiedCommittedInputJournal
from jiuwenswarm.server.runtime.work.native_work_journal import SqliteNativeWorkJournal
from jiuwenswarm.server.runtime.work.native_work_runtime import NativeWorkSnapshot, NativeWorkState
from jiuwenswarm.server.runtime.work.native_work_runtime import context_identity
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import FormalContextSnapshot


SCOPE = ScopeRef("subject", "project", "work-session", Assurance.AUTHENTICATED)


def host():
    manager = SimpleNamespace(cancel_all_inflight_work=AsyncMock(), cleanup=AsyncMock(), unpin_agent=Mock())
    return AgentRuntime(agent_manager=manager, initializer=AsyncMock())


def inputs():
    return dict(scope=SCOPE, request_id="work-request", input_id="input-1", instruction="Analyze sources",
                model_identity="model#0", model_config_version="version-1",
                context_id=context_identity(FormalContextSnapshot(SCOPE)), foreground=False)


@pytest.mark.asyncio
async def test_canonical_database_has_one_owner_and_shutdown_settles_work(tmp_path):
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "work.sqlite3")
    runtime = host()
    service = runtime.get_work_service(journal.database_path)
    assert runtime.get_work_service(tmp_path / "." / "work.sqlite3") is service
    started, release = asyncio.Event(), asyncio.Event()

    async def run(control):
        started.set()
        await control.read_only(release.wait())
        return "answer"

    work = await service.work_runtime.start(**inputs(), runner=run)
    await asyncio.wait_for(started.wait(), 2)
    await runtime.close()
    settled = service.work_runtime.query(scope=SCOPE, work_id=work.work_id)
    assert settled.state is NativeWorkState.CANCELLED and settled.execution_settled
    assert service.closed
    assert SqliteNativeWorkJournal(journal.database_path).restore()[0] == settled
    with pytest.raises(RuntimeStateError):
        runtime.get_work_service(journal.database_path)


@pytest.mark.asyncio
async def test_voice_release_keeps_host_work_and_actual_producer_pool_alive(tmp_path):
    from jiuwenswarm.channels.live_voice.native_business_router import NativeBusinessRouter

    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "work.sqlite3")
    runtime = host()
    registry = SimpleNamespace(_runtime=runtime, _unified_journal=journal, _agent_manager=runtime.agent_manager)
    first = NativeBusinessRouter(registry)
    owner = first.works()
    service = runtime.get_work_service(journal.database_path)
    producer = SimpleNamespace(close=AsyncMock(return_value=SimpleNamespace(closed=True)))
    facade = object()
    service.executors[SCOPE] = (producer, facade)
    started, release = asyncio.Event(), asyncio.Event()

    async def run(control):
        started.set()
        await control.read_only(release.wait())
        return "survived speech release"

    work = await owner.start(**inputs(), runner=run)
    await asyncio.wait_for(started.wait(), 2)
    await first.close()
    assert not service.closed
    assert owner.query(scope=SCOPE, work_id=work.work_id).state is NativeWorkState.RUNNING
    producer.close.assert_not_called()
    second = NativeBusinessRouter(registry)
    assert second.works() is owner and second._executors is service.executors
    release.set()
    # Await the actual existing work operation, not a projected receipt.
    await asyncio.wait_for(owner._records[(SCOPE, work.work_id, work.revision)].operation, 2)
    assert owner.query(scope=SCOPE, work_id=work.work_id).result_text == "survived speech release"
    await runtime.close()
    producer.close.assert_awaited_once()
    runtime.agent_manager.unpin_agent.assert_called_once_with(facade)


@pytest.mark.asyncio
async def test_existing_recovery_marks_lost_process_unknown_without_running_agent(tmp_path):
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "work.sqlite3")
    store = SqliteNativeWorkJournal(journal.database_path)
    before = NativeWorkSnapshot(
        **inputs(), work_id="work-1", revision=1, sequence=1, state=NativeWorkState.ACCEPTED,
        accepted_at="2026-09-13T08:00:00Z", updated_at="2026-09-13T08:00:00Z",
    )
    store.save(before)
    before = replace(before, state=NativeWorkState.RUNNING, sequence=2)
    store.save(before)
    runtime = host()
    service = runtime.get_work_service(journal.database_path)
    restored = service.work_runtime.query(scope=SCOPE, work_id="work-1")
    assert restored.state is NativeWorkState.UNKNOWN
    assert restored.reason == "PROCESS_OWNERSHIP_LOST" and restored.execution_settled
    assert restored.sequence == before.sequence + 1
    assert service.executors == {}
    runtime._initializer.assert_not_called()
    await runtime.close()


@pytest.mark.asyncio
async def test_voice_cannot_create_work_owner_without_host(tmp_path):
    from jiuwenswarm.channels.live_voice.native_business_router import NativeBusinessRouter
    from jiuwenswarm.channels.live_voice.native_business_contract import NativeBusinessViolation

    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "work.sqlite3")
    router = NativeBusinessRouter(SimpleNamespace(_runtime=None, _unified_journal=journal))
    with pytest.raises(NativeBusinessViolation, match="NATIVE_WORK_HOST_UNAVAILABLE"):
        router.works()
    assert router._work_owner is None and router._work_journal is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["incomplete", "error"])
async def test_incomplete_producer_cleanup_is_retained_for_host_close_retry(tmp_path, failure):
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "work.sqlite3")
    runtime = host()
    service = runtime.get_work_service(journal.database_path)
    first = SimpleNamespace(closed=False) if failure == "incomplete" else RuntimeError("cleanup failed")
    producer = SimpleNamespace(
        close=AsyncMock(side_effect=[first, SimpleNamespace(closed=True)]),
        snapshot=lambda: SimpleNamespace(closed=False),
    )
    facade = object()
    service.executors[SCOPE] = (producer, facade)
    with pytest.raises(RuntimeError):
        await runtime.close()
    assert not runtime.closed and not service.closed and service.closing
    assert service.executors[SCOPE] == (producer, facade)
    runtime.agent_manager.unpin_agent.assert_not_called()
    runtime.agent_manager.cleanup.assert_not_called()
    with pytest.raises(RuntimeStateError):
        runtime.get_work_service(journal.database_path)
    await runtime.close()
    assert runtime.closed and service.closed and service.executors == {}
    runtime.agent_manager.unpin_agent.assert_called_once_with(facade)


@pytest.mark.asyncio
async def test_borrowed_work_retains_authority_checks_after_voice_registry_stops(tmp_path):
    from jiuwenswarm.channels.live_voice.native_business_router import NativeBusinessRouter
    from jiuwenswarm.channels.live_voice.native_business_contract import NativeBusinessViolation

    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "work.sqlite3")
    runtime = host()
    context = SimpleNamespace(file_path="exact-project", require_usable=Mock())
    composition = SimpleNamespace(_accepting=True, _clock=lambda: "now",
        _resolve_native_activation_authority=Mock(return_value=SimpleNamespace(context=context)))
    registry = SimpleNamespace(_runtime=runtime, _unified_journal=journal, _stopped=True, _p3_composition=composition)
    router = NativeBusinessRouter(registry)
    router.works()
    route = SimpleNamespace(binding=SimpleNamespace(scope=SCOPE, session_id=SCOPE.session_id),
        native_p3_authority=SimpleNamespace(context=context))
    await router._require_work_authority(route)
    context.require_usable.assert_called_once()
    composition._accepting = False
    with pytest.raises(NativeBusinessViolation, match="NATIVE_WORK_AUTHORITY_UNAVAILABLE"):
        await router._require_work_authority(route)
    assert context.require_usable.call_count == 1
    await runtime.close()


async def executor_router(tmp_path):
    from jiuwenswarm.channels.live_voice.native_business_router import NativeBusinessRouter
    from tests.unit_tests.runtime.test_runtime_formal import setup

    value, agent, manager, admission, runtime, _wrapper = await setup()
    manager.get_agent = AsyncMock(return_value=agent)
    manager.pin_agent = Mock()
    manager.unpin_agent = Mock()
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "executor.sqlite3")
    registry = SimpleNamespace(_runtime=runtime, _unified_journal=journal, _agent_manager=manager)
    router = NativeBusinessRouter(registry)
    router.works()
    route = SimpleNamespace(binding=SimpleNamespace(scope=value.commit.scope),
        native_p3_authority=SimpleNamespace(context=SimpleNamespace(file_path="project-path")))
    return value, agent, manager, runtime, router, route


@pytest.mark.asyncio
async def test_recreated_session_uses_new_executor_and_old_facade_stays_fenced(tmp_path):
    value, agent, manager, runtime, router, route = await executor_router(tmp_path)
    first = await router._executor(route)
    assert await router._executor(route) is first
    assert [item async for item in first._facade.process_formal_live_voice_stream(value)][-1].is_complete
    old_generation = runtime.session_coordinator.snapshot_session(value.commit.scope.session_id).generation
    await runtime.session_coordinator.close_session(value.commit.scope.session_id)
    await runtime.register_session(session_id=value.commit.scope.session_id, channel_id="web")
    new_generation = runtime.session_coordinator.snapshot_session(value.commit.scope.session_id).generation
    assert new_generation > old_generation
    with pytest.raises(RuntimeStateError, match="FORMAL_SESSION_GENERATION_CHANGED"):
        await anext(first._facade.process_formal_live_voice_stream(replace(value, request_id="stale-request")))
    assert agent.seen == [value]
    second = await router._executor(route)
    assert second is not first and await router._executor(route) is second
    fresh = replace(value, request_id="fresh-request", internal_session_id="fresh-internal")
    result = [item async for item in second._facade.process_formal_live_voice_stream(fresh)]
    assert result[-1].payload["content"] == "Exact answer"
    assert agent.seen == [value, fresh]
    assert set(router._executors) == {(value.commit.scope, new_generation)}
    assert first.snapshot().closed
    assert manager.unpin_agent.call_count == 1
    await runtime.close()
    assert manager.unpin_agent.call_count == 2


@pytest.mark.asyncio
async def test_executor_generation_change_during_facade_lookup_has_zero_producer_effects(tmp_path):
    from jiuwenswarm.channels.live_voice.native_business_contract import NativeBusinessViolation

    value, agent, manager, runtime, router, route = await executor_router(tmp_path)

    async def recreate(*args):
        await runtime.session_coordinator.close_session(value.commit.scope.session_id)
        await runtime.register_session(session_id=value.commit.scope.session_id, channel_id="web")
        return agent

    manager.get_agent.side_effect = recreate
    with pytest.raises(NativeBusinessViolation, match="NATIVE_WORK_SESSION_GENERATION_CHANGED"):
        await router._executor(route)
    assert router._executors == {} and agent.seen == [] and agent.gates == []
    manager.pin_agent.assert_not_called()
    manager.unpin_agent.assert_not_called()
    await runtime.close()


@pytest.mark.asyncio
async def test_closed_session_cannot_allocate_work_executor(tmp_path):
    from jiuwenswarm.channels.live_voice.native_business_contract import NativeBusinessViolation

    value, agent, manager, runtime, router, route = await executor_router(tmp_path)
    await runtime.session_coordinator.close_session(value.commit.scope.session_id)
    with pytest.raises(NativeBusinessViolation, match="NATIVE_WORK_SESSION_UNAVAILABLE"):
        await router._executor(route)
    manager.get_agent.assert_not_called()
    manager.pin_agent.assert_not_called()
    assert router._executors == {} and agent.seen == []
    await runtime.close()


@pytest.mark.asyncio
async def test_host_close_waits_for_blocked_start_and_retains_late_failed_cleanup(tmp_path, monkeypatch):
    from jiuwenswarm.channels.live_voice import agent_conversation_runtime
    from jiuwenswarm.channels.live_voice.native_business_contract import NativeBusinessViolation

    value, agent, manager, runtime, router, route = await executor_router(tmp_path)
    started, release = asyncio.Event(), asyncio.Event()
    attempts = []

    class StartingExecutor:
        async def start(self):
            started.set()
            await release.wait()
            return True

        async def close(self, *, timeout_seconds):
            attempts.append(timeout_seconds)
            if len(attempts) == 1:
                raise RuntimeError("first startup cleanup failed")
            return SimpleNamespace(closed=len(attempts) >= 3)

        def snapshot(self):
            return SimpleNamespace(closed=False)

    producer = StartingExecutor()
    monkeypatch.setattr(agent_conversation_runtime, "AgentConversationRuntime", lambda **kwargs: producer)
    allocation = asyncio.create_task(router._executor(route))
    await asyncio.wait_for(started.wait(), 2)
    closing = asyncio.create_task(runtime.close())
    for _ in range(100):
        if router._work_service.closing:
            break
        await asyncio.sleep(0)
    assert router._work_service.closing and not router._work_service.closed
    assert not closing.done()
    manager.unpin_agent.assert_not_called()
    manager.cleanup.assert_not_called()
    release.set()
    with pytest.raises(NativeBusinessViolation, match="NATIVE_WORK_HOST_UNAVAILABLE"):
        await allocation
    with pytest.raises(RuntimeStateError, match="cleanup is incomplete"):
        await closing
    assert len(router._executors) == 1 and not runtime.closed and not router._work_service.closed
    manager.unpin_agent.assert_not_called()
    manager.cleanup.assert_not_called()
    assert agent.seen == []
    await runtime.close()
    assert runtime.closed and router._work_service.closed and router._executors == {}
    assert len(attempts) == 3
    manager.unpin_agent.assert_called_once_with(agent)


@pytest.mark.asyncio
async def test_more_than_pool_capacity_session_reopens_reclaim_idle_generations(tmp_path):
    value, agent, manager, runtime, router, route = await executor_router(tmp_path)
    for index in range(35):
        if index:
            await runtime.session_coordinator.close_session(value.commit.scope.session_id)
            await runtime.register_session(session_id=value.commit.scope.session_id, channel_id="web")
        executor = await router._executor(route)
        assert len(router._executors) == 1
        assert manager.unpin_agent.call_count == index
    fresh = replace(value, request_id="after-35-reopens", internal_session_id="new-generation-internal")
    chunks = [item async for item in executor._facade.process_formal_live_voice_stream(fresh)]
    assert chunks[-1].payload["content"] == "Exact answer" and agent.seen == [fresh]
    await runtime.close()
    assert manager.unpin_agent.call_count == 35


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["active", "cleanup-pending", "work-unsettled"])
async def test_nonsettled_predecessor_is_retained_without_reuse_or_unpin(tmp_path, state):
    value, agent, manager, runtime, router, route = await executor_router(tmp_path)
    generation = runtime.session_coordinator.snapshot_session(value.commit.scope.session_id).generation
    predecessor = SimpleNamespace(
        close=AsyncMock(return_value=SimpleNamespace(closed=False)),
        snapshot=lambda: SimpleNamespace(closed=False,
            active_requests=("active",) if state == "active" else (),
            harness=SimpleNamespace(active_rounds=())),
    )
    previous_facade = object()
    key = (value.commit.scope, generation)
    router._executors[key] = (predecessor, previous_facade)
    work = None
    release = asyncio.Event()
    if state == "work-unsettled":
        async def run(control):
            await control.read_only(release.wait())
            return "settled"

        arguments = {**inputs(), "scope": value.commit.scope,
            "context_id": context_identity(FormalContextSnapshot(value.commit.scope))}
        work = await router._work_owner.start(**arguments, runner=run)
    await runtime.session_coordinator.close_session(value.commit.scope.session_id)
    await runtime.register_session(session_id=value.commit.scope.session_id, channel_id="web")
    current = await router._executor(route)
    assert current is not predecessor and router._executors[key] == (predecessor, previous_facade)
    manager.unpin_agent.assert_not_called()
    if state in {"active", "work-unsettled"}:
        predecessor.close.assert_not_called()
    else:
        predecessor.close.assert_awaited_once()
    if work is not None:
        release.set()
        await asyncio.wait_for(router._work_owner._records[(work.scope, work.work_id, work.revision)].operation, 2)
    predecessor.close.return_value = SimpleNamespace(closed=True)
    await runtime.close()
    assert manager.unpin_agent.call_count == 2
