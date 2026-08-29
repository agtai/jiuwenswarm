# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import builtins
import json
import logging
import math
import struct
from collections.abc import Generator
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any, Generic, TypeVar

import pytest

import jiuwenswarm.gateway.live_voice.dedicated_media_route as route_module
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MEDIA_CONTRACT_VERSION,
    MediaAck,
    MediaAttach,
    MediaAudioFrame,
    MediaAuthorityBinding,
    MediaDetach,
    MediaDetachReason,
    MediaDirection,
    MediaEndOfTurn,
    MediaFrameFormat,
    MediaGenerationBinding,
    MediaGenerationKind,
    MediaSpeechStart,
    MediaPlayoutBinding,
    MediaPlaybackStopOutcome,
    MediaPlaybackStopReceipt,
    MediaTransportViolation,
    create_playback_stop_receipt,
    decode_audio_frame,
    deserialize_media_control,
    encode_audio_frame,
    serialize_media_control,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION,
    MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN,
    MEDIA_ROUTE_REGISTRATION_UNAVAILABLE,
    ActiveDedicatedMediaRoute,
    DedicatedMediaLeafCleanupOwner,
    DedicatedMediaDownlinkSourceFailure,
    DedicatedMediaRouteEvidence,
    DedicatedMediaRouteReason,
    DedicatedMediaRouteRequest,
    DedicatedMediaRouteTruth,
    InactiveDedicatedMediaRoute,
    create_dedicated_media_route,
    run_dedicated_media_downlink_socket_leaf,
    run_dedicated_media_socket_leaf,
)


class _FakeDedicatedSocket:
    def __init__(self, incoming: list[object], *, fail_send_at: int | None = None):
        self.incoming = list(incoming)
        self.sent: list[str | bytes] = []
        self.close_calls: list[tuple[int, str]] = []
        self.fail_send_at = fail_send_at

    async def recv(self) -> str | bytes:
        if not self.incoming:
            raise ConnectionError("peer transport closed")
        value = self.incoming.pop(0)
        if isinstance(value, Exception):
            raise value
        return value  # type: ignore[return-value]

    async def send(self, message: str | bytes) -> None:
        if self.fail_send_at is not None and len(self.sent) == self.fail_send_at:
            raise ConnectionError("private send failure")
        self.sent.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append((code, reason))


class _BlockingDedicatedSocket(_FakeDedicatedSocket):
    def __init__(self) -> None:
        super().__init__([])
        self.receiving = asyncio.Event()

    async def recv(self) -> str | bytes:
        self.receiving.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class _CancellationObservedSocket(_BlockingDedicatedSocket):
    def __init__(self) -> None:
        super().__init__()
        self.receive_cancelled = asyncio.Event()

    async def recv(self) -> str | bytes:
        try:
            return await super().recv()
        except asyncio.CancelledError:
            self.receive_cancelled.set()
            raise


class _BlockingCloseDedicatedSocket(_FakeDedicatedSocket):
    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append((code, reason))
        await asyncio.Event().wait()


class _CustomEndOfTurnAwaitable:
    def __init__(self, future: asyncio.Future[MediaEndOfTurn]) -> None:
        self.future = future

    def __await__(self) -> Generator[Any, None, MediaEndOfTurn]:
        return self.future.__await__()


_HostileT = TypeVar("_HostileT")


class _CancellationHostileAwaitable(Generic[_HostileT]):
    def __init__(
        self, value: _HostileT, *, late_failure: BaseException | None = None
    ) -> None:
        self.value = value
        self.late_failure = late_failure
        self.started = asyncio.Event()
        self.cancel_observed = asyncio.Event()
        self.release = asyncio.Event()

    async def _wait(self) -> _HostileT:
        self.started.set()
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancel_observed.set()
        if self.late_failure is not None:
            raise self.late_failure
        return self.value

    def __await__(self) -> Generator[Any, None, _HostileT]:
        return self._wait().__await__()


def _binding(
    *,
    lease_id: str = "lease-dedicated-01",
    generation_value: int = 7,
    connection_epoch: int = 3,
) -> MediaAuthorityBinding:
    return MediaAuthorityBinding(
        lease_id=lease_id,
        authority_evidence_id="authority-evidence-dedicated-01",
        connection_id="connection-dedicated-01",
        connection_epoch=connection_epoch,
        session_id="session-dedicated-01",
        media_session_id="media-session-dedicated-01",
        interaction_id="interaction-dedicated-01",
        track_id="capture-track-dedicated-01",
        correlation_id="correlation-dedicated-01",
        direction=MediaDirection.UPLINK,
        generation=MediaGenerationBinding(
            MediaGenerationKind.CAPTURE,
            "capture-dedicated-01",
            generation_value,
        ),
        frame_format=MediaFrameFormat(sample_rate_hz=8_000, samples_per_channel=160),
    )


def _frame(seq: int = 0, cursor: int = 0) -> MediaAudioFrame:
    return MediaAudioFrame(
        seq=seq,
        sample_cursor=cursor,
        samples=tuple(math.sin(index / 11) * 0.25 for index in range(160)),
    )


def _request(
    binding: MediaAuthorityBinding | None,
    *,
    enabled: bool = True,
    expected_origin: str | None = "https://voice.example.test",
    request_origin: str | None = "https://voice.example.test:443/",
    provider_available: bool = True,
    binary_transport_available: bool = True,
) -> DedicatedMediaRouteRequest:
    return DedicatedMediaRouteRequest(
        enabled=enabled,
        expected_origin=expected_origin,
        request_origin=request_origin,
        binding=binding,
        provider_available=provider_available,
        binary_transport_available=binary_transport_available,
    )


def _active(
    binding: MediaAuthorityBinding | None = None,
    *,
    effects: dict[str, int] | None = None,
) -> ActiveDedicatedMediaRoute:
    counters = effects if effects is not None else {"audio": 0}

    def consume(_frame: MediaAudioFrame) -> None:
        counters["audio"] = counters.get("audio", 0) + 1

    activation = create_dedicated_media_route(
        _request(binding or _binding()), on_audio_frame=consume
    )
    assert isinstance(activation, ActiveDedicatedMediaRoute)
    return activation


def _assert_zero_forbidden(effects: dict[str, int]) -> None:
    assert effects == {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }


def test_exact_attach_lvm1_ack_and_detach_round_trip_is_package_only() -> None:
    effects = {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }
    binding = _binding()
    activation = _active(binding, effects=effects)

    assert activation.session.accept_server_attach(MediaAttach(binding)) is None
    ack = activation.session.accept_binary(encode_audio_frame(binding, _frame()))
    assert ack == MediaAck(binding.lease_id, binding.generation.value, 0)
    assert effects["audio"] == 1
    assert all(effects[name] == 0 for name in effects if name != "audio")

    closed = activation.session.accept_detach(
        MediaDetach(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            reason_id=MediaDetachReason.PEER_CLOSE,
            through_seq=0,
        )
    )
    late = activation.session.accept_binary(encode_audio_frame(binding, _frame(1, 160)))
    repeated = activation.session.close()

    assert closed.was_active is True
    assert closed.reason_id is MediaDetachReason.PEER_CLOSE
    assert late is closed.detach
    assert repeated.was_active is False
    assert repeated.detach is closed.detach
    snapshot = activation.session.snapshot()
    assert snapshot.closed is True
    assert snapshot.attached is False
    assert snapshot.accepted_frames == 1
    assert snapshot.last_accepted_seq == 0
    assert snapshot.retained_detach is closed.detach
    assert snapshot.package_json_logger_hook_present is False
    assert snapshot.package_raw_audio_persistence_hook_present is False
    assert snapshot.consumer_privacy_verified is False

    evidence = activation.evidence
    assert evidence.route_truth == "unavailable"
    assert evidence.reason_id == MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN
    assert evidence.route_contract_version == DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION
    assert evidence.media_contract_version == MEDIA_CONTRACT_VERSION
    assert evidence.evidence_scope == "contract_only"
    assert evidence.same_origin_required is True
    assert evidence.binary_only is True
    assert evidence.formal_route_ready is False
    assert evidence.real_transport_observed is False
    assert evidence.io_registration_observed is False
    assert evidence.route_to_disk_zero_persistence_observed is False
    assert evidence.package_json_logger_hook_present is False
    assert evidence.package_raw_audio_persistence_hook_present is False
    assert evidence.consumer_privacy_verified is False
    assert evidence.blocking_reason_ids == (
        MEDIA_ROUTE_REGISTRATION_UNAVAILABLE,
        MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN,
    )


