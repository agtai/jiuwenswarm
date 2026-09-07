import asyncio
import json
import threading
from copy import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from dataclasses import replace

import pytest

from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import NativeRuntimeClientError
from jiuwenswarm.server.live_voice.native_business_observation import (
    NATIVE_PROVIDER_RECEIPT_VERSION,
    canonical_native_receipt, observation_cursor, project_native_receipt,
)
from jiuwenswarm.server.live_voice.native_work_runtime import NativeWorkRuntime, NativeWorkViolation
from tests.unit_tests.live_voice.test_native_business_registry import make_registry, call
from tests.unit_tests.live_voice.test_native_work_runtime import admission, terminal, scope


def receipt():
    return {"contract_version": "live-voice.native-business.v1", "operation": "work.get",
        "work": {"result_text": "verified result\n" + "tail" * 200, "revision": 2, "state": "completed"},
        "context": {"context_id": "a" * 64, "history": [{"role": "user", "content": "context" * 500}],
                    "tasks": [], "works": [], "model": {"model_identity": "agent", "model_config_version": "v1"}}}


def test_projection_keeps_all_result_facts_and_canonical_receipt_immutable():
    original = canonical_native_receipt(receipt())
    projected = json.loads(project_native_receipt(original))
    assert projected["provider_receipt_version"] == NATIVE_PROVIDER_RECEIPT_VERSION
    assert projected["context_reference"]["context_id"] == "a" * 64
    assert "context" not in projected and projected["work"] == receipt()["work"]
    assert original == canonical_native_receipt(receipt())
    assert len(project_native_receipt(original).encode("utf-8")) < len(original.encode("utf-8"))


@pytest.mark.parametrize("bad", ["", "null", "[]", '{"x":1,"x":2}',
    '{"contract_version":"live-voice.native-business.v1","operation":"work.get","context":NaN}',
    '{"contract_version":"other","context":{}}'])
def test_projection_unsupported_input_stays_exact(bad):
    assert project_native_receipt(bad) == bad


@pytest.mark.parametrize("bad", [{}, {"epoch": "a" * 32, "sequence": True, "read_sequence": 0},
    {"epoch": "A" * 32, "sequence": 0, "read_sequence": 0},
    {"epoch": "a" * 32, "sequence": 0, "read_sequence": -1},
    {"epoch": "a" * 32, "sequence": 0, "read_sequence": 0, "extra": 1}])
def test_cursor_is_closed_and_not_a_boolean_counter(bad):
    with pytest.raises(ValueError):
        observation_cursor(bad)


@pytest.mark.asyncio
async def test_work_wait_has_no_lost_wake_and_cancellation_cleans_exact_event():
    owner = NativeWorkRuntime()
    current = scope()
    initial = owner.observation_cursor(current)
    owner.wake_observers(current)  # Transition before waiter installation.
    await asyncio.wait_for(owner.wait_for_observation(scope=current, after=initial, wait_ms=1000), .1)
    after = owner.observation_cursor(current)
    first = asyncio.create_task(owner.wait_for_observation(scope=current, after=after, wait_ms=1000))
    second = asyncio.create_task(owner.wait_for_observation(scope=current, after=after, wait_ms=1000))
    await asyncio.sleep(0)
    assert owner._observation_waiters == 2
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    assert owner._observation_waiters == 1 and current in owner._observation_events
    owner.wake_observers(scope(session_id="other"))
    await asyncio.sleep(0)
    assert not second.done()
    owner.wake_observers(current)
    await asyncio.wait_for(second, .1)
    assert owner._observation_waiters == 0 and not owner._observation_events
    assert not owner._observation_event_waiters
    await owner.close()


