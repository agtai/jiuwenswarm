from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MEDIA_CONTRACT_VERSION,
    MEDIA_TRANSPORT_KIND,
    MEDIA_WIRE_CODEC,
    ActiveMediaActivation,
    BinarySendDisposition,
    InactiveMediaActivation,
    MediaAck,
    MediaActivationRequest,
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
    MediaPlaybackStopOutcome,
    MediaTransportViolation,
    create_gateway_media_activation,
    create_playback_stop_receipt,
    decode_audio_frame,
    deserialize_media_control,
    encode_audio_frame,
    serialize_media_control,
    validate_playback_stop_receipt,
)


def _binding(
    *,
    direction: MediaDirection = MediaDirection.UPLINK,
    lease_id: str = "lease-opaque-01",
    session_id: str = "session-01",
    track_id: str = "capture-track-01",
    generation_value: int = 7,
) -> MediaAuthorityBinding:
    if direction is MediaDirection.DOWNLINK:
        generation = MediaGenerationBinding(
            MediaGenerationKind.RESPONSE, "response-01", generation_value
        )
        playout = MediaPlayoutBinding("response-01", generation_value, "unit-01")
    else:
        generation = MediaGenerationBinding(
            MediaGenerationKind.CAPTURE, "capture-01", generation_value
        )
        playout = None
    return MediaAuthorityBinding(
        lease_id=lease_id,
        authority_evidence_id="authority-evidence-01",
        connection_id="connection-01",
        connection_epoch=3,
        session_id=session_id,
        media_session_id="media-session-01",
        interaction_id="interaction-01",
        track_id=track_id,
        correlation_id="correlation-01",
        direction=direction,
        generation=generation,
        frame_format=MediaFrameFormat(sample_rate_hz=8_000, samples_per_channel=160),
        playout=playout,
    )


def _frame(seq: int = 0, cursor: int = 0) -> MediaAudioFrame:
    samples = tuple(math.sin(index / 11) * 0.25 for index in range(160))
    return MediaAudioFrame(seq=seq, sample_cursor=cursor, samples=samples)


def _active(
    binding: MediaAuthorityBinding | None = None,
    *,
    max_pending_frames: int = 8,
    max_pending_bytes: int = 131_072,
    effects: dict[str, int] | None = None,
) -> ActiveMediaActivation:
    counters = effects if effects is not None else {"audio": 0}

    def consume(_frame: MediaAudioFrame) -> None:
        counters["audio"] = counters.get("audio", 0) + 1

    activation = create_gateway_media_activation(
        MediaActivationRequest(
            enabled=True,
            binding=binding or _binding(),
            provider_available=True,
            transport_available=True,
            max_pending_frames=max_pending_frames,
            max_pending_bytes=max_pending_bytes,
        ),
        on_audio_frame=consume,
    )
    assert isinstance(activation, ActiveMediaActivation)
    return activation


def _assert_zero_downstream(effects: dict[str, int]) -> None:
    assert effects == {"audio": 0, "agent": 0, "task": 0}


def test_lvm1_frame_and_typed_control_round_trip() -> None:
    binding = _binding()
    frame = _frame()

    binary = encode_audio_frame(binding, frame)
    decoded = decode_audio_frame(binding, binary)
    attach = MediaAttach(binding)
    decoded_control = deserialize_media_control(serialize_media_control(attach))

    assert binary[:4] == b"LVM1"
    assert decoded.seq == frame.seq
    assert decoded.sample_cursor == frame.sample_cursor
    assert decoded.samples == pytest.approx(frame.samples, abs=1e-7)
    assert decoded_control == attach
    assert MEDIA_CONTRACT_VERSION == "live-voice.media.v1"
    assert MEDIA_TRANSPORT_KIND == "websocket_binary"
    assert MEDIA_WIRE_CODEC == "pcm_f32le"


def test_actual_audio_context_rate_is_preserved_without_resampling() -> None:
    frame_format = MediaFrameFormat(sample_rate_hz=48_000, samples_per_channel=960)
    binding = replace(_binding(), frame_format=frame_format)
    samples = tuple((index % 31) / 64 for index in range(960))

    decoded = decode_audio_frame(
        binding, encode_audio_frame(binding, MediaAudioFrame(0, 0, samples))
    )

    assert binding.frame_format.sample_rate_hz == 48_000
    assert binding.frame_format.samples_per_channel == 960
    assert len(decoded.samples) == 960
    assert decoded.samples == pytest.approx(samples, abs=1e-7)


