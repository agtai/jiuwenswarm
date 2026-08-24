"""Provider-neutral Browser <-> Gateway realtime media transport seam.

This module owns the closed ``LVM1`` binary frame and semantic media control
objects.  It deliberately does not open sockets, acquire devices, start tasks,
or call a speech Provider.  All authority bindings are supplied by trusted
server composition and are validated, never derived from client claims.
"""

from __future__ import annotations

import json
import math
import struct
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Callable, Deque, Mapping, TypeAlias


MEDIA_CONTRACT_VERSION = "live-voice.media.v1"
MEDIA_TRANSPORT_KIND = "websocket_binary"
MEDIA_WIRE_CODEC = "pcm_f32le"
MEDIA_CAPTURE_ENCODING = "pcm_f32"
MEDIA_FRAME_DURATION_MS = 20
MEDIA_END_OF_TURN_CAPABILITY = "media.end_of_turn.v1"

_WIRE_MAGIC = b"LVM1"
_WIRE_VERSION = 1
_WIRE_AUDIO_KIND = 1
_WIRE_HEADER = struct.Struct("<4sBBHQQQI")
_MAX_SAFE_INTEGER = (1 << 53) - 1
_MIN_SAMPLE_RATE_HZ = 8_000
_MAX_SAMPLE_RATE_HZ = 192_000
_MAX_LEASE_ID_BYTES = 128
_MAX_ID_CHARS = 256
_MAX_CONTROL_BYTES = 16_384
_MAX_PCM_F32_ABS = 3.4028234663852886e38
_MAX_PCM_PAYLOAD_BYTES = (_MAX_SAMPLE_RATE_HZ // 50) * 4
_MAX_BINARY_FRAME_BYTES = (
    _WIRE_HEADER.size + _MAX_LEASE_ID_BYTES + _MAX_PCM_PAYLOAD_BYTES
)


class MediaDirection(str, Enum):
    UPLINK = "uplink"
    DOWNLINK = "downlink"


class MediaGenerationKind(str, Enum):
    CAPTURE = "capture"
    RESPONSE = "response"


class BinarySendDisposition(str, Enum):
    SENT = "sent"
    BACKPRESSURED = "backpressured"
    CLOSED = "closed"


class MediaPlaybackStopOutcome(str, Enum):
    LOCAL_FENCE_ESTABLISHED = "local_fence_established"
    LOCAL_FENCE_ESTABLISHED_SOURCE_UNKNOWN = "local_fence_established_source_unknown"
    TARGET_MISMATCH = "target_mismatch"
    NO_ACTIVE_TARGET = "no_active_target"
    ALREADY_STOPPED = "already_stopped"
    LOCAL_FENCE_FAILED = "local_fence_failed"
    FEATURE_DISABLED = "feature_disabled"
    ADAPTER_CLOSED = "adapter_closed"


class MediaDetachReason(str, Enum):
    ACK_GAP = "MEDIA_ACK_GAP"
    ACK_OUT_OF_ORDER = "MEDIA_ACK_OUT_OF_ORDER"
    ACK_UNSENT = "MEDIA_ACK_UNSENT"
    BINDING_MISMATCH = "MEDIA_BINDING_MISMATCH"
    CANCEL_SCOPE_VIOLATION = "MEDIA_CANCEL_SCOPE_VIOLATION"
    CONSUMER_FAILED = "MEDIA_CONSUMER_FAILED"
    CURSOR_MISMATCH = "MEDIA_CURSOR_MISMATCH"
    DUPLICATE_ATTACH = "MEDIA_DUPLICATE_ATTACH"
    DUPLICATE_OR_OUT_OF_ORDER = "MEDIA_DUPLICATE_OR_OUT_OF_ORDER"
    INVALID_FRAME = "MEDIA_INVALID_FRAME"
    LEASE_CLOSED = "MEDIA_LEASE_CLOSED"
    LOCAL_CLOSE = "MEDIA_LOCAL_CLOSE"
    MALFORMED_FRAME = "MEDIA_MALFORMED_FRAME"
    NONFINITE_AUDIO = "MEDIA_NONFINITE_AUDIO"
    NOT_ATTACHED = "MEDIA_NOT_ATTACHED"
    OVERSIZED_FRAME = "MEDIA_OVERSIZED_FRAME"
    PEER_CLOSE = "MEDIA_PEER_CLOSE"
    RECOGNITION_CONTINUATION = "MEDIA_RECOGNITION_CONTINUATION"
    SEQUENCE_GAP = "MEDIA_SEQUENCE_GAP"
    SEQUENCE_VIOLATION = "MEDIA_SEQUENCE_VIOLATION"
    STALE_GENERATION = "MEDIA_STALE_GENERATION"
    STREAMING_TTS_TEXT_OR_RETRY = "MEDIA_STREAMING_TTS_TEXT_OR_RETRY"
    TRANSPORT_CLOSED = "MEDIA_TRANSPORT_CLOSED"
    TRANSPORT_PROTOCOL_ERROR = "MEDIA_TRANSPORT_PROTOCOL_ERROR"
    TRANSPORT_SEND_FAILED = "MEDIA_TRANSPORT_SEND_FAILED"


def _coerce_detach_reason(
    value: object,
    *,
    fallback: MediaDetachReason = MediaDetachReason.LOCAL_CLOSE,
) -> MediaDetachReason:
    if isinstance(value, MediaDetachReason):
        return value
    try:
        return MediaDetachReason(value)
    except (TypeError, ValueError):
        return fallback


class MediaTransportViolation(ValueError):
    """A closed-contract violation carrying a stable detach reason."""

    def __init__(self, reason_id: str, message: str) -> None:
        super().__init__(message)
        self.reason_id = reason_id


def _require_id(name: str, value: str, *, max_chars: int = _MAX_ID_CHARS) -> None:
    if not isinstance(value, str) or not value or len(value) > max_chars:
        raise MediaTransportViolation("MEDIA_INVALID_BINDING", f"{name} is invalid")


def _require_safe_uint(
    name: str, value: int, *, reason_id: str = "MEDIA_INVALID_BINDING"
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= _MAX_SAFE_INTEGER
    ):
        raise MediaTransportViolation(
            reason_id, f"{name} is not a safe unsigned integer"
        )


def _require_zero_business_cancel(value: object, *, reason_id: str) -> None:
    if type(value) is not int or value != 0:
        raise MediaTransportViolation(
            reason_id, "business cancellation delta must be canonical integer zero"
        )


@dataclass(frozen=True, slots=True)
class MediaGenerationBinding:
    kind: MediaGenerationKind
    id: str
    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MediaGenerationKind):
            raise MediaTransportViolation(
                "MEDIA_INVALID_BINDING", "generation kind is not closed"
            )
        _require_id("generation.id", self.id)
        _require_safe_uint("generation.value", self.value)


