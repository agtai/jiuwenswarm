# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Central, default-off registration for the formal dedicated media route.

The package media leaf deliberately cannot register itself.  This module owns
the product ticket, same-origin handshake, ephemeral Speech authority, and the
memory-only audit facts needed by the W2 Web composition.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import hmac
import io
import json
import logging
import math
import os
import queue
import re
import secrets
import struct
import threading
import time
import wave
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Literal, Mapping

from jiuwenswarm.common.live_voice_profiling import identity_fields, profile_event
from jiuwenswarm.common.live_voice_capture_limits import MAX_CAPTURE_WAV_BYTES
from jiuwenswarm.common.live_voice_audio_diagnostics import record_audio_diagnostic
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    canonical_json_bytes,
)
from jiuwenswarm.common.security.ws_origin import (
    get_header_value,
    is_allowed_browser_origin,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MEDIA_END_OF_TURN_CAPABILITY,
    MediaAck,
    MediaAudioFrame,
    MediaAuthorityBinding,
    MediaDirection,
    MediaDetachReason,
    MediaFrameFormat,
    MediaGenerationBinding,
    MediaGenerationKind,
    MediaEndOfTurn,
    MediaPlaybackStopOutcome,
    MediaPlaybackStopReceipt,
    MediaSpeechStart,
    MediaPlayoutBinding,
    MediaTransportViolation,
    MediaAttach,
    deserialize_media_control,
    serialize_media_control,
    validate_playback_stop_receipt,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaLeafCleanupOwner,
    DedicatedMediaLeafCleanupSnapshot,
    DedicatedMediaRouteRequest,
    DedicatedMediaSocketLeafResult,
    run_dedicated_media_socket_leaf,
    run_dedicated_media_downlink_socket_leaf,
)
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import (
    GatewayNativeActivation,
    NATIVE_BROWSER_DESCRIPTOR_KEY,
    NativeRuntimeClientError,
)
from jiuwenswarm.gateway.live_voice.streaming_speech_route import (
    StreamingRecognitionFallbackReason,
    StreamingRecognitionEndOfTurn,
    StreamingRecognitionHandle,
    StreamingRecognitionOutcome,
    StreamingRecognitionRouteOwner,
    StreamingRecognitionSpeechStart,
)
from jiuwenswarm.gateway.live_voice.product_streaming_synthesis import (
    ProductStreamingSynthesisSource,
    start_product_streaming_synthesis,
)
from jiuwenswarm.gateway.live_voice import task_notification_preparation as task_preparation
from jiuwenswarm.gateway.live_voice.native_response_downlink import (
    NativeDownlinkPresentationUnit,
    NativeResponseDownlinkSource,
)
from jiuwenswarm.gateway.live_voice.streaming_synthesis_route import (
    StreamingSynthesisOutcome,
    StreamingSynthesisRouteOwner,
    StreamingSynthesisRouteViolation,
)
from jiuwenswarm.server.live_voice.batch_speech import (
    CONTRACT_VERSION as SPEECH_CONTRACT_VERSION,
    FormalBatchSpeechService,
    RECOGNIZE_OPERATION,
    SYNTHESIZE_OPERATION,
    SynthesisBatchRequest,
    SpeechAuthorizationBinding,
    SpeechRpcContext,
    parse_synthesis_batch_request,
)
from jiuwenswarm.server.live_voice.interaction_engine import InteractionAction
from jiuwenswarm.server.live_voice.latency_measurement import (
    L0Milestone,
    L0RoundBinding,
    L0RoundClassification,
    emit_runtime_l0_milestone,
    register_runtime_l0_binding,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    authorize_stream_request,
    SpeechResponseAuthority,
    SpeechStreamAuthority,
    StreamingSpeechViolation,
    CaptureRef,
    RecognitionStreamRef,
    RecognitionStreamRequest,
    RecognitionTurnDetection,
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import SpeechRouteTier
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    NATIVE_PCM_SAMPLE_RATE,
    NativeAudioOutput,
    NativeEngineEvent,
    NativeInputAudioFrame,
    NativeProviderDone,
    OpenAIRealtimeNativeInteractionEngine,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeInteractionBinding,
    NativePresentationCursor,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    PresentationAck,
    PresentationSurface,
)
from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    LiveVoiceObservabilityCollector,
    LiveVoiceMetric,
    LiveVoiceObservation,
    create_metric,
    create_observation,
)


MEDIA_ACTIVATE_METHOD = "live_voice.media.activate"
MEDIA_CLOSE_METHOD = "live_voice.media.close"
MEDIA_PLAYOUT_RECEIPT_METHOD = "live_voice.media.playout_receipt"
MEDIA_PLAYOUT_STOP_METHOD = "live_voice.media.playout_stop"
MEDIA_NATIVE_TEXT_METHOD = "live_voice.media.native_text"
STREAMING_RECOGNITION_RESULT_METHOD = "live_voice.speech.recognize_streaming_result"
MEDIA_ROUTE_PATH = "/ws/live-voice/media"
MEDIA_SUBPROTOCOL = "live-voice.media.v1"
MEDIA_FEATURE_ENV = "JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED"
MEDIA_END_OF_TURN_FEATURE_ENV = "JIUWENSWARM_LIVE_VOICE_END_OF_TURN_ENABLED"
MEDIA_AUTH_CONTRACT_VERSION = "live-voice.media-auth.v1"

_MAX_RECORDS = 128
_MAX_CAPTURE_WAV_BYTES = MAX_CAPTURE_WAV_BYTES
_MAX_DOWNLINK_WAV_BYTES = 8 * 1024 * 1024
# 20 ms media frames.  Keep streaming playout bounded while allowing a complete
# long-form response instead of truncating every route at the former 30 seconds.
_MAX_DOWNLINK_FRAMES = 9_000
_PRODUCT_PLAYOUT_QUEUE_CAPACITY = 256
_NATIVE_INPUT_QUEUE_CAPACITY = 800
_NATIVE_BUSINESS_POLL_SECONDS = 1.0
_NATIVE_STARTUP_CLOSE_WAIT_SECONDS = 0.1
_NATIVE_NOTIFICATION_QUEUE_CAPACITY = 256
_NATIVE_SPEECH_START_QUEUE_CAPACITY = 8
_NATIVE_END_OF_TURN_QUEUE_CAPACITY = 8
# Provider audio can arrive substantially faster than Browser playout, while
# interruption controls must still be consumed immediately.  Retain a fixed
# 81.92-second burst reservoir (4096 x 20 ms frames) and admit audio to Runtime
# in small concurrent batches; both bounds are independent of the Provider
# WebSocket library and keep the reader free to observe STOP/VAD events.
_NATIVE_PROVIDER_EVENT_QUEUE_CAPACITY = 4096
_NATIVE_AUDIO_PROPOSAL_BATCH = 16
_NATIVE_PROVIDER_TRANSPORT_FAILURES = frozenset({
    "REALTIME_TRANSPORT_SEND_FAILED", "REALTIME_TRANSPORT_RECEIVE_FAILED", "REALTIME_PROVIDER_TIMEOUT",
    "MEDIA_NATIVE_INPUT_BACKPRESSURE",
})
_NATIVE_ORDERED_CONTROL_OPERATIONS = frozenset(
    {"LISTEN", "REVISE", "SILENCE", "TURN_COMMIT", "SPEAK"}
)


def _native_audio_extends_batch(
    first: NativeAudioOutput,
    candidate: NativeAudioOutput,
    *,
    ordinal: int,
) -> bool:
    return (
        candidate.response == first.response
        and candidate.provider_response_id == first.provider_response_id
        and candidate.provider_item_id == first.provider_item_id
        and candidate.content_index == first.content_index
        and candidate.sequence == first.sequence + ordinal
    )


_PLAYOUT_RECEIPT_REQUEST_FIELDS = (
    "session_id",
    "subject_id",
    "correlation_id",
    "interaction_id",
    "response_id",
    "response_generation",
    "unit_id",
    "capture_frames_acked",
    "rendered_chunks",
    "rendered_through_seq",
    "playout_queue_capacity",
    "playout_peak_depth",
    "capture_control_ack",
    "playout_state",
)
_DEFAULT_TICKET_TTL_SECONDS = 30.0
_DEFAULT_AUTHORITY_TTL_SECONDS = 15 * 60.0
_MEDIA_AUTH_FRAME_MAX_BYTES = 8 * 1024
_MEDIA_AUTH_TIMEOUT_SECONDS = 2.0
_MAX_ID_CHARS = 256
# Capture frames are fixed at 20 ms. A cold native Provider open can
# legitimately take several seconds, so the former 64-frame (1.28 s) queue
# made a first short utterance fail before the Provider became ready while a
# warm later utterance succeeded. Retain references for the complete bounded
# 15-second open window plus one second of scheduling margin. The actual PCM
# remains owned by the existing bounded, memory-only batch capture buffer.
_MAX_STREAMING_PREOPEN_FRAMES = 800
# End-of-turn arbitration starts before the Provider open settles, so it waits
# for that open instead of cancelling it. The route owner already hard-bounds
# the open; this is the independent local bound.
_STREAMING_BEGIN_WAIT_SECONDS = 20.0
_STREAMING_RESULT_TIMEOUT_SECONDS = 36.0
_STREAMING_OBSERVABILITY_QUEUE_CAPACITY = 64
_STREAMING_OBSERVABILITY_CLOSE_BUDGET_SECONDS = 0.05
_LOCALES = frozenset({"en", "en-US", "zh", "zh-CN"})
_PRODUCT_CONTRACT_VERSION = "live-voice.product-composition.gate0.v1"
_P2_NOTIFICATION_BATCH_MAX = 16
_P2_NOTIFICATION_BATCH_KEYS = frozenset(
    {
        "status",
        "notifications",
        "session_id",
        "correlation_id",
        "interaction_id",
        "activation_id",
        "activation_generation",
    }
)
_P2_NOTIFICATION_ITEM_KEYS = frozenset(
    {
        "status",
        "kind",
        "request_id",
        "round_id",
        "response",
        "agent_event",
        "source_event",
        "progress_event",
        "presentation_unit",
        "error_reason",
        "publish_seq",
        "session_id",
        "correlation_id",
        "interaction_id",
        "activation_id",
        "activation_generation",
    }
)
_STREAMING_DIAGNOSTIC_QUEUE_CAPACITY = 16
_STREAMING_DIAGNOSTIC_CLOSE_BUDGET_SECONDS = 0.05
_MEDIA_FIRST_FRAME_DIAGNOSTIC_QUEUE_CAPACITY = 64
_FORMAL_P2_EVIDENCE = frozenset(
    {
        "TRUSTED_AUTHORITY_RESOLVED",
        "FORMAL_ACTIVATION_LEASE_OPEN",
        "RUNTIME_PATH_OBSERVED",
        "P2_NOTIFICATION_BACKPRESSURE_CLOSED",
    }
)
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _MediaFirstFrameDiagnosticItem:
    stage: str
    scope_sha256: str
    capture_generation: int
    frame_seq: int
    monotonic_ms: float
    elapsed_ms: float
    outcome: str
    reason: str


class _MediaFirstFrameDiagnosticWorker:
    """Bounded process-wide logger that never occupies the media ACK path."""

    def __init__(self) -> None:
        self._queue: queue.Queue[_MediaFirstFrameDiagnosticItem] = queue.Queue(
            maxsize=_MEDIA_FIRST_FRAME_DIAGNOSTIC_QUEUE_CAPACITY
        )
        self._start_lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def submit(self, item: _MediaFirstFrameDiagnosticItem) -> bool:
        self._ensure_started()
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            return False
        return True

    def _ensure_started(self) -> None:
        with self._start_lock:
            if self._worker is not None:
                return
            self._worker = threading.Thread(
                target=self._run,
                name="live-voice-media-first-frame-diagnostics",
                daemon=True,
            )
            self._worker.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                _LOGGER.info(
                    "live_voice_media_first_frame "
                    "stage=%s scope_sha256=%s generation=%d seq=%d "
                    "monotonic_ms=%.3f elapsed_ms=%.3f outcome=%s reason=%s",
                    item.stage,
                    item.scope_sha256,
                    item.capture_generation,
                    item.frame_seq,
                    item.monotonic_ms,
                    item.elapsed_ms,
                    item.outcome,
                    item.reason,
                )
            except BaseException:
                pass
            finally:
                self._queue.task_done()


_MEDIA_FIRST_FRAME_DIAGNOSTIC_WORKER = _MediaFirstFrameDiagnosticWorker()

StreamingXObsEvent = Literal["failure.observed", "degradation.activated"]
StreamingXObsMetric = Literal[
    "live_voice.failure_total", "live_voice.degradation_total"
]


class _StreamingObservabilityOwner:
    """Bounded non-authoritative handoff to possibly blocking X-OBS sinks."""

    def __init__(
        self,
        collector: LiveVoiceObservabilityCollector,
        *,
        capacity: int = _STREAMING_OBSERVABILITY_QUEUE_CAPACITY,
    ) -> None:
        self._collector = collector
        self._queue: queue.Queue[
            tuple[LiveVoiceObservation, LiveVoiceMetric] | None
        ] = queue.Queue(maxsize=max(1, capacity))
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._closed = False

    def submit(
        self, observation: LiveVoiceObservation, metric: LiveVoiceMetric
    ) -> bool:
        with self._lock:
            if self._closed:
                return False
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run,
                    name="live-voice-streaming-observability",
                    daemon=True,
                )
                self._worker.start()
            try:
                self._queue.put_nowait((observation, metric))
            except queue.Full:
                _LOGGER.warning(
                    "live_voice_streaming_observability_unavailable "
                    "reason=QUEUE_SATURATED"
                )
                return False
            return True

    def close(self) -> None:
        # Teardown is also diagnostic-only.  A sink that ignores its own
        # budget must not hold the product shutdown path.
        with self._lock:
            if self._closed:
                return
            self._closed = True
            worker = self._worker
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=_STREAMING_OBSERVABILITY_CLOSE_BUDGET_SECONDS)

    def _run(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=0.05)
            except queue.Empty:
                with self._lock:
                    if self._closed:
                        return
                continue
            try:
                if item is None:
                    return
                observation, metric = item
                try:
                    self._collector.emit_observation(observation)
                except Exception:
                    _LOGGER.warning(
                        "live_voice_streaming_observability_unavailable "
                        "reason=OBSERVATION_SINK_FAILED"
                    )
                try:
                    self._collector.emit_metric(metric)
                except Exception:
                    _LOGGER.warning(
                        "live_voice_streaming_observability_unavailable "
                        "reason=METRIC_SINK_FAILED"
                    )
            finally:
                self._queue.task_done()


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _required_id(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_ID_CHARS
    ):
        raise MediaTransportViolation(
            "MEDIA_INVALID_ACTIVATION", f"{field_name} is invalid"
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise MediaTransportViolation(
            "MEDIA_INVALID_ACTIVATION", f"{field_name} is invalid"
        ) from exc
    return value


def _safe_uint(value: object, field_name: str) -> int:
    if type(value) is not int or not 0 <= value <= (1 << 53) - 1:
        raise MediaTransportViolation(
            "MEDIA_INVALID_ACTIVATION", f"{field_name} is invalid"
        )
    return value


def _has_formal_p2_manifest(payload: Mapping[str, object]) -> bool:
    """Accept only the closed formal P2 fact emitted by AgentServer."""

    manifest = payload.get("product_composition")
    if not isinstance(manifest, Mapping):
        return False
    if (
        manifest.get("contract_version") != _PRODUCT_CONTRACT_VERSION
        or manifest.get("enabled") is not True
        or set(manifest) != {"contract_version", "enabled", "routes"}
    ):
        return False
    routes = manifest.get("routes")
    if not isinstance(routes, list):
        return False
    matches = [
        route
        for route in routes
        if isinstance(route, Mapping) and route.get("segment") == "p2.agent_interaction"
    ]
    if len(matches) != 1:
        return False
    route = matches[0]
    evidence = route.get("evidence_ids")
    return bool(
        set(route)
        == {
            "segment",
            "truth",
            "reason_id",
            "evidence_ids",
            "formal_runtime_observed",
        }
        and route.get("truth") == "formal"
        and route.get("reason_id") == "FORMAL_ROUTE_OBSERVED"
        and route.get("formal_runtime_observed") is True
        and isinstance(evidence, list)
        and all(isinstance(item, str) for item in evidence)
        and _FORMAL_P2_EVIDENCE.issubset(frozenset(evidence))
    )


def _binding_payload(binding: MediaAuthorityBinding) -> dict[str, object]:
    payload = json.loads(serialize_media_control(MediaAttach(binding)))
    result = payload.get("binding")
    assert isinstance(result, dict)
    return result


def _parse_media_auth_frame(value: object) -> tuple[str, MediaAuthorityBinding] | None:
    """Parse the bounded, closed first-frame capability without echoing secrets."""

    if not isinstance(value, str):
        return None
    try:
        if len(value.encode("utf-8")) > _MEDIA_AUTH_FRAME_MAX_BYTES:
            return None
        raw = json.loads(value)
    except (UnicodeEncodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, Mapping) or set(raw) != {
        "type",
        "contract_version",
        "media_ticket",
        "binding",
    }:
        return None
    ticket = raw.get("media_ticket")
    if (
        raw.get("type") != "media.auth"
        or raw.get("contract_version") != MEDIA_AUTH_CONTRACT_VERSION
        or not isinstance(ticket, str)
        or not 32 <= len(ticket) <= 128
        or not all(
            character.isascii() and (character.isalnum() or character in "_-")
            for character in ticket
        )
    ):
        return None
    try:
        attach = deserialize_media_control(
            json.dumps(
                {
                    "type": "media.attach",
                    "contract_version": "live-voice.media.v1",
                    "binding": raw.get("binding"),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    except MediaTransportViolation:
        return None
    if not isinstance(attach, MediaAttach):
        return None
    return ticket, attach.binding


def _request_origin(ws: Any) -> str | None:
    headers = getattr(ws, "request_headers", None)
    if headers is None:
        request = getattr(ws, "request", None)
        headers = getattr(request, "headers", None)
    origin = get_header_value(headers, "Origin")
    return origin if isinstance(origin, str) and origin else None


def _js_round(value: float) -> int:
    """Match JavaScript Math.round, including negative half values."""

    return math.floor(value + 0.5)


def _pcm16(samples: tuple[float, ...]) -> bytes:
    output = bytearray(len(samples) * 2)
    for index, sample in enumerate(samples):
        clipped = max(-1.0, min(1.0, sample))
        scaled = clipped * (32768 if clipped < 0 else 32767)
        struct.pack_into("<h", output, index * 2, _js_round(scaled))
    return bytes(output)


def _wav_bytes(pcm: bytes, sample_rate_hz: int) -> bytes:
    size = 44 + len(pcm)
    if size > _MAX_CAPTURE_WAV_BYTES:
        raise MediaTransportViolation(
            "MEDIA_CAPTURE_LIMIT_EXCEEDED", "capture exceeds the batch Speech limit"
        )
    header = bytearray(44)
    header[0:4] = b"RIFF"
    struct.pack_into("<I", header, 4, size - 8)
    header[8:12] = b"WAVE"
    header[12:16] = b"fmt "
    struct.pack_into(
        "<IHHIIHH", header, 16, 16, 1, 1, sample_rate_hz, sample_rate_hz * 2, 2, 16
    )
    header[36:40] = b"data"
    struct.pack_into("<I", header, 40, len(pcm))
    return bytes(header) + pcm


def _downlink_frames(
    audio_wav: bytes, sample_rate_hz: int
) -> tuple[MediaAudioFrame, ...]:
    if len(audio_wav) > _MAX_DOWNLINK_WAV_BYTES:
        raise MediaTransportViolation(
            "MEDIA_DOWNLINK_LIMIT_EXCEEDED",
            "synthesis audio exceeds the downlink limit",
        )
    try:
        with wave.open(io.BytesIO(audio_wav), "rb") as source:
            if (
                source.getcomptype() != "NONE"
                or source.getnchannels() != 1
                or source.getsampwidth() != 2
                or source.getframerate() != sample_rate_hz
                or source.getnframes() <= 0
            ):
                raise MediaTransportViolation(
                    "MEDIA_INVALID_DOWNLINK_AUDIO",
                    "downlink requires non-empty mono PCM16 WAV",
                )
            raw = source.readframes(source.getnframes())
    except (EOFError, wave.Error) as exc:
        raise MediaTransportViolation(
            "MEDIA_INVALID_DOWNLINK_AUDIO", "downlink audio is not a complete WAV"
        ) from exc
    samples_per_frame = sample_rate_hz // 50
    sample_count = len(raw) // 2
    frame_count = (sample_count + samples_per_frame - 1) // samples_per_frame
    if frame_count <= 0 or frame_count > _MAX_DOWNLINK_FRAMES:
        raise MediaTransportViolation(
            "MEDIA_DOWNLINK_LIMIT_EXCEEDED", "downlink duration exceeds the W2 bound"
        )
    signed = struct.unpack(f"<{sample_count}h", raw)
    frames: list[MediaAudioFrame] = []
    for seq in range(frame_count):
        offset = seq * samples_per_frame
        values = signed[offset : offset + samples_per_frame]
        normalized = tuple(value / (32768 if value < 0 else 32767) for value in values)
        if len(normalized) < samples_per_frame:
            normalized += (0.0,) * (samples_per_frame - len(normalized))
        frames.append(
            MediaAudioFrame(
                seq=seq,
                sample_cursor=offset,
                samples=normalized,
            )
        )
    return tuple(frames)


def _resample_native_frame(
    samples: tuple[float, ...], *, output_samples: int
) -> tuple[float, ...]:
    """Linearly resample one exact 20 ms mono frame without timeline drift."""

    if not samples or output_samples <= 0:
        raise MediaTransportViolation(
            "MEDIA_NATIVE_SAMPLE_RATE_UNSUPPORTED",
            "Native resampling requires non-empty exact 20 ms frames",
        )
    if len(samples) == output_samples:
        return samples
    ratio = len(samples) / output_samples
    result: list[float] = []
    for index in range(output_samples):
        position = (index + 0.5) * ratio - 0.5
        if position <= 0:
            result.append(samples[0])
            continue
        if position >= len(samples) - 1:
            result.append(samples[-1])
            continue
        left = math.floor(position)
        fraction = position - left
        result.append(samples[left] * (1.0 - fraction) + samples[left + 1] * fraction)
    return tuple(result)


def _native_downlink_frames(
    pcm16: bytes, *, sample_rate_hz: int = NATIVE_PCM_SAMPLE_RATE
) -> tuple[MediaAudioFrame, ...]:
    """Convert admitted PCM24k into exact 20 ms frames at the Browser rate."""

    provider_samples_per_frame = NATIVE_PCM_SAMPLE_RATE // 50
    browser_samples_per_frame = sample_rate_hz // 50
    if (
        type(pcm16) is not bytes
        or not pcm16
        or len(pcm16) % 2
        or len(pcm16) // 2 % provider_samples_per_frame
        or sample_rate_hz <= 0
        or sample_rate_hz % 50
    ):
        raise MediaTransportViolation(
            "MEDIA_NATIVE_AUDIO_FRAME_ALIGNMENT",
            "Native audio must contain complete 20 ms PCM16 frames",
        )
    sample_count = len(pcm16) // 2
    frame_count = sample_count // provider_samples_per_frame
    if frame_count > _MAX_DOWNLINK_FRAMES:
        raise MediaTransportViolation(
            "MEDIA_DOWNLINK_LIMIT_EXCEEDED",
            "Native audio exceeds the dedicated-media bound",
        )
    signed = struct.unpack(f"<{sample_count}h", pcm16)
    frames: list[MediaAudioFrame] = []
    for seq in range(frame_count):
        provider_offset = seq * provider_samples_per_frame
        values = signed[provider_offset : provider_offset + provider_samples_per_frame]
        normalized = tuple(value / (32768 if value < 0 else 32767) for value in values)
        frames.append(
            MediaAudioFrame(
                seq=seq,
                sample_cursor=seq * browser_samples_per_frame,
                samples=_resample_native_frame(
                    normalized, output_samples=browser_samples_per_frame
                ),
            )
        )
    return tuple(frames)


def _synthesis_authorization_binding(
    request: SynthesisBatchRequest,
) -> SpeechAuthorizationBinding:
    content_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {
                "response": {
                    "interaction_id": request.response.interaction_id,
                    "response_id": request.response.response_id,
                    "response_generation": request.response.response_generation,
                },
                "unit_id": request.unit_id,
                "display_text": request.display_text,
                "spoken_text": request.spoken_text,
                "transforms": [
                    {
                        "transform": item.transform,
                        "source_start": item.source_start,
                        "source_end": item.source_end,
                        "rendered_text": item.rendered_text,
                    }
                    for item in request.transforms
                ],
                "locale": request.locale,
                "voice": request.voice,
                "required_sample_rate_hz": request.required_sample_rate_hz,
            }
        )
    ).hexdigest()
    return SpeechAuthorizationBinding(
        subject_id=request.scope.subject_id,
        scope=request.scope,
        operation=SYNTHESIZE_OPERATION,
        operation_id=request.operation_id,
        correlation_id=request.correlation_id,
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=request.response,
        unit_id=request.unit_id,
        content_sha256=content_sha256,
    )


def _streaming_error_envelope(
    request: SynthesisBatchRequest, reason: str
) -> dict[str, object]:
    return {
        "contract_version": SPEECH_CONTRACT_VERSION,
        "request_id": request.request_id,
        "operation_id": request.operation_id,
        "ok": False,
        "result": None,
        "error": {
            "code": "CAPABILITY_UNAVAILABLE",
            "reason": reason,
            "message": "streaming speech stopped; continue with text or retry",
            "retriable": True,
            "correlation_id": request.correlation_id,
            "details": {},
        },
    }


@dataclass(slots=True)
class _MediaAuthority:
    record_id: str
    subject_id: str
    expected_origin: str
    product_activation_id: str
    product_activation_generation: int
    binding: MediaAuthorityBinding
    locale: str
    end_of_turn_capability: str | None
    issued_at: float
    ticket_expires_at: float
    authority_expires_at: float
    native_activation: GatewayNativeActivation | None = field(default=None, repr=False)
    native_session_key: tuple[str, str, str, str, int] | None = field(
        default=None, repr=False
    )
    native_provider_item_id: str | None = None
    native_content_index: int | None = None
    native_source_start_sample: int | None = None
    native_source_end_sample: int | None = None
    barge_in_capture: bool = False
    ticket_consumed: bool = False
    route_completed: bool = False
    accepted_frames: int = 0
    last_uplink_ack_through_seq: int | None = None
    last_uplink_ack_observed_at: str | None = None
    last_uplink_ack_monotonic_ms: float | None = None
    last_uplink_ack_duration_ms: float | None = None
    first_uplink_frame_accepted_diagnostic: bool = False
    first_uplink_ack_sent_diagnostic: bool = False
    pcm: bytearray = field(default_factory=bytearray, repr=False)
    recognition_content_sha256: str | None = None
    streaming_recognition_authority: SpeechStreamAuthority | None = field(
        default=None, repr=False
    )
    streaming_recognition_handle: StreamingRecognitionHandle | None = field(
        default=None, repr=False
    )
    streaming_recognition_outcome: StreamingRecognitionOutcome | None = field(
        default=None, repr=False
    )
    streaming_recognition_ready: asyncio.Future[StreamingRecognitionOutcome] | None = (
        field(default=None, repr=False)
    )
    streaming_recognition_begin_task: asyncio.Task[None] | None = field(
        default=None, repr=False
    )
    streaming_preopen_frames: list[MediaAudioFrame] = field(
        default_factory=list, repr=False
    )
    recognition_predecessor_subject_id: str | None = field(
        default=None, repr=False
    )
    recognition_continuation_predecessor: bool = False
    recognition_continuation_successor_subject_id: str | None = field(
        default=None, repr=False
    )
    streaming_voice_commit_receipt: str | None = field(default=None, repr=False)
    streaming_started_at: float | None = None
    streaming_observation_emitted: bool = False
    streaming_x_obs_event: StreamingXObsEvent | None = None
    streaming_x_obs_metric: StreamingXObsMetric | None = None
    streaming_observation_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False
    )
    synthesis_content_sha256: dict[tuple[ResponseRef, str], str] = field(
        default_factory=dict, repr=False
    )
    playout_receipts: dict[tuple[ResponseRef, str], dict[str, object]] = field(
        default_factory=dict, repr=False
    )
    playout_receipt_content_sha256: dict[tuple[ResponseRef, str], str] = field(
        default_factory=dict, repr=False
    )
    downlink_frames: tuple[MediaAudioFrame, ...] = field(default=(), repr=False)
    downlink_stream_source: (
        ProductStreamingSynthesisSource | NativeResponseDownlinkSource | task_preparation.PreparedNotificationSource | None
    ) = field(default=None, repr=False)
    downlink_response: ResponseRef | None = None
    downlink_unit_id: str | None = None
    downlink_unit_seq: int | None = None
    native_final_unit_id: str | None = None
    native_final_unit_seq: int | None = None
    native_generation_completed: bool | None = None
    native_transport_failure: bool = False
    downlink_content_sha256: str | None = field(default=None, repr=False)
    downlink_overlap_record_id: str | None = None
    downlink_overlap_observed: bool = False
    downlink_results: dict[tuple[ResponseRef, str], dict[str, object]] = field(
        default_factory=dict, repr=False
    )


def _l0_media_binding(
    record: _MediaAuthority,
    *,
    response: ResponseRef | None = None,
) -> L0RoundBinding | None:
    try:
        return L0RoundBinding(
            correlation_id=record.binding.correlation_id,
            session_id=record.binding.session_id,
            interaction_id=record.binding.interaction_id,
            activation_generation=record.product_activation_generation,
            response_id=(response.response_id if response is not None else None),
            response_generation=(
                response.response_generation if response is not None else None
            ),
        )
    except (TypeError, ValueError):
        # Product media identities intentionally accept a wider representation
        # than the content-free measurement contract.  Optional diagnostics
        # must never narrow or fail the authoritative media path.
        return None


def _terminal_preparation_event_key(result: Mapping[str, object]) -> str | None:
    source = result.get("source_event")
    if not isinstance(source, Mapping):
        return None
    scope, stream, payload, extensions = (source.get(name) for name in ("scope", "stream_ref", "payload", "extensions"))
    if not all(isinstance(value, Mapping) for value in (scope, stream, payload, extensions)):
        return None
    progress = extensions.get("jiuwenswarm.task_progress_return")
    if (scope.get("assurance") != "authenticated" or scope.get("session_id") != result.get("session_id")
            or stream.get("kind") != "task" or payload.get("state") != "terminal"
            or payload.get("outcome") not in {"completed", "failed", "interrupted", "unknown"}
            or not isinstance(progress, Mapping)):
        return None
    values = [scope.get("subject_id"), scope.get("project_id"), scope.get("session_id"),
              "authenticated", stream.get("id"), progress.get("persistent_attempt_id"), source.get("event_id")]
    try:
        for value in values:
            _required_id(value, "terminal_source_identity")
    except MediaTransportViolation:
        return None
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


@dataclass(slots=True)
class _SynthesisAuthorityTransfer:
    """A bounded P2 notification handoff, claimable by one media operation."""

    content_sha256: str
    expires_at: float
    claimed_subject_id: str | None = None
    claimed_operation_id: str | None = None
    task_notification: bool = False
    terminal_event_key: str | None = None
    presentation_retired: bool = False
    streaming_authority: SpeechStreamAuthority | None = field(default=None, repr=False)
    unplayed_preparation: tuple[task_preparation.PreparationIdentity, str] | None = field(default=None, repr=False)


@dataclass(slots=True)
class _NativeNotificationSequenceFence:
    """Bound one serialized Browser notification poll to its serving authority."""

    agent_high_water: int = 0
    native_work_state_sequence: int = 0
    task_presentation_retired_generation: int = -1
    local_request_id: str | None = None
    local_sequence: int | None = None
    local_response: dict[str, object] | None = field(default=None, repr=False)
    forwarded_request_id: str | None = None
    forwarded_client_sequence: int | None = None
    forwarded_agent_sequence: int | None = None
    terminal_notification: dict[str, object] | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class _ProductActivationAuthority:
    session_id: str
    connection_id: str
    correlation_id: str
    interaction_id: str
    activation_id: str
    activation_generation: int
    product_composition: dict[str, object] = field(repr=False)
    expires_at: float
    synthesis_content_sha256: OrderedDict[
        tuple[ResponseRef, str, str, int], _SynthesisAuthorityTransfer
    ] = field(default_factory=OrderedDict)
    notification_fence: _NativeNotificationSequenceFence = field(
        default_factory=_NativeNotificationSequenceFence,
        repr=False,
        compare=False,
    )
    streaming_response_authorities: list[SpeechResponseAuthority] = field(
        default_factory=list,
        repr=False,
        compare=False,
    )


@dataclass(slots=True)
class _NativeMediaSession:
    key: tuple[str, str, str, str, int]
    record_id: str
    activation: GatewayNativeActivation = field(repr=False)
    engine: Any = field(repr=False)
    input_queue: asyncio.Queue[NativeInputAudioFrame | None] = field(repr=False)
    speech_start_queue: asyncio.Queue[int] = field(repr=False)
    end_of_turn_queue: asyncio.Queue[tuple[int, int]] = field(repr=False)
    delivery_queue: asyncio.Queue[NativeEngineEvent] = field(repr=False)
    start_record: _MediaAuthority | None = field(default=None, repr=False)
    input_enqueued_at: dict[int, float] = field(default_factory=dict, repr=False)
    start_task: asyncio.Task[None] | None = field(default=None, repr=False)
    startup_retired: bool = False
    input_task: asyncio.Task[None] | None = field(default=None, repr=False)
    event_task: asyncio.Task[None] | None = field(default=None, repr=False)
    delivery_task: asyncio.Task[None] | None = field(default=None, repr=False)
    business_poll_task: asyncio.Task[None] | None = field(default=None, repr=False)
    business_refresh_task: asyncio.Task | None = field(default=None, repr=False)
    business_receipt_epoch: int = 0
    business_refresh_epoch: int = 0
    notification_wake_tasks: set[asyncio.Task[None]] = field(default_factory=set, repr=False)
    business_observation_cursor: dict[str, object] | None = field(default=None, repr=False)
    business_context_result: dict[str, object] | None = field(default=None, repr=False)
    business_read_ticket: int = 0
    business_applied_ticket: int = 0
    business_diagnostic_context_id: str | None = None
    business_diagnostic_model: tuple[str, str] | None = None
    business_diagnostic_works: dict[str, tuple[object, object, object]] = field(default_factory=dict, repr=False)
    business_work_state_sequence: int = 0
    business_work_state_digest: bytes | None = field(default=None, repr=False)
    delegate_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict, repr=False)
    delegate_proposals: dict[str, NativeEngineEvent] = field(default_factory=dict, repr=False)
    foreground_turn_id: str | None = None
    failure_reason: str | None = None
    delivery_response: ResponseRef | None = None
    request_state_sequence: int = 0
    generated_text_revision: int = 0
    generated_text: OrderedDict[ResponseRef, dict[str, object]] = field(default_factory=OrderedDict, repr=False)
    next_media_sequence: int = 0
    next_media_sample_cursor: int = 0
    next_input_sequence: int = 0
    next_input_sample_cursor: int = 0
    request_ordinal: int = 0
    downlink_record_ids: dict[ResponseRef, str] = field(
        default_factory=dict, repr=False
    )
    barge_fenced_responses: OrderedDict[ResponseRef, None] = field(
        default_factory=OrderedDict, repr=False
    )
    projected_input_transcript_items: set[str] = field(default_factory=set, repr=False)
    projected_task_associations: set[str] = field(default_factory=set, repr=False)
    runtime_close_request_id: str | None = field(default=None, repr=False)
    runtime_close_complete: bool = False
    provider_close_complete: bool = False
    close_task: asyncio.Task[bool] | None = field(default=None, repr=False)
    closed: bool = False


@dataclass(frozen=True, slots=True)
class _NativePlayoutReplay:
    request_sha256: str
    receipt: dict[str, object] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _StreamingObservationContext:
    operation_id: str
    correlation_id: str
    response: ResponseRef
    started_monotonic: float


@dataclass(frozen=True, slots=True)
class _StreamingDiagnosticItem:
    owner: "_StreamingSynthesisDiagnosticOwner"
    context: _StreamingObservationContext
    outcome: StreamingSynthesisOutcome


