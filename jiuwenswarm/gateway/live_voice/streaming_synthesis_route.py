# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded product owner for one native-streaming TTS route.

The Provider Adapter owns wire protocol and resampling.  This module owns the
product-facing lifetime between one exact ``ResponseRef``/unit request and
ordered 20 ms ``MediaAudioFrame`` values.  It does not claim browser playback,
write history, or retain text/audio after a stream is consumed or fenced.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import math
import struct
from array import array
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar, cast

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    ResponseRef,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechDegradationFact,
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
    MAX_STREAM_TIMEOUT_SECONDS,
    MAX_SYNTHESIS_TEXT_CHARS,
    NativeStreamingSpeechProvider,
    ProviderTransport,
    StreamingProviderCapability,
    StreamingSpeechViolation,
    StreamingSynthesisEvent,
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)


_LOGGER = logging.getLogger(__name__)
_DEFAULT_MAX_ACTIVE_STREAMS = 8
_DEFAULT_MAX_PENDING_FRAMES = 8
_DEFAULT_OPEN_TIMEOUT_SECONDS = 15.0
_DEFAULT_EVENT_TIMEOUT_SECONDS = 20.0
_DEFAULT_QUEUE_WAIT_SECONDS = 2.0
_PROVIDER_CLEANUP_TIMEOUT_SECONDS = 5.0
_MAX_ROUTE_IDENTITIES = 256
_DEFAULT_MAX_RETAINED_TASKS = 32
_CLEANUP_TASK_RESERVE = 4
# A retired identity surrenders its exact ledger entry and its retained handle,
# and keeps a compact tombstone instead.  Both fences only ever rise, so a
# digest collision can refuse a stream that could have run but can never admit
# a retired binding or a stale response that must stay refused.  The bound
# therefore limits the exact working set, not the number of streams one owner
# may serve.
_IDENTITY_ADMISSION_FENCE_BYTES = 1 << 20
_GENERATION_FENCE_ROWS = 4
_GENERATION_FENCE_CELLS = 1 << 13
_BINDING_IDENTITY_SCOPE = "synthesis.binding"
_RESPONSE_INTERACTION_SCOPE = "synthesis.response.interaction"
_RESPONSE_ID_SCOPE = "synthesis.response.id"
_PROCESS_CONTROL = (KeyboardInterrupt, SystemExit, GeneratorExit)

_T = TypeVar("_T")
StreamingSynthesisScopeIdentity = tuple[str, str, str]
_LEGACY_SYNTHESIS_SCOPE: StreamingSynthesisScopeIdentity = (
    "legacy-session",
    "legacy-subject",
    "legacy-correlation",
)
_ScopedStreamKey = tuple[StreamingSynthesisScopeIdentity, str, int]
_ScopedResponseKey = tuple[StreamingSynthesisScopeIdentity, str]


@dataclass(frozen=True, slots=True)
class _ExternalResult(Generic[_T]):
    value: _T | None = None
    process_control: BaseException | None = None


async def _capture_process_control(awaitable: Awaitable[_T]) -> _ExternalResult[_T]:
    """Keep process-control exceptions out of detached asyncio Tasks."""

    try:
        return _ExternalResult(value=await awaitable)
    except _PROCESS_CONTROL as exc:
        exc.__traceback__ = None
        exc.__context__ = None
        exc.__cause__ = None
        return _ExternalResult(process_control=exc)


def _discard_awaitable(awaitable: Awaitable[object]) -> None:
    if inspect.iscoroutine(awaitable):
        awaitable.close()
    elif isinstance(awaitable, asyncio.Future):
        awaitable.cancel()


class _OwnedWorkSuperseded(Exception):
    """One task this owner created was cancelled by this owner, not its caller.

    It never leaves this module: `_select` and `_begin_prepared` translate it
    into their existing selection and outcome vocabulary, so no new reason code
    or fallback action reaches any caller.
    """


@dataclass(slots=True)
class _SupersedableWork:
    """Owner-created work plus the caller-observable supersession signal.

    A caller's own WebSocket/RPC task is never stored here.  Close and
    successor supersession can therefore reach only the task this owner
    created, and the caller learns that it was superseded by observing
    `superseded` instead of losing its whole connection to a cancellation.
    """

    superseded: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    reason: StreamingSynthesisReason | None = field(default=None, repr=False)
    task: asyncio.Task[object] | None = field(default=None, repr=False)

    def adopt(self, task: asyncio.Task[object]) -> None:
        """Own one task this route created, never a caller's own task."""

        self.task = task
        if self.superseded.is_set():
            task.cancel()

    def withdraw(self) -> None:
        """Stop offering work that already left this owner's control."""

        self.task = None

    def supersede(
        self, reason: StreamingSynthesisReason
    ) -> asyncio.Task[object] | None:
        """Publish the first supersession truth, then offer owner-created work.

        The first reason wins, so a close following a successor cannot rewrite
        what the caller is told, and repeated supersession stays a no-op.
        """

        if not self.superseded.is_set():
            self.reason = reason
            self.superseded.set()
        return self.task


class _BoundedHardDeadlineOwner:
    """Bound all route-owned awaits, including cancellation-hostile Providers.

    A timed-out task is fenced immediately and remains strongly owned only until
    it really exits.  The fixed cap prevents a non-cooperative Provider from
    turning deadlines into unbounded retained work.
    """

    def __init__(self, *, max_tasks: int) -> None:
        self._max_tasks = max_tasks
        self._tasks: set[asyncio.Task[_ExternalResult[object]]] = set()
        self._reservations: set[object] = set()
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def retained_count(self) -> int:
        return len(self._tasks) + len(self._reservations)

    @property
    def capacity(self) -> int:
        return self._max_tasks + _CLEANUP_TASK_RESERVE

    def reserve(self) -> _TaskReservation | None:
        """Atomically reserve one normal task slot before caller side effects."""

        if len(self._tasks) + len(self._reservations) >= self._max_tasks:
            return None
        token = object()
        self._reservations.add(token)
        self._idle.clear()
        return _TaskReservation(self, token)

    async def run(
        self,
        awaitable: Awaitable[_T],
        *,
        timeout_seconds: float,
        operation: str,
        cleanup: bool = False,
        reservation: _TaskReservation | None = None,
        work: _SupersedableWork | None = None,
    ) -> _T:
        if reservation is not None:
            if cleanup or not reservation._consume(self):
                _discard_awaitable(cast(Awaitable[object], awaitable))
                raise StreamingSynthesisRouteViolation(
                    "INVALID_SYNTHESIS_TASK_RESERVATION",
                    "bounded route task reservation is invalid",
                )
        else:
            capacity = self._max_tasks + (_CLEANUP_TASK_RESERVE if cleanup else 0)
            if len(self._tasks) + len(self._reservations) >= capacity:
                _discard_awaitable(cast(Awaitable[object], awaitable))
                raise StreamingSynthesisRouteViolation(
                    "SYNTHESIS_RETAINED_TASK_CAPACITY_EXHAUSTED",
                    f"bounded route task capacity is exhausted for {operation}",
                )
        try:
            task = asyncio.create_task(
                _capture_process_control(awaitable),
                name=f"live-voice-streaming-tts-{operation}",
            )
        except BaseException:
            _discard_awaitable(cast(Awaitable[object], awaitable))
            self._set_idle_if_empty()
            raise
        owned = cast(asyncio.Task[_ExternalResult[object]], task)
        self._tasks.add(owned)
        self._idle.clear()
        owned.add_done_callback(self._consume_done)
        if work is not None:
            work.adopt(cast(asyncio.Task[object], owned))
        try:
            done, _ = await asyncio.wait((task,), timeout=timeout_seconds)
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            if work is not None:
                work.withdraw()
        if not done:
            task.cancel()
            raise TimeoutError(f"hard deadline expired for {operation}")
        self._tasks.discard(owned)
        self._set_idle_if_empty()
        if work is not None and task.cancelled():
            # Only this owner ever cancels a task it created, and only after
            # publishing supersession.  The caller's own task was untouched, so
            # this must never surface to it as its own cancellation.
            raise _OwnedWorkSuperseded(operation)
        result = task.result()
        if result.process_control is not None:
            raise result.process_control
        return cast(_T, result.value)

    async def cancel_and_wait(
        self,
        tasks: tuple[asyncio.Task[object], ...],
        *,
        timeout_seconds: float,
        operation: str,
    ) -> None:
        current = asyncio.current_task()
        pending = tuple(task for task in tasks if task is not current)
        for task in pending:
            task.cancel()
        if not pending:
            return
        done, not_done = await asyncio.wait(pending, timeout=timeout_seconds)
        for task in not_done:
            task.cancel()
        process_control: BaseException | None = None
        for task in done:
            try:
                task.result()
            except asyncio.CancelledError:
                continue
            except _PROCESS_CONTROL as exc:
                if process_control is None:
                    process_control = exc
            except BaseException:
                continue
        if process_control is not None:
            raise process_control
        if not_done:
            raise StreamingSynthesisRouteViolation(
                "SYNTHESIS_TASK_CLEANUP_TIMEOUT",
                f"bounded task cleanup expired for {operation}",
            )

    async def drain(self, *, timeout_seconds: float) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout_seconds)

    async def wait_until_idle(self) -> None:
        await self._idle.wait()

    def _release_reservation(self, token: object) -> None:
        self._reservations.discard(token)
        self._set_idle_if_empty()

    def _consume_reservation(self, token: object) -> bool:
        if token not in self._reservations:
            return False
        self._reservations.remove(token)
        return True

    def _set_idle_if_empty(self) -> None:
        if not self._tasks and not self._reservations:
            self._idle.set()

    def _consume_done(self, task: asyncio.Task[_ExternalResult[object]]) -> None:
        self._tasks.discard(task)
        self._set_idle_if_empty()
        try:
            task.exception()
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit, GeneratorExit):
            return


@dataclass(slots=True)
class _TaskReservation:
    _owner: _BoundedHardDeadlineOwner = field(repr=False)
    _token: object = field(repr=False)
    _active: bool = field(default=True, repr=False)

    def release(self) -> None:
        if self._active:
            self._active = False
            self._owner._release_reservation(self._token)

    def _consume(self, owner: _BoundedHardDeadlineOwner) -> bool:
        if not self._active or self._owner is not owner:
            return False
        if not owner._consume_reservation(self._token):
            return False
        self._active = False
        return True