@dataclass(frozen=True, slots=True)
class MediaPlayoutBinding:
    response_id: str
    response_generation: int
    unit_id: str

    def __post_init__(self) -> None:
        _require_id("playout.response_id", self.response_id)
        _require_safe_uint("playout.response_generation", self.response_generation)
        _require_id("playout.unit_id", self.unit_id)


@dataclass(frozen=True, slots=True)
class MediaFrameFormat:
    sample_rate_hz: int
    samples_per_channel: int
    encoding: str = MEDIA_CAPTURE_ENCODING
    byte_order: str = "little"
    channel_count: int = 1
    frame_duration_ms: int = MEDIA_FRAME_DURATION_MS

    def __post_init__(self) -> None:
        if self.encoding != MEDIA_CAPTURE_ENCODING or self.byte_order != "little":
            raise MediaTransportViolation(
                "MEDIA_INVALID_FORMAT", "only pcm_f32 little-endian is accepted"
            )
        if (
            isinstance(self.channel_count, bool)
            or not isinstance(self.channel_count, int)
            or self.channel_count != 1
            or isinstance(self.frame_duration_ms, bool)
            or not isinstance(self.frame_duration_ms, int)
            or self.frame_duration_ms != MEDIA_FRAME_DURATION_MS
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_FORMAT", "only 20 ms mono frames are accepted"
            )
        if (
            isinstance(self.sample_rate_hz, bool)
            or not isinstance(self.sample_rate_hz, int)
            or not _MIN_SAMPLE_RATE_HZ <= self.sample_rate_hz <= _MAX_SAMPLE_RATE_HZ
            or self.sample_rate_hz % 50 != 0
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_FORMAT",
                "sample rate cannot represent exact 20 ms frames",
            )
        if (
            isinstance(self.samples_per_channel, bool)
            or not isinstance(self.samples_per_channel, int)
            or self.samples_per_channel != self.sample_rate_hz // 50
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_FORMAT",
                "sample count does not match the actual sample rate",
            )


@dataclass(frozen=True, slots=True, repr=False)
class MediaAuthorityBinding:
    """Immutable, server-authored authority and presentation binding."""

    lease_id: str
    authority_evidence_id: str
    connection_id: str
    connection_epoch: int
    session_id: str
    media_session_id: str
    interaction_id: str
    track_id: str
    correlation_id: str
    direction: MediaDirection
    generation: MediaGenerationBinding
    frame_format: MediaFrameFormat
    playout: MediaPlayoutBinding | None = None

    def __post_init__(self) -> None:
        _require_id("lease_id", self.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        if len(self.lease_id.encode("utf-8")) > _MAX_LEASE_ID_BYTES:
            raise MediaTransportViolation(
                "MEDIA_INVALID_BINDING", "lease_id is too large when encoded"
            )
        for name in (
            "authority_evidence_id",
            "connection_id",
            "session_id",
            "media_session_id",
            "interaction_id",
            "track_id",
            "correlation_id",
        ):
            _require_id(name, getattr(self, name))
        _require_safe_uint("connection_epoch", self.connection_epoch)
        if not isinstance(self.direction, MediaDirection):
            raise MediaTransportViolation(
                "MEDIA_INVALID_BINDING", "direction is not closed"
            )
        expected_kind = (
            MediaGenerationKind.CAPTURE
            if self.direction is MediaDirection.UPLINK
            else MediaGenerationKind.RESPONSE
        )
        if self.generation.kind is not expected_kind:
            raise MediaTransportViolation(
                "MEDIA_INVALID_BINDING", "generation kind does not match direction"
            )
        if self.direction is MediaDirection.UPLINK and self.playout is not None:
            raise MediaTransportViolation(
                "MEDIA_INVALID_BINDING", "uplink must not carry playout authority"
            )
        if self.direction is MediaDirection.DOWNLINK:
            if self.playout is None:
                raise MediaTransportViolation(
                    "MEDIA_INVALID_BINDING", "downlink requires exact playout authority"
                )
            if (
                self.generation.id != self.playout.response_id
                or self.generation.value != self.playout.response_generation
            ):
                raise MediaTransportViolation(
                    "MEDIA_INVALID_BINDING", "response generation is not exact"
                )


@dataclass(frozen=True, slots=True)
class MediaAttach:
    binding: MediaAuthorityBinding
    type: str = field(default="media.attach", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.binding, MediaAuthorityBinding):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONTROL", "attach requires trusted binding"
            )


