# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import asyncio
import base64
import json
import logging
import struct
import traceback
from collections.abc import Mapping
from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.batch_speech import (
    FORMAL_BATCH_SPEECH_FLAG,
    SPEECH_API_BASE_ENV,
    SPEECH_API_KEY_ENV,
    SPEECH_PROVIDER_ENV,
    SPEECH_STT_MODEL_ENV,
    SPEECH_TTS_MODEL_ENV,
    SPEECH_TTS_VOICE_ENV,
    create_environment_batch_speech_provider,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    CapabilityProvenance,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    MAX_DEGRADATION_SINK_TASKS_PER_OWNER,
    MAX_EVENT_QUEUE,
    MAX_INCOMPLETE_TRANSPORT_CLEANUPS,
    OpenAIStreamingSpeechError,
    OpenAIStreamingSpeechConfig,
    OpenAIStreamingSpeechProvider,
    SpeechDegradationFact,
    SpeechDegradationReason,
    SpeechRouteTier,
    STREAMING_SPEECH_FLAG,
    _LOGGER,
    _DegradationSinkTaskOwner,
    _StreamingLinearResampler,
    _TransportCleanupOwner,
    _degradation_fact,
    _reason_for_exception,
    select_environment_streaming_speech,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    RecognitionEventKind,
    SynthesisEventKind,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    CaptureRef,
    RecognitionCommitDisposition,
    RecognitionAudioFrame,
    RecognitionStreamRequest,
    RecognitionStreamRef,
    RecognitionTimingBasis,
    RecognitionTurnBoundaryEvent,
    RecognitionTurnBoundaryKind,
    RecognitionTurnDetection,
    StreamingSpeechViolation,
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)


class FakeSocket:
    def __init__(self, initial: tuple[dict[str, object], ...] = ()) -> None:
        self.sent: list[dict[str, object]] = []
        self.incoming: asyncio.Queue[str | bytes | BaseException] = asyncio.Queue()
        self.closed = False
        self.closed_event = asyncio.Event()
        for event in initial:
            self.push(event)

    def push(self, value: dict[str, object] | str | bytes | BaseException) -> None:
        if isinstance(value, dict):
            self.incoming.put_nowait(json.dumps(value))
        else:
            self.incoming.put_nowait(value)

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self) -> str | bytes:
        value = await self.incoming.get()
        if isinstance(value, BaseException):
            raise value
        return value

    async def close(self) -> None:
        self.closed = True
        self.closed_event.set()


class FakeSseStream:
    def __init__(self, lines: tuple[str, ...]) -> None:
        self.lines = lines
        self.closed = False
        self.closed_event = asyncio.Event()

    async def __aiter__(self):
        for line in self.lines:
            await asyncio.sleep(0)
            yield line

    async def aclose(self) -> None:
        self.closed = True
        self.closed_event.set()


class BlockingSseStream:
    def __init__(self) -> None:
        self.closed = False
        self.closed_event = asyncio.Event()
        self._never = asyncio.Event()

    async def __aiter__(self):
        await self._never.wait()
        if False:
            yield ""

    async def aclose(self) -> None:
        self.closed = True
        self.closed_event.set()


class FailingSendSocket(FakeSocket):
    async def send(self, message: str) -> None:
        parsed = json.loads(message)
        if parsed.get("type") == "input_audio_buffer.append":
            raise ConnectionError(f"private-wire-payload:{message}")
        self.sent.append(parsed)


class BlockingCommitSocket(FakeSocket):
    def __init__(self, initial: tuple[dict[str, object], ...] = ()) -> None:
        super().__init__(initial)
        self.commit_started = asyncio.Event()
        self.release_commit = asyncio.Event()

    async def send(self, message: str) -> None:
        parsed = json.loads(message)
        if parsed.get("type") == "input_audio_buffer.commit":
            self.commit_started.set()
            await self.release_commit.wait()
        self.sent.append(parsed)


class CancellationDefiantCloseSocket(FakeSocket):
    def __init__(self, initial: tuple[dict[str, object], ...] = ()) -> None:
        super().__init__(initial)
        self.close_started = asyncio.Event()
        self.close_returned = asyncio.Event()
        self.release_close = asyncio.Event()

    async def close(self) -> None:
        self.close_started.set()
        while not self.release_close.is_set():
            try:
                await self.release_close.wait()
            except asyncio.CancelledError:
                continue
        await super().close()
        self.close_returned.set()


class CancellationDefiantCloseStream(BlockingSseStream):
    def __init__(self) -> None:
        super().__init__()
        self.close_started = asyncio.Event()
        self.close_returned = asyncio.Event()
        self.release_close = asyncio.Event()

    async def aclose(self) -> None:
        self.close_started.set()
        while not self.release_close.is_set():
            try:
                await self.release_close.wait()
            except asyncio.CancelledError:
                continue
        await super().aclose()
        self.close_returned.set()


class ProcessControlOnCancelSocket(FakeSocket):
    def __init__(self, initial: tuple[dict[str, object], ...] = ()) -> None:
        super().__init__(initial)
        self.receive_waiting = asyncio.Event()

    async def recv(self) -> str | bytes:
        if not self.incoming.empty():
            return await super().recv()
        self.receive_waiting.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise GeneratorExit() from None
        raise AssertionError("unreachable")


class ProcessControlOnceCloseSocket(FakeSocket):
    def __init__(
        self,
        initial: tuple[dict[str, object], ...] = (),
        *,
        process_control_type: type[BaseException] = GeneratorExit,
    ) -> None:
        super().__init__(initial)
        self.close_attempts = 0
        self.process_control_type = process_control_type

    async def close(self) -> None:
        self.close_attempts += 1
        if self.close_attempts == 1:
            raise self.process_control_type()
        await super().close()


class CapturingLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def config() -> OpenAIStreamingSpeechConfig:
    return OpenAIStreamingSpeechConfig(
        api_base="https://api.openai.com/v1",
        api_key="private-test-key",
        stt_model="gpt-4o-mini-transcribe",
        tts_model="gpt-4o-mini-tts",
        tts_voice="marin",
    )


def session_updated_event(
    turn_detection: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "type": "session.updated",
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "transcription": {"model": "gpt-4o-mini-transcribe"},
                    "turn_detection": turn_detection,
                }
            },
        },
    }


def server_vad_wire() -> dict[str, object]:
    return {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500,
        "create_response": False,
        "interrupt_response": False,
    }


def recognition_ref(*, generation: int = 0) -> RecognitionStreamRef:
    return RecognitionStreamRef(
        "recognition-1", generation, CaptureRef("capture-1", 0, 48_000)
    )


def recognition_frame(ref: RecognitionStreamRef) -> RecognitionAudioFrame:
    samples = (0.0, 0.25, -0.25, 0.0)
    return RecognitionAudioFrame(
        ref=ref,
        seq=0,
        sample_cursor=0,
        sample_count=len(samples),
        pcm_f32le=b"".join(struct.pack("<f", value) for value in samples),
    )


def second_recognition_frame(ref: RecognitionStreamRef) -> RecognitionAudioFrame:
    samples = (0.5, -0.5, 0.125, -0.125)
    return RecognitionAudioFrame(
        ref=ref,
        seq=1,
        sample_cursor=4,
        sample_count=len(samples),
        pcm_f32le=b"".join(struct.pack("<f", value) for value in samples),
    )


