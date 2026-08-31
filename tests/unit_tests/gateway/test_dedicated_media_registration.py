# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import replace
import base64
import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAck,
    MediaAudioFrame,
    MediaDetach,
    MediaDetachReason,
    MediaPlaybackStopOutcome,
    MediaTransportViolation,
    create_playback_stop_receipt,
    decode_audio_frame,
    deserialize_media_control,
    encode_audio_frame,
    serialize_media_control,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry,
    MEDIA_AUTH_CONTRACT_VERSION,
    MEDIA_ACTIVATE_METHOD,
    register_dedicated_media_rpc_handlers,
    handle_registered_media_socket,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaSocketLeafResult,
)
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import (
    GatewayNativeActivation,
    NativeRuntimeClientError,
)
from jiuwenswarm.gateway.live_voice import dedicated_media_registration
from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web.web_connect import (
    WebChannel,
    WebChannelConfig,
)
from jiuwenswarm.gateway.channel_manager.web import web_connect
from jiuwenswarm.server.live_voice.batch_speech import (
    RECOGNIZE_OPERATION,
    SYNTHESIZE_OPERATION,
    SpeechAuthorizationBinding,
    SpeechRpcContext,
)
from jiuwenswarm.server.live_voice.latency_measurement import L0Milestone
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeDelegateProposal,
    NativeInteractionBinding,
    NativeInputTranscript,
    NativePresentationCursor,
    NativeTurnCommit,
)
from jiuwenswarm.server.live_voice.interaction_engine import InteractionAction
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    NativeAudioOutput,
    NativeEngineEvent,
    NativeInputAudioFrame,
    NativeProviderDone,
)


ORIGIN = "https://voice.example.test"


def _params(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "session_id": "session-1",
        "interaction_id": "interaction-1",
        "correlation_id": "correlation-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
        "capture_id": "capture-1",
        "capture_generation": 0,
        "track_id": "track-1",
        "sample_rate_hz": 16_000,
        "locale": "zh-CN",
    }
    result.update(updates)
    return result


@pytest.fixture(autouse=True)
def _allowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS", "voice.example.test")


def _active_registry() -> DedicatedMediaProductRegistry:
    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    return registry


def _media_ticket(descriptor: dict[str, object]) -> str:
    assert descriptor["endpoint_path"] == "/ws/live-voice/media"
    ticket = descriptor["media_ticket"]
    assert isinstance(ticket, str)
    return ticket


def _pending_record(registry: DedicatedMediaProductRegistry, ticket: str) -> object:
    return registry._records[registry._pending_tickets[ticket]]


def _media_auth_frame(descriptor: dict[str, object]) -> str:
    return json.dumps(
        {
            "type": "media.auth",
            "contract_version": MEDIA_AUTH_CONTRACT_VERSION,
            "media_ticket": _media_ticket(descriptor),
            "binding": descriptor["binding"],
        },
        separators=(",", ":"),
    )


class _AuthOnlySocket:
    subprotocol = "live-voice.media.v1"
    request_headers = {"Origin": ORIGIN}

    def __init__(self, descriptor: dict[str, object]) -> None:
        self._auth_frame = _media_auth_frame(descriptor)

    async def recv(self) -> str:
        return self._auth_frame

    async def close(self, _code: int = 1000, _reason: str = "") -> None:
        return None


class _AutoAckDownlinkSocket:
    subprotocol = "live-voice.media.v1"
    request_headers = {"Origin": ORIGIN}

    def __init__(self, descriptor: dict[str, object]) -> None:
        self._auth_frame = _media_auth_frame(descriptor)
        binding = descriptor["binding"]
        assert isinstance(binding, dict)
        generation = binding["generation"]
        assert isinstance(generation, dict)
        self._lease_id = binding["lease_id"]
        self._generation = generation["value"]
        assert isinstance(self._lease_id, str)
        assert isinstance(self._generation, int)
        self._authenticated = False
        self.sent: list[str | bytes] = []
        self.close_calls = 0

    async def recv(self) -> str:
        if not self._authenticated:
            self._authenticated = True
            return self._auth_frame
        sent_frames = sum(isinstance(message, bytes) for message in self.sent)
        assert sent_frames > 0
        return serialize_media_control(
            MediaAck(self._lease_id, self._generation, sent_frames - 1)
        )

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    async def close(self, _code: int = 1000, _reason: str = "") -> None:
        self.close_calls += 1


def _formal_p2_manifest() -> dict[str, object]:
    return {
        "contract_version": "live-voice.product-composition.gate0.v1",
        "enabled": True,
        "routes": [
            {
                "segment": "p2.agent_interaction",
                "truth": "formal",
                "reason_id": "FORMAL_ROUTE_OBSERVED",
                "evidence_ids": [
                    "TRUSTED_AUTHORITY_RESOLVED",
                    "FORMAL_ACTIVATION_LEASE_OPEN",
                    "RUNTIME_PATH_OBSERVED",
                    "P2_NOTIFICATION_BACKPRESSURE_CLOSED",
                ],
                "formal_runtime_observed": True,
            }
        ],
    }


def _trust_product_activation(
    registry: DedicatedMediaProductRegistry,
    params: dict[str, object],
    *,
    user_id: str | None = "user-1",
    connection_id: str = "connection-1",
) -> None:
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "active",
                "session_id": params["session_id"],
                "correlation_id": params["correlation_id"],
                "interaction_id": params["interaction_id"],
                "activation_id": params["activation_id"],
                "activation_generation": params["activation_generation"],
            },
            "product_composition": _formal_p2_manifest(),
        },
        routed_session_id=str(params["session_id"]),
        user_id=user_id,
        connection_id=connection_id,
        request_method="live_voice.composition.p2.activate",
    )


def _activate(
    registry: DedicatedMediaProductRegistry,
    *,
    params: dict[str, object],
    request_origin: str | None,
    connection_id: str,
    user_id: str | None = "user-1",
) -> dict[str, object]:
    _trust_product_activation(
        registry, params, user_id=user_id, connection_id=connection_id
    )
    return registry.activate(
        params=params,
        request_origin=request_origin,
        connection_id=connection_id,
        user_id=user_id,
    )


def test_feature_off_and_provider_off_create_no_route() -> None:
    disabled = DedicatedMediaProductRegistry(enabled=False)
    assert disabled.activate(
        params={}, request_origin=None, connection_id="connection-1"
    ) == {"status": "disabled", "reason_id": "MEDIA_FEATURE_DISABLED"}

    unavailable = DedicatedMediaProductRegistry(enabled=True)
    assert unavailable.activate(
        params={}, request_origin=None, connection_id="connection-1"
    ) == {
        "status": "unavailable",
        "reason_id": "MEDIA_PROVIDER_UNAVAILABLE",
    }


def test_registry_retains_only_the_injected_native_runtime_client() -> None:
    native_client = object()

    registry = DedicatedMediaProductRegistry(
        enabled=False, native_runtime_client=native_client
    )

    assert registry.native_runtime_client is native_client
    assert DedicatedMediaProductRegistry(enabled=False).native_runtime_client is None


class _NativeActivationClient:
    def __init__(self, activation: GatewayNativeActivation | None) -> None:
        self.activation = activation
        self.lookups: list[tuple[str, str, str]] = []

    def activation_for(
        self, *, session_id: str, interaction_id: str, connection_id: str
    ) -> GatewayNativeActivation | None:
        self.lookups.append((session_id, interaction_id, connection_id))
        activation = self.activation
        if (
            activation is None
            or activation.binding.scope.session_id != session_id
            or activation.binding.interaction_id != interaction_id
            or activation.connection_id != connection_id
        ):
            return None
        return activation

    def browser_descriptor_for(
        self, *, session_id: str, interaction_id: str, connection_id: str
    ) -> dict[str, str] | None:
        if (
            self.activation_for(
                session_id=session_id,
                interaction_id=interaction_id,
                connection_id=connection_id,
            )
            is None
        ):
            return None
        return {
            "contract_version": "live-voice.native-interaction.v1",
            "engine": "openai-realtime-native",
            "model": "gpt-realtime-2.1-mini",
        }


class _FakeNativeRuntimeClient(_NativeActivationClient):
    def __init__(self, activation: GatewayNativeActivation) -> None:
        super().__init__(activation)
        self.proposals: list[NativeEngineEvent] = []
        self.audio_batches: list[tuple[NativeEngineEvent, ...]] = []
        self.audio_proposed = asyncio.Event()
        self.audio_sample_cursors: dict[ResponseRef, int] = {}
        self.playback_actions: list[tuple[str, object]] = []
        self.close_calls = 0
        self.close_request_ids: list[str] = []
        self.input_transcript_items: set[str] = set()
        self.input_transcript_following_assistant: list[dict[str, object]] = []
        self.presentation_history: dict[str, object] | None = None
        self.presentation_ack_error: Exception | None = None
        self.presentation_ack_result: dict[str, object] | None = None

    async def propose(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        event: NativeEngineEvent,
        request_id: str,
    ) -> dict[str, object]:
        assert self.activation is not None
        assert binding == self.activation.binding
        assert capability == self.activation.capability
        assert request_id
        self.proposals.append(event)
        if event.input_transcript is not None:
            transcript = event.input_transcript
            accepted = transcript.provider_item_id not in self.input_transcript_items
            self.input_transcript_items.add(transcript.provider_item_id)
            history: dict[str, object] = {
                "message": {
                    "id": f"live-voice:{transcript.commit_id}:native-user",
                    "role": "user",
                    "content": transcript.transcript,
                    "timestamp": 1788170401.0,
                },
                "binding": {
                    **binding.to_dict(),
                    "turn_id": transcript.turn_id,
                    "commit_id": transcript.commit_id,
                    "provider_session_id": transcript.provider_session_id,
                    "provider_item_id": transcript.provider_item_id,
                    "provider_event_id": transcript.provider_event_id,
                },
            }
            if self.input_transcript_following_assistant:
                history["following_assistant"] = list(
                    self.input_transcript_following_assistant
                )
            return {
                "kind": "input_transcript",
                "status": "observed",
                "accepted": accepted,
                "history": history,
            }
        if event.turn_commit is not None:
            return {"kind": "turn", "status": "observed", "accepted": True}
        if event.action is not None and event.action.operation == "SPEAK":
            provider_response_id = dict(event.action.payload)["provider_response_id"]
            return {
                "kind": "response",
                "status": "observed",
                "accepted": True,
                "provider_response_id": provider_response_id,
                "response": {
                    "interaction_id": binding.interaction_id,
                    "response_id": "native-response-1",
                    "response_generation": 1,
                },
            }
        if event.audio is not None:
            output = event.audio
            sample_count = (
                len(output.pcm16) // 2
                if output.provider_sample_count is None
                else output.provider_sample_count
            )
            source_start = self.audio_sample_cursors.get(output.response, 0)
            source_end = source_start + sample_count
            self.audio_sample_cursors[output.response] = source_end
            result = {
                "kind": "audio",
                "status": "observed",
                "accepted": True,
                "presentation_unit": {
                    "response": {
                        "interaction_id": output.response.interaction_id,
                        "response_id": output.response.response_id,
                        "response_generation": output.response.response_generation,
                    },
                    "surface": "audio",
                    "unit_id": f"native-audio-unit-{output.sequence}",
                    "seq": output.sequence,
                    "source_start_utf8": source_start,
                    "source_end_utf8": source_end,
                    "content_ref": f"sha256:{hashlib.sha256(output.pcm16).hexdigest()}",
                },
            }
            self.audio_proposed.set()
            return result
        if event.provider_done is not None:
            return {"kind": "done", "status": "observed", "accepted": True}
        if event.delegate is not None:
            return {
                "kind": "delegate",
                "status": "completed",
                "accepted": True,
                "provider_call_id": event.delegate.provider_call_id,
                "route": "dialogue",
                "turn_commit_id": "native-delegate-commit-1",
                "canonical_text": "Canonical Jiuwen result.",
                "response": {
                    "interaction_id": binding.interaction_id,
                    "response_id": "native-delegate-response-1",
                    "response_generation": event.delegate.response_generation + 1,
                },
            }
        return {"kind": "action", "status": "observed", "accepted": True}

    async def propose_audio_batch(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        events: tuple[NativeEngineEvent, ...],
        request_id: str,
    ) -> tuple[dict[str, object], ...]:
        assert events
        self.audio_batches.append(events)
        return tuple(
            [
                await self.propose(
                    binding=binding,
                    capability=capability,
                    event=event,
                    request_id=f"{request_id}:{ordinal}",
                )
                for ordinal, event in enumerate(events)
            ]
        )

    async def presentation_ack(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        request_id: str,
        ack: object = None,
        cursor: NativePresentationCursor | None = None,
        fence_response: ResponseRef | None = None,
        action_id: str | None = None,
    ) -> dict[str, object]:
        assert self.activation is not None
        assert binding == self.activation.binding
        assert capability == self.activation.capability
        assert request_id
        if ack is not None:
            assert cursor is None and fence_response is None and action_id is None
            self.playback_actions.append(("presentation", ack))
            if self.presentation_ack_error is not None:
                raise self.presentation_ack_error
            if self.presentation_ack_result is not None:
                return dict(self.presentation_ack_result)
            result: dict[str, object] = {
                "kind": "presentation_ack",
                "status": "observed",
                "history_eligible": self.presentation_history is not None,
            }
            if self.presentation_history is not None:
                result["history"] = self.presentation_history
            return result
        assert action_id is not None
        if fence_response is not None:
            assert cursor is None
            self.playback_actions.append(("runtime_fence", fence_response))
            return {
                "kind": "response_fence",
                "status": "observed",
                "applied": True,
                "cancel_command_id": action_id,
            }
        assert cursor is not None
        self.playback_actions.append(("runtime", cursor))
        return {
            "kind": "played_cursor",
            "status": "observed",
            "applied": True,
            "cancel_command_id": action_id,
        }

    async def close(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        request_id: str,
    ) -> dict[str, object]:
        assert self.activation is not None
        assert binding == self.activation.binding
        assert capability == self.activation.capability
        assert request_id
        self.close_calls += 1
        self.close_request_ids.append(request_id)
        return {"kind": "close", "status": "closed", "accepted": True}


