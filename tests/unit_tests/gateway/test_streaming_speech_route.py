# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import threading
import traceback

import pytest

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MEDIA_END_OF_TURN_CAPABILITY,
    MediaAudioFrame,
    MediaAuthorityBinding,
    MediaDirection,
    MediaFrameFormat,
    MediaGenerationBinding,
    MediaGenerationKind,
    MediaDetachReason,
    MediaTransportViolation,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry,
    MEDIA_AUTH_CONTRACT_VERSION,
    MEDIA_ROUTE_PATH,
    handle_registered_media_socket,
)
from jiuwenswarm.gateway.live_voice import (
    dedicated_media_registration,
    streaming_speech_route,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaSocketLeafResult,
)
from jiuwenswarm.gateway.live_voice.streaming_speech_route import (
    StreamingRecognitionFallbackReason,
    StreamingRecognitionOutcome,
    StreamingRecognitionRouteOwner,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechDegradationFact,
    SpeechDegradationReason,
    SpeechRouteTier,
    StreamingSpeechSelection,
)
from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceMetric,
    LiveVoiceObservation,
    LiveVoiceObservabilityCollector,
)
from jiuwenswarm.server.live_voice.latency_measurement import L0Milestone
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEventKind,
    RecognitionHypothesis,
    SpeechMode,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    CapabilityProvenance,
    ProviderTransport,
    RecognitionCommitDisposition,
    RecognitionAudioFrame,
    RecognitionProviderSupport,
    RecognitionTimingBasis,
    RecognitionTurnBoundaryEvent,
    RecognitionTurnBoundaryKind,
    RecognitionTurnDetection,
    StreamingProviderCapability,
    StreamingRecognitionEvent,
    SynthesisProviderSupport,
)


_PROVIDER_REF = ProviderRef("fake-streaming", "formal")
_STREAMING_FALLBACK_FIXTURE = json.loads(
    (
        Path(__file__).parents[2]
        / "fixtures/live_voice_streaming_recognition_v1/backend_fallback.json"
    ).read_text(encoding="utf-8")
)


@pytest.fixture(autouse=True)
def _allow_test_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS",
        "voice.example.test",
    )


def _capability() -> StreamingProviderCapability:
    return StreamingProviderCapability(
        provider=_PROVIDER_REF,
        recognition=RecognitionProviderSupport(
            modes=frozenset({SpeechMode.STREAM}),
            transport=ProviderTransport.NATIVE_STREAM,
            ordered_events=CapabilityProvenance.PROVIDER_NATIVE,
            exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
            provider_cancel_ack=CapabilityProvenance.UNAVAILABLE,
            native_partials=CapabilityProvenance.PROVIDER_NATIVE,
            server_vad=CapabilityProvenance.PROVIDER_NATIVE,
        ),
        synthesis=SynthesisProviderSupport(
            modes=frozenset({SpeechMode.STREAM}),
            transport=ProviderTransport.NATIVE_STREAM,
            ordered_events=CapabilityProvenance.PROVIDER_NATIVE,
            exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )


class _Provider:
    capability = _capability()
    fallback_tier = SpeechRouteTier.BATCH

    def __init__(self, *, block_send: bool = False) -> None:
        self.frames: list[RecognitionAudioFrame] = []
        self.events: asyncio.Queue[StreamingRecognitionEvent] = asyncio.Queue()
        self.cancel_count = 0
        self.close_count = 0
        self.open_count = 0
        self.closed = False
        self.block_send = block_send
        self.send_gate = asyncio.Event()

    async def open_recognition(self, ref, *, timeout_seconds: float) -> None:
        self.open_count += 1
        self.ref = ref

    async def send_recognition_audio(self, frame: RecognitionAudioFrame) -> None:
        if self.block_send:
            await self.send_gate.wait()
        self.frames.append(frame)

    async def commit_recognition(self, ref) -> RecognitionCommitDisposition:
        await self.events.put(
            StreamingRecognitionEvent(
                ref=ref,
                provider=_PROVIDER_REF,
                seq=0,
                audio_cursor=sum(frame.sample_count for frame in self.frames),
                kind=RecognitionEventKind.FINAL,
                hypothesis=RecognitionHypothesis(
                    (RecognitionAlternative("hello", "hello", None),)
                ),
            )
        )
        return RecognitionCommitDisposition.CLIENT_COMMIT_SENT

    async def next_recognition_event(self, ref, *, timeout_seconds: float):
        return await self.events.get()

    async def cancel_recognition(self, ref, *, reason: str = "caller_cancel") -> None:
        self.cancel_count += 1
        self.send_gate.set()

    async def close(self) -> None:
        self.close_count += 1
        self.closed = True
        self.send_gate.set()


class _ServerVadProvider(_Provider):
    def __init__(self, *, block_send: bool = False) -> None:
        super().__init__(block_send=block_send)
        self.commit_count = 0

    async def open_recognition(self, request, *, timeout_seconds: float) -> None:
        del timeout_seconds
        self.open_count += 1
        self.request = request
        self.ref = request.ref

    async def commit_recognition(self, ref) -> RecognitionCommitDisposition:
        assert ref == self.ref
        self.commit_count += 1
        return RecognitionCommitDisposition.SERVER_VAD_OBSERVED


class _DelayedOpenProvider(_Provider):
    def __init__(self) -> None:
        super().__init__()
        self.open_started = asyncio.Event()
        self.open_release = asyncio.Event()

    async def open_recognition(self, ref, *, timeout_seconds: float) -> None:
        del timeout_seconds
        self.open_count += 1
        self.ref = ref
        self.open_started.set()
        await self.open_release.wait()


def _binding() -> MediaAuthorityBinding:
    return MediaAuthorityBinding(
        lease_id="lease-1",
        authority_evidence_id="authority-1",
        connection_id="connection-1",
        connection_epoch=0,
        session_id="session-1",
        media_session_id="media-session-1",
        interaction_id="interaction-1",
        track_id="track-1",
        correlation_id="correlation-1",
        direction=MediaDirection.UPLINK,
        generation=MediaGenerationBinding(MediaGenerationKind.CAPTURE, "capture-1", 0),
        frame_format=MediaFrameFormat(16_000, 320),
    )


def _frame(seq: int) -> MediaAudioFrame:
    return MediaAudioFrame(seq=seq, sample_cursor=seq * 320, samples=(0.0,) * 320)


def _activation_params(index: int = 1) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "interaction_id": f"interaction-{index}",
        "correlation_id": f"correlation-{index}",
        "activation_id": f"activation-{index}",
        "activation_generation": 1,
        "capture_id": f"capture-{index}",
        "capture_generation": 0,
        "track_id": f"track-{index}",
        "sample_rate_hz": 16_000,
        "locale": "en-US",
    }


def _trust_activation(registry: DedicatedMediaProductRegistry, index: int = 1) -> None:
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "active",
                "session_id": "session-1",
                "correlation_id": f"correlation-{index}",
                "interaction_id": f"interaction-{index}",
                "activation_id": f"activation-{index}",
                "activation_generation": 1,
            },
            "product_composition": {
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
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
        request_method="live_voice.composition.p2.activate",
    )


def _media_auth_frame(activation: dict[str, object]) -> str:
    return json.dumps(
        {
            "type": "media.auth",
            "contract_version": MEDIA_AUTH_CONTRACT_VERSION,
            "media_ticket": activation["media_ticket"],
            "binding": activation["binding"],
        },
        separators=(",", ":"),
    )


class _AuthenticatedMediaSocket:
    subprotocol = "live-voice.media.v1"
    request_headers = {"Origin": "https://voice.example.test"}

    def __init__(self, activation: dict[str, object]) -> None:
        self._auth_frame = _media_auth_frame(activation)
        self.recv_count = 0
        self.closes: list[tuple[int, str]] = []

    async def recv(self) -> str:
        self.recv_count += 1
        return self._auth_frame

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closes.append((code, reason))


@pytest.mark.asyncio
async def test_streaming_owner_mirrors_exact_frames_and_returns_one_final() -> None:
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )

    handle, fallback = await owner.begin(_binding())
    assert handle is not None
    assert fallback is None
    owner.offer(handle, _frame(0))
    owner.offer(handle, _frame(1))
    outcome = await owner.finish(handle)

    assert outcome.completed is True
    assert outcome.final_text == "hello"
    assert [frame.seq for frame in provider.frames] == [0, 1]
    assert provider.cancel_count == 0
    await owner.close()
    assert provider.closed is True


