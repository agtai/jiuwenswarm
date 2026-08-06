# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded, conversation-neutral realtime media port."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import cast

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ConnectionEpochRef,
    ContractViolation,
)


class RealtimeMediaViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MediaFrame:
    connection: ConnectionEpochRef
    track_id: str
    seq: int
    payload: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class _RetainedMediaFrame:
    connection: ConnectionEpochRef
    track_id: str
    seq: int
    payload: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class MediaAck:
    connection: ConnectionEpochRef
    track_id: str
    through_seq: int


@dataclass(frozen=True, slots=True)
class MediaPortCloseResult:
    was_active: bool
    dropped_frames: int
    dropped_payload_bytes: int
    business_cancel_count_delta: int = field(default=0, init=False)


@dataclass(frozen=True, slots=True)
class MediaPayloadLifecycleSnapshot:
    """Payload-free RM leaf facts for a future route persistence audit.

    This snapshot proves only bounded in-memory ownership in this leaf.  It
    deliberately cannot claim that a product route was registered or that a
    socket, consumer, logger, or another process did not persist the payload.
    """

    closed: bool
    accepted_frames: int
    accepted_payload_bytes: int
    delivered_frames: int
    delivered_payload_bytes: int
    acknowledged_frames: int
    acknowledged_payload_bytes: int
    dropped_frames: int
    dropped_payload_bytes: int
    pending_frames: int
    pending_payload_bytes: int
    evidence_scope: str = field(default="realtime_media_leaf_only", init=False)
    snapshot_contains_raw_payload: bool = field(default=False, init=False)
    registered_route_observed: bool = field(default=False, init=False)
    route_to_disk_zero_persistence_observed: bool = field(default=False, init=False)