@dataclass(frozen=True, slots=True)
class MediaAck:
    lease_id: str
    generation: int
    through_seq: int
    type: str = field(default="media.ack", init=False)

    def __post_init__(self) -> None:
        _require_id("lease_id", self.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        _require_safe_uint("generation", self.generation)
        _require_safe_uint("through_seq", self.through_seq)


@dataclass(frozen=True, slots=True)
class MediaDetach:
    lease_id: str
    generation: int
    reason_id: MediaDetachReason
    through_seq: int | None = None
    business_cancel_count_delta: int = 0
    type: str = field(default="media.detach", init=False)

    def __post_init__(self) -> None:
        _require_id("lease_id", self.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        _require_safe_uint("generation", self.generation)
        if not isinstance(self.reason_id, MediaDetachReason):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONTROL", "detach reason is not closed"
            )
        if self.through_seq is not None:
            _require_safe_uint("through_seq", self.through_seq)
        _require_zero_business_cancel(
            self.business_cancel_count_delta,
            reason_id="MEDIA_CANCEL_SCOPE_VIOLATION",
        )


@dataclass(frozen=True, slots=True)
class MediaSpeechStart:
    lease_id: str
    generation: int
    provider_start_ms: int
    capability_version: str = MEDIA_END_OF_TURN_CAPABILITY
    detector: str = "server_vad"
    timing_basis: str = "provider_time"
    timing_provenance: str = "adapter_derived"
    create_response: bool = False
    interrupt_response: bool = False
    business_cancel_count_delta: int = 0
    type: str = field(default="media.speech_start", init=False)

    def __post_init__(self) -> None:
        _require_id("lease_id", self.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        _require_safe_uint("generation", self.generation)
        _require_safe_uint("provider_start_ms", self.provider_start_ms)
        if (
            self.capability_version != MEDIA_END_OF_TURN_CAPABILITY
            or self.detector != "server_vad"
            or self.timing_basis != "provider_time"
            or self.timing_provenance != "adapter_derived"
            or self.create_response is not False
            or self.interrupt_response is not False
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONTROL", "speech-start control contract is not exact"
            )
        _require_zero_business_cancel(
            self.business_cancel_count_delta,
            reason_id="MEDIA_CANCEL_SCOPE_VIOLATION",
        )


@dataclass(frozen=True, slots=True)
class MediaEndOfTurn:
    lease_id: str
    generation: int
    provider_start_ms: int
    provider_end_ms: int
    capability_version: str = MEDIA_END_OF_TURN_CAPABILITY
    detector: str = "server_vad"
    speech_started_observed: bool = True
    timing_basis: str = "provider_time"
    timing_provenance: str = "adapter_derived"
    create_response: bool = False
    interrupt_response: bool = False
    business_cancel_count_delta: int = 0
    type: str = field(default="media.end_of_turn", init=False)

    def __post_init__(self) -> None:
        _require_id("lease_id", self.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        _require_safe_uint("generation", self.generation)
        _require_safe_uint("provider_start_ms", self.provider_start_ms)
        _require_safe_uint("provider_end_ms", self.provider_end_ms)
        if self.provider_end_ms < self.provider_start_ms:
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONTROL", "EOT stop precedes speech start"
            )
        if (
            self.capability_version != MEDIA_END_OF_TURN_CAPABILITY
            or self.detector != "server_vad"
            or self.speech_started_observed is not True
            or self.timing_basis != "provider_time"
            or self.timing_provenance != "adapter_derived"
            or self.create_response is not False
            or self.interrupt_response is not False
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONTROL", "EOT control contract is not exact"
            )
        _require_zero_business_cancel(
            self.business_cancel_count_delta,
            reason_id="MEDIA_CANCEL_SCOPE_VIOLATION",
        )


@dataclass(frozen=True, slots=True)
class MediaPlaybackStopReceipt:
    lease_id: str
    response_id: str
    response_generation: int
    unit_id: str
    outcome: MediaPlaybackStopOutcome
    confirmed_through_seq: int | None = None
    business_cancel_count_delta: int = 0
    type: str = field(default="media.playback_stop_receipt", init=False)

    def __post_init__(self) -> None:
        _require_id("lease_id", self.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        _require_id("response_id", self.response_id)
        _require_safe_uint("response_generation", self.response_generation)
        _require_id("unit_id", self.unit_id)
        if not isinstance(self.outcome, MediaPlaybackStopOutcome):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONTROL", "playback stop outcome is not closed"
            )
        if self.confirmed_through_seq is not None:
            _require_safe_uint("confirmed_through_seq", self.confirmed_through_seq)
        _require_zero_business_cancel(
            self.business_cancel_count_delta,
            reason_id="MEDIA_CANCEL_SCOPE_VIOLATION",
        )


MediaControl: TypeAlias = (
    MediaAttach
    | MediaAck
    | MediaDetach
    | MediaSpeechStart
    | MediaEndOfTurn
    | MediaPlaybackStopReceipt
)


@dataclass(frozen=True, slots=True)
class MediaAudioFrame:
    seq: int
    sample_cursor: int
    samples: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class MediaCapability:
    contract_version: str
    transport_kind: str
    wire_codec: str
    capture_encoding: str
    frame_duration_ms: int
    channel_count: int
    provider_neutral: bool
    evidence_scope: str
    contract_vector_evidence_id: str
    formal_route_ready: bool
    real_transport_observed: bool
    registration_evidence_id: str | None
    runtime_evidence_id: str | None


@dataclass(frozen=True, slots=True)
class MediaActivationRequest:
    enabled: bool
    binding: MediaAuthorityBinding | None
    provider_available: bool
    transport_available: bool
    max_pending_frames: int = 8
    max_pending_bytes: int = 131_072


@dataclass(frozen=True, slots=True)
class InactiveMediaActivation:
    active: bool
    reason_id: str
    capability: MediaCapability


@dataclass(frozen=True, slots=True)
class ActiveMediaActivation:
    active: bool
    binding: MediaAuthorityBinding
    sender: "BoundedMediaSender"
    receiver: "StrictMediaReceiver"
    capability: MediaCapability


MediaActivation: TypeAlias = InactiveMediaActivation | ActiveMediaActivation


@dataclass(frozen=True, slots=True)
class MediaEnqueueResult:
    accepted: bool
    reason_id: str


@dataclass(frozen=True, slots=True)
class MediaDrainResult:
    sent_frames: int
    pending_frames: int
    pending_bytes: int
    reason_id: str


@dataclass(frozen=True, slots=True)
class MediaCloseResult:
    was_active: bool
    reason_id: MediaDetachReason
    dropped_frames: int
    dropped_bytes: int
    detach: MediaDetach | None
    business_cancel_count_delta: int = 0

    def __post_init__(self) -> None:
        _require_zero_business_cancel(
            self.business_cancel_count_delta,
            reason_id="MEDIA_CANCEL_SCOPE_VIOLATION",
        )


def _capability() -> MediaCapability:
    return MediaCapability(
        contract_version=MEDIA_CONTRACT_VERSION,
        transport_kind=MEDIA_TRANSPORT_KIND,
        wire_codec=MEDIA_WIRE_CODEC,
        capture_encoding=MEDIA_CAPTURE_ENCODING,
        frame_duration_ms=MEDIA_FRAME_DURATION_MS,
        channel_count=1,
        provider_neutral=True,
        evidence_scope="contract_only",
        contract_vector_evidence_id="live-voice.media.v1.roundtrip-vector",
        formal_route_ready=False,
        real_transport_observed=False,
        registration_evidence_id=None,
        runtime_evidence_id=None,
    )


def create_gateway_media_activation(
    request: MediaActivationRequest,
    *,
    on_audio_frame: Callable[[MediaAudioFrame], None],
) -> MediaActivation:
    """Create inert seams only after all externally resolved gates are present."""

    reason_id: str | None = None
    if request.enabled is not True:
        reason_id = "MEDIA_FEATURE_DISABLED"
    elif not isinstance(request.binding, MediaAuthorityBinding):
        reason_id = "MEDIA_AUTHORITY_UNAVAILABLE"
    elif request.provider_available is not True:
        reason_id = "MEDIA_PROVIDER_UNAVAILABLE"
    elif request.transport_available is not True:
        reason_id = "MEDIA_TRANSPORT_UNAVAILABLE"
    if reason_id is not None:
        return InactiveMediaActivation(
            active=False, reason_id=reason_id, capability=_capability()
        )
    if not callable(on_audio_frame):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "audio consumer must be callable"
        )
    binding = request.binding
    assert binding is not None
    return ActiveMediaActivation(
        active=True,
        binding=binding,
        sender=BoundedMediaSender(
            binding,
            max_pending_frames=request.max_pending_frames,
            max_pending_bytes=request.max_pending_bytes,
        ),
        receiver=StrictMediaReceiver(binding, on_audio_frame=on_audio_frame),
        capability=_capability(),
    )


def _check_control_uint(name: str, value: int) -> None:
    try:
        _require_safe_uint(name, value)
    except MediaTransportViolation as error:
        raise MediaTransportViolation("MEDIA_MALFORMED_CONTROL", str(error)) from error


def _check_control_id(
    name: str, value: object, *, max_chars: int = _MAX_ID_CHARS
) -> str:
    if not isinstance(value, str):
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_CONTROL", f"{name} is not a string"
        )
    try:
        _require_id(name, value, max_chars=max_chars)
    except MediaTransportViolation as error:
        raise MediaTransportViolation("MEDIA_MALFORMED_CONTROL", str(error)) from error
    return value