class _BargeRaceNativeRuntimeClient(_FakeNativeRuntimeClient):
    def __init__(self, activation: GatewayNativeActivation) -> None:
        super().__init__(activation)
        self.late_audio_entered = asyncio.Event()
        self.release_late_audio = asyncio.Event()

    async def propose(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        event: NativeEngineEvent,
        request_id: str,
    ) -> dict[str, object]:
        if event.audio is not None and event.audio.sequence == 1:
            assert self.activation is not None
            assert binding == self.activation.binding
            assert capability == self.activation.capability
            assert request_id
            self.proposals.append(event)
            self.late_audio_entered.set()
            await self.release_late_audio.wait()
            raise NativeRuntimeClientError(
                "NATIVE_AUDIO_RESPONSE_STALE",
                "response was fenced while the proposal was in flight",
            )
        return await super().propose(
            binding=binding,
            capability=capability,
            event=event,
            request_id=request_id,
        )


class _BlockedAudioNativeRuntimeClient(_FakeNativeRuntimeClient):
    def __init__(self, activation: GatewayNativeActivation) -> None:
        super().__init__(activation)
        self.blocked_audio_entered = asyncio.Event()
        self.release_blocked_audio = asyncio.Event()
        self.stop_proposed = asyncio.Event()

    async def propose(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        event: NativeEngineEvent,
        request_id: str,
    ) -> dict[str, object]:
        if event.audio is not None and event.audio.sequence == 1:
            self.blocked_audio_entered.set()
            await self.release_blocked_audio.wait()
        if event.action is not None and event.action.operation == "STOP":
            self.stop_proposed.set()
        return await super().propose(
            binding=binding,
            capability=capability,
            event=event,
            request_id=request_id,
        )


class _FirstAudioBlockedNativeRuntimeClient(_FakeNativeRuntimeClient):
    def __init__(self, activation: GatewayNativeActivation) -> None:
        super().__init__(activation)
        self.first_audio_entered = asyncio.Event()
        self.release_first_audio = asyncio.Event()
        self._blocked = False

    async def propose(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        event: NativeEngineEvent,
        request_id: str,
    ) -> dict[str, object]:
        if event.audio is not None and not self._blocked:
            self._blocked = True
            self.first_audio_entered.set()
            await self.release_first_audio.wait()
        return await super().propose(
            binding=binding,
            capability=capability,
            event=event,
            request_id=request_id,
        )


class _FailOnceNativeRuntimeCloseClient(_FakeNativeRuntimeClient):
    async def close(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        request_id: str,
    ) -> dict[str, object]:
        assert self.activation is not None
        assert binding == self.activation.binding
        assert capability == self.activation.capability
        assert request_id
        self.close_calls += 1
        self.close_request_ids.append(request_id)
        if self.close_calls == 1:
            raise OSError("transient Runtime close failure")
        return {"kind": "close", "status": "closed", "accepted": True}


class _MultiActivationNativeRuntimeClient(_FakeNativeRuntimeClient):
    def __init__(self, activation: GatewayNativeActivation) -> None:
        super().__init__(activation)
        self.activations = [activation]

    def activation_for(
        self, *, session_id: str, interaction_id: str, connection_id: str
    ) -> GatewayNativeActivation | None:
        self.lookups.append((session_id, interaction_id, connection_id))
        return next(
            (
                activation
                for activation in self.activations
                if activation.binding.scope.session_id == session_id
                and activation.binding.interaction_id == interaction_id
                and activation.connection_id == connection_id
            ),
            None,
        )

    async def close(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        request_id: str,
    ) -> dict[str, object]:
        assert any(
            activation.binding == binding and activation.capability == capability
            for activation in self.activations
        )
        assert request_id
        self.close_calls += 1
        self.close_request_ids.append(request_id)
        return {"kind": "close", "status": "closed", "accepted": True}


class _FakeNativeEngine:
    def __init__(self) -> None:
        self.events: asyncio.Queue[NativeEngineEvent | BaseException] = asyncio.Queue()
        self.offered_audio: list[NativeInputAudioFrame] = []
        self.started = False
        self.closed = False
        self.close_event = asyncio.Event()
        self.response_admitted = asyncio.Event()
        self.admissions: list[tuple[str, ResponseRef]] = []
        self.playback_actions: list[tuple[str, object]] = []
        self.presentation_acknowledgements: list[ResponseRef] = []
        self.delegate_results: list[tuple[str, ResponseRef, str]] = []
        self.delegate_result_sent = asyncio.Event()

    async def start(self) -> None:
        self.started = True

    async def offer_audio(self, frame: NativeInputAudioFrame) -> str:
        self.offered_audio.append(frame)
        return f"provider-input-{frame.seq}"

    async def next_event(self) -> NativeEngineEvent:
        retained = await self.events.get()
        if isinstance(retained, BaseException):
            raise retained
        return retained

    async def admit_response(
        self, provider_response_id: str, response: ResponseRef
    ) -> bool:
        self.admissions.append((provider_response_id, response))
        self.response_admitted.set()
        return True

    async def close(self) -> bool:
        self.closed = True
        self.close_event.set()
        return True

    async def cancel_response(
        self, cursor: NativePresentationCursor
    ) -> tuple[str, str]:
        self.playback_actions.append(("provider", cursor))
        return ("provider-cancel-1", "provider-truncate-1")

    async def fence_response(self, response: ResponseRef) -> bool:
        self.playback_actions.append(("provider_fence", response))
        return True

    async def acknowledge_presentation(self, response: ResponseRef) -> bool:
        self.presentation_acknowledgements.append(response)
        return True

    async def send_delegate_result(
        self, call_id: str, response: ResponseRef, output: str
    ) -> tuple[str, str]:
        self.delegate_results.append((call_id, response, output))
        self.delegate_result_sent.set()
        return ("provider-output-event-1", "provider-response-create-1")


class _IncompleteNativeEngine(_FakeNativeEngine):
    send_delegate_result = None


class _RetainedCloseNativeEngine(_FakeNativeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0

    async def close(self) -> bool:
        self.close_calls += 1
        complete = self.close_calls >= 2
        self.closed = complete
        if complete:
            self.close_event.set()
        return complete


class _CountingCloseNativeEngine(_FakeNativeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0

    async def close(self) -> bool:
        self.close_calls += 1
        return await super().close()


class _StartFailureRetainedCloseNativeEngine(_RetainedCloseNativeEngine):
    async def start(self) -> None:
        self.started = True
        raise OSError("Provider negotiation failed")


def _native_activation() -> GatewayNativeActivation:
    return GatewayNativeActivation(
        binding=NativeInteractionBinding(
            scope=ScopeRef(
                "subject-native", None, "session-1", Assurance.AUTHENTICATED
            ),
            interaction_id="interaction-1",
            activation_id="activation-1",
            activation_generation=1,
            correlation_id="correlation-1",
        ),
        capability="a" * 64,
        connection_id="connection-1",
    )


@pytest.mark.asyncio
async def test_native_engine_missing_delegate_result_is_rejected_before_start() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _IncompleteNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None

    try:
        with pytest.raises(MediaTransportViolation) as rejected:
            await registry.begin_native_interaction(uplink)
        assert rejected.value.reason_id == "MEDIA_NATIVE_PROVIDER_UNAVAILABLE"
        assert engine.started is False
        assert registry._native_sessions == {}
    finally:
        await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_start_failure_retains_incomplete_provider_close_owner() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _StartFailureRetainedCloseNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None

    with pytest.raises(MediaTransportViolation) as rejected:
        await registry.begin_native_interaction(uplink)

    assert rejected.value.reason_id == "MEDIA_NATIVE_PROVIDER_START_FAILED"
    assert engine.close_calls == 1
    assert uplink.record_id in registry._native_session_keys_by_record
    assert len(registry._native_sessions) == 1
    assert await registry.close_native_interaction(uplink) is True
    assert engine.close_calls == 2
    assert registry._native_sessions == {}
    assert registry._native_session_keys_by_record == {}


async def _present_native_test_audio_unit(
    registry: DedicatedMediaProductRegistry,
    client: _FakeNativeRuntimeClient,
    engine: _FakeNativeEngine,
    uplink: object,
    activated: dict[str, object],
    *,
    sequence: int,
) -> tuple[dict[str, object], dict[str, object]]:
    client.audio_proposed.clear()
    response = ResponseRef("interaction-1", f"native-response-{sequence}", sequence + 1)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id=f"provider-audio-{sequence}",
                provider_response_id=f"provider-response-{sequence}",
                provider_item_id=f"provider-item-{sequence}",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=response,
            )
        )
    )
    await asyncio.wait_for(client.audio_proposed.wait(), timeout=1.0)
    notification = registry.take_native_notification(
        session_id="session-1",
        interaction_id="interaction-1",
        connection_id="connection-1",
    )
    assert notification is not None
    audio = notification["audio"]
    assert isinstance(audio, dict)
    downlink = registry.consume_ticket(_media_ticket(audio), request_origin=ORIGIN)
    assert downlink is not None
    source = downlink.downlink_stream_source
    assert source is not None
    await engine.events.put(
        NativeEngineEvent(
            provider_done=NativeProviderDone(
                provider_event_id=f"provider-done-{sequence}",
                provider_response_id=f"provider-response-{sequence}",
                response=response,
                completed=True,
                transcript=None,
                transcript_event_id=None,
            )
        )
    )
    frames = [frame async for frame in source]
    registry.mark_downlink_started(downlink)
    frame_count = len(frames)
    assert registry.complete_downlink(
        downlink,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=0,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
            sent_frames=frame_count,
            acknowledged_through_seq=frame_count - 1,
            playback_stop_receipts=0,
            configured_max_pending_frames=8,
            configured_max_pending_bytes=131_072,
            peak_pending_frames=1,
            peak_pending_bytes=2_000,
        ),
    )
    presentation_unit = notification["presentation_unit"]
    assert isinstance(presentation_unit, dict)
    params: dict[str, object] = {
        "session_id": "session-1",
        "subject_id": activated["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "response_id": response.response_id,
        "response_generation": response.response_generation,
        "unit_id": presentation_unit["unit_id"],
        "capture_frames_acked": uplink.accepted_frames,
        "rendered_chunks": frame_count,
        "rendered_through_seq": frame_count - 1,
        "playout_queue_capacity": 256,
        "playout_peak_depth": 1,
        "capture_control_ack": "capture_flush_acked",
        "playout_state": "render_completed",
    }
    receipt = registry.acknowledge_playout(
        params=params,
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )
    assert await registry.acknowledge_native_playout(
        receipt=receipt,
        routed_session_id="session-1",
        connection_id="connection-1",
    )
    return params, receipt


def test_native_media_activation_skips_cascade_speech_and_binds_private_handle() -> (
    None
):
    client = _NativeActivationClient(_native_activation())
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
    )
    params = _params(sample_rate_hz=24_000)
    _trust_product_activation(registry, params, connection_id="connection-1")

    activated = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )

    assert activated["status"] == "active"
    assert activated["native_interaction"] == {
        "contract_version": "live-voice.native-interaction.v1",
        "engine": "openai-realtime-native",
        "model": "gpt-realtime-2.1-mini",
    }
    record = _pending_record(registry, _media_ticket(activated))
    assert record.native_activation == _native_activation()
    assert client.lookups == [
        ("session-1", "interaction-1", "connection-1"),
        ("session-1", "interaction-1", "connection-1"),
    ]


def test_native_media_activation_without_exact_private_handle_has_zero_route() -> None:
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=_NativeActivationClient(None),
    )
    params = _params(sample_rate_hz=24_000)
    _trust_product_activation(registry, params, connection_id="connection-1")

    with pytest.raises(MediaTransportViolation) as raised:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
        )

    assert raised.value.reason_id == "MEDIA_NATIVE_ACTIVATION_UNAVAILABLE"
    assert registry._records == {}
    assert registry._pending_tickets == {}


