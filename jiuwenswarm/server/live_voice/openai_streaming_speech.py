# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Default-off OpenAI streaming Speech Adapter and degradation seam.

The Provider wire protocol stops in this module.  It never commits a Turn,
dispatches Agent/Tool/Task work, writes history, or claims browser playout.
Transport close is retained as a transport observation and never promoted to a
Provider cancel acknowledgement.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import inspect
import json
import logging
import math
import os
import struct
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, TypeVar
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from jiuwenswarm.server.live_voice.batch_speech import (
    SPEECH_API_BASE_ENV,
    SPEECH_API_KEY_ENV,
    SPEECH_PROVIDER_ENV,
    SPEECH_STT_MODEL_ENV,
    SPEECH_TTS_MODEL_ENV,
    SPEECH_TTS_VOICE_ENV,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEventKind,
    RecognitionHypothesis,
    SpeechMode,
    SynthesisEventKind,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    CapabilityProvenance,
    MAX_AUDIO_SAMPLES_PER_FRAME,
    NativeStreamingSpeechProvider,
    ProviderTransport,
    RecognitionCommitDisposition,
    RecognitionAudioFrame,
    RecognitionProviderSupport,
    RecognitionStreamRequest,
    RecognitionStreamRef,
    RecognitionTimingBasis,
    RecognitionTurnBoundaryEvent,
    RecognitionTurnBoundaryKind,
    RecognitionTurnDetection,
    RecognitionTurnDetectionMode,
    StreamingRecognitionOutput,
    StreamingProviderCapability,
    StreamingRecognitionEvent,
    StreamingSpeechConformance,
    StreamingSpeechViolation,
    StreamingSynthesisEvent,
    SynthesisProviderSupport,
    SynthesisStreamRef,
    SynthesisStreamRequest,
)


STREAMING_SPEECH_FLAG = "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED"
DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe-2025-12-15"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts-2025-12-15"
DEFAULT_TTS_VOICE = "marin"
OPENAI_PCM_RATE_HZ = 24_000
MAX_WIRE_MESSAGE_BYTES = 1_048_576
MAX_SSE_LINE_BYTES = 262_144
MAX_SSE_EVENT_BYTES = 1_048_576
MAX_STREAM_AUDIO_BYTES = 8 * 1024 * 1024
MAX_PROVIDER_AUDIO_DELTA_BYTES = 96_000
MAX_EVENT_QUEUE = 64
MAX_SAFE_LABEL_CHARS = 256
DEGRADATION_SINK_BUDGET_SECONDS = 0.05
DEGRADATION_SINK_CLOSE_BUDGET_SECONDS = 0.1
MAX_DEGRADATION_SINK_TASKS_PER_OWNER = 4
MAX_DEGRADATION_SINK_TASKS_GLOBAL = 16
TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS = 0.05
TRANSPORT_CLEANUP_CLOSE_BUDGET_SECONDS = 0.1
MAX_INCOMPLETE_TRANSPORT_CLEANUPS = 32

_PROVIDER = ProviderRef("openai-streaming-speech", "formal")
_LOGGER = logging.getLogger(__name__)
_QueueValue = TypeVar("_QueueValue")


class OpenAIStreamingSpeechError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class SpeechRouteTier(StrEnum):
    STREAMING = "streaming"
    BATCH = "batch"
    TEXT = "text"


class SpeechDegradationReason(StrEnum):
    FEATURE_OFF = "STREAMING_SPEECH_FEATURE_OFF"
    CONFIGURATION_UNAVAILABLE = "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "STREAMING_SPEECH_PROVIDER_UNAVAILABLE"
    PROVIDER_PROTOCOL = "STREAMING_SPEECH_PROVIDER_PROTOCOL"
    PROVIDER_TIMEOUT = "STREAMING_SPEECH_PROVIDER_TIMEOUT"
    PROVIDER_CANCEL_UNACKNOWLEDGED = "STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED"
    BOUNDED_QUEUE_EXHAUSTED = "STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class SpeechDegradationFact:
    """One safe user-visible degradation fact with an X-OBS binding seam."""

    binding_ref: str
    operation: str
    reason: SpeechDegradationReason
    from_tier: SpeechRouteTier
    to_tier: SpeechRouteTier
    provider_id: str
    visible: bool
    latency_ms: int | None
    # The Provider adapter has no authoritative product trace binding.  The
    # product owner may replace these nulls with a typed X-OBS fact only after
    # it has enqueued an exact-bound diagnostic record.
    x_obs_event: str | None = None
    x_obs_metric: str | None = None
    metric_value: int = 1

    def safe_dict(self) -> dict[str, object]:
        return {
            "binding_ref": self.binding_ref,
            "operation": self.operation,
            "reason": self.reason.value,
            "from_tier": self.from_tier.value,
            "to_tier": self.to_tier.value,
            "provider_id": self.provider_id,
            "visible": self.visible,
            "latency_ms": self.latency_ms,
            "x_obs_event": self.x_obs_event,
            "x_obs_metric": self.x_obs_metric,
            "metric_value": self.metric_value,
        }


@dataclass(frozen=True, slots=True)
class TransportCleanupSnapshot:
    retained_task_count: int
    failed_resource_count: int
    incomplete_kinds: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return self.retained_task_count == self.failed_resource_count == 0


@dataclass(frozen=True, slots=True)
class StreamingSpeechSelection:
    tier: SpeechRouteTier
    provider: NativeStreamingSpeechProvider | None
    fact: SpeechDegradationFact | None


@dataclass(frozen=True, slots=True)
class OpenAIStreamingSpeechConfig:
    api_base: str
    api_key: str = field(repr=False)
    stt_model: str = DEFAULT_STT_MODEL
    tts_model: str = DEFAULT_TTS_MODEL
    tts_voice: str = DEFAULT_TTS_VOICE
    connect_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_base", _validate_api_base(self.api_base))
        _required_secret(self.api_key)
        _safe_label(self.stt_model, "stt_model")
        _safe_label(self.tts_model, "tts_model")
        _safe_label(self.tts_voice, "tts_voice")
        if (
            isinstance(self.connect_timeout_seconds, bool)
            or not isinstance(self.connect_timeout_seconds, (int, float))
            or not math.isfinite(self.connect_timeout_seconds)
            or not 0 < self.connect_timeout_seconds <= 30
        ):
            raise ValueError("connect timeout must be finite and in (0, 30]")


class RealtimeSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


class SpeechSseStream(Protocol):
    def __aiter__(self) -> AsyncIterator[str]: ...

    async def aclose(self) -> None: ...


RealtimeSocketFactory = Callable[
    [str, Mapping[str, str], float], Awaitable[RealtimeSocket]
]
SpeechSseFactory = Callable[
    [str, Mapping[str, str], Mapping[str, str], float],
    Awaitable[SpeechSseStream],
]
DegradationSink = Callable[[SpeechDegradationFact], object]


_DEGRADATION_SINK_TASKS: set[asyncio.Task[_SinkOutcome]] = set()


@dataclass(frozen=True, slots=True)
class _SinkOutcome:
    succeeded: bool
    process_control: BaseException | None = None


class _DegradationSinkTaskOwner:
    """Bound optional async observers without making them Provider authority."""

    def __init__(self) -> None:
        self._tasks: dict[asyncio.Task[_SinkOutcome], SpeechDegradationFact] = {}
        self._process_controls: deque[BaseException] = deque(
            maxlen=MAX_DEGRADATION_SINK_TASKS_PER_OWNER
        )
        self._closed = False

    @property
    def retained_task_count(self) -> int:
        self._prune()
        return len(self._tasks)

    async def publish(
        self, fact: SpeechDegradationFact, sink: DegradationSink | None
    ) -> None:
        _LOGGER.warning(
            "live_voice_speech_degradation %s",
            json.dumps(fact.safe_dict(), sort_keys=True, separators=(",", ":")),
        )
        if sink is None:
            return
        self._prune()
        self._raise_process_control()
        _prune_global_sink_tasks()
        try:
            result = sink(fact)
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
            del exc
            sink = None
            if _is_process_control(failure):
                raise failure from None
            _log_sink_unavailable(fact, reason="sync-error")
            return
        if not inspect.isawaitable(result):
            return
        if self._closed:
            _discard_sink_awaitable(result)
            _log_sink_unavailable(fact, reason="owner-closed")
            return
        if len(self._tasks) >= MAX_DEGRADATION_SINK_TASKS_PER_OWNER:
            _discard_sink_awaitable(result)
            _log_sink_unavailable(fact, reason="owner-capacity")
            return
        if len(_DEGRADATION_SINK_TASKS) >= MAX_DEGRADATION_SINK_TASKS_GLOBAL:
            _discard_sink_awaitable(result)
            _log_sink_unavailable(fact, reason="global-capacity")
            return
        task = asyncio.create_task(_await_sink(result))
        self._tasks[task] = fact
        _DEGRADATION_SINK_TASKS.add(task)
        task.add_done_callback(self._release)
        try:
            done, _ = await asyncio.wait(
                {task}, timeout=DEGRADATION_SINK_BUDGET_SECONDS
            )
        except asyncio.CancelledError:
            task.cancel()
            _log_sink_unavailable(fact, reason="caller-cancelled")
            raise
        if task not in done:
            task.cancel()
            _log_sink_unavailable(fact, reason="timeout")
            return
        outcome = task.result()
        self._release(task)
        self._raise_process_control()
        if not outcome.succeeded:
            _log_sink_unavailable(fact, reason="async-error")

    async def close(self) -> None:
        self._closed = True
        self._prune()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if not tasks:
            self._raise_process_control()
            return
        _, pending = await asyncio.wait(
            tasks, timeout=DEGRADATION_SINK_CLOSE_BUDGET_SECONDS
        )
        for task in pending:
            task.cancel()
            fact = self._tasks.get(task)
            if fact is not None:
                _log_sink_unavailable(fact, reason="close-timeout")
        self._prune()
        self._raise_process_control()

    def _prune(self) -> None:
        for task in tuple(self._tasks):
            if task.done():
                self._release(task)

    def _release(self, task: asyncio.Task[_SinkOutcome]) -> None:
        fact = self._tasks.pop(task, None)
        if fact is None:
            return
        _DEGRADATION_SINK_TASKS.discard(task)
        if task.cancelled():
            return
        with suppress(Exception, asyncio.CancelledError):
            outcome = task.result()
            if outcome.process_control is not None:
                self._process_controls.append(outcome.process_control)

    def _raise_process_control(self) -> None:
        if self._process_controls:
            raise self._process_controls.popleft() from None


