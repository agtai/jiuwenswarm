"""Endpoint experiments retain Runtime turn and interruption ownership."""
import pytest

from jiuwenswarm.server.live_voice import openai_realtime_native_engine as native
from jiuwenswarm.server.live_voice.native_interaction_config import NativeInteractionConfigurationError
from test_openai_realtime_native_engine import CapturingFactory, ScriptedSocket, binding, config, negotiation, business_context


@pytest.mark.asyncio
@pytest.mark.parametrize("eagerness", ["auto", "high"])
async def test_endpoint_strategy_is_requested_without_auto_response_or_interruption(monkeypatch, eagerness):
    records = []
    monkeypatch.setattr(native, "profile_snapshot_event", lambda event, snapshot, **fields: records.append(fields))
    socket = ScriptedSocket(negotiation())
    factory = CapturingFactory(socket)
    engine = native.OpenAIRealtimeNativeInteractionEngine(config(), binding=binding(), socket_factory=factory, vad_eagerness=eagerness)
    engine.configure_business_context(business_context())
    try:
        await engine.start()
        strategy = socket.sent[0]["session"]["audio"]["input"]["turn_detection"]
        assert strategy == {"type": "semantic_vad", "eagerness": eagerness, "create_response": False, "interrupt_response": False}
        assert len(factory.calls) == 1 and not any(item["type"] == "response.create" for item in socket.sent)
        observed = [r for r in records if r.get("milestone") == "endpoint_strategy_requested"]
        assert len(observed) == 1 and observed[0]["status"] == eagerness
        assert not any("confirmed" in r.get("milestone", "") for r in records)
    finally:
        await engine.close()


@pytest.mark.parametrize("value", [None, "medium", "high ", "HIGH", True, {}])
def test_invalid_strategy_rejects_before_transport_is_constructed(monkeypatch, value):
    creations = []
    monkeypatch.setattr(native, "OpenAIRealtimeSession", lambda *args, **kwargs: creations.append(kwargs))
    with pytest.raises(NativeInteractionConfigurationError) as failure:
        native.OpenAIRealtimeNativeInteractionEngine(config(), binding=binding(), vad_eagerness=value)
    assert failure.value.reason == "NATIVE_VAD_EAGERNESS_INVALID" and creations == []
