# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import builtins
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from pathlib import Path

import pytest

import jiuwenswarm.server.live_voice.realtime_media as realtime_media_module
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    ConnectionEpochRef,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAuthorityBinding,
    MediaDirection,
    MediaFrameFormat,
    MediaGenerationBinding,
    MediaGenerationKind,
    MediaPlayoutBinding,
)
from jiuwenswarm.server.live_voice.realtime_media import (
    ActiveRealtimeMediaActivation,
    InactiveRealtimeMediaActivation,
    MediaAck,
    MediaFrame,
    MediaPayloadLifecycleSnapshot,
    MediaPortCloseResult,
    RealtimeMediaActivationRequest,
    RealtimeMediaLeafAuditFact,
    RealtimeMediaPort,
    RealtimeMediaRegistrationOwner,
    RealtimeMediaViolation,
    create_realtime_media_activation,
)


class _EqualitySpoof:
    def __eq__(self, _other: object) -> bool:
        return True


def _authority_binding(
    *,
    direction: MediaDirection = MediaDirection.UPLINK,
) -> MediaAuthorityBinding:
    generation = MediaGenerationBinding(
        kind=(
            MediaGenerationKind.CAPTURE
            if direction is MediaDirection.UPLINK
            else MediaGenerationKind.RESPONSE
        ),
        id="capture-1" if direction is MediaDirection.UPLINK else "response-1",
        value=7,
    )
    return MediaAuthorityBinding(
        lease_id="lease-1",
        authority_evidence_id="authority-1",
        connection_id="connection-1",
        connection_epoch=3,
        session_id="session-1",
        media_session_id="media-session-1",
        interaction_id="interaction-1",
        track_id="track-1",
        correlation_id="correlation-1",
        direction=direction,
        generation=generation,
        frame_format=MediaFrameFormat(
            sample_rate_hz=8_000,
            samples_per_channel=160,
        ),
        playout=(
            None
            if direction is MediaDirection.UPLINK
            else MediaPlayoutBinding(
                response_id="response-1",
                response_generation=7,
                unit_id="unit-1",
            )
        ),
    )


@pytest.mark.parametrize(
    "connection",
    [
        object(),
        ConnectionEpochRef("", 0),
        ConnectionEpochRef("connection-1", True),
        ConnectionEpochRef("connection-1", -1),
        ConnectionEpochRef(_EqualitySpoof(), 0),  # type: ignore[arg-type]
        ConnectionEpochRef("connection-1", MAX_SAFE_INTEGER + 1),
        ConnectionEpochRef("invalid-\ud800-id", 0),
    ],
)
def test_constructor_rejects_malformed_connection_binding(connection: object) -> None:
    with pytest.raises(RealtimeMediaViolation) as raised:
        RealtimeMediaPort(connection)  # type: ignore[arg-type]

    assert raised.value.reason == "INVALID_CONNECTION_EPOCH_REF"


def test_bounded_queue_sequence_and_ack() -> None:
    connection = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(connection, capacity=2)
    port.enqueue(MediaFrame(connection, "track-1", 0, b"a"))
    port.enqueue(MediaFrame(connection, "track-1", 1, b"b"))
    assert [frame.payload for frame in port.read("track-1")] == [b"a", b"b"]
    assert [frame.payload for frame in port.read("track-1")] == [b"a", b"b"]
    with pytest.raises(RealtimeMediaViolation) as raised:
        port.enqueue(MediaFrame(connection, "track-1", 2, b"c"))
    assert raised.value.reason == "MEDIA_QUEUE_OVERFLOW"
    assert port.acknowledge(MediaAck(connection, "track-1", 0)) == 1
    assert port.pending("track-1") == 1
    snapshot = port.payload_lifecycle_snapshot()
    assert snapshot.accepted_frames == 2
    assert snapshot.accepted_payload_bytes == 2
    assert snapshot.delivered_frames == 2
    assert snapshot.delivered_payload_bytes == 2
    assert snapshot.acknowledged_frames == 1
    assert snapshot.acknowledged_payload_bytes == 1
    assert snapshot.pending_frames == 1
    assert snapshot.pending_payload_bytes == 1


