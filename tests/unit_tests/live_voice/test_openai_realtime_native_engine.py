# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import asyncio
import base64
import json
from collections.abc import Mapping
from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NativeInteractionBinding,
    NativePresentationCursor,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    MAX_NATIVE_AUDIO_DELTA_BYTES,
    NativeEngineEvent,
    NativeInputAudioFrame,
    NativeProviderState,
    OpenAIRealtimeNativeInteractionEngine,
    OpenAIRealtimeNativeInteractionError,
)
from jiuwenswarm.server.live_voice.openai_realtime_session import (
    OpenAIRealtimeSessionConfig,
)


_SCOPE = ScopeRef(
    "subject-native", "project-native", "session-native", Assurance.AUTHENTICATED
)


class ScriptedSocket:
    def __init__(
        self,
        initial: tuple[dict[str, object] | str | bytes | BaseException, ...] = (),
    ) -> None:
        self.incoming: asyncio.Queue[str | bytes | BaseException] = asyncio.Queue()
        self.sent: list[dict[str, object]] = []
        self.send_calls = 0
        self.fail_send_at: int | None = None
        self.close_calls = 0
        for value in initial:
            self.push(value)

    def push(self, value: dict[str, object] | str | bytes | BaseException) -> None:
        if isinstance(value, dict):
            self.incoming.put_nowait(json.dumps(value))
        else:
            self.incoming.put_nowait(value)

    async def send(self, message: str) -> None:
        self.send_calls += 1
        if self.send_calls == self.fail_send_at:
            raise OSError("injected Provider send failure")
        self.sent.append(json.loads(message))

    async def recv(self) -> str | bytes:
        value = await self.incoming.get()
        if isinstance(value, BaseException):
            raise value
        return value

    async def close(self) -> None:
        self.close_calls += 1


class CapturingFactory:
    def __init__(self, socket: ScriptedSocket) -> None:
        self.socket = socket
        self.calls: list[tuple[str, dict[str, str], float]] = []

    async def __call__(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> ScriptedSocket:
        self.calls.append((url, dict(headers), timeout))
        return self.socket


def provider_event(
    event_type: str, event_id: str, **payload: object
) -> dict[str, object]:
    return {"type": event_type, "event_id": event_id, **payload}


def negotiation() -> tuple[dict[str, object], dict[str, object]]:
    return (
        provider_event(
            "session.created",
            "event-session-created",
            session={"id": "provider-session-1", "type": "realtime"},
        ),
        provider_event(
            "session.updated",
            "event-session-updated",
            session={"id": "provider-session-1", "type": "realtime"},
        ),
    )


def speech_started(
    event_id: str, item_id: str, audio_start_ms: int
) -> dict[str, object]:
    return provider_event(
        "input_audio_buffer.speech_started",
        event_id,
        audio_start_ms=audio_start_ms,
        item_id=item_id,
    )


def speech_stopped(event_id: str, item_id: str, audio_end_ms: int) -> dict[str, object]:
    return provider_event(
        "input_audio_buffer.speech_stopped",
        event_id,
        audio_end_ms=audio_end_ms,
        item_id=item_id,
    )


def input_committed(event_id: str, item_id: str) -> dict[str, object]:
    return provider_event(
        "input_audio_buffer.committed",
        event_id,
        previous_item_id=None,
        item_id=item_id,
    )


def response_created(event_id: str, response_id: str) -> dict[str, object]:
    return provider_event(
        "response.created",
        event_id,
        response={
            "object": "realtime.response",
            "id": response_id,
            "status": "in_progress",
            "status_details": None,
            "output": [],
            "conversation_id": "provider-conversation-1",
            "output_modalities": ["audio"],
            "max_output_tokens": "inf",
            "audio": {
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "voice": "marin",
                }
            },
            "usage": None,
            "metadata": None,
        },
    )


def output_audio_delta(
    event_id: str,
    response_id: str,
    item_id: str,
    sequence: int,
    *,
    pcm16: bytes = b"\x01\x00" * 480,
) -> dict[str, object]:
    return provider_event(
        "response.output_audio.delta",
        event_id,
        response_id=response_id,
        item_id=item_id,
        output_index=sequence,
        content_index=0,
        delta=base64.b64encode(pcm16).decode("ascii"),
    )


def output_transcript_done(
    event_id: str,
    response_id: str,
    item_id: str,
    transcript: str,
) -> dict[str, object]:
    return provider_event(
        "response.output_audio_transcript.done",
        event_id,
        response_id=response_id,
        item_id=item_id,
        output_index=0,
        content_index=0,
        transcript=transcript,
    )


