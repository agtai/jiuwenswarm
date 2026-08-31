# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from dataclasses import replace
import base64
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
    canonical_json_bytes,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAck,
    MediaAttach,
    MediaAudioFrame,
    MediaDetach,
    MediaDetachReason,
    MediaTransportViolation,
    StrictMediaReceiver,
    deserialize_media_control,
    encode_audio_frame,
    serialize_media_control,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry,
    MEDIA_AUTH_CONTRACT_VERSION,
    MEDIA_ACTIVATE_METHOD,
    MEDIA_CLOSE_METHOD,
    STREAMING_RECOGNITION_RESULT_METHOD,
    register_dedicated_media_rpc_handlers,
    handle_registered_media_socket,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaSocketLeafResult,
)
from jiuwenswarm.gateway.live_voice.streaming_speech_route import (
    StreamingRecognitionFallbackReason,
    StreamingRecognitionOutcome,
    StreamingRecognitionRouteOwner,
)
from jiuwenswarm.gateway.live_voice import dedicated_media_registration
from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web.web_connect import (
    WebChannel,
    WebChannelConfig,
)
from jiuwenswarm.gateway.channel_manager.web import web_connect
from jiuwenswarm.gateway.live_voice.streaming_synthesis_route import (
    _MAX_ROUTE_IDENTITIES,
)
from jiuwenswarm.server.live_voice.batch_speech import (
    BatchSpeechProvider,
    FormalBatchSpeechService,
    ProviderCapability,
    ProviderRecognitionRequest,
    ProviderRecognitionResult,
    ProviderSynthesisRequest,
    ProviderSynthesisResult,
    RECOGNIZE_OPERATION,
    SYNTHESIZE_OPERATION,
    SpeechAuthorizationBinding,
    SpeechRecognitionSegmentBinding,
    SpeechRpcContext,
)
from jiuwenswarm.server.live_voice.latency_measurement import L0Milestone
from jiuwenswarm.server.live_voice.observability import LiveVoiceObservabilityCollector
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechRouteTier,
    StreamingSpeechSelection,
)
from jiuwenswarm.server.live_voice.speech_ports import ProviderRef, SpeechMode
from jiuwenswarm.server.live_voice.streaming_speech import (
    CapabilityProvenance,
    MAX_STREAMING_IDENTITY_LEDGER,
    ProviderTransport,
    RecognitionProviderSupport,
    StreamingProviderCapability,
    SynthesisProviderSupport,
)


ORIGIN = "https://voice.example.test"


