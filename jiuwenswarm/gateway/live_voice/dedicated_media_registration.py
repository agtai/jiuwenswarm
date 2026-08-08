# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Central, default-off registration for the formal dedicated media route.

The package media leaf deliberately cannot register itself.  This module owns
the product ticket, same-origin handshake, ephemeral Speech authority, and the
memory-only audit facts needed by the W2 Web composition.
"""

from __future__ import annotations

import hashlib
import base64
import io
import json
import math
import os
import secrets
import struct
import threading
import time
import wave
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

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
    MediaAudioFrame,
    MediaAuthorityBinding,
    MediaDirection,
    MediaFrameFormat,
    MediaGenerationBinding,
    MediaGenerationKind,
    MediaPlayoutBinding,
    MediaTransportViolation,
    MediaAttach,
    serialize_media_control,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaRouteRequest,
    DedicatedMediaSocketLeafResult,
    run_dedicated_media_socket_leaf,
    run_dedicated_media_downlink_socket_leaf,
)
from jiuwenswarm.server.live_voice.batch_speech import (
    RECOGNIZE_OPERATION,
    SYNTHESIZE_OPERATION,
    SpeechAuthorizationBinding,
    SpeechRpcContext,
)


MEDIA_ACTIVATE_METHOD = "live_voice.media.activate"
MEDIA_CLOSE_METHOD = "live_voice.media.close"
MEDIA_PLAYOUT_RECEIPT_METHOD = "live_voice.media.playout_receipt"
MEDIA_ROUTE_PREFIX = "/ws/live-voice/media/"
MEDIA_SUBPROTOCOL = "live-voice.media.v1"
MEDIA_FEATURE_ENV = "JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED"

_MAX_RECORDS = 128
_MAX_CAPTURE_WAV_BYTES = 4 * 1024 * 1024
_MAX_DOWNLINK_WAV_BYTES = 8 * 1024 * 1024
_MAX_DOWNLINK_FRAMES = 1_500
_PRODUCT_PLAYOUT_QUEUE_CAPACITY = 256
_DEFAULT_TICKET_TTL_SECONDS = 30.0
_DEFAULT_AUTHORITY_TTL_SECONDS = 15 * 60.0
_MAX_ID_CHARS = 256
_LOCALES = frozenset({"en", "en-US", "zh", "zh-CN"})
_PRODUCT_CONTRACT_VERSION = "live-voice.product-composition.gate0.v1"
_FORMAL_P2_EVIDENCE = frozenset(
    {
        "TRUSTED_AUTHORITY_RESOLVED",
        "FORMAL_ACTIVATION_LEASE_OPEN",
        "RUNTIME_PATH_OBSERVED",
        "P2_NOTIFICATION_BACKPRESSURE_CLOSED",
    }
)


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


def _downlink_frames(audio_wav: bytes, sample_rate_hz: int) -> tuple[MediaAudioFrame, ...]:
    if len(audio_wav) > _MAX_DOWNLINK_WAV_BYTES:
        raise MediaTransportViolation(
            "MEDIA_DOWNLINK_LIMIT_EXCEEDED", "synthesis audio exceeds the downlink limit"
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


@dataclass(slots=True)
class _MediaAuthority:
    ticket: str
    subject_id: str
    expected_origin: str
    product_activation_id: str
    product_activation_generation: int
    user_id: str
    binding: MediaAuthorityBinding
    locale: str
    issued_at: float
    ticket_expires_at: float
    authority_expires_at: float
    ticket_consumed: bool = False
    route_completed: bool = False
    accepted_frames: int = 0
    pcm: bytearray = field(default_factory=bytearray, repr=False)
    recognition_content_sha256: str | None = None
    synthesis_content_sha256: dict[tuple[ResponseRef, str], str] = field(
        default_factory=dict, repr=False
    )
    playout_receipts: dict[tuple[ResponseRef, str], dict[str, object]] = field(
        default_factory=dict, repr=False
    )
    downlink_frames: tuple[MediaAudioFrame, ...] = field(default=(), repr=False)
    downlink_response: ResponseRef | None = None
    downlink_unit_id: str | None = None
    downlink_overlap_ticket: str | None = None
    downlink_overlap_observed: bool = False
    downlink_results: dict[tuple[ResponseRef, str], dict[str, object]] = field(
        default_factory=dict, repr=False
    )


@dataclass(frozen=True, slots=True)
class _ProductActivationAuthority:
    session_id: str
    user_id: str
    connection_id: str
    correlation_id: str
    interaction_id: str
    activation_id: str
    activation_generation: int
    expires_at: float


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
    ) -> None:
        self.enabled = enabled is True
        self._monotonic = monotonic
        self._ticket_ttl = ticket_ttl_seconds
        self._authority_ttl = authority_ttl_seconds
        self._capacity = max(1, min(capacity, _MAX_RECORDS))
        self._records: OrderedDict[str, _MediaAuthority] = OrderedDict()
        self._subjects: dict[tuple[str, str], str] = {}
        self._product_activations: OrderedDict[
            tuple[str, str, str], _ProductActivationAuthority
        ] = OrderedDict()
        self._revoked: OrderedDict[str, tuple[str, str, str, str, int, str, str]] = (
            OrderedDict()
        )
        self._lock = threading.RLock()
        self._provider_available = False
        self._evidence_observer: Any | None = None

    @classmethod
    def from_environment(cls) -> "DedicatedMediaProductRegistry":
        return cls(enabled=_enabled(os.getenv(MEDIA_FEATURE_ENV)))

    def set_provider_available(self, value: bool) -> None:
        self._provider_available = value is True

    def set_evidence_observer(self, observer: Any | None) -> None:
        self._evidence_observer = observer

    @property
    def evidence_observer(self) -> Any | None:
        return self._evidence_observer

    def evidence_binding_for(
        self, params: object, session_id: str
    ) -> dict[str, object] | None:
        """Project only exact, retained P1 trace identity; never content."""

        if not isinstance(params, Mapping):
            return None
        scope = params.get("scope")
        if not isinstance(scope, Mapping):
            return None
        subject_id = scope.get("subject_id")
        correlation_id = params.get("correlation_id")
        if not isinstance(subject_id, str) or not isinstance(correlation_id, str):
            return None
        with self._lock:
            self._prune(self._monotonic())
            ticket = self._subjects.get((session_id, subject_id))
            record = self._records.get(ticket or "")
            if (
                record is None
                or record.binding.correlation_id != correlation_id
                or not record.ticket_consumed
            ):
                return None
            projected = {
                "correlation_id": correlation_id,
                "interaction_id": record.binding.interaction_id,
            }
            response = params.get("response")
            if isinstance(response, Mapping) and isinstance(
                response.get("response_id"), str
            ):
                projected["response_id"] = response["response_id"]
                generation = response.get("response_generation")
                if type(generation) is int:
                    projected["response_generation"] = generation
            return projected

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
        if not self._provider_available:
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
        if set(params) != expected_keys:
            raise MediaTransportViolation(
                "MEDIA_INVALID_ACTIVATION", "media activation fields are not closed"
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
        authenticated_user_id = _required_id(user_id, "user_id")

        now = self._monotonic()
        with self._lock:
            self._prune(now)
            trusted_activation = self._product_activations.get(
                (session_id, authenticated_user_id, interaction_id)
            )
            if (
                trusted_activation is None
                or trusted_activation.connection_id
                != _required_id(connection_id, "connection_id")
                or trusted_activation.correlation_id != correlation_id
                or trusted_activation.activation_id != activation_id
                or trusted_activation.activation_generation != activation_generation
                or now > trusted_activation.expires_at
            ):
                raise MediaTransportViolation(
                    "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED",
                    "media activation requires the exact accepted product P2 route",
                )
        ticket = secrets.token_urlsafe(32)
        subject_id = f"live-voice-media:{secrets.token_hex(16)}"
        binding = MediaAuthorityBinding(
            lease_id=f"media-lease-{secrets.token_hex(16)}",
            authority_evidence_id=f"media-authority-{secrets.token_hex(16)}",
            connection_id=_required_id(connection_id, "connection_id"),
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
            ticket=ticket,
            subject_id=subject_id,
            expected_origin=request_origin,
            product_activation_id=activation_id,
            product_activation_generation=activation_generation,
            user_id=authenticated_user_id,
            binding=binding,
            locale=locale,
            issued_at=now,
            ticket_expires_at=now + self._ticket_ttl,
            authority_expires_at=now + self._authority_ttl,
        )
        with self._lock:
            self._prune(now)
            if len(self._records) >= self._capacity:
                raise MediaTransportViolation(
                    "MEDIA_ROUTE_CAPACITY_EXCEEDED", "media route capacity is full"
                )
            self._records[ticket] = record
            self._subjects[(session_id, subject_id)] = ticket
        return {
            "status": "active",
            "reason_id": "MEDIA_ROUTE_TICKET_ISSUED",
            "subject_id": subject_id,
            "endpoint_path": f"{MEDIA_ROUTE_PREFIX}{ticket}",
            "subprotocol": MEDIA_SUBPROTOCOL,
            "ticket_ttl_ms": int(self._ticket_ttl * 1000),
            "binding": _binding_payload(binding),
            "privacy": {
                "raw_audio_persisted": False,
                "raw_audio_logged": False,
                "memory_only": True,
            },
        }

    def consume_ticket(
        self, ticket: str, *, request_origin: str | None
    ) -> _MediaAuthority | None:
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            record = self._records.get(ticket)
            if (
                record is None
                or record.ticket_consumed
                or now > record.ticket_expires_at
                or request_origin != record.expected_origin
                or not is_allowed_browser_origin(request_origin)
            ):
                return None
            record.ticket_consumed = True
            return record

    def accept_frame(self, record: _MediaAuthority, frame: MediaAudioFrame) -> None:
        encoded = _pcm16(frame.samples)
        with self._lock:
            if record.route_completed:
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

    def complete_route(
        self, record: _MediaAuthority, result: DedicatedMediaSocketLeafResult
    ) -> None:
        with self._lock:
            record.route_completed = True
            if not result.activated or result.accepted_frames <= 0 or not record.pcm:
                record.pcm.clear()
                return
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

    def abort_route(self, record: _MediaAuthority) -> None:
        """Close one exceptional/cancelled media owner with zero retained audio."""

        with self._lock:
            record.route_completed = True
            record.recognition_content_sha256 = None
            record.downlink_frames = ()
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
        authenticated_user_id = _required_id(user_id, "user_id")
        binding = (
            session_id,
            correlation_id,
            interaction_id,
            activation_id,
            activation_generation,
            owner_connection_id,
            authenticated_user_id,
        )
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            ticket = self._subjects.get((session_id, subject_id))
            record = self._records.get(ticket or "")
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
                    record.user_id,
                )
                if actual != binding:
                    raise MediaTransportViolation(
                        "MEDIA_CLOSE_BINDING_MISMATCH",
                        "media close does not own the exact route",
                    )
                owned_tickets = [
                    ticket
                    for ticket, candidate in self._records.items()
                    if candidate.subject_id == subject_id
                    and candidate.binding.session_id == session_id
                    and candidate.binding.correlation_id == correlation_id
                    and candidate.binding.interaction_id == interaction_id
                    and candidate.product_activation_id == activation_id
                    and candidate.product_activation_generation
                    == activation_generation
                    and candidate.binding.connection_id == owner_connection_id
                    and candidate.user_id == authenticated_user_id
                ]
                owned_records = [self._records.pop(ticket) for ticket in owned_tickets]
                self._subjects.pop((session_id, subject_id), None)
                for owned in owned_records:
                    owned.route_completed = True
                    owned.recognition_content_sha256 = None
                    owned.synthesis_content_sha256.clear()
                    owned.playout_receipts.clear()
                    owned.downlink_results.clear()
                    owned.downlink_frames = ()
                    owned.pcm.clear()
                self._revoked[subject_id] = binding
                self._revoked.move_to_end(subject_id)
                while len(self._revoked) > _MAX_RECORDS:
                    self._revoked.popitem(last=False)
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
                authenticated_user_id = _required_id(user_id, "user_id")
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
            key = (session_id, authenticated_user_id, interaction_id)
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
                authority = _ProductActivationAuthority(
                    session_id=session_id,
                    user_id=authenticated_user_id,
                    connection_id=owner_connection_id,
                    correlation_id=correlation_id,
                    interaction_id=interaction_id,
                    activation_id=activation_id,
                    activation_generation=activation_generation,
                    expires_at=self._monotonic() + self._authority_ttl,
                )
                existing = self._product_activations.get(key)
                if existing is not None and (
                    existing.connection_id,
                    existing.correlation_id,
                    existing.activation_id,
                    existing.activation_generation,
                ) != (
                    authority.connection_id,
                    authority.correlation_id,
                    authority.activation_id,
                    authority.activation_generation,
                ):
                    self._revoke_media_for_product_activation(existing)
                self._product_activations[key] = authority
                self._product_activations.move_to_end(key)
                while len(self._product_activations) > self._capacity:
                    _key, evicted = self._product_activations.popitem(last=False)
                    self._revoke_media_for_product_activation(evicted)
            return
        if status != "notification":
            return
        try:
            authenticated_user_id = _required_id(user_id, "user_id")
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
        if (
            result.get("kind") != "agent.output"
            or event.get("event_type") != "chat.final"
            or unit.get("surface") != "text"
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
            self._prune(self._monotonic())
            for record in self._records.values():
                if (
                    record.binding.session_id != session_id
                    or session_id != routed_session
                    or record.user_id != authenticated_user_id
                    or record.binding.connection_id != owner_connection_id
                    or record.binding.correlation_id != correlation_id
                    or record.binding.interaction_id != ref.interaction_id
                    or result.get("activation_id") != record.product_activation_id
                    or result.get("activation_generation")
                    != record.product_activation_generation
                    or self._monotonic() > record.authority_expires_at
                    or not self._has_retained_product_activation(
                        record, self._monotonic()
                    )
                ):
                    continue
                record.synthesis_content_sha256[(ref, unit_id)] = hashlib.sha256(
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
            ticket = self._subjects.get((session_id, subject or ""))
            record = self._records.get(ticket or "")
            if (
                record is not None
                and record.ticket_consumed
                and record.route_completed
                and record.binding.connection_id == connection_id
                and record.user_id == user_id
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
            ticket = self._subjects.get((binding.scope.session_id, binding.subject_id))
            record = self._records.get(ticket or "")
            if (
                record is None
                or not record.ticket_consumed
                or not record.route_completed
                or now > record.authority_expires_at
                or binding.correlation_id != record.binding.correlation_id
                or not self._has_retained_product_activation(record, now)
            ):
                return None
            if binding.operation == RECOGNIZE_OPERATION:
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
                expected = record.synthesis_content_sha256.get(
                    (binding.response, binding.unit_id)
                )
                return binding if expected == binding.content_sha256 else None
            return None

    def prepare_synthesis_downlink(
        self,
        operation_name: str,
        params: object,
        context: SpeechRpcContext,
        result: dict[str, object],
        session_id: str,
    ) -> dict[str, object]:
        """Replace exact product synthesis bytes with a one-use binary ticket."""

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
        if not isinstance(payload, Mapping) or not isinstance(response_payload, Mapping):
            return result
        audio = payload.get("audio")
        if not isinstance(audio, Mapping):
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
            parent_ticket = self._subjects.get((session_id, context.subject_id))
            parent = self._records.get(parent_ticket or "")
            key = (response, unit_id)
            if (
                parent is None
                or parent.binding.direction is not MediaDirection.UPLINK
                or parent.binding.correlation_id != params.get("correlation_id")
                or parent.binding.interaction_id != response.interaction_id
                or key not in parent.synthesis_content_sha256
                or now > parent.authority_expires_at
                or not self._has_retained_product_activation(parent, now)
            ):
                return result
            if len(self._records) >= self._capacity:
                raise MediaTransportViolation(
                    "MEDIA_ROUTE_CAPACITY_EXCEEDED", "media route capacity is full"
                )
            ticket = secrets.token_urlsafe(32)
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
                ticket=ticket,
                subject_id=parent.subject_id,
                expected_origin=parent.expected_origin,
                product_activation_id=parent.product_activation_id,
                product_activation_generation=parent.product_activation_generation,
                user_id=parent.user_id,
                binding=binding,
                locale=parent.locale,
                issued_at=now,
                ticket_expires_at=now + self._ticket_ttl,
                authority_expires_at=parent.authority_expires_at,
                downlink_frames=frames,
                downlink_response=response,
                downlink_unit_id=unit_id,
            )
            self._records[ticket] = record
        transformed_audio = {
            "format": "pcm_f32_mono_20ms",
            "sample_rate_hz": sample_rate_hz,
            "channel_count": 1,
            "frame_count": len(frames),
            "delivery": "dedicated_media_downlink",
            "endpoint_path": f"{MEDIA_ROUTE_PREFIX}{ticket}",
            "subprotocol": MEDIA_SUBPROTOCOL,
            "ticket_ttl_ms": int(self._ticket_ttl * 1000),
            "binding": _binding_payload(binding),
            "max_pending_frames": 8,
            "max_pending_bytes": 131_072,
        }
        return {
            **result,
            "result": {**payload, "audio": transformed_audio},
        }

    def mark_downlink_started(self, record: _MediaAuthority) -> None:
        """Bind the downlink start to one exact consumed live uplink."""

        with self._lock:
            record.downlink_overlap_ticket = next(
                (
                    ticket
                    for ticket, other in self._records.items()
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
            frame_count = len(record.downlink_frames)
            record.route_completed = True
            record.downlink_frames = ()
            response = record.downlink_response
            unit_id = record.downlink_unit_id
            overlapping_uplink = self._records.get(
                record.downlink_overlap_ticket or ""
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
                and frame_count > 0
                and result.sent_frames == frame_count
                and result.acknowledged_through_seq == frame_count - 1
                and result.playback_stop_receipts == 0
                and result.configured_max_pending_frames == 8
                and result.configured_max_pending_bytes == 131_072
                and 0 < result.peak_pending_frames <= 8
                and 0 < result.peak_pending_bytes <= 131_072
                and record.downlink_overlap_observed
            )
            if response is None or unit_id is None:
                return False
            parent_ticket = self._subjects.get(
                (record.binding.session_id, record.subject_id)
            )
            parent = self._records.get(parent_ticket or "")
            if parent is None:
                return False
            parent.downlink_results[(response, unit_id)] = {
                "complete": complete,
                "sent_frames": result.sent_frames,
                "acknowledged_through_seq": result.acknowledged_through_seq,
                "max_pending_frames": result.configured_max_pending_frames,
                "max_pending_bytes": result.configured_max_pending_bytes,
                "peak_pending_frames": result.peak_pending_frames,
                "peak_pending_bytes": result.peak_pending_bytes,
                "overlap_observed": record.downlink_overlap_observed,
            }
            return complete

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

        expected_keys = {
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
        }
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
        rendered_chunks = _safe_uint(
            params.get("rendered_chunks"), "rendered_chunks"
        )
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
        authenticated_user_id = _required_id(user_id, "user_id")
        owner_connection_id = _required_id(connection_id, "connection_id")
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            ticket = self._subjects.get((session_id, subject_id))
            record = self._records.get(ticket or "")
            if (
                record is None
                or record.user_id != authenticated_user_id
                or record.binding.connection_id != owner_connection_id
                or record.expected_origin != request_origin
                or not is_allowed_browser_origin(request_origin)
                or record.binding.correlation_id != correlation_id
                or record.binding.interaction_id != interaction_id
                or not record.ticket_consumed
                or not record.route_completed
                or record.accepted_frames != capture_frames_acked
                or now > record.authority_expires_at
                or not self._has_retained_product_activation(record, now)
                or (response, unit_id) not in record.synthesis_content_sha256
            ):
                raise MediaTransportViolation(
                    "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED",
                    "media playout receipt is not bound to the authorized product flow",
                )
            key = (response, unit_id)
            downlink = record.downlink_results.get(key)
            duplex_media_observed = bool(
                downlink is not None
                and downlink.get("complete") is True
                and downlink.get("overlap_observed") is True
            )
            receipt_id = "media-playout-" + hashlib.sha256(
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
                "duplex_media_observed": duplex_media_observed,
            }
            previous = record.playout_receipts.get(key)
            if previous is not None and previous != payload:
                raise MediaTransportViolation(
                    "MEDIA_PLAYOUT_RECEIPT_CONFLICT",
                    "media playout receipt cannot change after acceptance",
                )
            record.playout_receipts[key] = payload
            return dict(payload)

    def _prune(self, now: float) -> None:
        expired = [
            ticket
            for ticket, record in self._records.items()
            if now > record.authority_expires_at
            or (not record.ticket_consumed and now > record.ticket_expires_at)
        ]
        for ticket in expired:
            record = self._records.pop(ticket)
            subject_key = (record.binding.session_id, record.subject_id)
            if self._subjects.get(subject_key) == ticket:
                self._subjects.pop(subject_key, None)
            record.pcm.clear()
            record.playout_receipts.clear()
            record.downlink_results.clear()
            record.downlink_frames = ()
            record.downlink_overlap_ticket = None
        expired_activations = [
            key
            for key, authority in self._product_activations.items()
            if now > authority.expires_at
        ]
        for key in expired_activations:
            authority = self._product_activations.pop(key, None)
            if authority is not None:
                self._revoke_media_for_product_activation(authority)

    def _has_retained_product_activation(
        self, record: _MediaAuthority, now: float
    ) -> bool:
        authority = self._product_activations.get(
            (
                record.binding.session_id,
                record.user_id,
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
        tickets = [
            ticket
            for ticket, record in self._records.items()
            if (
                record.binding.session_id == authority.session_id
                and record.user_id == authority.user_id
                and record.binding.connection_id == authority.connection_id
                and record.binding.interaction_id == authority.interaction_id
                and record.binding.correlation_id == authority.correlation_id
                and record.product_activation_id == authority.activation_id
                and record.product_activation_generation
                == authority.activation_generation
            )
        ]
        for ticket in tickets:
            record = self._records.pop(ticket)
            self._subjects.pop(
                (record.binding.session_id, record.subject_id), None
            )
            record.route_completed = True
            record.recognition_content_sha256 = None
            record.synthesis_content_sha256.clear()
            record.playout_receipts.clear()
            record.downlink_results.clear()
            record.downlink_frames = ()
            record.downlink_overlap_ticket = None
            record.pcm.clear()


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
            observer = registry.evidence_observer
            if observer is not None:
                try:
                    await observer.observe_route(
                        session_id=session_id,
                        correlation_id=str(payload["correlation_id"]),
                        request_id=str(payload["receipt_id"]),
                        operation="media.playout.receipt",
                        result_ok=True,
                        interaction_id=str(payload["interaction_id"]),
                        response_id=str(payload["response_id"]),
                        response_generation=int(payload["response_generation"]),
                    )
                    if payload.get("duplex_media_observed") is True:
                        await observer.observe_route(
                            session_id=session_id,
                            correlation_id=str(payload["correlation_id"]),
                            request_id=f"{payload['receipt_id']}:duplex",
                            operation="media.duplex.receipt",
                            result_ok=True,
                            interaction_id=str(payload["interaction_id"]),
                            response_id=str(payload["response_id"]),
                            response_generation=int(payload["response_generation"]),
                        )
                except Exception:
                    pass
            await channel.send_response(ws, req_id, ok=True, payload=payload)
        except MediaTransportViolation as exc:
            await channel.send_response(
                ws, req_id, ok=False, error=str(exc), code=exc.reason_id
            )

    channel.register_method(MEDIA_ACTIVATE_METHOD, activation_handler)
    channel.register_method(MEDIA_CLOSE_METHOD, close_handler)
    channel.register_method(MEDIA_PLAYOUT_RECEIPT_METHOD, playout_receipt_handler)


async def handle_registered_media_socket(
    registry: DedicatedMediaProductRegistry,
    ws: Any,
    request_path: str,
) -> bool:
    """Handle a central media path and return whether it matched the prefix."""

    if not request_path.startswith(MEDIA_ROUTE_PREFIX):
        return False
    ticket = request_path.removeprefix(MEDIA_ROUTE_PREFIX)
    if (
        not ticket
        or "/" in ticket
        or getattr(ws, "subprotocol", None) != MEDIA_SUBPROTOCOL
    ):
        await ws.close(code=1008, reason="invalid live-voice media route")
        return True
    record = registry.consume_ticket(ticket, request_origin=_request_origin(ws))
    if record is None:
        await ws.close(code=1008, reason="invalid or expired live-voice media ticket")
        return True
    request = DedicatedMediaRouteRequest(
        enabled=registry.enabled,
        expected_origin=record.expected_origin,
        request_origin=_request_origin(ws),
        binding=record.binding,
        provider_available=True,
        binary_transport_available=True,
    )
    try:
        downlink_complete = False
        if record.binding.direction is MediaDirection.DOWNLINK:
            registry.mark_downlink_started(record)

            def retain_downlink_completion(
                leaf_result: DedicatedMediaSocketLeafResult,
            ) -> None:
                nonlocal downlink_complete
                downlink_complete = registry.complete_downlink(record, leaf_result)

            result = await run_dedicated_media_downlink_socket_leaf(
                request,
                socket=ws,
                frames=record.downlink_frames,
                on_playback_stop=lambda _receipt: None,
                on_complete=retain_downlink_completion,
                max_pending_frames=8,
                max_pending_bytes=131_072,
            )
        else:
            result = await run_dedicated_media_socket_leaf(
                request,
                socket=ws,
                on_audio_frame=lambda frame: registry.accept_frame(record, frame),
            )
    except BaseException:
        registry.abort_route(record)
        observer = registry.evidence_observer
        if observer is not None:
            try:
                await observer.observe_route(
                    session_id=record.binding.session_id,
                    correlation_id=record.binding.correlation_id,
                    request_id=record.binding.lease_id,
                    operation=(
                        "media.downlink"
                        if record.binding.direction is MediaDirection.DOWNLINK
                        else "media.capture"
                    ),
                    result_ok=False,
                    interaction_id=record.binding.interaction_id,
                    error_code="UNAVAILABLE",
                )
            except Exception:
                pass
        raise
    if record.binding.direction is not MediaDirection.DOWNLINK:
        registry.complete_route(record, result)
    observer = registry.evidence_observer
    if observer is not None:
        try:
            await observer.observe_route(
                session_id=record.binding.session_id,
                correlation_id=record.binding.correlation_id,
                request_id=record.binding.lease_id,
                operation=(
                    "media.downlink"
                    if record.binding.direction is MediaDirection.DOWNLINK
                    else "media.capture"
                ),
                result_ok=(
                    downlink_complete
                    if record.binding.direction is MediaDirection.DOWNLINK
                    else result.activated and result.accepted_frames > 0
                ),
                interaction_id=record.binding.interaction_id,
                response_id=(
                    record.downlink_response.response_id
                    if record.downlink_response is not None
                    else None
                ),
                response_generation=(
                    record.downlink_response.response_generation
                    if record.downlink_response is not None
                    else None
                ),
                error_code=(
                    None
                    if (
                        downlink_complete
                        if record.binding.direction is MediaDirection.DOWNLINK
                        else result.activated and result.accepted_frames > 0
                    )
                    else "UNAVAILABLE"
                ),
            )
        except Exception:
            pass
    return True


__all__ = [
    "DedicatedMediaProductRegistry",
    "MEDIA_ACTIVATE_METHOD",
    "MEDIA_CLOSE_METHOD",
    "MEDIA_PLAYOUT_RECEIPT_METHOD",
    "MEDIA_FEATURE_ENV",
    "MEDIA_ROUTE_PREFIX",
    "MEDIA_SUBPROTOCOL",
    "handle_registered_media_socket",
    "register_dedicated_media_rpc_handlers",
]