def test_lvm1_cross_language_fixture_is_byte_exact() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "live_voice_media_transport_v1"
        / "roundtrip.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    raw = fixture["binding"]
    generation = raw["generation"]
    frame_format = raw["frame_format"]
    binding = MediaAuthorityBinding(
        lease_id=raw["lease_id"],
        authority_evidence_id=raw["authority_evidence_id"],
        connection_id=raw["connection_id"],
        connection_epoch=raw["connection_epoch"],
        session_id=raw["session_id"],
        media_session_id=raw["media_session_id"],
        interaction_id=raw["interaction_id"],
        track_id=raw["track_id"],
        correlation_id=raw["correlation_id"],
        direction=MediaDirection(raw["direction"]),
        generation=MediaGenerationBinding(
            MediaGenerationKind(generation["kind"]),
            generation["id"],
            generation["value"],
        ),
        frame_format=MediaFrameFormat(**frame_format),
        playout=None,
    )
    source = fixture["frame"]
    samples = tuple(source["sample_prefix"]) + (0.0,) * source["trailing_zero_samples"]

    binary = encode_audio_frame(
        binding, MediaAudioFrame(source["seq"], source["sample_cursor"], samples)
    )

    assert len(binary) == fixture["expected_binary_bytes"]
    assert hashlib.sha256(binary).hexdigest() == fixture["expected_sha256"]


@pytest.mark.parametrize(
    ("replacement", "expected_reason"),
    [
        ({"session_id": "wrong-session"}, "MEDIA_BINDING_MISMATCH"),
        ({"track_id": "wrong-track"}, "MEDIA_BINDING_MISMATCH"),
        ({"lease_id": "wrong-lease"}, "MEDIA_BINDING_MISMATCH"),
    ],
)
def test_attach_rejects_wrong_exact_binding_with_zero_downstream(
    replacement: dict[str, object], expected_reason: str
) -> None:
    effects = {"audio": 0, "agent": 0, "task": 0}
    activation = _active(effects=effects)

    result = activation.receiver.attach(
        MediaAttach(replace(activation.binding, **replacement))
    )

    assert isinstance(result, MediaDetach)
    assert result.reason_id == expected_reason
    assert activation.receiver.closed is True
    _assert_zero_downstream(effects)


@pytest.mark.parametrize(
    ("mutate", "expected_reason"),
    [
        (lambda binary: binary[:10], "MEDIA_MALFORMED_FRAME"),
        (lambda binary: b"BAD!" + binary[4:], "MEDIA_MALFORMED_FRAME"),
        (lambda binary: binary + (b"\x00" * 20_000), "MEDIA_OVERSIZED_FRAME"),
        (
            lambda binary: binary[:8] + struct.pack("<Q", 999) + binary[16:],
            "MEDIA_STALE_GENERATION",
        ),
        (
            lambda binary: binary[:24] + struct.pack("<Q", 1) + binary[32:],
            "MEDIA_CURSOR_MISMATCH",
        ),
    ],
)
def test_malformed_oversized_stale_and_cursor_frames_detach_without_effects(
    mutate, expected_reason: str
) -> None:
    effects = {"audio": 0, "agent": 0, "task": 0}
    activation = _active(effects=effects)
    assert activation.receiver.attach(MediaAttach(activation.binding)) is None

    result = activation.receiver.accept_binary(
        mutate(encode_audio_frame(activation.binding, _frame()))
    )

    assert isinstance(result, MediaDetach)
    assert result.reason_id == expected_reason
    _assert_zero_downstream(effects)


def test_nonfinite_audio_is_terminal_before_consumer() -> None:
    effects = {"audio": 0, "agent": 0, "task": 0}
    activation = _active(effects=effects)
    activation.receiver.attach(MediaAttach(activation.binding))
    binary = bytearray(encode_audio_frame(activation.binding, _frame()))
    payload_offset = 36 + len(activation.binding.lease_id.encode("utf-8"))
    binary[payload_offset : payload_offset + 4] = struct.pack("<f", float("nan"))

    result = activation.receiver.accept_binary(binary)

    assert isinstance(result, MediaDetach)
    assert result.reason_id == "MEDIA_NONFINITE_AUDIO"
    _assert_zero_downstream(effects)


