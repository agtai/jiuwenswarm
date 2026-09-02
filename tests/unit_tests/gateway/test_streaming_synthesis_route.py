# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import struct
import traceback
from dataclasses import replace

import pytest

from tests.unit_tests.live_voice.c019_lifecycle_model import (
    from_adapter_snapshot,
    violations as lifecycle_violations,
    with_delivery_snapshot,
    with_gateway_snapshot,
    with_transport_observation,
)

from jiuwenswarm.gateway.live_voice import streaming_synthesis_route as route_module
from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.gateway.live_voice.product_streaming_synthesis import (
    ProductStreamingSynthesisSource,
)
from jiuwenswarm.gateway.live_voice.streaming_synthesis_route import (
    StreamingSynthesisFallbackAction,
    StreamingSynthesisReason,
    StreamingSynthesisRouteOwner,
    StreamingSynthesisRouteViolation,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    OpenAIStreamingSpeechConfig,
    OpenAIStreamingSpeechProvider,
    SpeechDegradationFact,
    SpeechDegradationReason,
    SpeechRouteTier,
    StreamingSpeechSelection,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    SpeechMode,
    SynthesisEventKind,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    CapabilityProvenance,
    NativeStreamingSpeechProvider,
    ProviderTransport,
    RecognitionProviderSupport,
    StreamingProviderCapability,
    StreamingSpeechConformance,
    StreamingSpeechViolation,
    StreamingSynthesisEvent,
    SynthesisProviderSupport,
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)


_PROVIDER_REF = ProviderRef("fake-streaming-speech", "formal")
_CAPABILITY = StreamingProviderCapability(
    provider=_PROVIDER_REF,
    recognition=RecognitionProviderSupport(
        modes=frozenset(),
        transport=ProviderTransport.UNSUPPORTED,
    ),
    synthesis=SynthesisProviderSupport(
        modes=frozenset({SpeechMode.STREAM}),
        transport=ProviderTransport.NATIVE_STREAM,
        ordered_events=CapabilityProvenance.ADAPTER_DERIVED,
        exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
        provider_cancel_ack=CapabilityProvenance.UNAVAILABLE,
        chunk_text_spans=CapabilityProvenance.UNAVAILABLE,
    ),
)


async def _wait_gate(gate: asyncio.Event, *, ignore_cancel: bool) -> None:
    while not gate.is_set():
        try:
            await gate.wait()
        except asyncio.CancelledError:
            if not ignore_cancel:
                raise


class _FakeSseStream:
    def __init__(self, lines: tuple[str, ...]) -> None:
        self._lines = lines
        self.closed = False

    async def __aiter__(self):
        for line in self._lines:
            yield line

    async def aclose(self) -> None:
        self.closed = True


class _ObservedFakeSseStream(_FakeSseStream):
    def __init__(self, lines: tuple[str, ...]) -> None:
        super().__init__(lines)
        self.yielded_lines = 0
        self._progressed = asyncio.Condition()

    async def __aiter__(self):
        for line in self._lines:
            async with self._progressed:
                self.yielded_lines += 1
                self._progressed.notify_all()
            yield line

    async def wait_until_yielded(self, count: int) -> None:
        async with self._progressed:
            await asyncio.wait_for(
                self._progressed.wait_for(lambda: self.yielded_lines >= count),
                timeout=1,
            )


class _CloseGatedObservedFakeSseStream(_ObservedFakeSseStream):
    def __init__(self, lines: tuple[str, ...]) -> None:
        super().__init__(lines)
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()

    async def aclose(self) -> None:
        self.close_started.set()
        await self.release_close.wait()
        await super().aclose()


class _TwoStageGatedSseStream(_FakeSseStream):
    def __init__(
        self,
        prefix: tuple[str, ...],
        middle: tuple[str, ...],
        suffix: tuple[str, ...],
    ) -> None:
        super().__init__(prefix + middle + suffix)
        self._prefix = prefix
        self._middle = middle
        self._suffix = suffix
        self.first_gate_waiting = asyncio.Event()
        self.release_first_gate = asyncio.Event()
        self.second_gate_waiting = asyncio.Event()
        self.release_second_gate = asyncio.Event()

    async def __aiter__(self):
        for line in self._prefix:
            yield line
        self.first_gate_waiting.set()
        await self.release_first_gate.wait()
        for line in self._middle:
            yield line
        self.second_gate_waiting.set()
        await self.release_second_gate.wait()
        for line in self._suffix:
            yield line


class _FirstPullGatedOpenAIProvider(OpenAIStreamingSpeechProvider):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.first_pull_started = asyncio.Event()
        self.release_first_pull = asyncio.Event()
        self._first_pull_released = False

    async def next_synthesis_event(self, ref, *, timeout_seconds: float):
        if not self._first_pull_released:
            self.first_pull_started.set()
            await self.release_first_pull.wait()
            self._first_pull_released = True
        return await super().next_synthesis_event(ref, timeout_seconds=timeout_seconds)


class _ObservedControlOpenAIProvider(OpenAIStreamingSpeechProvider):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pause_called = asyncio.Event()
        self.pause_calls = 0
        self.resume_calls = 0

    async def pause_synthesis(self, ref: SynthesisStreamRef) -> None:
        self.pause_calls += 1
        self.pause_called.set()
        await super().pause_synthesis(ref)

    async def resume_synthesis(self, ref: SynthesisStreamRef) -> None:
        self.resume_calls += 1
        await super().resume_synthesis(ref)


class _FakeProvider(NativeStreamingSpeechProvider):
    def __init__(self, capability: StreamingProviderCapability = _CAPABILITY) -> None:
        self._capability = capability
        self._conformance = StreamingSpeechConformance(
            capability,
            enabled=True,
            max_synthesis_sessions=8,
            max_identity_tombstones=64,
        )
        self.events: asyncio.Queue[StreamingSynthesisEvent | BaseException] = (
            asyncio.Queue()
        )
        self.open_count = 0
        self.requests: list[SynthesisStreamRequest] = []
        self.cancelled: list[SynthesisStreamRef] = []
        self.paused: list[SynthesisStreamRef] = []
        self.resumed: list[SynthesisStreamRef] = []
        self.pause_started = asyncio.Event()
        self.resume_started = asyncio.Event()
        self.parked: list[tuple[SynthesisStreamRef, int, float]] = []
        self.park_started = asyncio.Event()
        self.park_gate: asyncio.Event | None = None
        self.promoted: list[tuple[SynthesisStreamRef, int]] = []
        self.promote_started = asyncio.Event()
        self.promote_gate: asyncio.Event | None = None
        self.pause_error: BaseException | None = None
        self.resume_error: BaseException | None = None
        self.resume_gate: asyncio.Event | None = None
        self.closed = 0
        self.open_error: BaseException | None = None
        self.open_gate: asyncio.Event | None = None
        self.ignore_open_cancel = False
        self.open_started = asyncio.Event()
        self.open_completed = asyncio.Event()
        self.event_gate: asyncio.Event | None = None
        self.ignore_event_cancel = False
        self.event_started = asyncio.Event()
        self.event_calls = 0
        self.cancel_gate: asyncio.Event | None = None
        self.ignore_cancel_cancel = False
        self.cancel_error: BaseException | None = None
        self.cancel_started = asyncio.Event()
        self.cancel_interrupted = asyncio.Event()
        self.close_gate: asyncio.Event | None = None
        self.ignore_close_cancel = False
        self.close_started = asyncio.Event()
        self.close_error: BaseException | None = None

    @property
    def capability(self) -> StreamingProviderCapability:
        return self._capability

    @property
    def conformance(self) -> StreamingSpeechConformance:
        return self._conformance

    async def open_synthesis(self, request: SynthesisStreamRequest) -> None:
        self.open_count += 1
        if self.open_error is not None:
            raise self.open_error
        self._conformance.start_synthesis(request)
        self.requests.append(request)
        self.open_started.set()
        if self.open_gate is not None:
            await _wait_gate(self.open_gate, ignore_cancel=self.ignore_open_cancel)
        self.open_completed.set()

    async def next_synthesis_event(
        self, ref: SynthesisStreamRef, *, timeout_seconds: float
    ) -> StreamingSynthesisEvent:
        del timeout_seconds
        self.event_calls += 1
        self.event_started.set()
        if self.event_gate is not None:
            await _wait_gate(self.event_gate, ignore_cancel=self.ignore_event_cancel)
        item = await self.events.get()
        if isinstance(item, BaseException):
            raise item
        accepted = self._conformance.accept_synthesis_event(item)
        if accepted.kind in {
            SynthesisEventKind.COMPLETED,
            SynthesisEventKind.CANCELLED,
        }:
            self._conformance.reap_terminal()
        return accepted

    async def pause_synthesis(self, ref: SynthesisStreamRef) -> None:
        self.paused.append(ref)
        self.pause_started.set()
        if self.pause_error is not None:
            raise self.pause_error

    async def resume_synthesis(self, ref: SynthesisStreamRef) -> None:
        self.resumed.append(ref)
        self.resume_started.set()
        if self.resume_gate is not None:
            await self.resume_gate.wait()
        if self.resume_error is not None:
            raise self.resume_error

    async def park_synthesis_for_promotion(
        self,
        ref: SynthesisStreamRef,
        *,
        park_generation: int,
        max_pause_seconds: float,
    ) -> None:
        self.parked.append((ref, park_generation, max_pause_seconds))
        self.park_started.set()
        if self.park_gate is not None:
            await self.park_gate.wait()

    async def promote_parked_synthesis(
        self,
        ref: SynthesisStreamRef,
        *,
        park_generation: int,
    ) -> None:
        self.promoted.append((ref, park_generation))
        self.promote_started.set()
        if self.promote_gate is not None:
            await self.promote_gate.wait()

    async def cancel_synthesis(
        self, ref: SynthesisStreamRef, *, reason: str = "caller_cancel"
    ) -> None:
        del reason
        self.cancelled.append(ref)
        self.cancel_started.set()
        if self.cancel_gate is not None:
            try:
                await _wait_gate(
                    self.cancel_gate, ignore_cancel=self.ignore_cancel_cancel
                )
            except asyncio.CancelledError:
                self.cancel_interrupted.set()
                raise
        if self.cancel_error is not None:
            raise self.cancel_error
        try:
            self._conformance.request_synthesis_cancel(ref, reason="fake_cancel")
        except StreamingSpeechViolation:
            pass
        try:
            self._conformance.provider_closed_synthesis(ref)
        except StreamingSpeechViolation:
            pass
        self._conformance.reap_terminal()

    async def close(self) -> None:
        self.closed += 1
        self.close_started.set()
        if self.close_gate is not None:
            await _wait_gate(self.close_gate, ignore_cancel=self.ignore_close_cancel)
        if self.close_error is not None:
            error = self.close_error
            self.close_error = None
            raise error
        self._conformance.close()
        for request in tuple(self.requests):
            try:
                self._conformance.provider_closed_synthesis(request.ref)
            except StreamingSpeechViolation:
                pass
        self._conformance.reap_terminal()

    async def open_recognition(self, *_args, **_kwargs) -> None:
        raise AssertionError("recognition is outside this route")

    async def send_recognition_audio(self, *_args, **_kwargs) -> None:
        raise AssertionError("recognition is outside this route")

    async def commit_recognition(self, *_args, **_kwargs) -> None:
        raise AssertionError("recognition is outside this route")

    async def next_recognition_event(self, *_args, **_kwargs):
        raise AssertionError("recognition is outside this route")

    async def cancel_recognition(self, *_args, **_kwargs) -> None:
        raise AssertionError("recognition is outside this route")


class _CancellationHostileQueue(asyncio.Queue):
    def __init__(self) -> None:
        super().__init__()
        self.put_started = asyncio.Event()
        self.put_release = asyncio.Event()

    async def put(self, item) -> None:
        self.put_started.set()
        await _wait_gate(self.put_release, ignore_cancel=True)
        await super().put(item)


class _ParkedCancellationHostileProvider(_FakeProvider):
    def __init__(self, capability: StreamingProviderCapability) -> None:
        super().__init__(capability)
        self.second_event_started = asyncio.Event()
        self.release_second_event = asyncio.Event()

    async def next_synthesis_event(
        self, ref: SynthesisStreamRef, *, timeout_seconds: float
    ) -> StreamingSynthesisEvent:
        if self.event_calls == 0:
            return await super().next_synthesis_event(
                ref, timeout_seconds=timeout_seconds
            )
        self.event_calls += 1
        self.second_event_started.set()
        await _wait_gate(self.release_second_event, ignore_cancel=True)
        raise TimeoutError("settled hostile test wait")