@pytest.mark.asyncio
async def test_server_vad_eot_fences_frames_and_finish_coalesces_provider_commit() -> (
    None
):
    provider = _ServerVadProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, fallback = await owner.begin(
        _binding(), turn_detection=RecognitionTurnDetection.server_vad_default()
    )
    assert handle is not None
    assert fallback is None
    owner.offer(handle, _frame(0))
    for _ in range(20):
        if provider.frames:
            break
        await asyncio.sleep(0)
    assert [frame.seq for frame in provider.frames] == [0]
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            0,
            RecognitionTurnBoundaryKind.SPEECH_STARTED,
            "provider-item-1",
            provider_start_ms=100,
        )
    )
    speech_start = await asyncio.wait_for(owner.wait_speech_start(handle), timeout=1)
    assert speech_start.provider_start_ms == 100
    assert speech_start.timing_basis is RecognitionTimingBasis.PROVIDER_TIME
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            1,
            RecognitionTurnBoundaryKind.SPEECH_STOPPED,
            "provider-item-1",
            provider_end_ms=700,
        )
    )
    end_of_turn = await asyncio.wait_for(owner.wait_end_of_turn(handle), timeout=1)
    assert (end_of_turn.provider_start_ms, end_of_turn.provider_end_ms) == (100, 700)
    assert end_of_turn.timing_basis is RecognitionTimingBasis.PROVIDER_TIME
    owner.offer(handle, _frame(1))
    assert [frame.seq for frame in provider.frames] == [0]
    finish_task = asyncio.create_task(owner.finish(handle))
    for _ in range(20):
        if provider.commit_count:
            break
        await asyncio.sleep(0)
    assert provider.commit_count == 1
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            2,
            RecognitionTurnBoundaryKind.COMMITTED,
            "provider-item-1",
        )
    )
    await provider.events.put(
        StreamingRecognitionEvent(
            ref=handle.ref,
            provider=_PROVIDER_REF,
            seq=3,
            audio_cursor=None,
            kind=RecognitionEventKind.FINAL,
            hypothesis=RecognitionHypothesis(
                (RecognitionAlternative("EOT final", "EOT final", None),)
            ),
            timing_basis=RecognitionTimingBasis.PROVIDER_TIME,
        )
    )
    outcome = await asyncio.wait_for(finish_task, timeout=1)
    assert outcome.completed is True
    assert outcome.final_text == "EOT final"
    assert provider.commit_count == 1
    assert provider.cancel_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_manual_finish_and_server_eot_coalesce_when_eot_cancels_the_pump() -> (
    None
):
    provider = _ServerVadProvider(block_send=True)
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, fallback = await owner.begin(
        _binding(), turn_detection=RecognitionTurnDetection.server_vad_default()
    )
    assert handle is not None
    assert fallback is None
    owner.offer(handle, _frame(0))
    await asyncio.sleep(0)
    finish_task = asyncio.create_task(owner.finish(handle))
    await asyncio.sleep(0)
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            0,
            RecognitionTurnBoundaryKind.SPEECH_STARTED,
            "provider-item-race",
            provider_start_ms=100,
        )
    )
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            1,
            RecognitionTurnBoundaryKind.SPEECH_STOPPED,
            "provider-item-race",
            provider_end_ms=700,
        )
    )
    await asyncio.wait_for(owner.wait_end_of_turn(handle), timeout=1)
    for _ in range(20):
        if provider.commit_count:
            break
        await asyncio.sleep(0)
    assert provider.commit_count == 1
    assert provider.frames == []
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            2,
            RecognitionTurnBoundaryKind.COMMITTED,
            "provider-item-race",
        )
    )
    await provider.events.put(
        StreamingRecognitionEvent(
            ref=handle.ref,
            provider=_PROVIDER_REF,
            seq=3,
            audio_cursor=None,
            kind=RecognitionEventKind.FINAL,
            hypothesis=RecognitionHypothesis(
                (RecognitionAlternative("race final", "race final", None),)
            ),
            timing_basis=RecognitionTimingBasis.PROVIDER_TIME,
        )
    )
    outcome = await asyncio.wait_for(finish_task, timeout=1)
    assert outcome.completed is True
    assert outcome.final_text == "race final"
    assert provider.commit_count == 1
    assert provider.cancel_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_end_of_turn_activation_is_additive_exact_and_visible_on_fallback() -> (
    None
):
    provider = _ServerVadProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )

    async def issue_receipt(**_kwargs: object) -> str:
        return "streaming-receipt"

    registry = DedicatedMediaProductRegistry(enabled=True, end_of_turn_enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(owner, receipt_issuer=issue_receipt)
    await registry.prepare_streaming_provider()
    old_params = _activation_params(1)
    _trust_activation(registry, 1)
    old_client = registry.activate(
        params=old_params,
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    assert old_client["status"] == "active"
    assert "end_of_turn" not in old_client

    new_params = _activation_params(2)
    new_params["end_of_turn_capability"] = MEDIA_END_OF_TURN_CAPABILITY
    _trust_activation(registry, 2)
    negotiated = registry.activate(
        params=new_params,
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    assert negotiated["end_of_turn"] == {
        "status": "active",
        "capability_version": MEDIA_END_OF_TURN_CAPABILITY,
        "detector": "server_vad",
        "create_response": False,
        "interrupt_response": False,
    }

    bad_params = _activation_params(3)
    bad_params["end_of_turn_capability"] = "media.end_of_turn.v2"
    _trust_activation(registry, 3)
    with pytest.raises(MediaTransportViolation) as mismatch:
        registry.activate(
            params=bad_params,
            request_origin="https://voice.example.test",
            connection_id="connection-1",
            user_id="user-1",
        )
    assert mismatch.value.reason_id == "MEDIA_END_OF_TURN_CAPABILITY_MISMATCH"

    fallback_registry = DedicatedMediaProductRegistry(
        enabled=True, end_of_turn_enabled=False
    )
    fallback_registry.set_provider_available(True)
    fallback_registry.configure_streaming_recognition(
        owner, receipt_issuer=issue_receipt
    )
    await fallback_registry.prepare_streaming_provider()
    fallback_params = _activation_params(4)
    fallback_params["end_of_turn_capability"] = MEDIA_END_OF_TURN_CAPABILITY
    _trust_activation(fallback_registry, 4)
    fallback = fallback_registry.activate(
        params=fallback_params,
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    assert fallback["end_of_turn"] == {
        "status": "fallback",
        "requested_capability": MEDIA_END_OF_TURN_CAPABILITY,
        "reason_id": "MEDIA_END_OF_TURN_FEATURE_OFF",
        "fallback": "manual",
        "visible": True,
    }
    await owner.close()


@pytest.mark.asyncio
async def test_server_vad_request_fails_before_unsupported_provider_allocation() -> (
    None
):
    provider = _ServerVadProvider()
    provider.capability = replace(
        provider.capability,
        recognition=replace(
            provider.capability.recognition,
            server_vad=CapabilityProvenance.UNAVAILABLE,
        ),
    )
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )

    handle, fallback = await owner.begin(
        _binding(), turn_detection=RecognitionTurnDetection.server_vad_default()
    )

    assert handle is None
    assert fallback is not None
    assert fallback.reason is StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
    assert provider.open_count == 0
    assert provider.frames == []
    assert provider.commit_count == provider.cancel_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_streaming_owner_feature_off_is_visible_and_has_zero_provider() -> None:
    fact = SpeechDegradationFact(
        binding_ref="sha256:" + "a" * 64,
        operation="speech.route.select",
        reason=SpeechDegradationReason.FEATURE_OFF,
        from_tier=SpeechRouteTier.STREAMING,
        to_tier=SpeechRouteTier.BATCH,
        provider_id="openai-streaming-speech",
        visible=True,
        latency_ms=None,
    )
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0, result=StreamingSpeechSelection(SpeechRouteTier.BATCH, None, fact)
        )
    )

    assert await owner.available() is False
    handle, fallback = await owner.begin(_binding())
    assert handle is None
    assert fallback is not None
    assert fallback.fallback_tier is SpeechRouteTier.BATCH
    assert fallback.reason is StreamingRecognitionFallbackReason.FEATURE_OFF
    assert owner.selection_degradation == fact.safe_dict()


@pytest.mark.asyncio
async def test_registry_selection_failure_is_explicit_before_batch_capture() -> None:
    async def unavailable_selection() -> StreamingSpeechSelection:
        raise RuntimeError("PRIVATE_PROVIDER_CONFIGURATION")

    owner = StreamingRecognitionRouteOwner(unavailable_selection)
    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(
        owner,
        receipt_issuer=lambda **_binding: asyncio.sleep(0, result="unused"),
    )
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )

    assert activation["streaming_recognition"] is False
    assert activation["streaming_degradation"] == {
        "reason_id": "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE",
        "fallback_tier": "batch",
        "visible": True,
        "x_obs_event": None,
        "x_obs_metric": None,
    }
    assert "PRIVATE_PROVIDER_CONFIGURATION" not in repr(activation)


@pytest.mark.asyncio
async def test_disabled_registry_never_reads_streaming_selector() -> None:
    selector_calls = 0

    async def exploding_selection() -> StreamingSpeechSelection:
        nonlocal selector_calls
        selector_calls += 1
        raise RuntimeError("selector must remain untouched")

    owner = StreamingRecognitionRouteOwner(exploding_selection)
    registry = DedicatedMediaProductRegistry(enabled=False)
    registry.configure_streaming_recognition(
        owner,
        receipt_issuer=lambda **_binding: asyncio.sleep(0, result="unused"),
    )

    await registry.prepare_streaming_provider()
    assert selector_calls == 0
    assert registry.activate(
        params={},
        request_origin=None,
        connection_id="unused",
    ) == {"status": "disabled", "reason_id": "MEDIA_FEATURE_DISABLED"}