def test_feature_off_returns_before_other_fields_consumer_or_route_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effects = {"consumer": 0, "allocation": 0}

    def forbidden_allocation(*_args: object, **_kwargs: object) -> None:
        effects["allocation"] += 1
        raise AssertionError("route must not allocate while disabled")

    monkeypatch.setattr(
        "jiuwenswarm.gateway.live_voice.dedicated_media_route._DedicatedMediaRouteSession",
        # The private session is factory-only; patching it proves feature-off
        # returns before the only package allocation point.
        forbidden_allocation,
    )

    def consumer(_frame: MediaAudioFrame) -> None:
        effects["consumer"] += 1

    activation = create_dedicated_media_route(
        DedicatedMediaRouteRequest(
            enabled=False,
            expected_origin=None,
            request_origin=object(),  # type: ignore[arg-type]
            binding=object(),  # type: ignore[arg-type]
            provider_available=True,
            binary_transport_available=True,
        ),
        on_audio_frame=consumer,
    )

    assert isinstance(activation, InactiveDedicatedMediaRoute)
    assert activation.reason_id == "MEDIA_FEATURE_DISABLED"
    assert activation.reason_id is DedicatedMediaRouteReason.FEATURE_DISABLED
    assert activation.evidence.route_truth == "disabled"
    assert activation.evidence.route_truth is DedicatedMediaRouteTruth.DISABLED
    assert activation.evidence.formal_route_ready is False
    assert effects == {"consumer": 0, "allocation": 0}
    assert not hasattr(activation, "session")


def test_package_evidence_cannot_be_forged_as_formal() -> None:
    with pytest.raises(MediaTransportViolation) as invalid:
        DedicatedMediaRouteEvidence(  # type: ignore[arg-type]
            route_truth="formal",  # type: ignore[arg-type]
            reason_id="FORMAL_ROUTE_OBSERVED",  # type: ignore[arg-type]
        )
    assert getattr(invalid.value, "reason_id", None) == "MEDIA_INVALID_ROUTE_EVIDENCE"

    with pytest.raises(MediaTransportViolation) as unknown_reason:
        DedicatedMediaRouteEvidence(  # type: ignore[arg-type]
            route_truth=DedicatedMediaRouteTruth.UNAVAILABLE,
            reason_id="PRIVATE_OR_UNKNOWN_REASON",  # type: ignore[arg-type]
        )
    assert unknown_reason.value.reason_id == "MEDIA_INVALID_ROUTE_EVIDENCE"

    valid_evidence = DedicatedMediaRouteEvidence(
        route_truth=DedicatedMediaRouteTruth.UNAVAILABLE,
        reason_id=DedicatedMediaRouteReason.ORIGIN_REJECTED,
    )
    with pytest.raises(MediaTransportViolation) as inactive_reason:
        InactiveDedicatedMediaRoute(  # type: ignore[arg-type]
            active=False,
            reason_id="FORMAL_ROUTE_OBSERVED",  # type: ignore[arg-type]
            evidence=valid_evidence,
        )
    assert inactive_reason.value.reason_id == "MEDIA_INVALID_ROUTE_EVIDENCE"


def test_feature_disabled_reason_and_disabled_truth_are_bijective() -> None:
    with pytest.raises(MediaTransportViolation) as unavailable_feature_off:
        DedicatedMediaRouteEvidence(
            route_truth=DedicatedMediaRouteTruth.UNAVAILABLE,
            reason_id=DedicatedMediaRouteReason.FEATURE_DISABLED,
        )
    with pytest.raises(MediaTransportViolation) as disabled_runtime_reason:
        DedicatedMediaRouteEvidence(
            route_truth=DedicatedMediaRouteTruth.DISABLED,
            reason_id=DedicatedMediaRouteReason.ORIGIN_REJECTED,
        )

    assert (
        unavailable_feature_off.value.reason_id
        == disabled_runtime_reason.value.reason_id
        == "MEDIA_INVALID_ROUTE_EVIDENCE"
    )


def test_inactive_constructor_requires_exact_compatible_package_evidence() -> None:
    class _FakeFormalEvidence:
        reason_id = DedicatedMediaRouteReason.ORIGIN_REJECTED
        route_truth = "formal"
        formal_route_ready = True
        consumer_privacy_verified = True

    with pytest.raises(MediaTransportViolation) as fake_evidence:
        InactiveDedicatedMediaRoute(  # type: ignore[arg-type]
            active=False,
            reason_id=DedicatedMediaRouteReason.ORIGIN_REJECTED,
            evidence=_FakeFormalEvidence(),  # type: ignore[arg-type]
        )

    incompatible = DedicatedMediaRouteEvidence(
        route_truth=DedicatedMediaRouteTruth.UNAVAILABLE,
        reason_id=DedicatedMediaRouteReason.ORIGIN_REJECTED,
    )
    object.__setattr__(incompatible, "route_truth", DedicatedMediaRouteTruth.DISABLED)
    with pytest.raises(MediaTransportViolation) as incompatible_truth:
        InactiveDedicatedMediaRoute(
            active=False,
            reason_id=DedicatedMediaRouteReason.ORIGIN_REJECTED,
            evidence=incompatible,
        )

    assert (
        fake_evidence.value.reason_id
        == incompatible_truth.value.reason_id
        == "MEDIA_INVALID_ROUTE_EVIDENCE"
    )

    corrupted_proof = DedicatedMediaRouteEvidence(
        route_truth=DedicatedMediaRouteTruth.UNAVAILABLE,
        reason_id=DedicatedMediaRouteReason.ORIGIN_REJECTED,
    )
    for field_name in (
        "formal_route_ready",
        "real_transport_observed",
        "io_registration_observed",
        "route_to_disk_zero_persistence_observed",
        "package_json_logger_hook_present",
        "package_raw_audio_persistence_hook_present",
        "consumer_privacy_verified",
    ):
        object.__setattr__(corrupted_proof, field_name, True)
    with pytest.raises(MediaTransportViolation) as corrupted_inactive:
        InactiveDedicatedMediaRoute(
            active=False,
            reason_id=DedicatedMediaRouteReason.ORIGIN_REJECTED,
            evidence=corrupted_proof,
        )
    assert corrupted_inactive.value.reason_id == "MEDIA_INVALID_ROUTE_EVIDENCE"


def test_active_constructor_rejects_false_fake_session_and_false_evidence() -> None:
    valid = _active()
    disabled_evidence = DedicatedMediaRouteEvidence(
        route_truth=DedicatedMediaRouteTruth.DISABLED,
        reason_id=DedicatedMediaRouteReason.FEATURE_DISABLED,
    )
    wrong_unavailable_evidence = DedicatedMediaRouteEvidence(
        route_truth=DedicatedMediaRouteTruth.UNAVAILABLE,
        reason_id=DedicatedMediaRouteReason.ORIGIN_REJECTED,
    )
    corrupted_active_evidence = valid.evidence
    for field_name in (
        "formal_route_ready",
        "real_transport_observed",
        "io_registration_observed",
        "route_to_disk_zero_persistence_observed",
        "package_json_logger_hook_present",
        "package_raw_audio_persistence_hook_present",
        "consumer_privacy_verified",
    ):
        object.__setattr__(corrupted_active_evidence, field_name, True)

    invalid_inputs = (
        (False, valid.session, valid.evidence),
        (True, object(), valid.evidence),
        (True, valid.session, disabled_evidence),
        (True, valid.session, wrong_unavailable_evidence),
        (True, valid.session, corrupted_active_evidence),
    )
    for active, session, evidence in invalid_inputs:
        with pytest.raises(MediaTransportViolation) as invalid:
            ActiveDedicatedMediaRoute(  # type: ignore[arg-type]
                active=active,
                session=session,  # type: ignore[arg-type]
                evidence=evidence,
            )
        assert invalid.value.reason_id == "MEDIA_INVALID_ROUTE_EVIDENCE"


def test_session_construction_cannot_bypass_same_origin_factory() -> None:
    with pytest.raises(MediaTransportViolation) as bypass:
        route_module._DedicatedMediaRouteSession(  # noqa: SLF001
            _binding(),
            on_audio_frame=lambda _frame: None,
            construction_token=object(),
        )
    assert bypass.value.reason_id == "MEDIA_ROUTE_FACTORY_REQUIRED"


