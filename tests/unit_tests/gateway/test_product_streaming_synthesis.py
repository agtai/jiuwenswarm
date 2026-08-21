# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import io
import json
import struct
import threading
import time
import wave
from typing import Any

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance
from jiuwenswarm.gateway.live_voice import dedicated_media_registration
from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame,
    MediaDetachReason,
    MediaTransportViolation,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaDownlinkSourceFailure,
    DedicatedMediaSocketLeafResult,
)
from jiuwenswarm.gateway.live_voice.streaming_synthesis_route import (
    StreamingSynthesisRouteOwner,
)
from jiuwenswarm.server.live_voice.batch_speech import SpeechRpcContext
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechRouteTier,
    StreamingSpeechSelection,
)
from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceObservabilityCollector,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    SpeechMode,
    SynthesisEventKind,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    CapabilityProvenance,
    ProviderTransport,
    RecognitionProviderSupport,
    StreamingProviderCapability,
    StreamingSpeechConformance,
    StreamingSpeechViolation,
    StreamingSynthesisEvent,
    SynthesisProviderSupport,
    SynthesisStreamRef,
    SynthesisStreamRequest,
)


ORIGIN = "https://voice.example.test"
_PROVIDER_REF = ProviderRef("fake-product-streaming", "formal")
_CAPABILITY = StreamingProviderCapability(
    provider=_PROVIDER_REF,
    recognition=RecognitionProviderSupport(
        modes=frozenset(), transport=ProviderTransport.UNSUPPORTED
    ),
    synthesis=SynthesisProviderSupport(
        modes=frozenset({SpeechMode.STREAM}),
        transport=ProviderTransport.NATIVE_STREAM,
        ordered_events=CapabilityProvenance.ADAPTER_DERIVED,
        exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
        provider_cancel_ack=CapabilityProvenance.UNAVAILABLE,
        chunk_text_spans=CapabilityProvenance.UNAVAILABLE,
    ),
)