class _ConclusiveEventTimeoutProvider(_FakeProvider):
    def __init__(self, capability: StreamingProviderCapability) -> None:
        super().__init__(capability)
        self.active_event_calls = 0
        self.max_concurrent_event_calls = 0

    async def next_synthesis_event(
        self, ref: SynthesisStreamRef, *, timeout_seconds: float
    ) -> StreamingSynthesisEvent:
        self.event_calls += 1
        self.event_started.set()
        self.active_event_calls += 1
        self.max_concurrent_event_calls = max(
            self.max_concurrent_event_calls, self.active_event_calls
        )
        try:
            item = await asyncio.wait_for(self.events.get(), timeout=timeout_seconds)
        finally:
            self.active_event_calls -= 1
        if isinstance(item, BaseException):
            raise item
        accepted = self._conformance.accept_synthesis_event(item)
        if accepted.kind in {
            SynthesisEventKind.COMPLETED,
            SynthesisEventKind.CANCELLED,
        }:
            self._conformance.reap_terminal()
        return accepted


class _ObservedQueue(asyncio.Queue):
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self.put_completed = asyncio.Event()
        self.get_started = asyncio.Event()

    async def put(self, item) -> None:
        await super().put(item)
        self.put_completed.set()

    async def get(self):
        self.get_started.set()
        return await super().get()


class _ObservedBoundedQueue(asyncio.Queue):
    def __init__(self, maxsize: int) -> None:
        super().__init__(maxsize=maxsize)
        self.put_attempts = 0
        self.blocked_put_started = asyncio.Event()

    async def put(self, item) -> None:
        self.put_attempts += 1
        if self.put_attempts > self.maxsize:
            self.blocked_put_started.set()
        await super().put(item)


def _request(
    *,
    stream_id: str = "synthesis-1",
    stream_generation: int = 0,
    interaction_id: str = "interaction-1",
    response_id: str = "response-1",
    response_generation: int = 0,
    unit_id: str = "unit-1",
    unit_seq: int = 0,
    display_text: str = "private display text",
    spoken_text: str = "private spoken text",
    sample_rate_hz: int = 24_000,
) -> SynthesisStreamRequest:
    response = ResponseRef(interaction_id, response_id, response_generation)
    return SynthesisStreamRequest(
        ref=SynthesisStreamRef(
            stream_id,
            stream_generation,
            response,
            unit_id,
            unit_seq,
        ),
        display_text=display_text,
        spoken_text=spoken_text,
        display_span=TextSpan(10, 10 + len(display_text)),
        sample_rate_hz=sample_rate_hz,
        event_timeout_seconds=2.0,
    )


def _selection(provider: _FakeProvider) -> StreamingSpeechSelection:
    return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)


def _event(
    request: SynthesisStreamRequest,
    *,
    seq: int,
    cursor: int,
    kind: SynthesisEventKind,
    samples: tuple[int, ...] = (),
    provider: ProviderRef = _PROVIDER_REF,
) -> StreamingSynthesisEvent:
    pcm = struct.pack(f"<{len(samples)}h", *samples) if samples else None
    return StreamingSynthesisEvent(
        ref=request.ref,
        provider=provider,
        seq=seq,
        sample_cursor=cursor,
        kind=kind,
        sample_rate_hz=request.sample_rate_hz,
        sample_count=len(samples),
        pcm_s16le=pcm,
    )


async def _begin(
    provider: _FakeProvider,
    request: SynthesisStreamRequest,
    *,
    require_prefetch_decision: bool = False,
    prefetch_decision_timeout_seconds: float = 180.0,
    on_prefetch_promotion_timeout=None,
    **owner_options,
):
    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector, **owner_options)
    handle, outcome = await owner.begin(
        request,
        require_prefetch_decision=require_prefetch_decision,
        prefetch_decision_timeout_seconds=prefetch_decision_timeout_seconds,
        on_prefetch_promotion_timeout=on_prefetch_promotion_timeout,
    )
    assert handle is not None
    assert outcome is None
    return owner, handle


async def _wait_for_retained_cleanup(
    owner: StreamingSynthesisRouteOwner,
) -> None:
    await asyncio.wait_for(owner._task_owner.wait_until_idle(), timeout=1.0)
    assert owner.retained_task_count == 0


@pytest.mark.asyncio
async def test_streams_ordered_20ms_frames_with_exact_content_hidden_binding() -> None:
    provider = _FakeProvider()
    request = _request()
    owner, handle = await _begin(provider, request)
    samples = (32767,) * 480 + (-32768,) * 480
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=samples,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=960, kind=SynthesisEventKind.COMPLETED)
    )

    first = await owner.next_chunk(handle)
    second = await owner.next_chunk(handle)
    terminal = await owner.next_chunk(handle)

    assert first.chunk is not None and second.chunk is not None
    assert first.chunk.ref == request.ref
    assert first.chunk.request_binding_ref == second.chunk.request_binding_ref
    assert first.chunk.frame.seq == 0
    assert first.chunk.frame.sample_cursor == 0
    assert len(first.chunk.frame.samples) == 480
    assert first.chunk.frame.samples == (1.0,) * 480
    assert second.chunk.frame.seq == 1
    assert second.chunk.frame.sample_cursor == 480
    assert second.chunk.frame.samples == (-1.0,) * 480
    assert terminal.outcome is not None
    assert terminal.outcome.completed is True
    assert terminal.outcome.ref == request.ref
    assert terminal.outcome.request_binding_ref == first.chunk.request_binding_ref
    assert terminal.outcome.first_audio_emitted is True
    assert terminal.outcome.batch_eligible is False
    assert owner.active_count == 0
    assert "private display text" not in repr(handle)
    assert "private spoken text" not in repr(handle)
    assert "32767" not in repr(first.chunk)
    assert set(first.chunk.safe_metadata()) == {
        "request_binding_ref",
        "interaction_id",
        "response_id",
        "response_generation",
        "unit_id",
        "unit_seq",
        "frame_seq",
        "sample_cursor",
        "sample_count",
        "provider_id",
        "provider_implementation_class",
        "provider_fallback_from",
        "provider_available",
        "synthesis_modes",
        "transport",
        "ordered_events",
        "exact_audio_cursor",
        "provider_cancel_ack",
        "chunk_text_spans",
        "bounded_pause",
        "source_event_seq",
        "provider_cursor_through",
    }
    assert (
        first.chunk.capability.provider_cancel_ack is CapabilityProvenance.UNAVAILABLE
    )
    assert terminal.outcome.capability == first.chunk.capability
    await owner.close()


@pytest.mark.asyncio
async def test_real_openai_adapter_streams_through_route_without_batch_materialization() -> (
    None
):
    pcm = struct.pack("<480h", *((1000,) * 480))
    stream = _FakeSseStream(
        (
            "data: "
            + json.dumps(
                {
                    "type": "speech.audio.delta",
                    "audio": base64.b64encode(pcm).decode("ascii"),
                }
            ),
            "",
            'data: {"type":"speech.audio.done"}',
            "",
        )
    )
    provider_calls = 0

    async def sse_factory(*_args):
        nonlocal provider_calls
        provider_calls += 1
        return stream

    provider = OpenAIStreamingSpeechProvider(
        OpenAIStreamingSpeechConfig(
            api_base="https://api.openai.com/v1",
            api_key="private-test-key",
        ),
        sse_factory=sse_factory,
    )

    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingSynthesisRouteOwner(selector)
    request = _request()
    handle, begin_outcome = await owner.begin(request)
    assert handle is not None and begin_outcome is None
    first = await owner.next_chunk(handle)
    terminal = await owner.next_chunk(handle)

    assert first.chunk is not None
    assert first.chunk.frame.seq == 0
    assert first.chunk.frame.sample_cursor == 0
    assert len(first.chunk.frame.samples) == 480
    assert terminal.outcome is not None and terminal.outcome.completed is True
    assert terminal.outcome.first_audio_emitted is True
    assert provider_calls == 1
    assert stream.closed is True
    assert provider.conformance.snapshot().agent_dispatches == 0
    assert provider.conformance.snapshot().tool_dispatches == 0
    assert provider.conformance.snapshot().task_mutations == 0
    assert provider.conformance.snapshot().chat_mutations == 0
    assert provider.conformance.snapshot().turn_commits == 0
    await owner.close()


@pytest.mark.asyncio
async def test_real_adapter_drains_provider_completed_audio_through_bounded_pause() -> (
    None
):
    pcm = struct.pack("<5760h", *((1000,) * 5760))
    stream = _FakeSseStream(
        (
            "data: "
            + json.dumps(
                {
                    "type": "speech.audio.delta",
                    "audio": base64.b64encode(pcm).decode("ascii"),
                }
            ),
            "",
            'data: {"type":"speech.audio.done"}',
            "",
        )
    )

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(
        OpenAIStreamingSpeechConfig(
            api_base="https://api.openai.com/v1",
            api_key="private-test-key",
        ),
        sse_factory=sse_factory,
    )

    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingSynthesisRouteOwner(
        selector,
        max_pending_frames=8,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.5,
    )
    request = _request()
    handle, begin_outcome = await owner.begin(request)
    assert handle is not None and begin_outcome is None
    await asyncio.sleep(0.08)

    frame_sequences: list[int] = []
    while True:
        pull = await owner.next_chunk(handle)
        if pull.chunk is not None:
            frame_sequences.append(pull.chunk.frame.seq)
            continue
        assert pull.outcome is not None and pull.outcome.completed is True
        break
    assert frame_sequences == list(range(12))
    assert stream.closed is True
    await owner.close()


@pytest.mark.asyncio
async def test_real_adapter_provider_done_dominates_gateway_late_pause_resume() -> None:
    frame_samples = 24_000 // 50
    frame_count = 9
    pcm = struct.pack(
        f"<{frame_samples * frame_count}h",
        *((1000,) * (frame_samples * frame_count)),
    )
    stream = _CloseGatedObservedFakeSseStream(
        (
            "data: "
            + json.dumps(
                {
                    "type": "speech.audio.delta",
                    "audio": base64.b64encode(pcm).decode("ascii"),
                }
            ),
            "",
            'data: {"type":"speech.audio.done"}',
            "",
        )
    )

    async def sse_factory(*_args):
        return stream

    provider = _ObservedControlOpenAIProvider(
        OpenAIStreamingSpeechConfig(
            api_base="https://api.openai.com/v1",
            api_key="private-test-key",
        ),
        sse_factory=sse_factory,
        synthesis_pause_timeout_seconds=0.1,
    )

    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingSynthesisRouteOwner(
        selector,
        max_pending_frames=8,
        queue_wait_seconds=0.2,
        pause_wait_seconds=0.5,
    )
    request = _request(sample_rate_hz=24_000)
    handle, begin_outcome = await owner.begin(request)
    assert handle is not None and begin_outcome is None
    try:
        await asyncio.wait_for(stream.close_started.wait(), timeout=1)
        await asyncio.wait_for(provider.pause_called.wait(), timeout=1)
        session = provider._require_synthesis(request.ref)
        snapshot = provider._synthesis_lifecycle_snapshot(session)
        assert snapshot.provider_state.value == "done"
        assert snapshot.reader_state.value == "exited"
        oracle_state = from_adapter_snapshot(
            reader_state=snapshot.reader_state.value,
            provider_state=snapshot.provider_state.value,
            outcome_state=snapshot.outcome_state.value,
            pause_requested=snapshot.pause_requested,
            pause_acknowledged=snapshot.pause_acknowledged,
            resume_signal_set=snapshot.resume_signal_set,
            pause_mode=(
                None if snapshot.pause_mode is None else snapshot.pause_mode.value
            ),
            closing=snapshot.closing,
        )
        oracle_state = with_gateway_snapshot(
            oracle_state,
            queue_size=handle.queue.qsize(),
            queue_capacity=handle.queue.maxsize,
            browser_reserved_frames=0,
            prefetch_candidate=handle.prefetch_candidate,
            waiting_for_park=False,
        )
        assert lifecycle_violations(oracle_state) == ()
        assert handle.queue.qsize() == handle.queue.maxsize == 8

        stream.release_close.set()
        frame_sequences: list[int] = []
        while True:
            pull = await owner.next_chunk(handle, timeout_seconds=1)
            if pull.chunk is not None:
                frame_sequences.append(pull.chunk.frame.seq)
                continue
            assert pull.outcome is not None and pull.outcome.completed is True
            break

        assert frame_sequences == list(range(frame_count))
        assert provider.pause_calls == 1
        assert provider.resume_calls == 1
        assert provider.degradation_facts == ()
        assert stream.closed is True
        oracle_state = with_delivery_snapshot(
            oracle_state,
            accepted_audio_frames=frame_count,
            delivered_audio_frames=len(frame_sequences),
            completed_published=True,
        )
        oracle_state = with_transport_observation(
            oracle_state,
            attached=True,
            closed=stream.closed,
            expected_close=True,
            failure_reported=False,
        )
        assert lifecycle_violations(oracle_state) == ()
        snapshot = provider.conformance.snapshot()
        assert snapshot.agent_dispatches == 0
        assert snapshot.tool_dispatches == 0
        assert snapshot.task_mutations == 0
        assert snapshot.chat_mutations == 0
        assert snapshot.turn_commits == 0
    finally:
        stream.release_close.set()
        await owner.close()