class StreamingSynthesisRouteViolation(ValueError):
    """A fail-closed caller or route-contract violation."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class StreamingSynthesisFallbackAction(StrEnum):
    NONE = "none"
    BATCH_ELIGIBLE = "batch_eligible"
    TEXT_OR_RETRY = "text_or_retry"


class StreamingSynthesisReason(StrEnum):
    FEATURE_OFF = "STREAMING_SPEECH_FEATURE_OFF"
    CONFIGURATION_UNAVAILABLE = "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "STREAMING_SPEECH_PROVIDER_UNAVAILABLE"
    PROVIDER_PROTOCOL = "STREAMING_SPEECH_PROVIDER_PROTOCOL"
    PROVIDER_TIMEOUT = "STREAMING_SPEECH_PROVIDER_TIMEOUT"
    QUEUE_EXHAUSTED = "STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED"
    CAPACITY_EXHAUSTED = "STREAMING_SYNTHESIS_ROUTE_CAPACITY_EXHAUSTED"
    ROUTE_ABORTED = "STREAMING_SYNTHESIS_ROUTE_ABORTED"
    RESPONSE_SUPERSEDED = "STREAMING_SYNTHESIS_RESPONSE_SUPERSEDED"
    OWNER_CLOSED = "STREAMING_SYNTHESIS_OWNER_CLOSED"


@dataclass(frozen=True, slots=True)
class StreamingSynthesisCapabilityProvenance:
    """Exact, content-free capability facts attached to every route result."""

    provider: ProviderRef
    available: bool
    modes: frozenset[SpeechMode]
    transport: ProviderTransport
    ordered_events: CapabilityProvenance
    exact_audio_cursor: CapabilityProvenance
    provider_cancel_ack: CapabilityProvenance
    chunk_text_spans: CapabilityProvenance

    def safe_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider.provider_id,
            "provider_implementation_class": self.provider.implementation_class,
            "provider_fallback_from": self.provider.fallback_from,
            "provider_available": self.available,
            "synthesis_modes": tuple(sorted(mode.value for mode in self.modes)),
            "transport": self.transport.value,
            "ordered_events": self.ordered_events.value,
            "exact_audio_cursor": self.exact_audio_cursor.value,
            "provider_cancel_ack": self.provider_cancel_ack.value,
            "chunk_text_spans": self.chunk_text_spans.value,
        }


@dataclass(frozen=True, slots=True)
class StreamingSynthesisRouteFact:
    """Content-free degradation/terminal fact for UI, logs, and X-OBS."""

    binding_ref: str
    reason: StreamingSynthesisReason
    fallback_action: StreamingSynthesisFallbackAction
    first_audio_emitted: bool
    provider_id: str
    provider_implementation_class: str | None
    provider_fallback_from: str | None
    provider_available: bool
    synthesis_modes: tuple[str, ...]
    transport: ProviderTransport
    ordered_events: CapabilityProvenance
    exact_audio_cursor: CapabilityProvenance
    provider_cancel_ack: CapabilityProvenance
    chunk_text_spans: CapabilityProvenance
    visible: bool = True
    operation: str = "speech.synthesis.stream"
    x_obs_event: str = "live_voice.speech.degradation"
    x_obs_metric: str | None = "live_voice.failure_total"
    metric_value: int | None = 1

    def safe_dict(self) -> dict[str, object]:
        return {
            "binding_ref": self.binding_ref,
            "operation": self.operation,
            "reason": self.reason.value,
            "fallback_action": self.fallback_action.value,
            "first_audio_emitted": self.first_audio_emitted,
            "provider_id": self.provider_id,
            "provider_implementation_class": self.provider_implementation_class,
            "provider_fallback_from": self.provider_fallback_from,
            "provider_available": self.provider_available,
            "synthesis_modes": self.synthesis_modes,
            "transport": self.transport.value,
            "ordered_events": self.ordered_events.value,
            "exact_audio_cursor": self.exact_audio_cursor.value,
            "provider_cancel_ack": self.provider_cancel_ack.value,
            "chunk_text_spans": self.chunk_text_spans.value,
            "visible": self.visible,
            "x_obs_event": self.x_obs_event,
            "x_obs_metric": self.x_obs_metric,
            "metric_value": self.metric_value,
        }


@dataclass(frozen=True, slots=True)
class StreamingSynthesisOutcome:
    ref: SynthesisStreamRef | None
    request_binding_ref: str
    completed: bool
    first_audio_emitted: bool
    batch_eligible: bool
    provider_id: str
    provider: ProviderRef | None
    capability: StreamingSynthesisCapabilityProvenance | None
    reason: StreamingSynthesisReason | None
    fact: StreamingSynthesisRouteFact | None


@dataclass(frozen=True, slots=True)
class StreamingSynthesisChunk:
    """One exact, content-hidden media frame derived from Provider PCM."""

    ref: SynthesisStreamRef
    request_binding_ref: str
    provider: ProviderRef
    capability: StreamingSynthesisCapabilityProvenance
    frame: MediaAudioFrame = field(repr=False)
    source_event_seq: int
    provider_cursor_through: int

    def safe_metadata(self) -> dict[str, object]:
        return {
            "request_binding_ref": self.request_binding_ref,
            "interaction_id": self.ref.response.interaction_id,
            "response_id": self.ref.response.response_id,
            "response_generation": self.ref.response.response_generation,
            "unit_id": self.ref.unit_id,
            "unit_seq": self.ref.unit_seq,
            "frame_seq": self.frame.seq,
            "sample_cursor": self.frame.sample_cursor,
            "sample_count": len(self.frame.samples),
            "provider_id": self.provider.provider_id,
            "provider_implementation_class": self.provider.implementation_class,
            "provider_fallback_from": self.provider.fallback_from,
            "provider_available": self.capability.available,
            "synthesis_modes": tuple(
                sorted(mode.value for mode in self.capability.modes)
            ),
            "transport": self.capability.transport.value,
            "ordered_events": self.capability.ordered_events.value,
            "exact_audio_cursor": self.capability.exact_audio_cursor.value,
            "provider_cancel_ack": self.capability.provider_cancel_ack.value,
            "chunk_text_spans": self.capability.chunk_text_spans.value,
            "source_event_seq": self.source_event_seq,
            "provider_cursor_through": self.provider_cursor_through,
        }


@dataclass(frozen=True, slots=True)
class StreamingSynthesisPull:
    chunk: StreamingSynthesisChunk | None
    outcome: StreamingSynthesisOutcome | None

    def __post_init__(self) -> None:
        if (self.chunk is None) == (self.outcome is None):
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_PULL",
                "a synthesis pull must contain exactly one chunk or outcome",
            )


@dataclass(frozen=True, slots=True)
class _TerminalSignal:
    outcome: StreamingSynthesisOutcome


@dataclass(slots=True)
class _PreparedSynthesisRequest:
    """Validated request whose representation cannot expose text or PCM."""

    ref: SynthesisStreamRef
    binding_ref: str
    sample_rate_hz: int
    event_timeout_seconds: float
    _payload: SynthesisStreamRequest = field(repr=False)
    open_attempted: bool = field(default=False, repr=False)


@dataclass(frozen=True, slots=True)
class _CloseResult:
    process_control: BaseException | None = field(default=None, repr=False)
    cleanup_complete: bool = True


_QueueValue = StreamingSynthesisChunk | _TerminalSignal


@dataclass(slots=True)
class StreamingSynthesisHandle:
    ref: SynthesisStreamRef
    request_binding_ref: str
    scope_identity: StreamingSynthesisScopeIdentity
    sample_rate_hz: int
    event_timeout_seconds: float
    provider_ref: ProviderRef
    capability: StreamingSynthesisCapabilityProvenance
    provider: NativeStreamingSpeechProvider = field(repr=False)
    queue: asyncio.Queue[_QueueValue] = field(repr=False)
    provider_cancel_completion: asyncio.Future[bool] | None = field(
        default=None, repr=False
    )
    provider_cleanup_complete: bool = field(default=False, repr=False)
    producer_task: asyncio.Task[None] | None = field(default=None, repr=False)
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    pull_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    cleanup_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    next_provider_seq: int = 0
    next_provider_cursor: int = 0
    next_frame_seq: int = 0
    next_frame_cursor: int = 0
    started: bool = False
    first_audio_emitted: bool = False
    terminal_delivered: bool = False
    fenced: bool = False
    outcome: StreamingSynthesisOutcome | None = None
    cleanup_complete: bool = False
    cleanup_done: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    terminal_ready: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    process_control: BaseException | None = field(default=None, repr=False)


StreamingSpeechSelector = Callable[[], Awaitable[StreamingSpeechSelection]]


class StreamingSynthesisRouteOwner:
    """Lazy, bounded owner for concurrent, exact-response TTS streams."""

    def __init__(
        self,
        selector: StreamingSpeechSelector,
        *,
        max_active_streams: int = _DEFAULT_MAX_ACTIVE_STREAMS,
        max_pending_frames: int = _DEFAULT_MAX_PENDING_FRAMES,
        open_timeout_seconds: float = _DEFAULT_OPEN_TIMEOUT_SECONDS,
        event_timeout_seconds: float = _DEFAULT_EVENT_TIMEOUT_SECONDS,
        queue_wait_seconds: float = _DEFAULT_QUEUE_WAIT_SECONDS,
        max_retained_tasks: int = _DEFAULT_MAX_RETAINED_TASKS,
    ) -> None:
        if not callable(selector):
            raise TypeError("streaming Speech selector must be callable")
        _bounded_positive_int(
            max_active_streams, "max_active_streams", _DEFAULT_MAX_ACTIVE_STREAMS
        )
        _bounded_positive_int(
            max_pending_frames, "max_pending_frames", _DEFAULT_MAX_PENDING_FRAMES
        )
        _bounded_timeout(open_timeout_seconds, "open_timeout_seconds")
        _bounded_timeout(event_timeout_seconds, "event_timeout_seconds")
        _bounded_timeout(queue_wait_seconds, "queue_wait_seconds")
        _bounded_positive_int(
            max_retained_tasks, "max_retained_tasks", _DEFAULT_MAX_RETAINED_TASKS
        )
        self._selector = selector
        self._max_active_streams = max_active_streams
        self._max_pending_frames = max_pending_frames
        self._open_timeout_seconds = float(open_timeout_seconds)
        self._event_timeout_seconds = float(event_timeout_seconds)
        self._queue_wait_seconds = float(queue_wait_seconds)
        self._task_owner = _BoundedHardDeadlineOwner(max_tasks=max_retained_tasks)
        self._selection_lock = asyncio.Lock()
        self._begin_lock = asyncio.Lock()
        self._provider_open_lock = asyncio.Lock()
        self._provider_close_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._close_start_lock = asyncio.Lock()
        self._selection: StreamingSpeechSelection | None = None
        # Selection and opening work are owner-created tasks, never the
        # caller's WebSocket/RPC task.  Close and successor supersession may
        # cancel only what is reachable through these records.
        self._selection_work: _SupersedableWork | None = None
        self._selection_attempt: object | None = None
        self._active: dict[_ScopedStreamKey, StreamingSynthesisHandle] = {}
        self._opening: dict[_ScopedStreamKey, _SupersedableWork] = {}
        self._opening_responses: dict[_ScopedStreamKey, ResponseRef] = {}
        self._current_responses: OrderedDict[_ScopedResponseKey, ResponseRef] = (
            OrderedDict()
        )
        self._retained_bindings: OrderedDict[_ScopedStreamKey, str] = OrderedDict()
        self._known_handles: dict[_ScopedStreamKey, StreamingSynthesisHandle] = {}
        # Fail-closed retirement tombstones.  A retired binding stays refusable
        # as a reuse, and a retired interaction keeps a conservative maximum
        # response generation, without holding their exact entries.
        self._identity_admission_fence = bytearray(_IDENTITY_ADMISSION_FENCE_BYTES)
        self._generation_fence = tuple(
            array("Q", [0]) * _GENERATION_FENCE_CELLS
            for _ in range(_GENERATION_FENCE_ROWS)
        )
        self._provider_close_completed: set[int] = set()
        self._close_task: asyncio.Task[_CloseResult] | None = None
        self._close_cleanup_complete = False
        self._closed = False

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def retained_task_count(self) -> int:
        return self._task_owner.retained_count

    @property
    def retained_task_capacity(self) -> int:
        return self._task_owner.capacity

    @property
    def selection_degradation(self) -> dict[str, object] | None:
        selection = self._selection
        if selection is None or not isinstance(selection.fact, SpeechDegradationFact):
            return None
        safe = selection.fact.safe_dict()
        safe["provider_id"] = _safe_provider_id(safe.get("provider_id"))
        return safe

    async def available(self) -> bool:
        """Return truthful streaming-synthesis availability without opening it."""

        if self._closed:
            return False
        selection = await self._select()
        provider = selection.provider
        if selection.tier is not SpeechRouteTier.STREAMING or provider is None:
            return False
        try:
            capability = provider.capability
            conformance_capability = provider.conformance.capability
        except _PROCESS_CONTROL:
            raise
        except BaseException:
            return False
        return bool(
            capability == conformance_capability
            and capability.available
            and SpeechMode.STREAM in capability.synthesis.modes
            and capability.synthesis.transport is ProviderTransport.NATIVE_STREAM
            and capability.synthesis.chunk_text_spans
            is CapabilityProvenance.UNAVAILABLE
        )

    async def begin(
        self,
        request: SynthesisStreamRequest,
        *,
        scope_identity: StreamingSynthesisScopeIdentity | None = None,
    ) -> tuple[StreamingSynthesisHandle | None, StreamingSynthesisOutcome | None]:
        scope = _synthesis_scope_identity(scope_identity)
        prepared, validation_failure = _prepare_synthesis_request(request)
        request = None  # type: ignore[assignment]  # raw text leaves throwing frames
        if prepared is None:
            assert validation_failure is not None
            raise StreamingSynthesisRouteViolation(*validation_failure) from None
        return await self._begin_prepared(prepared, scope)

    async def _begin_prepared(
        self,
        prepared: _PreparedSynthesisRequest,
        scope_identity: StreamingSynthesisScopeIdentity,
    ) -> tuple[StreamingSynthesisHandle | None, StreamingSynthesisOutcome | None]:
        binding_ref = prepared.binding_ref
        ref = prepared.ref
        if self._closed:
            return None, self._failure_outcome(
                binding_ref,
                StreamingSynthesisReason.OWNER_CLOSED,
                ref=ref,
                first_audio_emitted=False,
                allow_batch=False,
                allow_fallback=False,
            )
        selection = await self._select()
        provider = selection.provider
        declared_capability: StreamingProviderCapability | None = None
        if provider is not None:
            try:
                declared_capability = provider.capability
            except _PROCESS_CONTROL:
                raise
            except BaseException:
                provider = None
        if (
            selection.tier is not SpeechRouteTier.STREAMING
            or provider is None
            or declared_capability is None
            or not declared_capability.available
            or SpeechMode.STREAM not in declared_capability.synthesis.modes
            or declared_capability.synthesis.transport
            is not ProviderTransport.NATIVE_STREAM
        ):
            reason = self._selection_reason(selection.fact)
            return None, self._failure_outcome(
                binding_ref,
                reason,
                ref=ref,
                first_audio_emitted=False,
                allow_batch=selection.tier is SpeechRouteTier.BATCH,
                provider_id=(
                    selection.fact.provider_id
                    if isinstance(selection.fact, SpeechDegradationFact)
                    else "unavailable"
                ),
            )
        try:
            capability = _capability_provenance(declared_capability)
        except StreamingSynthesisRouteViolation:
            return None, self._failure_outcome(
                binding_ref,
                StreamingSynthesisReason.PROVIDER_PROTOCOL,
                ref=ref,
                first_audio_emitted=False,
                allow_batch=True,
            )
        if capability.chunk_text_spans is not CapabilityProvenance.UNAVAILABLE:
            # This owner emits content-hidden audio frames only.  A Provider
            # span claim cannot be advertised until strict span validation and
            # route propagation are implemented together.
            return None, self._failure_outcome(
                binding_ref,
                StreamingSynthesisReason.PROVIDER_PROTOCOL,
                ref=ref,
                first_audio_emitted=False,
                allow_batch=True,
                capability=capability,
            )
        try:
            capability_matches = provider.conformance.capability == declared_capability
        except _PROCESS_CONTROL:
            raise
        except BaseException:
            capability_matches = False
        if not capability_matches:
            return None, self._failure_outcome(
                binding_ref,
                StreamingSynthesisReason.PROVIDER_PROTOCOL,
                ref=ref,
                first_audio_emitted=False,
                allow_batch=True,
                capability=capability,
            )

        key = _scoped_stream_key(scope_identity, ref)
        if asyncio.current_task() is None:
            raise RuntimeError("streaming synthesis begin requires an asyncio task")

        # The caller's own task never becomes route state.  Only the opening
        # task created below is supersedable, so close or a successor can never
        # cancel the connection request task this call arrived on.
        work = _SupersedableWork()
        opening_registered = False
        open_reservation: _TaskReservation | None = None
        try:
            async with self._begin_lock:
                if self._closed:
                    return None, self._failure_outcome(
                        binding_ref,
                        StreamingSynthesisReason.OWNER_CLOSED,
                        ref=ref,
                        first_audio_emitted=False,
                        allow_batch=False,
                        allow_fallback=False,
                        capability=capability,
                    )
                if (
                    self._retained_bindings.get(key) is not None
                    or self._retired_binding(key)
                    or key in self._opening
                ):
                    raise StreamingSynthesisRouteViolation(
                        "SYNTHESIS_STREAM_REUSED",
                        "a synthesis stream generation cannot be reused",
                    )
                self._preflight_response(ref.response, scope_identity)
                if not self._binding_capacity_available(key):
                    # Every retained identity still owns a live stream.  That is
                    # the same bounded-capacity refusal as the active-stream and
                    # task-slot walls below, so it reuses their existing typed
                    # fallback instead of failing the caller's handler.
                    return None, self._failure_outcome(
                        binding_ref,
                        StreamingSynthesisReason.CAPACITY_EXHAUSTED,
                        ref=ref,
                        first_audio_emitted=False,
                        allow_batch=True,
                        capability=capability,
                    )
                if len(self._active) + len(self._opening) >= self._max_active_streams:
                    return None, self._failure_outcome(
                        binding_ref,
                        StreamingSynthesisReason.CAPACITY_EXHAUSTED,
                        ref=ref,
                        first_audio_emitted=False,
                        allow_batch=True,
                        capability=capability,
                    )
                open_reservation = self._task_owner.reserve()
                if open_reservation is None:
                    return None, self._failure_outcome(
                        binding_ref,
                        StreamingSynthesisReason.CAPACITY_EXHAUSTED,
                        ref=ref,
                        first_audio_emitted=False,
                        allow_batch=True,
                        capability=capability,
                    )
                # A hard task slot precedes identity, response, Provider-open,
                # and cleanup effects.  Once response activation may mutate,
                # retain the binding as an anti-replay tombstone.
                self._make_binding_capacity(key)
                self._retained_bindings[key] = binding_ref
                self._opening[key] = work
                self._opening_responses[key] = ref.response
                opening_registered = True
                await self._activate_response(
                    provider, ref.response, scope_identity, own_work=work
                )
                if self._closed:
                    return None, self._failure_outcome(
                        binding_ref,
                        StreamingSynthesisReason.OWNER_CLOSED,
                        ref=ref,
                        first_audio_emitted=False,
                        allow_batch=False,
                        allow_fallback=False,
                        capability=capability,
                    )

            try:
                await self._task_owner.run(
                    self._open_provider_guarded(provider, prepared, key=key, work=work),
                    timeout_seconds=self._open_timeout_seconds,
                    operation="provider-open",
                    reservation=open_reservation,
                    work=work,
                )
            except _OwnedWorkSuperseded:
                # Close or a successor superseded this owner-created open.  The
                # caller keeps its own task and stays usable for later RPCs, and
                # the Provider effect was already settled inside the task that
                # was cancelled, so nothing is left for this frame to clean up.
                return None, self._failure_outcome(
                    binding_ref,
                    self._supersession_reason(work),
                    ref=ref,
                    first_audio_emitted=False,
                    allow_batch=False,
                    allow_fallback=False,
                    capability=capability,
                )
            except asyncio.CancelledError as caller_cancel:
                if prepared.open_attempted:
                    try:
                        await self._cancel_provider(
                            provider, ref, reason="begin_cancel"
                        )
                    except (
                        asyncio.CancelledError,
                        KeyboardInterrupt,
                        SystemExit,
                        GeneratorExit,
                    ):
                        pass
                raise caller_cancel
            except (KeyboardInterrupt, SystemExit, GeneratorExit) as caught_control:
                if prepared.open_attempted:
                    try:
                        await self._cancel_provider(
                            provider, ref, reason="process_control"
                        )
                    except (
                        asyncio.CancelledError,
                        KeyboardInterrupt,
                        SystemExit,
                        GeneratorExit,
                    ):
                        pass
                raise caught_control
            except BaseException as exc:
                reason = _reason_for_exception(exc)
                del exc
                if prepared.open_attempted:
                    await self._cancel_provider(provider, ref, reason="open_failure")
                return None, self._failure_outcome(
                    binding_ref,
                    reason,
                    ref=ref,
                    first_audio_emitted=False,
                    allow_batch=True,
                    capability=capability,
                )
        finally:
            if open_reservation is not None:
                open_reservation.release()
            if opening_registered and self._opening.get(key) is work:
                del self._opening[key]
                self._opening_responses.pop(key, None)

        handle: StreamingSynthesisHandle | None = None
        try:
            if self._closed:
                await self._cancel_provider(provider, ref, reason="owner_close")
                return None, self._failure_outcome(
                    binding_ref,
                    StreamingSynthesisReason.OWNER_CLOSED,
                    ref=ref,
                    first_audio_emitted=False,
                    allow_batch=False,
                    allow_fallback=False,
                    capability=capability,
                )
            handle = StreamingSynthesisHandle(
                ref=ref,
                request_binding_ref=binding_ref,
                scope_identity=scope_identity,
                sample_rate_hz=prepared.sample_rate_hz,
                event_timeout_seconds=prepared.event_timeout_seconds,
                provider_ref=declared_capability.provider,
                capability=capability,
                provider=provider,
                queue=asyncio.Queue(self._max_pending_frames),
            )
            async with self._lifecycle_lock:
                closed_after_open = self._closed
                if not closed_after_open:
                    self._active[key] = handle
                    self._known_handles[key] = handle
            if closed_after_open:
                await self._cancel_provider(provider, ref, reason="owner_close")
                return None, self._failure_outcome(
                    binding_ref,
                    StreamingSynthesisReason.OWNER_CLOSED,
                    ref=ref,
                    first_audio_emitted=False,
                    allow_batch=False,
                    allow_fallback=False,
                    capability=capability,
                )
            handle.producer_task = asyncio.create_task(
                self._produce(handle),
                name=(
                    f"live-voice-streaming-tts-{ref.stream_id}-{ref.stream_generation}"
                ),
            )
        except asyncio.CancelledError as caller_cancel:
            try:
                await self._discard_unstarted(key, handle)
                await self._cancel_provider(provider, ref, reason="begin_cancel")
            except (
                asyncio.CancelledError,
                KeyboardInterrupt,
                SystemExit,
                GeneratorExit,
            ):
                pass
            raise caller_cancel
        except _PROCESS_CONTROL as process_control:
            try:
                await self._discard_unstarted(key, handle)
                await self._cancel_provider(provider, ref, reason="process_control")
            except (
                asyncio.CancelledError,
                KeyboardInterrupt,
                SystemExit,
                GeneratorExit,
            ):
                pass
            raise process_control
        except BaseException as exc:
            await self._discard_unstarted(key, handle)
            reason = _reason_for_exception(exc)
            del exc
            await self._cancel_provider(provider, ref, reason="open_failure")
            return None, self._failure_outcome(
                binding_ref,
                reason,
                ref=ref,
                first_audio_emitted=False,
                allow_batch=True,
                capability=capability,
            )
        return handle, None

    async def next_chunk(
        self,
        handle: StreamingSynthesisHandle,
        *,
        timeout_seconds: float | None = None,
    ) -> StreamingSynthesisPull:
        self._require_handle(handle)
        timeout = (
            self._event_timeout_seconds
            if timeout_seconds is None
            else _bounded_timeout(timeout_seconds, "timeout_seconds")
        )
        try:
            async with handle.pull_lock:
                return await self._next_chunk_locked(handle, timeout=timeout)
        except asyncio.CancelledError as caller_cancel:
            await self._cleanup_interrupted_pull(handle)
            raise caller_cancel
        except (KeyboardInterrupt, SystemExit, GeneratorExit) as process_control:
            await self._cleanup_interrupted_pull(handle)
            raise process_control

    async def _next_chunk_locked(
        self, handle: StreamingSynthesisHandle, *, timeout: float
    ) -> StreamingSynthesisPull:
        deferred_control = await self._take_process_control(handle)
        if deferred_control is not None:
            await self._retire(handle)
            raise deferred_control
        async with handle.state_lock:
            if handle.terminal_delivered and handle.outcome is not None:
                if not handle.outcome.completed:
                    _drain_queue(handle.queue)
                return StreamingSynthesisPull(None, handle.outcome)
            if handle.outcome is not None and not handle.outcome.completed:
                _drain_queue(handle.queue)
                handle.terminal_delivered = True
                return StreamingSynthesisPull(None, handle.outcome)
        try:
            item = await self._task_owner.run(
                handle.queue.get(),
                timeout_seconds=timeout,
                operation="queue-get",
            )
        except TimeoutError:
            outcome = await self._terminate(
                handle,
                StreamingSynthesisReason.PROVIDER_TIMEOUT,
                allow_batch=True,
                cancel_provider=True,
            )
            return StreamingSynthesisPull(None, outcome)
        except StreamingSynthesisRouteViolation as capacity_error:
            if capacity_error.reason != "SYNTHESIS_RETAINED_TASK_CAPACITY_EXHAUSTED":
                raise
            outcome = await self._terminate(
                handle,
                StreamingSynthesisReason.CAPACITY_EXHAUSTED,
                allow_batch=True,
                cancel_provider=True,
            )
            return StreamingSynthesisPull(None, outcome)

        late_control = await self._take_process_control(handle)
        if late_control is not None:
            await self._retire(handle)
            raise late_control
        if isinstance(item, _TerminalSignal):
            async with handle.state_lock:
                if handle.outcome is not None and not handle.outcome.completed:
                    item = _TerminalSignal(handle.outcome)
                elif item.outcome.completed:
                    item = _TerminalSignal(
                        StreamingSynthesisOutcome(
                            ref=handle.ref,
                            request_binding_ref=handle.request_binding_ref,
                            completed=True,
                            first_audio_emitted=handle.first_audio_emitted,
                            batch_eligible=False,
                            provider_id=handle.provider_ref.provider_id,
                            provider=handle.provider_ref,
                            capability=handle.capability,
                            reason=None,
                            fact=None,
                        )
                    )
                handle.terminal_delivered = True
                handle.outcome = item.outcome
                if not item.outcome.completed:
                    _drain_queue(handle.queue)
            await self._retire(handle)
            return StreamingSynthesisPull(None, item.outcome)

        async with handle.state_lock:
            if handle.outcome is not None and not handle.outcome.completed:
                handle.terminal_delivered = True
                return StreamingSynthesisPull(None, handle.outcome)
            if handle.fenced and (
                handle.outcome is None or not handle.outcome.completed
            ):
                raise StreamingSynthesisRouteViolation(
                    "SYNTHESIS_OUTPUT_FENCED",
                    "fenced synthesis cannot emit another audio frame",
                )
            handle.first_audio_emitted = True
        return StreamingSynthesisPull(item, None)

    async def _cleanup_interrupted_pull(self, handle: StreamingSynthesisHandle) -> None:
        try:
            await self._terminate(
                handle,
                StreamingSynthesisReason.ROUTE_ABORTED,
                allow_batch=False,
                cancel_provider=True,
            )
        except (
            asyncio.CancelledError,
            KeyboardInterrupt,
            SystemExit,
            GeneratorExit,
        ):
            pass

    async def cancel(
        self,
        handle: StreamingSynthesisHandle,
        *,
        reason: StreamingSynthesisReason = StreamingSynthesisReason.ROUTE_ABORTED,
    ) -> StreamingSynthesisOutcome:
        self._require_handle(handle)
        if reason not in {
            StreamingSynthesisReason.ROUTE_ABORTED,
            StreamingSynthesisReason.RESPONSE_SUPERSEDED,
            StreamingSynthesisReason.OWNER_CLOSED,
        }:
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_CANCEL_REASON",
                "route cancel must use a closed non-fallback reason",
            )
        try:
            return await self._terminate(
                handle, reason, allow_batch=False, cancel_provider=True
            )
        except asyncio.CancelledError as caller_cancel:
            try:
                await self._terminate(
                    handle, reason, allow_batch=False, cancel_provider=True
                )
            except (
                asyncio.CancelledError,
                KeyboardInterrupt,
                SystemExit,
                GeneratorExit,
            ):
                pass
            raise caller_cancel

    async def wait_for_retained_cleanup(
        self, handle: StreamingSynthesisHandle
    ) -> bool:
        """Boundedly join this handle's retained Provider cancellation."""

        self._require_handle(handle)
        completion = handle.provider_cancel_completion
        if completion is None or completion.done():
            return True
        try:
            await asyncio.wait_for(
                asyncio.shield(completion),
                timeout=_PROVIDER_CLEANUP_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return False
        return True

    async def close(self) -> None:
        """Await one shared, retryable completion barrier for owner cleanup."""

        async with self._close_start_lock:
            close_task = self._close_task
            if close_task is None or (
                close_task.done() and not self._close_cleanup_complete
            ):
                self._closed = True
                close_task = asyncio.create_task(
                    self._run_close_cleanup(),
                    name="live-voice-streaming-tts-owner-close",
                )
                self._close_task = close_task
        caller_cancel: asyncio.CancelledError | None = None
        while True:
            try:
                result = await asyncio.shield(close_task)
                break
            except asyncio.CancelledError as exc:
                if caller_cancel is None:
                    caller_cancel = exc
                continue
        self._close_cleanup_complete = result.cleanup_complete
        if caller_cancel is not None:
            raise caller_cancel
        if result.process_control is not None:
            raise _fresh_process_control(result.process_control)

    async def _run_close_cleanup(self) -> _CloseResult:
        async with self._begin_lock:
            async with self._lifecycle_lock:
                opening = tuple(self._opening.values())
                handles = tuple(self._active.values())
                selection = self._selection
                selection_work = self._selection_work
        supersedable = opening + (
            (selection_work,) if selection_work is not None else ()
        )
        # Publish supersession first, then cancel only the tasks this owner
        # created.  A caller's WebSocket/RPC task must survive its route being
        # closed and stay usable for the rest of that connection.
        waiters = tuple(
            task
            for task in (
                work.supersede(StreamingSynthesisReason.OWNER_CLOSED)
                for work in supersedable
            )
            if task is not None
        )
        interruption: BaseException | None = None
        cleanup_complete = True
        if waiters:
            try:
                await self._task_owner.cancel_and_wait(
                    cast(tuple[asyncio.Task[object], ...], waiters),
                    timeout_seconds=_PROVIDER_CLEANUP_TIMEOUT_SECONDS,
                    operation="owner-close-waiters",
                )
            except asyncio.CancelledError as exc:
                interruption = exc
                try:
                    await self._task_owner.cancel_and_wait(
                        cast(tuple[asyncio.Task[object], ...], waiters),
                        timeout_seconds=_PROVIDER_CLEANUP_TIMEOUT_SECONDS,
                        operation="owner-close-waiters-retry",
                    )
                except (
                    asyncio.CancelledError,
                    KeyboardInterrupt,
                    SystemExit,
                    GeneratorExit,
                ) as cleanup_exc:
                    if interruption is None:
                        interruption = cleanup_exc
                except BaseException:
                    _LOGGER.error(
                        "live_voice_streaming_synthesis_close_failed "
                        "reason=opening_retry_timeout"
                    )
            except _PROCESS_CONTROL as exc:
                interruption = exc
            except BaseException:
                cleanup_complete = False
                _LOGGER.error(
                    "live_voice_streaming_synthesis_close_failed reason=opening_timeout"
                )
        for handle in handles:
            try:
                await self._terminate(
                    handle,
                    StreamingSynthesisReason.OWNER_CLOSED,
                    allow_batch=False,
                    cancel_provider=True,
                )
            except asyncio.CancelledError as exc:
                if interruption is None:
                    interruption = exc
                try:
                    await self._terminate(
                        handle,
                        StreamingSynthesisReason.OWNER_CLOSED,
                        allow_batch=False,
                        cancel_provider=True,
                    )
                except (
                    asyncio.CancelledError,
                    KeyboardInterrupt,
                    SystemExit,
                    GeneratorExit,
                ) as cleanup_exc:
                    if interruption is None:
                        interruption = cleanup_exc
            except _PROCESS_CONTROL as exc:
                if interruption is None:
                    interruption = exc
                cleanup_complete = False
        if selection is not None and selection.provider is not None:
            provider_closed = False
            for _attempt in range(2):
                try:
                    provider_closed = await self._close_provider_once(
                        selection.provider
                    )
                    if provider_closed:
                        break
                except _PROCESS_CONTROL as cleanup_exc:
                    if interruption is None:
                        interruption = cleanup_exc
                except BaseException:
                    _LOGGER.error(
                        "live_voice_streaming_synthesis_close_failed "
                        "reason=provider_close_retry"
                    )
            if not provider_closed:
                cleanup_complete = False
        try:
            await self._task_owner.drain(
                timeout_seconds=_PROVIDER_CLEANUP_TIMEOUT_SECONDS
            )
        except asyncio.CancelledError as exc:
            if interruption is None:
                interruption = exc
            try:
                await self._task_owner.drain(
                    timeout_seconds=_PROVIDER_CLEANUP_TIMEOUT_SECONDS
                )
            except asyncio.CancelledError:
                pass
        if self._task_owner.retained_count:
            cleanup_complete = False
        if self._active:
            cleanup_complete = False
        self._close_cleanup_complete = cleanup_complete
        return _CloseResult(interruption, cleanup_complete)

    async def _select(self) -> StreamingSpeechSelection:
        async with self._selection_lock:
            if self._selection is not None:
                return self._selection
            if self._closed:
                return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
            if asyncio.current_task() is None:
                raise RuntimeError("streaming Speech selection requires a task")
            attempt = object()
            # Close supersedes this owner-created selector task, never the
            # caller's task, so a slow selector racing close leaves the caller
            # with a truthful unavailable selection instead of a dead task.
            work = _SupersedableWork()
            self._selection_work = work
            self._selection_attempt = attempt
            try:
                selection = await self._task_owner.run(
                    self._invoke_selector(attempt),
                    timeout_seconds=self._open_timeout_seconds,
                    operation="provider-selector",
                    work=work,
                )
            except asyncio.CancelledError:
                raise
            except _PROCESS_CONTROL:
                raise
            except BaseException:
                selection = StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
            finally:
                if self._selection_work is work:
                    self._selection_work = None
                if self._selection_attempt is attempt:
                    self._selection_attempt = None
            if not isinstance(selection, StreamingSpeechSelection):
                selection = StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
            if self._closed:
                if selection.provider is not None:
                    await self._close_provider_once(selection.provider)
                return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
            self._selection = selection
            return selection

    async def _invoke_selector(self, attempt: object) -> StreamingSpeechSelection:
        selection = await self._selector()
        if (self._closed or self._selection_attempt is not attempt) and isinstance(
            selection, StreamingSpeechSelection
        ):
            if selection.provider is not None:
                await self._close_provider_once(selection.provider)
            return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
        return selection

    async def _close_provider_once(
        self, provider: NativeStreamingSpeechProvider
    ) -> bool:
        identity = id(provider)
        async with self._provider_close_lock:
            if identity in self._provider_close_completed:
                return True
            try:
                await self._task_owner.run(
                    provider.close(),
                    timeout_seconds=_PROVIDER_CLEANUP_TIMEOUT_SECONDS,
                    operation="provider-close",
                    cleanup=True,
                )
            except TimeoutError:
                _LOGGER.error(
                    "live_voice_streaming_synthesis_close_failed "
                    "reason=provider_close_timeout"
                )
                return False
            self._provider_close_completed.add(identity)
            return True

    async def _activate_response(
        self,
        provider: NativeStreamingSpeechProvider,
        response: ResponseRef,
        scope_identity: StreamingSynthesisScopeIdentity = _LEGACY_SYNTHESIS_SCOPE,
        *,
        own_work: _SupersedableWork | None = None,
    ) -> None:
        response_key = (scope_identity, response.interaction_id)
        current = self._current_responses.get(response_key)
        if current == response:
            return
        if (
            current is not None
            and (
                response.response_generation <= current.response_generation
                or response.response_id == current.response_id
            )
        ) or (current is None and self._retired_stale_response(response_key, response)):
            raise StreamingSynthesisRouteViolation(
                "STALE_SYNTHESIS_RESPONSE",
                "synthesis requires a strictly newer exact response generation",
            )
        predecessors = tuple(
            handle
            for handle in self._active.values()
            if handle.scope_identity == scope_identity
            and handle.ref.response.interaction_id == response.interaction_id
        )
        opening_predecessors = tuple(
            work
            for key, work in self._opening.items()
            if self._opening_responses.get(key) is not None
            and key[0] == scope_identity
            and self._opening_responses[key].interaction_id == response.interaction_id
            and self._opening_responses[key] != response
            and work is not own_work
        )
        if opening_predecessors:
            # Publish supersession first, then cancel only owner-created work.
            # A predecessor caller keeps its own task and observes the exact
            # superseded control outcome instead of losing its connection.
            predecessor_tasks = tuple(
                task
                for task in (
                    work.supersede(StreamingSynthesisReason.RESPONSE_SUPERSEDED)
                    for work in opening_predecessors
                )
                if task is not None
            )
            try:
                await self._task_owner.cancel_and_wait(
                    predecessor_tasks,
                    timeout_seconds=_PROVIDER_CLEANUP_TIMEOUT_SECONDS,
                    operation="predecessor-open",
                )
            except StreamingSynthesisRouteViolation:
                raise StreamingSynthesisRouteViolation(
                    "SYNTHESIS_OPEN_CANCEL_TIMEOUT",
                    "a predecessor synthesis open did not stop in time",
                ) from None
        if self._closed:
            return
        process_control: BaseException | None = None
        for handle in predecessors:
            try:
                await self._terminate(
                    handle,
                    StreamingSynthesisReason.RESPONSE_SUPERSEDED,
                    allow_batch=False,
                    cancel_provider=True,
                )
            except _PROCESS_CONTROL as exc:
                if process_control is None:
                    process_control = exc
        if process_control is not None:
            raise process_control
        provider.conformance.activate_response(response)
        self._make_response_capacity(response_key)
        self._current_responses[response_key] = response

    def _preflight_response(
        self,
        response: ResponseRef,
        scope_identity: StreamingSynthesisScopeIdentity = _LEGACY_SYNTHESIS_SCOPE,
    ) -> None:
        """Reject stale response identity before any retained route effect."""

        response_key = (scope_identity, response.interaction_id)
        current = self._current_responses.get(response_key)
        if (
            current is not None
            and current != response
            and (
                response.response_generation <= current.response_generation
                or response.response_id == current.response_id
            )
        ) or (current is None and self._retired_stale_response(response_key, response)):
            raise StreamingSynthesisRouteViolation(
                "STALE_SYNTHESIS_RESPONSE",
                "synthesis requires a strictly newer exact response generation",
            )

    async def _produce(self, handle: StreamingSynthesisHandle) -> None:
        pending: list[float] = []
        pending_source_seq = 0
        event_timeout_seconds = min(
            handle.event_timeout_seconds, self._event_timeout_seconds
        )
        try:
            while True:
                event = await self._task_owner.run(
                    handle.provider.next_synthesis_event(
                        handle.ref, timeout_seconds=event_timeout_seconds
                    ),
                    timeout_seconds=event_timeout_seconds,
                    operation="provider-event",
                )
                self._validate_event(handle, event)
                handle.next_provider_seq += 1
                if event.kind is SynthesisEventKind.STARTED:
                    handle.started = True
                    continue
                if event.kind is SynthesisEventKind.CANCELLED:
                    await self._terminate(
                        handle,
                        StreamingSynthesisReason.PROVIDER_UNAVAILABLE,
                        allow_batch=True,
                        cancel_provider=False,
                    )
                    return
                if event.kind is SynthesisEventKind.CHUNK:
                    assert event.pcm_s16le is not None
                    pending_source_seq = event.seq
                    pending.extend(_decode_pcm_s16le(event.pcm_s16le))
                    handle.next_provider_cursor += event.sample_count
                    frame_samples = handle.sample_rate_hz // 50
                    while len(pending) >= frame_samples:
                        values = tuple(pending[:frame_samples])
                        del pending[:frame_samples]
                        await self._enqueue_frame(
                            handle,
                            values,
                            source_event_seq=event.seq,
                            provider_cursor_through=handle.next_provider_cursor
                            - len(pending),
                        )
                    event = None
                    continue
                if event.kind is SynthesisEventKind.COMPLETED:
                    if pending:
                        frame_samples = handle.sample_rate_hz // 50
                        provider_cursor = handle.next_provider_cursor
                        pending.extend((0.0,) * (frame_samples - len(pending)))
                        await self._enqueue_frame(
                            handle,
                            tuple(pending),
                            source_event_seq=pending_source_seq,
                            provider_cursor_through=provider_cursor,
                        )
                        pending.clear()
                    if handle.next_frame_seq <= 0:
                        raise StreamingSynthesisRouteViolation(
                            "EMPTY_SYNTHESIS_STREAM",
                            "completed synthesis did not contain audio",
                        )
                    await self._complete(handle)
                    return
        except asyncio.CancelledError:
            raise
        except _PROCESS_CONTROL as process_control:
            pending.clear()
            async with handle.state_lock:
                handle.process_control = process_control
            try:
                await self._terminate(
                    handle,
                    StreamingSynthesisReason.ROUTE_ABORTED,
                    allow_batch=False,
                    cancel_provider=True,
                    cancel_producer=False,
                )
            except _PROCESS_CONTROL:
                # Preserve the original event-side process control.  Cleanup
                # process control must not strand it in a background Task.
                pass
            return
        except BaseException as exc:
            pending.clear()
            reason = _reason_for_exception(exc)
            del exc
            try:
                await self._terminate(
                    handle,
                    reason,
                    allow_batch=True,
                    cancel_provider=True,
                    cancel_producer=False,
                )
            except _PROCESS_CONTROL:
                # _terminate retains the cleanup-side process control for the
                # foreground puller after completing route cleanup.
                return
        finally:
            pending.clear()

    def _validate_event(
        self, handle: StreamingSynthesisHandle, event: StreamingSynthesisEvent
    ) -> None:
        if (
            not isinstance(event, StreamingSynthesisEvent)
            or event.ref != handle.ref
            or event.provider != handle.provider_ref
            or event.seq != handle.next_provider_seq
            or event.sample_cursor != handle.next_provider_cursor
            or event.sample_rate_hz != handle.sample_rate_hz
        ):
            raise StreamingSynthesisRouteViolation(
                "SYNTHESIS_EVENT_NOT_EXACT",
                "streaming synthesis event changed its exact route binding",
            )
        if event.kind is SynthesisEventKind.STARTED:
            if (
                handle.started
                or event.seq != 0
                or event.sample_count != 0
                or event.pcm_s16le is not None
            ):
                raise StreamingSynthesisRouteViolation(
                    "INVALID_SYNTHESIS_STARTED",
                    "synthesis started event is not closed",
                )
            return
        if not handle.started:
            raise StreamingSynthesisRouteViolation(
                "SYNTHESIS_NOT_STARTED",
                "synthesis audio or terminal output preceded started",
            )
        if event.kind is SynthesisEventKind.CHUNK:
            if (
                event.sample_count <= 0
                or event.pcm_s16le is None
                or len(event.pcm_s16le) != event.sample_count * 2
                or event.display_span is not None
                or event.spoken_span is not None
            ):
                raise StreamingSynthesisRouteViolation(
                    "INVALID_SYNTHESIS_CHUNK",
                    "synthesis audio chunk is not closed PCM16",
                )
            return
        if event.kind in {
            SynthesisEventKind.COMPLETED,
            SynthesisEventKind.CANCELLED,
        } and (
            event.sample_count != 0
            or event.pcm_s16le is not None
            or event.display_span is not None
            or event.spoken_span is not None
        ):
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_TERMINAL",
                "synthesis terminal event cannot contain text or audio",
            )
        if event.kind not in {
            SynthesisEventKind.STARTED,
            SynthesisEventKind.CHUNK,
            SynthesisEventKind.COMPLETED,
            SynthesisEventKind.CANCELLED,
        }:
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_EVENT_KIND",
                "synthesis event kind is unsupported",
            )

    async def _enqueue_frame(
        self,
        handle: StreamingSynthesisHandle,
        samples: tuple[float, ...],
        *,
        source_event_seq: int,
        provider_cursor_through: int,
    ) -> None:
        async with handle.state_lock:
            if handle.fenced:
                raise StreamingSynthesisRouteViolation(
                    "SYNTHESIS_OUTPUT_FENCED",
                    "fenced synthesis cannot queue another audio frame",
                )
            frame = MediaAudioFrame(
                seq=handle.next_frame_seq,
                sample_cursor=handle.next_frame_cursor,
                samples=samples,
            )
            chunk = StreamingSynthesisChunk(
                ref=handle.ref,
                request_binding_ref=handle.request_binding_ref,
                provider=handle.provider_ref,
                capability=handle.capability,
                frame=frame,
                source_event_seq=source_event_seq,
                provider_cursor_through=provider_cursor_through,
            )
            handle.next_frame_seq += 1
            handle.next_frame_cursor += len(samples)
        try:
            await self._task_owner.run(
                self._queue_put_guarded(handle, chunk),
                timeout_seconds=self._queue_wait_seconds,
                operation="queue-put-audio",
            )
        except TimeoutError as exc:
            raise StreamingSynthesisRouteViolation(
                StreamingSynthesisReason.QUEUE_EXHAUSTED.value,
                "streaming synthesis output queue is exhausted",
            ) from exc

    async def _complete(self, handle: StreamingSynthesisHandle) -> None:
        outcome = StreamingSynthesisOutcome(
            ref=handle.ref,
            request_binding_ref=handle.request_binding_ref,
            completed=True,
            first_audio_emitted=handle.first_audio_emitted,
            batch_eligible=False,
            provider_id=handle.provider_ref.provider_id,
            provider=handle.provider_ref,
            capability=handle.capability,
            reason=None,
            fact=None,
        )
        try:
            await self._task_owner.run(
                self._queue_put_guarded(handle, _TerminalSignal(outcome)),
                timeout_seconds=self._queue_wait_seconds,
                operation="queue-put-terminal",
            )
        except TimeoutError as exc:
            raise StreamingSynthesisRouteViolation(
                StreamingSynthesisReason.QUEUE_EXHAUSTED.value,
                "streaming synthesis terminal queue is exhausted",
            ) from exc
        async with handle.state_lock:
            if handle.outcome is None:
                handle.outcome = outcome
            handle.fenced = True
            handle.terminal_ready.set()

    @staticmethod
    async def _queue_put_guarded(
        handle: StreamingSynthesisHandle, item: _QueueValue
    ) -> None:
        await handle.queue.put(item)
        async with handle.state_lock:
            if handle.fenced and (
                handle.outcome is None or not handle.outcome.completed
            ):
                _drain_queue(handle.queue)
                if handle.outcome is not None and handle.cleanup_complete:
                    handle.queue.put_nowait(_TerminalSignal(handle.outcome))
                raise StreamingSynthesisRouteViolation(
                    "SYNTHESIS_LATE_QUEUE_WRITE_FENCED",
                    "a late queue write completed after synthesis was fenced",
                )

    async def _terminate(
        self,
        handle: StreamingSynthesisHandle,
        reason: StreamingSynthesisReason,
        *,
        allow_batch: bool,
        cancel_provider: bool,
        cancel_producer: bool = True,
    ) -> StreamingSynthesisOutcome:
        async with handle.cleanup_lock:
            return await self._terminate_locked(
                handle,
                reason,
                allow_batch=allow_batch,
                cancel_provider=cancel_provider,
                cancel_producer=cancel_producer,
            )

    async def _terminate_locked(
        self,
        handle: StreamingSynthesisHandle,
        reason: StreamingSynthesisReason,
        *,
        allow_batch: bool,
        cancel_provider: bool,
        cancel_producer: bool,
    ) -> StreamingSynthesisOutcome:
        async with handle.state_lock:
            if handle.outcome is not None and not handle.outcome.completed:
                outcome = handle.outcome
                if handle.cleanup_complete:
                    return outcome
            elif (
                handle.outcome is not None
                and handle.outcome.completed
                and handle.terminal_delivered
            ):
                return handle.outcome
            else:
                first_audio = handle.first_audio_emitted
                outcome = self._failure_outcome(
                    handle.request_binding_ref,
                    reason,
                    ref=handle.ref,
                    first_audio_emitted=first_audio,
                    allow_batch=allow_batch and not first_audio,
                    allow_fallback=reason
                    not in {
                        StreamingSynthesisReason.ROUTE_ABORTED,
                        StreamingSynthesisReason.RESPONSE_SUPERSEDED,
                        StreamingSynthesisReason.OWNER_CLOSED,
                    },
                    capability=handle.capability,
                )
                handle.outcome = outcome
                handle.fenced = True
                handle.terminal_ready.set()
                _drain_queue(handle.queue)
        process_control: BaseException | None = None
        provider_cleanup_complete = True
        if cancel_provider:
            completion = handle.provider_cancel_completion
            if completion is not None and completion.done():
                try:
                    handle.provider_cleanup_complete = completion.result()
                except BaseException:
                    handle.provider_cleanup_complete = False
                if not handle.provider_cleanup_complete:
                    handle.provider_cancel_completion = None
                    completion = None
            if handle.provider_cleanup_complete:
                provider_cleanup_complete = True
            elif completion is not None:
                # A hard-deadline cancellation is still retained.  Never race
                # it with another call against the same Provider stream.
                provider_cleanup_complete = False
            else:
                completion = asyncio.get_running_loop().create_future()
                handle.provider_cancel_completion = completion
                try:
                    provider_cleanup_complete = await self._cancel_provider(
                        handle.provider,
                        handle.ref,
                        reason=reason.value.lower(),
                        completion=completion,
                    )
                    if provider_cleanup_complete:
                        handle.provider_cleanup_complete = True
                except (KeyboardInterrupt, SystemExit, GeneratorExit) as exc:
                    process_control = exc
        producer = handle.producer_task
        producer_cleanup_complete = True
        if (
            cancel_producer
            and producer is not None
            and producer is not asyncio.current_task()
            and not producer.done()
        ):
            producer.cancel()
            try:
                await self._task_owner.cancel_and_wait(
                    (cast(asyncio.Task[object], producer),),
                    timeout_seconds=_PROVIDER_CLEANUP_TIMEOUT_SECONDS,
                    operation="producer-cleanup",
                )
            except asyncio.CancelledError:
                raise
            except _PROCESS_CONTROL as exc:
                if process_control is None:
                    process_control = exc
            except BaseException:
                producer_cleanup_complete = False
        cleanup_complete = provider_cleanup_complete and producer_cleanup_complete
        if cleanup_complete:
            await self._retire(handle)
        async with handle.state_lock:
            if process_control is not None and handle.process_control is None:
                handle.process_control = process_control
            handle.cleanup_complete = cleanup_complete
            if cleanup_complete:
                handle.cleanup_done.set()
            _drain_queue(handle.queue)
            handle.queue.put_nowait(_TerminalSignal(outcome))
        if process_control is not None:
            raise process_control
        return outcome

    async def _cancel_provider(
        self,
        provider: NativeStreamingSpeechProvider,
        ref: SynthesisStreamRef,
        *,
        reason: str,
        completion: asyncio.Future[bool] | None = None,
    ) -> bool:
        async def cancel_provider() -> None:
            try:
                await provider.cancel_synthesis(ref, reason=reason[:256])
            except BaseException:
                if completion is not None and not completion.done():
                    completion.set_result(False)
                raise
            else:
                if completion is not None and not completion.done():
                    completion.set_result(True)

        try:
            await self._task_owner.run(
                cancel_provider(),
                timeout_seconds=_PROVIDER_CLEANUP_TIMEOUT_SECONDS,
                operation="provider-cancel",
                cleanup=True,
            )
            return True
        except asyncio.CancelledError:
            raise
        except _PROCESS_CONTROL:
            raise
        except BaseException:
            # The Adapter may already have retired a failed/completed stream.
            # Its untrusted exception text is intentionally discarded.
            return False

    async def _open_provider_guarded(
        self,
        provider: NativeStreamingSpeechProvider,
        prepared: _PreparedSynthesisRequest,
        *,
        key: _ScopedStreamKey,
        work: _SupersedableWork,
    ) -> None:
        try:
            async with self._provider_open_lock:
                prepared.open_attempted = True
                await provider.open_synthesis(prepared._payload)
        except asyncio.CancelledError:
            # This task is owner-created, so its cancellation is this owner's
            # own supersession.  Settling the Provider here keeps the effect
            # inside the task the canceller joins, instead of leaving it to the
            # caller's connection task and racing the close drain.
            if prepared.open_attempted and work.superseded.is_set():
                try:
                    await self._cancel_provider(
                        provider, prepared.ref, reason="open_superseded"
                    )
                except (asyncio.CancelledError, *_PROCESS_CONTROL):
                    pass
            raise
        if (
            self._closed
            or work.superseded.is_set()
            or self._opening.get(key) is not work
        ):
            await self._cancel_provider(
                provider, prepared.ref, reason="late_open_fenced"
            )
            if work.superseded.is_set():
                raise _OwnedWorkSuperseded("provider-open")
            raise StreamingSynthesisRouteViolation(
                "SYNTHESIS_LATE_OPEN_FENCED",
                "a synthesis open completed after its route was fenced",
            )

    @staticmethod
    async def _take_process_control(
        handle: StreamingSynthesisHandle,
    ) -> BaseException | None:
        async with handle.state_lock:
            process_control = handle.process_control
            handle.process_control = None
            return process_control

    async def _retire(self, handle: StreamingSynthesisHandle) -> None:
        key = _scoped_stream_key(handle.scope_identity, handle.ref)
        async with self._lifecycle_lock:
            if self._active.get(key) is handle:
                del self._active[key]

    async def _discard_unstarted(
        self,
        key: _ScopedStreamKey,
        handle: StreamingSynthesisHandle | None,
    ) -> None:
        if handle is None:
            return
        async with self._lifecycle_lock:
            if self._active.get(key) is handle:
                del self._active[key]
            if self._known_handles.get(key) is handle:
                del self._known_handles[key]

    # Bounded identity retirement.  Every helper below is synchronous, so one
    # retirement pass cannot interleave with `_active`/`_opening` mutations.

    @staticmethod
    def _fence_identity(parts: tuple[str, ...]) -> str:
        """Encode one identity injectively, whatever its parts contain."""

        return "\0".join(f"{len(part)}:{part}" for part in parts)

    @staticmethod
    def _fence_digest(scope: str, identity: str) -> bytes:
        return hashlib.sha256(
            f"{scope}\0{identity}".encode("utf-8", "surrogatepass")
        ).digest()

    def _admission_fence_indices(self, scope: str, identity: str) -> tuple[int, ...]:
        digest = self._fence_digest(scope, identity)
        bit_capacity = len(self._identity_admission_fence) * 8
        return tuple(
            int.from_bytes(digest[offset : offset + 4], "big") % bit_capacity
            for offset in (0, 4, 8, 12)
        )

    def _generation_fence_indices(self, scope: str, identity: str) -> tuple[int, ...]:
        # Disjoint digest bytes keep the two fences independent, so an
        # admission collision cannot drag a generation cell with it.
        digest = self._fence_digest(scope, identity)
        capacity = len(self._generation_fence[0])
        return tuple(
            int.from_bytes(digest[offset : offset + 4], "big") % capacity
            for offset in (16, 20, 24, 28)
        )

    def _mark_retired(self, scope: str, identity: str) -> None:
        for index in self._admission_fence_indices(scope, identity):
            self._identity_admission_fence[index >> 3] |= 1 << (index & 7)

    def _fenced_identity(self, scope: str, identity: str) -> bool:
        return all(
            self._identity_admission_fence[index >> 3] & (1 << (index & 7))
            for index in self._admission_fence_indices(scope, identity)
        )

    @classmethod
    def _binding_identity(cls, key: _ScopedStreamKey) -> str:
        scope_identity, stream_id, stream_generation = key
        return cls._fence_identity((*scope_identity, stream_id, str(stream_generation)))

    @classmethod
    def _interaction_identity(cls, key: _ScopedResponseKey) -> str:
        scope_identity, interaction_id = key
        return cls._fence_identity((*scope_identity, interaction_id))

    @classmethod
    def _response_id_identity(cls, key: _ScopedResponseKey, response_id: str) -> str:
        # Scoped by interaction, exactly like the exact
        # `response_id == current.response_id` refusal it stands in for.
        scope_identity, interaction_id = key
        return cls._fence_identity((*scope_identity, interaction_id, response_id))

    def _release_binding(self, key: _ScopedStreamKey) -> None:
        """Drop one exact binding and its handle, keep the refusal tombstone."""

        self._mark_retired(_BINDING_IDENTITY_SCOPE, self._binding_identity(key))
        self._retained_bindings.pop(key, None)
        self._known_handles.pop(key, None)

    def _retired_binding(self, key: _ScopedStreamKey) -> bool:
        return self._fenced_identity(
            _BINDING_IDENTITY_SCOPE, self._binding_identity(key)
        )

    def _releasable_binding(self) -> _ScopedStreamKey | None:
        """Pick the least recently retained binding that owns no live stream."""

        return next(
            (
                retained
                for retained in self._retained_bindings
                if retained not in self._active and retained not in self._opening
            ),
            None,
        )

    def _binding_capacity_available(self, key: _ScopedStreamKey) -> bool:
        """Report identity capacity without mutating any retained state.

        A rejected admission therefore leaves the ledgers, the fences and every
        other retained structure exactly as they were.
        """

        if key in self._retained_bindings:
            return True
        if len(self._retained_bindings) < _MAX_ROUTE_IDENTITIES:
            return True
        return self._releasable_binding() is not None

    def _make_binding_capacity(self, key: _ScopedStreamKey) -> None:
        """Retire retained bindings that own no live stream, never a live one."""

        if key in self._retained_bindings:
            return
        while len(self._retained_bindings) >= _MAX_ROUTE_IDENTITIES:
            retired = self._releasable_binding()
            if retired is None:
                return
            self._release_binding(retired)

    def _release_response(self, key: _ScopedResponseKey) -> None:
        """Drop one exact response entry, keep its conservative high water."""

        response = self._current_responses.pop(key, None)
        interaction_identity = self._interaction_identity(key)
        self._mark_retired(_RESPONSE_INTERACTION_SCOPE, interaction_identity)
        if response is None:
            return
        self._mark_retired(
            _RESPONSE_ID_SCOPE, self._response_id_identity(key, response.response_id)
        )
        if response.response_generation <= 0:
            # The admission fence alone already refuses generation zero, so an
            # unreused interaction never needs a generation cell.
            return
        # No clamp is needed: `_request_binding_ref_inner` fails closed above
        # MAX_SAFE_INTEGER, so `generation + 1` can never overflow a cell.
        encoded = response.response_generation + 1
        for row, index in zip(
            self._generation_fence,
            self._generation_fence_indices(
                _RESPONSE_INTERACTION_SCOPE, interaction_identity
            ),
            strict=True,
        ):
            row[index] = max(row[index], encoded)

    def _retired_response_generation(self, key: _ScopedResponseKey) -> int | None:
        """Report a retired interaction's highest admitted response generation."""

        interaction_identity = self._interaction_identity(key)
        if not self._fenced_identity(_RESPONSE_INTERACTION_SCOPE, interaction_identity):
            return None
        fenced = min(
            row[index]
            for row, index in zip(
                self._generation_fence,
                self._generation_fence_indices(
                    _RESPONSE_INTERACTION_SCOPE, interaction_identity
                ),
                strict=True,
            )
        )
        return int(fenced) - 1 if fenced >= 1 else 0

    def _retired_stale_response(
        self, key: _ScopedResponseKey, response: ResponseRef
    ) -> bool:
        """Refuse a response whose exact interaction entry was already retired."""

        high_water = self._retired_response_generation(key)
        if high_water is not None and response.response_generation <= high_water:
            return True
        return self._fenced_identity(
            _RESPONSE_ID_SCOPE, self._response_id_identity(key, response.response_id)
        )

    def _live_interactions(self) -> set[_ScopedResponseKey]:
        live = {
            (handle.scope_identity, handle.ref.response.interaction_id)
            for handle in self._active.values()
        }
        live.update(
            (key[0], response.interaction_id)
            for key, response in self._opening_responses.items()
        )
        return live

    def _make_response_capacity(self, key: _ScopedResponseKey) -> None:
        """Retire interactions that own no live stream, never the caller's own."""

        if key in self._current_responses:
            return
        live = self._live_interactions()
        while len(self._current_responses) >= _MAX_ROUTE_IDENTITIES:
            retired = next(
                (
                    retained
                    for retained in self._current_responses
                    if retained != key and retained not in live
                ),
                None,
            )
            if retired is None:
                return
            self._release_response(retired)

    def _require_handle(self, handle: StreamingSynthesisHandle) -> None:
        if not isinstance(handle, StreamingSynthesisHandle):
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_HANDLE", "synthesis handle has the wrong type"
            )
        key = _scoped_stream_key(handle.scope_identity, handle.ref)
        retained = self._retained_bindings.get(key)
        known = self._known_handles.get(key)
        if retained != handle.request_binding_ref or known is not handle:
            raise StreamingSynthesisRouteViolation(
                "SYNTHESIS_HANDLE_NOT_OWNED",
                "synthesis handle is absent, stale, or belongs to another owner",
            )

    def _supersession_reason(self, work: _SupersedableWork) -> StreamingSynthesisReason:
        """Report supersession with the route's existing control vocabulary."""

        if work.reason is not None:
            return work.reason
        return (
            StreamingSynthesisReason.OWNER_CLOSED
            if self._closed
            else StreamingSynthesisReason.ROUTE_ABORTED
        )

    @staticmethod
    def _selection_reason(
        fact: SpeechDegradationFact | None,
    ) -> StreamingSynthesisReason:
        if not isinstance(fact, SpeechDegradationFact):
            return StreamingSynthesisReason.PROVIDER_UNAVAILABLE
        try:
            return StreamingSynthesisReason(fact.reason.value)
        except ValueError:
            return StreamingSynthesisReason.PROVIDER_UNAVAILABLE

    @staticmethod
    def _failure_outcome(
        binding_ref: str,
        reason: StreamingSynthesisReason,
        *,
        first_audio_emitted: bool,
        allow_batch: bool,
        ref: SynthesisStreamRef | None = None,
        allow_fallback: bool = True,
        capability: StreamingSynthesisCapabilityProvenance | None = None,
        provider_id: str = "unavailable",
    ) -> StreamingSynthesisOutcome:
        action = (
            StreamingSynthesisFallbackAction.NONE
            if not allow_fallback
            else (
                StreamingSynthesisFallbackAction.BATCH_ELIGIBLE
                if allow_batch and not first_audio_emitted
                else StreamingSynthesisFallbackAction.TEXT_OR_RETRY
            )
        )
        normal_control = action is StreamingSynthesisFallbackAction.NONE and reason in {
            StreamingSynthesisReason.ROUTE_ABORTED,
            StreamingSynthesisReason.RESPONSE_SUPERSEDED,
            StreamingSynthesisReason.OWNER_CLOSED,
        }
        fact = StreamingSynthesisRouteFact(
            binding_ref=binding_ref,
            reason=reason,
            fallback_action=action,
            first_audio_emitted=first_audio_emitted,
            provider_id=_safe_provider_id(
                capability.provider.provider_id
                if capability is not None
                else provider_id
            ),
            provider_implementation_class=(
                capability.provider.implementation_class
                if capability is not None
                else None
            ),
            provider_fallback_from=(
                capability.provider.fallback_from if capability is not None else None
            ),
            provider_available=(
                capability.available if capability is not None else False
            ),
            synthesis_modes=(
                tuple(sorted(mode.value for mode in capability.modes))
                if capability is not None
                else ()
            ),
            transport=(
                capability.transport
                if capability is not None
                else ProviderTransport.UNSUPPORTED
            ),
            ordered_events=(
                capability.ordered_events
                if capability is not None
                else CapabilityProvenance.UNAVAILABLE
            ),
            exact_audio_cursor=(
                capability.exact_audio_cursor
                if capability is not None
                else CapabilityProvenance.UNAVAILABLE
            ),
            provider_cancel_ack=(
                capability.provider_cancel_ack
                if capability is not None
                else CapabilityProvenance.UNAVAILABLE
            ),
            chunk_text_spans=(
                capability.chunk_text_spans
                if capability is not None
                else CapabilityProvenance.UNAVAILABLE
            ),
            visible=not normal_control,
            x_obs_event=(
                "live_voice.speech.control"
                if normal_control
                else "live_voice.speech.degradation"
            ),
            x_obs_metric=None if normal_control else "live_voice.failure_total",
            metric_value=None if normal_control else 1,
        )
        if not normal_control:
            _LOGGER.warning(
                "live_voice_streaming_synthesis_fallback binding_ref=%s reason=%s "
                "action=%s first_audio_emitted=%s provider_id=%s visible=true",
                binding_ref,
                reason.value,
                action.value,
                str(first_audio_emitted).lower(),
                fact.provider_id,
            )
        return StreamingSynthesisOutcome(
            ref=ref,
            request_binding_ref=binding_ref,
            completed=False,
            first_audio_emitted=first_audio_emitted,
            batch_eligible=action is StreamingSynthesisFallbackAction.BATCH_ELIGIBLE,
            provider_id=fact.provider_id,
            provider=capability.provider if capability is not None else None,
            capability=capability,
            reason=reason,
            fact=fact,
        )