def _binding_to_dict(binding: MediaAuthorityBinding) -> dict[str, object]:
    result = asdict(binding)
    result["direction"] = binding.direction.value
    result["generation"]["kind"] = binding.generation.kind.value  # type: ignore[index]
    return result


def _control_to_dict(control: MediaControl) -> dict[str, object]:
    if isinstance(control, MediaAttach):
        return {
            "type": control.type,
            "contract_version": MEDIA_CONTRACT_VERSION,
            "binding": _binding_to_dict(control.binding),
        }
    result = asdict(control)
    result["contract_version"] = MEDIA_CONTRACT_VERSION
    return result


def serialize_media_control(control: MediaControl) -> str:
    """Serialize semantic control state only at the transport boundary."""

    if isinstance(control, MediaAck):
        _require_id("lease_id", control.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        _require_safe_uint("generation", control.generation)
        _require_safe_uint("through_seq", control.through_seq)
    elif isinstance(control, MediaDetach):
        _require_id("lease_id", control.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        _require_safe_uint("generation", control.generation)
        if not isinstance(control.reason_id, MediaDetachReason):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONTROL", "detach reason is not closed"
            )
        if control.through_seq is not None:
            _require_safe_uint("through_seq", control.through_seq)
        _require_zero_business_cancel(
            control.business_cancel_count_delta,
            reason_id="MEDIA_CANCEL_SCOPE_VIOLATION",
        )
    elif isinstance(control, MediaPlaybackStopReceipt):
        _require_id("lease_id", control.lease_id, max_chars=_MAX_LEASE_ID_BYTES)
        _require_id("response_id", control.response_id)
        _require_safe_uint("response_generation", control.response_generation)
        _require_id("unit_id", control.unit_id)
        if not isinstance(control.outcome, MediaPlaybackStopOutcome):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONTROL", "playback stop outcome is not closed"
            )
        if control.confirmed_through_seq is not None:
            _require_safe_uint("confirmed_through_seq", control.confirmed_through_seq)
        _require_zero_business_cancel(
            control.business_cancel_count_delta,
            reason_id="MEDIA_CANCEL_SCOPE_VIOLATION",
        )
    elif isinstance(control, (MediaSpeechStart, MediaEndOfTurn)):
        # Frozen typed controls were validated at construction.
        pass
    elif not isinstance(control, MediaAttach):
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_CONTROL", "unknown semantic control object"
        )
    text = json.dumps(_control_to_dict(control), separators=(",", ":"), sort_keys=True)
    if len(text.encode("utf-8")) > _MAX_CONTROL_BYTES:
        raise MediaTransportViolation(
            "MEDIA_OVERSIZED_CONTROL", "control message exceeds its bound"
        )
    return text


def _require_exact_keys(
    value: Mapping[str, object], expected: set[str], name: str
) -> None:
    if set(value) != expected:
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_CONTROL", f"{name} fields are not closed"
        )


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_CONTROL", f"{name} is not an object"
        )
    return value


