# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio

import pytest

from jiuwenswarm.common.schema.agent import AgentResponse
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.gateway.channel_manager.web import app_web_handlers
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import (
    NATIVE_GATEWAY_DESCRIPTOR_KEY,
    NATIVE_INTERNAL_REQ_METHODS,
    GatewayNativeInteractionRuntimeClient,
    NativeRuntimeClientError,
)
from jiuwenswarm.server.live_voice.interaction_engine import InteractionAction
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeInteractionBinding,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    NativeEngineEvent,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    PresentationAck,
    PresentationSurface,
)


SCOPE = ScopeRef(
    "subject-native", "project-native", "session-native", Assurance.AUTHENTICATED
)
BINDING = NativeInteractionBinding(
    scope=SCOPE,
    interaction_id="interaction-native",
    activation_id="activation-native",
    activation_generation=1,
    correlation_id="correlation-native",
)
CAPABILITY = "a" * 64


def listen_event() -> NativeEngineEvent:
    return NativeEngineEvent(
        action=InteractionAction(
            action_id="action-listen-1",
            operation="LISTEN",
            interaction_id=BINDING.interaction_id,
            scope=SCOPE,
            payload=(("provider_item_id", "provider-input-1"),),
        )
    )


def activation_payload() -> dict[str, object]:
    return {
        "request_id": "activate-request-1",
        "ok": True,
        "result": {
            "status": "active",
            "replayed": False,
            "session_id": SCOPE.session_id,
            "correlation_id": BINDING.correlation_id,
            "interaction_id": BINDING.interaction_id,
            "activation_id": BINDING.activation_id,
            "activation_generation": BINDING.activation_generation,
            NATIVE_GATEWAY_DESCRIPTOR_KEY: {
                "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
                "binding": BINDING.to_dict(),
                "capability": CAPABILITY,
            },
        },
        "error": None,
        "product_composition": {"enabled": True},
    }


class FakeAgentClient:
    def __init__(self) -> None:
        self.requests: list[object] = []
        self.block = False
        self.result_override: dict[str, object] | None = None

    async def send_request(self, envelope):
        self.requests.append(envelope)
        if self.block:
            await asyncio.Future()
        if self.result_override is not None:
            result = self.result_override
        elif envelope.method == ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_CLOSE.value:
            result = {"kind": "close", "status": "closed", "accepted": True}
        elif (
            envelope.method
            == ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PRESENTATION_ACK.value
        ):
            result = {
                "kind": "presentation_ack",
                "status": "observed",
                "history_eligible": False,
            }
        else:
            result = {
                "kind": "action",
                "status": "observed",
                "accepted": True,
            }
        return AgentResponse(
            request_id=envelope.request_id,
            channel_id=envelope.channel,
            ok=True,
            payload={
                "request_id": envelope.request_id,
                "ok": True,
                "result": result,
                "error": None,
            },
        )


def observed_client(*, timeout_seconds: float = 0.2):
    agent = FakeAgentClient()
    client = GatewayNativeInteractionRuntimeClient(
        agent, timeout_seconds=timeout_seconds
    )
    sanitized = client.observe_activation_response(
        activation_payload(),
        routed_session_id=SCOPE.session_id,
        connection_id="web-connection-1",
        request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
    )
    return client, agent, sanitized


def test_internal_native_methods_are_exact_and_absent_from_browser_allowlist() -> None:
    assert NATIVE_INTERNAL_REQ_METHODS == frozenset(
        {
            "live_voice.internal.native.propose",
            "live_voice.internal.native.presentation_ack",
            "live_voice.internal.native.close",
        }
    )
    assert NATIVE_INTERNAL_REQ_METHODS.isdisjoint(app_web_handlers._FORWARD_REQ_METHODS)
    assert {
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PROPOSE.value,
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PRESENTATION_ACK.value,
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_CLOSE.value,
    } == NATIVE_INTERNAL_REQ_METHODS