def response_done(
    event_id: str, response_id: str, *, status: str = "completed"
) -> dict[str, object]:
    return provider_event(
        "response.done",
        event_id,
        response={
            "object": "realtime.response",
            "id": response_id,
            "status": status,
            "status_details": None,
            "output": [],
            "conversation_id": "provider-conversation-1",
            "output_modalities": ["audio"],
            "max_output_tokens": "inf",
            "audio": {
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "voice": "marin",
                }
            },
            "usage": None,
            "metadata": None,
        },
    )


def function_done(
    event_id: str,
    response_id: str,
    *,
    item_id: str = "function-item-1",
    call_id: str = "call-1",
    name: str = "jiuwen_delegate",
    arguments: str = '{"request_text":"create task: inspect repository"}',
) -> dict[str, object]:
    return provider_event(
        "response.function_call_arguments.done",
        event_id,
        response_id=response_id,
        item_id=item_id,
        output_index=0,
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def binding() -> NativeInteractionBinding:
    return NativeInteractionBinding(
        scope=_SCOPE,
        interaction_id="native-interaction-1",
        activation_id="native-activation-1",
        activation_generation=1,
        correlation_id="native-correlation-1",
    )


def response_ref(generation: int, response_id: str | None = None) -> ResponseRef:
    return ResponseRef(
        interaction_id=binding().interaction_id,
        response_id=response_id or f"runtime-response-{generation}",
        response_generation=generation,
    )


def config(**changes: object) -> OpenAIRealtimeSessionConfig:
    values: dict[str, object] = {
        "api_key": "private-native-provider-key",
        "model": "gpt-realtime-2.1-mini",
        "operation_timeout_seconds": 0.1,
        "close_timeout_seconds": 0.05,
    }
    values.update(changes)
    return OpenAIRealtimeSessionConfig(**values)  # type: ignore[arg-type]


def active_engine(
    *events: dict[str, object] | str | bytes | BaseException,
    event_queue_capacity: int = 16,
    pending_audio_capacity: int = 8,
    session_config: OpenAIRealtimeSessionConfig | None = None,
) -> tuple[OpenAIRealtimeNativeInteractionEngine, ScriptedSocket, CapturingFactory]:
    socket = ScriptedSocket((*negotiation(), *events))
    factory = CapturingFactory(socket)
    engine = OpenAIRealtimeNativeInteractionEngine(
        session_config or config(),
        binding=binding(),
        socket_factory=factory,
        event_queue_capacity=event_queue_capacity,
        pending_audio_capacity=pending_audio_capacity,
    )
    return engine, socket, factory


def action_payload(event: NativeEngineEvent) -> dict[str, str]:
    assert event.action is not None
    return dict(event.action.payload)


async def accept_basic_turn(
    engine: OpenAIRealtimeNativeInteractionEngine,
) -> tuple[NativeEngineEvent, NativeEngineEvent, NativeEngineEvent]:
    listen = await engine.next_event()
    silence = await engine.next_event()
    commit = await engine.next_event()
    assert listen.action is not None and listen.action.operation == "LISTEN"
    assert silence.action is not None and silence.action.operation == "SILENCE"
    assert commit.action is not None and commit.action.operation == "TURN_COMMIT"
    assert commit.turn_commit is not None
    return listen, silence, commit


@pytest.mark.asyncio
async def test_native_session_direct_audio_does_not_require_transcript_or_bridge() -> (
    None
):
    engine, socket, factory = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 640),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x01\x00",
        ),
        response_done("event-8", "provider-response-1"),
    )
    await engine.start()
    listen, silence, commit = await accept_basic_turn(engine)
    speak = await engine.next_event()
    assert speak.action is not None and speak.action.operation == "SPEAK"
    assert action_payload(speak)["provider_response_id"] == "provider-response-1"

    runtime_ref = response_ref(1)
    assert await engine.admit_response("provider-response-1", runtime_ref) is True
    assert await engine.next_event() == NativeEngineEvent()
    audio = await engine.next_event()
    done = await engine.next_event()

    assert [
        listen.action.operation,
        silence.action.operation,
        commit.action.operation,
        speak.action.operation,
    ] == ["LISTEN", "SILENCE", "TURN_COMMIT", "SPEAK"]
    assert action_payload(listen) == {
        "provider_item_id": "user-item-1",
        "provider_start_ms": "0",
    }
    assert commit.turn_commit is not None
    assert commit.turn_commit.audit_transcript is None
    assert commit.turn_commit.committed_audio_ms == 640
    assert audio.audio is not None
    assert audio.audio.pcm16 == b"\x01\x00" + b"\x00\x00" * 479
    assert audio.audio.response == runtime_ref
    assert done.provider_done is not None and done.provider_done.completed is True
    assert done.provider_done.transcript is None
    assert len(factory.calls) == 1
    assert socket.sent[0]["type"] == "session.update"
    assert socket.sent[0]["session"]["audio"]["input"]["turn_detection"] == {
        "type": "semantic_vad",
        "eagerness": "auto",
        "create_response": True,
        "interrupt_response": False,
    }
    assert socket.sent[0]["session"]["tools"] == [
        {
            "type": "function",
            "name": "jiuwen_delegate",
            "description": "Delegate authorized Jiuwen Agent or Task work.",
            "parameters": {
                "type": "object",
                "properties": {"request_text": {"type": "string"}},
                "required": ["request_text"],
                "additionalProperties": False,
            },
        }
    ]
    await engine.close()


