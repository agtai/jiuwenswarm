# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Speculative dialogue inference: model work before the decision, no effects.

The per-turn semantic decision and the Agent's first model call are both
bounded by the model's first-token latency.  A ``SpeculativeDialogue`` starts
the formal Agent stream for a committed turn at submit time, while the
semantic decision is still open, and keeps everything it produces in a
bounded in-process buffer.  Nothing of it is an effect: its tool calls are
paused at the execution seam of the lower Agent adapter, no Runtime response,
Bridge dispatch, journal effect, history record or notification exists for
it, and no consumer can observe it.

Only a complete decision settles it.  ``attach`` hands the buffered prefix
and the live tail to the formal round that the decision admitted, exactly as
if that round had produced them, and resumes the paused tools.  ``discard``
cancels the stream and aborts its paused tools; nothing it produced survives.
A candidate that outgrew its buffer, failed, or does not match the admitted
round's commit, context or tool policy is never attached.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalAgentExecution,
)

_LOGGER = logging.getLogger(__name__)

SPECULATION_MAX_CHUNKS = 2048
SPECULATION_MAX_BYTES = 262_144
_SPECULATIVE_SESSION_PREFIX = "lv-formal-spec-"


class SpeculativeDialogueViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode = ErrorCode.CONFLICT) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class SpeculativeFormalFacade(Protocol):
    """The formal seam plus the tool execution gate of the lower adapter."""

    def supports_formal_live_voice(self) -> bool: ...

    def process_formal_live_voice_stream(
        self, execution: FormalAgentExecution
    ) -> AsyncIterator[AgentResponseChunk]: ...

    def pause_formal_tools(self, session_id: str) -> None: ...

    def resume_formal_tools(self, session_id: str) -> None: ...

    def abort_formal_tools(self, session_id: str) -> None: ...


def facade_supports_speculation(facade: object) -> bool:
    supports = getattr(facade, "supports_formal_live_voice", None)
    if not callable(supports) or not supports():
        return False
    # A facade that knows whether its lower adapter exposes the tool gate
    # answers for itself; a plain method check would accept a gate that
    # fails at the first pause.
    probe = getattr(facade, "supports_speculative_dialogue", None)
    if callable(probe) and not probe():
        return False
    return all(
        callable(getattr(facade, name, None))
        for name in (
            "process_formal_live_voice_stream",
            "pause_formal_tools",
            "resume_formal_tools",
            "abort_formal_tools",
        )
    )


def speculative_session_id(token: str) -> str:
    return f"{_SPECULATIVE_SESSION_PREFIX}{token}"


def _context_signature(execution: FormalAgentExecution) -> tuple[bytes, tuple[tuple[str, str], ...]]:
    entries = tuple(
        (json.dumps(entry.ref.to_dict(), sort_keys=True, separators=(",", ":")), entry.content)
        for entry in execution.context.entries
    )
    return execution.commit.canonical_bytes(), entries


def _chunk_bytes(chunk: AgentResponseChunk) -> int:
    payload = chunk.payload if isinstance(chunk.payload, dict) else {}
    try:
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return SPECULATION_MAX_BYTES