def _prepare_synthesis_request(
    request: SynthesisStreamRequest,
) -> tuple[_PreparedSynthesisRequest | None, tuple[str, str] | None]:
    """Validate without exporting an exception frame that retains raw text."""

    try:
        binding_ref = _request_binding_ref_inner(request)
    except StreamingSynthesisRouteViolation as validation_error:
        failure = (validation_error.reason, str(validation_error))
        del validation_error
    except (TypeError, ValueError):
        failure = (
            "INVALID_SYNTHESIS_REQUEST",
            "synthesis request has an invalid bounded value",
        )
    else:
        prepared = _PreparedSynthesisRequest(
            ref=request.ref,
            binding_ref=binding_ref,
            sample_rate_hz=request.sample_rate_hz,
            event_timeout_seconds=request.event_timeout_seconds,
            _payload=request,
        )
        request = None  # type: ignore[assignment]
        return prepared, None
    request = None  # type: ignore[assignment]
    return None, failure


def _request_binding_ref_inner(request: SynthesisStreamRequest) -> str:
    if not isinstance(request, SynthesisStreamRequest):
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_REQUEST", "synthesis request has the wrong type"
        )
    ref = request.ref
    if not isinstance(ref, SynthesisStreamRef) or not isinstance(
        ref.response, ResponseRef
    ):
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_REF", "synthesis request reference is not canonical"
        )
    for value in (
        ref.stream_id,
        ref.response.interaction_id,
        ref.response.response_id,
        ref.unit_id,
    ):
        if not isinstance(value, str) or not value or len(value) > 256:
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_IDENTITY", "synthesis identity is invalid"
            )
    for value in (
        ref.stream_generation,
        ref.response.response_generation,
        ref.unit_seq,
    ):
        if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_GENERATION", "synthesis generation is invalid"
            )
    if (
        not isinstance(request.display_text, str)
        or not isinstance(request.spoken_text, str)
        or not request.display_text
        or not request.spoken_text
        or len(request.display_text) > MAX_SYNTHESIS_TEXT_CHARS
        or len(request.spoken_text) > MAX_SYNTHESIS_TEXT_CHARS
    ):
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_TEXT", "synthesis text is invalid"
        )
    if not isinstance(request.display_span, TextSpan):
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_SPAN", "synthesis display span is invalid"
        )
    if (
        type(request.display_span.start) is not int
        or type(request.display_span.end) is not int
        or request.display_span.start < 0
        or request.display_span.end > MAX_SAFE_INTEGER
        or request.display_span.end - request.display_span.start
        != len(request.display_text)
    ):
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_SPAN", "synthesis display span is out of bounds"
        )
    if (
        type(request.sample_rate_hz) is not int
        or not 8_000 <= request.sample_rate_hz <= 192_000
        or request.sample_rate_hz % 50
    ):
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_SAMPLE_RATE",
            "synthesis sample rate must support exact 20 ms media frames",
        )
    event_timeout_seconds = _bounded_timeout(
        request.event_timeout_seconds, "request.event_timeout_seconds"
    )
    digest = hashlib.sha256()
    for value in (
        ref.stream_id,
        str(ref.stream_generation),
        ref.response.interaction_id,
        ref.response.response_id,
        str(ref.response.response_generation),
        ref.unit_id,
        str(ref.unit_seq),
        str(request.display_span.start),
        str(request.display_span.end),
        str(request.sample_rate_hz),
        event_timeout_seconds.hex(),
        request.display_text,
        request.spoken_text,
    ):
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_TEXT", "synthesis request is not valid UTF-8"
            ) from exc
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return f"sha256:{digest.hexdigest()}"