def adapter_traceback_with_locals(exc: BaseException) -> str:
    provider_traceback = exc.__traceback__
    while (
        provider_traceback is not None
        and not provider_traceback.tb_frame.f_code.co_filename.replace(
            "\\", "/"
        ).endswith("/jiuwenswarm/server/live_voice/openai_streaming_speech.py")
    ):
        provider_traceback = provider_traceback.tb_next
    return "".join(
        traceback.TracebackException(
            type(exc), exc, provider_traceback, capture_locals=True
        ).format(chain=True)
    )


def synthesis_request(
    *, generation: int = 0, timeout_seconds: float = 1.0
) -> SynthesisStreamRequest:
    response = ResponseRef("interaction-1", f"response-{generation}", generation)
    return SynthesisStreamRequest(
        ref=SynthesisStreamRef("synthesis-1", generation, response, "unit-1", 0),
        display_text="API",
        spoken_text="A P I",
        display_span=TextSpan(10, 13),
        sample_rate_hz=48_000,
        timeout_seconds=timeout_seconds,
    )


def assert_zero_business_effects(provider: OpenAIStreamingSpeechProvider) -> None:
    snapshot = provider.conformance.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0


@pytest.mark.asyncio
async def test_capability_is_truthful_and_secret_stays_out_of_repr() -> None:
    provider = OpenAIStreamingSpeechProvider(config())
    capability = provider.capability
    assert (
        capability.recognition.exact_audio_cursor
        is CapabilityProvenance.ADAPTER_DERIVED
    )
    assert (
        capability.recognition.provider_cancel_ack is CapabilityProvenance.UNAVAILABLE
    )
    assert (
        capability.synthesis.exact_audio_cursor is CapabilityProvenance.ADAPTER_DERIVED
    )
    assert capability.synthesis.chunk_text_spans is CapabilityProvenance.UNAVAILABLE
    assert capability.has_declared_acceptance_gaps is True
    assert capability.acceptance_gaps == (
        "recognition.provider_cancel_ack",
        "synthesis.provider_cancel_ack",
        "synthesis.chunk_text_spans",
    )
    assert "private-test-key" not in repr(config())
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_server_vad_fences_input_and_final_uses_provider_time_truth() -> None:
    socket = FakeSocket((session_updated_event(server_vad_wire()),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    request = RecognitionStreamRequest(
        ref, RecognitionTurnDetection.server_vad_default()
    )
    await provider.open_recognition(request, timeout_seconds=2)
    assert (
        socket.sent[0]["session"]["audio"]["input"]["turn_detection"]
        == server_vad_wire()
    )
    await provider.send_recognition_audio(recognition_frame(ref))
    socket.push(
        {
            "type": "input_audio_buffer.speech_started",
            "item_id": "vad-item-1",
            "audio_start_ms": 120,
        }
    )
    socket.push(
        {
            "type": "input_audio_buffer.speech_stopped",
            "item_id": "vad-item-1",
            "audio_end_ms": 840,
        }
    )
    started = await provider.next_recognition_event(ref, timeout_seconds=1)
    stopped = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert isinstance(started, RecognitionTurnBoundaryEvent)
    assert isinstance(stopped, RecognitionTurnBoundaryEvent)
    assert started.kind is RecognitionTurnBoundaryKind.SPEECH_STARTED
    assert stopped.kind is RecognitionTurnBoundaryKind.SPEECH_STOPPED
    assert (started.provider_start_ms, stopped.provider_end_ms) == (120, 840)
    assert started.timing_basis is RecognitionTimingBasis.PROVIDER_TIME
    sent_before_late_frame = tuple(socket.sent)
    await provider.send_recognition_audio(second_recognition_frame(ref))
    assert tuple(socket.sent) == sent_before_late_frame
    disposition = await provider.commit_recognition(ref)
    assert disposition in {
        RecognitionCommitDisposition.SERVER_VAD_PENDING,
        RecognitionCommitDisposition.SERVER_VAD_OBSERVED,
    }
    assert [message["type"] for message in socket.sent].count(
        "input_audio_buffer.commit"
    ) == 0
    socket.push(
        {
            "type": "input_audio_buffer.committed",
            "item_id": "vad-item-1",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "vad-item-1",
            "transcript": "provider time final",
        }
    )
    committed = await provider.next_recognition_event(ref, timeout_seconds=1)
    final = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert isinstance(committed, RecognitionTurnBoundaryEvent)
    assert committed.kind is RecognitionTurnBoundaryKind.COMMITTED
    assert final.kind is RecognitionEventKind.FINAL
    assert final.audio_cursor is None
    assert final.timing_basis is RecognitionTimingBasis.PROVIDER_TIME
    assert final.hypothesis is not None
    assert final.hypothesis.selected.display_text == "provider time final"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_manual_commit_wins_server_vad_race_without_a_second_commit() -> None:
    socket = BlockingCommitSocket((session_updated_event(server_vad_wire()),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    await provider.open_recognition(
        RecognitionStreamRequest(ref, RecognitionTurnDetection.server_vad_default()),
        timeout_seconds=2,
    )
    await provider.send_recognition_audio(recognition_frame(ref))
    socket.push(
        {
            "type": "input_audio_buffer.speech_started",
            "item_id": "manual-race-item",
            "audio_start_ms": 20,
        }
    )
    started = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert isinstance(started, RecognitionTurnBoundaryEvent)

    manual_commit = asyncio.create_task(provider.commit_recognition(ref))
    await asyncio.wait_for(socket.commit_started.wait(), timeout=1)
    socket.push(
        {
            "type": "input_audio_buffer.speech_stopped",
            "item_id": "manual-race-item",
            "audio_end_ms": 140,
        }
    )
    await asyncio.sleep(0)
    socket.release_commit.set()
    assert (
        await asyncio.wait_for(manual_commit, timeout=1)
        is RecognitionCommitDisposition.CLIENT_COMMIT_SENT
    )
    stopped = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert isinstance(stopped, RecognitionTurnBoundaryEvent)
    assert stopped.kind is RecognitionTurnBoundaryKind.SPEECH_STOPPED
    assert [message["type"] for message in socket.sent].count(
        "input_audio_buffer.commit"
    ) == 1

    socket.push(
        {
            "type": "input_audio_buffer.committed",
            "item_id": "manual-race-item",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "manual-race-item",
            "transcript": "manual wins",
        }
    )
    final = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert final.kind is RecognitionEventKind.FINAL
    assert final.audio_cursor == 4
    assert final.timing_basis is RecognitionTimingBasis.EXACT_SOURCE_CURSOR
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_server_vad_wrong_item_fails_closed_without_business_effects() -> None:
    socket = FakeSocket((session_updated_event(server_vad_wire()),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    await provider.open_recognition(
        RecognitionStreamRequest(ref, RecognitionTurnDetection.server_vad_default()),
        timeout_seconds=2,
    )
    socket.push(
        {
            "type": "input_audio_buffer.speech_started",
            "item_id": "vad-item-1",
            "audio_start_ms": 10,
        }
    )
    socket.push(
        {
            "type": "input_audio_buffer.speech_stopped",
            "item_id": "forged-item",
            "audio_end_ms": 20,
        }
    )
    started = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert isinstance(started, RecognitionTurnBoundaryEvent)
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    with pytest.raises(OpenAIStreamingSpeechError) as failed:
        await provider.next_recognition_event(ref, timeout_seconds=1)
    assert failed.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert (
        provider.degradation_facts[-1].reason
        is SpeechDegradationReason.PROVIDER_PROTOCOL
    )
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_whisper_one_server_vad_is_not_locally_rejected() -> None:
    socket_calls = 0
    effective = session_updated_event(server_vad_wire())
    effective["session"]["audio"]["input"]["transcription"]["model"] = "whisper-1"
    socket = FakeSocket((effective,))

    async def socket_factory(*_args) -> FakeSocket:
        nonlocal socket_calls
        socket_calls += 1
        return socket

    provider = OpenAIStreamingSpeechProvider(
        replace(config(), stt_model="whisper-1"),
        socket_factory=socket_factory,
    )
    ref = recognition_ref()
    await provider.open_recognition(
        RecognitionStreamRequest(ref, RecognitionTurnDetection.server_vad_default()),
        timeout_seconds=1,
    )
    assert socket_calls == 1
    assert socket.sent[0]["session"]["audio"]["input"]["transcription"] == {
        "model": "whisper-1"
    }
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_unsupported_sample_rates_fail_before_provider_allocation() -> None:
    allocations = 0

    async def forbidden_factory(*_args):
        nonlocal allocations
        allocations += 1
        raise AssertionError("Provider transport must not be allocated")

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=forbidden_factory, sse_factory=forbidden_factory
    )
    bad_ref = RecognitionStreamRef(
        "recognition-rate", 0, CaptureRef("capture-rate", 0, 7_999)
    )
    with pytest.raises(OpenAIStreamingSpeechError) as bad_recognition:
        await provider.open_recognition(bad_ref, timeout_seconds=1)
    assert bad_recognition.value.reason == "SPEECH_SAMPLE_RATE_UNSUPPORTED"

    request = replace(synthesis_request(), sample_rate_hz=192_001)
    provider.conformance.activate_response(request.ref.response)
    with pytest.raises(OpenAIStreamingSpeechError) as bad_synthesis:
        await provider.open_synthesis(request)
    assert bad_synthesis.value.reason == "SPEECH_SAMPLE_RATE_UNSUPPORTED"
    assert allocations == 0
    assert provider.conformance.snapshot().active_recognition == 0
    assert provider.conformance.snapshot().active_synthesis == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_cancelled_recognition_registration_rolls_back_exact_session() -> None:
    socket = FakeSocket((session_updated_event(),))
    socket_allocated = asyncio.Event()

    async def socket_factory(*_args) -> FakeSocket:
        socket_allocated.set()
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    await provider._lock.acquire()
    open_task = asyncio.create_task(
        provider.open_recognition(recognition_ref(), timeout_seconds=1)
    )
    await asyncio.wait_for(socket_allocated.wait(), timeout=1)
    await asyncio.sleep(0)
    open_task.cancel()
    provider._lock.release()
    with pytest.raises(asyncio.CancelledError):
        await open_task
    snapshot = provider.conformance.snapshot()
    assert snapshot.active_recognition == snapshot.retained_recognition == 0
    assert socket.closed is True
    assert provider.degradation_facts == ()
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_cancelled_synthesis_registration_rolls_back_exact_session() -> None:
    provider = OpenAIStreamingSpeechProvider(config())
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider._lock.acquire()
    open_task = asyncio.create_task(provider.open_synthesis(request))
    while provider.conformance.snapshot().active_synthesis == 0:
        await asyncio.sleep(0)
    open_task.cancel()
    provider._lock.release()
    with pytest.raises(asyncio.CancelledError):
        await open_task
    snapshot = provider.conformance.snapshot()
    assert snapshot.active_synthesis == snapshot.retained_synthesis == 0
    assert provider.degradation_facts == ()
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_realtime_recognition_resamples_and_orders_partial_then_final() -> None:
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> FakeSocket:
        # The transcription snapshot must not be the realtime session model; the
        # server rejects that with invalid_model. It travels in session.update as
        # session.audio.input.transcription.model instead.
        assert url == "wss://api.openai.com/v1/realtime?intent=transcription"
        assert headers["Authorization"].startswith("Bearer ")
        assert timeout > 0
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2)
    await provider.send_recognition_audio(recognition_frame(ref))
    await provider.commit_recognition(ref)
    assert [item["type"] for item in socket.sent] == [
        "session.update",
        "input_audio_buffer.append",
        "input_audio_buffer.commit",
    ]
    sent_at_commit = tuple(socket.sent)
    with pytest.raises(OpenAIStreamingSpeechError) as post_commit:
        await provider.send_recognition_audio(second_recognition_frame(ref))
    assert post_commit.value.reason == "RECOGNITION_AUDIO_AFTER_COMMIT"
    assert tuple(socket.sent) == sent_at_commit
    assert provider.degradation_facts == ()
    socket.push(
        {
            "type": "input_audio_buffer.committed",
            "item_id": "item-1",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "content_index": 0,
            "item_id": "item-1",
            "delta": "hello",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "item-1",
            "transcript": "hello world",
        }
    )
    partial = await provider.next_recognition_event(ref, timeout_seconds=1)
    final = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert (partial.seq, partial.kind, partial.audio_cursor) == (
        0,
        RecognitionEventKind.PARTIAL,
        4,
    )
    assert partial.hypothesis is not None
    assert partial.hypothesis.selected.display_text == "hello"
    assert (final.seq, final.kind, final.audio_cursor) == (
        1,
        RecognitionEventKind.FINAL,
        4,
    )
    assert socket.closed is True
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_commit_atomically_fences_concurrent_audio_at_frozen_cursor() -> None:
    socket = BlockingCommitSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2)
    await provider.send_recognition_audio(recognition_frame(ref))
    commit_task = asyncio.create_task(provider.commit_recognition(ref))
    await asyncio.wait_for(socket.commit_started.wait(), timeout=1)
    late_send_task = asyncio.create_task(
        provider.send_recognition_audio(second_recognition_frame(ref))
    )
    await asyncio.sleep(0)
    assert late_send_task.done() is False
    socket.release_commit.set()
    await asyncio.wait_for(commit_task, timeout=1)
    with pytest.raises(OpenAIStreamingSpeechError) as late_send:
        await asyncio.wait_for(late_send_task, timeout=1)
    assert late_send.value.reason == "RECOGNITION_AUDIO_AFTER_COMMIT"
    assert [item["type"] for item in socket.sent] == [
        "session.update",
        "input_audio_buffer.append",
        "input_audio_buffer.commit",
    ]
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "concurrent-item",
            "transcript": "committed",
        }
    )
    final = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert final.audio_cursor == 4
    assert final.kind is RecognitionEventKind.FINAL
    assert provider.degradation_facts == ()
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_effective_transcription_session_mismatch_fails_closed() -> None:
    facts: list[SpeechDegradationFact] = []
    private_transcript = "private-provider-transcript"
    mismatched = session_updated_event()
    mismatched["session"]["audio"]["input"]["transcription"]["model"] = "other-model"
    mismatched["session"]["private_transcript"] = private_transcript
    socket = FakeSocket((mismatched,))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    with pytest.raises(OpenAIStreamingSpeechError) as exc_info:
        await provider.open_recognition(recognition_ref(), timeout_seconds=1)
    assert exc_info.value.reason == "SPEECH_PROVIDER_SESSION_MISMATCH"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert private_transcript not in adapter_traceback_with_locals(exc_info.value)
    assert socket.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert facts[-1].visible is True
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_ga_server_vad_echo_without_response_fields_opens_the_stream() -> None:
    """The real GA transcription session echoes only the fields it governs.

    ``create_response``/``interrupt_response`` belong to the realtime response
    API, so a transcription session drops them from ``session.updated``. Byte
    equality with the request rejected every real ``server_vad`` open, which
    silently degraded every dedicated-media capture to the text tier.
    """

    ga_echo = {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500,
    }
    socket = FakeSocket((session_updated_event(ga_echo),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    await provider.open_recognition(
        RecognitionStreamRequest(ref, RecognitionTurnDetection.server_vad_default()),
        timeout_seconds=2,
    )

    # The request still pins response generation off on every session shape.
    assert (
        socket.sent[0]["session"]["audio"]["input"]["turn_detection"]
        == server_vad_wire()
    )
    assert provider.conformance.snapshot().active_recognition == 1
    assert socket.closed is False
    await provider.cancel_recognition(ref)
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_unknown_server_vad_echo_field_still_fails_closed() -> None:
    facts: list[SpeechDegradationFact] = []
    unknown_echo = {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500,
        "eagerness": "high",
    }
    socket = FakeSocket((session_updated_event(unknown_echo),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    with pytest.raises(OpenAIStreamingSpeechError) as exc_info:
        await provider.open_recognition(
            RecognitionStreamRequest(
                recognition_ref(), RecognitionTurnDetection.server_vad_default()
            ),
            timeout_seconds=1,
        )
    assert exc_info.value.reason == "SPEECH_PROVIDER_SESSION_MISMATCH"
    assert socket.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_effective_server_vad_response_creation_mismatch_fails_closed() -> None:
    facts: list[SpeechDegradationFact] = []
    mismatched_vad = server_vad_wire()
    mismatched_vad["create_response"] = True
    socket = FakeSocket((session_updated_event(mismatched_vad),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    with pytest.raises(OpenAIStreamingSpeechError) as exc_info:
        await provider.open_recognition(
            RecognitionStreamRequest(
                recognition_ref(), RecognitionTurnDetection.server_vad_default()
            ),
            timeout_seconds=1,
        )
    assert exc_info.value.reason == "SPEECH_PROVIDER_SESSION_MISMATCH"
    assert socket.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_precommit_partials_order_then_final_uses_frozen_commit_cursor() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=1)
    await provider.send_recognition_audio(recognition_frame(ref))
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "content_index": 0,
            "item_id": "item-early",
            "delta": "hello",
        }
    )
    first = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert (first.seq, first.kind, first.audio_cursor) == (
        0,
        RecognitionEventKind.PARTIAL,
        4,
    )
    await provider.send_recognition_audio(second_recognition_frame(ref))
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "content_index": 0,
            "item_id": "item-early",
            "delta": " world",
        }
    )
    second = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert (second.seq, second.kind, second.audio_cursor) == (
        1,
        RecognitionEventKind.PARTIAL,
        8,
    )
    assert second.hypothesis is not None
    assert second.hypothesis.selected.display_text == "hello world"

    await provider.commit_recognition(ref)
    socket.push(
        {
            "type": "input_audio_buffer.committed",
            "item_id": "item-early",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "item-early",
            "transcript": "hello world",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "content_index": 0,
            "item_id": "item-early",
            "delta": " late",
        }
    )
    final = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert (final.seq, final.kind, final.audio_cursor) == (
        2,
        RecognitionEventKind.FINAL,
        8,
    )
    assert socket.closed is True
    assert facts == []
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_recognition_event(ref, timeout_seconds=0.01)
    assert retired.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_recognition_final_before_local_commit_fails_closed() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=1)
    await provider.send_recognition_audio(recognition_frame(ref))
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "item-precommit-final",
            "transcript": "must not escape",
        }
    )
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_recognition_event(ref, timeout_seconds=0.01)
    assert retired.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert facts[-1].to_tier is SpeechRouteTier.TEXT
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_recognition_queue_exhaustion_emits_one_closed_reason() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    # A consumer that never drains must still exhaust the stream. The budget is
    # explicit here so the assertion measures fail-closed behaviour rather than
    # the production wait that ordinary real-time pacing needs.
    provider = OpenAIStreamingSpeechProvider(
        config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
        event_queue_wait_seconds=0.05,
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2)
    await provider.send_recognition_audio(recognition_frame(ref))
    await provider.commit_recognition(ref)
    for seq in range(65):
        socket.push(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "content_index": 0,
                "item_id": "item-bounded",
                "delta": str(seq % 10),
            }
        )
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.BOUNDED_QUEUE_EXHAUSTED
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_item_mismatch_fails_closed_without_publishing_late_final() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2)
    await provider.send_recognition_audio(recognition_frame(ref))
    await provider.commit_recognition(ref)
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "content_index": 0,
            "item_id": "item-1",
            "delta": "hello",
        }
    )
    first = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert first.kind is RecognitionEventKind.PARTIAL
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "item-2",
            "transcript": "wrong",
        }
    )
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_recognition_event(ref, timeout_seconds=0.01)
    assert retired.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert facts[-1].visible is True
    assert facts[-1].x_obs_event is None
    assert facts[-1].x_obs_metric is None
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    ("include_content_index", "content_index"),
    [
        pytest.param(False, None, id="missing"),
        pytest.param(True, None, id="null"),
        pytest.param(True, False, id="false"),
        pytest.param(True, 1, id="wrong-int"),
    ],
)
@pytest.mark.asyncio
async def test_non_primary_transcription_content_fails_closed(
    include_content_index: bool, content_index: object
) -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2)
    await provider.send_recognition_audio(recognition_frame(ref))
    await provider.commit_recognition(ref)
    socket.push(
        {
            "type": "input_audio_buffer.committed",
            "item_id": "item-1",
        }
    )
    completed: dict[str, object] = {
        "type": "conversation.item.input_audio_transcription.completed",
        "item_id": "item-1",
        "transcript": "wrong content",
    }
    if include_content_index:
        completed["content_index"] = content_index
    socket.push(completed)
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_recognition_event(ref, timeout_seconds=0.01)
    assert retired.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_audio_transport_failure_fences_and_emits_safe_fallback() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FailingSendSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2)
    with pytest.raises(OpenAIStreamingSpeechError) as failed:
        await provider.send_recognition_audio(recognition_frame(ref))
    assert failed.value.reason == "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE"
    assert failed.value.__cause__ is None
    assert failed.value.__context__ is None
    assert "private-wire-payload" not in adapter_traceback_with_locals(failed.value)
    assert socket.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_UNAVAILABLE
    assert facts[-1].to_tier is SpeechRouteTier.TEXT
    assert provider.degradation_facts[-1] == facts[-1]
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_recognition_deadline_closes_transport_and_retains_cancel_truth() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=0.02)
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert socket.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_TIMEOUT
    snapshot = provider.conformance.snapshot()
    assert snapshot.active_recognition == 0
    assert snapshot.pending_provider_controls == 0
    assert snapshot.retained_identity_tombstones == 1
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_recognition_deadline_bounds_connect_before_socket_allocation() -> None:
    facts: list[SpeechDegradationFact] = []
    cancelled = asyncio.Event()

    async def blocking_socket_factory(*_args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    provider = OpenAIStreamingSpeechProvider(
        config(),
        socket_factory=blocking_socket_factory,
        degradation_sink=facts.append,
    )
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            provider.open_recognition(recognition_ref(), timeout_seconds=0.02),
            timeout=1,
        )
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_TIMEOUT
    snapshot = provider.conformance.snapshot()
    assert snapshot.active_recognition == 0
    assert snapshot.retained_identity_tombstones == 1
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_x_obs_sink_failure_does_not_hide_retained_visible_fact() -> None:
    private_sink_error = "private-sink-error"
    logs = CapturingLogHandler()

    def failing_sink(_fact: SpeechDegradationFact) -> None:
        raise RuntimeError(private_sink_error)

    provider = OpenAIStreamingSpeechProvider(
        config(),
        socket_factory=_unavailable_socket_factory,
        degradation_sink=failing_sink,
    )
    _LOGGER.addHandler(logs)
    try:
        with pytest.raises(OpenAIStreamingSpeechError) as unavailable:
            await provider.open_recognition(recognition_ref(), timeout_seconds=1)
    finally:
        _LOGGER.removeHandler(logs)
    assert unavailable.value.reason == "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE"
    assert provider.degradation_facts[-1].visible is True
    assert provider.degradation_facts[-1].x_obs_event is None
    assert provider.degradation_facts[-1].x_obs_metric is None
    assert "private-test-key" not in json.dumps(
        provider.degradation_facts[-1].safe_dict()
    )
    safe_logs = "\n".join(logs.messages)
    assert private_sink_error not in safe_logs
    assert "reason=sync-error" in safe_logs
    snapshot = provider.conformance.snapshot()
    assert snapshot.retained_recognition == 0
    assert snapshot.retained_identity_tombstones == 1
    await provider.close()


