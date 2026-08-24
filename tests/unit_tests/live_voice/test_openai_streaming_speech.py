# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import asyncio
import base64
import json
import logging
import struct
import traceback
from collections.abc import Mapping
from contextlib import suppress
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
    DEFAULT_REALTIME_MODEL,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    MAX_DEGRADATION_SINK_TASKS_PER_OWNER,
    MAX_INCOMPLETE_TRANSPORT_CLEANUPS,
    MAX_PROVIDER_AUDIO_DELTA_BYTES,
    MAX_STREAM_AUDIO_BYTES,
    REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS,
    TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS,
    OpenAIStreamingSpeechError,
    OpenAIStreamingSpeechConfig,
    OpenAIStreamingSpeechProvider,
    SpeechDegradationFact,
    SpeechDegradationReason,
    SpeechRouteTier,
    SPEECH_REALTIME_MODEL_ENV,
    STREAMING_SPEECH_FLAG,
    _LOGGER,
    _DegradationSinkTaskOwner,
    _RealtimeSocketTerminalEof,
    _StreamingLinearResampler,
    _TransportCleanupOwner,
    _default_socket_factory,
    _degradation_fact,
    _native_response_metadata,
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
        if self.closed:
            return
        self.closed = True
        # A real WebSocket wakes an active recv owner with ConnectionClosed
        # after all frames ordered before the close handshake.  Keep the fake's
        # transport barrier equivalent so terminal-drain tests cannot confuse a
        # successful close call with an empty receive queue.
        self.incoming.put_nowait(_RealtimeSocketTerminalEof())
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


class PacedSseStream(FakeSseStream):
    def __init__(self, lines: tuple[tuple[float, str], ...]) -> None:
        super().__init__(tuple(line for _, line in lines))
        self._paced_lines = lines

    async def __aiter__(self):
        for delay_seconds, line in self._paced_lines:
            await asyncio.sleep(delay_seconds)
            yield line


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


class CoordinatedCloseSocket(FakeSocket):
    def __init__(self, initial: tuple[dict[str, object], ...] = ()) -> None:
        super().__init__(initial)
        self.close_calls = 0
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()

    async def close(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        await self.release_close.wait()
        await super().close()


class OrderedOpeningCloseSocket(FakeSocket):
    def __init__(self, wake_failure: BaseException) -> None:
        super().__init__()
        self._wake_failure = wake_failure
        self.close_started = asyncio.Event()
        self.receive_woken = asyncio.Event()
        self.release_close = asyncio.Event()

    async def recv(self) -> str | bytes:
        try:
            return await super().recv()
        finally:
            if self.close_started.is_set():
                self.receive_woken.set()

    async def close(self) -> None:
        if self.closed:
            return
        self.close_started.set()
        self.incoming.put_nowait(self._wake_failure)
        await self.release_close.wait()
        self.closed = True
        self.closed_event.set()


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


def native_config(
    realtime_model: str = "gpt-realtime-1.5",
) -> OpenAIStreamingSpeechConfig:
    return OpenAIStreamingSpeechConfig(
        api_base="https://api.openai.com/v1",
        api_key="private-test-key",
        stt_model="gpt-4o-mini-transcribe",
        tts_model="unused-in-native-mode",
        tts_voice="marin",
        realtime_model=realtime_model,
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


def native_session_updated_event(
    turn_detection: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "type": "session.updated",
        "event_id": "event-session-updated",
        "session": {
            "type": "realtime",
            "model": "gpt-realtime-1.5",
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "transcription": {"model": "gpt-4o-mini-transcribe"},
                    "turn_detection": turn_detection,
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "voice": "marin",
                },
            },
            "tools": [],
            "tool_choice": "none",
        },
    }


def native_session_created_event() -> dict[str, object]:
    return {
        "type": "session.created",
        "event_id": "event-session-created",
        "session": {"id": "session-native"},
    }


def native_synthesis_session_updated_event() -> dict[str, object]:
    event = native_session_updated_event()
    session = event["session"]
    assert isinstance(session, dict)
    audio = session["audio"]
    assert isinstance(audio, dict)
    del audio["input"]
    return event


def native_audio_event(
    kind: str,
    response_id: str,
    *,
    event_id: str | None = None,
    **payload: object,
) -> dict[str, object]:
    return {
        "type": kind,
        "event_id": event_id or f"event-{kind}",
        "response_id": response_id,
        "item_id": "native-output-item",
        "output_index": 0,
        "content_index": 0,
        **payload,
    }


def native_response_created_event(
    request: SynthesisStreamRequest, response_id: str
) -> dict[str, object]:
    return {
        "type": "response.created",
        "event_id": "event-response-created",
        "response": {
            "id": response_id,
            "object": "realtime.response",
            "status": "in_progress",
            "status_details": None,
            "usage": None,
            "output": [],
            "conversation_id": None,
            "output_modalities": ["audio"],
            "audio": {
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "voice": "marin",
                }
            },
            "metadata": _native_response_metadata(request),
        },
    }


def native_response_prelude(
    socket: FakeSocket,
    request: SynthesisStreamRequest,
    response_id: str,
    *,
    created_event: dict[str, object] | None = None,
) -> None:
    socket.push(created_event or native_response_created_event(request, response_id))
    socket.push(
        {
            "type": "response.output_item.added",
            "event_id": "event-output-item-added",
            "response_id": response_id,
            "output_index": 0,
            "item": {
                "id": "native-output-item",
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        }
    )
    socket.push(
        native_audio_event(
            "response.content_part.added",
            response_id,
            part={"type": "audio", "transcript": ""},
        )
    )


def native_response_completion_events(
    request: SynthesisStreamRequest,
    response_id: str,
    *,
    terminal_output: list[dict[str, object]] | None = None,
) -> tuple[dict[str, object], ...]:
    completed_item = {
        "id": "native-output-item",
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_audio", "transcript": request.spoken_text}],
    }
    output = terminal_output if terminal_output is not None else [completed_item]
    return (
        native_audio_event(
            "response.content_part.done",
            response_id,
            part={"type": "audio", "transcript": request.spoken_text},
        ),
        {
            "type": "response.output_item.done",
            "event_id": "event-output-item-done",
            "response_id": response_id,
            "output_index": 0,
            "item": completed_item,
        },
        {
            "type": "response.done",
            "event_id": "event-response-done",
            "response": {
                "id": response_id,
                "object": "realtime.response",
                "status": "completed",
                "status_details": None,
                "metadata": _native_response_metadata(request),
                "conversation_id": None,
                "output_modalities": ["audio"],
                "audio": {
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24_000},
                        "voice": "marin",
                    }
                },
                "output": output,
                "usage": {
                    "total_tokens": 3,
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "input_token_details": {
                        "audio_tokens": 0,
                        "text_tokens": 1,
                        "image_tokens": 0,
                        "cached_tokens": 0,
                        "cached_tokens_details": {
                            "audio_tokens": 0,
                            "text_tokens": 0,
                            "image_tokens": 0,
                        },
                    },
                    "output_token_details": {
                        "audio_tokens": 1,
                        "text_tokens": 1,
                    },
                },
            },
        },
    )