@dataclass(frozen=True, slots=True)
class _CleanupOutcome:
    succeeded: bool
    process_control: BaseException | None = None


@dataclass(frozen=True, slots=True)
class _CleanupEntry:
    key: tuple[str, int]
    kind: str
    cleanup: Callable[[], Awaitable[None]] | None


class _TransportCleanupOwner:
    """Retain non-cooperative cleanup without extending caller deadlines."""

    def __init__(self) -> None:
        self._tasks: dict[asyncio.Task[_CleanupOutcome], _CleanupEntry] = {}
        self._by_key: dict[tuple[str, int], asyncio.Task[_CleanupOutcome]] = {}
        self._failed: dict[tuple[str, int], _CleanupEntry] = {}
        self._process_controls: deque[BaseException] = deque(
            maxlen=MAX_INCOMPLETE_TRANSPORT_CLEANUPS
        )

    def snapshot(self) -> TransportCleanupSnapshot:
        self._prune()
        kinds = sorted(
            entry.kind for entry in (*self._tasks.values(), *self._failed.values())
        )
        return TransportCleanupSnapshot(
            retained_task_count=len(self._tasks),
            failed_resource_count=len(self._failed),
            incomplete_kinds=tuple(kinds),
        )

    def require_session_capacity(self, *, active_sessions: int) -> None:
        snapshot = self.snapshot()
        incomplete = snapshot.retained_task_count + snapshot.failed_resource_count
        # One active session can retain both its transport close and worker task.
        if incomplete + (active_sessions + 1) * 2 > MAX_INCOMPLETE_TRANSPORT_CLEANUPS:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_CLEANUP_CAPACITY",
                "streaming Speech cleanup capacity is exhausted",
            )

    async def attempt(
        self,
        *,
        kind: str,
        resource: object,
        cleanup: Callable[[], Awaitable[None]],
    ) -> bool:
        self._prune()
        self._raise_process_control()
        key = (kind, id(resource))
        task = self._by_key.get(key)
        if task is not None:
            # A previous caller already owns the bounded close attempt.  Waiting
            # another full budget here would couple worker termination to a
            # cancellation-defiant transport close.
            _log_transport_cleanup(
                kind=kind, reason="already-pending", retained_count=len(self._tasks)
            )
            return False
        entry = self._failed.pop(key, None) or _CleanupEntry(key, kind, cleanup)
        if len(self._tasks) + len(self._failed) >= MAX_INCOMPLETE_TRANSPORT_CLEANUPS:
            _log_transport_cleanup(
                kind=kind, reason="capacity", retained_count=len(self._tasks)
            )
            return False
        task = asyncio.create_task(_await_cleanup(entry.cleanup))
        self._tasks[task] = entry
        self._by_key[key] = task
        task.add_done_callback(self._release)
        try:
            done, _ = await asyncio.wait(
                {task}, timeout=TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS
            )
        except asyncio.CancelledError:
            task.cancel()
            _log_transport_cleanup(
                kind=kind, reason="caller-cancelled", retained_count=len(self._tasks)
            )
            raise
        if task not in done:
            # The caller's budget is spent, but the close itself must keep
            # running: a real WebSocket close handshake needs a network round
            # trip, which never fits this budget.  Cancelling here would leave
            # the transport half-open and, because a cancelled cleanup is
            # retained as failed, would permanently consume one cleanup slot
            # per stream until capacity is exhausted.  Retaining the task keeps
            # the caller hard-bounded while the owner still finishes and
            # releases the slot.
            _log_transport_cleanup(
                kind=kind, reason="timeout", retained_count=len(self._tasks)
            )
            return False
        self._prune()
        self._raise_process_control()
        if task.cancelled():
            return False
        outcome = task.result()
        return outcome.succeeded

    async def cancel_task(self, task: asyncio.Task[Any], *, kind: str) -> bool:
        self._prune()
        self._raise_process_control()
        if task.done():
            self._raise_task_process_control(task)
            return True
        key = (kind, id(task))
        tracked = self._by_key.get(key)
        if tracked is None:
            if (
                len(self._tasks) + len(self._failed)
                >= MAX_INCOMPLETE_TRANSPORT_CLEANUPS
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_CLEANUP_CAPACITY",
                    "streaming Speech cleanup capacity is exhausted",
                )
            tracked = asyncio.create_task(_await_cancelled_task(task))
            entry = _CleanupEntry(key, kind, None)
            self._tasks[tracked] = entry
            self._by_key[key] = tracked
            tracked.add_done_callback(self._release)
        task.cancel()
        try:
            done, _ = await asyncio.wait(
                {tracked}, timeout=TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS
            )
        except asyncio.CancelledError:
            task.cancel()
            _log_transport_cleanup(
                kind=kind, reason="caller-cancelled", retained_count=len(self._tasks)
            )
            raise
        if tracked not in done:
            task.cancel()
            _log_transport_cleanup(
                kind=kind, reason="timeout", retained_count=len(self._tasks)
            )
            return False
        self._prune()
        self._raise_process_control()
        if tracked.cancelled():
            return False
        outcome = tracked.result()
        return outcome.succeeded

    async def close(self) -> TransportCleanupSnapshot:
        self._prune()
        for entry in tuple(self._failed.values()):
            if (
                entry.cleanup is None
                or len(self._tasks) >= MAX_INCOMPLETE_TRANSPORT_CLEANUPS
            ):
                continue
            self._failed.pop(entry.key, None)
            task = asyncio.create_task(_await_cleanup(entry.cleanup))
            self._tasks[task] = entry
            self._by_key[entry.key] = task
            task.add_done_callback(self._release)
        tasks = tuple(self._tasks)
        if tasks:
            _, pending = await asyncio.wait(
                tasks, timeout=TRANSPORT_CLEANUP_CLOSE_BUDGET_SECONDS
            )
            for task in pending:
                pending_entry = self._tasks.get(task)
                if pending_entry is not None:
                    # A cleanup coroutine may ignore cancellation.  Keep its task
                    # owned and counted so close remains hard-bounded and honest.
                    if pending_entry.cleanup is not None:
                        task.cancel()
                    _log_transport_cleanup(
                        kind=pending_entry.kind,
                        reason="close-timeout",
                        retained_count=len(self._tasks),
                    )
        self._prune()
        self._raise_process_control()
        return self.snapshot()

    def _prune(self) -> None:
        for task in tuple(self._tasks):
            if task.done():
                self._release(task)

    def _release(self, task: asyncio.Task[_CleanupOutcome]) -> None:
        entry = self._tasks.pop(task, None)
        if entry is None:
            return
        if self._by_key.get(entry.key) is task:
            del self._by_key[entry.key]
        if task.cancelled():
            if entry.cleanup is not None:
                self._failed[entry.key] = entry
            return
        with suppress(Exception, asyncio.CancelledError):
            outcome = task.result()
            if outcome.process_control is not None:
                self._process_controls.append(outcome.process_control)
            if not outcome.succeeded and entry.cleanup is not None:
                self._failed[entry.key] = entry

    def _raise_process_control(self) -> None:
        if self._process_controls:
            raise self._process_controls.popleft() from None

    @staticmethod
    def _raise_task_process_control(task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None and _is_process_control(failure):
            raise _safe_boundary_exception(failure) from None


_SELECTOR_DEGRADATION_SINK_TASKS = _DegradationSinkTaskOwner()


class _RecognitionCommitOwner(StrEnum):
    NONE = "none"
    MANUAL = "manual"
    SERVER_VAD = "server_vad"


@dataclass(slots=True)
class _RecognitionSession:
    request: RecognitionStreamRequest
    socket: RealtimeSocket = field(repr=False)
    resampler: _StreamingLinearResampler
    events: asyncio.Queue[StreamingRecognitionOutput] = field(repr=False)
    ready: asyncio.Future[None] = field(repr=False)
    deadline: float
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    receive_task: asyncio.Task[None] | None = field(default=None, repr=False)
    partial_text: str = field(default="", repr=False)
    item_id: str | None = None
    speech_item_id: str | None = field(default=None, repr=False)
    speech_start_ms: int | None = None
    speech_end_ms: int | None = None
    source_cursor: int = 0
    committed_source_cursor: int | None = None
    event_seq: int = 0
    committed: bool = False
    input_fenced: bool = False
    commit_owner: _RecognitionCommitOwner = _RecognitionCommitOwner.NONE
    closing: bool = False
    terminal: bool = False

    @property
    def ref(self) -> RecognitionStreamRef:
        return self.request.ref


@dataclass(slots=True)
class _SynthesisSession:
    request: SynthesisStreamRequest = field(repr=False)
    events: asyncio.Queue[StreamingSynthesisEvent] = field(repr=False)
    resampler: _StreamingLinearResampler
    task: asyncio.Task[None] | None = field(default=None, repr=False)
    stream: SpeechSseStream | None = field(default=None, repr=False)
    event_seq: int = 0
    audio_cursor: int = 0
    wire_audio_bytes: int = 0
    closing: bool = False
    terminal: bool = False


class _StreamingLinearResampler:
    """Stateful mono linear resampling whose chunking cannot change output."""

    def __init__(self, input_rate_hz: int, output_rate_hz: int) -> None:
        if type(input_rate_hz) is not int or input_rate_hz <= 0:
            raise ValueError("input sample rate must be positive")
        if type(output_rate_hz) is not int or output_rate_hz <= 0:
            raise ValueError("output sample rate must be positive")
        self.input_rate_hz = input_rate_hz
        self.output_rate_hz = output_rate_hz
        self._buffer: list[float] = []
        self._buffer_start = 0
        self._total_input = 0
        self._next_output = 0
        self._closed = False

    def feed(self, samples: list[float]) -> list[float]:
        if self._closed:
            raise ValueError("resampler is closed")
        if any(not math.isfinite(sample) for sample in samples):
            raise ValueError("PCM contains a non-finite sample")
        self._buffer.extend(samples)
        self._total_input += len(samples)
        return self._drain(final=False)

    def finish(self) -> list[float]:
        if self._closed:
            return []
        self._closed = True
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[float]:
        output: list[float] = []
        target = (
            (self._total_input * self.output_rate_hz) // self.input_rate_hz
            if final
            else None
        )
        while True:
            if target is not None and self._next_output >= target:
                break
            numerator = self._next_output * self.input_rate_hz
            left_index = numerator // self.output_rate_hz
            remainder = numerator % self.output_rate_hz
            right_index = left_index + (1 if remainder else 0)
            if right_index >= self._total_input:
                if not final or left_index >= self._total_input:
                    break
                right_index = left_index
                remainder = 0
            left = self._sample(left_index)
            right = self._sample(right_index)
            fraction = remainder / self.output_rate_hz
            output.append(left + ((right - left) * fraction))
            self._next_output += 1
        next_numerator = self._next_output * self.input_rate_hz
        retain_from = max(0, (next_numerator // self.output_rate_hz) - 1)
        drop = min(len(self._buffer), max(0, retain_from - self._buffer_start))
        if drop:
            del self._buffer[:drop]
            self._buffer_start += drop
        return output

    def _sample(self, absolute_index: int) -> float:
        relative = absolute_index - self._buffer_start
        if relative < 0 or relative >= len(self._buffer):
            raise ValueError("resampler state lost an input sample")
        return self._buffer[relative]


class _HttpxSseStream:
    def __init__(self, client: httpx.AsyncClient, response: httpx.Response) -> None:
        self._client = client
        self._response = response

    async def __aiter__(self) -> AsyncIterator[str]:
        async for line in self._response.aiter_lines():
            yield line

    async def aclose(self) -> None:
        await self._response.aclose()
        await self._client.aclose()


async def _default_socket_factory(
    url: str, headers: Mapping[str, str], timeout_seconds: float
) -> RealtimeSocket:
    import websockets

    kwargs: dict[str, object] = {
        "open_timeout": timeout_seconds,
        "close_timeout": min(timeout_seconds, 5.0),
        "max_size": MAX_WIRE_MESSAGE_BYTES,
        "compression": None,
    }
    parameter = (
        "additional_headers"
        if "additional_headers" in inspect.signature(websockets.connect).parameters
        else "extra_headers"
    )
    kwargs[parameter] = dict(headers)
    return await websockets.connect(url, **kwargs)


async def _default_sse_factory(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, str],
    timeout_seconds: float,
) -> SpeechSseStream:
    client = httpx.AsyncClient(follow_redirects=False, timeout=None)
    try:
        request = client.build_request("POST", url, headers=headers, json=dict(payload))
        response = await asyncio.wait_for(
            client.send(request, stream=True), timeout=timeout_seconds
        )
        if response.status_code != 200:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_REQUEST_REJECTED",
                f"speech Provider rejected the request with status {response.status_code}",
            )
        encoding = response.headers.get("content-encoding")
        if encoding is not None and encoding.strip().lower() != "identity":
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_UNSUPPORTED_CONTENT_ENCODING",
                "speech Provider must return an identity-encoded stream",
            )
        media_type = response.headers.get("content-type", "").split(";", 1)[0]
        if media_type.strip().lower() != "text/event-stream":
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_INVALID_CONTENT_TYPE",
                "speech Provider did not return an SSE stream",
            )
        return _HttpxSseStream(client, response)
    except BaseException:
        await client.aclose()
        raise