@pytest.mark.asyncio
async def test_untrusted_connect_exception_drops_secret_traceback_and_chain() -> None:
    private_provider_value = "private-connect-provider-value"

    async def failing_socket_factory(_url, headers, _timeout):
        raise RuntimeError(f"{headers['Authorization']}:{private_provider_value}")

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=failing_socket_factory
    )
    with pytest.raises(OpenAIStreamingSpeechError) as exc_info:
        await provider.open_recognition(recognition_ref(), timeout_seconds=1)
    assert exc_info.value.reason == "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    formatted = adapter_traceback_with_locals(exc_info.value)
    assert "private-test-key" not in formatted
    assert private_provider_value not in formatted
    assert "Authorization" not in formatted
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_malformed_provider_json_drops_raw_traceback_and_chain() -> None:
    private_raw = 'private-malformed-provider-value:{"unterminated"'
    socket = FakeSocket()
    socket.push(private_raw)

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    with pytest.raises(OpenAIStreamingSpeechError) as exc_info:
        await provider.open_recognition(recognition_ref(), timeout_seconds=1)
    assert exc_info.value.reason == "SPEECH_PROVIDER_INVALID_JSON"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert private_raw not in adapter_traceback_with_locals(exc_info.value)
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_async_x_obs_sink_is_bounded_cancelled_and_never_blocks_cleanup() -> None:
    sink_started = asyncio.Event()
    sink_cancelled = asyncio.Event()
    logs = CapturingLogHandler()

    async def hanging_sink(_fact: SpeechDegradationFact) -> None:
        sink_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            sink_cancelled.set()

    provider = OpenAIStreamingSpeechProvider(
        config(),
        socket_factory=_unavailable_socket_factory,
        degradation_sink=hanging_sink,
    )
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    _LOGGER.addHandler(logs)
    try:
        with pytest.raises(OpenAIStreamingSpeechError) as unavailable:
            await provider.open_recognition(recognition_ref(), timeout_seconds=1)
    finally:
        _LOGGER.removeHandler(logs)
    elapsed = loop.time() - started_at
    assert unavailable.value.reason == "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE"
    assert elapsed < 0.5
    await asyncio.wait_for(sink_started.wait(), timeout=1)
    await asyncio.wait_for(sink_cancelled.wait(), timeout=1)
    assert provider.degradation_facts[-1].visible is True
    assert "reason=timeout" in "\n".join(logs.messages)
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_cancel_swallowing_sink_is_hard_capped_and_close_is_bounded() -> None:
    release = asyncio.Event()
    started = 0
    logs = CapturingLogHandler()

    async def cancel_swallowing_sink(_fact: SpeechDegradationFact) -> None:
        nonlocal started
        started += 1
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue

    fact = _degradation_fact(
        operation="recognition.stream",
        reason=SpeechDegradationReason.PROVIDER_UNAVAILABLE,
        from_tier=SpeechRouteTier.STREAMING,
        to_tier=SpeechRouteTier.TEXT,
        provider_id="test-provider",
        latency_ms=None,
        identity="bounded-sink-test",
    )
    owner = _DegradationSinkTaskOwner()
    _LOGGER.addHandler(logs)
    try:
        for _ in range(MAX_DEGRADATION_SINK_TASKS_PER_OWNER + 2):
            await owner.publish(fact, cancel_swallowing_sink)
        assert owner.retained_task_count == MAX_DEGRADATION_SINK_TASKS_PER_OWNER
        assert started == MAX_DEGRADATION_SINK_TASKS_PER_OWNER
        await asyncio.wait_for(owner.close(), timeout=0.5)
    finally:
        release.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if owner.retained_task_count == 0:
                break
        _LOGGER.removeHandler(logs)
    assert owner.retained_task_count == 0
    safe_logs = "\n".join(logs.messages)
    assert "reason=owner-capacity" in safe_logs
    assert "reason=close-timeout" in safe_logs


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    "process_control_type", [KeyboardInterrupt, SystemExit, GeneratorExit]
)
async def test_sink_process_control_is_cleaned_up_and_rethrown(
    process_control_type: type[BaseException], asynchronous: bool
) -> None:
    owner = _DegradationSinkTaskOwner()
    fact = _degradation_fact(
        operation="recognition.stream",
        reason=SpeechDegradationReason.PROVIDER_UNAVAILABLE,
        from_tier=SpeechRouteTier.STREAMING,
        to_tier=SpeechRouteTier.TEXT,
        provider_id="test-provider",
        latency_ms=None,
        identity="sink-process-control",
    )

    def sync_sink(_fact: SpeechDegradationFact) -> None:
        raise process_control_type()

    async def async_sink(_fact: SpeechDegradationFact) -> None:
        raise process_control_type()

    sink = async_sink if asynchronous else sync_sink
    with pytest.raises(process_control_type):
        await owner.publish(fact, sink)
    assert owner.retained_task_count == 0
    await owner.close()