@pytest.mark.asyncio
async def test_native_audio_delta_crosses_provider_events_into_one_exact_20ms_frame() -> (
    None
):
    first = b"\x01\x00" * 200
    second = b"\x02\x00" * 280
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=first,
        ),
        output_audio_delta(
            "event-8",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=second,
        ),
        response_done("event-9", "provider-response-1"),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))

    assert await engine.next_event() == NativeEngineEvent()
    audio = await engine.next_event()
    done = await engine.next_event()

    assert audio.audio is not None
    assert audio.audio.sequence == 0
    assert audio.audio.pcm16 == first + second
    assert done.provider_done is not None and done.provider_done.completed is True
    await engine.close()


@pytest.mark.asyncio
async def test_cross_event_delta_keeps_exact_causation_for_each_emitted_frame() -> None:
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x01\x00" * 200,
        ),
        output_audio_delta(
            "event-8",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x02\x00" * 760,
        ),
        response_done("event-9", "provider-response-1"),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))

    assert await engine.next_event() == NativeEngineEvent()
    first = await engine.next_event()
    second = await engine.next_event()

    assert first.audio is not None and second.audio is not None
    assert (first.audio.provider_event_id, second.audio.provider_event_id) == (
        "event-7",
        "event-8",
    )
    assert first.audio.pcm16 == b"\x01\x00" * 200 + b"\x02\x00" * 280
    assert second.audio.pcm16 == b"\x02\x00" * 480
    await engine.close()


@pytest.mark.asyncio
async def test_one_provider_delta_emits_multiple_exact_frames_with_one_causation_id() -> (
    None
):
    pcm16 = b"\x01\x00" * 960
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=pcm16,
        ),
        response_done("event-8", "provider-response-1"),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))

    first = await engine.next_event()
    second = await engine.next_event()
    terminal = await engine.next_event()

    assert first.audio is not None and second.audio is not None
    assert (first.audio.provider_event_id, second.audio.provider_event_id) == (
        "event-7",
        "event-7",
    )
    assert (first.audio.sequence, second.audio.sequence) == (0, 1)
    assert first.audio.pcm16 == second.audio.pcm16 == b"\x01\x00" * 480
    assert terminal.provider_done is not None
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["cancelled", "failed"])
async def test_non_presentable_terminal_status_discards_partial_audio_tail(
    status: str,
) -> None:
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x01\x00" * 200,
        ),
        response_done("event-8", "provider-response-1", status=status),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))

    assert await engine.next_event() == NativeEngineEvent()
    terminal = await engine.next_event()

    assert terminal.audio is None
    assert terminal.provider_done is not None
    assert terminal.provider_done.completed is False
    assert engine.snapshot().released_audio_count == 0
    await engine.close()


@pytest.mark.asyncio
async def test_unadmitted_partial_audio_consumes_bounded_pending_capacity() -> None:
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x01\x00",
        ),
        output_audio_delta(
            "event-8",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x02\x00" * 480,
        ),
        pending_audio_capacity=1,
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()

    assert await engine.next_event() == NativeEngineEvent()
    before = engine.snapshot()
    assert before.pending_audio_count == 1
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.next_event()

    assert raised.value.reason == "NATIVE_PENDING_AUDIO_FULL"
    after = engine.snapshot()
    assert after.pending_audio_count == 1
    assert after.released_audio_count == 0
    await engine.close()