class _DelayedPreopenStreamingProvider:
    capability = StreamingProviderCapability(
        provider=ProviderRef("preopen-delayed", "formal"),
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
    fallback_tier = SpeechRouteTier.BATCH

    def __init__(self) -> None:
        self.open_started = asyncio.Event()
        self.open_release = asyncio.Event()
        self.never_event = asyncio.Event()
        self.frames: list[object] = []
        self.cancel_count = 0

    async def open_recognition(self, request, *, timeout_seconds: float) -> None:
        del timeout_seconds
        self.ref = request.ref
        self.open_started.set()
        await self.open_release.wait()

    async def send_recognition_audio(self, frame) -> None:
        self.frames.append(frame)

    async def commit_recognition(self, ref):
        del ref
        raise AssertionError("pre-open byte-budget test must not commit")

    async def next_recognition_event(self, ref, *, timeout_seconds: float):
        del ref, timeout_seconds
        await self.never_event.wait()
        raise AssertionError("unreachable")

    async def cancel_recognition(self, ref, *, reason: str = "caller_cancel") -> None:
        del ref, reason
        self.cancel_count += 1

    async def close(self) -> None:
        self.open_release.set()
        self.never_event.set()


class _ResultRpcChannel:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.methods: dict[str, object] = {}
        self.responses: list[dict[str, object]] = []
        self.fail_send = fail_send
        self.send_calls = 0

    def register_method(self, name: str, handler: object) -> None:
        self.methods[name] = handler

    async def send_response(
        self,
        _ws: object,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> None:
        self.send_calls += 1
        if self.fail_send:
            raise RuntimeError("simulated disconnected response transport")
        self.responses.append(
            {
                "req_id": req_id,
                "ok": ok,
                "payload": payload,
                "error": error,
                "code": code,
            }
        )


def _wav(sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * 320)
    return output.getvalue()


class _CountingBatchSpeechProvider(BatchSpeechProvider):
    def __init__(self) -> None:
        self.synthesize_calls = 0

    def capability(self) -> ProviderCapability:
        return ProviderCapability("counting", True, True, True)

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        del request
        raise AssertionError("recognition is outside this speech-authority test")

    async def synthesize(
        self, request: ProviderSynthesisRequest
    ) -> ProviderSynthesisResult:
        self.synthesize_calls += 1
        return ProviderSynthesisResult(
            _wav(request.required_sample_rate_hz), "counting-tts", "counting-voice"
        )


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


def _streaming_result_params(
    activation: dict[str, object], params: dict[str, object]
) -> dict[str, object]:
    return {
        "session_id": params["session_id"],
        "subject_id": activation["subject_id"],
        "correlation_id": params["correlation_id"],
        "interaction_id": params["interaction_id"],
        "capture_id": params["capture_id"],
        "capture_generation": params["capture_generation"],
        "track_id": params["track_id"],
    }


def _media_close_params(
    activation: dict[str, object], params: dict[str, object]
) -> dict[str, object]:
    return {
        "session_id": params["session_id"],
        "subject_id": activation["subject_id"],
        "correlation_id": params["correlation_id"],
        "interaction_id": params["interaction_id"],
        "activation_id": params["activation_id"],
        "activation_generation": params["activation_generation"],
    }


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


@pytest.mark.asyncio
async def test_streaming_preopen_retention_obeys_capture_resident_byte_budget(
    tmp_path: Path,
) -> None:
    """B22: legal 96 kHz frames remain bounded by the existing capture owner."""

    provider = _DelayedPreopenStreamingProvider()
    owner = StreamingRecognitionRouteOwner(
        lambda: asyncio.sleep(
            0,
            result=StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None),
        )
    )
    registry = _active_registry()
    registry.configure_streaming_recognition(
        owner,
        receipt_issuer=lambda **_binding: asyncio.sleep(0, result="unused"),
    )
    await registry.prepare_streaming_provider()
    activation = _activate(
        registry,
        params=_params(sample_rate_hz=96_000),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    foreign_activation = _activate(
        registry,
        params=_params(
            session_id="session-foreign",
            interaction_id="interaction-foreign",
            correlation_id="correlation-foreign",
            activation_id="activation-foreign",
            capture_id="capture-foreign",
            track_id="track-foreign",
        ),
        request_origin=ORIGIN,
        connection_id="connection-foreign",
        user_id="user-foreign",
    )
    foreign_record = _pending_record(registry, _media_ticket(foreign_activation))
    foreign_before = (
        foreign_record.ticket_consumed,
        foreign_record.accepted_frames,
        bytes(foreign_record.pcm),
        tuple(foreign_record.streaming_preopen_frames),
        foreign_record.route_completed,
    )
    files_before = tuple(tmp_path.rglob("*"))

    try:
        registry.start_streaming_recognition(record)
        await asyncio.wait_for(provider.open_started.wait(), timeout=1)
        begin_task = record.streaming_recognition_begin_task
        assert begin_task is not None and not begin_task.done()

        receiver = StrictMediaReceiver(
            record.binding,
            on_audio_frame=lambda frame: (
                registry.accept_frame(record, frame),
                registry.accept_streaming_frame(record, frame),
            ),
        )
        assert receiver.attach(MediaAttach(binding=record.binding)) is None
        source_samples = (0.25,) * 1_920
        acknowledgements: list[MediaAck] = []
        for seq in range(547):
            accepted = receiver.accept_binary(
                encode_audio_frame(
                    record.binding,
                    MediaAudioFrame(
                        seq=seq,
                        sample_cursor=seq * len(source_samples),
                        samples=source_samples,
                    ),
                )
            )
            assert isinstance(accepted, MediaAck)
            acknowledgements.append(accepted)

        retained_f32_bytes = sum(
            len(frame.samples) * 4 for frame in record.streaming_preopen_frames
        )
        outcome = record.streaming_recognition_outcome
        assert len(acknowledgements) == 547
        assert retained_f32_bytes <= dedicated_media_registration._MAX_CAPTURE_WAV_BYTES
        assert record.streaming_preopen_frames == []
        assert outcome is not None
        assert outcome.reason is StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED

        # Once the exact stream fell back, later legal frames cannot recreate
        # retained pre-open state or replace the settled outcome.
        next_frame = MediaAudioFrame(
            seq=547,
            sample_cursor=547 * len(source_samples),
            samples=source_samples,
        )
        registry.accept_streaming_frame(record, next_frame)
        assert record.streaming_preopen_frames == []
        assert record.streaming_recognition_outcome is outcome
        assert (
            foreign_record.ticket_consumed,
            foreign_record.accepted_frames,
            bytes(foreign_record.pcm),
            tuple(foreign_record.streaming_preopen_frames),
            foreign_record.route_completed,
        ) == foreign_before
        assert tuple(tmp_path.rglob("*")) == files_before == ()
        assert not any(
            callable(getattr(registry, name, None))
            for name in (
                "dispatch_agent",
                "dispatch_tool",
                "mutate_task",
                "write_chat",
                "write_history",
            )
        )
    finally:
        provider.open_release.set()
        begin_task = record.streaming_recognition_begin_task
        if begin_task is not None:
            with suppress(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(begin_task), timeout=3)
        await asyncio.wait_for(owner.close(), timeout=3)


@pytest.mark.asyncio
async def test_early_streaming_degradation_does_not_suppress_later_success_latency() -> (
    None
):
    """L12: degradation and terminal recognition own independent X-OBS slots."""

    now = [0.0]
    collector = LiveVoiceObservabilityCollector()
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now[0],
        streaming_observability=collector,
    )
    registry.set_provider_available(True)
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.streaming_started_at = 0.0

    now[0] = 0.1
    registry._emit_streaming_observability(
        record,
        outcome=registry._streaming_fallback(
            StreamingRecognitionFallbackReason.ROUTE_ABORTED
        ),
    )
    now[0] = 0.4
    record.route_completed = True
    record.streaming_recognition_outcome = StreamingRecognitionOutcome(
        completed=True,
        final_text="private transcript is not observed",
        provider=ProviderRef("formal-stream", "formal"),
        fallback_tier=None,
        reason=None,
    )
    record.streaming_voice_commit_receipt = "receipt-12345678901234567890"
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
        request_origin=ORIGIN,
    )
    for _ in range(100):
        if len(collector.observations()) >= 2 and len(collector.metrics()) >= 2:
            break
        import time

        time.sleep(0.001)
    observations = collector.observations()
    metrics = collector.metrics()
    registry.close_streaming_observability()

    assert result["status"] == "completed"
    assert [item.event_name for item in observations] == [
        "degradation.activated",
        "segment.completed",
    ]
    assert [item.metric_name for item in metrics] == [
        "live_voice.degradation_total",
        "live_voice.segment_latency_ms",
    ]
    assert metrics[-1].value == 400.0
    assert "private transcript" not in repr(observations + metrics)
    assert not hasattr(registry, "dispatch_agent")
    assert not hasattr(registry, "mutate_task")


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
async def test_blocked_streaming_result_does_not_own_same_connection_close() -> None:
    """B21: close dispatches while a prior exact result request is unresolved."""

    registry = _active_registry()

    class SameConnectionSocket:
        closed = False
        remote_address = ("127.0.0.1", 32100)
        request_headers = {"Origin": ORIGIN}

        def __init__(self) -> None:
            self.read_requested = asyncio.Event()
            self.frames_ready = asyncio.Event()
            self._frames = iter(())

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.read_requested.set()
            await self.frames_ready.wait()
            try:
                return next(self._frames)
            except StopIteration as error:
                raise StopAsyncIteration from error

        def publish(self, frames: list[str]) -> None:
            self._frames = iter(frames)
            self.frames_ready.set()

    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    register_dedicated_media_rpc_handlers(channel, registry=registry)
    callbacks: list[object] = []
    responses: list[dict[str, object]] = []
    channel.on_message(callbacks.append)

    async def capture_response(
        _ws: object,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> None:
        responses.append(
            {
                "req_id": req_id,
                "ok": ok,
                "payload": payload,
                "error": error,
                "code": code,
            }
        )

    channel.send_response = capture_response  # type: ignore[method-assign]
    socket = SameConnectionSocket()
    connection = asyncio.create_task(
        channel._connection_handler(
            socket,
            "/ws?user_id=user-1&session_id=session-1",
        )
    )
    await socket.read_requested.wait()

    activation_params = _params()
    activation = _activate(
        registry,
        params=activation_params,
        request_origin=ORIGIN,
        connection_id=socket._jiuwen_ws_id,
    )
    record = registry.consume_ticket(
        str(activation["media_ticket"]), request_origin=ORIGIN
    )
    assert record is not None
    record.route_completed = True
    ready = asyncio.get_running_loop().create_future()
    record.streaming_recognition_ready = ready
    result_params = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": activation_params["correlation_id"],
        "interaction_id": activation_params["interaction_id"],
        "capture_id": activation_params["capture_id"],
        "capture_generation": activation_params["capture_generation"],
        "track_id": activation_params["track_id"],
    }
    close_params = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": activation_params["correlation_id"],
        "interaction_id": activation_params["interaction_id"],
        "activation_id": activation_params["activation_id"],
        "activation_generation": activation_params["activation_generation"],
    }
    result_entered = asyncio.Event()
    close_dispatched = asyncio.Event()
    original_result = registry._settle_streaming_recognition_result
    original_revoke = registry.revoke

    async def observed_result(
        claimed_record: object, **kwargs: object
    ) -> dict[str, object]:
        result_entered.set()
        return await original_result(claimed_record, **kwargs)  # type: ignore[arg-type]

    def observed_revoke(**kwargs: object) -> dict[str, object]:
        close_dispatched.set()
        return original_revoke(**kwargs)

    registry._settle_streaming_recognition_result = observed_result  # type: ignore[method-assign]
    registry.revoke = observed_revoke  # type: ignore[method-assign]
    socket.publish(
        [
            json.dumps(
                {
                    "type": "req",
                    "id": "streaming-result-blocked",
                    "method": STREAMING_RECOGNITION_RESULT_METHOD,
                    "params": result_params,
                }
            ),
            json.dumps(
                {
                    "type": "req",
                    "id": "streaming-result-duplicate",
                    "method": STREAMING_RECOGNITION_RESULT_METHOD,
                    "params": result_params,
                }
            ),
            json.dumps(
                {
                    "type": "req",
                    "id": "media-close-same-connection",
                    "method": MEDIA_CLOSE_METHOD,
                    "params": close_params,
                }
            ),
            json.dumps(
                {
                    "type": "req",
                    "id": "streaming-result-late",
                    "method": STREAMING_RECOGNITION_RESULT_METHOD,
                    "params": result_params,
                }
            ),
        ]
    )
    await asyncio.wait_for(result_entered.wait(), timeout=1)
    for _ in range(100):
        if close_dispatched.is_set():
            break
        await asyncio.sleep(0.001)
    close_was_dispatched_while_result_blocked = close_dispatched.is_set()
    assert len(registry._streaming_cleanup_tasks) == 1

    ready.set_result(
        StreamingRecognitionOutcome(
            completed=False,
            final_text=None,
            provider=None,
            fallback_tier=SpeechRouteTier.BATCH,
            reason=StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED,
        )
    )
    await asyncio.wait_for(connection, timeout=5)
    for _ in range(100):
        if len(responses) == 4 and not registry._streaming_result_dispatch_tasks:
            break
        await asyncio.sleep(0.001)

    assert callbacks == []
    blocked = next(
        item for item in responses if item["req_id"] == "streaming-result-blocked"
    )
    assert blocked["ok"] is True
    assert blocked["payload"]["status"] == "fallback"  # type: ignore[index]
    duplicate = next(
        item for item in responses if item["req_id"] == "streaming-result-duplicate"
    )
    assert duplicate["ok"] is False
    assert duplicate["code"] == "MEDIA_INVALID_STREAMING_RESULT"
    assert [item["req_id"] for item in responses].count(
        "media-close-same-connection"
    ) == 1
    late = next(item for item in responses if item["req_id"] == "streaming-result-late")
    assert late["ok"] is False
    assert late["code"] == "MEDIA_STREAMING_RESULT_UNAUTHORIZED"
    assert close_was_dispatched_while_result_blocked is True
    assert record.streaming_result_dispatch_pending is False
    assert registry._streaming_result_dispatch_tasks == {}
    assert registry._streaming_cleanup_tasks == set()