class _Provider:
    def __init__(self, *, fail_open: bool = False, fail_after_audio: bool = False):
        self._conformance = StreamingSpeechConformance(_CAPABILITY, enabled=True)
        self.fail_open = fail_open
        self.fail_after_audio = fail_after_audio
        self.cancelled: list[SynthesisStreamRef] = []
        self.requests: list[SynthesisStreamRequest] = []
        self.events: asyncio.Queue[StreamingSynthesisEvent | BaseException] = (
            asyncio.Queue()
        )

    @property
    def capability(self) -> StreamingProviderCapability:
        return _CAPABILITY

    @property
    def conformance(self) -> StreamingSpeechConformance:
        return self._conformance

    @property
    def synthesis_model(self) -> str:
        return "fake-streaming-tts"

    @property
    def synthesis_voice(self) -> str:
        return "alloy"

    async def open_synthesis(self, request: SynthesisStreamRequest) -> None:
        if self.fail_open:
            raise OSError("private provider open failure")
        self._conformance.start_synthesis(request)
        self.requests.append(request)
        self.events.put_nowait(_event(request, 0, 0, SynthesisEventKind.STARTED))
        self.events.put_nowait(
            _event(
                request,
                1,
                0,
                SynthesisEventKind.CHUNK,
                (8192,) * (request.sample_rate_hz // 50),
            )
        )
        if self.fail_after_audio:
            self.events.put_nowait(OSError("private late provider failure"))
        else:
            self.events.put_nowait(
                _event(
                    request,
                    2,
                    request.sample_rate_hz // 50,
                    SynthesisEventKind.COMPLETED,
                )
            )

    async def next_synthesis_event(
        self, ref: SynthesisStreamRef, *, timeout_seconds: float
    ) -> StreamingSynthesisEvent:
        del ref, timeout_seconds
        item = await self.events.get()
        if isinstance(item, BaseException):
            raise item
        accepted = self._conformance.accept_synthesis_event(item)
        if accepted.kind is SynthesisEventKind.COMPLETED:
            self._conformance.reap_terminal()
        return accepted

    async def cancel_synthesis(
        self, ref: SynthesisStreamRef, *, reason: str = "caller_cancel"
    ) -> None:
        del reason
        self.cancelled.append(ref)
        try:
            self._conformance.request_synthesis_cancel(ref, reason="test_cancel")
            self._conformance.provider_closed_synthesis(ref)
        except StreamingSpeechViolation:
            pass
        self._conformance.reap_terminal()

    async def close(self) -> None:
        self._conformance.close()

    async def open_recognition(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("recognition is outside this test")

    async def send_recognition_audio(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("recognition is outside this test")

    async def commit_recognition(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("recognition is outside this test")

    async def next_recognition_event(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("recognition is outside this test")

    async def cancel_recognition(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("recognition is outside this test")


class _DelayedFirstAudioProvider(_Provider):
    def __init__(self) -> None:
        super().__init__()
        self.opened = asyncio.Event()
        self._pending_request: SynthesisStreamRequest | None = None

    async def open_synthesis(self, request: SynthesisStreamRequest) -> None:
        self._conformance.start_synthesis(request)
        self.requests.append(request)
        self._pending_request = request
        self.events.put_nowait(_event(request, 0, 0, SynthesisEventKind.STARTED))
        self.opened.set()

    def release_first_audio(self) -> None:
        request = self._pending_request
        assert request is not None
        self.events.put_nowait(
            _event(
                request,
                1,
                0,
                SynthesisEventKind.CHUNK,
                (8192,) * (request.sample_rate_hz // 50),
            )
        )
        self.events.put_nowait(
            _event(
                request,
                2,
                request.sample_rate_hz // 50,
                SynthesisEventKind.COMPLETED,
            )
        )


class _Batch:
    def __init__(self) -> None:
        self.calls = 0
        self.params: list[object] = []

    async def synthesize(
        self, params: object, _context: SpeechRpcContext
    ) -> dict[str, object]:
        self.calls += 1
        self.params.append(params)
        return {
            "contract_version": "live-voice.contract.v2",
            "request_id": "request-1",
            "operation_id": "operation-1",
            "ok": False,
            "result": None,
            "error": {
                "code": "CAPABILITY_UNAVAILABLE",
                "reason": "BATCH_TEST_SENTINEL",
                "message": "batch unavailable",
                "retriable": False,
                "correlation_id": "correlation-1",
                "details": {},
            },
        }


class _SuccessfulBatch:
    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(
        self, _params: object, _context: SpeechRpcContext
    ) -> dict[str, object]:
        self.calls += 1
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16_000)
            audio.writeframes(struct.pack("<320h", *((1024,) * 320)))
        return {
            "contract_version": "live-voice.contract.v2",
            "request_id": "request-1",
            "operation_id": "operation-1",
            "ok": True,
            "result": {
                "operation": "speech.synthesize.batch",
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-1",
                    "response_generation": 0,
                },
                "unit_id": "unit-1",
                "audio": {
                    "format": "wav_pcm16_mono",
                    "sample_rate_hz": 16_000,
                    "channel_count": 1,
                    "data_base64": base64.b64encode(output.getvalue()).decode("ascii"),
                },
                "provider": {
                    "provider_id": "fake-batch",
                    "implementation_class": "formal",
                    "fallback_from": "fake-product-streaming",
                    "model": "fake-batch-tts",
                    "voice": "alloy",
                },
                "presented": False,
            },
            "error": None,
        }


def _event(
    request: SynthesisStreamRequest,
    seq: int,
    cursor: int,
    kind: SynthesisEventKind,
    samples: tuple[int, ...] = (),
) -> StreamingSynthesisEvent:
    return StreamingSynthesisEvent(
        ref=request.ref,
        provider=_PROVIDER_REF,
        seq=seq,
        sample_cursor=cursor,
        kind=kind,
        sample_rate_hz=request.sample_rate_hz,
        sample_count=len(samples),
        pcm_s16le=struct.pack(f"<{len(samples)}h", *samples) if samples else None,
    )


def _product_manifest() -> dict[str, object]:
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


def _authorized_registry(
    provider: _Provider,
    *,
    observability: LiveVoiceObservabilityCollector | None = None,
    notification_batch: bool = False,
):
    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    activation_params = {
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
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "active",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "interaction_id": "interaction-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
            },
            "product_composition": _product_manifest(),
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
        request_method="live_voice.composition.p2.activate",
    )
    activation = registry.activate(
        params=activation_params,
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    parent = registry.consume_ticket(
        str(activation["media_ticket"]), request_origin=ORIGIN
    )
    assert parent is not None
    parent.route_completed = True
    parent.accepted_frames = 1
    text = "authoritative agent text"
    final_notification: dict[str, object] = {
        "status": "notification",
        "kind": "agent.output",
        "request_id": "request-notification-1",
        "round_id": "round-1",
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-1",
            "response_generation": 0,
        },
        "agent_event": {"event_type": "chat.final", "text": text},
        "source_event": None,
        "progress_event": None,
        "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
        "error_reason": None,
        "publish_seq": 0,
    }
    result: dict[str, object]
    if notification_batch:
        result = {
            "status": "notification_batch",
            "notifications": [final_notification],
            "session_id": "session-1",
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        }
    else:
        result = final_notification
    registry.observe_agent_response(
        {"ok": True, "result": result},
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingSynthesisRouteOwner(selector)
    registry.configure_streaming_synthesis(owner, observability=observability)
    context = SpeechRpcContext(
        str(activation["subject_id"]), "session-1", Assurance.AUTHENTICATED
    )
    params = {
        "contract_version": "live-voice.contract.v2",
        "request_id": "request-1",
        "operation_id": "operation-1",
        "operation": "speech.synthesize.batch",
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
            "display_text": text,
            "spoken_text": text,
            "transforms": [],
        },
        "authoritative_agent_text": True,
        "locale": "zh-CN",
        "voice": None,
        "required_sample_rate_hz": 16_000,
    }
    return registry, owner, context, params


def _observe_conflicting_agent_text(
    registry: DedicatedMediaProductRegistry,
    *,
    text: str = "conflicting later agent text",
) -> None:
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
                "agent_event": {"event_type": "chat.final", "text": text},
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )


@pytest.fixture(autouse=True)
def _allowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS", "voice.example.test")


@pytest.mark.asyncio
async def test_exact_agent_final_opens_real_streaming_product_downlink() -> None:
    provider = _Provider()
    registry, owner, context, params = _authorized_registry(provider)
    batch = _Batch()
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )

    assert result is not None and result["ok"] is True
    payload = result["result"]
    assert isinstance(payload, dict)
    audio = payload["audio"]
    assert isinstance(audio, dict)
    assert audio["endpoint_path"] == "/ws/live-voice/media"
    assert audio["frame_count"] is None
    assert audio["streaming"] is True
    assert audio["degradation_reason"] is None
    assert "media_ticket" in audio and str(audio["media_ticket"]) not in str(
        audio["endpoint_path"]
    )
    assert batch.calls == 0
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.ref.response.response_id == "response-1"
    assert request.ref.unit_id == "unit-1"
    assert request.display_span.start == 0
    assert request.event_timeout_seconds == 2.0
    downlink = registry.consume_ticket(
        str(audio["media_ticket"]), request_origin=ORIGIN
    )
    assert downlink is not None and downlink.downlink_stream_source is not None
    source = downlink.downlink_stream_source
    assert source.handle.scope_identity == (
        "session-1",
        context.subject_id,
        "correlation-1",
    )
    assert (await source.__anext__()).seq == 0
    with pytest.raises(StopAsyncIteration):
        await source.__anext__()
    assert source.completed is True
    assert source.emitted_frames == 1
    await owner.close()


@pytest.mark.asyncio
async def test_batched_agent_final_opens_real_streaming_product_downlink() -> None:
    provider = _Provider()
    registry, owner, context, params = _authorized_registry(
        provider, notification_batch=True
    )
    batch = _Batch()

    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )

    assert result is not None and result["ok"] is True
    assert len(provider.requests) == 1
    assert provider.requests[0].ref.response.response_id == "response-1"
    assert provider.requests[0].ref.unit_id == "unit-1"
    assert batch.calls == 0
    await owner.close()


@pytest.mark.asyncio
async def test_delayed_first_audio_conflict_closes_source_without_ticket_or_batch() -> (
    None
):
    provider = _DelayedFirstAudioProvider()
    registry, owner, context, params = _authorized_registry(provider)
    batch = _Batch()
    before_record_ids = tuple(registry._records)

    pending = asyncio.create_task(
        registry.try_streaming_synthesis(
            "speech.synthesize.batch",
            params,
            context,
            "session-1",
            batch_service=batch,  # type: ignore[arg-type]
        )
    )
    await asyncio.wait_for(provider.opened.wait(), timeout=1)
    _observe_conflicting_agent_text(registry)
    provider.release_first_audio()
    result = await asyncio.wait_for(pending, timeout=1)

    assert result is not None and result["ok"] is False
    assert result["error"]["reason"] == "MEDIA_STREAMING_TTS_TEXT_OR_RETRY"  # type: ignore[index]
    assert batch.calls == 0
    assert len(provider.requests) == 1
    assert provider.cancelled == [provider.requests[0].ref]
    assert tuple(registry._records) == before_record_ids
    assert registry._pending_tickets == {}
    assert all(
        record.downlink_stream_source is None for record in registry._records.values()
    )
    await owner.close()


@pytest.mark.asyncio
async def test_streaming_downlink_accepts_only_exact_completed_browser_receipt() -> (
    None
):
    provider = _Provider()
    registry, owner, context, params = _authorized_registry(provider)
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=_Batch(),  # type: ignore[arg-type]
    )
    audio = result["result"]["audio"]  # type: ignore[index]
    downlink = registry.consume_ticket(
        str(audio["media_ticket"]),
        request_origin=ORIGIN,  # type: ignore[index]
    )
    assert downlink is not None and downlink.downlink_stream_source is not None

    successor = registry.activate(
        params={
            "session_id": "session-1",
            "interaction_id": "interaction-1",
            "correlation_id": "correlation-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
            "capture_id": "capture-2",
            "capture_generation": 1,
            "track_id": "track-2",
            "sample_rate_hz": 16_000,
            "locale": "zh-CN",
        },
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    successor_uplink = registry.consume_ticket(
        str(successor["media_ticket"]), request_origin=ORIGIN
    )
    assert successor_uplink is not None
    registry.mark_downlink_started(downlink)
    registry.accept_frame(
        successor_uplink,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )

    source = downlink.downlink_stream_source
    assert (await source.__anext__()).seq == 0
    with pytest.raises(StopAsyncIteration):
        await source.__anext__()
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
    receipt_params = {
        "session_id": "session-1",
        "subject_id": params["scope"]["subject_id"],  # type: ignore[index]
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "response_id": "response-1",
        "response_generation": 0,
        "unit_id": "unit-1",
        "capture_frames_acked": 1,
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
    assert receipt["duplex_media_observed"] is True
    assert (
        registry.acknowledge_playout(
            params=receipt_params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
        == receipt
    )
    with pytest.raises(MediaTransportViolation) as mismatch:
        registry.acknowledge_playout(
            params={
                **receipt_params,
                "rendered_chunks": 2,
                "rendered_through_seq": 1,
            },
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert mismatch.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED"
    with pytest.raises(MediaTransportViolation) as conflict:
        registry.acknowledge_playout(
            params={**receipt_params, "playout_peak_depth": 2},
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert conflict.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_CONFLICT"
    _observe_conflicting_agent_text(registry)
    with pytest.raises(MediaTransportViolation) as stale_content:
        registry.acknowledge_playout(
            params=receipt_params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert stale_content.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED"
    parent_record_id = registry._subjects[
        ("session-1", str(params["scope"]["subject_id"]))
    ]  # type: ignore[index]
    parent = registry._records[parent_record_id]
    current_content = parent.synthesis_content_sha256[
        (source.handle.ref.response, source.handle.ref.unit_id)
    ]
    parent.downlink_results[(source.handle.ref.response, source.handle.ref.unit_id)][
        "content_sha256"
    ] = current_content
    with pytest.raises(MediaTransportViolation) as rebound_old_receipt:
        registry.acknowledge_playout(
            params=receipt_params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert rebound_old_receipt.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_CONFLICT"
    await owner.close()


@pytest.mark.asyncio
async def test_pre_first_audio_failure_calls_batch_exactly_once() -> None:
    provider = _Provider(fail_open=True)
    registry, owner, context, params = _authorized_registry(provider)
    batch = _Batch()
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )
    assert result is not None and result["ok"] is False
    assert (
        result["_streaming_degradation_reason"]
        == "STREAMING_SPEECH_PROVIDER_UNAVAILABLE"
    )
    assert batch.calls == 1
    assert isinstance(batch.params[0], dict)
    assert batch.params[0]["timeout_ms"] == 2_000
    await owner.close()


@pytest.mark.asyncio
async def test_pre_first_failure_batch_result_exposes_visible_fixed_path_reason() -> (
    None
):
    provider = _Provider(fail_open=True)
    registry, owner, context, params = _authorized_registry(provider)
    batch = _SuccessfulBatch()
    fallback = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )

    assert fallback is not None and fallback["ok"] is True
    transformed = registry.prepare_synthesis_downlink(
        "speech.synthesize.batch", params, context, fallback, "session-1"
    )
    assert "_streaming_degradation_reason" not in transformed
    audio = transformed["result"]["audio"]  # type: ignore[index]
    assert audio["endpoint_path"] == "/ws/live-voice/media"  # type: ignore[index]
    assert audio["streaming"] is False  # type: ignore[index]
    assert (
        audio["degradation_reason"]  # type: ignore[index]
        == "STREAMING_SPEECH_PROVIDER_UNAVAILABLE"
    )
    assert audio["frame_count"] == 1  # type: ignore[index]
    assert str(audio["media_ticket"]) not in str(audio["endpoint_path"])  # type: ignore[index]
    assert batch.calls == 1
    await owner.close()


@pytest.mark.asyncio
async def test_batch_fallback_content_conflict_cannot_mint_downlink_ticket() -> None:
    provider = _Provider(fail_open=True)
    registry, owner, context, params = _authorized_registry(provider)
    batch = _SuccessfulBatch()
    fallback = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )
    assert fallback is not None and fallback["ok"] is True
    _observe_conflicting_agent_text(registry)

    transformed = registry.prepare_synthesis_downlink(
        "speech.synthesize.batch", params, context, fallback, "session-1"
    )

    assert transformed["ok"] is False
    assert transformed["error"]["reason"] == "MEDIA_STREAMING_TTS_TEXT_OR_RETRY"  # type: ignore[index]
    assert transformed["result"] is None
    assert registry._pending_tickets == {}
    assert len(registry._records) == 1
    assert batch.calls == 1
    await owner.close()


@pytest.mark.asyncio
async def test_post_first_audio_failure_is_typed_text_or_retry_without_batch() -> None:
    provider = _Provider(fail_after_audio=True)
    registry, owner, context, params = _authorized_registry(provider)
    batch = _Batch()
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )
    assert result is not None and result["ok"] is True
    audio = result["result"]["audio"]  # type: ignore[index]
    downlink = registry.consume_ticket(
        str(audio["media_ticket"]),
        request_origin=ORIGIN,  # type: ignore[index]
    )
    assert downlink is not None and downlink.downlink_stream_source is not None
    source = downlink.downlink_stream_source
    assert (await source.__anext__()).seq == 0
    with pytest.raises(DedicatedMediaDownlinkSourceFailure) as caught:
        await source.__anext__()
    assert caught.value.reason_id.value == "MEDIA_STREAMING_TTS_TEXT_OR_RETRY"
    assert batch.calls == 0
    await owner.close()


@pytest.mark.asyncio
async def test_flag_off_registry_has_zero_streaming_owner_or_provider_effect() -> None:
    provider = _Provider()
    registry = DedicatedMediaProductRegistry(enabled=False)
    batch = _Batch()
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        {},
        SpeechRpcContext(None, "session-1", Assurance.REQUEST_ASSERTED),
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )
    assert result is None
    assert provider.requests == []
    assert provider.cancelled == []
    assert batch.calls == 0
    assert registry._streaming_synthesis_owner is None
    assert registry._records == {}


@pytest.mark.asyncio
async def test_barge_or_transport_abort_cancels_exact_source_without_batch() -> None:
    provider = _Provider()
    registry, owner, context, params = _authorized_registry(provider)
    batch = _Batch()
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )
    audio = result["result"]["audio"]  # type: ignore[index]
    downlink = registry.consume_ticket(
        str(audio["media_ticket"]),
        request_origin=ORIGIN,  # type: ignore[index]
    )
    assert downlink is not None and downlink.downlink_stream_source is not None
    source = downlink.downlink_stream_source

    registry.abort_route(downlink)
    await asyncio.wait_for(source.handle.cleanup_done.wait(), timeout=1)

    assert provider.cancelled == [source.handle.ref]
    assert batch.calls == 0
    assert downlink.downlink_stream_source is None
    with pytest.raises(StopAsyncIteration):
        await source.__anext__()
    await owner.close()


@pytest.mark.asyncio
async def test_successor_fences_seeded_predecessor_before_late_audio() -> None:
    provider = _Provider()
    registry, owner, context, params = _authorized_registry(provider)
    batch = _Batch()
    predecessor = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )
    prior_audio = predecessor["result"]["audio"]  # type: ignore[index]
    prior_record = registry.consume_ticket(
        str(prior_audio["media_ticket"]),
        request_origin=ORIGIN,  # type: ignore[index]
    )
    assert prior_record is not None and prior_record.downlink_stream_source is not None
    prior_source = prior_record.downlink_stream_source

    successor_text = "authoritative successor text"
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
                    "response_id": "response-2",
                    "response_generation": 1,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": successor_text,
                },
                "presentation_unit": {
                    "surface": "text",
                    "unit_id": "unit-2",
                },
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    successor_params = json.loads(json.dumps(params))
    successor_params["request_id"] = "request-2"
    successor_params["operation_id"] = "operation-2"
    successor_params["response"] = {
        "interaction_id": "interaction-1",
        "response_id": "response-2",
        "response_generation": 1,
    }
    successor_params["unit_id"] = "unit-2"
    successor_params["render_plan"] = {
        "display_text": successor_text,
        "spoken_text": successor_text,
        "transforms": [],
    }
    successor = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        successor_params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )

    assert successor is not None and successor["ok"] is True
    with pytest.raises(DedicatedMediaDownlinkSourceFailure):
        await prior_source.__anext__()
    assert prior_source.emitted_frames == 0
    assert prior_source.first_chunk is None
    assert provider.cancelled == [prior_source.handle.ref]
    assert batch.calls == 0
    await owner.close()