@pytest.mark.asyncio
async def test_gateway_native_proposal_requires_minted_activation_capability() -> None:
    client, agent, sanitized = observed_client()
    assert NATIVE_GATEWAY_DESCRIPTOR_KEY not in sanitized["result"]

    with pytest.raises(NativeRuntimeClientError) as raised:
        await client.propose(
            binding=BINDING,
            capability="browser-value",
            event=listen_event(),
            request_id="native-propose-1",
        )

    assert raised.value.reason == "NATIVE_RUNTIME_CAPABILITY_REJECTED"
    assert agent.requests == []


@pytest.mark.asyncio
async def test_gateway_native_proposal_sends_one_closed_internal_e2a_request() -> None:
    client, agent, _sanitized = observed_client()

    result = await client.propose(
        binding=BINDING,
        capability=CAPABILITY,
        event=listen_event(),
        request_id="native-propose-1",
    )

    assert result == {"kind": "action", "status": "observed", "accepted": True}
    assert len(agent.requests) == 1
    envelope = agent.requests[0]
    assert envelope.method == ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PROPOSE.value
    assert envelope.channel == "live_voice_native_gateway"
    assert envelope.session_id == SCOPE.session_id
    assert set(envelope.params) == {
        "contract_version",
        "binding",
        "capability",
        "proposal",
    }
    assert envelope.params["capability"] == CAPABILITY


@pytest.mark.asyncio
async def test_gateway_native_timeout_has_one_request_and_no_local_replay_record() -> (
    None
):
    client, agent, _sanitized = observed_client(timeout_seconds=0.01)
    agent.block = True

    with pytest.raises(NativeRuntimeClientError) as raised:
        await client.propose(
            binding=BINDING,
            capability=CAPABILITY,
            event=listen_event(),
            request_id="native-timeout-1",
        )

    assert raised.value.reason == "NATIVE_RUNTIME_TIMEOUT"
    assert len(agent.requests) == 1
    assert client.snapshot().completed_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("request_id", ["x" * 257, "native-request\nchanged"])
async def test_gateway_native_request_identity_is_bounded_before_e2a(
    request_id: str,
) -> None:
    client, agent, _sanitized = observed_client()

    with pytest.raises(NativeRuntimeClientError) as raised:
        await client.propose(
            binding=BINDING,
            capability=CAPABILITY,
            event=listen_event(),
            request_id=request_id,
        )

    assert raised.value.reason == "NATIVE_RUNTIME_REQUEST_ID_INVALID"
    assert agent.requests == []


@pytest.mark.asyncio
async def test_gateway_native_response_result_is_closed_per_method() -> None:
    client, agent, _sanitized = observed_client()
    agent.result_override = {
        "kind": "action",
        "status": "observed",
        "accepted": True,
        "capability": CAPABILITY,
    }

    with pytest.raises(NativeRuntimeClientError) as raised:
        await client.propose(
            binding=BINDING,
            capability=CAPABILITY,
            event=listen_event(),
            request_id="native-invalid-result-1",
        )

    assert raised.value.reason == "NATIVE_RUNTIME_RESPONSE_INVALID"
    assert len(agent.requests) == 1
    assert client.snapshot().completed_requests == 0


@pytest.mark.asyncio
async def test_gateway_native_ack_and_close_use_only_closed_internal_methods() -> None:
    client, agent, _sanitized = observed_client()
    ack = PresentationAck(
        ref=ResponseRef(BINDING.interaction_id, "native-response-1", 1),
        surface=PresentationSurface.AUDIO,
        unit_id="native-audio-unit-1",
        contiguous_cursor=0,
        presented_at="2026-08-25T13:00:00Z",
    )

    await client.presentation_ack(
        binding=BINDING,
        capability=CAPABILITY,
        request_id="native-ack-1",
        ack=ack,
    )
    await client.close(
        binding=BINDING,
        capability=CAPABILITY,
        request_id="native-close-1",
    )

    assert [item.method for item in agent.requests] == [
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PRESENTATION_ACK.value,
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_CLOSE.value,
    ]
    assert set(agent.requests[0].params) == {
        "contract_version",
        "binding",
        "capability",
        "ack",
        "cursor",
        "action_id",
    }
    assert set(agent.requests[1].params) == {
        "contract_version",
        "binding",
        "capability",
    }
    assert client.snapshot().activation_count == 0
