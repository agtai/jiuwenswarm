# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ConnectionEpochRef
from jiuwenswarm.server.live_voice.realtime_media import (
    MediaAck,
    MediaFrame,
    RealtimeMediaPort,
    RealtimeMediaViolation,
)


def test_bounded_queue_sequence_and_ack() -> None:
    connection = ConnectionEpochRef("connection-1", 2)
    port = RealtimeMediaPort(connection, capacity=2)
    port.enqueue(MediaFrame(connection, "track-1", 0, b"a"))
    port.enqueue(MediaFrame(connection, "track-1", 1, b"b"))
    assert [frame.payload for frame in port.read("track-1")] == [b"a", b"b"]
    with pytest.raises(RealtimeMediaViolation) as raised:
        port.enqueue(MediaFrame(connection, "track-1", 2, b"c"))
    assert raised.value.reason == "MEDIA_QUEUE_OVERFLOW"
    assert port.acknowledge(MediaAck(connection, "track-1", 0)) == 1
    assert port.pending("track-1") == 1


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