@pytest.mark.asyncio
async def test_native_continuous_uplink_crosses_browser_retention_bound_and_fences_duplicate() -> (
    None
):
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)

    for sequence in range(1_501):
        registry.accept_native_frame(
            uplink,
            MediaAudioFrame(
                seq=sequence,
                sample_cursor=sequence * 480,
                samples=(0.0,) * 480,
            ),
        )
        if sequence % 100 == 99:
            await asyncio.sleep(0)

    async def wait_for_input_drain() -> None:
        while len(engine.offered_audio) < 1_501:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_input_drain(), timeout=1.0)
    with pytest.raises(MediaTransportViolation) as duplicate:
        registry.accept_native_frame(
            uplink,
            MediaAudioFrame(
                seq=1_500,
                sample_cursor=1_500 * 480,
                samples=(0.0,) * 480,
            ),
        )

    assert duplicate.value.reason_id == "MEDIA_NATIVE_INPUT_FENCE_REJECTED"
    assert "sequence_mismatch:incoming=1500:expected=1501" in str(duplicate.value)
    assert uplink.accepted_frames == 1_501
    assert len(engine.offered_audio) == 1_501
    assert client.proposals == []
    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_audio_reuses_uplink_session_and_allocates_fenced_downlink() -> (
    None
):
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda binding: (
            engine if binding == activation_handle.binding else None
        ),
    )
    params = _params(sample_rate_hz=24_000)
    activated = _activate(
        registry,
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None

    await registry.begin_native_interaction(uplink)
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 480),
    )
    await engine.events.put(
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-speak-1",
                operation="SPEAK",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(("provider_response_id", "provider-response-1"),),
            )
        )
    )
    await engine.response_admitted.wait()
    response = engine.admissions[0][1]
    pcm16 = b"\x01\x00" * 480
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-1",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=0,
                pcm16=pcm16,
                response=response,
            )
        )
    )
    await client.audio_proposed.wait()
    notification_response = registry.take_native_notification_response(
        request_id="browser-notification-1",
        session_id="session-1",
        correlation_id="correlation-1",
        interaction_id="interaction-1",
        activation_id="activation-1",
        activation_generation=1,
        connection_id="connection-1",
        notification_sequence=1,
    )

    assert notification_response is not None
    assert notification_response["request_id"] == "browser-notification-1"
    assert notification_response["ok"] is True
    assert notification_response["error"] is None
    assert notification_response["product_composition"] == _formal_p2_manifest()
    notification = notification_response["result"]
    assert notification is not None
    assert engine.started is True
    assert len(engine.offered_audio) == 1
    assert uplink.accepted_frames == 1
    assert engine.offered_audio[0].seq == 0
    assert engine.offered_audio[0].sample_cursor == 0
    assert notification["kind"] == "native.audio"
    assert notification["response"] == {
        "interaction_id": response.interaction_id,
        "response_id": response.response_id,
        "response_generation": response.response_generation,
    }
    audio = notification["audio"]
    assert audio["delivery"] == "dedicated_media_downlink"
    assert audio["streaming"] is True
    assert audio["frame_count"] is None
    downlink = registry.consume_ticket(_media_ticket(audio), request_origin=ORIGIN)
    assert downlink is not None
    assert downlink.binding.direction.value == "downlink"
    assert downlink.downlink_frames == ()
    source = downlink.downlink_stream_source
    assert source is not None
    await engine.events.put(
        NativeEngineEvent(
            provider_done=NativeProviderDone(
                provider_event_id="provider-done-1",
                provider_response_id="provider-response-1",
                response=response,
                completed=True,
                transcript=None,
                transcript_event_id=None,
            )
        )
    )
    frames = [frame async for frame in source]
    assert len(frames) == 1
    assert dedicated_media_registration._pcm16(frames[0].samples) == pcm16
    assert source.completed is True
    assert all(proposal.delegate is None for proposal in client.proposals)
    assert sum(proposal.provider_done is not None for proposal in client.proposals) == 1
    await registry.close_native_interaction(uplink)


def test_native_notification_interception_cannot_steal_forwarded_agent_sequence() -> (
    None
):
    registry = DedicatedMediaProductRegistry(enabled=True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")
    queue_owner: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    queue_owner.put_nowait(
        {
            "status": "notification",
            "kind": "native.audio",
            "request_id": "provider-native-audio-1",
        }
    )
    registry._native_notifications[
        ("session-1", "interaction-1", "connection-1")
    ] = queue_owner
    binding = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
        "connection_id": "connection-1",
    }

    assert registry.mark_native_notification_forwarded(
        request_id="agent-notification-1",
        notification_sequence=1,
        **binding,
    )
    _trust_product_activation(registry, params, connection_id="connection-1")
    assert (
        registry.take_native_notification_response(
            request_id="agent-notification-1",
            notification_sequence=1,
            **binding,
        )
        is None
    )
    assert queue_owner.qsize() == 1

    local = registry.take_native_notification_response(
        request_id="local-notification-2",
        notification_sequence=2,
        **binding,
    )
    assert local is not None
    assert local["request_id"] == "local-notification-2"
    assert local["result"]["request_id"] == "local-notification-2"
    assert queue_owner.qsize() == 0

    assert (
        registry.take_native_notification_response(
            request_id="local-notification-2",
            notification_sequence=2,
            **binding,
        )
        == local
    )
    assert queue_owner.qsize() == 0

    assert (
        registry.take_native_notification_response(
            request_id="agent-notification-2",
            notification_sequence=2,
            **binding,
        )
        is None
    )
    assert registry.mark_native_notification_forwarded(
        request_id="agent-notification-2",
        notification_sequence=2,
        **binding,
    )


def test_native_notification_fence_rejects_cross_activation_binding() -> None:
    registry = DedicatedMediaProductRegistry(enabled=True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")
    queue_owner: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    queue_owner.put_nowait({"status": "notification", "kind": "native.audio"})
    registry._native_notifications[
        ("session-1", "interaction-1", "connection-1")
    ] = queue_owner

    assert (
        registry.take_native_notification_response(
            request_id="foreign-notification-1",
            session_id="session-1",
            correlation_id="correlation-1",
            interaction_id="interaction-1",
            activation_id="foreign-activation",
            activation_generation=1,
            connection_id="connection-1",
            notification_sequence=1,
        )
        is None
    )
    assert queue_owner.qsize() == 1


def test_notification_sequence_gap_permanently_disables_local_projection() -> None:
    registry = DedicatedMediaProductRegistry(enabled=True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")
    binding = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
        "connection_id": "connection-1",
    }

    assert not registry.mark_native_notification_forwarded(
        request_id="gap-notification-2",
        notification_sequence=2,
        **binding,
    )
    assert registry.mark_native_notification_forwarded(
        request_id="agent-notification-1",
        notification_sequence=1,
        **binding,
    )
    queue_owner: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    queue_owner.put_nowait({"status": "notification", "kind": "native.audio"})
    registry._native_notifications[
        ("session-1", "interaction-1", "connection-1")
    ] = queue_owner

    assert (
        registry.take_native_notification_response(
            request_id="gap-notification-2",
            notification_sequence=2,
            **binding,
        )
        is None
    )
    assert queue_owner.qsize() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("with_following_assistant", [False, True])
async def test_native_user_transcript_uses_existing_notification_queue_once(
    with_following_assistant: bool,
) -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    assistant_transcript = "我是 JiuwenSwarm。"
    assistant_response = {
        "interaction_id": "interaction-1",
        "response_id": "native-response-1",
        "response_generation": 1,
    }
    assistant_message = {
        "id": (
            "live-voice:interaction-1:native-response-1:1:native-audio:"
            + hashlib.sha256(assistant_transcript.encode("utf-8")).hexdigest()
        ),
        "role": "assistant",
        "content": assistant_transcript,
        "timestamp": 1788170402.0,
    }
    if with_following_assistant:
        client.input_transcript_following_assistant = [
            {
                "turn_id": "native-turn-1",
                "response": assistant_response,
                "transcript": assistant_transcript,
                "presented_at": "2026-08-31T10:00:02Z",
                "message": assistant_message,
            }
        ]
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    transcript = NativeInputTranscript(
        binding=activation_handle.binding,
        turn_id="native-turn-1",
        commit_id="native-commit-1",
        provider_session_id="provider-session-1",
        provider_item_id="provider-user-item-1",
        provider_event_id="provider-user-transcript-1",
        transcript="介绍你自己。",
    )
    event = NativeEngineEvent(input_transcript=transcript)
    await engine.events.put(event)

    async def wait_for_proposal() -> None:
        while not any(item.input_transcript is not None for item in client.proposals):
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_proposal(), timeout=1.0)
    response = registry.take_native_notification_response(
        request_id="browser-native-user-transcript-1",
        session_id="session-1",
        correlation_id="correlation-1",
        interaction_id="interaction-1",
        activation_id="activation-1",
        activation_generation=1,
        connection_id="connection-1",
        notification_sequence=1,
    )

    assert response is not None and response["ok"] is True
    notification = response["result"]
    assert notification == {
        "status": "notification",
        "kind": "native.user_transcript",
        "request_id": "browser-native-user-transcript-1",
        "round_id": None,
        "response": None,
        "agent_event": {
            "event_type": "chat.final",
            "message": {
                "id": "live-voice:native-commit-1:native-user",
                "role": "user",
                "content": "介绍你自己。",
                "timestamp": 1788170401.0,
            },
            "binding": {
                **activation_handle.binding.to_dict(),
                "turn_id": "native-turn-1",
                "commit_id": "native-commit-1",
                "provider_session_id": "provider-session-1",
                "provider_item_id": "provider-user-item-1",
                "provider_event_id": "provider-user-transcript-1",
            },
            **(
                {
                    "following_assistant": [
                        {
                            "message": assistant_message,
                            "binding": {
                                "turn_id": "native-turn-1",
                                "response": assistant_response,
                                "surface": "native_audio",
                                "presented_at": "2026-08-31T10:00:02Z",
                            },
                        }
                    ]
                }
                if with_following_assistant
                else {}
            ),
        },
        "source_event": None,
        "progress_event": None,
        "presentation_unit": None,
        "audio": None,
        "error_reason": None,
        "publish_seq": None,
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }

    await engine.events.put(event)

    async def wait_for_replay() -> None:
        while (
            len(
                [item for item in client.proposals if item.input_transcript is not None]
            )
            < 2
        ):
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_replay(), timeout=1.0)
    assert (
        registry.take_native_notification(
            session_id="session-1",
            interaction_id="interaction-1",
            connection_id="connection-1",
        )
        is None
    )
    await registry.close_native_interaction(uplink)
    assert engine.closed is True


@pytest.mark.asyncio
async def test_native_three_second_response_reuses_one_route_and_acks_last_runtime_unit() -> (
    None
):
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=48_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.0,) * 960),
    )
    response = ResponseRef("interaction-1", "native-response-1", 1)
    transcript = "Canonical native answer."
    transcript_digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    client.presentation_history = {
        "response": {
            "interaction_id": response.interaction_id,
            "response_id": response.response_id,
            "response_generation": response.response_generation,
        },
        "transcript": transcript,
        "presented_at": "2026-08-31T10:00:01.000Z",
        "message": {
            "id": (
                "live-voice:interaction-1:native-response-1:"
                f"1:native-audio:{transcript_digest}"
            ),
            "role": "assistant",
            "content": transcript,
            "timestamp": 1788170401.0,
        },
    }
    for sequence in range(150):
        await engine.events.put(
            NativeEngineEvent(
                audio=NativeAudioOutput(
                    provider_event_id=f"provider-audio-stream-{sequence}",
                    provider_response_id="provider-response-stream-1",
                    provider_item_id="provider-item-stream-1",
                    content_index=0,
                    sequence=sequence,
                    pcm16=sequence.to_bytes(2, "little") * 480,
                    response=response,
                )
            )
        )
    await asyncio.wait_for(client.audio_proposed.wait(), timeout=1.0)
    notification = registry.take_native_notification(
        session_id="session-1",
        interaction_id="interaction-1",
        connection_id="connection-1",
    )
    assert notification is not None
    audio_descriptor = notification["audio"]
    assert isinstance(audio_descriptor, dict)
    assert audio_descriptor["streaming"] is True
    assert audio_descriptor["frame_count"] is None
    downlink = _pending_record(registry, _media_ticket(audio_descriptor))
    source = downlink.downlink_stream_source
    assert source is not None
    await engine.events.put(
        NativeEngineEvent(
            provider_done=NativeProviderDone(
                provider_event_id="provider-done-stream-1",
                provider_response_id="provider-response-stream-1",
                response=response,
                completed=True,
                transcript=transcript,
                transcript_event_id="provider-transcript-presentation-1",
            )
        )
    )

    socket = _AutoAckDownlinkSocket(audio_descriptor)
    assert await asyncio.wait_for(
        handle_registered_media_socket(
            registry,
            socket,
            str(audio_descriptor["endpoint_path"]),
        ),
        timeout=5.0,
    )

    sent_binary = [message for message in socket.sent if isinstance(message, bytes)]
    frames = [decode_audio_frame(downlink.binding, message) for message in sent_binary]
    assert [frame.seq for frame in frames] == list(range(150))
    assert socket.close_calls == 1
    assert source.peak_buffered_frames <= 8
    assert (
        registry.take_native_notification(
            session_id="session-1",
            interaction_id="interaction-1",
            connection_id="connection-1",
        )
        is None
    )
    assert (
        sum(
            record.native_session_key is not None
            and record.binding.direction.value == "downlink"
            for record in registry._records.values()
        )
        == 1
    )
    assert downlink.downlink_content_sha256 == source.content_sha256
    presentation_unit = notification["presentation_unit"]
    assert isinstance(presentation_unit, dict)
    params = {
        "session_id": "session-1",
        "subject_id": activated["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "response_id": response.response_id,
        "response_generation": response.response_generation,
        "unit_id": presentation_unit["unit_id"],
        "capture_frames_acked": 1,
        "rendered_chunks": 150,
        "rendered_through_seq": 149,
        "playout_queue_capacity": 256,
        "playout_peak_depth": 8,
        "capture_control_ack": "capture_flush_acked",
        "playout_state": "render_completed",
    }
    receipt = registry.acknowledge_playout(
        params=params,
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )

    projected_receipt = await registry.acknowledge_native_playout(
        receipt=receipt,
        routed_session_id="session-1",
        connection_id="connection-1",
    )
    assert projected_receipt == {
        **receipt,
        "chat_projection": {
            "message": client.presentation_history["message"],
            "binding": {
                "response": client.presentation_history["response"],
                "surface": "native_audio",
                "presented_at": client.presentation_history["presented_at"],
            },
        },
    }
    presentation = client.playback_actions[-1]
    assert presentation[0] == "presentation"
    assert presentation[1].unit_id == "native-audio-unit-149"
    assert presentation[1].contiguous_cursor == 149
    assert (
        len([proposal for proposal in client.proposals if proposal.audio is not None])
        == 150
    )
    assert client.audio_batches
    assert all(1 < len(batch) <= 16 for batch in client.audio_batches)
    assert sum(len(batch) for batch in client.audio_batches) == 149
    assert all(
        proposal.turn_commit is None and proposal.delegate is None
        for proposal in client.proposals
    )
    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_delivery_splits_audio_batches_at_response_and_item_boundaries() -> (
    None
):
    activation_handle = _native_activation()
    client = _FirstAudioBlockedNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    first_response = ResponseRef("interaction-1", "native-response-first", 1)
    second_response = ResponseRef("interaction-1", "native-response-second", 2)

    def audio_event(
        *,
        response: ResponseRef,
        provider_response_id: str,
        provider_item_id: str,
        content_index: int,
        sequence: int,
    ) -> NativeEngineEvent:
        return NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id=f"provider-audio-{provider_item_id}-{sequence}",
                provider_response_id=provider_response_id,
                provider_item_id=provider_item_id,
                content_index=content_index,
                sequence=sequence,
                pcm16=sequence.to_bytes(2, "little") * 480,
                response=response,
            )
        )

    await engine.events.put(
        audio_event(
            response=first_response,
            provider_response_id="provider-response-first",
            provider_item_id="provider-item-first",
            content_index=0,
            sequence=0,
        )
    )
    await asyncio.wait_for(client.first_audio_entered.wait(), timeout=1.0)
    for sequence in (1, 2):
        engine.events.put_nowait(
            audio_event(
                response=first_response,
                provider_response_id="provider-response-first",
                provider_item_id="provider-item-first",
                content_index=0,
                sequence=sequence,
            )
        )
    for sequence in range(3):
        engine.events.put_nowait(
            audio_event(
                response=second_response,
                provider_response_id="provider-response-second",
                provider_item_id="provider-item-second-a",
                content_index=0,
                sequence=sequence,
            )
        )
    for sequence in range(3, 6):
        engine.events.put_nowait(
            audio_event(
                response=second_response,
                provider_response_id="provider-response-second",
                provider_item_id="provider-item-second-b",
                content_index=1,
                sequence=sequence,
            )
        )
    engine.events.put_nowait(
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-silence-after-audio-boundaries",
                operation="SILENCE",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
            )
        )
    )
    session = next(iter(registry._native_sessions.values()))

    async def wait_for_ordered_boundary() -> None:
        while engine.events.qsize() > 0:
            await asyncio.sleep(0)
        while session.delivery_queue.qsize() < 8:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_ordered_boundary(), timeout=1.0)
    client.release_first_audio.set()
    await asyncio.wait_for(session.delivery_queue.join(), timeout=1.0)

    batch_identities = [
        (
            batch[0].audio.response,
            batch[0].audio.provider_response_id,
            batch[0].audio.provider_item_id,
            batch[0].audio.content_index,
            tuple(event.audio.sequence for event in batch),
        )
        for batch in client.audio_batches
        if batch[0].audio is not None
    ]
    proposed_operations = [
        proposal.action.operation
        for proposal in client.proposals
        if proposal.action is not None
    ]
    delivery_live = (
        session.delivery_task is not None and not session.delivery_task.done()
    )
    event_live = session.event_task is not None and not session.event_task.done()
    await registry.close_native_interaction(uplink)

    assert batch_identities == [
        (
            first_response,
            "provider-response-first",
            "provider-item-first",
            0,
            (1, 2),
        ),
        (
            second_response,
            "provider-response-second",
            "provider-item-second-a",
            0,
            (1, 2),
        ),
        (
            second_response,
            "provider-response-second",
            "provider-item-second-b",
            1,
            (3, 4, 5),
        ),
    ]
    assert proposed_operations == ["SILENCE"]
    assert delivery_live is True
    assert event_live is True


