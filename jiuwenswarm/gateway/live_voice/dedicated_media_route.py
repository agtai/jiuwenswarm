# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Package-local proof seam for a dedicated same-origin media route.

This module is deliberately not a registered WebSocket handler.  It accepts an
already server-authored :class:`MediaAuthorityBinding`, enforces a same-origin
request context, and exposes typed LVM1 sessions plus runners for an injected,
already-accepted socket.  It has no JSON logger, persistence callback, socket
factory, or retry surface; short-lived tasks exist only for socket/EOT arbitration.

An active object proves only the package contract.  Product route truth remains
``unavailable`` until the Integration Owner registers the real handler and an
actual route-to-disk regression proves zero raw-audio persistence.
"""

from __future__ import annotations

import asyncio
import ipaddress
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
)
from urllib.parse import urlsplit

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MEDIA_CONTRACT_VERSION,
    BinarySendDisposition,
    BoundedMediaSender,
    MediaAck,
    MediaAttach,
    MediaAudioFrame,
    MediaAuthorityBinding,
    MediaCloseResult,
    MediaDetach,
    MediaDetachReason,
    MediaDirection,
    MediaEndOfTurn,
    MediaSpeechStart,
    MediaPlaybackStopReceipt,
    MediaTransportViolation,
    StrictMediaReceiver,
    deserialize_media_control,
    serialize_media_control,
    validate_playback_stop_receipt,
)


DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION = "live-voice.media.dedicated-route.v1"
MEDIA_ROUTE_REGISTRATION_UNAVAILABLE = "MEDIA_ROUTE_REGISTRATION_UNAVAILABLE"
MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN = "MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN"

_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_ROUTE_CONSTRUCTION_TOKEN = object()
_SOCKET_CLOSE_TIMEOUT_SECONDS = 1.0
_MAX_PENDING_FRAMES = 256
_MAX_PENDING_BYTES = 8 * 1024 * 1024
_PROCESS_CONTROL = (GeneratorExit, KeyboardInterrupt, SystemExit)


class DedicatedMediaDownlinkSourceFailure(RuntimeError):
    """A typed, content-free async source failure safe for the media peer."""

    def __init__(self, reason_id: MediaDetachReason) -> None:
        if not isinstance(reason_id, MediaDetachReason):
            raise TypeError("downlink source failure requires a media detach reason")
        super().__init__(reason_id.value)
        self.reason_id = reason_id


class DedicatedMediaRouteTruth(StrEnum):
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


class DedicatedMediaRouteReason(StrEnum):
    FEATURE_DISABLED = "MEDIA_FEATURE_DISABLED"
    ORIGIN_REJECTED = "MEDIA_ORIGIN_REJECTED"
    AUTHORITY_UNAVAILABLE = "MEDIA_AUTHORITY_UNAVAILABLE"
    DIRECTION_UNAVAILABLE = "MEDIA_DIRECTION_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "MEDIA_PROVIDER_UNAVAILABLE"
    TRANSPORT_UNAVAILABLE = "MEDIA_TRANSPORT_UNAVAILABLE"
    LOGGER_ZERO_PERSISTENCE_UNPROVEN = MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN


@dataclass(frozen=True, slots=True)
class DedicatedMediaRouteEvidence:
    """Truthful package evidence which cannot claim formal product readiness."""

    route_truth: DedicatedMediaRouteTruth
    reason_id: DedicatedMediaRouteReason
    route_contract_version: str = field(
        default=DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION, init=False
    )
    media_contract_version: str = field(default=MEDIA_CONTRACT_VERSION, init=False)
    evidence_scope: str = field(default="contract_only", init=False)
    same_origin_required: bool = field(default=True, init=False)
    binary_only: bool = field(default=True, init=False)
    formal_route_ready: bool = field(default=False, init=False)
    real_transport_observed: bool = field(default=False, init=False)
    io_registration_observed: bool = field(default=False, init=False)
    route_to_disk_zero_persistence_observed: bool = field(default=False, init=False)
    package_json_logger_hook_present: bool = field(default=False, init=False)
    package_raw_audio_persistence_hook_present: bool = field(default=False, init=False)
    consumer_privacy_verified: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.route_truth, DedicatedMediaRouteTruth):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "package evidence cannot claim a non-package route truth",
            )
        if not isinstance(self.reason_id, DedicatedMediaRouteReason):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "route reason must use the closed package vocabulary",
            )
        if (self.route_truth is DedicatedMediaRouteTruth.DISABLED) != (
            self.reason_id is DedicatedMediaRouteReason.FEATURE_DISABLED
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "feature-off reason and disabled truth must be bijective",
            )

    @property
    def blocking_reason_ids(self) -> tuple[str, ...]:
        if self.route_truth is DedicatedMediaRouteTruth.DISABLED:
            return (self.reason_id,)
        return (
            MEDIA_ROUTE_REGISTRATION_UNAVAILABLE,
            MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN,
        )


def _canonical_evidence(
    route_truth: DedicatedMediaRouteTruth,
    reason_id: DedicatedMediaRouteReason,
) -> DedicatedMediaRouteEvidence:
    return DedicatedMediaRouteEvidence(
        route_truth=route_truth,
        reason_id=reason_id,
    )


@dataclass(frozen=True, slots=True)
class DedicatedMediaRouteRequest:
    """Trusted construction inputs supplied by a future IO-owned handler."""

    enabled: bool
    expected_origin: str | None
    request_origin: str | None
    binding: MediaAuthorityBinding | None
    provider_available: bool
    binary_transport_available: bool


@dataclass(frozen=True, slots=True)
class InactiveDedicatedMediaRoute:
    active: bool
    reason_id: DedicatedMediaRouteReason
    evidence: DedicatedMediaRouteEvidence

    def __post_init__(self) -> None:
        if (
            self.active is not False
            or not isinstance(self.reason_id, DedicatedMediaRouteReason)
            or type(self.evidence) is not DedicatedMediaRouteEvidence
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "inactive route facts require exact closed package evidence",
            )
        expected_truth = (
            DedicatedMediaRouteTruth.DISABLED
            if self.reason_id is DedicatedMediaRouteReason.FEATURE_DISABLED
            else DedicatedMediaRouteTruth.UNAVAILABLE
        )
        if (
            self.evidence.reason_id is not self.reason_id
            or self.evidence.route_truth is not expected_truth
            or self.evidence != _canonical_evidence(expected_truth, self.reason_id)
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "inactive route reason and truth must describe the same gate",
            )


@dataclass(frozen=True, slots=True)
class ActiveDedicatedMediaRoute:
    active: bool
    session: "_DedicatedMediaRouteSession"
    evidence: DedicatedMediaRouteEvidence

    def __post_init__(self) -> None:
        canonical_evidence = _canonical_evidence(
            DedicatedMediaRouteTruth.UNAVAILABLE,
            DedicatedMediaRouteReason.LOGGER_ZERO_PERSISTENCE_UNPROVEN,
        )
        if (
            self.active is not True
            or type(self.session) is not _DedicatedMediaRouteSession
            or type(self.evidence) is not DedicatedMediaRouteEvidence
            or self.evidence != canonical_evidence
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "active package route requires its exact private session and "
                "unproven zero-persistence evidence",
            )


DedicatedMediaRouteActivation: TypeAlias = (
    InactiveDedicatedMediaRoute | ActiveDedicatedMediaRoute
)


@dataclass(frozen=True, slots=True)
class DedicatedMediaRouteSnapshot:
    attached: bool
    closed: bool
    accepted_frames: int
    last_accepted_seq: int | None
    retained_detach: MediaDetach | None
    package_json_logger_hook_present: bool = field(default=False, init=False)
    package_raw_audio_persistence_hook_present: bool = field(default=False, init=False)
    consumer_privacy_verified: bool = field(default=False, init=False)


class DedicatedMediaSocket(Protocol):
    """Minimal already-accepted socket surface supplied by central registration."""

    def recv(self) -> Awaitable[str | bytes | bytearray | memoryview]: ...

    def send(self, message: str | bytes) -> Awaitable[None]: ...

    def close(self, code: int = 1000, reason: str = "") -> Awaitable[None]: ...


_AwaitedT = TypeVar("_AwaitedT")


async def _await_owned_call(
    source: Callable[[], Awaitable[_AwaitedT]],
) -> _AwaitedT:
    """Own any contract-valid Awaitable behind one cancellable Task."""

    return await source()


@dataclass(frozen=True, slots=True)
class DedicatedMediaLeafCleanupSnapshot:
    capacity: int
    in_use: int
    retained_tasks: int
    closed: bool
    cleanup_complete: bool


class DedicatedMediaLeafCleanupOwner:
    """Bounded lifecycle owner for cancellation-hostile socket/EOT tasks."""

    def __init__(self, *, capacity: int = 64) -> None:
        if type(capacity) is not int or capacity < 2:
            raise ValueError("media cleanup capacity must be an integer >= 2")
        self._capacity = capacity
        self._in_use = 0
        self._closed = False
        self._reservations: dict[object, int] = {}
        self._retained: set[asyncio.Task[Any]] = set()

    @property
    def snapshot(self) -> DedicatedMediaLeafCleanupSnapshot:
        return DedicatedMediaLeafCleanupSnapshot(
            capacity=self._capacity,
            in_use=self._in_use,
            retained_tasks=len(self._retained),
            closed=self._closed,
            cleanup_complete=self._in_use == 0,
        )

    def reserve(self, slots: int = 2) -> object:
        if type(slots) is not int or slots <= 0:
            raise ValueError("media cleanup reservation must be positive")
        if self._closed:
            raise MediaTransportViolation(
                "MEDIA_CLEANUP_OWNER_CLOSED", "media cleanup owner is closed"
            )
        if self._in_use + slots > self._capacity:
            raise MediaTransportViolation(
                "MEDIA_CLEANUP_CAPACITY_EXCEEDED",
                "media cleanup capacity is exhausted",
            )
        token = object()
        self._reservations[token] = slots
        self._in_use += slots
        return token

    def settle_reservation(
        self,
        token: object,
        pending: set[asyncio.Task[Any]],
    ) -> int:
        slots = self._reservations.get(token)
        if slots is None:
            return 0
        completed: set[asyncio.Task[Any]] = set()
        still_pending: set[asyncio.Task[Any]] = set()
        for task in pending:
            (completed if task.done() else still_pending).add(task)
        pending = still_pending
        if len(pending) > slots:
            raise RuntimeError("media cleanup reservation was exceeded")
        self._reservations.pop(token)
        self._in_use -= slots - len(pending)
        for task in completed:
            self._consume_task_result(task)
        for task in pending:
            self._retained.add(task)
            task.add_done_callback(self._consume_retained)
        for task in tuple(pending):
            if task.done():
                self._consume_retained(task)
        return sum(task in self._retained for task in pending)

    async def retry_cleanup(
        self, *, timeout_seconds: float = _SOCKET_CLOSE_TIMEOUT_SECONDS
    ) -> bool:
        if not isinstance(timeout_seconds, (int, float)) or isinstance(
            timeout_seconds, bool
        ):
            raise TypeError("cleanup timeout must be numeric")
        if not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
            raise ValueError("cleanup timeout must be finite and positive")
        tasks = set(self._retained)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            done, _pending = await asyncio.wait(tasks, timeout=float(timeout_seconds))
            for task in done:
                self._consume_retained(task)
        return self.snapshot.cleanup_complete

    async def close(
        self, *, timeout_seconds: float = _SOCKET_CLOSE_TIMEOUT_SECONDS
    ) -> bool:
        if not isinstance(timeout_seconds, (int, float)) or isinstance(
            timeout_seconds, bool
        ):
            raise TypeError("cleanup timeout must be numeric")
        if not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
            raise ValueError("cleanup timeout must be finite and positive")
        self._closed = True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + float(timeout_seconds)
        if await self.retry_cleanup(timeout_seconds=timeout_seconds):
            return True
        if not self._reservations:
            return self.snapshot.cleanup_complete
        while self._reservations and loop.time() < deadline:
            await asyncio.sleep(0)
        return self.snapshot.cleanup_complete

    def _consume_retained(self, task: asyncio.Task[Any]) -> None:
        if task not in self._retained:
            return
        self._retained.discard(task)
        self._in_use -= 1
        self._consume_task_result(task)

    @staticmethod
    def _consume_task_result(task: asyncio.Task[Any]) -> None:
        try:
            task.exception()
        except BaseException:
            pass


@dataclass(frozen=True, slots=True)
class DedicatedMediaSocketLeafResult:
    """Runtime facts for one unregistered, injected socket leaf."""

    activated: bool
    socket_touched: bool
    attach_sent: bool
    accepted_frames: int
    close_result: MediaCloseResult | None
    reason_id: DedicatedMediaRouteReason | MediaDetachReason
    sent_frames: int = 0
    acknowledged_through_seq: int | None = None
    playback_stop_receipts: int = 0
    configured_max_pending_frames: int = 0
    configured_max_pending_bytes: int = 0
    peak_pending_frames: int = 0
    peak_pending_bytes: int = 0
    cleanup_complete: bool = True
    cleanup_pending_tasks: int = 0
    business_cancel_count_delta: int = field(default=0, init=False)
    evidence_scope: str = field(default="dedicated_media_socket_leaf_only", init=False)
    registered_route_observed: bool = field(default=False, init=False)
    route_to_disk_zero_persistence_observed: bool = field(default=False, init=False)
    formal_route_ready: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if type(self.business_cancel_count_delta) is not int:
            raise MediaTransportViolation(
                "MEDIA_CANCEL_SCOPE_VIOLATION",
                "media socket leaf cannot mutate business cancellation",
            )
        if (
            type(self.cleanup_complete) is not bool
            or type(self.cleanup_pending_tasks) is not int
            or self.cleanup_pending_tasks < 0
            or self.cleanup_complete != (self.cleanup_pending_tasks == 0)
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_CLEANUP_TRUTH",
                "media cleanup count contradicts completion truth",
            )
        if self.activated is False and (
            self.socket_touched
            or self.attach_sent
            or self.accepted_frames != 0
            or self.sent_frames != 0
            or self.acknowledged_through_seq is not None
            or self.playback_stop_receipts != 0
            or self.configured_max_pending_frames != 0
            or self.configured_max_pending_bytes != 0
            or self.peak_pending_frames != 0
            or self.peak_pending_bytes != 0
            or self.close_result is not None
            or not isinstance(self.reason_id, DedicatedMediaRouteReason)
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "inactive socket leaves require zero transport effects",
            )
        if self.activated is True and not isinstance(self.reason_id, MediaDetachReason):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "active socket leaf reason must use the media close vocabulary",
            )
        if self.activated is True and (
            self.peak_pending_frames > self.configured_max_pending_frames
            or self.peak_pending_bytes > self.configured_max_pending_bytes
            or min(
                self.configured_max_pending_frames,
                self.configured_max_pending_bytes,
                self.peak_pending_frames,
                self.peak_pending_bytes,
            )
            < 0
        ):
            raise MediaTransportViolation(
                "MEDIA_INVALID_ROUTE_EVIDENCE",
                "media socket queue facts exceed their configured bounds",
            )


def _inactive(
    reason_id: DedicatedMediaRouteReason, *, disabled: bool = False
) -> InactiveDedicatedMediaRoute:
    return InactiveDedicatedMediaRoute(
        active=False,
        reason_id=reason_id,
        evidence=_canonical_evidence(
            route_truth=(
                DedicatedMediaRouteTruth.DISABLED
                if disabled
                else DedicatedMediaRouteTruth.UNAVAILABLE
            ),
            reason_id=reason_id,
        ),
    )


def _canonical_origin(value: object) -> tuple[str, str, int] | None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not value.isascii()
        or any(character.isspace() or ord(character) < 0x20 for character in value)
        or "?" in value
        or "#" in value
    ):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname is None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or (port is not None and port == 0)
    ):
        return None
    hostname = parsed.hostname.lower()
    if not hostname or hostname.endswith(".") or "%" in hostname:
        return None
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if len(hostname) > 253 or any(
            _DOMAIN_LABEL.fullmatch(label) is None for label in hostname.split(".")
        ):
            return None
    return scheme, hostname, port or (443 if scheme == "https" else 80)


def _is_same_origin(expected_origin: object, request_origin: object) -> bool:
    expected = _canonical_origin(expected_origin)
    return expected is not None and expected == _canonical_origin(request_origin)


def create_dedicated_media_route(
    request: DedicatedMediaRouteRequest,
    *,
    on_audio_frame: Callable[[MediaAudioFrame], None],
) -> DedicatedMediaRouteActivation:
    """Create a package session only after every local gate passes.

    The feature-off branch intentionally returns before reading any other
    request field or inspecting the consumer.
    """

    if not isinstance(request, DedicatedMediaRouteRequest):
        raise MediaTransportViolation(
            "MEDIA_INVALID_ROUTE_REQUEST", "route request must be typed"
        )
    if request.enabled is not True:
        return _inactive(DedicatedMediaRouteReason.FEATURE_DISABLED, disabled=True)
    if not _is_same_origin(request.expected_origin, request.request_origin):
        return _inactive(DedicatedMediaRouteReason.ORIGIN_REJECTED)
    if not isinstance(request.binding, MediaAuthorityBinding):
        return _inactive(DedicatedMediaRouteReason.AUTHORITY_UNAVAILABLE)
    if request.binding.direction is not MediaDirection.UPLINK:
        return _inactive(DedicatedMediaRouteReason.DIRECTION_UNAVAILABLE)
    if request.provider_available is not True:
        return _inactive(DedicatedMediaRouteReason.PROVIDER_UNAVAILABLE)
    if request.binary_transport_available is not True:
        return _inactive(DedicatedMediaRouteReason.TRANSPORT_UNAVAILABLE)
    if not callable(on_audio_frame):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "audio consumer must be callable"
        )
    return ActiveDedicatedMediaRoute(
        active=True,
        session=_DedicatedMediaRouteSession(
            request.binding,
            on_audio_frame=on_audio_frame,
            construction_token=_ROUTE_CONSTRUCTION_TOKEN,
        ),
        evidence=DedicatedMediaRouteEvidence(
            route_truth=DedicatedMediaRouteTruth.UNAVAILABLE,
            reason_id=(DedicatedMediaRouteReason.LOGGER_ZERO_PERSISTENCE_UNPROVEN),
        ),
    )


class _DedicatedMediaRouteSession:
    """One same-origin, exact-binding, binary-only media lease."""

    def __init__(
        self,
        binding: MediaAuthorityBinding,
        *,
        on_audio_frame: Callable[[MediaAudioFrame], None],
        construction_token: object,
    ) -> None:
        if construction_token is not _ROUTE_CONSTRUCTION_TOKEN:
            raise MediaTransportViolation(
                "MEDIA_ROUTE_FACTORY_REQUIRED",
                "route sessions must pass the same-origin package factory",
            )
        if not isinstance(binding, MediaAuthorityBinding):
            raise MediaTransportViolation(
                "MEDIA_AUTHORITY_UNAVAILABLE", "trusted media binding is required"
            )
        self.binding = binding
        self._receiver = StrictMediaReceiver(binding, on_audio_frame=on_audio_frame)
        self._retained_detach: MediaDetach | None = None
        self._accepted_frames = 0
        self._last_accepted_seq: int | None = None

    def accept_server_attach(self, control: MediaAttach) -> MediaDetach | None:
        """Accept only the exact typed attach owned by server composition."""

        if self._retained_detach is not None:
            return self._retained_detach
        if not isinstance(control, MediaAttach) or control.binding is not self.binding:
            return self._terminate(MediaDetachReason.BINDING_MISMATCH)
        detach = self._receiver.attach(control)
        return None if detach is None else self._retain(detach)

    def accept_binary(
        self, raw: bytes | bytearray | memoryview
    ) -> MediaAck | MediaDetach:
        """Accept one LVM1 frame; text/JSON and pre-attach bytes fail closed."""

        if self._retained_detach is not None:
            return self._retained_detach
        result = self._receiver.accept_binary(raw)
        if isinstance(result, MediaDetach):
            return self._retain(result)
        self._accepted_frames += 1
        self._last_accepted_seq = result.through_seq
        return result

    def accept_detach(self, control: MediaDetach) -> MediaCloseResult:
        """Retain one typed detach and make cleanup replay-safe."""

        if self._retained_detach is not None:
            return self._close_result(was_active=False)
        if not isinstance(control, MediaDetach):
            self._terminate(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
            return self._close_result(was_active=True)
        result = self._receiver.accept_detach(control)
        assert result.detach is not None
        retained_detach = self._retain(result.detach)
        return MediaCloseResult(
            was_active=result.was_active,
            reason_id=retained_detach.reason_id,
            dropped_frames=0,
            dropped_bytes=0,
            detach=retained_detach,
        )

    def close(
        self,
        reason_id: MediaDetachReason = MediaDetachReason.LOCAL_CLOSE,
    ) -> MediaCloseResult:
        if not isinstance(reason_id, MediaDetachReason):
            reason_id = MediaDetachReason.LOCAL_CLOSE
        was_active = self._retained_detach is None
        self._terminate(reason_id)
        return self._close_result(was_active=was_active)

    def snapshot(self) -> DedicatedMediaRouteSnapshot:
        return DedicatedMediaRouteSnapshot(
            attached=self._receiver.attached,
            closed=self._retained_detach is not None,
            accepted_frames=self._accepted_frames,
            last_accepted_seq=self._last_accepted_seq,
            retained_detach=self._retained_detach,
        )

    def _terminate(self, reason_id: MediaDetachReason) -> MediaDetach:
        if self._retained_detach is None:
            result = self._receiver.close(reason_id)
            assert result.detach is not None
            self._retained_detach = result.detach
        return self._retained_detach

    def _retain(self, detach: MediaDetach) -> MediaDetach:
        if self._retained_detach is None:
            self._retained_detach = detach
            self._receiver.close(detach.reason_id)
        return self._retained_detach

    def _close_result(self, *, was_active: bool) -> MediaCloseResult:
        assert self._retained_detach is not None
        return MediaCloseResult(
            was_active=was_active,
            reason_id=self._retained_detach.reason_id,
            dropped_frames=0,
            dropped_bytes=0,
            detach=self._retained_detach,
        )


async def run_dedicated_media_socket_leaf(
    request: DedicatedMediaRouteRequest,
    *,
    socket: DedicatedMediaSocket,
    on_audio_frame: Callable[[MediaAudioFrame], None],
    on_complete: Callable[[DedicatedMediaSocketLeafResult], None] | None = None,
    on_uplink_ack_sent: Callable[[MediaAck], None] | None = None,
    next_speech_start: Callable[[], Awaitable[MediaSpeechStart]] | None = None,
    next_end_of_turn: Callable[[], Awaitable[MediaEndOfTurn]] | None = None,
    cleanup_owner: DedicatedMediaLeafCleanupOwner | None = None,
) -> DedicatedMediaSocketLeafResult:
    """Run one injected uplink WebSocket after the central handshake.

    The central route remains responsible for registration, subprotocol
    negotiation, trusted binding lookup, and passing the observed Origin into
    ``request``.  This leaf performs no logging, persistence, or retry and owns
    its socket/EOT arbitration tasks through a bounded cleanup owner. Feature-off
    returns before inspecting or touching ``socket``.
    """

    activation = create_dedicated_media_route(
        request,
        on_audio_frame=on_audio_frame,
    )
    if isinstance(activation, InactiveDedicatedMediaRoute):
        return DedicatedMediaSocketLeafResult(
            activated=False,
            socket_touched=False,
            attach_sent=False,
            accepted_frames=0,
            close_result=None,
            reason_id=activation.reason_id,
        )
    if on_complete is not None and not callable(on_complete):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "uplink completion consumer must be callable"
        )
    if on_uplink_ack_sent is not None and not callable(on_uplink_ack_sent):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "uplink ACK observer must be callable"
        )
    if next_end_of_turn is not None and not callable(next_end_of_turn):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "end-of-turn source must be callable"
        )
    if next_speech_start is not None and not callable(next_speech_start):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "speech-start source must be callable"
        )
    if (
        next_speech_start is not None or next_end_of_turn is not None
    ) and not isinstance(cleanup_owner, DedicatedMediaLeafCleanupOwner):
        raise MediaTransportViolation(
            "MEDIA_CLEANUP_OWNER_REQUIRED",
            "speech boundary arbitration requires a bounded cleanup owner",
        )
    cleanup_token = (
        cleanup_owner.reserve(
            1 + int(next_speech_start is not None) + int(next_end_of_turn is not None)
        )
        if (next_speech_start is not None or next_end_of_turn is not None)
        and cleanup_owner is not None
        else None
    )

    session = activation.session
    binding = session.binding
    attach_sent = False
    socket_touched = False
    socket_close_started = False
    speech_start_task: asyncio.Task[MediaSpeechStart] | None = None
    speech_start_sent = False
    speech_start_ms: int | None = None
    speech_boundaries_disabled = False
    end_of_turn_task: asyncio.Task[MediaEndOfTurn] | None = None
    end_of_turn_sent = False
    receive_task: asyncio.Task[str | bytes | bytearray | memoryview] | None = None
    cleanup_settled = False
    cleanup_pending_count = 0

    async def settle_owned_tasks(
        *tasks: asyncio.Future[Any] | None,
    ) -> tuple[BaseException | None, int]:
        nonlocal cleanup_pending_count, cleanup_settled
        if cleanup_settled:
            return None, cleanup_pending_count
        process_control: BaseException | None = None
        wait_interruption: BaseException | None = None
        owned_tasks = {
            task
            for task in (*tasks, speech_start_task, end_of_turn_task)
            if task is not None
        }
        for task in owned_tasks:
            if not task.done():
                task.cancel()
        pending = {task for task in owned_tasks if not task.done()}
        done = {task for task in owned_tasks if task.done()}
        if pending:
            try:
                settled, pending = await asyncio.wait(
                    pending, timeout=_SOCKET_CLOSE_TIMEOUT_SECONDS
                )
                done.update(settled)
            except BaseException as error:
                # Even caller cancellation or process control during the
                # bounded wait must hand every child to the lifecycle owner.
                wait_interruption = error
                done.update(task for task in pending if task.done())
                pending = {task for task in pending if not task.done()}
        for task in done:
            try:
                task.result()
            except _PROCESS_CONTROL as error:
                if process_control is None:
                    process_control = error
            except (Exception, asyncio.CancelledError):
                pass
        retained = {
            cast(asyncio.Task[Any], task)
            for task in pending
            if isinstance(task, asyncio.Task)
        }
        if cleanup_owner is not None and cleanup_token is not None:
            cleanup_pending_count = cleanup_owner.settle_reservation(
                cleanup_token, retained
            )
        cleanup_settled = True
        if wait_interruption is not None:
            raise wait_interruption
        return process_control, cleanup_pending_count

    async def close_socket() -> None:
        nonlocal socket_close_started, socket_touched
        if socket_close_started:
            return
        socket_close_started = True
        try:
            close = socket.close
        except Exception:
            return
        if not callable(close):
            return
        socket_touched = True
        try:
            await asyncio.wait_for(
                close(1000, "live-voice media leaf closed"),
                timeout=_SOCKET_CLOSE_TIMEOUT_SECONDS,
            )
        except Exception:
            # The local exact-binding fence is retained even if the transport
            # cannot confirm physical closure.
            pass

    async def settle_transport_interruption() -> None:
        """Close exact authority and settle every child behind one primary."""

        try:
            session.close(MediaDetachReason.TRANSPORT_CLOSED)
        except BaseException:
            pass
        try:
            await close_socket()
        except BaseException:
            pass
        try:
            await settle_owned_tasks(
                receive_task,
                speech_start_task,
                end_of_turn_task,
            )
        except BaseException:
            pass

    async def send_control(
        control: MediaAck
        | MediaDetach
        | MediaAttach
        | MediaSpeechStart
        | MediaEndOfTurn,
    ) -> bool:
        nonlocal socket_touched
        try:
            send = socket.send
        except (
            asyncio.CancelledError,
            GeneratorExit,
            KeyboardInterrupt,
            SystemExit,
        ):
            await settle_transport_interruption()
            raise
        except Exception:
            return False
        if not callable(send):
            return False
        socket_touched = True
        try:
            await send(serialize_media_control(control))
        except (
            asyncio.CancelledError,
            GeneratorExit,
            KeyboardInterrupt,
            SystemExit,
        ):
            await settle_transport_interruption()
            raise
        except Exception:
            return False
        return True

    async def send_close_detach(closed: MediaCloseResult) -> bool:
        if closed.detach is None:
            return False
        return await send_control(closed.detach)

    def result(
        closed: MediaCloseResult, *, cleanup_pending_tasks: int = 0
    ) -> DedicatedMediaSocketLeafResult:
        snapshot = session.snapshot()
        return DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=socket_touched,
            attach_sent=attach_sent,
            accepted_frames=snapshot.accepted_frames,
            close_result=closed,
            reason_id=closed.reason_id,
            cleanup_complete=cleanup_pending_tasks == 0,
            cleanup_pending_tasks=cleanup_pending_tasks,
        )

    async def terminate(
        closed: MediaCloseResult,
        *,
        acknowledge_peer_detach: bool = False,
    ) -> DedicatedMediaSocketLeafResult:
        owned_speech_start = speech_start_task
        owned_end_of_turn = end_of_turn_task
        owned_receive = receive_task
        for owned_task in (
            owned_receive,
            owned_speech_start,
            owned_end_of_turn,
        ):
            if owned_task is not None and not owned_task.done():
                owned_task.cancel()
        try:
            task_process_control, cleanup_pending_tasks = await settle_owned_tasks(
                owned_receive, owned_speech_start, owned_end_of_turn
            )
        except BaseException:
            try:
                await close_socket()
            except BaseException:
                pass
            raise
        if task_process_control is not None:
            try:
                await close_socket()
            finally:
                raise task_process_control
        leaf_result = result(closed, cleanup_pending_tasks=cleanup_pending_tasks)
        primary_failure: BaseException | None = None
        try:
            if on_complete is not None:
                on_complete(leaf_result)
                if acknowledge_peer_detach:
                    # This exact typed echo is the end-to-end completion
                    # receipt.  It is sent only after the authority owner has
                    # retained the route result, so a peer behind a WebSocket
                    # proxy need not infer completion from transport close.
                    await send_close_detach(closed)
        except BaseException as error:
            primary_failure = error
        # Completion must become registry-visible before the peer observes
        # physical close and can submit its batch Speech request.  Cleanup
        # process control is secondary to an already-fixed completion failure.
        close_failure: BaseException | None = None
        try:
            await close_socket()
        except BaseException as error:
            close_failure = error
        if primary_failure is not None:
            raise primary_failure from None
        if close_failure is not None:
            raise close_failure from None
        return leaf_result

    attach = MediaAttach(binding)
    attach_failure = session.accept_server_attach(attach)
    assert attach_failure is None
    try:
        attach_sent_ok = await send_control(attach)
    except asyncio.CancelledError:
        try:
            await close_socket()
        except BaseException:
            pass
        try:
            await settle_owned_tasks()
        except BaseException:
            pass
        raise
    except _PROCESS_CONTROL:
        session.close(MediaDetachReason.TRANSPORT_CLOSED)
        try:
            await close_socket()
        except BaseException:
            pass
        try:
            await settle_owned_tasks()
        except BaseException:
            pass
        raise
    if not attach_sent_ok:
        closed = session.close(MediaDetachReason.TRANSPORT_SEND_FAILED)
        return await terminate(closed)
    attach_sent = True
    if next_speech_start is not None:
        try:
            speech_start_task = asyncio.create_task(
                _await_owned_call(next_speech_start),
                name="live-voice-media-speech-start",
            )
        except BaseException:
            session.close(MediaDetachReason.TRANSPORT_CLOSED)
            try:
                await close_socket()
            except BaseException:
                pass
            try:
                await settle_owned_tasks()
            except BaseException:
                pass
            raise
    if next_end_of_turn is not None:
        try:
            end_of_turn_task = asyncio.create_task(
                _await_owned_call(next_end_of_turn),
                name="live-voice-media-end-of-turn",
            )
        except BaseException:
            session.close(MediaDetachReason.TRANSPORT_CLOSED)
            try:
                await close_socket()
            except BaseException:
                pass
            try:
                await settle_owned_tasks()
            except BaseException:
                pass
            raise

    while True:
        try:
            recv = socket.recv
        except (
            asyncio.CancelledError,
            GeneratorExit,
            KeyboardInterrupt,
            SystemExit,
        ):
            await settle_transport_interruption()
            raise
        except Exception:
            recv = None
        if not callable(recv):
            closed = session.close(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
            await send_close_detach(closed)
            return await terminate(closed)
        socket_touched = True
        try:
            boundary_tasks = {
                task
                for task in (speech_start_task, end_of_turn_task)
                if task is not None
            }
            if not boundary_tasks:
                message = await recv()
            else:
                receive_task = asyncio.create_task(
                    _await_owned_call(recv),
                    name="live-voice-media-uplink-receive",
                )
                if end_of_turn_sent:
                    message = await asyncio.shield(receive_task)
                else:
                    awaited_boundaries: set[asyncio.Task[Any]] = set()
                    if not speech_start_sent and speech_start_task is not None:
                        awaited_boundaries.add(speech_start_task)
                    if (
                        not speech_boundaries_disabled
                        and (speech_start_sent or speech_start_task is None)
                        and end_of_turn_task is not None
                    ):
                        awaited_boundaries.add(end_of_turn_task)
                    done, _pending = await asyncio.wait(
                        {receive_task, *awaited_boundaries},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if receive_task in done:
                        # Peer input wins an exact same-loop race. Its ACK/detach
                        # is serialized before the already-ready server control.
                        message = receive_task.result()
                    else:
                        if speech_start_task is not None and speech_start_task in done:
                            try:
                                speech_start = speech_start_task.result()
                            except Exception:
                                # Without a trusted start, EOT remains manual.
                                speech_start_task = None
                                speech_boundaries_disabled = True
                            else:
                                if (
                                    speech_start.lease_id != binding.lease_id
                                    or speech_start.generation
                                    != binding.generation.value
                                    or binding.direction is not MediaDirection.UPLINK
                                    or speech_start_sent
                                ):
                                    closed = session.close(
                                        MediaDetachReason.BINDING_MISMATCH
                                    )
                                    await send_close_detach(closed)
                                    return await terminate(closed)
                                if not await send_control(speech_start):
                                    closed = session.close(
                                        MediaDetachReason.TRANSPORT_SEND_FAILED
                                    )
                                    return await terminate(closed)
                                speech_start_sent = True
                                speech_start_ms = speech_start.provider_start_ms
                        if (
                            not speech_boundaries_disabled
                            and (speech_start_sent or speech_start_task is None)
                            and end_of_turn_task is not None
                            and end_of_turn_task.done()
                        ):
                            try:
                                end_of_turn = end_of_turn_task.result()
                            except Exception:
                                # The product owner logs/XOBS the typed failure. Keep
                                # manual stop usable without claiming automatic EOT.
                                end_of_turn_task = None
                            else:
                                if (
                                    end_of_turn.lease_id != binding.lease_id
                                    or end_of_turn.generation
                                    != binding.generation.value
                                    or binding.direction is not MediaDirection.UPLINK
                                    or (
                                        speech_start_sent
                                        and end_of_turn.provider_start_ms
                                        != speech_start_ms
                                    )
                                ):
                                    closed = session.close(
                                        MediaDetachReason.BINDING_MISMATCH
                                    )
                                    await send_close_detach(closed)
                                    return await terminate(closed)
                                if not await send_control(end_of_turn):
                                    closed = session.close(
                                        MediaDetachReason.TRANSPORT_SEND_FAILED
                                    )
                                    return await terminate(closed)
                                end_of_turn_sent = True
                        message = await asyncio.shield(receive_task)
                receive_task = None
        except asyncio.CancelledError:
            session.close(MediaDetachReason.TRANSPORT_CLOSED)
            try:
                await close_socket()
            except BaseException:
                # The caller cancellation remains authoritative after the
                # local socket and sibling-task cleanup attempt.
                pass
            try:
                await settle_owned_tasks(receive_task, end_of_turn_task)
            except BaseException:
                pass
            raise
        except _PROCESS_CONTROL:
            session.close(MediaDetachReason.TRANSPORT_CLOSED)
            try:
                await close_socket()
            except BaseException:
                # Preserve the exact EOT/recv process-control exception.
                pass
            try:
                await settle_owned_tasks(receive_task, end_of_turn_task)
            except BaseException:
                pass
            raise
        except Exception:
            closed = session.close(MediaDetachReason.TRANSPORT_CLOSED)
            return await terminate(closed)

        try:
            if isinstance(message, str):
                try:
                    control = deserialize_media_control(message)
                except MediaTransportViolation:
                    closed = session.close(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
                    await send_close_detach(closed)
                    return await terminate(closed)
                if not isinstance(control, MediaDetach):
                    closed = session.close(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
                    await send_close_detach(closed)
                    return await terminate(closed)
                closed = session.accept_detach(control)
                return await terminate(closed, acknowledge_peer_detach=True)

            if not isinstance(message, (bytes, bytearray, memoryview)):
                closed = session.close(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
                await send_close_detach(closed)
                return await terminate(closed)

            control = session.accept_binary(message)
            if not await send_control(control):
                closed = session.close(MediaDetachReason.TRANSPORT_SEND_FAILED)
                return await terminate(closed)
            if isinstance(control, MediaAck) and on_uplink_ack_sent is not None:
                try:
                    on_uplink_ack_sent(control)
                except BaseException:
                    # This optional diagnostic cannot alter media authority or
                    # turn a successfully-sent ACK into a transport failure.
                    pass
            if isinstance(control, MediaDetach):
                closed = session.close(control.reason_id)
                return await terminate(closed)
        except BaseException:
            session.close(MediaDetachReason.TRANSPORT_CLOSED)
            try:
                await close_socket()
            except BaseException:
                pass
            try:
                await settle_owned_tasks(
                    receive_task,
                    speech_start_task,
                    end_of_turn_task,
                )
            except BaseException:
                pass
            raise


async def run_dedicated_media_downlink_socket_leaf(
    request: DedicatedMediaRouteRequest,
    *,
    socket: DedicatedMediaSocket,
    frames: Iterable[MediaAudioFrame] | AsyncIterable[MediaAudioFrame],
    on_playback_stop: Callable[[MediaPlaybackStopReceipt], None],
    on_complete: Callable[[DedicatedMediaSocketLeafResult], None] | None = None,
    max_pending_frames: int = 8,
    max_pending_bytes: int = 131_072,
) -> DedicatedMediaSocketLeafResult:
    """Send one exact downlink lease over an injected, already-accepted socket."""

    if not isinstance(request, DedicatedMediaRouteRequest):
        raise MediaTransportViolation(
            "MEDIA_INVALID_ROUTE_REQUEST", "route request must be typed"
        )
    if request.enabled is not True:
        return DedicatedMediaSocketLeafResult(
            activated=False,
            socket_touched=False,
            attach_sent=False,
            accepted_frames=0,
            close_result=None,
            reason_id=DedicatedMediaRouteReason.FEATURE_DISABLED,
        )
    if not _is_same_origin(request.expected_origin, request.request_origin):
        reason = DedicatedMediaRouteReason.ORIGIN_REJECTED
    elif not isinstance(request.binding, MediaAuthorityBinding):
        reason = DedicatedMediaRouteReason.AUTHORITY_UNAVAILABLE
    elif request.binding.direction is not MediaDirection.DOWNLINK:
        reason = DedicatedMediaRouteReason.DIRECTION_UNAVAILABLE
    elif request.provider_available is not True:
        reason = DedicatedMediaRouteReason.PROVIDER_UNAVAILABLE
    elif request.binary_transport_available is not True:
        reason = DedicatedMediaRouteReason.TRANSPORT_UNAVAILABLE
    else:
        reason = None
    if reason is not None:
        return DedicatedMediaSocketLeafResult(
            activated=False,
            socket_touched=False,
            attach_sent=False,
            accepted_frames=0,
            close_result=None,
            reason_id=reason,
        )
    if not callable(on_playback_stop):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "playback stop consumer must be callable"
        )
    if on_complete is not None and not callable(on_complete):
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "downlink completion consumer must be callable"
        )
    if (
        type(max_pending_frames) is not int
        or not 0 < max_pending_frames <= _MAX_PENDING_FRAMES
        or type(max_pending_bytes) is not int
        or not 0 < max_pending_bytes <= _MAX_PENDING_BYTES
    ):
        raise MediaTransportViolation(
            "MEDIA_INVALID_BACKPRESSURE_LIMIT",
            "downlink queue limits exceed the bounded practical range",
        )

    binding = request.binding
    assert binding is not None
    sender = BoundedMediaSender(
        binding,
        max_pending_frames=max_pending_frames,
        max_pending_bytes=max_pending_bytes,
    )
    frame_iterator: Iterator[MediaAudioFrame] | None = None
    async_frame_iterator: AsyncIterator[MediaAudioFrame] | None = None
    try:
        async_factory = getattr(frames, "__aiter__", None)
        if callable(async_factory):
            async_frame_iterator = async_factory()
            if not hasattr(async_frame_iterator, "__anext__"):
                raise TypeError("async downlink source returned no iterator")
        else:
            frame_iterator = iter(cast(Iterable[MediaAudioFrame], frames))
    except TypeError as error:
        raise MediaTransportViolation(
            "MEDIA_INVALID_CONSUMER", "downlink frames must be iterable"
        ) from error
    socket_touched = False
    attach_sent = False
    sent_frames = 0
    acknowledged_through_seq: int | None = None
    playback_stop_receipts = 0
    peak_pending_frames = 0
    peak_pending_bytes = 0

    async def close_socket() -> None:
        nonlocal socket_touched
        try:
            close = socket.close
        except Exception:
            return
        if not callable(close):
            return
        socket_touched = True
        try:
            await asyncio.wait_for(
                close(1000, "live-voice media downlink leaf closed"),
                timeout=_SOCKET_CLOSE_TIMEOUT_SECONDS,
            )
        except Exception:
            pass

    async def send_message(message: str | bytes) -> bool:
        nonlocal socket_touched
        try:
            send = socket.send
        except Exception:
            return False
        if not callable(send):
            return False
        socket_touched = True
        try:
            await send(message)
        except asyncio.CancelledError:
            sender.close(MediaDetachReason.TRANSPORT_CLOSED)
            await asyncio.shield(close_socket())
            raise
        except Exception:
            return False
        return True

    def coerce_reason(value: object) -> MediaDetachReason:
        try:
            return MediaDetachReason(value)
        except (TypeError, ValueError):
            return MediaDetachReason.TRANSPORT_PROTOCOL_ERROR

    def result(closed: MediaCloseResult) -> DedicatedMediaSocketLeafResult:
        return DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=socket_touched,
            attach_sent=attach_sent,
            accepted_frames=0,
            close_result=closed,
            reason_id=closed.reason_id,
            sent_frames=sent_frames,
            acknowledged_through_seq=acknowledged_through_seq,
            playback_stop_receipts=playback_stop_receipts,
            configured_max_pending_frames=max_pending_frames,
            configured_max_pending_bytes=max_pending_bytes,
            peak_pending_frames=peak_pending_frames,
            peak_pending_bytes=peak_pending_bytes,
        )

    async def terminate(
        reason_id: MediaDetachReason,
        *,
        send_detach: bool = True,
    ) -> DedicatedMediaSocketLeafResult:
        closed = sender.close(reason_id)
        if send_detach and closed.detach is not None:
            await send_message(serialize_media_control(closed.detach))
        leaf_result = result(closed)
        try:
            if on_complete is not None:
                on_complete(leaf_result)
        finally:
            # Completion must become registry-visible before the peer observes
            # physical close and can submit its browser render receipt.
            await close_socket()
        return leaf_result

    if not await send_message(serialize_media_control(MediaAttach(binding))):
        return await terminate(
            MediaDetachReason.TRANSPORT_SEND_FAILED,
            send_detach=False,
        )
    attach_sent = True
    source_exhausted = False
    pending_frame: MediaAudioFrame | None = None

    async def take_source_frame() -> MediaAudioFrame:
        if async_frame_iterator is not None:
            return await async_frame_iterator.__anext__()
        assert frame_iterator is not None
        try:
            return next(frame_iterator)
        except StopIteration as error:
            # StopIteration cannot escape an async function (PEP 479).
            raise StopAsyncIteration from error

    async def close_source() -> None:
        iterator = async_frame_iterator
        if iterator is None:
            return
        close = getattr(iterator, "aclose", None)
        if not callable(close):
            return
        try:
            await asyncio.wait_for(close(), timeout=_SOCKET_CLOSE_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            return
        except BaseException:
            return

    try:
        while True:
            while not source_exhausted:
                if pending_frame is None:
                    try:
                        pending_frame = await take_source_frame()
                    except StopAsyncIteration:
                        source_exhausted = True
                        break
                    except DedicatedMediaDownlinkSourceFailure as error:
                        return await terminate(error.reason_id)
                    except asyncio.CancelledError:
                        raise
                    except BaseException:
                        return await terminate(MediaDetachReason.CONSUMER_FAILED)
                if not isinstance(pending_frame, MediaAudioFrame):
                    return await terminate(MediaDetachReason.INVALID_FRAME)
                enqueued = sender.enqueue(pending_frame)
                if enqueued.accepted:
                    peak_pending_frames = max(
                        peak_pending_frames, sender.pending_frames
                    )
                    peak_pending_bytes = max(peak_pending_bytes, sender.pending_bytes)
                    pending_frame = None
                    # A native stream may not have its next Provider chunk yet.
                    # Drain the accepted chunk immediately and wait for its
                    # browser render ACK instead of blocking first audio behind
                    # a speculative pull or reading beyond downlink pressure.
                    if async_frame_iterator is not None:
                        break
                    continue
                if enqueued.reason_id == "MEDIA_BACKPRESSURE_LIMIT":
                    break
                return await terminate(coerce_reason(enqueued.reason_id))

            outbound: list[bytes] = []

            def retain_outbound(binary: bytes) -> BinarySendDisposition:
                outbound.append(binary)
                return BinarySendDisposition.SENT

            drained = sender.drain(retain_outbound)
            if sender.closed:
                return await terminate(coerce_reason(drained.reason_id))
            for binary in outbound:
                if not await send_message(binary):
                    return await terminate(
                        MediaDetachReason.TRANSPORT_SEND_FAILED,
                        send_detach=False,
                    )
                sent_frames += 1

            if source_exhausted and sender.pending_frames == 0:
                return await terminate(MediaDetachReason.LOCAL_CLOSE)

            try:
                recv = socket.recv
            except Exception:
                recv = None
            if not callable(recv):
                return await terminate(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
            socket_touched = True
            try:
                message = await recv()
            except asyncio.CancelledError:
                sender.close(MediaDetachReason.TRANSPORT_CLOSED)
                await asyncio.shield(close_socket())
                raise
            except Exception:
                return await terminate(
                    MediaDetachReason.TRANSPORT_CLOSED,
                    send_detach=False,
                )
            if not isinstance(message, str):
                return await terminate(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
            try:
                control = deserialize_media_control(message)
            except MediaTransportViolation:
                return await terminate(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
            if isinstance(control, MediaAck):
                detach = sender.acknowledge(control)
                if detach is not None:
                    return await terminate(detach.reason_id)
                acknowledged_through_seq = control.through_seq
                continue
            if isinstance(control, MediaPlaybackStopReceipt):
                try:
                    exact_stop = validate_playback_stop_receipt(binding, control)
                    if (
                        exact_stop.confirmed_through_seq is not None
                        and exact_stop.confirmed_through_seq >= sent_frames
                    ):
                        return await terminate(MediaDetachReason.ACK_UNSENT)
                    on_playback_stop(exact_stop)
                except MediaTransportViolation as error:
                    return await terminate(coerce_reason(error.reason_id))
                except Exception:
                    return await terminate(MediaDetachReason.CONSUMER_FAILED)
                playback_stop_receipts += 1
                return await terminate(MediaDetachReason.PEER_CLOSE)
            if isinstance(control, MediaDetach):
                if (
                    control.lease_id != binding.lease_id
                    or control.generation != binding.generation.value
                ):
                    mismatch = (
                        MediaDetachReason.STALE_GENERATION
                        if control.generation != binding.generation.value
                        else MediaDetachReason.BINDING_MISMATCH
                    )
                    return await terminate(mismatch)
                return await terminate(control.reason_id, send_detach=False)
            return await terminate(MediaDetachReason.TRANSPORT_PROTOCOL_ERROR)
    finally:
        await close_source()


__all__ = [
    "DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION",
    "MEDIA_CONTRACT_VERSION",
    "MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN",
    "MEDIA_ROUTE_REGISTRATION_UNAVAILABLE",
    "ActiveDedicatedMediaRoute",
    "DedicatedMediaLeafCleanupOwner",
    "DedicatedMediaLeafCleanupSnapshot",
    "DedicatedMediaRouteActivation",
    "DedicatedMediaRouteEvidence",
    "DedicatedMediaRouteRequest",
    "DedicatedMediaRouteReason",
    "DedicatedMediaRouteSnapshot",
    "DedicatedMediaRouteTruth",
    "DedicatedMediaDownlinkSourceFailure",
    "DedicatedMediaSocket",
    "DedicatedMediaSocketLeafResult",
    "InactiveDedicatedMediaRoute",
    "create_dedicated_media_route",
    "run_dedicated_media_socket_leaf",
    "run_dedicated_media_downlink_socket_leaf",
]