def test_outgoing_non_pcm_f32_value_terminally_closes_sender() -> None:
    activation = _active()
    invalid = MediaAudioFrame(0, 0, (1e300,) + (0.0,) * 159)

    result = activation.sender.enqueue(invalid)

    assert result.accepted is False
    assert result.reason_id == "MEDIA_INVALID_FRAME"
    assert activation.sender.closed is True


@pytest.mark.parametrize(
    (
        "first_seq",
        "first_cursor",
        "second_seq",
        "second_cursor",
        "expected_reason",
        "expected_audio",
    ),
    [
        (1, 160, None, None, "MEDIA_SEQUENCE_GAP", 0),
        (0, 0, 0, 0, "MEDIA_DUPLICATE_OR_OUT_OF_ORDER", 1),
        (0, 0, 2, 320, "MEDIA_SEQUENCE_GAP", 1),
        (0, 0, 1, 161, "MEDIA_CURSOR_MISMATCH", 1),
    ],
)
def test_duplicate_gap_out_of_order_and_cursor_policy_is_terminal(
    first_seq: int,
    first_cursor: int,
    second_seq: int | None,
    second_cursor: int | None,
    expected_reason: str,
    expected_audio: int,
) -> None:
    effects = {"audio": 0, "agent": 0, "task": 0}
    activation = _active(effects=effects)
    activation.receiver.attach(MediaAttach(activation.binding))

    result = activation.receiver.accept_binary(
        encode_audio_frame(activation.binding, _frame(first_seq, first_cursor))
    )
    if second_seq is not None and not isinstance(result, MediaDetach):
        result = activation.receiver.accept_binary(
            encode_audio_frame(
                activation.binding, _frame(second_seq, second_cursor or 0)
            )
        )

    assert isinstance(result, MediaDetach)
    assert result.reason_id == expected_reason
    assert effects == {"audio": expected_audio, "agent": 0, "task": 0}


def test_sender_is_bounded_and_releases_only_sent_acked_frames() -> None:
    activation = _active(max_pending_frames=1)
    sender = activation.sender
    assert sender.enqueue(_frame(0, 0)).accepted is True
    blocked = sender.enqueue(_frame(1, 160))
    assert blocked.accepted is False
    assert blocked.reason_id == "MEDIA_BACKPRESSURE_LIMIT"
    assert sender.pending_frames == 1

    backpressured = sender.drain(lambda _binary: BinarySendDisposition.BACKPRESSURED)
    assert backpressured.sent_frames == 0
    assert sender.pending_frames == 1
    assert (
        sender.acknowledge(MediaAck(activation.binding.lease_id, 7, 0)).reason_id
        == "MEDIA_ACK_UNSENT"
    )

    activation = _active(max_pending_frames=1)
    sender = activation.sender
    assert sender.enqueue(_frame(0, 0)).accepted is True
    drained = sender.drain(lambda _binary: BinarySendDisposition.SENT)
    assert drained.sent_frames == 1
    assert sender.acknowledge(MediaAck(activation.binding.lease_id, 7, 0)) is None
    assert sender.pending_frames == 0
    assert sender.pending_bytes == 0
    assert sender.enqueue(_frame(1, 160)).accepted is True


def test_wrong_ack_generation_detaches_and_close_is_bounded() -> None:
    activation = _active()
    activation.sender.enqueue(_frame())
    activation.sender.drain(lambda _binary: BinarySendDisposition.SENT)

    detach = activation.sender.acknowledge(MediaAck(activation.binding.lease_id, 6, 0))
    close = activation.sender.close()

    assert detach is not None and detach.reason_id == "MEDIA_STALE_GENERATION"
    assert close.was_active is False
    assert close.dropped_frames == 1
    assert close.business_cancel_count_delta == 0