class OpenAIStreamingSpeechProvider:
    """OpenAI wire Adapter behind the provider-neutral streaming contract."""

    def __init__(
        self,
        config: OpenAIStreamingSpeechConfig,
        *,
        socket_factory: RealtimeSocketFactory | None = None,
        sse_factory: SpeechSseFactory | None = None,
        degradation_sink: DegradationSink | None = None,
        fallback_tier: SpeechRouteTier = SpeechRouteTier.TEXT,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(config, OpenAIStreamingSpeechConfig):
            raise TypeError("config must be OpenAIStreamingSpeechConfig")
        self._config = config
        self._socket_factory = socket_factory or _default_socket_factory
        self._sse_factory = sse_factory or _default_sse_factory
        self._degradation_sink = degradation_sink
        if fallback_tier is not SpeechRouteTier.TEXT:
            raise ValueError(
                "runtime fallback must be text; product wiring owns batch eligibility"
            )
        self._fallback_tier = fallback_tier
        self._degradation_sink_tasks = _DegradationSinkTaskOwner()
        self._transport_cleanup_tasks = _TransportCleanupOwner()
        self._monotonic = monotonic
        self._capability = StreamingProviderCapability(
            provider=_PROVIDER,
            recognition=RecognitionProviderSupport(
                modes=frozenset({SpeechMode.STREAM}),
                transport=ProviderTransport.NATIVE_STREAM,
                ordered_events=CapabilityProvenance.ADAPTER_DERIVED,
                exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
                provider_cancel_ack=CapabilityProvenance.UNAVAILABLE,
                native_partials=CapabilityProvenance.PROVIDER_NATIVE,
                server_vad=CapabilityProvenance.PROVIDER_NATIVE,
            ),
            synthesis=SynthesisProviderSupport(
                modes=frozenset({SpeechMode.STREAM}),
                transport=ProviderTransport.NATIVE_STREAM,
                ordered_events=CapabilityProvenance.TRANSPORT_OBSERVED,
                exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
                provider_cancel_ack=CapabilityProvenance.UNAVAILABLE,
                chunk_text_spans=CapabilityProvenance.UNAVAILABLE,
            ),
        )
        self._conformance = StreamingSpeechConformance(
            self._capability, enabled=True, monotonic=monotonic
        )
        self._recognition: dict[tuple[str, int], _RecognitionSession] = {}
        self._synthesis: dict[tuple[str, int], _SynthesisSession] = {}
        self._degradation_facts: deque[SpeechDegradationFact] = deque(maxlen=128)
        self._opening_recognition_tasks: set[asyncio.Task[object]] = set()
        self._lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._closed = False

    @property
    def capability(self) -> StreamingProviderCapability:
        return self._capability

    @property
    def conformance(self) -> StreamingSpeechConformance:
        return self._conformance

    @property
    def synthesis_model(self) -> str:
        return self._config.tts_model

    @property
    def synthesis_voice(self) -> str | None:
        return self._config.tts_voice

    @property
    def fallback_tier(self) -> SpeechRouteTier:
        return self._fallback_tier

    @property
    def degradation_facts(self) -> tuple[SpeechDegradationFact, ...]:
        return tuple(self._degradation_facts)

    @property
    def cleanup_snapshot(self) -> TransportCleanupSnapshot:
        return self._transport_cleanup_tasks.snapshot()

    async def open_recognition(
        self,
        request: RecognitionStreamRequest | RecognitionStreamRef,
        *,
        timeout_seconds: float,
    ) -> None:
        started_at = self._monotonic()
        self._require_open()
        self._require_cleanup_capacity()
        if isinstance(request, RecognitionStreamRef):
            request = RecognitionStreamRequest(
                request, RecognitionTurnDetection.manual()
            )
        if not isinstance(request, RecognitionStreamRequest):
            raise TypeError("request must be RecognitionStreamRequest")
        ref = request.ref
        _supported_sample_rate(ref.capture.sample_rate_hz)
        socket: RealtimeSocket | None = None
        session: _RecognitionSession | None = None
        failure: BaseException | None = None
        conformance_started = False
        opening_task = asyncio.current_task()
        if opening_task is None:
            raise RuntimeError("recognition open requires an asyncio task")
        self._opening_recognition_tasks.add(opening_task)
        try:
            self._conformance.start_recognition(
                request, timeout_seconds=timeout_seconds
            )
            conformance_started = True
            deadline = started_at + float(timeout_seconds)
            url = _realtime_url(self._config.api_base)
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError("recognition stream timed out before connect")
            connect_budget = min(self._config.connect_timeout_seconds, remaining)
            socket = await self._open_recognition_socket(
                url=url, timeout_seconds=connect_budget
            )
            loop = asyncio.get_running_loop()
            session = _RecognitionSession(
                request=request,
                socket=socket,
                resampler=_StreamingLinearResampler(
                    ref.capture.sample_rate_hz, OPENAI_PCM_RATE_HZ
                ),
                events=asyncio.Queue(MAX_EVENT_QUEUE),
                ready=loop.create_future(),
                deadline=deadline,
            )
            key = _recognition_key(ref)
            async with self._lock:
                if self._closed or key in self._recognition:
                    raise OpenAIStreamingSpeechError(
                        "RECOGNITION_STREAM_CONFLICT",
                        "recognition stream is closed or already active",
                    )
                self._recognition[key] = session
            session.receive_task = asyncio.create_task(
                self._receive_recognition(session),
                name=f"openai-stt-{ref.session_id}-{ref.session_generation}",
            )
            await self._send_recognition_wire(
                session,
                _wire_json(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "transcription",
                            "audio": {
                                "input": {
                                    "format": {
                                        "type": "audio/pcm",
                                        "rate": OPENAI_PCM_RATE_HZ,
                                    },
                                    "transcription": {"model": self._config.stt_model},
                                    "turn_detection": _turn_detection_wire(request),
                                }
                            },
                        },
                    }
                ),
            )
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError("recognition stream timed out before ready")
            await asyncio.wait_for(
                asyncio.shield(session.ready),
                timeout=min(self._config.connect_timeout_seconds, remaining),
            )
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        finally:
            self._opening_recognition_tasks.discard(opening_task)
        if failure is not None:
            await self._rollback_failed_recognition(
                ref,
                session=session,
                socket=socket,
                conformance_started=conformance_started,
            )
            if not _is_process_control(failure) and not isinstance(
                failure, asyncio.CancelledError
            ):
                with suppress(Exception, asyncio.CancelledError):
                    await self._emit_failure(
                        operation="recognition.open",
                        reason=_reason_for_exception(failure),
                        started_at=started_at,
                        identity=f"{ref.session_id}:{ref.session_generation}",
                    )
            socket = None
            session = None
            opening_task = None
            raise failure

    async def send_recognition_audio(self, frame: RecognitionAudioFrame) -> None:
        session: _RecognitionSession | None = None
        samples: list[float] | None = None
        encoded: bytes | None = None
        failure: BaseException | None = None
        try:
            session = self._require_recognition(frame.ref)
            async with session.send_lock:
                if session.input_fenced:
                    # The route consumes the typed STOPPED boundary on its own
                    # task. A frame already queued in that handoff window must
                    # be dropped here, never written after the Provider EOT and
                    # never misclassified as a Provider outage.
                    frame = None  # type: ignore[assignment]
                    session = None
                    return
                if session.committed:
                    raise OpenAIStreamingSpeechError(
                        "RECOGNITION_AUDIO_AFTER_COMMIT",
                        "recognition audio is closed after commit",
                    )
                if session.closing or session.terminal:
                    raise OpenAIStreamingSpeechError(
                        "RECOGNITION_OUTPUT_FENCED", "recognition stream is fenced"
                    )
                self._conformance.accept_audio_frame(frame)
                samples = _decode_f32le(frame.pcm_f32le)
                encoded = _encode_s16le(session.resampler.feed(samples))
                session.source_cursor = frame.sample_cursor + frame.sample_count
                if encoded:
                    try:
                        await self._send_recognition_wire(
                            session,
                            _wire_json(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(encoded).decode("ascii"),
                                }
                            ),
                        )
                    except BaseException as exc:
                        transport_failure = _safe_transport_exception(exc)
                        del exc
                        await self._fail_recognition_transport(
                            session, transport_failure
                        )
                        raise transport_failure
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        frame = None  # type: ignore[assignment]  # clear raw PCM before a safe raise
        session = None
        samples = None
        encoded = None
        if failure is not None:
            raise failure

    async def commit_recognition(
        self, ref: RecognitionStreamRef
    ) -> RecognitionCommitDisposition:
        session: _RecognitionSession | None = None
        tail: bytes | None = None
        failure: BaseException | None = None
        try:
            session = self._require_recognition(ref)
            async with session.send_lock:
                if session.closing or session.terminal:
                    raise OpenAIStreamingSpeechError(
                        "RECOGNITION_COMMIT_CONFLICT",
                        "recognition stream cannot be committed in its current state",
                    )
                if session.commit_owner is _RecognitionCommitOwner.SERVER_VAD:
                    return (
                        RecognitionCommitDisposition.SERVER_VAD_OBSERVED
                        if session.committed
                        else RecognitionCommitDisposition.SERVER_VAD_PENDING
                    )
                if (
                    session.committed
                    or session.commit_owner is not _RecognitionCommitOwner.NONE
                ):
                    raise OpenAIStreamingSpeechError(
                        "RECOGNITION_COMMIT_CONFLICT",
                        "recognition stream already has a commit owner",
                    )
                tail = _encode_s16le(session.resampler.finish())
                try:
                    if tail:
                        await self._send_recognition_wire(
                            session,
                            _wire_json(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(tail).decode("ascii"),
                                }
                            ),
                        )
                    # The Provider transcription events expose item/text identity,
                    # not an audio cursor. Freeze our exact accepted source boundary
                    # before the commit send can yield to an immediate ACK.
                    session.committed_source_cursor = session.source_cursor
                    session.committed = True
                    session.commit_owner = _RecognitionCommitOwner.MANUAL
                    await self._send_recognition_wire(
                        session,
                        _wire_json({"type": "input_audio_buffer.commit"}),
                    )
                except BaseException as exc:
                    transport_failure = _safe_transport_exception(exc)
                    del exc
                    await self._fail_recognition_transport(session, transport_failure)
                    raise transport_failure
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        session = None
        tail = None
        if failure is not None:
            raise failure
        return RecognitionCommitDisposition.CLIENT_COMMIT_SENT

    async def next_recognition_event(
        self, ref: RecognitionStreamRef, *, timeout_seconds: float
    ) -> StreamingRecognitionOutput:
        session = self._require_recognition(ref)
        event = await asyncio.wait_for(session.events.get(), timeout=timeout_seconds)
        if event.kind in {RecognitionEventKind.FINAL, RecognitionEventKind.CANCELLED}:
            await self._retire_recognition(session)
        return event

    async def cancel_recognition(
        self, ref: RecognitionStreamRef, *, reason: str = "caller_cancel"
    ) -> None:
        session = self._require_recognition(ref)
        self._conformance.request_recognition_cancel(ref, reason=reason)
        session.closing = True
        await self._close_socket(session.socket)
        if session.receive_task is not None:
            await self._transport_cleanup_tasks.cancel_task(
                session.receive_task, kind="recognition-worker"
            )
        self._conformance.provider_closed_recognition(ref)
        session.terminal = True
        await self._retire_recognition(session)
        await self._emit_failure(
            operation="recognition.cancel",
            reason=SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED,
            started_at=None,
            identity=f"{ref.session_id}:{ref.session_generation}",
        )

    async def open_synthesis(self, request: SynthesisStreamRequest) -> None:
        session: _SynthesisSession | None = None
        failure: BaseException | None = None
        conformance_started = False
        try:
            self._require_open()
            self._require_cleanup_capacity()
            _supported_sample_rate(request.sample_rate_hz)
            self._conformance.start_synthesis(request)
            conformance_started = True
            key = _synthesis_key(request.ref)
            session = _SynthesisSession(
                request=request,
                events=asyncio.Queue(MAX_EVENT_QUEUE),
                resampler=_StreamingLinearResampler(
                    OPENAI_PCM_RATE_HZ, request.sample_rate_hz
                ),
            )
            async with self._lock:
                if self._closed or key in self._synthesis:
                    raise OpenAIStreamingSpeechError(
                        "SYNTHESIS_STREAM_CONFLICT",
                        "synthesis stream is closed or already active",
                    )
                self._synthesis[key] = session
            session.task = asyncio.create_task(
                self._run_synthesis(session),
                name=(
                    f"openai-tts-{request.ref.stream_id}-{request.ref.stream_generation}"
                ),
            )
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        if failure is not None:
            await self._rollback_failed_synthesis(
                request.ref,
                session=session,
                conformance_started=conformance_started,
            )
        request = None  # type: ignore[assignment]  # clear spoken text before raise
        session = None
        if failure is not None:
            raise failure

    async def next_synthesis_event(
        self, ref: SynthesisStreamRef, *, timeout_seconds: float
    ) -> StreamingSynthesisEvent:
        session = self._require_synthesis(ref)
        event = await asyncio.wait_for(session.events.get(), timeout=timeout_seconds)
        if event.kind in {SynthesisEventKind.COMPLETED, SynthesisEventKind.CANCELLED}:
            await self._retire_synthesis(session)
        return event

    async def cancel_synthesis(
        self, ref: SynthesisStreamRef, *, reason: str = "caller_cancel"
    ) -> None:
        session = self._require_synthesis(ref)
        self._conformance.request_synthesis_cancel(ref, reason=reason)
        session.closing = True
        if session.stream is not None:
            await self._close_stream(session.stream)
        if session.task is not None:
            await self._transport_cleanup_tasks.cancel_task(
                session.task, kind="synthesis-worker"
            )
        self._conformance.provider_closed_synthesis(ref)
        session.terminal = True
        await self._retire_synthesis(session)
        await self._emit_failure(
            operation="synthesis.cancel",
            reason=SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED,
            started_at=None,
            identity=f"{ref.stream_id}:{ref.stream_generation}",
        )

    async def close(self) -> None:
        async with self._close_lock:
            await self._close_serialized()

    async def _close_serialized(self) -> None:
        process_control: BaseException | None = None
        cleanup_failure: BaseException | None = None
        if not self._closed:
            self._closed = True
            self._conformance.close()
        opening_tasks = tuple(
            task
            for task in self._opening_recognition_tasks
            if task is not asyncio.current_task()
        )
        if opening_tasks:
            results = await asyncio.gather(
                *(
                    _settle_close_action(
                        self._transport_cleanup_tasks.cancel_task(
                            opening_task, kind="recognition-open-worker"
                        )
                    )
                    for opening_task in opening_tasks
                ),
                return_exceptions=True,
            )
            process_control = _first_process_control(process_control, results)
        recognition = tuple(
            recognition_session
            for recognition_session in self._recognition.values()
            if not recognition_session.terminal
        )
        synthesis = tuple(
            synthesis_session
            for synthesis_session in self._synthesis.values()
            if not synthesis_session.terminal
        )
        for recognition_session in recognition:
            recognition_session.closing = True
        for synthesis_session in synthesis:
            synthesis_session.closing = True
        results = await asyncio.gather(
            *(
                _settle_close_action(self._close_socket(recognition_session.socket))
                for recognition_session in recognition
            ),
            *(
                _settle_close_action(self._close_stream(synthesis_session.stream))
                for synthesis_session in synthesis
                if synthesis_session.stream is not None
            ),
            return_exceptions=True,
        )
        process_control = _first_process_control(process_control, results)
        tasks = tuple(
            task
            for task in (
                *(
                    recognition_session.receive_task
                    for recognition_session in recognition
                ),
                *(synthesis_session.task for synthesis_session in synthesis),
            )
            if task is not None
        )
        if tasks:
            results = await asyncio.gather(
                *(
                    _settle_close_action(
                        self._transport_cleanup_tasks.cancel_task(
                            task, kind="stream-worker"
                        )
                    )
                    for task in tasks
                ),
                return_exceptions=True,
            )
            process_control = _first_process_control(process_control, results)
        for recognition_session in recognition:
            with suppress(StreamingSpeechViolation):
                self._conformance.provider_closed_recognition(recognition_session.ref)
            recognition_session.terminal = True
        for synthesis_session in synthesis:
            with suppress(StreamingSpeechViolation):
                self._conformance.provider_closed_synthesis(
                    synthesis_session.request.ref
                )
            synthesis_session.terminal = True
        self._conformance.reap_terminal()
        self._recognition.clear()
        self._synthesis.clear()
        try:
            await self._finalize_cleanup_owners()
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
            if _is_process_control(failure):
                process_control = process_control or failure
            elif isinstance(failure, asyncio.CancelledError):
                raise failure from None
            else:
                cleanup_failure = failure
        opening_tasks = ()
        recognition = ()
        synthesis = ()
        tasks = ()
        if process_control is not None:
            raise process_control from None
        if cleanup_failure is not None:
            raise cleanup_failure from None

    async def _receive_recognition(self, session: _RecognitionSession) -> None:
        failure: BaseException | None = None
        raw: str | bytes | None = None
        try:
            while not session.closing and not session.terminal:
                remaining = session.deadline - self._monotonic()
                if remaining <= 0:
                    raise TimeoutError("recognition stream timed out")
                # Keep receive and cancellation in the owned worker Task.  A
                # nested wait_for Task can surface a transport process-control
                # exception after its parent is cancelled, leaving the actual
                # failure unobserved and outside the cleanup owner.
                async with asyncio.timeout(remaining):
                    raw = await session.socket.recv()
                terminal = await self._consume_recognition_message(session, raw)
                raw = None
                if terminal:
                    return
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        finally:
            raw = None
        if isinstance(failure, asyncio.CancelledError):
            await self._close_socket(session.socket)
            raise failure
        if failure is not None and _is_process_control(failure):
            if not session.ready.done():
                session.ready.set_exception(failure)
            if not session.terminal:
                with suppress(StreamingSpeechViolation):
                    self._conformance.provider_closed_recognition(session.ref)
                session.terminal = True
            await self._close_socket(session.socket)
            await self._retire_recognition(session)
            raise failure
        if failure is not None:
            ready_before_failure = session.ready.done()
            if not ready_before_failure:
                session.ready.set_exception(failure)
            if not session.closing:
                if isinstance(failure, (TimeoutError, asyncio.TimeoutError)):
                    self._conformance.expire()
                self._conformance.provider_closed_recognition(session.ref)
                session.terminal = True
                await self._retire_recognition(session)
                if ready_before_failure:
                    await self._emit_failure(
                        operation="recognition.stream",
                        reason=_reason_for_exception(failure),
                        started_at=None,
                        identity=(
                            f"{session.ref.session_id}:{session.ref.session_generation}"
                        ),
                    )
                await self._close_socket(session.socket)
        await self._close_socket(session.socket)

    async def _consume_recognition_message(
        self, session: _RecognitionSession, raw: str | bytes
    ) -> bool:
        if type(raw) is not str:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_BINARY_CONTROL",
                "recognition Provider returned a binary control message",
            )
        if len(raw.encode("utf-8")) > MAX_WIRE_MESSAGE_BYTES:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_MESSAGE_LIMIT",
                "recognition Provider message exceeds the limit",
            )
        event = _json_object(raw)
        kind = event.get("type")
        if kind in {"session.updated", "transcription_session.updated"}:
            _validate_transcription_session(
                event,
                expected_model=self._config.stt_model,
                expected_turn_detection=session.request.turn_detection,
            )
            if not session.ready.done():
                session.ready.set_result(None)
            return False
        if kind == "input_audio_buffer.speech_started":
            if (
                session.request.turn_detection.mode
                is not RecognitionTurnDetectionMode.SERVER_VAD
                or session.speech_item_id is not None
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TURN_ORDER",
                    "speech_started was unnegotiated or duplicated",
                )
            item_id = _safe_label(event.get("item_id"), "item_id")
            start_ms = _provider_milliseconds(
                event.get("audio_start_ms"), "audio_start_ms"
            )
            session.speech_item_id = item_id
            session.speech_start_ms = start_ms
            await self._publish_recognition_boundary(
                session,
                RecognitionTurnBoundaryKind.SPEECH_STARTED,
                item_id,
                provider_start_ms=start_ms,
            )
            return False
        if kind == "input_audio_buffer.speech_stopped":
            item_id = _safe_label(event.get("item_id"), "item_id")
            end_ms = _provider_milliseconds(event.get("audio_end_ms"), "audio_end_ms")
            async with session.send_lock:
                if (
                    session.request.turn_detection.mode
                    is not RecognitionTurnDetectionMode.SERVER_VAD
                    or session.speech_item_id is None
                    or session.speech_end_ms is not None
                    or item_id != session.speech_item_id
                    or session.speech_start_ms is None
                    or end_ms < session.speech_start_ms
                ):
                    raise OpenAIStreamingSpeechError(
                        "SPEECH_PROVIDER_TURN_ORDER",
                        "speech_stopped did not close the observed speech item",
                    )
                # Serialize the input fence with the only socket-send owner.
                # Once this boundary is published, no later audio append can
                # cross the observed EOT.
                session.speech_end_ms = end_ms
                session.input_fenced = True
                if session.commit_owner is _RecognitionCommitOwner.NONE:
                    session.commit_owner = _RecognitionCommitOwner.SERVER_VAD
            await self._publish_recognition_boundary(
                session,
                RecognitionTurnBoundaryKind.SPEECH_STOPPED,
                item_id,
                provider_end_ms=end_ms,
            )
            return False
        if kind == "input_audio_buffer.committed":
            item_id = _safe_label(event.get("item_id"), "item_id")
            if session.commit_owner is _RecognitionCommitOwner.SERVER_VAD:
                if (
                    session.speech_end_ms is None
                    or session.committed
                    or item_id != session.speech_item_id
                ):
                    raise OpenAIStreamingSpeechError(
                        "SPEECH_PROVIDER_TURN_ORDER",
                        "server VAD commit did not match the stopped speech item",
                    )
                session.committed = True
                session.committed_source_cursor = None
                self._bind_item(session, item_id)
                await self._publish_recognition_boundary(
                    session,
                    RecognitionTurnBoundaryKind.COMMITTED,
                    item_id,
                )
                return False
            self._require_committed(session)
            self._bind_item(session, item_id)
            return False
        if kind == "conversation.item.input_audio_transcription.delta":
            _require_primary_audio_content(event)
            self._bind_item(session, event.get("item_id"))
            delta = _provider_text(event.get("delta"), "delta")
            if len(session.partial_text) + len(delta) > 16_000:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_INVALID_TEXT",
                    "cumulative recognition partial text exceeds the limit",
                )
            session.partial_text += delta
            await self._publish_recognition(
                session,
                RecognitionEventKind.PARTIAL,
                session.partial_text,
            )
            return False
        if kind == "conversation.item.input_audio_transcription.completed":
            _require_primary_audio_content(event)
            self._require_committed(session)
            self._bind_item(session, event.get("item_id"))
            transcript = _provider_text(event.get("transcript"), "transcript")
            await self._close_socket(session.socket)
            await self._publish_recognition(
                session, RecognitionEventKind.FINAL, transcript
            )
            session.terminal = True
            return True
        if kind in {
            "conversation.item.input_audio_transcription.failed",
            "error",
        }:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_RECOGNITION_FAILED",
                "recognition Provider reported a failure",
            )
        if kind in {
            "session.created",
            "transcription_session.created",
            # ``conversation.item.created`` is the retired beta name. The GA
            # transcription session announces the committed item as ``added``
            # and then ``done``; both carry their id under ``item.id`` rather
            # than a top-level ``item_id``, and the committed identity this
            # stream binds already came from ``input_audio_buffer.committed``.
            "conversation.item.created",
            "conversation.item.added",
            "conversation.item.done",
            "rate_limits.updated",
        }:
            # These observations don't alter Speech output truth.
            return False
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_UNKNOWN_EVENT",
            "recognition Provider returned an unknown event",
        )

    async def _publish_recognition(
        self,
        session: _RecognitionSession,
        kind: RecognitionEventKind,
        text: str,
    ) -> None:
        if session.closing or session.terminal:
            return
        hypothesis = RecognitionHypothesis(
            (RecognitionAlternative(text, text, None),), selected_index=0
        )
        event = StreamingRecognitionEvent(
            ref=session.ref,
            provider=_PROVIDER,
            seq=session.event_seq,
            audio_cursor=self._recognition_event_cursor(session, kind),
            kind=kind,
            hypothesis=hypothesis,
            timing_basis=(
                RecognitionTimingBasis.PROVIDER_TIME
                if session.commit_owner is _RecognitionCommitOwner.SERVER_VAD
                else RecognitionTimingBasis.EXACT_SOURCE_CURSOR
            ),
        )
        try:
            accepted = self._conformance.accept_recognition_event(event)
        except StreamingSpeechViolation:
            if session.closing:
                return
            raise
        session.event_seq += 1
        await self._put_bounded(session.events, accepted)

    async def _publish_recognition_boundary(
        self,
        session: _RecognitionSession,
        kind: RecognitionTurnBoundaryKind,
        provider_item_id: str,
        *,
        provider_start_ms: int | None = None,
        provider_end_ms: int | None = None,
    ) -> None:
        if session.closing or session.terminal:
            return
        event = RecognitionTurnBoundaryEvent(
            ref=session.ref,
            provider=_PROVIDER,
            seq=session.event_seq,
            kind=kind,
            provider_item_id=provider_item_id,
            provider_start_ms=provider_start_ms,
            provider_end_ms=provider_end_ms,
        )
        accepted = self._conformance.accept_recognition_boundary(event)
        session.event_seq += 1
        await self._put_bounded(session.events, accepted)

    async def _run_synthesis(self, session: _SynthesisSession) -> None:
        started_at = self._monotonic()
        failure: BaseException | None = None
        tail: bytes | None = None
        try:
            async with asyncio.timeout(session.request.timeout_seconds):
                session.stream = await self._open_synthesis_stream(session)
                await self._publish_synthesis(session, SynthesisEventKind.STARTED)
                done = await self._consume_synthesis_stream(session)
                if not done:
                    raise OpenAIStreamingSpeechError(
                        "SPEECH_PROVIDER_TTS_INCOMPLETE",
                        "speech Provider closed without a done event",
                    )
                tail = _encode_s16le(session.resampler.finish())
                if tail:
                    await self._publish_synthesis(
                        session, SynthesisEventKind.CHUNK, pcm=tail
                    )
                if session.stream is not None:
                    await self._close_stream(session.stream)
                await self._publish_synthesis(session, SynthesisEventKind.COMPLETED)
                session.terminal = True
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        tail = None
        if isinstance(failure, asyncio.CancelledError):
            if session.stream is not None:
                await self._close_stream(session.stream)
            raise failure
        if failure is not None and _is_process_control(failure):
            if session.stream is not None:
                await self._close_stream(session.stream)
            if not session.terminal:
                with suppress(StreamingSpeechViolation):
                    self._conformance.provider_closed_synthesis(session.request.ref)
                session.terminal = True
            await self._retire_synthesis(session)
            raise failure
        if failure is not None and not session.closing:
            if isinstance(failure, (TimeoutError, asyncio.TimeoutError)):
                self._conformance.expire()
            self._conformance.provider_closed_synthesis(session.request.ref)
            session.terminal = True
            await self._retire_synthesis(session)
            await self._emit_failure(
                operation="synthesis.stream",
                reason=_reason_for_exception(failure),
                started_at=started_at,
                identity=(
                    f"{session.request.ref.stream_id}:"
                    f"{session.request.ref.stream_generation}"
                ),
            )
            if session.stream is not None:
                await self._close_stream(session.stream)

    async def _open_synthesis_stream(
        self, session: _SynthesisSession
    ) -> SpeechSseStream:
        headers: Mapping[str, str] = {
            "Accept": "text/event-stream",
            "Accept-Encoding": "identity",
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        payload: Mapping[str, str] = {
            "model": self._config.tts_model,
            "voice": self._config.tts_voice,
            "input": session.request.spoken_text,
            "response_format": "pcm",
            "stream_format": "sse",
        }
        failure: BaseException | None = None
        stream: SpeechSseStream | None = None
        try:
            stream = await self._sse_factory(
                f"{self._config.api_base}/audio/speech",
                headers,
                payload,
                self._config.connect_timeout_seconds,
            )
        except BaseException as exc:
            failure = _safe_transport_exception(exc)
        headers = {}
        payload = {}
        session = None  # type: ignore[assignment]  # clear spoken text before raise
        if failure is not None:
            raise failure
        if stream is None:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                "synthesis Provider transport is unavailable",
            )
        return stream

    async def _consume_synthesis_stream(self, session: _SynthesisSession) -> bool:
        if session.stream is None:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                "synthesis Provider transport is unavailable",
            )
        data_lines: list[str] = []
        data_bytes = 0
        done = False
        async for line in session.stream:
            if session.closing:
                return False
            if len(line.encode("utf-8")) > MAX_SSE_LINE_BYTES:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_SSE_LINE_LIMIT",
                    "speech Provider SSE line exceeds the limit",
                )
            if line == "":
                if data_lines:
                    done = await self._consume_sse_event(session, "\n".join(data_lines))
                    data_lines.clear()
                    data_bytes = 0
                    if done:
                        break
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_line = line[5:].lstrip(" ")
                data_bytes += len(data_line.encode("utf-8"))
                if data_bytes > MAX_SSE_EVENT_BYTES:
                    raise OpenAIStreamingSpeechError(
                        "SPEECH_PROVIDER_SSE_EVENT_LIMIT",
                        "speech Provider SSE event exceeds the limit",
                    )
                data_lines.append(data_line)
        if data_lines and not done:
            done = await self._consume_sse_event(session, "\n".join(data_lines))
        return done

    async def _consume_sse_event(self, session: _SynthesisSession, data: str) -> bool:
        event = _json_object(data)
        kind = event.get("type")
        if kind == "speech.audio.delta":
            encoded = event.get("audio")
            if not isinstance(encoded, str) or not encoded:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_INVALID_AUDIO",
                    "speech Provider returned invalid audio",
                )
            try:
                pcm = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_INVALID_AUDIO",
                    "speech Provider returned invalid audio",
                ) from exc
            session.wire_audio_bytes += len(pcm)
            if (
                session.wire_audio_bytes > MAX_STREAM_AUDIO_BYTES
                or len(pcm) > MAX_PROVIDER_AUDIO_DELTA_BYTES
                or len(pcm) % 2
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_AUDIO_LIMIT",
                    "speech Provider audio is invalid or exceeds the limit",
                )
            output = _encode_s16le(session.resampler.feed(_decode_s16le(pcm)))
            frame_bytes = MAX_AUDIO_SAMPLES_PER_FRAME * 2
            for offset in range(0, len(output), frame_bytes):
                await self._publish_synthesis(
                    session,
                    SynthesisEventKind.CHUNK,
                    pcm=output[offset : offset + frame_bytes],
                )
            return False
        if kind == "speech.audio.done":
            return True
        if kind == "error":
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_SYNTHESIS_FAILED",
                "speech Provider reported a synthesis failure",
            )
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_UNKNOWN_SSE_EVENT",
            "speech Provider returned an unknown SSE event",
        )

    async def _publish_synthesis(
        self,
        session: _SynthesisSession,
        kind: SynthesisEventKind,
        *,
        pcm: bytes | None = None,
    ) -> None:
        if session.closing or session.terminal:
            return
        sample_count = 0 if pcm is None else len(pcm) // 2
        event = StreamingSynthesisEvent(
            ref=session.request.ref,
            provider=_PROVIDER,
            seq=session.event_seq,
            sample_cursor=session.audio_cursor,
            kind=kind,
            sample_rate_hz=session.request.sample_rate_hz,
            sample_count=sample_count,
            pcm_s16le=pcm,
            display_span=None,
            spoken_span=None,
        )
        try:
            accepted = self._conformance.accept_synthesis_event(event)
        except StreamingSpeechViolation:
            if session.closing:
                return
            raise
        session.event_seq += 1
        session.audio_cursor += sample_count
        await self._put_bounded(session.events, accepted)

    @staticmethod
    async def _put_bounded(
        queue: asyncio.Queue[_QueueValue], value: _QueueValue
    ) -> None:
        try:
            queue.put_nowait(value)
        except asyncio.QueueFull as exc:
            raise OpenAIStreamingSpeechError(
                "SPEECH_EVENT_QUEUE_EXHAUSTED",
                "streaming Speech event queue is exhausted",
            ) from exc

    @staticmethod
    def _require_committed(session: _RecognitionSession) -> None:
        if not session.committed:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_PRECOMMIT_OUTPUT",
                "recognition Provider emitted text before the requested commit",
            )

    @staticmethod
    def _committed_cursor(session: _RecognitionSession) -> int:
        OpenAIStreamingSpeechProvider._require_committed(session)
        if session.committed_source_cursor is None:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_CURSOR_UNAVAILABLE",
                "server VAD does not provide an exact source cursor",
            )
        return session.committed_source_cursor

    @staticmethod
    def _recognition_event_cursor(
        session: _RecognitionSession, kind: RecognitionEventKind
    ) -> int | None:
        if session.commit_owner is _RecognitionCommitOwner.SERVER_VAD:
            OpenAIStreamingSpeechProvider._require_committed(session)
            return None
        if kind is RecognitionEventKind.FINAL:
            return OpenAIStreamingSpeechProvider._committed_cursor(session)
        if session.committed_source_cursor is not None:
            return session.committed_source_cursor
        return session.source_cursor

    @staticmethod
    def _bind_item(session: _RecognitionSession, value: object) -> None:
        item_id = _safe_label(value, "item_id")
        if session.item_id is None:
            session.item_id = item_id
        elif session.item_id != item_id:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_ITEM_MISMATCH",
                "recognition events changed their committed item identity",
            )

    async def _rollback_failed_recognition(
        self,
        ref: RecognitionStreamRef,
        *,
        session: _RecognitionSession | None,
        socket: RealtimeSocket | None,
        conformance_started: bool,
    ) -> None:
        if session is not None:
            session.closing = True
            await self._close_socket(session.socket)
            if session.receive_task is not None:
                await self._transport_cleanup_tasks.cancel_task(
                    session.receive_task, kind="recognition-worker"
                )
            session.terminal = True
            key = _recognition_key(ref)
            async with self._lock:
                if self._recognition.get(key) is session:
                    del self._recognition[key]
        elif socket is not None:
            await self._close_socket(socket)
        if conformance_started:
            with suppress(StreamingSpeechViolation):
                self._conformance.provider_closed_recognition(ref)
            self._conformance.reap_terminal()

    async def _rollback_failed_synthesis(
        self,
        ref: SynthesisStreamRef,
        *,
        session: _SynthesisSession | None,
        conformance_started: bool,
    ) -> None:
        if session is not None:
            session.closing = True
            if session.stream is not None:
                await self._close_stream(session.stream)
            if session.task is not None:
                await self._transport_cleanup_tasks.cancel_task(
                    session.task, kind="synthesis-worker"
                )
            session.terminal = True
            key = _synthesis_key(ref)
            async with self._lock:
                if self._synthesis.get(key) is session:
                    del self._synthesis[key]
        if conformance_started:
            with suppress(StreamingSpeechViolation):
                self._conformance.provider_closed_synthesis(ref)
            self._conformance.reap_terminal()

    async def _fail_recognition_transport(
        self, session: _RecognitionSession, exc: BaseException
    ) -> None:
        if session.terminal or session.closing:
            return
        session.closing = True
        await self._close_socket(session.socket)
        if session.receive_task is not None:
            await self._transport_cleanup_tasks.cancel_task(
                session.receive_task, kind="recognition-worker"
            )
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            self._conformance.expire()
        self._conformance.provider_closed_recognition(session.ref)
        session.terminal = True
        await self._retire_recognition(session)
        if _is_process_control(exc):
            raise exc
        await self._emit_failure(
            operation="recognition.stream",
            reason=_reason_for_exception(exc),
            started_at=None,
            identity=f"{session.ref.session_id}:{session.ref.session_generation}",
        )

    async def _open_recognition_socket(
        self, *, url: str, timeout_seconds: float
    ) -> RealtimeSocket:
        headers: Mapping[str, str] = {"Authorization": f"Bearer {self._config.api_key}"}
        failure: BaseException | None = None
        socket: RealtimeSocket | None = None
        try:
            socket = await asyncio.wait_for(
                self._socket_factory(url, headers, timeout_seconds),
                timeout=timeout_seconds,
            )
        except BaseException as exc:
            failure = _safe_transport_exception(exc)
        headers = {}
        if failure is not None:
            raise failure
        if socket is None:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                "recognition Provider transport is unavailable",
            )
        return socket

    async def _send_recognition_wire(
        self, session: _RecognitionSession, message: str
    ) -> None:
        remaining = session.deadline - self._monotonic()
        if remaining <= 0:
            raise TimeoutError("recognition stream timed out before send")
        await asyncio.wait_for(session.socket.send(message), timeout=remaining)

    async def _retire_recognition(self, session: _RecognitionSession) -> None:
        key = _recognition_key(session.ref)
        async with self._lock:
            if self._recognition.get(key) is session:
                del self._recognition[key]
        self._conformance.reap_terminal()

    async def _retire_synthesis(self, session: _SynthesisSession) -> None:
        key = _synthesis_key(session.request.ref)
        async with self._lock:
            if self._synthesis.get(key) is session:
                del self._synthesis[key]
        self._conformance.reap_terminal()

    async def _emit_failure(
        self,
        *,
        operation: str,
        reason: SpeechDegradationReason,
        started_at: float | None,
        identity: str,
    ) -> SpeechDegradationFact:
        latency_ms = None
        if started_at is not None:
            latency_ms = max(0, int((self._monotonic() - started_at) * 1000))
        fact = _degradation_fact(
            operation=operation,
            reason=reason,
            from_tier=SpeechRouteTier.STREAMING,
            to_tier=SpeechRouteTier.TEXT,
            provider_id=_PROVIDER.provider_id,
            latency_ms=latency_ms,
            identity=identity,
        )
        self._degradation_facts.append(fact)
        await self._degradation_sink_tasks.publish(fact, self._degradation_sink)
        return fact

    async def _close_socket(self, socket: RealtimeSocket) -> bool:
        return await self._transport_cleanup_tasks.attempt(
            kind="socket", resource=socket, cleanup=socket.close
        )

    async def _close_stream(self, stream: SpeechSseStream) -> bool:
        return await self._transport_cleanup_tasks.attempt(
            kind="sse-stream", resource=stream, cleanup=stream.aclose
        )

    async def _finalize_cleanup_owners(self) -> None:
        failure: BaseException | None = None
        cleanup_snapshot = self._transport_cleanup_tasks.snapshot()
        try:
            cleanup_snapshot = await self._transport_cleanup_tasks.close()
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        try:
            await self._degradation_sink_tasks.close()
        except BaseException as exc:
            if failure is None:
                failure = _safe_boundary_exception(exc)
        if failure is not None:
            raise failure from None
        if not cleanup_snapshot.clean:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_CLEANUP_INCOMPLETE",
                "streaming Speech Provider closed with retained cleanup",
            )

    def _require_open(self) -> None:
        if self._closed:
            raise OpenAIStreamingSpeechError(
                "STREAMING_SPEECH_CLOSED", "streaming Speech Provider is closed"
            )

    def _require_cleanup_capacity(self) -> None:
        snapshot = self._conformance.snapshot()
        self._transport_cleanup_tasks.require_session_capacity(
            active_sessions=snapshot.active_recognition + snapshot.active_synthesis
        )

    def _require_recognition(self, ref: RecognitionStreamRef) -> _RecognitionSession:
        session = self._recognition.get(_recognition_key(ref))
        if session is None or session.ref != ref:
            raise OpenAIStreamingSpeechError(
                "RECOGNITION_STREAM_NOT_FOUND",
                "recognition stream is absent or stale",
            )
        return session

    def _require_synthesis(self, ref: SynthesisStreamRef) -> _SynthesisSession:
        session = self._synthesis.get(_synthesis_key(ref))
        if session is None or session.request.ref != ref:
            raise OpenAIStreamingSpeechError(
                "SYNTHESIS_STREAM_NOT_FOUND", "synthesis stream is absent or stale"
            )
        return session