class _StreamingSynthesisDiagnosticWorker:
    """One process-wide worker for all bounded product TTS diagnostics.

    Python cannot stop a thread whose configured sink blocks forever. Keeping
    one daemon worker process-wide prevents repeated WebChannel/registry
    lifetimes from creating an unbounded pool of abandoned workers.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[_StreamingDiagnosticItem] = queue.Queue(
            maxsize=_STREAMING_DIAGNOSTIC_QUEUE_CAPACITY
        )
        self._start_lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def submit(self, item: _StreamingDiagnosticItem) -> bool:
        self._ensure_started()
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            _LOGGER.warning(
                "live_voice_streaming_tts_diagnostic_dropped reason=QUEUE_SATURATED"
            )
            return False
        return True

    def _ensure_started(self) -> None:
        with self._start_lock:
            if self._worker is not None:
                return
            self._worker = threading.Thread(
                target=self._run,
                name="live-voice-streaming-tts-diagnostics",
                daemon=True,
            )
            self._worker.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            delivered = False
            drop_reason: str | None = None
            try:
                delivered = item.owner._deliver(item.context, item.outcome)
                if not delivered:
                    drop_reason = "OWNER_CLOSED_PENDING"
            except BaseException:
                drop_reason = "SINK_FAILED"
            finally:
                item.owner._complete_one(
                    delivered=delivered,
                    drop_reason=drop_reason,
                )
                self._queue.task_done()
                del item


_STREAMING_SYNTHESIS_DIAGNOSTIC_WORKER = _StreamingSynthesisDiagnosticWorker()


class _StreamingSynthesisDiagnosticOwner:
    """Closed lifecycle lease over the shared bounded diagnostic worker."""

    def __init__(
        self,
        deliver: Callable[
            [_StreamingObservationContext, StreamingSynthesisOutcome], None
        ],
    ) -> None:
        self._deliver_callback = deliver
        self._condition = threading.Condition()
        self._closed = False
        self._pending = 0
        self._accepted = 0
        self._delivered = 0
        self._dropped = 0

    def submit(
        self,
        context: _StreamingObservationContext,
        outcome: StreamingSynthesisOutcome,
    ) -> bool:
        with self._condition:
            if self._closed:
                _LOGGER.warning(
                    "live_voice_streaming_tts_diagnostic_dropped reason=OWNER_CLOSED"
                )
                return False
            self._pending += 1
            self._accepted += 1
        item = _StreamingDiagnosticItem(self, context, outcome)
        try:
            queued = _STREAMING_SYNTHESIS_DIAGNOSTIC_WORKER.submit(item)
        except BaseException:
            self._complete_one(
                delivered=False,
                drop_reason="WORKER_UNAVAILABLE",
            )
            return False
        if queued:
            return True
        # The process-wide worker already logged the bounded queue rejection.
        self._complete_one(delivered=False, drop_reason=None)
        return False

    def close(self) -> bool:
        deadline = time.monotonic() + _STREAMING_DIAGNOSTIC_CLOSE_BUDGET_SECONDS
        with self._condition:
            self._closed = True
            while self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _LOGGER.warning(
                        "live_voice_streaming_tts_diagnostic_cleanup_incomplete "
                        "reason=SINK_DID_NOT_STOP pending=%d",
                        self._pending,
                    )
                    return False
                self._condition.wait(timeout=remaining)
            return True

    @property
    def accounting(self) -> tuple[int, int, int, int]:
        """Return accepted, delivered, dropped, and still-pending counts."""

        with self._condition:
            return (
                self._accepted,
                self._delivered,
                self._dropped,
                self._pending,
            )

    def _deliver(
        self,
        context: _StreamingObservationContext,
        outcome: StreamingSynthesisOutcome,
    ) -> bool:
        with self._condition:
            if self._closed:
                return False
        self._deliver_callback(context, outcome)
        return True

    def _complete_one(
        self,
        *,
        delivered: bool,
        drop_reason: str | None,
    ) -> None:
        with self._condition:
            if delivered:
                self._delivered += 1
            else:
                self._dropped += 1
            if self._pending > 0:
                self._pending -= 1
            if self._pending == 0:
                self._condition.notify_all()
        if drop_reason is not None:
            _LOGGER.warning(
                "live_voice_streaming_tts_diagnostic_dropped reason=%s",
                drop_reason,
            )


class DedicatedMediaProductRegistry:
    """Bounded ticket registry and exact Speech authorization resolver."""

    def __init__(
        self,
        *,
        enabled: bool,
        monotonic: Callable[[], float] = time.monotonic,
        ticket_ttl_seconds: float = _DEFAULT_TICKET_TTL_SECONDS,
        authority_ttl_seconds: float = _DEFAULT_AUTHORITY_TTL_SECONDS,
        capacity: int = _MAX_RECORDS,
        end_of_turn_enabled: bool = False,
        streaming_observability: LiveVoiceObservabilityCollector | None = None,
        native_runtime_client: Any | None = None,
        native_engine_factory: (
            Callable[[Any], OpenAIRealtimeNativeInteractionEngine] | None
        ) = None,
        native_downlink_append_timeout_seconds: float = 3.0,
    ) -> None:
        self.enabled = enabled is True
        self._monotonic = monotonic
        self._task_preparations = task_preparation.TaskNotificationPreparationOwner(monotonic=monotonic)
        self._tts_opening: dict[tuple[str, str, str], set[object]] = {}
        self._ticket_ttl = ticket_ttl_seconds
        self._authority_ttl = authority_ttl_seconds
        self._capacity = max(1, min(capacity, _MAX_RECORDS))
        self.end_of_turn_enabled = end_of_turn_enabled is True
        self._native_runtime_client = native_runtime_client
        self._native_engine_factory = native_engine_factory
        self._native_downlink_append_timeout_seconds = (
            native_downlink_append_timeout_seconds
        )
        self._native_session_lock = asyncio.Lock()
        self._native_playout_lock = asyncio.Lock()
        self._native_cleanup_tasks: set[asyncio.Task[Any]] = set()
        self._native_sessions: dict[
            tuple[str, str, str, str, int], _NativeMediaSession
        ] = {}
        self._native_pending_starts: dict[
            tuple[str, str, str, str, int], _NativeMediaSession
        ] = {}
        self._native_close_capacity_reservations: set[
            tuple[str, str, str, str, int]
        ] = set()
        self._native_session_keys_by_record: dict[
            str, tuple[str, str, str, str, int]
        ] = {}
        self._native_notifications: dict[
            tuple[str, str, str], asyncio.Queue[dict[str, object]]
        ] = {}
        self._native_playout_replays: OrderedDict[
            tuple[tuple[str, str, str, str, int], ResponseRef, str],
            _NativePlayoutReplay,
        ] = OrderedDict()
        self._records: OrderedDict[str, _MediaAuthority] = OrderedDict()
        # One-use credentials exist only in this pre-authentication index.  All
        # durable authority references use an unrelated internal record id.
        self._pending_tickets: OrderedDict[str, str] = OrderedDict()
        self._subjects: dict[tuple[str, str], str] = {}
        self._product_activations: OrderedDict[
            tuple[str, str, str], _ProductActivationAuthority
        ] = OrderedDict()
        self._revoked: OrderedDict[str, tuple[str, str, str, str, int, str]] = (
            OrderedDict()
        )
        self._lock = threading.RLock()
        self._batch_provider_available = False
        self._streaming_provider_available = False
        self._streaming_selection_degradation: dict[str, object] | None = None
        self._streaming_recognition_owner: StreamingRecognitionRouteOwner | None = None
        self._streaming_receipt_issuer: Callable[..., Awaitable[str]] | None = None
        self._streaming_cleanup_tasks: set[asyncio.Task[None]] = set()
        if streaming_observability is not None and not isinstance(
            streaming_observability, LiveVoiceObservabilityCollector
        ):
            raise TypeError("streaming observability collector is invalid")
        self._streaming_observability = streaming_observability
        self._streaming_observability_owner = (
            _StreamingObservabilityOwner(
                streaming_observability,
                capacity=_STREAMING_OBSERVABILITY_QUEUE_CAPACITY,
            )
            if streaming_observability is not None
            else None
        )
        self._streaming_synthesis_owner: StreamingSynthesisRouteOwner | None = None
        self._streaming_synthesis_observability: (
            LiveVoiceObservabilityCollector | None
        ) = None
        self._stream_cleanup_tasks: set[asyncio.Task[None]] = set()
        self._media_leaf_cleanup_owner = DedicatedMediaLeafCleanupOwner(
            capacity=max(2, self._capacity * 2)
        )
        self._streaming_diagnostic_owner: _StreamingSynthesisDiagnosticOwner | None = (
            None
        )
        self._streaming_diagnostics_cleanup_complete: bool | None = None

    @classmethod
    def from_environment(
        cls,
        *,
        native_runtime_client: Any | None = None,
        native_engine_factory: (
            Callable[[Any], OpenAIRealtimeNativeInteractionEngine] | None
        ) = None,
    ) -> "DedicatedMediaProductRegistry":
        enabled = _enabled(os.getenv(MEDIA_FEATURE_ENV))
        return cls(
            enabled=enabled,
            end_of_turn_enabled=(
                enabled and _enabled(os.getenv(MEDIA_END_OF_TURN_FEATURE_ENV))
            ),
            streaming_observability=(
                LiveVoiceObservabilityCollector() if enabled else None
            ),
            native_runtime_client=native_runtime_client,
            native_engine_factory=native_engine_factory,
        )

    @property
    def native_runtime_client(self) -> Any | None:
        """Return the process-private Native carrier owner, if selected."""

        return self._native_runtime_client

    def abort_native_activation(self, activation: GatewayNativeActivation) -> bool:
        """Remove one exact partially observed Native media authority."""

        if not isinstance(activation, GatewayNativeActivation):
            return False
        binding = activation.binding
        key = (
            binding.scope.session_id or "",
            activation.connection_id,
            binding.interaction_id,
        )
        with self._lock:
            authority = self._product_activations.get(key)
            if authority is None or (
                authority.correlation_id,
                authority.activation_id,
                authority.activation_generation,
            ) != (
                binding.correlation_id,
                binding.activation_id,
                binding.activation_generation,
            ):
                return False
            self._product_activations.pop(key, None)
            self._revoke_media_for_product_activation(authority)
            return True

    async def begin_native_interaction(self, record: _MediaAuthority) -> bool:
        """Start the one Gateway-owned Provider session for an exact uplink."""

        activation = record.native_activation
        if (
            not isinstance(activation, GatewayNativeActivation)
            or record.binding.direction is not MediaDirection.UPLINK
            or not record.ticket_consumed
            or record.route_completed
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_ACTIVATION_UNAVAILABLE",
                "Native Provider start requires one consumed exact uplink",
            )
        factory = self._native_engine_factory
        if not callable(factory):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_PROVIDER_UNAVAILABLE",
                "Native Provider factory is unavailable",
            )
        key = self._native_session_key(record)
        async with self._native_session_lock:
            self._require_native_start_owner(record)
            prior = self._native_sessions.get(key) or self._native_pending_starts.get(key)
            if prior is not None:
                if prior.record_id == record.record_id and not prior.closed:
                    session = prior
                    created = False
                else:
                    raise MediaTransportViolation(
                        "MEDIA_NATIVE_SESSION_ALREADY_ACTIVE",
                        "Native activation already owns one Provider session",
                    )
            else:
                session = self._retain_native_start(record, activation, factory)
                created = True
        task = session.start_task
        try:
            if task is not None:
                await asyncio.shield(task)
            self._require_native_start_owner(record, session, allow_started=True)
        except BaseException as error:
            self._schedule_native_close(record)
            with suppress(BaseException):
                await self.close_native_interaction(record)
            if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                raise
            raise MediaTransportViolation(
                "MEDIA_NATIVE_PROVIDER_START_FAILED",
                "Native Provider session did not start",
            ) from error
        return created

    def _require_native_start_owner(
        self,
        record: _MediaAuthority | None,
        session: _NativeMediaSession | None = None,
        *,
        allow_started: bool = False,
    ) -> None:
        """Recheck retained authority after every bootstrap suspension."""

        with self._lock:
            now = self._monotonic()
            current = bool(
                record is not None
                and self._records.get(record.record_id) is record
                and self._subjects.get((record.binding.session_id, record.subject_id))
                == record.record_id
                and record.ticket_consumed
                and not record.route_completed
                and now <= record.authority_expires_at
                and self._has_retained_product_activation(record, now)
            )
            if current and session is not None:
                current = bool(
                    not session.closed
                    and record is session.start_record
                    and record.native_activation is session.activation
                    and self._native_session_key(record) == session.key
                    and self._native_session_keys_by_record.get(record.record_id)
                    == session.key
                    and (
                        self._native_pending_starts.get(session.key) is session
                        or (allow_started and self._native_sessions.get(session.key) is session)
                    )
                )
            if not current:
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_ACTIVATION_UNAVAILABLE",
                    "Native startup no longer owns the exact media authority",
                )

    def _retain_native_start(self, record, activation, factory) -> _NativeMediaSession:
        """Reserve one exact pending owner before starting any async operation."""

        key = self._native_session_key(record)
        engine = factory(activation.binding)
        if engine is None or not all(
            callable(getattr(engine, method, None))
            for method in (
                "start", "offer_audio", "next_event", "admit_response",
                "acknowledge_presentation", "cancel_response", "fence_response",
                "stop_foreground", "send_delegate_result", "close",
            )
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_PROVIDER_UNAVAILABLE",
                "Native Provider factory returned no exact Engine",
            )
        session = _NativeMediaSession(
            key=key, record_id=record.record_id, activation=activation, engine=engine,
            start_record=record,
            input_queue=asyncio.Queue(maxsize=_NATIVE_INPUT_QUEUE_CAPACITY),
            speech_start_queue=asyncio.Queue(maxsize=_NATIVE_SPEECH_START_QUEUE_CAPACITY),
            end_of_turn_queue=asyncio.Queue(maxsize=_NATIVE_END_OF_TURN_QUEUE_CAPACITY),
            delivery_queue=asyncio.Queue(maxsize=_NATIVE_PROVIDER_EVENT_QUEUE_CAPACITY),
        )
        self._native_pending_starts[key] = session
        self._native_session_keys_by_record[record.record_id] = key
        session.start_task = asyncio.create_task(
            self._run_native_session_start(record, session),
            name=f"live-voice-native-start:{record.record_id}",
        )
        # The caller can be cancelled while an external operation ignores its
        # cancellation. Retain and consume that task until it actually settles.
        session.start_task.add_done_callback(
            lambda done: None if done.cancelled() else done.exception()
        )
        return session

    async def _run_native_session_start(self, record, session) -> None:
        activation, engine = session.activation, session.engine
        self._require_native_start_owner(record, session)
        business_initial = None
        if activation.business_contract_version is not None:
            if not all(callable(getattr(engine, method, None)) for method in (
                "configure_business_context", "update_business_context", "acknowledge_business_turn",
                "acknowledge_business_stop", "defer_work_response",
            )) or not callable(getattr(self._native_runtime_client, "business_context", None)):
                raise MediaTransportViolation("MEDIA_NATIVE_BUSINESS_UNAVAILABLE", "Negotiated business context is unavailable")
            async def refresh_business_context():
                return await self._refresh_native_business_context(session)
            business_initial = await refresh_business_context()
            self._require_native_start_owner(record, session)
            self._native_work_state_rows(business_initial["context"]["works"])
            optimized = getattr(activation, "observation_contract_version", None) is not None
            engine.configure_business_context(business_initial["context"], refresh=refresh_business_context,
                presentation_busy=lambda: self._native_task_presentation_busy(session),
                **({"continuation_preparation": True, "receipt_projection": True} if optimized else {}))
        await engine.start()
        self._require_native_start_owner(record, session)
        if business_initial is not None:
            await engine.update_business_context(business_initial["context"], business_initial["work_events"])
            self._require_native_start_owner(record, session)
        # Promotion and consumers have no suspension between the final authority
        # check and publication. Pending owners cannot consume or publish media.
        with self._lock:
            self._require_native_start_owner(record, session)
            self._native_pending_starts.pop(session.key)
            self._native_sessions[session.key] = session
            notification_key = (
                record.binding.session_id, record.binding.interaction_id,
                record.binding.connection_id,
            )
            self._native_notifications.setdefault(
                notification_key, asyncio.Queue(maxsize=_NATIVE_NOTIFICATION_QUEUE_CAPACITY),
            )
            if business_initial is not None:
                self._profile_native_business_context(session, business_initial)
                self._publish_native_work_state(session, business_initial)
            session.input_task = asyncio.create_task(
                self._run_native_input(session), name="live-voice-native-media-input",
            )
            session.delivery_task = asyncio.create_task(
                self._run_native_delivery(session), name="live-voice-native-media-delivery",
            )
            session.event_task = asyncio.create_task(
                self._run_native_events(session), name="live-voice-native-media-events",
            )
            if activation.business_contract_version is not None:
                session.business_poll_task = asyncio.create_task(
                    self._run_native_business_poll(session), name="live-voice-native-business-context")
            for task in (session.input_task, session.event_task, session.delivery_task, session.business_poll_task):
                if task is not None:
                    task.add_done_callback(
                        lambda retained, owner=record: self._consume_native_task(owner, retained)
                    )

    def accept_native_frame(
        self, record: _MediaAuthority, frame: MediaAudioFrame
    ) -> None:
        """Queue one already media-validated frame for the exact Native Engine."""

        key = self._native_session_keys_by_record.get(record.record_id)
        session = self._native_sessions.get(key) if key is not None else None
        fence_detail: str | None = None
        if session is None:
            fence_detail = "session_missing"
        elif session.closed:
            fence_detail = "session_closed"
        elif session.record_id != record.record_id:
            fence_detail = "record_mismatch"
        elif record.route_completed:
            fence_detail = "route_completed"
        elif frame.seq != session.next_media_sequence:
            fence_detail = (
                "sequence_mismatch"
                f":incoming={frame.seq}:expected={session.next_media_sequence}"
            )
        elif frame.sample_cursor != session.next_media_sample_cursor:
            fence_detail = (
                "cursor_mismatch"
                f":incoming={frame.sample_cursor}"
                f":expected={session.next_media_sample_cursor}"
            )
        elif len(frame.samples) != record.binding.frame_format.samples_per_channel:
            fence_detail = (
                "frame_size_mismatch"
                f":incoming={len(frame.samples)}"
                f":expected={record.binding.frame_format.samples_per_channel}"
            )
        if fence_detail is not None:
            if record.native_transport_failure and fence_detail in {"session_missing", "session_closed", "route_completed"}:
                raise MediaTransportViolation(
                    MediaDetachReason.NATIVE_PROVIDER_TRANSPORT_FAILED.value,
                    "The exact Native Provider transport failed",
                )
            raise MediaTransportViolation(
                "MEDIA_NATIVE_INPUT_FENCE_REJECTED",
                "Native input frame does not match the exact open uplink cursor "
                f"({fence_detail})",
            )
        provider_samples = _resample_native_frame(
            frame.samples, output_samples=NATIVE_PCM_SAMPLE_RATE // 50
        )
        native_frame = NativeInputAudioFrame(
            seq=session.next_input_sequence,
            sample_cursor=session.next_input_sample_cursor,
            pcm16=_pcm16(provider_samples),
        )
        try:
            session.input_queue.put_nowait(native_frame)
        except asyncio.QueueFull:
            session.failure_reason = "MEDIA_NATIVE_INPUT_BACKPRESSURE"
            record.native_transport_failure = True
            profile_event("native_media_failure", **identity_fields(session.activation.binding),
                stage="media.input", reason=session.failure_reason,
                queue_frames=session.input_queue.qsize(),
                pending_audio_ms=session.input_queue.qsize() * 20, outcome="failed")
            self._schedule_native_close(record)
            raise MediaTransportViolation(
                MediaDetachReason.NATIVE_PROVIDER_TRANSPORT_FAILED.value,
                "Native input queue is saturated",
            ) from None
        session.input_enqueued_at[native_frame.seq] = self._monotonic()
        session.next_media_sequence += 1
        session.next_media_sample_cursor += len(frame.samples)
        session.next_input_sequence += 1
        session.next_input_sample_cursor += len(provider_samples)
        record.accepted_frames += 1

    async def wait_native_speech_start(
        self, record: _MediaAuthority
    ) -> MediaSpeechStart:
        """Return the next Runtime-admitted Native Provider speech boundary."""

        key = self._native_session_keys_by_record.get(record.record_id)
        session = self._native_sessions.get(key) if key is not None else None
        if (
            session is None
            or session.closed
            or session.record_id != record.record_id
            or record.route_completed
        ):
            raise RuntimeError("Native speech-start route is unavailable")
        provider_start_ms = await session.speech_start_queue.get()
        session.speech_start_queue.task_done()
        current = self._native_sessions.get(key)
        if (
            current is not session
            or session.closed
            or record.route_completed
            or self._records.get(record.record_id) is not record
        ):
            raise RuntimeError("Native speech-start authority became stale")
        return MediaSpeechStart(
            lease_id=record.binding.lease_id,
            generation=record.binding.generation.value,
            provider_start_ms=provider_start_ms,
        )

    async def wait_native_end_of_turn(self, record: _MediaAuthority) -> MediaEndOfTurn:
        """Return the next Runtime-admitted Native Provider turn boundary."""

        key = self._native_session_keys_by_record.get(record.record_id)
        session = self._native_sessions.get(key) if key is not None else None
        if (
            session is None
            or session.closed
            or session.record_id != record.record_id
            or record.route_completed
        ):
            raise RuntimeError("Native end-of-turn route is unavailable")
        provider_start_ms, provider_end_ms = await session.end_of_turn_queue.get()
        session.end_of_turn_queue.task_done()
        current = self._native_sessions.get(key)
        if (
            current is not session
            or session.closed
            or record.route_completed
            or self._records.get(record.record_id) is not record
        ):
            raise RuntimeError("Native end-of-turn authority became stale")
        return MediaEndOfTurn(
            lease_id=record.binding.lease_id,
            generation=record.binding.generation.value,
            provider_start_ms=provider_start_ms,
            provider_end_ms=provider_end_ms,
        )

    async def next_native_notification(
        self,
        *,
        session_id: str,
        interaction_id: str,
        connection_id: str,
    ) -> dict[str, object]:
        key = (
            _required_id(session_id, "session_id"),
            _required_id(interaction_id, "interaction_id"),
            _required_id(connection_id, "connection_id"),
        )
        queue_owner = self._native_notifications.get(key)
        if queue_owner is None:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_NOTIFICATION_UNAVAILABLE",
                "Native notification route is not active",
            )
        return await queue_owner.get()

    def take_native_notification(
        self,
        *,
        session_id: str,
        interaction_id: str,
        connection_id: str,
    ) -> dict[str, object] | None:
        try:
            key = (
                _required_id(session_id, "session_id"),
                _required_id(interaction_id, "interaction_id"),
                _required_id(connection_id, "connection_id"),
            )
        except MediaTransportViolation:
            return None
        queue_owner = self._native_notifications.get(key)
        if queue_owner is None:
            return None
        try:
            return queue_owner.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def take_native_notification_response(
        self,
        *,
        request_id: str,
        session_id: str,
        correlation_id: str,
        interaction_id: str,
        activation_id: str,
        activation_generation: int,
        connection_id: str,
        notification_sequence: int,
    ) -> dict[str, object] | None:
        parsed_request_id = _required_id(request_id, "request_id")
        parsed_session_id = _required_id(session_id, "session_id")
        parsed_correlation_id = _required_id(correlation_id, "correlation_id")
        parsed_interaction_id = _required_id(interaction_id, "interaction_id")
        parsed_activation_id = _required_id(activation_id, "activation_id")
        parsed_activation_generation = _safe_uint(
            activation_generation, "activation_generation"
        )
        parsed_connection_id = _required_id(connection_id, "connection_id")
        parsed_notification_sequence = _safe_uint(
            notification_sequence, "notification_sequence"
        )
        if parsed_notification_sequence == 0:
            raise MediaTransportViolation(
                "MEDIA_INVALID_ACTIVATION", "notification_sequence is invalid"
            )
        with self._lock:
            authority = self._product_activations.get(
                (parsed_session_id, parsed_connection_id, parsed_interaction_id)
            )
            if (
                authority is None
                or self._monotonic() > authority.expires_at
                or authority.correlation_id != parsed_correlation_id
                or authority.activation_id != parsed_activation_id
                or authority.activation_generation != parsed_activation_generation
            ):
                return None
            fence = authority.notification_fence
            if fence.local_request_id == parsed_request_id:
                if (
                    fence.local_sequence != parsed_notification_sequence
                    or fence.local_response is None
                ):
                    return None
                return json.loads(
                    canonical_json_bytes(fence.local_response).decode("utf-8")
                )
            # A request already forwarded to AgentServer remains owned by that
            # authority on retry.  A newly queued local frame must not steal it.
            if fence.forwarded_request_id == parsed_request_id:
                return None
            fence.local_request_id = None
            fence.local_sequence = None
            fence.local_response = None
            # Gateway-local projections never consume AgentServer's committed
            # cursor.  The Browser therefore keeps using the still-next
            # candidate until an AgentServer response explicitly consumes it.
            expected_agent_sequence = fence.agent_high_water + 1
            if parsed_notification_sequence != expected_agent_sequence:
                return None
            notification = fence.terminal_notification
            if notification is not None:
                fence.terminal_notification = None
            else:
                queue_owner = self._native_notifications.get(
                    (parsed_session_id, parsed_interaction_id, parsed_connection_id)
                )
                if queue_owner is None:
                    return None
                try:
                    notification = queue_owner.get_nowait()
                except asyncio.QueueEmpty:
                    return None
            manifest = json.loads(
                canonical_json_bytes(authority.product_composition).decode("utf-8")
            )
            projected = dict(notification)
            projected["request_id"] = parsed_request_id
            projected["sequence_effect"] = "neutral"
            response = {
                "request_id": parsed_request_id,
                "ok": True,
                "result": projected,
                "error": None,
                "product_composition": manifest,
            }
            fence.local_request_id = parsed_request_id
            fence.local_sequence = parsed_notification_sequence
            fence.local_response = json.loads(
                canonical_json_bytes(response).decode("utf-8")
            )
            return response

    def mark_native_notification_forwarded(
        self,
        *,
        request_id: str,
        session_id: str,
        correlation_id: str,
        interaction_id: str,
        activation_id: str,
        activation_generation: int,
        connection_id: str,
        notification_sequence: int,
    ) -> bool:
        """Fence one unchanged Browser candidate before AgentServer forwarding."""

        parsed_request_id = _required_id(request_id, "request_id")
        parsed_session_id = _required_id(session_id, "session_id")
        parsed_correlation_id = _required_id(correlation_id, "correlation_id")
        parsed_interaction_id = _required_id(interaction_id, "interaction_id")
        parsed_activation_id = _required_id(activation_id, "activation_id")
        parsed_activation_generation = _safe_uint(
            activation_generation, "activation_generation"
        )
        parsed_connection_id = _required_id(connection_id, "connection_id")
        parsed_notification_sequence = _safe_uint(
            notification_sequence, "notification_sequence"
        )
        if parsed_notification_sequence == 0:
            return False
        with self._lock:
            authority = self._product_activations.get(
                (parsed_session_id, parsed_connection_id, parsed_interaction_id)
            )
            if (
                authority is None
                or self._monotonic() > authority.expires_at
                or authority.correlation_id != parsed_correlation_id
                or authority.activation_id != parsed_activation_id
                or authority.activation_generation != parsed_activation_generation
            ):
                return False
            fence = authority.notification_fence
            if fence.local_request_id != parsed_request_id:
                fence.local_request_id = None
                fence.local_sequence = None
                fence.local_response = None
            if fence.forwarded_request_id == parsed_request_id:
                if (
                    fence.forwarded_client_sequence != parsed_notification_sequence
                    or fence.forwarded_agent_sequence is None
                ):
                    return False
                return True
            fence.forwarded_request_id = None
            fence.forwarded_client_sequence = None
            fence.forwarded_agent_sequence = None
            if parsed_notification_sequence <= fence.agent_high_water:
                return True
            expected_agent_sequence = fence.agent_high_water + 1
            if parsed_notification_sequence != expected_agent_sequence:
                # AgentServer remains the strict sequence authority.  Forward
                # the unchanged candidate so it can return its exact cursor;
                # do not poison later local projections for this activation.
                return False
            fence.forwarded_request_id = parsed_request_id
            fence.forwarded_client_sequence = parsed_notification_sequence
            fence.forwarded_agent_sequence = parsed_notification_sequence
            fence.agent_high_water = parsed_notification_sequence
            return True

    async def close_native_interaction(self, record: _MediaAuthority) -> bool:
        key = self._native_session_keys_by_record.get(record.record_id)
        if key is None:
            return False
        async with self._native_session_lock:
            session = self._native_sessions.get(key) or self._native_pending_starts.get(key)
            if session is None or session.record_id != record.record_id:
                return False
            self._fence_native_start(session)
            task = session.close_task
            if task is None or task.done():
                if session.failure_reason in _NATIVE_PROVIDER_TRANSPORT_FAILURES:
                    parent = self._records.get(session.record_id)
                    if parent is not None:
                        parent.native_transport_failure = True
                session.closed = True
                self._reconcile_task_preparations()
                task = asyncio.create_task(
                    self._run_native_session_close(record, session),
                    name=f"live-voice-native-close:{record.record_id}",
                )
                session.close_task = task
                self._native_cleanup_tasks.add(task)
                task.add_done_callback(self._native_cleanup_tasks.discard)
                task.add_done_callback(
                    lambda done: None if done.cancelled() else done.exception()
                )
        if session.startup_retired:
            # A cancellation-resistant bootstrap retains one cleanup owner and
            # its capacity. It cannot hold the close caller or the registry lock.
            done, _ = await asyncio.wait({task}, timeout=_NATIVE_STARTUP_CLOSE_WAIT_SECONDS)
            return task.result() if task in done else False
        return await asyncio.shield(task)

    def _fence_native_start(self, session: _NativeMediaSession) -> None:
        if self._native_pending_starts.get(session.key) is not session:
            return
        session.startup_retired = True
        self._native_close_capacity_reservations.add(session.key)
        if session.closed:
            return
        session.closed = True
        for task in (session.start_task, session.business_refresh_task):
            if task is not None and not task.done():
                task.cancel()

    async def _run_native_session_close(
        self,
        record: _MediaAuthority,
        session: _NativeMediaSession,
    ) -> bool:
        key = session.key
        if session.failure_reason in _NATIVE_PROVIDER_TRANSPORT_FAILURES:
            record.native_transport_failure = True
            for candidate in tuple(self._records.values()):
                if candidate.native_session_key != key:
                    continue
                candidate.native_transport_failure = True
                source = candidate.downlink_stream_source
                if isinstance(source, NativeResponseDownlinkSource):
                    await source.fail_provider_transport(source.response)
        notification_key = (
            session.activation.binding.scope.session_id or "",
            session.activation.binding.interaction_id,
            session.activation.connection_id,
        )
        with self._lock:
            self._native_close_capacity_reservations.add(key)
            record.route_completed = True
            record.recognition_content_sha256 = None
            record.synthesis_content_sha256.clear()
            record.playout_receipts.clear()
            record.playout_receipt_content_sha256.clear()
            record.downlink_results.clear()
            record.downlink_frames = ()
            self._release_stream_source(record)
            record.downlink_overlap_record_id = None
            record.pcm.clear()
            for replay_key in tuple(self._native_playout_replays):
                if replay_key[0] == key:
                    self._native_playout_replays.pop(replay_key, None)
            for record_id, candidate in tuple(self._records.items()):
                if candidate.native_session_key != key:
                    continue
                self._records.pop(record_id, None)
                self._drop_pending_for_record_id(record_id)
                candidate.route_completed = True
                candidate.recognition_content_sha256 = None
                candidate.synthesis_content_sha256.clear()
                candidate.playout_receipts.clear()
                candidate.playout_receipt_content_sha256.clear()
                candidate.downlink_results.clear()
                candidate.downlink_frames = ()
                self._release_stream_source(candidate)
                candidate.downlink_overlap_record_id = None
                candidate.pcm.clear()
            # A pending owner never published this queue. A newer activation
            # sharing the interaction may have created it while old start drains.
            if not session.startup_retired:
                self._native_notifications.pop(notification_key, None)
        if session.startup_retired:
            startup_tasks = tuple(
                task for task in (session.start_task, session.business_refresh_task)
                if task is not None
            )
            # Do not run Engine.close concurrently with start: an implementation
            # can swallow cancellation and still write READY before returning.
            if startup_tasks:
                await asyncio.gather(*startup_tasks, return_exceptions=True)
        current = asyncio.current_task()
        tasks = tuple(
            task
            for task in (
                session.input_task,
                session.event_task,
                session.delivery_task,
                session.business_poll_task,
                session.business_refresh_task,
                *session.notification_wake_tasks,
                *session.delegate_tasks.values(),
            )
            if task is not None and task is not current
        )
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for queue_owner in (
            session.input_queue,
            session.speech_start_queue,
            session.end_of_turn_queue,
            session.delivery_queue,
        ):
            while True:
                try:
                    queue_owner.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    queue_owner.task_done()
        session.input_enqueued_at.clear()
        client = self._native_runtime_client
        close_runtime = getattr(client, "close", None)
        if callable(close_runtime):
            if session.runtime_close_request_id is None:
                session.runtime_close_request_id = self._native_request_id(
                    session, "close"
                )
            try:
                await close_runtime(
                    binding=session.activation.binding,
                    capability=session.activation.capability,
                    request_id=session.runtime_close_request_id,
                )
            except BaseException:
                pass
            else:
                session.runtime_close_complete = True
        if not session.provider_close_complete:
            session.provider_close_complete = await session.engine.close() is True
        if not (session.runtime_close_complete and session.provider_close_complete):
            return False
        async with self._native_session_lock:
            with self._lock:
                if self._native_sessions.get(key) is session:
                    self._native_sessions.pop(key, None)
                if self._native_pending_starts.get(key) is session:
                    self._native_pending_starts.pop(key, None)
                if self._native_session_keys_by_record.get(record.record_id) == key:
                    self._native_session_keys_by_record.pop(record.record_id, None)
                self._native_close_capacity_reservations.discard(key)
        return True

    async def _run_native_business_poll(self, session: _NativeMediaSession) -> None:
        while not session.closed:
            try:
                if getattr(session.activation, "observation_contract_version", None) is not None:
                    result = await self._read_native_business_context(session, wait_ms=1000)
                else:
                    await asyncio.sleep(_NATIVE_BUSINESS_POLL_SECONDS)
                    result = await self._refresh_native_business_context(session)
            except NativeRuntimeClientError as error:
                if session.closed:
                    return  # Revocation settled this exact observer's lifetime.
                if error.reason != "NATIVE_RUNTIME_TIMEOUT":
                    raise
                # An observation performs no business effect. Keep the last
                # cursor and retry; never apply stale facts or close healthy
                # media because this independent read exceeded its deadline.
                record_audio_diagnostic("native_business_observation_retry",
                    reason=error.reason, session_id=session.activation.binding.scope.session_id)
                await asyncio.sleep(_NATIVE_BUSINESS_POLL_SECONDS)
                continue
            except MediaTransportViolation:
                if session.closed:
                    return
                raise
            if session.closed:
                return
            stops = await session.engine.update_business_context(result["context"], result["work_events"])
            for event in stops:
                await self._handle_native_event(session, event)

    async def _refresh_native_business_context(self, session: _NativeMediaSession):
        while True:
            if session.closed:
                raise MediaTransportViolation("MEDIA_NATIVE_SESSION_CLOSED", "Business context route is closed")
            task = session.business_refresh_task
            if task is None:
                task = asyncio.create_task(self._read_native_business_context(session, wait_ms=0))
                session.business_refresh_task = task
                session.business_refresh_epoch = session.business_receipt_epoch
                def finished(done):
                    if session.business_refresh_task is done:
                        session.business_refresh_task = None
                    if not done.cancelled():
                        done.exception()
                task.add_done_callback(finished)
            epoch = session.business_refresh_epoch
            await asyncio.shield(task)
            if session.closed:
                raise MediaTransportViolation("MEDIA_NATIVE_SESSION_CLOSED", "Business context owner closed during refresh")
            if epoch == session.business_receipt_epoch:
                break
            # A shared RPC started before an admitted receipt cannot certify
            # its effects. Coalesce one new read after that receipt, retaining
            # cancellation ownership and cursor ordering of both reads.
        # The shared read can finish before this waiter resumes. An intervening
        # observation may already have advanced the cursor-ordered cache.
        if session.business_context_result is None:
            raise MediaTransportViolation("MEDIA_NATIVE_OBSERVATION_UNAVAILABLE", "Business context refresh produced no snapshot")
        return session.business_context_result

    async def _read_native_business_context(self, session: _NativeMediaSession, *, wait_ms: int):
        if session.closed:
            raise MediaTransportViolation("MEDIA_NATIVE_SESSION_CLOSED", "Business context route is closed")
        session.business_read_ticket += 1
        ticket = session.business_read_ticket
        observer = getattr(self._native_runtime_client, "observe_business_context", None)
        if getattr(session.activation, "observation_contract_version", None) is not None:
            if not callable(observer):
                raise MediaTransportViolation("MEDIA_NATIVE_OBSERVATION_UNAVAILABLE", "Negotiated observer is unavailable")
            result = await observer(session.activation, request_id=self._native_request_id(session, "business-observation"),
                after=session.business_observation_cursor if wait_ms else None, wait_ms=wait_ms)
        else:
            result = await self._native_runtime_client.business_context(session.activation,
                request_id=self._native_request_id(session, "business-context"))
        if session.closed:
            raise MediaTransportViolation("MEDIA_NATIVE_SESSION_CLOSED", "Business context owner closed during observation")
        if self._native_pending_starts.get(session.key) is session:
            self._require_native_start_owner(session.start_record, session)
        cursor = result.get("cursor")
        prior = session.business_observation_cursor
        stale = False
        if cursor is not None and prior is not None:
            stale = ((cursor["read_sequence"], cursor["sequence"]) < (prior["read_sequence"], prior["sequence"])
                     if cursor["epoch"] == prior["epoch"]
                     else ticket < session.business_applied_ticket)
        elif cursor is None:
            stale = ticket < session.business_applied_ticket
        if stale and session.business_context_result is not None:
            return session.business_context_result
        session.business_applied_ticket = max(ticket, session.business_applied_ticket)
        session.business_observation_cursor = cursor
        session.business_context_result = result
        if self._native_sessions.get(session.key) is session:
            self._profile_native_business_context(session, result)
            self._publish_native_work_state(session, result)
        return result

    def _native_task_presentation_busy(self, session: _NativeMediaSession) -> bool:
        """Read the existing Task synthesis handoff and media playout ownership."""
        with self._lock:
            parent = self._records.get(session.record_id)
            if parent is None or session.closed:
                return True
            activation = self._product_activations.get((parent.binding.session_id,
                parent.binding.connection_id, parent.binding.interaction_id))
            if activation is None:
                return True
            now = self._monotonic()
            return any(transfer.task_notification and not transfer.presentation_retired and now <= transfer.expires_at
                and (response, unit_id) in parent.synthesis_content_sha256
                and (response, unit_id) not in parent.playout_receipts
                for (response, unit_id, _locale, _rate), transfer in activation.synthesis_content_sha256.items())

    @staticmethod
    def _native_work_state_rows(raw: object) -> list[dict[str, object]]:
        if type(raw) is not list or len(raw) > 32:
            raise MediaTransportViolation("MEDIA_NATIVE_WORK_STATE_INVALID", "Work state collection is not bounded")
        works = []
        for row in raw:
            if (not isinstance(row, Mapping) or not {"work_id", "revision", "sequence", "state", "execution_settled"}.issubset(row)
                    or type(row["work_id"]) is not str or not row["work_id"]
                    or row["work_id"] != row["work_id"].strip()
                    or len(row["work_id"].encode("utf-8", errors="replace")) > 256
                    or type(row["revision"]) is not int or not 0 < row["revision"] <= 2**53 - 1
                    or type(row["sequence"]) is not int or not 0 < row["sequence"] <= 2**53 - 1
                    or type(row["state"]) is not str or row["state"] not in {
                        "accepted", "running", "cancelling", "completed", "cancelled", "superseded", "failed", "unknown"}
                    or type(row["execution_settled"]) is not bool):
                raise MediaTransportViolation("MEDIA_NATIVE_WORK_STATE_INVALID", "Work state row is invalid")
            _required_id(row["work_id"], "work_id")
            works.append({key: row[key] for key in ("work_id", "revision", "sequence", "state", "execution_settled")})
        if len({row["work_id"] for row in works}) != len(works):
            raise MediaTransportViolation("MEDIA_NATIVE_WORK_STATE_INVALID", "Work identities are not unique")
        return works

    def _publish_native_work_state(self, session: _NativeMediaSession, result: Mapping[str, object]) -> None:
        """Project only the accepted work lifecycle; no text/audio/history effects."""
        if session.activation.business_contract_version is None:
            return
        with self._lock:
            parent = self._records.get(session.record_id)
            if (session.closed or self._native_sessions.get(session.key) is not session or parent is None
                    or parent.route_completed or parent.native_activation != session.activation
                    or not self._has_retained_product_activation(parent, self._monotonic())):
                return
            works = self._native_work_state_rows(result["context"]["works"])
            digest = hashlib.sha256(canonical_json_bytes(works)).digest()
            if digest == session.business_work_state_digest:
                return
            notifications = self._native_notifications.get((parent.binding.session_id,
                parent.binding.interaction_id, parent.binding.connection_id))
            authority = self._product_activations[(parent.binding.session_id,
                parent.binding.connection_id, parent.binding.interaction_id)]
            fence = authority.notification_fence
            if notifications is None or notifications.full() or fence.native_work_state_sequence >= 2**53 - 1:
                raise MediaTransportViolation("MEDIA_NATIVE_NOTIFICATION_BACKPRESSURE", "Work state notification unavailable")
            sequence = fence.native_work_state_sequence + 1
            notifications.put_nowait({
                "status": "notification", "kind": "native.work_state", "sequence_effect": "neutral",
                "request_id": self._native_request_id(session, "work-state"),
                "work_state": {"contract_version": "live-voice.native-work-state.v1", "sequence": sequence, "works": works},
                "round_id": None, "response": None, "agent_event": None, "source_event": None,
                "progress_event": None, "presentation_unit": None, "audio": None, "error_reason": None, "publish_seq": None,
                "session_id": parent.binding.session_id, "correlation_id": parent.binding.correlation_id,
                "interaction_id": parent.binding.interaction_id, "activation_id": parent.product_activation_id,
                "activation_generation": parent.product_activation_generation,
            })
            session.business_work_state_sequence = sequence
            fence.native_work_state_sequence = sequence
            session.business_work_state_digest = digest

    @staticmethod
    def _profile_native_business_context(session: _NativeMediaSession, result: Mapping[str, object]) -> None:
        context = result["context"]
        fields = identity_fields(session.activation.binding)
        if context["context_id"] != session.business_diagnostic_context_id:
            session.business_diagnostic_context_id = context["context_id"]
            profile_event("native_context_selected", **fields, context_id=context["context_id"], status="current")
        model = context["model"]
        selection = (model["model_identity"], model["model_config_version"])
        if selection != session.business_diagnostic_model:
            session.business_diagnostic_model = selection
            profile_event("native_model_confirmed", **fields, model_id=selection[0], model_config_version=selection[1], status="confirmed")
        retained = {}
        for work in context["works"]:
            state = (work["revision"], work["state"], work["sequence"])
            retained[work["work_id"]] = state
            if session.business_diagnostic_works.get(work["work_id"]) != state:
                profile_event("native_work_state", **fields, work_id=work["work_id"],
                    revision_number=work["revision"], seq=work["sequence"], status=work["state"])
        session.business_diagnostic_works = retained

    async def _run_native_input(self, session: _NativeMediaSession) -> None:
        while not session.closed:
            frame = await session.input_queue.get()
            try:
                if frame is None or session.closed:
                    return
                started = self._monotonic()
                enqueued = session.input_enqueued_at.pop(frame.seq, started)
                source_event_id = await session.engine.offer_audio(frame)
                finished = self._monotonic()
                if frame.seq % 50 == 0 or finished - started >= .1:
                    profile_event("native_input_delivery", **identity_fields(session.activation.binding),
                        frame_seq=frame.seq, source_event_id=source_event_id, queue_frames=session.input_queue.qsize(),
                        frame_queue_wait_ms=(started - enqueued) * 1000,
                        duration_ms=(finished - started) * 1000,
                        pending_audio_ms=session.input_queue.qsize() * 20,
                        elapsed_ms=(finished - enqueued) * 1000, outcome="sent")
            finally:
                session.input_queue.task_done()

    async def _run_native_events(self, session: _NativeMediaSession) -> None:
        while not session.closed:
            event = await session.engine.next_event()
            if session.closed:
                return
            take_failure = getattr(session.engine, "take_continuation_failure", None)
            if callable(take_failure):
                while (failure := take_failure()) is not None:
                    turn_id, reason = failure
                    self._native_request_state(session, "failed", turn_id, reason)
            if not isinstance(event, NativeEngineEvent):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_EVENT_INVALID",
                    "Native Engine returned an invalid event",
                )
            if all(
                item is None
                for item in (
                    event.action,
                    event.turn_commit,
                    event.input_transcript,
                    event.audio,
                    event.delegate,
                    event.provider_done,
                    event.generated_transcript,
                )
            ):
                continue
            if event.generated_transcript is not None:
                # SPEAK admission is ordered above Provider output. Generated
                # display can then bypass audio delivery without minting an ACK.
                await self._handle_native_event(session, event)
                continue
            if event.action is not None and event.action.operation == "STOP":
                await self._handle_native_event(session, event)
                continue
            if (
                event.action is not None
                and event.action.operation in _NATIVE_ORDERED_CONTROL_OPERATIONS
            ):
                # Engine generation/delivery/playback gates own successor
                # eligibility. Admit this ordered control before reading its
                # output, without waiting behind unrelated queued PCM. In
                # particular a new SPEAK must not prevent the sole reader from
                # observing a later Provider STOP while old media drains.
                await self._handle_native_event(session, event)
                continue
            if event.audio is not None or event.provider_done is not None:
                fenced_response = (
                    event.audio.response
                    if event.audio is not None
                    else event.provider_done.response
                )
                if self._native_response_is_barge_fenced(session, fenced_response):
                    continue
            try:
                session.delivery_queue.put_nowait(event)
            except asyncio.QueueFull:
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_PROVIDER_EVENT_BACKPRESSURE",
                    "Native Provider delivery exceeded its bounded queue",
                ) from None

    async def _run_native_delivery(self, session: _NativeMediaSession) -> None:
        pending: NativeEngineEvent | None = None
        try:
            while not session.closed:
                event = pending
                pending = None
                if event is None:
                    event = await session.delivery_queue.get()
                if session.closed:
                    session.delivery_queue.task_done()
                    return
                session.delivery_response = event.audio.response if event.audio is not None else (
                    event.provider_done.response if event.provider_done is not None else None
                )
                if event.audio is None:
                    try:
                        if event.delegate is not None:
                            call_id = event.delegate.provider_call_id
                            if call_id not in session.delegate_tasks:
                                if len(session.delegate_tasks) >= 8:
                                    raise MediaTransportViolation("MEDIA_NATIVE_DELEGATE_BACKPRESSURE", "Native foreground settlement capacity exceeded")
                                # Reserve semantic ownership in delivery order before
                                # allowing Provider done/ACK to expose an idle foreground.
                                action = event.action
                                assert action is not None
                                reservation = NativeEngineEvent(action=InteractionAction(
                                    action_id=f"{action.action_id}:reserve", operation="DELEGATE",
                                    interaction_id=action.interaction_id, scope=action.scope,
                                    payload=(("provider_call_id", call_id), ("turn_id", event.delegate.turn_id),
                                             ("response_generation", str(event.delegate.response_generation))),
                                ))
                                try:
                                    await self._handle_native_event(session, reservation)
                                except NativeRuntimeClientError:
                                    if any(ref.response_generation == event.delegate.response_generation for ref in session.barge_fenced_responses):
                                        continue
                                    raise
                                if session.closed:
                                    return
                                session.delegate_proposals[call_id] = event
                                task = asyncio.create_task(self._run_native_delegate_event(session, event))
                                session.delegate_tasks[call_id] = task
                                def settled(done, call=call_id, owner=session):
                                    owner.delegate_tasks.pop(call, None)
                                    owner.delegate_proposals.pop(call, None)
                                    record = self._records.get(owner.record_id)
                                    if record is not None:
                                        self._consume_native_task(record, done)
                                task.add_done_callback(settled)
                        else:
                            await self._handle_native_event(session, event)
                    finally:
                        session.delivery_queue.task_done()
                    continue
                batch = [event]
                first_audio = event.audio
                while len(batch) < _NATIVE_AUDIO_PROPOSAL_BATCH:
                    try:
                        candidate = session.delivery_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    candidate_audio = candidate.audio
                    if candidate_audio is None or not _native_audio_extends_batch(
                        first_audio,
                        candidate_audio,
                        ordinal=len(batch),
                    ):
                        pending = candidate
                        break
                    batch.append(candidate)
                try:
                    await self._deliver_native_audio_batch(session, batch)
                finally:
                    for _event in batch:
                        session.delivery_queue.task_done()
        finally:
            if pending is not None:
                session.delivery_queue.task_done()

    async def _deliver_native_audio_batch(
        self,
        session: _NativeMediaSession,
        batch: list[NativeEngineEvent],
    ) -> None:
        client = self._native_runtime_client
        if client is None:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_RUNTIME_UNAVAILABLE",
                "Native Runtime client disappeared",
            )
        admitted = [
            event
            for event in batch
            if event.audio is not None
            and not self._native_response_is_barge_fenced(session, event.audio.response)
        ]
        if admitted:
            first_audio = admitted[0].audio
            assert first_audio is not None
            if first_audio.response not in session.downlink_record_ids:
                await self._deliver_native_audio(session, admitted.pop(0))
        if not admitted or session.closed:
            return
        if len(admitted) == 1:
            await self._deliver_native_audio(session, admitted[0])
            return
        propose_audio_batch = getattr(client, "propose_audio_batch", None)
        if not callable(propose_audio_batch):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_RUNTIME_UNAVAILABLE",
                "Native Runtime audio batch admission disappeared",
            )
        request_id = self._native_request_id(session, "propose")
        started = time.perf_counter()
        try:
            results = await propose_audio_batch(
                binding=session.activation.binding,
                capability=session.activation.capability,
                events=tuple(admitted),
                request_id=request_id,
            )
        except NativeRuntimeClientError as error:
            if error.reason == "NATIVE_AUDIO_RESPONSE_STALE" and all(
                event.audio is not None
                and self._native_response_is_barge_fenced(session, event.audio.response)
                for event in admitted
            ):
                return
            raise
        finally:
            self._profile_native_audio_admission(session, admitted[0].audio, request_id, len(admitted), started)
        if type(results) is not tuple or len(results) != len(admitted):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_AUDIO_ADMISSION_INVALID",
                "Native Runtime audio batch result count is not exact",
            )
        for event, result in zip(admitted, results, strict=True):
            audio = event.audio
            assert audio is not None
            if not isinstance(result, Mapping):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_AUDIO_ADMISSION_INVALID",
                    "Native Runtime audio batch item is invalid",
                )
            if self._native_response_is_barge_fenced(session, audio.response):
                continue
            await self._allocate_native_downlink(session, audio, result)

    @staticmethod
    def _profile_native_audio_admission(session, audio, request_id, count, started):
        try:
            profile_event(
                "native_audio_supply", **identity_fields(session.activation.binding, audio.response),
                stage="gateway_runtime_admission", request_id=request_id,
                provider_response_id=audio.provider_response_id, provider_item_id=audio.provider_item_id,
                source_event_id=audio.provider_event_id, frame_seq=audio.sequence, frame_count=count,
                duration_ms=(time.perf_counter() - started) * 1000,
                queue_frames=session.delivery_queue.qsize(),
            )
        except Exception:
            pass

    async def _deliver_native_audio(
        self, session: _NativeMediaSession, event: NativeEngineEvent
    ) -> None:
        if session.closed:
            return
        client = self._native_runtime_client
        if client is None:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_RUNTIME_UNAVAILABLE",
                "Native Runtime client disappeared",
            )
        audio = event.audio
        assert audio is not None
        request_id = self._native_request_id(session, "propose")
        started = time.perf_counter()
        try:
            result = await client.propose(
                binding=session.activation.binding,
                capability=session.activation.capability,
                event=event,
                request_id=request_id,
            )
        except NativeRuntimeClientError as error:
            if (
                error.reason == "NATIVE_AUDIO_RESPONSE_STALE"
                and self._native_response_is_barge_fenced(session, audio.response)
            ):
                return
            raise
        finally:
            self._profile_native_audio_admission(session, audio, request_id, 1, started)
        if not self._native_response_is_barge_fenced(session, audio.response):
            await self._allocate_native_downlink(session, audio, result)

    async def _handle_native_event(
        self, session: _NativeMediaSession, event: NativeEngineEvent
    ) -> None:
        if session.closed:
            return
        if event.generated_transcript is not None:
            observation = event.generated_transcript
            with self._lock:
                parent = self._records.get(session.record_id)
                retained = session.generated_text.get(observation.response)
                if (session.closed or self._native_sessions.get(session.key) is not session
                    or parent is None or parent.route_completed
                    or not self._has_retained_product_activation(parent, self._monotonic())
                    or retained is None or not retained["turn_id"]
                    or retained["provider_response_id"] != observation.provider_response_id
                    or retained["state"] != "generating"
                    or self._native_response_is_barge_fenced(session, observation.response)):
                    return
                if retained["text"] != observation.text:
                    retained["text"] = observation.text
                    self._revise_native_text(session, retained)
            return
        client = self._native_runtime_client
        if client is None:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_RUNTIME_UNAVAILABLE",
                "Native Runtime client disappeared",
            )
        fenced_response = (
            event.audio.response
            if event.audio is not None
            else (
                event.provider_done.response
                if event.provider_done is not None
                else None
            )
        )
        if event.action is not None and event.action.operation == "SPEAK" and "runtime_response_id" in dict(event.action.payload):
            fenced_response = self._native_stop_response(event.action)
        if fenced_response is not None and self._native_response_is_barge_fenced(
            session, fenced_response
        ):
            return
        if event.action is not None and event.action.operation == "STOP":
            self._retain_native_barge_fence(
                session, self._native_stop_response(event.action)
            )
        try:
            result = await client.propose(
                binding=session.activation.binding,
                capability=session.activation.capability,
                event=event,
                request_id=self._native_request_id(session, "propose"),
            )
        except NativeRuntimeClientError as error:
            if (
                error.reason == "NATIVE_AUDIO_RESPONSE_STALE"
                and event.audio is not None
                and self._native_response_is_barge_fenced(session, event.audio.response)
            ):
                return
            if (error.reason == "NATIVE_RESPONSE_PRESENTATION_BUSY"
                    and session.activation.business_contract_version is not None
                    and event.action is not None and event.action.operation == "SPEAK"
                    and "work_event_id" in dict(event.action.payload)):
                await session.engine.defer_work_response(dict(event.action.payload)["provider_response_id"])
                return
            raise
        if event.delegate is not None:
            await self._return_native_delegate_result(session, event, result)
        elif event.input_transcript is not None:
            self._queue_native_user_transcript(session, event, result)
        elif event.action is not None:
            if event.action.operation == "SPEAK":
                await self._admit_native_response(session, event, result)
            elif event.action.operation == "LISTEN":
                self._retain_native_speech_start(session, event, result)
            elif event.action.operation == "TURN_COMMIT":
                self._retain_native_end_of_turn(session, event, result)
                assert event.turn_commit is not None
                session.foreground_turn_id = event.turn_commit.turn_id
                if session.activation.business_contract_version is not None:
                    await session.engine.acknowledge_business_turn(event.turn_commit.turn_id)
                self._native_request_state(session, "processing", event.turn_commit.turn_id)
            elif event.action.operation == "STOP":
                response = self._native_stop_response(event.action)
                stop = getattr(session.engine, "stop_foreground", None)
                if callable(stop):
                    await stop(response)
                else:
                    await session.engine.fence_response(response)
                if session.activation.business_contract_version is not None:
                    await session.engine.acknowledge_business_stop(response)
                if session.foreground_turn_id is not None:
                    self._native_request_state(session, "interrupted", session.foreground_turn_id, response=response)
        elif event.audio is not None:
            await self._allocate_native_downlink(session, event.audio, result)
        elif event.provider_done is not None:
            await self._seal_native_downlink(session, event.provider_done, result)
            if result.get("accepted") is False:
                await session.engine.fence_response(event.provider_done.response)
                return
            settle_delivery = getattr(session.engine, "acknowledge_delivery", None)
            if callable(settle_delivery):
                await settle_delivery(event.provider_done.response)
            retained = session.generated_text.get(event.provider_done.response)
            if retained is not None and retained["state"] == "generating":
                retained["state"] = "generated" if event.provider_done.completed else "interrupted"
                self._revise_native_text(session, retained)

    async def _run_native_delegate_event(self, session: _NativeMediaSession, event: NativeEngineEvent) -> None:
        delegate = event.delegate
        assert delegate is not None
        try:
            await self._handle_native_event(session, event)
        except Exception as error:
            reason = getattr(error, "reason", "NATIVE_DELEGATE_FAILED")
            business = session.activation.business_contract_version is not None
            if reason == "NATIVE_DELEGATE_INTERRUPTED":
                if business:
                    await session.engine.retire_delegate(delegate.provider_call_id, interrupted=True)
                return
            if not business and any(
                ref.response_generation == delegate.response_generation for ref in session.barge_fenced_responses
            ):
                return
            if isinstance(error, NativeRuntimeClientError) and reason.startswith(("NATIVE_DELEGATE_", "NATIVE_TASK_DELEGATE_", "SEMANTIC_")):
                retire = getattr(session.engine, "retire_delegate", None)
                if callable(retire):
                    await retire(delegate.provider_call_id, interrupted=False)
                self._native_request_state(session, "failed", delegate.turn_id, reason)
                return
            raise

    def _native_request_state(self, session: _NativeMediaSession, phase: str, turn_id: str, reason: str | None = None, *, response: ResponseRef | None = None, retain_for_close: bool = False) -> None:
        if session.closed or session.foreground_turn_id != turn_id:
            return
        parent = self._records.get(session.record_id)
        if parent is None or parent.route_completed:
            return
        notifications = self._native_notifications.get((parent.binding.session_id,
            parent.binding.interaction_id, parent.binding.connection_id))
        if not retain_for_close and (notifications is None or notifications.full()):
            raise MediaTransportViolation("MEDIA_NATIVE_NOTIFICATION_BACKPRESSURE", "Native request state unavailable")
        session.request_state_sequence += 1
        profile_event("native_request_state", **identity_fields(session.activation.binding, response),
                      turn_id=turn_id, status=phase, reason=reason, seq=session.request_state_sequence)
        notification = {
            "status": "notification", "kind": "native.request_state",
            "request_id": self._native_request_id(session, "request-state"),
            "round_id": None, "response": None if response is None else {
                "interaction_id": response.interaction_id, "response_id": response.response_id,
                "response_generation": response.response_generation}, "agent_event": None, "source_event": None,
            "progress_event": None, "presentation_unit": None, "audio": None,
            "error_reason": None, "publish_seq": None,
            "request_state": {"turn_id": turn_id, "phase": phase, "reason": reason,
                              "sequence": session.request_state_sequence},
            "session_id": parent.binding.session_id, "correlation_id": parent.binding.correlation_id,
            "interaction_id": parent.binding.interaction_id, "activation_id": parent.product_activation_id,
            "activation_generation": parent.product_activation_generation,
        }
        if retain_for_close:
            # One terminal diagnostic belongs to the authenticated activation,
            # independently of the media queue that close must destroy.
            with self._lock:
                authority = self._product_activations.get((parent.binding.session_id,
                    parent.binding.connection_id, parent.binding.interaction_id))
                if (authority is not None and self._monotonic() <= authority.expires_at
                    and authority.correlation_id == parent.binding.correlation_id
                    and authority.activation_id == parent.product_activation_id
                    and authority.activation_generation == parent.product_activation_generation
                    and authority.notification_fence.terminal_notification is None):
                    authority.notification_fence.terminal_notification = notification
        else:
            assert notifications is not None
            notifications.put_nowait(notification)

    def _queue_native_user_transcript(
        self,
        session: _NativeMediaSession,
        event: NativeEngineEvent,
        result: Mapping[str, object],
    ) -> None:
        transcript = event.input_transcript
        assert transcript is not None
        history = result.get("history")
        following = (
            history.get("following_assistant") if isinstance(history, Mapping) else None
        )
        if (
            set(result) != {"kind", "status", "accepted", "history"}
            or result.get("kind") != "input_transcript"
            or result.get("status") != "observed"
            or type(result.get("accepted")) is not bool
            or not isinstance(history, Mapping)
            or set(history)
            not in (
                {"message", "binding"},
                {"message", "binding", "following_assistant"},
            )
            or (
                following is not None
                and (not isinstance(following, list) or not following)
            )
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_INPUT_TRANSCRIPT_INVALID",
                "Native input transcript result is not exact",
            )
        message = history.get("message")
        history_binding = history.get("binding")
        timestamp = message.get("timestamp") if isinstance(message, Mapping) else None
        binding_keys = {
            "scope",
            "interaction_id",
            "activation_id",
            "activation_generation",
            "correlation_id",
            "turn_id",
            "commit_id",
            "provider_session_id",
            "provider_item_id",
            "provider_event_id",
        }
        if (
            not isinstance(message, Mapping)
            or set(message) != {"id", "role", "content", "timestamp"}
            or message.get("id") != f"live-voice:{transcript.commit_id}:native-user"
            or message.get("role") != "user"
            or message.get("content") != transcript.transcript
            or isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or timestamp < 0
            or not isinstance(history_binding, Mapping)
            or set(history_binding) != binding_keys
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_INPUT_TRANSCRIPT_INVALID",
                "Native input transcript history is not exact",
            )
        following_projection: list[dict[str, object]] = []
        for candidate in following or ():
            if not isinstance(candidate, Mapping) or set(candidate) != {
                "turn_id",
                "response",
                "transcript",
                "presented_at",
                "message",
            }:
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_INPUT_TRANSCRIPT_INVALID",
                    "following Native assistant history is not exact",
                )
            assistant_response = candidate.get("response")
            assistant_message = candidate.get("message")
            assistant_transcript = candidate.get("transcript")
            presented_at = candidate.get("presented_at")
            assistant_timestamp = (
                assistant_message.get("timestamp")
                if isinstance(assistant_message, Mapping)
                else None
            )
            if (
                candidate.get("turn_id") != transcript.turn_id
                or not isinstance(assistant_response, Mapping)
                or set(assistant_response)
                != {"interaction_id", "response_id", "response_generation"}
                or assistant_response.get("interaction_id")
                != transcript.binding.interaction_id
                or type(assistant_response.get("response_id")) is not str
                or not assistant_response.get("response_id")
                or isinstance(assistant_response.get("response_generation"), bool)
                or not isinstance(assistant_response.get("response_generation"), int)
                or assistant_response.get("response_generation", 0) <= 0
                or type(assistant_transcript) is not str
                or not assistant_transcript
                or assistant_transcript != assistant_transcript.strip()
                or type(presented_at) is not str
                or not presented_at
                or not isinstance(assistant_message, Mapping)
                or set(assistant_message) != {"id", "role", "content", "timestamp"}
                or assistant_message.get("role") != "assistant"
                or assistant_message.get("content") != assistant_transcript
                or assistant_message.get("id")
                != (
                    "live-voice:"
                    f"{assistant_response.get('interaction_id')}:"
                    f"{assistant_response.get('response_id')}:"
                    f"{assistant_response.get('response_generation')}:native-audio:"
                    f"{hashlib.sha256(assistant_transcript.encode('utf-8')).hexdigest()}"
                )
                or isinstance(assistant_timestamp, bool)
                or not isinstance(assistant_timestamp, (int, float))
                or not math.isfinite(assistant_timestamp)
                or assistant_timestamp < 0
            ):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_INPUT_TRANSCRIPT_INVALID",
                    "following Native assistant history is invalid",
                )
            following_projection.append(
                {
                    "message": dict(assistant_message),
                    "binding": {
                        "turn_id": transcript.turn_id,
                        "response": dict(assistant_response),
                        "surface": "native_audio",
                        "presented_at": presented_at,
                    },
                }
            )
        raw_activation_binding = {
            key: history_binding[key]
            for key in (
                "scope",
                "interaction_id",
                "activation_id",
                "activation_generation",
                "correlation_id",
            )
        }
        try:
            parsed_binding = NativeInteractionBinding.from_dict(raw_activation_binding)
        except Exception as error:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_INPUT_TRANSCRIPT_INVALID",
                "Native input transcript binding is invalid",
            ) from error
        if (
            parsed_binding != session.activation.binding
            or history_binding.get("turn_id") != transcript.turn_id
            or history_binding.get("commit_id") != transcript.commit_id
            or history_binding.get("provider_session_id")
            != transcript.provider_session_id
            or history_binding.get("provider_item_id") != transcript.provider_item_id
            or history_binding.get("provider_event_id") != transcript.provider_event_id
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_INPUT_TRANSCRIPT_INVALID",
                "Native input transcript history does not match its Provider fact",
            )
        if result.get("accepted") is False or (
            transcript.provider_item_id in session.projected_input_transcript_items
        ):
            return
        parent = self._records.get(session.record_id)
        notification_key = (
            session.activation.binding.scope.session_id or "",
            session.activation.binding.interaction_id,
            session.activation.connection_id,
        )
        notifications = self._native_notifications.get(notification_key)
        if (
            parent is None
            or parent.route_completed
            or parent.native_activation != session.activation
            or notifications is None
            or notifications.full()
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_NOTIFICATION_BACKPRESSURE",
                "Native user transcript notification route is unavailable",
            )
        notification = {
            "status": "notification",
            "kind": "native.user_transcript",
            "request_id": self._native_request_id(session, "input-transcript"),
            "round_id": None,
            "response": None,
            "agent_event": {
                "event_type": "chat.final",
                "message": dict(message),
                "binding": dict(history_binding),
                **(
                    {"following_assistant": following_projection}
                    if following_projection
                    else {}
                ),
            },
            "source_event": None,
            "progress_event": None,
            "presentation_unit": None,
            "audio": None,
            "error_reason": None,
            "publish_seq": None,
            "session_id": parent.binding.session_id,
            "correlation_id": parent.binding.correlation_id,
            "interaction_id": parent.binding.interaction_id,
            "activation_id": parent.product_activation_id,
            "activation_generation": parent.product_activation_generation,
        }
        notifications.put_nowait(notification)
        session.projected_input_transcript_items.add(transcript.provider_item_id)

    @staticmethod
    def _native_stop_response(action: InteractionAction) -> ResponseRef:
        payload = dict(action.payload)
        response_id = payload.get("runtime_response_id")
        generation = payload.get("response_generation")
        if (
            type(response_id) is not str
            or not response_id
            or type(generation) is not str
            or not generation.isascii()
            or not generation.isdecimal()
            or (len(generation) > 1 and generation.startswith("0"))
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_STOP_RESPONSE_INVALID",
                "Native STOP lacks one exact Runtime response",
            )
        return ResponseRef(action.interaction_id, response_id, int(generation))

    async def _return_native_delegate_result(
        self,
        session: _NativeMediaSession,
        event: NativeEngineEvent,
        result: Mapping[str, object],
    ) -> None:
        delegate = event.delegate
        assert delegate is not None
        if session.closed:
            return
        response_payload = result.get("response")
        settled_task = result.get("status") in {"interrupted", "failed"}
        if (
            result.get("kind") != "delegate"
            or result.get("status") not in {"prepared", "interrupted", "failed"}
            or type(result.get("accepted")) is not bool
            or result.get("provider_call_id") != delegate.provider_call_id
            or not isinstance(response_payload, Mapping)
            or set(response_payload)
            != {"interaction_id", "response_id", "response_generation"}
            or (not settled_task and type(result.get("canonical_text")) is not str)
            or (settled_task and (result.get("route") != "task" or "task_id" not in result or "reason" not in result or "canonical_text" in result))
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_DELEGATE_RESULT_INVALID",
                "Native delegate result does not match the Provider call",
            )
        response = ResponseRef(
            interaction_id=_required_id(
                response_payload.get("interaction_id"), "response.interaction_id"
            ),
            response_id=_required_id(
                response_payload.get("response_id"), "response.response_id"
            ),
            response_generation=_safe_uint(
                response_payload.get("response_generation"),
                "response.response_generation",
            ),
        )
        if (
            response.interaction_id != session.activation.binding.interaction_id
            or response.response_generation != delegate.response_generation
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_DELEGATE_RESULT_INVALID",
                "Native prepared result must retain its exact source generation",
            )
        task_id = None
        task_commit_id = None
        if "task_id" in result:
            task_id = _required_id(result["task_id"], "task_id")
            task_commit_id = _required_id(result.get("turn_commit_id"), "turn_commit_id")
            if result.get("route") != "task":
                raise MediaTransportViolation("MEDIA_NATIVE_TASK_ASSOCIATION_INVALID", "task association requires formal Task route")
        if task_id is not None and delegate.provider_call_id not in session.projected_task_associations:
            parent = self._records.get(session.record_id)
            key = (session.activation.binding.scope.session_id or "",
                   session.activation.binding.interaction_id, session.activation.connection_id)
            notifications = self._native_notifications.get(key)
            if (session.closed or parent is None or parent.route_completed
                or parent.native_activation != session.activation or notifications is None
                or notifications.full() or len(session.projected_task_associations) >= 128):
                raise MediaTransportViolation("MEDIA_NATIVE_NOTIFICATION_BACKPRESSURE", "Task discovery notification unavailable")
            notifications.put_nowait({
                "status": "notification", "kind": "native.task_association",
                "request_id": self._native_request_id(session, "task-association"),
                "round_id": None, "response": dict(response_payload),
                "task_association": {"task_id": task_id,
                    "turn_commit_id": task_commit_id,
                    "provider_call_id": delegate.provider_call_id},
                "agent_event": None, "source_event": None, "progress_event": None,
                "presentation_unit": None, "audio": None, "error_reason": None, "publish_seq": None,
                "session_id": parent.binding.session_id, "correlation_id": parent.binding.correlation_id,
                "interaction_id": parent.binding.interaction_id, "activation_id": parent.product_activation_id,
                "activation_generation": parent.product_activation_generation,
            })
            session.projected_task_associations.add(delegate.provider_call_id)

        if settled_task:
            retire = getattr(session.engine, "retire_delegate", None)
            if callable(retire):
                await retire(delegate.provider_call_id, interrupted=result["status"] == "interrupted")
            if result["status"] == "failed":
                self._native_request_state(session, "failed", delegate.turn_id, str(result["reason"]))
            return
        business = session.activation.business_contract_version is not None
        if not business and any(ref.response_generation == delegate.response_generation for ref in session.barge_fenced_responses):
            return
        if business:
            session.business_receipt_epoch += 1
        event_ids = await session.engine.send_delegate_result(
            delegate.provider_call_id,
            response,
            str(result["canonical_text"]),
        )
        if (
            type(event_ids) is not tuple
            or len(event_ids) != 2
            or type(event_ids[0]) is not str or not event_ids[0]
            or (event_ids[1] is None and not business)
            or (event_ids[1] is not None and (type(event_ids[1]) is not str or not event_ids[1]))
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_DELEGATE_PROVIDER_SEND_INVALID",
                "Native Engine returned no exact Provider delegate receipts",
            )

    def _retain_native_speech_start(
        self,
        session: _NativeMediaSession,
        event: NativeEngineEvent,
        result: Mapping[str, object],
    ) -> None:
        action = event.action
        assert action is not None
        payload = dict(action.payload)
        raw_start = payload.get("provider_start_ms")
        if (
            result.get("kind") != "action"
            or result.get("status") != "observed"
            or result.get("accepted") is not True
            or type(raw_start) is not str
            or not raw_start.isascii()
            or not raw_start.isdecimal()
            or (len(raw_start) > 1 and raw_start.startswith("0"))
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_SPEECH_START_INVALID",
                "Native speech start lacks exact Runtime admission and Provider time",
            )
        try:
            session.speech_start_queue.put_nowait(int(raw_start))
        except asyncio.QueueFull:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_SPEECH_START_BACKPRESSURE",
                "Native speech-start queue is saturated",
            ) from None

    def _retain_native_end_of_turn(
        self,
        session: _NativeMediaSession,
        event: NativeEngineEvent,
        result: Mapping[str, object],
    ) -> None:
        action = event.action
        commit = event.turn_commit
        assert action is not None
        payload = dict(action.payload)
        if (
            commit is None
            or result.get("kind") != "turn"
            or result.get("status") != "observed"
            or result.get("accepted") is not True
            or commit.binding != session.activation.binding
            or set(payload) != {"turn_id", "provider_item_id"}
            or payload.get("turn_id") != commit.turn_id
            or payload.get("provider_item_id") != commit.provider_item_id
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_END_OF_TURN_INVALID",
                "Native end of turn lacks exact Runtime admission and Provider timing",
            )
        try:
            session.end_of_turn_queue.put_nowait(
                (commit.input_audio_start_ms, commit.input_audio_end_ms)
            )
        except asyncio.QueueFull:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_END_OF_TURN_BACKPRESSURE",
                "Native end-of-turn queue is saturated",
            ) from None

    async def _admit_native_response(
        self,
        session: _NativeMediaSession,
        event: NativeEngineEvent,
        result: Mapping[str, object],
    ) -> None:
        action = event.action
        assert action is not None
        payload = dict(action.payload)
        response_payload = result.get("response")
        if (
            result.get("kind") != "response"
            or result.get("status") != "observed"
            or result.get("accepted") is not True
            or not isinstance(response_payload, Mapping)
            or set(response_payload)
            != {"interaction_id", "response_id", "response_generation"}
            or result.get("provider_response_id") != payload.get("provider_response_id")
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_RESPONSE_ADMISSION_INVALID",
                "Native Runtime response admission is not exact",
            )
        response = ResponseRef(
            interaction_id=_required_id(
                response_payload.get("interaction_id"), "response.interaction_id"
            ),
            response_id=_required_id(
                response_payload.get("response_id"), "response.response_id"
            ),
            response_generation=_safe_uint(
                response_payload.get("response_generation"),
                "response.response_generation",
            ),
        )
        if response.interaction_id != session.activation.binding.interaction_id:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_RESPONSE_ADMISSION_INVALID",
                "Native response does not match the exact interaction",
            )
        await session.engine.admit_response(
            str(result["provider_response_id"]), response
        )
        with self._lock:
            parent = self._records.get(session.record_id)
            if (session.closed or self._native_sessions.get(session.key) is not session
                or parent is None or parent.route_completed
                or not self._has_retained_product_activation(parent, self._monotonic())
                or self._native_response_is_barge_fenced(session, response)):
                return
            if response not in session.generated_text:
                session.generated_text[response] = {
                    "provider_response_id": str(result["provider_response_id"]),
                    "turn_id": payload.get("turn_id"),
                    "response": {"interaction_id": response.interaction_id, "response_id": response.response_id,
                                 "response_generation": response.response_generation},
                    "text": "", "state": "generating", "revision": 0,
                    "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                }
                while len(session.generated_text) > min(self._capacity, 64):
                    session.generated_text.popitem(last=False)

    async def _allocate_native_downlink(
        self,
        session: _NativeMediaSession,
        output: NativeAudioOutput,
        result: Mapping[str, object],
    ) -> None:
        unit = result.get("presentation_unit")
        if (
            result.get("kind") != "audio"
            or result.get("status") != "observed"
            or type(result.get("accepted")) is not bool
            or not isinstance(unit, Mapping)
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_AUDIO_ADMISSION_INVALID",
                "Native audio lacks exact Runtime presentation admission",
            )
        if result.get("accepted") is False:
            return
        expected_unit_keys = {
            "response",
            "surface",
            "unit_id",
            "seq",
            "source_start_utf8",
            "source_end_utf8",
            "content_ref",
        }
        response_payload = unit.get("response")
        digest = hashlib.sha256(output.pcm16).hexdigest()
        provider_sample_count = output.provider_sample_count
        if provider_sample_count is None:
            provider_sample_count = len(output.pcm16) // 2
        source_start_sample = unit.get("source_start_utf8")
        source_end_sample = unit.get("source_end_utf8")
        if (
            set(unit) != expected_unit_keys
            or unit.get("surface") != "audio"
            or unit.get("seq") != output.sequence
            or unit.get("content_ref") != f"sha256:{digest}"
            or type(source_start_sample) is not int
            or type(source_end_sample) is not int
            or source_start_sample < 0
            or type(provider_sample_count) is not int
            or not 0 < provider_sample_count <= len(output.pcm16) // 2
            or source_end_sample - source_start_sample != provider_sample_count
            or not isinstance(response_payload, Mapping)
            or set(response_payload)
            != {"interaction_id", "response_id", "response_generation"}
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_AUDIO_ADMISSION_INVALID",
                "Native audio PresentationUnit is not exact",
            )
        response = ResponseRef(
            interaction_id=_required_id(
                response_payload.get("interaction_id"), "response.interaction_id"
            ),
            response_id=_required_id(
                response_payload.get("response_id"), "response.response_id"
            ),
            response_generation=_safe_uint(
                response_payload.get("response_generation"),
                "response.response_generation",
            ),
        )
        unit_id = _required_id(unit.get("unit_id"), "unit_id")
        if response != output.response:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_AUDIO_ADMISSION_INVALID",
                "Native audio response admission is stale",
            )
        if self._native_response_is_barge_fenced(session, response):
            return
        parent = self._records.get(session.record_id)
        now = self._monotonic()
        if (
            parent is None
            or parent.route_completed
            or parent.native_activation != session.activation
            or not self._has_retained_product_activation(parent, now)
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_AUDIO_FENCED",
                "Native audio parent uplink is no longer authoritative",
            )
        browser_sample_rate = parent.binding.frame_format.sample_rate_hz
        frames = _native_downlink_frames(
            output.pcm16, sample_rate_hz=browser_sample_rate
        )
        if len(frames) != 1:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_AUDIO_FRAME_ALIGNMENT",
                "Native response source requires one exact 20 ms Provider frame",
            )
        browser_frame = replace(
            frames[0],
            seq=output.sequence,
            sample_cursor=output.sequence * (browser_sample_rate // 50),
        )
        presentation = NativeDownlinkPresentationUnit(
            response=response,
            unit_id=unit_id,
            unit_seq=output.sequence,
            provider_item_id=output.provider_item_id,
            content_index=output.content_index,
            source_start_sample=source_start_sample,
            source_end_sample=source_end_sample,
            content_sha256=digest,
        )
        retained_id = session.downlink_record_ids.get(response)
        retained = self._records.get(retained_id or "")
        if retained_id is not None:
            source = retained.downlink_stream_source if retained is not None else None
            if (
                retained is None
                or retained.route_completed
                or retained.native_session_key != session.key
                or not isinstance(source, NativeResponseDownlinkSource)
            ):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_AUDIO_FENCED",
                    "Native response downlink is no longer authoritative",
                )
            try:
                await source.append(browser_frame, presentation, pcm16=output.pcm16)
            except MediaTransportViolation as error:
                if (
                    error.reason_id == "MEDIA_NATIVE_STREAM_CLOSED"
                    and self._native_response_is_barge_fenced(session, response)
                ):
                    return
                raise
            retained.native_provider_item_id = output.provider_item_id
            retained.native_content_index = output.content_index
            retained.native_source_end_sample = source_end_sample
            retained.downlink_content_sha256 = source.content_sha256
            parent.synthesis_content_sha256[
                (response, retained.downlink_unit_id or "")
            ] = source.content_sha256
            return
        notification_key = (
            parent.binding.session_id,
            parent.binding.interaction_id,
            parent.binding.connection_id,
        )
        notifications = self._native_notifications.get(notification_key)
        if notifications is None or notifications.full():
            raise MediaTransportViolation(
                "MEDIA_NATIVE_NOTIFICATION_BACKPRESSURE",
                "Native notification queue is saturated",
            )
        with self._lock:
            self._prune(now)
            if self._media_capacity_in_use() >= self._capacity:
                raise MediaTransportViolation(
                    "MEDIA_ROUTE_CAPACITY_EXCEEDED", "media route capacity is full"
                )
            ticket = secrets.token_urlsafe(32)
            record_id = f"media-record-{secrets.token_hex(16)}"
            binding = MediaAuthorityBinding(
                lease_id=f"media-downlink-{secrets.token_hex(16)}",
                authority_evidence_id=f"media-authority-{secrets.token_hex(16)}",
                connection_id=parent.binding.connection_id,
                connection_epoch=parent.binding.connection_epoch,
                session_id=parent.binding.session_id,
                media_session_id=f"media-session-{secrets.token_hex(16)}",
                interaction_id=response.interaction_id,
                track_id=f"native-playout-{secrets.token_hex(12)}",
                correlation_id=parent.binding.correlation_id,
                direction=MediaDirection.DOWNLINK,
                generation=MediaGenerationBinding(
                    MediaGenerationKind.RESPONSE,
                    response.response_id,
                    response.response_generation,
                ),
                frame_format=MediaFrameFormat(
                    sample_rate_hz=browser_sample_rate,
                    samples_per_channel=browser_sample_rate // 50,
                ),
                playout=MediaPlayoutBinding(
                    response.response_id,
                    response.response_generation,
                    unit_id,
                ),
            )
            source = NativeResponseDownlinkSource(
                response=response,
                sample_rate_hz=browser_sample_rate,
                capacity=8,
                max_frames=_MAX_DOWNLINK_FRAMES,
                append_timeout_seconds=self._native_downlink_append_timeout_seconds,
            )
            downlink = _MediaAuthority(
                record_id=record_id,
                subject_id=parent.subject_id,
                expected_origin=parent.expected_origin,
                product_activation_id=parent.product_activation_id,
                product_activation_generation=parent.product_activation_generation,
                binding=binding,
                locale=parent.locale,
                end_of_turn_capability=None,
                issued_at=now,
                ticket_expires_at=now + self._ticket_ttl,
                authority_expires_at=parent.authority_expires_at,
                native_activation=session.activation,
                native_session_key=session.key,
                native_provider_item_id=output.provider_item_id,
                native_content_index=output.content_index,
                native_source_start_sample=source_start_sample,
                native_source_end_sample=source_end_sample,
                downlink_stream_source=source,
                downlink_response=response,
                downlink_unit_id=unit_id,
                downlink_unit_seq=output.sequence,
                downlink_content_sha256=digest,
            )
            self._records[record_id] = downlink
            self._pending_tickets[ticket] = record_id
            parent.synthesis_content_sha256[(response, unit_id)] = digest
            session.downlink_record_ids[response] = record_id
        try:
            await source.append(browser_frame, presentation, pcm16=output.pcm16)
        except BaseException:
            with self._lock:
                self._records.pop(record_id, None)
                self._pending_tickets.pop(ticket, None)
                parent.synthesis_content_sha256.pop((response, unit_id), None)
                session.downlink_record_ids.pop(response, None)
            await source.aclose()
            raise
        audio = {
            "format": "pcm_f32_mono_20ms",
            "sample_rate_hz": browser_sample_rate,
            "channel_count": 1,
            "frame_count": None,
            "delivery": "dedicated_media_downlink",
            "endpoint_path": MEDIA_ROUTE_PATH,
            "media_ticket": ticket,
            "subprotocol": MEDIA_SUBPROTOCOL,
            "ticket_ttl_ms": int(self._ticket_ttl * 1000),
            "binding": _binding_payload(binding),
            "max_pending_frames": 8,
            "max_pending_bytes": 131_072,
            "streaming": True,
            "degradation_reason": None,
        }
        notification = {
            "status": "notification",
            "kind": "native.audio",
            "request_id": self._native_request_id(session, "audio"),
            "round_id": None,
            "response": dict(response_payload),
            "agent_event": None,
            "source_event": None,
            "progress_event": None,
            "presentation_unit": dict(unit),
            "audio": audio,
            "error_reason": None,
            "publish_seq": None,
            "session_id": parent.binding.session_id,
            "correlation_id": parent.binding.correlation_id,
            "interaction_id": parent.binding.interaction_id,
            "activation_id": parent.product_activation_id,
            "activation_generation": parent.product_activation_generation,
        }
        try:
            notifications.put_nowait(notification)
            _LOGGER.info("live_voice_native_audio_notification_queued")
        except asyncio.QueueFull:
            with self._lock:
                self._records.pop(record_id, None)
                self._pending_tickets.pop(ticket, None)
                parent.synthesis_content_sha256.pop((response, unit_id), None)
                session.downlink_record_ids.pop(response, None)
            await source.aclose()
            raise MediaTransportViolation(
                "MEDIA_NATIVE_NOTIFICATION_BACKPRESSURE",
                "Native notification queue is saturated",
            ) from None

        # The local descriptor must be visible before the remote poll is woken.
        # This control RPC is session-owned and never stalls subsequent PCM.
        wake = getattr(self._native_runtime_client, "wake_native_notification", None)
        if callable(wake) and not session.closed:
            if len(session.notification_wake_tasks) < 8:
                task = asyncio.create_task(self._wake_native_notification(session, response),
                    name="live-voice-native-notification-wake")
                session.notification_wake_tasks.add(task)
                task.add_done_callback(session.notification_wake_tasks.discard)
            else:
                _LOGGER.warning("live_voice_native_notification_wake_failed reason=CAPACITY")

    async def _wake_native_notification(self, session: _NativeMediaSession, response: ResponseRef) -> None:
        started = time.perf_counter()
        try:
            if session.closed:
                return
            await self._native_runtime_client.wake_native_notification(
                session.activation, response=response,
                request_id=self._native_request_id(session, "notification-wake"))
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed optimization retains the existing poll's ownership and
            # outcome. No discarded descriptor, audio failure or fabricated ACK.
            _LOGGER.warning("live_voice_native_notification_wake_failed reason=UNAVAILABLE")
        finally:
            _LOGGER.info("live_voice_native_notification_wake duration_ms=%.1f",
                (time.perf_counter() - started) * 1000)

    async def _seal_native_downlink(
        self,
        session: _NativeMediaSession,
        done: NativeProviderDone,
        result: Mapping[str, object],
    ) -> None:
        if (
            result.get("kind") != "done"
            or result.get("status") != "observed"
            or type(result.get("accepted")) is not bool
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_DONE_ADMISSION_INVALID",
                "Native Provider completion lacks exact Runtime admission",
            )
        if self._native_response_is_barge_fenced(session, done.response):
            return
        record_id = session.downlink_record_ids.get(done.response)
        record = self._records.get(record_id or "")
        source = record.downlink_stream_source if record is not None else None
        if record_id is None:
            return
        if (
            record is None
            or record.native_session_key != session.key
            or not isinstance(source, NativeResponseDownlinkSource)
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_AUDIO_FENCED",
                "Native response completion lost its downlink source",
            )
        if result.get("accepted") is False:
            await source.aclose()
            return
        # EOF describes the finite received PCM, not successful generation.
        # Incomplete/failed output must drain its valid frames and wait for the
        # exact Browser rendered ACK; closing here would discard queued tails.
        record.native_generation_completed = done.completed
        try:
            await source.seal(done.response)
        except MediaTransportViolation as error:
            if (
                error.reason_id == "MEDIA_NATIVE_STREAM_CLOSED"
                and self._native_response_is_barge_fenced(session, done.response)
            ):
                return
            raise

    async def accept_native_playback_stop(
        self,
        record: _MediaAuthority,
        receipt: MediaPlaybackStopReceipt,
    ) -> bool:
        """Admit an exact Browser fence, with optional played-cursor truncation."""

        exact = validate_playback_stop_receipt(record.binding, receipt)
        if exact.outcome is not MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_PLAYBACK_FENCE_UNPROVEN",
                "Native Provider cancellation requires an exact local playout fence",
            )
        key = record.native_session_key
        session = self._native_sessions.get(key) if key is not None else None
        parent = self._records.get(session.record_id) if session is not None else None
        if (
            session is None
            or session.closed
            or not record.ticket_consumed
            or record.native_activation != session.activation
            or parent is None
            or parent.route_completed
            or parent.native_activation != session.activation
            or record.downlink_response is None
            or not isinstance(
                record.downlink_stream_source, NativeResponseDownlinkSource
            )
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_PLAYBACK_FENCED",
                "Native playback stop is no longer bound to an active response",
            )
        source = record.downlink_stream_source
        assert isinstance(source, NativeResponseDownlinkSource)
        cursor: NativePresentationCursor | None = None
        if exact.confirmed_through_seq is not None:
            played = source.unit_for_media_sequence(exact.confirmed_through_seq)
            provider_sample_end = source.provider_sample_end_for_media_sequence(
                exact.confirmed_through_seq
            )
            if (
                played is None
                or provider_sample_end is None
                or played.response != record.downlink_response
            ):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_PLAYBACK_CURSOR_INVALID",
                    "Native played cursor has no exact admitted Runtime unit",
                )
            cursor = NativePresentationCursor(
                response=record.downlink_response,
                provider_item_id=played.provider_item_id,
                content_index=played.content_index,
                audio_end_ms=(provider_sample_end * 1_000 // NATIVE_PCM_SAMPLE_RATE),
            )
        action_id = self._native_barge_action_id(record, exact, cursor)
        client = self._native_runtime_client
        presentation_ack = getattr(client, "presentation_ack", None)
        if not callable(presentation_ack):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_RUNTIME_UNAVAILABLE",
                "Native Runtime presentation authority disappeared",
            )
        result = await presentation_ack(
            binding=session.activation.binding,
            capability=session.activation.capability,
            request_id=self._native_request_id(session, "barge"),
            cursor=cursor,
            fence_response=(record.downlink_response if cursor is None else None),
            action_id=action_id,
        )
        expected_kind = "played_cursor" if cursor is not None else "response_fence"
        if (
            not isinstance(result, Mapping)
            or result.get("kind") != expected_kind
            or result.get("status") != "observed"
            or type(result.get("applied")) is not bool
            or result.get("cancel_command_id") != action_id
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_BARGE_ADMISSION_INVALID",
                "Native Runtime barge admission is not exact",
            )
        if result.get("applied") is False:
            return False
        self._retain_native_barge_fence(session, record.downlink_response)
        await source.aclose()
        if cursor is None:
            await session.engine.stop_foreground(record.downlink_response)
        else:
            await session.engine.cancel_response(cursor)
        return True

    def _retain_native_barge_fence(
        self, session: _NativeMediaSession, response: ResponseRef
    ) -> None:
        with self._lock:
            retained = session.generated_text.get(response)
            if retained is not None and retained["state"] not in {"interrupted", "played"}:
                retained["state"] = "interrupted"
                self._revise_native_text(session, retained)
            session.barge_fenced_responses[response] = None
            session.barge_fenced_responses.move_to_end(response)
            while len(session.barge_fenced_responses) > self._capacity:
                session.barge_fenced_responses.popitem(last=False)

    def _native_response_is_barge_fenced(
        self, session: _NativeMediaSession, response: ResponseRef
    ) -> bool:
        with self._lock:
            return response in session.barge_fenced_responses

    @staticmethod
    def _native_barge_action_id(
        record: _MediaAuthority,
        receipt: MediaPlaybackStopReceipt,
        cursor: NativePresentationCursor | None,
    ) -> str:
        digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "lease_id": record.binding.lease_id,
                    "response": {
                        "interaction_id": record.downlink_response.interaction_id,
                        "response_id": record.downlink_response.response_id,
                        "response_generation": (
                            record.downlink_response.response_generation
                        ),
                    }
                    if record.downlink_response is not None
                    else None,
                    "unit_id": receipt.unit_id,
                    "confirmed_through_seq": receipt.confirmed_through_seq,
                    "provider_item_id": (
                        None if cursor is None else cursor.provider_item_id
                    ),
                    "content_index": None if cursor is None else cursor.content_index,
                    "audio_end_ms": None if cursor is None else cursor.audio_end_ms,
                }
            )
        ).hexdigest()
        return f"native-barge-{digest}"

    @staticmethod
    def _native_session_key(
        record: _MediaAuthority,
    ) -> tuple[str, str, str, str, int]:
        return (
            record.binding.session_id,
            record.binding.connection_id,
            record.binding.interaction_id,
            record.product_activation_id,
            record.product_activation_generation,
        )

    @staticmethod
    def _native_request_id(session: _NativeMediaSession, kind: str) -> str:
        session.request_ordinal += 1
        digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "key": list(session.key),
                    "ordinal": session.request_ordinal,
                    "kind": kind,
                }
            )
        ).hexdigest()
        return f"native-media-{digest}"

    @staticmethod
    def _native_playout_request_sha256(value: Mapping[str, object]) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    field_name: value.get(field_name)
                    for field_name in _PLAYOUT_RECEIPT_REQUEST_FIELDS
                }
            )
        ).hexdigest()

    def _retain_native_playout_replay(
        self,
        *,
        session_key: tuple[str, str, str, str, int],
        response: ResponseRef,
        unit_id: str,
        receipt: Mapping[str, object],
    ) -> None:
        replay_key = (session_key, response, unit_id)
        self._native_playout_replays[replay_key] = _NativePlayoutReplay(
            request_sha256=self._native_playout_request_sha256(receipt),
            receipt=dict(receipt),
        )
        self._native_playout_replays.move_to_end(replay_key)
        while len(self._native_playout_replays) > self._capacity:
            self._native_playout_replays.popitem(last=False)

    def _consume_native_task(
        self, record: _MediaAuthority, task: asyncio.Task[None]
    ) -> None:
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error is not None:
            reason = getattr(error, "reason_id", getattr(error, "reason", "UNKNOWN"))
            key = self._native_session_keys_by_record.get(record.record_id)
            session = self._native_sessions.get(key) if key is not None else None
            if session is not None:
                response = session.delivery_response if task is session.delivery_task else None
                profile_event("native_media_failure", **identity_fields(session.activation.binding, response),
                              stage="media.delivery" if task is session.delivery_task else "media.provider",
                              reason=reason, turn_id=session.foreground_turn_id, outcome="failed")
                if session.failure_reason is None:
                    session.failure_reason = reason
                    if session.foreground_turn_id is not None:
                        self._native_request_state(session, "failed", session.foreground_turn_id,
                                                   reason, retain_for_close=True)
                for snapshot in session.generated_text.values():
                    if snapshot["state"] == "generating":
                        snapshot["state"] = "interrupted"
                        self._revise_native_text(session, snapshot)
            _LOGGER.error(
                "live_voice_native_media_task_failed reason=%s",
                getattr(error, "reason_id", getattr(error, "reason", "UNKNOWN")),
                exc_info=(type(error), error, error.__traceback__),
            )
            self._schedule_native_close(record)

    @property
    def streaming_observability(self) -> LiveVoiceObservabilityCollector | None:
        return self._streaming_observability

    def close_streaming_observability(self) -> None:
        owner = self._streaming_observability_owner
        if owner is not None:
            owner.close()

    @property
    def media_leaf_cleanup_snapshot(self) -> DedicatedMediaLeafCleanupSnapshot:
        return self._media_leaf_cleanup_owner.snapshot

    async def retry_media_leaf_cleanup(self, *, timeout_seconds: float = 1.0) -> bool:
        return await self._media_leaf_cleanup_owner.retry_cleanup(
            timeout_seconds=timeout_seconds
        )

    async def close_media_leaf_cleanup(self, *, timeout_seconds: float = 1.0) -> bool:
        return await self._media_leaf_cleanup_owner.close(
            timeout_seconds=timeout_seconds
        )

    def set_provider_available(self, value: bool) -> None:
        self._batch_provider_available = value is True

    async def prepare_streaming_provider(self) -> None:
        if not self.enabled:
            return
        owner = self._streaming_recognition_owner
        if owner is None:
            return
        try:
            available = await owner.available()
        except asyncio.CancelledError:
            raise
        except Exception:
            available = False
        with self._lock:
            self._streaming_provider_available = available
            fact = owner.selection_degradation
            self._streaming_selection_degradation = (
                {
                    "reason_id": StreamingRecognitionFallbackReason.CONFIGURATION_UNAVAILABLE.value,
                    "fallback_tier": (
                        SpeechRouteTier.BATCH.value
                        if self._batch_provider_available
                        else SpeechRouteTier.TEXT.value
                    ),
                    "visible": True,
                    "x_obs_event": None,
                    "x_obs_metric": None,
                }
                if not available and fact is None
                else (
                    None
                    if fact is None
                    else {
                        "reason_id": fact.get("reason"),
                        "fallback_tier": fact.get("to_tier"),
                        "visible": fact.get("visible"),
                        # Startup has no capture/interaction record from which
                        # an exact X-OBS binding can be emitted.
                        "x_obs_event": None,
                        "x_obs_metric": None,
                    }
                )
            )

    def configure_streaming_recognition(
        self,
        owner: StreamingRecognitionRouteOwner,
        *,
        receipt_issuer: Callable[..., Awaitable[str]],
    ) -> None:
        if not isinstance(owner, StreamingRecognitionRouteOwner):
            raise TypeError("streaming recognition owner is invalid")
        if not callable(receipt_issuer):
            raise TypeError("streaming recognition receipt issuer is invalid")
        with self._lock:
            if self._records:
                raise RuntimeError(
                    "streaming recognition must be configured before use"
                )
            self._streaming_recognition_owner = owner
            self._streaming_receipt_issuer = receipt_issuer

    def configure_streaming_synthesis(
        self,
        owner: StreamingSynthesisRouteOwner,
        *,
        observability: LiveVoiceObservabilityCollector | None = None,
    ) -> None:
        if not self.enabled:
            raise RuntimeError("streaming synthesis cannot attach to disabled media")
        if not isinstance(owner, StreamingSynthesisRouteOwner):
            raise TypeError("streaming synthesis requires its route owner")
        if observability is not None and not isinstance(
            observability, LiveVoiceObservabilityCollector
        ):
            raise TypeError("streaming synthesis observability must be typed")
        if self._streaming_synthesis_owner is not None:
            raise RuntimeError("streaming synthesis is already configured")
        self._streaming_synthesis_owner = owner
        self._streaming_synthesis_observability = observability
        if observability is not None:
            self._streaming_diagnostic_owner = _StreamingSynthesisDiagnosticOwner(
                self._observe_streaming_outcome
            )

    @property
    def streaming_diagnostics_cleanup_complete(self) -> bool | None:
        return self._streaming_diagnostics_cleanup_complete

    def close_streaming_diagnostics(self) -> bool:
        owner = self._streaming_diagnostic_owner
        if owner is None:
            self._streaming_diagnostics_cleanup_complete = True
            return True
        complete = owner.close()
        self._streaming_diagnostics_cleanup_complete = complete
        return complete

    def _observe_streaming_outcome(
        self,
        context: _StreamingObservationContext,
        outcome: StreamingSynthesisOutcome,
    ) -> None:
        collector = self._streaming_synthesis_observability
        if collector is None:
            return
        try:
            identity = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "operation_id": context.operation_id,
                        "binding_ref": outcome.request_binding_ref,
                        "reason": outcome.reason.value
                        if outcome.reason
                        else "completed",
                    }
                )
            ).hexdigest()[:32]
            observed_at = (
                datetime.now(UTC)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            observed_monotonic = self._monotonic()
            binding = {
                "correlation_id": context.correlation_id,
                "interaction_id": context.response.interaction_id,
                "response_id": context.response.response_id,
                "response_generation": context.response.response_generation,
            }
            provider_id = outcome.provider_id
            if outcome.completed:
                collector.emit_observation(
                    {
                        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                        "event_id": f"tts-completed-{identity}",
                        "event_name": "segment.completed",
                        "segment_name": "speech.synthesis",
                        "observed_at": observed_at,
                        "monotonic_ms": observed_monotonic * 1000,
                        "binding": binding,
                        "route": {
                            "implementation_class": "formal",
                            "owner_module": "gateway.streaming_synthesis",
                            "capability_provider": provider_id,
                            "contract_version": LIVE_VOICE_CONTRACT_VERSION,
                            "reason_code": None,
                        },
                        "source_component": "gateway.streaming_synthesis",
                        "state": "terminal",
                        "outcome": "completed",
                        "duration_ms": max(
                            0.0,
                            (observed_monotonic - context.started_monotonic) * 1000,
                        ),
                    }
                )
                return
            fact = outcome.fact
            if fact is None or not fact.visible or fact.x_obs_metric is None:
                # Route abort, successor fencing, and owner shutdown are normal
                # controls, not Provider degradation. The route owner already
                # classifies these as content-free control facts.
                return
            fallback_route = {
                "implementation_class": "fallback",
                "owner_module": "gateway.streaming_synthesis",
                "capability_provider": provider_id,
                "contract_version": None,
                "reason_code": "ROUTE_FALLBACK",
            }
            collector.emit_observation(
                {
                    "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                    "event_id": f"tts-degraded-{identity}",
                    "event_name": "degradation.activated",
                    "segment_name": "system.degradation",
                    "observed_at": observed_at,
                    "monotonic_ms": self._monotonic() * 1000,
                    "binding": binding,
                    "route": fallback_route,
                    "source_component": "gateway.streaming_synthesis",
                    "reason_code": "DEGRADED",
                }
            )
            collector.emit_metric(
                {
                    "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                    "measurement_id": f"tts-degraded-metric-{identity}",
                    "metric_name": "live_voice.degradation_total",
                    "metric_kind": "counter",
                    "unit": "count",
                    "value": 1,
                    "observed_at": observed_at,
                    "binding": binding,
                    "route": fallback_route,
                    "segment_name": "system.degradation",
                    "implementation_class": "fallback",
                    "reason_code": "DEGRADED",
                }
            )
        except BaseException:
            _LOGGER.warning(
                "live_voice_streaming_tts_diagnostic_dropped reason=EMISSION_FAILED"
            )
            # X-OBS must never block or change Speech/media business behavior.
            return

    def _schedule_streaming_outcome(
        self,
        context: _StreamingObservationContext,
        outcome: StreamingSynthesisOutcome,
    ) -> None:
        owner = self._streaming_diagnostic_owner
        if owner is not None:
            owner.submit(context, outcome)

    def _release_stream_source(self, record: _MediaAuthority) -> None:
        source = record.downlink_stream_source
        record.downlink_stream_source = None
        if source is None:
            return
        try:
            task = asyncio.create_task(
                source.aclose(), name="live-voice-product-tts-source-close"
            )
        except RuntimeError:
            return
        self._stream_cleanup_tasks.add(task)
        task.add_done_callback(self._consume_stream_cleanup)

    def _consume_stream_cleanup(self, task: asyncio.Task[None]) -> None:
        self._stream_cleanup_tasks.discard(task)
        try:
            task.exception()
        except BaseException:
            return

    def activate(
        self,
        *,
        params: Mapping[str, object],
        request_origin: str | None,
        connection_id: str,
        user_id: str | None = None,
    ) -> dict[str, object]:
        if not self.enabled:
            return {"status": "disabled", "reason_id": "MEDIA_FEATURE_DISABLED"}
        native_selected = self._native_runtime_client is not None
        if not native_selected and not (
            self._batch_provider_available or self._streaming_provider_available
        ):
            return {
                "status": "unavailable",
                "reason_id": "MEDIA_PROVIDER_UNAVAILABLE",
            }
        expected_keys = {
            "session_id",
            "interaction_id",
            "correlation_id",
            "activation_id",
            "activation_generation",
            "capture_id",
            "capture_generation",
            "track_id",
            "sample_rate_hz",
            "locale",
        }
        requests_end_of_turn = "end_of_turn_capability" in params
        optional_keys = {
            "end_of_turn_capability",
            "recognition_predecessor_subject_id",
        }
        if not expected_keys <= set(params) or not set(params) <= (
            expected_keys | optional_keys
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ACTIVATION", "media activation fields are not closed"
            )
        requested_end_of_turn = params.get("end_of_turn_capability")
        if (
            requests_end_of_turn
            and requested_end_of_turn != MEDIA_END_OF_TURN_CAPABILITY
        ):
            raise MediaTransportViolation(
                "MEDIA_END_OF_TURN_CAPABILITY_MISMATCH",
                "requested end-of-turn capability is unsupported",
            )
        recognition_predecessor_subject_id = (
            _required_id(
                params.get("recognition_predecessor_subject_id"),
                "recognition_predecessor_subject_id",
            )
            if "recognition_predecessor_subject_id" in params
            else None
        )
        owner = self._streaming_recognition_owner
        end_of_turn_available = bool(
            requests_end_of_turn
            and self.end_of_turn_enabled
            and self._streaming_provider_available
            and owner is not None
            and owner.end_of_turn_available
        )
        if request_origin is None or not is_allowed_browser_origin(request_origin):
            raise MediaTransportViolation(
                "MEDIA_ORIGIN_REJECTED", "media activation requires an allowed Origin"
            )
        session_id = _required_id(params["session_id"], "session_id")
        interaction_id = _required_id(params["interaction_id"], "interaction_id")
        correlation_id = _required_id(params["correlation_id"], "correlation_id")
        activation_id = _required_id(params["activation_id"], "activation_id")
        activation_generation = _safe_uint(
            params["activation_generation"], "activation_generation"
        )
        capture_id = _required_id(params["capture_id"], "capture_id")
        capture_generation = _safe_uint(
            params["capture_generation"], "capture_generation"
        )
        track_id = _required_id(params["track_id"], "track_id")
        sample_rate_hz = _safe_uint(params["sample_rate_hz"], "sample_rate_hz")
        if not 8_000 <= sample_rate_hz <= 192_000 or sample_rate_hz % 50:
            raise MediaTransportViolation(
                "MEDIA_INVALID_ACTIVATION", "sample_rate_hz is invalid"
            )
        locale = _required_id(params["locale"], "locale")
        if locale not in _LOCALES:
            raise MediaTransportViolation(
                "MEDIA_INVALID_ACTIVATION", "locale is not enabled for W2"
            )
        # The Web ``user_id`` is a browser/header/query comparison claim.  The
        # exact server-minted WebSocket connection owns this transport
        # capability; a client claim can neither mint nor transfer authority.
        owner_connection_id = _required_id(connection_id, "connection_id")

        now = self._monotonic()
        with self._lock:
            self._prune(now)
            trusted_activation = self._product_activations.get(
                (session_id, owner_connection_id, interaction_id)
            )
            if (
                trusted_activation is None
                or trusted_activation.connection_id != owner_connection_id
                or trusted_activation.correlation_id != correlation_id
                or trusted_activation.activation_id != activation_id
                or trusted_activation.activation_generation != activation_generation
                or now > trusted_activation.expires_at
            ):
                raise MediaTransportViolation(
                    "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED",
                    "media activation requires the exact accepted product P2 route",
                )
        native_activation = None
        native_browser_descriptor: dict[str, object] = {}
        if native_selected:
            resolver = getattr(self._native_runtime_client, "activation_for", None)
            if callable(resolver):
                native_activation = resolver(
                    session_id=session_id,
                    interaction_id=interaction_id,
                    connection_id=owner_connection_id,
                )
            if (
                not isinstance(native_activation, GatewayNativeActivation)
                or native_activation.binding.scope.session_id != session_id
                or native_activation.binding.interaction_id != interaction_id
                or native_activation.binding.correlation_id != correlation_id
                or native_activation.binding.activation_id != activation_id
                or native_activation.binding.activation_generation
                != activation_generation
                or native_activation.connection_id != owner_connection_id
            ):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_ACTIVATION_UNAVAILABLE",
                    "Native media requires the exact private Runtime activation",
                )
            projector = getattr(
                self._native_runtime_client, "browser_descriptor_for", None
            )
            descriptor = (
                projector(
                    session_id=session_id,
                    interaction_id=interaction_id,
                    connection_id=owner_connection_id,
                )
                if callable(projector)
                else None
            )
            if (
                not isinstance(descriptor, Mapping)
                or set(descriptor) != {"contract_version", "engine", "model"}
                or descriptor.get("contract_version")
                != NATIVE_INTERACTION_CONTRACT_VERSION
                or descriptor.get("engine") != "openai-realtime-native"
            ):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_DESCRIPTOR_UNAVAILABLE",
                    "Native media requires the exact public Engine descriptor",
                )
            native_browser_descriptor = {
                NATIVE_BROWSER_DESCRIPTOR_KEY: {
                    "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
                    "engine": "openai-realtime-native",
                    "model": _required_id(descriptor.get("model"), "native model"),
                }
            }
        ticket = secrets.token_urlsafe(32)
        record_id = f"media-record-{secrets.token_hex(16)}"
        subject_id = f"live-voice-media:{secrets.token_hex(16)}"
        binding = MediaAuthorityBinding(
            lease_id=f"media-lease-{secrets.token_hex(16)}",
            authority_evidence_id=f"media-authority-{secrets.token_hex(16)}",
            connection_id=owner_connection_id,
            connection_epoch=0,
            session_id=session_id,
            media_session_id=f"media-session-{secrets.token_hex(16)}",
            interaction_id=interaction_id,
            track_id=track_id,
            correlation_id=correlation_id,
            direction=MediaDirection.UPLINK,
            generation=MediaGenerationBinding(
                MediaGenerationKind.CAPTURE, capture_id, capture_generation
            ),
            frame_format=MediaFrameFormat(
                sample_rate_hz=sample_rate_hz,
                samples_per_channel=sample_rate_hz // 50,
            ),
        )
        record = _MediaAuthority(
            record_id=record_id,
            subject_id=subject_id,
            expected_origin=request_origin,
            product_activation_id=activation_id,
            product_activation_generation=activation_generation,
            binding=binding,
            locale=locale,
            end_of_turn_capability=(
                MEDIA_END_OF_TURN_CAPABILITY if end_of_turn_available else None
            ),
            recognition_predecessor_subject_id=(
                recognition_predecessor_subject_id
            ),
            issued_at=now,
            ticket_expires_at=now + self._ticket_ttl,
            authority_expires_at=now + self._authority_ttl,
            native_activation=native_activation,
        )
        with self._lock:
            self._prune(now)
            if self._media_capacity_in_use() >= self._capacity:
                raise MediaTransportViolation(
                    "MEDIA_ROUTE_CAPACITY_EXCEEDED", "media route capacity is full"
                )
            if recognition_predecessor_subject_id is not None:
                predecessor_id = self._subjects.get(
                    (session_id, recognition_predecessor_subject_id)
                )
                predecessor = self._records.get(predecessor_id or "")
                if (
                    predecessor is None
                    or predecessor.subject_id
                    != recognition_predecessor_subject_id
                    or predecessor.binding.direction is not MediaDirection.UPLINK
                    or predecessor.binding.connection_id != owner_connection_id
                    or predecessor.expected_origin != request_origin
                    or predecessor.binding.session_id != session_id
                    or predecessor.binding.interaction_id != interaction_id
                    or predecessor.binding.correlation_id != correlation_id
                    or predecessor.product_activation_id != activation_id
                    or predecessor.product_activation_generation
                    != activation_generation
                    or predecessor.binding.generation.id == capture_id
                    or predecessor.binding.generation.value == capture_generation
                    or predecessor.binding.track_id == track_id
                    or predecessor.binding.frame_format.sample_rate_hz
                    != sample_rate_hz
                    or predecessor.locale != locale
                    or not predecessor.recognition_continuation_predecessor
                    or predecessor.recognition_predecessor_subject_id is not None
                    or predecessor.recognition_continuation_successor_subject_id
                    is not None
                    or not predecessor.ticket_consumed
                    or not predecessor.route_completed
                    or predecessor.accepted_frames <= 0
                    or predecessor.recognition_content_sha256 is None
                    or now > predecessor.authority_expires_at
                    or not self._has_retained_product_activation(predecessor, now)
                ):
                    raise MediaTransportViolation(
                        "MEDIA_RECOGNITION_PREDECESSOR_UNTRUSTED",
                        "continued recognition requires the exact completed predecessor",
                    )
                predecessor.recognition_continuation_successor_subject_id = subject_id
            # Product P1 opens the replacement uplink after the authoritative
            # response downlink exists and before playout begins. That exact
            # overlap is the only capture profile that receives the wider VAD
            # prefix; ordinary turns keep the provider default.
            record.barge_in_capture = any(
                candidate.binding.direction is MediaDirection.DOWNLINK
                and not candidate.route_completed
                and candidate.binding.session_id == session_id
                and candidate.binding.interaction_id == interaction_id
                and candidate.binding.correlation_id == correlation_id
                and candidate.product_activation_id == activation_id
                and candidate.product_activation_generation == activation_generation
                and candidate.downlink_response is not None
                and now <= candidate.authority_expires_at
                for candidate in self._records.values()
            )
            self._records[record_id] = record
            self._pending_tickets[ticket] = record_id
            self._subjects[(session_id, subject_id)] = record_id
        route_descriptor = {"endpoint_path": MEDIA_ROUTE_PATH, "media_ticket": ticket}
        streaming_descriptor = (
            {}
            if self._streaming_recognition_owner is None
            else {
                "streaming_recognition": self._streaming_provider_available,
                "streaming_degradation": self._streaming_selection_degradation,
            }
        )
        end_of_turn_descriptor: dict[str, object] = {}
        if requests_end_of_turn:
            if end_of_turn_available:
                end_of_turn_descriptor = {
                    "end_of_turn": {
                        "status": "active",
                        "capability_version": MEDIA_END_OF_TURN_CAPABILITY,
                        "detector": "server_vad",
                        "create_response": False,
                        "interrupt_response": False,
                    }
                }
            else:
                reason_id = (
                    "MEDIA_END_OF_TURN_FEATURE_OFF"
                    if not self.end_of_turn_enabled
                    else "MEDIA_END_OF_TURN_PROVIDER_UNAVAILABLE"
                )
                _LOGGER.warning(
                    "live_voice_end_of_turn_degradation reason=%s target=manual visible=true",
                    reason_id,
                )
                end_of_turn_descriptor = {
                    "end_of_turn": {
                        "status": "fallback",
                        "requested_capability": MEDIA_END_OF_TURN_CAPABILITY,
                        "reason_id": reason_id,
                        "fallback": "manual",
                        "visible": True,
                    }
                }
        return {
            "status": "active",
            "reason_id": "MEDIA_ROUTE_TICKET_ISSUED",
            "subject_id": subject_id,
            **route_descriptor,
            "subprotocol": MEDIA_SUBPROTOCOL,
            "ticket_ttl_ms": int(self._ticket_ttl * 1000),
            **streaming_descriptor,
            **end_of_turn_descriptor,
            **native_browser_descriptor,
            "binding": _binding_payload(binding),
            "privacy": {
                "raw_audio_persisted": False,
                "raw_audio_logged": False,
                "memory_only": True,
            },
        }

    def consume_ticket(
        self,
        ticket: str,
        *,
        request_origin: str | None,
        claimed_binding: MediaAuthorityBinding | None = None,
    ) -> _MediaAuthority | None:
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            # Ticket lookup scans the bounded pending index and uses a
            # constant-time comparison. A successful capability is removed
            # immediately; the authority record remains reachable by subject.
            matched_ticket: str | None = None
            try:
                candidate = ticket.encode("utf-8") if isinstance(ticket, str) else b""
            except UnicodeEncodeError:
                candidate = b""
            for pending_ticket in self._pending_tickets:
                if hmac.compare_digest(pending_ticket.encode("utf-8"), candidate):
                    matched_ticket = pending_ticket
            if matched_ticket is None:
                return None
            record_id = self._pending_tickets.get(matched_ticket)
            record = self._records.get(record_id or "")
            if (
                record is None
                or record.ticket_consumed
                or now > record.ticket_expires_at
                or request_origin != record.expected_origin
                or not is_allowed_browser_origin(request_origin)
                or (claimed_binding is not None and claimed_binding != record.binding)
            ):
                return None
            assert matched_ticket is not None
            if isinstance(record.downlink_stream_source, task_preparation.PreparedNotificationSource):
                try:
                    record.downlink_stream_source.attach()
                except task_preparation.PreparationViolation:
                    self._reconcile_task_preparations()
                    return None
            self._pending_tickets.pop(matched_ticket, None)
            record.ticket_consumed = True
            return record

    def start_streaming_recognition(self, record: _MediaAuthority) -> None:
        """Start Provider allocation without delaying browser media attach."""

        if record.binding.direction is not MediaDirection.UPLINK:
            return
        loop = asyncio.get_running_loop()
        with self._lock:
            if (
                self._records.get(record.record_id) is not record
                or not record.ticket_consumed
                or record.route_completed
            ):
                return
            if record.streaming_recognition_ready is not None:
                return
            record.streaming_recognition_ready = loop.create_future()
            record.streaming_started_at = self._monotonic()
            owner = self._streaming_recognition_owner
        if owner is None:
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.CONFIGURATION_UNAVAILABLE
                ),
            )
            return
        detection = (
            (
                RecognitionTurnDetection.server_vad_barge_in()
                if record.barge_in_capture
                else RecognitionTurnDetection.server_vad_default()
            )
            if record.end_of_turn_capability == MEDIA_END_OF_TURN_CAPABILITY
            else RecognitionTurnDetection.manual()
        )
        request = authorize_stream_request(
            RecognitionStreamRequest(
                RecognitionStreamRef(
                    record.binding.media_session_id,
                    record.binding.generation.value,
                    CaptureRef(
                        record.binding.generation.id,
                        record.binding.generation.value,
                        record.binding.frame_format.sample_rate_hz,
                    ),
                ),
                detection,
            ),
            is_current=lambda: self._streaming_capture_current(record),
        )
        with self._lock:
            invalidated = (
                self._records.get(record.record_id) is not record
                or record.route_completed
                or record.streaming_recognition_outcome is not None
            )
            if not invalidated:
                record.streaming_recognition_authority = request.authority
        if invalidated:
            request.authority.revoke()
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.ROUTE_ABORTED
                ),
            )
            return
        task = loop.create_task(
            self._open_streaming_recognition(record, owner, request),
            name=f"live-voice-streaming-stt-open-{record.record_id}",
        )
        with self._lock:
            if (
                self._records.get(record.record_id) is record
                and not record.route_completed
                and record.streaming_recognition_begin_task is None
            ):
                record.streaming_recognition_begin_task = task
                return
        task.cancel()
        self._streaming_cleanup_tasks.add(task)
        task.add_done_callback(self._streaming_cleanup_tasks.discard)

    async def begin_streaming_recognition(self, record: _MediaAuthority) -> None:
        """Compatibility helper for callers that explicitly await Provider readiness."""

        self.start_streaming_recognition(record)
        with self._lock:
            task = record.streaming_recognition_begin_task
        if task is not None:
            await asyncio.shield(task)

    def _streaming_capture_current(self, record: _MediaAuthority) -> bool:
        with self._lock:
            now = self._monotonic()
            return (
                self._records.get(record.record_id) is record
                and record.ticket_consumed
                and record.streaming_recognition_outcome is None
                and now <= record.authority_expires_at
                and self._has_retained_product_activation(record, now)
            )

    async def _open_streaming_recognition(
        self,
        record: _MediaAuthority,
        owner: StreamingRecognitionRouteOwner,
        request: RecognitionStreamRequest,
    ) -> None:
        try:
            handle, fallback = await owner.begin(
                record.binding,
                turn_detection=request.turn_detection,
                request=request,
            )
        except asyncio.CancelledError:
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.ROUTE_ABORTED
                ),
            )
            raise
        except StreamingSpeechViolation as error:
            reason = (
                StreamingRecognitionFallbackReason.AUTHORITY_EXPIRED
                if error.reason
                in {
                    "SPEECH_AUTHORITY_REQUIRED",
                    "SPEECH_AUTHORITY_EXPIRED",
                    "SPEECH_AUTHORITY_CONSUMED",
                }
                else StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
            )
            self._retain_streaming_outcome(record, self._streaming_fallback(reason))
            return
        except Exception:
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE
                ),
            )
            return
        with self._lock:
            current = (
                self._records.get(record.record_id) is record
                and record.streaming_recognition_outcome is None
            )
            if current:
                record.streaming_recognition_handle = handle
                preopen_frames = tuple(record.streaming_preopen_frames)
                record.streaming_preopen_frames.clear()
            else:
                preopen_frames = ()
        if not current:
            if handle is not None:
                await owner.abort(handle)
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.ROUTE_ABORTED
                ),
            )
            return
        if handle is not None:
            record_audio_diagnostic("provider_open_ready", session_id=record.binding.session_id,
                media_session_id=record.binding.media_session_id,
                interaction_id=record.binding.interaction_id, correlation_id=record.binding.correlation_id,
                capture_id=record.binding.generation.id, lease_id=record.binding.lease_id,
                generation=record.binding.generation.value, preopen_frames=len(preopen_frames))
            for frame in preopen_frames:
                owner.offer(handle, frame)
        if fallback is not None:
            self._retain_streaming_outcome(record, fallback)

    async def wait_streaming_end_of_turn(
        self, record: _MediaAuthority
    ) -> MediaEndOfTurn:
        """Return one negotiated, content-free Provider-time EOT control."""

        try:
            await self._await_streaming_begin(record)
            with self._lock:
                owner = self._streaming_recognition_owner
                handle = record.streaming_recognition_handle
                current = (
                    self._records.get(record.record_id) is record
                    and not record.route_completed
                    and record.end_of_turn_capability == MEDIA_END_OF_TURN_CAPABILITY
                )
            if not current or owner is None or handle is None:
                raise RuntimeError("end-of-turn route is unavailable")
            observed: StreamingRecognitionEndOfTurn = await owner.wait_end_of_turn(
                handle
            )
            with self._lock:
                if (
                    self._records.get(record.record_id) is not record
                    or record.route_completed
                    or record.streaming_recognition_handle is not handle
                ):
                    raise RuntimeError("end-of-turn authority became stale")
            _LOGGER.info(
                "live_voice_end_of_turn_observed detector=server_vad "
                "timing_basis=provider_time provenance=adapter_derived"
            )
            record_audio_diagnostic("gateway_eot_ready", session_id=record.binding.session_id,
                media_session_id=record.binding.media_session_id,
                interaction_id=record.binding.interaction_id, correlation_id=record.binding.correlation_id,
                capture_id=record.binding.generation.id, lease_id=record.binding.lease_id,
                generation=record.binding.generation.value, provider_start_ms=observed.provider_start_ms,
                provider_end_ms=observed.provider_end_ms)
            emit_runtime_l0_milestone(
                component="gateway",
                milestone=L0Milestone.PROVIDER_EOT,
                binding=_l0_media_binding(record),
                event_nonce=record.record_id,
            )
            return MediaEndOfTurn(
                lease_id=record.binding.lease_id,
                generation=record.binding.generation.value,
                provider_start_ms=observed.provider_start_ms,
                provider_end_ms=observed.provider_end_ms,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._emit_streaming_observability(
                record,
                outcome=self._streaming_fallback(
                    StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
                ),
            )
            _LOGGER.warning(
                "live_voice_end_of_turn_degradation reason=EOT_PROVIDER_FAILED "
                "target=manual visible=true"
            )
            raise RuntimeError("end-of-turn Provider path failed") from None

    async def wait_streaming_speech_start(
        self, record: _MediaAuthority
    ) -> MediaSpeechStart:
        """Return one negotiated, content-free Provider speech-start control."""

        try:
            await self._await_streaming_begin(record)
            with self._lock:
                owner = self._streaming_recognition_owner
                handle = record.streaming_recognition_handle
                current = (
                    self._records.get(record.record_id) is record
                    and not record.route_completed
                    and record.end_of_turn_capability == MEDIA_END_OF_TURN_CAPABILITY
                )
            if not current or owner is None or handle is None:
                raise RuntimeError("speech-start route is unavailable")
            observed: StreamingRecognitionSpeechStart = await owner.wait_speech_start(
                handle
            )
            with self._lock:
                if (
                    self._records.get(record.record_id) is not record
                    or record.route_completed
                    or record.streaming_recognition_handle is not handle
                ):
                    raise RuntimeError("speech-start authority became stale")
            record_audio_diagnostic("gateway_speech_start_ready", session_id=record.binding.session_id,
                media_session_id=record.binding.media_session_id,
                interaction_id=record.binding.interaction_id, correlation_id=record.binding.correlation_id,
                capture_id=record.binding.generation.id, lease_id=record.binding.lease_id,
                generation=record.binding.generation.value, provider_start_ms=observed.provider_start_ms)
            return MediaSpeechStart(
                lease_id=record.binding.lease_id,
                generation=record.binding.generation.value,
                provider_start_ms=observed.provider_start_ms,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._emit_streaming_observability(
                record,
                outcome=self._streaming_fallback(
                    StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
                ),
            )
            raise RuntimeError("speech-start Provider path failed") from None

    def accept_streaming_frame(
        self, record: _MediaAuthority, frame: MediaAudioFrame
    ) -> None:
        cancel_begin = False
        with self._lock:
            if (
                self._records.get(record.record_id) is not record
                or record.route_completed
            ):
                return
            owner = self._streaming_recognition_owner
            handle = record.streaming_recognition_handle
            begin_task = record.streaming_recognition_begin_task
            if (
                owner is not None
                and handle is None
                and begin_task is not None
                and record.streaming_recognition_outcome is None
            ):
                if len(record.streaming_preopen_frames) < _MAX_STREAMING_PREOPEN_FRAMES:
                    record.streaming_preopen_frames.append(frame)
                else:
                    record.streaming_preopen_frames.clear()
                    cancel_begin = True
        if owner is not None and handle is not None:
            owner.offer(handle, frame)
        elif cancel_begin:
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED
                ),
            )
            assert begin_task is not None
            begin_task.cancel()

    async def finish_streaming_recognition(self, record: _MediaAuthority) -> None:
        with self._lock:
            begin_pending = (
                record.streaming_recognition_begin_task is not None
                and record.streaming_recognition_handle is None
                and record.streaming_recognition_outcome is None
            )
        if begin_pending:
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.PROVIDER_TIMEOUT
                ),
            )
        await self._settle_streaming_begin(record)
        owner = self._streaming_recognition_owner
        handle = record.streaming_recognition_handle
        if record.streaming_recognition_outcome is not None:
            return
        if owner is None or handle is None:
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.CONFIGURATION_UNAVAILABLE
                ),
            )
            return
        try:
            outcome = await owner.finish(handle)
        except asyncio.CancelledError:
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.ROUTE_ABORTED
                ),
            )
            raise
        except Exception:
            outcome = self._streaming_fallback(
                StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE
            )
        with self._lock:
            current = (
                self._records.get(record.record_id) is record
                and record.route_completed
                and record.recognition_content_sha256 is not None
                and record.accepted_frames > 0
            )
            record.streaming_recognition_handle = None
        if not current:
            self._retain_streaming_outcome(
                record,
                self._streaming_fallback(
                    StreamingRecognitionFallbackReason.ROUTE_ABORTED
                ),
            )
            return
        if (
            outcome.completed
            and outcome.final_text is not None
            and record.streaming_started_at is not None
        ):
            elapsed_ms = (self._monotonic() - record.streaming_started_at) * 1000.0
            emit_runtime_l0_milestone(
                component="gateway",
                milestone=L0Milestone.STT_FINAL_AVAILABLE,
                binding=_l0_media_binding(record),
                duration_ms=elapsed_ms if elapsed_ms >= 0.0 else None,
                event_nonce=record.record_id,
            )
        if (
            outcome.completed
            and record.recognition_predecessor_subject_id is None
            and not record.recognition_continuation_predecessor
        ):
            issuer = self._streaming_receipt_issuer
            if issuer is None or outcome.final_text is None:
                outcome = self._streaming_fallback(
                    StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
                )
            else:
                try:
                    receipt = await issuer(
                        operation_id=f"streaming-recognition-{record.binding.lease_id}",
                        capture_id=record.binding.generation.id,
                        capture_generation=record.binding.generation.value,
                        session_id=record.binding.session_id,
                        correlation_id=record.binding.correlation_id,
                        interaction_id=record.binding.interaction_id,
                        text=outcome.final_text,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    outcome = self._streaming_fallback(
                        StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
                    )
                else:
                    with self._lock:
                        if self._records.get(record.record_id) is record:
                            record.streaming_voice_commit_receipt = receipt
        self._retain_streaming_outcome(record, outcome)

    async def abort_streaming_recognition(self, record: _MediaAuthority) -> None:
        self._retain_streaming_outcome(
            record,
            self._streaming_fallback(StreamingRecognitionFallbackReason.ROUTE_ABORTED),
        )
        await self._settle_streaming_begin(record)
        with self._lock:
            owner = self._streaming_recognition_owner
            handle = record.streaming_recognition_handle
            record.streaming_recognition_handle = None
        if owner is not None and handle is not None:
            with suppress(Exception, asyncio.CancelledError):
                await owner.abort(handle)

    async def _await_streaming_begin(self, record: _MediaAuthority) -> None:
        """Observe the retained Provider open without cancelling or draining it.

        ``_settle_streaming_begin`` is teardown: it cancels an open nobody wants
        any more and drops the pre-open frames. End-of-turn arbitration starts
        one scheduling turn after ``start_streaming_recognition``, so calling
        that teardown here cancelled the very open it was waiting for and
        discarded the audio buffered before the Provider was ready, which
        aborted every real streaming recognition on this route.
        """

        with self._lock:
            task = record.streaming_recognition_begin_task
        if task is None or task.done():
            return
        # asyncio.wait never cancels on timeout; a Provider that misses this
        # bound stays owned by the finish/abort path.
        done, _pending = await asyncio.wait(
            {task}, timeout=_STREAMING_BEGIN_WAIT_SECONDS
        )
        if not done:
            return
        try:
            task.result()
        except (Exception, asyncio.CancelledError):
            return

    async def _settle_streaming_begin(self, record: _MediaAuthority) -> None:
        with self._lock:
            task = record.streaming_recognition_begin_task
            record.streaming_recognition_begin_task = None
            record.streaming_preopen_frames.clear()
        if task is None:
            return
        if not task.done():
            task.cancel()
        done, pending = await asyncio.wait({task}, timeout=1.0)
        if pending:
            self._streaming_cleanup_tasks.add(task)
            task.add_done_callback(self._streaming_cleanup_tasks.discard)
            return
        try:
            task.result()
        except (Exception, asyncio.CancelledError):
            return

    async def streaming_recognition_result(
        self,
        *,
        params: Mapping[str, object],
        routed_session_id: str,
        connection_id: str,
        request_origin: str | None,
    ) -> dict[str, object]:
        expected_keys = {
            "session_id",
            "subject_id",
            "correlation_id",
            "interaction_id",
            "capture_id",
            "capture_generation",
            "track_id",
        }
        if set(params) != expected_keys:
            raise MediaTransportViolation(
                "MEDIA_INVALID_STREAMING_RESULT",
                "streaming recognition result fields are not closed",
            )
        session_id = _required_id(params.get("session_id"), "session_id")
        if session_id != routed_session_id:
            raise MediaTransportViolation(
                "MEDIA_SESSION_MISMATCH",
                "streaming recognition result must target the routed session",
            )
        subject_id = _required_id(params.get("subject_id"), "subject_id")
        correlation_id = _required_id(params.get("correlation_id"), "correlation_id")
        interaction_id = _required_id(params.get("interaction_id"), "interaction_id")
        capture_id = _required_id(params.get("capture_id"), "capture_id")
        capture_generation = _safe_uint(
            params.get("capture_generation"), "capture_generation"
        )
        track_id = _required_id(params.get("track_id"), "track_id")
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            record_id = self._subjects.get((session_id, subject_id))
            record = self._records.get(record_id or "")
            if (
                record is None
                or record.binding.direction is not MediaDirection.UPLINK
                or record.binding.connection_id != connection_id
                or record.expected_origin != request_origin
                or not is_allowed_browser_origin(request_origin)
                or record.binding.correlation_id != correlation_id
                or record.binding.interaction_id != interaction_id
                or record.binding.generation.id != capture_id
                or record.binding.generation.value != capture_generation
                or record.binding.track_id != track_id
                or record.recognition_predecessor_subject_id is not None
                or record.recognition_continuation_predecessor
                or not record.ticket_consumed
                or not record.route_completed
                or now > record.authority_expires_at
                or not self._has_retained_product_activation(record, now)
            ):
                raise MediaTransportViolation(
                    "MEDIA_STREAMING_RESULT_UNAUTHORIZED",
                    "streaming recognition result authority is absent or stale",
                )
            ready = record.streaming_recognition_ready
            immediate = record.streaming_recognition_outcome
        if immediate is None and ready is not None:
            try:
                immediate = await asyncio.wait_for(
                    asyncio.shield(ready),
                    timeout=_STREAMING_RESULT_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                immediate = self._streaming_fallback(
                    StreamingRecognitionFallbackReason.PROVIDER_TIMEOUT
                )
                self._retain_streaming_outcome(record, immediate)
                # The caller is about to authorize a product fallback.  Fence
                # the exact streaming stream first so it cannot later mint an
                # unreachable receipt or keep consuming Provider resources.
                await self.abort_streaming_recognition(record)
        if immediate is None:
            immediate = self._streaming_fallback(
                StreamingRecognitionFallbackReason.CONFIGURATION_UNAVAILABLE
            )
        with self._lock:
            if self._records.get(record.record_id) is not record:
                raise MediaTransportViolation(
                    "MEDIA_STREAMING_RESULT_UNAUTHORIZED",
                    "streaming recognition result authority is absent or stale",
                )
            receipt = record.streaming_voice_commit_receipt
        capture = {
            "capture_id": capture_id,
            "capture_generation": capture_generation,
            "track_id": track_id,
            "final": True,
        }
        if immediate.completed:
            if (
                immediate.final_text is None
                or immediate.provider is None
                or receipt is None
            ):
                raise MediaTransportViolation(
                    "MEDIA_STREAMING_RESULT_INCOMPLETE",
                    "streaming recognition result is incomplete",
                )
            result = {
                "status": "completed",
                "operation": "speech.recognize.stream",
                "capture": capture,
                "final_text": immediate.final_text,
                "raw_text": immediate.final_text,
                "commits_turn": False,
                "voice_commit_receipt": receipt,
                "provider": {
                    "provider_id": immediate.provider.provider_id,
                    "implementation_class": immediate.provider.implementation_class,
                    "fallback_from": immediate.provider.fallback_from,
                },
                "degradation": None,
            }
            self._emit_streaming_observability(
                record,
                outcome=immediate,
            )
            return result
        # A Provider adapter cannot know whether the product retained one
        # complete, bounded capture.  Batch replay is authorized here, and only
        # here, after the canonical media route sealed its exact digest.
        fallback_tier = (
            SpeechRouteTier.BATCH
            if (
                self._batch_provider_available
                and record.route_completed
                and record.accepted_frames > 0
                and record.recognition_content_sha256 is not None
                and immediate.reason
                not in {
                    StreamingRecognitionFallbackReason.ROUTE_ABORTED,
                    StreamingRecognitionFallbackReason.AUTHORITY_EXPIRED,
                }
            )
            else SpeechRouteTier.TEXT
        )
        reason_id = (
            immediate.reason.value
            if immediate.reason is not None
            else StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE.value
        )
        _LOGGER.warning(
            "live_voice_streaming_recognition_degradation reason=%s target=%s visible=true",
            reason_id,
            fallback_tier.value,
        )
        x_obs_event, x_obs_metric = self._emit_streaming_observability(
            record,
            outcome=immediate,
        )
        result = {
            "status": "fallback",
            "operation": "speech.recognize.stream",
            "capture": capture,
            "fallback_tier": fallback_tier.value,
            "reason_id": reason_id,
            "visible": True,
            "x_obs_event": x_obs_event,
            "x_obs_metric": x_obs_metric,
        }
        return result

    def _emit_streaming_observability(
        self,
        record: _MediaAuthority,
        *,
        outcome: StreamingRecognitionOutcome,
    ) -> tuple[StreamingXObsEvent | None, StreamingXObsMetric | None]:
        owner = self._streaming_observability_owner
        if owner is None:
            return None, None
        with record.streaming_observation_lock:
            if record.streaming_observation_emitted:
                return record.streaming_x_obs_event, record.streaming_x_obs_metric
            built = self._build_streaming_observability(record, outcome=outcome)
            if built is None:
                emitted: tuple[
                    StreamingXObsEvent | None, StreamingXObsMetric | None
                ] = (None, None)
            else:
                observation, metric = built
                emitted = (
                    (observation.event_name, metric.metric_name)
                    if owner.submit(observation, metric)
                    else (None, None)
                )
            record.streaming_x_obs_event, record.streaming_x_obs_metric = emitted
            record.streaming_observation_emitted = True
            return emitted

    def _build_streaming_observability(
        self,
        record: _MediaAuthority,
        *,
        outcome: StreamingRecognitionOutcome,
    ) -> tuple[LiveVoiceObservation, LiveVoiceMetric] | None:
        started_at = record.streaming_started_at
        now = self._monotonic()
        duration_ms = max(
            0.0,
            (now - (started_at if started_at is not None else now)) * 1000.0,
        )
        observed_at = (
            datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        binding = {
            "correlation_id": record.binding.correlation_id,
            "interaction_id": record.binding.interaction_id,
        }
        source_record_id = record.record_id
        try:
            if outcome.completed and outcome.provider is not None:
                route = {
                    "implementation_class": "formal",
                    "owner_module": "gateway.streaming_speech_route",
                    "capability_provider": outcome.provider.provider_id,
                    "contract_version": LIVE_VOICE_CONTRACT_VERSION,
                    "reason_code": None,
                }
                observation = create_observation(
                    {
                        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                        "event_id": f"{source_record_id}:stt-completed",
                        "event_name": "segment.completed",
                        "segment_name": "speech.recognition",
                        "observed_at": observed_at,
                        "monotonic_ms": now * 1000.0,
                        "binding": binding,
                        "route": route,
                        "source_component": "gateway.streaming_speech",
                        "source_record_id": source_record_id,
                        "state": "terminal",
                        "outcome": "completed",
                        "duration_ms": duration_ms,
                    }
                )
                metric = create_metric(
                    {
                        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                        "measurement_id": f"{source_record_id}:stt-latency",
                        "metric_name": "live_voice.segment_latency_ms",
                        "metric_kind": "histogram",
                        "unit": "milliseconds",
                        "value": duration_ms,
                        "observed_at": observed_at,
                        "binding": binding,
                        "route": route,
                        "segment_name": "speech.recognition",
                        "implementation_class": "formal",
                        "outcome": "completed",
                    }
                )
                return observation, metric
            route = {
                "implementation_class": "fallback",
                "owner_module": "gateway.streaming_speech_route",
                "capability_provider": (
                    outcome.provider.provider_id
                    if outcome.provider is not None
                    else None
                ),
                "contract_version": None,
                "reason_code": "ROUTE_FALLBACK",
            }
            if outcome.reason is StreamingRecognitionFallbackReason.ROUTE_ABORTED:
                event_name: StreamingXObsEvent = "degradation.activated"
                metric_name: StreamingXObsMetric = "live_voice.degradation_total"
                segment_name = "system.degradation"
                reason_code = "DEGRADED"
                error_code = None
            else:
                event_name = "failure.observed"
                metric_name = "live_voice.failure_total"
                segment_name = "speech.recognition"
                fallback_reason = outcome.reason or (
                    StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE
                )
                reason_code, error_code = {
                    StreamingRecognitionFallbackReason.PROVIDER_TIMEOUT: (
                        "TIMEOUT",
                        "TIMEOUT",
                    ),
                    StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL: (
                        "PROTOCOL_REJECTED",
                        "PROTOCOL_VIOLATION",
                    ),
                    StreamingRecognitionFallbackReason.CONFIGURATION_UNAVAILABLE: (
                        "UNAVAILABLE",
                        "CAPABILITY_UNAVAILABLE",
                    ),
                    StreamingRecognitionFallbackReason.FEATURE_OFF: (
                        "UNAVAILABLE",
                        "CAPABILITY_UNAVAILABLE",
                    ),
                }.get(
                    fallback_reason,
                    ("UNAVAILABLE", "UNAVAILABLE"),
                )
            observation_payload = {
                "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                "event_id": f"{source_record_id}:stt-degraded",
                "event_name": event_name,
                "segment_name": segment_name,
                "observed_at": observed_at,
                "monotonic_ms": now * 1000.0,
                "binding": binding,
                "route": route,
                "source_component": "gateway.streaming_speech",
                "source_record_id": source_record_id,
                "reason_code": reason_code,
            }
            metric_payload = {
                "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                "measurement_id": f"{source_record_id}:stt-degraded",
                "metric_name": metric_name,
                "metric_kind": "counter",
                "unit": "count",
                "value": 1,
                "observed_at": observed_at,
                "binding": binding,
                "route": route,
                "segment_name": segment_name,
                "implementation_class": "fallback",
                "reason_code": reason_code,
            }
            if error_code is not None:
                observation_payload["error_code"] = error_code
                metric_payload["error_code"] = error_code
            return (
                create_observation(observation_payload),
                create_metric(metric_payload),
            )
        except Exception:
            _LOGGER.warning(
                "live_voice_streaming_observability_unavailable reason=FACT_REJECTED"
            )
            return None

    def _retain_streaming_outcome(
        self, record: _MediaAuthority, outcome: StreamingRecognitionOutcome
    ) -> None:
        ready: asyncio.Future[StreamingRecognitionOutcome] | None
        with self._lock:
            if record.streaming_recognition_outcome is None:
                record.streaming_recognition_outcome = outcome
            retained = record.streaming_recognition_outcome
            ready = record.streaming_recognition_ready
        if ready is not None and not ready.done():
            ready.set_result(retained)

    def _streaming_fallback(
        self, reason: StreamingRecognitionFallbackReason
    ) -> StreamingRecognitionOutcome:
        return StreamingRecognitionOutcome(
            completed=False,
            final_text=None,
            provider=None,
            fallback_tier=(
                SpeechRouteTier.TEXT
                if reason
                in {
                    StreamingRecognitionFallbackReason.ROUTE_ABORTED,
                    StreamingRecognitionFallbackReason.AUTHORITY_EXPIRED,
                }
                else (
                    SpeechRouteTier.BATCH
                    if self._batch_provider_available
                    else SpeechRouteTier.TEXT
                )
            ),
            reason=reason,
        )

    def accept_frame(self, record: _MediaAuthority, frame: MediaAudioFrame) -> None:
        encoded = _pcm16(frame.samples)
        with self._lock:
            if (
                self._records.get(record.record_id) is not record
                or record.route_completed
            ):
                raise MediaTransportViolation(
                    "MEDIA_LEASE_CLOSED", "media capture route is already complete"
                )
            if len(record.pcm) + len(encoded) + 44 > _MAX_CAPTURE_WAV_BYTES:
                raise MediaTransportViolation(
                    "MEDIA_CAPTURE_LIMIT_EXCEEDED",
                    "capture exceeds the batch Speech limit",
                )
            record.pcm.extend(encoded)
            record.accepted_frames += 1

    def observe_uplink_frame_accepted(
        self,
        record: _MediaAuthority,
        acknowledgement: MediaAck,
        accepted_monotonic: float,
    ) -> None:
        """Log the content-free boundary after seq=0 is accepted."""

        if not isinstance(accepted_monotonic, (int, float)) or not math.isfinite(
            accepted_monotonic
        ):
            return
        with self._lock:
            if (
                self._records.get(record.record_id) is not record
                or record.route_completed
                or record.binding.direction is not MediaDirection.UPLINK
                or record.first_uplink_frame_accepted_diagnostic
                or acknowledgement.lease_id != record.binding.lease_id
                or acknowledgement.generation != record.binding.generation.value
                or acknowledgement.through_seq != 0
                or record.accepted_frames <= 0
            ):
                return
            record.first_uplink_frame_accepted_diagnostic = True
        self._log_first_frame_diagnostic(
            record,
            stage="gateway_frame_accepted",
            observed_monotonic=float(accepted_monotonic),
            reason="MEDIA_FRAME_ACCEPTED",
        )

    def observe_uplink_ack_sent(
        self, record: _MediaAuthority, acknowledgement: MediaAck
    ) -> None:
        """Retain the exact successful WebSocket ACK-send boundary for L0."""

        observed_monotonic = self._monotonic()
        observed_at = (
            datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        log_first_ack = False
        with self._lock:
            if (
                self._records.get(record.record_id) is not record
                or record.route_completed
                or record.binding.direction is not MediaDirection.UPLINK
                or acknowledgement.lease_id != record.binding.lease_id
                or acknowledgement.generation != record.binding.generation.value
                or acknowledgement.through_seq < 0
                or acknowledgement.through_seq >= record.accepted_frames
                or (
                    record.last_uplink_ack_through_seq is not None
                    and acknowledgement.through_seq < record.last_uplink_ack_through_seq
                )
            ):
                return
            record.last_uplink_ack_through_seq = acknowledgement.through_seq
            record.last_uplink_ack_observed_at = observed_at
            record.last_uplink_ack_monotonic_ms = observed_monotonic * 1_000.0
            record.last_uplink_ack_duration_ms = max(
                0.0, (observed_monotonic - record.issued_at) * 1_000.0
            )
            if (
                acknowledgement.through_seq == 0
                and not record.first_uplink_ack_sent_diagnostic
            ):
                record.first_uplink_ack_sent_diagnostic = True
                log_first_ack = True
        if log_first_ack:
            self._log_first_frame_diagnostic(
                record,
                stage="gateway_ack_sent",
                observed_monotonic=observed_monotonic,
                reason="MEDIA_ACK_SEND_SUCCEEDED",
            )
        if acknowledgement.through_seq % 50 == 0:
            record_audio_diagnostic("gateway_ack_sent", session_id=record.binding.session_id,
                media_session_id=record.binding.media_session_id,
                interaction_id=record.binding.interaction_id, correlation_id=record.binding.correlation_id,
                capture_id=record.binding.generation.id, lease_id=record.binding.lease_id,
                generation=record.binding.generation.value, frames_acked=acknowledgement.through_seq + 1,
                frame_count=record.accepted_frames, preopen_frames=len(record.streaming_preopen_frames))

    @staticmethod
    def _first_frame_scope_sha256(record: _MediaAuthority) -> str:
        source = "\x1f".join(
            (
                record.binding.session_id,
                record.binding.interaction_id,
                record.binding.correlation_id,
                record.binding.media_session_id,
                record.binding.track_id,
                record.binding.lease_id,
                record.binding.generation.kind.value,
                record.binding.generation.id,
                str(record.binding.generation.value),
            )
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    def _log_first_frame_diagnostic(
        self,
        record: _MediaAuthority,
        *,
        stage: str,
        observed_monotonic: float,
        reason: str,
    ) -> None:
        _MEDIA_FIRST_FRAME_DIAGNOSTIC_WORKER.submit(
            _MediaFirstFrameDiagnosticItem(
                stage=stage,
                scope_sha256=self._first_frame_scope_sha256(record),
                capture_generation=record.binding.generation.value,
                frame_seq=0,
                monotonic_ms=observed_monotonic * 1_000.0,
                elapsed_ms=max(
                    0.0, (observed_monotonic - record.issued_at) * 1_000.0
                ),
                outcome="success",
                reason=reason,
            )
        )

    def complete_route(
        self, record: _MediaAuthority, result: DedicatedMediaSocketLeafResult
    ) -> None:
        completed = False
        final_ack: tuple[str, float, float] | None = None
        with self._lock:
            record.route_completed = True
            record.recognition_continuation_predecessor = (
                getattr(result, "reason_id", None)
                is MediaDetachReason.RECOGNITION_CONTINUATION
            )
            if not result.activated or result.accepted_frames <= 0 or not record.pcm:
                record.pcm.clear()
            else:
                wav = _wav_bytes(
                    bytes(record.pcm), record.binding.frame_format.sample_rate_hz
                )
                audio_sha = hashlib.sha256(wav).hexdigest()
                record.recognition_content_sha256 = hashlib.sha256(
                    canonical_json_bytes(
                        {
                            "capture_id": record.binding.generation.id,
                            "capture_generation": record.binding.generation.value,
                            "track_id": record.binding.track_id,
                            "locale": record.locale,
                            "sample_rate_hz": record.binding.frame_format.sample_rate_hz,
                            "audio_sha256": audio_sha,
                        }
                    )
                ).hexdigest()
                record.pcm.clear()
                completed = True
                if (
                    record.last_uplink_ack_through_seq == result.accepted_frames - 1
                    and record.last_uplink_ack_observed_at is not None
                    and record.last_uplink_ack_monotonic_ms is not None
                    and record.last_uplink_ack_duration_ms is not None
                ):
                    final_ack = (
                        record.last_uplink_ack_observed_at,
                        record.last_uplink_ack_monotonic_ms,
                        record.last_uplink_ack_duration_ms,
                    )
        if completed:
            if final_ack is not None:
                observed_at, monotonic_ms, duration_ms = final_ack
                emit_runtime_l0_milestone(
                    component="gateway",
                    milestone=L0Milestone.LAST_FRAME_ACKED,
                    binding=_l0_media_binding(record),
                    observed_at=observed_at,
                    monotonic_ms=monotonic_ms,
                    duration_ms=duration_ms,
                    event_nonce=record.record_id,
                )
            emit_runtime_l0_milestone(
                component="gateway",
                milestone=L0Milestone.UPLINK_CLOSED,
                binding=_l0_media_binding(record),
                event_nonce=record.record_id,
            )

    def abort_route(self, record: _MediaAuthority) -> None:
        """Close one exceptional/cancelled media owner with zero retained audio."""

        with self._lock:
            if isinstance(record.downlink_stream_source, task_preparation.PreparedNotificationSource):
                record.downlink_stream_source.fence("TASK_PREPARATION_CANCELLED")
                self._reconcile_task_preparations()
            record.route_completed = True
            record.recognition_content_sha256 = None
            record.downlink_frames = ()
            self._release_stream_source(record)
            record.pcm.clear()

    def revoke(
        self,
        *,
        params: Mapping[str, object],
        routed_session_id: str,
        connection_id: str,
        user_id: str | None = None,
    ) -> dict[str, object]:
        """Idempotently revoke one exact browser-owned media/Speech authority."""

        expected_keys = {
            "session_id",
            "subject_id",
            "correlation_id",
            "interaction_id",
            "activation_id",
            "activation_generation",
        }
        if set(params) != expected_keys:
            raise MediaTransportViolation(
                "MEDIA_INVALID_CLOSE", "media close fields are not closed"
            )
        session_id = _required_id(params.get("session_id"), "session_id")
        if session_id != routed_session_id:
            raise MediaTransportViolation(
                "MEDIA_SESSION_MISMATCH",
                "media close must target the dispatcher-owned session",
            )
        subject_id = _required_id(params.get("subject_id"), "subject_id")
        correlation_id = _required_id(params.get("correlation_id"), "correlation_id")
        interaction_id = _required_id(params.get("interaction_id"), "interaction_id")
        activation_id = _required_id(params.get("activation_id"), "activation_id")
        activation_generation = _safe_uint(
            params.get("activation_generation"), "activation_generation"
        )
        owner_connection_id = _required_id(connection_id, "connection_id")
        binding = (
            session_id,
            correlation_id,
            interaction_id,
            activation_id,
            activation_generation,
            owner_connection_id,
        )
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            record_id = self._subjects.get((session_id, subject_id))
            record = self._records.get(record_id or "")
            if record is None:
                if self._revoked.get(subject_id) != binding:
                    raise MediaTransportViolation(
                        "MEDIA_CLOSE_BINDING_MISMATCH",
                        "media close does not own an active or revoked route",
                    )
            else:
                actual = (
                    record.binding.session_id,
                    record.binding.correlation_id,
                    record.binding.interaction_id,
                    record.product_activation_id,
                    record.product_activation_generation,
                    record.binding.connection_id,
                )
                if actual != binding:
                    raise MediaTransportViolation(
                        "MEDIA_CLOSE_BINDING_MISMATCH",
                        "media close does not own the exact route",
                    )
                owned_record_ids = [
                    candidate_record_id
                    for candidate_record_id, candidate in self._records.items()
                    if candidate.subject_id == subject_id
                    and candidate.binding.session_id == session_id
                    and candidate.binding.correlation_id == correlation_id
                    and candidate.binding.interaction_id == interaction_id
                    and candidate.product_activation_id == activation_id
                    and candidate.product_activation_generation == activation_generation
                    and candidate.binding.connection_id == owner_connection_id
                ]
                owned_records = [
                    self._records.pop(owned_record_id)
                    for owned_record_id in owned_record_ids
                ]
                self._subjects.pop((session_id, subject_id), None)
                for owned_record_id, owned in zip(
                    owned_record_ids, owned_records, strict=True
                ):
                    self._drop_pending_for_record_id(owned_record_id)
                    owned.route_completed = True
                    owned.recognition_content_sha256 = None
                    owned.synthesis_content_sha256.clear()
                    owned.playout_receipts.clear()
                    owned.playout_receipt_content_sha256.clear()
                    owned.downlink_results.clear()
                    owned.downlink_frames = ()
                    self._release_stream_source(owned)
                    owned.pcm.clear()
                    self._schedule_streaming_abort(owned)
                    self._schedule_native_close(owned)
                self._remember_revoked(subject_id, binding)
        self._reconcile_task_preparations()
        return {
            "status": "closed",
            "reason_id": "MEDIA_ROUTE_REVOKED",
            "session_id": session_id,
            "subject_id": subject_id,
            "correlation_id": correlation_id,
            "interaction_id": interaction_id,
            "activation_id": activation_id,
            "activation_generation": activation_generation,
        }

    def observe_agent_response(
        self,
        payload: Mapping[str, object],
        *,
        routed_session_id: str | None = None,
        user_id: str | None = None,
        connection_id: str | None = None,
        request_method: str | None = None,
    ) -> None:
        """Retain accepted P2 authority and exact Agent text response facts."""

        if payload.get("ok") is not True:
            return
        result = payload.get("result")
        if not isinstance(result, Mapping):
            return
        status = result.get("status")
        if status in {"active", "closed"}:
            expected_method = (
                "live_voice.composition.p2.activate"
                if status == "active"
                else "live_voice.composition.p2.close"
            )
            if request_method != expected_method or not _has_formal_p2_manifest(
                payload
            ):
                return
            try:
                session_id = _required_id(result.get("session_id"), "session_id")
                owner_connection_id = _required_id(connection_id, "connection_id")
                if session_id != _required_id(routed_session_id, "routed_session_id"):
                    return
                correlation_id = _required_id(
                    result.get("correlation_id"), "correlation_id"
                )
                interaction_id = _required_id(
                    result.get("interaction_id"), "interaction_id"
                )
                activation_id = _required_id(
                    result.get("activation_id"), "activation_id"
                )
                activation_generation = _safe_uint(
                    result.get("activation_generation"), "activation_generation"
                )
            except MediaTransportViolation:
                return
            key = (session_id, owner_connection_id, interaction_id)
            manifest_value = payload.get("product_composition")
            assert isinstance(manifest_value, Mapping)
            manifest = json.loads(canonical_json_bytes(manifest_value).decode("utf-8"))
            with self._lock:
                self._prune(self._monotonic())
                if status == "closed":
                    existing = self._product_activations.get(key)
                    if existing is not None and (
                        existing.correlation_id,
                        existing.activation_id,
                        existing.activation_generation,
                        existing.connection_id,
                    ) == (
                        correlation_id,
                        activation_id,
                        activation_generation,
                        owner_connection_id,
                    ):
                        self._product_activations.pop(key, None)
                        self._revoke_media_for_product_activation(existing)
                    return
                existing = self._product_activations.get(key)
                same_activation = existing is not None and (
                    existing.connection_id,
                    existing.correlation_id,
                    existing.activation_id,
                    existing.activation_generation,
                ) == (
                    owner_connection_id,
                    correlation_id,
                    activation_id,
                    activation_generation,
                )
                authority = _ProductActivationAuthority(
                    session_id=session_id,
                    connection_id=owner_connection_id,
                    correlation_id=correlation_id,
                    interaction_id=interaction_id,
                    activation_id=activation_id,
                    activation_generation=activation_generation,
                    product_composition=manifest,
                    expires_at=self._monotonic() + self._authority_ttl,
                    notification_fence=(
                        existing.notification_fence
                        if same_activation and existing is not None
                        else _NativeNotificationSequenceFence()
                    ),
                    streaming_response_authorities=(
                        existing.streaming_response_authorities
                        if same_activation and existing is not None
                        else []
                    ),
                )
                if existing is not None and not same_activation:
                    self._revoke_media_for_product_activation(existing)
                elif existing is not None:
                    authority.synthesis_content_sha256.update(existing.synthesis_content_sha256)
                self._product_activations[key] = authority
                self._product_activations.move_to_end(key)
                while len(self._product_activations) > self._capacity:
                    _key, evicted = self._product_activations.popitem(last=False)
                    self._revoke_media_for_product_activation(evicted)
            return
        if status == "presentation_failed_fallback_text":
            self._observe_task_presentation_failure(payload, result,
                routed_session_id=routed_session_id, connection_id=connection_id,
                request_method=request_method)
            return
        if status == "notification_batch":
            notifications = result.get("notifications")
            if (
                set(result) != _P2_NOTIFICATION_BATCH_KEYS
                or not isinstance(notifications, list)
                or not 1 <= len(notifications) <= _P2_NOTIFICATION_BATCH_MAX
            ):
                return
            try:
                batch_binding = (
                    _required_id(result.get("session_id"), "session_id"),
                    _required_id(result.get("correlation_id"), "correlation_id"),
                    _required_id(result.get("interaction_id"), "interaction_id"),
                    _required_id(result.get("activation_id"), "activation_id"),
                    _safe_uint(
                        result.get("activation_generation"), "activation_generation"
                    ),
                )
                validated: list[Mapping[str, object]] = []
                prior_publish_seq: int | None = None
                for notification in notifications:
                    if (
                        not isinstance(notification, Mapping)
                        or set(notification) != _P2_NOTIFICATION_ITEM_KEYS
                        or notification.get("status") != "notification"
                    ):
                        return
                    notification_binding = (
                        _required_id(notification.get("session_id"), "session_id"),
                        _required_id(
                            notification.get("correlation_id"), "correlation_id"
                        ),
                        _required_id(
                            notification.get("interaction_id"), "interaction_id"
                        ),
                        _required_id(
                            notification.get("activation_id"), "activation_id"
                        ),
                        _safe_uint(
                            notification.get("activation_generation"),
                            "activation_generation",
                        ),
                    )
                    if notification_binding != batch_binding:
                        return
                    publish_seq = notification.get("publish_seq")
                    if publish_seq is None:
                        if len(notifications) != 1:
                            return
                    else:
                        current_publish_seq = _safe_uint(
                            publish_seq, "notification.publish_seq"
                        )
                        if (
                            prior_publish_seq is not None
                            and current_publish_seq <= prior_publish_seq
                        ):
                            return
                        prior_publish_seq = current_publish_seq
                    validated.append(notification)
            except MediaTransportViolation:
                return
            for notification in validated[:-1]:
                event = notification.get("agent_event")
                if (
                    not isinstance(event, Mapping)
                    or event.get("event_type") not in {"chat.delta", "chat.reasoning"}
                    or event.get("error_reason") is not None
                    or notification.get("source_event") is not None
                    or notification.get("progress_event") is not None
                    or notification.get("presentation_unit") is not None
                    or notification.get("error_reason") is not None
                ):
                    return
            # Validate the complete bounded batch before retaining any media
            # authority. Reuse the exact legacy notification path so batching
            # changes transport efficiency, never Speech authorization rules.
            for notification in validated:
                self.observe_agent_response(
                    {"ok": True, "result": notification},
                    routed_session_id=routed_session_id,
                    user_id=user_id,
                    connection_id=connection_id,
                    request_method=request_method,
                )
            return
        if status != "notification":
            return
        try:
            owner_connection_id = _required_id(connection_id, "connection_id")
            routed_session = _required_id(routed_session_id, "routed_session_id")
        except MediaTransportViolation:
            return
        event = result.get("agent_event")
        response = result.get("response")
        unit = result.get("presentation_unit")
        if not all(isinstance(value, Mapping) for value in (event, response, unit)):
            return
        assert isinstance(event, Mapping)
        assert isinstance(response, Mapping)
        assert isinstance(unit, Mapping)
        surface = unit.get("surface")
        trusted_task_audio = (
            surface == "audio"
            and event.get("source_provenance") == "server.task_notification"
        )
        terminal_event_key = _terminal_preparation_event_key(result) if trusted_task_audio else None
        if (
            result.get("kind") != "agent.output"
            or event.get("event_type") != "chat.final"
            or (surface != "text" and not trusted_task_audio)
            or not isinstance(event.get("text"), str)
            or not str(event["text"]).strip()
        ):
            return
        try:
            session_id = _required_id(result.get("session_id"), "session_id")
            correlation_id = _required_id(
                result.get("correlation_id"), "correlation_id"
            )
            if set(response) != {
                "interaction_id",
                "response_id",
                "response_generation",
            }:
                return
            ref = ResponseRef(
                interaction_id=_required_id(
                    response.get("interaction_id"), "response.interaction_id"
                ),
                response_id=_required_id(
                    response.get("response_id"), "response.response_id"
                ),
                response_generation=_safe_uint(
                    response.get("response_generation"),
                    "response.response_generation",
                ),
            )
            unit_id = _required_id(unit.get("unit_id"), "unit_id")
        except Exception:
            return
        text = str(event["text"])
        with self._lock:
            now = self._monotonic()
            self._prune(now)
            activation_key = (session_id, owner_connection_id, ref.interaction_id)
            activation = self._product_activations.get(activation_key)
            if (
                session_id != routed_session
                or activation is None
                or activation.correlation_id != correlation_id
                or activation.activation_id != result.get("activation_id")
                or activation.activation_generation
                != result.get("activation_generation")
                or activation.connection_id != owner_connection_id
            ):
                return
            # A final notification is exact, server-originated proof that the
            # accepted P2 activation is still live on this connection. Renew
            # its bounded media trust before authorizing the corresponding
            # synthesis. Without this sliding renewal a turn begun just before
            # the fixed activation deadline can lose cleanup authority while
            # its downlink or successor capture is still completing.
            retained_synthesis_content = OrderedDict(
                activation.synthesis_content_sha256
            )
            self._prune_synthesis_transfers(retained_synthesis_content, now)
            for record in self._records.values():
                if (
                    record.binding.session_id != session_id
                    or session_id != routed_session
                    or record.binding.connection_id != owner_connection_id
                    or record.binding.correlation_id != correlation_id
                    or record.binding.interaction_id != ref.interaction_id
                    or result.get("activation_id") != record.product_activation_id
                    or result.get("activation_generation")
                    != record.product_activation_generation
                    or now > record.authority_expires_at
                    or not self._has_retained_product_activation(record, now)
                ):
                    continue
                content_sha256 = hashlib.sha256(
                    canonical_json_bytes(
                        {
                            "response": {
                                "interaction_id": ref.interaction_id,
                                "response_id": ref.response_id,
                                "response_generation": ref.response_generation,
                            },
                            "unit_id": unit_id,
                            "display_text": text,
                            "spoken_text": text,
                            "transforms": [],
                            "locale": record.locale,
                            "voice": None,
                            "required_sample_rate_hz": record.binding.frame_format.sample_rate_hz,
                        }
                    )
                ).hexdigest()
                transfer_key = (
                    ref,
                    unit_id,
                    record.locale,
                    record.binding.frame_format.sample_rate_hz,
                )
                existing_transfer = retained_synthesis_content.get(transfer_key)
                if (trusted_task_audio and ref.response_generation
                        <= activation.notification_fence.task_presentation_retired_generation
                        and not (existing_transfer is not None
                            and existing_transfer.task_notification
                            and not existing_transfer.presentation_retired
                            and existing_transfer.content_sha256 == content_sha256
                            and existing_transfer.terminal_event_key == terminal_event_key)):
                    # Task responses have one terminal unit and monotonic generations.
                    # Keep existing other grants; never reissue a retired/stale one.
                    continue
                transfer = self._retain_synthesis_transfer(
                    retained_synthesis_content,
                    key=transfer_key,
                    content_sha256=content_sha256,
                    now=now,
                    expires_at=now + self._authority_ttl,
                    task_notification=trusted_task_audio,
                    terminal_event_key=terminal_event_key,
                )
                if transfer is not None and not transfer.presentation_retired:
                    record.synthesis_content_sha256[(ref, unit_id)] = (
                        transfer.content_sha256
                    )
                elif (
                    existing_transfer is not None
                    and not existing_transfer.presentation_retired
                    and (existing_transfer.content_sha256 != content_sha256
                         or existing_transfer.terminal_event_key != terminal_event_key)
                ):
                    # A trusted final that changes the exact render digest
                    # fences the old operation.  The replacement gets a new
                    # unclaimed transfer rather than inheriting its claim.
                    retained_synthesis_content[transfer_key] = (
                        _SynthesisAuthorityTransfer(
                            content_sha256, now + self._authority_ttl,
                            task_notification=trusted_task_audio,
                            terminal_event_key=terminal_event_key,
                        )
                    )
                    record.synthesis_content_sha256[(ref, unit_id)] = content_sha256
            self._product_activations[activation_key] = _ProductActivationAuthority(
                session_id=activation.session_id,
                connection_id=activation.connection_id,
                correlation_id=activation.correlation_id,
                interaction_id=activation.interaction_id,
                activation_id=activation.activation_id,
                activation_generation=activation.activation_generation,
                product_composition=activation.product_composition,
                expires_at=now + self._authority_ttl,
                synthesis_content_sha256=retained_synthesis_content,
                notification_fence=activation.notification_fence,
                streaming_response_authorities=activation.streaming_response_authorities,
            )
            self._product_activations.move_to_end(activation_key)
            self._reconcile_task_preparations()

    def _observe_task_presentation_failure(self, payload: Mapping[str, object],
            result: Mapping[str, object], *, routed_session_id: str | None,
            connection_id: str | None, request_method: str | None) -> None:
        """Only the server's exact settled failure releases a Task audio handoff."""
        if (request_method != "live_voice.composition.p2.presentation.failed"
                or not _has_formal_p2_manifest(payload)
                or set(result) != {"status", "session_id", "correlation_id", "interaction_id",
                    "activation_id", "activation_generation", "response_id", "response_generation",
                    "surface", "unit_id", "failure_reason", "fallback", "replayed"}
                or result.get("surface") != "audio" or result.get("fallback") != "text"
                or not isinstance(result.get("failure_reason"), str)
                or result.get("failure_reason") not in {"task_audio_playout_failed", "task_audio_owner_unavailable"}
                or type(result.get("replayed")) is not bool):
            return
        try:
            session_id = _required_id(result["session_id"], "session_id")
            owner_connection = _required_id(connection_id, "connection_id")
            if session_id != _required_id(routed_session_id, "routed_session_id"):
                return
            correlation_id = _required_id(result["correlation_id"], "correlation_id")
            activation_id = _required_id(result["activation_id"], "activation_id")
            generation = _safe_uint(result["activation_generation"], "activation_generation")
            ref = ResponseRef(_required_id(result["interaction_id"], "interaction_id"),
                _required_id(result["response_id"], "response_id"),
                _safe_uint(result["response_generation"], "response_generation"))
            unit_id = _required_id(result["unit_id"], "unit_id")
        except MediaTransportViolation:
            return
        with self._lock:
            now = self._monotonic()
            self._prune(now)
            activation = self._product_activations.get((session_id, owner_connection, ref.interaction_id))
            if (activation is None or activation.correlation_id != correlation_id
                    or activation.activation_id != activation_id or activation.activation_generation != generation):
                return
            for response, _unit, _locale, _rate in activation.synthesis_content_sha256:
                if ((response.response_id == ref.response_id) !=
                        (response.response_generation == ref.response_generation)):
                    return  # A retained exact identity disproves this receipt.
            known_units = {unit for (response, unit, _locale, _rate), transfer
                in activation.synthesis_content_sha256.items() if response == ref and transfer.task_notification}
            if known_units and unit_id not in known_units:
                return
            # The exact formal failure remains authoritative after transfer TTL
            # or eviction. This scalar is not an active SpeechResponseAuthority.
            fence = activation.notification_fence
            fence.task_presentation_retired_generation = max(
                fence.task_presentation_retired_generation, ref.response_generation)
            for (response, unit, _locale, _rate), transfer in activation.synthesis_content_sha256.items():
                if response == ref and unit == unit_id and transfer.task_notification:
                    transfer.presentation_retired = True
            for record in self._records.values():
                if (record.binding.session_id == session_id and record.binding.connection_id == owner_connection
                        and record.binding.correlation_id == correlation_id
                        and record.binding.interaction_id == ref.interaction_id
                        and record.product_activation_id == activation_id
                        and record.product_activation_generation == generation):
                    record.synthesis_content_sha256.pop((ref, unit_id), None)
            self._reconcile_task_preparations()

    @staticmethod
    def _retain_synthesis_transfer(
        transfers: OrderedDict[
            tuple[ResponseRef, str, str, int], _SynthesisAuthorityTransfer
        ],
        *,
        key: tuple[ResponseRef, str, str, int],
        content_sha256: str,
        now: float,
        expires_at: float,
        task_notification: bool = False,
        terminal_event_key: str | None = None,
    ) -> _SynthesisAuthorityTransfer | None:
        DedicatedMediaProductRegistry._prune_synthesis_transfers(transfers, now)
        existing = transfers.get(key)
        if existing is not None:
            if (existing.content_sha256 != content_sha256 or existing.task_notification != task_notification
                    or existing.terminal_event_key != terminal_event_key):
                return None
            transfers.move_to_end(key)
            return existing
        while len(transfers) >= _P2_NOTIFICATION_BATCH_MAX:
            evicted_key = next(
                (
                    candidate_key
                    for candidate_key, candidate in transfers.items()
                    if candidate.claimed_subject_id is None or candidate.presentation_retired
                ),
                None,
            )
            if evicted_key is None:
                return None
            transfers.pop(evicted_key)
        transfer = _SynthesisAuthorityTransfer(content_sha256, expires_at,
            task_notification=task_notification, terminal_event_key=terminal_event_key)
        transfers[key] = transfer
        return transfer

    @staticmethod
    def _prune_synthesis_transfers(
        transfers: OrderedDict[
            tuple[ResponseRef, str, str, int], _SynthesisAuthorityTransfer
        ],
        now: float,
    ) -> None:
        for key, transfer in tuple(transfers.items()):
            if now > transfer.expires_at:
                transfers.pop(key, None)

    def _live_native_task_synthesis(
        self, record: _MediaAuthority, binding: SpeechAuthorizationBinding, now: float,
    ) -> bool:
        """Open capture grants no batch speech authority by itself."""
        key = self._native_session_keys_by_record.get(record.record_id)
        session = self._native_sessions.get(key) if key is not None else None
        activation = self._product_activations.get((record.binding.session_id,
            record.binding.connection_id, record.binding.interaction_id))
        if (record.route_completed or session is None or session.closed or
            session.record_id != record.record_id or session.activation != record.native_activation or
            activation is None or binding.operation != SYNTHESIZE_OPERATION or
            binding.response is None or binding.response.interaction_id != record.binding.interaction_id or
            binding.unit_id is None):
            return False
        transfer = activation.synthesis_content_sha256.get((binding.response, binding.unit_id,
            record.locale, record.binding.frame_format.sample_rate_hz))
        return bool(transfer is not None and transfer.task_notification and not transfer.presentation_retired and now <= transfer.expires_at and
                    transfer.content_sha256 == binding.content_sha256)

    def context_for(
        self,
        ws: Any,
        params: object,
        session_id: str,
        user_id: str | None,
    ) -> SpeechRpcContext:
        connection_id = str(getattr(ws, "_jiuwen_ws_id", "") or id(ws))
        subject = None
        if isinstance(params, Mapping):
            scope = params.get("scope")
            if isinstance(scope, Mapping):
                candidate = scope.get("subject_id")
                if isinstance(candidate, str):
                    subject = candidate
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            record_id = self._subjects.get((session_id, subject or ""))
            record = self._records.get(record_id or "")
            native_task_synthesis = False
            if record is not None and not record.route_completed:
                try:
                    request = parse_synthesis_batch_request(params, SpeechRpcContext(
                        record.subject_id, session_id, Assurance.AUTHENTICATED))
                    native_task_synthesis = self._live_native_task_synthesis(
                        record, _synthesis_authorization_binding(request), now)
                except Exception:
                    pass  # Recognition/arbitrary open-capture requests stay asserted.
            if (
                record is not None
                and record.ticket_consumed
                and ((record.route_completed and record.native_activation is None) or native_task_synthesis)
                and record.binding.connection_id == connection_id
                and now <= record.authority_expires_at
                and self._has_retained_product_activation(record, now)
            ):
                return SpeechRpcContext(
                    record.subject_id, session_id, Assurance.AUTHENTICATED
                )
        return SpeechRpcContext(subject, session_id, Assurance.REQUEST_ASSERTED)

    def authorize(
        self, binding: SpeechAuthorizationBinding
    ) -> SpeechAuthorizationBinding | None:
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            record_id = self._subjects.get(
                (binding.scope.session_id, binding.subject_id)
            )
            record = self._records.get(record_id or "")
            if (
                record is None
                or not record.ticket_consumed
                or (not (record.route_completed and record.native_activation is None)
                    and not self._live_native_task_synthesis(record, binding, now))
                or now > record.authority_expires_at
                or binding.correlation_id != record.binding.correlation_id
                or not self._has_retained_product_activation(record, now)
            ):
                return None
            if binding.operation == RECOGNIZE_OPERATION:
                if binding.recognition_segments:
                    segments = binding.recognition_segments
                    if (
                        len(segments) != 2
                        or binding.scope.subject_id != segments[-1].subject_id
                        or binding.subject_id != segments[-1].subject_id
                        or binding.capture_id != segments[-1].capture_id
                        or binding.capture_generation
                        != segments[-1].capture_generation
                        or binding.track_id != segments[-1].track_id
                        or segments[0].subject_id == segments[1].subject_id
                        or segments[0].capture_id == segments[1].capture_id
                        or segments[0].capture_generation
                        == segments[1].capture_generation
                        or segments[0].track_id == segments[1].track_id
                        or binding.content_sha256
                        != hashlib.sha256(
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
                    ):
                        return None
                    records: list[_MediaAuthority] = []
                    for segment in segments:
                        segment_record_id = self._subjects.get(
                            (binding.scope.session_id, segment.subject_id)
                        )
                        segment_record = self._records.get(segment_record_id or "")
                        if (
                            segment_record is None
                            or not segment_record.ticket_consumed
                            or not segment_record.route_completed
                            or now > segment_record.authority_expires_at
                            or segment_record.binding.direction
                            is not MediaDirection.UPLINK
                            or segment_record.binding.correlation_id
                            != binding.correlation_id
                            or not self._has_retained_product_activation(
                                segment_record, now
                            )
                            or segment_record.accepted_frames <= 0
                            or segment.capture_id
                            != segment_record.binding.generation.id
                            or segment.capture_generation
                            != segment_record.binding.generation.value
                            or segment.track_id != segment_record.binding.track_id
                            or segment.content_sha256
                            != segment_record.recognition_content_sha256
                        ):
                            return None
                        records.append(segment_record)
                    predecessor, current = records
                    if (
                        predecessor.issued_at >= current.issued_at
                        or not predecessor.recognition_continuation_predecessor
                        or predecessor.recognition_predecessor_subject_id is not None
                        or predecessor.recognition_continuation_successor_subject_id
                        != current.subject_id
                        or current.recognition_predecessor_subject_id
                        != predecessor.subject_id
                        or predecessor.binding.session_id
                        != current.binding.session_id
                        or predecessor.binding.correlation_id
                        != current.binding.correlation_id
                        or predecessor.binding.interaction_id
                        != current.binding.interaction_id
                        or predecessor.product_activation_id
                        != current.product_activation_id
                        or predecessor.product_activation_generation
                        != current.product_activation_generation
                        or predecessor.binding.connection_id
                        != current.binding.connection_id
                        or predecessor.locale != current.locale
                        or predecessor.binding.frame_format.sample_rate_hz
                        != current.binding.frame_format.sample_rate_hz
                    ):
                        return None
                    return binding
                if (
                    record.recognition_continuation_predecessor
                    or record.recognition_predecessor_subject_id is not None
                ):
                    return None
                if record.recognition_content_sha256 is None and record.pcm:
                    wav = _wav_bytes(
                        bytes(record.pcm), record.binding.frame_format.sample_rate_hz
                    )
                    record.recognition_content_sha256 = hashlib.sha256(
                        canonical_json_bytes(
                            {
                                "capture_id": record.binding.generation.id,
                                "capture_generation": record.binding.generation.value,
                                "track_id": record.binding.track_id,
                                "locale": record.locale,
                                "sample_rate_hz": record.binding.frame_format.sample_rate_hz,
                                "audio_sha256": hashlib.sha256(wav).hexdigest(),
                            }
                        )
                    ).hexdigest()
                if (
                    record.accepted_frames <= 0
                    or binding.capture_id != record.binding.generation.id
                    or binding.capture_generation != record.binding.generation.value
                    or binding.track_id != record.binding.track_id
                    or binding.content_sha256 != record.recognition_content_sha256
                ):
                    return None
                return binding
            if binding.operation == SYNTHESIZE_OPERATION:
                if binding.response is None or binding.unit_id is None:
                    return None
                activation = self._product_activations.get(
                    (
                        record.binding.session_id,
                        record.binding.connection_id,
                        record.binding.interaction_id,
                    )
                )
                if activation is None:
                    return None
                transfer = activation.synthesis_content_sha256.get(
                    (
                        binding.response,
                        binding.unit_id,
                        record.locale,
                        record.binding.frame_format.sample_rate_hz,
                    )
                )
                if transfer is None or transfer.presentation_retired or transfer.content_sha256 != binding.content_sha256:
                    return None
                if transfer.claimed_subject_id is None:
                    transfer.claimed_subject_id = record.subject_id
                    transfer.claimed_operation_id = binding.operation_id
                elif (
                    transfer.claimed_subject_id != record.subject_id
                    or transfer.claimed_operation_id != binding.operation_id
                ):
                    return None
                record.synthesis_content_sha256[(binding.response, binding.unit_id)] = (
                    transfer.content_sha256
                )
                return binding
            return None

    def task_preparation_capabilities(self, params: object) -> dict[str, object]:
        if params != {"contract_version": task_preparation.CONTRACT_VERSION}:
            raise task_preparation.PreparationViolation("TASK_PREPARATION_CONTRACT_INVALID")
        return {"contract_version": task_preparation.CONTRACT_VERSION,
            "available": self.enabled and self._streaming_synthesis_owner is not None,
            "max_frames": task_preparation.MAX_FRAMES, "max_bytes": task_preparation.MAX_BYTES,
            "retention_ms": int(task_preparation.RETENTION_SECONDS * 1000)}

    def _task_preparation_request(self, params: object, *, routed_session_id: str,
            connection_id: str, request_origin: str | None, with_text: bool = False,
            allow_retired: bool = False,
    ) -> tuple[task_preparation.PreparationIdentity, str, _MediaAuthority, _SynthesisAuthorityTransfer]:
        keys = {"contract_version", "preparation_id", "session_id", "subject_id", "correlation_id",
            "interaction_id", "activation_id", "activation_generation", "event_key", "response",
            "unit_id", "text_sha256", "locale", "sample_rate_hz"}
        if with_text:
            keys.add("text")
        if (not isinstance(params, Mapping) or set(params) != keys
                or params.get("contract_version") != task_preparation.CONTRACT_VERSION):
            raise task_preparation.PreparationViolation("TASK_PREPARATION_CONTRACT_INVALID")
        response = params["response"]
        if not isinstance(response, Mapping) or set(response) != {"interaction_id", "response_id", "response_generation"}:
            raise task_preparation.PreparationViolation("TASK_PREPARATION_CONTRACT_INVALID")
        identity = task_preparation.PreparationIdentity(
            *(_required_id(params[name], name) for name in ("session_id",)),
            connection_id, *(_required_id(params[name], name) for name in
                ("subject_id", "correlation_id", "interaction_id", "activation_id")),
            _safe_uint(params["activation_generation"], "activation_generation"),
            str(params["event_key"]), _required_id(response["response_id"], "response_id"),
            _safe_uint(response["response_generation"], "response_generation"),
            _required_id(params["unit_id"], "unit_id"), str(params["text_sha256"]),
            _required_id(params["locale"], "locale"), _safe_uint(params["sample_rate_hz"], "sample_rate_hz"))
        preparation_id = _required_id(params["preparation_id"], "preparation_id")
        if (identity.session_id != routed_session_id or response["interaction_id"] != identity.interaction_id
                or not isinstance(params["event_key"], str) or not 0 < len(identity.event_key) <= 2048
                or not isinstance(params["text_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", identity.text_sha256)
                or identity.sample_rate_hz not in {16_000, 24_000, 48_000}):
            raise task_preparation.PreparationViolation("TASK_PREPARATION_IDENTITY_INVALID")
        parent = self._records.get(self._subjects.get((identity.session_id, identity.subject_id), ""))
        native_session_key = self._native_session_keys_by_record.get(parent.record_id) if parent is not None else None
        native_session = self._native_sessions.get(native_session_key) if native_session_key is not None else None
        now = self._monotonic()
        if (parent is None or native_session is None or native_session.closed
                or native_session.record_id != parent.record_id or parent.route_completed or not parent.ticket_consumed
                or parent.native_activation is None or parent.binding.connection_id != connection_id
                or parent.expected_origin != request_origin or not is_allowed_browser_origin(request_origin)
                or parent.binding.correlation_id != identity.correlation_id
                or parent.binding.interaction_id != identity.interaction_id
                or parent.product_activation_id != identity.activation_id
                or parent.product_activation_generation != identity.activation_generation
                or parent.locale != identity.locale
                or parent.binding.frame_format.sample_rate_hz != identity.sample_rate_hz
                or now >= parent.authority_expires_at or not self._has_retained_product_activation(parent, now)):
            raise task_preparation.PreparationViolation("TASK_PREPARATION_OWNER_MISMATCH")
        activation = self._product_activations[(identity.session_id, connection_id, identity.interaction_id)]
        ref = ResponseRef(identity.interaction_id, identity.response_id, identity.response_generation)
        transfer = activation.synthesis_content_sha256.get((ref, identity.unit_id, identity.locale, identity.sample_rate_hz))
        if (transfer is None or not transfer.task_notification or transfer.terminal_event_key != identity.event_key
                or now >= transfer.expires_at):
            raise task_preparation.PreparationViolation("TASK_PREPARATION_SOURCE_MISMATCH")
        if transfer.presentation_retired and not allow_retired:
            raise task_preparation.PreparationViolation("TASK_PREPARATION_RETIRED")
        if with_text:
            text = params["text"]
            if (not isinstance(text, str) or not text.strip() or len(text) > 4000
                    or hashlib.sha256(text.encode("utf-8")).hexdigest() != identity.text_sha256):
                raise task_preparation.PreparationViolation("TASK_PREPARATION_TEXT_MISMATCH")
            digest = hashlib.sha256(canonical_json_bytes({"response": dict(response), "unit_id": identity.unit_id,
                "display_text": text, "spoken_text": text, "transforms": [], "locale": identity.locale,
                "voice": None, "required_sample_rate_hz": identity.sample_rate_hz})).hexdigest()
            if digest != transfer.content_sha256:
                raise task_preparation.PreparationViolation("TASK_PREPARATION_TEXT_MISMATCH")
        return identity, preparation_id, parent, transfer

    async def prepare_task_notification(self, *, params: object, routed_session_id: str,
            connection_id: str, request_origin: str | None) -> dict[str, object]:
        # A yielding browser cancels the exact unplayed child before retrying.
        # Keep cleanup strongly owned and wait outside the Registry lock.
        with self._lock:
            identity, preparation_id, _parent, transfer = self._task_preparation_request(params,
                routed_session_id=routed_session_id, connection_id=connection_id, request_origin=request_origin, with_text=True)
            previous = self._task_preparations.active(identity.activation_key)
            cleanup = (previous.producer if previous is not None
                and previous.identity == identity and not previous.attached and previous.emitted_frames == 0
                and previous.preparation_id != preparation_id and previous.reason == "TASK_PREPARATION_CANCELLED"
                else None)
        if cleanup is not None and not cleanup.done():
            await asyncio.wait({cleanup}, timeout=2.0)
        with self._lock:
            self._prune(self._monotonic())
            identity, preparation_id, parent, transfer = self._task_preparation_request(params,
                routed_session_id=routed_session_id, connection_id=connection_id, request_origin=request_origin, with_text=True)
            owner = self._streaming_synthesis_owner
            if owner is None:
                raise task_preparation.PreparationViolation("TASK_PREPARATION_UNAVAILABLE")
            key = (identity.session_id, connection_id, identity.interaction_id)
            existing = self._task_preparations.active(identity.activation_key)
            if existing is None and (self._tts_opening.get(key) or any(
                    record.binding.direction is MediaDirection.DOWNLINK and not record.route_completed
                    and record.binding.session_id == identity.session_id and record.binding.connection_id == connection_id
                    and record.binding.interaction_id == identity.interaction_id and record.native_activation is None
                    for record in self._records.values())):
                raise task_preparation.PreparationViolation("TASK_PREPARATION_BUSY")

            def current() -> bool:
                with self._lock:
                    now = self._monotonic()
                    activation = self._product_activations.get(key)
                    ref = ResponseRef(identity.interaction_id, identity.response_id, identity.response_generation)
                    native_key = self._native_session_keys_by_record.get(parent.record_id)
                    native = self._native_sessions.get(native_key) if native_key is not None else None
                    return bool(self._records.get(parent.record_id) is parent and not parent.route_completed
                        and native is not None and not native.closed and native.record_id == parent.record_id
                        and now < parent.authority_expires_at and self._has_retained_product_activation(parent, now)
                        and activation is not None and not transfer.presentation_retired and now < transfer.expires_at
                        and activation.synthesis_content_sha256.get((ref, identity.unit_id, identity.locale, identity.sample_rate_hz)) is transfer
                        and transfer.terminal_event_key == identity.event_key)

            async def produce() -> ProductStreamingSynthesisSource:
                context = SpeechRpcContext(identity.subject_id, identity.session_id, Assurance.AUTHENTICATED)
                payload = {"contract_version": SPEECH_CONTRACT_VERSION, "request_id": preparation_id,
                    "operation_id": preparation_id, "operation": SYNTHESIZE_OPERATION,
                    "correlation_id": identity.correlation_id, "session_id": identity.session_id,
                    "scope": {"subject_id": identity.subject_id, "project_id": None,
                        "session_id": identity.session_id, "assurance": "authenticated"},
                    "timeout_ms": 15_000, "response": dict(params["response"]), "unit_id": identity.unit_id,
                    "render_plan": {"display_text": params["text"], "spoken_text": params["text"], "transforms": []},
                    "authoritative_agent_text": True, "locale": identity.locale, "voice": None,
                    "required_sample_rate_hz": identity.sample_rate_hz}
                request = parse_synthesis_batch_request(payload, context)
                binding = _synthesis_authorization_binding(request)
                with self._lock:
                    retry = transfer.unplayed_preparation
                    if (current() and retry is not None and retry[0] == identity
                            and retry[1] != preparation_id
                            and transfer.claimed_subject_id == identity.subject_id
                            and transfer.claimed_operation_id == retry[1]):
                        # start() admitted a fresh identity only after the old
                        # producer and its unplayed tickets retired completely.
                        authorities = self._product_activations[key].streaming_response_authorities
                        if authorities and authorities[0].response == request.response:
                            authorities[0] = authorities[0].retry_unplayed()
                        if transfer.streaming_authority is not None:
                            transfer.streaming_authority.revoke()
                        transfer.claimed_operation_id = preparation_id
                        transfer.streaming_authority = None
                        transfer.unplayed_preparation = None
                    if not current() or self.authorize(binding) != binding:
                        raise task_preparation.PreparationViolation("TASK_PREPARATION_STALE")
                    stream = self._admit_streaming_synthesis(request, identity.session_id, identity.subject_id,
                        "task-preparation-" + hashlib.sha256(preparation_id.encode()).hexdigest()[:32])
                if stream is None:
                    raise task_preparation.PreparationViolation("TASK_PREPARATION_STALE")
                start = await start_product_streaming_synthesis(owner, stream,
                    scope_identity=(identity.session_id, identity.subject_id, identity.correlation_id))
                if start.source is None:
                    raise task_preparation.PreparationViolation("TASK_PREPARATION_SYNTHESIS_FAILED")
                return start.source

            slot = self._task_preparations.start(identity, preparation_id, produce, current)
        await slot.wait_ready()
        return {"contract_version": task_preparation.CONTRACT_VERSION,
            "preparation_id": preparation_id, "status": "ready", "presented": False}

    async def claim_task_notification(self, *, params: object, routed_session_id: str,
            connection_id: str, request_origin: str | None) -> dict[str, object]:
        with self._lock:
            self._prune(self._monotonic())
            identity, preparation_id, parent, transfer = self._task_preparation_request(params,
                routed_session_id=routed_session_id, connection_id=connection_id, request_origin=request_origin)
            slot = self._task_preparations.exact(identity, preparation_id)
        await slot.wait_ready()
        with self._lock:
            self._task_preparation_request(params, routed_session_id=routed_session_id,
                connection_id=connection_id, request_origin=request_origin)
            if self._media_capacity_in_use() >= self._capacity:
                raise task_preparation.PreparationViolation("TASK_PREPARATION_CAPACITY")
            slot.claim(ticket_ttl=self._ticket_ttl)
            now = self._monotonic()
            ref = ResponseRef(identity.interaction_id, identity.response_id, identity.response_generation)
            ticket = secrets.token_urlsafe(32)
            record_id = f"media-record-{secrets.token_hex(16)}"
            media_binding = MediaAuthorityBinding(lease_id=f"media-downlink-{secrets.token_hex(16)}",
                authority_evidence_id=f"media-authority-{secrets.token_hex(16)}",
                connection_id=connection_id, connection_epoch=parent.binding.connection_epoch,
                session_id=identity.session_id, media_session_id=f"media-session-{secrets.token_hex(16)}",
                interaction_id=identity.interaction_id, track_id=f"playout-{secrets.token_hex(12)}",
                correlation_id=identity.correlation_id, direction=MediaDirection.DOWNLINK,
                generation=MediaGenerationBinding(MediaGenerationKind.RESPONSE, ref.response_id, ref.response_generation),
                frame_format=MediaFrameFormat(sample_rate_hz=identity.sample_rate_hz,
                    samples_per_channel=identity.sample_rate_hz // 50),
                playout=MediaPlayoutBinding(ref.response_id, ref.response_generation, identity.unit_id))
            self._records[record_id] = _MediaAuthority(record_id=record_id, subject_id=parent.subject_id,
                expected_origin=parent.expected_origin, product_activation_id=identity.activation_id,
                product_activation_generation=identity.activation_generation, binding=media_binding,
                locale=identity.locale, end_of_turn_capability=None, issued_at=now,
                ticket_expires_at=now + self._ticket_ttl, authority_expires_at=parent.authority_expires_at,
                downlink_stream_source=slot, downlink_response=ref, downlink_unit_id=identity.unit_id,
                downlink_content_sha256=transfer.content_sha256)
            self._pending_tickets[ticket] = record_id
            audio = {"format": "pcm_f32_mono_20ms", "sample_rate_hz": identity.sample_rate_hz,
                "channel_count": 1, "frame_count": None, "delivery": "dedicated_media_downlink",
                "endpoint_path": MEDIA_ROUTE_PATH, "media_ticket": ticket, "subprotocol": MEDIA_SUBPROTOCOL,
                "ticket_ttl_ms": int(self._ticket_ttl * 1000), "binding": _binding_payload(media_binding),
                "max_pending_frames": 8, "max_pending_bytes": 131_072, "streaming": True, "degradation_reason": None}
        return {"contract_version": task_preparation.CONTRACT_VERSION, "preparation_id": preparation_id,
            "status": "claimed", "response": dict(params["response"]), "unit_id": identity.unit_id,
            "audio": audio, "provider": slot.provider, "presented": False}

    def cancel_task_notification(self, *, params: object, routed_session_id: str,
            connection_id: str, request_origin: str | None) -> dict[str, object]:
        with self._lock:
            identity, preparation_id, _parent, transfer = self._task_preparation_request(params,
                routed_session_id=routed_session_id, connection_id=connection_id, request_origin=request_origin,
                allow_retired=True)
            slot = self._task_preparations.active(identity.activation_key)
            if (slot is not None and slot.identity == identity and slot.preparation_id == preparation_id
                    and not slot.attached and slot.emitted_frames == 0 and not slot.settled
                    and slot.reason in {None, "TASK_PREPARATION_CANCELLED"}
                    and transfer.claimed_operation_id == preparation_id):
                transfer.unplayed_preparation = (identity, preparation_id)
            self._task_preparations.cancel(identity, preparation_id)
            self._reconcile_task_preparations()
        return {"contract_version": task_preparation.CONTRACT_VERSION, "preparation_id": preparation_id,
            "status": "cancelled", "presented": False}

    def _admit_streaming_synthesis(
        self,
        request: SynthesisBatchRequest,
        session_id: str,
        subject_id: str,
        stream_id: str,
    ) -> SynthesisStreamRequest | None:
        """Consume the existing content-transfer authority, including RPC replay.

        Only opaque bindings/grants are retained, not spoken text or a request.
        The single response high-water belongs to this live activation; provider
        history is neither an issuer nor an authorization fallback.
        """
        binding = _synthesis_authorization_binding(request)
        with self._lock:
            parent_id = self._subjects.get((session_id, subject_id))
            parent = self._records.get(parent_id or "")
            if parent is None:
                return None
            activation_key = (
                session_id,
                parent.binding.connection_id,
                request.response.interaction_id,
            )
            activation = self._product_activations.get(activation_key)
            transfer_key = (
                request.response,
                request.unit_id,
                parent.locale,
                request.required_sample_rate_hz,
            )
            transfer = (
                activation.synthesis_content_sha256.get(transfer_key)
                if activation
                else None
            )
            if (
                transfer is None
                or transfer.presentation_retired
                or transfer.content_sha256 != binding.content_sha256
                or transfer.claimed_subject_id != subject_id
                or transfer.claimed_operation_id != request.operation_id
            ):
                return None
            response = request.response
            evidence_id = parent.binding.authority_evidence_id

            def current_synthesis() -> bool:
                with self._lock:
                    now = self._monotonic()
                    record = self._records.get(parent_id)
                    current = self._product_activations.get(activation_key)
                    return bool(
                        record is not None
                        and record.binding.authority_evidence_id == evidence_id
                        and now <= record.authority_expires_at
                        and self._has_retained_product_activation(record, now)
                        and now <= transfer.expires_at
                        and not transfer.presentation_retired
                        and current is not None
                        and current.streaming_response_authorities
                        and current.streaming_response_authorities[0].response
                        == response
                        and current.synthesis_content_sha256.get(transfer_key)
                        is transfer
                    )

            authorities = activation.streaming_response_authorities
            prior = authorities[0] if authorities else None
            if prior is not None and prior.response != response:
                if (
                    response.response_generation <= prior.response.response_generation
                    or response.response_id == prior.response.response_id
                ):
                    return None
                # Publishing the new authority invalidates old response checks.
                # Do not acquire a Speech lock while holding the Registry lock.
                authorities.clear()
            if not authorities:
                authorities.append(SpeechResponseAuthority(response, current_synthesis))
            stream_request = SynthesisStreamRequest(
                ref=SynthesisStreamRef(stream_id, 0, response, request.unit_id, 0),
                display_text=request.display_text,
                spoken_text=request.spoken_text,
                display_span=TextSpan(0, len(request.display_text)),
                sample_rate_hz=request.required_sample_rate_hz,
                event_timeout_seconds=request.timeout_ms / 1000,
                response_authority=authorities[0],
            )
            if transfer.streaming_authority is None:
                stream_request = authorize_stream_request(
                    stream_request, is_current=current_synthesis
                )
                transfer.streaming_authority = stream_request.authority
            return replace(stream_request, authority=transfer.streaming_authority)

    async def try_streaming_synthesis(self, operation_name: str, params: object,
            context: SpeechRpcContext, session_id: str, *, batch_service: FormalBatchSpeechService
    ) -> dict[str, object] | None:
        if operation_name != SYNTHESIZE_OPERATION or self._streaming_synthesis_owner is None:
            return None
        try:
            request = parse_synthesis_batch_request(params, context)
        except Exception:
            return None
        token = object()
        key = None
        with self._lock:
            parent = self._records.get(self._subjects.get((session_id, context.subject_id or ""), ""))
            if parent is not None:
                key = (session_id, parent.binding.connection_id, request.response.interaction_id)
                preparation_key = (*key, parent.product_activation_id, parent.product_activation_generation)
                if self._task_preparations.active(preparation_key) is not None:
                    return _streaming_error_envelope(request, "TASK_PREPARATION_BUSY")
                self._tts_opening.setdefault(key, set()).add(token)
        try:
            return await self._try_streaming_synthesis_admitted(operation_name, params, context,
                session_id, batch_service=batch_service)
        finally:
            if key is not None:
                with self._lock:
                    tokens = self._tts_opening.get(key)
                    if tokens is not None:
                        tokens.discard(token)
                        if not tokens:
                            self._tts_opening.pop(key, None)

    async def _try_streaming_synthesis_admitted(
        self,
        operation_name: str,
        params: object,
        context: SpeechRpcContext,
        session_id: str,
        *,
        batch_service: FormalBatchSpeechService,
    ) -> dict[str, object] | None:
        """Own the exact product streaming route or explicitly delegate batch."""

        owner = self._streaming_synthesis_owner
        if operation_name != SYNTHESIZE_OPERATION or owner is None:
            return None
        if (
            not isinstance(context, SpeechRpcContext)
            or context.assurance is not Assurance.AUTHENTICATED
            or context.subject_id is None
            or context.session_id != session_id
        ):
            return None
        try:
            request = parse_synthesis_batch_request(params, context)
        except Exception:
            return None
        # The native route does not yet carry render-transform or per-request
        # voice semantics.  Those exact requests stay on the existing batch
        # contract instead of being silently approximated.
        if request.transforms or request.voice is not None:
            return None
        binding = _synthesis_authorization_binding(request)
        if self.authorize(binding) != binding:
            return None
        with self._lock:
            l0_parent_id = self._subjects.get((session_id, context.subject_id))
            l0_parent = self._records.get(l0_parent_id or "")
            if (
                l0_parent is None
                or l0_parent.binding.direction is not MediaDirection.UPLINK
                or l0_parent.binding.correlation_id != request.correlation_id
                or l0_parent.binding.interaction_id != request.response.interaction_id
            ):
                l0_parent = None
        if l0_parent is not None:
            response_measurement_binding = _l0_media_binding(
                l0_parent,
                response=request.response,
            )
            register_runtime_l0_binding(response_measurement_binding)
            emit_runtime_l0_milestone(
                component="gateway",
                milestone=L0Milestone.TTS_REQUEST,
                binding=response_measurement_binding,
                event_nonce=request.operation_id,
            )
        stream_identity = hashlib.sha256(
            canonical_json_bytes(
                {
                    "operation_id": request.operation_id,
                    "response_id": request.response.response_id,
                    "response_generation": request.response.response_generation,
                    "unit_id": request.unit_id,
                }
            )
        ).hexdigest()[:40]
        observation_context = _StreamingObservationContext(
            request.operation_id,
            request.correlation_id,
            request.response,
            self._monotonic(),
        )

        def observe_outcome(outcome: StreamingSynthesisOutcome) -> None:
            self._schedule_streaming_outcome(observation_context, outcome)

        stream_request = self._admit_streaming_synthesis(
            request, session_id, context.subject_id, f"product-tts-{stream_identity}"
        )
        if stream_request is None:
            return _streaming_error_envelope(
                request, "MEDIA_STREAMING_TTS_AUTHORITY_EXPIRED"
            )
        try:
            start = await start_product_streaming_synthesis(
                owner,
                stream_request,
                scope_identity=(
                    session_id,
                    context.subject_id,
                    request.correlation_id,
                ),
                on_outcome=observe_outcome,
            )
        except StreamingSynthesisRouteViolation as error:
            if error.reason in {
                "SPEECH_AUTHORITY_REQUIRED",
                "SPEECH_AUTHORITY_EXPIRED",
                "SPEECH_AUTHORITY_CONSUMED",
            }:
                return _streaming_error_envelope(
                    request, "MEDIA_STREAMING_TTS_AUTHORITY_EXPIRED"
                )
            raise
        if start.source is None:
            outcome = start.outcome
            assert outcome is not None
            if l0_parent is not None:
                emit_runtime_l0_milestone(
                    component="gateway",
                    milestone=L0Milestone.FALLBACK,
                    binding=_l0_media_binding(
                        l0_parent,
                        response=request.response,
                    ),
                    classification=L0RoundClassification.FALLBACK,
                    event_nonce=request.operation_id,
                )
            if outcome.batch_eligible and not outcome.first_audio_emitted:
                batch_result = await batch_service.synthesize(params, context)
                return {
                    **batch_result,
                    "_streaming_degradation_reason": (
                        outcome.reason.value if outcome.reason is not None else None
                    ),
                }
            return _streaming_error_envelope(
                request, "MEDIA_STREAMING_TTS_TEXT_OR_RETRY"
            )

        source = start.source
        if l0_parent is not None:
            emit_runtime_l0_milestone(
                component="gateway",
                milestone=L0Milestone.PROVIDER_FIRST_AUDIO,
                binding=_l0_media_binding(l0_parent, response=request.response),
                event_nonce=request.operation_id,
            )
        try:
            model = source.model
            voice = source.voice
            implementation_class = source.provider_implementation_class
            if implementation_class != "formal":
                raise TypeError("streaming Provider is not a formal route")
        except BaseException:
            await source.aclose()
            return _streaming_error_envelope(
                request, "MEDIA_STREAMING_TTS_TEXT_OR_RETRY"
            )
        now = self._monotonic()
        stored: tuple[str, MediaAuthorityBinding] | None = None
        with self._lock:
            self._prune(now)
            parent_record_id = self._subjects.get((session_id, context.subject_id))
            parent = self._records.get(parent_record_id or "")
            key = (request.response, request.unit_id)
            if (
                parent is not None
                and parent.binding.direction is MediaDirection.UPLINK
                and parent.binding.correlation_id == request.correlation_id
                and parent.binding.interaction_id == request.response.interaction_id
                and parent.synthesis_content_sha256.get(key) == binding.content_sha256
                and now <= parent.authority_expires_at
                and self._has_retained_product_activation(parent, now)
                and self._media_capacity_in_use() < self._capacity
            ):
                ticket = secrets.token_urlsafe(32)
                record_id = f"media-record-{secrets.token_hex(16)}"
                media_binding = MediaAuthorityBinding(
                    lease_id=f"media-downlink-{secrets.token_hex(16)}",
                    authority_evidence_id=f"media-authority-{secrets.token_hex(16)}",
                    connection_id=parent.binding.connection_id,
                    connection_epoch=parent.binding.connection_epoch,
                    session_id=parent.binding.session_id,
                    media_session_id=f"media-session-{secrets.token_hex(16)}",
                    interaction_id=request.response.interaction_id,
                    track_id=f"playout-{secrets.token_hex(12)}",
                    correlation_id=parent.binding.correlation_id,
                    direction=MediaDirection.DOWNLINK,
                    generation=MediaGenerationBinding(
                        MediaGenerationKind.RESPONSE,
                        request.response.response_id,
                        request.response.response_generation,
                    ),
                    frame_format=MediaFrameFormat(
                        sample_rate_hz=request.required_sample_rate_hz,
                        samples_per_channel=request.required_sample_rate_hz // 50,
                    ),
                    playout=MediaPlayoutBinding(
                        request.response.response_id,
                        request.response.response_generation,
                        request.unit_id,
                    ),
                )
                self._records[record_id] = _MediaAuthority(
                    record_id=record_id,
                    subject_id=parent.subject_id,
                    expected_origin=parent.expected_origin,
                    product_activation_id=parent.product_activation_id,
                    product_activation_generation=parent.product_activation_generation,
                    binding=media_binding,
                    locale=parent.locale,
                    end_of_turn_capability=None,
                    issued_at=now,
                    ticket_expires_at=now + self._ticket_ttl,
                    authority_expires_at=parent.authority_expires_at,
                    downlink_stream_source=source,
                    downlink_response=request.response,
                    downlink_unit_id=request.unit_id,
                    downlink_content_sha256=binding.content_sha256,
                )
                self._pending_tickets[ticket] = record_id
                stored = ticket, media_binding
        if stored is None:
            await source.aclose()
            return _streaming_error_envelope(
                request, "MEDIA_STREAMING_TTS_TEXT_OR_RETRY"
            )
        ticket, media_binding = stored
        if l0_parent is not None:
            emit_runtime_l0_milestone(
                component="gateway",
                milestone=L0Milestone.DOWNLINK_TICKET,
                binding=_l0_media_binding(l0_parent, response=request.response),
                event_nonce=request.operation_id,
            )
        audio = {
            "format": "pcm_f32_mono_20ms",
            "sample_rate_hz": request.required_sample_rate_hz,
            "channel_count": 1,
            "frame_count": None,
            "delivery": "dedicated_media_downlink",
            "endpoint_path": MEDIA_ROUTE_PATH,
            "media_ticket": ticket,
            "subprotocol": MEDIA_SUBPROTOCOL,
            "ticket_ttl_ms": int(self._ticket_ttl * 1000),
            "binding": _binding_payload(media_binding),
            "max_pending_frames": 8,
            "max_pending_bytes": 131_072,
            "streaming": True,
            "degradation_reason": None,
        }
        provider = {
            "provider_id": source.provider_id,
            "implementation_class": implementation_class,
            "model": model,
            "fallback_from": source.provider_fallback_from,
            **({"voice": voice} if voice is not None else {}),
        }
        return {
            "contract_version": SPEECH_CONTRACT_VERSION,
            "request_id": request.request_id,
            "operation_id": request.operation_id,
            "ok": True,
            "result": {
                "operation": SYNTHESIZE_OPERATION,
                "response": {
                    "interaction_id": request.response.interaction_id,
                    "response_id": request.response.response_id,
                    "response_generation": request.response.response_generation,
                },
                "unit_id": request.unit_id,
                "audio": audio,
                "provider": provider,
                "presented": False,
            },
            "error": None,
        }

    def prepare_synthesis_downlink(
        self,
        operation_name: str,
        params: object,
        context: SpeechRpcContext,
        result: dict[str, object],
        session_id: str,
    ) -> dict[str, object]:
        """Replace exact product synthesis bytes with a one-use binary ticket."""

        degradation_reason = result.get("_streaming_degradation_reason")
        if "_streaming_degradation_reason" in result:
            result = {
                key: value
                for key, value in result.items()
                if key != "_streaming_degradation_reason"
            }
        if (
            operation_name != SYNTHESIZE_OPERATION
            or not isinstance(params, Mapping)
            or not isinstance(context, SpeechRpcContext)
            or context.assurance is not Assurance.AUTHENTICATED
            or context.subject_id is None
            or context.session_id != session_id
            or result.get("ok") is not True
        ):
            return result
        payload = result.get("result")
        response_payload = params.get("response")
        if not isinstance(payload, Mapping) or not isinstance(
            response_payload, Mapping
        ):
            return result
        audio = payload.get("audio")
        if not isinstance(audio, Mapping):
            return result
        if audio.get("delivery") == "dedicated_media_downlink":
            return result
        try:
            request = parse_synthesis_batch_request(params, context)
            authorization_binding = _synthesis_authorization_binding(request)
        except Exception:
            return result
        try:
            response = ResponseRef(
                interaction_id=_required_id(
                    response_payload.get("interaction_id"), "response.interaction_id"
                ),
                response_id=_required_id(
                    response_payload.get("response_id"), "response.response_id"
                ),
                response_generation=_safe_uint(
                    response_payload.get("response_generation"),
                    "response.response_generation",
                ),
            )
            unit_id = _required_id(params.get("unit_id"), "unit_id")
            sample_rate_hz = _safe_uint(
                audio.get("sample_rate_hz"), "audio.sample_rate_hz"
            )
            encoded_value = audio.get("data_base64")
            if not isinstance(encoded_value, str) or not encoded_value:
                raise MediaTransportViolation(
                    "MEDIA_INVALID_DOWNLINK_AUDIO",
                    "synthesis audio base64 is invalid",
                )
            encoded = encoded_value
            audio_wav = base64.b64decode(encoded, validate=True)
            frames = _downlink_frames(audio_wav, sample_rate_hz)
        except (ValueError, MediaTransportViolation) as exc:
            if isinstance(exc, MediaTransportViolation):
                raise
            raise MediaTransportViolation(
                "MEDIA_INVALID_DOWNLINK_AUDIO", "synthesis audio base64 is invalid"
            ) from exc
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            parent_record_id = self._subjects.get((session_id, context.subject_id))
            parent = self._records.get(parent_record_id or "")
            key = (response, unit_id)
            if (
                parent is None
                or parent.binding.direction is not MediaDirection.UPLINK
                or parent.binding.correlation_id != params.get("correlation_id")
                or parent.binding.interaction_id != response.interaction_id
                or response != request.response
                or unit_id != request.unit_id
                or now > parent.authority_expires_at
                or not self._has_retained_product_activation(parent, now)
            ):
                return result
            if (
                parent.synthesis_content_sha256.get(key)
                != authorization_binding.content_sha256
            ):
                return _streaming_error_envelope(
                    request, "MEDIA_STREAMING_TTS_TEXT_OR_RETRY"
                )
            if self._media_capacity_in_use() >= self._capacity:
                raise MediaTransportViolation(
                    "MEDIA_ROUTE_CAPACITY_EXCEEDED", "media route capacity is full"
                )
            ticket = secrets.token_urlsafe(32)
            record_id = f"media-record-{secrets.token_hex(16)}"
            binding = MediaAuthorityBinding(
                lease_id=f"media-downlink-{secrets.token_hex(16)}",
                authority_evidence_id=f"media-authority-{secrets.token_hex(16)}",
                connection_id=parent.binding.connection_id,
                connection_epoch=parent.binding.connection_epoch,
                session_id=parent.binding.session_id,
                media_session_id=f"media-session-{secrets.token_hex(16)}",
                interaction_id=response.interaction_id,
                track_id=f"playout-{secrets.token_hex(12)}",
                correlation_id=parent.binding.correlation_id,
                direction=MediaDirection.DOWNLINK,
                generation=MediaGenerationBinding(
                    MediaGenerationKind.RESPONSE,
                    response.response_id,
                    response.response_generation,
                ),
                frame_format=MediaFrameFormat(
                    sample_rate_hz=sample_rate_hz,
                    samples_per_channel=sample_rate_hz // 50,
                ),
                playout=MediaPlayoutBinding(
                    response.response_id,
                    response.response_generation,
                    unit_id,
                ),
            )
            record = _MediaAuthority(
                record_id=record_id,
                subject_id=parent.subject_id,
                expected_origin=parent.expected_origin,
                product_activation_id=parent.product_activation_id,
                product_activation_generation=parent.product_activation_generation,
                binding=binding,
                locale=parent.locale,
                end_of_turn_capability=None,
                issued_at=now,
                ticket_expires_at=now + self._ticket_ttl,
                authority_expires_at=parent.authority_expires_at,
                downlink_frames=frames,
                downlink_response=response,
                downlink_unit_id=unit_id,
                downlink_content_sha256=authorization_binding.content_sha256,
            )
            self._records[record_id] = record
            self._pending_tickets[ticket] = record_id
        route_descriptor = {"endpoint_path": MEDIA_ROUTE_PATH, "media_ticket": ticket}
        transformed_audio = {
            "format": "pcm_f32_mono_20ms",
            "sample_rate_hz": sample_rate_hz,
            "channel_count": 1,
            "frame_count": len(frames),
            "delivery": "dedicated_media_downlink",
            **route_descriptor,
            "subprotocol": MEDIA_SUBPROTOCOL,
            "ticket_ttl_ms": int(self._ticket_ttl * 1000),
            "binding": _binding_payload(binding),
            "max_pending_frames": 8,
            "max_pending_bytes": 131_072,
            "streaming": False,
            "degradation_reason": degradation_reason,
        }
        return {
            **result,
            "result": {**payload, "audio": transformed_audio},
        }

    def mark_downlink_started(self, record: _MediaAuthority) -> None:
        """Bind the downlink start to one exact consumed live uplink."""

        with self._lock:
            record.downlink_overlap_record_id = next(
                (
                    record_id
                    for record_id, other in self._records.items()
                    if other is not record
                    and other.binding.direction is MediaDirection.UPLINK
                    and other.binding.session_id == record.binding.session_id
                    and other.binding.interaction_id == record.binding.interaction_id
                    and other.binding.correlation_id == record.binding.correlation_id
                    and other.product_activation_id == record.product_activation_id
                    and other.product_activation_generation
                    == record.product_activation_generation
                    and other.ticket_consumed
                    and not other.route_completed
                ),
                None,
            )
            record.downlink_overlap_observed = False

    def complete_downlink(
        self, record: _MediaAuthority, result: DedicatedMediaSocketLeafResult
    ) -> bool:
        with self._lock:
            self._reconcile_task_preparations()
            if self._records.get(record.record_id) is not record:
                return False
            source = record.downlink_stream_source
            prepared_source = source if isinstance(source, task_preparation.PreparedNotificationSource) else None
            native_source = (
                source if isinstance(source, NativeResponseDownlinkSource) else None
            )
            frame_count = (
                source.emitted_frames
                if source is not None
                else len(record.downlink_frames)
            )
            source_completed = source.completed if source is not None else True
            native_final_unit = (
                native_source.unit_for_media_sequence(result.acknowledged_through_seq)
                if native_source is not None
                and result.acknowledged_through_seq is not None
                else None
            )
            if native_final_unit is not None:
                record.native_final_unit_id = native_final_unit.unit_id
                record.native_final_unit_seq = native_final_unit.unit_seq
                record.downlink_content_sha256 = native_source.content_sha256
            record.route_completed = True
            record.downlink_frames = ()
            # Native playback may outlive its download. Retain the bounded
            # frame-to-Provider cursor map until playback ACK/stop or teardown.
            if native_source is None and prepared_source is None:
                self._release_stream_source(record)
            response = record.downlink_response
            unit_id = record.downlink_unit_id
            content_sha256 = record.downlink_content_sha256
            overlapping_uplink = self._records.get(
                record.downlink_overlap_record_id or ""
            )
            record.downlink_overlap_observed = bool(
                overlapping_uplink is not None
                and overlapping_uplink.binding.direction is MediaDirection.UPLINK
                and overlapping_uplink.ticket_consumed
                and not overlapping_uplink.route_completed
                and overlapping_uplink.accepted_frames > 0
            )
            complete = bool(
                result.activated
                and response is not None
                and unit_id is not None
                and content_sha256 is not None
                and frame_count > 0
                and source_completed
                and (
                    native_source is None
                    or (
                        native_final_unit is not None
                        and native_final_unit.response == response
                        and native_final_unit.unit_seq == frame_count - 1
                    )
                )
                and result.sent_frames == frame_count
                and result.acknowledged_through_seq == frame_count - 1
                and result.playback_stop_receipts == 0
                and result.configured_max_pending_frames == 8
                and result.configured_max_pending_bytes == 131_072
                and 0 < result.peak_pending_frames <= 8
                and 0 < result.peak_pending_bytes <= 131_072
            )
            if prepared_source is not None and not complete:
                prepared_source.fence("TASK_PREPARATION_TRANSPORT_FAILED")
                self._reconcile_task_preparations()
                return False
            if response is None or unit_id is None:
                return False
            parent_record_id = self._subjects.get(
                (record.binding.session_id, record.subject_id)
            )
            parent = self._records.get(parent_record_id or "")
            if parent is None:
                return False
            key = (response, unit_id)
            if native_source is not None and content_sha256 is not None:
                parent.synthesis_content_sha256[key] = content_sha256
            parent.downlink_results[key] = {
                "complete": complete,
                "sent_frames": result.sent_frames,
                "acknowledged_through_seq": result.acknowledged_through_seq,
                "max_pending_frames": result.configured_max_pending_frames,
                "max_pending_bytes": result.configured_max_pending_bytes,
                "peak_pending_frames": result.peak_pending_frames,
                "peak_pending_bytes": result.peak_pending_bytes,
                "overlap_observed": record.downlink_overlap_observed,
                "content_sha256": content_sha256,
            }
            if record.native_session_key is not None and not complete:
                self._release_stream_source(record)
                self._records.pop(record.record_id, None)
                self._drop_pending_for_record_id(record.record_id)
                parent.synthesis_content_sha256.pop(key, None)
                parent.downlink_results.pop(key, None)
                record.downlink_overlap_record_id = None
                record.pcm.clear()
            return complete

    @staticmethod
    def _revise_native_text(session: _NativeMediaSession, snapshot: dict[str, object]) -> None:
        session.generated_text_revision += 1
        snapshot["revision"] = session.generated_text_revision
        profile_event("native_generated_text", **identity_fields(session.activation.binding),
                      response_id=snapshot["response"]["response_id"],
                      response_generation=snapshot["response"]["response_generation"],
                      status=snapshot["state"], seq=session.generated_text_revision,
                      output_chars=len(snapshot["text"]))

    def read_native_text(self, *, params: Mapping[str, object], routed_session_id: str,
                         connection_id: str, request_origin: str | None) -> dict[str, object]:
        """Authenticated, bounded generated-display snapshots; no presentation effect."""
        binding_keys = {"session_id", "interaction_id", "correlation_id", "activation_id", "activation_generation"}
        if set(params) != binding_keys | {"after_revision"}:
            raise MediaTransportViolation("MEDIA_NATIVE_TEXT_INVALID", "Native text fields are not closed")
        binding = {key: (_safe_uint(params[key], key) if key == "activation_generation"
                         else _required_id(params[key], key)) for key in binding_keys}
        after = _safe_uint(params["after_revision"], "after_revision")
        with self._lock:
            now = self._monotonic()
            authority = self._product_activations.get((binding["session_id"], connection_id, binding["interaction_id"]))
            session = next((item for item in self._native_sessions.values()
                            if item.activation.binding.scope.session_id == binding["session_id"]
                            and all(getattr(item.activation.binding, key) == binding[key]
                                    for key in binding_keys - {"session_id"})
                            and item.activation.connection_id == connection_id), None)
            parent = self._records.get(session.record_id) if session is not None else None
            if (binding["session_id"] != routed_session_id or authority is None or now > authority.expires_at
                or authority.correlation_id != binding["correlation_id"]
                or authority.activation_id != binding["activation_id"]
                or authority.activation_generation != binding["activation_generation"]
                or session is None or session.closed or parent is None or parent.route_completed
                or parent.expected_origin != request_origin or not is_allowed_browser_origin(request_origin)
                or not self._has_retained_product_activation(parent, now)
                or after > session.generated_text_revision):
                raise MediaTransportViolation("MEDIA_NATIVE_TEXT_UNTRUSTED", "Native text requires exact live Web authority")
            candidates = sorted((item for item in session.generated_text.values() if item["revision"] > after and item["text"]),
                                key=lambda item: item["revision"])
            snapshots, snapshot_bytes = [], 0
            for item in candidates:
                snapshot = {key: value for key, value in item.items() if key != "provider_response_id"}
                size = len(canonical_json_bytes(snapshot))
                if len(snapshots) >= 8 or snapshot_bytes + size > 262_144:
                    break
                snapshots.append(snapshot)
                snapshot_bytes += size
            revision = snapshots[-1]["revision"] if len(snapshots) < len(candidates) else session.generated_text_revision
            return {"status": "native_text", "binding": binding, "revision": revision,
                    "snapshots": copy.deepcopy(snapshots)}

    async def stop_native_playout(
        self, *, params: Mapping[str, object], routed_session_id: str,
        connection_id: str, request_origin: str | None,
    ) -> dict[str, object]:
        """Receive the existing exact stop receipt over the retained Web control."""
        if set(params) != {"session_id", "subject_id", "receipt"}:
            raise MediaTransportViolation("MEDIA_INVALID_CONTROL", "playback stop fields are not closed")
        session_id = _required_id(params.get("session_id"), "session_id")
        if session_id != routed_session_id:
            raise MediaTransportViolation("MEDIA_SESSION_MISMATCH", "playback stop requires the routed session")
        subject_id = _required_id(params.get("subject_id"), "subject_id")
        receipt = deserialize_media_control(json.dumps(params.get("receipt")))
        if not isinstance(receipt, MediaPlaybackStopReceipt):
            raise MediaTransportViolation("MEDIA_INVALID_CONTROL", "playback stop receipt is required")
        async with self._native_playout_lock:
            with self._lock:
                now = self._monotonic()
                self._prune(now)
                parent = self._records.get(self._subjects.get((session_id, subject_id), ""))
                record = next((item for item in self._records.values()
                               if item.binding.lease_id == receipt.lease_id), None)
                if (parent is None or record is None or record is parent
                    or parent.binding.connection_id != connection_id
                    or record.binding.connection_id != connection_id
                    or record.binding.session_id != session_id or record.subject_id != subject_id
                    or parent.expected_origin != request_origin or record.expected_origin != request_origin
                    or not is_allowed_browser_origin(request_origin)
                    or now > parent.authority_expires_at or now > record.authority_expires_at
                    or not self._has_retained_product_activation(parent, now)
                    or record.native_activation != parent.native_activation):
                    raise MediaTransportViolation("MEDIA_STOP_UNTRUSTED", "playback stop has no exact live Web authority")
                validate_playback_stop_receipt(record.binding, receipt)
                source = record.downlink_stream_source
                if (receipt.confirmed_through_seq is not None
                    and (not isinstance(source, NativeResponseDownlinkSource)
                         or receipt.confirmed_through_seq >= source.emitted_frames)):
                    raise MediaTransportViolation("MEDIA_NATIVE_PLAYBACK_CURSOR_INVALID", "playback stop cannot confirm unsent audio")
                if record.route_completed:
                    prior = parent.downlink_results.get((record.downlink_response, record.downlink_unit_id))
                    if (prior is None or prior.get("complete") is not True
                        or (receipt.confirmed_through_seq is not None
                            and receipt.confirmed_through_seq > prior["acknowledged_through_seq"])):
                        raise MediaTransportViolation("MEDIA_STOP_UNTRUSTED", "completed download has no exact received cursor")
            expected_session = self._native_sessions.get(record.native_session_key)
            applied = await self.accept_native_playback_stop(record, receipt)
            with self._lock:
                session = self._native_sessions.get(record.native_session_key)
                retained_record = self._records.get(record.record_id)
                # Closing a streaming source can retire its leaf before the
                # Provider cancel returns. Its exact live parent still owns it.
                if (session is None or session is not expected_session or session.closed
                    or self._records.get(parent.record_id) is not parent
                    or (retained_record is not None and retained_record is not record)
                    or not self._has_retained_product_activation(parent, self._monotonic())):
                    raise MediaTransportViolation("MEDIA_STOP_STALE", "playback stop authority retired during acknowledgement")
            if record.route_completed:
                with self._lock:
                    self._records.pop(record.record_id, None)
                    self._drop_pending_for_record_id(record.record_id)
                    key = (record.downlink_response, record.downlink_unit_id)
                    parent.synthesis_content_sha256.pop(key, None)
                    parent.downlink_results.pop(key, None)
                    parent.playout_receipts.pop(key, None)
                    parent.playout_receipt_content_sha256.pop(key, None)
                    session = self._native_sessions.get(record.native_session_key)
                    if session is not None:
                        session.downlink_record_ids.pop(record.downlink_response, None)
                    self._release_stream_source(record)
            return {"status": "native_playout_stopped", "receipt": dict(params["receipt"]), "applied": applied}

    def acknowledge_playout(
        self,
        *,
        params: Mapping[str, object],
        routed_session_id: str,
        connection_id: str,
        user_id: str | None,
        request_origin: str | None,
    ) -> dict[str, object]:
        """Accept one exact browser-render receipt for an authorized TTS unit."""

        expected_keys = set(_PLAYOUT_RECEIPT_REQUEST_FIELDS)
        if set(params) != expected_keys:
            raise MediaTransportViolation(
                "MEDIA_INVALID_PLAYOUT_RECEIPT",
                "media playout receipt fields are not closed",
            )
        session_id = _required_id(params.get("session_id"), "session_id")
        if session_id != routed_session_id:
            raise MediaTransportViolation(
                "MEDIA_SESSION_MISMATCH",
                "media playout receipt must target the dispatcher-owned session",
            )
        subject_id = _required_id(params.get("subject_id"), "subject_id")
        correlation_id = _required_id(params.get("correlation_id"), "correlation_id")
        interaction_id = _required_id(params.get("interaction_id"), "interaction_id")
        response = ResponseRef(
            interaction_id=interaction_id,
            response_id=_required_id(params.get("response_id"), "response_id"),
            response_generation=_safe_uint(
                params.get("response_generation"), "response_generation"
            ),
        )
        unit_id = _required_id(params.get("unit_id"), "unit_id")
        capture_frames_acked = _safe_uint(
            params.get("capture_frames_acked"), "capture_frames_acked"
        )
        rendered_chunks = _safe_uint(params.get("rendered_chunks"), "rendered_chunks")
        rendered_through_seq = _safe_uint(
            params.get("rendered_through_seq"), "rendered_through_seq"
        )
        queue_capacity = _safe_uint(
            params.get("playout_queue_capacity"), "playout_queue_capacity"
        )
        queue_peak_depth = _safe_uint(
            params.get("playout_peak_depth"), "playout_peak_depth"
        )
        if (
            capture_frames_acked <= 0
            or rendered_chunks <= 0
            or rendered_through_seq != rendered_chunks - 1
            or queue_capacity != _PRODUCT_PLAYOUT_QUEUE_CAPACITY
            or not 0 < queue_peak_depth <= queue_capacity
            or params.get("capture_control_ack") != "capture_flush_acked"
            or params.get("playout_state") != "render_completed"
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_PLAYOUT_RECEIPT",
                "media playout receipt does not prove the bounded browser flow",
            )
        owner_connection_id = _required_id(connection_id, "connection_id")
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            record_id = self._subjects.get((session_id, subject_id))
            record = self._records.get(record_id or "")
            session_key = (
                self._native_session_keys_by_record.get(record.record_id)
                if record is not None
                else None
            )
            native_media = bool(
                record is not None
                and record.native_activation is not None
                and session_key is not None
            )
            if (
                record is None
                or record.binding.connection_id != owner_connection_id
                or record.expected_origin != request_origin
                or not is_allowed_browser_origin(request_origin)
                or record.binding.correlation_id != correlation_id
                or record.binding.interaction_id != interaction_id
                or not record.ticket_consumed
                or (not record.route_completed and not native_media)
                or now > record.authority_expires_at
                or not self._has_retained_product_activation(record, now)
            ):
                raise MediaTransportViolation(
                    "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED",
                    "media playout receipt is not bound to the authorized product flow",
                )
            key = (response, unit_id)
            replay_key = (
                (session_key, response, unit_id) if session_key is not None else None
            )
            replay = (
                self._native_playout_replays.get(replay_key)
                if replay_key is not None
                else None
            )
            if replay is not None:
                if replay.request_sha256 != self._native_playout_request_sha256(params):
                    raise MediaTransportViolation(
                        "MEDIA_PLAYOUT_RECEIPT_CONFLICT",
                        "media playout receipt cannot change after acceptance",
                    )
                assert replay_key is not None
                self._native_playout_replays.move_to_end(replay_key)
                return dict(replay.receipt)
            if record.accepted_frames != capture_frames_acked:
                raise MediaTransportViolation(
                    "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED",
                    "media playout receipt is not bound to the authorized product flow",
                )
            if key not in record.synthesis_content_sha256:
                raise MediaTransportViolation(
                    "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED",
                    "media playout receipt is not bound to the authorized product flow",
                )
            downlink = record.downlink_results.get(key)
            if (
                downlink is None
                or downlink.get("complete") is not True
                or not isinstance(downlink.get("overlap_observed"), bool)
                or downlink.get("content_sha256")
                != record.synthesis_content_sha256.get(key)
                or downlink.get("sent_frames") != rendered_chunks
                or downlink.get("acknowledged_through_seq") != rendered_through_seq
            ):
                raise MediaTransportViolation(
                    "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED",
                    "media playout receipt does not match the completed downlink",
                )
            receipt_id = (
                "media-playout-"
                + hashlib.sha256(
                    canonical_json_bytes(
                        {
                            "session_id": session_id,
                            "subject_id": subject_id,
                            "correlation_id": correlation_id,
                            "response": {
                                "interaction_id": response.interaction_id,
                                "response_id": response.response_id,
                                "response_generation": response.response_generation,
                            },
                            "unit_id": unit_id,
                            "capture_frames_acked": capture_frames_acked,
                            "rendered_chunks": rendered_chunks,
                            "rendered_through_seq": rendered_through_seq,
                            "playout_queue_capacity": queue_capacity,
                            "playout_peak_depth": queue_peak_depth,
                        }
                    )
                ).hexdigest()[:32]
            )
            payload = {
                "status": "media_playout_acknowledged",
                "reason_id": "MEDIA_PLAYOUT_RECEIPT_ACCEPTED",
                "receipt_id": receipt_id,
                "session_id": session_id,
                "subject_id": subject_id,
                "correlation_id": correlation_id,
                "interaction_id": response.interaction_id,
                "response_id": response.response_id,
                "response_generation": response.response_generation,
                "unit_id": unit_id,
                "capture_frames_acked": capture_frames_acked,
                "rendered_chunks": rendered_chunks,
                "rendered_through_seq": rendered_through_seq,
                "playout_queue_capacity": queue_capacity,
                "playout_peak_depth": queue_peak_depth,
                "capture_control_ack": "capture_flush_acked",
                "playout_state": "render_completed",
                "duplex_media_observed": downlink["overlap_observed"],
            }
            previous = record.playout_receipts.get(key)
            previous_content_sha256 = record.playout_receipt_content_sha256.get(key)
            content_sha256 = downlink.get("content_sha256")
            if previous is not None and previous_content_sha256 != content_sha256:
                raise MediaTransportViolation(
                    "MEDIA_PLAYOUT_RECEIPT_CONFLICT",
                    "media playout receipt content binding cannot change",
                )
            if previous is not None and previous != payload:
                raise MediaTransportViolation(
                    "MEDIA_PLAYOUT_RECEIPT_CONFLICT",
                    "media playout receipt cannot change after acceptance",
                )
            prepared_child = next((child for child in self._records.values()
                if child.subject_id == record.subject_id and child.binding.session_id == session_id
                and child.binding.connection_id == owner_connection_id
                and child.product_activation_id == record.product_activation_id
                and child.product_activation_generation == record.product_activation_generation
                and child.downlink_response == response and child.downlink_unit_id == unit_id
                and isinstance(child.downlink_stream_source, task_preparation.PreparedNotificationSource)), None)
            if prepared_child is not None:
                try:
                    prepared_child.downlink_stream_source.mark_rendered()
                except task_preparation.PreparationViolation:
                    self._reconcile_task_preparations()
                    raise MediaTransportViolation("MEDIA_PLAYOUT_RECEIPT_UNTRUSTED",
                        "Task preparation no longer owns its render receipt") from None
                self._records.pop(prepared_child.record_id, None)
                self._drop_pending_for_record_id(prepared_child.record_id)
                self._release_stream_source(prepared_child)
            record.playout_receipts[key] = payload
            assert isinstance(content_sha256, str)
            record.playout_receipt_content_sha256[key] = content_sha256
            return dict(payload)

    async def acknowledge_native_playout(
        self,
        *,
        receipt: Mapping[str, object],
        routed_session_id: str,
        connection_id: str,
    ) -> dict[str, object] | None:
        """Forward one accepted Native render receipt to Runtime exactly once."""

        response = ResponseRef(
            interaction_id=_required_id(
                receipt.get("interaction_id"), "interaction_id"
            ),
            response_id=_required_id(receipt.get("response_id"), "response_id"),
            response_generation=_safe_uint(
                receipt.get("response_generation"), "response_generation"
            ),
        )
        session_id = _required_id(receipt.get("session_id"), "session_id")
        unit_id = _required_id(receipt.get("unit_id"), "unit_id")
        if session_id != routed_session_id:
            raise MediaTransportViolation(
                "MEDIA_SESSION_MISMATCH",
                "Native playout ACK must target the routed session",
            )
        key = (response, unit_id)
        async with self._native_playout_lock:
            with self._lock:
                parent_id = self._subjects.get(
                    (session_id, _required_id(receipt.get("subject_id"), "subject_id"))
                )
                parent = self._records.get(parent_id or "")
                session_key = (
                    self._native_session_keys_by_record.get(parent.record_id)
                    if parent is not None
                    else None
                )
                session = (
                    self._native_sessions.get(session_key)
                    if session_key is not None
                    else None
                )
                replay_key = (
                    (session_key, response, unit_id)
                    if session_key is not None
                    else None
                )
                replay = (
                    self._native_playout_replays.get(replay_key)
                    if replay_key is not None
                    else None
                )
                if replay is not None:
                    if (
                        parent is None
                        or parent.binding.connection_id != connection_id
                        or parent.native_activation is None
                        or session is None
                        or session.closed
                        or replay.receipt != dict(receipt)
                    ):
                        return None
                    assert replay_key is not None
                    self._native_playout_replays.move_to_end(replay_key)
                    return dict(replay.receipt)
                downlink = next(
                    (
                        candidate
                        for candidate in self._records.values()
                        if candidate.native_session_key == session_key
                        and candidate.downlink_response == response
                        and candidate.downlink_unit_id == unit_id
                    ),
                    None,
                )
                if (
                    parent is None
                    or parent.binding.connection_id != connection_id
                    or parent.native_activation is None
                    or parent.playout_receipts.get(key) != dict(receipt)
                    or session is None
                    or session.closed
                    or downlink is None
                    or downlink.route_completed is not True
                    or downlink.native_final_unit_id is None
                    or downlink.native_final_unit_seq is None
                ):
                    return None
                ack = PresentationAck(
                    ref=response,
                    surface=PresentationSurface.AUDIO,
                    unit_id=downlink.native_final_unit_id,
                    contiguous_cursor=downlink.native_final_unit_seq,
                    presented_at=(
                        datetime.now(UTC)
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z")
                    ),
                )
            client = self._native_runtime_client
            presentation_ack = getattr(client, "presentation_ack", None)
            if not callable(presentation_ack):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_RUNTIME_UNAVAILABLE",
                    "Native Runtime presentation authority disappeared",
                )
            ack_started = self._monotonic()
            profile_event("native_presentation_ack", **identity_fields(session.activation.binding, response), stage="runtime", outcome="started")
            try:
                result = await presentation_ack(
                    binding=session.activation.binding,
                    capability=session.activation.capability,
                    request_id=self._native_request_id(session, "presentation"),
                    ack=ack,
                )
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                raise
            except Exception as error:
                profile_event("native_presentation_ack", **identity_fields(session.activation.binding, response),
                              stage="runtime", outcome="failed", elapsed_ms=(self._monotonic() - ack_started) * 1000,
                              error_reason=getattr(error, "reason", "NATIVE_ACK_FAILED"), error_type=type(error).__name__)
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_PRESENTATION_ACK_REJECTED",
                    "Native Runtime rejected the exact browser presentation ACK",
                ) from error
            profile_event("native_presentation_ack", **identity_fields(session.activation.binding, response),
                          stage="runtime", outcome="complete", elapsed_ms=(self._monotonic() - ack_started) * 1000)
            if (
                not isinstance(result, Mapping)
                or result.get("kind") != "presentation_ack"
                or result.get("status") != "observed"
                or type(result.get("history_eligible")) is not bool
            ):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_PRESENTATION_ACK_INVALID",
                    "Native Runtime presentation result is not exact",
                )
            projected_receipt = dict(receipt)
            if result.get("history_eligible") is True:
                if downlink.native_generation_completed is not True:
                    raise MediaTransportViolation(
                        "MEDIA_NATIVE_PRESENTATION_ACK_INVALID",
                        "A partial generation cannot publish complete heard history",
                    )
                history = result.get("history")
                if not isinstance(history, Mapping) or set(history) != {
                    "response",
                    "transcript",
                    "presented_at",
                    "message",
                }:
                    raise MediaTransportViolation(
                        "MEDIA_NATIVE_PRESENTATION_ACK_INVALID",
                        "Native assistant history projection is not closed",
                    )
                history_response = history.get("response")
                message = history.get("message")
                transcript = history.get("transcript")
                presented_at = history.get("presented_at")
                timestamp = (
                    message.get("timestamp") if isinstance(message, Mapping) else None
                )
                if (
                    not isinstance(history_response, Mapping)
                    or set(history_response)
                    != {"interaction_id", "response_id", "response_generation"}
                    or ResponseRef(
                        _required_id(
                            history_response.get("interaction_id"),
                            "history.response.interaction_id",
                        ),
                        _required_id(
                            history_response.get("response_id"),
                            "history.response.response_id",
                        ),
                        _safe_uint(
                            history_response.get("response_generation"),
                            "history.response.response_generation",
                        ),
                    )
                    != response
                    or type(transcript) is not str
                    or not transcript
                    or transcript != transcript.strip()
                    or type(presented_at) is not str
                    or not presented_at
                    or not isinstance(message, Mapping)
                    or set(message) != {"id", "role", "content", "timestamp"}
                    or message.get("role") != "assistant"
                    or message.get("content") != transcript
                    or message.get("id")
                    != (
                        "live-voice:"
                        f"{response.interaction_id}:{response.response_id}:"
                        f"{response.response_generation}:native-audio:"
                        f"{hashlib.sha256(transcript.encode('utf-8')).hexdigest()}"
                    )
                    or isinstance(timestamp, bool)
                    or not isinstance(timestamp, (int, float))
                    or not math.isfinite(timestamp)
                    or timestamp < 0
                ):
                    raise MediaTransportViolation(
                        "MEDIA_NATIVE_PRESENTATION_ACK_INVALID",
                        "Native assistant history projection is not exact",
                    )
                projected_receipt["chat_projection"] = {
                    "message": dict(message),
                    "binding": {
                        "response": dict(history_response),
                        "surface": "native_audio",
                        "presented_at": presented_at,
                    },
                }
            try:
                presentation_retired = await session.engine.acknowledge_presentation(
                    response
                )
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                raise
            except Exception as error:
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_PRESENTATION_ACK_REJECTED",
                    "Native Engine rejected the exact browser presentation ACK",
                ) from error
            if type(presentation_retired) is not bool:
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_PRESENTATION_ACK_INVALID",
                    "Native Engine presentation acknowledgement is not exact",
                )
            with self._lock:
                if (
                    self._native_sessions.get(session_key) is not session
                    or session.closed
                    or self._records.get(parent.record_id) is not parent
                    or self._records.get(downlink.record_id) is not downlink
                ):
                    raise MediaTransportViolation(
                        "MEDIA_NATIVE_PRESENTATION_ACK_STALE",
                        "Native presentation authority changed during Runtime admission",
                    )
                assert session_key is not None
                self._retain_native_playout_replay(
                    session_key=session_key,
                    response=response,
                    unit_id=unit_id,
                    receipt=projected_receipt,
                )
                self._records.pop(downlink.record_id, None)
                self._drop_pending_for_record_id(downlink.record_id)
                session.downlink_record_ids.pop(response, None)
                parent.synthesis_content_sha256.pop(key, None)
                parent.playout_receipts.pop(key, None)
                parent.playout_receipt_content_sha256.pop(key, None)
                parent.downlink_results.pop(key, None)
                downlink.downlink_frames = ()
                self._release_stream_source(downlink)
                downlink.downlink_overlap_record_id = None
                downlink.pcm.clear()
                retained_text = session.generated_text.get(response)
                if retained_text is not None and retained_text["state"] != "interrupted":
                    retained_text["state"] = "played"
                    self._revise_native_text(session, retained_text)
            return projected_receipt

    def _drop_pending_for_record_id(self, record_id: str) -> None:
        for ticket, pending_record_id in tuple(self._pending_tickets.items()):
            if pending_record_id == record_id:
                self._pending_tickets.pop(ticket, None)

    def _media_capacity_in_use(self) -> int:
        """Count live media records plus orphaned retained Native close owners."""

        record_owned_sessions = {
            session_key
            for record_id, session_key in self._native_session_keys_by_record.items()
            if record_id in self._records
        }
        record_owned_sessions.update(
            record.native_session_key
            for record in self._records.values()
            if record.native_session_key is not None
        )
        orphaned_close_owners = (
            self._native_close_capacity_reservations - record_owned_sessions
        )
        return len(self._records) + len(orphaned_close_owners)

    def _prune(self, now: float) -> None:
        # Preparation expiry revokes only its exact child, before generic
        # media expiry can remember a revocation for the shared parent subject.
        self._reconcile_task_preparations()
        for authority in self._product_activations.values():
            self._prune_synthesis_transfers(authority.synthesis_content_sha256, now)
        expired = [
            record_id
            for record_id, record in self._records.items()
            if now > record.authority_expires_at
            or (not record.ticket_consumed and now > record.ticket_expires_at)
        ]
        for record_id in expired:
            record = self._records.pop(record_id)
            self._drop_pending_for_record_id(record_id)
            subject_key = (record.binding.session_id, record.subject_id)
            if self._subjects.get(subject_key) == record_id:
                self._subjects.pop(subject_key, None)
            self._remember_revoked(
                record.subject_id,
                (
                    record.binding.session_id,
                    record.binding.correlation_id,
                    record.binding.interaction_id,
                    record.product_activation_id,
                    record.product_activation_generation,
                    record.binding.connection_id,
                ),
            )
            record.pcm.clear()
            record.playout_receipts.clear()
            record.playout_receipt_content_sha256.clear()
            record.downlink_results.clear()
            record.downlink_frames = ()
            self._release_stream_source(record)
            record.downlink_overlap_record_id = None
            self._schedule_streaming_abort(record)
            self._schedule_native_close(record)
        expired_activations = [
            key
            for key, authority in self._product_activations.items()
            if now > authority.expires_at
        ]
        for key in expired_activations:
            authority = self._product_activations.pop(key, None)
            if authority is not None:
                self._revoke_media_for_product_activation(authority)
        self._reconcile_task_preparations()

    def _reconcile_task_preparations(self) -> None:
        """Fence only failed preparation children, including unconsumed tickets."""
        with self._lock:
            self._task_preparations.reconcile()
            for record_id, record in tuple(self._records.items()):
                source = record.downlink_stream_source
                if not isinstance(source, task_preparation.PreparedNotificationSource) or source.reason is None:
                    continue
                self._records.pop(record_id, None)
                self._drop_pending_for_record_id(record_id)
                record.route_completed = True
                parent = self._records.get(self._subjects.get((record.binding.session_id, record.subject_id), ""))
                if parent is not None:
                    key = (record.downlink_response, record.downlink_unit_id)
                    result = parent.downlink_results.get(key)
                    if result is not None and result.get("content_sha256") == record.downlink_content_sha256:
                        parent.downlink_results.pop(key, None)
                record.downlink_content_sha256 = None
                self._release_stream_source(record)

    def _has_retained_product_activation(
        self, record: _MediaAuthority, now: float
    ) -> bool:
        authority = self._product_activations.get(
            (
                record.binding.session_id,
                record.binding.connection_id,
                record.binding.interaction_id,
            )
        )
        return bool(
            authority is not None
            and authority.connection_id == record.binding.connection_id
            and authority.correlation_id == record.binding.correlation_id
            and authority.activation_id == record.product_activation_id
            and authority.activation_generation == record.product_activation_generation
            and now <= authority.expires_at
        )

    def _revoke_media_for_product_activation(
        self, authority: _ProductActivationAuthority
    ) -> None:
        authority.synthesis_content_sha256.clear()
        record_ids = [
            record_id
            for record_id, record in self._records.items()
            if (
                record.binding.session_id == authority.session_id
                and record.binding.connection_id == authority.connection_id
                and record.binding.interaction_id == authority.interaction_id
                and record.binding.correlation_id == authority.correlation_id
                and record.product_activation_id == authority.activation_id
                and record.product_activation_generation
                == authority.activation_generation
            )
        ]
        for record_id in record_ids:
            record = self._records.pop(record_id)
            self._drop_pending_for_record_id(record_id)
            self._subjects.pop((record.binding.session_id, record.subject_id), None)
            self._remember_revoked(
                record.subject_id,
                (
                    record.binding.session_id,
                    record.binding.correlation_id,
                    record.binding.interaction_id,
                    record.product_activation_id,
                    record.product_activation_generation,
                    record.binding.connection_id,
                ),
            )
            record.route_completed = True
            record.recognition_content_sha256 = None
            record.synthesis_content_sha256.clear()
            record.playout_receipts.clear()
            record.playout_receipt_content_sha256.clear()
            record.downlink_results.clear()
            record.downlink_frames = ()
            self._release_stream_source(record)
            record.downlink_overlap_record_id = None
            record.pcm.clear()
            self._schedule_streaming_abort(record)
            self._schedule_native_close(record)

        self._reconcile_task_preparations()

    def _schedule_native_close(self, record: _MediaAuthority) -> None:
        key = self._native_session_keys_by_record.get(record.record_id)
        if key is None:
            return
        with self._lock:
            if self._native_session_keys_by_record.get(record.record_id) != key:
                return
            session = self._native_pending_starts.get(key)
            if session is not None and session.record_id == record.record_id:
                self._fence_native_start(session)
            active = self._native_sessions.get(key)
            if active is not None and active.record_id == record.record_id:
                # Revoke eligibility synchronously with the route, before the
                # asynchronous close performs RPC/socket/resource teardown.
                active.closed = True
            self._native_close_capacity_reservations.add(key)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def close_retained() -> None:
            try:
                await self.close_native_interaction(record)
            except (Exception, asyncio.CancelledError):
                return

        task = loop.create_task(
            close_retained(),
            name=f"live-voice-native-revoke-{record.record_id}",
        )
        self._native_cleanup_tasks.add(task)
        task.add_done_callback(self._native_cleanup_tasks.discard)

    def _schedule_streaming_abort(self, record: _MediaAuthority) -> None:
        if record.streaming_recognition_authority is not None:
            record.streaming_recognition_authority.revoke()
        owner = self._streaming_recognition_owner
        begin_task = record.streaming_recognition_begin_task
        record.streaming_recognition_begin_task = None
        record.streaming_preopen_frames.clear()
        handle = record.streaming_recognition_handle
        record.streaming_recognition_handle = None
        if owner is None or (begin_task is None and (handle is None or handle.settled)):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def abort_retained() -> None:
            try:
                if begin_task is not None:
                    if not begin_task.done():
                        begin_task.cancel()
                    done, _pending = await asyncio.wait({begin_task}, timeout=1.0)
                    if begin_task in done:
                        begin_task.result()
                if handle is not None and not handle.settled:
                    await asyncio.wait_for(owner.abort(handle), timeout=6.0)
            except (Exception, asyncio.CancelledError):
                return

        task = loop.create_task(
            abort_retained(),
            name=f"live-voice-streaming-stt-revoke-{record.record_id}",
        )
        self._streaming_cleanup_tasks.add(task)
        task.add_done_callback(self._streaming_cleanup_tasks.discard)

    def _remember_revoked(
        self,
        subject_id: str,
        binding: tuple[str, str, str, str, int, str],
    ) -> None:
        """Retain only the exact bounded tombstone required for close replay."""

        self._revoked[subject_id] = binding
        self._revoked.move_to_end(subject_id)
        while len(self._revoked) > _MAX_RECORDS:
            self._revoked.popitem(last=False)