def test_injected_transport_failure_closes_without_implicit_retry() -> None:
    activation = _active()
    activation.sender.enqueue(_frame())

    def fail_send(_binary: bytes) -> BinarySendDisposition:
        raise OSError("private transport detail")

    result = activation.sender.drain(fail_send)

    assert result.sent_frames == 0
    assert result.reason_id == "MEDIA_TRANSPORT_SEND_FAILED"
    assert activation.sender.closed is True


def test_semantic_detach_and_close_fence_the_lease_without_downstream_effects() -> None:
    effects = {"audio": 0, "agent": 0, "task": 0}
    activation = _active(effects=effects)
    assert activation.receiver.attach(MediaAttach(activation.binding)) is None
    control = MediaDetach(
        activation.binding.lease_id,
        activation.binding.generation.value,
        MediaDetachReason.LOCAL_CLOSE,
    )

    detached = activation.receiver.accept_detach(control)
    late = activation.receiver.accept_binary(
        encode_audio_frame(activation.binding, _frame())
    )
    repeated = activation.receiver.close()

    assert detached.was_active is True
    assert detached.reason_id == "MEDIA_LOCAL_CLOSE"
    assert detached.business_cancel_count_delta == 0
    assert isinstance(late, MediaDetach) and late.reason_id == "MEDIA_LOCAL_CLOSE"
    assert repeated.was_active is False
    _assert_zero_downstream(effects)


@pytest.mark.parametrize(
    ("enabled", "binding", "provider", "transport", "reason"),
    [
        (False, _binding(), True, True, "MEDIA_FEATURE_DISABLED"),
        (True, None, True, True, "MEDIA_AUTHORITY_UNAVAILABLE"),
        (True, _binding(), False, True, "MEDIA_PROVIDER_UNAVAILABLE"),
        (True, _binding(), True, False, "MEDIA_TRANSPORT_UNAVAILABLE"),
    ],
)
def test_inactive_gates_allocate_no_media_objects_and_have_zero_effects(
    enabled: bool,
    binding: MediaAuthorityBinding | None,
    provider: bool,
    transport: bool,
    reason: str,
) -> None:
    effects = {"audio": 0, "agent": 0, "task": 0}
    activation = create_gateway_media_activation(
        MediaActivationRequest(
            enabled=enabled,
            binding=binding,
            provider_available=provider,
            transport_available=transport,
        ),
        on_audio_frame=lambda _frame: effects.__setitem__(
            "audio", effects["audio"] + 1
        ),
    )

    assert isinstance(activation, InactiveMediaActivation)
    assert activation.reason_id == reason
    assert not hasattr(activation, "sender")
    assert not hasattr(activation, "receiver")
    assert activation.capability.real_transport_observed is False
    assert activation.capability.formal_route_ready is False
    assert activation.capability.evidence_scope == "contract_only"
    assert activation.capability.registration_evidence_id is None
    assert activation.capability.runtime_evidence_id is None
    _assert_zero_downstream(effects)


def test_downlink_stop_receipt_is_exact_and_never_business_cancel() -> None:
    binding = _binding(direction=MediaDirection.DOWNLINK)

    receipt = create_playback_stop_receipt(
        binding,
        outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED,
        confirmed_through_seq=4,
    )
    decoded = deserialize_media_control(serialize_media_control(receipt))

    assert decoded == receipt
    assert receipt.response_id == binding.playout.response_id
    assert receipt.response_generation == binding.playout.response_generation
    assert receipt.unit_id == binding.playout.unit_id
    assert receipt.business_cancel_count_delta == 0
    with pytest.raises(MediaTransportViolation) as wrong_unit:
        validate_playback_stop_receipt(binding, replace(receipt, unit_id="wrong-unit"))
    assert wrong_unit.value.reason_id == "MEDIA_STOP_BINDING_MISMATCH"
    with pytest.raises(MediaTransportViolation, match="downlink authority"):
        create_playback_stop_receipt(
            _binding(), outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED
        )


