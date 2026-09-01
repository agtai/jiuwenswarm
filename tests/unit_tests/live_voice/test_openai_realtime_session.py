# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import asyncio
import json
import traceback
from collections.abc import Mapping

import pytest

from jiuwenswarm.server.live_voice.openai_realtime_session import (
    MAX_REALTIME_WIRE_MESSAGE_BYTES,
    OpenAIRealtimeSession,
    OpenAIRealtimeSessionConfig,
    OpenAIRealtimeSessionError,
    RealtimeSessionState,
    official_realtime_url,
)


class ScriptedRealtimeSocket:
    def __init__(
        self,
        initial: tuple[dict[str, object] | str | bytes | BaseException, ...] = (),
        *,
        close_failure: BaseException | None = None,
        send_failure_type: str | None = None,
    ) -> None:
        self.incoming: asyncio.Queue[str | bytes | BaseException] = asyncio.Queue()
        self.sent: list[dict[str, object]] = []
        self.close_calls = 0
        self.close_failure = close_failure
        self.send_failure_type = send_failure_type
        self.sent_event = asyncio.Event()
        self.close_started = asyncio.Event()
        self.close_released = asyncio.Event()
        self.block_close = False
        for value in initial:
            self.push(value)

    def push(self, value: dict[str, object] | str | bytes | BaseException) -> None:
        if isinstance(value, dict):
            self.incoming.put_nowait(json.dumps(value))
        else:
            self.incoming.put_nowait(value)

    async def send(self, message: str) -> None:
        parsed = json.loads(message)
        if parsed.get("type") == self.send_failure_type:
            raise RuntimeError(f"untrusted-send:{message}")
        self.sent.append(parsed)
        self.sent_event.set()

    async def recv(self) -> str | bytes:
        value = await self.incoming.get()
        if isinstance(value, BaseException):
            raise value
        return value

    async def close(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        if self.block_close:
            await self.close_released.wait()
        if self.close_failure is not None:
            raise self.close_failure


class CapturingFactory:
    def __init__(self, socket: ScriptedRealtimeSocket) -> None:
        self.socket = socket
        self.calls: list[tuple[str, dict[str, str], float]] = []

    async def __call__(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> ScriptedRealtimeSocket:
        self.calls.append((url, dict(headers), timeout))
        return self.socket


class PrivateNonJsonValue:
    def __init__(self, value: str) -> None:
        self.value = value

    def __repr__(self) -> str:
        return self.value


def event(event_type: str, event_id: str, **payload: object) -> dict[str, object]:
    return {"type": event_type, "event_id": event_id, **payload}


def negotiated_events() -> tuple[dict[str, object], dict[str, object]]:
    return (
        event(
            "session.created",
            "evt-1",
            session={"id": "sess-1", "type": "realtime"},
        ),
        event(
            "session.updated",
            "evt-2",
            session={"id": "sess-1", "type": "realtime"},
        ),
    )


def session_update() -> dict[str, object]:
    return {
        "type": "realtime",
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24_000},
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": 24_000},
            },
        },
    }


def realtime_config(**changes: object) -> OpenAIRealtimeSessionConfig:
    values: dict[str, object] = {
        "api_key": "private-realtime-test-key",
        "model": "gpt-realtime-2.1-mini",
        "operation_timeout_seconds": 0.1,
        "close_timeout_seconds": 0.05,
    }
    values.update(changes)
    return OpenAIRealtimeSessionConfig(**values)  # type: ignore[arg-type]


def session_traceback_with_locals(exc: BaseException) -> str:
    provider_traceback = exc.__traceback__
    while (
        provider_traceback is not None
        and not provider_traceback.tb_frame.f_code.co_filename.replace(
            "\\", "/"
        ).endswith("/jiuwenswarm/server/live_voice/openai_realtime_session.py")
    ):
        provider_traceback = provider_traceback.tb_next
    return "".join(
        traceback.TracebackException(
            type(exc),
            exc,
            provider_traceback,
            capture_locals=True,
        ).format()
    )


