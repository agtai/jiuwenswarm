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
from typing import Any, Protocol, TypeVar, cast
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
SPEECH_REALTIME_MODEL_ENV = "LIVE_VOICE_SPEECH_REALTIME_MODEL"
DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe-2025-12-15"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts-2025-12-15"
DEFAULT_TTS_VOICE = "marin"
DEFAULT_REALTIME_MODEL = "gpt-realtime-1.5"
OPENAI_PCM_RATE_HZ = 24_000
MAX_WIRE_MESSAGE_BYTES = 1_048_576
MAX_SSE_LINE_BYTES = 262_144
MAX_SSE_EVENT_BYTES = 1_048_576
MAX_STREAM_AUDIO_BYTES = 8 * 1024 * 1024
MAX_PROVIDER_AUDIO_DELTA_BYTES = 96_000
MAX_NATIVE_SERVER_EVENT_IDS = 4_096
NATIVE_TERMINAL_QUARANTINE_SECONDS = 0.05
_NATIVE_RESPONSE_REQUIRED_FIELDS = frozenset(
    {
        "id",
        "object",
        "status",
        "status_details",
        "usage",
        "output",
        "conversation_id",
        "output_modalities",
        "audio",
        "metadata",
    }
)
MAX_EVENT_QUEUE = 64
# How long a full event queue may hold the Provider reader before the stream is
# declared exhausted. Every other link in the pipeline already waits under a
# bound; this one refused instantly, so a consumer draining at real playout speed
# killed the stream a few seconds in. One Provider audio delta is bounded by
# MAX_PROVIDER_AUDIO_DELTA_BYTES, two seconds of 24 kHz pcm_s16le, so the budget
# must exceed the real-time drain of a single chunk. Holding the reader also
# closes the transport receive window, which is the backpressure the Provider
# needs; it never buffers beyond MAX_EVENT_QUEUE.
EVENT_QUEUE_WAIT_SECONDS = 6.0
MAX_SAFE_LABEL_CHARS = 256
DEGRADATION_SINK_BUDGET_SECONDS = 0.05
DEGRADATION_SINK_CLOSE_BUDGET_SECONDS = 0.1
MAX_DEGRADATION_SINK_TASKS_PER_OWNER = 4
MAX_DEGRADATION_SINK_TASKS_GLOBAL = 16
TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS = 0.05
TRANSPORT_CLEANUP_CLOSE_BUDGET_SECONDS = 0.1
# ``websockets`` otherwise inherits the Provider connect budget here (up to
# five seconds).  That makes an ordinary peer which doesn't acknowledge our
# close frame outlive both cleanup-owner budgets and turns a successful stream
# into ``SPEECH_PROVIDER_CLEANUP_INCOMPLETE``.  The frame is sent before this
# timeout starts; when it expires, websockets aborts the transport.  Reserving
# half the attempt budget leaves time for connection-lost bookkeeping while
# keeping the public cleanup call hard-bounded.
REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS = TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS / 2
MAX_INCOMPLETE_TRANSPORT_CLEANUPS = 32

_PROVIDER = ProviderRef("openai-streaming-speech", "formal")
_NATIVE_REALTIME_PROVIDER = ProviderRef("openai-realtime-native-speech", "formal")
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
    realtime_model: str | None = None
    connect_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_base", _validate_api_base(self.api_base))
        _required_secret(self.api_key)
        _safe_label(self.stt_model, "stt_model")
        _safe_label(self.tts_model, "tts_model")
        _safe_label(self.tts_voice, "tts_voice")
        if self.realtime_model is not None:
            model = _safe_label(self.realtime_model, "realtime_model")
            if not _supported_native_realtime_model(model):
                raise ValueError("native Realtime mode requires a gpt-realtime model")
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


class _RealtimeSocketTerminalEof(Exception):
    """Internal proof that a locally closing WebSocket receive owner reached EOF."""


class _WebSocketRealtimeSocket:
    def __init__(self, socket: Any) -> None:
        self._socket = socket

    async def send(self, message: str) -> None:
        await self._socket.send(message)

    async def recv(self) -> str | bytes:
        try:
            return await self._socket.recv()
        except BaseException as exc:
            if _is_process_control(exc) or isinstance(exc, asyncio.CancelledError):
                raise
            from websockets.exceptions import ConnectionClosed

            if isinstance(exc, ConnectionClosed):
                raise _RealtimeSocketTerminalEof() from None
            raise

    async def close(self) -> None:
        await self._socket.close()


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
        self._attempt_results: dict[
            asyncio.Task[_CleanupOutcome], asyncio.Future[bool]
        ] = {}
        self._attempt_deadlines: dict[asyncio.Task[_CleanupOutcome], float] = {}
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
            entry = self._tasks.get(task)
            if (
                entry is None
                or task not in self._attempt_results
                or not _same_cleanup(entry.cleanup, cleanup)
            ):
                _log_transport_cleanup(
                    kind=kind,
                    reason="identity-conflict",
                    retained_count=len(self._tasks),
                )
                return False
            return await self._await_shared_attempt(task, kind=kind)
        entry = self._failed.get(key)
        if entry is not None:
            if not _same_cleanup(entry.cleanup, cleanup):
                _log_transport_cleanup(
                    kind=kind,
                    reason="identity-conflict",
                    retained_count=len(self._tasks),
                )
                return False
            del self._failed[key]
        else:
            entry = _CleanupEntry(key, kind, cleanup)
        if len(self._tasks) + len(self._failed) >= MAX_INCOMPLETE_TRANSPORT_CLEANUPS:
            _log_transport_cleanup(
                kind=kind, reason="capacity", retained_count=len(self._tasks)
            )
            return False
        task = asyncio.create_task(_await_cleanup(entry.cleanup))
        self._track_attempt(task, entry)
        return await self._await_shared_attempt(task, kind=kind)

    def _track_attempt(
        self, task: asyncio.Task[_CleanupOutcome], entry: _CleanupEntry
    ) -> None:
        loop = asyncio.get_running_loop()
        self._tasks[task] = entry
        self._by_key[entry.key] = task
        self._attempt_results[task] = loop.create_future()
        self._attempt_deadlines[task] = (
            loop.time() + TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS
        )
        task.add_done_callback(self._release)

    async def _await_shared_attempt(
        self, task: asyncio.Task[_CleanupOutcome], *, kind: str
    ) -> bool:
        result = self._attempt_results.get(task)
        deadline = self._attempt_deadlines.get(task)
        if result is None or deadline is None:
            _log_transport_cleanup(
                kind=kind,
                reason="identity-conflict",
                retained_count=len(self._tasks),
            )
            return False
        try:
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            done, _ = await asyncio.wait({result}, timeout=remaining)
        except asyncio.CancelledError:
            _log_transport_cleanup(
                kind=kind, reason="caller-cancelled", retained_count=len(self._tasks)
            )
            raise
        timed_out = False
        if result not in done and not result.done():
            result.set_result(False)
            timed_out = True
        if timed_out:
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
        self._prune()
        self._raise_process_control()
        return result.result()

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
            self._track_attempt(task, entry)
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
        result = self._attempt_results.pop(task, None)
        self._attempt_deadlines.pop(task, None)
        if self._by_key.get(entry.key) is task:
            del self._by_key[entry.key]
        if task.cancelled():
            if result is not None and not result.done():
                result.set_result(False)
            if entry.cleanup is not None:
                self._failed[entry.key] = entry
            return
        with suppress(Exception, asyncio.CancelledError):
            outcome = task.result()
            if result is not None and not result.done():
                result.set_result(outcome.succeeded)
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


class _RecognitionFinalizationCause(StrEnum):
    CANCEL = "cancel"
    NORMAL_FINAL = "normal_final"
    PROVIDER_FAILURE = "provider_failure"
    ROLLBACK = "rollback"
    SERVICE_CLOSE = "service_close"


@dataclass(frozen=True, slots=True)
class _RecognitionFinalizationOutcome:
    cause: _RecognitionFinalizationCause
    failure: BaseException | None = field(default=None, repr=False)


class _SynthesisFinalizationCause(StrEnum):
    CANCEL = "cancel"
    NORMAL_COMPLETE = "normal_complete"
    PROVIDER_FAILURE = "provider_failure"
    ROLLBACK = "rollback"
    SERVICE_CLOSE = "service_close"


@dataclass(frozen=True, slots=True)
class _SynthesisFinalizationOutcome:
    cause: _SynthesisFinalizationCause
    failure: BaseException | None = field(default=None, repr=False)