def test_format_and_closed_control_validation_fail_closed() -> None:
    with pytest.raises(MediaTransportViolation, match="exact 20 ms"):
        MediaFrameFormat(sample_rate_hz=44_101, samples_per_channel=882)
    with pytest.raises(MediaTransportViolation) as error:
        deserialize_media_control(
            '{"type":"media.ack","contract_version":"live-voice.media.v1",'
            '"lease_id":"lease","generation":1,"through_seq":0,"session_id":"client-claim"}'
        )
    assert error.value.reason_id == "MEDIA_MALFORMED_CONTROL"

    with pytest.raises(MediaTransportViolation, match="mono"):
        MediaFrameFormat(
            sample_rate_hz=8_000, samples_per_channel=160, channel_count=True
        )
    attach = json.loads(serialize_media_control(MediaAttach(_binding())))
    attach["binding"]["frame_format"]["channel_count"] = True
    with pytest.raises(MediaTransportViolation) as noncanonical_format:
        deserialize_media_control(json.dumps(attach))
    assert noncanonical_format.value.reason_id == "MEDIA_INVALID_FORMAT"


def test_arbitrary_detach_reason_is_rejected_before_receiver_state_change() -> None:
    effects = {"audio": 0, "agent": 0, "task": 0}
    activation = _active(effects=effects)
    assert activation.receiver.attach(MediaAttach(activation.binding)) is None
    valid = MediaDetach(
        activation.binding.lease_id,
        activation.binding.generation.value,
        MediaDetachReason.PEER_CLOSE,
    )
    raw = json.loads(serialize_media_control(valid))
    raw["reason_id"] = "private-content\nnot-a-stable-reason"

    with pytest.raises(MediaTransportViolation) as malformed:
        deserialize_media_control(json.dumps(raw))
    with pytest.raises(MediaTransportViolation) as direct:
        MediaDetach(
            activation.binding.lease_id,
            activation.binding.generation.value,
            "private-content\nnot-a-stable-reason",  # type: ignore[arg-type]
        )

    assert malformed.value.reason_id == "MEDIA_MALFORMED_CONTROL"
    assert direct.value.reason_id == "MEDIA_INVALID_CONTROL"
    assert activation.receiver.attached is True
    assert activation.receiver.closed is False
    _assert_zero_downstream(effects)

    local = _active().sender.close("private-content\nnot-a-stable-reason")  # type: ignore[arg-type]
    assert local.reason_id is MediaDetachReason.LOCAL_CLOSE
    assert (
        local.detach is not None
        and local.detach.reason_id is MediaDetachReason.LOCAL_CLOSE
    )


@pytest.mark.parametrize("invalid_zero", [False, 0.0])
def test_business_cancel_delta_requires_canonical_integer_zero(
    invalid_zero: object,
) -> None:
    effects = {"audio": 0, "agent": 0, "task": 0}
    activation = _active(effects=effects)
    assert activation.receiver.attach(MediaAttach(activation.binding)) is None
    detach = MediaDetach(
        activation.binding.lease_id,
        activation.binding.generation.value,
        MediaDetachReason.PEER_CLOSE,
    )
    detach_raw = json.loads(serialize_media_control(detach))
    detach_raw["business_cancel_count_delta"] = invalid_zero
    stop = create_playback_stop_receipt(
        _binding(direction=MediaDirection.DOWNLINK),
        outcome=MediaPlaybackStopOutcome.LOCAL_FENCE_ESTABLISHED,
    )
    stop_raw = json.loads(serialize_media_control(stop))
    stop_raw["business_cancel_count_delta"] = invalid_zero

    with pytest.raises(MediaTransportViolation) as detach_json:
        deserialize_media_control(json.dumps(detach_raw))
    with pytest.raises(MediaTransportViolation) as stop_json:
        deserialize_media_control(json.dumps(stop_raw))
    with pytest.raises(MediaTransportViolation) as detach_semantic:
        replace(detach, business_cancel_count_delta=invalid_zero)
    with pytest.raises(MediaTransportViolation) as stop_semantic:
        replace(stop, business_cancel_count_delta=invalid_zero)

    assert detach_json.value.reason_id == "MEDIA_MALFORMED_CONTROL"
    assert stop_json.value.reason_id == "MEDIA_MALFORMED_CONTROL"
    assert detach_semantic.value.reason_id == "MEDIA_CANCEL_SCOPE_VIOLATION"
    assert stop_semantic.value.reason_id == "MEDIA_CANCEL_SCOPE_VIOLATION"
    assert activation.receiver.attached is True
    assert activation.receiver.closed is False
    _assert_zero_downstream(effects)
