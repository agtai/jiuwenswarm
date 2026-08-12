# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Exact product bridge from streaming TTS route ownership to media frames.

The bridge is deliberately content-hidden after construction.  It seeds the
first Provider-derived frame before a product media ticket is issued, then
retains only the exact stream handle needed for ordered pulls and cancellation.
It never owns Agent, Tool, Task, presentation, or history effects.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame,
    MediaDetachReason,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaDownlinkSourceFailure,
)
from jiuwenswarm.gateway.live_voice.streaming_synthesis_route import (
    StreamingSynthesisChunk,
    StreamingSynthesisHandle,
    StreamingSynthesisOutcome,
    StreamingSynthesisReason,
    StreamingSynthesisRouteOwner,
)
from jiuwenswarm.server.live_voice.streaming_speech import SynthesisStreamRequest


OutcomeObserver = Callable[[StreamingSynthesisOutcome], None]


@dataclass(frozen=True, slots=True)
class ProductStreamingSynthesisStart:
    source: "ProductStreamingSynthesisSource | None"
    outcome: StreamingSynthesisOutcome | None

    def __post_init__(self) -> None:
        if (self.source is None) == (self.outcome is None):
            raise ValueError("streaming product start requires one source or outcome")


@dataclass(slots=True)
class ProductStreamingSynthesisSource:
    """One exact async downlink source with idempotent route cancellation."""

    owner: StreamingSynthesisRouteOwner = field(repr=False)
    handle: StreamingSynthesisHandle = field(repr=False)
    first_chunk: StreamingSynthesisChunk | None = field(repr=False)
    on_outcome: OutcomeObserver | None = field(default=None, repr=False)
    completed: bool = False
    emitted_frames: int = 0
    _closed: bool = field(default=False, repr=False)
    _close_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __aiter__(self) -> "ProductStreamingSynthesisSource":
        return self

    @property
    def provider_id(self) -> str:
        return self.handle.provider_ref.provider_id

    @property
    def provider_implementation_class(self) -> str | None:
        return self.handle.provider_ref.implementation_class

    @property
    def provider_fallback_from(self) -> str | None:
        return self.handle.provider_ref.fallback_from

    @property
    def model(self) -> str:
        value = self.handle.provider.synthesis_model
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise TypeError("streaming Provider returned no safe synthesis model")
        return value

    @property
    def voice(self) -> str | None:
        value = self.handle.provider.synthesis_voice
        if value is not None and (
            not isinstance(value, str) or not value.strip() or value != value.strip()
        ):
            raise TypeError("streaming Provider returned an invalid synthesis voice")
        return value

    async def __anext__(self) -> MediaAudioFrame:
        if self._closed or self.completed:
            raise StopAsyncIteration
        chunk = self.first_chunk
        if chunk is not None and (
            self.handle.fenced
            or (self.handle.outcome is not None and not self.handle.outcome.completed)
        ):
            # A successor/cancel may fence the route after the product seeded
            # first audio but before the one-use media ticket is consumed.
            self.first_chunk = None
            chunk = None
        if chunk is not None:
            self.first_chunk = None
            return self._accept_chunk(chunk)
        pull = await self.owner.next_chunk(self.handle)
        if pull.chunk is not None:
            return self._accept_chunk(pull.chunk)
        outcome = pull.outcome
        assert outcome is not None
        self.completed = outcome.completed
        self._closed = True
        self._observe(outcome)
        if outcome.completed:
            raise StopAsyncIteration
        raise DedicatedMediaDownlinkSourceFailure(
            MediaDetachReason.STREAMING_TTS_TEXT_OR_RETRY
        )

    async def aclose(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self.first_chunk = None
            outcome = await self.owner.cancel(
                self.handle, reason=StreamingSynthesisReason.ROUTE_ABORTED
            )
            self._observe(outcome)

    def _accept_chunk(self, chunk: StreamingSynthesisChunk) -> MediaAudioFrame:
        if (
            chunk.ref != self.handle.ref
            or chunk.request_binding_ref != self.handle.request_binding_ref
            or chunk.provider != self.handle.provider_ref
            or chunk.frame.seq != self.emitted_frames
        ):
            raise DedicatedMediaDownlinkSourceFailure(
                MediaDetachReason.STREAMING_TTS_TEXT_OR_RETRY
            )
        self.emitted_frames += 1
        return chunk.frame

    def _observe(self, outcome: StreamingSynthesisOutcome) -> None:
        observer = self.on_outcome
        if observer is None:
            return
        try:
            observer(outcome)
        except BaseException:
            # Diagnostics are explicitly outside the business route.
            return


async def start_product_streaming_synthesis(
    owner: StreamingSynthesisRouteOwner,
    request: SynthesisStreamRequest,
    *,
    on_outcome: OutcomeObserver | None = None,
) -> ProductStreamingSynthesisStart:
    """Open and pull first audio before the caller may mint a media ticket."""

    handle, outcome = await owner.begin(request)
    if handle is None:
        assert outcome is not None
        if on_outcome is not None:
            try:
                on_outcome(outcome)
            except BaseException:
                pass
        return ProductStreamingSynthesisStart(None, outcome)
    first = await owner.next_chunk(handle)
    if first.chunk is None:
        assert first.outcome is not None
        if on_outcome is not None:
            try:
                on_outcome(first.outcome)
            except BaseException:
                pass
        return ProductStreamingSynthesisStart(None, first.outcome)
    return ProductStreamingSynthesisStart(
        ProductStreamingSynthesisSource(
            owner=owner,
            handle=handle,
            first_chunk=first.chunk,
            on_outcome=on_outcome,
        ),
        None,
    )


__all__ = [
    "OutcomeObserver",
    "ProductStreamingSynthesisSource",
    "ProductStreamingSynthesisStart",
    "start_product_streaming_synthesis",
]