@pytest.mark.asyncio
async def test_two_turns_reuse_one_session_and_contiguous_audio_input() -> None:
    events = (
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        response_done("event-7", "provider-response-1"),
        speech_started("event-8", "user-item-2", 20),
        speech_stopped("event-9", "user-item-2", 40),
        input_committed("event-10", "user-item-2"),
        response_created("event-11", "provider-response-2"),
        response_done("event-12", "provider-response-2"),
    )
    engine, socket, factory = active_engine(*events)
    await engine.start()
    frame0 = NativeInputAudioFrame(seq=0, sample_cursor=0, pcm16=b"\x00\x00" * 480)
    frame1 = NativeInputAudioFrame(seq=1, sample_cursor=480, pcm16=b"\x01\x00" * 480)
    await engine.offer_audio(frame0)
    await engine.offer_audio(frame1)

    await accept_basic_turn(engine)
    speak1 = await engine.next_event()
    assert speak1.action is not None
    await engine.admit_response("provider-response-1", response_ref(1))
    assert (await engine.next_event()).provider_done is not None
    _, _, commit2 = await accept_basic_turn(engine)
    speak2 = await engine.next_event()
    assert speak2.action is not None
    await engine.admit_response("provider-response-2", response_ref(2))
    assert (await engine.next_event()).provider_done is not None

    assert len(factory.calls) == 1
    assert commit2.turn_commit is not None
    assert [
        event["type"]
        for event in socket.sent
        if event["type"] == "input_audio_buffer.append"
    ] == ["input_audio_buffer.append", "input_audio_buffer.append"]
    assert engine.snapshot().next_input_sequence == 2
    assert engine.snapshot().next_input_sample_cursor == 960
    assert engine.snapshot().turn_count == 2
    await engine.close()


@pytest.mark.asyncio
async def test_unsolicited_second_direct_response_in_one_turn_has_zero_new_effect() -> (
    None
):
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        response_done("event-7", "provider-response-1"),
        response_created("event-8", "provider-response-2"),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))
    assert (await engine.next_event()).provider_done is not None
    before = engine.snapshot()

    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.next_event()

    assert raised.value.reason == "NATIVE_DIRECT_RESPONSE_ALREADY_CREATED"
    after = engine.snapshot()
    assert after.turn_count == before.turn_count
    assert after.response_count == before.response_count
    assert after.retained_action_count == before.retained_action_count
    assert after.released_audio_count == before.released_audio_count
    assert after.delegate_count == before.delegate_count
    await engine.close()


@pytest.mark.asyncio
async def test_audio_is_buffered_until_exact_runtime_admission() -> None:
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta("event-7", "provider-response-1", "assistant-item-1", 0),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    buffered = await engine.next_event()
    assert buffered == NativeEngineEvent()
    assert engine.snapshot().pending_audio_count == 1
    assert engine.snapshot().released_audio_count == 0

    ref = response_ref(1)
    assert await engine.admit_response("provider-response-1", ref) is True
    released = await engine.next_event()
    assert released.audio is not None and released.audio.response == ref
    assert engine.snapshot().pending_audio_count == 0
    assert engine.snapshot().released_audio_count == 1
    await engine.close()


@pytest.mark.asyncio
async def test_complete_transcript_keeps_exact_provider_provenance() -> None:
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta("event-7", "provider-response-1", "assistant-item-1", 0),
        output_transcript_done(
            "event-8",
            "provider-response-1",
            "assistant-item-1",
            "Canonical answer.",
        ),
        response_done("event-9", "provider-response-1"),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))
    assert (await engine.next_event()).audio is not None
    assert await engine.next_event() == NativeEngineEvent()
    done = await engine.next_event()

    assert done.provider_done is not None
    assert done.provider_done.transcript == "Canonical answer."
    assert done.provider_done.transcript_event_id == "event-8"
    await engine.close()


@pytest.mark.asyncio
async def test_explicit_harmless_ga_event_has_zero_native_effect() -> None:
    engine, _, _ = active_engine(
        provider_event(
            "rate_limits.updated",
            "event-3",
            rate_limits=[{"name": "requests", "remaining": 1}],
        )
    )
    await engine.start()
    before = engine.snapshot()

    assert await engine.next_event() == NativeEngineEvent()

    after = engine.snapshot()
    assert after.emitted_event_count == before.emitted_event_count == 0
    assert after.retained_action_count == before.retained_action_count == 0
    await engine.close()


@pytest.mark.asyncio
async def test_speech_restart_before_commit_proposes_revise_then_listen() -> None:
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        speech_started("event-5", "user-item-2", 20),
    )
    await engine.start()
    assert (await engine.next_event()).action.operation == "LISTEN"  # type: ignore[union-attr]
    assert (await engine.next_event()).action.operation == "SILENCE"  # type: ignore[union-attr]
    revise = await engine.next_event()
    listen = await engine.next_event()
    assert revise.action is not None and revise.action.operation == "REVISE"
    assert listen.action is not None and listen.action.operation == "LISTEN"
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_event",
    [
        provider_event("unknown.preview.event", "event-3", value=True),
        {
            **speech_started("event-3", "user-item-1", 0),
            "unexpected": True,
        },
        {
            key: value
            for key, value in speech_started("event-3", "user-item-1", 0).items()
            if key != "item_id"
        },
    ],
    ids=("unknown", "extra", "missing"),
)
async def test_unknown_or_non_closed_provider_event_has_zero_output(
    bad_event: dict[str, object],
) -> None:
    engine, _, _ = active_engine(bad_event)
    await engine.start()
    before = engine.snapshot()

    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.next_event()

    assert raised.value.reason in {
        "NATIVE_PROVIDER_EVENT_UNSUPPORTED",
        "NATIVE_PROVIDER_EVENT_NOT_CLOSED",
    }
    after = engine.snapshot()
    assert after.emitted_event_count == before.emitted_event_count == 0
    assert after.retained_action_count == before.retained_action_count == 0
    assert after.released_audio_count == before.released_audio_count == 0
    assert after.delegate_count == before.delegate_count == 0
    await engine.close()