def _decode_pcm_s16le(value: bytes) -> tuple[float, ...]:
    if not isinstance(value, bytes) or not value or len(value) % 2:
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_PCM", "synthesis PCM must be non-empty s16le"
        )
    signed = struct.unpack(f"<{len(value) // 2}h", value)
    return tuple(sample / (32768 if sample < 0 else 32767) for sample in signed)


def _capability_provenance(
    capability: StreamingProviderCapability,
) -> StreamingSynthesisCapabilityProvenance:
    if not isinstance(capability, StreamingProviderCapability):
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_CAPABILITY",
            "streaming synthesis capability is not canonical",
        )
    if _safe_provider_id(
        capability.provider.provider_id
    ) != capability.provider.provider_id or (
        capability.provider.fallback_from is not None
        and _safe_provider_id(capability.provider.fallback_from)
        != capability.provider.fallback_from
    ):
        raise StreamingSynthesisRouteViolation(
            "UNSAFE_SYNTHESIS_PROVIDER_IDENTITY",
            "streaming synthesis Provider identity is not log-safe",
        )
    support = capability.synthesis
    return StreamingSynthesisCapabilityProvenance(
        provider=capability.provider,
        available=capability.available,
        modes=support.modes,
        transport=support.transport,
        ordered_events=support.ordered_events,
        exact_audio_cursor=support.exact_audio_cursor,
        provider_cancel_ack=support.provider_cancel_ack,
        chunk_text_spans=support.chunk_text_spans,
    )