@pytest.mark.asyncio
async def test_streaming_result_dispatch_capacity_survives_close_and_recovers() -> None:
    """B21: closed records still consume the existing dispatch cap until settled."""

    registry = DedicatedMediaProductRegistry(enabled=True, capacity=1)
    registry.set_provider_available(True)
    channel = _ResultRpcChannel()
    register_dedicated_media_rpc_handlers(channel, registry=registry)
    handler = channel.methods[STREAMING_RECOGNITION_RESULT_METHOD]
    socket = SimpleNamespace(_jiuwen_ws_id="connection-1", request_headers={"Origin": ORIGIN})

    first_params = _params()
    first_activation = _activate(
        registry,
        params=first_params,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    first_record = registry.consume_ticket(
        _media_ticket(first_activation), request_origin=ORIGIN
    )
    assert first_record is not None
    first_record.route_completed = True
    first_ready = asyncio.get_running_loop().create_future()
    first_record.streaming_recognition_ready = first_ready
    await handler(  # type: ignore[operator]
        socket,
        "result-first",
        _streaming_result_params(first_activation, first_params),
        "session-1",
        None,
    )
    assert len(registry._streaming_result_dispatch_tasks) == 1

    registry.revoke(
        params=_media_close_params(first_activation, first_params),
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    second_params = _params(
        correlation_id="correlation-2",
        interaction_id="interaction-2",
        activation_id="activation-2",
        capture_id="capture-2",
        track_id="track-2",
    )
    second_activation = _activate(
        registry,
        params=second_params,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    second_record = registry.consume_ticket(
        _media_ticket(second_activation), request_origin=ORIGIN
    )
    assert second_record is not None
    second_record.route_completed = True
    second_ready = asyncio.get_running_loop().create_future()
    second_record.streaming_recognition_ready = second_ready

    await handler(  # type: ignore[operator]
        socket,
        "result-capacity-rejected",
        _streaming_result_params(second_activation, second_params),
        "session-1",
        None,
    )

    rejected = next(
        item
        for item in channel.responses
        if item["req_id"] == "result-capacity-rejected"
    )
    assert rejected["ok"] is False
    assert rejected["code"] == "MEDIA_INVALID_STREAMING_RESULT"
    assert len(registry._streaming_result_dispatch_tasks) == 1
    assert len(registry._streaming_cleanup_tasks) == 1
    assert second_record.streaming_result_dispatch_pending is False
    assert second_ready.done() is False

    first_ready.set_result(
        StreamingRecognitionOutcome(
            completed=False,
            final_text=None,
            provider=None,
            fallback_tier=SpeechRouteTier.TEXT,
            reason=StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED,
        )
    )
    for _ in range(100):
        if not registry._streaming_result_dispatch_tasks:
            break
        await asyncio.sleep(0.001)
    assert first_record.streaming_result_dispatch_pending is False
    assert registry._streaming_result_dispatch_tasks == {}

    await handler(  # type: ignore[operator]
        socket,
        "result-capacity-recovered",
        _streaming_result_params(second_activation, second_params),
        "session-1",
        None,
    )
    assert len(registry._streaming_result_dispatch_tasks) == 1
    second_ready.set_result(
        StreamingRecognitionOutcome(
            completed=False,
            final_text=None,
            provider=None,
            fallback_tier=SpeechRouteTier.TEXT,
            reason=StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED,
        )
    )
    for _ in range(100):
        if not registry._streaming_result_dispatch_tasks:
            break
        await asyncio.sleep(0.001)

    recovered = next(
        item
        for item in channel.responses
        if item["req_id"] == "result-capacity-recovered"
    )
    assert recovered["ok"] is True
    assert recovered["payload"]["status"] == "fallback"  # type: ignore[index]
    assert second_record.streaming_result_dispatch_pending is False
    assert registry._streaming_result_dispatch_tasks == {}
    assert registry._streaming_cleanup_tasks == set()
    assert not any(
        callable(getattr(registry, name, None))
        for name in (
            "dispatch_agent",
            "dispatch_tool",
            "mutate_task",
            "write_chat",
            "write_history",
        )
    )


@pytest.mark.asyncio
async def test_streaming_result_send_failure_releases_dispatch_without_retry() -> None:
    """B21: disconnected response transport cannot leak or retry the owner task."""

    registry = DedicatedMediaProductRegistry(enabled=True, capacity=1)
    registry.set_provider_available(True)
    channel = _ResultRpcChannel(fail_send=True)
    register_dedicated_media_rpc_handlers(channel, registry=registry)
    handler = channel.methods[STREAMING_RECOGNITION_RESULT_METHOD]
    socket = SimpleNamespace(_jiuwen_ws_id="connection-1", request_headers={"Origin": ORIGIN})
    params = _params()
    activation = _activate(
        registry,
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    record.streaming_recognition_outcome = StreamingRecognitionOutcome(
        completed=False,
        final_text=None,
        provider=None,
        fallback_tier=SpeechRouteTier.TEXT,
        reason=StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED,
    )
    loop = asyncio.get_running_loop()
    previous_exception_handler = loop.get_exception_handler()
    unobserved: list[dict[str, object]] = []
    loop.set_exception_handler(lambda _loop, context: unobserved.append(context))
    try:
        await handler(  # type: ignore[operator]
            socket,
            "result-disconnected",
            _streaming_result_params(activation, params),
            "session-1",
            None,
        )
        for _ in range(100):
            if (
                not registry._streaming_result_dispatch_tasks
                and not registry._streaming_cleanup_tasks
            ):
                break
            await asyncio.sleep(0.001)
        await asyncio.sleep(0)
    finally:
        loop.set_exception_handler(previous_exception_handler)

    assert channel.send_calls == 1
    assert channel.responses == []
    assert unobserved == []
    assert record.streaming_result_dispatch_pending is False
    assert registry._streaming_result_dispatch_tasks == {}
    assert registry._streaming_cleanup_tasks == set()
    assert not hasattr(registry, "dispatch_agent")
    assert not hasattr(registry, "dispatch_tool")
    assert not hasattr(registry, "mutate_task")


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


def _continued_recognition_authority() -> tuple[
    DedicatedMediaProductRegistry,
    SpeechAuthorizationBinding,
    object,
    object,
]:
    now = 1.0
    registry = DedicatedMediaProductRegistry(enabled=True, monotonic=lambda: now)
    registry.set_provider_available(True)
    predecessor_activation = _activate(
        registry,
        params=_params(
            capture_id="capture-predecessor",
            capture_generation=1,
            track_id="track-predecessor",
        ),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    predecessor = registry.consume_ticket(
        _media_ticket(predecessor_activation), request_origin=ORIGIN
    )
    assert predecessor is not None
    registry.accept_frame(
        predecessor,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(-0.25,) * 320),
    )
    registry.complete_route(
        predecessor,
        SimpleNamespace(
            activated=True,
            accepted_frames=1,
            reason_id=MediaDetachReason.RECOGNITION_CONTINUATION,
        ),  # type: ignore[arg-type]
    )
    now = 2.0
    current_activation = _activate(
        registry,
        params=_params(
            capture_id="capture-current",
            capture_generation=2,
            track_id="track-current",
            recognition_predecessor_subject_id=str(
                predecessor_activation["subject_id"]
            ),
        ),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    current = registry.consume_ticket(
        _media_ticket(current_activation), request_origin=ORIGIN
    )
    assert current is not None
    registry.accept_frame(
        current,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )
    registry.complete_route(
        current,
        SimpleNamespace(activated=True, accepted_frames=1),  # type: ignore[arg-type]
    )
    segments = (
        SpeechRecognitionSegmentBinding(
            subject_id=str(predecessor_activation["subject_id"]),
            capture_id="capture-predecessor",
            capture_generation=1,
            track_id="track-predecessor",
            content_sha256=str(predecessor.recognition_content_sha256),
        ),
        SpeechRecognitionSegmentBinding(
            subject_id=str(current_activation["subject_id"]),
            capture_id="capture-current",
            capture_generation=2,
            track_id="track-current",
            content_sha256=str(current.recognition_content_sha256),
        ),
    )

    def combined_digest(
        candidates: tuple[SpeechRecognitionSegmentBinding, ...],
    ) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "segments": [
                        {
                            "subject_id": segment.subject_id,
                            "capture_id": segment.capture_id,
                            "capture_generation": segment.capture_generation,
                            "track_id": segment.track_id,
                            "content_sha256": segment.content_sha256,
                        }
                        for segment in candidates
                    ]
                }
            )
        ).hexdigest()

    scope = ScopeRef(
        segments[-1].subject_id, None, "session-1", Assurance.AUTHENTICATED
    )
    binding = SpeechAuthorizationBinding(
        subject_id=segments[-1].subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="recognize-continuation",
        correlation_id="correlation-1",
        capture_id=segments[-1].capture_id,
        capture_generation=segments[-1].capture_generation,
        track_id=segments[-1].track_id,
        response=None,
        unit_id=None,
        content_sha256=combined_digest(segments),
        recognition_segments=segments,
    )
    return registry, binding, predecessor, current


def _continued_binding_with_segments(
    binding: SpeechAuthorizationBinding,
    segments: tuple[SpeechRecognitionSegmentBinding, ...],
) -> SpeechAuthorizationBinding:
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "segments": [
                    {
                        "subject_id": segment.subject_id,
                        "capture_id": segment.capture_id,
                        "capture_generation": segment.capture_generation,
                        "track_id": segment.track_id,
                        "content_sha256": segment.content_sha256,
                    }
                    for segment in segments
                ]
            }
        )
    ).hexdigest()
    return replace(binding, recognition_segments=segments, content_sha256=digest)