def server_vad_wire() -> dict[str, object]:
    return {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 1_200,
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
    *, generation: int = 0, event_timeout_seconds: float = 1.0
) -> SynthesisStreamRequest:
    response = ResponseRef("interaction-1", f"response-{generation}", generation)
    return SynthesisStreamRequest(
        ref=SynthesisStreamRef("synthesis-1", generation, response, "unit-1", 0),
        display_text="API",
        spoken_text="A P I",
        display_span=TextSpan(10, 13),
        sample_rate_hz=48_000,
        event_timeout_seconds=event_timeout_seconds,
    )


def assert_zero_business_effects(provider: OpenAIStreamingSpeechProvider) -> None:
    snapshot = provider.conformance.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0


async def open_native_synthesis_for_test(
    *,
    facts: list[SpeechDegradationFact] | None = None,
    event_timeout_seconds: float = 1.0,
    socket: FakeSocket | None = None,
) -> tuple[
    OpenAIStreamingSpeechProvider,
    FakeSocket,
    SynthesisStreamRequest,
]:
    if socket is None:
        socket = FakeSocket(
            (
                native_session_created_event(),
                native_synthesis_session_updated_event(),
            )
        )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=(facts.append if facts is not None else None),
    )
    request = synthesis_request(event_timeout_seconds=event_timeout_seconds)
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    started = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    assert started.kind is SynthesisEventKind.STARTED
    return provider, socket, request