def register_dedicated_media_rpc_handlers(
    channel: Any,
    *,
    registry: DedicatedMediaProductRegistry,
) -> None:
    async def activation_handler(
        ws: Any,
        req_id: str,
        params: object,
        session_id: str,
        user_id: str | None = None,
    ) -> None:
        try:
            if not isinstance(params, Mapping):
                raise MediaTransportViolation(
                    "MEDIA_INVALID_ACTIVATION", "media activation must be an object"
                )
            if params.get("session_id") != session_id:
                raise MediaTransportViolation(
                    "MEDIA_SESSION_MISMATCH",
                    "media activation must target the dispatcher-owned session",
                )
            await registry.prepare_streaming_provider()
            connection_id = str(getattr(ws, "_jiuwen_ws_id", "") or id(ws))
            payload = registry.activate(
                params=params,
                request_origin=_request_origin(ws),
                connection_id=connection_id,
                user_id=user_id,
            )
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except MediaTransportViolation as exc:
            await channel.send_response(
                ws, req_id, ok=False, error=str(exc), code=exc.reason_id
            )

    async def close_handler(
        ws: Any,
        req_id: str,
        params: object,
        session_id: str,
        user_id: str | None = None,
    ) -> None:
        try:
            if not isinstance(params, Mapping):
                raise MediaTransportViolation(
                    "MEDIA_INVALID_CLOSE", "media close must be an object"
                )
            connection_id = str(getattr(ws, "_jiuwen_ws_id", "") or id(ws))
            payload = registry.revoke(
                params=params,
                routed_session_id=session_id,
                connection_id=connection_id,
                user_id=user_id,
            )
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except MediaTransportViolation as exc:
            await channel.send_response(
                ws, req_id, ok=False, error=str(exc), code=exc.reason_id
            )

    async def playout_receipt_handler(
        ws: Any,
        req_id: str,
        params: object,
        session_id: str,
        user_id: str | None = None,
    ) -> None:
        try:
            if not isinstance(params, Mapping):
                raise MediaTransportViolation(
                    "MEDIA_INVALID_PLAYOUT_RECEIPT",
                    "media playout receipt must be an object",
                )
            payload = registry.acknowledge_playout(
                params=params,
                routed_session_id=session_id,
                connection_id=str(getattr(ws, "_jiuwen_ws_id", "") or id(ws)),
                user_id=user_id,
                request_origin=_request_origin(ws),
            )
            native_payload = await registry.acknowledge_native_playout(
                receipt=payload,
                routed_session_id=session_id,
                connection_id=str(getattr(ws, "_jiuwen_ws_id", "") or id(ws)),
            )
            if native_payload is not None:
                payload = native_payload
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except MediaTransportViolation as exc:
            await channel.send_response(
                ws, req_id, ok=False, error=str(exc), code=exc.reason_id
            )

    async def playout_stop_handler(ws: Any, req_id: str, params: object,
                                   session_id: str, user_id: str | None = None) -> None:
        try:
            if not isinstance(params, Mapping):
                raise MediaTransportViolation("MEDIA_INVALID_CONTROL", "playback stop must be an object")
            payload = await registry.stop_native_playout(
                params=params, routed_session_id=session_id,
                connection_id=str(getattr(ws, "_jiuwen_ws_id", "") or id(ws)),
                request_origin=_request_origin(ws),
            )
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except Exception as exc:
            await channel.send_response(ws, req_id, ok=False, error=str(exc),
                                        code=getattr(exc, "reason_id", getattr(exc, "reason", "MEDIA_STOP_FAILED")))

    async def native_text_handler(ws: Any, req_id: str, params: object,
                                  session_id: str, user_id: str | None = None) -> None:
        try:
            if not isinstance(params, Mapping):
                raise MediaTransportViolation("MEDIA_NATIVE_TEXT_INVALID", "Native text request must be an object")
            payload = registry.read_native_text(params=params, routed_session_id=session_id,
                connection_id=str(getattr(ws, "_jiuwen_ws_id", "") or id(ws)), request_origin=_request_origin(ws))
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except MediaTransportViolation as exc:
            await channel.send_response(ws, req_id, ok=False, error=str(exc), code=exc.reason_id)

    async def streaming_recognition_result_handler(
        ws: Any,
        req_id: str,
        params: object,
        session_id: str,
        user_id: str | None = None,
    ) -> None:
        del user_id
        try:
            if not isinstance(params, Mapping):
                raise MediaTransportViolation(
                    "MEDIA_INVALID_STREAMING_RESULT",
                    "streaming recognition result must be an object",
                )
            payload = await registry.streaming_recognition_result(
                params=params,
                routed_session_id=session_id,
                connection_id=str(getattr(ws, "_jiuwen_ws_id", "") or id(ws)),
                request_origin=_request_origin(ws),
            )
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except MediaTransportViolation as exc:
            await channel.send_response(
                ws, req_id, ok=False, error=str(exc), code=exc.reason_id
            )

    channel.register_method(MEDIA_ACTIVATE_METHOD, activation_handler)
    def task_preparation_handler(action: str) -> Callable[..., Awaitable[None]]:
        async def handler(ws: Any, req_id: str, params: object, session_id: str,
                          user_id: str | None = None) -> None:
            del user_id
            try:
                if action == "capabilities":
                    payload = registry.task_preparation_capabilities(params)
                else:
                    arguments = {"params": params, "routed_session_id": session_id,
                        "connection_id": str(getattr(ws, "_jiuwen_ws_id", "") or id(ws)),
                        "request_origin": _request_origin(ws)}
                    if action == "prepare":
                        payload = await registry.prepare_task_notification(**arguments)
                    elif action == "claim":
                        payload = await registry.claim_task_notification(**arguments)
                    else:
                        payload = registry.cancel_task_notification(**arguments)
                await channel.send_response(ws, req_id, ok=True, payload=payload)
            except (task_preparation.PreparationViolation, MediaTransportViolation) as exc:
                await channel.send_response(ws, req_id, ok=False,
                    error="Task notification preparation is unavailable", code=exc.reason_id)
        return handler

    for method, action in ((task_preparation.CAPABILITIES_METHOD, "capabilities"),
                          (task_preparation.PREPARE_METHOD, "prepare"),
                          (task_preparation.CLAIM_METHOD, "claim"),
                          (task_preparation.CANCEL_METHOD, "cancel")):
        channel.register_method(method, task_preparation_handler(action))
    channel.register_method(MEDIA_CLOSE_METHOD, close_handler)
    channel.register_method(MEDIA_PLAYOUT_RECEIPT_METHOD, playout_receipt_handler)
    channel.register_method(MEDIA_PLAYOUT_STOP_METHOD, playout_stop_handler)
    channel.register_method(MEDIA_NATIVE_TEXT_METHOD, native_text_handler)
    channel.register_method(
        STREAMING_RECOGNITION_RESULT_METHOD,
        streaming_recognition_result_handler,
    )