@pytest.mark.asyncio
async def test_streaming_owner_queue_exhaustion_falls_back_without_dropping_capture() -> (
    None
):
    provider = _Provider(block_send=True)
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, _ = await owner.begin(_binding())
    assert handle is not None

    overflow_frame_count = streaming_speech_route._MAX_PENDING_PROVIDER_FRAMES + 2
    for seq in range(overflow_frame_count):
        owner.offer(handle, _frame(seq))
    assert handle.failure is StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED
    outcome = await owner.finish(handle)

    assert outcome.completed is False
    # The Provider owner cannot decide whether a complete bounded capture is
    # available.  It returns TEXT; the product registry may authorize one
    # batch replay after sealing the canonical media digest.
    assert outcome.fallback_tier is SpeechRouteTier.TEXT
    assert outcome.reason is StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED
    assert provider.cancel_count == 1


@pytest.mark.parametrize("defect", ["provider", "sequence", "cursor"])
@pytest.mark.asyncio
async def test_streaming_owner_rejects_non_exact_provider_final(defect: str) -> None:
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, _ = await owner.begin(_binding())
    assert handle is not None
    owner.offer(handle, _frame(0))

    async def commit(ref) -> None:
        await provider.events.put(
            StreamingRecognitionEvent(
                ref=ref,
                provider=(
                    ProviderRef("foreign-provider", "formal")
                    if defect == "provider"
                    else _PROVIDER_REF
                ),
                seq=1 if defect == "sequence" else 0,
                audio_cursor=319 if defect == "cursor" else 320,
                kind=RecognitionEventKind.FINAL,
                hypothesis=RecognitionHypothesis(
                    (RecognitionAlternative("hello", "hello", None),)
                ),
            )
        )

    provider.commit_recognition = commit
    outcome = await owner.finish(handle)

    assert outcome.completed is False
    assert outcome.fallback_tier is SpeechRouteTier.TEXT
    assert outcome.reason is StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
    assert provider.cancel_count == 1


@pytest.mark.asyncio
async def test_invalid_provider_event_traceback_does_not_retain_transcript() -> None:
    private_text = "PRIVATE_STREAMING_TRANSCRIPT"
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, _ = await owner.begin(_binding())
    assert handle is not None
    owner.offer(handle, _frame(0))

    async def commit(ref) -> None:
        await provider.events.put(
            StreamingRecognitionEvent(
                ref=ref,
                provider=ProviderRef("foreign-provider", "formal"),
                seq=0,
                audio_cursor=320,
                kind=RecognitionEventKind.FINAL,
                hypothesis=RecognitionHypothesis(
                    (RecognitionAlternative(private_text, private_text, None),)
                ),
            )
        )

    provider.commit_recognition = commit
    outcome = await owner.finish(handle)

    assert outcome.completed is False
    assert handle.event_task is not None
    failure = handle.event_task.exception()
    assert failure is not None
    rendered = "".join(
        traceback.TracebackException.from_exception(
            failure, capture_locals=True
        ).format()
    )
    assert private_text not in rendered
    assert private_text not in repr(outcome)


@pytest.mark.asyncio
async def test_streaming_owner_rejects_non_contiguous_product_frame_before_wire() -> (
    None
):
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, _ = await owner.begin(_binding())
    assert handle is not None
    owner.offer(handle, _frame(1))
    outcome = await owner.finish(handle)

    assert outcome.completed is False
    assert outcome.reason is StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
    assert provider.frames == []
    assert provider.cancel_count == 1


@pytest.mark.asyncio
async def test_streaming_owner_revoke_cancels_a_finish_waiting_on_provider_commit() -> (
    None
):
    provider = _Provider()
    commit_entered = asyncio.Event()

    async def blocked_commit(_ref) -> None:
        commit_entered.set()
        await asyncio.Event().wait()

    provider.commit_recognition = blocked_commit
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, _ = await owner.begin(_binding())
    assert handle is not None
    owner.offer(handle, _frame(0))
    finishing = asyncio.create_task(owner.finish(handle))
    await asyncio.wait_for(commit_entered.wait(), timeout=1.0)

    await asyncio.wait_for(owner.abort(handle), timeout=1.0)

    assert finishing.cancelled()
    assert handle.settled is True
    assert handle.finish_task is None
    assert provider.cancel_count >= 1
    assert handle.pump_task is not None and handle.pump_task.done()
    assert handle.event_task is not None and handle.event_task.done()


@pytest.mark.asyncio
async def test_streaming_owner_caller_cancel_retires_exact_provider_stream() -> None:
    provider = _Provider()
    commit_entered = asyncio.Event()

    async def blocked_commit(_ref) -> None:
        commit_entered.set()
        await asyncio.Event().wait()

    provider.commit_recognition = blocked_commit
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, _ = await owner.begin(_binding())
    assert handle is not None
    owner.offer(handle, _frame(0))
    finishing = asyncio.create_task(owner.finish(handle))
    await asyncio.wait_for(commit_entered.wait(), timeout=1.0)

    finishing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await finishing

    assert provider.cancel_count == 1
    assert handle.settled is True
    assert handle.finish_task is None
    assert owner._handles == {}
    await owner.close()


@pytest.mark.asyncio
async def test_precommit_event_wait_outlives_short_final_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_FINAL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(streaming_speech_route, "_PRECOMMIT_EVENT_TIMEOUT_SECONDS", 0.5)
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, _ = await owner.begin(_binding())
    assert handle is not None

    await asyncio.sleep(0.1)
    assert handle.event_task is not None and not handle.event_task.done()
    owner.offer(handle, _frame(0))
    outcome = await owner.finish(handle)

    assert outcome.completed is True
    assert provider.cancel_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_server_vad_final_may_arrive_before_browser_finish() -> None:
    provider = _ServerVadProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, fallback = await owner.begin(
        _binding(), turn_detection=RecognitionTurnDetection.server_vad_default()
    )
    assert handle is not None
    assert fallback is None
    owner.offer(handle, _frame(0))
    for _ in range(20):
        if provider.frames:
            break
        await asyncio.sleep(0)
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            0,
            RecognitionTurnBoundaryKind.SPEECH_STARTED,
            "provider-item-early-final",
            provider_start_ms=100,
        )
    )
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            1,
            RecognitionTurnBoundaryKind.SPEECH_STOPPED,
            "provider-item-early-final",
            provider_end_ms=700,
        )
    )
    await provider.events.put(
        StreamingRecognitionEvent(
            ref=handle.ref,
            provider=_PROVIDER_REF,
            seq=2,
            audio_cursor=None,
            kind=RecognitionEventKind.FINAL,
            hypothesis=RecognitionHypothesis(
                (RecognitionAlternative("early final", "early final", None),)
            ),
            timing_basis=RecognitionTimingBasis.PROVIDER_TIME,
        )
    )
    end_of_turn = await asyncio.wait_for(owner.wait_end_of_turn(handle), timeout=1)
    assert (end_of_turn.provider_start_ms, end_of_turn.provider_end_ms) == (100, 700)
    for _ in range(20):
        if handle.event_task is not None and handle.event_task.done():
            break
        await asyncio.sleep(0)
    assert handle.event_task is not None and handle.event_task.done()

    outcome = await asyncio.wait_for(owner.finish(handle), timeout=1)

    assert outcome.completed is True
    assert outcome.final_text == "early final"
    assert provider.commit_count == 0
    assert provider.cancel_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_provider_session_budget_covers_precommit_and_final_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_OPEN_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(streaming_speech_route, "_PRECOMMIT_EVENT_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(streaming_speech_route, "_FINAL_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(
        streaming_speech_route, "_RECOGNITION_SESSION_TIMEOUT_SECONDS", 0.35
    )
    provider = _Provider()
    observed_timeout: float | None = None

    async def open_with_observed_budget(request, *, timeout_seconds: float) -> None:
        nonlocal observed_timeout
        observed_timeout = timeout_seconds
        provider.open_count += 1
        provider.ref = request.ref

    provider.open_recognition = open_with_observed_budget
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )

    handle, fallback = await owner.begin(_binding())

    assert handle is not None
    assert fallback is None
    assert observed_timeout == pytest.approx(0.35)
    assert observed_timeout > streaming_speech_route._OPEN_TIMEOUT_SECONDS
    await owner.abort(handle)
    await owner.close()


@pytest.mark.asyncio
async def test_streaming_owner_capacity_rejects_before_second_provider_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_MAX_ACTIVE_STREAMS", 1)
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    first, first_fallback = await owner.begin(_binding())
    assert first is not None
    assert first_fallback is None
    second_binding = replace(
        _binding(),
        media_session_id="media-session-2",
        generation=MediaGenerationBinding(MediaGenerationKind.CAPTURE, "capture-2", 0),
    )

    second, second_fallback = await owner.begin(second_binding)

    assert second is None
    assert second_fallback is not None
    assert second_fallback.reason is StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED
    assert provider.open_count == 1
    await owner.abort(first)
    assert owner._handles == {}
    await owner.close()


@pytest.mark.asyncio
async def test_streaming_owner_close_aborts_every_exact_active_stream() -> None:
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, fallback = await owner.begin(_binding())
    assert handle is not None
    assert fallback is None
    owner.offer(handle, _frame(0))

    await owner.close()

    assert handle.settled is True
    assert provider.cancel_count >= 1
    assert provider.closed is True
    assert owner._handles == {}


@pytest.mark.asyncio
async def test_streaming_owner_close_settles_cooperative_open_reservation() -> None:
    provider = _DelayedOpenProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    beginning = asyncio.create_task(owner.begin(_binding()))
    await provider.open_started.wait()

    await owner.close()

    with pytest.raises(asyncio.CancelledError):
        await beginning
    assert owner._opening_tasks == {}
    assert owner._handles == {}
    assert owner._retained_provider_tasks == set()
    assert provider.open_count == 1
    assert provider.close_count == 1
    assert provider.closed is True
    await owner.close()
    assert provider.close_count == 1