def _parse_binding(value: object) -> MediaAuthorityBinding:
    raw = _require_mapping(value, "binding")
    _require_exact_keys(
        raw,
        {
            "lease_id",
            "authority_evidence_id",
            "connection_id",
            "connection_epoch",
            "session_id",
            "media_session_id",
            "interaction_id",
            "track_id",
            "correlation_id",
            "direction",
            "generation",
            "frame_format",
            "playout",
        },
        "binding",
    )
    generation = _require_mapping(raw["generation"], "generation")
    _require_exact_keys(generation, {"kind", "id", "value"}, "generation")
    frame_format = _require_mapping(raw["frame_format"], "frame_format")
    _require_exact_keys(
        frame_format,
        {
            "sample_rate_hz",
            "samples_per_channel",
            "encoding",
            "byte_order",
            "channel_count",
            "frame_duration_ms",
        },
        "frame_format",
    )
    playout_raw = raw["playout"]
    playout = None
    if playout_raw is not None:
        playout_map = _require_mapping(playout_raw, "playout")
        _require_exact_keys(
            playout_map, {"response_id", "response_generation", "unit_id"}, "playout"
        )
        playout = MediaPlayoutBinding(
            response_id=_check_control_id(
                "playout.response_id", playout_map["response_id"]
            ),
            response_generation=playout_map["response_generation"],  # type: ignore[arg-type]
            unit_id=_check_control_id("playout.unit_id", playout_map["unit_id"]),
        )
    try:
        return MediaAuthorityBinding(
            lease_id=_check_control_id(
                "lease_id", raw["lease_id"], max_chars=_MAX_LEASE_ID_BYTES
            ),
            authority_evidence_id=_check_control_id(
                "authority_evidence_id", raw["authority_evidence_id"]
            ),
            connection_id=_check_control_id("connection_id", raw["connection_id"]),
            connection_epoch=raw["connection_epoch"],  # type: ignore[arg-type]
            session_id=_check_control_id("session_id", raw["session_id"]),
            media_session_id=_check_control_id(
                "media_session_id", raw["media_session_id"]
            ),
            interaction_id=_check_control_id("interaction_id", raw["interaction_id"]),
            track_id=_check_control_id("track_id", raw["track_id"]),
            correlation_id=_check_control_id("correlation_id", raw["correlation_id"]),
            direction=MediaDirection(raw["direction"]),
            generation=MediaGenerationBinding(
                kind=MediaGenerationKind(generation["kind"]),
                id=_check_control_id("generation.id", generation["id"]),
                value=generation["value"],  # type: ignore[arg-type]
            ),
            frame_format=MediaFrameFormat(
                sample_rate_hz=frame_format["sample_rate_hz"],  # type: ignore[arg-type]
                samples_per_channel=frame_format["samples_per_channel"],  # type: ignore[arg-type]
                encoding=_check_control_id(
                    "frame_format.encoding", frame_format["encoding"]
                ),
                byte_order=_check_control_id(
                    "frame_format.byte_order", frame_format["byte_order"]
                ),
                channel_count=frame_format["channel_count"],  # type: ignore[arg-type]
                frame_duration_ms=frame_format["frame_duration_ms"],  # type: ignore[arg-type]
            ),
            playout=playout,
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, MediaTransportViolation):
            raise
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_CONTROL", "binding contains invalid enum values"
        ) from error


def deserialize_media_control(text: str) -> MediaControl:
    """Decode closed control JSON into typed semantic objects."""

    if not isinstance(text, str) or len(text.encode("utf-8")) > _MAX_CONTROL_BYTES:
        raise MediaTransportViolation(
            "MEDIA_OVERSIZED_CONTROL", "control message exceeds its bound"
        )
    try:
        raw = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_CONTROL", "control message is not valid JSON"
        ) from error
    value = _require_mapping(raw, "control")
    control_type = value.get("type")
    if value.get("contract_version") != MEDIA_CONTRACT_VERSION:
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_CONTROL", "control contract version is not accepted"
        )
    if control_type == "media.attach":
        _require_exact_keys(value, {"type", "contract_version", "binding"}, "attach")
        return MediaAttach(_parse_binding(value["binding"]))
    if control_type == "media.ack":
        _require_exact_keys(
            value,
            {"type", "contract_version", "lease_id", "generation", "through_seq"},
            "ack",
        )
        _check_control_uint("generation", value["generation"])  # type: ignore[arg-type]
        _check_control_uint("through_seq", value["through_seq"])  # type: ignore[arg-type]
        return MediaAck(
            _check_control_id(
                "lease_id", value["lease_id"], max_chars=_MAX_LEASE_ID_BYTES
            ),
            value["generation"],  # type: ignore[arg-type]
            value["through_seq"],  # type: ignore[arg-type]
        )
    if control_type == "media.detach":
        _require_exact_keys(
            value,
            {
                "type",
                "contract_version",
                "lease_id",
                "generation",
                "reason_id",
                "through_seq",
                "business_cancel_count_delta",
            },
            "detach",
        )
        _check_control_uint("generation", value["generation"])  # type: ignore[arg-type]
        through_seq = value["through_seq"]
        if through_seq is not None:
            _check_control_uint("through_seq", through_seq)  # type: ignore[arg-type]
        _require_zero_business_cancel(
            value["business_cancel_count_delta"],
            reason_id="MEDIA_MALFORMED_CONTROL",
        )
        try:
            reason_id = MediaDetachReason(value["reason_id"])
        except (TypeError, ValueError) as error:
            raise MediaTransportViolation(
                "MEDIA_MALFORMED_CONTROL", "detach reason is not closed"
            ) from error
        return MediaDetach(
            _check_control_id(
                "lease_id", value["lease_id"], max_chars=_MAX_LEASE_ID_BYTES
            ),
            value["generation"],  # type: ignore[arg-type]
            reason_id,
            through_seq,  # type: ignore[arg-type]
        )
    if control_type == "media.speech_start":
        _require_exact_keys(
            value,
            {
                "type",
                "contract_version",
                "capability_version",
                "lease_id",
                "generation",
                "detector",
                "provider_start_ms",
                "timing_basis",
                "timing_provenance",
                "create_response",
                "interrupt_response",
                "business_cancel_count_delta",
            },
            "speech_start",
        )
        return MediaSpeechStart(
            lease_id=_check_control_id(
                "lease_id", value["lease_id"], max_chars=_MAX_LEASE_ID_BYTES
            ),
            generation=value["generation"],  # type: ignore[arg-type]
            provider_start_ms=value["provider_start_ms"],  # type: ignore[arg-type]
            capability_version=value["capability_version"],  # type: ignore[arg-type]
            detector=value["detector"],  # type: ignore[arg-type]
            timing_basis=value["timing_basis"],  # type: ignore[arg-type]
            timing_provenance=value["timing_provenance"],  # type: ignore[arg-type]
            create_response=value["create_response"],  # type: ignore[arg-type]
            interrupt_response=value["interrupt_response"],  # type: ignore[arg-type]
            business_cancel_count_delta=value["business_cancel_count_delta"],  # type: ignore[arg-type]
        )
    if control_type == "media.end_of_turn":
        _require_exact_keys(
            value,
            {
                "type",
                "contract_version",
                "capability_version",
                "lease_id",
                "generation",
                "detector",
                "speech_started_observed",
                "provider_start_ms",
                "provider_end_ms",
                "timing_basis",
                "timing_provenance",
                "create_response",
                "interrupt_response",
                "business_cancel_count_delta",
            },
            "end_of_turn",
        )
        return MediaEndOfTurn(
            lease_id=_check_control_id(
                "lease_id", value["lease_id"], max_chars=_MAX_LEASE_ID_BYTES
            ),
            generation=value["generation"],  # type: ignore[arg-type]
            provider_start_ms=value["provider_start_ms"],  # type: ignore[arg-type]
            provider_end_ms=value["provider_end_ms"],  # type: ignore[arg-type]
            capability_version=value["capability_version"],  # type: ignore[arg-type]
            detector=value["detector"],  # type: ignore[arg-type]
            speech_started_observed=value["speech_started_observed"],  # type: ignore[arg-type]
            timing_basis=value["timing_basis"],  # type: ignore[arg-type]
            timing_provenance=value["timing_provenance"],  # type: ignore[arg-type]
            create_response=value["create_response"],  # type: ignore[arg-type]
            interrupt_response=value["interrupt_response"],  # type: ignore[arg-type]
            business_cancel_count_delta=value["business_cancel_count_delta"],  # type: ignore[arg-type]
        )
    if control_type == "media.playback_stop_receipt":
        _require_exact_keys(
            value,
            {
                "type",
                "contract_version",
                "lease_id",
                "response_id",
                "response_generation",
                "unit_id",
                "outcome",
                "confirmed_through_seq",
                "business_cancel_count_delta",
            },
            "playback_stop_receipt",
        )
        _check_control_uint("response_generation", value["response_generation"])  # type: ignore[arg-type]
        confirmed = value["confirmed_through_seq"]
        if confirmed is not None:
            _check_control_uint("confirmed_through_seq", confirmed)  # type: ignore[arg-type]
        _require_zero_business_cancel(
            value["business_cancel_count_delta"],
            reason_id="MEDIA_MALFORMED_CONTROL",
        )
        try:
            outcome = MediaPlaybackStopOutcome(value["outcome"])
        except (TypeError, ValueError) as error:
            raise MediaTransportViolation(
                "MEDIA_MALFORMED_CONTROL", "playback stop outcome is not closed"
            ) from error
        return MediaPlaybackStopReceipt(
            lease_id=_check_control_id(
                "lease_id", value["lease_id"], max_chars=_MAX_LEASE_ID_BYTES
            ),
            response_id=_check_control_id("response_id", value["response_id"]),
            response_generation=value["response_generation"],  # type: ignore[arg-type]
            unit_id=_check_control_id("unit_id", value["unit_id"]),
            outcome=outcome,
            confirmed_through_seq=confirmed,  # type: ignore[arg-type]
        )
    raise MediaTransportViolation("MEDIA_MALFORMED_CONTROL", "unknown control type")