def _single_recognition_binding(
    binding: SpeechAuthorizationBinding,
    segment: SpeechRecognitionSegmentBinding,
) -> SpeechAuthorizationBinding:
    return replace(
        binding,
        subject_id=segment.subject_id,
        scope=replace(binding.scope, subject_id=segment.subject_id),
        capture_id=segment.capture_id,
        capture_generation=segment.capture_generation,
        track_id=segment.track_id,
        content_sha256=segment.content_sha256,
        recognition_segments=(),
    )


def test_continued_recognition_requires_exact_ordered_media_authorities() -> None:
    registry, exact, predecessor, current = _continued_recognition_authority()

    assert registry.authorize(exact) == exact
    assert (
        registry.authorize(
            _single_recognition_binding(exact, exact.recognition_segments[0])
        )
        is None
    )
    assert (
        registry.authorize(
            _single_recognition_binding(exact, exact.recognition_segments[1])
        )
        is None
    )
    before = (len(registry._records), len(registry._subjects))

    reversed_segments = tuple(reversed(exact.recognition_segments))
    assert (
        registry.authorize(_continued_binding_with_segments(exact, reversed_segments))
        is None
    )
    forged_track = (
        replace(exact.recognition_segments[0], track_id="track-forged"),
        exact.recognition_segments[1],
    )
    assert (
        registry.authorize(_continued_binding_with_segments(exact, forged_track))
        is None
    )
    forged_audio = (
        replace(exact.recognition_segments[0], content_sha256="0" * 64),
        exact.recognition_segments[1],
    )
    assert (
        registry.authorize(_continued_binding_with_segments(exact, forged_audio))
        is None
    )
    predecessor.binding = replace(
        predecessor.binding, connection_id="connection-foreign"
    )
    assert registry.authorize(exact) is None
    assert (len(registry._records), len(registry._subjects)) == before
    assert predecessor.recognition_content_sha256 is not None
    assert current.recognition_content_sha256 is not None


