# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded, conversation-neutral realtime media port."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import ConnectionEpochRef


class RealtimeMediaViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MediaFrame:
    connection: ConnectionEpochRef
    track_id: str
    seq: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class MediaAck:
    connection: ConnectionEpochRef
    track_id: str
    through_seq: int


class RealtimeMediaPort:
    def __init__(self, connection: ConnectionEpochRef, *, capacity: int = 32) -> None:
        if type(capacity) is not int or capacity <= 0:
            raise RealtimeMediaViolation(
                "INVALID_CAPACITY", "capacity must be a positive integer"
            )
        self._connection = connection
        self._capacity = capacity
        self._lock = threading.RLock()
        self._queues: dict[str, list[MediaFrame]] = {}
        self._last_seq: dict[str, int] = {}
        self._delivered: dict[str, int] = {}
        self._acked: dict[str, int] = {}

    def enqueue(self, frame: MediaFrame) -> None:
        with self._lock:
            self._validate_frame(frame)
            queue = self._queues.setdefault(frame.track_id, [])
            if len(queue) >= self._capacity:
                raise RealtimeMediaViolation(
                    "MEDIA_QUEUE_OVERFLOW", "bounded media queue is full"
                )
            expected = self._last_seq.get(frame.track_id, -1) + 1
            if frame.seq != expected:
                raise RealtimeMediaViolation(
                    "NON_CONTIGUOUS_MEDIA_SEQUENCE",
                    f"expected media sequence {expected}",
                )
            queue.append(frame)
            self._last_seq[frame.track_id] = frame.seq

    def read(
        self, track_id: str, *, limit: int | None = None
    ) -> tuple[MediaFrame, ...]:
        with self._lock:
            queue = self._queues.get(track_id, [])
            if limit is None:
                limit = len(queue)
            if type(limit) is not int or limit < 0:
                raise RealtimeMediaViolation(
                    "INVALID_LIMIT", "limit must be a non-negative integer"
                )
            selected = tuple(queue[:limit])
            if selected:
                self._delivered[track_id] = max(
                    self._delivered.get(track_id, -1), selected[-1].seq
                )
            return selected

    def acknowledge(self, ack: MediaAck) -> int:
        with self._lock:
            if ack.connection != self._connection:
                raise RealtimeMediaViolation(
                    "CONNECTION_EPOCH_MISMATCH",
                    "media acknowledgement belongs to another connection epoch",
                )
            queue = self._queues.get(ack.track_id, [])
            delivered = self._delivered.get(ack.track_id, -1)
            prior = self._acked.get(ack.track_id, -1)
            if ack.through_seq < prior or ack.through_seq > delivered:
                raise RealtimeMediaViolation(
                    "INVALID_MEDIA_ACK", "acknowledgement is stale or beyond delivery"
                )
            self._queues[ack.track_id] = [
                frame for frame in queue if frame.seq > ack.through_seq
            ]
            self._acked[ack.track_id] = ack.through_seq
            return len(queue) - len(self._queues[ack.track_id])

    def pending(self, track_id: str) -> int:
        with self._lock:
            return len(self._queues.get(track_id, []))

    def _validate_frame(self, frame: MediaFrame) -> None:
        if frame.connection != self._connection:
            raise RealtimeMediaViolation(
                "CONNECTION_EPOCH_MISMATCH",
                "media frame belongs to another connection epoch",
            )
        if not frame.track_id.strip():
            raise RealtimeMediaViolation(
                "INVALID_TRACK_ID", "track_id must be non-empty"
            )
        if type(frame.seq) is not int or frame.seq < 0:
            raise RealtimeMediaViolation(
                "INVALID_MEDIA_SEQUENCE", "media sequence must be non-negative"
            )
        if type(frame.payload) is not bytes or not frame.payload:
            raise RealtimeMediaViolation(
                "INVALID_MEDIA_PAYLOAD", "media payload must be non-empty bytes"
            )