async def select_environment_streaming_speech(
    *,
    environ: Mapping[str, str] | None = None,
    batch_available: bool,
    socket_factory: RealtimeSocketFactory | None = None,
    sse_factory: SpeechSseFactory | None = None,
    degradation_sink: DegradationSink | None = None,
) -> StreamingSpeechSelection:
    """Select streaming, batch, or text with one explicit degradation fact."""

    if type(batch_available) is not bool:
        raise TypeError("batch_available must be a boolean")
    env = os.environ if environ is None else environ
    target = SpeechRouteTier.BATCH if batch_available else SpeechRouteTier.TEXT
    if not _enabled(env.get(STREAMING_SPEECH_FLAG)):
        fact = _degradation_fact(
            operation="speech.route.select",
            reason=SpeechDegradationReason.FEATURE_OFF,
            from_tier=SpeechRouteTier.STREAMING,
            to_tier=target,
            provider_id=_PROVIDER.provider_id,
            latency_ms=None,
            identity="feature-off",
        )
        await _publish_fact(fact, degradation_sink)
        return StreamingSpeechSelection(target, None, fact)
    provider_name = str(env.get(SPEECH_PROVIDER_ENV) or "").strip().lower()
    api_base = str(env.get(SPEECH_API_BASE_ENV) or "").strip()
    api_key = str(env.get(SPEECH_API_KEY_ENV) or "").strip()
    if provider_name != "openai" or not api_base or not api_key:
        return await _configuration_fallback(target, degradation_sink)
    try:
        config = OpenAIStreamingSpeechConfig(
            api_base=api_base,
            api_key=api_key,
            stt_model=(
                str(env.get(SPEECH_STT_MODEL_ENV) or "").strip() or DEFAULT_STT_MODEL
            ),
            tts_model=(
                str(env.get(SPEECH_TTS_MODEL_ENV) or "").strip() or DEFAULT_TTS_MODEL
            ),
            tts_voice=(
                str(env.get(SPEECH_TTS_VOICE_ENV) or "").strip() or DEFAULT_TTS_VOICE
            ),
        )
    except (OpenAIStreamingSpeechError, TypeError, ValueError):
        return await _configuration_fallback(target, degradation_sink)
    provider = OpenAIStreamingSpeechProvider(
        config,
        socket_factory=socket_factory,
        sse_factory=sse_factory,
        degradation_sink=degradation_sink,
    )
    return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)


