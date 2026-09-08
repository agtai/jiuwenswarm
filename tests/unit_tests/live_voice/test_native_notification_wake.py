"""Native readiness wakes one exact poll without consuming business output."""
import asyncio
from dataclasses import replace

import pytest

from jiuwenswarm.server.live_voice.agent_conversation_runtime import (
    AgentConversationNotification, AgentConversationNotificationWake,
    _BoundedNotificationBuffer, _NotificationConsumerDetached,
)
from jiuwenswarm.server.live_voice.native_interaction_carrier import NATIVE_NOTIFICATION_WAKE_VERSION
from tests.unit_tests.live_voice.test_notification_authorization_concurrency import setup_registry, effects
from tests.unit_tests.live_voice import test_product_composition_registry as f


def wake_params(binding, capability, response):
    return {"contract_version": NATIVE_NOTIFICATION_WAKE_VERSION, "binding": binding.to_dict(),
            "capability": capability, "response": {"interaction_id": response.interaction_id,
                "response_id": response.response_id, "response_generation": response.response_generation}}


async def admitted_registry(tmp_path):
    registry, binding, capability, response = await setup_registry(tmp_path)
    result = await registry.handle_native_propose(params=f._native_audio_batch_params(binding, capability,
        [f._native_audio_proposal(binding, response)]), request_id="admit-audio", session_id=f.SCOPE.session_id)
    assert result.ok
    return registry, binding, capability, response


@pytest.mark.asyncio
@pytest.mark.parametrize("queued_business", [False, True])
async def test_wake_preempts_buffer_without_consuming_business(queued_business):
    buffer = _BoundedNotificationBuffer(observer_capacity=8, critical_capacity=8)
    wake, detached = asyncio.Event(), asyncio.Event()
    poll = asyncio.create_task(buffer.get(lease_active=lambda: True, detached=detached, wake=wake))
    await asyncio.sleep(0)
    notification = AgentConversationNotification("task.completed", "business", "round", f.ResponseRef("i", "r", 1))
    if queued_business:
        buffer.publish(notification, critical_key=("task", "completed"))
    wake.set()
    with pytest.raises(AgentConversationNotificationWake):
        await asyncio.wait_for(poll, .15)
    assert buffer.delivered_total == 0
    assert buffer.qsize() == int(queued_business)
    assert not wake.is_set()
    if queued_business:
        assert (await buffer.get()).kind == "task.completed"
        assert buffer.delivered_total == 1


@pytest.mark.asyncio
async def test_detached_wake_never_consumes_or_clears_new_owner_signal():
    buffer = _BoundedNotificationBuffer(observer_capacity=8, critical_capacity=8)
    wake = asyncio.Event()
    wake.set()
    with pytest.raises(_NotificationConsumerDetached):
        await buffer.get(lease_active=lambda: False, wake=wake)
    assert wake.is_set() and buffer.delivered_total == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("caller_cancelled", [False, True])
async def test_current_admitted_audio_wakes_retained_poll_and_replays_once(tmp_path, caller_cancelled):
    registry, binding, capability, response = await admitted_registry(tmp_path)
    route = registry._p2_routes[(binding.scope.session_id, binding.interaction_id)]
    params = f._p2_params(notification_sequence=1)
    async def poll():
        return await registry.handle_p2_notification_next(params=params, request_id="waiting-poll",
            session_id=f.SCOPE.session_id)
    caller = asyncio.create_task(poll())
    try:
        async with asyncio.timeout(1):
            while "waiting-poll" not in registry._p2_notification_operations:
                await asyncio.sleep(0)
        owner = registry._p2_notification_operations["waiting-poll"].task
        assert not owner.done()
        if caller_cancelled:
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
        result = await registry.handle_native_propose(params=wake_params(binding, capability, response),
            request_id="wake-ready", session_id=f.SCOPE.session_id)
        assert result.ok and result.payload["result"]["kind"] == "notification_wake"
        received = await asyncio.wait_for(asyncio.shield(owner), .15)
        assert received.payload["result"]["kind"] == "transport.keepalive"
        assert await poll() is received
        before = effects(registry, route)
        assert await registry.handle_native_propose(params=wake_params(binding, capability, response),
            request_id="wake-ready", session_id=f.SCOPE.session_id) is result
        assert effects(registry, route) == before
        # A new transport request for the same response cannot wake twice.
        assert (await registry.handle_native_propose(params=wake_params(binding, capability, response),
            request_id="wake-ready-again", session_id=f.SCOPE.session_id)).ok
        record = route.activation_lease._runtime._active_notification_lease
        assert not record.wake.is_set()
    finally:
        await asyncio.gather(caller, return_exceptions=True)
        await registry.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["capability", "session", "generation", "response", "no_audio", "extra", "closed"])
async def test_invalid_wake_has_zero_business_audio_history_or_notification_effect(tmp_path, defect):
    factory = setup_registry if defect == "no_audio" else admitted_registry
    registry, binding, capability, response = await factory(tmp_path)
    route = registry._p2_routes[(binding.scope.session_id, binding.interaction_id)]
    params = wake_params(binding, capability, response)
    routed_session = f.SCOPE.session_id
    if defect == "capability": params["capability"] = "f" * 64
    elif defect == "session": routed_session = "foreign-session"
    elif defect == "generation": params["binding"]["activation_generation"] += 1
    elif defect == "response": params["response"]["response_generation"] += 1
    elif defect == "extra": params["audio"] = "forbidden"
    elif defect == "closed": route.native_closed = True
    before = effects(registry, route)
    try:
        result = await registry.handle_native_propose(params=params, request_id="bad-wake", session_id=routed_session)
        assert not result.ok
        assert effects(registry, route) == before
        assert route.native_notification_woken_response is None
        assert not route.activation_lease._runtime._active_notification_lease.wake.is_set()
    finally:
        route.native_closed = False
        await registry.stop()