@pytest.mark.asyncio
async def test_real_adapter_dual_full_queues_resume_without_deadlock() -> None:
    samples_per_delta = 5760
    frames_per_delta = samples_per_delta // 480
    pcm = struct.pack(f"<{samples_per_delta}h", *((1000,) * samples_per_delta))
    audio_event = "data: " + json.dumps(
        {
            "type": "speech.audio.delta",
            "audio": base64.b64encode(pcm).decode("ascii"),
        }
    )
    delta_count = 80
    stream = _ObservedFakeSseStream(
        tuple(line for _ in range(delta_count) for line in (audio_event, ""))
        + ('data: {"type":"speech.audio.done"}', "")
    )

    async def sse_factory(*_args):
        return stream

    provider = _FirstPullGatedOpenAIProvider(
        OpenAIStreamingSpeechConfig(
            api_base="https://api.openai.com/v1",
            api_key="private-test-key",
        ),
        sse_factory=sse_factory,
        event_queue_wait_seconds=0.5,
        synthesis_pause_timeout_seconds=1.0,
    )

    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingSynthesisRouteOwner(
        selector,
        max_pending_frames=8,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.5,
    )
    request = _request()
    handle, begin_outcome = await owner.begin(request)
    assert handle is not None and begin_outcome is None
    session = provider._require_synthesis(request.ref)

    await asyncio.wait_for(provider.first_pull_started.wait(), timeout=1)
    await stream.wait_until_yielded(128)
    assert session.events.qsize() == session.events.maxsize == 64
    provider.release_first_pull.set()

    async def wait_for_dual_saturation() -> None:
        while (
            session.events.qsize() < session.events.maxsize or handle.queue.qsize() < 8
        ):
            await asyncio.sleep(0)

    try:
        await asyncio.wait_for(wait_for_dual_saturation(), timeout=1)
        assert stream.yielded_lines >= 128
        assert session.events.qsize() == session.events.maxsize == 64
        assert handle.queue.qsize() == handle.queue.maxsize == 8

        frame_sequences: list[int] = []
        while True:
            pull = await owner.next_chunk(handle, timeout_seconds=1)
            if pull.chunk is not None:
                frame_sequences.append(pull.chunk.frame.seq)
                continue
            assert pull.outcome is not None and pull.outcome.completed is True
            break

        assert frame_sequences == list(range(delta_count * frames_per_delta))
        assert provider.degradation_facts == ()
        assert stream.closed is True
        snapshot = provider.conformance.snapshot()
        assert snapshot.agent_dispatches == 0
        assert snapshot.tool_dispatches == 0
        assert snapshot.task_mutations == 0
        assert snapshot.chat_mutations == 0
        assert snapshot.turn_commits == 0
    finally:
        await owner.close()
    assert owner.retained_task_count == 0


@pytest.mark.asyncio
async def test_promoted_prefetch_resumes_later_ordinary_queue_pressure() -> None:
    """A promoted successor must not retain PARK ownership of later pauses."""

    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="post-promotion-ordinary-pressure")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.5,
        event_timeout_seconds=0.2,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=0.03,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1000,) * 480,
        )
    )
    first = await owner.next_chunk(handle, timeout_seconds=1)
    assert first.chunk is not None and first.chunk.frame.seq == 0

    await owner.park_prefetch(handle, park_generation=7, timeout_seconds=1.0)
    await owner.promote_prefetch(handle, park_generation=7)
    assert handle.flow_state.value == "promoted"
    await asyncio.sleep(0.04)

    provider.pause_started.clear()
    provider.events.put_nowait(
        _event(
            request,
            seq=2,
            cursor=480,
            kind=SynthesisEventKind.CHUNK,
            samples=(1000,) * (480 * 3),
        )
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=3,
            cursor=480 * 4,
            kind=SynthesisEventKind.COMPLETED,
        )
    )
    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)

    frame_sequences = [first.chunk.frame.seq]
    while True:
        pull = await owner.next_chunk(handle, timeout_seconds=1)
        if pull.chunk is not None:
            frame_sequences.append(pull.chunk.frame.seq)
            continue
        assert pull.outcome is not None and pull.outcome.completed is True
        break

    assert frame_sequences == [0, 1, 2, 3]
    assert provider.paused
    assert provider.resumed
    assert provider.cancelled == []
    snapshot = provider.conformance.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0
    await owner.close()


@pytest.mark.asyncio
async def test_parked_pressure_does_not_issue_a_second_ordinary_pause() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="parked-pressure-before-promotion")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.5,
        event_timeout_seconds=0.2,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=1.0,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1000,) * 480,
        )
    )
    while handle.queue.qsize() != 1:
        await asyncio.sleep(0)
    await owner.park_prefetch(handle, park_generation=8, timeout_seconds=1.0)

    provider.events.put_nowait(
        _event(
            request,
            seq=2,
            cursor=480,
            kind=SynthesisEventKind.CHUNK,
            samples=(1000,) * 480,
        )
    )
    await asyncio.sleep(0.02)
    assert provider.paused == []

    await owner.promote_prefetch(handle, park_generation=8)
    provider.events.put_nowait(
        _event(
            request,
            seq=3,
            cursor=960,
            kind=SynthesisEventKind.COMPLETED,
        )
    )
    frames = []
    while True:
        pull = await owner.next_chunk(handle, timeout_seconds=1)
        if pull.chunk is not None:
            frames.append(pull.chunk.frame.seq)
            continue
        assert pull.outcome is not None and pull.outcome.completed is True
        break
    assert frames == [0, 1]
    assert provider.cancelled == []
    await owner.close()


@pytest.mark.asyncio
async def test_promotion_winning_control_lock_reclassifies_pending_pressure() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    provider.promote_gate = asyncio.Event()
    request = _request(stream_id="promotion-wins-pending-pressure")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.5,
        event_timeout_seconds=0.2,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=1.0,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1000,) * 480,
        )
    )
    while handle.queue.qsize() != 1:
        await asyncio.sleep(0)
    await owner.park_prefetch(handle, park_generation=9, timeout_seconds=1.0)
    promotion = asyncio.create_task(owner.promote_prefetch(handle, park_generation=9))
    await asyncio.wait_for(provider.promote_started.wait(), timeout=1)

    provider.events.put_nowait(
        _event(
            request,
            seq=2,
            cursor=480,
            kind=SynthesisEventKind.CHUNK,
            samples=(1000,) * 480,
        )
    )
    await asyncio.sleep(0)
    provider.promote_gate.set()
    await asyncio.wait_for(promotion, timeout=1)
    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)
    provider.events.put_nowait(
        _event(
            request,
            seq=3,
            cursor=960,
            kind=SynthesisEventKind.COMPLETED,
        )
    )

    frames = []
    while True:
        pull = await owner.next_chunk(handle, timeout_seconds=1)
        if pull.chunk is not None:
            frames.append(pull.chunk.frame.seq)
            continue
        assert pull.outcome is not None and pull.outcome.completed is True
        break
    assert frames == [0, 1]
    assert provider.paused
    assert provider.resumed
    assert provider.cancelled == []
    await owner.close()


@pytest.mark.asyncio
async def test_real_adapter_reads_done_after_post_promotion_pause_resume() -> None:
    frame = struct.pack("<480h", *((1000,) * 480))
    three_frames = struct.pack("<1440h", *((1000,) * 1440))

    def audio_line(pcm: bytes) -> str:
        return "data: " + json.dumps(
            {
                "type": "speech.audio.delta",
                "audio": base64.b64encode(pcm).decode("ascii"),
            }
        )

    stream = _TwoStageGatedSseStream(
        (audio_line(frame), "", audio_line(three_frames), ""),
        (audio_line(frame), ""),
        (audio_line(frame), "", 'data: {"type":"speech.audio.done"}', ""),
    )

    async def sse_factory(*_args):
        return stream

    provider = _ObservedControlOpenAIProvider(
        OpenAIStreamingSpeechConfig(
            api_base="https://api.openai.com/v1",
            api_key="private-test-key",
        ),
        sse_factory=sse_factory,
        event_queue_wait_seconds=0.5,
        synthesis_pause_timeout_seconds=1.0,
    )

    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingSynthesisRouteOwner(
        selector,
        max_pending_frames=1,
        queue_wait_seconds=0.2,
        pause_wait_seconds=0.5,
        event_timeout_seconds=0.5,
    )
    request = _request(stream_id="real-adapter-post-promotion-done")
    handle, begin_outcome = await owner.begin(
        request,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=1.0,
    )
    assert handle is not None and begin_outcome is None
    first = await owner.next_chunk(handle, timeout_seconds=1)
    assert first.chunk is not None and first.chunk.frame.seq == 0
    await asyncio.wait_for(stream.first_gate_waiting.wait(), timeout=1)

    park = asyncio.create_task(
        owner.park_prefetch(handle, park_generation=10, timeout_seconds=1.0)
    )
    session = provider._require_synthesis(request.ref)
    while not session.pause_requested.is_set():
        await asyncio.sleep(0)
    stream.release_first_gate.set()
    await asyncio.wait_for(park, timeout=1)
    await owner.promote_prefetch(handle, park_generation=10)
    await asyncio.wait_for(stream.second_gate_waiting.wait(), timeout=1)
    provider.pause_called.clear()
    provider.pause_calls = 0
    provider.resume_calls = 0

    async def drain() -> tuple[list[int], bool]:
        frames = [first.chunk.frame.seq]
        while True:
            pull = await owner.next_chunk(handle, timeout_seconds=1)
            if pull.chunk is not None:
                frames.append(pull.chunk.frame.seq)
                continue
            assert pull.outcome is not None
            return frames, pull.outcome.completed

    drain_task = asyncio.create_task(drain())
    await asyncio.wait_for(provider.pause_called.wait(), timeout=1)
    while not session.pause_requested.is_set():
        await asyncio.sleep(0)
    stream.release_second_gate.set()
    frame_sequences, completed = await asyncio.wait_for(drain_task, timeout=2)

    assert completed is True
    assert frame_sequences == [0, 1, 2, 3, 4, 5]
    assert provider.pause_calls >= 1
    assert provider.resume_calls == provider.pause_calls
    assert provider.degradation_facts == ()
    assert stream.closed is True
    snapshot = provider.conformance.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0
    await owner.close()


@pytest.mark.asyncio
async def test_park_suspends_inflight_gateway_provider_event_deadline() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="park-suspends-provider-event-deadline")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=2,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.5,
        event_timeout_seconds=0.03,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=1.0,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    while provider.event_calls < 2:
        await asyncio.sleep(0)

    await owner.park_prefetch(handle, park_generation=11, timeout_seconds=1.0)
    await asyncio.sleep(0.05)
    assert handle.cleanup_done.is_set() is False
    assert provider.event_calls == 2
    assert owner._task_owner.retained_count == 1

    await owner.promote_prefetch(handle, park_generation=11)
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1000,) * 480,
        )
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=2,
            cursor=480,
            kind=SynthesisEventKind.COMPLETED,
        )
    )

    first = await owner.next_chunk(handle, timeout_seconds=1)
    terminal = await owner.next_chunk(handle, timeout_seconds=1)
    assert first.chunk is not None and first.chunk.frame.seq == 0
    assert terminal.outcome is not None and terminal.outcome.completed is True
    assert provider.event_calls == 3
    assert owner._task_owner.retained_count == 0
    assert provider.cancelled == []
    snapshot = provider.conformance.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0
    await owner.close()