async def _configuration_fallback(
    target: SpeechRouteTier, sink: DegradationSink | None
) -> StreamingSpeechSelection:
    fact = _degradation_fact(
        operation="speech.route.select",
        reason=SpeechDegradationReason.CONFIGURATION_UNAVAILABLE,
        from_tier=SpeechRouteTier.STREAMING,
        to_tier=target,
        provider_id=_PROVIDER.provider_id,
        latency_ms=None,
        identity="configuration-unavailable",
    )
    await _publish_fact(fact, sink)
    return StreamingSpeechSelection(target, None, fact)


def _degradation_fact(
    *,
    operation: str,
    reason: SpeechDegradationReason,
    from_tier: SpeechRouteTier,
    to_tier: SpeechRouteTier,
    provider_id: str,
    latency_ms: int | None,
    identity: str,
) -> SpeechDegradationFact:
    material = "\x1f".join(
        (operation, reason.value, from_tier.value, to_tier.value, provider_id, identity)
    ).encode("utf-8")
    return SpeechDegradationFact(
        binding_ref=f"sha256:{hashlib.sha256(material).hexdigest()}",
        operation=operation,
        reason=reason,
        from_tier=from_tier,
        to_tier=to_tier,
        provider_id=provider_id,
        visible=True,
        latency_ms=latency_ms,
    )


