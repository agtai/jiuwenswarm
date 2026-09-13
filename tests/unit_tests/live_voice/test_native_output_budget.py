"""Native audio budget is explicit without changing turn or business authority."""

import pytest

from jiuwenswarm.server.live_voice import openai_realtime_native_engine as native
from jiuwenswarm.server.live_voice.native_interaction_config import NativeInteractionConfigurationError
from test_openai_realtime_native_engine import (
    CapturingFactory, ScriptedSocket, binding, business_context, config, negotiation,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", ["inf", 1, 4096])
@pytest.mark.parametrize("business", [False, True])
async def test_session_budget_covers_direct_responses_without_automatic_turns(budget, business):
    socket = ScriptedSocket(negotiation())
    factory = CapturingFactory(socket)
    engine = native.OpenAIRealtimeNativeInteractionEngine(
        config(), binding=binding(), socket_factory=factory, max_output_tokens=budget,
    )
    if business:
        engine.configure_business_context(business_context())
    try:
        await engine.start()
        session = socket.sent[0]["session"]
        assert session["max_output_tokens"] == budget
        detection = session["audio"]["input"]["turn_detection"]
        assert detection["create_response"] is False
        assert detection["interrupt_response"] is False
        assert not any(item["type"] == "response.create" for item in socket.sent)
    finally:
        await engine.close()


@pytest.mark.parametrize("budget", [None, True, 0, -1, 4097, 32000, 1.0, "1024", "INF", "inf\n", [], {}])
def test_invalid_budget_rejects_before_transport_construction(monkeypatch, budget):
    constructed = []
    monkeypatch.setattr(native, "OpenAIRealtimeSession", lambda *args, **kwargs: constructed.append(kwargs))
    with pytest.raises(NativeInteractionConfigurationError) as raised:
        native.OpenAIRealtimeNativeInteractionEngine(config(), binding=binding(), max_output_tokens=budget)
    assert raised.value.reason == "NATIVE_MAX_OUTPUT_TOKENS_INVALID"
    assert constructed == []