@pytest.mark.asyncio
async def test_native_unconsumed_downlink_saturation_closes_before_later_controls() -> (
    None
):
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
        native_downlink_append_timeout_seconds=0.01,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    response = ResponseRef("interaction-1", "native-response-saturated", 1)
    for sequence in range(9):
        await engine.events.put(
            NativeEngineEvent(
                audio=NativeAudioOutput(
                    provider_event_id=f"provider-audio-saturated-{sequence}",
                    provider_response_id="provider-response-saturated",
                    provider_item_id="provider-item-saturated",
                    content_index=0,
                    sequence=sequence,
                    pcm16=sequence.to_bytes(2, "little") * 480,
                    response=response,
                )
            )
        )
    await engine.events.put(
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-listen-after-saturation",
                operation="LISTEN",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(
                    ("provider_item_id", "provider-user-after-saturation"),
                    ("provider_start_ms", "140"),
                ),
            )
        )
    )
    await engine.events.put(
        NativeEngineEvent(
            provider_done=NativeProviderDone(
                provider_event_id="provider-done-after-saturation",
                provider_response_id="provider-response-saturated",
                response=response,
                completed=True,
                transcript=None,
                transcript_event_id=None,
            )
        )
    )

    await asyncio.wait_for(engine.close_event.wait(), timeout=1.0)

    async def wait_until_cleanup_is_visible() -> None:
        while registry._native_sessions:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_until_cleanup_is_visible(), timeout=1.0)
    assert len(client.proposals) == 9
    assert all(proposal.audio is not None for proposal in client.proposals)
    # The lifecycle barrier moved LISTEN behind the prior audio, then stopped
    # the Provider reader. Saturation admits neither that control nor the later
    # completion; the unread fake completion remains outside product effects.
    assert engine.events.qsize() == 1
    assert engine.events._queue[0].provider_done is not None
    assert client.close_calls == 1
    assert registry._records == {uplink.record_id: uplink}
    assert uplink.route_completed is True
    assert registry._pending_tickets == {}
    assert (
        registry.take_native_notification(
            session_id="session-1",
            interaction_id="interaction-1",
            connection_id="connection-1",
        )
        is None
    )


@pytest.mark.asyncio
async def test_native_delegate_result_is_returned_to_provider_once() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    delegate = NativeDelegateProposal(
        binding=activation_handle.binding,
        turn_id="native-turn-1",
        response_generation=1,
        provider_event_id="provider-function-event-1",
        provider_call_id="provider-call-1",
        provider_item_id="provider-function-item-1",
        request_text="Use Jiuwen safely.",
    )
    await engine.events.put(
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-delegate-action-1",
                operation="DELEGATE",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(
                    ("provider_call_id", delegate.provider_call_id),
                    ("turn_id", delegate.turn_id),
                ),
            ),
            delegate=delegate,
        )
    )

    await asyncio.wait_for(engine.delegate_result_sent.wait(), timeout=1.0)

    assert engine.delegate_results == [
        (
            "provider-call-1",
            ResponseRef(
                activation_handle.binding.interaction_id,
                "native-delegate-response-1",
                2,
            ),
            "Canonical Jiuwen result.",
        )
    ]
    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_media_resamples_browser_48khz_to_provider_24khz_and_back() -> (
    None
):
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda binding: (
            engine if binding == activation_handle.binding else None
        ),
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=48_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 960),
    )
    await engine.events.put(
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-speak-48k",
                operation="SPEAK",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(("provider_response_id", "provider-response-48k"),),
            )
        )
    )
    await engine.response_admitted.wait()
    response = engine.admissions[0][1]
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-48k",
                provider_response_id="provider-response-48k",
                provider_item_id="provider-item-48k",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=response,
            )
        )
    )
    await client.audio_proposed.wait()
    notification_response = registry.take_native_notification_response(
        request_id="browser-notification-48k",
        session_id="session-1",
        correlation_id="correlation-1",
        interaction_id="interaction-1",
        activation_id="activation-1",
        activation_generation=1,
        connection_id="connection-1",
        notification_sequence=1,
    )
    assert notification_response is not None
    notification = notification_response["result"]
    assert notification is not None
    audio = notification["audio"]
    assert audio["sample_rate_hz"] == 48_000
    downlink = registry.consume_ticket(_media_ticket(audio), request_origin=ORIGIN)
    assert downlink is not None
    assert downlink.binding.frame_format.sample_rate_hz == 48_000
    assert downlink.binding.frame_format.samples_per_channel == 960
    source = downlink.downlink_stream_source
    assert source is not None
    await engine.events.put(
        NativeEngineEvent(
            provider_done=NativeProviderDone(
                provider_event_id="provider-done-48k",
                provider_response_id="provider-response-48k",
                response=response,
                completed=True,
                transcript=None,
                transcript_event_id=None,
            )
        )
    )
    frames = [frame async for frame in source]
    assert len(frames) == 1
    assert len(frames[0].samples) == 960
    assert len(engine.offered_audio) == 1
    assert len(engine.offered_audio[0].pcm16) == 480 * 2
    assert engine.offered_audio[0].sample_cursor == 0
    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_listen_event_becomes_exact_media_speech_start() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)

    speech_start = asyncio.create_task(registry.wait_native_speech_start(uplink))
    await engine.events.put(
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-listen-1",
                operation="LISTEN",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(
                    ("provider_item_id", "provider-user-item-1"),
                    ("provider_start_ms", "120"),
                ),
            )
        )
    )

    control = await asyncio.wait_for(speech_start, timeout=1.0)
    assert control.lease_id == uplink.binding.lease_id
    assert control.generation == uplink.binding.generation.value
    assert control.provider_start_ms == 120
    assert control.detector == "server_vad"
    assert control.create_response is False
    assert control.interrupt_response is False

    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_turn_commit_becomes_exact_media_end_of_turn() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)

    end_of_turn = asyncio.create_task(registry.wait_native_end_of_turn(uplink))
    commit = NativeTurnCommit(
        contract_version=NATIVE_INTERACTION_CONTRACT_VERSION,
        commit_id="native-commit-1",
        binding=activation_handle.binding,
        turn_id="native-turn-1",
        provider_session_id="provider-session-1",
        provider_item_id="provider-user-item-1",
        provider_event_id="provider-commit-event-1",
        causation_id="provider-commit-event-1",
        input_audio_start_ms=120,
        input_audio_end_ms=780,
        committed_audio_ms=660,
    )
    await engine.events.put(
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-turn-commit-1",
                operation="TURN_COMMIT",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(
                    ("turn_id", commit.turn_id),
                    ("provider_item_id", commit.provider_item_id),
                ),
            ),
            turn_commit=commit,
        )
    )

    control = await asyncio.wait_for(end_of_turn, timeout=1.0)
    assert control.lease_id == uplink.binding.lease_id
    assert control.generation == uplink.binding.generation.value
    assert control.provider_start_ms == 120
    assert control.provider_end_ms == 780
    assert control.detector == "server_vad"
    assert control.create_response is False
    assert control.interrupt_response is False
    assert (
        registry.take_native_notification(
            session_id="session-1",
            interaction_id="interaction-1",
            connection_id="connection-1",
        )
        is None
    )

    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