@pytest.mark.asyncio
async def test_session_negotiates_once_and_replays_identical_provider_event() -> None:
    provider_event = event(
        "input_audio_buffer.speech_started",
        "evt-3",
        audio_start_ms=20,
    )
    socket = ScriptedRealtimeSocket(
        (*negotiated_events(), provider_event, provider_event)
    )
    factory = CapturingFactory(socket)
    session = OpenAIRealtimeSession(realtime_config(), socket_factory=factory)

    await session.open(session_update=session_update())
    first = await session.receive_event()
    replay = await session.receive_event()

    assert first == replay
    assert first.event_type == "input_audio_buffer.speech_started"
    assert first.event_id == "evt-3"
    assert first.to_dict() == provider_event
    assert session.snapshot().provider_event_count == 3
    assert session.snapshot().provider_session_id == "sess-1"
    assert session.snapshot().state is RealtimeSessionState.OPEN
    assert factory.calls == [
        (
            "wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1-mini",
            {"Authorization": "Bearer private-realtime-test-key"},
            realtime_config().connect_timeout_seconds,
        )
    ]
    assert socket.sent == [
        {
            "type": "session.update",
            "event_id": "client_event_00000001",
            "session": session_update(),
        }
    ]
    await session.close()


@pytest.mark.asyncio
async def test_changed_provider_event_replay_fails_and_close_remains_unique() -> None:
    socket = ScriptedRealtimeSocket(
        (
            *negotiated_events(),
            event("response.created", "evt-3", response={"id": "r1"}),
            event("response.created", "evt-3", response={"id": "r2"}),
        )
    )
    session = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(socket)
    )
    await session.open(session_update=session_update())
    await session.receive_event()

    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await session.receive_event()

    assert raised.value.reason == "REALTIME_PROVIDER_EVENT_CONFLICT"
    assert session.snapshot().primary_error_reason == raised.value.reason
    first, second = await asyncio.gather(session.close(), session.close())
    assert first == second
    assert first.state is RealtimeSessionState.CLOSED
    assert socket.close_calls == 1


@pytest.mark.asyncio
async def test_send_event_uses_closed_payload_and_monotonic_identity() -> None:
    socket = ScriptedRealtimeSocket(negotiated_events())
    session = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(socket)
    )
    await session.open(session_update=session_update())

    event_id = await session.send_event("input_audio_buffer.append", {"audio": "AAEC"})

    assert event_id == "client_event_00000002"
    assert socket.sent[-1] == {
        "type": "input_audio_buffer.append",
        "event_id": event_id,
        "audio": "AAEC",
    }
    before = tuple(socket.sent)
    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await session.send_event("response.create", {"type": "forged"})
    assert raised.value.reason == "REALTIME_CLIENT_EVENT_NOT_CLOSED"
    assert tuple(socket.sent) == before
    await session.close()


@pytest.mark.asyncio
async def test_send_failures_drop_audio_and_session_update_payloads() -> None:
    private_audio = "private-native-audio-value"
    audio_socket = ScriptedRealtimeSocket(
        negotiated_events(), send_failure_type="input_audio_buffer.append"
    )
    audio_session = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(audio_socket)
    )
    await audio_session.open(session_update=session_update())
    with pytest.raises(OpenAIRealtimeSessionError) as audio_raised:
        await audio_session.send_event(
            "input_audio_buffer.append", {"audio": private_audio}
        )
    assert audio_raised.value.reason == "REALTIME_TRANSPORT_SEND_FAILED"
    assert private_audio not in session_traceback_with_locals(audio_raised.value)
    await audio_session.close()

    private_instruction = "private-native-instruction-value"
    update_socket = ScriptedRealtimeSocket(
        (negotiated_events()[0],), send_failure_type="session.update"
    )
    update_session = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(update_socket)
    )
    private_update = session_update()
    private_update["instructions"] = private_instruction
    with pytest.raises(OpenAIRealtimeSessionError) as update_raised:
        await update_session.open(session_update=private_update)
    assert update_raised.value.reason == "REALTIME_TRANSPORT_SEND_FAILED"
    assert private_instruction not in session_traceback_with_locals(update_raised.value)
    assert update_socket.close_calls == 1