@pytest.mark.asyncio
async def test_streaming_owner_close_reports_cancellation_hostile_open_until_settled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        streaming_speech_route, "_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS", 0.01
    )
    provider = _Provider()
    open_started = asyncio.Event()
    open_cancelled = asyncio.Event()
    open_release = asyncio.Event()

    async def cancellation_hostile_open(ref, *, timeout_seconds: float) -> None:
        del timeout_seconds
        provider.open_count += 1
        provider.ref = ref
        open_started.set()
        while not open_release.is_set():
            try:
                await open_release.wait()
            except asyncio.CancelledError:
                open_cancelled.set()

    provider.open_recognition = cancellation_hostile_open
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    beginning = asyncio.create_task(owner.begin(_binding()))
    await open_started.wait()

    with pytest.raises(RuntimeError, match="cleanup is incomplete"):
        await asyncio.wait_for(owner.close(), timeout=0.2)

    assert open_cancelled.is_set()
    assert beginning.done() is False
    assert len(owner._opening_tasks) == 1
    assert tuple(owner._handles.values()) == (None,)
    assert provider.close_count == 1
    assert provider.closed is True

    open_release.set()
    handle, fallback = await asyncio.wait_for(beginning, timeout=1.0)
    assert handle is None
    assert fallback is not None
    assert fallback.reason is StreamingRecognitionFallbackReason.ROUTE_ABORTED
    assert owner._opening_tasks == {}
    assert owner._handles == {}

    await owner.close()
    assert owner._retained_provider_tasks == set()
    assert provider.close_count == 1


@pytest.mark.asyncio
async def test_streaming_owner_hard_bounds_provider_send_that_swallows_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_PROVIDER_SEND_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        streaming_speech_route, "_PROVIDER_CANCEL_TIMEOUT_SECONDS", 0.01
    )
    monkeypatch.setattr(
        streaming_speech_route, "_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS", 0.01
    )
    provider = _Provider()
    release = asyncio.Event()
    swallowed_cancel = asyncio.Event()

    async def uncooperative_send(_frame: RecognitionAudioFrame) -> None:
        try:
            await release.wait()
        except asyncio.CancelledError:
            swallowed_cancel.set()
            await release.wait()

    async def bounded_cancel(_ref, *, reason: str = "caller_cancel") -> None:
        del reason
        provider.cancel_count += 1

    provider.send_recognition_audio = uncooperative_send
    provider.cancel_recognition = bounded_cancel
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, _ = await owner.begin(_binding())
    assert handle is not None
    owner.offer(handle, _frame(0))

    started = asyncio.get_running_loop().time()
    outcome = await owner.finish(handle)
    elapsed = asyncio.get_running_loop().time() - started

    assert outcome.completed is False
    assert outcome.reason is StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE
    assert elapsed < 0.2
    assert swallowed_cancel.is_set()
    assert 1 <= len(owner._retained_provider_tasks) <= 2
    release.set()
    for _ in range(50):
        if not owner._retained_provider_tasks:
            break
        await asyncio.sleep(0.01)
    assert owner._retained_provider_tasks == set()
    await owner.close()
    assert owner._provider_close_complete is True
    await owner.close()


@pytest.mark.asyncio
async def test_provider_task_capacity_atomically_rejects_second_hostile_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_MAX_RETAINED_PROVIDER_TASKS", 1)
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None),
        )
    )
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release = asyncio.Event()
    swallowed_cancel = asyncio.Event()

    async def hostile_call(started: asyncio.Event) -> None:
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            swallowed_cancel.set()
            await release.wait()

    first = asyncio.create_task(
        owner._bounded_provider_call(
            lambda: hostile_call(first_started),
            timeout_seconds=0.05,
            task_name="first-hostile-provider-call",
        )
    )
    await first_started.wait()

    with pytest.raises(RuntimeError, match="cleanup capacity is exhausted"):
        await owner._bounded_provider_call(
            lambda: hostile_call(second_started),
            timeout_seconds=0.05,
            task_name="second-hostile-provider-call",
        )

    assert second_started.is_set() is False
    with pytest.raises(TimeoutError, match="provider operation timed out"):
        await first
    assert swallowed_cancel.is_set()
    assert owner._provider_task_capacity_in_use == 1
    assert len(owner._provider_capacity_tasks) == 1
    assert len(owner._retained_provider_tasks) == 1

    release.set()
    for _ in range(100):
        if owner._provider_task_capacity_in_use == 0:
            break
        await asyncio.sleep(0.001)
    assert owner._provider_task_capacity_in_use == 0
    assert owner._provider_capacity_tasks == set()
    assert owner._retained_provider_tasks == set()

    assert (
        await owner._bounded_provider_call(
            lambda: asyncio.sleep(0, result="released"),
            timeout_seconds=0.05,
            task_name="provider-call-after-release",
        )
        == "released"
    )
    assert owner._provider_task_capacity_in_use == 0
    await owner.close()


@pytest.mark.asyncio
async def test_provider_task_capacity_releases_success_error_and_process_control() -> (
    None
):
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None),
        )
    )

    assert (
        await owner._bounded_provider_call(
            lambda: asyncio.sleep(0, result="ok"),
            timeout_seconds=0.05,
            task_name="successful-provider-call",
        )
        == "ok"
    )
    assert owner._provider_task_capacity_in_use == 0

    async def fail() -> None:
        raise ValueError("provider failure")

    with pytest.raises(ValueError, match="provider failure"):
        await owner._bounded_provider_call(
            fail,
            timeout_seconds=0.05,
            task_name="failed-provider-call",
        )
    assert owner._provider_task_capacity_in_use == 0

    async def stop_process() -> None:
        raise GeneratorExit("private-provider-detail")

    with pytest.raises(GeneratorExit):
        await owner._bounded_provider_call(
            stop_process,
            timeout_seconds=0.05,
            task_name="process-control-provider-call",
        )
    assert owner._provider_task_capacity_in_use == 0

    cancel_started = asyncio.Event()

    async def cooperative_cancel() -> None:
        cancel_started.set()
        await asyncio.Event().wait()

    cancelled = asyncio.create_task(
        owner._bounded_provider_call(
            cooperative_cancel,
            timeout_seconds=60.0,
            task_name="cancelled-provider-call",
        )
    )
    await cancel_started.wait()
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    for _ in range(10):
        if owner._provider_task_capacity_in_use == 0:
            break
        await asyncio.sleep(0)
    assert owner._provider_task_capacity_in_use == 0
    assert owner._provider_capacity_tasks == set()
    assert owner._retained_provider_tasks == set()
    await owner.close()


@pytest.mark.asyncio
async def test_business_capacity_never_blocks_provider_cleanup_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_MAX_RETAINED_PROVIDER_TASKS", 1)
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None),
        )
    )
    provider = _Provider()
    blocker_started = asyncio.Event()
    blocker_release = asyncio.Event()

    async def hostile_blocker() -> None:
        blocker_started.set()
        try:
            await blocker_release.wait()
        except asyncio.CancelledError:
            await blocker_release.wait()

    blocker = asyncio.create_task(
        owner._bounded_provider_call(
            hostile_blocker,
            timeout_seconds=0.05,
            task_name="provider-capacity-blocker",
        )
    )
    await blocker_started.wait()

    await owner._bounded_provider_close(provider.close)
    assert provider.close_count == 1
    assert provider.closed is True
    assert owner._provider_cleanup_capacity_in_use == 0
    assert owner._provider_close_obligations == {}

    with pytest.raises(TimeoutError, match="provider operation timed out"):
        await blocker
    blocker_release.set()
    for _ in range(100):
        if owner._provider_task_capacity_in_use == 0:
            break
        await asyncio.sleep(0.001)

    assert owner._provider_task_capacity_in_use == 0
    await owner.close()


@pytest.mark.asyncio
async def test_late_provider_obligation_survives_full_cleanup_reserve_until_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_MAX_PROVIDER_CLEANUP_TASKS", 1)
    monkeypatch.setattr(streaming_speech_route, "_PROVIDER_CLOSE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(streaming_speech_route, "_OPEN_TIMEOUT_SECONDS", 0.01)
    blocker = _Provider()
    late = _Provider()
    blocker_started = asyncio.Event()
    blocker_release = asyncio.Event()
    selector_started = asyncio.Event()
    selector_release = asyncio.Event()

    async def hostile_blocker_close() -> None:
        blocker.close_count += 1
        blocker_started.set()
        try:
            await blocker_release.wait()
        except asyncio.CancelledError:
            await blocker_release.wait()
        blocker.closed = True

    blocker.close = hostile_blocker_close

    async def late_selector() -> StreamingSpeechSelection:
        selector_started.set()
        while not selector_release.is_set():
            try:
                await selector_release.wait()
            except asyncio.CancelledError:
                continue
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, late, None)

    owner = StreamingRecognitionRouteOwner(late_selector)
    first_close = asyncio.create_task(owner._bounded_provider_close(blocker.close))
    await blocker_started.wait()
    with pytest.raises(TimeoutError, match="provider operation timed out"):
        await first_close
    assert owner._provider_cleanup_capacity_in_use == 1

    availability = asyncio.create_task(owner.available())
    await selector_started.wait()
    assert await availability is False
    selector_release.set()
    for _ in range(100):
        if len(owner._provider_close_obligations) == 2:
            break
        await asyncio.sleep(0.001)

    # The late selector's close task could not enter the full cleanup reserve,
    # but the exact Provider remains retained for owner.close().
    assert len(owner._provider_close_obligations) == 2
    assert late.close_count == 0
    assert owner._provider_cleanup_capacity_in_use == 1

    blocker_release.set()
    for _ in range(100):
        if owner._provider_cleanup_capacity_in_use == 0:
            break
        await asyncio.sleep(0.001)
    await owner.close()

    assert [blocker.close_count, late.close_count] == [1, 1]
    assert [blocker.closed, late.closed] == [True, True]
    assert owner._provider_close_obligations == {}
    assert owner._provider_close_tasks == {}
    assert owner._provider_cleanup_tasks == set()
    assert owner._provider_cleanup_capacity_in_use == 0
    assert owner._provider_close_obligation_reservations == set()
    assert owner._provider_capacity_tasks == set()
    assert owner._provider_task_capacity_in_use == 0