@pytest.mark.parametrize(
    ("request_changes", "reason_id"),
    [
        ({"request_origin": "https://other.example.test"}, "MEDIA_ORIGIN_REJECTED"),
        ({"request_origin": "null"}, "MEDIA_ORIGIN_REJECTED"),
        (
            {"request_origin": "https://voice.example.test/path"},
            "MEDIA_ORIGIN_REJECTED",
        ),
        (
            {"request_origin": "https://user@voice.example.test"},
            "MEDIA_ORIGIN_REJECTED",
        ),
        ({"request_origin": "https://voice.example.test:0"}, "MEDIA_ORIGIN_REJECTED"),
        ({"request_origin": "https://voice.example.test?"}, "MEDIA_ORIGIN_REJECTED"),
        ({"binding": None}, "MEDIA_AUTHORITY_UNAVAILABLE"),
        (
            {
                "binding": replace(
                    _binding(),
                    direction=MediaDirection.DOWNLINK,
                    generation=MediaGenerationBinding(
                        MediaGenerationKind.RESPONSE, "response-dedicated-01", 7
                    ),
                    playout=MediaPlayoutBinding(
                        "response-dedicated-01", 7, "unit-dedicated-01"
                    ),
                )
            },
            "MEDIA_DIRECTION_UNAVAILABLE",
        ),
        ({"provider_available": False}, "MEDIA_PROVIDER_UNAVAILABLE"),
        ({"binary_transport_available": False}, "MEDIA_TRANSPORT_UNAVAILABLE"),
    ],
)
def test_inactive_gates_have_zero_downstream_or_route_effects(
    request_changes: dict[str, object], reason_id: str
) -> None:
    effects = {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }
    request = replace(
        _request(_binding()),
        **request_changes,  # type: ignore[arg-type]
    )

    activation = create_dedicated_media_route(
        request,
        on_audio_frame=lambda _frame: effects.__setitem__("audio", 1),
    )

    assert isinstance(activation, InactiveDedicatedMediaRoute)
    assert activation.reason_id == reason_id
    assert activation.evidence.route_truth == "unavailable"
    assert activation.evidence.formal_route_ready is False
    assert not hasattr(activation, "session")
    _assert_zero_forbidden(effects)


@pytest.mark.parametrize(
    "different_binding",
    [
        lambda binding: replace(binding),
        lambda binding: replace(binding, connection_epoch=binding.connection_epoch + 1),
        lambda binding: replace(binding, lease_id="different-lease"),
        lambda binding: replace(
            binding,
            generation=replace(binding.generation, value=binding.generation.value + 1),
        ),
    ],
)
def test_only_exact_server_owned_typed_attach_is_accepted(
    different_binding,
) -> None:
    effects = {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }
    binding = _binding()
    activation = _active(binding, effects=effects)
    client_reconstructed = different_binding(binding)

    detach = activation.session.accept_server_attach(MediaAttach(client_reconstructed))
    late = activation.session.accept_binary(encode_audio_frame(binding, _frame()))

    assert detach is not None
    assert detach.reason_id is MediaDetachReason.BINDING_MISMATCH
    assert late is detach
    _assert_zero_forbidden(effects)


def test_untyped_attach_and_binary_before_attach_fail_closed() -> None:
    for operation in ("untyped", "binary_first"):
        effects = {
            "audio": 0,
            "agent": 0,
            "tool": 0,
            "task": 0,
            "history": 0,
            "logger": 0,
            "persistence": 0,
        }
        binding = _binding()
        activation = _active(binding, effects=effects)
        if operation == "untyped":
            detach = activation.session.accept_server_attach(  # type: ignore[arg-type]
                {"type": "media.attach", "binding": binding}
            )
            expected = MediaDetachReason.BINDING_MISMATCH
        else:
            detach = activation.session.accept_binary(
                encode_audio_frame(binding, _frame())
            )
            expected = MediaDetachReason.NOT_ATTACHED
        assert isinstance(detach, MediaDetach)
        assert detach.reason_id is expected
        _assert_zero_forbidden(effects)


@pytest.mark.parametrize(
    ("mutate", "reason_id"),
    [
        (
            lambda binding, raw: encode_audio_frame(
                replace(binding, lease_id="wrong-lease"), _frame()
            ),
            MediaDetachReason.BINDING_MISMATCH,
        ),
        (
            lambda binding, raw: encode_audio_frame(
                replace(
                    binding,
                    generation=replace(
                        binding.generation, value=binding.generation.value + 1
                    ),
                ),
                _frame(),
            ),
            MediaDetachReason.STALE_GENERATION,
        ),
        (lambda _binding, _raw: b"LVM1", MediaDetachReason.MALFORMED_FRAME),
        (
            lambda _binding, raw: _change_payload_length(raw, 4),
            MediaDetachReason.INVALID_FRAME,
        ),
        (
            lambda binding, _raw: encode_audio_frame(binding, _frame(1, 160)),
            MediaDetachReason.SEQUENCE_GAP,
        ),
    ],
)
def test_lease_generation_format_and_sequence_fences_precede_audio_callback(
    mutate, reason_id: MediaDetachReason
) -> None:
    effects = {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }
    binding = _binding()
    activation = _active(binding, effects=effects)
    assert activation.session.accept_server_attach(MediaAttach(binding)) is None
    raw = encode_audio_frame(binding, _frame())

    detach = activation.session.accept_binary(mutate(binding, raw))
    late = activation.session.accept_binary(raw)

    assert isinstance(detach, MediaDetach)
    assert detach.reason_id is reason_id
    assert late is detach
    _assert_zero_forbidden(effects)


def _change_payload_length(raw: bytes, payload_length: int) -> bytes:
    changed = bytearray(raw)
    struct.pack_into("<I", changed, 32, payload_length)
    return bytes(changed)


def test_duplicate_frame_detaches_after_one_effect_and_retains_cleanup() -> None:
    effects = {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }
    binding = _binding()
    activation = _active(binding, effects=effects)
    raw = encode_audio_frame(binding, _frame())
    assert activation.session.accept_server_attach(MediaAttach(binding)) is None
    assert isinstance(activation.session.accept_binary(raw), MediaAck)

    detach = activation.session.accept_binary(raw)
    repeated = activation.session.close(MediaDetachReason.LOCAL_CLOSE)

    assert isinstance(detach, MediaDetach)
    assert detach.reason_id is MediaDetachReason.DUPLICATE_OR_OUT_OF_ORDER
    assert repeated.detach is detach
    assert effects["audio"] == 1
    assert all(effects[name] == 0 for name in effects if name != "audio")


def test_wrong_detach_binding_is_retained_without_business_side_effects() -> None:
    effects = {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }
    binding = _binding()
    activation = _active(binding, effects=effects)
    assert activation.session.accept_server_attach(MediaAttach(binding)) is None

    closed = activation.session.accept_detach(
        MediaDetach(
            lease_id="wrong-lease",
            generation=binding.generation.value,
            reason_id=MediaDetachReason.PEER_CLOSE,
        )
    )
    replay = activation.session.accept_detach(
        MediaDetach(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
        )
    )

    assert closed.reason_id is MediaDetachReason.BINDING_MISMATCH
    assert replay.detach is closed.detach
    assert closed.business_cancel_count_delta == 0
    _assert_zero_forbidden(effects)


def test_binary_path_never_calls_json_logger_or_file_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effects = {"audio": 0, "forbidden": 0}
    binding = _binding()
    activation = _active(binding, effects=effects)
    raw = encode_audio_frame(binding, _frame())

    def forbidden(*_args: object, **_kwargs: object) -> None:
        effects["forbidden"] += 1
        raise AssertionError("binary media must not enter logging or persistence")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(json, "dumps", forbidden)
    monkeypatch.setattr(logging.Logger, "_log", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)

    assert activation.session.accept_server_attach(MediaAttach(binding)) is None
    ack = activation.session.accept_binary(raw)
    closed = activation.session.close()

    assert isinstance(ack, MediaAck)
    assert closed.reason_id is MediaDetachReason.LOCAL_CLOSE
    assert effects == {"audio": 1, "forbidden": 0}


def test_injected_consumer_privacy_is_explicitly_unverified() -> None:
    effects = {"consumer_persistence": 0}
    binding = _binding()
    activation = create_dedicated_media_route(
        _request(binding),
        on_audio_frame=lambda _frame: effects.__setitem__(
            "consumer_persistence", effects["consumer_persistence"] + 1
        ),
    )
    assert isinstance(activation, ActiveDedicatedMediaRoute)
    assert activation.session.accept_server_attach(MediaAttach(binding)) is None

    assert isinstance(
        activation.session.accept_binary(encode_audio_frame(binding, _frame())),
        MediaAck,
    )
    assert effects["consumer_persistence"] == 1
    assert activation.evidence.consumer_privacy_verified is False
    assert activation.evidence.route_to_disk_zero_persistence_observed is False