@pytest.mark.asyncio
async def test_settled_provider_wait_reopens_without_overlap_or_active_time_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        route_module, "_PROVIDER_EVENT_SETTLEMENT_MARGIN_SECONDS", 299.97
    )
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _ConclusiveEventTimeoutProvider(capability)
    request = _request(stream_id="parked-settled-provider-timeout")
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    owner, handle = await _begin(
        provider,
        request,
        event_timeout_seconds=0.04,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=1.0,
    )
    while provider.event_calls < 2:
        await asyncio.sleep(0)
    await owner.park_prefetch(handle, park_generation=14, timeout_seconds=1.0)
    while provider.event_calls < 3:
        await asyncio.sleep(0)

    assert provider.max_concurrent_event_calls == 1
    assert handle.cleanup_done.is_set() is False
    await owner.promote_prefetch(handle, park_generation=14)
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1000,) * 480,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=480, kind=SynthesisEventKind.COMPLETED)
    )

    first = await owner.next_chunk(handle, timeout_seconds=1)
    terminal = await owner.next_chunk(handle, timeout_seconds=1)
    assert first.chunk is not None and first.chunk.frame.seq == 0
    assert terminal.outcome is not None and terminal.outcome.completed is True
    assert provider.event_calls == 4
    assert provider.max_concurrent_event_calls == 1
    assert owner.retained_task_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_cancel_parked_hostile_provider_event_never_opens_a_second_pull() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _ParkedCancellationHostileProvider(capability)
    request = _request(stream_id="parked-hostile-provider-event")
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    owner, handle = await _begin(
        provider,
        request,
        event_timeout_seconds=0.03,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=1.0,
    )
    await asyncio.wait_for(provider.second_event_started.wait(), timeout=1)
    await owner.park_prefetch(handle, park_generation=12, timeout_seconds=1.0)

    outcome = await owner.cancel(handle)

    assert outcome.reason is StreamingSynthesisReason.ROUTE_ABORTED
    assert provider.event_calls == 2
    assert 0 < owner.retained_task_count <= owner.retained_task_capacity
    snapshot = provider.conformance.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0

    provider.release_second_event.set()
    await _wait_for_retained_cleanup(owner)
    assert provider.event_calls == 2
    await owner.close()


@pytest.mark.asyncio
async def test_parked_provider_event_process_control_cleans_and_rethrows() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="parked-provider-event-control")
    owner, handle = await _begin(
        provider,
        request,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=1.0,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    while provider.event_calls < 2:
        await asyncio.sleep(0)
    await owner.park_prefetch(handle, park_generation=13, timeout_seconds=1.0)

    provider.events.put_nowait(GeneratorExit())
    with pytest.raises(GeneratorExit):
        await owner.next_chunk(handle, timeout_seconds=1)

    assert provider.event_calls == 2
    assert provider.cancelled == [handle.ref]
    assert owner.active_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_provider_completed_partial_tail_drains_without_late_pause() -> None:
    pcm = struct.pack("<500h", *((1000,) * 500))
    stream = _FakeSseStream(
        (
            "data: "
            + json.dumps(
                {
                    "type": "speech.audio.delta",
                    "audio": base64.b64encode(pcm).decode("ascii"),
                }
            ),
            "",
            'data: {"type":"speech.audio.done"}',
            "",
        )
    )

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(
        OpenAIStreamingSpeechConfig(
            api_base="https://api.openai.com/v1",
            api_key="private-test-key",
        ),
        sse_factory=sse_factory,
    )

    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingSynthesisRouteOwner(
        selector,
        max_pending_frames=1,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.5,
    )
    request = _request()
    handle, begin_outcome = await owner.begin(request)
    assert handle is not None and begin_outcome is None
    await asyncio.sleep(0.08)

    frames: list[int] = []
    while True:
        pull = await owner.next_chunk(handle)
        if pull.chunk is not None:
            frames.append(pull.chunk.frame.seq)
            continue
        assert pull.outcome is not None and pull.outcome.completed is True
        break
    assert frames == [0, 1]
    assert stream.closed is True
    await owner.close()


@pytest.mark.asyncio
async def test_partial_terminal_frame_is_zero_padded_without_faking_provider_cursor() -> (
    None
):
    provider = _FakeProvider()
    request = _request()
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(8192,) * 240,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=240, kind=SynthesisEventKind.COMPLETED)
    )

    pulled = await owner.next_chunk(handle)
    assert pulled.chunk is not None
    assert len(pulled.chunk.frame.samples) == 480
    assert pulled.chunk.frame.samples[:240] == (8192 / 32767,) * 240
    assert pulled.chunk.frame.samples[240:] == (0.0,) * 240
    assert pulled.chunk.provider_cursor_through == 240
    assert (await owner.next_chunk(handle)).outcome is not None
    await owner.close()


@pytest.mark.asyncio
async def test_failure_before_first_delivery_discards_audio_and_is_batch_eligible(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _FakeProvider()
    request = _request(spoken_text="secret-in-provider-error")
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    provider.events.put_nowait(RuntimeError("secret-in-provider-error"))
    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1.0)

    with caplog.at_level(logging.WARNING):
        pulled = await owner.next_chunk(handle)
    assert pulled.outcome is not None
    assert pulled.outcome.first_audio_emitted is False
    assert pulled.outcome.batch_eligible is True
    assert (
        pulled.outcome.fact.fallback_action
        is StreamingSynthesisFallbackAction.BATCH_ELIGIBLE
    )
    assert request.ref in provider.cancelled
    assert "secret-in-provider-error" not in caplog.text
    await owner.close()


@pytest.mark.asyncio
async def test_failure_after_first_delivery_never_allows_batch_replay() -> None:
    provider = _FakeProvider()
    request = _request()
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(100,) * 480,
        )
    )
    first = await owner.next_chunk(handle)
    assert first.chunk is not None
    provider.events.put_nowait(RuntimeError("late private failure"))

    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.first_audio_emitted is True
    assert terminal.outcome.batch_eligible is False
    assert (
        terminal.outcome.fact.fallback_action
        is StreamingSynthesisFallbackAction.TEXT_OR_RETRY
    )
    assert (await owner.next_chunk(handle)).outcome == terminal.outcome
    await owner.close()


@pytest.mark.asyncio
async def test_bounded_queue_failure_before_delivery_clears_retained_pcm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeProvider()
    request = _request()
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.01,
        event_timeout_seconds=0.2,
    )
    diagnostics: list[dict[str, object]] = []

    def record_pressure(message: str, *args: object, **kwargs: object) -> None:
        if message == "live_voice_streaming_synthesis_queue_pressure":
            extra = kwargs.get("extra")
            assert isinstance(extra, dict)
            diagnostics.append(extra)

    monkeypatch.setattr(route_module._LOGGER, "warning", record_pressure)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 960,
        )
    )
    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1.0)

    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.QUEUE_EXHAUSTED
    assert terminal.outcome.batch_eligible is True
    assert handle.queue.qsize() == 0
    assert len(diagnostics) == 1
    assert diagnostics[0]["queue_size"] == 1
    assert diagnostics[0]["queue_capacity"] == 1
    assert diagnostics[0]["frames_enqueued"] == 1
    assert diagnostics[0]["frames_pulled"] == 0
    assert diagnostics[0]["unit_seq"] == 0
    assert "private display text" not in repr(diagnostics[0])
    assert "private spoken text" not in repr(diagnostics[0])
    assert "samples=" not in repr(handle)
    await owner.close()


@pytest.mark.asyncio
async def test_burst_audio_waits_for_a_bounded_consumer_without_losing_frame_order() -> (
    None
):
    provider = _FakeProvider()
    request = _request()
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=2,
        queue_wait_seconds=0.2,
        event_timeout_seconds=0.2,
    )
    observed_queue = _ObservedBoundedQueue(maxsize=2)
    handle.queue = observed_queue
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * (480 * 3),
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=480 * 3, kind=SynthesisEventKind.COMPLETED)
    )

    await asyncio.wait_for(observed_queue.blocked_put_started.wait(), timeout=1.0)
    assert observed_queue.qsize() == 2

    first = await owner.next_chunk(handle)
    second = await owner.next_chunk(handle)
    third = await owner.next_chunk(handle)
    terminal = await owner.next_chunk(handle)

    assert first.chunk is not None
    assert second.chunk is not None
    assert third.chunk is not None
    assert [first.chunk.frame.seq, second.chunk.frame.seq, third.chunk.frame.seq] == [
        0,
        1,
        2,
    ]
    assert [
        first.chunk.frame.sample_cursor,
        second.chunk.frame.sample_cursor,
        third.chunk.frame.sample_cursor,
    ] == [0, 480, 960]
    assert terminal.outcome is not None and terminal.outcome.completed is True
    assert terminal.outcome.first_audio_emitted is True
    assert observed_queue.put_attempts == 4
    assert handle.frames_enqueued == 3
    assert handle.frames_pulled == 3
    await owner.close()


@pytest.mark.asyncio
async def test_declared_provider_pause_survives_legacy_queue_wait_and_resumes() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request()
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.5,
        event_timeout_seconds=0.5,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 1920,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=1920, kind=SynthesisEventKind.COMPLETED)
    )

    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)
    await asyncio.sleep(0.08)
    assert handle.cleanup_done.is_set() is False

    first = await owner.next_chunk(handle)
    assert first.chunk is not None and first.chunk.frame.seq == 0
    await asyncio.wait_for(provider.resume_started.wait(), timeout=1)
    frame_sequences = [first.chunk.frame.seq]
    while True:
        pull = await owner.next_chunk(handle)
        if pull.chunk is not None:
            frame_sequences.append(pull.chunk.frame.seq)
            continue
        assert pull.outcome is not None and pull.outcome.completed is True
        break
    assert frame_sequences == [0, 1, 2, 3]
    assert provider.paused
    assert provider.paused == provider.resumed
    assert set(provider.paused) == {request.ref}
    await owner.close()


@pytest.mark.asyncio
async def test_legacy_staged_successor_reaches_ordinary_queue_deadline() -> None:
    """Freeze the pre-PARK failure when a Browser retains one successor."""

    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="legacy-staged-successor")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=8,
        queue_wait_seconds=0.01,
        pause_wait_seconds=0.05,
        event_timeout_seconds=0.2,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * (480 * 60),
        )
    )

    # The old protocol has no explicit PARK transition.  Model the Browser
    # retaining its 500 ms target (25 x 20 ms frames) and then withholding
    # further transport acknowledgement while the predecessor is playing.
    retained = []
    for _ in range(25):
        pull = await owner.next_chunk(handle, timeout_seconds=0.2)
        assert pull.chunk is not None
        retained.append(pull.chunk.frame.seq)
    assert retained == list(range(25))

    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1.0)
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.QUEUE_EXHAUSTED
    assert terminal.outcome.first_audio_emitted is True
    assert handle.queue.qsize() == 0
    assert provider.paused == [request.ref]
    assert provider.resumed == [request.ref]
    snapshot = provider.conformance.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0
    await owner.close()


@pytest.mark.asyncio
async def test_park_prefetch_adopts_ordinary_queue_pause_without_timeout() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="park-adopts-ordinary")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.01,
        pause_wait_seconds=0.05,
        event_timeout_seconds=0.2,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * (480 * 4),
        )
    )
    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)

    await owner.park_prefetch(handle, park_generation=3, timeout_seconds=0.3)
    await asyncio.sleep(0.08)  # Cross the superseded ordinary 50 ms deadline.
    assert handle.cleanup_done.is_set() is False
    assert provider.parked == [(request.ref, 3, 5.3)]
    assert provider.resumed == []

    await owner.promote_prefetch(handle, park_generation=3)
    frames = []
    for _ in range(4):
        pull = await owner.next_chunk(handle, timeout_seconds=0.2)
        assert pull.chunk is not None
        frames.append(pull.chunk.frame.seq)
    assert frames == [0, 1, 2, 3]
    assert provider.promoted == [(request.ref, 3)]
    assert provider.resumed == []
    await owner.cancel(handle, reason=StreamingSynthesisReason.ROUTE_ABORTED)
    await owner.close()


@pytest.mark.asyncio
async def test_park_prefetch_has_independent_nonrenewable_promotion_lease() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="park-independent-lease")
    owner, handle = await _begin(
        provider,
        request,
        queue_wait_seconds=0.05,
        event_timeout_seconds=0.2,
    )

    await owner.park_prefetch(handle, park_generation=4, timeout_seconds=0.03)
    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1)
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.PROMOTION_TIMEOUT
    assert provider.cancelled == [request.ref]
    assert provider.resumed == []
    await owner.close()


