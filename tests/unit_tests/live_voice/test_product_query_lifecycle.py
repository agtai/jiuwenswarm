# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Query lifecycle regressions across the real Registry, Runtime and P3 adapter."""
import asyncio
import threading

import pytest

from tests.unit_tests.live_voice import test_product_composition_registry as p


def query(registry, request_id="slow-query"):
    return registry.handle_p3_query(
        operation="task.status",
        params={"auth_token": "trusted-token", "session_id": p.SCOPE.session_id, "task_id": "task-1"},
        request_id=request_id, session_id=p.SCOPE.session_id,
    )


@pytest.mark.asyncio
async def test_slow_query_does_not_serialize_audio_ack_and_stop(tmp_path, monkeypatch):
    registry, composition, manager, _ = p._registry(
        tmp_path, interaction_engine=p.InteractionEngineKind.OPENAI_REALTIME_NATIVE,
    )
    binding, capability, response = await p._activate_native_delegate_source(registry, stem="query-concurrency")
    entered, release = asyncio.Event(), asyncio.Event()
    original = registry._p3_adapter.activate_prepared_query

    async def blocked(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(registry._p3_adapter, "activate_prepared_query", blocked)
    pending = asyncio.create_task(query(registry))
    try:
        await asyncio.wait_for(entered.wait(), 2)

        async def propose(proposal, request_id):
            return await asyncio.wait_for(registry.handle_native_propose(
                params=p._native_propose_params(binding, capability, proposal),
                request_id=request_id, session_id=p.SCOPE.session_id,
            ), 1)

        admitted = await propose(p._native_audio_proposal(binding, response), "audio-during-query")
        assert admitted.ok
        unit = admitted.payload["result"]["presentation_unit"]
        ack = await asyncio.wait_for(registry.handle_native_presentation_ack(
            params=p._native_ack_params(binding, capability, response, unit_id=unit["unit_id"]),
            request_id="ack-during-query", session_id=p.SCOPE.session_id,
        ), 1)
        assert ack.ok
        stop = p.NativeInteractionProposal.from_engine_event(binding, p.NativeEngineEvent(
            action=p.InteractionAction(action_id="stop-during-query", operation="STOP",
                interaction_id=binding.interaction_id, scope=binding.scope,
                payload=(("provider_response_id", "provider-response-1"), ("runtime_response_id", response.response_id),
                         ("response_generation", str(response.response_generation)))),
        ))
        assert (await propose(stop, "stop-during-query")).ok
        assert not pending.done() and not release.is_set()
        release.set()
        assert (await pending).ok
        assert manager.agent.calls == 0
    finally:
        release.set()
        await pending
        await registry.stop()


@pytest.mark.asyncio
async def test_cancelled_query_waiter_keeps_thread_and_shutdown_ownership(tmp_path, monkeypatch):
    registry, composition, manager, _ = p._registry(tmp_path)
    loop = asyncio.get_running_loop()
    entered, release, thread_finished = asyncio.Event(), threading.Event(), threading.Event()
    closed = asyncio.Event()
    original = composition.resolve_product_authority_candidate
    original_close = registry.close_active_routes

    def blocked(**kwargs):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5), "test failed to release authority thread"
        try:
            return original(**kwargs)
        finally:
            thread_finished.set()

    async def close():
        assert thread_finished.is_set()
        closed.set()
        await original_close()

    monkeypatch.setattr(composition, "resolve_product_authority_candidate", blocked)
    monkeypatch.setattr(registry, "close_active_routes", close)
    pending = asyncio.create_task(query(registry))
    stopping = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert registry._p3_query_tasks
        # Bounded ownership counts cancelled waiters until their real work ends.
        monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)
        rejected = await query(registry, "over-capacity")
        assert not rejected.ok and rejected.payload["error"]["reason"] == "PRODUCT_OPERATION_LEDGER_FULL"
        stopping = asyncio.create_task(registry.stop())
        await asyncio.sleep(0)
        assert not stopping.done() and not closed.is_set()
        rejected = await query(registry, "after-stop")
        assert not rejected.ok and rejected.payload["error"]["reason"] == "PRODUCT_COMPOSITION_STOPPED"
        release.set()
        await asyncio.wait_for(stopping, 3)
        assert closed.is_set() and thread_finished.is_set()
        assert not registry._p3_query_tasks
        assert manager.get_calls == []
    finally:
        release.set()
        if stopping is not None:
            await stopping
        else:
            await registry.stop()


@pytest.mark.asyncio
async def test_query_authority_failure_after_wait_has_no_business_effects(tmp_path, monkeypatch):
    registry, composition, manager, _ = p._registry(tmp_path)
    loop = asyncio.get_running_loop()
    entered, release = asyncio.Event(), threading.Event()
    original = composition.resolve_product_authority_candidate

    def blocked(**kwargs):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)
        return original(**kwargs)

    monkeypatch.setattr(composition, "resolve_product_authority_candidate", blocked)
    pending = asyncio.create_task(query(registry))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        composition.fail_authority = p.FormalTaskViolation(
            "TEST_AUTHORITY_REVOKED", "test revocation", p.ErrorCode.PERMISSION_DENIED,
        )
        release.set()
        result = await asyncio.wait_for(pending, 2)
        assert not result.ok and result.payload["error"]["reason"] == "TEST_AUTHORITY_REVOKED"
        assert not composition.query_calls
        assert manager.get_calls == [] and manager.agent.calls == 0
    finally:
        release.set()
        await pending
        await registry.stop()

@pytest.mark.asyncio
async def test_query_survives_voice_route_close_without_late_audio_or_history(tmp_path, monkeypatch):
    registry, composition, manager, pushed = p._registry(
        tmp_path, interaction_engine=p.InteractionEngineKind.OPENAI_REALTIME_NATIVE,
    )
    binding, capability, response = await p._activate_native_delegate_source(registry, stem="query-route-close")
    route = registry._p2_routes[(p.SCOPE.session_id, binding.interaction_id)]
    runtime = route.activation_lease._runtime
    entered, release = asyncio.Event(), asyncio.Event()
    original = registry._p3_adapter.activate_prepared_query

    async def blocked(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(registry._p3_adapter, "activate_prepared_query", blocked)
    pending = asyncio.create_task(query(registry))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(registry.close_active_routes(), 1)
        assert not registry._p2_routes and not pending.done()
        before = runtime.snapshot()
        pushed_before = list(pushed)
        release.set()
        assert (await asyncio.wait_for(pending, 2)).ok
        assert runtime.snapshot() == before and pushed == pushed_before
        assert manager.agent.calls == 0
    finally:
        release.set()
        await pending
        await registry.stop()