async def _publish_fact(
    fact: SpeechDegradationFact, sink: DegradationSink | None
) -> None:
    await _SELECTOR_DEGRADATION_SINK_TASKS.publish(fact, sink)


async def _await_sink(result: Awaitable[object]) -> _SinkOutcome:
    try:
        await result
    except BaseException as exc:
        failure = _safe_boundary_exception(exc)
        if _is_process_control(failure):
            return _SinkOutcome(False, failure)
        if isinstance(failure, asyncio.CancelledError):
            raise failure
        return _SinkOutcome(False)
    return _SinkOutcome(True)


async def _await_cleanup(
    cleanup: Callable[[], Awaitable[None]] | None,
) -> _CleanupOutcome:
    if cleanup is None:
        return _CleanupOutcome(False)
    try:
        await cleanup()
    except BaseException as exc:
        failure = _safe_boundary_exception(exc)
        if _is_process_control(failure):
            return _CleanupOutcome(False, failure)
        if isinstance(failure, asyncio.CancelledError):
            raise failure
        return _CleanupOutcome(False)
    return _CleanupOutcome(True)


async def _await_cancelled_task(task: asyncio.Task[Any]) -> _CleanupOutcome:
    try:
        await task
    except BaseException as exc:
        failure = _safe_boundary_exception(exc)
        if _is_process_control(failure):
            return _CleanupOutcome(False, failure)
        if isinstance(failure, asyncio.CancelledError):
            return _CleanupOutcome(True)
        return _CleanupOutcome(True)
    return _CleanupOutcome(True)