@pytest.mark.parametrize("browser_sample_rate", [24_000, 48_000])
async def test_native_playback_stop_admits_later_item_before_provider_cancel(
    browser_sample_rate: int,
) -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    shared_actions: list[tuple[str, object]] = []
    client.playback_actions = shared_actions
    engine.playback_actions = shared_actions
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=browser_sample_rate),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    response = ResponseRef("interaction-1", "native-response-1", 1)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-barge-1",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=response,
            )
        )
    )
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-barge-2",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-2",
                content_index=0,
                sequence=1,
                pcm16=b"\x02\x00" * 480,
                response=response,
            )
        )
    )

    async def wait_for_both_audio_items() -> None:
        while sum(proposal.audio is not None for proposal in client.proposals) < 2:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_both_audio_items(), timeout=1.0)
    notification = registry.take_native_notification(
        session_id="session-1",
        interaction_id="interaction-1",
        connection_id="connection-1",
    )
    assert notification is not None
    audio = notification["audio"]
    assert isinstance(audio, dict)
    downlink = registry.consume_ticket(_media_ticket(audio), request_origin=ORIGIN)
    assert downlink is not None

    await registry.accept_native_playback_stop(
        downlink,
        create_playback_stop_receipt(
            downlink.binding,
            outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED,
            confirmed_through_seq=1,
        ),
    )

    cursor = NativePresentationCursor(
        response=response,
        provider_item_id="provider-item-2",
        content_index=0,
        audio_end_ms=20,
    )
    assert shared_actions == [("runtime", cursor), ("provider", cursor)]

    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_playback_stop_without_cursor_fences_locally_without_provider_mutation() -> (
    None
):
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    shared_actions: list[tuple[str, object]] = []
    client.playback_actions = shared_actions
    engine.playback_actions = shared_actions
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    response = ResponseRef("interaction-1", "native-response-1", 1)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-before-first-render",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=response,
            )
        )
    )
    await client.audio_proposed.wait()
    notification = registry.take_native_notification(
        session_id="session-1",
        interaction_id="interaction-1",
        connection_id="connection-1",
    )
    assert notification is not None
    audio = notification["audio"]
    assert isinstance(audio, dict)
    downlink = registry.consume_ticket(_media_ticket(audio), request_origin=ORIGIN)
    assert downlink is not None

    assert await registry.accept_native_playback_stop(
        downlink,
        create_playback_stop_receipt(
            downlink.binding,
            outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED,
            confirmed_through_seq=None,
        ),
    )

    assert shared_actions == [
        ("runtime_fence", response),
        ("provider_fence", response),
    ]
    assert all(kind != "provider" for kind, _value in shared_actions)
    source = downlink.downlink_stream_source
    assert source is not None and source.closed is True

    session = next(iter(registry._native_sessions.values()))
    assert session.event_task is not None
    record_count_after_barge = len(registry._records)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-after-response-fence",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=1,
                pcm16=b"\x02\x00" * 480,
                response=response,
            )
        )
    )
    await engine.events.put(
        NativeEngineEvent(
            provider_done=NativeProviderDone(
                provider_event_id="provider-done-after-response-fence",
                provider_response_id="provider-response-1",
                response=response,
                completed=True,
                transcript=None,
                transcript_event_id=None,
            )
        )
    )

    async def wait_for_stale_provider_events() -> None:
        while engine.events.qsize() > 0 and not session.event_task.done():
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_stale_provider_events(), timeout=1.0)

    assert session.event_task.done() is False
    assert len(client.proposals) == 1
    assert len(registry._records) == record_count_after_barge
    assert (
        registry.take_native_notification(
            session_id="session-1",
            interaction_id="interaction-1",
            connection_id="connection-1",
        )
        is None
    )
    assert engine.closed is False
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.0,) * 480),
    )

    async def wait_for_continuous_uplink() -> None:
        while not engine.offered_audio:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_continuous_uplink(), timeout=1.0)
    assert len(engine.offered_audio) == 1
    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_audio_fenced_while_runtime_proposal_is_in_flight_keeps_session_open() -> (
    None
):
    activation_handle = _native_activation()
    client = _BargeRaceNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    response = ResponseRef("interaction-1", "native-response-1", 1)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-before-racing-fence",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=response,
            )
        )
    )
    await client.audio_proposed.wait()
    notification = registry.take_native_notification(
        session_id="session-1",
        interaction_id="interaction-1",
        connection_id="connection-1",
    )
    assert notification is not None
    audio = notification["audio"]
    assert isinstance(audio, dict)
    downlink = registry.consume_ticket(_media_ticket(audio), request_origin=ORIGIN)
    assert downlink is not None

    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-racing-response-fence",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=1,
                pcm16=b"\x02\x00" * 480,
                response=response,
            )
        )
    )
    await asyncio.wait_for(client.late_audio_entered.wait(), timeout=1.0)
    assert await registry.accept_native_playback_stop(
        downlink,
        create_playback_stop_receipt(
            downlink.binding,
            outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED,
            confirmed_through_seq=None,
        ),
    )
    client.release_late_audio.set()
    await engine.events.put(
        NativeEngineEvent(
            provider_done=NativeProviderDone(
                provider_event_id="provider-done-after-racing-fence",
                provider_response_id="provider-response-1",
                response=response,
                completed=True,
                transcript=None,
                transcript_event_id=None,
            )
        )
    )

    session = next(iter(registry._native_sessions.values()))
    assert session.event_task is not None

    async def wait_for_racing_events() -> None:
        while engine.events.qsize() > 0 and not session.event_task.done():
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_racing_events(), timeout=1.0)

    assert session.event_task.done() is False
    assert len(client.proposals) == 2
    assert (
        registry.take_native_notification(
            session_id="session-1",
            interaction_id="interaction-1",
            connection_id="connection-1",
        )
        is None
    )
    assert engine.closed is False
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.0,) * 480),
    )

    async def wait_for_continuous_uplink() -> None:
        while not engine.offered_audio:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_continuous_uplink(), timeout=1.0)
    assert len(engine.offered_audio) == 1
    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_turn_control_barrier_stops_provider_reader_behind_playout_audio() -> (
    None
):
    activation_handle = _native_activation()
    client = _BlockedAudioNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    response = ResponseRef("interaction-1", "native-response-1", 1)
    for sequence in range(2):
        await engine.events.put(
            NativeEngineEvent(
                audio=NativeAudioOutput(
                    provider_event_id=f"provider-audio-control-race-{sequence}",
                    provider_response_id="provider-response-1",
                    provider_item_id="provider-item-1",
                    content_index=0,
                    sequence=sequence,
                    pcm16=(sequence + 1).to_bytes(2, "little") * 480,
                    response=response,
                )
            )
        )
        if sequence == 0:
            await asyncio.wait_for(client.audio_proposed.wait(), timeout=1.0)
    await asyncio.wait_for(client.blocked_audio_entered.wait(), timeout=1.0)

    commit = NativeTurnCommit(
        contract_version=NATIVE_INTERACTION_CONTRACT_VERSION,
        commit_id="native-control-race-commit",
        binding=activation_handle.binding,
        turn_id="native-turn-control-race",
        provider_session_id="provider-session-1",
        provider_item_id="provider-user-item-control-race",
        provider_event_id="provider-commit-control-race",
        causation_id="provider-commit-control-race",
        input_audio_start_ms=800,
        input_audio_end_ms=1_200,
        committed_audio_ms=400,
    )
    lifecycle_events = (
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-listen-control-race",
                operation="LISTEN",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(
                    ("provider_item_id", commit.provider_item_id),
                    ("provider_start_ms", "800"),
                ),
            )
        ),
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-silence-control-race",
                operation="SILENCE",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(("provider_item_id", commit.provider_item_id),),
            )
        ),
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-turn-commit-control-race",
                operation="TURN_COMMIT",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(
                    ("turn_id", commit.turn_id),
                    ("provider_item_id", commit.provider_item_id),
                ),
            ),
            turn_commit=commit,
        ),
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-speak-control-race",
                operation="SPEAK",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(
                    ("provider_response_id", "provider-response-2"),
                    ("turn_id", commit.turn_id),
                ),
            )
        ),
    )
    for event in lifecycle_events:
        await engine.events.put(event)

    try:
        await asyncio.sleep(0.05)
        assert engine.response_admitted.is_set() is False
        assert engine.events.qsize() == 3
        client.release_blocked_audio.set()
        await asyncio.wait_for(engine.response_admitted.wait(), timeout=1.0)
        assert [
            proposal.action.operation
            for proposal in client.proposals
            if proposal.action is not None
        ][-4:] == ["LISTEN", "SILENCE", "TURN_COMMIT", "SPEAK"]
    finally:
        client.release_blocked_audio.set()
        await asyncio.wait_for(registry.close_native_interaction(uplink), timeout=1.0)


@pytest.mark.asyncio
async def test_native_provider_stop_overtakes_blocked_audio_admission() -> None:
    activation_handle = _native_activation()
    client = _BlockedAudioNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    response = ResponseRef("interaction-1", "native-response-1", 1)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-before-block",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=response,
            )
        )
    )
    await asyncio.wait_for(client.audio_proposed.wait(), timeout=1.0)

    async def wait_for_initial_notification() -> dict[str, object]:
        while True:
            notification = registry.take_native_notification(
                session_id="session-1",
                interaction_id="interaction-1",
                connection_id="connection-1",
            )
            if notification is not None:
                return notification
            await asyncio.sleep(0)

    notification = await asyncio.wait_for(wait_for_initial_notification(), timeout=1.0)
    assert notification is not None

    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-blocked",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=1,
                pcm16=b"\x02\x00" * 480,
                response=response,
            )
        )
    )
    await asyncio.wait_for(client.blocked_audio_entered.wait(), timeout=1.0)
    for sequence in range(2, 602):
        await engine.events.put(
            NativeEngineEvent(
                audio=NativeAudioOutput(
                    provider_event_id=f"provider-audio-queued-before-stop-{sequence}",
                    provider_response_id="provider-response-1",
                    provider_item_id="provider-item-1",
                    content_index=0,
                    sequence=sequence,
                    pcm16=sequence.to_bytes(2, "little") * 480,
                    response=response,
                )
            )
        )
    await engine.events.put(
        NativeEngineEvent(
            action=InteractionAction(
                action_id="native-provider-stop-overtakes-audio",
                operation="STOP",
                interaction_id=activation_handle.binding.interaction_id,
                scope=activation_handle.binding.scope,
                payload=(
                    ("provider_response_id", "provider-response-1"),
                    ("runtime_response_id", response.response_id),
                    ("response_generation", str(response.response_generation)),
                ),
            )
        )
    )

    session = next(iter(registry._native_sessions.values()))
    try:
        try:
            await asyncio.wait_for(client.stop_proposed.wait(), timeout=0.25)
        except TimeoutError:
            if session.event_task is not None and session.event_task.done():
                await session.event_task
            raise
        assert session.event_task is not None and session.event_task.done() is False
        assert response in session.barge_fenced_responses

        async def wait_for_drained_provider_events() -> None:
            while engine.events.qsize() > 0 and not session.event_task.done():
                await asyncio.sleep(0)

        await asyncio.wait_for(wait_for_drained_provider_events(), timeout=1.0)
        assert session.event_task.done() is False
        assert engine.closed is False
    finally:
        client.release_blocked_audio.set()
        if session.delivery_task is not None and not session.delivery_task.done():
            await asyncio.wait_for(session.delivery_queue.join(), timeout=1.0)
            assert [
                proposal.audio.sequence
                for proposal in client.proposals
                if proposal.audio is not None
            ] == [0, 1]
        await asyncio.wait_for(registry.close_native_interaction(uplink), timeout=1.0)


@pytest.mark.asyncio
async def test_native_completed_downlink_reuses_existing_playout_receipt_ack() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.0,) * 480),
    )
    response = ResponseRef("interaction-1", "native-response-1", 1)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-presentation-1",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=response,
            )
        )
    )
    await client.audio_proposed.wait()
    notification = registry.take_native_notification(
        session_id="session-1",
        interaction_id="interaction-1",
        connection_id="connection-1",
    )
    assert notification is not None
    audio = notification["audio"]
    assert isinstance(audio, dict)
    downlink = registry.consume_ticket(_media_ticket(audio), request_origin=ORIGIN)
    assert downlink is not None
    source = downlink.downlink_stream_source
    assert source is not None
    await engine.events.put(
        NativeEngineEvent(
            provider_done=NativeProviderDone(
                provider_event_id="provider-done-presentation-1",
                provider_response_id="provider-response-1",
                response=response,
                completed=True,
                transcript=None,
                transcript_event_id=None,
            )
        )
    )
    assert len([frame async for frame in source]) == 1
    registry.mark_downlink_started(downlink)
    assert registry.complete_downlink(
        downlink,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=0,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
            sent_frames=1,
            acknowledged_through_seq=0,
            playback_stop_receipts=0,
            configured_max_pending_frames=8,
            configured_max_pending_bytes=131_072,
            peak_pending_frames=1,
            peak_pending_bytes=2_000,
        ),
    )
    params = {
        "session_id": "session-1",
        "subject_id": activated["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "response_id": response.response_id,
        "response_generation": response.response_generation,
        "unit_id": notification["presentation_unit"]["unit_id"],
        "capture_frames_acked": 1,
        "rendered_chunks": 1,
        "rendered_through_seq": 0,
        "playout_queue_capacity": 256,
        "playout_peak_depth": 1,
        "capture_control_ack": "capture_flush_acked",
        "playout_state": "render_completed",
    }
    receipt = registry.acknowledge_playout(
        params=params,
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )

    assert await registry.acknowledge_native_playout(
        receipt=receipt,
        routed_session_id="session-1",
        connection_id="connection-1",
    )
    presentation = client.playback_actions[-1]
    assert presentation[0] == "presentation"
    assert presentation[1].ref == response
    assert presentation[1].unit_id == params["unit_id"]
    assert presentation[1].contiguous_cursor == 0
    assert engine.presentation_acknowledgements == [response]
    assert downlink.record_id not in registry._records
    assert uplink.synthesis_content_sha256 == {}
    assert uplink.playout_receipts == {}
    assert uplink.playout_receipt_content_sha256 == {}
    assert uplink.downlink_results == {}
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=1, sample_cursor=480, samples=(0.0,) * 480),
    )
    assert uplink.accepted_frames == 2
    replayed_receipt = registry.acknowledge_playout(
        params=params,
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )
    assert replayed_receipt == receipt
    assert await registry.acknowledge_native_playout(
        receipt=replayed_receipt,
        routed_session_id="session-1",
        connection_id="connection-1",
    )
    assert [kind for kind, _value in client.playback_actions].count("presentation") == 1
    assert engine.presentation_acknowledgements == [response]
    changed_params = dict(params)
    changed_params["playout_peak_depth"] = 2
    with pytest.raises(MediaTransportViolation) as changed_replay:
        registry.acknowledge_playout(
            params=changed_params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert changed_replay.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_CONFLICT"

    await registry.close_native_interaction(uplink)
    assert uplink.pcm == bytearray()
    assert uplink.playout_receipts == {}
    assert uplink.playout_receipt_content_sha256 == {}
    assert uplink.downlink_results == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_mode", "reason_id"),
    [
        ("exception", "MEDIA_NATIVE_PRESENTATION_ACK_REJECTED"),
        ("malformed", "MEDIA_NATIVE_PRESENTATION_ACK_INVALID"),
    ],
)
async def test_native_runtime_rejected_presentation_has_zero_engine_effect(
    failure_mode: str,
    reason_id: str,
) -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.0,) * 480),
    )
    if failure_mode == "exception":
        client.presentation_ack_error = RuntimeError("runtime presentation rejected")
    else:
        client.presentation_ack_result = {
            "kind": "presentation_ack",
            "status": "observed",
        }

    with pytest.raises(MediaTransportViolation) as rejected:
        await _present_native_test_audio_unit(
            registry,
            client,
            engine,
            uplink,
            activated,
            sequence=0,
        )

    assert rejected.value.reason_id == reason_id
    assert [kind for kind, _value in client.playback_actions] == ["presentation"]
    assert engine.presentation_acknowledgements == []
    assert len(registry._records) == 2
    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_playout_replay_tombstones_are_bounded_by_route_capacity() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        capacity=2,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    registry.accept_native_frame(
        uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.0,) * 480),
    )

    completed = [
        await _present_native_test_audio_unit(
            registry,
            client,
            engine,
            uplink,
            activated,
            sequence=sequence,
        )
        for sequence in range(3)
    ]

    with pytest.raises(MediaTransportViolation) as evicted_replay:
        registry.acknowledge_playout(
            params=completed[0][0],
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert evicted_replay.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED"
    latest_receipt = registry.acknowledge_playout(
        params=completed[-1][0],
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )
    assert latest_receipt == completed[-1][1]
    assert await registry.acknowledge_native_playout(
        receipt=latest_receipt,
        routed_session_id="session-1",
        connection_id="connection-1",
    )
    assert [kind for kind, _value in client.playback_actions].count("presentation") == 3

    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_failed_downlink_releases_record_and_transient_ledgers() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    response = ResponseRef("interaction-1", "native-response-failed", 1)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-failed",
                provider_response_id="provider-response-failed",
                provider_item_id="provider-item-failed",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=response,
            )
        )
    )
    await client.audio_proposed.wait()
    notification = registry.take_native_notification(
        session_id="session-1",
        interaction_id="interaction-1",
        connection_id="connection-1",
    )
    assert notification is not None
    audio = notification["audio"]
    assert isinstance(audio, dict)
    downlink = registry.consume_ticket(_media_ticket(audio), request_origin=ORIGIN)
    assert downlink is not None
    registry.mark_downlink_started(downlink)

    complete = registry.complete_downlink(
        downlink,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=0,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
            sent_frames=0,
            acknowledged_through_seq=None,
            playback_stop_receipts=0,
            configured_max_pending_frames=8,
            configured_max_pending_bytes=131_072,
            peak_pending_frames=0,
            peak_pending_bytes=0,
        ),
    )

    assert complete is False
    assert downlink.record_id not in registry._records
    assert uplink.synthesis_content_sha256 == {}
    assert uplink.downlink_results == {}
    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_media_revoke_closes_provider_runtime_and_queued_routes() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)

    closed = registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": activated["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    cleanup = tuple(registry._native_cleanup_tasks)
    assert cleanup
    await asyncio.gather(*cleanup)

    assert closed["status"] == "closed"
    assert engine.closed is True
    assert client.close_calls == 1
    assert registry._native_sessions == {}
    assert registry._native_session_keys_by_record == {}
    assert registry._native_notifications == {}