def test_origin_canonicalization_is_exact_and_conservative() -> None:
    binding = _binding()
    accepted = create_dedicated_media_route(
        _request(
            binding,
            expected_origin="http://127.0.0.1",
            request_origin="http://127.0.0.1:80/",
        ),
        on_audio_frame=lambda _frame: None,
    )
    wrong_port = create_dedicated_media_route(
        _request(
            binding,
            expected_origin="https://voice.example.test",
            request_origin="https://voice.example.test:444",
        ),
        on_audio_frame=lambda _frame: None,
    )

    assert isinstance(accepted, ActiveDedicatedMediaRoute)
    assert isinstance(wrong_port, InactiveDedicatedMediaRoute)
    assert wrong_port.reason_id == "MEDIA_ORIGIN_REJECTED"
    assert MEDIA_CONTRACT_VERSION == "live-voice.media.v1"
    assert (
        DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION == "live-voice.media.dedicated-route.v1"
    )


def _downlink_binding() -> MediaAuthorityBinding:
    return replace(
        _binding(),
        direction=MediaDirection.DOWNLINK,
        track_id="playout-track-dedicated-01",
        generation=MediaGenerationBinding(
            MediaGenerationKind.RESPONSE,
            "response-dedicated-01",
            7,
        ),
        playout=MediaPlayoutBinding(
            "response-dedicated-01",
            7,
            "unit-dedicated-01",
        ),
    )


@pytest.mark.asyncio
async def test_injected_socket_leaf_sends_server_attach_ack_and_closes_on_typed_detach() -> (
    None
):
    effects = {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }
    binding = _binding()
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
        through_seq=0,
    )
    socket = _FakeDedicatedSocket(
        [
            encode_audio_frame(binding, _frame()),
            serialize_media_control(peer_detach),
        ]
    )
    sent_acknowledgements: list[MediaAck] = []

    result = await run_dedicated_media_socket_leaf(
        _request(binding),
        socket=socket,
        on_audio_frame=lambda _frame: effects.__setitem__(
            "audio", effects["audio"] + 1
        ),
        on_uplink_ack_sent=sent_acknowledgements.append,
    )

    controls = [deserialize_media_control(item) for item in socket.sent]
    assert controls == [
        MediaAttach(binding),
        MediaAck(binding.lease_id, binding.generation.value, 0),
    ]
    assert result.activated is True
    assert result.socket_touched is True
    assert result.attach_sent is True
    assert result.accepted_frames == 1
    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert result.close_result is not None
    assert result.close_result.business_cancel_count_delta == 0
    assert result.business_cancel_count_delta == 0
    assert result.registered_route_observed is False
    assert result.route_to_disk_zero_persistence_observed is False
    assert result.formal_route_ready is False
    assert socket.close_calls == [(1000, "live-voice media leaf closed")]
    assert effects["audio"] == 1
    assert sent_acknowledgements == [
        MediaAck(binding.lease_id, binding.generation.value, 0)
    ]
    assert all(effects[name] == 0 for name in effects if name != "audio")


@pytest.mark.asyncio
async def test_uplink_ack_observer_runs_only_after_successful_socket_send() -> None:
    binding = _binding()
    socket = _FakeDedicatedSocket(
        [encode_audio_frame(binding, _frame())],
        fail_send_at=1,
    )
    sent_acknowledgements: list[MediaAck] = []

    result = await run_dedicated_media_socket_leaf(
        _request(binding),
        socket=socket,
        on_audio_frame=lambda _frame: None,
        on_uplink_ack_sent=sent_acknowledgements.append,
    )

    assert result.reason_id is MediaDetachReason.TRANSPORT_SEND_FAILED
    assert sent_acknowledgements == []


@pytest.mark.asyncio
async def test_socket_leaf_single_sender_orders_ack_before_eot_then_peer_detach() -> (
    None
):
    binding = _binding()
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
        through_seq=0,
    )

    class _EotSocket(_FakeDedicatedSocket):
        def __init__(self) -> None:
            super().__init__([])
            self.recv_count = 0
            self.waiting_after_audio = asyncio.Event()
            self.release_detach = asyncio.Event()

        async def recv(self) -> str | bytes:
            self.recv_count += 1
            if self.recv_count == 1:
                return encode_audio_frame(binding, _frame())
            self.waiting_after_audio.set()
            await self.release_detach.wait()
            return serialize_media_control(peer_detach)

    socket = _EotSocket()

    async def next_speech_start() -> MediaSpeechStart:
        await socket.waiting_after_audio.wait()
        return MediaSpeechStart(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
        )

    async def next_end_of_turn() -> MediaEndOfTurn:
        await socket.waiting_after_audio.wait()
        return MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        )

    route_task = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_speech_start=next_speech_start,
            next_end_of_turn=next_end_of_turn,
            cleanup_owner=DedicatedMediaLeafCleanupOwner(),
        )
    )
    for _ in range(40):
        if len(socket.sent) == 4:
            break
        await asyncio.sleep(0)
    controls = [deserialize_media_control(item) for item in socket.sent]
    assert [type(control) for control in controls] == [
        MediaAttach,
        MediaAck,
        MediaSpeechStart,
        MediaEndOfTurn,
    ]
    socket.release_detach.set()
    result = await asyncio.wait_for(route_task, timeout=1)
    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert result.business_cancel_count_delta == 0


@pytest.mark.asyncio
async def test_socket_leaf_rearms_native_speech_start_without_eot() -> None:
    binding = _binding()
    release_audio = asyncio.Event()
    release_detach = asyncio.Event()

    class _ContinuousSocket(_FakeDedicatedSocket):
        def __init__(self) -> None:
            super().__init__([])
            self.recv_count = 0

        async def recv(self) -> str | bytes:
            self.recv_count += 1
            if self.recv_count == 1:
                await release_audio.wait()
                return encode_audio_frame(binding, _frame())
            await release_detach.wait()
            return serialize_media_control(
                MediaDetach(
                    lease_id=binding.lease_id,
                    generation=binding.generation.value,
                    reason_id=MediaDetachReason.PEER_CLOSE,
                )
            )

    socket = _ContinuousSocket()
    starts = iter((100, 640))
    third_start = asyncio.Event()

    async def next_speech_start() -> MediaSpeechStart:
        try:
            provider_start_ms = next(starts)
        except StopIteration:
            await third_start.wait()
            raise AssertionError("unexpected third speech start")
        return MediaSpeechStart(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=provider_start_ms,
        )

    route = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_speech_start=next_speech_start,
            repeat_speech_start=True,
            cleanup_owner=DedicatedMediaLeafCleanupOwner(),
        )
    )
    for _ in range(40):
        controls = [deserialize_media_control(item) for item in socket.sent]
        if any(isinstance(item, MediaSpeechStart) for item in controls):
            break
        await asyncio.sleep(0)
    release_audio.set()
    for _ in range(40):
        controls = [deserialize_media_control(item) for item in socket.sent]
        if sum(isinstance(item, MediaSpeechStart) for item in controls) == 2:
            break
        await asyncio.sleep(0)
    release_detach.set()
    result = await asyncio.wait_for(route, timeout=1.0)

    controls = [deserialize_media_control(item) for item in socket.sent]
    assert [
        item.provider_start_ms
        for item in controls
        if isinstance(item, MediaSpeechStart)
    ] == [100, 640]
    assert result.reason_id is MediaDetachReason.PEER_CLOSE


@pytest.mark.asyncio
async def test_socket_leaf_rearms_exact_native_speech_boundary_pairs() -> None:
    binding = _binding()

    class _ContinuousSocket(_FakeDedicatedSocket):
        def __init__(self) -> None:
            super().__init__([])
            self.incoming_queue: asyncio.Queue[str | bytes] = asyncio.Queue()

        async def recv(self) -> str | bytes:
            return await self.incoming_queue.get()

    socket = _ContinuousSocket()
    starts = iter((100, 640))
    ends = iter(((100, 520), (640, 1_060)))
    third_start = asyncio.Event()
    third_end = asyncio.Event()

    async def next_speech_start() -> MediaSpeechStart:
        try:
            provider_start_ms = next(starts)
        except StopIteration:
            await third_start.wait()
            raise AssertionError("unexpected third speech start")
        return MediaSpeechStart(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=provider_start_ms,
        )

    async def next_end_of_turn() -> MediaEndOfTurn:
        try:
            provider_start_ms, provider_end_ms = next(ends)
        except StopIteration:
            await third_end.wait()
            raise AssertionError("unexpected third end of turn")
        return MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=provider_start_ms,
            provider_end_ms=provider_end_ms,
        )

    route = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_speech_start=next_speech_start,
            next_end_of_turn=next_end_of_turn,
            repeat_speech_boundaries=True,
            cleanup_owner=DedicatedMediaLeafCleanupOwner(),
        )
    )

    for expected_boundary_count in (2, 4):
        for _ in range(40):
            controls = [deserialize_media_control(item) for item in socket.sent]
            boundary_count = sum(
                isinstance(item, (MediaSpeechStart, MediaEndOfTurn))
                for item in controls
            )
            if boundary_count == expected_boundary_count:
                break
            await asyncio.sleep(0)
        assert boundary_count == expected_boundary_count
        if expected_boundary_count == 2:
            await socket.incoming_queue.put(encode_audio_frame(binding, _frame()))
        else:
            await socket.incoming_queue.put(
                serialize_media_control(
                    MediaDetach(
                        lease_id=binding.lease_id,
                        generation=binding.generation.value,
                        reason_id=MediaDetachReason.PEER_CLOSE,
                        through_seq=0,
                    )
                )
            )

    result = await asyncio.wait_for(route, timeout=1.0)
    controls = [deserialize_media_control(item) for item in socket.sent]
    boundaries = [
        item for item in controls if isinstance(item, (MediaSpeechStart, MediaEndOfTurn))
    ]
    assert [type(item) for item in boundaries] == [
        MediaSpeechStart,
        MediaEndOfTurn,
        MediaSpeechStart,
        MediaEndOfTurn,
    ]
    assert [item.provider_start_ms for item in boundaries] == [100, 100, 640, 640]
    assert [
        item.provider_end_ms
        for item in boundaries
        if isinstance(item, MediaEndOfTurn)
    ] == [520, 1_060]
    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert result.business_cancel_count_delta == 0