def test_wrong_epoch_and_sequence_do_not_enter_queue() -> None:
    connection = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(connection)
    with pytest.raises(RealtimeMediaViolation) as raised:
        port.enqueue(
            MediaFrame(ConnectionEpochRef("connection-1", 1), "track", 0, b"a")
        )
    assert raised.value.reason == "CONNECTION_EPOCH_MISMATCH"
    with pytest.raises(RealtimeMediaViolation) as raised:
        port.enqueue(MediaFrame(connection, "track", 1, b"a"))
    assert raised.value.reason == "NON_CONTIGUOUS_MEDIA_SEQUENCE"
    assert port.pending("track") == 0


def test_constructor_retains_a_canonical_connection_copy() -> None:
    supplied = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(supplied, allowed_track_id="track")
    object.__setattr__(supplied, "connection_epoch", 3)
    before = port.payload_lifecycle_snapshot()

    with pytest.raises(RealtimeMediaViolation) as raised:
        port.enqueue(MediaFrame(supplied, "track", 0, b"mutated"))

    assert raised.value.reason == "CONNECTION_EPOCH_MISMATCH"
    assert port.payload_lifecycle_snapshot() == before
    original = ConnectionEpochRef("connection-1", 2)
    port.enqueue(MediaFrame(original, "track", 0, b"canonical"))
    assert port.pending("track") == 1


@pytest.mark.parametrize(
    "malformed_connection",
    [
        object(),
        ConnectionEpochRef("", 2),
        ConnectionEpochRef("connection-1", True),
        ConnectionEpochRef("connection-1", -1),
        ConnectionEpochRef(_EqualitySpoof(), 2),  # type: ignore[arg-type]
        ConnectionEpochRef("connection-1", MAX_SAFE_INTEGER + 1),
        ConnectionEpochRef("invalid-\ud800-id", 2),
    ],
)
def test_malformed_frame_binding_has_zero_queue_and_counter_effect(
    malformed_connection: object,
) -> None:
    connection = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(connection)
    before = port.payload_lifecycle_snapshot()

    with pytest.raises(RealtimeMediaViolation) as raised:
        port.enqueue(
            MediaFrame(
                malformed_connection,  # type: ignore[arg-type]
                "spoofed-track",
                0,
                b"audio",
            )
        )

    assert raised.value.reason == "INVALID_MEDIA_FRAME"
    assert port.payload_lifecycle_snapshot() == before
    assert port.pending("spoofed-track") == 0
    port.enqueue(MediaFrame(connection, "real-track", 0, b"valid"))
    assert port.pending("real-track") == 1


@pytest.mark.parametrize(
    "malformed_connection",
    [
        object(),
        ConnectionEpochRef("", 2),
        ConnectionEpochRef("connection-1", True),
        ConnectionEpochRef("connection-1", -1),
        ConnectionEpochRef(_EqualitySpoof(), 2),  # type: ignore[arg-type]
        ConnectionEpochRef("connection-1", MAX_SAFE_INTEGER + 1),
        ConnectionEpochRef("invalid-\ud800-id", 2),
    ],
)
def test_malformed_ack_binding_has_zero_queue_and_counter_effect(
    malformed_connection: object,
) -> None:
    connection = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(connection, allowed_track_id="track")
    port.enqueue(MediaFrame(connection, "track", 0, b"audio"))
    port.read("track")
    before = port.payload_lifecycle_snapshot()

    with pytest.raises(RealtimeMediaViolation) as raised:
        port.acknowledge(
            MediaAck(
                malformed_connection,  # type: ignore[arg-type]
                "track",
                0,
            )
        )

    assert raised.value.reason == "INVALID_MEDIA_ACK"
    assert port.payload_lifecycle_snapshot() == before
    assert port.pending("track") == 1


@pytest.mark.parametrize(
    "wrong_connection",
    [
        ConnectionEpochRef("other-connection", 2),
        ConnectionEpochRef("connection-1", 3),
    ],
)
def test_valid_but_wrong_ack_binding_has_zero_queue_and_counter_effect(
    wrong_connection: ConnectionEpochRef,
) -> None:
    connection = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(connection, allowed_track_id="track")
    port.enqueue(MediaFrame(connection, "track", 0, b"audio"))
    port.read("track")
    before = port.payload_lifecycle_snapshot()

    with pytest.raises(RealtimeMediaViolation) as raised:
        port.acknowledge(MediaAck(wrong_connection, "track", 0))

    assert raised.value.reason == "CONNECTION_EPOCH_MISMATCH"
    assert port.payload_lifecycle_snapshot() == before
    assert port.pending("track") == 1