@pytest.mark.asyncio
async def test_wait_capacity_shutdown_timeout_and_epoch_restart():
    owner = NativeWorkRuntime()
    current = scope()
    after = owner.observation_cursor(current)
    await owner.wait_for_observation(scope=current, after=after, wait_ms=1)
    assert not owner._observation_events
    waiters = [asyncio.create_task(owner.wait_for_observation(scope=current, after=after, wait_ms=1000)) for _ in range(128)]
    await asyncio.sleep(0)
    with pytest.raises(NativeWorkViolation) as error:
        await owner.wait_for_observation(scope=current, after=after, wait_ms=1000)
    assert error.value.reason == "NATIVE_OBSERVATION_CAPACITY"
    await owner.close()
    await asyncio.wait_for(asyncio.gather(*waiters), .2)
    assert not owner._observation_events and not owner._observation_event_waiters
    replacement = NativeWorkRuntime()
    assert replacement.observation_cursor(current)["epoch"] != after["epoch"]
    await asyncio.wait_for(replacement.wait_for_observation(scope=current, after=after, wait_ms=1000), .1)
    await replacement.close()


def activation(env):
    return env.client.activation_for(session_id="session-1", interaction_id="interaction-1", connection_id="business-wire")


@pytest.mark.asyncio
async def test_scope_churn_rotates_bounded_observations_without_losing_or_removing_new_waiter():
    owner = NativeWorkRuntime(max_records=4)
    current = scope()
    entered, release = asyncio.Event(), asyncio.Event()
    async def runner(control):
        entered.set()
        await control.read_only(release.wait())
        return "Preserved Work result"
    work = await owner.start(**admission(runner, current_scope=current))
    await entered.wait()
    records_before = owner.list(scope=current)
    owner.wake_observers(current)
    old_cursor = owner.observation_cursor(current)
    old_waiters = [asyncio.create_task(owner.wait_for_observation(
        scope=current, after=old_cursor, wait_ms=1000)) for _ in range(2)]
    await asyncio.sleep(0)
    assert owner._observation_waiters == 2
    for index in range(4):
        owner.wake_observers(scope(session_id=f"churn-{index}"))
    new_cursor = owner.observation_cursor(current)
    assert new_cursor["epoch"] != old_cursor["epoch"]
    # Install the replacement before yielding to old waiter cleanup.
    new_waiter = asyncio.create_task(owner.wait_for_observation(
        scope=current, after=new_cursor, wait_ms=1000))
    await asyncio.sleep(0)
    await asyncio.wait_for(asyncio.gather(*old_waiters), .2)
    assert not new_waiter.done()
    assert owner._observation_waiters == 1 and current in owner._observation_events
    # An old epoch cannot park on its formerly matching per-scope sequence.
    await asyncio.wait_for(owner.wait_for_observation(
        scope=current, after=old_cursor, wait_ms=1000), .1)
    owner.wake_observers(current)
    await asyncio.wait_for(new_waiter, .2)
    assert not owner._observation_events and not owner._observation_event_waiters
    for index in range(1000):
        owner.wake_observers(scope(session_id=f"retired-{index}"))
        assert len(owner._observation_sequence) <= 4
    assert owner.list(scope=current) == records_before and len(owner._records) == 1
    release.set()
    assert (await terminal(owner, work)).result_text == "Preserved Work result"
    await owner.close()


async def finish(env):
    await env.registry.stop()
    await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["current", "closed", "replaced", "expired"])