def _synthesis_scope_identity(
    value: StreamingSynthesisScopeIdentity | None,
) -> StreamingSynthesisScopeIdentity:
    if value is None:
        return _LEGACY_SYNTHESIS_SCOPE
    if not isinstance(value, tuple) or len(value) != 3:
        raise StreamingSynthesisRouteViolation(
            "INVALID_SYNTHESIS_SCOPE", "synthesis scope identity is invalid"
        )
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 256:
            raise StreamingSynthesisRouteViolation(
                "INVALID_SYNTHESIS_SCOPE", "synthesis scope identity is invalid"
            )
    return value


def _scoped_stream_key(
    scope_identity: StreamingSynthesisScopeIdentity, ref: SynthesisStreamRef
) -> _ScopedStreamKey:
    return scope_identity, ref.stream_id, ref.stream_generation


def _safe_provider_id(value: object) -> str:
    if (
        isinstance(value, str)
        and 0 < len(value) <= 128
        and value.isascii()
        and all(character.isalnum() or character in "-_.:" for character in value)
    ):
        return value
    return "unavailable"


def _fresh_process_control(exc: BaseException) -> BaseException:
    """Return a traceback-free exception for each completion-barrier waiter."""

    try:
        fresh = type(exc)(*exc.args)
    except BaseException:
        fresh = RuntimeError("streaming synthesis cleanup was interrupted")
    fresh.__traceback__ = None
    fresh.__context__ = None
    fresh.__cause__ = None
    return fresh