class RealtimeMediaPort:
    # 20 ms of mono pcm_f32 at the media contract's 192 kHz ceiling.
    _DEFAULT_MAX_FRAME_PAYLOAD_BYTES = 15_360

    def __init__(
        self,
        connection: ConnectionEpochRef,
        *,
        capacity: int = 32,
        allowed_track_id: str | None = None,
        max_frame_payload_bytes: int = _DEFAULT_MAX_FRAME_PAYLOAD_BYTES,
        max_retained_payload_bytes: int | None = None,
    ) -> None:
        canonical_connection = self._canonicalize_connection_ref(
            connection,
            reason="INVALID_CONNECTION_EPOCH_REF",
            field_name="connection",
        )
        if type(capacity) is not int or capacity <= 0:
            raise RealtimeMediaViolation(
                "INVALID_CAPACITY", "capacity must be a positive integer"
            )
        if allowed_track_id is not None:
            self._validate_track_id(allowed_track_id)
        if type(max_frame_payload_bytes) is not int or max_frame_payload_bytes <= 0:
            raise RealtimeMediaViolation(
                "INVALID_PAYLOAD_BOUND",
                "max_frame_payload_bytes must be a positive integer",
            )
        if max_retained_payload_bytes is None:
            max_retained_payload_bytes = capacity * max_frame_payload_bytes
        if (
            type(max_retained_payload_bytes) is not int
            or max_retained_payload_bytes <= 0
        ):
            raise RealtimeMediaViolation(
                "INVALID_PAYLOAD_BOUND",
                "max_retained_payload_bytes must be a positive integer",
            )
        self._connection = canonical_connection
        self._capacity = capacity
        self._allowed_track_id = allowed_track_id
        self._max_frame_payload_bytes = max_frame_payload_bytes
        self._max_retained_payload_bytes = max_retained_payload_bytes
        self._lock = threading.RLock()
        self._queues: dict[str, list[_RetainedMediaFrame]] = {}
        self._last_seq: dict[str, int] = {}
        self._delivered: dict[str, int] = {}
        self._acked: dict[str, int] = {}
        self._closed = False
        self._accepted_frames = 0
        self._accepted_payload_bytes = 0
        self._delivered_frames = 0
        self._delivered_payload_bytes = 0
        self._acknowledged_frames = 0
        self._acknowledged_payload_bytes = 0
        self._dropped_frames = 0
        self._dropped_payload_bytes = 0
        self._retained_frames = 0
        self._retained_payload_bytes = 0

    def enqueue(self, frame: MediaFrame) -> None:
        with self._lock:
            self._require_open()
            retained_frame = self._validate_frame(frame)
            self._require_allowed_track(retained_frame.track_id, bind_if_unset=False)
            if self._retained_frames >= self._capacity:
                raise RealtimeMediaViolation(
                    "MEDIA_QUEUE_OVERFLOW", "bounded media queue is full"
                )
            payload_bytes = len(retained_frame.payload)
            if (
                self._retained_payload_bytes + payload_bytes
                > self._max_retained_payload_bytes
            ):
                raise RealtimeMediaViolation(
                    "MEDIA_PAYLOAD_CAPACITY_EXCEEDED",
                    "aggregate retained media payload capacity would be exceeded",
                )
            expected = self._last_seq.get(retained_frame.track_id, -1) + 1
            if retained_frame.seq != expected:
                raise RealtimeMediaViolation(
                    "NON_CONTIGUOUS_MEDIA_SEQUENCE",
                    f"expected media sequence {expected}",
                )
            self._require_allowed_track(retained_frame.track_id, bind_if_unset=True)
            self._queues.setdefault(retained_frame.track_id, []).append(retained_frame)
            self._last_seq[retained_frame.track_id] = retained_frame.seq
            self._accepted_frames += 1
            self._accepted_payload_bytes += payload_bytes
            self._retained_frames += 1
            self._retained_payload_bytes += payload_bytes

    def read(
        self, track_id: str, *, limit: int | None = None
    ) -> tuple[MediaFrame, ...]:
        with self._lock:
            self._require_open()
            self._validate_track_id(track_id)
            self._require_allowed_track(track_id, bind_if_unset=False)
            queue = self._queues.get(track_id, [])
            if limit is None:
                limit = len(queue)
            if type(limit) is not int or limit < 0:
                raise RealtimeMediaViolation(
                    "INVALID_LIMIT", "limit must be a non-negative integer"
                )
            selected_records = tuple(queue[:limit])
            if selected_records:
                prior = self._delivered.get(track_id, -1)
                newly_delivered = tuple(
                    frame for frame in selected_records if frame.seq > prior
                )
                self._delivered[track_id] = max(prior, selected_records[-1].seq)
                self._delivered_frames += len(newly_delivered)
                self._delivered_payload_bytes += sum(
                    len(frame.payload) for frame in newly_delivered
                )
            return tuple(self._snapshot_frame(frame) for frame in selected_records)

    def acknowledge(self, ack: MediaAck) -> int:
        with self._lock:
            self._require_open()
            if type(ack) is not MediaAck:
                raise RealtimeMediaViolation(
                    "INVALID_MEDIA_ACK", "acknowledgement must be typed"
                )
            canonical_ack_connection = self._canonicalize_connection_ref(
                ack.connection,
                reason="INVALID_MEDIA_ACK",
                field_name="ack.connection",
            )
            if not self._same_connection(canonical_ack_connection, self._connection):
                raise RealtimeMediaViolation(
                    "CONNECTION_EPOCH_MISMATCH",
                    "media acknowledgement belongs to another connection epoch",
                )
            self._validate_track_id(ack.track_id)
            self._require_allowed_track(ack.track_id, bind_if_unset=False)
            if type(ack.through_seq) is not int or ack.through_seq < 0:
                raise RealtimeMediaViolation(
                    "INVALID_MEDIA_ACK",
                    "acknowledgement sequence must be a non-negative integer",
                )
            queue = self._queues.get(ack.track_id, [])
            delivered = self._delivered.get(ack.track_id, -1)
            prior = self._acked.get(ack.track_id, -1)
            if ack.through_seq < prior or ack.through_seq > delivered:
                raise RealtimeMediaViolation(
                    "INVALID_MEDIA_ACK", "acknowledgement is stale or beyond delivery"
                )
            acknowledged = [frame for frame in queue if frame.seq <= ack.through_seq]
            acknowledged_payload_bytes = sum(
                len(frame.payload) for frame in acknowledged
            )
            self._queues[ack.track_id] = [
                frame for frame in queue if frame.seq > ack.through_seq
            ]
            self._acked[ack.track_id] = ack.through_seq
            self._acknowledged_frames += len(acknowledged)
            self._acknowledged_payload_bytes += acknowledged_payload_bytes
            self._retained_frames -= len(acknowledged)
            self._retained_payload_bytes -= acknowledged_payload_bytes
            return len(acknowledged)

    def pending(self, track_id: str) -> int:
        with self._lock:
            self._validate_track_id(track_id)
            self._require_allowed_track(track_id, bind_if_unset=False)
            return len(self._queues.get(track_id, []))

    def close(self) -> MediaPortCloseResult:
        """Fence the leaf and release every retained payload reference.

        Repeated close is a zero-effect cleanup retry.  Closing this transport
        leaf never widens into a response, round, or task cancellation.
        """

        with self._lock:
            if self._closed:
                return MediaPortCloseResult(
                    was_active=False,
                    dropped_frames=0,
                    dropped_payload_bytes=0,
                )
            self._closed = True
            dropped_frames = sum(len(queue) for queue in self._queues.values())
            dropped_payload_bytes = sum(
                len(frame.payload) for queue in self._queues.values() for frame in queue
            )
            self._dropped_frames += dropped_frames
            self._dropped_payload_bytes += dropped_payload_bytes
            self._retained_frames = 0
            self._retained_payload_bytes = 0
            self._queues.clear()
            self._last_seq.clear()
            self._delivered.clear()
            self._acked.clear()
            return MediaPortCloseResult(
                was_active=True,
                dropped_frames=dropped_frames,
                dropped_payload_bytes=dropped_payload_bytes,
            )

    def payload_lifecycle_snapshot(self) -> MediaPayloadLifecycleSnapshot:
        """Return content-free leaf counters without upgrading product truth."""

        with self._lock:
            return MediaPayloadLifecycleSnapshot(
                closed=self._closed,
                accepted_frames=self._accepted_frames,
                accepted_payload_bytes=self._accepted_payload_bytes,
                delivered_frames=self._delivered_frames,
                delivered_payload_bytes=self._delivered_payload_bytes,
                acknowledged_frames=self._acknowledged_frames,
                acknowledged_payload_bytes=self._acknowledged_payload_bytes,
                dropped_frames=self._dropped_frames,
                dropped_payload_bytes=self._dropped_payload_bytes,
                pending_frames=self._retained_frames,
                pending_payload_bytes=self._retained_payload_bytes,
            )

    def _require_open(self) -> None:
        if self._closed:
            raise RealtimeMediaViolation(
                "MEDIA_PORT_CLOSED", "realtime media port is closed"
            )

    @staticmethod
    def _validate_track_id(track_id: object) -> None:
        if type(track_id) is not str or not track_id.strip():
            raise RealtimeMediaViolation(
                "INVALID_TRACK_ID", "track_id must be non-empty"
            )

    def _require_allowed_track(self, track_id: str, *, bind_if_unset: bool) -> None:
        if self._allowed_track_id is None:
            if bind_if_unset:
                self._allowed_track_id = track_id
            return
        if track_id != self._allowed_track_id:
            raise RealtimeMediaViolation(
                "MEDIA_TRACK_MISMATCH",
                "track_id does not match the port's admitted track",
            )

    @staticmethod
    def _canonicalize_connection_ref(
        connection: object, *, reason: str, field_name: str
    ) -> ConnectionEpochRef:
        if type(connection) is not ConnectionEpochRef:
            raise RealtimeMediaViolation(
                reason, f"{field_name} must be an exact ConnectionEpochRef"
            )
        typed_connection = cast(ConnectionEpochRef, connection)
        try:
            return ConnectionEpochRef.from_dict(  # type: ignore[attr-defined,no-any-return]
                typed_connection.to_dict()
            )
        except ContractViolation as exc:
            raise RealtimeMediaViolation(
                reason, f"{field_name} is not canonical ({exc.reason})"
            ) from exc

    @staticmethod
    def _same_connection(left: ConnectionEpochRef, right: ConnectionEpochRef) -> bool:
        return (
            left.connection_id == right.connection_id
            and left.connection_epoch == right.connection_epoch
        )

    @staticmethod
    def _snapshot_frame(frame: _RetainedMediaFrame) -> MediaFrame:
        return MediaFrame(
            connection=ConnectionEpochRef(
                connection_id=frame.connection.connection_id,
                connection_epoch=frame.connection.connection_epoch,
            ),
            track_id=frame.track_id,
            seq=frame.seq,
            payload=memoryview(frame.payload).tobytes(),
        )

    def _validate_frame(self, frame: MediaFrame) -> _RetainedMediaFrame:
        if type(frame) is not MediaFrame:
            raise RealtimeMediaViolation(
                "INVALID_MEDIA_FRAME", "media frame must be typed"
            )
        submitted_connection = frame.connection
        submitted_track_id = frame.track_id
        submitted_seq = frame.seq
        submitted_payload = frame.payload
        canonical_frame_connection = self._canonicalize_connection_ref(
            submitted_connection,
            reason="INVALID_MEDIA_FRAME",
            field_name="frame.connection",
        )
        if not self._same_connection(canonical_frame_connection, self._connection):
            raise RealtimeMediaViolation(
                "CONNECTION_EPOCH_MISMATCH",
                "media frame belongs to another connection epoch",
            )
        self._validate_track_id(submitted_track_id)
        if type(submitted_seq) is not int or submitted_seq < 0:
            raise RealtimeMediaViolation(
                "INVALID_MEDIA_SEQUENCE", "media sequence must be non-negative"
            )
        if type(submitted_payload) is not bytes or not submitted_payload:
            raise RealtimeMediaViolation(
                "INVALID_MEDIA_PAYLOAD", "media payload must be non-empty bytes"
            )
        if len(submitted_payload) > self._max_frame_payload_bytes:
            raise RealtimeMediaViolation(
                "MEDIA_FRAME_PAYLOAD_TOO_LARGE",
                "media frame payload exceeds the per-frame byte bound",
            )
        return _RetainedMediaFrame(
            connection=canonical_frame_connection,
            track_id=submitted_track_id,
            seq=submitted_seq,
            payload=memoryview(submitted_payload).tobytes(),
        )