@pytest.mark.asyncio
async def test_same_ready_peer_detach_wins_and_suppresses_eot() -> None:
    binding = _binding()
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
    )
    socket = _FakeDedicatedSocket([serialize_media_control(peer_detach)])

    async def next_end_of_turn() -> MediaEndOfTurn:
        return MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        )

    result = await run_dedicated_media_socket_leaf(
        _request(binding),
        socket=socket,
        on_audio_frame=lambda _frame: None,
        next_end_of_turn=next_end_of_turn,
        cleanup_owner=DedicatedMediaLeafCleanupOwner(),
    )
    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    controls = [deserialize_media_control(item) for item in socket.sent]
    assert controls == [MediaAttach(binding)]


@pytest.mark.asyncio
async def test_socket_leaf_accepts_future_receive_and_end_of_turn_sources() -> None:
    binding = _binding()
    receive_future: asyncio.Future[str | bytes] = (
        asyncio.get_running_loop().create_future()
    )
    end_of_turn_future: asyncio.Future[MediaEndOfTurn] = (
        asyncio.get_running_loop().create_future()
    )

    class _FutureSocket:
        def __init__(self) -> None:
            self.sent: list[str | bytes] = []
            self.close_calls: list[tuple[int, str]] = []

        def recv(self) -> asyncio.Future[str | bytes]:
            return receive_future

        async def send(self, message: str | bytes) -> None:
            self.sent.append(message)

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.close_calls.append((code, reason))

    socket = _FutureSocket()
    route_task = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=lambda: end_of_turn_future,
            cleanup_owner=DedicatedMediaLeafCleanupOwner(),
        )
    )
    await asyncio.sleep(0)
    end_of_turn_future.set_result(
        MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        )
    )
    for _ in range(40):
        if len(socket.sent) == 2:
            break
        await asyncio.sleep(0)
    controls = [deserialize_media_control(item) for item in socket.sent]
    assert [type(control) for control in controls] == [MediaAttach, MediaEndOfTurn]

    receive_future.set_result(
        serialize_media_control(
            MediaDetach(
                lease_id=binding.lease_id,
                generation=binding.generation.value,
                reason_id=MediaDetachReason.PEER_CLOSE,
            )
        )
    )
    result = await asyncio.wait_for(route_task, timeout=1)
    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_peer_detach_cancels_custom_end_of_turn_awaitable() -> None:
    binding = _binding()
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
    )
    socket = _FakeDedicatedSocket([serialize_media_control(peer_detach)])
    source_future: asyncio.Future[MediaEndOfTurn] = (
        asyncio.get_running_loop().create_future()
    )
    source = _CustomEndOfTurnAwaitable(source_future)

    result = await run_dedicated_media_socket_leaf(
        _request(binding),
        socket=socket,
        on_audio_frame=lambda _frame: None,
        next_end_of_turn=lambda: source,
        cleanup_owner=DedicatedMediaLeafCleanupOwner(),
    )

    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert source_future.cancelled()
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_socket_close_cancels_custom_end_of_turn_awaitable() -> None:
    binding = _binding()
    socket = _BlockingDedicatedSocket()
    source_future: asyncio.Future[MediaEndOfTurn] = (
        asyncio.get_running_loop().create_future()
    )
    source = _CustomEndOfTurnAwaitable(source_future)
    route_task = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=lambda: source,
            cleanup_owner=DedicatedMediaLeafCleanupOwner(),
        )
    )
    await socket.receiving.wait()

    route_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await route_task

    assert source_future.cancelled()
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_end_of_turn_process_control_closes_and_cancels_receive_sibling() -> None:
    binding = _binding()
    socket = _CancellationObservedSocket()
    process_control = GeneratorExit("end-of-turn process control")

    async def next_end_of_turn() -> MediaEndOfTurn:
        await socket.receiving.wait()
        raise process_control

    route_task = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=next_end_of_turn,
            cleanup_owner=DedicatedMediaLeafCleanupOwner(),
        )
    )
    with pytest.raises(GeneratorExit) as raised:
        await route_task

    assert raised.value is process_control
    assert socket.receive_cancelled.is_set()
    assert len(socket.sent) == 1
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_receive_process_control_closes_and_cancels_end_of_turn_sibling() -> None:
    binding = _binding()
    end_of_turn_started = asyncio.Event()
    end_of_turn_future: asyncio.Future[MediaEndOfTurn] = (
        asyncio.get_running_loop().create_future()
    )
    process_control = GeneratorExit("receive process control")

    class _ProcessControlSocket(_FakeDedicatedSocket):
        async def recv(self) -> str | bytes:
            await end_of_turn_started.wait()
            raise process_control

    async def next_end_of_turn() -> MediaEndOfTurn:
        end_of_turn_started.set()
        return await end_of_turn_future

    socket = _ProcessControlSocket([])
    with pytest.raises(GeneratorExit) as raised:
        await run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=next_end_of_turn,
            cleanup_owner=DedicatedMediaLeafCleanupOwner(),
        )

    assert raised.value is process_control
    assert end_of_turn_future.cancelled()
    assert len(socket.sent) == 1
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_hostile_eot_is_retained_bounded_and_truthfully_converges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_SOCKET_CLOSE_TIMEOUT_SECONDS", 0.01)
    binding = _binding()
    owner = DedicatedMediaLeafCleanupOwner(capacity=2)
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
    )
    hostile = _CancellationHostileAwaitable(
        MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        ),
        late_failure=RuntimeError("content-free late EOT cleanup failure"),
    )

    class _DetachAfterEotStarts(_FakeDedicatedSocket):
        async def recv(self) -> str | bytes:
            await hostile.started.wait()
            return serialize_media_control(peer_detach)

    retained: list[object] = []
    result = await run_dedicated_media_socket_leaf(
        _request(binding),
        socket=_DetachAfterEotStarts([]),
        on_audio_frame=lambda _frame: None,
        on_complete=retained.append,
        next_end_of_turn=lambda: hostile,
        cleanup_owner=owner,
    )
    assert result.cleanup_complete is False
    assert result.cleanup_pending_tasks == 1
    assert retained == [result]
    assert hostile.cancel_observed.is_set()
    assert owner.snapshot.in_use == 1
    assert owner.snapshot.retained_tasks == 1
    assert owner.snapshot.cleanup_complete is False

    saturated_socket = _FakeDedicatedSocket([])
    with pytest.raises(MediaTransportViolation) as saturated:
        await run_dedicated_media_socket_leaf(
            _request(binding),
            socket=saturated_socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=lambda: hostile,
            cleanup_owner=owner,
        )
    assert saturated.value.reason_id == "MEDIA_CLEANUP_CAPACITY_EXCEEDED"
    assert saturated_socket.sent == []
    assert saturated_socket.close_calls == []

    assert await owner.retry_cleanup(timeout_seconds=0.01) is False
    hostile.release.set()
    assert await owner.retry_cleanup(timeout_seconds=1) is True
    assert await owner.close(timeout_seconds=1) is True
    assert owner.snapshot.closed is True
    assert owner.snapshot.cleanup_complete is True
    closed_socket = _FakeDedicatedSocket([])
    with pytest.raises(MediaTransportViolation) as closed:
        await run_dedicated_media_socket_leaf(
            _request(binding),
            socket=closed_socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=lambda: hostile,
            cleanup_owner=owner,
        )
    assert closed.value.reason_id == "MEDIA_CLEANUP_OWNER_CLOSED"
    assert closed_socket.sent == []
    assert closed_socket.close_calls == []