class SpeculativeDialogue:
    """One candidate dialogue inference for one committed turn."""

    def __init__(
        self,
        *,
        facade: SpeculativeFormalFacade,
        execution: FormalAgentExecution,
        max_chunks: int = SPECULATION_MAX_CHUNKS,
        max_bytes: int = SPECULATION_MAX_BYTES,
        on_settle: Callable[["SpeculativeDialogue"], None] | None = None,
    ) -> None:
        if not facade_supports_speculation(facade):
            raise SpeculativeDialogueViolation(
                "SPECULATION_UNAVAILABLE",
                "the Agent facade exposes no formal tool execution gate",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if not isinstance(execution, FormalAgentExecution):
            raise TypeError("speculative dialogue requires a FormalAgentExecution")
        if not execution.internal_session_id.startswith(_SPECULATIVE_SESSION_PREFIX):
            raise SpeculativeDialogueViolation(
                "SPECULATION_SESSION_INVALID",
                "a speculative execution needs its own formal session identity",
                ErrorCode.INVALID_ARGUMENT,
            )
        if type(max_chunks) is not int or max_chunks <= 0 or type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("speculation limits must be positive integers")
        self._facade = facade
        self._execution = execution
        self._signature = _context_signature(execution)
        self._max_chunks = max_chunks
        self._max_bytes = max_bytes
        self._on_settle = on_settle
        self._state = "created"
        self._buffer: deque[tuple[AgentResponseChunk, int]] = deque()
        self._bytes = 0
        self._ended = False
        self._overflow = False
        self._error: BaseException | None = None
        self._wakeup = asyncio.Event()
        self._space_available = asyncio.Event()
        self._tools_aborted = False
        self._cancel_requested = False
        self._stream_closing = False
        self._task: asyncio.Task[None] | None = None
        self._stream: AsyncIterator[AgentResponseChunk] | None = None
        self._started_at = time.monotonic()
        self._first_chunk_at: float | None = None
        self._settled_reason: str | None = None

    # -- identity -----------------------------------------------------------

    @property
    def request_id(self) -> str:
        return self._execution.request_id

    @property
    def session_id(self) -> str:
        return self._execution.internal_session_id

    @property
    def state(self) -> str:
        return self._state

    @property
    def settled(self) -> bool:
        return self._state in {"discarded", "attached"} and self._ended and not self._buffer

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "chunks": len(self._buffer),
            "bytes": self._bytes,
            "ended": self._ended,
            "overflow": self._overflow,
            "failed": self._error is not None,
            "reason": self._settled_reason,
        }

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._state != "created":
            raise SpeculativeDialogueViolation(
                "SPECULATION_ALREADY_STARTED", "a speculative dialogue starts once"
            )
        loop = asyncio.get_running_loop()
        # The pause precedes the first model call, so no tool can run before
        # the decision even if the model answers with a tool call immediately.
        try:
            self._facade.pause_formal_tools(self.session_id)
        except Exception as error:  # noqa: BLE001 - fail closed to the serial path
            raise SpeculativeDialogueViolation(
                "SPECULATION_TOOL_GATE_UNAVAILABLE",
                "formal tool execution could not be paused",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            ) from error
        self._state = "pending"
        self._started_at = time.monotonic()
        self._task = loop.create_task(
            self._pump(), name=f"live-voice-speculative-dialogue:{self.request_id}"
        )
        _LOGGER.info(
            "live_voice_speculation_started request_id=%s session=%s",
            self.request_id, self.session_id,
        )

    async def _pump(self) -> None:
        stream = self._facade.process_formal_live_voice_stream(self._execution)
        self._stream = stream
        exhausted = False
        try:
            async for chunk in stream:
                if self._first_chunk_at is None:
                    self._first_chunk_at = time.monotonic()
                size = _chunk_bytes(chunk)
                if size > self._max_bytes:
                    raise SpeculativeDialogueViolation(
                        "SPECULATION_CHUNK_TOO_LARGE", "Agent chunk exceeds the buffer byte bound",
                        ErrorCode.UNAVAILABLE,
                    )
                while len(self._buffer) >= self._max_chunks or self._bytes + size > self._max_bytes:
                    if self._state != "attached":
                        # An unadmitted candidate cannot wait for a consumer.
                        # Reject it so the selected route can use its serial path.
                        self._overflow = True
                        break
                    # Only unread data occupies this buffer. Wait for consumption
                    # without changing or discarding the admitted Agent output.
                    self._space_available.clear()
                    await self._space_available.wait()
                if self._overflow:
                    break
                self._buffer.append((chunk, size))
                self._bytes += size
                self._wakeup.set()
            else:
                exhausted = True
        except asyncio.CancelledError:
            raise
        except BaseException as error:  # noqa: BLE001 - retained for the attach decision
            self._error = error
        finally:
            # The task that drives the iterator must also close it: the formal
            # adapter holds permission ContextVar tokens across its yields.
            try:
                self._stream_closing = True
                await self._close_stream()
            finally:
                if not exhausted:
                    self._abort_tools()
                self._ended = True
                self._wakeup.set()

    async def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        close = getattr(stream, "aclose", None)
        if callable(close):
            try:
                await close()
            except BaseException as error:  # noqa: BLE001 - best effort cleanup
                if self._error is None:
                    self._error = error
                _LOGGER.warning(
                    "live_voice_speculation_stream_close_failed request_id=%s kind=%s",
                    self.request_id, type(error).__name__,
                )

    def _abort_tools(self) -> None:
        if self._tools_aborted:
            return
        self._tools_aborted = True
        try:
            self._facade.abort_formal_tools(self.session_id)
        except Exception as error:  # noqa: BLE001 - best effort cleanup
            _LOGGER.warning(
                "live_voice_speculation_tool_abort_failed request_id=%s kind=%s",
                self.request_id, type(error).__name__,
            )

    # -- decision -------------------------------------------------------------

    def attachable(self, execution: FormalAgentExecution) -> bool:
        """The admitted round may take this candidate over only if it is the same work."""

        if self._state != "pending" or self._overflow or self._error is not None:
            return False
        if not isinstance(execution, FormalAgentExecution):
            return False
        if (
            execution.request_id != self._execution.request_id
            or execution.channel_id != self._execution.channel_id
            or execution.allow_tools != self._execution.allow_tools
            or execution.answer_from_selected_task_result
            != self._execution.answer_from_selected_task_result
        ):
            return False
        return _context_signature(execution) == self._signature

    def attach(self, execution: FormalAgentExecution) -> AsyncIterator[AgentResponseChunk]:
        if not self.attachable(execution):
            raise SpeculativeDialogueViolation(
                "SPECULATION_NOT_ATTACHABLE",
                "the admitted round does not match the speculative candidate",
            )
        self._state = "attached"
        self._settled_reason = "attached"
        try:
            self._facade.resume_formal_tools(self.session_id)
        except Exception as error:  # noqa: BLE001 - a stuck gate must not silently hang the round
            self._state = "pending"
            self._settled_reason = None
            raise SpeculativeDialogueViolation(
                "SPECULATION_TOOL_GATE_UNAVAILABLE",
                "formal tool execution could not be resumed",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            ) from error
        lead_ms = (
            (time.monotonic() - self._first_chunk_at) * 1000.0
            if self._first_chunk_at is not None
            else None
        )
        _LOGGER.info(
            "live_voice_speculation_attached request_id=%s buffered_chunks=%d buffered_bytes=%d first_chunk_lead_ms=%s",
            self.request_id, len(self._buffer), self._bytes,
            "n/a" if lead_ms is None else f"{lead_ms:.0f}",
        )
        return self._replay()

    async def _replay(self) -> AsyncIterator[AgentResponseChunk]:
        try:
            while True:
                while self._buffer:
                    chunk, size = self._buffer.popleft()
                    self._bytes -= size
                    self._space_available.set()
                    yield chunk
                if self._ended:
                    break
                # No await sits between this check and the wait, so the pump
                # cannot append a chunk that this consumer would then miss.
                if not self._buffer and not self._ended:
                    self._wakeup.clear()
                    await self._wakeup.wait()
            if self._error is not None:
                raise self._error
        finally:
            try:
                if not self._ended:
                    # The admitted round closed early (cancel, interruption,
                    # failure); its producer retains stream cleanup ownership.
                    await self._cancel_pump()
                    self._abort_tools()
            finally:
                self._buffer.clear()
                self._bytes = 0
                self._settle()

    async def discard(self, reason: str) -> None:
        if self.settled:
            return
        previous = self._state
        self._state = "discarded"
        if previous != "discarded":
            self._settled_reason = reason
        try:
            if previous != "created":
                await self._cancel_pump()
        finally:
            if previous != "created":
                self._abort_tools()
            self._ended = True
            self._buffer.clear()
            self._bytes = 0
            self._wakeup.set()
            self._settle()
        _LOGGER.info(
            "live_voice_speculation_discarded request_id=%s reason=%s chunks=%d bytes=%d elapsed_ms=%.0f",
            self.request_id, reason, len(self._buffer), self._bytes,
            (time.monotonic() - self._started_at) * 1000.0,
        )

    async def _cancel_pump(self) -> None:
        task = self._task
        if task is not None and not task.done():
            if not self._cancel_requested and not self._stream_closing:
                self._cancel_requested = True
                task.cancel()
            # Concurrent close/discard and cancelled waiters must not deliver
            # another cancellation into the producer's resource cleanup.
            joined = asyncio.gather(task, return_exceptions=True)
            cancelled = False
            while not joined.done():
                try:
                    await asyncio.shield(joined)
                except asyncio.CancelledError:
                    cancelled = True
            if cancelled:
                raise asyncio.CancelledError

    def _settle(self) -> None:
        callback, self._on_settle = self._on_settle, None
        if callback is not None:
            callback(self)