def encode_audio_frame(binding: MediaAuthorityBinding, frame: MediaAudioFrame) -> bytes:
    """Encode one closed LVM1 audio frame with no client identity claims."""

    _require_safe_uint("frame.seq", frame.seq, reason_id="MEDIA_INVALID_FRAME")
    _require_safe_uint(
        "frame.sample_cursor", frame.sample_cursor, reason_id="MEDIA_INVALID_FRAME"
    )
    if (
        not isinstance(frame.samples, tuple)
        or len(frame.samples) != binding.frame_format.samples_per_channel
    ):
        raise MediaTransportViolation(
            "MEDIA_INVALID_FRAME", "frame does not contain exact 20 ms audio"
        )
    for sample in frame.samples:
        if isinstance(sample, bool) or not isinstance(sample, (int, float)):
            raise MediaTransportViolation(
                "MEDIA_INVALID_FRAME", "frame contains a non-numeric sample"
            )
        if not math.isfinite(sample):
            raise MediaTransportViolation(
                "MEDIA_NONFINITE_AUDIO", "frame contains non-finite samples"
            )
        if abs(sample) > _MAX_PCM_F32_ABS:
            raise MediaTransportViolation(
                "MEDIA_INVALID_FRAME", "frame sample is outside pcm_f32 range"
            )
    lease = binding.lease_id.encode("utf-8")
    if len(lease) > _MAX_LEASE_ID_BYTES:
        raise MediaTransportViolation("MEDIA_INVALID_BINDING", "lease id is too large")
    payload = struct.pack(f"<{len(frame.samples)}f", *frame.samples)
    return (
        _WIRE_HEADER.pack(
            _WIRE_MAGIC,
            _WIRE_VERSION,
            _WIRE_AUDIO_KIND,
            len(lease),
            binding.generation.value,
            frame.seq,
            frame.sample_cursor,
            len(payload),
        )
        + lease
        + payload
    )


def decode_audio_frame(
    binding: MediaAuthorityBinding, raw: bytes | bytearray | memoryview
) -> MediaAudioFrame:
    """Decode and fully validate a closed LVM1 audio frame."""

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_FRAME", "audio frame is not binary"
        )
    view = memoryview(raw)
    if len(view) > _MAX_BINARY_FRAME_BYTES:
        raise MediaTransportViolation(
            "MEDIA_OVERSIZED_FRAME", "audio frame exceeds its global bound"
        )
    if len(view) < _WIRE_HEADER.size:
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_FRAME", "audio frame is truncated"
        )
    magic, version, kind, lease_length, generation, seq, cursor, payload_length = (
        _WIRE_HEADER.unpack_from(view)
    )
    if magic != _WIRE_MAGIC or version != _WIRE_VERSION or kind != _WIRE_AUDIO_KIND:
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_FRAME", "audio frame header is not accepted"
        )
    if lease_length == 0 or lease_length > _MAX_LEASE_ID_BYTES:
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_FRAME", "lease length is invalid"
        )
    expected_payload_length = binding.frame_format.samples_per_channel * 4
    if payload_length != expected_payload_length:
        raise MediaTransportViolation(
            "MEDIA_INVALID_FRAME", "payload does not contain exact 20 ms audio"
        )
    if len(view) != _WIRE_HEADER.size + lease_length + payload_length:
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_FRAME", "audio frame length is inconsistent"
        )
    try:
        lease_id = bytes(
            view[_WIRE_HEADER.size : _WIRE_HEADER.size + lease_length]
        ).decode("utf-8")
    except UnicodeDecodeError as error:
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_FRAME", "lease id is not UTF-8"
        ) from error
    if lease_id != binding.lease_id:
        raise MediaTransportViolation(
            "MEDIA_BINDING_MISMATCH", "lease binding does not match"
        )
    if generation != binding.generation.value:
        raise MediaTransportViolation(
            "MEDIA_STALE_GENERATION", "frame generation does not match"
        )
    if (
        generation > _MAX_SAFE_INTEGER
        or seq > _MAX_SAFE_INTEGER
        or cursor > _MAX_SAFE_INTEGER
    ):
        raise MediaTransportViolation(
            "MEDIA_MALFORMED_FRAME", "frame integer exceeds the cross-language bound"
        )
    payload_offset = _WIRE_HEADER.size + lease_length
    samples = struct.unpack_from(
        f"<{binding.frame_format.samples_per_channel}f", view, payload_offset
    )
    if any(not math.isfinite(sample) for sample in samples):
        raise MediaTransportViolation(
            "MEDIA_NONFINITE_AUDIO", "frame contains non-finite samples"
        )
    return MediaAudioFrame(seq=seq, sample_cursor=cursor, samples=samples)