@pytest.mark.asyncio
async def test_speech_start_failure_keeps_hostile_eot_owned_until_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_SOCKET_CLOSE_TIMEOUT_SECONDS", 0.01)
    binding = _binding()
    owner = DedicatedMediaLeafCleanupOwner(capacity=3)
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
    )
    hostile_eot = _CancellationHostileAwaitable(
        MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        )
    )
    speech_start_failed = asyncio.Event()
    release_detach = asyncio.Event()

    async def next_speech_start() -> MediaSpeechStart:
        await hostile_eot.started.wait()
        speech_start_failed.set()
        raise RuntimeError("content-free speech-start source failure")

    class _DetachAfterSpeechStartFailure(_FakeDedicatedSocket):
        async def recv(self) -> str | bytes:
            await release_detach.wait()
            return serialize_media_control(peer_detach)

    socket = _DetachAfterSpeechStartFailure([])
    route_task = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_speech_start=next_speech_start,
            next_end_of_turn=lambda: hostile_eot,
            cleanup_owner=owner,
        )
    )
    await asyncio.wait_for(speech_start_failed.wait(), timeout=1)
    for _ in range(3):
        await asyncio.sleep(0)
    assert [type(deserialize_media_control(item)) for item in socket.sent] == [
        MediaAttach
    ]

    release_detach.set()
    result = await asyncio.wait_for(route_task, timeout=1)

    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert result.cleanup_complete is False
    assert result.cleanup_pending_tasks == 1
    assert hostile_eot.cancel_observed.is_set()
    assert owner.snapshot.retained_tasks == 1
    assert [type(deserialize_media_control(item)) for item in socket.sent] == [
        MediaAttach
    ]

    hostile_eot.release.set()
    assert await owner.retry_cleanup(timeout_seconds=1) is True
    assert owner.snapshot.cleanup_complete is True


@pytest.mark.asyncio
async def test_caller_cancellation_retains_hostile_eot_until_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_SOCKET_CLOSE_TIMEOUT_SECONDS", 0.01)
    binding = _binding()
    owner = DedicatedMediaLeafCleanupOwner(capacity=2)
    hostile_eot = _CancellationHostileAwaitable(
        MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        )
    )
    socket = _CancellationObservedSocket()
    route_task = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=lambda: hostile_eot,
            cleanup_owner=owner,
        )
    )
    await hostile_eot.started.wait()
    await socket.receiving.wait()

    route_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await route_task

    assert hostile_eot.cancel_observed.is_set()
    assert socket.receive_cancelled.is_set()
    assert len(socket.close_calls) == 1
    assert owner.snapshot.in_use == 1
    assert owner.snapshot.retained_tasks == 1
    assert owner.snapshot.cleanup_complete is False

    hostile_eot.release.set()
    assert await owner.retry_cleanup(timeout_seconds=1) is True
    assert owner.snapshot.cleanup_complete is True


@pytest.mark.asyncio
async def test_cancellation_during_hostile_settle_still_closes_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_SOCKET_CLOSE_TIMEOUT_SECONDS", 1)
    binding = _binding()
    owner = DedicatedMediaLeafCleanupOwner(capacity=2)
    hostile_eot = _CancellationHostileAwaitable(
        MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        )
    )
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
    )

    class _DetachAfterEotStarts(_FakeDedicatedSocket):
        async def recv(self) -> str | bytes:
            await hostile_eot.started.wait()
            return serialize_media_control(peer_detach)

    socket = _DetachAfterEotStarts([])
    route_task = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=lambda: hostile_eot,
            cleanup_owner=owner,
        )
    )
    await hostile_eot.cancel_observed.wait()

    route_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await route_task

    assert len(socket.close_calls) == 1
    assert owner.snapshot.in_use == 1
    assert owner.snapshot.retained_tasks == 1
    hostile_eot.release.set()
    assert await owner.retry_cleanup(timeout_seconds=1) is True


@pytest.mark.asyncio
async def test_post_eot_hostile_receive_remains_owned_until_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_SOCKET_CLOSE_TIMEOUT_SECONDS", 0.01)
    binding = _binding()
    owner = DedicatedMediaLeafCleanupOwner(capacity=2)
    hostile_receive = _CancellationHostileAwaitable[str | bytes](b"late")

    class _PostEotHostileSocket(_FakeDedicatedSocket):
        def __init__(self) -> None:
            super().__init__([])
            self.recv_count = 0
            self.eot_sent = asyncio.Event()

        async def send(self, message: str | bytes) -> None:
            await super().send(message)
            if len(self.sent) == 2:
                self.eot_sent.set()

        async def recv(self) -> str | bytes:
            self.recv_count += 1
            if self.recv_count == 1:
                await self.eot_sent.wait()
                return encode_audio_frame(binding, _frame())
            return await hostile_receive

    async def next_end_of_turn() -> MediaEndOfTurn:
        await asyncio.sleep(0)
        return MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        )

    socket = _PostEotHostileSocket()
    route_task = asyncio.create_task(
        run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=next_end_of_turn,
            cleanup_owner=owner,
        )
    )
    try:
        await asyncio.wait_for(socket.eot_sent.wait(), timeout=1)
        await asyncio.wait_for(hostile_receive.started.wait(), timeout=1)
        assert [type(deserialize_media_control(item)) for item in socket.sent] == [
            MediaAttach,
            MediaEndOfTurn,
            MediaAck,
        ]
    except BaseException:
        hostile_receive.release.set()
        route_task.cancel()
        with suppress(BaseException):
            await route_task
        raise

    route_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await route_task

    assert hostile_receive.cancel_observed.is_set()
    assert len(socket.close_calls) == 1
    assert owner.snapshot.retained_tasks == 1
    hostile_receive.release.set()
    assert await owner.retry_cleanup(timeout_seconds=1) is True


@pytest.mark.asyncio
async def test_eot_process_control_retains_hostile_receive_until_owner_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_SOCKET_CLOSE_TIMEOUT_SECONDS", 0.01)
    binding = _binding()
    owner = DedicatedMediaLeafCleanupOwner(capacity=2)
    hostile_receive = _CancellationHostileAwaitable[str | bytes](b"late")
    process_control = GeneratorExit("end-of-turn process control")

    class _HostileReceiveSocket(_FakeDedicatedSocket):
        def recv(  # type: ignore[override]
            self,
        ) -> _CancellationHostileAwaitable[str | bytes]:
            return hostile_receive

    async def next_end_of_turn() -> MediaEndOfTurn:
        await hostile_receive.started.wait()
        raise process_control

    socket = _HostileReceiveSocket([])
    with pytest.raises(GeneratorExit) as raised:
        await run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=next_end_of_turn,
            cleanup_owner=owner,
        )
    assert raised.value is process_control
    assert hostile_receive.cancel_observed.is_set()
    assert owner.snapshot.retained_tasks == 1
    assert len(socket.close_calls) == 1

    hostile_receive.release.set()
    assert await owner.close(timeout_seconds=1) is True
    assert owner.snapshot.cleanup_complete is True


@pytest.mark.asyncio
async def test_receive_process_control_retains_hostile_eot_until_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_SOCKET_CLOSE_TIMEOUT_SECONDS", 0.01)
    binding = _binding()
    owner = DedicatedMediaLeafCleanupOwner(capacity=2)
    hostile_eot = _CancellationHostileAwaitable(
        MediaEndOfTurn(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            provider_start_ms=100,
            provider_end_ms=700,
        )
    )
    process_control = GeneratorExit("receive process control")

    class _ProcessControlAfterEotSocket(_FakeDedicatedSocket):
        async def recv(self) -> str | bytes:
            await hostile_eot.started.wait()
            raise process_control

    socket = _ProcessControlAfterEotSocket([])
    with pytest.raises(GeneratorExit) as raised:
        await run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
            next_end_of_turn=lambda: hostile_eot,
            cleanup_owner=owner,
        )
    assert raised.value is process_control
    assert hostile_eot.cancel_observed.is_set()
    assert owner.snapshot.retained_tasks == 1
    assert len(socket.close_calls) == 1

    hostile_eot.release.set()
    assert await owner.retry_cleanup(timeout_seconds=1) is True
    assert owner.snapshot.cleanup_complete is True


