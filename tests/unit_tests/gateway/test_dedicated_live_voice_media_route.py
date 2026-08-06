# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import builtins
import json
import logging
import math
import struct
from dataclasses import replace
from pathlib import Path

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
    MediaFrameFormat,
    MediaGenerationBinding,
    MediaGenerationKind,
    MediaPlayoutBinding,
    MediaTransportViolation,
    encode_audio_frame,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION,
    MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN,
    MEDIA_ROUTE_REGISTRATION_UNAVAILABLE,
    ActiveDedicatedMediaRoute,
    DedicatedMediaRouteEvidence,
    DedicatedMediaRouteReason,
    DedicatedMediaRouteRequest,
    DedicatedMediaRouteTruth,
    InactiveDedicatedMediaRoute,
    create_dedicated_media_route,
)


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
