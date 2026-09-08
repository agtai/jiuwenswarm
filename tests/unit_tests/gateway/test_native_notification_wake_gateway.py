"""Gateway wake ordering, private carrier and cancellation ownership."""
import asyncio
from dataclasses import replace

import pytest

from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import NativeRuntimeClientError
from jiuwenswarm.server.live_voice.native_interaction_carrier import NATIVE_NOTIFICATION_WAKE_VERSION
from tests.unit_tests.gateway import test_dedicated_media_registration as f
from tests.unit_tests.gateway import test_native_interaction_runtime_client as c


@pytest.fixture(autouse=True)
def allowed_origin(monkeypatch):
    monkeypatch.setenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS", "voice.example.test")


@pytest.mark.asyncio
async def test_wake_client_carries_exact_capability_and_rejects_replaced_connection():
    client, agent, _ = c.observed_client()
    activation = client.activation_for(session_id=c.SCOPE.session_id,
        interaction_id=c.BINDING.interaction_id, connection_id="web-connection-1")
    agent.result_override = {"kind": "notification_wake", "status": "observed", "accepted": True}
    response = c.audio_event().audio.response
    assert (await client.wake_native_notification(activation, response=response, request_id="wake-1"))["accepted"]
    assert agent.requests[-1].params == {"contract_version": NATIVE_NOTIFICATION_WAKE_VERSION,
        "binding": c.BINDING.to_dict(), "capability": c.CAPABILITY,
        "response": {"interaction_id": response.interaction_id, "response_id": response.response_id,
                     "response_generation": response.response_generation}}
    before = len(agent.requests)
    with pytest.raises(NativeRuntimeClientError):
        await client.wake_native_notification(replace(activation, connection_id="foreign"),
            response=response, request_id="wake-foreign")
    assert len(agent.requests) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_descriptor_precedes_wake_rpc_and_pcm_supply_and_close_do_not_wait(failure):
    activation = f._native_activation()
    entered, cancelled = asyncio.Event(), asyncio.Event()
    class Client(f._FakeNativeRuntimeClient):
        async def wake_native_notification(self, exact, *, response, request_id):
            assert exact == activation and request_id
            # A serialized browser retry can already find this local descriptor.
            notification = registry.take_native_notification(session_id="session-1",
                interaction_id="interaction-1", connection_id="connection-1")
            assert notification["kind"] == "native.audio"
            assert notification["response"]["response_id"] == response.response_id
            self.downlink = registry.consume_ticket(f._media_ticket(notification["audio"]), request_origin=f.ORIGIN)
            entered.set()
            if failure:
                raise OSError("test unavailable")
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
    client, engine = Client(activation), f._FakeNativeEngine()
    registry = f.DedicatedMediaProductRegistry(enabled=True, native_runtime_client=client,
        native_engine_factory=lambda _binding: engine)
    activated = f._activate(registry, params=f._params(sample_rate_hz=24_000),
        request_origin=f.ORIGIN, connection_id="connection-1")
    uplink = registry.consume_ticket(f._media_ticket(activated), request_origin=f.ORIGIN)
    await registry.begin_native_interaction(uplink)
    response = f.ResponseRef("interaction-1", "wake-response", 1)
    session = registry._native_sessions[registry._native_session_keys_by_record[uplink.record_id]]
    try:
        for seq in range(3):
            await engine.events.put(f.NativeEngineEvent(audio=f.NativeAudioOutput(
                provider_event_id=f"audio-{seq}", provider_response_id="provider-response",
                provider_item_id="item", content_index=0, sequence=seq,
                pcm16=b"\x01\x00" * 480, response=response)))
        await asyncio.wait_for(entered.wait(), 1)
        async with asyncio.timeout(1):
            while client.downlink.downlink_stream_source.buffered_frames != 3:
                await asyncio.sleep(0)
        assert len(session.notification_wake_tasks) <= 1
        assert engine.presentation_acknowledgements == []
        assert await asyncio.wait_for(registry.close_native_interaction(uplink), .5)
        assert not session.notification_wake_tasks
        if not failure:
            assert cancelled.is_set()
    finally:
        await registry.close_native_interaction(uplink)