@pytest.mark.parametrize("prebind_track", [False, True])
def test_track_admission_prevents_multi_track_capacity_bypass(
    prebind_track: bool,
) -> None:
    connection = ConnectionEpochRef("connection-1", 0)
    port = RealtimeMediaPort(
        connection,
        capacity=2,
        allowed_track_id="track-a" if prebind_track else None,
    )
    port.enqueue(MediaFrame(connection, "track-a", 0, b"a"))
    before = port.payload_lifecycle_snapshot()

    with pytest.raises(RealtimeMediaViolation) as raised:
        port.enqueue(MediaFrame(connection, "track-b", 0, b"b"))

    assert raised.value.reason == "MEDIA_TRACK_MISMATCH"
    assert port.payload_lifecycle_snapshot() == before
    assert port.pending("track-a") == 1
    with pytest.raises(RealtimeMediaViolation) as wrong_track:
        port.pending("track-b")
    assert wrong_track.value.reason == "MEDIA_TRACK_MISMATCH"


def test_payload_bounds_reject_overflow_without_effect() -> None:
    connection = ConnectionEpochRef("connection-1", 0)
    port = RealtimeMediaPort(
        connection,
        allowed_track_id="track",
        max_frame_payload_bytes=4,
        max_retained_payload_bytes=5,
    )
    empty = port.payload_lifecycle_snapshot()

    with pytest.raises(RealtimeMediaViolation) as oversized:
        port.enqueue(MediaFrame(connection, "track", 0, b"12345"))
    assert oversized.value.reason == "MEDIA_FRAME_PAYLOAD_TOO_LARGE"
    assert port.payload_lifecycle_snapshot() == empty
    assert port.pending("track") == 0

    port.enqueue(MediaFrame(connection, "track", 0, b"123"))
    retained = port.payload_lifecycle_snapshot()
    with pytest.raises(RealtimeMediaViolation) as aggregate:
        port.enqueue(MediaFrame(connection, "track", 1, b"456"))
    assert aggregate.value.reason == "MEDIA_PAYLOAD_CAPACITY_EXCEEDED"
    assert port.payload_lifecycle_snapshot() == retained
    assert port.pending("track") == 1

    assert port.read("track") == (MediaFrame(connection, "track", 0, b"123"),)
    assert port.acknowledge(MediaAck(connection, "track", 0)) == 1
    port.enqueue(MediaFrame(connection, "track", 1, b"456"))
    reclaimed = port.payload_lifecycle_snapshot()
    assert reclaimed.pending_frames == 1
    assert reclaimed.pending_payload_bytes == 3


def test_submitted_frame_mutation_cannot_change_retained_media() -> None:
    original_payload = b"abc"
    mutated_payload = b"mutated-submitted-payload-sentinel"
    port_connection = ConnectionEpochRef("connection-1", 2)
    submitted_connection = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(
        port_connection,
        allowed_track_id="track",
        max_frame_payload_bytes=len(original_payload),
        max_retained_payload_bytes=len(original_payload),
    )
    submitted = MediaFrame(submitted_connection, "track", 0, original_payload)

    port.enqueue(submitted)
    object.__setattr__(submitted_connection, "connection_epoch", 99)
    object.__setattr__(submitted, "track_id", "mutated-track")
    object.__setattr__(submitted, "seq", 99)
    object.__setattr__(submitted, "payload", mutated_payload)

    retained = port.payload_lifecycle_snapshot()
    assert retained.accepted_frames == 1
    assert retained.accepted_payload_bytes == len(original_payload)
    assert retained.pending_frames == 1
    assert retained.pending_payload_bytes == len(original_payload)
    result = port.read("track")
    assert result == (MediaFrame(port_connection, "track", 0, original_payload),)
    assert result[0] is not submitted
    assert result[0].connection is not submitted_connection
    assert result[0].connection.connection_epoch == 2
    delivered = port.payload_lifecycle_snapshot()
    assert delivered.delivered_frames == 1
    assert delivered.delivered_payload_bytes == len(original_payload)
    assert port.acknowledge(MediaAck(port_connection, "track", 0)) == 1
    acknowledged = port.payload_lifecycle_snapshot()
    assert acknowledged.acknowledged_frames == 1
    assert acknowledged.acknowledged_payload_bytes == len(original_payload)
    assert acknowledged.pending_frames == 0
    assert acknowledged.pending_payload_bytes == 0
    assert acknowledged.dropped_frames == 0
    assert mutated_payload.decode() not in repr(submitted)
    assert mutated_payload.decode() not in repr(result)