@dataclass(slots=True)
class _FinalizationFailures:
    process_control: BaseException | None = field(default=None, repr=False)
    cancellation: BaseException | None = field(default=None, repr=False)
    cleanup: BaseException | None = field(default=None, repr=False)

    @property
    def failure(self) -> BaseException | None:
        return self.process_control or self.cancellation or self.cleanup

    def record(self, exc: BaseException) -> None:
        failure = _safe_boundary_exception(exc)
        if _is_process_control(failure):
            self.process_control = self.process_control or failure
        elif isinstance(failure, asyncio.CancelledError):
            self.cancellation = self.cancellation or failure
        else:
            self.cleanup = self.cleanup or failure

    async def settle(
        self,
        action: Awaitable[object],
        *,
        incomplete_is_failure: bool = True,
    ) -> bool:
        try:
            result = await _settle_close_action(action)
        except BaseException as exc:
            self.record(exc)
            return False
        else:
            if isinstance(result, BaseException):
                self.record(result)
                return False
            if result is False:
                if incomplete_is_failure:
                    self.record(_cleanup_incomplete_failure())
                return False
            return True


class _NativeSynthesisPhase(StrEnum):
    NEGOTIATING = "negotiating"
    AWAITING_RESPONSE = "awaiting_response"
    RESPONSE_CREATED = "response_created"
    ITEM_ADDED = "item_added"
    CONTENT_ADDED = "content_added"
    AUDIO_DONE = "audio_done"
    TRANSCRIPT_DONE = "transcript_done"
    CONTENT_DONE = "content_done"
    ITEM_DONE = "item_done"
    TERMINAL = "terminal"


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
    finalization_task: asyncio.Task[_RecognitionFinalizationOutcome] | None = field(
        default=None, repr=False
    )
    partial_text: str = field(default="", repr=False)
    item_id: str | None = None
    speech_item_id: str | None = field(default=None, repr=False)
    speech_start_ms: int | None = None
    speech_end_ms: int | None = None
    source_cursor: int = 0
    committed_source_cursor: int | None = None
    event_seq: int = 0
    committed: bool = False
    negotiated: bool = False
    native_event_ids: set[str] = field(default_factory=set, repr=False)
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
    finalization_task: asyncio.Task[_SynthesisFinalizationOutcome] | None = field(
        default=None, repr=False
    )
    stream: SpeechSseStream | None = field(default=None, repr=False)
    socket: RealtimeSocket | None = field(default=None, repr=False)
    provider_response_id: str | None = None
    provider_item_id: str | None = None
    provider_audio_done: bool = False
    provider_transcript_done: bool = False
    provider_transcript: str = field(default="", repr=False)
    pending_native_audio: bytearray = field(default_factory=bytearray, repr=False)
    native_phase: _NativeSynthesisPhase = _NativeSynthesisPhase.NEGOTIATING
    native_session_created: bool = False
    native_event_ids: set[str] = field(default_factory=set, repr=False)
    native_progress_deadline: float | None = None
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
        "close_timeout": REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS,
        "max_size": MAX_WIRE_MESSAGE_BYTES,
        "compression": None,
    }
    parameter = (
        "additional_headers"
        if "additional_headers" in inspect.signature(websockets.connect).parameters
        else "extra_headers"
    )
    kwargs[parameter] = dict(headers)
    socket = await websockets.connect(url, **kwargs)
    return _WebSocketRealtimeSocket(socket)


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
        event_queue_wait_seconds: float = EVENT_QUEUE_WAIT_SECONDS,
    ) -> None:
        if not isinstance(config, OpenAIStreamingSpeechConfig):
            raise TypeError("config must be OpenAIStreamingSpeechConfig")
        if (
            type(event_queue_wait_seconds) is not float
            or not 0.0 < event_queue_wait_seconds <= 60.0
        ):
            raise ValueError(
                "event_queue_wait_seconds must be a bounded positive float"
            )
        self._event_queue_wait_seconds = event_queue_wait_seconds
        self._config = config
        self._socket_factory = socket_factory or _default_socket_factory
        self._sse_factory = sse_factory or _default_sse_factory
        self._degradation_sink = degradation_sink
        if fallback_tier is not SpeechRouteTier.TEXT:
            raise ValueError(
                "runtime fallback must be text; product wiring owns batch eligibility"
            )
        self._fallback_tier = fallback_tier
        self._provider_ref = (
            _NATIVE_REALTIME_PROVIDER
            if config.realtime_model is not None
            else _PROVIDER
        )
        self._degradation_sink_tasks = _DegradationSinkTaskOwner()
        self._transport_cleanup_tasks = _TransportCleanupOwner()
        self._monotonic = monotonic
        self._capability = StreamingProviderCapability(
            provider=self._provider_ref,
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
        return self._config.realtime_model or self._config.tts_model

    @property
    def synthesis_voice(self) -> str | None:
        return self._config.tts_voice

    @property
    def fallback_tier(self) -> SpeechRouteTier:
        return self._fallback_tier

    @property
    def native_realtime(self) -> bool:
        return self._config.realtime_model is not None

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
            url = _realtime_url(
                self._config.api_base, model=self._config.realtime_model
            )
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
                _wire_json(_recognition_session_update(self._config, request)),
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
                self._require_negotiated_recognition(session)
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
                self._require_negotiated_recognition(session)
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
        self._require_negotiated_recognition(session)
        event = await asyncio.wait_for(session.events.get(), timeout=timeout_seconds)
        if event.kind in {RecognitionEventKind.FINAL, RecognitionEventKind.CANCELLED}:
            await self._retire_recognition(session)
        return event

    async def cancel_recognition(
        self, ref: RecognitionStreamRef, *, reason: str = "caller_cancel"
    ) -> None:
        session = self._require_recognition(ref)
        outcome = await self._finalize_recognition_session(
            session,
            cause=_RecognitionFinalizationCause.CANCEL,
            reason=reason,
        )
        _raise_recognition_finalization(outcome)

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
        outcome = await self._finalize_synthesis_session(
            session,
            cause=_SynthesisFinalizationCause.CANCEL,
            reason=reason,
        )
        _raise_synthesis_finalization(outcome)

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
        results = await asyncio.gather(
            *(
                self._finalize_recognition_session(
                    recognition_session,
                    cause=_RecognitionFinalizationCause.SERVICE_CLOSE,
                )
                for recognition_session in recognition
            ),
            *(
                self._finalize_synthesis_session(
                    synthesis_session,
                    cause=_SynthesisFinalizationCause.SERVICE_CLOSE,
                )
                for synthesis_session in synthesis
            ),
            return_exceptions=True,
        )
        process_control = _first_process_control(process_control, results)
        for result in results:
            failure = (
                result.failure
                if isinstance(
                    result,
                    (
                        _RecognitionFinalizationOutcome,
                        _SynthesisFinalizationOutcome,
                    ),
                )
                else None
            )
            if failure is None:
                continue
            if _is_process_control(failure):
                process_control = process_control or failure
            elif isinstance(failure, asyncio.CancelledError):
                raise failure from None
            else:
                cleanup_failure = cleanup_failure or failure
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
        if process_control is not None:
            raise process_control from None
        if cleanup_failure is not None:
            raise cleanup_failure from None

    async def _finalize_recognition_session(
        self,
        session: _RecognitionSession,
        *,
        cause: _RecognitionFinalizationCause,
        trigger_failure: BaseException | None = None,
        reason: str = "",
        final_text: str = "",
    ) -> _RecognitionFinalizationOutcome:
        task = session.finalization_task
        if task is None:
            if session.terminal:
                return _RecognitionFinalizationOutcome(cause)
            # Assignment is synchronous: every later contender observes and
            # awaits this exact Task instead of starting another terminal path.
            if cause is not _RecognitionFinalizationCause.NORMAL_FINAL:
                session.closing = True
            origin_task = asyncio.current_task()
            task = asyncio.create_task(
                self._run_recognition_finalization(
                    session,
                    cause=cause,
                    trigger_failure=trigger_failure,
                    reason=reason,
                    final_text=final_text,
                    origin_task=origin_task,
                ),
                name=(
                    "openai-stt-finalize-"
                    f"{session.ref.session_id}-{session.ref.session_generation}"
                ),
            )
            session.finalization_task = task
        return await asyncio.shield(task)

    async def _run_recognition_finalization(
        self,
        session: _RecognitionSession,
        *,
        cause: _RecognitionFinalizationCause,
        trigger_failure: BaseException | None,
        reason: str,
        final_text: str,
        origin_task: asyncio.Task[Any] | None,
    ) -> _RecognitionFinalizationOutcome:
        ready_was_done = session.ready.done()
        failures = _FinalizationFailures()

        if trigger_failure is not None and (
            _is_process_control(trigger_failure)
            or isinstance(trigger_failure, asyncio.CancelledError)
        ):
            failures.record(trigger_failure)

        try:
            if cause is _RecognitionFinalizationCause.CANCEL:
                self._conformance.request_recognition_cancel(session.ref, reason=reason)
            elif cause is _RecognitionFinalizationCause.PROVIDER_FAILURE and isinstance(
                trigger_failure, (TimeoutError, asyncio.TimeoutError)
            ):
                self._conformance.expire()
        except BaseException as exc:
            failures.record(exc)

        if cause is _RecognitionFinalizationCause.NORMAL_FINAL:
            await self._settle_finalization_socket(failures, session.socket)
            if failures.failure is None:
                try:
                    await self._publish_recognition(
                        session, RecognitionEventKind.FINAL, final_text
                    )
                except BaseException as exc:
                    trigger_failure = _safe_boundary_exception(exc)
                    if _is_process_control(trigger_failure) or isinstance(
                        trigger_failure, asyncio.CancelledError
                    ):
                        failures.record(trigger_failure)
                else:
                    session.terminal = True
                    return _RecognitionFinalizationOutcome(cause)
            session.closing = True

        receive_owns_provider_failure = (
            cause is _RecognitionFinalizationCause.PROVIDER_FAILURE
            and origin_task is session.receive_task
        )
        if (
            cause is not _RecognitionFinalizationCause.NORMAL_FINAL
            and not receive_owns_provider_failure
        ):
            await self._settle_finalization_socket(failures, session.socket)

        receive_task = session.receive_task
        if (
            receive_task is not None
            and receive_task is not origin_task
            and receive_task is not asyncio.current_task()
        ):
            await failures.settle(
                self._transport_cleanup_tasks.cancel_task(
                    receive_task, kind="recognition-worker"
                )
            )

        try:
            self._conformance.provider_closed_recognition(session.ref)
        except StreamingSpeechViolation as exc:
            if cause not in {
                _RecognitionFinalizationCause.NORMAL_FINAL,
                _RecognitionFinalizationCause.ROLLBACK,
                _RecognitionFinalizationCause.SERVICE_CLOSE,
            }:
                failures.record(exc)
        except BaseException as exc:
            failures.record(exc)

        session.terminal = True
        try:
            await self._retire_recognition(session)
        except BaseException as exc:
            failures.record(exc)

        try:
            if cause is _RecognitionFinalizationCause.CANCEL:
                await self._emit_failure(
                    operation="recognition.cancel",
                    reason=SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED,
                    started_at=None,
                    identity=(
                        f"{session.ref.session_id}:{session.ref.session_generation}"
                    ),
                )
            else:
                degradation_failure = trigger_failure or failures.cleanup
                if (
                    cause
                    in {
                        _RecognitionFinalizationCause.NORMAL_FINAL,
                        _RecognitionFinalizationCause.PROVIDER_FAILURE,
                    }
                    and ready_was_done
                    and degradation_failure is not None
                    and not _is_process_control(degradation_failure)
                    and not isinstance(degradation_failure, asyncio.CancelledError)
                ):
                    await self._emit_failure(
                        operation="recognition.stream",
                        reason=_reason_for_exception(degradation_failure),
                        started_at=None,
                        identity=(
                            f"{session.ref.session_id}:{session.ref.session_generation}"
                        ),
                    )
        except BaseException as exc:
            failures.record(exc)

        if receive_owns_provider_failure:
            # Existing observers use transport close as the visible completion
            # barrier for a receive-owned failure.  Keep that truth while all
            # other causes close first to wake the receive worker.
            await self._settle_finalization_socket(failures, session.socket)

        # Opening waits are released only after transport, worker, conformance,
        # registry and observability settlement.  No receive-side wakeup can
        # publish a competing outcome before this point.
        if not session.ready.done():
            if cause in {
                _RecognitionFinalizationCause.NORMAL_FINAL,
                _RecognitionFinalizationCause.PROVIDER_FAILURE,
            }:
                if isinstance(trigger_failure, asyncio.CancelledError):
                    session.ready.cancel()
                elif trigger_failure is not None:
                    session.ready.set_exception(trigger_failure)
                else:
                    session.ready.set_exception(
                        OpenAIStreamingSpeechError(
                            "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                            "recognition Provider transport is unavailable",
                        )
                    )
            else:
                session.ready.cancel()

        return _RecognitionFinalizationOutcome(
            cause,
            failures.failure,
        )

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
                if session.closing:
                    raw = None
                    return
                terminal = await self._consume_recognition_message(session, raw)
                raw = None
                if terminal:
                    return
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        finally:
            raw = None
        if session.closing:
            if failure is not None and _is_process_control(failure):
                raise failure from None
            return
        if failure is not None:
            opening_failure = not session.ready.done()
            outcome = await self._finalize_recognition_session(
                session,
                cause=_RecognitionFinalizationCause.PROVIDER_FAILURE,
                trigger_failure=failure,
            )
            if opening_failure:
                return
            _raise_recognition_finalization(outcome)

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
        if self._config.realtime_model is not None:
            self._accept_native_recognition_event_id(session, event)
        kind = event.get("type")
        if not session.negotiated and kind not in {
            "session.created",
            "transcription_session.created",
            "session.updated",
            "transcription_session.updated",
            "rate_limits.updated",
            "error",
        }:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_TURN_ORDER",
                "recognition Provider emitted data before session negotiation",
            )
        if kind in {"session.updated", "transcription_session.updated"}:
            if session.negotiated:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TURN_ORDER",
                    "recognition Provider duplicated session negotiation",
                )
            _validate_transcription_session(
                event,
                expected_model=self._config.stt_model,
                expected_turn_detection=session.request.turn_detection,
                expected_realtime_model=self._config.realtime_model,
                expected_voice=(
                    self._config.tts_voice
                    if self._config.realtime_model is not None
                    else None
                ),
            )
            session.negotiated = True
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
            outcome = await self._finalize_recognition_session(
                session,
                cause=_RecognitionFinalizationCause.NORMAL_FINAL,
                final_text=transcript,
            )
            _raise_recognition_finalization(outcome)
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
            provider=self._provider_ref,
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
            provider=self._provider_ref,
            seq=session.event_seq,
            kind=kind,
            provider_item_id=provider_item_id,
            provider_start_ms=provider_start_ms,
            provider_end_ms=provider_end_ms,
        )
        accepted = self._conformance.accept_recognition_boundary(event)
        session.event_seq += 1
        await self._put_bounded(session.events, accepted)

    async def _finalize_synthesis_session(
        self,
        session: _SynthesisSession,
        *,
        cause: _SynthesisFinalizationCause,
        trigger_failure: BaseException | None = None,
        reason: str = "",
        started_at: float | None = None,
        tail: bytes = b"",
    ) -> _SynthesisFinalizationOutcome:
        task = session.finalization_task
        if task is None:
            if session.terminal:
                return _SynthesisFinalizationOutcome(cause)
            if cause is not _SynthesisFinalizationCause.NORMAL_COMPLETE:
                session.closing = True
            origin_task = asyncio.current_task()
            task = asyncio.create_task(
                self._run_synthesis_finalization(
                    session,
                    cause=cause,
                    trigger_failure=trigger_failure,
                    reason=reason,
                    started_at=started_at,
                    tail=tail,
                    origin_task=origin_task,
                ),
                name=(
                    "openai-tts-finalize-"
                    f"{session.request.ref.stream_id}-"
                    f"{session.request.ref.stream_generation}"
                ),
            )
            session.finalization_task = task
        return await asyncio.shield(task)

    async def _run_synthesis_finalization(
        self,
        session: _SynthesisSession,
        *,
        cause: _SynthesisFinalizationCause,
        trigger_failure: BaseException | None,
        reason: str,
        started_at: float | None,
        tail: bytes,
        origin_task: asyncio.Task[Any] | None,
    ) -> _SynthesisFinalizationOutcome:
        failures = _FinalizationFailures()
        if trigger_failure is not None and (
            _is_process_control(trigger_failure)
            or isinstance(trigger_failure, asyncio.CancelledError)
        ):
            failures.record(trigger_failure)

        try:
            if cause is _SynthesisFinalizationCause.CANCEL:
                self._conformance.request_synthesis_cancel(
                    session.request.ref, reason=reason
                )
            elif cause is _SynthesisFinalizationCause.PROVIDER_FAILURE and isinstance(
                trigger_failure, (TimeoutError, asyncio.TimeoutError)
            ):
                self._conformance.expire()
        except BaseException as exc:
            failures.record(exc)

        if (
            cause is _SynthesisFinalizationCause.CANCEL
            and session.socket is not None
            and session.provider_response_id is not None
        ):
            try:
                async with asyncio.timeout(TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS):
                    await session.socket.send(
                        _wire_json(
                            {
                                "type": "response.cancel",
                                "response_id": session.provider_response_id,
                            }
                        )
                    )
            except BaseException as exc:
                failure = _safe_boundary_exception(exc)
                if _is_process_control(failure) or isinstance(
                    failure, asyncio.CancelledError
                ):
                    failures.record(failure)

        if cause is _SynthesisFinalizationCause.NORMAL_COMPLETE:
            if session.stream is not None:
                await self._settle_finalization_stream(failures, session.stream)
            if session.socket is not None:
                await self._settle_finalization_socket(failures, session.socket)
            if failures.failure is None:
                try:
                    if tail:
                        await self._publish_synthesis(
                            session, SynthesisEventKind.CHUNK, pcm=tail
                        )
                    await self._publish_synthesis(session, SynthesisEventKind.COMPLETED)
                except BaseException as exc:
                    trigger_failure = _safe_boundary_exception(exc)
                    if _is_process_control(trigger_failure) or isinstance(
                        trigger_failure, asyncio.CancelledError
                    ):
                        failures.record(trigger_failure)
                else:
                    session.terminal = True
                    return _SynthesisFinalizationOutcome(cause)
            session.closing = True

        session.pending_native_audio.clear()
        worker_owns_provider_failure = (
            cause is _SynthesisFinalizationCause.PROVIDER_FAILURE
            and origin_task is session.task
        )
        if (
            cause is not _SynthesisFinalizationCause.NORMAL_COMPLETE
            and not worker_owns_provider_failure
        ):
            if session.stream is not None:
                await self._settle_finalization_stream(failures, session.stream)
            if session.socket is not None:
                await self._settle_finalization_socket(failures, session.socket)

        worker = session.task
        if (
            worker is not None
            and worker is not origin_task
            and worker is not asyncio.current_task()
        ):
            await failures.settle(
                self._transport_cleanup_tasks.cancel_task(
                    worker, kind="synthesis-worker"
                )
            )

        try:
            self._conformance.provider_closed_synthesis(session.request.ref)
        except StreamingSpeechViolation as exc:
            if cause not in {
                _SynthesisFinalizationCause.NORMAL_COMPLETE,
                _SynthesisFinalizationCause.ROLLBACK,
                _SynthesisFinalizationCause.SERVICE_CLOSE,
            }:
                failures.record(exc)
        except BaseException as exc:
            failures.record(exc)

        session.terminal = True
        try:
            await self._retire_synthesis(session)
        except BaseException as exc:
            failures.record(exc)

        try:
            if cause is _SynthesisFinalizationCause.CANCEL:
                await self._emit_failure(
                    operation="synthesis.cancel",
                    reason=SpeechDegradationReason.PROVIDER_CANCEL_UNACKNOWLEDGED,
                    started_at=None,
                    identity=(
                        f"{session.request.ref.stream_id}:"
                        f"{session.request.ref.stream_generation}"
                    ),
                )
            else:
                degradation_failure = trigger_failure or failures.cleanup
                if (
                    cause
                    in {
                        _SynthesisFinalizationCause.NORMAL_COMPLETE,
                        _SynthesisFinalizationCause.PROVIDER_FAILURE,
                    }
                    and degradation_failure is not None
                    and not _is_process_control(degradation_failure)
                    and not isinstance(degradation_failure, asyncio.CancelledError)
                ):
                    await self._emit_failure(
                        operation="synthesis.stream",
                        reason=_reason_for_exception(degradation_failure),
                        started_at=started_at,
                        identity=(
                            f"{session.request.ref.stream_id}:"
                            f"{session.request.ref.stream_generation}"
                        ),
                    )
        except BaseException as exc:
            failures.record(exc)

        if worker_owns_provider_failure:
            if session.stream is not None:
                await self._settle_finalization_stream(failures, session.stream)
            if session.socket is not None:
                await self._settle_finalization_socket(failures, session.socket)

        return _SynthesisFinalizationOutcome(cause, failures.failure)

    async def _run_synthesis(self, session: _SynthesisSession) -> None:
        started_at = self._monotonic()
        failure: BaseException | None = None
        tail: bytes | None = None
        try:
            if self._config.realtime_model is None:
                async with asyncio.timeout(session.request.event_timeout_seconds):
                    session.stream = await self._open_synthesis_stream(session)
                await self._publish_synthesis(session, SynthesisEventKind.STARTED)
                done = await self._consume_synthesis_stream(session)
            else:
                done = await self._run_native_realtime_synthesis(session)
            if not done:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TTS_INCOMPLETE",
                    "speech Provider closed without a done event",
                )
        except BaseException as exc:
            failure = _safe_boundary_exception(exc)
        if failure is None:
            try:
                tail = _encode_s16le(session.resampler.finish())
            except BaseException as exc:
                failure = _safe_boundary_exception(exc)
            else:
                outcome = await self._finalize_synthesis_session(
                    session,
                    cause=_SynthesisFinalizationCause.NORMAL_COMPLETE,
                    started_at=started_at,
                    tail=tail,
                )
                tail = None
                _raise_synthesis_finalization(outcome)
                return
        tail = None
        if failure is None:
            return
        if session.closing:
            if _is_process_control(failure):
                raise failure from None
            return
        outcome = await self._finalize_synthesis_session(
            session,
            cause=_SynthesisFinalizationCause.PROVIDER_FAILURE,
            trigger_failure=failure,
            started_at=started_at,
        )
        _raise_synthesis_finalization(outcome)

    async def _run_native_realtime_synthesis(self, session: _SynthesisSession) -> bool:
        model = self._config.realtime_model
        if model is None:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_CONFIGURATION_UNAVAILABLE",
                "native Realtime synthesis model is unavailable",
            )
        headers: Mapping[str, str] = {
            "Authorization": f"Bearer {self._config.api_key}",
        }
        async with asyncio.timeout(session.request.event_timeout_seconds):
            session.socket = await self._socket_factory(
                _realtime_url(self._config.api_base, model=model),
                headers,
                self._config.connect_timeout_seconds,
            )
        headers = {}
        await self._send_native_synthesis(
            session,
            _wire_json(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "output_modalities": ["audio"],
                        "audio": {
                            "output": {
                                "format": {
                                    "type": "audio/pcm",
                                    "rate": OPENAI_PCM_RATE_HZ,
                                },
                                "voice": self._config.tts_voice,
                            }
                        },
                        "tools": [],
                        "tool_choice": "none",
                    },
                }
            ),
        )
        self._note_native_progress(session)
        while True:
            raw = await self._recv_native_synthesis(session)
            event = _json_object(raw)
            self._accept_native_event_id(session, event)
            kind = event.get("type")
            if kind == "session.created":
                if (
                    session.native_phase is not _NativeSynthesisPhase.NEGOTIATING
                    or session.native_session_created
                ):
                    raise OpenAIStreamingSpeechError(
                        "SPEECH_PROVIDER_TURN_ORDER",
                        "native Realtime synthesis duplicated session creation",
                    )
                session.native_session_created = True
                self._note_native_progress(session)
                continue
            if kind != "session.updated" or not session.native_session_created:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TURN_ORDER",
                    "native Realtime synthesis was not negotiated before output",
                )
            _validate_realtime_synthesis_session(
                event,
                expected_model=model,
                expected_voice=self._config.tts_voice,
            )
            session.native_phase = _NativeSynthesisPhase.AWAITING_RESPONSE
            self._note_native_progress(session)
            break
        metadata = _native_response_metadata(session.request)
        spoken_text = session.request.spoken_text
        await self._send_native_synthesis(
            session,
            _wire_json(
                {
                    "type": "response.create",
                    "response": {
                        "conversation": "none",
                        "metadata": metadata,
                        "output_modalities": ["audio"],
                        "input": [],
                        "instructions": (
                            "Say exactly the following text. Do not add, remove, "
                            "translate, summarize, or paraphrase anything.\n\n"
                            f"{spoken_text}"
                        ),
                    },
                }
            ),
        )
        metadata = {}
        spoken_text = ""
        self._note_native_progress(session)
        await self._publish_synthesis(session, SynthesisEventKind.STARTED)
        while True:
            raw = await self._recv_native_synthesis(session)
            if await self._consume_native_synthesis_message(session, raw):
                await self._quarantine_native_terminal(session)
                await self._settle_native_terminal_transport(session)
                await self._publish_native_audio_buffer(session)
                return True

    async def _quarantine_native_terminal(self, session: _SynthesisSession) -> None:
        deadline = self._monotonic() + min(
            NATIVE_TERMINAL_QUARANTINE_SECONDS,
            session.request.event_timeout_seconds,
        )
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return
            try:
                async with asyncio.timeout(remaining):
                    raw = await self._recv_native_synthesis(session)
            except (TimeoutError, asyncio.TimeoutError):
                return
            self._consume_native_terminal_observation(session, raw)

    async def _settle_native_terminal_transport(
        self, session: _SynthesisSession
    ) -> None:
        socket = session.socket
        if socket is None:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                "native Realtime synthesis terminal transport is unavailable",
            )
        drain_task = asyncio.create_task(
            self._drain_native_terminal_during_close(session, socket),
            name=(
                f"openai-native-terminal-drain-"
                f"{session.request.ref.stream_id}-"
                f"{session.request.ref.stream_generation}"
            ),
        )
        try:
            if not await self._close_socket(socket):
                if drain_task.done():
                    try:
                        drain_task.result()
                    except OpenAIStreamingSpeechError:
                        raise
                    except BaseException as exc:
                        if _is_process_control(exc):
                            raise exc from None
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                    "native Realtime synthesis terminal transport did not close",
                )
            session.socket = None
            try:
                async with asyncio.timeout(TRANSPORT_CLEANUP_ATTEMPT_BUDGET_SECONDS):
                    await asyncio.shield(drain_task)
            except OpenAIStreamingSpeechError:
                raise
            except asyncio.CancelledError:
                raise
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                    "native Realtime terminal receive owner did not settle",
                ) from exc
            except _RealtimeSocketTerminalEof:
                # The wrapper emits this only after the WebSocket protocol has
                # delivered every frame ordered before its close boundary.
                return
            except BaseException as exc:
                if _is_process_control(exc):
                    raise exc from None
                raise _safe_transport_exception(exc) from None
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                "native Realtime terminal receive owner ended without transport EOF",
            )
        finally:
            if not drain_task.done():
                await self._transport_cleanup_tasks.cancel_task(
                    drain_task, kind="native-terminal-drain"
                )
            else:
                # Observe an already-finished loser when close itself raised
                # before the main path could await the drain outcome.
                with suppress(BaseException):
                    drain_task.exception()

    async def _drain_native_terminal_during_close(
        self,
        session: _SynthesisSession,
        socket: RealtimeSocket,
    ) -> None:
        while True:
            raw = await socket.recv()
            self._consume_native_terminal_observation(session, raw)

    def _consume_native_terminal_observation(
        self, session: _SynthesisSession, raw: str | bytes
    ) -> None:
        if type(raw) is not str:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_BINARY_CONTROL",
                "native Realtime synthesis returned a binary control message",
            )
        if len(raw.encode("utf-8")) > MAX_WIRE_MESSAGE_BYTES:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_MESSAGE_LIMIT",
                "native Realtime synthesis message exceeds the limit",
            )
        event = _json_object(raw)
        self._accept_native_event_id(session, event)
        kind = event.get("type")
        if kind == "rate_limits.updated":
            return
        self._raise_native_phase(session, kind)

    async def _recv_native_synthesis(self, session: _SynthesisSession) -> str:
        if session.socket is None:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                "native Realtime synthesis transport is unavailable",
            )
        timeout_seconds = session.request.event_timeout_seconds
        if session.native_progress_deadline is not None:
            remaining = session.native_progress_deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "native Realtime synthesis made no bounded protocol progress"
                )
            timeout_seconds = min(timeout_seconds, remaining)
        async with asyncio.timeout(timeout_seconds):
            raw = await session.socket.recv()
        if type(raw) is not str:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_BINARY_CONTROL",
                "native Realtime synthesis returned a binary control message",
            )
        if len(raw.encode("utf-8")) > MAX_WIRE_MESSAGE_BYTES:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_MESSAGE_LIMIT",
                "native Realtime synthesis message exceeds the limit",
            )
        return raw

    async def _send_native_synthesis(
        self, session: _SynthesisSession, message: str
    ) -> None:
        if session.socket is None:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE",
                "native Realtime synthesis transport is unavailable",
            )
        async with asyncio.timeout(session.request.event_timeout_seconds):
            await session.socket.send(message)

    async def _consume_native_synthesis_message(
        self, session: _SynthesisSession, raw: str
    ) -> bool:
        event = _json_object(raw)
        self._accept_native_event_id(session, event)
        kind = event.get("type")
        if kind == "response.created":
            self._require_native_phase(
                session, _NativeSynthesisPhase.AWAITING_RESPONSE, kind
            )
            response = event.get("response")
            if type(response) is not dict:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_RESPONSE_MISMATCH",
                    "native Realtime synthesis omitted its response",
                )
            response_id = _safe_label(response.get("id"), "response_id")
            if session.provider_response_id is not None or not (
                _native_initial_response_matches(
                    response,
                    expected_metadata=_native_response_metadata(session.request),
                    expected_voice=self._config.tts_voice,
                )
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_RESPONSE_MISMATCH",
                    "native Realtime synthesis response lost its exact binding",
                )
            session.provider_response_id = response_id
            session.native_phase = _NativeSynthesisPhase.RESPONSE_CREATED
            self._note_native_progress(session)
            return False
        if kind == "response.output_item.added":
            self._require_native_phase(
                session, _NativeSynthesisPhase.RESPONSE_CREATED, kind
            )
            self._require_native_response_binding(session, event)
            item = event.get("item")
            if (
                event.get("output_index") != 0
                or type(item) is not dict
                or item.get("type") != "message"
                or item.get("status") != "in_progress"
                or item.get("role") != "assistant"
                or item.get("content") != []
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_CONTENT_MISMATCH",
                    "native Realtime synthesis added an invalid output item",
                )
            session.provider_item_id = _safe_label(item.get("id"), "item_id")
            session.native_phase = _NativeSynthesisPhase.ITEM_ADDED
            self._note_native_progress(session)
            return False
        if kind == "response.content_part.added":
            self._require_native_phase(session, _NativeSynthesisPhase.ITEM_ADDED, kind)
            self._require_native_content_binding(session, event)
            part = event.get("part")
            if type(part) is not dict or part.get("type") != "audio":
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_CONTENT_MISMATCH",
                    "native Realtime synthesis added a non-audio content part",
                )
            session.native_phase = _NativeSynthesisPhase.CONTENT_ADDED
            self._note_native_progress(session)
            return False
        if kind == "response.output_audio.delta":
            self._require_native_phase(
                session, _NativeSynthesisPhase.CONTENT_ADDED, kind
            )
            self._require_native_audio_binding(session, event)
            encoded = event.get("delta")
            if not isinstance(encoded, str) or not encoded:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_INVALID_AUDIO",
                    "native Realtime synthesis returned invalid audio",
                )
            try:
                pcm = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_INVALID_AUDIO",
                    "native Realtime synthesis returned invalid audio",
                ) from exc
            if (
                not pcm
                or len(pcm) % 2
                or len(pcm) > MAX_PROVIDER_AUDIO_DELTA_BYTES
                or len(session.pending_native_audio) + len(pcm) > MAX_STREAM_AUDIO_BYTES
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_AUDIO_LIMIT",
                    "native Realtime synthesis audio is invalid or exceeds the limit",
                )
            session.pending_native_audio.extend(pcm)
            session.wire_audio_bytes += len(pcm)
            self._note_native_progress(session)
            return False
        if kind == "response.output_audio.done":
            self._require_native_phase(
                session, _NativeSynthesisPhase.CONTENT_ADDED, kind
            )
            self._require_native_audio_binding(session, event)
            if session.provider_audio_done or not session.pending_native_audio:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TURN_ORDER",
                    "native Realtime synthesis completed missing or duplicate audio",
                )
            session.provider_audio_done = True
            session.native_phase = _NativeSynthesisPhase.AUDIO_DONE
            self._note_native_progress(session)
            return False
        if kind == "response.output_audio_transcript.delta":
            if session.native_phase not in {
                _NativeSynthesisPhase.CONTENT_ADDED,
                _NativeSynthesisPhase.AUDIO_DONE,
            }:
                self._raise_native_phase(session, kind)
            self._require_native_audio_binding(session, event)
            if session.provider_transcript_done:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TURN_ORDER",
                    "native Realtime synthesis transcript changed after completion",
                )
            delta = _provider_text(event.get("delta"), "transcript delta")
            if len(session.provider_transcript) + len(delta) > 16_000:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_INVALID_TEXT",
                    "native Realtime synthesis transcript exceeds the limit",
                )
            session.provider_transcript += delta
            self._note_native_progress(session)
            return False
        if kind == "response.output_audio_transcript.done":
            self._require_native_phase(session, _NativeSynthesisPhase.AUDIO_DONE, kind)
            self._require_native_audio_binding(session, event)
            transcript = _provider_text(event.get("transcript"), "transcript")
            if (
                session.provider_transcript_done
                or (
                    session.provider_transcript
                    and session.provider_transcript != transcript
                )
                or transcript != session.request.spoken_text
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TEXT_MISMATCH",
                    "native Realtime synthesis changed authoritative Agent text",
                )
            session.provider_transcript = transcript
            session.provider_transcript_done = True
            session.native_phase = _NativeSynthesisPhase.TRANSCRIPT_DONE
            self._note_native_progress(session)
            return False
        if kind == "response.content_part.done":
            self._require_native_phase(
                session, _NativeSynthesisPhase.TRANSCRIPT_DONE, kind
            )
            self._require_native_content_binding(session, event)
            part = event.get("part")
            if (
                type(part) is not dict
                or part.get("type") != "audio"
                or part.get("transcript") != session.request.spoken_text
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TEXT_MISMATCH",
                    "native Realtime synthesis completed a changed content part",
                )
            session.native_phase = _NativeSynthesisPhase.CONTENT_DONE
            self._note_native_progress(session)
            return False
        if kind == "response.output_item.done":
            self._require_native_phase(
                session, _NativeSynthesisPhase.CONTENT_DONE, kind
            )
            self._require_native_response_binding(session, event)
            if event.get("output_index") != 0 or not _native_output_message_matches(
                event.get("item"),
                expected_item_id=session.provider_item_id,
                expected_text=session.request.spoken_text,
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_CONTENT_MISMATCH",
                    "native Realtime synthesis completed an invalid output item",
                )
            session.native_phase = _NativeSynthesisPhase.ITEM_DONE
            self._note_native_progress(session)
            return False
        if kind == "response.done":
            self._require_native_phase(session, _NativeSynthesisPhase.ITEM_DONE, kind)
            response = event.get("response")
            if type(response) is not dict:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_RESPONSE_MISMATCH",
                    "native Realtime synthesis omitted terminal response truth",
                )
            self._require_native_response_binding(session, response)
            if (
                response.get("status") != "completed"
                or response.get("metadata")
                != _native_response_metadata(session.request)
                or not session.provider_audio_done
                or not session.provider_transcript_done
                or not session.pending_native_audio
                or not _native_terminal_output_matches(
                    response,
                    expected_item_id=session.provider_item_id,
                    expected_text=session.request.spoken_text,
                    expected_voice=self._config.tts_voice,
                )
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_TTS_INCOMPLETE",
                    "native Realtime synthesis did not complete exact audio output",
                )
            session.native_phase = _NativeSynthesisPhase.TERMINAL
            self._note_native_progress(session)
            return True
        if kind == "error":
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_SYNTHESIS_FAILED",
                "native Realtime synthesis Provider reported a failure",
            )
        if kind == "rate_limits.updated":
            return False
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_UNKNOWN_EVENT",
            "native Realtime synthesis returned an unknown event",
        )

    def _accept_native_event_id(
        self, session: _SynthesisSession, event: Mapping[str, object]
    ) -> None:
        self._accept_bounded_native_event_id(
            session.native_event_ids,
            event,
            operation="synthesis",
        )

    def _accept_native_recognition_event_id(
        self, session: _RecognitionSession, event: Mapping[str, object]
    ) -> None:
        self._accept_bounded_native_event_id(
            session.native_event_ids,
            event,
            operation="recognition",
        )

    @staticmethod
    def _accept_bounded_native_event_id(
        event_ids: set[str],
        event: Mapping[str, object],
        *,
        operation: str,
    ) -> None:
        event_id = _safe_label(event.get("event_id"), "event_id")
        if event_id in event_ids:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_EVENT_REPLAY",
                f"native Realtime {operation} replayed a server event",
            )
        if len(event_ids) >= MAX_NATIVE_SERVER_EVENT_IDS:
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_EVENT_LIMIT",
                f"native Realtime {operation} exceeded the event identity limit",
            )
        event_ids.add(event_id)

    def _note_native_progress(self, session: _SynthesisSession) -> None:
        session.native_progress_deadline = (
            self._monotonic() + session.request.event_timeout_seconds
        )

    @staticmethod
    def _require_native_phase(
        session: _SynthesisSession,
        expected: _NativeSynthesisPhase,
        event_kind: object,
    ) -> None:
        if session.native_phase is not expected:
            OpenAIStreamingSpeechProvider._raise_native_phase(session, event_kind)

    @staticmethod
    def _raise_native_phase(session: _SynthesisSession, event_kind: object) -> None:
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_TURN_ORDER",
            (
                "native Realtime synthesis event is out of order "
                f"for phase {session.native_phase.value}: {event_kind}"
            ),
        )

    def _require_native_response_binding(
        self, session: _SynthesisSession, event: Mapping[str, object]
    ) -> None:
        if (
            session.provider_response_id is None
            or event.get("response_id", event.get("id")) != session.provider_response_id
        ):
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_RESPONSE_MISMATCH",
                "native Realtime synthesis event belongs to another response",
            )

    def _require_native_audio_binding(
        self, session: _SynthesisSession, event: Mapping[str, object]
    ) -> None:
        self._require_native_content_binding(session, event)

    def _require_native_content_binding(
        self, session: _SynthesisSession, event: Mapping[str, object]
    ) -> None:
        self._require_native_response_binding(session, event)
        if (
            session.provider_item_id is None
            or event.get("item_id") != session.provider_item_id
            or event.get("output_index") != 0
            or event.get("content_index") != 0
        ):
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_CONTENT_MISMATCH",
                "native Realtime synthesis changed its primary audio identity",
            )

    async def _publish_native_audio_buffer(self, session: _SynthesisSession) -> None:
        pcm = bytes(session.pending_native_audio)
        session.pending_native_audio.clear()
        frame_bytes = MAX_AUDIO_SAMPLES_PER_FRAME * 2
        for input_offset in range(0, len(pcm), MAX_PROVIDER_AUDIO_DELTA_BYTES):
            provider_chunk = pcm[
                input_offset : input_offset + MAX_PROVIDER_AUDIO_DELTA_BYTES
            ]
            output = _encode_s16le(
                session.resampler.feed(_decode_s16le(provider_chunk))
            )
            provider_chunk = b""
            for output_offset in range(0, len(output), frame_bytes):
                await self._publish_synthesis(
                    session,
                    SynthesisEventKind.CHUNK,
                    pcm=output[output_offset : output_offset + frame_bytes],
                )
            output = b""
        pcm = b""

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
        iterator = session.stream.__aiter__()
        while True:
            async with asyncio.timeout(session.request.event_timeout_seconds):
                event = await self._read_synthesis_sse_event(session, iterator)
            if event is None:
                return False
            if event:
                return True

    async def _read_synthesis_sse_event(
        self,
        session: _SynthesisSession,
        iterator: AsyncIterator[str],
    ) -> bool | None:
        """Read one complete SSE event without letting comments renew its budget."""

        data_lines: list[str] = []
        data_bytes = 0
        while True:
            try:
                line = await anext(iterator)
            except StopAsyncIteration:
                if data_lines:
                    return await self._consume_sse_event(session, "\n".join(data_lines))
                return None
            if session.closing:
                return None
            if len(line.encode("utf-8")) > MAX_SSE_LINE_BYTES:
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_SSE_LINE_LIMIT",
                    "speech Provider SSE line exceeds the limit",
                )
            if line == "":
                if data_lines:
                    return await self._consume_sse_event(session, "\n".join(data_lines))
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
            provider=self._provider_ref,
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

    async def _put_bounded(
        self, queue: asyncio.Queue[_QueueValue], value: _QueueValue
    ) -> None:
        """Hold the Provider reader on a full queue instead of killing the stream.

        A consumer that drains at real playout speed legitimately keeps this
        queue full for as long as one chunk takes to play. Refusing immediately
        turned that ordinary pacing into ``SPEECH_EVENT_QUEUE_EXHAUSTED`` and cut
        the audio off mid-utterance. The bound stays hard: a consumer that stops
        draining still exhausts the stream once the budget elapses, and nothing
        is buffered beyond ``MAX_EVENT_QUEUE``.
        """

        try:
            queue.put_nowait(value)
            return
        except asyncio.QueueFull:
            pass
        try:
            await asyncio.wait_for(
                queue.put(value), timeout=self._event_queue_wait_seconds
            )
        except (TimeoutError, asyncio.QueueFull) as exc:
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
            outcome = await self._finalize_recognition_session(
                session,
                cause=_RecognitionFinalizationCause.ROLLBACK,
            )
            _raise_recognition_finalization(outcome)
            return
        owns_conformance_settlement = conformance_started
        if socket is not None:
            await self._close_socket(socket)
        if owns_conformance_settlement:
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
            outcome = await self._finalize_synthesis_session(
                session,
                cause=_SynthesisFinalizationCause.ROLLBACK,
            )
            _raise_synthesis_finalization(outcome)
            return
        if conformance_started:
            with suppress(StreamingSpeechViolation):
                self._conformance.provider_closed_synthesis(ref)
            self._conformance.reap_terminal()

    async def _fail_recognition_transport(
        self, session: _RecognitionSession, exc: BaseException
    ) -> None:
        outcome = await self._finalize_recognition_session(
            session,
            cause=_RecognitionFinalizationCause.PROVIDER_FAILURE,
            trigger_failure=exc,
        )
        _raise_recognition_finalization(outcome)

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
            provider_id=self._provider_ref.provider_id,
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

    async def _settle_finalization_socket(
        self, failures: _FinalizationFailures, socket: RealtimeSocket
    ) -> None:
        if await failures.settle(
            self._close_socket(socket), incomplete_is_failure=False
        ):
            return
        await failures.settle(self._close_socket(socket))

    async def _settle_finalization_stream(
        self, failures: _FinalizationFailures, stream: SpeechSseStream
    ) -> None:
        if await failures.settle(
            self._close_stream(stream), incomplete_is_failure=False
        ):
            return
        await failures.settle(self._close_stream(stream))

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

    @staticmethod
    def _require_negotiated_recognition(session: _RecognitionSession) -> None:
        if not session.negotiated:
            raise OpenAIStreamingSpeechError(
                "RECOGNITION_SESSION_NOT_NEGOTIATED",
                "recognition session is not negotiated",
            )

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
    native_realtime = provider_name == "openai-realtime"
    selected_provider = _NATIVE_REALTIME_PROVIDER if native_realtime else _PROVIDER
    if (
        provider_name not in {"openai", "openai-realtime"}
        or not api_base
        or not api_key
    ):
        return await _configuration_fallback(
            target, degradation_sink, provider_id=selected_provider.provider_id
        )
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
            realtime_model=(
                str(env.get(SPEECH_REALTIME_MODEL_ENV) or "").strip()
                or DEFAULT_REALTIME_MODEL
                if native_realtime
                else None
            ),
        )
    except (OpenAIStreamingSpeechError, TypeError, ValueError):
        return await _configuration_fallback(
            target, degradation_sink, provider_id=selected_provider.provider_id
        )
    provider = OpenAIStreamingSpeechProvider(
        config,
        socket_factory=socket_factory,
        sse_factory=sse_factory,
        degradation_sink=degradation_sink,
    )
    return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)