@pytest.mark.asyncio
async def test_provider_event_capacity_replays_recent_and_evicts_oldest() -> None:
    retained = event("response.created", "evt-3", response={"id": "r1"})
    socket = ScriptedRealtimeSocket(
        (
            *negotiated_events(),
            retained,
            retained,
            event("response.done", "evt-4", response={"id": "r1"}),
        )
    )
    session = OpenAIRealtimeSession(
        realtime_config(max_provider_events=3),
        socket_factory=CapturingFactory(socket),
    )
    await session.open(session_update=session_update())
    assert await session.receive_event() == await session.receive_event()

    terminal = await session.receive_event()

    assert terminal.event_type == "response.done"
    assert terminal.event_id == "evt-4"
    assert session.snapshot().provider_event_count == 3
    assert session.snapshot().state is RealtimeSessionState.OPEN
    await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wire", "reason"),
    [
        (b"binary", "REALTIME_PROVIDER_MESSAGE_NOT_TEXT"),
        (
            '{"type":"response.created","event_id":"evt-3","event_id":"evt-4"}',
            "REALTIME_PROVIDER_MESSAGE_INVALID",
        ),
        (
            "x" * (MAX_REALTIME_WIRE_MESSAGE_BYTES + 1),
            "REALTIME_PROVIDER_MESSAGE_TOO_LARGE",
        ),
    ],
    ids=("binary", "duplicate-key", "oversized"),
)
async def test_provider_wire_is_bounded_text_with_unique_json_keys(
    wire: str | bytes, reason: str
) -> None:
    socket = ScriptedRealtimeSocket((*negotiated_events(), wire))
    session = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(socket)
    )
    await session.open(session_update=session_update())

    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await session.receive_event()

    assert raised.value.reason == reason
    await session.close()


@pytest.mark.asyncio
async def test_provider_protocol_and_conflict_tracebacks_drop_raw_wire() -> None:
    private_wire = "private-provider-wire-value"
    malformed_socket = ScriptedRealtimeSocket(
        (*negotiated_events(), f'{{"private":"{private_wire}"')
    )
    malformed = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(malformed_socket)
    )
    await malformed.open(session_update=session_update())
    with pytest.raises(OpenAIRealtimeSessionError) as malformed_raised:
        await malformed.receive_event()
    assert malformed_raised.value.reason == "REALTIME_PROVIDER_MESSAGE_INVALID"
    assert private_wire not in session_traceback_with_locals(malformed_raised.value)
    await malformed.close()

    private_response = "private-provider-response-value"
    conflict_socket = ScriptedRealtimeSocket(
        (
            *negotiated_events(),
            event("response.created", "evt-3", response={"id": "retained"}),
            event(
                "response.created",
                "evt-3",
                response={"id": private_response},
            ),
        )
    )
    conflict = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(conflict_socket)
    )
    await conflict.open(session_update=session_update())
    await conflict.receive_event()
    with pytest.raises(OpenAIRealtimeSessionError) as conflict_raised:
        await conflict.receive_event()
    assert conflict_raised.value.reason == "REALTIME_PROVIDER_EVENT_CONFLICT"
    assert private_response not in session_traceback_with_locals(conflict_raised.value)
    await conflict.close()


@pytest.mark.asyncio
async def test_open_session_receive_idle_keeps_waiting_for_next_provider_event() -> None:
    socket = ScriptedRealtimeSocket(negotiated_events())
    session = OpenAIRealtimeSession(
        realtime_config(operation_timeout_seconds=0.01),
        socket_factory=CapturingFactory(socket),
    )
    await session.open(session_update=session_update())

    receive_task = asyncio.create_task(session.receive_event())
    await asyncio.sleep(0.035)

    assert receive_task.done() is False
    assert session.snapshot().state is RealtimeSessionState.OPEN
    assert session.snapshot().primary_error_reason is None

    socket.push(event("input_audio_buffer.speech_started", "evt-3", audio_start_ms=0))
    received = await asyncio.wait_for(receive_task, timeout=1)

    assert received.event_id == "evt-3"
    snapshot = await session.close()
    assert snapshot.state is RealtimeSessionState.CLOSED
    assert socket.close_calls == 1


