# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded product owner for one dedicated-media streaming STT route.

The browser media socket remains the sole audio authority.  This owner mirrors
accepted frames into a bounded Provider queue while the existing batch digest
path stays available for one explicit fallback.  It never commits a Turn or
dispatches Agent, Tool, or Task work.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable, TypeVar

from jiuwenswarm.common.live_voice_capture_limits import MAX_CAPTURE_DURATION_SECONDS
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame,
    MediaAuthorityBinding,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechDegradationFact,
    SpeechRouteTier,
    StreamingSpeechSelection,
    _reason_for_exception,
)
from jiuwenswarm.server.live_voice.speech_ports import RecognitionEventKind, ProviderRef
from jiuwenswarm.server.live_voice.streaming_speech import (
    CapabilityProvenance,
    CaptureRef,
    NativeStreamingSpeechProvider,
    RecognitionAudioFrame,
    RecognitionCommitDisposition,
    RecognitionStreamRequest,
    RecognitionStreamRef,
    RecognitionTimingBasis,
    RecognitionTurnBoundaryEvent,
    RecognitionTurnBoundaryKind,
    RecognitionTurnDetection,
    StreamingRecognitionEvent,
    StreamingSpeechViolation,
    require_stream_authority,
)


_LOGGER = logging.getLogger(__name__)
# 20 ms media frames.  A cold Provider connection can accumulate the same
# bounded pre-open burst that DedicatedMediaProductRegistry retains; the
# Provider pump must be able to accept that burst without immediately turning
# a successful open into QUEUE_EXHAUSTED.
_MAX_PENDING_PROVIDER_FRAMES = 800
_OPEN_TIMEOUT_SECONDS = 15.0
_PROVIDER_SEND_TIMEOUT_SECONDS = 5.0
_PROVIDER_COMMIT_TIMEOUT_SECONDS = 10.0
_PROVIDER_CANCEL_TIMEOUT_SECONDS = 1.0
_PROVIDER_CLOSE_TIMEOUT_SECONDS = 5.0
_PUMP_DRAIN_TIMEOUT_SECONDS = 5.0
_FINAL_TIMEOUT_SECONDS = 20.0
# A late utterance may use the full existing 61.5 s absolute capture window.
# Provider partials are optional. Do not expire before a legal final; finish()
# still uses the shorter postcommit deadline. The extra 3.5 s is transport grace.
_PRECOMMIT_EVENT_TIMEOUT_SECONDS = MAX_CAPTURE_DURATION_SECONDS + 3.5
# Native recognition Providers own an absolute session deadline, not just a
# connection deadline.  Keep the outer open call bounded by
# ``_OPEN_TIMEOUT_SECONDS`` below, while granting the Provider enough lifetime
# for the complete legal capture plus the post-commit final-event window.
_RECOGNITION_SESSION_TIMEOUT_SECONDS = (
    _OPEN_TIMEOUT_SECONDS + _PRECOMMIT_EVENT_TIMEOUT_SECONDS + _FINAL_TIMEOUT_SECONDS
)
_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS = 1.0
_MAX_ACTIVE_STREAMS = 32
_MAX_RETAINED_PROVIDER_TASKS = 64
_MAX_PROVIDER_CLOSE_OBLIGATIONS = 64
_MAX_PROVIDER_CLEANUP_TASKS = 64
_QUEUE_SENTINEL = object()
_PROCESS_CONTROL = (KeyboardInterrupt, SystemExit, GeneratorExit)
_T = TypeVar("_T")


class StreamingRecognitionFallbackReason(StrEnum):
    FEATURE_OFF = "STREAMING_SPEECH_FEATURE_OFF"
    CONFIGURATION_UNAVAILABLE = "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "STREAMING_SPEECH_PROVIDER_UNAVAILABLE"
    PROVIDER_PROTOCOL = "STREAMING_SPEECH_PROVIDER_PROTOCOL"
    PROVIDER_TIMEOUT = "STREAMING_SPEECH_PROVIDER_TIMEOUT"
    QUEUE_EXHAUSTED = "STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED"
    ROUTE_ABORTED = "STREAMING_SPEECH_ROUTE_ABORTED"
    RESOURCE_CAPACITY = "STREAMING_SPEECH_RESOURCE_CAPACITY"
    CLEANUP_INCOMPLETE = "STREAMING_SPEECH_CLEANUP_INCOMPLETE"
    AUTHORITY_EXPIRED = "STREAMING_SPEECH_AUTHORITY_EXPIRED"


@dataclass(frozen=True, slots=True)
class StreamingRecognitionOutcome:
    completed: bool
    final_text: str | None = field(repr=False)
    provider: ProviderRef | None
    fallback_tier: SpeechRouteTier | None
    reason: StreamingRecognitionFallbackReason | None


@dataclass(frozen=True, slots=True)
class StreamingRecognitionEndOfTurn:
    provider: ProviderRef
    provider_start_ms: int
    provider_end_ms: int
    detector: str = "server_vad"
    timing_basis: RecognitionTimingBasis = RecognitionTimingBasis.PROVIDER_TIME
    timing_provenance: CapabilityProvenance = CapabilityProvenance.ADAPTER_DERIVED
    speech_started_observed: bool = True
    create_response: bool = False
    interrupt_response: bool = False
    business_cancel_count_delta: int = 0


@dataclass(frozen=True, slots=True)
class StreamingRecognitionSpeechStart:
    provider: ProviderRef
    provider_start_ms: int
    detector: str = "server_vad"
    timing_basis: RecognitionTimingBasis = RecognitionTimingBasis.PROVIDER_TIME
    timing_provenance: CapabilityProvenance = CapabilityProvenance.ADAPTER_DERIVED
    create_response: bool = False
    interrupt_response: bool = False
    business_cancel_count_delta: int = 0


@dataclass(slots=True)
class StreamingRecognitionHandle:
    ref: RecognitionStreamRef
    provider: NativeStreamingSpeechProvider = field(repr=False)
    queue: asyncio.Queue[RecognitionAudioFrame | object] = field(repr=False)
    pump_task: asyncio.Task[None] | None = field(default=None, repr=False)
    event_task: asyncio.Task[StreamingRecognitionEvent] | None = field(
        default=None, repr=False
    )
    end_of_turn: asyncio.Future[StreamingRecognitionEndOfTurn] | None = field(
        default=None, repr=False
    )
    speech_start: asyncio.Future[StreamingRecognitionSpeechStart] | None = field(
        default=None, repr=False
    )
    finish_task: asyncio.Task[StreamingRecognitionOutcome] | None = field(
        default=None, repr=False
    )
    failure: StreamingRecognitionFallbackReason | None = None
    closed: bool = False
    settled: bool = False
    committed: bool = False
    input_fenced: bool = False
    next_frame_seq: int = 0
    next_sample_cursor: int = 0
    sent_sample_end: int = 0
    next_event_seq: int = 0
    last_event_cursor: int = 0
    speech_start_ms: int | None = None
    speech_stopped: bool = False


