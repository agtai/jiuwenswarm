# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Package-local proof seam for a dedicated same-origin media route.

This module is deliberately not a registered WebSocket handler.  It accepts an
already server-authored :class:`MediaAuthorityBinding`, enforces a same-origin
request context, and exposes only typed attach/detach controls plus closed LVM1
binary input.  It has no JSON logger, persistence callback, socket, task, or
retry surface.

An active object proves only the package contract.  Product route truth remains
``unavailable`` until the Integration Owner registers the real handler and an
actual route-to-disk regression proves zero raw-audio persistence.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, TypeAlias
from urllib.parse import urlsplit

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MEDIA_CONTRACT_VERSION,
    MediaAck,
    MediaAttach,
    MediaAudioFrame,
    MediaAuthorityBinding,
    MediaCloseResult,
    MediaDetach,
    MediaDetachReason,
    MediaDirection,
    MediaTransportViolation,
    StrictMediaReceiver,
)


DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION = "live-voice.media.dedicated-route.v1"
MEDIA_ROUTE_REGISTRATION_UNAVAILABLE = "MEDIA_ROUTE_REGISTRATION_UNAVAILABLE"
MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN = "MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN"

_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_ROUTE_CONSTRUCTION_TOKEN = object()


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


__all__ = [
    "DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION",
    "MEDIA_CONTRACT_VERSION",
    "MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN",
    "MEDIA_ROUTE_REGISTRATION_UNAVAILABLE",
    "ActiveDedicatedMediaRoute",
    "DedicatedMediaRouteActivation",
    "DedicatedMediaRouteEvidence",
    "DedicatedMediaRouteRequest",
    "DedicatedMediaRouteReason",
    "DedicatedMediaRouteSnapshot",
    "DedicatedMediaRouteTruth",
    "InactiveDedicatedMediaRoute",
    "create_dedicated_media_route",
]
