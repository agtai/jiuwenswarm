"""Bounded, unpresented PCM owned by one exact terminal notification.

This owner has no Gateway credentials, media tickets, UI, Task, history or ACK
capabilities. The Registry supplies the authenticated identity/current check and
owns ticket creation after claim. A cancelled producer keeps its capacity until
cleanup really exits, including cancellation-hostile adapters.
"""

from __future__ import annotations

import asyncio
from array import array
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import math
import time
from typing import Any

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame, MediaDetachReason,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaDownlinkSourceFailure,
)

CONTRACT_VERSION = "live-voice.task-notification-preparation.v1"
CAPABILITIES_METHOD = "live_voice.speech.task_preparation_capabilities"
PREPARE_METHOD = "live_voice.speech.task_preparation_prepare"
CLAIM_METHOD = "live_voice.speech.task_preparation_claim"
CANCEL_METHOD = "live_voice.speech.task_preparation_cancel"
MAX_FRAMES = 750
MAX_BYTES = 3 * 1024 * 1024
RETENTION_SECONDS = 30.0
PRODUCTION_SECONDS = 15.0
RENDER_SECONDS = 30.0
MAX_SLOTS = 8


class PreparationViolation(Exception):
    def __init__(self, reason: str):
        self.reason_id = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class PreparationIdentity:
    session_id: str
    connection_id: str
    subject_id: str
    correlation_id: str
    interaction_id: str
    activation_id: str
    activation_generation: int
    event_key: str
    response_id: str
    response_generation: int
    unit_id: str
    text_sha256: str
    locale: str
    sample_rate_hz: int

    @property
    def activation_key(self) -> tuple[str, str, str, str, int]:
        return (self.session_id, self.connection_id, self.interaction_id,
                self.activation_id, self.activation_generation)