async def test_slow_context_authority_keeps_audio_lock_available_and_rechecks_retirement(
    tmp_path, monkeypatch, change,
):
    env = await make_registry(tmp_path, monkeypatch)
    router = env.registry._native_business
    route = env.registry._p2_routes[("session-1", "interaction-1")]
    release, entered = threading.Event(), threading.Event()
    pending = None
    try:
        selected = await router._context_result(route)
        async def retained_context(unused):
            return selected
        monkeypatch.setattr(router, "_context_result", retained_context)
        composition = env.harness.composition
        resolve = composition._resolve_native_activation_authority
        def slow_resolve(*args, **kwargs):
            current = resolve(*args, **kwargs)
            entered.set()
            # Bound the red-path stall as well as worker cleanup on assertion failure.
            release.wait(2)
            return current
        monkeypatch.setattr(composition, "_resolve_native_activation_authority", slow_resolve)
        before = composition._core.store.counts()
        origins = dict(env.registry._voice_task_origins)
        pending = asyncio.create_task(env.client.observe_business_context(
            activation(env), request_id="slow-authority"))
        assert await asyncio.to_thread(entered.wait, 2)
        assert not pending.done(), "Synchronous authority I/O blocked the event loop"
        # Audio admission uses this same registry lock and must stay schedulable.
        await asyncio.wait_for(env.registry._lock.acquire(), .2)
        env.registry._lock.release()
        if change == "closed":
            route.native_closed = True
        elif change == "replaced":
            env.registry._p2_routes[("session-1", "interaction-1")] = copy(route)
        elif change == "expired":
            composition._clock = lambda: (datetime.now(UTC) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        release.set()
        if change == "current":
            observed = await asyncio.wait_for(pending, 1)
            assert observed["context"] == selected[0].payload()
        else:
            with pytest.raises(NativeRuntimeClientError):
                await asyncio.wait_for(pending, 1)
        assert composition._core.store.counts() == before
        assert env.registry._voice_task_origins == origins
        assert env.manager.agent.executions == []
        assert router.works().list(scope=env.binding.scope) == ()
    finally:
        release.set()
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
        env.registry._p2_routes[("session-1", "interaction-1")] = route
        await finish(env)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["observation", "projection"])