def test_continued_predecessor_can_activate_only_one_successor() -> None:
    registry, exact, predecessor, current = _continued_recognition_authority()
    before = (len(registry._records), len(registry._subjects))
    params = _params(
        capture_id="capture-second-successor",
        capture_generation=3,
        track_id="track-second-successor",
        recognition_predecessor_subject_id=predecessor.subject_id,
    )

    with pytest.raises(
        MediaTransportViolation, match="exact completed predecessor"
    ):
        _activate(
            registry,
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
        )

    assert (len(registry._records), len(registry._subjects)) == before
    assert current.subject_id == exact.subject_id


def test_continued_activation_rejects_equal_capture_generation() -> None:
    registry = _active_registry()
    predecessor_activation = _activate(
        registry,
        params=_params(
            capture_id="capture-predecessor",
            capture_generation=1,
            track_id="track-predecessor",
        ),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    predecessor = registry.consume_ticket(
        _media_ticket(predecessor_activation), request_origin=ORIGIN
    )
    assert predecessor is not None
    registry.accept_frame(
        predecessor,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(-0.25,) * 320),
    )
    registry.complete_route(
        predecessor,
        SimpleNamespace(
            activated=True,
            accepted_frames=1,
            reason_id=MediaDetachReason.RECOGNITION_CONTINUATION,
        ),  # type: ignore[arg-type]
    )
    successor_params = _params(
        capture_id="capture-current",
        capture_generation=1,
        track_id="track-current",
        recognition_predecessor_subject_id=predecessor.subject_id,
    )
    _trust_product_activation(
        registry,
        successor_params,
        connection_id="connection-1",
    )

    with pytest.raises(
        MediaTransportViolation, match="exact completed predecessor"
    ):
        registry.activate(
            params=successor_params,
            request_origin=ORIGIN,
            connection_id="connection-1",
        )

    assert len(registry._records) == 1