@pytest.mark.asyncio
async def test_xobs_is_typed_content_free_and_slow_sink_cannot_block_route() -> None:
    delivered = []

    def slow_sink(observation) -> None:
        time.sleep(0.4)
        delivered.append(observation)

    collector = LiveVoiceObservabilityCollector(observation_sink=slow_sink)
    provider = _Provider(fail_open=True)
    registry, owner, context, params = _authorized_registry(
        provider, observability=collector
    )
    batch = _Batch()
    started = time.monotonic()
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=batch,  # type: ignore[arg-type]
    )
    elapsed = time.monotonic() - started

    assert result is not None
    assert elapsed < 0.3
    assert batch.calls == 1
    await asyncio.sleep(0.5)
    observations = collector.observations()
    metrics = collector.metrics()
    assert len(observations) == 1
    assert observations[0].event_name == "degradation.activated"
    assert observations[0].reason_code == "DEGRADED"
    assert len(metrics) == 1
    assert metrics[0].metric_name == "live_voice.degradation_total"
    private_text = str(params["render_plan"]["spoken_text"])  # type: ignore[index]
    assert private_text not in repr(observations)
    assert private_text not in repr(metrics)
    assert private_text not in repr(registry._records)
    assert registry.close_streaming_diagnostics() is True
    await owner.close()