@pytest.mark.asyncio
async def test_incomplete_native_provider_close_retains_owner_until_exact_retry() -> (
    None
):
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _RetainedCloseNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    key = registry._native_session_keys_by_record[uplink.record_id]

    assert await registry.close_native_interaction(uplink) is False
    assert registry._native_sessions[key].engine is engine
    assert registry._native_session_keys_by_record[uplink.record_id] == key
    assert engine.close_calls == 1
    assert registry._media_capacity_in_use() == 1

    assert await registry.close_native_interaction(uplink) is True
    assert engine.close_calls == 2
    assert len(client.close_request_ids) == 2
    assert client.close_request_ids[1] == client.close_request_ids[0]
    assert registry._native_sessions == {}
    assert registry._native_session_keys_by_record == {}


@pytest.mark.asyncio
async def test_runtime_close_failure_retains_provider_completed_owner_for_exact_retry() -> (
    None
):
    activation_handle = _native_activation()
    client = _FailOnceNativeRuntimeCloseClient(activation_handle)
    engine = _CountingCloseNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        capacity=1,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    key = registry._native_session_keys_by_record[uplink.record_id]

    assert await registry.close_native_interaction(uplink) is False
    assert registry._native_sessions[key].engine is engine
    assert registry._native_session_keys_by_record[uplink.record_id] == key
    assert registry._media_capacity_in_use() == 1
    assert client.close_calls == 1
    assert engine.close_calls == 1

    assert await registry.close_native_interaction(uplink) is True
    assert client.close_calls == 2
    assert client.close_request_ids[1] == client.close_request_ids[0]
    assert engine.close_calls == 1
    assert registry._native_sessions == {}
    assert registry._native_session_keys_by_record == {}
    assert registry._native_close_capacity_reservations == set()
    assert registry._records == {uplink.record_id: uplink}
    assert registry._media_capacity_in_use() == 1

    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": activated["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    assert client.close_calls == 2
    assert engine.close_calls == 1
    assert registry._media_capacity_in_use() == 0


@pytest.mark.asyncio
async def test_incomplete_native_revoke_retains_capacity_until_provider_close() -> None:
    activation_handle = _native_activation()
    client = _MultiActivationNativeRuntimeClient(activation_handle)
    engine = _RetainedCloseNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        capacity=1,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)

    successor = _params(
        interaction_id="interaction-2",
        correlation_id="correlation-2",
        activation_id="activation-2",
        capture_id="capture-2",
        sample_rate_hz=24_000,
    )
    successor_activation = GatewayNativeActivation(
        binding=NativeInteractionBinding(
            scope=ScopeRef(
                "subject-native", None, "session-1", Assurance.AUTHENTICATED
            ),
            interaction_id="interaction-2",
            activation_id="activation-2",
            activation_generation=1,
            correlation_id="correlation-2",
        ),
        capability="b" * 64,
        connection_id="connection-1",
    )
    client.activations.append(successor_activation)

    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": activated["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    assert registry._records == {}
    assert len(registry._native_close_capacity_reservations) == 1
    assert registry._media_capacity_in_use() == 1
    with pytest.raises(MediaTransportViolation) as immediate_saturation:
        _activate(
            registry,
            params=successor,
            request_origin=ORIGIN,
            connection_id="connection-1",
        )
    assert immediate_saturation.value.reason_id == "MEDIA_ROUTE_CAPACITY_EXCEEDED"

    cleanup = tuple(registry._native_cleanup_tasks)
    assert cleanup
    await asyncio.gather(*cleanup)
    assert engine.close_calls == 1
    assert len(registry._native_sessions) == 1
    assert registry._records == {}

    with pytest.raises(MediaTransportViolation) as saturated:
        _activate(
            registry,
            params=successor,
            request_origin=ORIGIN,
            connection_id="connection-1",
        )
    assert saturated.value.reason_id == "MEDIA_ROUTE_CAPACITY_EXCEEDED"

    assert await registry.close_native_interaction(uplink) is True
    replacement = _activate(
        registry,
        params=successor,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    assert replacement["status"] == "active"


@pytest.mark.asyncio
async def test_native_notification_is_not_dropped_without_live_product_authority() -> (
    None
):
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)
    await engine.events.put(
        NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id="provider-audio-retained-1",
                provider_response_id="provider-response-1",
                provider_item_id="provider-item-1",
                content_index=0,
                sequence=0,
                pcm16=b"\x01\x00" * 480,
                response=ResponseRef("interaction-1", "native-response-1", 1),
            )
        )
    )
    await client.audio_proposed.wait()
    queue_owner = registry._native_notifications[
        ("session-1", "interaction-1", "connection-1")
    ]
    assert queue_owner.qsize() == 1
    registry._product_activations.clear()

    assert (
        registry.take_native_notification_response(
            request_id="notification-without-authority-1",
            session_id="session-1",
            correlation_id="correlation-1",
            interaction_id="interaction-1",
            activation_id="activation-1",
            activation_generation=1,
            connection_id="connection-1",
            notification_sequence=1,
        )
        is None
    )
    assert queue_owner.qsize() == 1

    await registry.close_native_interaction(uplink)


@pytest.mark.asyncio
async def test_native_provider_event_failure_fences_and_closes_session() -> None:
    activation_handle = _native_activation()
    client = _FakeNativeRuntimeClient(activation_handle)
    engine = _FakeNativeEngine()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        native_runtime_client=client,
        native_engine_factory=lambda _binding: engine,
    )
    activated = _activate(
        registry,
        params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    uplink = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    assert uplink is not None
    await registry.begin_native_interaction(uplink)

    await engine.events.put(RuntimeError("Provider transport closed"))
    await asyncio.wait_for(engine.close_event.wait(), timeout=1.0)

    assert client.close_calls == 1
    assert registry._native_sessions == {}
    assert registry._native_notifications == {}


def test_websocket_transport_debug_cannot_persist_binary_media(
    tmp_path: Path,
) -> None:
    path = tmp_path / "websocket-transport.log"
    sink = logging.FileHandler(path, encoding="utf-8")
    transport_logger = web_connect._websocket_transport_logger
    previous_level = transport_logger.level
    transport_logger.setLevel(logging.DEBUG)
    transport_logger.addHandler(sink)
    marker = "PRIVATE_BINARY_PCM_MARKER"
    try:
        transport_logger.debug("< BINARY %s", marker)
        transport_logger.info("transport lifecycle only")
        sink.flush()
    finally:
        transport_logger.removeHandler(sink)
        sink.close()
        transport_logger.setLevel(previous_level)

    rendered = path.read_text("utf-8")
    assert marker not in rendered
    assert "transport lifecycle only" in rendered


@pytest.mark.parametrize(
    ("params", "origin"),
    [
        ({**_params(), "unknown": True}, ORIGIN),
        ({key: value for key, value in _params().items() if key != "track_id"}, ORIGIN),
        (_params(sample_rate_hz=15_999), ORIGIN),
        (_params(locale="fr-FR"), ORIGIN),
        (_params(), "https://other.example.test"),
        (_params(), None),
    ],
)
def test_activation_rejects_unclosed_or_untrusted_inputs(
    params: dict[str, object], origin: str | None
) -> None:
    with pytest.raises(MediaTransportViolation):
        _active_registry().activate(
            params=params, request_origin=origin, connection_id="connection-1"
        )


def test_ticket_is_single_use_and_exact_origin_bound() -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)

    assert (
        registry.consume_ticket(ticket, request_origin="https://other.example.test")
        is None
    )
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is None


def test_stock_web_empty_identity_uses_connection_owned_p2_authority() -> None:
    registry = _active_registry()
    params = _params()
    _trust_product_activation(
        registry,
        params,
        user_id=None,
        connection_id="stock-web-connection",
    )

    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="stock-web-connection",
        user_id=None,
    )

    assert activation["status"] == "active"
    assert activation["reason_id"] == "MEDIA_ROUTE_TICKET_ISSUED"
    assert activation["binding"]["connection_id"] == "stock-web-connection"
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    context = registry.context_for(
        SimpleNamespace(_jiuwen_ws_id="stock-web-connection"),
        {"scope": {"subject_id": activation["subject_id"]}},
        "session-1",
        None,
    )
    assert context.assurance is Assurance.AUTHENTICATED


def test_browser_identity_claim_cannot_mint_or_transfer_media_authority() -> None:
    registry = _active_registry()
    params = _params()
    with pytest.raises(MediaTransportViolation) as untrusted:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="browser-static-claim",
        )
    assert untrusted.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"
    assert registry._records == {}
    assert registry._subjects == {}

    _trust_product_activation(
        registry,
        params,
        user_id="browser-static-claim",
        connection_id="connection-1",
    )
    with pytest.raises(MediaTransportViolation) as foreign:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-foreign",
            user_id="browser-static-claim",
        )
    assert foreign.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"
    assert registry._records == {}
    assert registry._subjects == {}

    scope = ScopeRef("browser-static-claim", None, "session-1", Assurance.AUTHENTICATED)
    unauthorized_speech = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="forged-browser-recognition",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=0,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256="a" * 64,
    )
    assert registry.authorize(unauthorized_speech) is None

    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="changed-browser-claim",
    )
    assert activation["status"] == "active"
    assert activation["binding"]["connection_id"] == "connection-1"
    assert "browser-static-claim" not in repr(activation)
    assert "changed-browser-claim" not in repr(activation)


def test_partial_capture_never_authorizes_speech() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    registry.accept_frame(
        record,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )
    record.recognition_content_sha256 = "a" * 64
    scope = ScopeRef(
        str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    binding = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="recognize-partial",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=0,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256="a" * 64,
    )

    assert registry.authorize(binding) is None


def test_expired_unconsumed_ticket_releases_capacity_before_authority_ttl() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        ticket_ttl_seconds=1,
        authority_ttl_seconds=100,
        capacity=1,
    )
    registry.set_provider_available(True)
    _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    now = 2.0

    replacement = _activate(
        registry,
        params=_params(
            capture_id="capture-2",
            track_id="track-2",
            activation_id="activation-2",
        ),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )

    assert replacement["status"] == "active"
    assert len(registry._records) == 1


def test_exact_media_close_is_idempotent_and_revokes_all_speech_authority() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.recognition_content_sha256 = "a" * 64
    close = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }

    first = registry.revoke(
        params=close,
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )
    replay = registry.revoke(
        params=close,
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )

    assert first == replay
    assert registry._records == {}
    assert record.recognition_content_sha256 is None
    assert record.synthesis_content_sha256 == {}
    with pytest.raises(MediaTransportViolation) as forged:
        registry.revoke(
            params=close,
            routed_session_id="session-1",
            connection_id="connection-forged",
            user_id="user-1",
        )
    assert forged.value.reason_id == "MEDIA_CLOSE_BINDING_MISMATCH"


def test_product_activation_expiry_retains_exact_media_close_tombstone() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-owner")
    now = 9.0
    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-owner",
        user_id="user-1",
    )
    ticket = _media_ticket(activation)
    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is not None
    close = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }

    # The media authority itself is still live, but pruning the older P2
    # activation revokes it first. The browser's later exact close must remain
    # idempotent instead of becoming permanently cleanup_pending.
    now = 11.0
    first = registry.revoke(
        params=close,
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )
    replay = registry.revoke(
        params=close,
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )

    assert first == replay
    assert first["reason_id"] == "MEDIA_ROUTE_REVOKED"
    assert registry._records == {}
    with pytest.raises(MediaTransportViolation) as forged:
        registry.revoke(
            params=close,
            routed_session_id="session-1",
            connection_id="connection-forged",
            user_id="user-1",
        )
    assert forged.value.reason_id == "MEDIA_CLOSE_BINDING_MISMATCH"


def test_media_authority_expiry_retains_exact_media_close_tombstone() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-owner")
    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-owner",
        user_id="user-1",
    )
    ticket = _media_ticket(activation)
    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is not None

    now = 11.0
    close = registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": activation["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )

    assert close["reason_id"] == "MEDIA_ROUTE_REVOKED"
    assert registry._records == {}


def test_exact_final_notification_renews_live_product_media_trust() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")
    now = 9.0
    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True

    now = 9.5
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-1",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "authoritative response",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    now = 11.0
    context = registry.context_for(
        SimpleNamespace(_jiuwen_ws_id="connection-1"),
        {"scope": {"subject_id": activation["subject_id"]}},
        "session-1",
        "user-1",
    )
    assert context.assurance is Assurance.AUTHENTICATED
    assert registry._records