def test_returned_frame_mutation_cannot_change_retained_media() -> None:
    original_payload = b"drop"
    mutated_payload = b"mutated-returned-payload-sentinel"
    connection = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(
        connection,
        allowed_track_id="track",
        max_frame_payload_bytes=len(original_payload),
        max_retained_payload_bytes=len(original_payload),
    )
    port.enqueue(MediaFrame(connection, "track", 0, original_payload))
    first_result = port.read("track")
    outward = first_result[0]

    object.__setattr__(outward.connection, "connection_epoch", 99)
    object.__setattr__(outward, "track_id", "mutated-track")
    object.__setattr__(outward, "seq", 99)
    object.__setattr__(outward, "payload", mutated_payload)

    retained = port.payload_lifecycle_snapshot()
    assert retained.delivered_frames == 1
    assert retained.delivered_payload_bytes == len(original_payload)
    assert retained.pending_frames == 1
    assert retained.pending_payload_bytes == len(original_payload)
    second_result = port.read("track")
    canonical = second_result[0]
    assert canonical is not outward
    assert canonical.connection is not outward.connection
    assert canonical == MediaFrame(connection, "track", 0, original_payload)
    assert canonical.connection.connection_epoch == 2
    assert port.payload_lifecycle_snapshot().delivered_frames == 1
    closed = port.close()
    assert closed.dropped_frames == 1
    assert closed.dropped_payload_bytes == len(original_payload)
    final = port.payload_lifecycle_snapshot()
    assert final.dropped_frames == 1
    assert final.dropped_payload_bytes == len(original_payload)
    assert final.pending_frames == 0
    assert final.pending_payload_bytes == 0
    for diagnostic in (outward, first_result, second_result, retained, closed, final):
        assert mutated_payload.decode() not in repr(diagnostic)


def test_media_port_exposes_no_conversation_lifecycle() -> None:
    port = RealtimeMediaPort(ConnectionEpochRef("connection-1", 0))
    assert not hasattr(port, "interaction_state")
    assert not hasattr(port, "turn_state")
    assert not hasattr(port, "response_state")


def test_ack_cannot_discard_a_frame_that_was_not_read() -> None:
    connection = ConnectionEpochRef("connection-1", 0)
    port = RealtimeMediaPort(connection)
    port.enqueue(MediaFrame(connection, "track", 0, b"audio"))
    with pytest.raises(RealtimeMediaViolation) as raised:
        port.acknowledge(MediaAck(connection, "track", 0))
    assert raised.value.reason == "INVALID_MEDIA_ACK"
    assert port.pending("track") == 1


@pytest.mark.parametrize(
    "ack",
    [
        MediaAck(ConnectionEpochRef("connection-1", 0), "", 0),
        MediaAck(ConnectionEpochRef("connection-1", 0), "track", -1),
        MediaAck(ConnectionEpochRef("connection-1", 0), "track", True),
    ],
)
def test_invalid_ack_is_rejected_without_payload_release(ack: MediaAck) -> None:
    connection = ConnectionEpochRef("connection-1", 0)
    port = RealtimeMediaPort(connection)
    port.enqueue(MediaFrame(connection, "track", 0, b"audio"))
    port.read("track")

    with pytest.raises(RealtimeMediaViolation) as raised:
        port.acknowledge(ack)

    assert raised.value.reason in {"INVALID_TRACK_ID", "INVALID_MEDIA_ACK"}
    assert port.pending("track") == 1
    snapshot = port.payload_lifecycle_snapshot()
    assert snapshot.acknowledged_frames == 0
    assert snapshot.acknowledged_payload_bytes == 0