def test_continued_recognition_cannot_import_a_cross_session_predecessor() -> None:
    registry, exact, predecessor, current = _continued_recognition_authority()
    predecessor.binding = replace(predecessor.binding, session_id="session-foreign")
    registry._subjects.pop(("session-1", predecessor.subject_id))
    registry._subjects[("session-foreign", predecessor.subject_id)] = (
        predecessor.record_id
    )

    assert registry.authorize(exact) is None
    assert predecessor.recognition_content_sha256 is not None
    assert current.recognition_content_sha256 is not None


def test_continued_activation_requires_a_completed_exact_predecessor() -> None:
    registry = _active_registry()
    params = _params(
        capture_id="capture-current",
        capture_generation=2,
        track_id="track-current",
        recognition_predecessor_subject_id="media-subject-absent",
    )
    _trust_product_activation(
        registry,
        params,
        connection_id="connection-1",
    )

    with pytest.raises(
        MediaTransportViolation, match="exact completed predecessor"
    ):
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
        )

    assert registry._records == {}
    assert registry._subjects == {}


@pytest.mark.parametrize(
    "boundary",
    [
        "interaction",
        "activation_id",
        "activation_generation",
        "predecessor_flag",
        "successor_marker",
    ],
)
def test_continued_recognition_rejects_cross_authority_predecessor(
    boundary: str,
) -> None:
    registry, exact, predecessor, current = _continued_recognition_authority()
    if boundary == "interaction":
        predecessor.binding = replace(
            predecessor.binding, interaction_id="interaction-foreign"
        )
    elif boundary == "activation_id":
        predecessor.product_activation_id = "activation-foreign"
    elif boundary == "activation_generation":
        predecessor.product_activation_generation += 1
    elif boundary == "predecessor_flag":
        predecessor.recognition_continuation_predecessor = False
    else:
        current.recognition_predecessor_subject_id = None

    assert registry.authorize(exact) is None
    assert predecessor.recognition_content_sha256 is not None
    assert current.recognition_content_sha256 is not None


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


def _observe_task_notification(
    registry: DedicatedMediaProductRegistry,
    *,
    response_id: str = "response-task-progress-1",
    unit_id: str = "unit-1",
    text: str = "Task progress notification",
    response_generation: int = 0,
) -> ResponseRef:
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
                    "response_id": response_id,
                    "response_generation": response_generation,
                },
                "agent_event": {"event_type": "chat.final", "text": text},
                "presentation_unit": {"surface": "text", "unit_id": unit_id},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    return ResponseRef("interaction-1", response_id, response_generation)


def _task_synthesis_request(
    *,
    subject_id: str,
    response: ResponseRef,
    unit_id: str = "unit-1",
    request_id: str = "request-task-progress",
    operation_id: str = "operation-task-progress",
    locale: str = "zh-CN",
    sample_rate_hz: int = 16_000,
    text: str = "Task progress notification",
    session_id: str = "session-1",
) -> dict[str, object]:
    return {
        "contract_version": "live-voice.contract.v2",
        "request_id": request_id,
        "operation_id": operation_id,
        "operation": SYNTHESIZE_OPERATION,
        "correlation_id": "correlation-1",
        "session_id": session_id,
        "scope": {
            "subject_id": subject_id,
            "project_id": None,
            "session_id": session_id,
            "assurance": Assurance.AUTHENTICATED.value,
        },
        "timeout_ms": 1_000,
        "response": {
            "interaction_id": response.interaction_id,
            "response_id": response.response_id,
            "response_generation": response.response_generation,
        },
        "unit_id": unit_id,
        "render_plan": {
            "display_text": text,
            "spoken_text": text,
            "transforms": [],
        },
        "authoritative_agent_text": True,
        "locale": locale,
        "voice": None,
        "required_sample_rate_hz": sample_rate_hz,
    }