@pytest.mark.asyncio
async def test_blocked_xobs_has_one_worker_and_bounded_truthful_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    logs: list[str] = []

    def capture_warning(message: str, *args: object) -> None:
        logs.append(message % args if args else message)

    monkeypatch.setattr(
        dedicated_media_registration._LOGGER, "warning", capture_warning
    )

    def blocked_sink(_observation) -> None:
        entered.set()
        release.wait(timeout=5)

    before_workers = tuple(
        thread
        for thread in threading.enumerate()
        if thread.name == "live-voice-streaming-tts-diagnostics"
    )
    registry, owner, context, params = _authorized_registry(
        _Provider(fail_open=True),
        observability=LiveVoiceObservabilityCollector(observation_sink=blocked_sink),
    )
    started = time.monotonic()
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=_Batch(),  # type: ignore[arg-type]
    )
    assert result is not None
    assert time.monotonic() - started < 0.3
    assert await asyncio.to_thread(entered.wait, 1)

    second_registry = None
    second_owner = None
    try:
        close_started = time.monotonic()
        assert registry.close_streaming_diagnostics() is False
        assert time.monotonic() - close_started < 0.2
        assert registry.streaming_diagnostics_cleanup_complete is False
        diagnostic_owner = registry._streaming_diagnostic_owner
        assert diagnostic_owner is not None
        assert diagnostic_owner.submit(None, None) is False  # type: ignore[arg-type]

        second_registry, second_owner, second_context, second_params = (
            _authorized_registry(
                _Provider(fail_open=True),
                observability=LiveVoiceObservabilityCollector(),
            )
        )
        second = await second_registry.try_streaming_synthesis(
            "speech.synthesize.batch",
            second_params,
            second_context,
            "session-1",
            batch_service=_Batch(),  # type: ignore[arg-type]
        )
        assert second is not None
        second_diagnostic_owner = second_registry._streaming_diagnostic_owner
        assert second_diagnostic_owner is not None
        saturation_results = [
            second_diagnostic_owner.submit(None, None)  # type: ignore[arg-type]
            for _ in range(20)
        ]
        assert saturation_results.count(True) == 15
        assert saturation_results.count(False) == 5
        assert second_registry.close_streaming_diagnostics() is False
        after_workers = tuple(
            thread
            for thread in threading.enumerate()
            if thread.name == "live-voice-streaming-tts-diagnostics"
        )
        assert len(after_workers) == 1
        assert len(after_workers) >= len(before_workers)
        assert any("cleanup_incomplete" in entry for entry in logs)
        assert any("reason=OWNER_CLOSED" in entry for entry in logs)
        assert any("reason=QUEUE_SATURATED" in entry for entry in logs)
    finally:
        release.set()
        for _ in range(100):
            first_complete = registry.close_streaming_diagnostics()
            second_complete = bool(
                second_registry is None or second_registry.close_streaming_diagnostics()
            )
            if first_complete and second_complete:
                break
            await asyncio.sleep(0.01)
        await owner.close()
        if second_owner is not None:
            await second_owner.close()
    assert registry.streaming_diagnostics_cleanup_complete is True
    assert second_registry is not None
    assert second_registry.streaming_diagnostics_cleanup_complete is True
    assert diagnostic_owner.accounting == (1, 1, 0, 0)
    assert second_diagnostic_owner.accounting == (21, 0, 21, 0)
    assert any("reason=OWNER_CLOSED_PENDING" in entry for entry in logs)