@dataclass(slots=True)
class _QueuedFrame:
    frame: MediaAudioFrame
    binary: bytes
    sent: bool = False


class BoundedMediaSender:
    """Explicitly drained bounded sender; it never owns or opens a socket."""

    def __init__(
        self,
        binding: MediaAuthorityBinding,
        *,
        max_pending_frames: int,
        max_pending_bytes: int,
    ) -> None:
        if (
            isinstance(max_pending_frames, bool)
            or not isinstance(max_pending_frames, int)
            or max_pending_frames <= 0
            or isinstance(max_pending_bytes, bool)
            or not isinstance(max_pending_bytes, int)
            or max_pending_bytes <= 0
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_LIMIT", "queue bounds must be positive"
            )
        self.binding = binding
        self._max_pending_frames = max_pending_frames
        self._max_pending_bytes = max_pending_bytes
        self._queue: Deque[_QueuedFrame] = deque()
        self._pending_bytes = 0
        self._next_seq = 0
        self._next_cursor = 0
        self._last_ack = -1
        self._closed = False
        self._detach: MediaDetach | None = None

    @property
    def pending_frames(self) -> int:
        return len(self._queue)

    @property
    def pending_bytes(self) -> int:
        return self._pending_bytes

    @property
    def closed(self) -> bool:
        return self._closed

    def _terminal(self, reason_id: object) -> MediaDetach:
        closed_reason = _coerce_detach_reason(reason_id)
        if self._detach is None:
            self._detach = MediaDetach(
                lease_id=self.binding.lease_id,
                generation=self.binding.generation.value,
                reason_id=closed_reason,
                through_seq=None if self._last_ack < 0 else self._last_ack,
            )
        self._closed = True
        return self._detach

    def enqueue(self, frame: MediaAudioFrame) -> MediaEnqueueResult:
        if self._closed:
            return MediaEnqueueResult(False, "MEDIA_LEASE_CLOSED")
        if frame.seq != self._next_seq:
            self._terminal("MEDIA_SEQUENCE_VIOLATION")
            return MediaEnqueueResult(False, "MEDIA_SEQUENCE_VIOLATION")
        if frame.sample_cursor != self._next_cursor:
            self._terminal("MEDIA_CURSOR_MISMATCH")
            return MediaEnqueueResult(False, "MEDIA_CURSOR_MISMATCH")
        try:
            binary = encode_audio_frame(self.binding, frame)
        except MediaTransportViolation as error:
            self._terminal(error.reason_id)
            return MediaEnqueueResult(False, error.reason_id)
        if (
            len(self._queue) >= self._max_pending_frames
            or self._pending_bytes + len(binary) > self._max_pending_bytes
        ):
            return MediaEnqueueResult(False, "MEDIA_BACKPRESSURE_LIMIT")
        self._queue.append(_QueuedFrame(frame=frame, binary=binary))
        self._pending_bytes += len(binary)
        self._next_seq += 1
        self._next_cursor += self.binding.frame_format.samples_per_channel
        return MediaEnqueueResult(True, "MEDIA_ENQUEUED")

    def drain(
        self, try_send_binary: Callable[[bytes], BinarySendDisposition]
    ) -> MediaDrainResult:
        if self._closed:
            return MediaDrainResult(
                0, len(self._queue), self._pending_bytes, "MEDIA_LEASE_CLOSED"
            )
        sent_frames = 0
        for item in self._queue:
            if item.sent:
                continue
            try:
                disposition = try_send_binary(item.binary)
            except Exception:
                self._terminal("MEDIA_TRANSPORT_SEND_FAILED")
                break
            if disposition is BinarySendDisposition.BACKPRESSURED:
                break
            if disposition is BinarySendDisposition.CLOSED:
                self._terminal("MEDIA_TRANSPORT_CLOSED")
                break
            if disposition is not BinarySendDisposition.SENT:
                self._terminal("MEDIA_TRANSPORT_PROTOCOL_ERROR")
                break
            item.sent = True
            sent_frames += 1
        reason = (
            self._detach.reason_id
            if self._detach is not None
            else (
                "MEDIA_DRAINED"
                if sent_frames
                else "MEDIA_AWAITING_ACK"
                if self._queue and all(item.sent for item in self._queue)
                else "MEDIA_BACKPRESSURED"
            )
        )
        return MediaDrainResult(
            sent_frames, len(self._queue), self._pending_bytes, reason
        )

    def acknowledge(self, control: MediaAck) -> MediaDetach | None:
        if self._closed:
            return self._detach or self._terminal("MEDIA_LEASE_CLOSED")
        if control.lease_id != self.binding.lease_id:
            return self._terminal("MEDIA_BINDING_MISMATCH")
        if control.generation != self.binding.generation.value:
            return self._terminal("MEDIA_STALE_GENERATION")
        if control.through_seq < self._last_ack:
            return self._terminal("MEDIA_ACK_OUT_OF_ORDER")
        if control.through_seq == self._last_ack:
            return None
        candidates = [
            item for item in self._queue if item.frame.seq <= control.through_seq
        ]
        if any(not item.sent for item in candidates):
            return self._terminal("MEDIA_ACK_UNSENT")
        if (
            not candidates
            or candidates[0].frame.seq != self._last_ack + 1
            or candidates[-1].frame.seq != control.through_seq
        ):
            return self._terminal("MEDIA_ACK_GAP")
        for _ in candidates:
            item = self._queue.popleft()
            self._pending_bytes -= len(item.binary)
        self._last_ack = control.through_seq
        return None

    def close(
        self,
        reason_id: MediaDetachReason = MediaDetachReason.LOCAL_CLOSE,
    ) -> MediaCloseResult:
        was_active = not self._closed
        detach = self._terminal(reason_id)
        dropped_frames = len(self._queue)
        dropped_bytes = self._pending_bytes
        self._queue.clear()
        self._pending_bytes = 0
        return MediaCloseResult(
            was_active, detach.reason_id, dropped_frames, dropped_bytes, detach
        )