@pytest.mark.asyncio
async def test_uplink_completion_is_retained_before_physical_close() -> None:
    binding = _binding()
    effects = {"completed": False}
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
        through_seq=0,
    )

    class _OrderedCloseSocket(_FakeDedicatedSocket):
        async def send(self, message: str | bytes) -> None:
            await super().send(message)
            if isinstance(message, str) and isinstance(
                deserialize_media_control(message), MediaDetach
            ):
                assert effects["completed"] is True

        async def close(self, code: int = 1000, reason: str = "") -> None:
            assert effects["completed"] is True
            await super().close(code, reason)

    socket = _OrderedCloseSocket(
        [
            encode_audio_frame(binding, _frame()),
            serialize_media_control(peer_detach),
        ]
    )

    result = await run_dedicated_media_socket_leaf(
        _request(binding),
        socket=socket,
        on_audio_frame=lambda _frame: None,
        on_complete=lambda _result: effects.__setitem__("completed", True),
    )

    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert effects == {"completed": True}
    completion_receipt = deserialize_media_control(socket.sent[-1])
    assert completion_receipt == peer_detach
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_uplink_completion_is_not_downgraded_when_receipt_send_fails() -> None:
    binding = _binding()
    effects = {"completed": False}
    peer_detach = MediaDetach(
        lease_id=binding.lease_id,
        generation=binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
        through_seq=0,
    )
    socket = _FakeDedicatedSocket(
        [
            encode_audio_frame(binding, _frame()),
            serialize_media_control(peer_detach),
        ],
        fail_send_at=2,
    )

    result = await run_dedicated_media_socket_leaf(
        _request(binding),
        socket=socket,
        on_audio_frame=lambda _frame: None,
        on_complete=lambda _result: effects.__setitem__("completed", True),
    )

    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert effects == {"completed": True}
    assert len(socket.sent) == 2
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_socket_leaf_flag_off_returns_before_socket_or_consumer_inspection() -> (
    None
):
    class _ForbiddenSocket:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"feature-off inspected socket.{name}")

    effects = {"consumer": 0, "eot": 0}
    result = await run_dedicated_media_socket_leaf(
        DedicatedMediaRouteRequest(
            enabled=False,
            expected_origin=None,
            request_origin=None,
            binding=None,
            provider_available=True,
            binary_transport_available=True,
        ),
        socket=_ForbiddenSocket(),  # type: ignore[arg-type]
        on_audio_frame=lambda _frame: effects.__setitem__("consumer", 1),
        next_end_of_turn=lambda: effects.__setitem__("eot", 1),  # type: ignore[arg-type,return-value]
    )

    assert result.activated is False
    assert result.socket_touched is False
    assert result.attach_sent is False
    assert result.accepted_frames == 0
    assert result.close_result is None
    assert result.reason_id is DedicatedMediaRouteReason.FEATURE_DISABLED
    assert effects == {"consumer": 0, "eot": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("incoming", "reason_id", "accepted_frames"),
    [
        (b"not-lvm1", MediaDetachReason.MALFORMED_FRAME, 0),
        (
            encode_audio_frame(
                _binding(generation_value=8),
                _frame(),
            ),
            MediaDetachReason.STALE_GENERATION,
            0,
        ),
        (
            serialize_media_control(
                MediaAck(_binding().lease_id, _binding().generation.value, 0)
            ),
            MediaDetachReason.TRANSPORT_PROTOCOL_ERROR,
            0,
        ),
    ],
)
async def test_socket_leaf_malformed_stale_and_wrong_control_fail_closed(
    incoming: str | bytes,
    reason_id: MediaDetachReason,
    accepted_frames: int,
) -> None:
    effects = {
        "audio": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "logger": 0,
        "persistence": 0,
    }
    socket = _FakeDedicatedSocket([incoming])

    result = await run_dedicated_media_socket_leaf(
        _request(_binding()),
        socket=socket,
        on_audio_frame=lambda _frame: effects.__setitem__("audio", 1),
    )

    assert result.reason_id is reason_id
    assert result.accepted_frames == accepted_frames
    assert isinstance(deserialize_media_control(socket.sent[-1]), MediaDetach)
    assert deserialize_media_control(socket.sent[-1]).reason_id is reason_id  # type: ignore[union-attr]
    _assert_zero_forbidden(effects)


@pytest.mark.asyncio
async def test_socket_leaf_send_failure_retains_local_fence_without_retry() -> None:
    socket = _FakeDedicatedSocket([], fail_send_at=0)

    result = await run_dedicated_media_socket_leaf(
        _request(_binding()),
        socket=socket,
        on_audio_frame=lambda _frame: None,
    )

    assert result.attach_sent is False
    assert result.reason_id is MediaDetachReason.TRANSPORT_SEND_FAILED
    assert socket.sent == []
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_downlink_socket_leaf_bounds_frames_waits_for_ack_and_accepts_exact_stop() -> (
    None
):
    binding = _downlink_binding()
    stop = create_playback_stop_receipt(
        binding,
        outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED,
        confirmed_through_seq=0,
    )
    socket = _FakeDedicatedSocket(
        [
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value, 0)
            ),
            serialize_media_control(stop),
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value, 1)
            ),
        ]
    )
    effects = {
        "playback_stop": 0,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "persistence": 0,
    }

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=[_frame(), _frame(1, 160)],
        on_playback_stop=lambda _receipt: effects.__setitem__(
            "playback_stop", effects["playback_stop"] + 1
        ),
        max_pending_frames=1,
        max_pending_bytes=2048,
    )

    assert deserialize_media_control(socket.sent[0]) == MediaAttach(binding)
    binaries = [item for item in socket.sent if isinstance(item, bytes)]
    assert len(binaries) == 2
    terminal = deserialize_media_control(socket.sent[-1])
    assert isinstance(terminal, MediaDetach)
    assert terminal.reason_id is MediaDetachReason.PEER_CLOSE
    assert terminal.business_cancel_count_delta == 0
    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert result.sent_frames == 2
    assert result.acknowledged_through_seq == 0
    assert result.playback_stop_receipts == 1
    assert result.business_cancel_count_delta == 0
    assert result.close_result is not None
    assert result.close_result.dropped_frames == 1
    assert effects == {
        "playback_stop": 1,
        "agent": 0,
        "tool": 0,
        "task": 0,
        "history": 0,
        "persistence": 0,
    }


@pytest.mark.asyncio
async def test_downlink_socket_leaf_awaits_playback_stop_authority_fence() -> None:
    binding = _downlink_binding()
    socket = _FakeDedicatedSocket(
        [
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value, 0)
            ),
            serialize_media_control(
                create_playback_stop_receipt(
                    binding,
                    outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED,
                    confirmed_through_seq=0,
                )
            ),
        ]
    )
    retained: list[MediaPlaybackStopReceipt] = []

    async def retain_stop(receipt: MediaPlaybackStopReceipt) -> None:
        await asyncio.sleep(0)
        retained.append(receipt)

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=[_frame(), _frame(1, 160)],
        on_playback_stop=retain_stop,
    )

    assert result.reason_id is MediaDetachReason.PEER_CLOSE
    assert len(retained) == 1
    assert retained[0].confirmed_through_seq == 0


@pytest.mark.asyncio
async def test_downlink_feature_off_does_not_iterate_frames_or_touch_socket() -> None:
    class _Forbidden:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"feature-off inspected {name}")

        def __iter__(self):
            raise AssertionError("feature-off iterated frames")

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(None, enabled=False),
        socket=_Forbidden(),  # type: ignore[arg-type]
        frames=_Forbidden(),  # type: ignore[arg-type]
        on_playback_stop=lambda _receipt: (_ for _ in ()).throw(
            AssertionError("feature-off invoked playback stop")
        ),
    )

    assert result.activated is False
    assert result.reason_id is DedicatedMediaRouteReason.FEATURE_DISABLED
    assert result.socket_touched is False
    assert result.sent_frames == 0
    assert result.playback_stop_receipts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("max_pending_frames", "max_pending_bytes"),
    [
        (257, 2048),
        (1.5, 2048),
        (True, 2048),
        ((1 << 53), 2048),
        (1, 8 * 1024 * 1024 + 1),
        (1, 1.5),
        (1, True),
        (1, 1 << 53),
    ],
)
async def test_downlink_public_limits_fail_before_socket_or_iterator_effects(
    max_pending_frames: object,
    max_pending_bytes: object,
) -> None:
    class _UnconsumedFrames:
        def __iter__(self):
            raise AssertionError("invalid limits must precede iterator consumption")

    socket = _FakeDedicatedSocket([])
    effects = {"playback_stop": 0}

    with pytest.raises(MediaTransportViolation) as invalid:
        await run_dedicated_media_downlink_socket_leaf(
            _request(_downlink_binding()),
            socket=socket,
            frames=_UnconsumedFrames(),
            on_playback_stop=lambda _receipt: effects.__setitem__("playback_stop", 1),
            max_pending_frames=max_pending_frames,  # type: ignore[arg-type]
            max_pending_bytes=max_pending_bytes,  # type: ignore[arg-type]
        )

    assert invalid.value.reason_id == "MEDIA_INVALID_BACKPRESSURE_LIMIT"
    assert socket.sent == []
    assert socket.close_calls == []
    assert effects == {"playback_stop": 0}