@pytest.mark.asyncio
async def test_throwing_xobs_sink_isolated_from_business_and_metric() -> None:
    def throwing_sink(_observation) -> None:
        raise RuntimeError("private diagnostic sink failure")

    collector = LiveVoiceObservabilityCollector(observation_sink=throwing_sink)
    registry, owner, context, params = _authorized_registry(
        _Provider(fail_open=True), observability=collector
    )
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=_Batch(),  # type: ignore[arg-type]
    )
    assert result is not None
    for _ in range(100):
        if collector.metrics():
            break
        await asyncio.sleep(0.01)
    assert len(collector.observations()) == 1
    assert len(collector.metrics()) == 1
    assert collector.stats().sink_failures == 1
    assert registry.close_streaming_diagnostics() is True
    await owner.close()


@pytest.mark.asyncio
async def test_success_emits_completion_xobs_but_cancel_is_not_degradation() -> None:
    success_collector = LiveVoiceObservabilityCollector()
    provider = _Provider()
    registry, owner, context, params = _authorized_registry(
        provider, observability=success_collector
    )
    result = await registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        params,
        context,
        "session-1",
        batch_service=_Batch(),  # type: ignore[arg-type]
    )
    audio = result["result"]["audio"]  # type: ignore[index]
    record = registry.consume_ticket(
        str(audio["media_ticket"]),
        request_origin=ORIGIN,  # type: ignore[index]
    )
    assert record is not None and record.downlink_stream_source is not None
    source = record.downlink_stream_source
    assert (await source.__anext__()).seq == 0
    with pytest.raises(StopAsyncIteration):
        await source.__anext__()
    for _ in range(20):
        if success_collector.observations():
            break
        await asyncio.sleep(0.01)

    observations = success_collector.observations()
    assert len(observations) == 1
    assert observations[0].event_name == "segment.completed"
    assert observations[0].segment_name == "speech.synthesis"
    assert success_collector.metrics() == ()
    assert registry.close_streaming_diagnostics() is True
    await owner.close()

    cancel_collector = LiveVoiceObservabilityCollector()
    cancel_provider = _Provider()
    cancel_registry, cancel_owner, cancel_context, cancel_params = _authorized_registry(
        cancel_provider, observability=cancel_collector
    )
    cancel_result = await cancel_registry.try_streaming_synthesis(
        "speech.synthesize.batch",
        cancel_params,
        cancel_context,
        "session-1",
        batch_service=_Batch(),  # type: ignore[arg-type]
    )
    cancel_audio = cancel_result["result"]["audio"]  # type: ignore[index]
    cancel_record = cancel_registry.consume_ticket(
        str(cancel_audio["media_ticket"]),
        request_origin=ORIGIN,  # type: ignore[index]
    )
    assert (
        cancel_record is not None and cancel_record.downlink_stream_source is not None
    )
    await cancel_record.downlink_stream_source.aclose()
    await asyncio.sleep(0.05)

    assert cancel_collector.observations() == ()
    assert cancel_collector.metrics() == ()
    assert cancel_registry.close_streaming_diagnostics() is True
    await cancel_owner.close()