@pytest.mark.asyncio
async def test_prefetch_candidate_reaches_park_reserve_larger_than_route_queue() -> (
    None
):
    """Ordinary pressure must not wait for PARK before PARK is reachable."""

    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="prefetch-reserve-exceeds-route-queue")
    promotion_timeouts = []
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=8,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.3,
        event_timeout_seconds=0.05,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=0.5,
        on_prefetch_promotion_timeout=lambda: promotion_timeouts.append(True),
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * (480 * 60),
        )
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=2,
            cursor=480 * 60,
            kind=SynthesisEventKind.COMPLETED,
        )
    )
    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)
    assert handle.queue.maxsize == 8
    assert handle.queue.qsize() == 8

    retained = []
    for _ in range(25):
        pull = await owner.next_chunk(handle)
        assert pull.chunk is not None
        retained.append(pull.chunk.frame.seq)

    assert retained == list(range(25))
    assert provider.resumed
    await owner.park_prefetch(handle, park_generation=5, timeout_seconds=0.3)
    assert handle.flow_state.value == "prefetch_parked"
    await owner.promote_prefetch(handle, park_generation=5)

    while True:
        pull = await owner.next_chunk(handle)
        if pull.chunk is not None:
            retained.append(pull.chunk.frame.seq)
            continue
        assert pull.outcome is not None and pull.outcome.completed
        break

    assert retained == list(range(60))
    # PARK/PROMOTE settles its own pause owner. Any later bounded queue
    # pressure is ordinary again and therefore has an exact RESUME.
    assert len(provider.paused) == len(provider.resumed)
    assert provider.parked == [(request.ref, 5, 5.3)]
    assert provider.promoted == [(request.ref, 5)]
    assert provider.cancelled == []
    assert promotion_timeouts == []
    await _wait_for_retained_cleanup(owner)
    assert owner.active_count == 0
    snapshot = provider.conformance.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0
    await owner.close()
    assert owner.retained_task_count == 0


@pytest.mark.asyncio
async def test_prefetch_candidate_hands_ordinary_pause_to_park_before_resume() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="park-races-ordinary-resume")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.05,
        pause_wait_seconds=0.3,
        event_timeout_seconds=0.3,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=0.3,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * (480 * 3),
        )
    )
    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)
    reads_before_park = provider.event_calls

    park = asyncio.create_task(
        owner.park_prefetch(handle, park_generation=5, timeout_seconds=0.3)
    )
    await asyncio.wait_for(park, timeout=1)
    first = await owner.next_chunk(handle)
    assert first.chunk is not None
    assert handle.flow_state.value == "prefetch_parked"
    assert provider.resumed == []
    assert provider.event_calls == reads_before_park
    assert provider.parked == [(request.ref, 5, 5.3)]

    await owner.promote_prefetch(handle, park_generation=5)
    assert provider.promoted == [(request.ref, 5)]
    await owner.cancel(handle, reason=StreamingSynthesisReason.ROUTE_ABORTED)
    await owner.close()


@pytest.mark.asyncio
async def test_park_arriving_during_resume_blocks_next_provider_read() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    provider.resume_gate = asyncio.Event()
    request = _request(stream_id="park-during-ordinary-resume")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.1,
        pause_wait_seconds=0.3,
        event_timeout_seconds=0.3,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=0.5,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * (480 * 2),
        )
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=2,
            cursor=480 * 2,
            kind=SynthesisEventKind.COMPLETED,
        )
    )
    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)
    assert (await owner.next_chunk(handle)).chunk is not None
    await asyncio.wait_for(provider.resume_started.wait(), timeout=1)
    reads_before_park = provider.event_calls

    park = asyncio.create_task(
        owner.park_prefetch(handle, park_generation=6, timeout_seconds=0.3)
    )
    for _ in range(100):
        if handle.flow_state.value == "park_requested":
            break
        await asyncio.sleep(0)
    assert handle.flow_state.value == "park_requested"
    provider.resume_gate.set()
    await asyncio.wait_for(park, timeout=1)
    await asyncio.sleep(0)

    assert handle.flow_state.value == "prefetch_parked"
    assert provider.event_calls == reads_before_park
    await owner.promote_prefetch(handle, park_generation=6)
    assert (await owner.next_chunk(handle)).chunk is not None
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None and terminal.outcome.completed
    await owner.close()


@pytest.mark.asyncio
async def test_prefetch_candidate_without_media_decision_fails_at_exact_deadline() -> (
    None
):
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="prefetch-decision-timeout")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.01,
        pause_wait_seconds=0.2,
        event_timeout_seconds=0.3,
        require_prefetch_decision=True,
        prefetch_decision_timeout_seconds=0.03,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * (480 * 3),
        )
    )
    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)
    await asyncio.sleep(0.04)
    assert (await owner.next_chunk(handle)).chunk is not None
    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1)
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.PROMOTION_TIMEOUT
    assert provider.resumed == []
    await owner.close()


@pytest.mark.asyncio
async def test_promotion_lease_starts_when_park_is_accepted() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    provider.park_gate = asyncio.Event()
    request = _request(stream_id="park-lease-not-renewed-by-provider-settlement")
    owner, handle = await _begin(
        provider,
        request,
        queue_wait_seconds=0.2,
        event_timeout_seconds=0.2,
    )

    park = asyncio.create_task(
        owner.park_prefetch(handle, park_generation=8, timeout_seconds=0.03)
    )
    await asyncio.wait_for(provider.park_started.wait(), timeout=1)
    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1)
    provider.park_gate.set()
    await asyncio.gather(park, return_exceptions=True)
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.PROMOTION_TIMEOUT
    assert provider.cancelled == [request.ref]
    await owner.close()


@pytest.mark.asyncio
async def test_terminal_park_and_promotion_are_exact_provider_noops() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="terminal-park-noop")
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=480, kind=SynthesisEventKind.COMPLETED)
    )
    assert (await owner.next_chunk(handle)).chunk is not None
    assert (await owner.next_chunk(handle)).outcome is not None

    await owner.park_prefetch(handle, park_generation=6, timeout_seconds=0.1)
    await owner.promote_prefetch(handle, park_generation=6)
    assert provider.parked == []
    assert provider.promoted == []
    with pytest.raises(StreamingSynthesisRouteViolation):
        await owner.promote_prefetch(handle, park_generation=7)
    await owner.close()


@pytest.mark.asyncio
async def test_buffered_terminal_park_cannot_renew_promotion_lease() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="buffered-terminal-park-lease")
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=480, kind=SynthesisEventKind.COMPLETED)
    )
    await asyncio.wait_for(handle.terminal_ready.wait(), timeout=1)

    await owner.park_prefetch(handle, park_generation=7, timeout_seconds=0.03)
    await asyncio.sleep(0.02)
    await owner.park_prefetch(handle, park_generation=7, timeout_seconds=0.03)
    await asyncio.sleep(0.02)
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.PROMOTION_TIMEOUT
    assert provider.parked == []
    await owner.close()


@pytest.mark.asyncio
async def test_delivered_terminal_park_expires_before_late_promotion() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="delivered-terminal-park-lease")
    timeout_observed = []
    owner, handle = await _begin(
        provider,
        request,
        require_prefetch_decision=True,
        on_prefetch_promotion_timeout=lambda: timeout_observed.append(True),
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=480, kind=SynthesisEventKind.COMPLETED)
    )
    assert (await owner.next_chunk(handle)).chunk is not None
    assert (await owner.next_chunk(handle)).outcome is not None

    await owner.park_prefetch(handle, park_generation=10, timeout_seconds=0.03)
    await asyncio.sleep(0.04)
    assert handle.promotion_lease_expired is True
    assert timeout_observed == [True]
    assert handle.cleanup_done.is_set() is True
    assert owner.retained_task_count == 0
    with pytest.raises(StreamingSynthesisRouteViolation):
        await owner.promote_prefetch(handle, park_generation=10)
    await owner.close()


@pytest.mark.asyncio
async def test_delivered_terminal_close_releases_promotion_lease() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="delivered-terminal-close-releases-park")
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=480, kind=SynthesisEventKind.COMPLETED)
    )
    assert (await owner.next_chunk(handle)).chunk is not None
    assert (await owner.next_chunk(handle)).outcome is not None
    await owner.park_prefetch(handle, park_generation=12, timeout_seconds=0.03)

    await owner.cancel(handle, reason=StreamingSynthesisReason.ROUTE_ABORTED)
    await asyncio.sleep(0.04)
    assert handle.park_generation is None
    assert handle.promotion_lease_expired is False
    await owner.close()


@pytest.mark.asyncio
async def test_concurrent_failure_during_provider_park_cannot_ack_success() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    provider.park_gate = asyncio.Event()
    request = _request(stream_id="park-races-terminal-failure")
    owner, handle = await _begin(provider, request, queue_wait_seconds=0.2)
    park = asyncio.create_task(
        owner.park_prefetch(handle, park_generation=11, timeout_seconds=0.1)
    )
    await asyncio.wait_for(provider.park_started.wait(), timeout=1)
    await owner.cancel(handle, reason=StreamingSynthesisReason.ROUTE_ABORTED)
    provider.park_gate.set()
    with pytest.raises(StreamingSynthesisRouteViolation):
        await park
    assert handle.outcome is not None and handle.outcome.completed is False
    await owner.close()


@pytest.mark.asyncio
async def test_completed_delivered_while_provider_park_settles_is_valid_noop() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    provider.park_gate = asyncio.Event()
    request = _request(stream_id="completed-delivered-during-provider-park")
    owner, handle = await _begin(provider, request, queue_wait_seconds=0.2)
    park = asyncio.create_task(
        owner.park_prefetch(handle, park_generation=13, timeout_seconds=0.1)
    )
    await asyncio.wait_for(provider.park_started.wait(), timeout=1)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    provider.events.put_nowait(
        _event(request, seq=2, cursor=480, kind=SynthesisEventKind.COMPLETED)
    )
    assert (await owner.next_chunk(handle)).chunk is not None
    assert (await owner.next_chunk(handle)).outcome is not None

    provider.park_gate.set()
    await asyncio.wait_for(park, timeout=1)
    assert handle.park_generation == 13
    assert handle.promotion_timeout_task is not None
    await owner.promote_prefetch(handle, park_generation=13)
    assert provider.promoted == []
    await owner.close()


@pytest.mark.asyncio
async def test_failed_terminal_cannot_ack_park_or_promotion() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            parked_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request(stream_id="failed-terminal-cannot-promote")
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(RuntimeError("private provider failure"))
    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1)
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.completed is False

    with pytest.raises(StreamingSynthesisRouteViolation):
        await owner.park_prefetch(handle, park_generation=9, timeout_seconds=0.1)
    with pytest.raises(StreamingSynthesisRouteViolation):
        await owner.promote_prefetch(handle, park_generation=9)
    assert provider.parked == []
    assert provider.promoted == []
    await owner.close()


@pytest.mark.asyncio
async def test_declared_provider_pause_timeout_fails_closed_and_resumes_once() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    request = _request()
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        queue_wait_seconds=0.01,
        pause_wait_seconds=0.05,
        event_timeout_seconds=0.2,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 960,
        )
    )

    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1)
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.QUEUE_EXHAUSTED
    assert terminal.outcome.batch_eligible is True
    assert provider.paused == provider.resumed == [request.ref]
    assert provider.cancelled == [request.ref]
    assert handle.queue.qsize() == 0
    await owner.close()


@pytest.mark.asyncio
async def test_provider_resume_process_control_rethrows_after_paused_cleanup() -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            bounded_pause=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )
    provider = _FakeProvider(capability)
    provider.resume_error = GeneratorExit()
    request = _request(stream_id="pause-resume-control")
    owner, handle = await _begin(
        provider,
        request,
        max_pending_frames=1,
        pause_wait_seconds=0.5,
        event_timeout_seconds=0.5,
    )
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 960,
        )
    )

    await asyncio.wait_for(provider.pause_started.wait(), timeout=1)
    first = await owner.next_chunk(handle)
    assert first.chunk is not None and first.chunk.frame.seq == 0
    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1)
    with pytest.raises(GeneratorExit):
        await owner.next_chunk(handle)
    assert provider.paused == provider.resumed == [request.ref]
    assert owner.active_count == 0
    provider.resume_error = None
    await owner.close()


@pytest.mark.asyncio
async def test_cancel_fences_queued_and_late_audio_without_fallback() -> None:
    provider = _FakeProvider()
    request = _request()
    owner, handle = await _begin(provider, request)
    observed_queue = _ObservedQueue(owner._max_pending_frames)
    handle.queue = observed_queue
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    await observed_queue.put_completed.wait()
    outcome = await owner.cancel(handle)

    assert outcome.completed is False
    assert outcome.batch_eligible is False
    assert outcome.fact.fallback_action is StreamingSynthesisFallbackAction.NONE
    assert provider.cancelled == [request.ref]
    terminal = await owner.next_chunk(handle)
    assert terminal.chunk is None
    assert terminal.outcome == outcome
    await owner.close()