def _discard_sink_awaitable(result: Awaitable[object]) -> None:
    if isinstance(result, asyncio.Future):
        result.cancel()
        return
    close = getattr(result, "close", None)
    if callable(close):
        with suppress(Exception):
            close()


def _prune_global_sink_tasks() -> None:
    for task in tuple(_DEGRADATION_SINK_TASKS):
        if task.done():
            _DEGRADATION_SINK_TASKS.discard(task)


def _log_sink_unavailable(fact: SpeechDegradationFact, *, reason: str) -> None:
    # Only the stable binding and closed category are logged.  The optional
    # consumer's exception/message may itself contain private Provider data.
    _LOGGER.error(
        "live_voice_speech_degradation_sink_unavailable binding_ref=%s reason=%s",
        fact.binding_ref,
        reason,
    )


def _log_transport_cleanup(*, kind: str, reason: str, retained_count: int) -> None:
    _LOGGER.error(
        "live_voice_speech_transport_cleanup_incomplete "
        "kind=%s reason=%s retained_count=%d",
        kind,
        reason,
        retained_count,
    )


def _safe_transport_exception(exc: BaseException) -> BaseException:
    """Discard an untrusted transport exception and all of its local frames."""

    if isinstance(exc, KeyboardInterrupt):
        return KeyboardInterrupt()
    if isinstance(exc, SystemExit):
        return SystemExit()
    if isinstance(exc, GeneratorExit):
        return GeneratorExit()
    if isinstance(exc, asyncio.CancelledError):
        return asyncio.CancelledError()
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        return TimeoutError("streaming Speech Provider timed out")
    return OpenAIStreamingSpeechError(
        "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
        "streaming Speech Provider transport is unavailable",
    )