async def _authenticate_registered_media_socket(
    registry: DedicatedMediaProductRegistry,
    ws: Any,
    request_path: str,
) -> _MediaAuthority | None:
    """Consume one capability without retaining its bytes in the media coroutine."""

    first_frame: object = None
    parsed_auth: tuple[str, MediaAuthorityBinding] | None = None
    ticket: str | None = None
    claimed_binding: MediaAuthorityBinding | None = None
    try:
        if request_path != MEDIA_ROUTE_PATH:
            return None
        try:
            first_frame = await asyncio.wait_for(
                ws.recv(), timeout=_MEDIA_AUTH_TIMEOUT_SECONDS
            )
        except Exception:
            return None
        parsed_auth = _parse_media_auth_frame(first_frame)
        if parsed_auth is None:
            return None
        ticket, claimed_binding = parsed_auth
        return registry.consume_ticket(
            ticket,
            request_origin=_request_origin(ws),
            claimed_binding=claimed_binding,
        )
    finally:
        # These references must die before the caller awaits a long-lived media
        # leaf; traceback capture from a later route failure cannot recover the
        # already-consumed one-use capability.
        first_frame = None
        parsed_auth = None
        ticket = None
        claimed_binding = None


async def handle_registered_media_socket(
    registry: DedicatedMediaProductRegistry,
    ws: Any,
    request_path: str,
) -> bool:
    """Authenticate the fixed Alpha path before entering the existing leaf."""

    if request_path != MEDIA_ROUTE_PATH:
        return False
    if getattr(ws, "subprotocol", None) != MEDIA_SUBPROTOCOL:
        await ws.close(code=1008, reason="invalid live-voice media route")
        return True

    record = await _authenticate_registered_media_socket(registry, ws, request_path)
    if record is None:
        try:
            await ws.close(code=1008, reason="invalid live-voice media route")
        except Exception:
            pass
        return True
    request = DedicatedMediaRouteRequest(
        enabled=registry.enabled,
        expected_origin=record.expected_origin,
        request_origin=_request_origin(ws),
        binding=record.binding,
        provider_available=True,
        binary_transport_available=True,
    )
    route_completion_retained = False
    try:
        downlink_complete = False
        if record.binding.direction is MediaDirection.DOWNLINK:
            _LOGGER.info("live_voice_native_downlink_socket_attached")
            registry.mark_downlink_started(record)

            def retain_downlink_completion(
                leaf_result: DedicatedMediaSocketLeafResult,
            ) -> None:
                nonlocal downlink_complete, route_completion_retained
                if route_completion_retained:
                    raise MediaTransportViolation(
                        "MEDIA_ROUTE_COMPLETION_DUPLICATE",
                        "media route completion callback was repeated",
                    )
                if record.native_session_key is not None:
                    _LOGGER.info(
                        "live_voice_native_downlink_completed reason=%s sent_frames=%d acknowledged=%s",
                        leaf_result.reason_id,
                        leaf_result.sent_frames,
                        leaf_result.acknowledged_through_seq is not None,
                    )
                downlink_complete = registry.complete_downlink(record, leaf_result)
                route_completion_retained = True

            await run_dedicated_media_downlink_socket_leaf(
                request,
                socket=ws,
                frames=(
                    record.downlink_stream_source
                    if record.downlink_stream_source is not None
                    else record.downlink_frames
                ),
                on_playback_stop=(
                    (
                        lambda receipt: registry.accept_native_playback_stop(
                            record, receipt
                        )
                    )
                    if record.native_session_key is not None
                    else (lambda _receipt: None)
                ),
                on_complete=retain_downlink_completion,
                max_pending_frames=8,
                max_pending_bytes=131_072,
                cleanup_owner=registry._media_leaf_cleanup_owner,
            )
        else:
            native_media = record.native_activation is not None
            if native_media:
                await registry.begin_native_interaction(record)
            else:
                registry.start_streaming_recognition(record)
                # Give an immediately-ready Provider one scheduling turn, but never
                # put its network connect deadline in front of browser media attach.
                await asyncio.sleep(0)

            def retain_uplink_completion(
                leaf_result: DedicatedMediaSocketLeafResult,
            ) -> None:
                nonlocal route_completion_retained
                if route_completion_retained:
                    raise MediaTransportViolation(
                        "MEDIA_ROUTE_COMPLETION_DUPLICATE",
                        "media route completion callback was repeated",
                    )
                if (
                    isinstance(leaf_result, DedicatedMediaSocketLeafResult)
                    and not leaf_result.cleanup_complete
                ):
                    _LOGGER.warning(
                        "live_voice_media_cleanup_pending pending_tasks=%d",
                        leaf_result.cleanup_pending_tasks,
                    )
                registry.complete_route(record, leaf_result)
                route_completion_retained = True

            def retain_uplink_frame(frame: MediaAudioFrame) -> None:
                if native_media:
                    try:
                        registry.accept_native_frame(record, frame)
                    except Exception as error:
                        reason = getattr(error, "reason_id", None)
                        if not isinstance(reason, str) or not reason.startswith(
                            "MEDIA_NATIVE_"
                        ):
                            reason = "MEDIA_NATIVE_INPUT_CONSUMER_UNCLASSIFIED"
                        detail = (
                            str(error)
                            if reason == "MEDIA_NATIVE_INPUT_FENCE_REJECTED"
                            else "not_applicable"
                        )
                        _LOGGER.error(
                            "live_voice_native_uplink_consumer_failed reason=%s "
                            "detail=%s",
                            reason,
                            detail,
                        )
                        raise
                else:
                    # Batch fallback retains only its existing bounded digest path;
                    # the Provider mirror is independently bounded and cannot
                    # interrupt capture if it degrades.
                    registry.accept_frame(record, frame)
                    registry.accept_streaming_frame(record, frame)

            result = await run_dedicated_media_socket_leaf(
                request,
                socket=ws,
                on_audio_frame=retain_uplink_frame,
                on_complete=retain_uplink_completion,
                on_uplink_frame_accepted=lambda acknowledgement, accepted_at: (
                    registry.observe_uplink_frame_accepted(
                        record, acknowledgement, accepted_at
                    )
                ),
                on_uplink_ack_sent=lambda acknowledgement: (
                    registry.observe_uplink_ack_sent(record, acknowledgement)
                ),
                next_speech_start=(
                    (lambda: registry.wait_native_speech_start(record))
                    if native_media
                    else (
                        (lambda: registry.wait_streaming_speech_start(record))
                        if record.end_of_turn_capability == MEDIA_END_OF_TURN_CAPABILITY
                        else None
                    )
                ),
                next_end_of_turn=(
                    (lambda: registry.wait_native_end_of_turn(record))
                    if native_media
                    else (
                        (lambda: registry.wait_streaming_end_of_turn(record))
                        if record.end_of_turn_capability == MEDIA_END_OF_TURN_CAPABILITY
                        else None
                    )
                ),
                repeat_speech_boundaries=native_media,
                fail_on_speech_boundary_error=not native_media,
                cleanup_owner=(
                    registry._media_leaf_cleanup_owner
                    if native_media
                    or record.end_of_turn_capability == MEDIA_END_OF_TURN_CAPABILITY
                    else None
                ),
            )
            if native_media:
                await registry.close_native_interaction(record)
            elif (
                result.activated
                and result.accepted_frames > 0
                and record.recognition_content_sha256 is not None
            ):
                await registry.finish_streaming_recognition(record)
            else:
                await registry.abort_streaming_recognition(record)
        if not route_completion_retained:
            raise MediaTransportViolation(
                "MEDIA_ROUTE_COMPLETION_UNAVAILABLE",
                "media route completion callback was not retained",
            )
    except BaseException:
        if record.binding.direction is MediaDirection.UPLINK:
            if record.native_activation is not None:
                await asyncio.shield(registry.close_native_interaction(record))
            else:
                await asyncio.shield(registry.abort_streaming_recognition(record))
        if not route_completion_retained:
            registry.abort_route(record)
        cleanup_snapshot = registry.media_leaf_cleanup_snapshot
        if not cleanup_snapshot.cleanup_complete:
            _LOGGER.warning(
                "live_voice_media_cleanup_pending pending_tasks=%d",
                cleanup_snapshot.retained_tasks,
            )
        raise
    return True


__all__ = [
    "DedicatedMediaProductRegistry",
    "MEDIA_ACTIVATE_METHOD",
    "MEDIA_AUTH_CONTRACT_VERSION",
    "MEDIA_CLOSE_METHOD",
    "MEDIA_PLAYOUT_RECEIPT_METHOD",
    "MEDIA_FEATURE_ENV",
    "MEDIA_END_OF_TURN_FEATURE_ENV",
    "MEDIA_ROUTE_PATH",
    "MEDIA_SUBPROTOCOL",
    "handle_registered_media_socket",
    "register_dedicated_media_rpc_handlers",
]