@pytest.mark.asyncio
async def test_negotiation_receive_timeout_remains_typed_and_closes_once() -> None:
    socket = ScriptedRealtimeSocket((negotiated_events()[0],))
    session = OpenAIRealtimeSession(
        realtime_config(operation_timeout_seconds=0.01),
        socket_factory=CapturingFactory(socket),
    )

    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await session.open(session_update=session_update())

    assert raised.value.reason == "REALTIME_PROVIDER_TIMEOUT"
    assert session.snapshot().state is RealtimeSessionState.CLOSED
    assert socket.close_calls == 1


@pytest.mark.asyncio
async def test_negotiation_mismatch_closes_without_exposing_provider_or_secret() -> (
    None
):
    private_value = "private-provider-session-value"
    socket = ScriptedRealtimeSocket(
        (
            event(
                "session.created",
                "evt-1",
                session={"id": private_value, "type": "realtime"},
            ),
            event(
                "session.updated",
                "evt-2",
                session={"id": "different-session", "type": "realtime"},
            ),
        )
    )
    session = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(socket)
    )

    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await session.open(session_update=session_update())

    assert raised.value.reason == "REALTIME_SESSION_NEGOTIATION_FAILED"
    assert private_value not in str(raised.value)
    assert "private-realtime-test-key" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert socket.close_calls == 1


@pytest.mark.asyncio
async def test_connect_failure_drops_secret_traceback_and_empty_transport() -> None:
    secret = "private-realtime-test-key"

    async def failing_factory(
        _url: str, headers: Mapping[str, str], _timeout: float
    ) -> ScriptedRealtimeSocket:
        raise RuntimeError(f"untrusted:{headers['Authorization']}")

    failing = OpenAIRealtimeSession(
        realtime_config(api_key=secret), socket_factory=failing_factory
    )
    private_instruction = "private-connect-instruction-value"
    connect_update = session_update()
    connect_update["instructions"] = private_instruction
    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await failing.open(session_update=connect_update)
    assert raised.value.reason == "REALTIME_CONNECT_FAILED"
    assert secret not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    formatted = session_traceback_with_locals(raised.value)
    assert secret not in formatted
    assert "Authorization" not in formatted
    assert private_instruction not in formatted

    async def empty_factory(
        _url: str, _headers: Mapping[str, str], _timeout: float
    ) -> ScriptedRealtimeSocket:
        return None  # type: ignore[return-value]

    empty = OpenAIRealtimeSession(realtime_config(), socket_factory=empty_factory)
    with pytest.raises(OpenAIRealtimeSessionError) as empty_raised:
        await empty.open(session_update=session_update())
    assert empty_raised.value.reason == "REALTIME_CONNECT_FAILED"
    assert empty.snapshot().provider_event_count == 0
    assert empty.snapshot().state is RealtimeSessionState.CLOSED


@pytest.mark.asyncio
async def test_invalid_session_update_has_zero_transport_and_safe_traceback() -> None:
    private_value = "private-invalid-session-update-value"
    socket = ScriptedRealtimeSocket()
    factory = CapturingFactory(socket)
    session = OpenAIRealtimeSession(realtime_config(), socket_factory=factory)

    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await session.open(
            session_update={"instructions": PrivateNonJsonValue(private_value)}
        )

    assert raised.value.reason == "REALTIME_CLIENT_EVENT_INVALID"
    assert factory.calls == []
    assert socket.close_calls == 0
    assert session.snapshot().state is RealtimeSessionState.CLOSED
    assert private_value not in session_traceback_with_locals(raised.value)