StreamingSpeechSelector = Callable[[], Awaitable[StreamingSpeechSelection]]


class StreamingRecognitionRouteOwner:
    """Lazy, single-Provider owner for bounded concurrent recognition routes."""

    def __init__(self, selector: StreamingSpeechSelector) -> None:
        if not callable(selector):
            raise TypeError("streaming Speech selector must be callable")
        self._selector = selector
        self._selection_lock = asyncio.Lock()
        self._selection_task: asyncio.Task[StreamingSpeechSelection] | None = None
        self._handle_lock = asyncio.Lock()
        self._selection: StreamingSpeechSelection | None = None
        self._handles: dict[
            tuple[str, int, str, int], StreamingRecognitionHandle | None
        ] = {}
        # A None handle is a capacity reservation, not a settled route.  Keep
        # both sides of every Provider open explicitly owned so close() can
        # fence publication, cancel the exact Provider call, and wait for the
        # outer begin operation to release its reservation.
        self._opening_tasks: dict[
            tuple[str, int, str, int],
            tuple[asyncio.Task[Any], asyncio.Task[None]],
        ] = {}
        # Count every concrete Provider operation from admission until its
        # task has actually settled.  A timed-out task that ignores
        # cancellation keeps its reservation, so concurrent callers cannot
        # turn the retained-cleanup bound into an unbounded in-flight set.
        self._provider_task_capacity_in_use = 0
        self._provider_capacity_tasks: set[asyncio.Task[Any]] = set()
        self._retained_provider_tasks: set[asyncio.Task[Any]] = set()
        self._retained_process_control: BaseException | None = None
        # A selector that times out can still return a late Provider after a
        # successor selector has started.  Close ownership is therefore keyed
        # by the concrete Provider/factory owner; different Providers must
        # never share one close task.
        self._provider_close_tasks: dict[int, tuple[object, asyncio.Task[None]]] = {}
        self._provider_close_obligations: dict[
            int, tuple[object, Callable[[], Awaitable[None]]]
        ] = {}
        self._provider_close_obligation_reservations: set[object] = set()
        # Provider cleanup has an independent bounded reserve.  A saturated
        # business-operation pool must not prevent a late selector from
        # retaining and closing the concrete Provider it already allocated.
        self._provider_cleanup_capacity_in_use = 0
        self._provider_cleanup_tasks: set[asyncio.Task[Any]] = set()
        self._closed_provider_owners: dict[int, object] = {}
        self._provider_close_complete = False
        self._closed = False

    async def begin(
        self,
        binding: MediaAuthorityBinding,
        *,
        turn_detection: RecognitionTurnDetection | None = None,
        request: RecognitionStreamRequest | None = None,
    ) -> tuple[StreamingRecognitionHandle | None, StreamingRecognitionOutcome | None]:
        if self._closed:
            return None, self._fallback(
                StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE,
                SpeechRouteTier.TEXT,
            )
        selection = await self._select()
        if (
            selection.provider is None
            or selection.tier is not SpeechRouteTier.STREAMING
        ):
            reason = self._selection_reason(selection.fact)
            return None, self._fallback(reason, selection.tier)
        provider = selection.provider
        detection = turn_detection or RecognitionTurnDetection.manual()
        if (
            detection.server_vad is not None
            and provider.capability.recognition.server_vad
            is not CapabilityProvenance.PROVIDER_NATIVE
        ):
            return None, self._fallback(
                StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL,
                SpeechRouteTier.TEXT,
            )
        ref = RecognitionStreamRef(
            session_id=binding.media_session_id,
            session_generation=binding.generation.value,
            capture=CaptureRef(
                binding.generation.id,
                binding.generation.value,
                binding.frame_format.sample_rate_hz,
            ),
        )
        stream_key = self._stream_key(ref)
        if request is None or request.ref != ref or request.turn_detection != detection:
            raise StreamingSpeechViolation(
                "SPEECH_AUTHORITY_REQUIRED",
                "exact Media-authorized recognition request required",
            )
        require_stream_authority(request, stage="route")
        operation_task = asyncio.current_task()
        if operation_task is None:
            return None, self._fallback(
                StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE,
                SpeechRouteTier.TEXT,
            )
        async with self._handle_lock:
            if self._closed:
                return None, self._fallback(
                    StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE,
                    SpeechRouteTier.TEXT,
                )
            if stream_key in self._handles or len(self._handles) >= _MAX_ACTIVE_STREAMS:
                return None, self._fallback(
                    StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED,
                    SpeechRouteTier.TEXT,
                )

            # Reserve capacity and register the concrete Provider call in one
            # lock ownership step.  close() can therefore never observe a None
            # reservation without also observing the operation that owns it.
            async def invoke_open() -> None:
                await provider.open_recognition(
                    request,
                    timeout_seconds=_RECOGNITION_SESSION_TIMEOUT_SECONDS,
                )

            try:
                open_task = self._start_provider_task(
                    invoke_open,
                    task_name=f"live-voice-streaming-stt-open-{ref.session_id}",
                )
            except RuntimeError:
                return None, self._fallback(
                    StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED,
                    SpeechRouteTier.TEXT,
                )
            self._handles[stream_key] = None
            self._opening_tasks[stream_key] = (operation_task, open_task)
        try:
            open_process_control: BaseException | None = None
            try:
                await self._await_bounded_provider_task(
                    open_task, timeout_seconds=_OPEN_TIMEOUT_SECONDS
                )
            except asyncio.CancelledError:
                await self._release_stream_reservation(stream_key)
                raise
            except _PROCESS_CONTROL as exc:
                open_process_control = self._safe_process_control(exc)
            except Exception as exc:
                await self._release_stream_reservation(stream_key)
                return None, self._fallback(
                    StreamingRecognitionFallbackReason(
                        _reason_for_exception(exc).value
                    ),
                    SpeechRouteTier.TEXT,
                )
            if open_process_control is not None:
                await self._release_stream_reservation(stream_key)
                raise open_process_control from None
            queue: asyncio.Queue[RecognitionAudioFrame | object] = asyncio.Queue(
                _MAX_PENDING_PROVIDER_FRAMES
            )
            handle = StreamingRecognitionHandle(
                ref=ref,
                provider=provider,
                queue=queue,
                end_of_turn=(
                    asyncio.get_running_loop().create_future()
                    if detection.server_vad is not None
                    else None
                ),
                speech_start=(
                    asyncio.get_running_loop().create_future()
                    if detection.server_vad is not None
                    else None
                ),
            )
            handle.pump_task = asyncio.create_task(
                self._pump(handle),
                name=f"live-voice-streaming-stt-pump-{ref.session_id}",
            )
            handle.event_task = asyncio.create_task(
                self._collect_final(handle),
                name=f"live-voice-streaming-stt-events-{ref.session_id}",
            )
            if handle.end_of_turn is not None:
                handle.end_of_turn.add_done_callback(_consume_eot_future_failure)
                assert handle.speech_start is not None
                handle.speech_start.add_done_callback(
                    _consume_speech_start_future_failure
                )
                handle.event_task.add_done_callback(_eot_collector_callback(handle))
            async with self._handle_lock:
                publish = not self._closed and self._handles.get(stream_key) is None
                if publish:
                    self._handles[stream_key] = handle
                else:
                    self._handles.pop(stream_key, None)
            if not publish:
                await self.abort(handle)
                return None, self._fallback(
                    StreamingRecognitionFallbackReason.ROUTE_ABORTED,
                    SpeechRouteTier.TEXT,
                )
            return handle, None
        finally:
            await self._release_opening_task(stream_key, operation_task, open_task)

    async def available(self) -> bool:
        if self._closed:
            return False
        selection = await self._select()
        return bool(
            not self._closed
            and selection.tier is SpeechRouteTier.STREAMING
            and selection.provider is not None
            and selection.provider.capability.available
        )

    @property
    def selection_degradation(self) -> dict[str, object] | None:
        selection = self._selection
        if selection is None or selection.fact is None:
            return None
        return selection.fact.safe_dict()

    @property
    def end_of_turn_available(self) -> bool:
        selection = self._selection
        return bool(
            not self._closed
            and selection is not None
            and selection.tier is SpeechRouteTier.STREAMING
            and selection.provider is not None
            and selection.provider.capability.recognition.server_vad
            is CapabilityProvenance.PROVIDER_NATIVE
        )

    def offer(self, handle: StreamingRecognitionHandle, frame: MediaAudioFrame) -> None:
        if handle.closed or handle.input_fenced or handle.failure is not None:
            return
        try:
            if (
                frame.seq != handle.next_frame_seq
                or frame.sample_cursor != handle.next_sample_cursor
                or len(frame.samples) <= 0
            ):
                handle.failure = StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
                return
            payload = struct.pack(f"<{len(frame.samples)}f", *frame.samples)
            provider_frame = RecognitionAudioFrame(
                ref=handle.ref,
                seq=frame.seq,
                sample_cursor=frame.sample_cursor,
                sample_count=len(frame.samples),
                pcm_f32le=payload,
            )
            handle.queue.put_nowait(provider_frame)
            handle.next_frame_seq += 1
            handle.next_sample_cursor += len(frame.samples)
        except asyncio.QueueFull:
            handle.failure = StreamingRecognitionFallbackReason.QUEUE_EXHAUSTED
        except Exception:
            handle.failure = StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL

    async def wait_end_of_turn(
        self, handle: StreamingRecognitionHandle
    ) -> StreamingRecognitionEndOfTurn:
        future = handle.end_of_turn
        if future is None:
            raise RuntimeError("end-of-turn was not negotiated for this stream")
        return await asyncio.shield(future)

    async def wait_speech_start(
        self, handle: StreamingRecognitionHandle
    ) -> StreamingRecognitionSpeechStart:
        future = handle.speech_start
        if future is None:
            raise RuntimeError("speech-start was not negotiated for this stream")
        return await asyncio.shield(future)

    async def finish(
        self, handle: StreamingRecognitionHandle
    ) -> StreamingRecognitionOutcome:
        if handle.closed:
            return self._fallback(
                StreamingRecognitionFallbackReason.ROUTE_ABORTED,
                SpeechRouteTier.TEXT,
            )
        handle.closed = True
        current_task = asyncio.current_task()
        if current_task is not None:
            handle.finish_task = current_task
        operation_process_control: BaseException | None = None
        try:
            if handle.failure is None:
                try:
                    if handle.pump_task is None:
                        raise RuntimeError("streaming recognition pump is absent")
                    if not handle.input_fenced:
                        await asyncio.wait_for(
                            handle.queue.put(_QUEUE_SENTINEL),
                            timeout=_PUMP_DRAIN_TIMEOUT_SECONDS,
                        )
                        await asyncio.wait_for(
                            asyncio.shield(handle.pump_task),
                            timeout=_PUMP_DRAIN_TIMEOUT_SECONDS,
                        )
                    elif not handle.pump_task.done():
                        handle.pump_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await asyncio.shield(handle.pump_task)
                except TimeoutError:
                    handle.failure = StreamingRecognitionFallbackReason.PROVIDER_TIMEOUT
                except asyncio.CancelledError:
                    current = asyncio.current_task()
                    provider_eot_cancelled_pump = bool(
                        handle.input_fenced
                        and handle.pump_task is not None
                        and handle.pump_task.cancelled()
                        and current is not None
                        and current.cancelling() == 0
                    )
                    if not provider_eot_cancelled_pump:
                        raise
                except Exception:
                    handle.failure = (
                        StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
                    )
            if handle.failure is None:
                try:
                    handle.committed = True
                    event_already_final = bool(
                        handle.input_fenced
                        and handle.event_task is not None
                        and handle.event_task.done()
                        and not handle.event_task.cancelled()
                        and handle.event_task.exception() is None
                    )
                    disposition = (
                        RecognitionCommitDisposition.SERVER_VAD_OBSERVED
                        if event_already_final
                        else await self._bounded_provider_call(
                            lambda: handle.provider.commit_recognition(handle.ref),
                            timeout_seconds=_PROVIDER_COMMIT_TIMEOUT_SECONDS,
                            task_name=(
                                "live-voice-streaming-stt-commit-"
                                f"{handle.ref.session_id}"
                            ),
                        )
                    )
                    if disposition not in {
                        RecognitionCommitDisposition.CLIENT_COMMIT_SENT,
                        RecognitionCommitDisposition.SERVER_VAD_PENDING,
                        RecognitionCommitDisposition.SERVER_VAD_OBSERVED,
                    }:
                        raise RuntimeError("recognition commit ownership was untyped")
                    if handle.event_task is None:
                        raise RuntimeError("streaming recognition collector is absent")
                    event = await asyncio.wait_for(
                        asyncio.shield(handle.event_task),
                        timeout=_FINAL_TIMEOUT_SECONDS,
                    )
                    if (
                        event.kind is not RecognitionEventKind.FINAL
                        or event.hypothesis is None
                    ):
                        raise ValueError(
                            "streaming recognition did not produce a final"
                        )
                    selected = event.hypothesis.selected
                    if not selected.display_text:
                        raise ValueError("streaming recognition final is empty")
                    return StreamingRecognitionOutcome(
                        completed=True,
                        final_text=selected.display_text,
                        provider=event.provider,
                        fallback_tier=None,
                        reason=None,
                    )
                except TimeoutError:
                    handle.failure = StreamingRecognitionFallbackReason.PROVIDER_TIMEOUT
                except asyncio.CancelledError:
                    raise
                except Exception:
                    handle.failure = (
                        StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
                    )
            return self._fallback(
                handle.failure
                or StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE,
                SpeechRouteTier.TEXT,
            )
        except asyncio.CancelledError:
            # Cancellation of the caller that owns finish() is also a product
            # route abort.  Preserve that fact for finally so the exact
            # Provider stream is cancelled before the handle is retired.
            handle.failure = StreamingRecognitionFallbackReason.ROUTE_ABORTED
            raise
        except _PROCESS_CONTROL as exc:
            # Process-control must still retire the exact Provider stream and
            # local tasks before it escapes the product owner.  Reconstruct it
            # outside the exception handler so Provider text/args cannot stay
            # attached through __context__.
            operation_process_control = self._safe_process_control(exc)
            handle.failure = StreamingRecognitionFallbackReason.ROUTE_ABORTED
        finally:
            cleanup_process_control: BaseException | None = None
            if handle.failure is not None:
                try:
                    await self._bounded_provider_call(
                        lambda: handle.provider.cancel_recognition(
                            handle.ref, reason="product_streaming_fallback"
                        ),
                        timeout_seconds=_PROVIDER_CANCEL_TIMEOUT_SECONDS,
                        task_name=(
                            f"live-voice-streaming-stt-cancel-{handle.ref.session_id}"
                        ),
                    )
                except _PROCESS_CONTROL as exc:
                    cleanup_process_control = exc
                except (Exception, asyncio.CancelledError):
                    pass
            for task in (handle.pump_task, handle.event_task):
                if task is None:
                    continue
                task_process_control = await self._cancel_local_task(task)
                if cleanup_process_control is None:
                    cleanup_process_control = task_process_control
            handle.finish_task = None
            handle.settled = True
            await self._release_handle(handle)
            if (
                cleanup_process_control is not None
                and operation_process_control is None
                and not isinstance(sys.exception(), _PROCESS_CONTROL)
            ):
                raise cleanup_process_control
        if operation_process_control is not None:
            raise operation_process_control from None
        raise RuntimeError("streaming recognition operation did not settle")

    async def abort(self, handle: StreamingRecognitionHandle) -> None:
        if handle.settled:
            return
        handle.failure = StreamingRecognitionFallbackReason.ROUTE_ABORTED
        if not handle.closed:
            await self.finish(handle)
            return
        # A product revoke may race a finish already waiting on commit/final.
        # Cancel the exact Provider stream and its local waiters instead of
        # allowing revoked authority to keep consuming Provider resources.
        process_control: BaseException | None = None
        try:
            await self._bounded_provider_call(
                lambda: handle.provider.cancel_recognition(
                    handle.ref, reason="product_streaming_route_revoked"
                ),
                timeout_seconds=_PROVIDER_CANCEL_TIMEOUT_SECONDS,
                task_name=f"live-voice-streaming-stt-abort-{handle.ref.session_id}",
            )
        except _PROCESS_CONTROL as exc:
            process_control = exc
        except (Exception, asyncio.CancelledError):
            pass
        finish_task = handle.finish_task
        if finish_task is not None and finish_task is not asyncio.current_task():
            task_process_control = await self._cancel_local_task(finish_task)
            if process_control is None:
                process_control = task_process_control
        for task in (handle.pump_task, handle.event_task):
            if task is None:
                continue
            task_process_control = await self._cancel_local_task(task)
            if process_control is None:
                process_control = task_process_control
        if process_control is not None:
            raise process_control

    async def close(self) -> None:
        self._prune_retained_provider_tasks()
        if (
            self._closed
            and self._provider_close_complete
            and not self._opening_tasks
            and not self._handles
            and not self._retained_provider_tasks
            and not self._provider_close_obligations
            and not self._provider_close_obligation_reservations
            and not self._provider_close_tasks
            and self._retained_process_control is None
        ):
            return
        # Fence in-flight selector callers without waiting on arbitrary
        # selector code while holding the selection lock.  The selector task
        # owns late-Provider cleanup, so even a selector that swallows
        # cancellation cannot publish availability after close().
        self._closed = True
        async with self._selection_lock:
            selection_task = self._selection_task
            self._selection_task = None
        if selection_task is not None:
            if not selection_task.done():
                selection_task.cancel()
                _selection_done, selection_pending = await asyncio.wait(
                    {selection_task}, timeout=_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS
                )
                if selection_pending:
                    self._retain_provider_task(selection_task)
            if selection_task.done():
                try:
                    selection_task.result()
                except _PROCESS_CONTROL as exc:
                    if self._retained_process_control is None:
                        self._retained_process_control = self._safe_process_control(exc)
                except (Exception, asyncio.CancelledError):
                    pass
        async with self._handle_lock:
            openings = tuple(self._opening_tasks.values())
            handles = tuple(
                handle for handle in self._handles.values() if handle is not None
            )
        current_task = asyncio.current_task()
        opening_wait_tasks: set[asyncio.Task[Any]] = set()
        opening_provider_tasks: set[asyncio.Task[Any]] = set()
        opening_cleanup_incomplete = False
        for operation_task, provider_task in openings:
            opening_provider_tasks.add(provider_task)
            if provider_task is current_task:
                opening_cleanup_incomplete = True
            elif not provider_task.done():
                provider_task.cancel()
            if operation_task is current_task:
                opening_cleanup_incomplete = True
            else:
                opening_wait_tasks.add(operation_task)
            if provider_task is not current_task:
                opening_wait_tasks.add(provider_task)
        opening_done: set[asyncio.Task[Any]] = set()
        opening_pending: set[asyncio.Task[Any]] = set()
        if opening_wait_tasks:
            opening_done, opening_pending = await asyncio.wait(
                opening_wait_tasks,
                timeout=_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS,
            )
        for opening_task in opening_pending:
            if opening_task in opening_provider_tasks:
                self._retain_provider_task(opening_task)
        opening_cleanup_incomplete = bool(opening_pending) or opening_cleanup_incomplete
        opening_process_control: BaseException | None = None
        for opening_task in opening_done:
            try:
                opening_task.result()
            except _PROCESS_CONTROL as exc:
                if opening_process_control is None:
                    opening_process_control = self._safe_process_control(exc)
            except (Exception, asyncio.CancelledError):
                pass
        abort_tasks = tuple(
            asyncio.create_task(
                self.abort(handle),
                name=f"live-voice-streaming-stt-close-{handle.ref.session_id}",
            )
            for handle in handles
        )
        retained_process_control = self._take_retained_process_control()
        process_control = opening_process_control
        if process_control is None:
            process_control = retained_process_control
        if abort_tasks:
            abort_done, abort_pending = await asyncio.wait(
                abort_tasks,
                timeout=_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS,
            )
            for abort_task in abort_pending:
                abort_task.cancel()
                self._retain_provider_task(abort_task)
            for abort_task in abort_done:
                try:
                    abort_task.result()
                except _PROCESS_CONTROL as exc:
                    if process_control is None:
                        process_control = exc
                except (Exception, asyncio.CancelledError):
                    pass
        close_failure: BaseException | None = None
        try:
            self._prune_provider_close_tasks()
            for _identity_key, (_identity, factory) in tuple(
                self._provider_close_obligations.items()
            ):
                try:
                    await self._bounded_provider_close(factory)
                except _PROCESS_CONTROL as exc:
                    if process_control is None:
                        process_control = self._safe_process_control(exc)
                except asyncio.CancelledError:
                    if close_failure is None:
                        close_failure = asyncio.CancelledError()
                except Exception as exc:
                    if close_failure is None:
                        close_failure = (
                            TimeoutError("streaming provider operation timed out")
                            if isinstance(exc, TimeoutError)
                            else RuntimeError("streaming provider close failed")
                        )
        finally:
            retained = tuple(self._retained_provider_tasks)
            for task in retained:
                if not task.done():
                    task.cancel()
            if retained:
                retained_done, _retained_pending = await asyncio.wait(
                    retained,
                    timeout=_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS,
                )
                for retained_task in retained_done:
                    if retained_task.cancelled():
                        continue
                    try:
                        retained_task.result()
                    except _PROCESS_CONTROL as exc:
                        if process_control is None:
                            process_control = exc
                    except (Exception, asyncio.CancelledError):
                        pass
            retained_process_control = self._take_retained_process_control()
            if process_control is None:
                process_control = retained_process_control
            self._prune_provider_close_tasks()
            self._provider_close_complete = not (
                self._provider_close_obligations or self._provider_close_tasks
            )
        if process_control is not None:
            raise process_control
        if close_failure is not None:
            raise close_failure from None
        self._prune_retained_provider_tasks()
        async with self._handle_lock:
            opening_cleanup_incomplete = (
                bool(self._opening_tasks or self._handles) or opening_cleanup_incomplete
            )
        if (
            self._retained_provider_tasks
            or self._provider_close_obligations
            or self._provider_close_obligation_reservations
            or self._provider_close_tasks
            or opening_cleanup_incomplete
        ):
            raise RuntimeError("streaming speech route cleanup is incomplete")

    async def _select(self) -> StreamingSpeechSelection:
        async with self._selection_lock:
            if self._selection is not None:
                return self._selection
            if self._closed:
                return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
            task = self._selection_task
            if task is None:
                if (
                    len(self._provider_close_obligations)
                    + len(self._provider_close_obligation_reservations)
                    >= _MAX_PROVIDER_CLOSE_OBLIGATIONS
                ):
                    return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
                reservation = object()
                self._provider_close_obligation_reservations.add(reservation)
                try:
                    task = self._start_provider_task(
                        lambda: self._run_selector(reservation),
                        task_name="live-voice-streaming-stt-selector",
                    )
                except RuntimeError:
                    self._provider_close_obligation_reservations.discard(reservation)
                    return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)

                def release_reservation(
                    _task: asyncio.Task[StreamingSpeechSelection],
                ) -> None:
                    self._provider_close_obligation_reservations.discard(reservation)

                task.add_done_callback(release_reservation)
                self._selection_task = task
        done, _pending = await asyncio.wait({task}, timeout=_OPEN_TIMEOUT_SECONDS)
        if not done:
            async with self._selection_lock:
                if self._selection_task is task:
                    self._selection_task = None
            task.cancel()
            self._retain_provider_task(task)
            return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
        selection_process_control: BaseException | None = None
        try:
            selection = task.result()
        except asyncio.CancelledError:
            async with self._selection_lock:
                current = self._selection_task is task
                if current:
                    self._selection_task = None
                closed = self._closed
            if closed or not current:
                return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
            raise
        except _PROCESS_CONTROL as exc:
            selection_process_control = self._safe_process_control(exc)
            async with self._selection_lock:
                if self._selection_task is task:
                    self._selection_task = None
        except Exception:
            async with self._selection_lock:
                if self._selection_task is task:
                    self._selection_task = None
            return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
        if selection_process_control is not None:
            raise selection_process_control from None
        async with self._selection_lock:
            if self._selection_task is task:
                self._selection_task = None
            if not self._closed and self._selection is None:
                self._selection = selection
            if self._closed:
                return StreamingSpeechSelection(SpeechRouteTier.TEXT, None, None)
            return self._selection or StreamingSpeechSelection(
                SpeechRouteTier.TEXT, None, None
            )

    async def _run_selector(self, reservation: object) -> StreamingSpeechSelection:
        try:
            selection = await self._selector()
            if type(selection) is not StreamingSpeechSelection:
                raise TypeError("streaming Speech selector returned an invalid result")
            if selection.provider is not None:
                # Retain the exact resource before publication or any
                # close-task admission.  The slot was reserved before the
                # selector could allocate a Provider, so registration cannot
                # fail even when every other obligation is occupied.
                self._retain_provider_close_obligation(
                    selection.provider.close,
                    reservation=reservation,
                )
            else:
                self._provider_close_obligation_reservations.discard(reservation)
        finally:
            # Error/cancellation before Provider allocation releases the
            # reservation; a successful registration already consumed it.
            self._provider_close_obligation_reservations.discard(reservation)
        async with self._selection_lock:
            publishable = (
                not self._closed and self._selection_task is asyncio.current_task()
            )
            if publishable and self._selection is None:
                self._selection = selection
        if not publishable and selection.provider is not None:
            await self._bounded_provider_close(selection.provider.close)
        return selection

    async def _pump(self, handle: StreamingRecognitionHandle) -> None:
        while True:
            item = await handle.queue.get()
            if item is _QUEUE_SENTINEL:
                return
            if not isinstance(item, RecognitionAudioFrame):
                handle.failure = StreamingRecognitionFallbackReason.PROVIDER_PROTOCOL
                return
            try:
                # Publish the product-side send boundary before awaiting the
                # transport so a Provider delta that arrives reentrantly can
                # still be checked against the exact submitted cursor.
                handle.sent_sample_end = item.sample_cursor + item.sample_count
                await self._bounded_provider_call(
                    lambda: handle.provider.send_recognition_audio(item),
                    timeout_seconds=_PROVIDER_SEND_TIMEOUT_SECONDS,
                    task_name=(
                        f"live-voice-streaming-stt-send-{handle.ref.session_id}-{item.seq}"
                    ),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                handle.failure = StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE
                return

    async def _collect_final(
        self, handle: StreamingRecognitionHandle
    ) -> StreamingRecognitionEvent:
        while True:
            event_timeout = (
                _FINAL_TIMEOUT_SECONDS
                if handle.committed
                else _PRECOMMIT_EVENT_TIMEOUT_SECONDS
            )
            event = await self._bounded_provider_call(
                lambda: handle.provider.next_recognition_event(
                    handle.ref, timeout_seconds=event_timeout
                ),
                timeout_seconds=event_timeout,
                task_name=f"live-voice-streaming-stt-event-{handle.ref.session_id}",
            )
            invalid_identity = (
                event.ref != handle.ref
                or event.provider != handle.provider.capability.provider
                or event.seq != handle.next_event_seq
            )
            if invalid_identity:
                del event
                raise RuntimeError("streaming recognition event was not exact")
            handle.next_event_seq += 1
            if isinstance(event, RecognitionTurnBoundaryEvent):
                await self._accept_turn_boundary(handle, event)
                del event
                continue
            if not isinstance(event, StreamingRecognitionEvent):
                del event
                raise RuntimeError("streaming recognition event was untyped")
            if event.hypothesis is None:
                del event
                raise RuntimeError("streaming recognition text was absent")
            audio_cursor = event.audio_cursor
            if audio_cursor is not None:
                if (
                    audio_cursor < handle.last_event_cursor
                    or audio_cursor > handle.sent_sample_end
                ):
                    del event
                    raise RuntimeError("streaming recognition cursor was not exact")
                handle.last_event_cursor = audio_cursor
            elif (
                not handle.input_fenced
                or event.timing_basis is not RecognitionTimingBasis.PROVIDER_TIME
                or event.timing_provenance is not CapabilityProvenance.ADAPTER_DERIVED
            ):
                del event
                raise RuntimeError("streaming recognition timing was unproven")
            if event.kind is RecognitionEventKind.FINAL:
                # Provider-native server VAD owns the input fence.  Its final
                # transcript may race ahead of the browser's follow-up finish
                # RPC after speech_stopped; that final is already committed by
                # the authoritative Provider boundary.  Manual streams still
                # require the explicit client commit below.
                if not handle.committed and not handle.input_fenced:
                    del event
                    raise RuntimeError("streaming recognition final was not committed")
                if (
                    not handle.input_fenced
                    and event.audio_cursor != handle.sent_sample_end
                ):
                    del event
                    raise RuntimeError("manual recognition cursor was not committed")
                return event
            if event.kind is RecognitionEventKind.CANCELLED:
                del event
                raise RuntimeError("streaming recognition was cancelled")
            if event.kind is not RecognitionEventKind.PARTIAL:
                del event
                raise RuntimeError("streaming recognition event kind is unsupported")
            # Do not retain the previous partial transcript in the coroutine
            # frame while awaiting the next Provider event.
            del event

    async def _accept_turn_boundary(
        self,
        handle: StreamingRecognitionHandle,
        event: RecognitionTurnBoundaryEvent,
    ) -> None:
        if event.kind is RecognitionTurnBoundaryKind.SPEECH_STARTED:
            if handle.speech_start_ms is not None or event.provider_start_ms is None:
                raise RuntimeError("speech start boundary was duplicated")
            handle.speech_start_ms = event.provider_start_ms
            future = handle.speech_start
            if future is None or future.done():
                raise RuntimeError("speech-start boundary was not uniquely negotiated")
            future.set_result(
                StreamingRecognitionSpeechStart(
                    provider=event.provider,
                    provider_start_ms=event.provider_start_ms,
                )
            )
            return
        if event.kind is RecognitionTurnBoundaryKind.SPEECH_STOPPED:
            if (
                handle.speech_start_ms is None
                or handle.speech_stopped
                or event.provider_end_ms is None
                or event.provider_end_ms < handle.speech_start_ms
            ):
                raise RuntimeError("speech stop boundary was invalid")
            handle.speech_stopped = True
            handle.input_fenced = True
            while True:
                try:
                    queued = handle.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if isinstance(queued, RecognitionAudioFrame):
                    del queued
            pump = handle.pump_task
            if pump is not None and not pump.done():
                pump.cancel()
            future = handle.end_of_turn
            if future is None or future.done():
                raise RuntimeError("end-of-turn boundary was not uniquely negotiated")
            future.set_result(
                StreamingRecognitionEndOfTurn(
                    provider=event.provider,
                    provider_start_ms=handle.speech_start_ms,
                    provider_end_ms=event.provider_end_ms,
                )
            )
            return
        if event.kind is RecognitionTurnBoundaryKind.COMMITTED:
            if not handle.speech_stopped:
                raise RuntimeError("server commit preceded speech stop")
            return
        raise RuntimeError("turn boundary kind was unsupported")

    async def _bounded_provider_call(
        self,
        factory: Callable[[], Awaitable[_T]],
        *,
        timeout_seconds: float,
        task_name: str,
    ) -> _T:
        task = self._start_provider_task(factory, task_name=task_name)
        return await self._await_bounded_provider_task(
            task, timeout_seconds=timeout_seconds
        )

    def _start_provider_task(
        self,
        factory: Callable[[], Awaitable[_T]],
        *,
        task_name: str,
    ) -> asyncio.Task[_T]:
        """Atomically admit and start one capacity-owned Provider operation."""

        self._prune_provider_task_capacity()
        if self._provider_task_capacity_in_use >= _MAX_RETAINED_PROVIDER_TASKS:
            raise RuntimeError("streaming provider cleanup capacity is exhausted")
        # There is no await between reservation and task publication.  Event
        # loop peers therefore cannot pass the same last-slot check.
        self._provider_task_capacity_in_use += 1

        async def invoke() -> _T:
            return await factory()

        try:
            task: asyncio.Task[_T] = asyncio.create_task(invoke(), name=task_name)
        except BaseException:
            self._provider_task_capacity_in_use -= 1
            raise
        self._provider_capacity_tasks.add(task)
        task.add_done_callback(self._release_provider_task_capacity)
        return task

    async def _await_bounded_provider_task(
        self,
        task: asyncio.Task[_T],
        *,
        timeout_seconds: float,
    ) -> _T:
        try:
            done, _pending = await asyncio.wait({task}, timeout=timeout_seconds)
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
            self._retain_provider_task(task)
            raise
        if task not in done:
            task.cancel()
            self._retain_provider_task(task)
            raise TimeoutError("streaming provider operation timed out")
        try:
            return task.result()
        finally:
            self._release_provider_task_capacity(task)

    async def _bounded_provider_close(
        self, factory: Callable[[], Awaitable[None]]
    ) -> None:
        self._prune_provider_close_tasks()
        identity_key, identity = self._retain_provider_close_obligation(factory)
        if self._closed_provider_owners.get(identity_key) is identity:
            return
        retained = self._provider_close_tasks.get(identity_key)
        task = retained[1] if retained is not None and retained[0] is identity else None
        if task is None:
            task = self._start_provider_cleanup_task(
                factory,
                task_name="live-voice-streaming-speech-provider-close",
            )
            self._provider_close_tasks[identity_key] = (identity, task)
        done, _pending = await asyncio.wait(
            {task}, timeout=_PROVIDER_CLOSE_TIMEOUT_SECONDS
        )
        if task not in done:
            task.cancel()
            self._retain_provider_task(task)
            raise TimeoutError("streaming provider operation timed out")
        self._release_provider_cleanup_task_capacity(task)
        try:
            task.result()
        except BaseException:
            retained = self._provider_close_tasks.get(identity_key)
            if retained is not None and retained[0] is identity and retained[1] is task:
                self._provider_close_tasks.pop(identity_key, None)
            raise
        retained = self._provider_close_tasks.get(identity_key)
        if retained is not None and retained[0] is identity and retained[1] is task:
            self._provider_close_tasks.pop(identity_key, None)
            self._complete_provider_close_obligation(identity_key, identity)

    def _prune_provider_close_tasks(self) -> None:
        for identity_key, (identity, task) in tuple(self._provider_close_tasks.items()):
            if not task.done():
                continue
            self._provider_close_tasks.pop(identity_key, None)
            self._release_provider_cleanup_task_capacity(task)
            if task.cancelled():
                continue
            try:
                task.result()
            except BaseException:
                continue
            self._complete_provider_close_obligation(identity_key, identity)

    def _retain_provider_close_obligation(
        self,
        factory: Callable[[], Awaitable[None]],
        *,
        reservation: object | None = None,
    ) -> tuple[int, object]:
        owner = getattr(factory, "__self__", None)
        identity: object = owner if owner is not None else factory
        identity_key = id(identity)
        if self._closed_provider_owners.get(identity_key) is identity:
            if reservation is not None:
                self._provider_close_obligation_reservations.discard(reservation)
            return identity_key, identity
        retained = self._provider_close_obligations.get(identity_key)
        if retained is not None and retained[0] is identity:
            if reservation is not None:
                self._provider_close_obligation_reservations.discard(reservation)
            return identity_key, identity
        owns_reservation = (
            reservation is not None
            and reservation in self._provider_close_obligation_reservations
        )
        unreserved_total = len(self._provider_close_obligations) + len(
            self._provider_close_obligation_reservations
        )
        if not owns_reservation and unreserved_total >= _MAX_PROVIDER_CLOSE_OBLIGATIONS:
            raise RuntimeError(
                "streaming provider cleanup obligation capacity is exhausted"
            )
        if owns_reservation:
            self._provider_close_obligation_reservations.discard(reservation)
        self._provider_close_obligations[identity_key] = (identity, factory)
        return identity_key, identity

    def _complete_provider_close_obligation(
        self, identity_key: int, identity: object
    ) -> None:
        retained = self._provider_close_obligations.get(identity_key)
        if retained is not None and retained[0] is identity:
            self._provider_close_obligations.pop(identity_key, None)
        self._closed_provider_owners[identity_key] = identity
        while len(self._closed_provider_owners) > _MAX_PROVIDER_CLOSE_OBLIGATIONS:
            self._closed_provider_owners.pop(next(iter(self._closed_provider_owners)))

    def _start_provider_cleanup_task(
        self,
        factory: Callable[[], Awaitable[_T]],
        *,
        task_name: str,
    ) -> asyncio.Task[_T]:
        self._prune_provider_cleanup_task_capacity()
        if self._provider_cleanup_capacity_in_use >= _MAX_PROVIDER_CLEANUP_TASKS:
            raise RuntimeError("streaming provider cleanup task capacity is exhausted")
        self._provider_cleanup_capacity_in_use += 1

        async def invoke() -> _T:
            return await factory()

        try:
            task: asyncio.Task[_T] = asyncio.create_task(invoke(), name=task_name)
        except BaseException:
            self._provider_cleanup_capacity_in_use -= 1
            raise
        self._provider_cleanup_tasks.add(task)
        task.add_done_callback(self._release_provider_cleanup_task_capacity)
        return task

    def _release_provider_cleanup_task_capacity(self, task: asyncio.Task[Any]) -> None:
        if task not in self._provider_cleanup_tasks:
            return
        self._provider_cleanup_tasks.discard(task)
        self._provider_cleanup_capacity_in_use -= 1

    def _prune_provider_cleanup_task_capacity(self) -> None:
        for task in tuple(self._provider_cleanup_tasks):
            if task.done():
                self._release_provider_cleanup_task_capacity(task)

    async def _cancel_local_task(self, task: asyncio.Task[Any]) -> BaseException | None:
        if task.done():
            try:
                task.result()
            except _PROCESS_CONTROL as exc:
                return exc
            except (Exception, asyncio.CancelledError):
                pass
            return None
        task.cancel()
        done, _pending = await asyncio.wait(
            {task}, timeout=_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS
        )
        if task not in done:
            self._retain_provider_task(task)
            return None
        try:
            task.result()
        except _PROCESS_CONTROL as exc:
            return exc
        except (Exception, asyncio.CancelledError):
            pass
        return None

    def _retain_provider_task(self, task: asyncio.Task[Any]) -> None:
        if task in self._retained_provider_tasks:
            return
        self._retained_provider_tasks.add(task)
        task.add_done_callback(self._release_provider_task)

    def _release_provider_task_capacity(self, task: asyncio.Task[Any]) -> None:
        if task not in self._provider_capacity_tasks:
            return
        self._provider_capacity_tasks.discard(task)
        self._provider_task_capacity_in_use -= 1

    def _prune_provider_task_capacity(self) -> None:
        for task in tuple(self._provider_capacity_tasks):
            if task.done():
                self._release_provider_task_capacity(task)

    def _release_provider_task(self, task: asyncio.Task[Any]) -> None:
        self._retained_provider_tasks.discard(task)
        if task.cancelled():
            return
        try:
            failure = task.exception()
        except asyncio.CancelledError:
            return
        if isinstance(failure, _PROCESS_CONTROL):
            self._retained_process_control = self._safe_process_control(failure)

    def _prune_retained_provider_tasks(self) -> None:
        for task in tuple(self._retained_provider_tasks):
            if task.done():
                self._release_provider_task(task)

    def _take_retained_process_control(self) -> BaseException | None:
        process_control = self._retained_process_control
        self._retained_process_control = None
        return process_control

    @staticmethod
    def _safe_process_control(exc: BaseException) -> BaseException:
        if isinstance(exc, KeyboardInterrupt):
            return KeyboardInterrupt()
        if isinstance(exc, SystemExit):
            return SystemExit()
        return GeneratorExit()

    async def _release_handle(self, handle: StreamingRecognitionHandle) -> None:
        stream_key = self._stream_key(handle.ref)
        async with self._handle_lock:
            if self._handles.get(stream_key) is handle:
                self._handles.pop(stream_key, None)

    async def _release_stream_reservation(
        self, stream_key: tuple[str, int, str, int]
    ) -> None:
        async with self._handle_lock:
            if self._handles.get(stream_key) is None:
                self._handles.pop(stream_key, None)

    async def _release_opening_task(
        self,
        stream_key: tuple[str, int, str, int],
        operation_task: asyncio.Task[Any],
        provider_task: asyncio.Task[None],
    ) -> None:
        async with self._handle_lock:
            if self._opening_tasks.get(stream_key) == (
                operation_task,
                provider_task,
            ):
                self._opening_tasks.pop(stream_key, None)

    @staticmethod
    def _stream_key(ref: RecognitionStreamRef) -> tuple[str, int, str, int]:
        return (
            ref.session_id,
            ref.session_generation,
            ref.capture.capture_id,
            ref.capture.capture_generation,
        )

    @staticmethod
    def _selection_reason(
        fact: SpeechDegradationFact | None,
    ) -> StreamingRecognitionFallbackReason:
        if fact is None:
            return StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE
        try:
            return StreamingRecognitionFallbackReason(fact.reason.value)
        except ValueError:
            return StreamingRecognitionFallbackReason.PROVIDER_UNAVAILABLE

    @staticmethod
    def _fallback(
        reason: StreamingRecognitionFallbackReason, tier: SpeechRouteTier
    ) -> StreamingRecognitionOutcome:
        _LOGGER.warning(
            "live_voice_streaming_recognition_fallback reason=%s target=%s visible=true",
            reason.value,
            tier.value,
        )
        return StreamingRecognitionOutcome(
            completed=False,
            final_text=None,
            provider=None,
            fallback_tier=tier,
            reason=reason,
        )


def _settle_eot_from_collector(
    handle: StreamingRecognitionHandle,
    task: asyncio.Task[StreamingRecognitionEvent],
) -> None:
    future = handle.end_of_turn
    if future is None or future.done():
        return
    try:
        failure = None if task.cancelled() else task.exception()
    except BaseException:
        failure = RuntimeError("streaming recognition collector failed")
    if task.cancelled() or failure is not None:
        speech_start = handle.speech_start
        if speech_start is not None and not speech_start.done():
            speech_start.set_exception(
                RuntimeError("streaming recognition speech-start failed")
            )
        future.set_exception(RuntimeError("streaming recognition EOT failed"))
        return
    speech_start = handle.speech_start
    if speech_start is not None and not speech_start.done():
        speech_start.set_exception(
            RuntimeError("streaming recognition speech-start was absent")
        )
    future.set_exception(RuntimeError("streaming recognition EOT was absent"))


def _eot_collector_callback(
    handle: StreamingRecognitionHandle,
) -> Callable[[asyncio.Task[StreamingRecognitionEvent]], None]:
    def settle(task: asyncio.Task[StreamingRecognitionEvent]) -> None:
        _settle_eot_from_collector(handle, task)

    return settle


def _consume_eot_future_failure(
    future: asyncio.Future[StreamingRecognitionEndOfTurn],
) -> None:
    if future.cancelled():
        return
    try:
        future.exception()
    except BaseException:
        return


def _consume_speech_start_future_failure(
    future: asyncio.Future[StreamingRecognitionSpeechStart],
) -> None:
    if future.cancelled():
        return
    try:
        future.exception()
    except BaseException:
        return


__all__ = [
    "StreamingRecognitionEndOfTurn",
    "StreamingRecognitionFallbackReason",
    "StreamingRecognitionHandle",
    "StreamingRecognitionOutcome",
    "StreamingRecognitionRouteOwner",
    "StreamingRecognitionSpeechStart",
]