@pytest.mark.asyncio
async def test_provider_error_is_sanitized_and_has_zero_native_effect() -> None:
    engine, _, _ = active_engine(
        provider_event(
            "error",
            "event-3",
            error={
                "type": "invalid_request_error",
                "code": "invalid_value",
                "message": "private-provider-detail",
                "param": "session.audio",
                "event_id": None,
            },
        )
    )
    await engine.start()
    before = engine.snapshot()

    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.next_event()

    assert raised.value.reason == "NATIVE_PROVIDER_ERROR"
    assert "private-provider-detail" not in str(raised.value)
    after = engine.snapshot()
    assert after.emitted_event_count == before.emitted_event_count == 0
    assert after.retained_action_count == before.retained_action_count == 0
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("delta", "reason"),
    [
        ("not-base64!", "NATIVE_PROVIDER_AUDIO_INVALID"),
        (
            base64.b64encode(b"\x00" * (MAX_NATIVE_AUDIO_DELTA_BYTES + 2)).decode(),
            "NATIVE_PROVIDER_AUDIO_TOO_LARGE",
        ),
        (base64.b64encode(b"\x00").decode(), "NATIVE_PROVIDER_AUDIO_INVALID"),
    ],
    ids=("base64", "oversized", "odd-pcm"),
)
async def test_invalid_audio_delta_has_zero_new_audio_effect(
    delta: str, reason: str
) -> None:
    events = [
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta("event-7", "provider-response-1", "assistant-item-1", 0),
    ]
    events[-1]["delta"] = delta
    engine, _, _ = active_engine(*events)
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))
    before = engine.snapshot()

    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.next_event()

    assert raised.value.reason == reason
    after = engine.snapshot()
    assert after.released_audio_count == before.released_audio_count == 0
    assert after.pending_audio_count == before.pending_audio_count == 0
    await engine.close()


@pytest.mark.asyncio
async def test_response_before_commit_and_item_mismatch_fail_closed() -> None:
    premature, _, _ = active_engine(response_created("event-3", "provider-response-1"))
    await premature.start()
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as premature_raised:
        await premature.next_event()
    assert premature_raised.value.reason == "NATIVE_RESPONSE_BEFORE_TURN_COMMIT"
    assert premature.snapshot().retained_action_count == 0
    await premature.close()

    mismatch, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "different-item", 20),
    )
    await mismatch.start()
    await mismatch.next_event()
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as mismatch_raised:
        await mismatch.next_event()
    assert mismatch_raised.value.reason == "NATIVE_PROVIDER_ITEM_MISMATCH"
    assert mismatch.snapshot().retained_action_count == 1
    await mismatch.close()


@pytest.mark.asyncio
async def test_changed_provider_replay_fails_before_new_engine_effect() -> None:
    first = speech_started("event-3", "user-item-1", 0)
    changed = speech_started("event-3", "user-item-2", 0)
    engine, _, _ = active_engine(first, changed)
    await engine.start()
    assert (await engine.next_event()).action is not None
    before = engine.snapshot()

    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.next_event()

    assert raised.value.reason == "REALTIME_PROVIDER_EVENT_CONFLICT"
    after = engine.snapshot()
    assert after.emitted_event_count == before.emitted_event_count
    assert after.retained_action_count == before.retained_action_count
    await engine.close()


@pytest.mark.asyncio
async def test_response_admission_is_exact_and_changed_replay_has_zero_release() -> (
    None
):
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    ref = response_ref(1)
    assert await engine.admit_response("provider-response-1", ref) is True
    assert await engine.admit_response("provider-response-1", ref) is False
    before = engine.snapshot()

    with pytest.raises(OpenAIRealtimeNativeInteractionError) as changed:
        await engine.admit_response("provider-response-1", response_ref(2))
    assert changed.value.reason == "NATIVE_RESPONSE_ADMISSION_CONFLICT"
    assert engine.snapshot() == before

    wrong_interaction = replace(ref, interaction_id="other-interaction")
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as wrong:
        await engine.admit_response("provider-response-1", wrong_interaction)
    assert wrong.value.reason == "NATIVE_RESPONSE_SCOPE_MISMATCH"
    assert engine.snapshot() == before
    await engine.close()