def test_expired_product_activation_cannot_be_revived_by_late_notification() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")

    now = 11.0
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-late",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "late response",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-late"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert registry._product_activations == {}
    with pytest.raises(MediaTransportViolation) as rejected:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
    assert rejected.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"


def test_exact_p2_activation_replay_reestablishes_expired_media_trust() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")

    now = 11.0
    with pytest.raises(MediaTransportViolation) as expired:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
    assert expired.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"

    # The browser's explicit Start first replays this exact authoritative P2
    # activation. The observed AgentServer response may establish a new short-
    # lived media authority; no client-only binding can do so.
    _trust_product_activation(registry, params, connection_id="connection-1")
    activated = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )

    assert activated["status"] == "active"
    assert activated["binding"]["interaction_id"] == "interaction-1"


def test_cross_session_route_notification_cannot_renew_product_activation() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")

    now = 9.0
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-cross-session",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "cross-session response",
                },
                "presentation_unit": {
                    "surface": "text",
                    "unit_id": "unit-cross-session",
                },
            },
        },
        routed_session_id="session-foreign",
        user_id="user-1",
        connection_id="connection-1",
    )

    now = 11.0
    with pytest.raises(MediaTransportViolation) as rejected:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
    assert rejected.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"
    assert registry._product_activations == {}


def test_speech_context_requires_the_exact_activation_connection() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    params = {"scope": {"subject_id": activation["subject_id"]}}

    owner = registry.context_for(
        SimpleNamespace(_jiuwen_ws_id="connection-owner"),
        params,
        "session-1",
        "user-1",
    )
    foreign = registry.context_for(
        SimpleNamespace(_jiuwen_ws_id="connection-foreign"),
        params,
        "session-1",
        "user-1",
    )

    assert owner.assurance is Assurance.AUTHENTICATED
    assert foreign.assurance is Assurance.REQUEST_ASSERTED


@pytest.mark.asyncio
async def test_activation_handler_rejects_a_forged_session_before_allocation() -> None:
    registry = _active_registry()
    registered: dict[str, object] = {}
    responses: list[dict[str, object]] = []

    class Channel:
        def register_method(self, name: str, handler: object) -> None:
            registered[name] = handler

        async def send_response(
            self,
            _ws: object,
            _req_id: str,
            *,
            ok: bool,
            payload: object = None,
            error: object = None,
            code: object = None,
        ) -> None:
            responses.append(
                {"ok": ok, "payload": payload, "error": error, "code": code}
            )

    channel = Channel()
    register_dedicated_media_rpc_handlers(channel, registry=registry)
    handler = registered[MEDIA_ACTIVATE_METHOD]
    await handler(  # type: ignore[operator]
        SimpleNamespace(
            _jiuwen_ws_id="connection-owner",
            request_headers={"Origin": ORIGIN},
        ),
        "request-1",
        _params(session_id="session-forged"),
        "session-dispatcher",
        None,
    )

    assert responses == [
        {
            "ok": False,
            "payload": None,
            "error": "media activation must target the dispatcher-owned session",
            "code": "MEDIA_SESSION_MISMATCH",
        }
    ]
    assert registry._records == {}


@pytest.mark.asyncio
async def test_exceptional_media_socket_exit_clears_every_raw_audio_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)

    async def fail_after_frame(*_args: object, **kwargs: object) -> object:
        callback = kwargs["on_audio_frame"]
        callback(  # type: ignore[operator]
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
        )
        raise RuntimeError("socket leaf failed")

    monkeypatch.setattr(
        dedicated_media_registration,
        "run_dedicated_media_socket_leaf",
        fail_after_frame,
    )
    ws = _AuthOnlySocket(activation)

    with pytest.raises(RuntimeError, match="socket leaf failed"):
        await handle_registered_media_socket(registry, ws, endpoint_path)

    assert record.route_completed is True
    assert record.pcm == bytearray()
    assert record.recognition_content_sha256 is None


@pytest.mark.asyncio
async def test_completed_media_socket_retains_recognition_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)

    async def complete_after_frame(*_args: object, **kwargs: object) -> object:
        kwargs["on_audio_frame"](  # type: ignore[operator]
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
        )
        result = SimpleNamespace(activated=True, accepted_frames=1)
        kwargs["on_complete"](result)  # type: ignore[operator]
        return result

    monkeypatch.setattr(
        dedicated_media_registration,
        "run_dedicated_media_socket_leaf",
        complete_after_frame,
    )
    ws = _AuthOnlySocket(activation)

    assert await handle_registered_media_socket(registry, ws, endpoint_path)

    assert record.route_completed is True
    assert record.recognition_content_sha256 is not None


def test_production_gateway_completion_emits_content_free_l0_ack_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[dict[str, object]] = []
    monkeypatch.setattr(
        dedicated_media_registration,
        "emit_runtime_l0_milestone",
        lambda **kwargs: emitted.append(kwargs) or True,
    )
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    record = _pending_record(registry, _media_ticket(activation))
    registry.accept_frame(
        record,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )
    registry.observe_uplink_ack_sent(
        record,
        MediaAck(record.binding.lease_id, record.binding.generation.value, 0),
    )
    registry.complete_route(
        record,
        SimpleNamespace(activated=True, accepted_frames=1),
    )

    assert [item["milestone"] for item in emitted] == [
        L0Milestone.LAST_FRAME_ACKED,
        L0Milestone.UPLINK_CLOSED,
    ]
    assert emitted[0]["binding"].session_id == "session-1"
    assert emitted[0]["binding"].activation_generation == 1
    assert emitted[0]["duration_ms"] >= 0
    assert emitted[0]["observed_at"] == record.last_uplink_ack_observed_at
    assert emitted[0]["monotonic_ms"] == record.last_uplink_ack_monotonic_ms
    assert "samples" not in repr(emitted)
    assert "pcm" not in repr(emitted).lower()


def test_optional_l0_binding_never_rejects_wider_product_media_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[dict[str, object]] = []
    monkeypatch.setattr(
        dedicated_media_registration,
        "emit_runtime_l0_milestone",
        lambda **kwargs: emitted.append(kwargs) or True,
    )
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(correlation_id="correlation with space"),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    record = _pending_record(registry, _media_ticket(activation))
    registry.accept_frame(
        record,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )
    registry.observe_uplink_ack_sent(
        record,
        MediaAck(record.binding.lease_id, record.binding.generation.value, 0),
    )
    registry.complete_route(
        record,
        SimpleNamespace(activated=True, accepted_frames=1),
    )

    assert record.route_completed is True
    assert [item["binding"] for item in emitted] == [None, None]


@pytest.mark.asyncio
async def test_media_socket_success_without_completion_callback_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)

    async def omit_completion(*_args: object, **kwargs: object) -> object:
        kwargs["on_audio_frame"](  # type: ignore[operator]
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
        )
        return SimpleNamespace(activated=True, accepted_frames=1)

    monkeypatch.setattr(
        dedicated_media_registration,
        "run_dedicated_media_socket_leaf",
        omit_completion,
    )
    ws = _AuthOnlySocket(activation)

    with pytest.raises(
        MediaTransportViolation, match="completion callback was not retained"
    ):
        await handle_registered_media_socket(registry, ws, endpoint_path)

    assert record.route_completed is True
    assert record.recognition_content_sha256 is None
    assert record.pcm == bytearray()


@pytest.mark.asyncio
async def test_uplink_registry_authority_is_visible_before_socket_close() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)
    frame = MediaAudioFrame(
        seq=0,
        sample_cursor=0,
        samples=(0.25,) * record.binding.frame_format.samples_per_channel,
    )
    peer_detach = MediaDetach(
        lease_id=record.binding.lease_id,
        generation=record.binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
        through_seq=0,
    )
    close_observations: list[tuple[bool, bool]] = []
    receipt_observations: list[tuple[bool, bool]] = []

    class _OrderedSocket:
        subprotocol = "live-voice.media.v1"
        request_headers = {"Origin": ORIGIN}

        def __init__(self) -> None:
            self.incoming = [
                _media_auth_frame(activation),
                encode_audio_frame(record.binding, frame),
                serialize_media_control(peer_detach),
            ]
            self.sent: list[str | bytes] = []

        async def recv(self) -> str | bytes:
            return self.incoming.pop(0)

        async def send(self, message: str | bytes) -> None:
            self.sent.append(message)
            if isinstance(message, str) and isinstance(
                deserialize_media_control(message), MediaDetach
            ):
                receipt_observations.append(
                    (
                        record.route_completed,
                        record.recognition_content_sha256 is not None,
                    )
                )

        async def close(self, code: int = 1000, reason: str = "") -> None:
            assert code == 1000
            assert reason == "live-voice media leaf closed"
            close_observations.append(
                (
                    record.route_completed,
                    record.recognition_content_sha256 is not None,
                )
            )

    assert await handle_registered_media_socket(
        registry, _OrderedSocket(), endpoint_path
    )
    assert record.route_completed is True
    assert receipt_observations == [(True, True)]
    assert close_observations == [(True, True)]


@pytest.mark.asyncio
async def test_uplink_completion_is_not_aborted_when_close_wait_is_cancelled() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)
    frame = MediaAudioFrame(
        seq=0,
        sample_cursor=0,
        samples=(0.25,) * record.binding.frame_format.samples_per_channel,
    )
    peer_detach = MediaDetach(
        lease_id=record.binding.lease_id,
        generation=record.binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
        through_seq=0,
    )
    close_started = asyncio.Event()

    class _BlockingCloseSocket:
        subprotocol = "live-voice.media.v1"
        request_headers = {"Origin": ORIGIN}

        def __init__(self) -> None:
            self.incoming = [
                _media_auth_frame(activation),
                encode_audio_frame(record.binding, frame),
                serialize_media_control(peer_detach),
            ]

        async def recv(self) -> str | bytes:
            return self.incoming.pop(0)

        async def send(self, _message: str | bytes) -> None:
            return None

        async def close(self, _code: int = 1000, _reason: str = "") -> None:
            close_started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(
        handle_registered_media_socket(registry, _BlockingCloseSocket(), endpoint_path)
    )
    await asyncio.wait_for(close_started.wait(), timeout=1)
    retained_hash = record.recognition_content_sha256
    assert record.route_completed is True
    assert retained_hash is not None

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert record.route_completed is True
    assert record.recognition_content_sha256 == retained_hash


@pytest.mark.asyncio
async def test_media_handshake_rejects_wrong_origin_even_when_general_check_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())

    response = await channel._process_request(
        "/ws/live-voice/media",
        {"Origin": "https://attacker.example.test"},
    )

    assert response is not None
    assert int(response[0]) == 403


@pytest.mark.asyncio
async def test_media_handshake_rejects_missing_origin_even_when_general_check_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())

    response = await channel._process_request(
        "/ws/live-voice/media",
        {},
    )

    assert response is not None
    assert int(response[0]) == 403


@pytest.mark.asyncio
async def test_dispatcher_routes_only_the_fixed_media_path_to_the_media_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    channel.live_voice_media_registry = _active_registry()
    routed: list[str] = []
    closed: list[tuple[int, str]] = []

    async def fake_leaf(_registry: object, _ws: object, path: str) -> bool:
        routed.append(path)
        return True

    monkeypatch.setattr(
        dedicated_media_registration, "handle_registered_media_socket", fake_leaf
    )

    async def record_close(code: int = 1000, reason: str = "") -> None:
        closed.append((code, reason))

    request_path = "/ws/live-voice/media"
    socket = SimpleNamespace(close=record_close, path=request_path)

    assert (await channel._process_request(request_path, {"Origin": ORIGIN})) is None
    await channel._connection_handler(socket, request_path)

    assert routed == [request_path]
    assert closed == []


@pytest.mark.asyncio
async def test_ticket_like_media_path_is_not_route_authority_or_registry_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    registry = _active_registry()
    channel.live_voice_media_registry = registry
    routed: list[str] = []
    closed: list[tuple[int, str]] = []

    async def fake_leaf(_registry: object, _ws: object, path: str) -> bool:
        routed.append(path)
        return True

    monkeypatch.setattr(
        dedicated_media_registration, "handle_registered_media_socket", fake_leaf
    )

    async def record_close(code: int = 1000, reason: str = "") -> None:
        closed.append((code, reason))

    request_path = "/ws/live-voice/media/private-ticket"
    before = (len(registry._records), len(registry._pending_tickets))
    socket = SimpleNamespace(close=record_close, path=request_path)

    assert (await channel._process_request(request_path, {"Origin": ORIGIN})) is None
    await channel._connection_handler(socket, request_path)

    assert routed == []
    assert closed == [(1008, "unsupported path: /ws/live-voice/media/<redacted>")]
    assert "private-ticket" not in repr(closed)
    assert (len(registry._records), len(registry._pending_tickets)) == before


@pytest.mark.asyncio
async def test_media_handler_rejects_ticket_path_before_any_effect() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    before = (len(registry._records), len(registry._pending_tickets))

    class _PoisonSocket:
        @property
        def subprotocol(self) -> str:
            raise AssertionError("rejected path must not inspect the socket")

        async def recv(self) -> object:
            raise AssertionError("rejected path must not read credentials")

        async def close(self, _code: int = 1000, _reason: str = "") -> None:
            raise AssertionError("rejected path is not an accepted media socket")

    assert not await handle_registered_media_socket(
        registry,
        _PoisonSocket(),
        f"/ws/live-voice/media/{ticket}",
    )
    assert (len(registry._records), len(registry._pending_tickets)) == before
    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is not None


@pytest.mark.asyncio
async def test_media_handshake_never_logs_the_authority_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    ticket = "private-media-authority-ticket"
    logged: list[tuple[object, ...]] = []
    monkeypatch.setattr(web_connect.logger, "info", lambda *args: logged.append(args))

    assert (
        await channel._process_request(
            f"/ws/live-voice/media/{ticket}", {"Origin": ORIGIN}
        )
        is None
    )

    rendered = repr(logged)
    assert ticket not in rendered
    assert "/ws/live-voice/media/<redacted>" in rendered