def test_task_notification_speech_authority_hands_off_to_rotated_media_owner() -> None:
    registry = _active_registry()
    initial = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    original = registry.consume_ticket(_media_ticket(initial), request_origin=ORIGIN)
    assert original is not None
    original.route_completed = True
    response = {
        "interaction_id": "interaction-1",
        "response_id": "response-task-progress-1",
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
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "Task progress notification",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    ref = ResponseRef("interaction-1", "response-task-progress-1", 0)
    expected = original.synthesis_content_sha256[(ref, "unit-1")]

    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": initial["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    successor = registry.activate(
        params=_params(capture_id="capture-2", track_id="track-2"),
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    current = registry.consume_ticket(_media_ticket(successor), request_origin=ORIGIN)
    assert current is not None
    current.route_completed = True
    scope = ScopeRef(
        str(successor["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    binding = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=SYNTHESIZE_OPERATION,
        operation_id="synthesize-task-progress-after-rotation",
        correlation_id="correlation-1",
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=ref,
        unit_id="unit-1",
        content_sha256=expected,
    )

    assert registry.authorize(binding) == binding


@pytest.mark.asyncio
async def test_task_notification_speech_transfer_claims_one_successor_operation() -> None:
    registry = _active_registry()
    initial = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    original = registry.consume_ticket(_media_ticket(initial), request_origin=ORIGIN)
    assert original is not None
    original.route_completed = True
    response = _observe_task_notification(registry)
    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": initial["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    provider = _CountingBatchSpeechProvider()
    service = FormalBatchSpeechService(provider, authorization_resolver=registry)
    no_owner = _task_synthesis_request(
        subject_id=str(initial["subject_id"]), response=response
    )
    no_owner_result = await service.synthesize(
        no_owner,
        SpeechRpcContext(str(initial["subject_id"]), "session-1", Assurance.AUTHENTICATED),
    )
    assert no_owner_result["error"]["reason"] == "SPEECH_OPERATION_NOT_AUTHORIZED"
    assert provider.synthesize_calls == 0

    successor = registry.activate(
        params=_params(capture_id="capture-2", track_id="track-2"),
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    current = registry.consume_ticket(_media_ticket(successor), request_origin=ORIGIN)
    assert current is not None
    current.route_completed = True
    request = _task_synthesis_request(
        subject_id=str(successor["subject_id"]), response=response
    )
    context = SpeechRpcContext(
        str(successor["subject_id"]), "session-1", Assurance.AUTHENTICATED
    )
    first = await service.synthesize(request, context)
    assert first["ok"] is True
    assert provider.synthesize_calls == 1
    retry = await service.synthesize(request, context)
    assert retry["ok"] is True
    assert provider.synthesize_calls == 1

    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": successor["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    later = registry.activate(
        params=_params(capture_id="capture-3", track_id="track-3"),
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    later_record = registry.consume_ticket(
        _media_ticket(later), request_origin=ORIGIN
    )
    assert later_record is not None
    later_record.route_completed = True
    replay = await service.synthesize(
        _task_synthesis_request(
            subject_id=str(later["subject_id"]),
            response=response,
            request_id="request-later",
            operation_id="operation-later",
        ),
        SpeechRpcContext(
            str(later["subject_id"]), "session-1", Assurance.AUTHENTICATED
        ),
    )
    assert replay["error"]["reason"] == "SPEECH_OPERATION_NOT_AUTHORIZED"
    assert provider.synthesize_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "no_owner",
        "wrong_session",
        "wrong_connection",
        "activation_generation",
        "locale",
        "sample_rate",
        "stale_response",
        "stale_unit",
    ],
)
async def test_task_notification_speech_authority_failures_never_call_provider(
    failure: str,
) -> None:
    registry = _active_registry()
    initial = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    original = registry.consume_ticket(_media_ticket(initial), request_origin=ORIGIN)
    assert original is not None
    original.route_completed = True
    response = _observe_task_notification(registry)
    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": initial["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    subject_id = str(initial["subject_id"])
    locale = "zh-CN"
    sample_rate_hz = 16_000
    if failure != "no_owner":
        successor_params = _params(capture_id="capture-2", track_id="track-2")
        if failure == "locale":
            successor_params["locale"] = "en-US"
            locale = "en-US"
        if failure == "sample_rate":
            successor_params["sample_rate_hz"] = 48_000
            sample_rate_hz = 48_000
        successor = registry.activate(
            params=successor_params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
        successor_record = registry.consume_ticket(
            _media_ticket(successor), request_origin=ORIGIN
        )
        assert successor_record is not None
        successor_record.route_completed = True
        subject_id = str(successor["subject_id"])
    request_response = (
        ResponseRef("interaction-1", "response-stale", 1)
        if failure == "stale_response"
        else response
    )
    unit_id = "unit-stale" if failure == "stale_unit" else "unit-1"
    session_id = "session-other" if failure == "wrong_session" else "session-1"
    request = _task_synthesis_request(
        subject_id=subject_id,
        response=request_response,
        unit_id=unit_id,
        request_id=f"request-{failure}",
        operation_id=f"operation-{failure}",
        locale=locale,
        sample_rate_hz=sample_rate_hz,
        session_id=session_id,
    )
    context = SpeechRpcContext(subject_id, session_id, Assurance.AUTHENTICATED)
    if failure == "wrong_connection":
        context = registry.context_for(
            SimpleNamespace(_jiuwen_ws_id="connection-other"),
            request,
            "session-1",
            "user-1",
        )
    if failure == "activation_generation":
        _trust_product_activation(
            registry,
            _params(activation_id="activation-2", activation_generation=2),
        )
    provider = _CountingBatchSpeechProvider()
    result = await FormalBatchSpeechService(
        provider, authorization_resolver=registry
    ).synthesize(request, context)
    assert result["ok"] is False
    assert provider.synthesize_calls == 0


def test_task_notification_transfer_ledger_has_deterministic_capacity_and_expiry() -> None:
    now = [0.0]
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now[0],
        authority_ttl_seconds=1.0,
    )
    registry.set_provider_available(True)
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    for index in range(17):
        _observe_task_notification(
            registry,
            response_id=f"response-capacity-{index}",
            unit_id=f"unit-capacity-{index}",
            text=f"Task progress {index}",
            response_generation=index,
        )
    authority = registry._product_activations[
        ("session-1", "connection-1", "interaction-1")
    ]
    assert len(authority.synthesis_content_sha256) == 16
    assert (
        ResponseRef("interaction-1", "response-capacity-0", 0),
        "unit-capacity-0",
        "zh-CN",
        16_000,
    ) not in authority.synthesis_content_sha256

    now[0] = 2.0
    assert registry.authorize(
        SpeechAuthorizationBinding(
            subject_id=str(activation["subject_id"]),
            scope=ScopeRef(
                str(activation["subject_id"]),
                None,
                "session-1",
                Assurance.AUTHENTICATED,
            ),
            operation=SYNTHESIZE_OPERATION,
            operation_id="operation-expired",
            correlation_id="correlation-1",
            capture_id=None,
            capture_generation=None,
            track_id=None,
            response=ResponseRef("interaction-1", "response-capacity-16", 16),
            unit_id="unit-capacity-16",
            content_sha256="0" * 64,
        )
    ) is None
    assert registry._product_activations == {}
    assert authority.synthesis_content_sha256 == {}


def test_task_notification_transfer_expiry_is_not_renewed_by_later_notifications() -> None:
    now = [0.0]
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now[0],
        authority_ttl_seconds=1.0,
    )
    registry.set_provider_available(True)
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    first_response = _observe_task_notification(registry, response_id="response-first")
    digest = record.synthesis_content_sha256[(first_response, "unit-1")]
    now[0] = 0.5
    _observe_task_notification(registry, response_id="response-later")
    now[0] = 1.1
    binding = SpeechAuthorizationBinding(
        subject_id=str(activation["subject_id"]),
        scope=ScopeRef(
            str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
        ),
        operation=SYNTHESIZE_OPERATION,
        operation_id="operation-expired-transfer",
        correlation_id="correlation-1",
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=first_response,
        unit_id="unit-1",
        content_sha256=digest,
    )
    assert registry.authorize(binding) is None
    authority = registry._product_activations[
        ("session-1", "connection-1", "interaction-1")
    ]
    assert (
        first_response,
        "unit-1",
        "zh-CN",
        16_000,
    ) not in authority.synthesis_content_sha256


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
    (("none", False), ("before_downlink_complete", True), ("after_downlink_complete", False)),
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


def test_product_tts_identity_budget_is_aligned_with_the_synthesis_route() -> None:
    """The product TTS allocation mints one fresh identity per request.

    ``_handle_streaming_synthesis`` derives ``product-tts-<digest>`` from the
    operation, response and unit of every accepted synthesize call and always
    opens it at generation zero, so each product TTS request costs one new
    streaming identity.  The ledgers upstream therefore decide how many product
    TTS requests one long-lived registry can serve, and the Provider budget
    must not be tighter than the route's own retained-binding ledger: a
    Provider that refuses first becomes the wall for an identity the route
    still treats as live.
    """

    assert MAX_STREAMING_IDENTITY_LEDGER == _MAX_ROUTE_IDENTITIES


@pytest.mark.asyncio
async def test_silent_socket_expires_via_background_sweeper() -> None:
    """F06: 静默 socket 的权限过期不依赖任何其他注册表调用——
    后台清扫器按间隔跑 _prune,置位停车栅栏并移除记录。"""
    clock = {"now": 0.0}
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: clock["now"],
        authority_ttl_seconds=5.0,
        expiry_sweep_interval_seconds=0.02,
    )
    registry.set_provider_available(True)
    params = _params()
    activation = _activate(
        registry, params=params, request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    assert record.stop.is_set() is False

    clock["now"] = 100.0
    await asyncio.sleep(0.15)

    assert record.stop.is_set() is True
    assert registry._records == {}
    await registry.close_expiry_sweeper()


@pytest.mark.asyncio
async def test_stop_all_leaves_wakes_records_and_refuses_new_admissions() -> None:
    """F16 相位一:停车栅栏唤醒在册叶子并拒绝新的票据消费。"""
    registry = _active_registry()
    params = _params()
    activation = _activate(
        registry, params=params, request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)

    woken = registry.stop_all_leaves()
    assert woken >= 1

    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is None
    await registry.close_expiry_sweeper()


class _ParkedMediaSocket:
    """recv 永远停车、close 只记录——模拟最不合作的传输。"""

    def __init__(self) -> None:
        self.closed_codes: list[int] = []
        self.sent: list[object] = []

    async def recv(self):
        await asyncio.Event().wait()

    async def send(self, message) -> None:
        self.sent.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_codes.append(code)


@pytest.mark.asyncio
async def test_revoked_leaf_parked_in_recv_terminates_with_honest_incomplete() -> None:
    """F06: 停车栅栏必须唤醒停在 recv 的叶子;传输在预算内仍不停时,
    返回诚实的 cleanup_complete=False,绝不无限挂起。"""
    from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
        DedicatedMediaRouteRequest,
        run_dedicated_media_socket_leaf,
    )

    registry = _active_registry()
    params = _params()
    activation = _activate(
        registry, params=params, request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None

    request = DedicatedMediaRouteRequest(
        enabled=True,
        expected_origin=ORIGIN,
        request_origin=ORIGIN,
        binding=record.binding,
        provider_available=True,
        binary_transport_available=True,
    )
    socket = _ParkedMediaSocket()
    leaf = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            request,
            socket=socket,
            on_audio_frame=lambda _frame: None,
            stop_event=record.stop,
            deadline_remaining=lambda: registry.record_deadline_remaining(record),
        )
    )
    await asyncio.sleep(0.05)
    assert leaf.done() is False

    record.stop.set()
    result = await asyncio.wait_for(leaf, timeout=30)

    assert 1001 in socket.closed_codes
    assert result.cleanup_complete is False
    await registry.close_expiry_sweeper()