def test_duplicate_ack_and_close_retry_have_zero_additional_effect() -> None:
    connection = ConnectionEpochRef("connection-1", 0)
    port = RealtimeMediaPort(connection)
    port.enqueue(MediaFrame(connection, "track", 0, b"acknowledged"))
    port.enqueue(MediaFrame(connection, "track", 1, b"dropped"))
    port.read("track", limit=1)

    assert port.acknowledge(MediaAck(connection, "track", 0)) == 1
    assert port.acknowledge(MediaAck(connection, "track", 0)) == 0
    closed = port.close()
    replay = port.close()

    assert closed.was_active is True
    assert closed.dropped_frames == 1
    assert closed.dropped_payload_bytes == len(b"dropped")
    assert closed.business_cancel_count_delta == 0
    assert replay.was_active is False
    assert replay.dropped_frames == 0
    assert replay.dropped_payload_bytes == 0
    assert replay.business_cancel_count_delta == 0
    snapshot = port.payload_lifecycle_snapshot()
    assert snapshot.closed is True
    assert snapshot.accepted_frames == 2
    assert snapshot.acknowledged_frames == 1
    assert snapshot.dropped_frames == 1
    assert snapshot.pending_frames == 0
    assert snapshot.pending_payload_bytes == 0
    with pytest.raises(RealtimeMediaViolation) as late_enqueue:
        port.enqueue(MediaFrame(connection, "track", 2, b"late"))
    assert late_enqueue.value.reason == "MEDIA_PORT_CLOSED"
    with pytest.raises(RealtimeMediaViolation) as late_read:
        port.read("track")
    assert late_read.value.reason == "MEDIA_PORT_CLOSED"
    with pytest.raises(RealtimeMediaViolation) as late_ack:
        port.acknowledge(MediaAck(connection, "track", 1))
    assert late_ack.value.reason == "MEDIA_PORT_CLOSED"


def test_close_waits_for_inflight_enqueue_then_drops_its_payload() -> None:
    connection = ConnectionEpochRef("connection-1", 0)
    port = RealtimeMediaPort(connection)
    validation_entered = threading.Event()
    release_validation = threading.Event()
    close_started = threading.Event()
    original_validate = port._validate_frame

    def blocked_validate(frame: MediaFrame) -> object:
        retained_frame = original_validate(frame)
        validation_entered.set()
        assert release_validation.wait(timeout=2)
        return retained_frame

    def close_after_signal() -> MediaPortCloseResult:
        close_started.set()
        return port.close()

    port._validate_frame = blocked_validate  # type: ignore[method-assign]
    with ThreadPoolExecutor(max_workers=2) as executor:
        enqueue_future = executor.submit(
            port.enqueue, MediaFrame(connection, "track", 0, b"concurrent")
        )
        assert validation_entered.wait(timeout=2)
        close_future = executor.submit(close_after_signal)
        assert close_started.wait(timeout=2)
        assert close_future.done() is False
        release_validation.set()
        enqueue_future.result(timeout=2)
        closed = close_future.result(timeout=2)

    assert closed.was_active is True
    assert closed.dropped_frames == 1
    assert closed.dropped_payload_bytes == len(b"concurrent")
    snapshot = port.payload_lifecycle_snapshot()
    assert snapshot.closed is True
    assert snapshot.accepted_frames == 1
    assert snapshot.dropped_frames == 1
    assert snapshot.pending_frames == 0


def test_payload_audit_hook_is_leaf_only_payload_free_and_does_not_touch_disk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effects = {"persistence": 0}
    marker = b"raw-audio-persistence-sentinel-93c765"
    connection = ConnectionEpochRef("connection-1", 0)
    port = RealtimeMediaPort(connection)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        effects["persistence"] += 1
        raise AssertionError("the realtime media leaf must not persist payloads")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(json, "dumps", forbidden)
    monkeypatch.setattr(logging.Logger, "_log", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)

    port.enqueue(MediaFrame(connection, "track", 0, marker))
    assert port.read("track")[0].payload == marker
    assert port.acknowledge(MediaAck(connection, "track", 0)) == 1
    port.close()
    snapshot = port.payload_lifecycle_snapshot()

    assert effects == {"persistence": 0}
    assert type(snapshot) is MediaPayloadLifecycleSnapshot
    assert snapshot.evidence_scope == "realtime_media_leaf_only"
    assert snapshot.snapshot_contains_raw_payload is False
    assert snapshot.registered_route_observed is False
    assert snapshot.route_to_disk_zero_persistence_observed is False
    assert marker.decode() not in repr(snapshot)
    assert "payload" not in {item.name for item in fields(snapshot)}