def _drain_queue(queue: asyncio.Queue[_QueueValue]) -> None:
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return


def _reason_for_exception(exc: BaseException) -> StreamingSynthesisReason:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return StreamingSynthesisReason.PROVIDER_TIMEOUT
    if isinstance(exc, StreamingSpeechViolation):
        return StreamingSynthesisReason.PROVIDER_PROTOCOL
    reason = getattr(exc, "reason", None)
    if reason == "SYNTHESIS_RETAINED_TASK_CAPACITY_EXHAUSTED":
        return StreamingSynthesisReason.CAPACITY_EXHAUSTED
    if reason == StreamingSynthesisReason.QUEUE_EXHAUSTED.value:
        return StreamingSynthesisReason.QUEUE_EXHAUSTED
    if isinstance(exc, StreamingSynthesisRouteViolation):
        return StreamingSynthesisReason.PROVIDER_PROTOCOL
    return StreamingSynthesisReason.PROVIDER_UNAVAILABLE


def _bounded_positive_int(value: object, name: str, maximum: int) -> int:
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError(f"{name} must be in [1, {maximum}]")
    return value


def _bounded_timeout(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 < value <= MAX_STREAM_TIMEOUT_SECONDS
    ):
        raise ValueError(f"{name} must be finite and in (0, 300]")
    return float(value)


__all__ = [
    "StreamingSynthesisCapabilityProvenance",
    "StreamingSynthesisChunk",
    "StreamingSynthesisFallbackAction",
    "StreamingSynthesisHandle",
    "StreamingSynthesisOutcome",
    "StreamingSynthesisPull",
    "StreamingSynthesisReason",
    "StreamingSynthesisRouteFact",
    "StreamingSynthesisRouteOwner",
    "StreamingSynthesisRouteViolation",
    "StreamingSynthesisScopeIdentity",
]