@pytest.mark.asyncio
async def test_delegate_is_proposal_only_and_result_round_trip_is_exact() -> None:
    engine, socket, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        function_done("event-7", "provider-response-1"),
        response_done("event-8", "provider-response-1"),
        response_created("event-9", "provider-response-2"),
        output_audio_delta("event-10", "provider-response-2", "assistant-item-2", 0),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    ref = response_ref(1)
    await engine.admit_response("provider-response-1", ref)
    delegate = await engine.next_event()
    assert delegate.action is not None and delegate.action.operation == "DELEGATE"
    assert delegate.delegate is not None
    assert delegate.delegate.request_text == "create task: inspect repository"
    assert engine.snapshot().delegate_count == 1
    done = await engine.next_event()
    assert done.provider_done is not None

    result_ref = response_ref(2)
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as stale:
        await engine.send_delegate_result("call-1", ref, "canonical result")
    assert stale.value.reason == "NATIVE_DELEGATE_RESPONSE_NOT_NEW"

    output_ids = await engine.send_delegate_result(
        "call-1", result_ref, "canonical result"
    )
    assert len(output_ids) == 2
    assert [event["type"] for event in socket.sent[-2:]] == [
        "conversation.item.create",
        "response.create",
    ]
    assert socket.sent[-2]["item"] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "canonical result",
    }
    assert (
        await engine.send_delegate_result("call-1", result_ref, "canonical result")
        == output_ids
    )
    follow_up = await engine.next_event()
    assert follow_up.action is not None and follow_up.action.operation == "SPEAK"
    assert action_payload(follow_up) == {
        "provider_response_id": "provider-response-2",
        "turn_id": "native-turn-00000001",
        "runtime_response_id": result_ref.response_id,
        "response_generation": "2",
    }
    follow_up_audio = await engine.next_event()
    assert follow_up_audio.audio is not None
    assert follow_up_audio.audio.response == result_ref
    sent = tuple(socket.sent)
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as changed:
        await engine.send_delegate_result("call-1", result_ref, "changed result")
    assert changed.value.reason == "NATIVE_DELEGATE_RESULT_CONFLICT"
    assert tuple(socket.sent) == sent
    await engine.close()


@pytest.mark.asyncio
async def test_concurrent_exact_delegate_result_sends_one_provider_pair() -> None:
    engine, socket, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        function_done("event-7", "provider-response-1"),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))
    await engine.next_event()
    before = len(socket.sent)
    ref = response_ref(2)

    results = await asyncio.gather(
        engine.send_delegate_result("call-1", ref, "canonical result"),
        engine.send_delegate_result("call-1", ref, "canonical result"),
    )

    assert results[0] == results[1]
    assert [event["type"] for event in socket.sent[before:]] == [
        "conversation.item.create",
        "response.create",
    ]
    await engine.close()


@pytest.mark.asyncio
async def test_delegate_response_create_send_failure_fails_closed() -> None:
    engine, socket, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        function_done("event-7", "provider-response-1"),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))
    await engine.next_event()
    before = len(socket.sent)
    socket.fail_send_at = socket.send_calls + 2

    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.send_delegate_result("call-1", response_ref(2), "canonical result")

    assert raised.value.reason == "REALTIME_TRANSPORT_SEND_FAILED"
    assert [event["type"] for event in socket.sent[before:]] == [
        "conversation.item.create"
    ]
    snapshot = engine.snapshot()
    assert snapshot.state is NativeProviderState.FAILED
    assert snapshot.primary_error_reason == "REALTIME_TRANSPORT_SEND_FAILED"
    assert engine._delegate_results == {}
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "arguments", "reason"),
    [
        ("other_tool", '{"request_text":"x"}', "NATIVE_DELEGATE_FUNCTION_UNSUPPORTED"),
        ("jiuwen_delegate", "{", "NATIVE_DELEGATE_ARGUMENTS_INVALID"),
        (
            "jiuwen_delegate",
            '{"request_text":"x","tool":"shell"}',
            "NATIVE_DELEGATE_ARGUMENTS_NOT_CLOSED",
        ),
    ],
)
async def test_invalid_delegate_has_zero_delegate_effect(
    name: str, arguments: str, reason: str
) -> None:
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        function_done("event-7", "provider-response-1", name=name, arguments=arguments),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))
    before = engine.snapshot()
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.next_event()
    assert raised.value.reason == reason
    assert engine.snapshot().delegate_count == before.delegate_count == 0
    await engine.close()


