# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib

import pytest

from jiuwenswarm.common.schema.agent import AgentResponse
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.gateway.channel_manager.web import app_web_handlers
from jiuwenswarm.gateway.live_voice import (
    native_interaction_runtime_client as client_module,
)
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import (
    NATIVE_BROWSER_DESCRIPTOR_KEY,
    NATIVE_GATEWAY_DESCRIPTOR_KEY,
    NATIVE_INTERNAL_REQ_METHODS,
    GatewayNativeInteractionRuntimeClient,
    NativeRuntimeClientError,
)
from jiuwenswarm.server.live_voice.interaction_engine import InteractionAction
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeDelegateProposal,
    NativeInteractionBinding,
    NativeInputTranscript,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    NativeAudioOutput,
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


def audio_event(sequence: int = 0) -> NativeEngineEvent:
    return NativeEngineEvent(
        audio=NativeAudioOutput(
            provider_event_id=f"provider-audio-{sequence}",
            provider_response_id="provider-response-1",
            provider_item_id="provider-assistant-item-1",
            content_index=0,
            sequence=sequence,
            pcm16=b"\x12\x34" * 480,
            response=ResponseRef(BINDING.interaction_id, "native-response-1", 1),
        )
    )


def delegate_event() -> NativeEngineEvent:
    delegate = NativeDelegateProposal(
        binding=BINDING,
        turn_id="native-turn-1",
        response_generation=1,
        provider_event_id="provider-function-event-1",
        provider_call_id="provider-call-1",
        provider_item_id="provider-function-item-1",
        request_text="Use Jiuwen safely.",
    )
    return NativeEngineEvent(
        action=InteractionAction(
            action_id="native-delegate-action-1",
            operation="DELEGATE",
            interaction_id=BINDING.interaction_id,
            scope=SCOPE,
            payload=(
                ("provider_call_id", delegate.provider_call_id),
                ("turn_id", delegate.turn_id),
            ),
        ),
        delegate=delegate,
    )