async def wait_for_native_buffer_size(
    provider: OpenAIStreamingSpeechProvider,
    request: SynthesisStreamRequest,
    expected_size: int,
) -> None:
    for _ in range(10_000):
        session = provider._synthesis.get(
            (request.ref.stream_id, request.ref.stream_generation)
        )
        if session is not None and len(session.pending_native_audio) == expected_size:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"native audio buffer did not reach {expected_size}")


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
        "silence_duration_ms": 1_200,
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
        "silence_duration_ms": 1_200,
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
    clock = [0.0]

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
        monotonic=lambda: clock[0],
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2.0)
    session = provider._require_recognition(ref)
    assert session.receive_task is not None
    receive_task = session.receive_task
    clock[0] = 3.0
    socket.push({"type": "rate_limits.updated", "rate_limits": []})
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    await asyncio.wait_for(receive_task, timeout=1)
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
async def test_transport_cleanup_owner_shares_one_same_key_result_only() -> None:
    owner = _TransportCleanupOwner()
    resource = object()
    other_resource = object()
    started = asyncio.Event()
    other_started = asyncio.Event()
    release = asyncio.Event()
    other_release = asyncio.Event()
    cleanup_calls = 0
    other_cleanup_calls = 0
    conflicting_cleanup_calls = 0

    async def cleanup() -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        started.set()
        await release.wait()

    async def other_cleanup() -> None:
        nonlocal other_cleanup_calls
        other_cleanup_calls += 1
        other_started.set()
        await other_release.wait()

    async def conflicting_cleanup() -> None:
        nonlocal conflicting_cleanup_calls
        conflicting_cleanup_calls += 1

    first = asyncio.create_task(
        owner.attempt(kind="socket", resource=resource, cleanup=cleanup)
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    same_key_waiter = asyncio.create_task(
        owner.attempt(kind="socket", resource=resource, cleanup=cleanup)
    )
    cancelled_waiter = asyncio.create_task(
        owner.attempt(kind="socket", resource=resource, cleanup=cleanup)
    )
    await asyncio.sleep(0)
    assert same_key_waiter.done() is False
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter
    assert cleanup_calls == 1

    assert (
        await owner.attempt(
            kind="socket", resource=resource, cleanup=conflicting_cleanup
        )
        is False
    )
    other = asyncio.create_task(
        owner.attempt(kind="socket", resource=other_resource, cleanup=other_cleanup)
    )
    await asyncio.wait_for(other_started.wait(), timeout=1)

    release.set()
    other_release.set()
    assert await asyncio.gather(first, same_key_waiter, other) == [True, True, True]
    assert cleanup_calls == 1
    assert other_cleanup_calls == 1
    assert conflicting_cleanup_calls == 0
    assert owner.snapshot().clean is True


@pytest.mark.asyncio
async def test_transport_cleanup_owner_shares_timeout_and_failure_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.openai_streaming_speech."
        "TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS",
        0.01,
    )
    owner = _TransportCleanupOwner()
    timeout_resource = object()
    timeout_started = asyncio.Event()
    timeout_release = asyncio.Event()
    timeout_calls = 0

    async def timed_out_cleanup() -> None:
        nonlocal timeout_calls
        timeout_calls += 1
        timeout_started.set()
        await timeout_release.wait()

    first_timeout = asyncio.create_task(
        owner.attempt(
            kind="socket", resource=timeout_resource, cleanup=timed_out_cleanup
        )
    )
    await asyncio.wait_for(timeout_started.wait(), timeout=1)
    timeout_waiter = asyncio.create_task(
        owner.attempt(
            kind="socket", resource=timeout_resource, cleanup=timed_out_cleanup
        )
    )
    assert await asyncio.gather(first_timeout, timeout_waiter) == [False, False]
    assert timeout_calls == 1
    assert owner.snapshot().retained_task_count == 1

    timeout_release.set()
    assert (await owner.close()).clean is True

    failure_resource = object()
    failure_started = asyncio.Event()
    failure_release = asyncio.Event()
    failure_calls = 0

    async def retryable_failed_cleanup() -> None:
        nonlocal failure_calls
        failure_calls += 1
        if failure_calls == 1:
            failure_started.set()
            await failure_release.wait()
            raise RuntimeError("injected cleanup failure")

    first_failure = asyncio.create_task(
        owner.attempt(
            kind="socket", resource=failure_resource, cleanup=retryable_failed_cleanup
        )
    )
    await asyncio.wait_for(failure_started.wait(), timeout=1)
    failure_waiter = asyncio.create_task(
        owner.attempt(
            kind="socket", resource=failure_resource, cleanup=retryable_failed_cleanup
        )
    )
    failure_release.set()
    assert await asyncio.gather(first_failure, failure_waiter) == [False, False]
    assert failure_calls == 1
    assert owner.snapshot().failed_resource_count == 1
    assert (await owner.close()).clean is True
    assert failure_calls == 2


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
async def test_final_and_explicit_close_share_cleanup_before_successor_listening() -> (
    None
):
    socket = CoordinatedCloseSocket((session_updated_event(),))
    successor_socket = FakeSocket((session_updated_event(),))
    sockets = iter((socket, successor_socket))

    async def socket_factory(*_args) -> FakeSocket:
        return next(sockets)

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=2)
    await provider.send_recognition_audio(recognition_frame(ref))
    await provider.commit_recognition(ref)
    socket.push({"type": "input_audio_buffer.committed", "item_id": "race-item"})
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "race-item",
            "transcript": "normal final",
        }
    )
    await asyncio.wait_for(socket.close_started.wait(), timeout=1)

    explicit_close = asyncio.create_task(provider._close_socket(socket))
    await asyncio.sleep(0)
    assert explicit_close.done() is False
    socket.release_close.set()
    assert await asyncio.wait_for(explicit_close, timeout=1) is True

    final = await provider.next_recognition_event(ref, timeout_seconds=1)
    assert final.kind is RecognitionEventKind.FINAL
    assert final.hypothesis is not None
    assert final.hypothesis.selected.display_text == "normal final"
    assert socket.close_calls == 1
    assert provider.cleanup_snapshot.clean is True

    successor_ref = RecognitionStreamRef(
        "recognition-1", 1, CaptureRef("capture-1", 1, 48_000)
    )
    await provider.open_recognition(successor_ref, timeout_seconds=2)
    await provider.send_recognition_audio(recognition_frame(successor_ref))
    await provider.commit_recognition(successor_ref)
    successor_socket.push(
        {"type": "input_audio_buffer.committed", "item_id": "successor-item"}
    )
    successor_socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "content_index": 0,
            "item_id": "successor-item",
            "transcript": "successor final",
        }
    )
    successor_final = await provider.next_recognition_event(
        successor_ref, timeout_seconds=1
    )
    assert successor_final.kind is RecognitionEventKind.FINAL
    assert successor_final.hypothesis is not None
    assert successor_final.hypothesis.selected.display_text == "successor final"
    assert provider.degradation_facts == ()
    assert provider.conformance.snapshot().pending_provider_controls == 0
    assert_zero_business_effects(provider)
    await provider.close()


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
async def test_synthesis_timeout_is_per_event_not_whole_stream() -> None:
    pcm = struct.pack("<hhhh", 0, 1000, -1000, 0)
    audio_delta = "data: " + json.dumps(
        {
            "type": "speech.audio.delta",
            "audio": base64.b64encode(pcm).decode("ascii"),
        }
    )
    stream = PacedSseStream(
        (
            (0.12, audio_delta),
            (0, ""),
            (0.12, audio_delta),
            (0, ""),
            (0.12, 'data: {"type":"speech.audio.done","usage":{}}'),
            (0, ""),
        )
    )

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(config(), sse_factory=sse_factory)
    request = synthesis_request(event_timeout_seconds=0.3)
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)

    events = [
        await provider.next_synthesis_event(request.ref, timeout_seconds=1)
        for _ in range(5)
    ]

    assert [event.kind for event in events] == [
        SynthesisEventKind.STARTED,
        SynthesisEventKind.CHUNK,
        SynthesisEventKind.CHUNK,
        SynthesisEventKind.CHUNK,
        SynthesisEventKind.COMPLETED,
    ]
    assert stream.closed is True
    assert provider.conformance.snapshot().active_synthesis == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_synthesis_sse_comments_do_not_renew_event_timeout() -> None:
    facts: list[SpeechDegradationFact] = []
    stream = PacedSseStream(tuple((0.04, ": keep-alive") for _ in range(5)))

    async def sse_factory(*_args):
        return stream

    provider = OpenAIStreamingSpeechProvider(
        config(), sse_factory=sse_factory, degradation_sink=facts.append
    )
    request = synthesis_request(event_timeout_seconds=0.1)
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)

    started = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    assert started.kind is SynthesisEventKind.STARTED
    await asyncio.wait_for(stream.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_TIMEOUT
    assert provider.conformance.snapshot().active_synthesis == 0
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
    request = synthesis_request(event_timeout_seconds=0.05)
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
            await owner.attempt(kind="socket", resource=resource, cleanup=slow_cleanup)
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


@pytest.mark.asyncio
async def test_default_socket_close_timeout_fits_cleanup_attempt_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class ClosedWebSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed = False

        async def send(self, message: str) -> None:
            self.sent.append(message)

        async def recv(self) -> str:
            from websockets.exceptions import ConnectionClosedOK

            raise ConnectionClosedOK(None, None)

        async def close(self) -> None:
            self.closed = True

    marker = ClosedWebSocket()

    async def connect(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return marker

    monkeypatch.setattr("websockets.connect", connect)
    result = await _default_socket_factory(
        "wss://speech.invalid/realtime", {"Authorization": "redacted"}, 5.0
    )

    assert getattr(result, "_socket") is marker
    assert captured["close_timeout"] == REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS
    assert (
        REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS < TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS
    )
    await result.send("wire-message")
    assert marker.sent == ["wire-message"]
    with pytest.raises(_RealtimeSocketTerminalEof):
        await result.recv()
    await result.close()
    assert marker.closed is True


@pytest.mark.asyncio
async def test_selector_explicitly_enables_native_realtime_without_changing_legacy() -> (
    None
):
    assert DEFAULT_REALTIME_MODEL == "gpt-realtime-1.5"
    common = {
        STREAMING_SPEECH_FLAG: "true",
        SPEECH_API_BASE_ENV: "https://api.openai.com/v1",
        SPEECH_API_KEY_ENV: "server-only-key",
        SPEECH_STT_MODEL_ENV: "gpt-4o-mini-transcribe",
        SPEECH_TTS_VOICE_ENV: "marin",
    }
    native = await select_environment_streaming_speech(
        environ={**common, SPEECH_PROVIDER_ENV: "openai-realtime"},
        batch_available=True,
    )
    assert native.tier is SpeechRouteTier.STREAMING
    assert native.provider is not None
    assert native.provider.native_realtime is True
    assert native.provider.synthesis_model == DEFAULT_REALTIME_MODEL
    assert native.provider.capability.provider.provider_id == (
        "openai-realtime-native-speech"
    )
    assert "server-only-key" not in repr(native.provider)

    legacy = await select_environment_streaming_speech(
        environ={**common, SPEECH_PROVIDER_ENV: "openai"},
        batch_available=True,
    )
    assert legacy.provider is not None
    assert legacy.provider.native_realtime is False
    assert legacy.provider.synthesis_model == DEFAULT_TTS_MODEL
    assert legacy.provider.capability.provider.provider_id == "openai-streaming-speech"

    await native.provider.close()
    await legacy.provider.close()


@pytest.mark.asyncio
async def test_selector_rejects_non_realtime_model_for_native_route() -> None:
    for rejected_model in (
        "gpt-4o",
        "gpt-realtimeevil",
        "gpt-realtime-translate",
        "gpt-realtime-whisper",
    ):
        selected = await select_environment_streaming_speech(
            environ={
                STREAMING_SPEECH_FLAG: "true",
                SPEECH_PROVIDER_ENV: "openai-realtime",
                SPEECH_API_BASE_ENV: "https://api.openai.com/v1",
                SPEECH_API_KEY_ENV: "server-only-key",
                SPEECH_REALTIME_MODEL_ENV: rejected_model,
            },
            batch_available=True,
        )
        assert selected.tier is SpeechRouteTier.BATCH
        assert selected.provider is None
        assert selected.fact is not None
        assert selected.fact.reason is SpeechDegradationReason.CONFIGURATION_UNAVAILABLE
        assert selected.fact.provider_id == "openai-realtime-native-speech"


@pytest.mark.asyncio
async def test_native_realtime_recognition_negotiates_no_response_or_tools() -> None:
    socket = FakeSocket((native_session_updated_event(server_vad_wire()),))
    captured: dict[str, object] = {}

    async def socket_factory(
        url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> FakeSocket:
        captured.update(url=url, headers=dict(headers), timeout=timeout_seconds)
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(), socket_factory=socket_factory
    )
    ref = recognition_ref()
    await provider.open_recognition(
        RecognitionStreamRequest(ref, RecognitionTurnDetection.server_vad_default()),
        timeout_seconds=1,
    )
    assert captured["url"] == (
        "wss://api.openai.com/v1/realtime?model=gpt-realtime-1.5"
    )
    assert captured["headers"] == {"Authorization": "Bearer private-test-key"}
    update = socket.sent[0]
    assert update["type"] == "session.update"
    session = update["session"]
    assert isinstance(session, dict)
    assert session["type"] == "realtime"
    assert "model" not in session
    assert session["output_modalities"] == ["audio"]
    assert session["tools"] == []
    assert session["tool_choice"] == "none"
    audio = session["audio"]
    assert isinstance(audio, dict)
    input_audio = audio["input"]
    assert isinstance(input_audio, dict)
    assert input_audio["turn_detection"] == server_vad_wire()

    await provider.send_recognition_audio(recognition_frame(ref))
    socket.push(
        {
            "type": "input_audio_buffer.speech_started",
            "event_id": "event-recognition-speech-started",
            "item_id": "item-native",
            "audio_start_ms": 10,
        }
    )
    socket.push(
        {
            "type": "input_audio_buffer.speech_stopped",
            "event_id": "event-recognition-speech-stopped",
            "item_id": "item-native",
            "audio_end_ms": 240,
        }
    )
    socket.push(
        {
            "type": "input_audio_buffer.committed",
            "event_id": "event-recognition-committed",
            "item_id": "item-native",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "event_id": "event-recognition-transcription-completed",
            "content_index": 0,
            "item_id": "item-native",
            "transcript": "调用真实智能体",
        }
    )
    observed = [
        await provider.next_recognition_event(ref, timeout_seconds=1) for _ in range(4)
    ]
    assert [event.kind for event in observed[:3]] == [
        RecognitionTurnBoundaryKind.SPEECH_STARTED,
        RecognitionTurnBoundaryKind.SPEECH_STOPPED,
        RecognitionTurnBoundaryKind.COMMITTED,
    ]
    final = observed[-1]
    assert final.kind is RecognitionEventKind.FINAL
    assert final.provider.provider_id == "openai-realtime-native-speech"
    assert final.hypothesis is not None
    assert final.hypothesis.selected.display_text == "调用真实智能体"
    assert socket.closed is True
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_recognition_rejects_session_tool_downgrade() -> None:
    updated = native_session_updated_event()
    session = updated["session"]
    assert isinstance(session, dict)
    session["tools"] = [{"type": "function", "name": "forbidden"}]
    socket = FakeSocket((updated,))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(), socket_factory=socket_factory
    )
    with pytest.raises(OpenAIStreamingSpeechError) as mismatch:
        await provider.open_recognition(recognition_ref(), timeout_seconds=1)
    assert mismatch.value.reason == "SPEECH_PROVIDER_SESSION_MISMATCH"
    assert socket.closed is True
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    ("field", "value", "remove"),
    (
        ("create_response", None, True),
        ("create_response", None, False),
        ("create_response", 0, False),
        ("create_response", True, False),
        ("interrupt_response", None, True),
        ("interrupt_response", None, False),
        ("interrupt_response", 0, False),
        ("interrupt_response", True, False),
    ),
)
@pytest.mark.asyncio
async def test_native_realtime_recognition_requires_explicit_false_vad_controls(
    field: str,
    value: object,
    remove: bool,
) -> None:
    facts: list[SpeechDegradationFact] = []
    updated = native_session_updated_event(server_vad_wire())
    session = updated["session"]
    assert isinstance(session, dict)
    audio = session["audio"]
    assert isinstance(audio, dict)
    input_config = audio["input"]
    assert isinstance(input_config, dict)
    turn_detection = input_config["turn_detection"]
    assert isinstance(turn_detection, dict)
    if remove:
        del turn_detection[field]
    else:
        turn_detection[field] = value
    socket = FakeSocket()

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = RecognitionStreamRequest(
        recognition_ref(), RecognitionTurnDetection.server_vad_default()
    )
    open_task = asyncio.create_task(
        provider.open_recognition(request, timeout_seconds=1)
    )
    for _ in range(100):
        await asyncio.sleep(0)
        if socket.sent:
            break
    assert socket.sent

    with pytest.raises(OpenAIStreamingSpeechError) as audio_not_ready:
        await provider.send_recognition_audio(recognition_frame(request.ref))
    assert audio_not_ready.value.reason == "RECOGNITION_SESSION_NOT_NEGOTIATED"
    with pytest.raises(OpenAIStreamingSpeechError) as commit_not_ready:
        await provider.commit_recognition(request.ref)
    assert commit_not_ready.value.reason == "RECOGNITION_SESSION_NOT_NEGOTIATED"
    with pytest.raises(OpenAIStreamingSpeechError) as output_not_ready:
        await provider.next_recognition_event(request.ref, timeout_seconds=0.01)
    assert output_not_ready.value.reason == "RECOGNITION_SESSION_NOT_NEGOTIATED"

    socket.push(updated)
    with pytest.raises(OpenAIStreamingSpeechError) as mismatch:
        await open_task
    assert mismatch.value.reason == "SPEECH_PROVIDER_SESSION_MISMATCH"
    assert socket.sent == [
        {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "output_modalities": ["audio"],
                "instructions": (
                    "Do not answer the user. This session only transcribes "
                    "committed input for an external authoritative agent."
                ),
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24_000},
                        "transcription": {"model": "gpt-4o-mini-transcribe"},
                        "turn_detection": server_vad_wire(),
                    },
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24_000},
                        "voice": "marin",
                    },
                },
                "tools": [],
                "tool_choice": "none",
            },
        }
    ]
    assert socket.closed is True
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_recognition_rejects_output_before_negotiation() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket()

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = RecognitionStreamRequest(
        recognition_ref(), RecognitionTurnDetection.server_vad_default()
    )
    open_task = asyncio.create_task(
        provider.open_recognition(request, timeout_seconds=1)
    )
    for _ in range(100):
        await asyncio.sleep(0)
        if socket.sent:
            break
    assert socket.sent and socket.sent[0]["type"] == "session.update"
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "event_id": "event-pre-negotiation-final",
            "content_index": 0,
            "item_id": "pre-negotiation-item",
            "transcript": "must not become final",
        }
    )
    socket.push(native_session_updated_event(server_vad_wire()))

    with pytest.raises(OpenAIStreamingSpeechError) as mismatch:
        await open_task
    assert mismatch.value.reason == "SPEECH_PROVIDER_TURN_ORDER"
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert socket.closed is True
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_recognition_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_opening_recognition_cancel_settles_ready_once() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket()

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = RecognitionStreamRequest(
        recognition_ref(), RecognitionTurnDetection.server_vad_default()
    )
    open_task = asyncio.create_task(
        provider.open_recognition(request, timeout_seconds=0.4)
    )
    for _ in range(100):
        await asyncio.sleep(0)
        if socket.sent:
            break
    assert socket.sent and socket.sent[0]["type"] == "session.update"

    await provider.cancel_recognition(request.ref)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(open_task, timeout=0.05)

    assert socket.closed is True
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_recognition_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert provider.conformance.snapshot().active_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    "wake_failure_type", (_RealtimeSocketTerminalEof, ConnectionError)
)
@pytest.mark.asyncio
async def test_native_realtime_opening_cancel_owns_close_wakeup_and_duplicate(
    wake_failure_type: type[BaseException],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts: list[SpeechDegradationFact] = []
    socket = OrderedOpeningCloseSocket(wake_failure_type())

    async def socket_factory(*_args) -> OrderedOpeningCloseSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = RecognitionStreamRequest(
        recognition_ref(), RecognitionTurnDetection.server_vad_default()
    )
    provider_closed_calls: list[RecognitionStreamRef] = []
    provider_closed = provider.conformance.provider_closed_recognition

    def record_provider_closed(ref: RecognitionStreamRef) -> None:
        provider_closed_calls.append(ref)
        provider_closed(ref)

    monkeypatch.setattr(
        provider.conformance,
        "provider_closed_recognition",
        record_provider_closed,
    )
    open_task = asyncio.create_task(
        provider.open_recognition(request, timeout_seconds=0.4)
    )
    for _ in range(100):
        await asyncio.sleep(0)
        if socket.sent:
            break
    assert socket.sent and socket.sent[0]["type"] == "session.update"
    session = provider._require_recognition(request.ref)

    first_cancel = asyncio.create_task(provider.cancel_recognition(request.ref))
    await asyncio.wait_for(socket.close_started.wait(), timeout=1)
    second_cancel = asyncio.create_task(provider.cancel_recognition(request.ref))
    await asyncio.wait_for(socket.receive_woken.wait(), timeout=1)
    for _ in range(10):
        await asyncio.sleep(0)
    ready_was_stolen = session.ready.done()
    socket.release_close.set()

    cancel_results = await asyncio.gather(
        first_cancel, second_cancel, return_exceptions=True
    )
    try:
        await asyncio.wait_for(open_task, timeout=0.05)
    except BaseException as exc:
        open_failure = exc
    else:
        open_failure = None

    assert ready_was_stolen is False
    assert cancel_results == [None, None]
    assert isinstance(open_failure, asyncio.CancelledError)
    assert socket.closed is True
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED
    assert provider_closed_calls == [request.ref]
    assert provider.conformance.snapshot().active_recognition == 0
    assert provider.conformance.snapshot().retained_recognition == 0
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_opening_cancel_finalizes_before_process_control() -> (
    None
):
    facts: list[SpeechDegradationFact] = []
    socket = OrderedOpeningCloseSocket(GeneratorExit())

    async def socket_factory(*_args) -> OrderedOpeningCloseSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = RecognitionStreamRequest(
        recognition_ref(), RecognitionTurnDetection.server_vad_default()
    )
    open_task = asyncio.create_task(
        provider.open_recognition(request, timeout_seconds=0.4)
    )
    for _ in range(100):
        await asyncio.sleep(0)
        if socket.sent:
            break
    assert socket.sent and socket.sent[0]["type"] == "session.update"

    cancel_task = asyncio.create_task(provider.cancel_recognition(request.ref))
    await asyncio.wait_for(socket.close_started.wait(), timeout=1)
    await asyncio.wait_for(socket.receive_woken.wait(), timeout=1)
    socket.release_close.set()

    with pytest.raises(GeneratorExit):
        await cancel_task
    # Process control is preserved through both owners, but only after cancel
    # has settled conformance/registry state and released the opening waiter.
    with pytest.raises(GeneratorExit):
        await asyncio.wait_for(open_task, timeout=0.05)
    snapshot = provider.conformance.snapshot()
    assert snapshot.active_recognition == snapshot.retained_recognition == 0
    assert provider._recognition == {}
    assert facts == []
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize("violation", ("missing", "replay"))
@pytest.mark.asyncio
async def test_native_realtime_recognition_requires_unique_server_event_id(
    violation: str,
) -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((native_session_updated_event(server_vad_wire()),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = RecognitionStreamRequest(
        recognition_ref(), RecognitionTurnDetection.server_vad_default()
    )
    await provider.open_recognition(request, timeout_seconds=1)
    event: dict[str, object] = {"type": "rate_limits.updated", "rate_limits": []}
    if violation == "replay":
        event["event_id"] = "event-session-updated"
    socket.push(event)

    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_recognition_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_recognition_replayed_lifecycle_releases_no_final() -> (
    None
):
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((native_session_updated_event(server_vad_wire()),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = RecognitionStreamRequest(
        recognition_ref(), RecognitionTurnDetection.server_vad_default()
    )
    await provider.open_recognition(request, timeout_seconds=1)
    session = provider._require_recognition(request.ref)
    replayed_id = "event-replayed-recognition-lifecycle"
    socket.push(
        {
            "type": "input_audio_buffer.speech_started",
            "event_id": replayed_id,
            "item_id": "item-replayed-recognition",
            "audio_start_ms": 10,
        }
    )
    socket.push(
        {
            "type": "input_audio_buffer.speech_stopped",
            "event_id": replayed_id,
            "item_id": "item-replayed-recognition",
            "audio_end_ms": 20,
        }
    )
    socket.push(
        {
            "type": "input_audio_buffer.committed",
            "event_id": replayed_id,
            "item_id": "item-replayed-recognition",
        }
    )
    socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "event_id": replayed_id,
            "content_index": 0,
            "item_id": "item-replayed-recognition",
            "transcript": "replayed identity must not become final",
        }
    )

    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    queued = []
    while not session.events.empty():
        queued.append(session.events.get_nowait())
    assert all(event.kind is not RecognitionEventKind.FINAL for event in queued)
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_recognition_event_identity_ledger_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.openai_streaming_speech."
        "MAX_NATIVE_SERVER_EVENT_IDS",
        2,
    )
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket((native_session_updated_event(server_vad_wire()),))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = RecognitionStreamRequest(
        recognition_ref(), RecognitionTurnDetection.server_vad_default()
    )
    await provider.open_recognition(request, timeout_seconds=1)
    socket.push(
        {
            "type": "rate_limits.updated",
            "event_id": "event-recognition-ledger-exact-max",
            "rate_limits": [],
        }
    )
    socket.push(
        {
            "type": "rate_limits.updated",
            "event_id": "event-recognition-ledger-over-limit",
            "rate_limits": [],
        }
    )

    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_recognition_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "RECOGNITION_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    "effective_model", ("gpt-realtime-translate", "gpt-realtime-whisper")
)
@pytest.mark.parametrize("operation", ("recognition", "synthesis"))
@pytest.mark.asyncio
async def test_native_realtime_effective_model_cannot_change_provider_purpose(
    effective_model: str,
    operation: str,
) -> None:
    facts: list[SpeechDegradationFact] = []
    updated = (
        native_session_updated_event()
        if operation == "recognition"
        else native_synthesis_session_updated_event()
    )
    session = updated["session"]
    assert isinstance(session, dict)
    session["model"] = effective_model
    socket = FakeSocket(
        (
            *((native_session_created_event(),) if operation == "synthesis" else ()),
            updated,
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config("gpt-realtime"),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    if operation == "recognition":
        with pytest.raises(OpenAIStreamingSpeechError) as mismatch:
            await provider.open_recognition(recognition_ref(), timeout_seconds=1)
        assert mismatch.value.reason == "SPEECH_PROVIDER_SESSION_MISMATCH"
    else:
        request = synthesis_request()
        provider.conformance.activate_response(request.ref.response)
        await provider.open_synthesis(request)
        await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
        with pytest.raises(OpenAIStreamingSpeechError) as retired:
            await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
        assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert socket.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_generic_alias_accepts_compatible_voice_model() -> None:
    updated = native_session_updated_event()
    session = updated["session"]
    assert isinstance(session, dict)
    session["model"] = "gpt-realtime-2.1"
    socket = FakeSocket((updated,))

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config("gpt-realtime"), socket_factory=socket_factory
    )
    ref = recognition_ref()
    await provider.open_recognition(ref, timeout_seconds=1)
    await provider.cancel_recognition(ref, reason="test-complete")
    assert socket.closed is True
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_releases_only_exact_transcribed_agent_text() -> (
    None
):
    socket = FakeSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(), socket_factory=socket_factory
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    started = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    assert started.kind is SynthesisEventKind.STARTED
    assert started.provider.provider_id == "openai-realtime-native-speech"

    synthesis_update = socket.sent[0]
    assert synthesis_update["type"] == "session.update"
    synthesis_session = synthesis_update["session"]
    assert isinstance(synthesis_session, dict)
    assert "model" not in synthesis_session
    response_create = socket.sent[1]
    assert response_create["type"] == "response.create"
    response = response_create["response"]
    assert isinstance(response, dict)
    assert response["conversation"] == "none"
    assert response["input"] == []
    assert response["output_modalities"] == ["audio"]
    assert response["metadata"] == _native_response_metadata(request)
    assert all(isinstance(value, str) for value in response["metadata"].values())
    assert request.spoken_text in str(response["instructions"])

    response_id = "provider-response-native"
    native_response_prelude(socket, request, response_id)
    pcm = struct.pack("<hhhh", 0, 1000, -1000, 0)
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            response_id,
            delta=base64.b64encode(pcm).decode("ascii"),
        )
    )
    with pytest.raises(asyncio.TimeoutError):
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)

    socket.push(native_audio_event("response.output_audio.done", response_id))
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.delta",
            response_id,
            delta=request.spoken_text,
        )
    )
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.done",
            response_id,
            transcript=request.spoken_text,
        )
    )
    for event in native_response_completion_events(request, response_id):
        socket.push(event)
    socket.push(
        {
            "type": "rate_limits.updated",
            "event_id": "event-terminal-rate-limits",
            "rate_limits": [],
        }
    )

    chunks = []
    while True:
        event = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
        if event.kind is SynthesisEventKind.CHUNK:
            assert socket.closed is True
            chunks.append(event)
        if event.kind is SynthesisEventKind.COMPLETED:
            break
    assert chunks
    assert sum(chunk.sample_count for chunk in chunks) == 8
    assert all(chunk.pcm_s16le for chunk in chunks)
    assert all(
        chunk.provider.provider_id == "openai-realtime-native-speech"
        for chunk in chunks
    )
    assert socket.closed is True
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_late_after_terminal_releases_zero_audio() -> (
    None
):
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(facts=facts)
    response_id = "provider-response-late-after-terminal"
    native_response_prelude(socket, request, response_id)
    encoded = base64.b64encode(struct.pack("<hhhh", 1, -1, 2, -2)).decode("ascii")
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            response_id,
            event_id="event-audio-before-terminal",
            delta=encoded,
        )
    )
    socket.push(native_audio_event("response.output_audio.done", response_id))
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.done",
            response_id,
            transcript=request.spoken_text,
        )
    )
    for event in native_response_completion_events(request, response_id):
        socket.push(event)
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            response_id,
            event_id="event-audio-after-terminal",
            delta=encoded,
        )
    )

    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_late_during_close_releases_zero_audio() -> (
    None
):
    facts: list[SpeechDegradationFact] = []
    socket = CoordinatedCloseSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )
    provider, _, request = await open_native_synthesis_for_test(
        facts=facts,
        socket=socket,
    )
    response_id = "provider-response-late-during-close"
    native_response_prelude(socket, request, response_id)
    encoded = base64.b64encode(struct.pack("<hhhh", 1, -1, 2, -2)).decode("ascii")
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            response_id,
            event_id="event-audio-before-close",
            delta=encoded,
        )
    )
    socket.push(native_audio_event("response.output_audio.done", response_id))
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.done",
            response_id,
            transcript=request.spoken_text,
        )
    )
    for event in native_response_completion_events(request, response_id):
        socket.push(event)

    await asyncio.wait_for(socket.close_started.wait(), timeout=1)
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            response_id,
            event_id="event-unique-late-during-close",
            delta=encoded,
        )
    )
    socket.release_close.set()

    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    for _ in range(100):
        await asyncio.sleep(0)
        if facts:
            break
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    terminal_eof = socket.incoming.get_nowait()
    assert isinstance(terminal_eof, _RealtimeSocketTerminalEof)
    assert socket.incoming.empty()
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_close_drain_allows_rate_limits() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = CoordinatedCloseSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )
    provider, _, request = await open_native_synthesis_for_test(
        facts=facts,
        socket=socket,
    )
    response_id = "provider-response-rate-limits-during-close"
    native_response_prelude(socket, request, response_id)
    encoded = base64.b64encode(struct.pack("<hhhh", 1, -1, 2, -2)).decode("ascii")
    socket.push(
        native_audio_event("response.output_audio.delta", response_id, delta=encoded)
    )
    socket.push(native_audio_event("response.output_audio.done", response_id))
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.done",
            response_id,
            transcript=request.spoken_text,
        )
    )
    for event in native_response_completion_events(request, response_id):
        socket.push(event)

    await asyncio.wait_for(socket.close_started.wait(), timeout=1)
    socket.push(
        {
            "type": "rate_limits.updated",
            "event_id": "event-rate-limits-during-close",
            "rate_limits": [],
        }
    )
    socket.release_close.set()

    chunks = []
    while True:
        event = await provider.next_synthesis_event(request.ref, timeout_seconds=1)
        if event.kind is SynthesisEventKind.CHUNK:
            assert socket.closed is True
            chunks.append(event)
        if event.kind is SynthesisEventKind.COMPLETED:
            break
    assert chunks
    assert not facts
    assert socket.incoming.empty()
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    "mutation",
    (
        "conversation",
        "modalities",
        "voice",
        "status",
        "output",
        "audio_format",
        "missing_conversation",
        "missing_status_details",
        "missing_usage",
    ),
)
@pytest.mark.asyncio
async def test_native_realtime_synthesis_rejects_changed_initial_response(
    mutation: str,
) -> None:
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(facts=facts)
    response_id = "provider-response-invalid-created"
    created = native_response_created_event(request, response_id)
    response = created["response"]
    assert isinstance(response, dict)
    if mutation == "conversation":
        response["conversation_id"] = "conv-history-forbidden"
    elif mutation == "modalities":
        response["output_modalities"] = ["text"]
    elif mutation == "voice":
        audio = response["audio"]
        assert isinstance(audio, dict)
        output = audio["output"]
        assert isinstance(output, dict)
        output["voice"] = "cedar"
    elif mutation == "status":
        response["status"] = "completed"
    elif mutation == "output":
        response["output"] = [{"type": "message", "id": "unexpected-item"}]
    elif mutation == "audio_format":
        audio = response["audio"]
        assert isinstance(audio, dict)
        output = audio["output"]
        assert isinstance(output, dict)
        output["format"] = {"type": "audio/pcmu"}
    elif mutation == "missing_conversation":
        del response["conversation_id"]
    elif mutation == "missing_status_details":
        del response["status_details"]
    else:
        del response["usage"]

    native_response_prelude(
        socket,
        request,
        response_id,
        created_event=created,
    )
    encoded = base64.b64encode(struct.pack("<hh", 1, -1)).decode("ascii")
    socket.push(
        native_audio_event("response.output_audio.delta", response_id, delta=encoded)
    )
    socket.push(native_audio_event("response.output_audio.done", response_id))
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.done",
            response_id,
            transcript=request.spoken_text,
        )
    )
    for event in native_response_completion_events(request, response_id):
        socket.push(event)

    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    "mutation",
    (
        "object",
        "status_details",
        "usage_type",
        "usage_total",
        "missing_usage",
    ),
)
@pytest.mark.asyncio
async def test_native_realtime_synthesis_rejects_contradictory_terminal_response(
    mutation: str,
) -> None:
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(facts=facts)
    response_id = "provider-response-invalid-terminal"
    native_response_prelude(socket, request, response_id)
    encoded = base64.b64encode(struct.pack("<hhhh", 1, -1, 2, -2)).decode("ascii")
    socket.push(
        native_audio_event("response.output_audio.delta", response_id, delta=encoded)
    )
    socket.push(native_audio_event("response.output_audio.done", response_id))
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.done",
            response_id,
            transcript=request.spoken_text,
        )
    )
    completion = list(native_response_completion_events(request, response_id))
    terminal = completion[-1]["response"]
    assert isinstance(terminal, dict)
    if mutation == "object":
        terminal["object"] = "not.realtime.response"
    elif mutation == "status_details":
        terminal["status_details"] = {
            "type": "failed",
            "error": {"type": "server_error"},
        }
    elif mutation == "usage_type":
        terminal["usage"] = "invalid-usage"
    elif mutation == "usage_total":
        usage = terminal["usage"]
        assert isinstance(usage, dict)
        usage["total_tokens"] = 4
    else:
        del terminal["usage"]
    for event in completion:
        socket.push(event)

    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert len(facts) == 1
    assert facts[0].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_replay_releases_zero_audio() -> None:
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(facts=facts)
    response_id = "provider-response-replay"
    native_response_prelude(socket, request, response_id)
    delta = native_audio_event(
        "response.output_audio.delta",
        response_id,
        event_id="event-replayed-audio",
        delta=base64.b64encode(struct.pack("<hhhh", 1, -1, 2, -2)).decode("ascii"),
    )
    socket.push(delta)
    socket.push(delta)
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    "invalid_edge", ("transcript_done", "audio_after_done", "terminal")
)
@pytest.mark.asyncio
async def test_native_realtime_synthesis_rejects_terminal_reordering(
    invalid_edge: str,
) -> None:
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(facts=facts)
    response_id = "provider-response-reordered"
    native_response_prelude(socket, request, response_id)
    if invalid_edge == "transcript_done":
        socket.push(
            native_audio_event(
                "response.output_audio_transcript.done",
                response_id,
                transcript=request.spoken_text,
            )
        )
    elif invalid_edge == "audio_after_done":
        encoded = base64.b64encode(struct.pack("<hh", 1, -1)).decode("ascii")
        socket.push(
            native_audio_event(
                "response.output_audio.delta",
                response_id,
                event_id="event-audio-before-done",
                delta=encoded,
            )
        )
        socket.push(native_audio_event("response.output_audio.done", response_id))
        socket.push(
            native_audio_event(
                "response.output_audio.delta",
                response_id,
                event_id="event-audio-after-done",
                delta=encoded,
            )
        )
    else:
        socket.push(native_response_completion_events(request, response_id)[-1])
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_nonprogress_flood_cannot_renew_deadline() -> (
    None
):
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(
        facts=facts, event_timeout_seconds=0.05
    )

    async def flood_rate_limits() -> None:
        for index in range(30):
            await asyncio.sleep(0.01)
            socket.push(
                {
                    "type": "rate_limits.updated",
                    "event_id": f"event-rate-limit-{index}",
                    "rate_limits": [],
                }
            )

    flood = asyncio.create_task(flood_rate_limits())
    await asyncio.wait_for(socket.closed_event.wait(), timeout=0.5)
    flood.cancel()
    with suppress(asyncio.CancelledError):
        await flood
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_TIMEOUT
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_requires_server_event_id() -> None:
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(facts=facts)
    socket.push(
        {
            "type": "response.created",
            "response": {
                "id": "provider-response-missing-event-id",
                "metadata": _native_response_metadata(request),
            },
        }
    )
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_event_identity_ledger_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.openai_streaming_speech."
        "MAX_NATIVE_SERVER_EVENT_IDS",
        4,
    )
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(facts=facts)
    native_response_prelude(socket, request, "provider-response-event-limit")
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize(
    ("delta_size", "accepted"),
    (
        (MAX_PROVIDER_AUDIO_DELTA_BYTES, True),
        (MAX_PROVIDER_AUDIO_DELTA_BYTES + 2, False),
    ),
)
@pytest.mark.asyncio
async def test_native_realtime_synthesis_enforces_exact_delta_boundary(
    delta_size: int,
    accepted: bool,
) -> None:
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(facts=facts)
    response_id = "provider-response-delta-boundary"
    native_response_prelude(socket, request, response_id)
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            response_id,
            delta=base64.b64encode(bytes(delta_size)).decode("ascii"),
        )
    )
    if accepted:
        await wait_for_native_buffer_size(provider, request, delta_size)
        await provider.cancel_synthesis(request.ref)
        assert (
            facts[-1].reason is SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED
        )
    else:
        await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
        assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.parametrize("overflow", (False, True))