@pytest.mark.asyncio
async def test_cancel_response_sends_exact_cancel_then_truncate_once() -> None:
    engine, socket, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x00\x00" * 480,
        ),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    ref = response_ref(1)
    await engine.admit_response("provider-response-1", ref)
    await engine.next_event()
    cursor = NativePresentationCursor(
        response=ref,
        provider_item_id="assistant-item-1",
        content_index=0,
        audio_end_ms=10,
    )
    ids = await engine.cancel_response(cursor)
    assert [event["type"] for event in socket.sent[-2:]] == [
        "response.cancel",
        "conversation.item.truncate",
    ]
    assert socket.sent[-2]["response_id"] == "provider-response-1"
    assert socket.sent[-1] == {
        "type": "conversation.item.truncate",
        "event_id": ids[1],
        "item_id": "assistant-item-1",
        "content_index": 0,
        "audio_end_ms": 10,
    }
    socket.push(
        provider_event(
            "conversation.item.truncated",
            "event-truncated-ack",
            item_id="assistant-item-1",
            content_index=0,
            audio_end_ms=10,
        )
    )
    assert await engine.next_event() == NativeEngineEvent()
    assert await engine.cancel_response(cursor) == ids
    sent = tuple(socket.sent)
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as changed:
        await engine.cancel_response(replace(cursor, audio_end_ms=9))
    assert changed.value.reason == "NATIVE_CANCEL_CONFLICT"
    assert tuple(socket.sent) == sent
    await engine.close()


@pytest.mark.asyncio
async def test_concurrent_exact_cancel_sends_one_provider_pair() -> None:
    engine, socket, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x00\x00" * 480,
        ),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    ref = response_ref(1)
    await engine.admit_response("provider-response-1", ref)
    await engine.next_event()
    cursor = NativePresentationCursor(
        response=ref,
        provider_item_id="assistant-item-1",
        content_index=0,
        audio_end_ms=10,
    )
    before = len(socket.sent)

    results = await asyncio.gather(
        engine.cancel_response(cursor), engine.cancel_response(cursor)
    )

    assert results[0] == results[1]
    assert [event["type"] for event in socket.sent[before:]] == [
        "response.cancel",
        "conversation.item.truncate",
    ]
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("late_kind", ["transcript", "function", "done"])
async def test_cancelled_response_discards_late_provider_authority_events(
    late_kind: str,
) -> None:
    late_events = {
        "transcript": output_transcript_done(
            "event-8",
            "provider-response-1",
            "assistant-item-1",
            "Too late.",
        ),
        "function": function_done("event-8", "provider-response-1"),
        "done": response_done("event-8", "provider-response-1", status="cancelled"),
    }
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x00\x00" * 480,
        ),
        late_events[late_kind],
        speech_started("event-9", "user-item-2", 40),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    ref = response_ref(1)
    await engine.admit_response("provider-response-1", ref)
    await engine.next_event()
    await engine.cancel_response(
        NativePresentationCursor(
            response=ref,
            provider_item_id="assistant-item-1",
            content_index=0,
            audio_end_ms=10,
        )
    )
    before = engine.snapshot()

    assert await engine.next_event() == NativeEngineEvent()
    listen = await engine.next_event()
    assert listen.action is not None and listen.action.operation == "LISTEN"
    after = engine.snapshot()
    assert after.released_audio_count == before.released_audio_count
    assert after.delegate_count == before.delegate_count
    assert after.retained_action_count == before.retained_action_count + 1
    await engine.close()


@pytest.mark.asyncio
async def test_cursorless_engine_fence_discards_late_output_without_provider_send() -> None:
    engine, socket, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta(
            "event-7",
            "provider-response-1",
            "assistant-item-1",
            0,
            pcm16=b"\x00\x00" * 480,
        ),
        output_transcript_done(
            "event-8",
            "provider-response-1",
            "assistant-item-1",
            "Too late.",
        ),
        function_done("event-9", "provider-response-1"),
        response_done("event-10", "provider-response-1"),
        speech_started("event-11", "user-item-2", 40),
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    ref = response_ref(1)
    await engine.admit_response("provider-response-1", ref)
    await engine.next_event()
    sent_before_fence = tuple(socket.sent)

    assert await engine.fence_response(ref) is True
    assert await engine.fence_response(ref) is False
    assert tuple(socket.sent) == sent_before_fence
    assert [await engine.next_event() for _ in range(3)] == [
        NativeEngineEvent(),
        NativeEngineEvent(),
        NativeEngineEvent(),
    ]
    listen = await engine.next_event()
    assert listen.action is not None and listen.action.operation == "LISTEN"
    assert engine.snapshot().delegate_count == 0
    assert tuple(socket.sent) == sent_before_fence
    await engine.close()