async def test_context_expiring_while_waiting_for_registry_lock_has_zero_effects(tmp_path, monkeypatch, boundary):
    env = await make_registry(tmp_path, monkeypatch)
    router = env.registry._native_business
    route = env.registry._p2_routes[("session-1", "interaction-1")]
    ready, resume = asyncio.Event(), asyncio.Event()
    waiting = None
    held = False
    try:
        selected = await router._context_result(route)
        async def retained_context(unused):
            return selected
        monkeypatch.setattr(router, "_context_result", retained_context)
        require = router._require_context_authority
        async def resolved_then_wait(candidate):
            current = await require(candidate)
            ready.set()
            await resume.wait()
            return current
        monkeypatch.setattr(router, "_require_context_authority", resolved_then_wait)
        monkeypatch.setattr(router, "task_origins", lambda scope: ("retained-task",))
        before = env.harness.composition._core.store.counts()
        origins = dict(env.registry._voice_task_origins)
        operation = (env.client.observe_business_context(activation(env), request_id="expiry-lock")
            if boundary == "observation" else router._restore_task_projection(
                route, env.binding.scope, [SimpleNamespace(task_id="retained-task")]))
        waiting = asyncio.create_task(operation)
        await asyncio.wait_for(ready.wait(), 1)
        await env.registry._lock.acquire()
        held = True
        resume.set()
        await asyncio.sleep(0)
        assert not waiting.done() and env.registry._lock._waiters
        env.harness.composition._clock = lambda: (datetime.now(UTC) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        env.registry._lock.release()
        held = False
        with pytest.raises(Exception) as rejected:
            await asyncio.wait_for(waiting, 1)
        assert "EXPIRED" in getattr(rejected.value, "reason", "")
        assert env.harness.composition._core.store.counts() == before
        assert env.registry._voice_task_origins == origins
        assert env.manager.agent.executions == [] and router.works().list(scope=env.binding.scope) == ()
    finally:
        if held:
            env.registry._lock.release()
        resume.set()
        if waiting is not None:
            await asyncio.gather(waiting, return_exceptions=True)
        await finish(env)


@pytest.mark.asyncio
async def test_serialized_authenticated_terminal_wakes_wait_without_poll_timeout(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    release, running = asyncio.Event(), asyncio.Event()
    async def runner(control):
        running.set()
        await control.read_only(release.wait())
        return "Complete grounded result tail"
    owner = env.registry._native_business.works()
    try:
        work = await owner.start(**admission(runner, current_scope=env.binding.scope))
        await running.wait()
        first = await env.client.observe_business_context(activation(env), request_id="observe-first")
        assert first["kind"] == "business_observation" and first["work_events"] == []
        waiting = asyncio.create_task(env.client.observe_business_context(activation(env), request_id="observe-wait",
            after=first["cursor"], wait_ms=1000))
        for _ in range(100):
            if owner._observation_waiters:
                break
            await asyncio.sleep(.001)
        assert owner._observation_waiters == 1
        release.set()
        observed = await asyncio.wait_for(waiting, .7)
        assert observed["cursor"]["sequence"] > first["cursor"]["sequence"]
        assert observed["work_events"][0]["result_text"] == "Complete grounded result tail"
        assert (await terminal(owner, work)).execution_settled
        assert not env.manager.agent.executions
    finally:
        release.set()
        await finish(env)


@pytest.mark.asyncio
async def test_server_activation_retirement_during_wait_releases_no_context(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    router = env.registry._native_business
    owner = router.works()
    try:
        first = await env.client.observe_business_context(activation(env), request_id="observe-first")
        waiting = asyncio.create_task(env.client.observe_business_context(activation(env), request_id="observe-wait",
            after=first["cursor"], wait_ms=1000))
        for _ in range(100):
            if owner._observation_waiters:
                break
            await asyncio.sleep(.001)
        route = env.registry._p2_routes[("session-1", "interaction-1")]
        route.native_closed = True
        router.retire_activation(route)
        with pytest.raises(NativeRuntimeClientError):
            await asyncio.wait_for(waiting, .7)
        assert owner._observation_waiters == 0
        assert not env.manager.agent.executions
    finally:
        await finish(env)


@pytest.mark.asyncio
async def test_client_wrong_capability_and_unnegotiated_observation_have_zero_requests(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    called = []
    async def forbidden(envelope):
        called.append(envelope)
        raise AssertionError("No RPC allowed")
    monkeypatch.setattr(env.client._agent, "send_request", forbidden)
    try:
        for changed in (replace(activation(env), capability="b" * 64),
                        replace(activation(env), observation_contract_version=None),
                        replace(activation(env), connection_id="other")):
            with pytest.raises(NativeRuntimeClientError):
                await env.client.observe_business_context(changed, request_id="wrong")
        for invalid in (True, -1, 1001):
            with pytest.raises(NativeRuntimeClientError):
                await env.client.observe_business_context(activation(env), request_id="wrong", wait_ms=invalid)
        assert not called
    finally:
        await finish(env)


@pytest.mark.asyncio
async def test_canonical_first_sqlite_replay_bytes_match_without_second_task_effect(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    texts = []
    original = env.client.propose
    async def captured(**arguments):
        result = await original(**arguments)
        texts.append(result["canonical_text"])
        return result
    monkeypatch.setattr(env.client, "propose", captured)
    try:
        value, params = await call(env, "task.create", name="Replay report", instruction="Write replay report")
        before = env.harness.composition._core.store.counts()
        journal = env.registry._unified_journal
        # Reopen the real SQLite journal, discarding any Python result mapping.
        env.registry._unified_journal = type(journal)(journal.database_path)
        result = await env.registry.handle_native_propose(params=params, request_id="replayed", session_id="session-1")
        assert result.ok
        assert texts[0] == result.payload["result"]["canonical_text"] == canonical_native_receipt(value)
        assert env.harness.composition._core.store.counts() == before
        assert not env.manager.agent.executions
    finally:
        await finish(env)


@pytest.mark.asyncio
async def test_context_read_coalesces_and_one_cancelled_reader_cannot_cancel_other(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    router = env.registry._native_business
    entered, release = asyncio.Event(), asyncio.Event()
    original = router._read_context
    calls = []
    async def paused(route):
        calls.append(route)
        entered.set()
        await release.wait()
        return await original(route)
    monkeypatch.setattr(router, "_read_context", paused)
    route = env.registry._p2_routes[("session-1", "interaction-1")]
    try:
        one = asyncio.create_task(router.context(route))
        two = asyncio.create_task(router.context(route))
        await entered.wait()
        one.cancel()
        await asyncio.gather(one, return_exceptions=True)
        assert len(calls) == 1 and not two.done()
        release.set()
        assert (await asyncio.wait_for(two, .7)).payload()["context_id"]
        await asyncio.sleep(0)
        assert not router._context_reads
    finally:
        release.set()
        await finish(env)