@pytest.mark.asyncio
async def test_transport_cleanup_owner_hard_caps_cancel_swallowing_tasks() -> None:
    owner = _TransportCleanupOwner()
    release = asyncio.Event()
    started = 0
    resources = [object() for _ in range(MAX_INCOMPLETE_TRANSPORT_CLEANUPS + 1)]

    async def noncooperative_cleanup() -> None:
        nonlocal started
        started += 1
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue

    results = await asyncio.gather(
        *(
            owner.attempt(
                kind="socket", resource=resource, cleanup=noncooperative_cleanup
            )
            for resource in resources[:-1]
        )
    )
    assert results == [False] * MAX_INCOMPLETE_TRANSPORT_CLEANUPS
    assert started == MAX_INCOMPLETE_TRANSPORT_CLEANUPS
    assert owner.snapshot().retained_task_count == MAX_INCOMPLETE_TRANSPORT_CLEANUPS
    overflow = await owner.attempt(
        kind="socket", resource=resources[-1], cleanup=noncooperative_cleanup
    )
    assert overflow is False
    assert started == MAX_INCOMPLETE_TRANSPORT_CLEANUPS
    incomplete = await asyncio.wait_for(owner.close(), timeout=0.5)
    assert incomplete.clean is False
    assert incomplete.retained_task_count == MAX_INCOMPLETE_TRANSPORT_CLEANUPS

    release.set()
    for _ in range(50):
        await asyncio.sleep(0)
        if owner.snapshot().clean:
            break
    assert (await owner.close()).clean is True