@pytest.mark.asyncio
async def test_close_obligation_reservation_bounds_late_selector_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_MAX_PROVIDER_CLOSE_OBLIGATIONS", 1)
    monkeypatch.setattr(streaming_speech_route, "_OPEN_TIMEOUT_SECONDS", 0.01)
    provider = _Provider()
    selector_started = asyncio.Event()
    selector_release = asyncio.Event()
    selector_calls = 0

    async def hostile_selector() -> StreamingSpeechSelection:
        nonlocal selector_calls
        selector_calls += 1
        selector_started.set()
        while not selector_release.is_set():
            try:
                await selector_release.wait()
            except asyncio.CancelledError:
                continue
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingRecognitionRouteOwner(hostile_selector)
    first = asyncio.create_task(owner.available())
    await selector_started.wait()
    assert await first is False
    assert len(owner._provider_close_obligation_reservations) == 1

    # The only obligation slot was reserved before selector allocation, so a
    # successor cannot allocate a Provider that the bounded queue cannot own.
    assert await owner.available() is False
    assert selector_calls == 1

    selector_release.set()
    for _ in range(100):
        if provider.closed:
            break
        await asyncio.sleep(0.001)
    assert provider.close_count == 1
    await owner.close()
    assert owner._provider_close_obligation_reservations == set()
    assert owner._provider_close_obligations == {}
    assert owner._provider_close_tasks == {}
    assert owner._provider_cleanup_tasks == set()
    assert owner._provider_cleanup_capacity_in_use == 0
    assert owner._provider_capacity_tasks == set()
    assert owner._provider_task_capacity_in_use == 0


@pytest.mark.asyncio
async def test_provider_close_error_retains_exact_obligation_for_one_retry() -> None:
    provider = _Provider()
    close_calls = 0

    async def one_shot_error_close() -> None:
        nonlocal close_calls
        close_calls += 1
        if close_calls == 1:
            raise ValueError("private-provider-detail")
        provider.closed = True

    provider.close = one_shot_error_close
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    assert await owner.available()

    with pytest.raises(RuntimeError, match="provider close failed"):
        await owner.close()
    assert len(owner._provider_close_obligations) == 1
    assert owner._provider_cleanup_capacity_in_use == 0

    await owner.close()
    assert close_calls == 2
    assert provider.closed is True
    assert owner._provider_close_obligations == {}
    assert owner._provider_close_tasks == {}
    assert owner._provider_cleanup_capacity_in_use == 0


@pytest.mark.asyncio
async def test_streaming_owner_close_hard_bounds_provider_that_swallows_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming_speech_route, "_PROVIDER_CLOSE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        streaming_speech_route, "_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS", 0.01
    )
    provider = _Provider()
    release = asyncio.Event()
    swallowed_cancel = asyncio.Event()

    async def uncooperative_close() -> None:
        try:
            await release.wait()
        except asyncio.CancelledError:
            swallowed_cancel.set()
            await release.wait()

    provider.close = uncooperative_close
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    assert await owner.available()

    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError, match="provider operation timed out"):
        await owner.close()
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.2
    assert swallowed_cancel.is_set()
    assert len(owner._retained_provider_tasks) == 1
    assert owner._provider_task_capacity_in_use == 0
    assert owner._provider_cleanup_capacity_in_use == 1
    release.set()
    for _ in range(50):
        if not owner._retained_provider_tasks:
            break
        await asyncio.sleep(0.01)
    assert owner._retained_provider_tasks == set()
    assert owner._provider_task_capacity_in_use == 0
    assert owner._provider_cleanup_capacity_in_use == 0

    await owner.close()
    assert owner._provider_close_complete is True


@pytest.mark.asyncio
async def test_streaming_owner_close_rethrows_process_control_after_active_cleanup() -> (
    None
):
    provider = _Provider()

    async def process_control_cancel(_ref, *, reason: str = "caller_cancel") -> None:
        del reason
        raise GeneratorExit()

    provider.cancel_recognition = process_control_cancel
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, fallback = await owner.begin(_binding())
    assert handle is not None
    assert fallback is None

    with pytest.raises(GeneratorExit):
        await owner.close()

    assert handle.settled is True
    assert owner._handles == {}
    assert provider.closed is True
    assert owner._provider_close_complete is True
    await owner.close()


@pytest.mark.asyncio
async def test_streaming_owner_transport_process_control_allows_exact_close_retry() -> (
    None
):
    provider = _Provider()
    close_calls = 0

    async def one_shot_process_control_close() -> None:
        nonlocal close_calls
        close_calls += 1
        if close_calls == 1:
            raise GeneratorExit()
        provider.closed = True

    provider.close = one_shot_process_control_close
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    assert await owner.available()

    with pytest.raises(GeneratorExit):
        await owner.close()
    assert owner._provider_close_complete is False
    assert owner._provider_task_capacity_in_use == 0
    assert len(owner._provider_close_obligations) == 1
    assert owner._provider_cleanup_capacity_in_use == 0

    await owner.close()
    assert close_calls == 2
    assert provider.closed is True
    assert owner._provider_close_complete is True
    assert owner._provider_close_obligations == {}
    assert owner._provider_close_tasks == {}
    assert owner._provider_cleanup_capacity_in_use == 0


@pytest.mark.asyncio
async def test_streaming_owner_open_process_control_releases_reserved_identity() -> (
    None
):
    provider = _Provider()
    open_calls = 0

    async def one_shot_process_control_open(ref, *, timeout_seconds: float) -> None:
        nonlocal open_calls
        del timeout_seconds
        open_calls += 1
        if open_calls == 1:
            raise GeneratorExit("private-provider-detail")
        provider.ref = ref

    provider.open_recognition = one_shot_process_control_open
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )

    with pytest.raises(GeneratorExit) as raised:
        await owner.begin(_binding())
    assert raised.value.args == ()
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert owner._handles == {}
    assert owner._provider_task_capacity_in_use == 0

    handle, fallback = await owner.begin(_binding())
    assert handle is not None
    assert fallback is None
    await owner.abort(handle)
    await owner.close()


@pytest.mark.asyncio
async def test_streaming_owner_finish_process_control_retires_exact_stream() -> None:
    provider = _Provider()

    async def process_control_commit(_ref) -> None:
        raise GeneratorExit("private-provider-detail")

    provider.commit_recognition = process_control_commit
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    handle, fallback = await owner.begin(_binding())
    assert handle is not None
    assert fallback is None
    owner.offer(handle, _frame(0))

    with pytest.raises(GeneratorExit) as raised:
        await owner.finish(handle)
    assert raised.value.args == ()
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert provider.cancel_count == 1
    assert handle.settled is True
    assert owner._handles == {}

    await owner.close()


@pytest.mark.asyncio
async def test_streaming_owner_close_cancels_cooperative_provider_selection() -> None:
    provider = _Provider()
    selector_started = asyncio.Event()
    selector_release = asyncio.Event()

    async def delayed_selector() -> StreamingSpeechSelection:
        selector_started.set()
        await selector_release.wait()
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingRecognitionRouteOwner(delayed_selector)
    available_task = asyncio.create_task(owner.available())
    await selector_started.wait()
    close_task = asyncio.create_task(owner.close())
    await asyncio.sleep(0)
    selector_release.set()

    assert await available_task is False
    await close_task
    # The cooperative selector was cancelled before it allocated/published
    # this Provider, so there is no Provider resource to close.
    assert provider.closed is False
    assert owner._provider_close_complete is True
    assert owner._provider_close_obligation_reservations == set()
    assert await owner.available() is False


@pytest.mark.asyncio
async def test_streaming_owner_close_hard_bounds_selector_that_swallows_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _Provider()
    selector_started = asyncio.Event()
    selector_release = asyncio.Event()

    async def uncooperative_selector() -> StreamingSpeechSelection:
        selector_started.set()
        while not selector_release.is_set():
            try:
                await selector_release.wait()
            except asyncio.CancelledError:
                continue
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    monkeypatch.setattr(
        streaming_speech_route, "_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS", 0.01
    )
    owner = StreamingRecognitionRouteOwner(uncooperative_selector)
    available_task = asyncio.create_task(owner.available())
    await selector_started.wait()

    with pytest.raises(RuntimeError, match="cleanup is incomplete"):
        await asyncio.wait_for(owner.close(), timeout=0.2)
    assert available_task.done() is False

    selector_release.set()
    assert await available_task is False
    for _ in range(100):
        if provider.closed:
            break
        await asyncio.sleep(0.001)
    # The selector ignored cancellation and allocated after close; the owner
    # must close that late Provider before the selector task can settle.
    assert provider.closed is True
    await owner.close()