@pytest.mark.asyncio
async def test_feature_off_and_invalid_request_have_zero_provider_effects() -> None:
    provider = _FakeProvider()
    fact = SpeechDegradationFact(
        binding_ref="sha256:" + "0" * 64,
        operation="speech.route.select",
        reason=SpeechDegradationReason.FEATURE_OFF,
        from_tier=SpeechRouteTier.STREAMING,
        to_tier=SpeechRouteTier.BATCH,
        provider_id=_PROVIDER_REF.provider_id,
        visible=True,
        latency_ms=None,
    )

    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.BATCH, None, fact)

    owner = StreamingSynthesisRouteOwner(selector)
    assert await owner.available() is False
    handle, outcome = await owner.begin(_request())
    assert handle is None and outcome is not None
    assert outcome.reason is StreamingSynthesisReason.FEATURE_OFF
    assert outcome.ref == _request().ref
    assert outcome.batch_eligible is True
    assert outcome.provider_id == _PROVIDER_REF.provider_id
    assert outcome.fact is not None
    assert outcome.fact.provider_cancel_ack is CapabilityProvenance.UNAVAILABLE
    assert provider.open_count == 0
    assert provider.cancelled == []
    await owner.close()
    assert provider.closed == 0

    enabled_owner, _ = await _begin(provider, _request())
    bad = replace(_request(stream_id="bad-rate"), sample_rate_hz=24_001)
    with pytest.raises(StreamingSynthesisRouteViolation) as invalid:
        await enabled_owner.begin(bad)
    assert invalid.value.reason == "INVALID_SYNTHESIS_SAMPLE_RATE"
    assert provider.open_count == 1
    await enabled_owner.close()


@pytest.mark.asyncio
async def test_active_capacity_rejects_before_second_provider_effect() -> None:
    provider = _FakeProvider()
    first_request = _request()
    owner, first = await _begin(provider, first_request, max_active_streams=1)
    second_request = _request(
        stream_id="synthesis-2",
        interaction_id="interaction-2",
        response_id="response-2",
    )
    second, outcome = await owner.begin(second_request)
    assert second is None and outcome is not None
    assert outcome.reason is StreamingSynthesisReason.CAPACITY_EXHAUSTED
    assert outcome.batch_eligible is True
    assert provider.open_count == 1
    await owner.cancel(first)
    await owner.close()


@pytest.mark.asyncio
async def test_successor_cancels_predecessor_and_stale_response_fails_closed() -> None:
    provider = _FakeProvider()
    first_request = _request()
    owner, first = await _begin(provider, first_request)
    successor_request = _request(
        stream_id="synthesis-2",
        stream_generation=0,
        response_id="response-2",
        response_generation=1,
    )
    successor, outcome = await owner.begin(successor_request)
    assert successor is not None and outcome is None
    assert provider.cancelled == [first_request.ref]
    predecessor_terminal = await owner.next_chunk(first)
    assert predecessor_terminal.outcome is not None
    assert (
        predecessor_terminal.outcome.reason
        is StreamingSynthesisReason.RESPONSE_SUPERSEDED
    )
    assert predecessor_terminal.outcome.batch_eligible is False

    stale_request = _request(
        stream_id="synthesis-stale",
        response_id="response-stale",
        response_generation=0,
    )
    with pytest.raises(StreamingSynthesisRouteViolation) as stale:
        await owner.begin(stale_request)
    assert stale.value.reason == "STALE_SYNTHESIS_RESPONSE"
    assert provider.open_count == 2
    await owner.cancel(successor)
    await owner.close()


@pytest.mark.asyncio
async def test_successor_fences_provider_complete_but_unplayed_predecessor() -> None:
    provider = _FakeProvider()
    first_request = _request()
    owner, first = await _begin(provider, first_request)
    provider.events.put_nowait(
        _event(first_request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            first_request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    provider.events.put_nowait(
        _event(
            first_request,
            seq=2,
            cursor=480,
            kind=SynthesisEventKind.COMPLETED,
        )
    )
    await first.terminal_ready.wait()
    assert owner.active_count == 1

    successor_request = _request(
        stream_id="synthesis-2",
        response_id="response-2",
        response_generation=1,
    )
    successor, outcome = await owner.begin(successor_request)
    assert successor is not None and outcome is None
    stale_pull = await owner.next_chunk(first)
    assert stale_pull.chunk is None
    assert stale_pull.outcome is not None
    assert stale_pull.outcome.reason is StreamingSynthesisReason.RESPONSE_SUPERSEDED
    assert stale_pull.outcome.batch_eligible is False
    await owner.cancel(successor)
    await owner.close()


@pytest.mark.asyncio
async def test_successor_cancels_inflight_open_before_activating_new_response() -> None:
    provider = _FakeProvider()
    provider.open_gate = asyncio.Event()

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector)
    first_request = _request()
    first_task = asyncio.create_task(owner.begin(first_request))
    await provider.open_started.wait()
    successor_request = _request(
        stream_id="synthesis-2",
        response_id="response-2",
        response_generation=1,
    )
    successor_task = asyncio.create_task(owner.begin(successor_request))
    await provider.cancel_started.wait()
    provider.open_gate.set()

    with pytest.raises(asyncio.CancelledError):
        await first_task
    successor, outcome = await successor_task
    assert successor is not None and outcome is None
    assert first_request.ref in provider.cancelled
    assert provider.open_count == 2
    await owner.cancel(successor)
    await owner.close()


@pytest.mark.asyncio
async def test_process_control_during_open_cleans_identity_and_rethrows() -> None:
    provider = _FakeProvider()
    provider.open_error = SystemExit()
    request = _request()

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector)
    with pytest.raises(SystemExit):
        await owner.begin(request)
    assert provider.open_count == 1
    assert provider.cancelled == [request.ref]
    assert owner.active_count == 0
    provider.open_error = None
    with pytest.raises(StreamingSynthesisRouteViolation) as reused:
        await owner.begin(request)
    assert reused.value.reason == "SYNTHESIS_STREAM_REUSED"
    await owner.close()


@pytest.mark.asyncio
async def test_close_cancels_inflight_open_and_closes_shared_provider_once() -> None:
    provider = _FakeProvider()
    provider.open_gate = asyncio.Event()

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector)
    request = _request()
    begin_task = asyncio.create_task(owner.begin(request))
    await provider.open_started.wait()
    await owner.close()

    with pytest.raises(asyncio.CancelledError):
        await begin_task
    assert provider.cancelled == [request.ref]
    assert provider.closed == 1
    assert owner.active_count == 0
    await owner.close()
    assert provider.closed == 1


@pytest.mark.asyncio
async def test_cancel_between_provider_open_and_handle_registration_rolls_back() -> (
    None
):
    provider = _FakeProvider()

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector)
    await owner._lifecycle_lock.acquire()
    request = _request()
    begin_task = asyncio.create_task(owner.begin(request))
    await provider.open_started.wait()
    await provider.open_completed.wait()
    begin_task.cancel()
    owner._lifecycle_lock.release()

    with pytest.raises(asyncio.CancelledError):
        await begin_task
    assert provider.cancelled == [request.ref]
    assert owner.active_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_provider_protocol_mismatch_fails_before_audio_delivery() -> None:
    provider = _FakeProvider()
    request = _request()
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
            provider=ProviderRef("foreign", "formal"),
        )
    )
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.PROVIDER_PROTOCOL
    assert terminal.outcome.batch_eligible is True
    await owner.close()


@pytest.mark.asyncio
async def test_caller_cancel_cleans_provider_retires_and_rethrows() -> None:
    provider = _FakeProvider()
    owner, handle = await _begin(provider, _request())
    observed_queue = _ObservedQueue()
    handle.queue = observed_queue
    pull_task = asyncio.create_task(owner.next_chunk(handle))
    await observed_queue.get_started.wait()
    pull_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await pull_task
    assert provider.cancelled == [handle.ref]
    assert owner.active_count == 0
    terminal = await owner.next_chunk(handle)
    assert terminal.chunk is None
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.ROUTE_ABORTED
    assert handle.queue.empty()
    await owner.close()


@pytest.mark.asyncio
async def test_request_event_timeout_bounds_gateway_provider_wait() -> None:
    provider = _FakeProvider()
    request = replace(
        _request(stream_id="request-event-timeout"), event_timeout_seconds=0.02
    )
    owner, handle = await _begin(
        provider,
        request,
        event_timeout_seconds=1.0,
    )

    terminal = await owner.next_chunk(handle, timeout_seconds=0.2)

    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.PROVIDER_TIMEOUT
    assert terminal.outcome.first_audio_emitted is False
    assert terminal.outcome.batch_eligible is True
    assert provider.cancelled == [handle.ref]
    await owner.close()


@pytest.mark.asyncio
async def test_hard_deadlines_bound_cancellation_hostile_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_PROVIDER_CLEANUP_TIMEOUT_SECONDS", 0.02)
    loop = asyncio.get_running_loop()

    opening = _FakeProvider()
    opening.open_gate = asyncio.Event()
    opening.ignore_open_cancel = True

    async def open_selector() -> StreamingSpeechSelection:
        return _selection(opening)

    open_owner = StreamingSynthesisRouteOwner(open_selector, open_timeout_seconds=0.02)
    started = loop.time()
    handle, outcome = await open_owner.begin(_request())
    assert loop.time() - started < 0.2
    assert handle is None and outcome is not None
    assert outcome.reason is StreamingSynthesisReason.PROVIDER_TIMEOUT
    assert 0 < open_owner.retained_task_count <= open_owner.retained_task_capacity
    opening.open_gate.set()
    await _wait_for_retained_cleanup(open_owner)
    await open_owner.close()

    eventing = _FakeProvider()
    eventing.event_gate = asyncio.Event()
    eventing.ignore_event_cancel = True
    event_request = _request(stream_id="event-hostile")
    event_owner, event_handle = await _begin(
        eventing,
        event_request,
        event_timeout_seconds=0.02,
    )
    eventing.events.put_nowait(
        _event(
            event_request,
            seq=0,
            cursor=0,
            kind=SynthesisEventKind.STARTED,
        )
    )
    await eventing.event_started.wait()
    started = loop.time()
    event_terminal = await event_owner.next_chunk(event_handle, timeout_seconds=0.04)
    assert loop.time() - started < 0.2
    assert event_terminal.outcome is not None
    assert event_terminal.outcome.reason is StreamingSynthesisReason.PROVIDER_TIMEOUT
    eventing.event_gate.set()
    await _wait_for_retained_cleanup(event_owner)
    await event_owner.close()

    cancelling = _FakeProvider()
    cancelling.cancel_gate = asyncio.Event()
    cancelling.ignore_cancel_cancel = True
    cancel_owner, cancel_handle = await _begin(
        cancelling, _request(stream_id="cancel-hostile")
    )
    started = loop.time()
    cancel_outcome = await cancel_owner.cancel(cancel_handle)
    assert loop.time() - started < 0.2
    assert cancel_outcome.reason is StreamingSynthesisReason.ROUTE_ABORTED
    assert 0 < cancel_owner.retained_task_count <= cancel_owner.retained_task_capacity
    assert cancel_handle.cleanup_complete is False
    assert cancel_owner.active_count == 1
    cancelling.cancel_gate.set()
    await _wait_for_retained_cleanup(cancel_owner)
    recovered_cancel = await cancel_owner.cancel(cancel_handle)
    assert recovered_cancel == cancel_outcome
    assert cancel_handle.cleanup_complete is True
    assert cancel_owner.active_count == 0
    await cancel_owner.close()

    closing = _FakeProvider()
    closing.close_gate = asyncio.Event()
    closing.ignore_close_cancel = True
    close_owner, close_handle = await _begin(
        closing, _request(stream_id="close-hostile")
    )
    await close_owner.cancel(close_handle)
    started = loop.time()
    await close_owner.close()
    assert loop.time() - started < 0.2
    assert 0 < close_owner.retained_task_count <= close_owner.retained_task_capacity
    closing.close_gate.set()
    await _wait_for_retained_cleanup(close_owner)


