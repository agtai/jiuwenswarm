import json

import pytest

from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import (
    _validate_business_context_result, NativeRuntimeClientError,
)
from jiuwenswarm.server.live_voice.native_business_observation import project_native_receipt
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    OpenAIRealtimeNativeInteractionEngine, OpenAIRealtimeNativeInteractionError,
)


def context(capabilities):
    return {"context_id": "a" * 64, "history": [{"role": "user", "content": "Paris expense " * 40, "delivery": "heard"}], "tasks": [], "works": [],
            "model": {"model_identity": "agent", "model_config_version": "v1"},
            "capabilities": capabilities}


@pytest.mark.parametrize("capabilities", [[], ["repurchase"], ["expense"]])
def test_supported_demo_context_survives_gateway_engine_and_receipt(capabilities):
    source = context(capabilities)
    result = {"kind": "business_context", "contract_version": "live-voice.native-business.v1",
              "context": source, "work_events": []}
    validated = _validate_business_context_result(result)["context"]
    assert OpenAIRealtimeNativeInteractionEngine._business_context_copy(validated) == source
    receipt = json.dumps({"contract_version": "live-voice.native-business.v1",
                          "operation": "work.get", "context": source, "work": {}})
    projected = json.loads(project_native_receipt(receipt))
    assert projected["context_reference"]["context_id"] == source["context_id"]
    assert "context" not in projected


@pytest.mark.parametrize("capabilities", [["unknown"], ["expense", "repurchase"]])
def test_unknown_or_mixed_capabilities_remain_rejected(capabilities):
    source = context(capabilities)
    with pytest.raises(NativeRuntimeClientError):
        _validate_business_context_result({"kind": "business_context",
            "contract_version": "live-voice.native-business.v1", "context": source, "work_events": []})
    with pytest.raises(OpenAIRealtimeNativeInteractionError):
        OpenAIRealtimeNativeInteractionEngine._business_context_copy(source)