def test_raw_payload_is_redacted_from_all_diagnostic_representations() -> None:
    marker = b"raw-audio-repr-sentinel-a4f07d"
    marker_text = marker.decode()
    connection = ConnectionEpochRef("connection-1", 0)
    port = RealtimeMediaPort(connection, capacity=1, allowed_track_id="track")
    frame = MediaFrame(connection, "track", 0, marker)

    port.enqueue(frame)
    result = port.read("track")
    with pytest.raises(RealtimeMediaViolation) as raised:
        port.enqueue(MediaFrame(connection, "track", 1, marker))
    snapshot = port.payload_lifecycle_snapshot()
    close_result = port.close()

    for diagnostic in (frame, result, raised.value, snapshot, close_result):
        assert marker_text not in repr(diagnostic)


def test_registration_owner_positive_journey_emits_only_payload_free_leaf_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = b"registration-owner-raw-audio-sentinel"
    persistence_effects = 0
    facts: list[RealtimeMediaLeafAuditFact] = []

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal persistence_effects
        persistence_effects += 1
        raise AssertionError("Media registration leaf must not persist payloads")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(json, "dumps", forbidden)
    monkeypatch.setattr(logging.Logger, "_log", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    activation = create_realtime_media_activation(
        RealtimeMediaActivationRequest(
            enabled=True,
            binding=_authority_binding(),
            provider_available=True,
            transport_available=True,
        ),
        on_audit_fact=facts.append,
    )

    assert type(activation) is ActiveRealtimeMediaActivation
    connection = ConnectionEpochRef("connection-1", 3)
    activation.owner.enqueue(MediaFrame(connection, "track-1", 0, marker))
    assert activation.owner.read("track-1")[0].payload == marker
    assert activation.owner.acknowledge(MediaAck(connection, "track-1", 0)) == 1
    first_close = activation.owner.close()
    replay_close = activation.owner.close()

    assert replay_close is first_close
    assert first_close.business_cancel_count_delta == 0
    assert persistence_effects == 0
    assert facts == []
    assert activation.owner.pending_audit_facts == 5
    assert activation.owner.drain_audit_facts(limit=32) == 5
    assert [fact.event for fact in facts] == [
        "activation.ready",
        "frame.accepted",
        "frame.delivered",
        "frame.acknowledged",
        "activation.closed",
    ]
    final = facts[-1]
    assert final.closed is True
    assert final.lease_id == "lease-1"
    assert final.connection_epoch == 3
    assert final.track_id == "track-1"
    assert final.correlation_id == "correlation-1"
    assert final.generation_id == "capture-1"
    assert final.fact_contains_raw_payload is False
    assert final.registered_route_observed is False
    assert final.formal_route_ready is False
    assert final.route_to_disk_zero_persistence_observed is False
    assert final.business_cancel_count_delta == 0
    assert marker.decode() not in repr(facts)
    assert not any(
        "payload" in item.name
        and item.name
        not in {
            "accepted_payload_bytes",
            "delivered_payload_bytes",
            "acknowledged_payload_bytes",
            "dropped_payload_bytes",
            "pending_payload_bytes",
            "fact_contains_raw_payload",
        }
        for item in fields(RealtimeMediaLeafAuditFact)
    )


def test_feature_off_returns_before_binding_callback_or_owner_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allocations = 0

    class ForbiddenOwner:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            nonlocal allocations
            allocations += 1
            raise AssertionError("feature-off allocated a registration owner")

    monkeypatch.setattr(
        realtime_media_module, "RealtimeMediaRegistrationOwner", ForbiddenOwner
    )
    activation = create_realtime_media_activation(
        RealtimeMediaActivationRequest(
            enabled=False,
            binding=object(),  # type: ignore[arg-type]
            provider_available=object(),  # type: ignore[arg-type]
            transport_available=object(),  # type: ignore[arg-type]
            audit_capacity=object(),  # type: ignore[arg-type]
        ),
        on_audit_fact=object(),  # type: ignore[arg-type]
    )

    assert type(activation) is InactiveRealtimeMediaActivation
    assert activation.reason_id == "MEDIA_FEATURE_DISABLED"
    assert allocations == 0
    assert not hasattr(activation, "owner")
    assert activation.registered_route_observed is False
    assert activation.formal_route_ready is False
    assert activation.route_to_disk_zero_persistence_observed is False


@pytest.mark.parametrize(
    ("provider_available", "transport_available", "reason_id"),
    [
        (False, True, "MEDIA_PROVIDER_UNAVAILABLE"),
        (True, False, "MEDIA_TRANSPORT_UNAVAILABLE"),
    ],
)
def test_dependency_unavailable_has_zero_owner_and_audit_effect(
    monkeypatch: pytest.MonkeyPatch,
    provider_available: bool,
    transport_available: bool,
    reason_id: str,
) -> None:
    effects = {"owner": 0, "audit": 0}

    class ForbiddenOwner:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            effects["owner"] += 1
            raise AssertionError("unavailable dependency allocated an owner")

    monkeypatch.setattr(
        realtime_media_module, "RealtimeMediaRegistrationOwner", ForbiddenOwner
    )
    activation = create_realtime_media_activation(
        RealtimeMediaActivationRequest(
            enabled=True,
            binding=_authority_binding(),
            provider_available=provider_available,
            transport_available=transport_available,
            audit_capacity=object(),  # type: ignore[arg-type]
        ),
        on_audit_fact=lambda _fact: effects.__setitem__("audit", effects["audit"] + 1),
    )

    assert type(activation) is InactiveRealtimeMediaActivation
    assert activation.reason_id == reason_id
    assert effects == {"owner": 0, "audit": 0}


def test_registration_owner_retains_canonical_binding_and_rejects_late_mismatch() -> (
    None
):
    submitted = _authority_binding(direction=MediaDirection.DOWNLINK)
    facts: list[RealtimeMediaLeafAuditFact] = []
    activation = create_realtime_media_activation(
        RealtimeMediaActivationRequest(True, submitted, True, True),
        on_audit_fact=facts.append,
    )
    assert type(activation) is ActiveRealtimeMediaActivation
    object.__setattr__(submitted, "connection_epoch", 99)
    object.__setattr__(submitted, "correlation_id", "mutated-correlation")
    object.__setattr__(submitted.playout, "unit_id", "mutated-unit")
    before = activation.owner.payload_lifecycle_snapshot()

    with pytest.raises(RealtimeMediaViolation) as wrong_epoch:
        activation.owner.enqueue(
            MediaFrame(ConnectionEpochRef("connection-1", 99), "track-1", 0, b"x")
        )
    with pytest.raises(RealtimeMediaViolation) as wrong_track:
        activation.owner.enqueue(
            MediaFrame(ConnectionEpochRef("connection-1", 3), "wrong-track", 0, b"x")
        )

    assert wrong_epoch.value.reason == "CONNECTION_EPOCH_MISMATCH"
    assert wrong_track.value.reason == "MEDIA_TRACK_MISMATCH"
    assert activation.owner.payload_lifecycle_snapshot() == before
    retained = activation.owner.audit_snapshot()
    assert retained.connection_epoch == 3
    assert retained.correlation_id == "correlation-1"
    assert retained.response_id == "response-1"
    assert retained.response_generation == 7
    assert retained.unit_id == "unit-1"
    assert facts == []
    assert activation.owner.drain_audit_facts(limit=1) == 1
    assert [fact.event for fact in facts] == ["activation.ready"]

    activation.owner.close()
    with pytest.raises(RealtimeMediaViolation) as late:
        activation.owner.enqueue(
            MediaFrame(ConnectionEpochRef("connection-1", 3), "track-1", 0, b"late")
        )
    assert late.value.reason == "MEDIA_PORT_CLOSED"
    assert activation.owner.audit_snapshot().accepted_frames == 0


def test_audit_callback_runs_only_during_an_explicit_bounded_drain() -> None:
    calls = 0

    def failing_callback(_fact: RealtimeMediaLeafAuditFact) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("private audit failure")

    activation = create_realtime_media_activation(
        RealtimeMediaActivationRequest(True, _authority_binding(), True, True),
        on_audit_fact=failing_callback,
    )
    assert type(activation) is ActiveRealtimeMediaActivation
    connection = ConnectionEpochRef("connection-1", 3)
    activation.owner.enqueue(MediaFrame(connection, "track-1", 0, b"audio"))
    activation.owner.read("track-1")
    activation.owner.acknowledge(MediaAck(connection, "track-1", 0))
    closed = activation.owner.close()

    assert calls == 0
    assert activation.owner.audit_delivery_failures == 0
    assert activation.owner.pending_audit_facts == 5
    assert activation.owner.drain_audit_facts(limit=2) == 2
    assert calls == 2
    assert activation.owner.audit_delivery_failures == 2
    assert activation.owner.pending_audit_facts == 3
    assert activation.owner.drain_audit_facts(limit=10) == 3
    assert calls == 5
    assert activation.owner.audit_delivery_failures == 5
    assert activation.owner.audit_snapshot().audit_delivery_failures == 5
    assert closed.business_cancel_count_delta == 0
    assert activation.formal_route_ready is False
    assert activation.route_to_disk_zero_persistence_observed is False


def test_audit_lane_is_fixed_capacity_and_blocking_consumer_cannot_freeze_cleanup() -> (
    None
):
    callback_entered = threading.Event()
    callback_release = threading.Event()

    def blocking_consumer(_fact: RealtimeMediaLeafAuditFact) -> None:
        callback_entered.set()
        callback_release.wait(timeout=5)

    activation = create_realtime_media_activation(
        RealtimeMediaActivationRequest(
            True,
            _authority_binding(),
            True,
            True,
            audit_capacity=2,
        ),
        on_audit_fact=blocking_consumer,
    )
    assert type(activation) is ActiveRealtimeMediaActivation
    connection = ConnectionEpochRef("connection-1", 3)
    activation.owner.enqueue(MediaFrame(connection, "track-1", 0, b"audio"))
    activation.owner.read("track-1")
    first_close = activation.owner.close()
    replay_close = activation.owner.close()
    snapshot = activation.owner.audit_snapshot()

    assert replay_close is first_close
    assert callback_entered.is_set() is False
    assert activation.owner.pending_audit_facts == 2
    assert activation.owner.dropped_audit_facts == 2
    assert snapshot.pending_audit_facts == 2
    assert snapshot.dropped_audit_facts == 2
    assert snapshot.fact_contains_raw_payload is False
    assert snapshot.registered_route_observed is False
    assert snapshot.formal_route_ready is False
    assert snapshot.route_to_disk_zero_persistence_observed is False
    assert first_close.business_cancel_count_delta == 0


def test_explicit_blocking_audit_drain_does_not_hold_owner_lock_or_freeze_close() -> (
    None
):
    callback_entered = threading.Event()
    callback_release = threading.Event()

    def blocking_consumer(_fact: RealtimeMediaLeafAuditFact) -> None:
        callback_entered.set()
        callback_release.wait(timeout=5)

    activation = create_realtime_media_activation(
        RealtimeMediaActivationRequest(True, _authority_binding(), True, True),
        on_audit_fact=blocking_consumer,
    )
    assert type(activation) is ActiveRealtimeMediaActivation

    with ThreadPoolExecutor(max_workers=2) as executor:
        drain = executor.submit(activation.owner.drain_audit_facts, limit=1)
        assert callback_entered.wait(timeout=1)
        close = executor.submit(activation.owner.close)
        close_result = close.result(timeout=1)
        callback_release.set()
        assert drain.result(timeout=1) == 1

    assert close_result.business_cancel_count_delta == 0
    assert activation.owner.closed is True
    assert activation.owner.pending_audit_facts == 1


def test_registration_owner_cannot_be_constructed_outside_factory() -> None:
    with pytest.raises(RealtimeMediaViolation) as raised:
        RealtimeMediaRegistrationOwner(
            _authority_binding(),
            capacity=1,
            max_frame_payload_bytes=100,
            max_retained_payload_bytes=100,
            audit_capacity=1,
            on_audit_fact=None,
            construction_token=object(),
        )

    assert raised.value.reason == "MEDIA_ACTIVATION_FACTORY_REQUIRED"