def test_completed_route_authorizes_only_exact_independent_capture_and_no_disk(
    tmp_path: Path,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    registry.accept_frame(
        record,
        MediaAudioFrame(
            seq=0,
            sample_cursor=0,
            samples=tuple(0.25 if index % 2 else -0.25 for index in range(320)),
        ),
    )
    registry.complete_route(
        record,
        SimpleNamespace(activated=True, accepted_frames=1),  # type: ignore[arg-type]
    )
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert before == after == []
    assert record.pcm == bytearray()
    scope = ScopeRef(
        subject_id=str(activation["subject_id"]),
        project_id=None,
        session_id="session-1",
        assurance=Assurance.AUTHENTICATED,
    )
    exact = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="recognize-1",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=0,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256=str(record.recognition_content_sha256),
    )
    assert registry.authorize(exact) == exact
    forged = replace(exact, content_sha256="0" * 64)
    assert registry.authorize(forged) is None


def test_agent_notification_authorizes_only_exact_agent_text_render_plan() -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    response = {
        "interaction_id": "interaction-1",
        "response_id": "response-1",
        "response_generation": 0,
    }
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": response,
                "agent_event": {"event_type": "chat.final", "text": "正式 Agent 文本"},
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    ref = ResponseRef("interaction-1", "response-1", 0)
    expected = record.synthesis_content_sha256[(ref, "unit-1")]
    scope = ScopeRef(
        str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    exact = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=SYNTHESIZE_OPERATION,
        operation_id="synthesize-1",
        correlation_id="correlation-1",
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=ref,
        unit_id="unit-1",
        content_sha256=expected,
    )
    assert registry.authorize(exact) == exact
    assert (
        registry.authorize(replace(exact, correlation_id="correlation-other")) is None
    )
    wrong = SpeechAuthorizationBinding(
        subject_id=exact.subject_id,
        scope=exact.scope,
        operation=exact.operation,
        operation_id=exact.operation_id,
        correlation_id=exact.correlation_id,
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=exact.response,
        unit_id=exact.unit_id,
        content_sha256="f" * 64,
    )
    assert registry.authorize(wrong) is None


def test_mismatched_notification_batch_has_zero_partial_speech_authority() -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    binding = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }
    valid_final = {
        "status": "notification",
        "kind": "agent.output",
        "request_id": "request-valid",
        "round_id": "round-valid",
        **binding,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-valid",
            "response_generation": 0,
        },
        "agent_event": {"event_type": "chat.final", "text": "valid first item"},
        "source_event": None,
        "progress_event": None,
        "presentation_unit": {"surface": "text", "unit_id": "unit-valid"},
        "error_reason": None,
        "publish_seq": 0,
    }
    mismatched_final = {
        **valid_final,
        "activation_generation": 2,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-mismatched",
            "response_generation": 1,
        },
        "agent_event": {
            "event_type": "chat.final",
            "text": "mismatched second item",
        },
        "presentation_unit": {
            "surface": "text",
            "unit_id": "unit-mismatched",
        },
        "publish_seq": 1,
    }

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification_batch",
                "notifications": [valid_final, mismatched_final],
                **binding,
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert record.synthesis_content_sha256 == {}


def test_same_binding_final_before_invalid_batch_tail_has_zero_speech_authority() -> (
    None
):
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    binding = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }
    valid_final = {
        "status": "notification",
        "kind": "agent.output",
        "request_id": "request-valid",
        "round_id": "round-valid",
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-valid",
            "response_generation": 0,
        },
        "agent_event": {"event_type": "chat.final", "text": "valid first item"},
        "source_event": None,
        "progress_event": None,
        "presentation_unit": {"surface": "text", "unit_id": "unit-valid"},
        "error_reason": None,
        "publish_seq": 0,
        **binding,
    }
    invalid_tail = {
        "status": "notification",
        "kind": "transport.keepalive",
        "request_id": "request-invalid-tail",
        "round_id": None,
        "response": None,
        "agent_event": None,
        "source_event": None,
        "progress_event": None,
        "presentation_unit": None,
        "error_reason": None,
        "publish_seq": 1,
        **binding,
    }

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification_batch",
                "notifications": [valid_final, invalid_tail],
                **binding,
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert record.synthesis_content_sha256 == {}


def test_playout_receipt_requires_exact_authenticated_media_and_synthesis_flow() -> (
    None
):
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    record.accepted_frames = 3
    ref = ResponseRef("interaction-1", "response-1", 0)
    record.synthesis_content_sha256[(ref, "unit-1")] = "a" * 64
    params = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "response_id": "response-1",
        "response_generation": 0,
        "unit_id": "unit-1",
        "capture_frames_acked": 3,
        "rendered_chunks": 300,
        "rendered_through_seq": 299,
        "playout_queue_capacity": 256,
        "playout_peak_depth": 256,
        "capture_control_ack": "capture_flush_acked",
        "playout_state": "render_completed",
    }

    with pytest.raises(MediaTransportViolation) as missing:
        registry.acknowledge_playout(
            params=params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert missing.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED"
    record.downlink_results[(ref, "unit-1")] = {
        "complete": False,
        "sent_frames": 300,
        "acknowledged_through_seq": 299,
        "overlap_observed": True,
        "content_sha256": "a" * 64,
    }
    with pytest.raises(MediaTransportViolation) as incomplete:
        registry.acknowledge_playout(
            params=params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert incomplete.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED"
    record.downlink_results[(ref, "unit-1")] = {
        "complete": True,
        "sent_frames": 300,
        "acknowledged_through_seq": 299,
        "overlap_observed": True,
        "content_sha256": "a" * 64,
    }

    accepted = registry.acknowledge_playout(
        params=params,
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )
    assert accepted["status"] == "media_playout_acknowledged"
    assert accepted["receipt_id"].startswith("media-playout-")
    assert (
        registry.acknowledge_playout(
            params=params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
        == accepted
    )
    for updates in (
        {"capture_frames_acked": 2},
        {"response_id": "response-forged"},
        {"rendered_chunks": 299, "rendered_through_seq": 298},
        {"playout_peak_depth": 257},
    ):
        with pytest.raises(MediaTransportViolation):
            registry.acknowledge_playout(
                params={**params, **updates},
                routed_session_id="session-1",
                connection_id="connection-1",
                user_id="user-1",
                request_origin=ORIGIN,
            )
    assert tuple(record.playout_receipts) == ((ref, "unit-1"),)


@pytest.mark.parametrize(
    ("successor_frame_timing", "expected_duplex"),
    (
        ("none", False),
        ("before_downlink_complete", True),
        ("after_downlink_complete", False),
    ),
)
def test_synthesis_downlink_receipt_reports_early_duplex_without_rejecting_playout(
    successor_frame_timing: str, expected_duplex: bool
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    parent_ticket = _media_ticket(activation)
    parent = registry.consume_ticket(parent_ticket, request_origin=ORIGIN)
    assert parent is not None
    parent.route_completed = True
    parent.accepted_frames = 3
    ref = ResponseRef("interaction-1", "response-1", 0)
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-1",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "formal Agent text",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    expected_content = parent.synthesis_content_sha256[(ref, "unit-1")]
    speech_params = {
        "contract_version": "live-voice.contract.v2",
        "request_id": "request-1",
        "operation_id": "operation-1",
        "operation": SYNTHESIZE_OPERATION,
        "correlation_id": "correlation-1",
        "session_id": "session-1",
        "scope": {
            "subject_id": activation["subject_id"],
            "project_id": None,
            "session_id": "session-1",
            "assurance": "authenticated",
        },
        "timeout_ms": 2_000,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-1",
            "response_generation": 0,
        },
        "unit_id": "unit-1",
        "render_plan": {
            "display_text": "formal Agent text",
            "spoken_text": "formal Agent text",
            "transforms": [],
        },
        "authoritative_agent_text": True,
        "locale": "zh-CN",
        "voice": None,
        "required_sample_rate_hz": 16_000,
    }
    speech_result = {
        "ok": True,
        "result": {
            "operation": SYNTHESIZE_OPERATION,
            "response": speech_params["response"],
            "unit_id": "unit-1",
            "audio": {
                "format": "wav_pcm16_mono",
                "sample_rate_hz": 16_000,
                "channel_count": 1,
                "data_base64": base64.b64encode(
                    dedicated_media_registration._wav_bytes(b"\x00\x00" * 320, 16_000)
                ).decode("ascii"),
            },
            "provider": {"provider_id": "provider-1"},
            "presented": False,
        },
    }
    transformed = registry.prepare_synthesis_downlink(
        SYNTHESIZE_OPERATION,
        speech_params,
        SpeechRpcContext(
            str(activation["subject_id"]), "session-1", Assurance.AUTHENTICATED
        ),
        speech_result,
        "session-1",
    )
    audio = transformed["result"]["audio"]  # type: ignore[index]
    assert isinstance(audio, dict)
    assert audio["delivery"] == "dedicated_media_downlink"
    assert "data_base64" not in audio
    assert audio["frame_count"] == 1
    downlink_ticket = _media_ticket(audio)
    downlink = registry.consume_ticket(downlink_ticket, request_origin=ORIGIN)
    assert downlink is not None
    assert downlink.downlink_content_sha256 == expected_content

    next_activation = registry.activate(
        params=_params(
            capture_id="capture-2",
            capture_generation=1,
            track_id="track-2",
        ),
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    next_ticket = _media_ticket(next_activation)
    next_uplink = registry.consume_ticket(next_ticket, request_origin=ORIGIN)
    assert next_uplink is not None
    assert parent.barge_in_capture is False
    assert next_uplink.barge_in_capture is True
    registry.mark_downlink_started(downlink)
    assert downlink.downlink_overlap_record_id == next_uplink.record_id
    assert downlink.downlink_overlap_observed is False
    if successor_frame_timing == "before_downlink_complete":
        registry.accept_frame(
            next_uplink,
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
        )
    assert registry.complete_downlink(
        downlink,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=0,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
            sent_frames=1,
            acknowledged_through_seq=0,
            configured_max_pending_frames=8,
            configured_max_pending_bytes=131_072,
            peak_pending_frames=1,
            peak_pending_bytes=1_320,
        ),
    )
    if successor_frame_timing == "after_downlink_complete":
        registry.accept_frame(
            next_uplink,
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
        )
    assert downlink.downlink_overlap_observed is expected_duplex
    receipt_params = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "response_id": "response-1",
        "response_generation": 0,
        "unit_id": "unit-1",
        "capture_frames_acked": 3,
        "rendered_chunks": 1,
        "rendered_through_seq": 0,
        "playout_queue_capacity": 256,
        "playout_peak_depth": 1,
        "capture_control_ack": "capture_flush_acked",
        "playout_state": "render_completed",
    }
    receipt = registry.acknowledge_playout(
        params=receipt_params,
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )
    assert receipt["duplex_media_observed"] is expected_duplex
    assert tuple(parent.playout_receipts) == ((ref, "unit-1"),)
    assert next_uplink.route_completed is False


def test_agent_notification_from_another_p2_activation_has_zero_speech_authority() -> (
    None
):
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-forged",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-1",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "cross-activation text",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert record.synthesis_content_sha256 == {}


@pytest.mark.parametrize(
    ("request_method", "manifest", "connection_id"),
    [
        ("agent.chat", True, "connection-1"),
        ("live_voice.composition.p2.activate", False, "connection-1"),
        ("live_voice.composition.p2.activate", True, None),
    ],
)
def test_generic_shape_or_disconnected_response_cannot_mint_media_authority(
    request_method: str, manifest: bool, connection_id: str | None
) -> None:
    registry = _active_registry()
    params = _params()
    payload: dict[str, object] = {
        "ok": True,
        "result": {
            "status": "active",
            "session_id": "session-1",
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
    }
    if manifest:
        payload["product_composition"] = _formal_p2_manifest()
    registry.observe_agent_response(
        payload,
        routed_session_id="session-1",
        user_id="user-1",
        connection_id=connection_id,
        request_method=request_method,
    )

    with pytest.raises(MediaTransportViolation) as rejected:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
    assert rejected.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"
    assert registry._records == {}


def test_p2_close_revokes_media_and_leaves_zero_speech_provider_effect() -> None:
    registry = _active_registry()
    params = _params()
    activation = _activate(
        registry,
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    registry.accept_frame(
        record, MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
    )
    registry.complete_route(
        record,
        SimpleNamespace(activated=True, accepted_frames=1),  # type: ignore[arg-type]
    )
    record.synthesis_content_sha256[
        (ResponseRef("interaction-1", "response-1", 0), "unit-1")
    ] = "b" * 64
    prior_digest = str(record.recognition_content_sha256)
    scope = ScopeRef(
        str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    recognize = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="recognize-after-close",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=0,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256=prior_digest,
    )

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "closed",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "interaction_id": "interaction-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
            },
            "product_composition": _formal_p2_manifest(),
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
        request_method="live_voice.composition.p2.close",
    )

    assert registry._records == {}
    assert record.pcm == bytearray()
    assert record.recognition_content_sha256 is None
    assert record.synthesis_content_sha256 == {}
    assert registry.authorize(recognize) is None


def test_replacing_p2_activation_revokes_old_media_before_new_provider_use() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.pcm.extend(b"private-pcm")
    record.recognition_content_sha256 = "a" * 64
    record.synthesis_content_sha256[
        (ResponseRef("interaction-1", "response-1", 0), "unit-1")
    ] = "b" * 64

    replacement = _params(activation_id="activation-2", activation_generation=2)
    _trust_product_activation(registry, replacement)

    assert registry._records == {}
    assert record.pcm == bytearray()
    assert record.recognition_content_sha256 is None
    assert record.synthesis_content_sha256 == {}