class AttachedFormalFacade:
    """A facade for one admitted round that takes a speculative candidate over.

    When the admitted execution matches the candidate, the round consumes the
    candidate's buffered prefix and live tail.  Otherwise the candidate is
    discarded and the round runs on the real facade, which keeps the serial
    behaviour as the fallback for any mismatch.
    """

    def __init__(self, speculation: SpeculativeDialogue, fallback: object) -> None:
        self._speculation = speculation
        self._fallback = fallback

    def supports_formal_live_voice(self) -> bool:
        supports = getattr(self._fallback, "supports_formal_live_voice", None)
        return bool(callable(supports) and supports())

    async def process_formal_live_voice_stream(
        self, execution: FormalAgentExecution
    ) -> AsyncIterator[AgentResponseChunk]:
        if self._speculation.attachable(execution):
            source = self._speculation.attach(execution)
        else:
            await self._speculation.discard("not_attachable")
            source = self._fallback.process_formal_live_voice_stream(execution)
        try:
            async for chunk in source:
                yield chunk
        finally:
            close = getattr(source, "aclose", None)
            if callable(close):
                await close()


__all__ = [
    "SPECULATION_MAX_BYTES",
    "SPECULATION_MAX_CHUNKS",
    "AttachedFormalFacade",
    "SpeculativeDialogue",
    "SpeculativeDialogueViolation",
    "SpeculativeFormalFacade",
    "facade_supports_speculation",
    "speculative_session_id",
]