def _safe_boundary_exception(exc: BaseException) -> BaseException:
    """Rebuild a content-free exception without retaining the original chain."""

    if isinstance(exc, KeyboardInterrupt):
        return KeyboardInterrupt()
    if isinstance(exc, SystemExit):
        return SystemExit()
    if isinstance(exc, GeneratorExit):
        return GeneratorExit()
    if isinstance(exc, asyncio.CancelledError):
        return asyncio.CancelledError()
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        return TimeoutError("streaming Speech Provider timed out")
    if isinstance(exc, OpenAIStreamingSpeechError):
        return OpenAIStreamingSpeechError(
            exc.reason, "streaming Speech Provider operation failed"
        )
    if isinstance(exc, StreamingSpeechViolation):
        return StreamingSpeechViolation(
            exc.reason, "streaming Speech conformance failed"
        )
    return OpenAIStreamingSpeechError(
        "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
        "streaming Speech Provider transport is unavailable",
    )


def _reason_for_exception(exc: BaseException) -> SpeechDegradationReason:
    if _is_process_control(exc):
        raise TypeError("process-control exceptions cannot be degradation reasons")
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        return SpeechDegradationReason.PROVIDER_TIMEOUT
    if isinstance(exc, OpenAIStreamingSpeechError):
        if exc.reason == "SPEECH_EVENT_QUEUE_EXHAUSTED":
            return SpeechDegradationReason.BOUNDED_QUEUE_EXHAUSTED
        if exc.reason in {
            "SPEECH_PROVIDER_REQUEST_REJECTED",
            "SPEECH_PROVIDER_RECOGNITION_FAILED",
            "SPEECH_PROVIDER_SYNTHESIS_FAILED",
            "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
        }:
            return SpeechDegradationReason.PROVIDER_UNAVAILABLE
    if isinstance(
        exc, (OpenAIStreamingSpeechError, StreamingSpeechViolation, ValueError)
    ):
        return SpeechDegradationReason.PROVIDER_PROTOCOL
    return SpeechDegradationReason.PROVIDER_UNAVAILABLE


def _is_process_control(exc: BaseException) -> bool:
    return isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit))


def _first_process_control(
    current: BaseException | None, results: Iterable[object]
) -> BaseException | None:
    if current is not None:
        return current
    for result in results:
        if isinstance(result, BaseException) and _is_process_control(result):
            return _safe_boundary_exception(result)
    return None


async def _settle_close_action(action: Awaitable[object]) -> object:
    """Keep process controls out of gather child Tasks until finalization ends."""

    try:
        return await action
    except BaseException as exc:
        failure = _safe_boundary_exception(exc)
        if isinstance(failure, asyncio.CancelledError):
            raise failure from None
        return failure


def _validate_api_base(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("API base is required")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.openai.com"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError("streaming Speech requires the official OpenAI HTTPS API base")
    return "https://api.openai.com/v1"


def _realtime_url(api_base: str) -> str:
    """Build the realtime transcription session URL.

    The session is opened with ``intent=transcription`` rather than a ``model``
    parameter. A realtime session's ``model`` must be a realtime model; passing
    the transcription snapshot there makes the server reject the session with
    ``invalid_model`` before any audio is sent. The transcription snapshot is
    carried by the ``session.update`` payload as
    ``session.audio.input.transcription.model`` instead.
    """
    parsed = urlparse(api_base)
    path = f"{parsed.path.rstrip('/')}/realtime"
    return urlunparse(
        ("wss", parsed.netloc, path, "", urlencode({"intent": "transcription"}), "")
    )


def _required_secret(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 4_096
        or "\r" in value
        or "\n" in value
    ):
        raise ValueError("API key must be non-empty, bounded, trimmed, and single-line")


def _supported_sample_rate(value: object) -> int:
    if type(value) is not int or not 8_000 <= value <= 192_000:
        raise OpenAIStreamingSpeechError(
            "SPEECH_SAMPLE_RATE_UNSUPPORTED",
            "streaming Speech sample rate must be in [8000, 192000]",
        )
    return value


def _safe_label(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_SAFE_LABEL_CHARS
        or any(character.isspace() for character in value)
    ):
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_INVALID_IDENTITY", f"{field_name} is invalid"
        )
    value.encode("utf-8", errors="strict")
    return value


def _provider_text(value: object, field_name: str) -> str:
    invalid = not isinstance(value, str)
    if isinstance(value, str):
        invalid = not value or len(value) > 16_000
    if isinstance(value, str) and not invalid:
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            invalid = True
    if invalid:
        value = None
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_INVALID_TEXT", f"{field_name} is invalid"
        )
    assert isinstance(value, str)
    return value


def _provider_milliseconds(value: object, field_name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= (1 << 53) - 1
    ):
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_INVALID_TIMING", f"{field_name} is invalid"
        )
    return value


def _require_primary_audio_content(event: Mapping[str, object]) -> None:
    content_index = event.get("content_index")
    if type(content_index) is not int or content_index != 0:
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_CONTENT_MISMATCH",
            "recognition Provider content index is not the primary audio content",
        )


def _turn_detection_wire(request: RecognitionStreamRequest) -> dict[str, object] | None:
    return _turn_detection_value(request.turn_detection)


def _validate_transcription_session(
    event: Mapping[str, object],
    *,
    expected_model: str,
    expected_turn_detection: RecognitionTurnDetection,
) -> None:
    session = event.get("session")
    if type(session) is not dict:
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_SESSION_MISMATCH",
            "speech Provider omitted the effective transcription session",
        )
    # Current GA shape.
    audio = session.get("audio")
    if type(audio) is dict:
        input_config = audio.get("input")
        if type(input_config) is not dict:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_SESSION_MISMATCH",
                "speech Provider returned an invalid input configuration",
            )
        audio_format = input_config.get("format")
        transcription = input_config.get("transcription")
        if (
            session.get("type") != "transcription"
            or type(audio_format) is not dict
            or audio_format.get("type") != "audio/pcm"
            or audio_format.get("rate") != OPENAI_PCM_RATE_HZ
            or type(transcription) is not dict
            or transcription.get("model") != expected_model
            or input_config.get("turn_detection", object())
            != _turn_detection_value(expected_turn_detection)
        ):
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_SESSION_MISMATCH",
                "speech Provider changed the requested transcription contract",
            )
        return
    # Earlier transcription-session shape retained only at the Adapter edge.
    transcription = session.get("input_audio_transcription")
    if (
        session.get("input_audio_format") != "pcm16"
        or type(transcription) is not dict
        or transcription.get("model") != expected_model
        or session.get("turn_detection", object())
        != _turn_detection_value(expected_turn_detection)
    ):
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_SESSION_MISMATCH",
            "speech Provider changed the requested transcription contract",
        )


def _turn_detection_value(
    detection: RecognitionTurnDetection,
) -> dict[str, object] | None:
    if detection.mode is RecognitionTurnDetectionMode.MANUAL:
        return None
    config = detection.server_vad
    assert config is not None
    return {
        "type": "server_vad",
        "threshold": float(config.threshold),
        "prefix_padding_ms": config.prefix_padding_ms,
        "silence_duration_ms": config.silence_duration_ms,
        "create_response": False,
        "interrupt_response": False,
    }


def _json_object(value: str) -> dict[str, object]:
    invalid = False
    parsed: object = None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        invalid = True
    if invalid:
        value = ""
        parsed = None
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_INVALID_JSON", "speech Provider returned invalid JSON"
        )
    if type(parsed) is not dict:
        value = ""
        parsed = None
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_INVALID_JSON", "speech Provider JSON must be an object"
        )
    return parsed


def _wire_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode_f32le(value: bytes) -> list[float]:
    if len(value) % 4:
        raise OpenAIStreamingSpeechError(
            "INVALID_PCM_F32_FRAME", "PCM f32 payload is misaligned"
        )
    return [sample[0] for sample in struct.iter_unpack("<f", value)]


def _decode_s16le(value: bytes) -> list[float]:
    if len(value) % 2:
        raise OpenAIStreamingSpeechError(
            "INVALID_PCM_S16_CHUNK", "PCM s16 payload is misaligned"
        )
    return [sample[0] / 32768.0 for sample in struct.iter_unpack("<h", value)]


def _encode_s16le(samples: list[float]) -> bytes:
    output = bytearray()
    for sample in samples:
        if not math.isfinite(sample):
            raise OpenAIStreamingSpeechError(
                "INVALID_PCM_SAMPLE", "PCM contains a non-finite sample"
            )
        clipped = min(1.0, max(-1.0, sample))
        integer = max(-32768, min(32767, round(clipped * 32767)))
        output.extend(struct.pack("<h", integer))
    return bytes(output)


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _recognition_key(ref: RecognitionStreamRef) -> tuple[str, int]:
    return ref.session_id, ref.session_generation


def _synthesis_key(ref: SynthesisStreamRef) -> tuple[str, int]:
    return ref.stream_id, ref.stream_generation


__all__ = [
    "CapabilityProvenance",
    "DEFAULT_STT_MODEL",
    "DEFAULT_TTS_MODEL",
    "DEFAULT_TTS_VOICE",
    "OPENAI_PCM_RATE_HZ",
    "OpenAIStreamingSpeechConfig",
    "OpenAIStreamingSpeechError",
    "OpenAIStreamingSpeechProvider",
    "SpeechDegradationFact",
    "SpeechDegradationReason",
    "SpeechRouteTier",
    "STREAMING_SPEECH_FLAG",
    "StreamingSpeechSelection",
    "select_environment_streaming_speech",
]
