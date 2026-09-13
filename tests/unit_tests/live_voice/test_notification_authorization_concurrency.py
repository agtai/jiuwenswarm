"""Business authorization I/O cannot monopolize audio's Registry lock."""
import asyncio
from dataclasses import replace

import pytest

from tests.unit_tests.live_voice import test_product_composition_registry as fixtures


async def setup_registry(tmp_path):
    registry, *rest = fixtures._registry(tmp_path,
        interaction_engine=fixtures.InteractionEngineKind.OPENAI_REALTIME_NATIVE)
    binding, capability, response = await fixtures._activate_native_delegate_source(registry, stem="auth-load")
    return registry, binding, capability, response


def effects(registry, route):
    """Observe the real fixture owners, including consumed notifications/history."""
    return (route.notification_admitted_sequence, route.notification_replay_floor,
            route.activation_lease._runtime.snapshot(), route.native_runtime_owner.snapshot(),
            tuple(registry._p2_notification_operations),
            tuple(registry._native_propose_operations), tuple(registry._native_delegate_operations),
            tuple(registry._agent_manager.get_calls), registry._agent_manager.agent.calls,
            registry._agent_manager.code_agent.calls, tuple(registry._p3_composition.query_calls),
            tuple(registry._p3_composition.semantic_calls), tuple(registry._p3_composition.retry_admission_calls))


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["replacement", "replay_eviction"])
async def test_authorization_window_cannot_recreate_retired_owner(tmp_path, monkeypatch, transition):
    registry, *_ = await setup_registry(tmp_path)
    key = (fixtures.SCOPE.session_id, "interaction-1")
    original_route = registry._p2_routes[key]
    params = fixtures._p2_params(notification_sequence=1)
    request_id = "retired-owner"
    if transition == "replay_eviction":
        assert (await registry.handle_p2_notification_next(params=params,
            request_id=request_id, session_id=fixtures.SCOPE.session_id)).ok
    entered, release = asyncio.Event(), asyncio.Event()
    original = registry._authority_registration
    async def delayed(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)
    monkeypatch.setattr(registry, "_authority_registration", delayed)
    poll = asyncio.create_task(registry.handle_p2_notification_next(params=params,
        request_id=request_id, session_id=fixtures.SCOPE.session_id))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if transition == "replacement":
            # Same serialized binding still cannot replace the captured owner.
            registry._p2_routes[key] = replace(original_route)
        else:
            assert registry._evict_completed_product_operation(
                registry._p2_notification_operations, notification=True)
        before = effects(registry, registry._p2_routes[key])
        release.set()
        result = await poll
        assert not result.ok
        assert result.payload["error"]["reason"] == "PRODUCT_P2_ROUTE_NOT_FOUND"
        assert effects(registry, registry._p2_routes[key]) == before
    finally:
        release.set()
        await asyncio.gather(poll, return_exceptions=True)
        registry._p2_routes[key] = original_route
        await registry.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [False, True])
async def test_concurrent_authorization_retains_one_notification_consumer(tmp_path, monkeypatch, conflict):
    registry, *_ = await setup_registry(tmp_path)
    route = registry._p2_routes[(fixtures.SCOPE.session_id, "interaction-1")]
    entered, release = asyncio.Event(), asyncio.Event()
    original = registry._authority_registration
    slow = None
    async def delayed(**kwargs):
        if asyncio.current_task() is slow:
            entered.set()
            await release.wait()
        return await original(**kwargs)
    monkeypatch.setattr(registry, "_authority_registration", delayed)
    params = fixtures._p2_params(notification_sequence=1)
    slow = asyncio.create_task(registry.handle_p2_notification_next(params=params,
        request_id="concurrent-owner", session_id=fixtures.SCOPE.session_id))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        fast = await registry.handle_p2_notification_next(
            params={**params, **({"max_notifications": 2} if conflict else {})},
            request_id="concurrent-owner", session_id=fixtures.SCOPE.session_id)
        assert fast.ok
        retained = registry._p2_notification_operations["concurrent-owner"]
        before = effects(registry, route)
        release.set()
        result = await slow
        if conflict:
            assert not result.ok
            assert result.payload["error"]["reason"] == "PRODUCT_REQUEST_ID_CONFLICT"
        else:
            assert result is fast
        assert registry._p2_notification_operations["concurrent-owner"] is retained
        assert effects(registry, route) == before
    finally:
        release.set()
        await asyncio.gather(slow, return_exceptions=True)
        await registry.stop()


@pytest.mark.asyncio
async def test_notification_authorization_wait_does_not_block_exact_audio_admission(tmp_path, monkeypatch):
    registry, binding, capability, response = await setup_registry(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original = registry._authority_registration
    async def delayed(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)
    monkeypatch.setattr(registry, "_authority_registration", delayed)
    poll = asyncio.create_task(registry.handle_p2_notification_next(
        params=fixtures._p2_params(notification_sequence=1), request_id="poll-under-load",
        session_id=fixtures.SCOPE.session_id))
    audio = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        audio = asyncio.create_task(registry.handle_native_propose(
            params=fixtures._native_audio_batch_params(binding, capability,
                [fixtures._native_audio_proposal(binding, response)]),
            request_id="audio-during-auth", session_id=fixtures.SCOPE.session_id))
        ready, _ = await asyncio.wait((audio,), timeout=.15)
        assert audio in ready, "notification authorization holds the media admission lock"
        result = audio.result()
        assert result.ok and result.payload["result"]["items"][0]["accepted"]
        assert not poll.done()
    finally:
        release.set()
        await asyncio.gather(poll, *([audio] if audio is not None else []), return_exceptions=True)
        await registry.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["cancel", "close"])
async def test_authorization_inflight_cannot_publish_after_cancel_or_route_close(tmp_path, monkeypatch, transition):
    registry, binding, capability, response = await setup_registry(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original = registry._authority_registration
    poll = None
    async def delayed(**kwargs):
        if asyncio.current_task() is poll:
            entered.set()
            await release.wait()
        return await original(**kwargs)
    monkeypatch.setattr(registry, "_authority_registration", delayed)
    poll = asyncio.create_task(registry.handle_p2_notification_next(
        params=fixtures._p2_params(notification_sequence=1), request_id="retired-auth-poll",
        session_id=fixtures.SCOPE.session_id))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if transition == "cancel":
            poll.cancel()
            with pytest.raises(asyncio.CancelledError):
                await poll
        else:
            closed = await asyncio.wait_for(registry.handle_p2_close(params=fixtures._p2_params(),
                request_id="close-during-auth", session_id=fixtures.SCOPE.session_id), .5)
            assert closed.ok
            release.set()
            result = await poll
            assert not result.ok
        assert "retired-auth-poll" not in registry._p2_notification_operations
    finally:
        release.set()
        await asyncio.gather(poll, return_exceptions=True)
        await registry.stop()