@pytest.mark.asyncio
async def test_queue_capacity_fails_before_two_action_barge_proposal() -> None:
    engine, socket, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta("event-7", "provider-response-1", "assistant-item-1", 0),
        speech_started("event-8", "user-item-2", 20),
        event_queue_capacity=1,
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    await engine.admit_response("provider-response-1", response_ref(1))
    await engine.next_event()
    before = engine.snapshot()
    sent_before = tuple(socket.sent)
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.next_event()
    assert raised.value.reason == "NATIVE_ENGINE_EVENT_QUEUE_FULL"
    after = engine.snapshot()
    assert after.retained_action_count == before.retained_action_count
    assert tuple(socket.sent) == sent_before
    await engine.close()


@pytest.mark.asyncio
async def test_barge_stop_proposal_binds_exact_runtime_generation() -> None:
    engine, _, _ = active_engine(
        speech_started("event-3", "user-item-1", 0),
        speech_stopped("event-4", "user-item-1", 20),
        input_committed("event-5", "user-item-1"),
        response_created("event-6", "provider-response-1"),
        output_audio_delta("event-7", "provider-response-1", "assistant-item-1", 0),
        speech_started("event-8", "user-item-2", 20),
        event_queue_capacity=2,
    )
    await engine.start()
    await accept_basic_turn(engine)
    await engine.next_event()
    ref = response_ref(1)
    await engine.admit_response("provider-response-1", ref)
    await engine.next_event()

    stop = await engine.next_event()
    listen = await engine.next_event()

    assert stop.action is not None and stop.action.operation == "STOP"
    assert action_payload(stop) == {
        "provider_response_id": "provider-response-1",
        "runtime_response_id": ref.response_id,
        "response_generation": "1",
    }
    assert listen.action is not None and listen.action.operation == "LISTEN"
    await engine.close()


@pytest.mark.asyncio
async def test_timeout_remote_close_process_control_and_unique_close() -> None:
    timeout_engine, timeout_socket, _ = active_engine(
        session_config=config(operation_timeout_seconds=0.01)
    )
    await timeout_engine.start()
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as timed_out:
        await timeout_engine.next_event()
    assert timed_out.value.reason == "REALTIME_PROVIDER_TIMEOUT"
    await timeout_engine.close()
    await timeout_engine.close()
    assert timeout_socket.close_calls == 1

    remote, _, _ = active_engine(ConnectionError("private-remote"))
    await remote.start()
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as remote_raised:
        await remote.next_event()
    assert remote_raised.value.reason == "REALTIME_TRANSPORT_RECEIVE_FAILED"
    await remote.close()

    process, process_socket, _ = active_engine(GeneratorExit())
    await process.start()
    with pytest.raises(GeneratorExit):
        await process.next_event()
    assert process.snapshot().state is NativeProviderState.FAILED
    await process.close()
    assert process_socket.close_calls == 1


@pytest.mark.asyncio
async def test_noncontiguous_input_audio_has_zero_provider_send() -> None:
    engine, socket, _ = active_engine()
    await engine.start()
    await engine.offer_audio(
        NativeInputAudioFrame(seq=0, sample_cursor=0, pcm16=b"\x00\x00" * 4)
    )
    before = tuple(socket.sent)
    with pytest.raises(OpenAIRealtimeNativeInteractionError) as raised:
        await engine.offer_audio(
            NativeInputAudioFrame(seq=2, sample_cursor=4, pcm16=b"\x00\x00" * 4)
        )
    assert raised.value.reason == "NATIVE_INPUT_AUDIO_SEQUENCE_GAP"
    assert tuple(socket.sent) == before
    await engine.close()


@pytest.mark.asyncio
async def test_concurrent_duplicate_input_sequence_sends_only_one_frame() -> None:
    engine, socket, _ = active_engine()
    await engine.start()
    frame = NativeInputAudioFrame(seq=0, sample_cursor=0, pcm16=b"\x00\x00" * 4)

    results = await asyncio.gather(
        engine.offer_audio(frame), engine.offer_audio(frame), return_exceptions=True
    )

    assert sum(type(result) is str for result in results) == 1
    errors = [
        result
        for result in results
        if isinstance(result, OpenAIRealtimeNativeInteractionError)
    ]
    assert len(errors) == 1
    assert errors[0].reason == "NATIVE_INPUT_AUDIO_SEQUENCE_GAP"
    assert (
        sum(event["type"] == "input_audio_buffer.append" for event in socket.sent) == 1
    )
    assert engine.snapshot().next_input_sequence == 1
    await engine.close()