@pytest.mark.asyncio
async def test_two_late_selectors_close_each_exact_provider_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = [_Provider(), _Provider()]
    selector_releases = [asyncio.Event(), asyncio.Event()]
    selector_started = [asyncio.Event(), asyncio.Event()]
    close_started = [asyncio.Event(), asyncio.Event()]
    close_release = asyncio.Event()
    calls = 0

    for index, provider in enumerate(providers):

        async def blocking_close(
            index: int = index, provider: _Provider = provider
        ) -> None:
            provider.close_count += 1
            provider.closed = True
            close_started[index].set()
            await close_release.wait()

        provider.close = blocking_close

    async def late_selector() -> StreamingSpeechSelection:
        nonlocal calls
        index = calls
        calls += 1
        selector_started[index].set()
        while not selector_releases[index].is_set():
            try:
                await selector_releases[index].wait()
            except asyncio.CancelledError:
                continue
        return StreamingSpeechSelection(
            SpeechRouteTier.STREAMING, providers[index], None
        )

    monkeypatch.setattr(streaming_speech_route, "_OPEN_TIMEOUT_SECONDS", 0.01)
    owner = StreamingRecognitionRouteOwner(late_selector)

    first = asyncio.create_task(owner.available())
    await selector_started[0].wait()
    assert await first is False
    second = asyncio.create_task(owner.available())
    await selector_started[1].wait()
    assert await second is False

    selector_releases[0].set()
    selector_releases[1].set()
    await asyncio.wait_for(
        asyncio.gather(close_started[0].wait(), close_started[1].wait()),
        timeout=0.5,
    )
    close_release.set()
    for _ in range(100):
        if not owner._retained_provider_tasks:
            break
        await asyncio.sleep(0.001)

    assert [provider.closed for provider in providers] == [True, True]
    assert [provider.close_count for provider in providers] == [1, 1]
    await owner.close()
    assert owner._provider_close_obligations == {}
    assert owner._provider_close_tasks == {}
    assert owner._provider_cleanup_tasks == set()
    assert owner._provider_cleanup_capacity_in_use == 0
    assert owner._provider_close_obligation_reservations == set()
    assert owner._provider_capacity_tasks == set()
    assert owner._provider_task_capacity_in_use == 0


async def _wait_for_diagnostics(
    observations: list[LiveVoiceObservation],
    metrics: list[LiveVoiceMetric],
    *,
    count: int = 1,
) -> None:
    for _ in range(200):
        if len(observations) >= count and len(metrics) >= count:
            return
        await asyncio.sleep(0.001)
    raise AssertionError("streaming diagnostics did not drain")