@pytest.mark.asyncio
async def test_recognition_cancel_is_local_fence_not_provider_ack() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2)
    await provider.send_recognition_audio(recognition_frame(ref))
    await provider.cancel_recognition(ref)
    assert socket.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED
    snapshot = provider.conformance.snapshot()
    assert snapshot.active_recognition == 0
    assert snapshot.retained_recognition == 0
    assert snapshot.retained_identity_tombstones == 1
    with pytest.raises(StreamingSpeechViolation) as fenced:
        provider.conformance.accept_recognition_event(
            replace(
                # An unavailable cancel ACK cannot be manufactured from close.
                _cancelled_recognition_event(ref),
                audio_cursor=4,
            )
        )
    assert fenced.value.reason == "STALE_RECOGNITION_SESSION"
    with pytest.raises(StreamingSpeechViolation) as reused:
        await provider.open_recognition(ref, timeout_seconds=1)
    assert reused.value.reason == "STALE_RECOGNITION_GENERATION"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_noncooperative_socket_close_is_retained_and_reported() -> None:
    socket = CancellationDefiantCloseSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=1)
    try:
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        await asyncio.wait_for(provider.cancel_recognition(ref), timeout=0.5)
        assert loop.time() - started_at < 0.4
        assert socket.closed is False
        assert provider.cleanup_snapshot.clean is False
        assert provider.cleanup_snapshot.retained_task_count == 1

        with pytest.raises(OpenAIStreamingSpeechError) as incomplete:
            await asyncio.wait_for(provider.close(), timeout=0.5)
        assert incomplete.value.reason == "SPEECH_PROVIDER_CLEANUP_INCOMPLETE"
    finally:
        socket.release_close.set()
        await asyncio.wait_for(socket.close_returned.wait(), timeout=1)
        await provider.close()
    assert provider.cleanup_snapshot.clean is True


