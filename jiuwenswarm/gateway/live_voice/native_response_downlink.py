# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded response-scoped Native audio source for dedicated media.

The source is a Gateway data-plane carrier only.  Runtime still authors every
presentation unit before its matching frame can be appended.  Raw PCM is used
only to advance an incremental response digest and is never retained here.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import hashlib
import re

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame,
    MediaTransportViolation,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


@dataclass(frozen=True, slots=True)
class NativeDownlinkPresentationUnit:
    """Content-hidden mapping from one browser frame to one Runtime unit."""

    response: ResponseRef
    unit_id: str
    unit_seq: int
    provider_item_id: str
    content_index: int
    source_start_sample: int
    source_end_sample: int
    content_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.response, ResponseRef):
            self._invalid("response is not typed")
        for name, text_value in (
            ("unit_id", self.unit_id),
            ("provider_item_id", self.provider_item_id),
        ):
            if (
                not isinstance(text_value, str)
                or not text_value
                or text_value != text_value.strip()
            ):
                self._invalid(f"{name} is invalid")
        for name, integer_value in (
            ("unit_seq", self.unit_seq),
            ("content_index", self.content_index),
            ("source_start_sample", self.source_start_sample),
            ("source_end_sample", self.source_end_sample),
        ):
            if (
                type(integer_value) is not int
                or not 0 <= integer_value <= _MAX_SAFE_INTEGER
            ):
                self._invalid(f"{name} is invalid")
        if self.source_end_sample <= self.source_start_sample:
            self._invalid("source span is empty")
        if not isinstance(self.content_sha256, str) or _SHA256.fullmatch(
            self.content_sha256
        ) is None:
            self._invalid("content digest is invalid")

    @staticmethod
    def _invalid(message: str) -> None:
        raise MediaTransportViolation(
            "MEDIA_NATIVE_STREAM_UNIT_INVALID", message
        )


class NativeResponseDownlinkSource:
    """One exact bounded async source for a complete Native response."""

    def __init__(
        self,
        *,
        response: ResponseRef,
        sample_rate_hz: int,
        capacity: int,
        max_frames: int,
        append_timeout_seconds: float = 3.0,
    ) -> None:
        if not isinstance(response, ResponseRef):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_STREAM_RESPONSE_INVALID",
                "Native stream response is not typed",
            )
        if (
            type(sample_rate_hz) is not int
            or sample_rate_hz <= 0
            or sample_rate_hz % 50
            or type(capacity) is not int
            or not 0 < capacity <= 256
            or type(max_frames) is not int
            or not 0 < max_frames <= 9_000
            or isinstance(append_timeout_seconds, bool)
            or not isinstance(append_timeout_seconds, (int, float))
            or not 0 < float(append_timeout_seconds) <= 30.0
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_STREAM_LIMIT_INVALID",
                "Native stream limits are invalid",
            )
        self.response = response
        self.sample_rate_hz = sample_rate_hz
        self.capacity = capacity
        self.max_frames = max_frames
        self.append_timeout_seconds = float(append_timeout_seconds)
        self.completed = False
        self.emitted_frames = 0
        self.appended_frames = 0
        self.peak_buffered_frames = 0
        self._condition = asyncio.Condition()
        self._frames: deque[MediaAudioFrame] = deque()
        self._units: dict[int, NativeDownlinkPresentationUnit] = {}
        self._digest = hashlib.sha256()
        self._sealed = False
        self._closed = False

    def __aiter__(self) -> NativeResponseDownlinkSource:
        return self

    @property
    def buffered_frames(self) -> int:
        return len(self._frames)

    @property
    def content_sha256(self) -> str:
        return self._digest.hexdigest()

    @property
    def sealed(self) -> bool:
        return self._sealed

    @property
    def closed(self) -> bool:
        return self._closed

    def unit_for_media_sequence(
        self, sequence: int
    ) -> NativeDownlinkPresentationUnit | None:
        return self._units.get(sequence)

    async def append(
        self,
        frame: MediaAudioFrame,
        unit: NativeDownlinkPresentationUnit,
        *,
        pcm16: bytes,
    ) -> None:
        if not isinstance(frame, MediaAudioFrame) or not isinstance(
            unit, NativeDownlinkPresentationUnit
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_STREAM_FRAME_INVALID",
                "Native stream append requires typed frame and unit",
            )
        if unit.response != self.response:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_STREAM_RESPONSE_MISMATCH",
                "Native stream unit response does not match the source response",
            )
        if (
            type(pcm16) is not bytes
            or len(pcm16) != 960
            or hashlib.sha256(pcm16).hexdigest() != unit.content_sha256
            or unit.source_end_sample - unit.source_start_sample != 480
        ):
            raise MediaTransportViolation(
                "MEDIA_NATIVE_STREAM_FRAME_INVALID",
                "Native stream requires one exact admitted 20 ms Provider frame",
            )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.append_timeout_seconds
        async with self._condition:
            while len(self._frames) >= self.capacity and not (
                self._closed or self._sealed
            ):
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise MediaTransportViolation(
                        "MEDIA_NATIVE_STREAM_BACKPRESSURE_TIMEOUT",
                        "Native response source remained saturated",
                    )
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    raise MediaTransportViolation(
                        "MEDIA_NATIVE_STREAM_BACKPRESSURE_TIMEOUT",
                        "Native response source remained saturated",
                    ) from None
            if self._closed:
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_STREAM_CLOSED", "Native response source is closed"
                )
            if self._sealed:
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_STREAM_SEALED", "Native response source is sealed"
                )
            expected_sequence = self.appended_frames
            expected_cursor = expected_sequence * (self.sample_rate_hz // 50)
            if (
                frame.seq != expected_sequence
                or frame.sample_cursor != expected_cursor
                or len(frame.samples) != self.sample_rate_hz // 50
                or unit.unit_seq != expected_sequence
                or unit.source_start_sample != expected_sequence * 480
                or expected_sequence >= self.max_frames
            ):
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_STREAM_SEQUENCE_INVALID",
                    "Native response frame is stale, non-contiguous, or over capacity",
                )
            self._frames.append(frame)
            self._units[expected_sequence] = unit
            self._digest.update(pcm16)
            self.appended_frames += 1
            self.peak_buffered_frames = max(
                self.peak_buffered_frames, len(self._frames)
            )
            self._condition.notify_all()

    async def seal(self, response: ResponseRef) -> None:
        if response != self.response:
            raise MediaTransportViolation(
                "MEDIA_NATIVE_STREAM_RESPONSE_MISMATCH",
                "Native response seal does not match the source response",
            )
        async with self._condition:
            if self._closed:
                if self.completed:
                    return
                raise MediaTransportViolation(
                    "MEDIA_NATIVE_STREAM_CLOSED", "Native response source is closed"
                )
            self._sealed = True
            self._condition.notify_all()

    async def __anext__(self) -> MediaAudioFrame:
        async with self._condition:
            while not self._frames:
                if self._sealed:
                    self.completed = True
                    self._closed = True
                    self._condition.notify_all()
                    raise StopAsyncIteration
                if self._closed:
                    raise StopAsyncIteration
                await self._condition.wait()
            frame = self._frames.popleft()
            self.emitted_frames += 1
            self._condition.notify_all()
            return frame

    async def aclose(self) -> None:
        async with self._condition:
            if self._closed:
                return
            self._closed = True
            self._frames.clear()
            self._condition.notify_all()


__all__ = [
    "NativeDownlinkPresentationUnit",
    "NativeResponseDownlinkSource",
]