@pytest.mark.asyncio
async def test_cancel_during_negotiation_closes_allocated_socket_once() -> None:
    socket = ScriptedRealtimeSocket((negotiated_events()[0],))
    session = OpenAIRealtimeSession(
        realtime_config(operation_timeout_seconds=1.0),
        socket_factory=CapturingFactory(socket),
    )
    open_task = asyncio.create_task(session.open(session_update=session_update()))
    await asyncio.wait_for(socket.sent_event.wait(), timeout=1)

    open_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await open_task

    assert socket.close_calls == 1
    assert session.snapshot().state is RealtimeSessionState.CLOSED
    assert session.snapshot().close_complete is True


@pytest.mark.asyncio
async def test_close_failure_is_secondary_to_first_primary_error() -> None:
    socket = ScriptedRealtimeSocket(
        (
            *negotiated_events(),
            event("response.created", "evt-3", response={"id": "r1"}),
            event("response.created", "evt-3", response={"id": "r2"}),
        ),
        close_failure=RuntimeError("private-close-value"),
    )
    session = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(socket)
    )
    await session.open(session_update=session_update())
    await session.receive_event()
    with pytest.raises(OpenAIRealtimeSessionError) as raised:
        await session.receive_event()

    snapshot = await session.close()

    assert snapshot.primary_error_reason == raised.value.reason
    assert snapshot.close_error_reason == "REALTIME_TRANSPORT_CLOSE_FAILED"
    assert snapshot.state is RealtimeSessionState.CLOSED
    assert "private-close-value" not in repr(snapshot)
    assert socket.close_calls == 1


@pytest.mark.asyncio
async def test_concurrent_close_uses_one_retained_transport_task() -> None:
    socket = ScriptedRealtimeSocket(negotiated_events())
    socket.block_close = True
    session = OpenAIRealtimeSession(
        realtime_config(close_timeout_seconds=0.01),
        socket_factory=CapturingFactory(socket),
    )
    await session.open(session_update=session_update())

    first = asyncio.create_task(session.close())
    second = asyncio.create_task(session.close())
    await asyncio.wait_for(socket.close_started.wait(), timeout=1)
    first_snapshot, second_snapshot = await asyncio.gather(first, second)

    assert first_snapshot.state is RealtimeSessionState.CLOSING
    assert second_snapshot.state is RealtimeSessionState.CLOSING
    assert first_snapshot.close_complete is False
    assert socket.close_calls == 1
    socket.close_released.set()
    final = await session.close()
    assert final.state is RealtimeSessionState.CLOSED
    assert final.close_complete is True
    assert socket.close_calls == 1


@pytest.mark.asyncio
async def test_transport_process_control_propagates_after_state_finalization() -> None:
    socket = ScriptedRealtimeSocket(negotiated_events(), close_failure=GeneratorExit())
    session = OpenAIRealtimeSession(
        realtime_config(), socket_factory=CapturingFactory(socket)
    )
    await session.open(session_update=session_update())

    with pytest.raises(GeneratorExit):
        await session.close()

    assert session.snapshot().state is RealtimeSessionState.CLOSED
    assert session.snapshot().close_complete is True
    assert socket.close_calls == 1


def test_config_and_official_url_are_closed_and_secret_safe() -> None:
    config = realtime_config()
    assert "private-realtime-test-key" not in repr(config)
    assert (
        official_realtime_url(config.api_base, model="gpt-realtime/custom")
        == "wss://api.openai.com/v1/realtime?model=gpt-realtime%2Fcustom"
    )
    assert (
        official_realtime_url(config.api_base, intent="transcription")
        == "wss://api.openai.com/v1/realtime?intent=transcription"
    )

    for kwargs in ({}, {"model": "m", "intent": "transcription"}):
        with pytest.raises(ValueError, match="exactly one"):
            official_realtime_url(config.api_base, **kwargs)
    with pytest.raises(ValueError, match="official OpenAI"):
        official_realtime_url("https://example.com/v1", model="m")
    with pytest.raises(ValueError, match="model"):
        realtime_config(model="bad\nmodel")