@pytest.mark.asyncio
async def test_downlink_practical_limit_boundaries_are_accepted() -> None:
    binding = _downlink_binding()
    socket = _FakeDedicatedSocket(
        [
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value, 0)
            )
        ]
    )

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=[_frame()],
        on_playback_stop=lambda _receipt: None,
        max_pending_frames=256,
        max_pending_bytes=8 * 1024 * 1024,
    )

    assert result.sent_frames == 1
    assert result.reason_id is MediaDetachReason.LOCAL_CLOSE
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_downlink_async_source_streams_in_order_and_closes_exactly_once() -> None:
    binding = _downlink_binding()

    class _AsyncFrames:
        def __init__(self) -> None:
            self.next_seq = 0
            self.close_calls = 0

        def __aiter__(self):
            return self

        async def __anext__(self) -> MediaAudioFrame:
            if self.next_seq >= 2:
                raise StopAsyncIteration
            frame = _frame(self.next_seq, self.next_seq * 160)
            self.next_seq += 1
            return frame

        async def aclose(self) -> None:
            self.close_calls += 1

    frames = _AsyncFrames()
    socket = _FakeDedicatedSocket(
        [
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value, 0)
            ),
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value, 1)
            ),
        ]
    )

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=frames,
        on_playback_stop=lambda _receipt: None,
        max_pending_frames=1,
        max_pending_bytes=2048,
    )

    binaries = [item for item in socket.sent if isinstance(item, bytes)]
    assert [decode_audio_frame(binding, item).seq for item in binaries] == [0, 1]
    assert result.reason_id is MediaDetachReason.LOCAL_CLOSE
    assert result.sent_frames == 2
    assert result.acknowledged_through_seq == 1
    assert frames.close_calls == 1


@pytest.mark.asyncio
async def test_downlink_async_source_failure_is_typed_and_never_replays_audio() -> None:
    binding = _downlink_binding()

    class _FailAfterFirstFrame:
        def __init__(self) -> None:
            self.next_calls = 0
            self.close_calls = 0

        def __aiter__(self):
            return self

        async def __anext__(self) -> MediaAudioFrame:
            self.next_calls += 1
            if self.next_calls == 1:
                return _frame()
            raise DedicatedMediaDownlinkSourceFailure(
                MediaDetachReason.STREAMING_TTS_TEXT_OR_RETRY
            )

        async def aclose(self) -> None:
            self.close_calls += 1

    frames = _FailAfterFirstFrame()
    socket = _FakeDedicatedSocket(
        [
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value, 0)
            )
        ]
    )

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=frames,
        on_playback_stop=lambda _receipt: None,
        max_pending_frames=1,
        max_pending_bytes=2048,
    )

    assert result.reason_id is MediaDetachReason.STREAMING_TTS_TEXT_OR_RETRY
    assert result.sent_frames == 1
    assert len([item for item in socket.sent if isinstance(item, bytes)]) == 1
    terminal = deserialize_media_control(socket.sent[-1])
    assert isinstance(terminal, MediaDetach)
    assert terminal.reason_id is MediaDetachReason.STREAMING_TTS_TEXT_OR_RETRY
    assert terminal.business_cancel_count_delta == 0
    assert frames.close_calls == 1


@pytest.mark.asyncio
async def test_downlink_transport_loss_closes_async_source_without_retry() -> None:
    binding = _downlink_binding()

    class _OpenAsyncFrames:
        def __init__(self) -> None:
            self.emitted = False
            self.close_calls = 0

        def __aiter__(self):
            return self

        async def __anext__(self) -> MediaAudioFrame:
            if self.emitted:
                await asyncio.Event().wait()
                raise AssertionError("unreachable")
            self.emitted = True
            return _frame()

        async def aclose(self) -> None:
            self.close_calls += 1

    frames = _OpenAsyncFrames()
    socket = _FakeDedicatedSocket([ConnectionError("private transport loss")])

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=frames,
        on_playback_stop=lambda _receipt: None,
        max_pending_frames=1,
        max_pending_bytes=2048,
    )

    assert result.reason_id is MediaDetachReason.TRANSPORT_CLOSED
    assert result.sent_frames == 1
    assert result.business_cancel_count_delta == 0
    assert frames.close_calls == 1


@pytest.mark.asyncio
async def test_downlink_completion_is_retained_before_physical_close() -> None:
    binding = _downlink_binding()
    effects = {"completed": False}

    class _OrderedCloseSocket(_FakeDedicatedSocket):
        async def close(self, code: int = 1000, reason: str = "") -> None:
            assert effects["completed"] is True
            await super().close(code, reason)

    socket = _OrderedCloseSocket(
        [
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value, 0)
            )
        ]
    )

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=[_frame()],
        on_playback_stop=lambda _receipt: None,
        on_complete=lambda _result: effects.__setitem__("completed", True),
        max_pending_frames=1,
        max_pending_bytes=2048,
    )

    assert result.reason_id is MediaDetachReason.LOCAL_CLOSE
    assert effects == {"completed": True}
    assert len(socket.close_calls) == 1


@pytest.mark.asyncio
async def test_downlink_wrong_ack_generation_detaches_before_stop_or_other_scope_effects() -> (
    None
):
    binding = _downlink_binding()
    socket = _FakeDedicatedSocket(
        [
            serialize_media_control(
                MediaAck(binding.lease_id, binding.generation.value + 1, 0)
            )
        ]
    )
    effects = {"stop": 0, "agent": 0, "tool": 0, "task": 0, "history": 0}

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=[_frame()],
        on_playback_stop=lambda _receipt: effects.__setitem__("stop", 1),
        max_pending_frames=1,
        max_pending_bytes=2048,
    )

    assert result.reason_id is MediaDetachReason.STALE_GENERATION
    assert result.acknowledged_through_seq is None
    assert result.playback_stop_receipts == 0
    assert effects == {"stop": 0, "agent": 0, "tool": 0, "task": 0, "history": 0}


@pytest.mark.asyncio
async def test_downlink_stop_cannot_confirm_an_unsent_cursor() -> None:
    binding = _downlink_binding()
    impossible_stop = create_playback_stop_receipt(
        binding,
        outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED,
        confirmed_through_seq=1,
    )
    socket = _FakeDedicatedSocket([serialize_media_control(impossible_stop)])
    effects = {"stop": 0, "agent": 0, "tool": 0, "task": 0, "history": 0}

    result = await run_dedicated_media_downlink_socket_leaf(
        _request(binding),
        socket=socket,
        frames=[_frame()],
        on_playback_stop=lambda _receipt: effects.__setitem__("stop", 1),
        max_pending_frames=1,
        max_pending_bytes=2048,
    )

    assert result.reason_id is MediaDetachReason.ACK_UNSENT
    assert result.sent_frames == 1
    assert result.playback_stop_receipts == 0
    assert effects == {"stop": 0, "agent": 0, "tool": 0, "task": 0, "history": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["uplink", "downlink"])
async def test_socket_leaf_cancellation_closes_transport_without_retry(
    direction: str,
) -> None:
    socket = _BlockingDedicatedSocket()
    binding = _binding() if direction == "uplink" else _downlink_binding()
    if direction == "uplink":
        operation = run_dedicated_media_socket_leaf(
            _request(binding),
            socket=socket,
            on_audio_frame=lambda _frame: None,
        )
    else:
        operation = run_dedicated_media_downlink_socket_leaf(
            _request(binding),
            socket=socket,
            frames=[_frame()],
            on_playback_stop=lambda _receipt: None,
            max_pending_frames=1,
            max_pending_bytes=2048,
        )
    task = asyncio.create_task(operation)
    await socket.receiving.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(socket.close_calls) == 1
    assert len(socket.sent) == (1 if direction == "uplink" else 2)


@pytest.mark.asyncio
async def test_socket_leaf_cleanup_is_bounded_when_physical_close_never_confirms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_SOCKET_CLOSE_TIMEOUT_SECONDS", 0.01)
    socket = _BlockingCloseDedicatedSocket([b"not-lvm1"])

    result = await run_dedicated_media_socket_leaf(
        _request(_binding()),
        socket=socket,
        on_audio_frame=lambda _frame: None,
    )

    assert result.reason_id is MediaDetachReason.MALFORMED_FRAME
    assert len(socket.close_calls) == 1