class StrictMediaReceiver:
    """Strict receiver with terminal generation, sequence, and cursor fencing."""

    def __init__(
        self,
        binding: MediaAuthorityBinding,
        *,
        on_audio_frame: Callable[[MediaAudioFrame], None],
    ) -> None:
        if not callable(on_audio_frame):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CONSUMER", "audio consumer must be callable"
            )
        self.binding = binding
        self._on_audio_frame = on_audio_frame
        self._attached = False
        self._closed = False
        self._next_seq = 0
        self._next_cursor = 0
        self._last_ack = -1
        self._detach: MediaDetach | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def attached(self) -> bool:
        return self._attached

    def _terminal(self, reason_id: object) -> MediaDetach:
        closed_reason = _coerce_detach_reason(
            reason_id, fallback=MediaDetachReason.MALFORMED_FRAME
        )
        if self._detach is None:
            self._detach = MediaDetach(
                lease_id=self.binding.lease_id,
                generation=self.binding.generation.value,
                reason_id=closed_reason,
                through_seq=None if self._last_ack < 0 else self._last_ack,
            )
        self._closed = True
        self._attached = False
        return self._detach

    def attach(self, control: MediaAttach) -> MediaDetach | None:
        if self._closed:
            return self._detach or self._terminal("MEDIA_LEASE_CLOSED")
        if self._attached:
            return self._terminal("MEDIA_DUPLICATE_ATTACH")
        if control.binding != self.binding:
            return self._terminal("MEDIA_BINDING_MISMATCH")
        self._attached = True
        return None

    def accept_binary(
        self, raw: bytes | bytearray | memoryview
    ) -> MediaAck | MediaDetach:
        if self._closed:
            return self._detach or self._terminal("MEDIA_LEASE_CLOSED")
        if not self._attached:
            return self._terminal("MEDIA_NOT_ATTACHED")
        try:
            frame = decode_audio_frame(self.binding, raw)
        except MediaTransportViolation as error:
            return self._terminal(error.reason_id)
        if frame.seq < self._next_seq:
            return self._terminal("MEDIA_DUPLICATE_OR_OUT_OF_ORDER")
        if frame.seq > self._next_seq:
            return self._terminal("MEDIA_SEQUENCE_GAP")
        if frame.sample_cursor != self._next_cursor:
            return self._terminal("MEDIA_CURSOR_MISMATCH")
        try:
            self._on_audio_frame(frame)
        except Exception:
            return self._terminal("MEDIA_CONSUMER_FAILED")
        self._last_ack = frame.seq
        self._next_seq += 1
        self._next_cursor += self.binding.frame_format.samples_per_channel
        return MediaAck(self.binding.lease_id, self.binding.generation.value, frame.seq)

    def accept_detach(self, control: MediaDetach) -> MediaCloseResult:
        was_active = not self._closed
        if control.lease_id != self.binding.lease_id:
            detach = self._terminal("MEDIA_BINDING_MISMATCH")
        elif control.generation != self.binding.generation.value:
            detach = self._terminal("MEDIA_STALE_GENERATION")
        elif (
            type(control.business_cancel_count_delta) is not int
            or control.business_cancel_count_delta != 0
        ):
            detach = self._terminal("MEDIA_CANCEL_SCOPE_VIOLATION")
        else:
            detach = self._terminal(control.reason_id)
        return MediaCloseResult(was_active, detach.reason_id, 0, 0, detach)

    def close(
        self,
        reason_id: MediaDetachReason = MediaDetachReason.LOCAL_CLOSE,
    ) -> MediaCloseResult:
        was_active = not self._closed
        detach = self._terminal(reason_id)
        return MediaCloseResult(was_active, detach.reason_id, 0, 0, detach)


def create_playback_stop_receipt(
    binding: MediaAuthorityBinding,
    *,
    outcome: MediaPlaybackStopOutcome,
    confirmed_through_seq: int | None = None,
) -> MediaPlaybackStopReceipt:
    """Create a playout-only stop receipt which cannot escalate cancellation."""

    if binding.direction is not MediaDirection.DOWNLINK or binding.playout is None:
        raise MediaTransportViolation(
            "MEDIA_STOP_BINDING_MISMATCH", "playback stop requires downlink authority"
        )
    if not isinstance(outcome, MediaPlaybackStopOutcome):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONTROL", "playback stop outcome is not closed"
        )
    if confirmed_through_seq is not None:
        _require_safe_uint("confirmed_through_seq", confirmed_through_seq)
    receipt = MediaPlaybackStopReceipt(
        lease_id=binding.lease_id,
        response_id=binding.playout.response_id,
        response_generation=binding.playout.response_generation,
        unit_id=binding.playout.unit_id,
        outcome=outcome,
        confirmed_through_seq=confirmed_through_seq,
    )
    return validate_playback_stop_receipt(binding, receipt)


def validate_playback_stop_receipt(
    binding: MediaAuthorityBinding,
    control: MediaPlaybackStopReceipt,
) -> MediaPlaybackStopReceipt:
    """Validate an exact playout receipt without widening cancellation scope."""

    if binding.direction is not MediaDirection.DOWNLINK or binding.playout is None:
        raise MediaTransportViolation(
            "MEDIA_STOP_BINDING_MISMATCH", "playback stop requires downlink authority"
        )
    if (
        control.lease_id != binding.lease_id
        or control.response_id != binding.playout.response_id
        or control.response_generation != binding.playout.response_generation
        or control.unit_id != binding.playout.unit_id
    ):
        raise MediaTransportViolation(
            "MEDIA_STOP_BINDING_MISMATCH", "playback stop tuple does not match"
        )
    if not isinstance(control.outcome, MediaPlaybackStopOutcome):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONTROL", "playback stop outcome is not closed"
        )
    if control.confirmed_through_seq is not None:
        _require_safe_uint("confirmed_through_seq", control.confirmed_through_seq)
    _require_zero_business_cancel(
        control.business_cancel_count_delta,
        reason_id="MEDIA_CANCEL_SCOPE_VIOLATION",
    )
    return control