@dataclass(slots=True)
class PreparedNotificationSource:
    identity: PreparationIdentity
    preparation_id: str
    current: Callable[[], bool] = field(repr=False)
    retire: Callable[["PreparedNotificationSource"], None] = field(repr=False)
    expires_at: float
    monotonic: Callable[[], float] = field(repr=False)
    state: str = "preparing"
    claimed: bool = False
    attached: bool = False
    completed: bool = False
    settled: bool = False
    emitted_frames: int = 0
    produced_frames: int = 0
    produced_bytes: int = 0
    provider: dict[str, object] | None = field(default=None, repr=False)
    reason: str | None = None
    producer: asyncio.Task[None] | None = field(default=None, repr=False)
    expiry: asyncio.TimerHandle | None = field(default=None, repr=False)
    production_expiry: asyncio.TimerHandle | None = field(default=None, repr=False)
    ready: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    changed: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _frames: deque[bytes] = field(default_factory=deque, repr=False)
    _produced: bool = False
    _reading: bool = False

    def is_current(self) -> bool:
        return self.reason is None and self.current() and self.monotonic() < self.expires_at

    def check(self) -> None:
        if not self.is_current():
            self.fence(self.reason or "TASK_PREPARATION_EXPIRED")
            raise PreparationViolation(self.reason or "TASK_PREPARATION_EXPIRED")

    async def wait_ready(self) -> None:
        await self.ready.wait()
        self.check()

    def fence(self, reason: str) -> None:
        if self.reason is not None or self.settled:
            return
        self.reason = reason
        self.state = "cancelled" if reason == "TASK_PREPARATION_CANCELLED" else "failed"
        self._frames.clear()
        if self.expiry is not None:
            self.expiry.cancel()
            self.expiry = None
        if self.production_expiry is not None:
            self.production_expiry.cancel()
            self.production_expiry = None
        self.ready.set()
        self.changed.set()
        task = self.producer
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
        if task is None or task.done():
            self.retire(self)

    def claim(self, *, ticket_ttl: float = RETENTION_SECONDS) -> None:
        self.check()
        if self.claimed:
            raise PreparationViolation("TASK_PREPARATION_ALREADY_CLAIMED")
        self.claimed = True
        self.state = "claimed"
        self.expires_at = self.monotonic() + ticket_ttl
        if self.expiry is not None:
            self.expiry.cancel()
        self.expiry = asyncio.get_running_loop().call_later(ticket_ttl, self.fence, "TASK_PREPARATION_EXPIRED")

    def attach(self) -> None:
        self.check()
        if not self.claimed or self.attached:
            raise PreparationViolation("TASK_PREPARATION_OWNER_MISMATCH")
        self.attached = True
        self.expires_at = self.monotonic() + RENDER_SECONDS
        if self.expiry is not None:
            self.expiry.cancel()
        self.expiry = asyncio.get_running_loop().call_later(
            RENDER_SECONDS, self.fence, "TASK_PREPARATION_RENDER_TIMEOUT")

    def mark_rendered(self) -> None:
        self.check()
        if not self.attached or not self.completed:
            raise PreparationViolation("TASK_PREPARATION_NOT_RENDERED")
        self.settled = True
        self.state = "settled"
        self.retire(self)

    def __aiter__(self) -> "PreparedNotificationSource":
        return self

    async def __anext__(self) -> MediaAudioFrame:
        if self._reading or not self.claimed:
            raise DedicatedMediaDownlinkSourceFailure(MediaDetachReason.STREAMING_TTS_TEXT_OR_RETRY)
        self._reading = True
        try:
            while True:
                if self.completed:
                    raise StopAsyncIteration
                try:
                    self.check()
                except PreparationViolation:
                    raise DedicatedMediaDownlinkSourceFailure(
                        MediaDetachReason.STREAMING_TTS_TEXT_OR_RETRY) from None
                if self._frames:
                    samples = array("f")
                    samples.frombytes(self._frames.popleft())
                    seq = self.emitted_frames
                    self.emitted_frames += 1
                    return MediaAudioFrame(seq, seq * (self.identity.sample_rate_hz // 50), tuple(samples))
                if self._produced:
                    self.completed = True
                    self.state = "awaiting_receipt"
                    raise StopAsyncIteration
                self.changed.clear()
                await self.changed.wait()
        finally:
            self._reading = False

    async def aclose(self) -> None:
        # The media leaf closes its iterator even after successful EOF. PCM
        # cleanup is not render settlement; retain exact cancellation authority
        # until the Registry accepts the receipt or the render deadline fences it.
        if not self.completed:
            self.fence("TASK_PREPARATION_CANCELLED")
        task = self.producer
        if task is not None and task is not asyncio.current_task() and not task.done():
            # A cancellation-hostile producer remains strongly owned. Never
            # detach it and admit an unbounded chain of replacements.
            await asyncio.wait({task}, timeout=1.0)


class TaskNotificationPreparationOwner:
    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic,
                 retention_seconds: float = RETENTION_SECONDS,
                 production_seconds: float = PRODUCTION_SECONDS):
        self._monotonic = monotonic
        self._retention = retention_seconds
        self._production = production_seconds
        self._slots: dict[tuple[str, str, str, str, int], PreparedNotificationSource] = {}
        self._closed: OrderedDict[tuple[tuple[str, str, str, str, int], str], PreparationIdentity] = OrderedDict()

    @property
    def retained_count(self) -> int:
        return len(self._slots)

    def active(self, key: tuple[str, str, str, str, int]) -> PreparedNotificationSource | None:
        return self._slots.get(key)

    def start(self, identity: PreparationIdentity, preparation_id: str,
              produce: Callable[[], Awaitable[Any]], current: Callable[[], bool]) -> PreparedNotificationSource:
        key = identity.activation_key
        existing = self._slots.get(key)
        if existing is not None:
            if existing.identity == identity and existing.preparation_id == preparation_id:
                existing.check()
                return existing
            raise PreparationViolation("TASK_PREPARATION_BUSY")
        if (key, preparation_id) in self._closed:
            raise PreparationViolation("TASK_PREPARATION_RETIRED")
        if len(self._slots) >= MAX_SLOTS:
            raise PreparationViolation("TASK_PREPARATION_CAPACITY")
        if not current():
            raise PreparationViolation("TASK_PREPARATION_STALE")
        slot = PreparedNotificationSource(identity, preparation_id, current, self._retire,
            self._monotonic() + self._retention, self._monotonic)
        self._slots[key] = slot
        loop = asyncio.get_running_loop()
        slot.expiry = loop.call_later(self._retention, slot.fence, "TASK_PREPARATION_EXPIRED")
        slot.production_expiry = loop.call_later(self._production, slot.fence, "TASK_PREPARATION_TIMEOUT")
        slot.producer = loop.create_task(self._produce(slot, produce), name="task-notification-prepare")
        slot.producer.add_done_callback(lambda _task: self._retire_if_closed(slot))
        return slot

    def exact(self, identity: PreparationIdentity, preparation_id: str) -> PreparedNotificationSource:
        slot = self._slots.get(identity.activation_key)
        if slot is None or slot.identity != identity or slot.preparation_id != preparation_id:
            raise PreparationViolation("TASK_PREPARATION_OWNER_MISMATCH")
        return slot

    def cancel(self, identity: PreparationIdentity, preparation_id: str) -> bool:
        if self._closed.get((identity.activation_key, preparation_id)) == identity:
            return False
        self.exact(identity, preparation_id).fence("TASK_PREPARATION_CANCELLED")
        return True

    def reconcile(self) -> None:
        for slot in tuple(self._slots.values()):
            if not slot.is_current():
                slot.fence("TASK_PREPARATION_STALE")

    def _retire_if_closed(self, slot: PreparedNotificationSource) -> None:
        if slot.reason is not None or slot.settled:
            self._retire(slot)

    def _retire(self, slot: PreparedNotificationSource) -> None:
        if slot.producer is not None and not slot.producer.done():
            return
        key = slot.identity.activation_key
        if self._slots.get(key) is not slot:
            return
        self._slots.pop(key)
        slot._frames.clear()
        if slot.expiry is not None:
            slot.expiry.cancel()
            slot.expiry = None
        self._closed[(key, slot.preparation_id)] = slot.identity
        while len(self._closed) > 128:
            self._closed.popitem(last=False)

    async def _produce(self, slot: PreparedNotificationSource, produce: Callable[[], Awaitable[Any]]) -> None:
        source = None
        try:
            async with asyncio.timeout(self._production):
                source = await produce()
                slot.check()
                slot.provider = {"provider_id": source.provider_id,
                    "implementation_class": source.provider_implementation_class,
                    "fallback_from": source.provider_fallback_from,
                    "model": source.model,
                    **({"voice": source.voice} if source.voice is not None else {})}
                if slot.provider["implementation_class"] != "formal" or slot.provider["fallback_from"] is not None:
                    raise PreparationViolation("TASK_PREPARATION_PROVIDER_INVALID")
                async for frame in source:
                    slot.check()
                    count = slot.identity.sample_rate_hz // 50
                    if (frame.seq != slot.produced_frames or frame.sample_cursor != frame.seq * count
                            or len(frame.samples) != count or not all(math.isfinite(value) for value in frame.samples)):
                        raise PreparationViolation("TASK_PREPARATION_PCM_INVALID")
                    pcm = array("f", frame.samples).tobytes()
                    if slot.produced_frames >= MAX_FRAMES or slot.produced_bytes + len(pcm) > MAX_BYTES:
                        raise PreparationViolation("TASK_PREPARATION_AUDIO_LIMIT")
                    slot._frames.append(pcm)
                    slot.produced_frames += 1
                    slot.produced_bytes += len(pcm)
                    if not slot.claimed:
                        slot.state = "ready"
                    slot.ready.set()
                    slot.changed.set()
                if slot.produced_frames == 0 or not source.completed:
                    raise PreparationViolation("TASK_PREPARATION_EMPTY")
                slot._produced = True
                slot.changed.set()
        except asyncio.CancelledError:
            slot.fence("TASK_PREPARATION_CANCELLED")
        except Exception as exc:
            slot.fence(getattr(exc, "reason_id", "TASK_PREPARATION_FAILED"))
        finally:
            if slot.production_expiry is not None:
                slot.production_expiry.cancel()
                slot.production_expiry = None
            if source is not None:
                try:
                    await source.aclose()
                except (Exception, asyncio.CancelledError):
                    slot.fence("TASK_PREPARATION_CLEANUP_FAILED")
            slot.ready.set()
            slot.changed.set()