def input_transcript_event() -> NativeEngineEvent:
    return NativeEngineEvent(
        input_transcript=NativeInputTranscript(
            binding=BINDING,
            turn_id="native-turn-1",
            commit_id="native-commit-1",
            provider_session_id="provider-session-1",
            provider_item_id="provider-input-1",
            provider_event_id="provider-transcript-1",
            transcript="介绍你自己。",
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


def activation_payload_for(
    binding: NativeInteractionBinding, capability: str
) -> dict[str, object]:
    return {
        "request_id": f"activate-request-{binding.activation_generation}",
        "ok": True,
        "result": {
            "status": "active",
            "replayed": False,
            "session_id": binding.scope.session_id,
            "correlation_id": binding.correlation_id,
            "interaction_id": binding.interaction_id,
            "activation_id": binding.activation_id,
            "activation_generation": binding.activation_generation,
            NATIVE_GATEWAY_DESCRIPTOR_KEY: {
                "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
                "binding": binding.to_dict(),
                "capability": capability,
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
            cursor = envelope.params.get("cursor")
            result = (
                {
                    "kind": "response_fence",
                    "status": "observed",
                    "applied": True,
                    "cancel_command_id": envelope.params.get("action_id"),
                }
                if isinstance(cursor, dict) and cursor.get("fence_only") is True
                else {
                    "kind": "presentation_ack",
                    "status": "observed",
                    "history_eligible": False,
                }
            )
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
        agent,
        native_model="gpt-realtime-2.1-mini",
        timeout_seconds=timeout_seconds,
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


def test_gateway_native_activation_handle_is_exact_private_and_connection_bound() -> (
    None
):
    client, _agent, _sanitized = observed_client()

    activation = client.activation_for(
        session_id=SCOPE.session_id,
        interaction_id=BINDING.interaction_id,
        connection_id="web-connection-1",
    )

    assert activation is not None
    assert activation.binding == BINDING
    assert activation.capability == CAPABILITY
    assert CAPABILITY not in repr(activation)
    assert client.browser_descriptor_for(
        session_id=SCOPE.session_id,
        interaction_id=BINDING.interaction_id,
        connection_id="web-connection-1",
    ) == {
        "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
        "engine": "openai-realtime-native",
        "model": "gpt-realtime-2.1-mini",
    }
    assert (
        client.activation_for(
            session_id=SCOPE.session_id,
            interaction_id=BINDING.interaction_id,
            connection_id="web-connection-foreign",
        )
        is None
    )
    assert client.forget_connection("web-connection-1") == 1
    assert (
        client.activation_for(
            session_id=SCOPE.session_id,
            interaction_id=BINDING.interaction_id,
            connection_id="web-connection-1",
        )
        is None
    )


@pytest.mark.asyncio
async def test_stale_activation_compensation_preserves_newer_exact_capability() -> None:
    agent = FakeAgentClient()
    client = GatewayNativeInteractionRuntimeClient(
        agent,
        native_model="gpt-realtime-2.1-mini",
        timeout_seconds=0.2,
    )
    newer = NativeInteractionBinding(
        scope=SCOPE,
        interaction_id=BINDING.interaction_id,
        activation_id="activation-native-2",
        activation_generation=2,
        correlation_id="correlation-native-2",
    )
    expected_newer = client_module.GatewayNativeActivation(
        newer, "b" * 64, "web-connection-2"
    )
    client.observe_activation_response(
        activation_payload_for(newer, "b" * 64),
        routed_session_id=SCOPE.session_id,
        connection_id="web-connection-2",
        request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
    )

    with pytest.raises(NativeRuntimeClientError) as stale:
        client.observe_activation_response(
            activation_payload(),
            routed_session_id=SCOPE.session_id,
            connection_id="web-connection-1",
            request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
        )
    assert stale.value.reason == "NATIVE_RUNTIME_ACTIVATION_STALE"
    assert (
        client.activation_for(
            session_id=SCOPE.session_id,
            interaction_id=BINDING.interaction_id,
            connection_id="web-connection-2",
        )
        == expected_newer
    )

    first = await client.abort_activation_response(
        activation_payload(),
        routed_session_id=SCOPE.session_id,
        connection_id="web-connection-1",
        request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
        request_id="native-activation-aborted:old",
    )
    replay = await client.abort_activation_response(
        activation_payload(),
        routed_session_id=SCOPE.session_id,
        connection_id="web-connection-1",
        request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
        request_id="native-activation-aborted:old",
    )

    assert first == replay == {"kind": "close", "status": "closed", "accepted": True}
    assert len(agent.requests) == 2
    assert all(
        request.params["binding"] == BINDING.to_dict() for request in agent.requests
    )
    assert (
        client.activation_for(
            session_id=SCOPE.session_id,
            interaction_id=BINDING.interaction_id,
            connection_id="web-connection-2",
        )
        == expected_newer
    )


@pytest.mark.asyncio
async def test_gateway_native_proposal_requires_minted_activation_capability() -> None:
    client, agent, sanitized = observed_client()
    assert NATIVE_GATEWAY_DESCRIPTOR_KEY not in sanitized["result"]
    assert sanitized["result"][NATIVE_BROWSER_DESCRIPTOR_KEY] == {
        "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
        "engine": "openai-realtime-native",
        "model": "gpt-realtime-2.1-mini",
    }

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
async def test_gateway_accepts_ordered_user_then_assistant_chat_projection() -> None:
    client, agent, _sanitized = observed_client()
    transcript = input_transcript_event().input_transcript
    assert transcript is not None
    assistant = "我是 JiuwenSwarm。"
    digest = hashlib.sha256(assistant.encode("utf-8")).hexdigest()
    agent.result_override = {
        "kind": "input_transcript",
        "status": "observed",
        "accepted": True,
        "history": {
            "message": {
                "id": "live-voice:native-commit-1:native-user",
                "role": "user",
                "content": transcript.transcript,
                "timestamp": 1788170401.0,
            },
            "binding": {
                **BINDING.to_dict(),
                "turn_id": transcript.turn_id,
                "commit_id": transcript.commit_id,
                "provider_session_id": transcript.provider_session_id,
                "provider_item_id": transcript.provider_item_id,
                "provider_event_id": transcript.provider_event_id,
            },
            "following_assistant": [
                {
                    "turn_id": transcript.turn_id,
                    "response": {
                        "interaction_id": BINDING.interaction_id,
                        "response_id": "native-response-1",
                        "response_generation": 1,
                    },
                    "transcript": assistant,
                    "presented_at": "2026-08-31T10:00:02Z",
                    "message": {
                        "id": (
                            "live-voice:interaction-native:native-response-1:1:"
                            f"native-audio:{digest}"
                        ),
                        "role": "assistant",
                        "content": assistant,
                        "timestamp": 1788170402.0,
                    },
                }
            ],
        },
    }

    result = await client.propose(
        binding=BINDING,
        capability=CAPABILITY,
        event=input_transcript_event(),
        request_id="native-input-transcript-ordered-1",
    )

    assert result == agent.result_override

    malformed = dict(agent.result_override)
    malformed_history = dict(malformed["history"])
    malformed_following = [dict(malformed_history["following_assistant"][0])]
    malformed_following[0]["turn_id"] = "wrong-turn"
    malformed_history["following_assistant"] = malformed_following
    malformed["history"] = malformed_history
    agent.result_override = malformed
    with pytest.raises(NativeRuntimeClientError) as raised:
        await client.propose(
            binding=BINDING,
            capability=CAPABILITY,
            event=input_transcript_event(),
            request_id="native-input-transcript-ordered-2",
        )
    assert raised.value.reason == "NATIVE_RUNTIME_RESPONSE_INVALID"


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
async def test_gateway_delegate_uses_method_specific_thirty_second_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, agent, _sanitized = observed_client(timeout_seconds=0.01)
    observed_deadlines: list[float] = []

    async def capture_deadline(awaitable, *, timeout):
        observed_deadlines.append(timeout)
        return await awaitable

    monkeypatch.setattr(client_module.asyncio, "wait_for", capture_deadline)
    agent.result_override = {
        "kind": "delegate",
        "status": "completed",
        "accepted": True,
        "provider_call_id": "provider-call-1",
        "route": "dialogue",
        "turn_commit_id": "native-delegate-commit-1",
        "canonical_text": "Canonical Jiuwen result.",
        "response": {
            "interaction_id": BINDING.interaction_id,
            "response_id": "native-delegate-response-1",
            "response_generation": 2,
        },
    }

    result = await client.propose(
        binding=BINDING,
        capability=CAPABILITY,
        event=delegate_event(),
        request_id="native-delegate-deadline-1",
    )

    assert result == agent.result_override
    assert observed_deadlines == [30.0]


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
async def test_gateway_accepts_closed_runtime_audio_admission_without_pcm() -> None:
    client, agent, _sanitized = observed_client()
    agent.result_override = {
        "kind": "audio",
        "status": "observed",
        "accepted": True,
        "presentation_unit": {
            "response": {
                "interaction_id": BINDING.interaction_id,
                "response_id": "native-response-1",
                "response_generation": 1,
            },
            "surface": "audio",
            "unit_id": "native-audio-unit-1",
            "seq": 0,
            "source_start_utf8": 0,
            "source_end_utf8": 480,
            "content_ref": "sha256:" + "a" * 64,
        },
    }

    result = await client.propose(
        binding=BINDING,
        capability=CAPABILITY,
        event=audio_event(),
        request_id="native-audio-1",
    )

    assert result == agent.result_override
    proposal = agent.requests[0].params["proposal"]
    assert "audio_observation" in proposal
    assert "pcm16" not in str(proposal)


@pytest.mark.asyncio
async def test_gateway_native_audio_batch_uses_one_bounded_closed_e2a_request() -> None:
    client, agent, _sanitized = observed_client()
    items = [
        {
            "kind": "audio",
            "status": "observed",
            "accepted": True,
            "presentation_unit": {
                "response": {
                    "interaction_id": BINDING.interaction_id,
                    "response_id": "native-response-1",
                    "response_generation": 1,
                },
                "surface": "audio",
                "unit_id": f"native-audio-unit-{sequence}",
                "seq": sequence,
                "source_start_utf8": sequence * 480,
                "source_end_utf8": (sequence + 1) * 480,
                "content_ref": "sha256:" + f"{sequence + 1:064x}",
            },
        }
        for sequence in range(16)
    ]
    agent.result_override = {
        "kind": "audio_batch",
        "status": "observed",
        "items": items,
    }

    result = await client.propose_audio_batch(
        binding=BINDING,
        capability=CAPABILITY,
        events=tuple(audio_event(sequence) for sequence in range(16)),
        request_id="native-audio-batch-1",
    )

    assert result == tuple(items)
    assert len(agent.requests) == 1
    envelope = agent.requests[0]
    assert set(envelope.params) == {
        "contract_version",
        "binding",
        "capability",
        "proposals",
    }
    assert len(envelope.params["proposals"]) == 16
    assert "pcm16" not in str(envelope.params["proposals"])


@pytest.mark.asyncio
async def test_gateway_accepts_closed_native_delegate_result() -> None:
    client, agent, _sanitized = observed_client()
    agent.result_override = {
        "kind": "delegate",
        "status": "completed",
        "accepted": True,
        "provider_call_id": "provider-call-1",
        "route": "dialogue",
        "turn_commit_id": "native-delegate-commit-1",
        "canonical_text": "Canonical Jiuwen result.",
        "response": {
            "interaction_id": BINDING.interaction_id,
            "response_id": "native-delegate-response-1",
            "response_generation": 2,
        },
    }

    result = await client.propose(
        binding=BINDING,
        capability=CAPABILITY,
        event=listen_event(),
        request_id="native-delegate-result-1",
    )

    assert result == agent.result_override


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"route": "provider-selected-route"},
        {"canonical_text": "changed\ncontrol"},
        {"response": {"interaction_id": BINDING.interaction_id}},
    ],
)
async def test_gateway_rejects_malformed_native_delegate_result(
    change: dict[str, object],
) -> None:
    client, agent, _sanitized = observed_client()
    result: dict[str, object] = {
        "kind": "delegate",
        "status": "completed",
        "accepted": True,
        "provider_call_id": "provider-call-1",
        "route": "dialogue",
        "turn_commit_id": "native-delegate-commit-1",
        "canonical_text": "Canonical Jiuwen result.",
        "response": {
            "interaction_id": BINDING.interaction_id,
            "response_id": "native-delegate-response-1",
            "response_generation": 2,
        },
    }
    result.update(change)
    agent.result_override = result

    with pytest.raises(NativeRuntimeClientError) as raised:
        await client.propose(
            binding=BINDING,
            capability=CAPABILITY,
            event=listen_event(),
            request_id="native-delegate-invalid-1",
        )

    assert raised.value.reason == "NATIVE_RUNTIME_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_gateway_rejects_audio_admission_with_recoverable_audio_field() -> None:
    client, agent, _sanitized = observed_client()
    agent.result_override = {
        "kind": "audio",
        "status": "observed",
        "accepted": True,
        "presentation_unit": {
            "response": {
                "interaction_id": BINDING.interaction_id,
                "response_id": "native-response-1",
                "response_generation": 1,
            },
            "surface": "audio",
            "unit_id": "native-audio-unit-1",
            "seq": 0,
            "source_start_utf8": 0,
            "source_end_utf8": 480,
            "content_ref": "sha256:" + "a" * 64,
            "pcm16": "EjQ=",
        },
    }

    with pytest.raises(NativeRuntimeClientError) as raised:
        await client.propose(
            binding=BINDING,
            capability=CAPABILITY,
            event=audio_event(),
            request_id="native-audio-invalid-1",
        )

    assert raised.value.reason == "NATIVE_RUNTIME_RESPONSE_INVALID"


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
    await client.presentation_ack(
        binding=BINDING,
        capability=CAPABILITY,
        request_id="native-fence-1",
        fence_response=ack.ref,
        action_id="native-fence-action-1",
    )
    await client.close(
        binding=BINDING,
        capability=CAPABILITY,
        request_id="native-close-1",
    )

    assert [item.method for item in agent.requests] == [
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PRESENTATION_ACK.value,
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
        "ack",
        "cursor",
        "action_id",
    }
    assert agent.requests[1].params["cursor"] == {
        "response": {
            "interaction_id": ack.ref.interaction_id,
            "response_id": ack.ref.response_id,
            "response_generation": ack.ref.response_generation,
        },
        "fence_only": True,
    }
    assert set(agent.requests[2].params) == {
        "contract_version",
        "binding",
        "capability",
    }
    assert client.snapshot().activation_count == 0


@pytest.mark.asyncio
async def test_gateway_activation_abort_reuses_closed_native_close_variant() -> None:
    agent = FakeAgentClient()
    client = GatewayNativeInteractionRuntimeClient(
        agent,
        native_model="gpt-realtime-2.1-mini",
        timeout_seconds=0.2,
    )

    result = await client.abort_activation_response(
        activation_payload(),
        routed_session_id=SCOPE.session_id,
        connection_id="missing-web-connection",
        request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
        request_id="native-activation-aborted-1",
    )

    assert result == {"kind": "close", "status": "closed", "accepted": True}
    assert len(agent.requests) == 1
    assert agent.requests[0].method == ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_CLOSE.value
    assert agent.requests[0].params["disposition"] == "activation_aborted"
    assert client.snapshot().activation_count == 0


@pytest.mark.asyncio
async def test_gateway_accepts_exact_native_assistant_chat_projection_on_ack() -> None:
    client, agent, _sanitized = observed_client()
    response = ResponseRef(BINDING.interaction_id, "native-response-1", 1)
    transcript = "Canonical native answer."
    digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    agent.result_override = {
        "kind": "presentation_ack",
        "status": "observed",
        "history_eligible": True,
        "history": {
            "response": {
                "interaction_id": response.interaction_id,
                "response_id": response.response_id,
                "response_generation": response.response_generation,
            },
            "transcript": transcript,
            "presented_at": "2026-08-31T10:00:01.000Z",
            "message": {
                "id": (
                    "live-voice:interaction-native:native-response-1:"
                    f"1:native-audio:{digest}"
                ),
                "role": "assistant",
                "content": transcript,
                "timestamp": 1788170401.0,
            },
        },
    }
    ack = PresentationAck(
        ref=response,
        surface=PresentationSurface.AUDIO,
        unit_id="native-audio-unit-1",
        contiguous_cursor=0,
        presented_at="2026-08-31T10:00:01.000Z",
    )

    result = await client.presentation_ack(
        binding=BINDING,
        capability=CAPABILITY,
        request_id="native-assistant-projection-1",
        ack=ack,
    )

    assert result == agent.result_override