@pytest.mark.asyncio
async def test_product_source_joins_exact_retained_cancel_before_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_PROVIDER_CLEANUP_TIMEOUT_SECONDS", 0.05)
    provider = _FakeProvider()
    provider.cancel_gate = asyncio.Event()
    provider.ignore_cancel_cancel = True
    owner, handle = await _begin(
        provider, _request(stream_id="product-source-cancel-hostile")
    )
    source = ProductStreamingSynthesisSource(owner, handle, None)
    unrelated_started = asyncio.Event()
    unrelated_gate = asyncio.Event()

    async def unrelated_operation() -> None:
        unrelated_started.set()
        await unrelated_gate.wait()

    unrelated = asyncio.create_task(
        owner._task_owner.run(
            unrelated_operation(),
            timeout_seconds=1,
            operation="unrelated-test-operation",
        )
    )
    await unrelated_started.wait()

    async def release_retained_cancel() -> None:
        await provider.cancel_started.wait()
        await asyncio.sleep(0.06)
        assert provider.cancel_gate is not None
        provider.cancel_gate.set()

    release = asyncio.create_task(release_retained_cancel())
    await asyncio.wait_for(source.aclose(), timeout=0.2)
    await release

    assert provider.cancelled == [handle.ref]
    assert handle.cleanup_complete is True
    assert owner.active_count == 0
    assert unrelated.done() is False
    unrelated_gate.set()
    await unrelated
    assert owner.retained_task_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_close_fences_late_selector_and_closes_provider_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_PROVIDER_CLEANUP_TIMEOUT_SECONDS", 0.02)
    provider = _FakeProvider()
    selector_started = asyncio.Event()
    selector_release = asyncio.Event()

    async def selector() -> StreamingSpeechSelection:
        selector_started.set()
        await _wait_gate(selector_release, ignore_cancel=True)
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(
        selector,
        open_timeout_seconds=0.05,
        max_retained_tasks=1,
    )
    availability = asyncio.create_task(owner.available())
    await selector_started.wait()
    await owner.close()
    with pytest.raises(asyncio.CancelledError):
        await availability
    selector_release.set()
    await _wait_for_retained_cleanup(owner)
    assert provider.open_count == 0
    assert provider.closed == 1
    await owner.close()
    assert provider.closed == 1


@pytest.mark.asyncio
async def test_identity_capacity_preflight_has_zero_response_or_provider_effect() -> (
    None
):
    provider = _FakeProvider()

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector)
    owner._retained_bindings.update(
        {(f"retained-{index}", 0): f"sha256:{index:064x}" for index in range(256)}
    )
    request = _request(stream_id="capacity-preflight")
    with pytest.raises(StreamingSynthesisRouteViolation) as exhausted:
        await owner.begin(request)
    assert exhausted.value.reason == "SYNTHESIS_IDENTITY_CAPACITY_EXHAUSTED"
    assert provider.open_count == 0
    assert provider.cancelled == []
    assert provider.conformance._active_responses == {}
    assert owner._opening == {}
    assert owner._opening_responses == {}
    await owner.close()


@pytest.mark.asyncio
async def test_retained_task_capacity_preflight_has_zero_route_or_provider_effect() -> (
    None
):
    provider = _FakeProvider()

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector, max_retained_tasks=1)
    owner._selection = _selection(provider)
    reservation = owner._task_owner.reserve()
    assert reservation is not None
    request = _request(stream_id="task-capacity-preflight")

    handle, outcome = await owner.begin(request)

    assert handle is None and outcome is not None
    assert outcome.reason is StreamingSynthesisReason.CAPACITY_EXHAUSTED
    assert provider.open_count == 0
    assert provider.cancelled == []
    assert provider.closed == 0
    assert provider.conformance._active_responses == {}
    assert owner._retained_bindings == {}
    assert owner._current_responses == {}
    assert owner._opening == {}
    reservation.release()
    await owner.close()


@pytest.mark.asyncio
async def test_stale_response_attempts_do_not_consume_identity_ledger() -> None:
    provider = _FakeProvider()
    current = _request(
        stream_id="current-response",
        response_id="response-current",
        response_generation=1,
    )
    owner, current_handle = await _begin(provider, current)
    await owner.cancel(current_handle)
    retained_before = dict(owner._retained_bindings)
    cancelled_before = list(provider.cancelled)

    for index in range(255):
        stale = _request(
            stream_id=f"stale-{index}",
            response_id=f"response-stale-{index}",
            response_generation=0,
        )
        with pytest.raises(StreamingSynthesisRouteViolation) as rejected:
            await owner.begin(stale)
        assert rejected.value.reason == "STALE_SYNTHESIS_RESPONSE"

    assert owner._retained_bindings == retained_before
    assert provider.open_count == 1
    assert provider.cancelled == cancelled_before
    valid = _request(
        stream_id="valid-successor",
        response_id="response-valid",
        response_generation=2,
    )
    successor, outcome = await owner.begin(valid)
    assert successor is not None and outcome is None
    assert len(owner._retained_bindings) == 2
    await owner.cancel(successor)
    await owner.close()


@pytest.mark.asyncio
async def test_invalid_request_traceback_locals_do_not_retain_text() -> None:
    provider = _FakeProvider()

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector)
    canary_display = "DISPLAY-CANARY-DO-NOT-LOG"
    canary_spoken = "SPOKEN-CANARY-DO-NOT-LOG"
    invalid = replace(
        _request(
            display_text=canary_display,
            spoken_text=canary_spoken,
        ),
        sample_rate_hz=24_001,
    )
    try:
        await owner.begin(invalid)
    except StreamingSynthesisRouteViolation as error:
        assert error.__context__ is None
        route_traceback = error.__traceback__
        while (
            route_traceback is not None
            and os.path.basename(route_traceback.tb_frame.f_code.co_filename)
            != "streaming_synthesis_route.py"
        ):
            route_traceback = route_traceback.tb_next
        assert route_traceback is not None
        rendered = "".join(
            traceback.TracebackException(
                type(error), error, route_traceback, capture_locals=True
            ).format()
        )
        assert canary_display not in rendered
        assert canary_spoken not in rendered
    else:
        raise AssertionError("invalid synthesis request unexpectedly passed")
    assert provider.open_count == 0
    await owner.close()


@pytest.mark.parametrize(
    "span_provenance",
    [
        CapabilityProvenance.PROVIDER_NATIVE,
        CapabilityProvenance.ADAPTER_DERIVED,
    ],
)
@pytest.mark.asyncio
async def test_declared_chunk_text_spans_fail_before_route_or_provider_effect(
    span_provenance: CapabilityProvenance,
) -> None:
    capability = replace(
        _CAPABILITY,
        synthesis=replace(
            _CAPABILITY.synthesis,
            chunk_text_spans=span_provenance,
        ),
    )
    provider = _FakeProvider(capability)

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector)
    assert await owner.available() is False
    request = _request(
        stream_id=f"unsupported-span-{span_provenance.value}",
        display_text="nonempty display span",
        spoken_text="nonempty spoken content",
    )

    handle, outcome = await owner.begin(request)

    assert handle is None and outcome is not None
    assert outcome.reason is StreamingSynthesisReason.PROVIDER_PROTOCOL
    assert outcome.fact is not None
    assert outcome.fact.chunk_text_spans is span_provenance
    assert provider.open_count == 0
    assert provider.cancelled == []
    assert provider.closed == 0
    assert provider.conformance._active_responses == {}
    assert owner._retained_bindings == {}
    assert owner._current_responses == {}
    assert owner._opening == {}
    await owner.close()


@pytest.mark.asyncio
async def test_post_validation_failures_capture_no_request_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary_display = "POST-VALIDATION-DISPLAY-CANARY"
    canary_spoken = "POST-VALIDATION-SPOKEN-CANARY"

    async def assert_private_failure(
        owner: StreamingSynthesisRouteOwner,
        request: SynthesisStreamRequest,
        expected_reason: str,
    ) -> None:
        try:
            await owner.begin(request)
        except StreamingSynthesisRouteViolation as error:
            assert error.reason == expected_reason
            route_traceback = error.__traceback__
            # Match the route module frame by exact basename. A suffix match also
            # accepts this test file (``test_streaming_synthesis_route.py`` ends
            # with the module name), which would stop the walk on the caller frame
            # and capture the test's own canary locals instead of the route's.
            while route_traceback is not None and (
                os.path.basename(route_traceback.tb_frame.f_code.co_filename)
                != "streaming_synthesis_route.py"
            ):
                route_traceback = route_traceback.tb_next
            assert route_traceback is not None
            rendered = "".join(
                traceback.TracebackException(
                    type(error), error, route_traceback, capture_locals=True
                ).format()
            )
            assert canary_display not in rendered
            assert canary_spoken not in rendered
            assert "SynthesisStreamRequest(" not in rendered
        else:
            raise AssertionError("private synthesis request unexpectedly passed")

    reused_provider = _FakeProvider()
    reused_request = _request(
        stream_id="private-reused",
        display_text=canary_display,
        spoken_text=canary_spoken,
    )
    reused_owner, reused_handle = await _begin(reused_provider, reused_request)
    await assert_private_failure(
        reused_owner, reused_request, "SYNTHESIS_STREAM_REUSED"
    )
    await reused_owner.cancel(reused_handle)
    await reused_owner.close()

    stale_provider = _FakeProvider()
    current = _request(
        stream_id="private-current",
        response_id="private-response-current",
        response_generation=1,
    )
    stale_owner, current_handle = await _begin(stale_provider, current)
    stale_request = _request(
        stream_id="private-stale",
        response_id="private-response-stale",
        response_generation=0,
        display_text=canary_display,
        spoken_text=canary_spoken,
    )
    await assert_private_failure(stale_owner, stale_request, "STALE_SYNTHESIS_RESPONSE")
    await stale_owner.cancel(current_handle)
    await stale_owner.close()

    capacity_provider = _FakeProvider()

    async def capacity_selector() -> StreamingSpeechSelection:
        return _selection(capacity_provider)

    capacity_owner = StreamingSynthesisRouteOwner(capacity_selector)
    capacity_owner._retained_bindings.update(
        {(f"full-{index}", 0): f"sha256:{index:064x}" for index in range(256)}
    )
    await assert_private_failure(
        capacity_owner,
        _request(
            stream_id="private-capacity",
            display_text=canary_display,
            spoken_text=canary_spoken,
        ),
        "SYNTHESIS_IDENTITY_CAPACITY_EXHAUSTED",
    )
    await capacity_owner.close()

    activation_provider = _FakeProvider()

    def reject_activation(_response: ResponseRef) -> None:
        raise StreamingSynthesisRouteViolation(
            "SYNTHESIS_ACTIVATION_REJECTED", "response activation rejected"
        )

    monkeypatch.setattr(
        activation_provider.conformance, "activate_response", reject_activation
    )

    async def activation_selector() -> StreamingSpeechSelection:
        return _selection(activation_provider)

    activation_owner = StreamingSynthesisRouteOwner(activation_selector)
    activation_request = _request(
        stream_id="private-activation",
        display_text=canary_display,
        spoken_text=canary_spoken,
    )
    await assert_private_failure(
        activation_owner,
        activation_request,
        "SYNTHESIS_ACTIVATION_REJECTED",
    )
    assert activation_provider.open_count == 0
    assert activation_provider.cancelled == []
    assert (
        ("legacy-session", "legacy-subject", "legacy-correlation"),
        activation_request.ref.stream_id,
        activation_request.ref.stream_generation,
    ) in activation_owner._retained_bindings
    await activation_owner.close()


@pytest.mark.asyncio
async def test_request_binding_binds_timeout_and_complete_capability_provenance() -> (
    None
):
    first_provider = _FakeProvider()
    first_request = _request(stream_id="binding-timeout")
    first_owner, first_handle = await _begin(first_provider, first_request)
    second_provider = _FakeProvider()
    second_request = replace(first_request, event_timeout_seconds=3.0)
    second_owner, second_handle = await _begin(second_provider, second_request)
    assert first_handle.request_binding_ref != second_handle.request_binding_ref
    assert first_handle.capability.provider == _PROVIDER_REF
    assert first_handle.capability.available is True
    assert first_handle.capability.modes == frozenset({SpeechMode.STREAM})
    assert first_handle.capability.transport is ProviderTransport.NATIVE_STREAM
    assert (
        first_handle.capability.provider_cancel_ack is CapabilityProvenance.UNAVAILABLE
    )
    first_failure = await first_owner.cancel(first_handle)
    assert first_failure.provider == _PROVIDER_REF
    assert first_failure.capability == first_handle.capability
    assert first_failure.fact is not None
    assert first_failure.fact.provider_id == _PROVIDER_REF.provider_id
    assert first_failure.fact.provider_cancel_ack is CapabilityProvenance.UNAVAILABLE
    await second_owner.cancel(second_handle)
    await first_owner.close()
    await second_owner.close()