async def _configuration_fallback(
    target: SpeechRouteTier,
    sink: DegradationSink | None,
    *,
    provider_id: str = _PROVIDER.provider_id,
) -> StreamingSpeechSelection:
    fact = _degradation_fact(
        operation="speech.route.select",
        reason=SpeechDegradationReason.CONFIGURATION_UNAVAILABLE,
        from_tier=SpeechRouteTier.STREAMING,
        to_tier=target,
        provider_id=provider_id,
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


def _same_cleanup(
    first: Callable[[], Awaitable[None]] | None,
    second: Callable[[], Awaitable[None]],
) -> bool:
    if first is second:
        return True
    first_self = getattr(first, "__self__", None)
    second_self = getattr(second, "__self__", None)
    first_function = getattr(first, "__func__", None)
    return (
        first_self is not None
        and first_self is second_self
        and first_function is not None
        and first_function is getattr(second, "__func__", None)
    )


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


def _cleanup_incomplete_failure() -> OpenAIStreamingSpeechError:
    return OpenAIStreamingSpeechError(
        "SPEECH_PROVIDER_CLEANUP_INCOMPLETE",
        "streaming Speech Provider cleanup is incomplete",
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
            "SPEECH_PROVIDER_CLEANUP_INCOMPLETE",
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


def _raise_recognition_finalization(
    outcome: _RecognitionFinalizationOutcome,
) -> None:
    if outcome.failure is not None:
        raise outcome.failure from None


def _raise_synthesis_finalization(
    outcome: _SynthesisFinalizationOutcome,
) -> None:
    if outcome.failure is not None:
        raise outcome.failure from None


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


def _realtime_url(api_base: str, *, model: str | None = None) -> str:
    """Build an official Realtime transcription or native-model URL.

    The legacy cascade opens with ``intent=transcription``; the native Adapter
    selects its Realtime model in the URL. In both modes the transcription
    snapshot is carried by the ``session.update`` payload as
    ``session.audio.input.transcription.model`` instead.
    """
    parsed = urlparse(api_base)
    path = f"{parsed.path.rstrip('/')}/realtime"
    query = (
        {"intent": "transcription"}
        if model is None
        else {"model": _safe_label(model, "realtime_model")}
    )
    return urlunparse(("wss", parsed.netloc, path, "", urlencode(query), ""))


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


def _recognition_session_update(
    config: OpenAIStreamingSpeechConfig,
    request: RecognitionStreamRequest,
) -> dict[str, object]:
    input_config: dict[str, object] = {
        "format": {"type": "audio/pcm", "rate": OPENAI_PCM_RATE_HZ},
        "transcription": {"model": config.stt_model},
        "turn_detection": _turn_detection_wire(request),
    }
    if config.realtime_model is None:
        session: dict[str, object] = {
            "type": "transcription",
            "audio": {"input": input_config},
        }
    else:
        session = {
            "type": "realtime",
            "output_modalities": ["audio"],
            "instructions": (
                "Do not answer the user. This session only transcribes committed "
                "input for an external authoritative agent."
            ),
            "audio": {
                "input": input_config,
                "output": {
                    "format": {"type": "audio/pcm", "rate": OPENAI_PCM_RATE_HZ},
                    "voice": config.tts_voice,
                },
            },
            "tools": [],
            "tool_choice": "none",
        }
    return {"type": "session.update", "session": session}


def _native_response_metadata(
    request: SynthesisStreamRequest,
) -> dict[str, object]:
    response = request.ref.response
    return {
        "live_voice_interaction_id": response.interaction_id,
        "live_voice_response_id": response.response_id,
        "live_voice_response_generation": str(response.response_generation),
        "live_voice_unit_id": request.ref.unit_id,
        "live_voice_unit_seq": str(request.ref.unit_seq),
        "live_voice_stream_id": request.ref.stream_id,
        "live_voice_stream_generation": str(request.ref.stream_generation),
    }


def _native_initial_response_matches(
    response: Mapping[str, object],
    *,
    expected_metadata: Mapping[str, object],
    expected_voice: str,
) -> bool:
    if not _NATIVE_RESPONSE_REQUIRED_FIELDS.issubset(response):
        return False
    audio = response.get("audio")
    audio_output = audio.get("output") if type(audio) is dict else None
    audio_format = audio_output.get("format") if type(audio_output) is dict else None
    return (
        response.get("object") == "realtime.response"
        and response.get("status") == "in_progress"
        and response.get("status_details") is None
        and response.get("usage") is None
        and response.get("output") == []
        and response.get("conversation_id") is None
        and response.get("output_modalities") == ["audio"]
        and response.get("metadata") == expected_metadata
        and type(audio_output) is dict
        and type(audio_format) is dict
        and audio_format.get("type") == "audio/pcm"
        and audio_format.get("rate") == OPENAI_PCM_RATE_HZ
        and audio_output.get("voice") == expected_voice
    )


def _native_terminal_output_matches(
    response: Mapping[str, object],
    *,
    expected_item_id: str | None,
    expected_text: str,
    expected_voice: str,
) -> bool:
    if not _NATIVE_RESPONSE_REQUIRED_FIELDS.issubset(response):
        return False
    output = response.get("output")
    if type(output) is not list or len(output) != 1 or expected_item_id is None:
        return False
    item = output[0]
    audio = response.get("audio")
    audio_output = audio.get("output") if type(audio) is dict else None
    audio_format = audio_output.get("format") if type(audio_output) is dict else None
    return (
        response.get("object") == "realtime.response"
        and response.get("status_details") is None
        and _native_terminal_usage_matches(response.get("usage"))
        and response.get("conversation_id") is None
        and response.get("output_modalities") == ["audio"]
        and type(audio_output) is dict
        and type(audio_format) is dict
        and audio_format.get("type") == "audio/pcm"
        and audio_format.get("rate") == OPENAI_PCM_RATE_HZ
        and audio_output.get("voice") == expected_voice
        and _native_output_message_matches(
            item,
            expected_item_id=expected_item_id,
            expected_text=expected_text,
        )
    )


def _native_terminal_usage_matches(value: object) -> bool:
    if type(value) is not dict:
        return False
    required_fields = {
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "input_token_details",
        "output_token_details",
    }
    if not required_fields.issubset(value):
        return False
    total_tokens = value.get("total_tokens")
    input_tokens = value.get("input_tokens")
    output_tokens = value.get("output_tokens")
    input_details = value.get("input_token_details")
    output_details = value.get("output_token_details")
    if not all(
        _is_nonnegative_int(count)
        for count in (total_tokens, input_tokens, output_tokens)
    ):
        return False
    if type(input_details) is not dict or type(output_details) is not dict:
        return False
    input_audio = input_details.get("audio_tokens")
    input_text = input_details.get("text_tokens")
    input_image = input_details.get("image_tokens", 0)
    cached_tokens = input_details.get("cached_tokens")
    output_audio = output_details.get("audio_tokens")
    output_text = output_details.get("text_tokens")
    if not all(
        _is_nonnegative_int(count)
        for count in (
            input_audio,
            input_text,
            input_image,
            cached_tokens,
            output_audio,
            output_text,
        )
    ):
        return False
    total_tokens = cast(int, total_tokens)
    input_tokens = cast(int, input_tokens)
    output_tokens = cast(int, output_tokens)
    input_audio = cast(int, input_audio)
    input_text = cast(int, input_text)
    input_image = cast(int, input_image)
    cached_tokens = cast(int, cached_tokens)
    output_audio = cast(int, output_audio)
    output_text = cast(int, output_text)
    if (
        total_tokens != input_tokens + output_tokens
        or input_tokens != input_audio + input_text + input_image
        or output_tokens != output_audio + output_text
        or cached_tokens > input_tokens
    ):
        return False
    cached_details = input_details.get("cached_tokens_details")
    if cached_details is None:
        return cached_tokens == 0
    if type(cached_details) is not dict:
        return False
    cached_audio = cached_details.get("audio_tokens", 0)
    cached_text = cached_details.get("text_tokens", 0)
    cached_image = cached_details.get("image_tokens", 0)
    return (
        all(
            _is_nonnegative_int(count)
            for count in (cached_audio, cached_text, cached_image)
        )
        and cached_tokens == cached_audio + cached_text + cached_image
    )


def _is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _native_output_message_matches(
    item: object,
    *,
    expected_item_id: str | None,
    expected_text: str,
) -> bool:
    if type(item) is not dict or expected_item_id is None:
        return False
    content = item.get("content")
    if type(content) is not list or len(content) != 1:
        return False
    part = content[0]
    return (
        item.get("id") == expected_item_id
        and item.get("type") == "message"
        and item.get("status") == "completed"
        and item.get("role") == "assistant"
        and type(part) is dict
        and part.get("type") == "output_audio"
        and part.get("transcript") == expected_text
    )


def _validate_realtime_synthesis_session(
    event: Mapping[str, object],
    *,
    expected_model: str,
    expected_voice: str,
) -> None:
    session = event.get("session")
    audio = session.get("audio") if type(session) is dict else None
    output = audio.get("output") if type(audio) is dict else None
    output_format = output.get("format") if type(output) is dict else None
    if (
        type(session) is not dict
        or session.get("type") != "realtime"
        or not _realtime_model_echo_accepted(session.get("model"), expected_model)
        or session.get("output_modalities") != ["audio"]
        or session.get("tools") != []
        or session.get("tool_choice") != "none"
        or type(output) is not dict
        or type(output_format) is not dict
        or output_format.get("type") != "audio/pcm"
        or output_format.get("rate") != OPENAI_PCM_RATE_HZ
        or output.get("voice") != expected_voice
    ):
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_SESSION_MISMATCH",
            "speech Provider changed the requested native Realtime synthesis contract",
        )


def _validate_transcription_session(
    event: Mapping[str, object],
    *,
    expected_model: str,
    expected_turn_detection: RecognitionTurnDetection,
    expected_realtime_model: str | None,
    expected_voice: str | None,
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
        native_realtime = expected_realtime_model is not None
        if (
            session.get("type") != ("realtime" if native_realtime else "transcription")
            or type(audio_format) is not dict
            or audio_format.get("type") != "audio/pcm"
            or audio_format.get("rate") != OPENAI_PCM_RATE_HZ
            or type(transcription) is not dict
            or transcription.get("model") != expected_model
            or "turn_detection" not in input_config
            or not _turn_detection_echo_accepted(
                input_config.get("turn_detection"),
                expected_turn_detection,
                require_response_controls=native_realtime,
            )
        ):
            raise OpenAIStreamingSpeechError(
                "SPEECH_PROVIDER_SESSION_MISMATCH",
                "speech Provider changed the requested transcription contract",
            )
        if native_realtime:
            assert expected_realtime_model is not None
            output_config = audio.get("output")
            output_format = (
                output_config.get("format") if type(output_config) is dict else None
            )
            if (
                not _realtime_model_echo_accepted(
                    session.get("model"), expected_realtime_model
                )
                or session.get("output_modalities") != ["audio"]
                or session.get("tools") != []
                or session.get("tool_choice") != "none"
                or type(output_config) is not dict
                or type(output_format) is not dict
                or output_format.get("type") != "audio/pcm"
                or output_format.get("rate") != OPENAI_PCM_RATE_HZ
                or output_config.get("voice") != expected_voice
            ):
                raise OpenAIStreamingSpeechError(
                    "SPEECH_PROVIDER_SESSION_MISMATCH",
                    "speech Provider changed the requested native Realtime contract",
                )
        return
    if expected_realtime_model is not None:
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_SESSION_MISMATCH",
            "native Realtime speech requires the current session contract",
        )
    # Earlier transcription-session shape retained only at the Adapter edge.
    transcription = session.get("input_audio_transcription")
    if (
        session.get("input_audio_format") != "pcm16"
        or type(transcription) is not dict
        or transcription.get("model") != expected_model
        or "turn_detection" not in session
        or not _turn_detection_echo_accepted(
            session.get("turn_detection"), expected_turn_detection
        )
    ):
        raise OpenAIStreamingSpeechError(
            "SPEECH_PROVIDER_SESSION_MISMATCH",
            "speech Provider changed the requested transcription contract",
        )


def _realtime_model_echo_accepted(value: object, expected: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        model = _safe_label(value, "realtime_model")
        configured = _safe_label(expected, "realtime_model")
    except OpenAIStreamingSpeechError:
        return False
    if not _supported_native_realtime_model(
        model
    ) or not _supported_native_realtime_model(configured):
        return False
    return model == configured or model.startswith(f"{configured}-")


def _supported_native_realtime_model(model: str) -> bool:
    return (
        model == "gpt-realtime" or model.startswith("gpt-realtime-")
    ) and not model.startswith(("gpt-realtime-translate", "gpt-realtime-whisper"))


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


def _turn_detection_echo_accepted(
    echo: object,
    detection: RecognitionTurnDetection,
    *,
    require_response_controls: bool = False,
) -> bool:
    """Compare the effective session echo against the negotiated detection.

    The request keeps sending ``create_response``/``interrupt_response`` so no
    session shape can auto-generate a response, but a GA transcription session
    owns no response and echoes neither field.  Byte equality with the request
    therefore rejects every real ``server_vad`` open, so compare the fields the
    transcription session actually governs and still fail closed on any
    unknown key or on response generation the Adapter never requested.
    """

    expected = _turn_detection_value(detection)
    if expected is None:
        return echo is None
    if type(echo) is not dict:
        return False
    governed = ("type", "threshold", "prefix_padding_ms", "silence_duration_ms")
    optional = ("create_response", "interrupt_response")
    if set(echo) - set(governed) - set(optional):
        return False
    if any(echo.get(field) != expected[field] for field in governed):
        return False
    if require_response_controls:
        return all(
            type(echo.get(field)) is bool and echo[field] is False for field in optional
        )
    return not any(echo.get(field) for field in optional)


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
    "DEFAULT_REALTIME_MODEL",
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
    "SPEECH_REALTIME_MODEL_ENV",
    "STREAMING_SPEECH_FLAG",
    "StreamingSpeechSelection",
    "select_environment_streaming_speech",
]