@pytest.mark.asyncio
async def test_recognition_process_control_cleans_up_and_rethrows() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, degradation_sink=facts.append
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=1)
    session = provider._require_recognition(ref)
    assert session.receive_task is not None
    receive_task = session.receive_task
    socket.push(GeneratorExit())
    with pytest.raises(GeneratorExit):
        await receive_task
    assert socket.closed is True
    assert facts == []
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


def _cancelled_recognition_event(ref: RecognitionStreamRef):
    from jiuwenswarm.server.live_voice.streaming_speech import (
        StreamingRecognitionEvent,
    )

    return StreamingRecognitionEvent(
        ref=ref,
        provider=OpenAIStreamingSpeechProvider(config()).capability.provider,
        seq=0,
        audio_cursor=0,
        kind=RecognitionEventKind.CANCELLED,
    )


@pytest.mark.asyncio
async def test_streaming_tts_sse_has_derived_cursor_and_request_level_text_provenance() -> (
    None
):
    pcm = struct.pack("<hhhh", 0, 1000, -1000, 0)
    stream = FakeSseStream(
        (
            "data: "
            + json.dumps(
                {
                    "type": "speech.audio.delta",
                    "audio": base64.b64encode(pcm).decode("ascii"),
                }
            ),
            "",
            'data: {"type":"speech.audio.done","usage":{}}',
            "",
        )
    )
    captured: dict[str, object] = {}

    async def sse_factory(url, headers, payload, timeout):
        captured.update(
            url=url, headers=dict(headers), payload=dict(payload), timeout=timeout
        )
        return stream

    provider = OpenAIStreamingSpeechProvider(config(), sse_factory=sse_factory)
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    started = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    chunk1 = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    chunk2 = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    completed = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    assert started.kind is SynthesisEventKind.STARTED
    assert chunk1.kind is chunk2.kind is SynthesisEventKind.CHUNK
    assert chunk1.sample_cursor == 0
    assert chunk2.sample_cursor == chunk1.sample_count
    assert chunk1.display_span is chunk1.spoken_span is None
    assert completed.kind is SynthesisEventKind.COMPLETED
    assert completed.sample_cursor == chunk1.sample_count + chunk2.sample_count == 8
    assert captured["url"] == "https://api.openai.com/v1/audio/speech"
    assert captured["payload"] == {
        "model": "gpt-4o-mini-tts",
        "voice": "marin",
        "input": "A P I",
        "response_format": "pcm",
        "stream_format": "sse",
    }
    assert stream.closed is True
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_tts_request_failure_retains_only_safe_fact_and_no_task_exception() -> (
    None
):
    private_transport_value = "private-tts-transport-value"
    request_started = asyncio.Event()
    release_request = asyncio.Event()
    fact_ready = asyncio.Event()
    facts: list[SpeechDegradationFact] = []
    provider_task: asyncio.Task[object] | None = None
    logs = CapturingLogHandler()

    async def failing_sse_factory(_url, headers, payload, _timeout):
        nonlocal provider_task
        provider_task = asyncio.current_task()
        request_started.set()
        await release_request.wait()
        raise RuntimeError(
            f"{headers['Authorization']}:{payload['input']}:{private_transport_value}"
        )

    def sink(fact: SpeechDegradationFact) -> None:
        facts.append(fact)
        fact_ready.set()

    provider = OpenAIStreamingSpeechProvider(
        config(), sse_factory=failing_sse_factory, degradation_sink=sink
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await asyncio.wait_for(request_started.wait(), timeout=1)
    assert provider_task is not None
    _LOGGER.addHandler(logs)
    try:
        release_request.set()
        await asyncio.wait_for(fact_ready.wait(), timeout=1)
        await asyncio.wait_for(provider_task, timeout=1)
    finally:
        _LOGGER.removeHandler(logs)
    assert provider_task.exception() is None
    assert provider_task.get_stack() == []
    safe_fact = json.dumps(facts[-1].safe_dict())
    assert "private-test-key" not in safe_fact
    assert request.spoken_text not in safe_fact
    assert private_transport_value not in safe_fact
    safe_logs = "\n".join(logs.messages)
    assert "private-test-key" not in safe_logs
    assert request.spoken_text not in safe_logs
    assert private_transport_value not in safe_logs
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_UNAVAILABLE
    assert provider.conformance.snapshot().active_synthesis == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_synthesis_sse_event_bytes_are_bounded_and_visible() -> None:
    facts: list[SpeechDegradationFact] = []
    fragment = "x" * 250_000
    stream = FakeSseStream(tuple(f"data: {fragment}" for _ in range(5)) + ("",))

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(
        config(), sse_factory=sse_factory, degradation_sink=facts.append
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    started = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    assert started.kind is SynthesisEventKind.STARTED
    await asyncio.wait_for(stream.closed_event.wait(), timeout=1)
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert provider.conformance.snapshot().active_synthesis == 0
    assert_zero_business_effects(provider)
    await provider.close()


def test_stateful_resampling_is_invariant_to_provider_chunk_boundaries() -> None:
    samples = [0.0, 0.2, -0.4, 0.8, -1.0, 0.5, 0.25]
    one = _StreamingLinearResampler(24_000, 48_000)
    one_result = one.feed(samples) + one.finish()

    split = _StreamingLinearResampler(24_000, 48_000)
    split_result = (
        split.feed(samples[:2])
        + split.feed(samples[2:5])
        + split.feed(samples[5:])
        + split.finish()
    )
    assert split_result == one_result
    assert len(one_result) == (len(samples) * 48_000) // 24_000


@pytest.mark.asyncio
async def test_synthesis_cancel_closes_transport_without_cancelled_event() -> None:
    facts: list[SpeechDegradationFact] = []
    stream = BlockingSseStream()

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(
        config(), sse_factory=sse_factory, degradation_sink=facts.append
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    started = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    assert started.kind is SynthesisEventKind.STARTED
    await provider.cancel_synthesis(request.ref)
    assert stream.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_noncooperative_stream_close_is_retained_and_reported() -> None:
    stream = CancellationDefiantCloseStream()

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(config(), sse_factory=sse_factory)
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    try:
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        await asyncio.wait_for(provider.cancel_synthesis(request.ref), timeout=0.5)
        assert loop.time() - started_at < 0.4
        assert stream.closed is False
        assert provider.cleanup_snapshot.clean is False
        assert provider.cleanup_snapshot.retained_task_count == 1

        with pytest.raises(OpenAIStreamingSpeechError) as incomplete:
            await asyncio.wait_for(provider.close(), timeout=0.5)
        assert incomplete.value.reason == "SPEECH_PROVIDER_CLEANUP_INCOMPLETE"
    finally:
        stream.release_close.set()
        await asyncio.wait_for(stream.close_returned.wait(), timeout=1)
        await provider.close()
    assert provider.cleanup_snapshot.clean is True


@pytest.mark.asyncio
async def test_synthesis_timeout_is_visible_and_bounded() -> None:
    facts: list[SpeechDegradationFact] = []
    stream = BlockingSseStream()

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(
        config(), sse_factory=sse_factory, degradation_sink=facts.append
    )
    request = synthesis_request(timeout_seconds=0.05)
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    await asyncio.wait_for(stream.closed_event.wait(), timeout=1)
    assert stream.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_TIMEOUT
    assert facts[-1].to_tier is SpeechRouteTier.TEXT
    assert provider.conformance.snapshot().active_synthesis == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_synthesis_process_control_cleans_up_and_rethrows() -> None:
    facts: list[SpeechDegradationFact] = []

    class ProcessControlStream(FakeSseStream):
        async def __aiter__(self):
            raise GeneratorExit()
            if False:
                yield ""

    stream = ProcessControlStream(())

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(
        config(), sse_factory=sse_factory, degradation_sink=facts.append
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    session = provider._require_synthesis(request.ref)
    assert session.task is not None
    synthesis_task = session.task
    with pytest.raises(GeneratorExit):
        await synthesis_task
    assert stream.closed is True
    assert facts == []
    assert provider.conformance.snapshot().active_synthesis == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    "process_control", [KeyboardInterrupt(), SystemExit(), GeneratorExit()]
)
def test_process_control_exceptions_cannot_be_classified_as_degradation(
    process_control: BaseException,
) -> None:
    with pytest.raises(TypeError):
        _reason_for_exception(process_control)


@pytest.mark.asyncio
async def test_provider_close_bounds_active_transport_cleanup_and_is_idempotent() -> (
    None
):
    socket = FakeSocket((session_updated_event(),))
    stream = BlockingSseStream()

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=socket_factory, sse_factory=sse_factory
    )
    await provider.open_recognition(recognition_ref(), timeout_seconds=2)
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)

    await asyncio.wait_for(provider.close(), timeout=1)
    await provider.close()
    assert socket.closed is True
    assert stream.closed is True
    snapshot = provider.conformance.snapshot()
    assert snapshot.closed is True
    assert snapshot.active_recognition == snapshot.active_synthesis == 0
    assert_zero_business_effects(provider)


@pytest.mark.asyncio
async def test_provider_close_cancels_pending_recognition_connect() -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocking_socket_factory(*_args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    provider = OpenAIStreamingSpeechProvider(
        config(), socket_factory=blocking_socket_factory
    )
    open_task = asyncio.create_task(
        provider.open_recognition(recognition_ref(), timeout_seconds=2)
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    await asyncio.wait_for(provider.close(), timeout=1)
    with pytest.raises(asyncio.CancelledError):
        await open_task
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert provider.degradation_facts == ()
    snapshot = provider.conformance.snapshot()
    assert snapshot.closed is True
    assert snapshot.active_recognition == 0
    assert snapshot.retained_recognition == 0
    assert snapshot.retained_identity_tombstones == 1
    assert_zero_business_effects(provider)


@pytest.mark.asyncio
async def test_provider_close_rethrows_worker_process_control_after_finalization() -> (
    None
):
    socket = ProcessControlOnCancelSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    await provider.open_recognition(recognition_ref(), timeout_seconds=1)
    await asyncio.wait_for(socket.receive_waiting.wait(), timeout=1)

    with pytest.raises(GeneratorExit):
        await asyncio.wait_for(provider.close(), timeout=1)
    snapshot = provider.conformance.snapshot()
    assert snapshot.closed is True
    assert snapshot.active_recognition == snapshot.retained_recognition == 0
    assert provider._recognition == {}
    assert provider._synthesis == {}
    assert provider._opening_recognition_tasks == set()
    assert socket.closed is True
    assert provider.cleanup_snapshot.clean is True
    assert_zero_business_effects(provider)

    await provider.close()
    assert provider.cleanup_snapshot.clean is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "process_control_type", [KeyboardInterrupt, SystemExit, GeneratorExit]
)
async def test_transport_close_process_control_retries_before_rethrow(
    process_control_type: type[BaseException],
) -> None:
    socket = ProcessControlOnceCloseSocket(
        (session_updated_event(),), process_control_type=process_control_type
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    await provider.open_recognition(recognition_ref(), timeout_seconds=1)

    with pytest.raises(process_control_type):
        await provider.close()
    snapshot = provider.conformance.snapshot()
    assert snapshot.closed is True
    assert snapshot.active_recognition == snapshot.retained_recognition == 0
    assert provider._recognition == {}
    assert provider._synthesis == {}
    assert provider._opening_recognition_tasks == set()
    assert socket.close_attempts == 2
    assert socket.closed is True
    assert provider.cleanup_snapshot.clean is True
    assert_zero_business_effects(provider)

    await provider.close()
    assert provider.cleanup_snapshot.clean is True


@pytest.mark.asyncio
async def test_selector_is_default_off_and_each_fallback_is_bound_and_visible() -> None:
    facts: list[SpeechDegradationFact] = []
    disabled = await select_environment_streaming_speech(
        environ={}, batch_available=True, degradation_sink=facts.append
    )
    assert disabled.tier is SpeechRouteTier.BATCH
    assert disabled.provider is None
    assert disabled.fact is facts[-1]
    assert disabled.fact is not None
    assert disabled.fact.reason is SpeechDegradationReason.FEATURE_OFF
    assert disabled.fact.binding_ref.startswith("sha256:")
    assert len(disabled.fact.binding_ref) == 71
    assert disabled.fact.visible is True
    assert disabled.fact.x_obs_event is None
    assert disabled.fact.x_obs_metric is None

    unavailable = await select_environment_streaming_speech(
        environ={STREAMING_SPEECH_FLAG: "true"},
        batch_available=False,
        degradation_sink=facts.append,
    )
    assert unavailable.tier is SpeechRouteTier.TEXT
    assert unavailable.fact is not None
    assert unavailable.fact.reason is SpeechDegradationReason.CONFIGURATION_UNAVAILABLE


def test_d078_streaming_probe_defaults_are_frozen() -> None:
    assert DEFAULT_STT_MODEL == "gpt-4o-mini-transcribe-2025-12-15"
    assert DEFAULT_TTS_MODEL == "gpt-4o-mini-tts-2025-12-15"
    assert DEFAULT_TTS_VOICE == "marin"


@pytest.mark.asyncio
async def test_selector_requires_the_d078_official_openai_streaming_route() -> None:
    env = {
        STREAMING_SPEECH_FLAG: "true",
        SPEECH_PROVIDER_ENV: "openai",
        SPEECH_API_BASE_ENV: "https://api.openai.com/v1",
        SPEECH_API_KEY_ENV: "server-only-key",
        SPEECH_STT_MODEL_ENV: "gpt-4o-mini-transcribe",
        SPEECH_TTS_MODEL_ENV: "gpt-4o-mini-tts",
        SPEECH_TTS_VOICE_ENV: "marin",
    }
    selected = await select_environment_streaming_speech(
        environ=env, batch_available=True
    )
    assert selected.tier is SpeechRouteTier.STREAMING
    assert selected.provider is not None
    assert selected.provider.fallback_tier is SpeechRouteTier.TEXT
    assert selected.fact is None
    assert "server-only-key" not in repr(selected.provider)
    await selected.provider.close()

    shared_env = {**env, FORMAL_BATCH_SPEECH_FLAG: "true"}
    batch_provider = create_environment_batch_speech_provider(shared_env)
    assert batch_provider.capability().available is True
    ordered = await select_environment_streaming_speech(
        environ=shared_env,
        batch_available=True,
    )
    assert ordered.tier is SpeechRouteTier.STREAMING
    assert ordered.provider is not None
    await ordered.provider.close()

    for provider, api_base in (
        ("openai-compatible", "https://api.openai.com/v1"),
        ("openai", "https://provider.example/v1"),
        ("openai", "https://api.openai.com:8443/v1"),
        ("openai", "https://api.openai.com/v1/tenant"),
    ):
        rejected = await select_environment_streaming_speech(
            environ={
                **env,
                SPEECH_PROVIDER_ENV: provider,
                SPEECH_API_BASE_ENV: api_base,
            },
            batch_available=True,
        )
        assert rejected.tier is SpeechRouteTier.BATCH
        assert rejected.provider is None
        assert rejected.fact is not None
        assert rejected.fact.reason is SpeechDegradationReason.CONFIGURATION_UNAVAILABLE


def test_provider_rejects_runtime_batch_fallback_without_operation_eligibility() -> (
    None
):
    with pytest.raises(ValueError, match="product wiring owns batch eligibility"):
        OpenAIStreamingSpeechProvider(config(), fallback_tier=SpeechRouteTier.BATCH)


@pytest.mark.asyncio
async def test_selector_binds_runtime_failure_directly_to_text_without_batch() -> None:
    facts: list[SpeechDegradationFact] = []
    env = {
        STREAMING_SPEECH_FLAG: "true",
        SPEECH_PROVIDER_ENV: "openai",
        SPEECH_API_BASE_ENV: "https://api.openai.com/v1",
        SPEECH_API_KEY_ENV: "server-only-key",
    }
    selected = await select_environment_streaming_speech(
        environ=env,
        batch_available=False,
        socket_factory=_unavailable_socket_factory,
        degradation_sink=facts.append,
    )
    assert selected.provider is not None
    assert selected.provider.fallback_tier is SpeechRouteTier.TEXT
    with pytest.raises(OpenAIStreamingSpeechError) as unavailable:
        await selected.provider.open_recognition(recognition_ref(), timeout_seconds=1)
    assert unavailable.value.reason == "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE"
    assert facts[-1].from_tier is SpeechRouteTier.STREAMING
    assert facts[-1].to_tier is SpeechRouteTier.TEXT
    await selected.provider.close()


async def _unavailable_socket_factory(*_args):
    raise ConnectionError("synthetic Provider unavailable")


@pytest.mark.asyncio
async def test_invalid_or_insecure_configuration_falls_back_without_secret_echo(
    caplog,
) -> None:
    secret = "must-not-appear"
    selected = await select_environment_streaming_speech(
        environ={
            STREAMING_SPEECH_FLAG: "true",
            SPEECH_PROVIDER_ENV: "openai",
            SPEECH_API_BASE_ENV: "http://provider.example/v1",
            SPEECH_API_KEY_ENV: secret,
        },
        batch_available=True,
    )
    assert selected.tier is SpeechRouteTier.BATCH
    assert selected.fact is not None
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_ga_transcription_item_lifecycle_events_do_not_fail_the_stream() -> None:
    """The live GA transcription session announces its committed item.

    A real ``intent=transcription`` socket emits ``conversation.item.added``
    and ``conversation.item.done`` between ``input_audio_buffer.committed`` and
    the transcript events; ``conversation.item.created`` is the retired beta
    name and is no longer sent.  Treating the GA names as unknown events aborts
    every real recognition after commit, so this order must stay accepted while
    output truth still comes only from the transcript events.
    """

    socket = FakeSocket((session_updated_event(),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    await provider.open_recognition(
        RecognitionStreamRequest(ref, RecognitionTurnDetection.manual()),
        timeout_seconds=2,
    )
    await provider.send_recognition_audio(recognition_frame(ref))
    await provider.commit_recognition(ref)
    socket.push({"type": "input_audio_buffer.committed", "item_id": "ga-item-1"})
    socket.push(
        {
            "type": "conversation.item.added",
            "item": {"id": "ga-item-1", "type": "message", "role": "user"},
        }
    )
    socket.push(
        {
            "type": "conversation.item.done",
            "item": {"id": "ga-item-1", "type": "message", "role": "user"},
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "content_index": 0,
            "item_id": "ga-item-1",
            "delta": "语音",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "ga-item-1",
            "transcript": "语音联调成功",
        }
    )
    partial = await provider.next_recognition_event(ref, timeout_seconds=1)
    final = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert partial.kind is RecognitionEventKind.PARTIAL
    assert partial.hypothesis.selected.display_text == "语音"
    assert final.kind is RecognitionEventKind.FINAL
    assert final.hypothesis.selected.display_text == "语音联调成功"
    # The item lifecycle observations produced no extra recognition output.
    assert final.seq == partial.seq + 1
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_slow_transport_close_finishes_and_releases_its_cleanup_slot() -> None:
    """A close slower than the attempt budget must still complete.

    A real WebSocket close handshake needs a network round trip and can never
    fit the attempt budget.  Cancelling it would leave the transport half-open
    and permanently retain one failed cleanup slot per stream, so a bounded
    number of streams would exhaust ``MAX_INCOMPLETE_TRANSPORT_CLEANUPS`` and
    close the route.  The caller must stay bounded while the owner finishes.
    """

    owner = _TransportCleanupOwner()
    release = asyncio.Event()
    completed = 0

    async def slow_cleanup() -> None:
        nonlocal completed
        await release.wait()
        completed += 1

    resources = [object() for _ in range(4)]
    for resource in resources:
        assert (
            await owner.attempt(
                kind="socket", resource=resource, cleanup=slow_cleanup
            )
            is False
        )
    pending = owner.snapshot()
    assert pending.retained_task_count == len(resources)
    assert pending.failed_resource_count == 0

    release.set()
    for _ in range(100):
        await asyncio.sleep(0)
        if owner.snapshot().clean:
            break
    settled = owner.snapshot()
    assert completed == len(resources)
    # Every slot is returned: nothing is retained and nothing is marked failed.
    assert settled.retained_task_count == 0
    assert settled.failed_resource_count == 0
    assert settled.clean is True
    owner.require_session_capacity(active_sessions=0)
    assert (await owner.close()).clean is True