@pytest.mark.asyncio
async def test_native_realtime_synthesis_enforces_exact_total_audio_boundary(
    overflow: bool,
) -> None:
    facts: list[SpeechDegradationFact] = []
    provider, socket, request = await open_native_synthesis_for_test(
        facts=facts, event_timeout_seconds=5
    )
    response_id = "provider-response-total-boundary"
    native_response_prelude(socket, request, response_id)
    remaining = MAX_STREAM_AUDIO_BYTES
    index = 0
    while remaining:
        size = min(remaining, MAX_PROVIDER_AUDIO_DELTA_BYTES)
        socket.push(
            native_audio_event(
                "response.output_audio.delta",
                response_id,
                event_id=f"event-total-audio-{index}",
                delta=base64.b64encode(bytes(size)).decode("ascii"),
            )
        )
        remaining -= size
        index += 1
    await wait_for_native_buffer_size(provider, request, MAX_STREAM_AUDIO_BYTES)
    if overflow:
        socket.push(
            native_audio_event(
                "response.output_audio.delta",
                response_id,
                event_id="event-total-audio-overflow",
                delta=base64.b64encode(b"\x00\x00").decode("ascii"),
            )
        )
        await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
        assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    else:
        await provider.cancel_synthesis(request.ref)
        assert (
            facts[-1].reason is SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED
        )
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_rejects_changed_text_before_audio_release() -> (
    None
):
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    response_id = "provider-response-mismatch"
    native_response_prelude(socket, request, response_id)
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            response_id,
            delta=base64.b64encode(struct.pack("<hh", 1, -1)).decode("ascii"),
        )
    )
    socket.push(native_audio_event("response.output_audio.done", response_id))
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.done",
            response_id,
            transcript="not the agent text",
        )
    )
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_rejects_terminal_non_audio_output() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    response_id = "provider-response-tool-output"
    native_response_prelude(socket, request, response_id)
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            response_id,
            delta=base64.b64encode(struct.pack("<hh", 1, -1)).decode("ascii"),
        )
    )
    socket.push(native_audio_event("response.output_audio.done", response_id))
    socket.push(
        native_audio_event(
            "response.output_audio_transcript.done",
            response_id,
            transcript=request.spoken_text,
        )
    )
    for event in native_response_completion_events(
        request,
        response_id,
        terminal_output=[
            {
                "id": "native-tool-item",
                "type": "function_call",
                "status": "completed",
                "name": "forbidden_tool",
            }
        ],
    ):
        socket.push(event)
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_rejects_cross_response_audio() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    native_response_prelude(socket, request, "expected-response")
    socket.push(
        native_audio_event(
            "response.output_audio.delta",
            "stale-response",
            delta=base64.b64encode(struct.pack("<hh", 1, -1)).decode("ascii"),
        )
    )
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_rejects_invalid_audio_before_release() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    response_id = "provider-response-invalid-audio"
    native_response_prelude(socket, request, response_id)
    socket.push(
        native_audio_event(
            "response.output_audio.delta", response_id, delta="not-base64%"
        )
    )
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_session_downgrade_fails_closed() -> None:
    facts: list[SpeechDegradationFact] = []
    updated = native_synthesis_session_updated_event()
    session = updated["session"]
    assert isinstance(session, dict)
    session["tool_choice"] = "auto"
    socket = FakeSocket(
        (
            native_session_created_event(),
            updated,
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_PROTOCOL
    with pytest.raises(OpenAIStreamingSpeechError) as retired:
        await provider.next_synthesis_event(request.ref, timeout_seconds=0.01)
    assert retired.value.reason == "SYNTHESIS_STREAM_NOT_FOUND"
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_event_timeout_is_bounded_and_visible() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = synthesis_request(event_timeout_seconds=0.05)
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    await asyncio.wait_for(socket.closed_event.wait(), timeout=1)
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_TIMEOUT
    assert facts[-1].to_tier is SpeechRouteTier.TEXT
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_native_realtime_synthesis_cancel_binds_exact_provider_response() -> None:
    facts: list[SpeechDegradationFact] = []
    socket = FakeSocket(
        (
            native_session_created_event(),
            native_synthesis_session_updated_event(),
        )
    )

    async def socket_factory(*_args) -> FakeSocket:
        return socket

    provider = OpenAIStreamingSpeechProvider(
        native_config(),
        socket_factory=socket_factory,
        degradation_sink=facts.append,
    )
    request = synthesis_request()
    provider.conformance.activate_response(request.ref.response)
    await provider.open_synthesis(request)
    await provider.next_synthesis_event(request.ref, timeout_seconds=1)
    response_id = "provider-response-cancel"
    socket.push(native_response_created_event(request, response_id))
    for _ in range(100):
        await asyncio.sleep(0)
        session = provider._synthesis.get(
            (request.ref.stream_id, request.ref.stream_generation)
        )
        if session is not None and session.provider_response_id == response_id:
            break
    await provider.cancel_synthesis(request.ref)
    assert socket.sent[-1] == {
        "type": "response.cancel",
        "response_id": response_id,
    }
    assert socket.closed is True
    assert facts[-1].reason is SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED
    assert_zero_business_effects(provider)
    await provider.close()