@pytest.mark.asyncio
async def test_event_process_control_cleans_then_rethrows_to_caller() -> None:
    provider = _FakeProvider()
    owner, handle = await _begin(provider, _request(stream_id="event-control"))
    provider.events.put_nowait(GeneratorExit())
    with pytest.raises(GeneratorExit):
        await owner.next_chunk(handle)
    assert provider.cancelled == [handle.ref]
    assert owner.active_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_cancellation_hostile_queue_write_is_late_fenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_PROVIDER_CLEANUP_TIMEOUT_SECONDS", 0.02)
    provider = _FakeProvider()
    request = _request(stream_id="queue-hostile")
    owner, handle = await _begin(provider, request, queue_wait_seconds=0.02)
    hostile_queue = _CancellationHostileQueue()
    handle.queue = hostile_queue
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    await hostile_queue.put_started.wait()
    await asyncio.wait_for(handle.cleanup_done.wait(), timeout=1.0)
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.QUEUE_EXHAUSTED
    assert terminal.outcome.batch_eligible is True
    hostile_queue.put_release.set()
    await _wait_for_retained_cleanup(owner)
    repeated = await owner.next_chunk(handle)
    assert repeated.chunk is None
    assert repeated.outcome == terminal.outcome
    await owner.close()


@pytest.mark.asyncio
async def test_retained_task_cap_rejects_new_effect_and_recovers() -> None:
    selector_started = asyncio.Event()
    selector_release = asyncio.Event()

    async def selector() -> StreamingSpeechSelection:
        selector_started.set()
        await _wait_gate(selector_release, ignore_cancel=True)
        return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)

    owner = StreamingSynthesisRouteOwner(
        selector,
        open_timeout_seconds=0.02,
        max_retained_tasks=1,
    )
    assert await owner.available() is False
    await selector_started.wait()
    assert owner.retained_task_count == 1
    assert await owner.available() is False
    assert owner.retained_task_count == 1
    selector_release.set()
    await _wait_for_retained_cleanup(owner)
    await owner.close()


@pytest.mark.asyncio
async def test_predecessor_open_process_control_cleans_then_rethrows() -> None:
    provider = _FakeProvider()

    async def selector() -> StreamingSpeechSelection:
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(selector)
    prior_response = ResponseRef("interaction-1", "response-0", 0)
    predecessor_done = asyncio.Event()

    async def fail_predecessor() -> None:
        try:
            raise GeneratorExit()
        finally:
            predecessor_done.set()

    predecessor = asyncio.create_task(fail_predecessor())
    await predecessor_done.wait()
    legacy_scope = ("legacy-session", "legacy-subject", "legacy-correlation")
    predecessor_key = (legacy_scope, "predecessor", 0)
    owner._opening[predecessor_key] = predecessor
    owner._opening_responses[predecessor_key] = prior_response
    owner._current_responses[(legacy_scope, prior_response.interaction_id)] = (
        prior_response
    )
    successor = _request(
        stream_id="successor-control",
        response_id="response-1",
        response_generation=1,
    )

    with pytest.raises(GeneratorExit):
        await owner.begin(successor)
    assert provider.open_count == 0
    assert provider.cancelled == []
    assert (
        legacy_scope,
        successor.ref.stream_id,
        successor.ref.stream_generation,
    ) not in owner._opening
    assert (
        owner._current_responses[(legacy_scope, prior_response.interaction_id)]
        == prior_response
    )
    owner._opening.pop(predecessor_key, None)
    owner._opening_responses.pop(predecessor_key, None)
    await owner.close()


def test_response_generation_high_water_is_isolated_by_trusted_scope() -> None:
    async def selector() -> StreamingSpeechSelection:
        return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)

    owner = StreamingSynthesisRouteOwner(selector)
    first_scope = ("session-a", "subject-a", "correlation-a")
    second_scope = ("session-b", "subject-a", "correlation-b")
    prior = ResponseRef("shared-interaction", "response-a", 3)
    reset = ResponseRef("shared-interaction", "response-b", 0)
    owner._current_responses[(first_scope, prior.interaction_id)] = prior

    owner._preflight_response(reset, second_scope)
    with pytest.raises(StreamingSynthesisRouteViolation) as stale:
        owner._preflight_response(reset, first_scope)
    assert stale.value.reason == "STALE_SYNTHESIS_RESPONSE"


@pytest.mark.asyncio
async def test_close_caller_cancel_retries_cleanup_then_rethrows() -> None:
    provider = _FakeProvider()
    provider.close_gate = asyncio.Event()
    owner, handle = await _begin(provider, _request(stream_id="close-caller-cancel"))
    close_task = asyncio.create_task(owner.close())
    await provider.close_started.wait()
    close_task.cancel()
    provider.close_gate.set()

    with pytest.raises(asyncio.CancelledError):
        await close_task
    assert owner.active_count == 0
    assert handle.cleanup_complete is True
    assert provider.cancelled == [handle.ref]
    assert provider.closed == 1
    assert provider.conformance.snapshot().closed is True


@pytest.mark.asyncio
async def test_concurrent_close_waits_for_one_shared_completion_barrier() -> None:
    provider = _FakeProvider()
    provider.close_gate = asyncio.Event()
    owner, handle = await _begin(provider, _request(stream_id="shared-close"))

    first = asyncio.create_task(owner.close())
    second = asyncio.create_task(owner.close())
    await provider.close_started.wait()
    assert first.done() is False
    assert second.done() is False
    provider.close_gate.set()
    await asyncio.gather(first, second)

    assert provider.closed == 1
    assert provider.cancelled == [handle.ref]
    assert handle.cleanup_complete is True
    assert owner.active_count == 0
    await owner.close()
    assert provider.closed == 1


@pytest.mark.asyncio
async def test_provider_close_process_control_retries_cleanup_before_rethrow() -> None:
    provider = _FakeProvider()
    provider.close_error = GeneratorExit()
    owner, handle = await _begin(provider, _request(stream_id="provider-close-control"))

    results = await asyncio.gather(owner.close(), owner.close(), return_exceptions=True)

    assert all(isinstance(result, GeneratorExit) for result in results)
    assert provider.closed == 2
    assert provider.conformance.snapshot().closed is True
    assert provider.cancelled == [handle.ref]
    assert handle.cleanup_complete is True
    assert owner.active_count == 0
    with pytest.raises(GeneratorExit):
        await owner.close()
    assert provider.closed == 2


@pytest.mark.asyncio
async def test_normal_control_outcomes_do_not_emit_degradation_or_failure_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[tuple[object, ...]] = []

    def record_warning(*args: object) -> None:
        warnings.append(args)

    monkeypatch.setattr(route_module._LOGGER, "warning", record_warning)
    provider = _FakeProvider()
    owner, aborted_handle = await _begin(provider, _request(stream_id="normal-abort"))
    aborted = await owner.cancel(aborted_handle)
    assert aborted.fact is not None
    assert aborted.fact.visible is False
    assert aborted.fact.x_obs_event == "live_voice.speech.control"
    assert aborted.fact.x_obs_metric is None
    assert aborted.fact.metric_value is None
    assert warnings == []
    await owner.close()

    supersede_provider = _FakeProvider()
    first_request = _request(stream_id="normal-predecessor")
    supersede_owner, predecessor = await _begin(supersede_provider, first_request)
    successor_request = _request(
        stream_id="normal-successor",
        response_id="normal-response-successor",
        response_generation=1,
    )
    successor, begin_outcome = await supersede_owner.begin(successor_request)
    assert successor is not None and begin_outcome is None
    superseded = await supersede_owner.next_chunk(predecessor)
    assert superseded.outcome is not None and superseded.outcome.fact is not None
    assert superseded.outcome.fact.x_obs_event == "live_voice.speech.control"
    assert superseded.outcome.fact.x_obs_metric is None
    await supersede_owner.cancel(successor)
    await supersede_owner.close()

    closed_provider = _FakeProvider()
    closed_owner, closed_handle = await _begin(
        closed_provider, _request(stream_id="normal-owner-close")
    )
    await closed_owner.close()
    closed = await closed_owner.next_chunk(closed_handle)
    assert closed.outcome is not None and closed.outcome.fact is not None
    assert closed.outcome.fact.x_obs_event == "live_voice.speech.control"
    assert closed.outcome.fact.x_obs_metric is None
    assert warnings == []

    failure_provider = _FakeProvider()
    failure_owner, failure_handle = await _begin(
        failure_provider, _request(stream_id="real-provider-failure")
    )
    failure_provider.events.put_nowait(RuntimeError("private provider failure"))
    failure = await failure_owner.next_chunk(failure_handle)
    assert failure.outcome is not None and failure.outcome.fact is not None
    assert failure.outcome.fact.x_obs_event == "live_voice.speech.degradation"
    assert failure.outcome.fact.x_obs_metric == "live_voice.failure_total"
    assert failure.outcome.fact.metric_value == 1
    assert len(warnings) == 1
    warning_template = warnings[0][0]
    assert isinstance(warning_template, str)
    assert warning_template.startswith("live_voice_streaming_synthesis_fallback")
    assert "private provider failure" not in repr(warnings)
    await failure_owner.close()


@pytest.mark.asyncio
async def test_event_failure_cleanup_process_control_rethrows_in_foreground() -> None:
    provider = _FakeProvider()
    provider.cancel_error = GeneratorExit()
    owner, handle = await _begin(provider, _request(stream_id="cleanup-control"))
    provider.events.put_nowait(RuntimeError("untrusted provider failure"))

    with pytest.raises(GeneratorExit):
        await owner.next_chunk(handle)
    assert owner.active_count == 0
    assert handle.cleanup_complete is True
    assert provider.cancelled == [handle.ref]
    provider.cancel_error = None
    await owner.close()


@pytest.mark.asyncio
async def test_timed_out_selector_late_provider_is_closed_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_PROVIDER_CLEANUP_TIMEOUT_SECONDS", 0.02)
    provider = _FakeProvider()
    selector_release = asyncio.Event()

    async def selector() -> StreamingSpeechSelection:
        await _wait_gate(selector_release, ignore_cancel=True)
        return _selection(provider)

    owner = StreamingSynthesisRouteOwner(
        selector,
        open_timeout_seconds=0.02,
        max_retained_tasks=1,
    )
    assert await owner.available() is False
    assert owner.retained_task_count == 1
    selector_release.set()
    await _wait_for_retained_cleanup(owner)
    assert provider.open_count == 0
    assert provider.closed == 1
    assert owner.selection_degradation is None
    await owner.close()
    assert provider.closed == 1


@pytest.mark.asyncio
async def test_pull_task_capacity_exhaustion_fails_stream_closed() -> None:
    provider = _FakeProvider()
    owner, handle = await _begin(
        provider,
        _request(stream_id="pull-capacity"),
        max_retained_tasks=1,
    )
    await provider.event_started.wait()
    terminal = await owner.next_chunk(handle)
    assert terminal.outcome is not None
    assert terminal.outcome.reason is StreamingSynthesisReason.CAPACITY_EXHAUSTED
    assert terminal.outcome.batch_eligible is True
    assert owner.active_count == 0
    assert provider.cancelled == [handle.ref]
    await owner.close()


@pytest.mark.asyncio
async def test_caller_cancel_after_queue_dequeue_still_cleans_without_emission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeProvider()
    request = _request(stream_id="post-dequeue-cancel")
    owner, handle = await _begin(provider, request)
    provider.events.put_nowait(
        _event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    provider.events.put_nowait(
        _event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=(1,) * 480,
        )
    )
    original_take = owner._take_process_control
    late_take_started = asyncio.Event()
    late_take_release = asyncio.Event()
    take_count = 0

    async def gated_take(
        target: route_module.StreamingSynthesisHandle,
    ) -> BaseException | None:
        nonlocal take_count
        take_count += 1
        if take_count == 2:
            late_take_started.set()
            await late_take_release.wait()
        return await original_take(target)

    monkeypatch.setattr(owner, "_take_process_control", gated_take)
    pull_task = asyncio.create_task(owner.next_chunk(handle))
    await late_take_started.wait()
    pull_task.cancel()
    late_take_release.set()
    with pytest.raises(asyncio.CancelledError):
        await pull_task
    assert handle.first_audio_emitted is False
    assert handle.cleanup_complete is True
    assert owner.active_count == 0
    assert provider.cancelled == [handle.ref]
    await owner.close()


@pytest.mark.asyncio
async def test_cancel_api_caller_cancel_retries_cleanup_then_rethrows() -> None:
    provider = _FakeProvider()
    provider.cancel_gate = asyncio.Event()
    owner, handle = await _begin(provider, _request(stream_id="cancel-api-caller"))
    cancel_task = asyncio.create_task(owner.cancel(handle))
    await provider.cancel_started.wait()
    cancel_task.cancel()
    await provider.cancel_interrupted.wait()
    provider.cancel_gate.set()

    with pytest.raises(asyncio.CancelledError):
        await cancel_task
    assert handle.cleanup_complete is True
    assert owner.active_count == 0
    assert provider.cancelled == [handle.ref, handle.ref]
    await owner.close()