def _prepare_fallback_result_authority(
    registry: DedicatedMediaProductRegistry,
    *,
    index: int,
) -> dict[str, object]:
    _trust_activation(registry, index)
    activation_params = _activation_params(index)
    activation = registry.activate(
        params=activation_params,
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    record = registry.consume_ticket(
        str(activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert record is not None
    registry.accept_frame(record, _frame(0))
    registry.complete_route(
        record,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=1,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
        ),
    )
    registry._retain_streaming_outcome(
        record,
        StreamingRecognitionOutcome(
            completed=False,
            final_text=None,
            provider=None,
            fallback_tier=SpeechRouteTier.BATCH,
            reason=StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED,
        ),
    )
    return {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": activation_params["correlation_id"],
        "interaction_id": activation_params["interaction_id"],
        "capture_id": activation_params["capture_id"],
        "capture_generation": activation_params["capture_generation"],
        "track_id": activation_params["track_id"],
    }


@pytest.mark.asyncio
async def test_streaming_owner_selector_process_control_is_content_free() -> None:
    async def process_control_selector() -> StreamingSpeechSelection:
        raise GeneratorExit("PRIVATE_SELECTOR_CONFIGURATION")

    owner = StreamingRecognitionRouteOwner(process_control_selector)
    with pytest.raises(GeneratorExit) as raised:
        await owner.available()
    assert raised.value.args == ()
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "PRIVATE_SELECTOR_CONFIGURATION" not in "".join(
        traceback.format_exception(raised.value)
    )
    assert owner._provider_close_obligation_reservations == set()
    assert owner._provider_close_obligations == {}

    await owner.close()


@pytest.mark.asyncio
async def test_registry_returns_streaming_final_without_batch_audio_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    receipts: list[dict[str, object]] = []
    emitted: list[dict[str, object]] = []
    monkeypatch.setattr(
        dedicated_media_registration,
        "emit_runtime_l0_milestone",
        lambda **kwargs: emitted.append(kwargs) or True,
    )

    async def issue_receipt(**binding: object) -> str:
        assert emitted[-1]["milestone"] is L0Milestone.STT_FINAL_AVAILABLE
        receipts.append(dict(binding))
        return "streaming-voice-receipt-12345678901234567890"

    observations: list[LiveVoiceObservation] = []
    metrics: list[LiveVoiceMetric] = []
    collector = LiveVoiceObservabilityCollector(
        observation_sink=observations.append,
        metric_sink=metrics.append,
    )
    registry = DedicatedMediaProductRegistry(
        enabled=True, streaming_observability=collector
    )
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(owner, receipt_issuer=issue_receipt)
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    assert activation["streaming_recognition"] is True
    record = registry.consume_ticket(
        str(activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert record is not None
    await registry.begin_streaming_recognition(record)
    for seq in range(2):
        frame = _frame(seq)
        registry.accept_frame(record, frame)
        registry.accept_streaming_frame(record, frame)
    registry.complete_route(
        record,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=2,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
        ),
    )
    await registry.finish_streaming_recognition(record)
    result = await registry.streaming_recognition_result(
        params={
            "session_id": "session-1",
            "subject_id": activation["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "capture_id": "capture-1",
            "capture_generation": 0,
            "track_id": "track-1",
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )

    assert result["status"] == "completed"
    assert result["final_text"] == "hello"
    assert result["voice_commit_receipt"] == (
        "streaming-voice-receipt-12345678901234567890"
    )
    assert len(receipts) == 1
    assert receipts[0]["text"] == "hello"
    assert [item["milestone"] for item in emitted].count(
        L0Milestone.STT_FINAL_AVAILABLE
    ) == 1
    assert "hello" not in repr(emitted)
    assert record.pcm == bytearray()
    assert record.recognition_content_sha256 is not None
    await _wait_for_diagnostics(observations, metrics)
    assert [item.event_name for item in observations] == ["segment.completed"]
    assert [item.metric_name for item in metrics] == ["live_voice.segment_latency_ms"]
    assert observations[0].binding.interaction_id == "interaction-1"
    assert observations[0].route.capability_provider == "fake-streaming"
    assert "hello" not in repr(observations + metrics)
    registry.close_streaming_observability()


@pytest.mark.asyncio
async def test_continued_capture_uses_streaming_eot_without_minting_commit_receipt() -> (
    None
):
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    receipts: list[dict[str, object]] = []

    async def issue_receipt(**binding: object) -> str:
        receipts.append(dict(binding))
        return "streaming-voice-receipt-must-not-be-issued"

    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(owner, receipt_issuer=issue_receipt)
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    predecessor_activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    predecessor = registry.consume_ticket(
        str(predecessor_activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert predecessor is not None
    await registry.begin_streaming_recognition(predecessor)
    predecessor_frame = _frame(0)
    registry.accept_frame(predecessor, predecessor_frame)
    registry.accept_streaming_frame(predecessor, predecessor_frame)
    registry.complete_route(
        predecessor,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=1,
            close_result=None,
            reason_id=MediaDetachReason.RECOGNITION_CONTINUATION,
        ),
    )
    await registry.finish_streaming_recognition(predecessor)
    assert predecessor.recognition_continuation_predecessor is True
    assert receipts == []
    assert predecessor.streaming_voice_commit_receipt is None
    with pytest.raises(
        MediaTransportViolation, match="authority is absent or stale"
    ):
        await registry.streaming_recognition_result(
            params={
                "session_id": "session-1",
                "subject_id": predecessor_activation["subject_id"],
                "correlation_id": "correlation-1",
                "interaction_id": "interaction-1",
                "capture_id": "capture-1",
                "capture_generation": 0,
                "track_id": "track-1",
            },
            routed_session_id="session-1",
            connection_id="connection-1",
            request_origin="https://voice.example.test",
        )

    successor_params = {
        **_activation_params(),
        "capture_id": "capture-2",
        "capture_generation": 1,
        "track_id": "track-2",
        "recognition_predecessor_subject_id": predecessor_activation["subject_id"],
    }
    successor_activation = registry.activate(
        params=successor_params,
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    successor = registry.consume_ticket(
        str(successor_activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert successor is not None
    assert successor.recognition_predecessor_subject_id == (
        predecessor_activation["subject_id"]
    )
    await registry.begin_streaming_recognition(successor)
    frame = _frame(0)
    registry.accept_frame(successor, frame)
    registry.accept_streaming_frame(successor, frame)
    registry.complete_route(
        successor,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=1,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
        ),
    )
    await registry.finish_streaming_recognition(successor)

    assert receipts == []
    assert successor.streaming_voice_commit_receipt is None
    with pytest.raises(
        MediaTransportViolation, match="authority is absent or stale"
    ):
        await registry.streaming_recognition_result(
            params={
                "session_id": "session-1",
                "subject_id": successor_activation["subject_id"],
                "correlation_id": "correlation-1",
                "interaction_id": "interaction-1",
                "capture_id": "capture-2",
                "capture_generation": 1,
                "track_id": "track-2",
            },
            routed_session_id="session-1",
            connection_id="connection-1",
            request_origin="https://voice.example.test",
        )
    await owner.close()


@pytest.mark.asyncio
async def test_fixed_media_socket_runs_streaming_stt_to_formal_receipt_without_batch_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _DelayedOpenProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    receipts: list[dict[str, object]] = []

    async def issue_receipt(**binding: object) -> str:
        receipts.append(dict(binding))
        return "streaming-voice-receipt-12345678901234567890"

    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(owner, receipt_issuer=issue_receipt)
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    assert provider.open_count == 0

    async def complete_after_frames(*_args: object, **kwargs: object) -> object:
        for seq in range(2):
            kwargs["on_audio_frame"](_frame(seq))  # type: ignore[operator]
        # Browser media attach and first frames do not wait for Provider open.
        # Releasing it now proves the bounded pre-open queue drains exactly.
        provider.open_release.set()
        retained_record = next(iter(registry._records.values()))
        for _ in range(200):
            if retained_record.streaming_recognition_handle is not None:
                break
            await asyncio.sleep(0.001)
        assert retained_record.streaming_recognition_handle is not None
        result = DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=2,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
        )
        kwargs["on_complete"](result)  # type: ignore[operator]
        return result

    monkeypatch.setattr(
        dedicated_media_registration,
        "run_dedicated_media_socket_leaf",
        complete_after_frames,
    )
    socket = _AuthenticatedMediaSocket(activation)

    assert await handle_registered_media_socket(registry, socket, MEDIA_ROUTE_PATH)
    result = await registry.streaming_recognition_result(
        params={
            "session_id": "session-1",
            "subject_id": activation["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "capture_id": "capture-1",
            "capture_generation": 0,
            "track_id": "track-1",
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )

    assert socket.recv_count == 1
    assert result["status"] == "completed"
    assert result["final_text"] == "hello"
    assert result["voice_commit_receipt"] == (
        "streaming-voice-receipt-12345678901234567890"
    )
    assert len(receipts) == 1
    assert receipts[0]["text"] == "hello"
    assert [frame.seq for frame in provider.frames] == [0, 1]
    record = next(iter(registry._records.values()))
    assert record.pcm == bytearray()


@pytest.mark.asyncio
async def test_cold_streaming_open_preserves_short_utterance_until_server_vad_eot() -> (
    None
):
    provider = _DelayedOpenProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    registry = DedicatedMediaProductRegistry(enabled=True, end_of_turn_enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(
        owner,
        receipt_issuer=lambda **_binding: asyncio.sleep(0, result="unused"),
    )
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params={
            **_activation_params(),
            "end_of_turn_capability": MEDIA_END_OF_TURN_CAPABILITY,
        },
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    record = registry.consume_ticket(
        str(activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert record is not None

    registry.start_streaming_recognition(record)
    await asyncio.wait_for(provider.open_started.wait(), timeout=1)
    end_of_turn_task = asyncio.create_task(registry.wait_streaming_end_of_turn(record))
    # 100 x 20 ms reproduces a cold open that exceeded the former 64-frame
    # queue before the user could finish even a short greeting.
    for seq in range(100):
        frame = _frame(seq)
        registry.accept_frame(record, frame)
        registry.accept_streaming_frame(record, frame)
    assert len(record.streaming_preopen_frames) == 100
    assert not end_of_turn_task.done()

    provider.open_release.set()
    for _ in range(200):
        if record.streaming_recognition_handle is not None:
            break
        await asyncio.sleep(0.001)
    handle = record.streaming_recognition_handle
    assert handle is not None
    for _ in range(200):
        if len(provider.frames) == 100:
            break
        await asyncio.sleep(0.001)
    assert [frame.seq for frame in provider.frames] == list(range(100))
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            0,
            RecognitionTurnBoundaryKind.SPEECH_STARTED,
            "provider-item-cold",
            provider_start_ms=100,
        )
    )
    await provider.events.put(
        RecognitionTurnBoundaryEvent(
            handle.ref,
            _PROVIDER_REF,
            1,
            RecognitionTurnBoundaryKind.SPEECH_STOPPED,
            "provider-item-cold",
            provider_end_ms=900,
        )
    )

    observed = await asyncio.wait_for(end_of_turn_task, timeout=1)
    assert (observed.provider_start_ms, observed.provider_end_ms) == (100, 900)
    assert provider.cancel_count == 0
    registry.abort_route(record)
    await registry.abort_streaming_recognition(record)
    await owner.close()


@pytest.mark.asyncio
async def test_barge_in_capture_opens_provider_with_wider_prefix_only() -> None:
    provider = _ServerVadProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    registry = DedicatedMediaProductRegistry(enabled=True, end_of_turn_enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(
        owner,
        receipt_issuer=lambda **_binding: asyncio.sleep(0, result="unused"),
    )
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params={
            **_activation_params(),
            "end_of_turn_capability": MEDIA_END_OF_TURN_CAPABILITY,
        },
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    record = registry.consume_ticket(
        str(activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert record is not None
    assert record.barge_in_capture is False
    record.barge_in_capture = True

    await registry.begin_streaming_recognition(record)
    assert provider.request.turn_detection.server_vad is not None
    assert provider.request.turn_detection.server_vad.prefix_padding_ms == 800
    assert (
        RecognitionTurnDetection.server_vad_default().server_vad.prefix_padding_ms
        == 300
    )

    registry.abort_route(record)
    await registry.abort_streaming_recognition(record)
    await owner.close()


@pytest.mark.asyncio
async def test_slow_streaming_open_never_delays_media_attach_or_omits_early_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _DelayedOpenProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    receipts: list[dict[str, object]] = []

    async def issue_receipt(**binding: object) -> str:
        receipts.append(dict(binding))
        return "forbidden-streaming-receipt-12345678901234567890"

    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(owner, receipt_issuer=issue_receipt)
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    leaf_entered = asyncio.Event()

    async def complete_without_waiting_for_provider(
        *_args: object, **kwargs: object
    ) -> object:
        leaf_entered.set()
        for seq in range(2):
            kwargs["on_audio_frame"](_frame(seq))  # type: ignore[operator]
        result = DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=2,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
        )
        kwargs["on_complete"](result)  # type: ignore[operator]
        return result

    monkeypatch.setattr(
        dedicated_media_registration,
        "run_dedicated_media_socket_leaf",
        complete_without_waiting_for_provider,
    )
    socket = _AuthenticatedMediaSocket(activation)

    started = asyncio.get_running_loop().time()
    assert await handle_registered_media_socket(registry, socket, MEDIA_ROUTE_PATH)
    elapsed = asyncio.get_running_loop().time() - started

    assert leaf_entered.is_set()
    assert elapsed < 0.5
    result = await registry.streaming_recognition_result(
        params={
            "session_id": "session-1",
            "subject_id": activation["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "capture_id": "capture-1",
            "capture_generation": 0,
            "track_id": "track-1",
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )
    assert result["status"] == "fallback"
    assert result["fallback_tier"] == "batch"
    assert result["reason_id"] == "STREAMING_SPEECH_PROVIDER_TIMEOUT"
    assert receipts == []
    assert provider.frames == []
    record = next(iter(registry._records.values()))
    assert record.recognition_content_sha256 is not None
    assert record.accepted_frames == 2


@pytest.mark.asyncio
async def test_registry_streaming_failure_exposes_one_safe_batch_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jiuwenswarm.gateway.live_voice import dedicated_media_registration

    safe_logs: list[str] = []
    monkeypatch.setattr(
        dedicated_media_registration._LOGGER,
        "warning",
        lambda message, *args: safe_logs.append(message % args),
    )
    provider = _Provider(block_send=True)
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    observations: list[LiveVoiceObservation] = []
    metrics: list[LiveVoiceMetric] = []
    collector = LiveVoiceObservabilityCollector(
        observation_sink=observations.append,
        metric_sink=metrics.append,
    )
    registry = DedicatedMediaProductRegistry(
        enabled=True, streaming_observability=collector
    )
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(
        owner,
        receipt_issuer=lambda **_binding: asyncio.sleep(0, result="unused"),
    )
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    record = registry.consume_ticket(
        str(activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert record is not None
    await registry.begin_streaming_recognition(record)
    overflow_frame_count = streaming_speech_route._MAX_PENDING_PROVIDER_FRAMES + 2
    for seq in range(overflow_frame_count):
        frame = _frame(seq)
        registry.accept_frame(record, frame)
        registry.accept_streaming_frame(record, frame)
    registry.complete_route(
        record,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=overflow_frame_count,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
        ),
    )
    await registry.finish_streaming_recognition(record)
    result_params = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "capture_id": "capture-1",
        "capture_generation": 0,
        "track_id": "track-1",
    }
    result = await registry.streaming_recognition_result(
        params=result_params,
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )

    # The exact response is consumed unchanged by the TypeScript client test.
    assert result == _STREAMING_FALLBACK_FIXTURE
    assert safe_logs == [
        "live_voice_streaming_recognition_degradation reason=STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED target=batch visible=true"
    ]
    await _wait_for_diagnostics(observations, metrics)
    assert [item.event_name for item in observations] == ["failure.observed"]
    assert [item.metric_name for item in metrics] == ["live_voice.failure_total"]
    assert observations[0].binding.interaction_id == "interaction-1"
    assert "hello" not in repr(observations + metrics)
    replay = await registry.streaming_recognition_result(
        params=result_params,
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )
    assert replay == result
    assert len(observations) == len(metrics) == 1
    registry.close_streaming_observability()


@pytest.mark.asyncio
async def test_blocked_observability_sink_never_blocks_streaming_fallback() -> None:
    sink_entered = threading.Event()
    sink_release = threading.Event()

    def blocking_sink(_observation: LiveVoiceObservation) -> None:
        sink_entered.set()
        sink_release.wait()

    collector = LiveVoiceObservabilityCollector(observation_sink=blocking_sink)
    registry = DedicatedMediaProductRegistry(
        enabled=True, streaming_observability=collector
    )
    registry.set_provider_available(True)
    params = _prepare_fallback_result_authority(registry, index=11)

    started = asyncio.get_running_loop().time()
    result = await registry.streaming_recognition_result(
        params=params,
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )
    elapsed = asyncio.get_running_loop().time() - started
    for _ in range(200):
        if sink_entered.is_set():
            break
        await asyncio.sleep(0.001)

    assert sink_entered.is_set()
    assert elapsed < 0.2
    assert result["status"] == "fallback"
    assert result["fallback_tier"] == "batch"
    assert result["x_obs_event"] == "failure.observed"
    sink_release.set()
    registry.close_streaming_observability()


@pytest.mark.asyncio
async def test_exceptional_observability_sinks_do_not_change_streaming_result() -> None:
    def failing_sink(_value: object) -> None:
        raise RuntimeError("PRIVATE_DIAGNOSTIC_SINK")

    collector = LiveVoiceObservabilityCollector(
        observation_sink=failing_sink,
        metric_sink=failing_sink,
    )
    registry = DedicatedMediaProductRegistry(
        enabled=True, streaming_observability=collector
    )
    registry.set_provider_available(True)
    params = _prepare_fallback_result_authority(registry, index=12)

    result = await registry.streaming_recognition_result(
        params=params,
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )
    for _ in range(200):
        if collector.stats().sink_failures == 2:
            break
        await asyncio.sleep(0.001)

    assert result["status"] == "fallback"
    assert result["fallback_tier"] == "batch"
    assert result["x_obs_event"] == "failure.observed"
    assert collector.stats().sink_failures == 2
    registry.close_streaming_observability()


@pytest.mark.asyncio
async def test_observability_queue_saturation_is_nullable_not_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_entered = threading.Event()
    sink_release = threading.Event()

    def blocking_sink(_observation: LiveVoiceObservation) -> None:
        sink_entered.set()
        sink_release.wait()

    monkeypatch.setattr(
        dedicated_media_registration,
        "_STREAMING_OBSERVABILITY_QUEUE_CAPACITY",
        1,
    )
    collector = LiveVoiceObservabilityCollector(observation_sink=blocking_sink)
    registry = DedicatedMediaProductRegistry(
        enabled=True, streaming_observability=collector
    )
    registry.set_provider_available(True)
    params = [
        _prepare_fallback_result_authority(registry, index=index)
        for index in (21, 22, 23)
    ]

    first = await registry.streaming_recognition_result(
        params=params[0],
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )
    for _ in range(200):
        if sink_entered.is_set():
            break
        await asyncio.sleep(0.001)
    assert sink_entered.is_set()
    second = await registry.streaming_recognition_result(
        params=params[1],
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )
    third = await registry.streaming_recognition_result(
        params=params[2],
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )

    assert [
        first["fallback_tier"],
        second["fallback_tier"],
        third["fallback_tier"],
    ] == [
        "batch",
        "batch",
        "batch",
    ]
    assert first["x_obs_event"] == second["x_obs_event"] == "failure.observed"
    assert third["x_obs_event"] is None
    assert third["x_obs_metric"] is None
    sink_release.set()
    registry.close_streaming_observability()


@pytest.mark.asyncio
async def test_result_timeout_aborts_stream_before_authorizing_batch_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jiuwenswarm.gateway.live_voice import dedicated_media_registration

    monkeypatch.setattr(
        dedicated_media_registration,
        "_STREAMING_RESULT_TIMEOUT_SECONDS",
        0.01,
    )
    provider = _Provider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(
        owner,
        receipt_issuer=lambda **_binding: asyncio.sleep(0, result="unused"),
    )
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    record = registry.consume_ticket(
        str(activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert record is not None
    await registry.begin_streaming_recognition(record)
    frame = _frame(0)
    registry.accept_frame(record, frame)
    registry.accept_streaming_frame(record, frame)
    registry.complete_route(
        record,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=1,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
        ),
    )

    result_params = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "capture_id": "capture-1",
        "capture_generation": 0,
        "track_id": "track-1",
    }
    result = await registry.streaming_recognition_result(
        params=result_params,
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )

    assert result["status"] == "fallback"
    assert result["fallback_tier"] == "batch"
    assert result["reason_id"] == "STREAMING_SPEECH_PROVIDER_TIMEOUT"
    assert provider.cancel_count == 1
    assert record.streaming_recognition_handle is None
    await asyncio.sleep(0.02)
    assert record.streaming_voice_commit_receipt is None


@pytest.mark.asyncio
async def test_registry_incomplete_route_never_authorizes_batch_replay() -> None:
    provider = _Provider(block_send=True)
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    observations: list[LiveVoiceObservation] = []
    metrics: list[LiveVoiceMetric] = []
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        streaming_observability=LiveVoiceObservabilityCollector(
            observation_sink=observations.append,
            metric_sink=metrics.append,
        ),
    )
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(
        owner,
        receipt_issuer=lambda **_binding: asyncio.sleep(0, result="unused"),
    )
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    record = registry.consume_ticket(
        str(activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert record is not None
    await registry.begin_streaming_recognition(record)
    registry.abort_route(record)
    await registry.abort_streaming_recognition(record)

    result = await registry.streaming_recognition_result(
        params={
            "session_id": "session-1",
            "subject_id": activation["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "capture_id": "capture-1",
            "capture_generation": 0,
            "track_id": "track-1",
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="https://voice.example.test",
    )

    assert result["status"] == "fallback"
    assert result["fallback_tier"] == "text"
    assert result["reason_id"] == "STREAMING_SPEECH_ROUTE_ABORTED"
    assert result["x_obs_event"] == "degradation.activated"
    assert result["x_obs_metric"] == "live_voice.degradation_total"
    await _wait_for_diagnostics(observations, metrics)
    assert observations[0].event_name == "degradation.activated"
    assert metrics[0].metric_name == "live_voice.degradation_total"
    assert record.recognition_content_sha256 is None
    registry.close_streaming_observability()


@pytest.mark.asyncio
async def test_registry_revoke_fences_streaming_and_cancels_exact_handle() -> None:
    provider = _Provider(block_send=True)
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    receipt_calls = 0

    async def issue_receipt(**_binding: object) -> str:
        nonlocal receipt_calls
        receipt_calls += 1
        return "unused"

    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    registry.configure_streaming_recognition(owner, receipt_issuer=issue_receipt)
    await registry.prepare_streaming_provider()
    _trust_activation(registry)
    activation = registry.activate(
        params=_activation_params(),
        request_origin="https://voice.example.test",
        connection_id="connection-1",
        user_id="user-1",
    )
    record = registry.consume_ticket(
        str(activation["media_ticket"]),
        request_origin="https://voice.example.test",
    )
    assert record is not None
    await registry.begin_streaming_recognition(record)
    registry.accept_frame(record, _frame(0))
    registry.accept_streaming_frame(record, _frame(0))

    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": activation["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
    )
    for _ in range(100):
        if provider.cancel_count == 1:
            break
        await asyncio.sleep(0.01)

    assert provider.cancel_count == 1
    assert receipt_calls == 0
    assert record.streaming_recognition_handle is None
    assert record.pcm == bytearray()
    with pytest.raises(MediaTransportViolation, match="authority is absent or stale"):
        await registry.streaming_recognition_result(
            params={
                "session_id": "session-1",
                "subject_id": activation["subject_id"],
                "correlation_id": "correlation-1",
                "interaction_id": "interaction-1",
                "capture_id": "capture-1",
                "capture_generation": 0,
                "track_id": "track-1",
            },
            routed_session_id="session-1",
            connection_id="connection-1",
            request_origin="https://voice.example.test",
        )


def test_streaming_outcome_repr_never_contains_transcript() -> None:
    from jiuwenswarm.gateway.live_voice.streaming_speech_route import (
        StreamingRecognitionOutcome,
    )

    outcome = StreamingRecognitionOutcome(
        completed=True,
        final_text="PRIVATE_TRANSCRIPT",
        provider=_PROVIDER_REF,
        fallback_tier=None,
        reason=None,
    )
    assert "PRIVATE_TRANSCRIPT" not in repr(outcome)
