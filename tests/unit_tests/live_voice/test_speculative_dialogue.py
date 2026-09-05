# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Speculative dialogue inference: buffered model work, gated execution, no leaks."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.server.live_voice.speculative_dialogue import (
    AttachedFormalFacade,
    SpeculativeDialogue,
    SpeculativeDialogueViolation,
    facade_supports_speculation,
    speculative_session_id,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalAgentExecution,
    FormalContextSnapshot,
)
from tests.unit_tests.live_voice.test_agent_conversation_runtime import commit


class FakeFacade:
    def __init__(
        self,
        payloads: list[dict[str, object]],
        *,
        hold_before: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.payloads = payloads
        self.hold_before = hold_before
        self.release = asyncio.Event()
        self.error = error
        self.paused: list[str] = []
        self.resumed: list[str] = []
        self.aborted: list[str] = []
        self.streams = 0
        self.closed = 0
        self.started = asyncio.Event()

    def supports_formal_live_voice(self) -> bool:
        return True

    async def process_formal_live_voice_stream(
        self, execution: FormalAgentExecution
    ) -> AsyncIterator[AgentResponseChunk]:
        self.streams += 1
        self.started.set()
        try:
            for index, payload in enumerate(self.payloads):
                if self.hold_before is not None and index == self.hold_before:
                    await self.release.wait()
                yield AgentResponseChunk(
                    request_id=execution.request_id,
                    channel_id=execution.channel_id,
                    payload=payload,
                    is_complete=index == len(self.payloads) - 1,
                )
            if self.error is not None:
                raise self.error
        finally:
            self.closed += 1

    def pause_formal_tools(self, session_id: str) -> None:
        self.paused.append(session_id)

    def resume_formal_tools(self, session_id: str) -> None:
        self.resumed.append(session_id)

    def abort_formal_tools(self, session_id: str) -> None:
        self.aborted.append(session_id)


def _execution(**changes) -> FormalAgentExecution:
    selected = commit()
    fields = {
        "request_id": "unified-agent-1",
        "channel_id": "web",
        "internal_session_id": speculative_session_id("abc"),
        "commit": selected,
        "context": FormalContextSnapshot(selected.scope),
        "allow_tools": True,
    }
    fields.update(changes)
    return FormalAgentExecution(**fields)


def _payloads(count: int) -> list[dict[str, object]]:
    deltas = [{"event_type": "chat.delta", "content": f"piece-{i} "} for i in range(count - 1)]
    return [*deltas, {"event_type": "chat.final", "content": "final answer"}]


async def _collect(stream: AsyncIterator[AgentResponseChunk]) -> list[str]:
    return [str(chunk.payload["content"]) async for chunk in stream]


@pytest.mark.asyncio
async def test_start_pauses_tools_before_the_first_model_call() -> None:
    facade = FakeFacade(_payloads(3), hold_before=0)
    execution = _execution()
    candidate = SpeculativeDialogue(facade=facade, execution=execution)
    assert candidate.state == "created" and facade.streams == 0
    candidate.start()
    assert facade.paused == [execution.internal_session_id]
    assert facade.streams == 0, "the stream starts on the loop, after the pause is in place"
    await facade.started.wait()
    assert candidate.state == "pending" and facade.resumed == [] and facade.aborted == []
    await candidate.discard("test")


@pytest.mark.asyncio
async def test_attach_replays_the_buffered_prefix_then_the_live_tail_in_order() -> None:
    facade = FakeFacade(_payloads(5), hold_before=3)
    execution = _execution()
    settled: list[str] = []
    candidate = SpeculativeDialogue(
        facade=facade, execution=execution, on_settle=lambda c: settled.append(c.state)
    )
    candidate.start()
    await asyncio.sleep(0.02)
    assert candidate.snapshot()["chunks"] == 3, "three chunks buffered while the decision is open"
    assert candidate.attachable(_execution())
    stream = candidate.attach(_execution())
    assert facade.resumed == [execution.internal_session_id]
    facade.release.set()
    assert await _collect(stream) == ["piece-0 ", "piece-1 ", "piece-2 ", "piece-3 ", "final answer"]
    assert candidate.settled and candidate.state == "attached"
    assert settled == ["attached"]
    assert facade.streams == 1 and facade.aborted == []


@pytest.mark.asyncio
async def test_discard_cancels_the_model_work_and_aborts_the_paused_tools() -> None:
    facade = FakeFacade(_payloads(3), hold_before=1)
    execution = _execution()
    settled: list[str] = []
    candidate = SpeculativeDialogue(
        facade=facade, execution=execution, on_settle=lambda c: settled.append(c.state)
    )
    candidate.start()
    await asyncio.sleep(0.02)
    await candidate.discard("route:task")
    assert candidate.state == "discarded" and candidate.settled
    assert facade.aborted == [execution.internal_session_id]
    assert facade.closed == 1, "the cancelled stream ran its cleanup"
    assert candidate.snapshot() == {
        "state": "discarded", "chunks": 0, "bytes": 0, "ended": True,
        "overflow": False, "failed": False, "reason": "route:task",
    }
    await candidate.discard("again")
    assert settled == ["discarded"] and facade.aborted == [execution.internal_session_id]
    assert not candidate.attachable(_execution())
    with pytest.raises(SpeculativeDialogueViolation) as refusal:
        candidate.attach(_execution())
    assert refusal.value.reason == "SPECULATION_NOT_ATTACHABLE"


@pytest.mark.asyncio
async def test_only_the_same_work_is_attachable() -> None:
    facade = FakeFacade(_payloads(2), hold_before=1)
    candidate = SpeculativeDialogue(facade=facade, execution=_execution())
    candidate.start()
    await asyncio.sleep(0.01)
    assert candidate.attachable(_execution())
    assert not candidate.attachable(_execution(request_id="unified-agent-2"))
    assert not candidate.attachable(_execution(channel_id="tui"))
    assert not candidate.attachable(_execution(allow_tools=False))
    other = commit(turn_id="turn-other", commit_id="commit-other")
    assert not candidate.attachable(
        _execution(commit=other, context=FormalContextSnapshot(other.scope))
    )
    await candidate.discard("test")


@pytest.mark.asyncio
async def test_overflow_fails_closed_and_stops_the_candidate() -> None:
    facade = FakeFacade(_payloads(6), hold_before=None)
    execution = _execution()
    candidate = SpeculativeDialogue(facade=facade, execution=execution, max_chunks=2)
    candidate.start()
    await asyncio.sleep(0.02)
    snapshot = candidate.snapshot()
    assert snapshot["overflow"] and snapshot["chunks"] == 2 and snapshot["ended"]
    assert facade.aborted == [execution.internal_session_id]
    assert facade.closed == 1
    assert not candidate.attachable(_execution())
    await candidate.discard("overflow")


@pytest.mark.asyncio
async def test_a_failed_candidate_is_never_attached() -> None:
    facade = FakeFacade(_payloads(2), error=RuntimeError("provider failed"))
    candidate = SpeculativeDialogue(facade=facade, execution=_execution())
    candidate.start()
    await asyncio.sleep(0.02)
    assert candidate.snapshot()["failed"] and candidate.snapshot()["ended"]
    assert not candidate.attachable(_execution())
    await candidate.discard("failed")


@pytest.mark.asyncio
async def test_closing_the_attached_stream_early_kills_the_candidate() -> None:
    facade = FakeFacade(_payloads(4), hold_before=2)
    execution = _execution()
    candidate = SpeculativeDialogue(facade=facade, execution=execution)
    candidate.start()
    await asyncio.sleep(0.02)
    stream = candidate.attach(_execution())
    first = await stream.__anext__()
    assert first.payload["content"] == "piece-0 "
    await stream.aclose()
    assert candidate.settled
    assert facade.aborted == [execution.internal_session_id]
    assert facade.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bounds", [{"max_chunks": 2}, {"max_bytes": 130}])
async def test_attached_stream_backpressures_unread_data_and_releases_consumed_content(bounds) -> None:
    # A fast producer and slow consumer must work for arbitrarily many buffer
    # turnovers; neither total bytes nor total chunks is a response quota.
    payloads = _payloads(4097)
    facade = FakeFacade(payloads, hold_before=0)
    execution = _execution()
    candidate = SpeculativeDialogue(facade=facade, execution=execution, **bounds)
    candidate.start()
    await facade.started.wait()
    stream = candidate.attach(execution)
    facade.release.set()
    received = []
    async with asyncio.timeout(5):
        async for chunk in stream:
            received.append(chunk.payload)
            await asyncio.sleep(0)
            snapshot = candidate.snapshot()
            assert snapshot["chunks"] <= bounds.get("max_chunks", 2048)
            assert snapshot["bytes"] <= bounds.get("max_bytes", 262_144)
            assert not snapshot["overflow"]
    assert received == payloads
    assert candidate.snapshot()["chunks"] == candidate.snapshot()["bytes"] == 0
    assert facade.closed == 1 and facade.aborted == [] and facade.streams == 1


@pytest.mark.asyncio
async def test_cancel_backpressured_candidate_does_not_stop_another_candidate() -> None:
    left, right = FakeFacade(_payloads(20), hold_before=0), FakeFacade(_payloads(4), hold_before=0)
    a = SpeculativeDialogue(facade=left, execution=_execution(), max_chunks=2)
    other_execution = _execution(request_id="other", internal_session_id=speculative_session_id("other"))
    b = SpeculativeDialogue(facade=right, execution=other_execution, max_chunks=2)
    a.start()
    b.start()
    sa, sb = a.attach(_execution()), b.attach(other_execution)
    left.release.set()
    right.release.set()
    await anext(sa)
    await asyncio.sleep(0)
    assert not a.snapshot()["ended"], "a full unread buffer must wait, not stop the Agent"
    await sa.aclose()
    await sa.aclose()
    assert a.snapshot()["chunks"] == a.snapshot()["bytes"] == 0
    assert left.closed == 1 and left.aborted == [a.session_id]
    assert await _collect(sb) == [p["content"] for p in right.payloads]
    assert right.closed == 1 and right.aborted == []


@pytest.mark.asyncio
async def test_attached_oversize_chunk_fails_explicitly_and_releases_the_stream() -> None:
    facade = FakeFacade([{"event_type": "chat.final", "content": "x" * 200}], hold_before=0)
    candidate = SpeculativeDialogue(facade=facade, execution=_execution(), max_bytes=100)
    candidate.start()
    stream = candidate.attach(_execution())
    facade.release.set()
    with pytest.raises(SpeculativeDialogueViolation, match="chunk"):
        await _collect(stream)
    assert candidate.snapshot()["chunks"] == candidate.snapshot()["bytes"] == 0
    assert facade.closed == 1 and facade.aborted == [candidate.session_id]


@pytest.mark.asyncio
async def test_repeated_admitted_failures_release_buffer_and_close_in_producer_context() -> None:
    from contextvars import ContextVar

    marker = ContextVar("speculative-test-context", default=None)
    closed = []

    class ContextFacade(FakeFacade):
        async def process_formal_live_voice_stream(self, execution):
            token = marker.set(execution.internal_session_id)
            owner = asyncio.current_task()
            try:
                async for chunk in super().process_formal_live_voice_stream(execution):
                    yield chunk
            finally:
                marker.reset(token)
                closed.append(asyncio.current_task() is owner)

    for index in range(20):
        execution = _execution(internal_session_id=speculative_session_id(str(index)))
        facade = ContextFacade(_payloads(3), hold_before=1, error=RuntimeError("provider failed"))
        candidate = SpeculativeDialogue(facade=facade, execution=execution, max_chunks=2)
        candidate.start()
        await facade.started.wait()
        stream = candidate.attach(execution)
        facade.release.set()
        with pytest.raises(RuntimeError, match="provider failed"):
            await _collect(stream)
        assert candidate.snapshot()["chunks"] == candidate.snapshot()["bytes"] == 0
        assert facade.closed == 1
        assert marker.get() is None
    assert closed == [True] * 20


@pytest.mark.asyncio
async def test_concurrent_close_and_cancelled_discard_wait_for_producer_cleanup() -> None:
    cleanup_started, cleanup_release = asyncio.Event(), asyncio.Event()
    cleaned = []

    class SlowCloseFacade(FakeFacade):
        async def process_formal_live_voice_stream(self, execution):
            try:
                yield AgentResponseChunk(
                    request_id=execution.request_id, channel_id=execution.channel_id,
                    payload={"event_type": "chat.delta", "content": "first"},
                    is_complete=False,
                )
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await cleanup_release.wait()
                cleaned.append(True)

    facade = SlowCloseFacade([])
    candidate = SpeculativeDialogue(facade=facade, execution=_execution())
    candidate.start()
    stream = candidate.attach(_execution())
    await anext(stream)
    closing = asyncio.create_task(stream.aclose())
    await cleanup_started.wait()
    discarding = asyncio.create_task(candidate.discard("runtime_closing"))
    await asyncio.sleep(0)
    discarding.cancel()
    await asyncio.sleep(0)
    assert not candidate.settled
    cleanup_release.set()
    results = await asyncio.gather(closing, discarding, return_exceptions=True)
    assert cleaned == [True]
    assert isinstance(results[1], asyncio.CancelledError)
    await candidate.discard("again")
    assert candidate.settled
    assert candidate.snapshot()["chunks"] == candidate.snapshot()["bytes"] == 0
    assert facade.aborted == [candidate.session_id]


@pytest.mark.asyncio
async def test_attached_facade_takes_the_candidate_or_falls_back() -> None:
    fallback = FakeFacade(_payloads(2))
    facade = FakeFacade(_payloads(3), hold_before=1)
    execution = _execution()
    candidate = SpeculativeDialogue(facade=facade, execution=execution)
    candidate.start()
    await asyncio.sleep(0.01)
    facade.release.set()
    attached = AttachedFormalFacade(candidate, fallback)
    assert attached.supports_formal_live_voice()
    assert await _collect(attached.process_formal_live_voice_stream(_execution())) == [
        "piece-0 ", "piece-1 ", "final answer",
    ]
    assert fallback.streams == 0

    facade2 = FakeFacade(_payloads(3), hold_before=1)
    candidate2 = SpeculativeDialogue(facade=facade2, execution=_execution())
    candidate2.start()
    await asyncio.sleep(0.01)
    attached2 = AttachedFormalFacade(candidate2, fallback)
    assert await _collect(
        attached2.process_formal_live_voice_stream(_execution(request_id="unified-agent-2"))
    ) == ["piece-0 ", "final answer"]
    assert fallback.streams == 1 and candidate2.state == "discarded"
    assert facade2.aborted == [candidate2.session_id]


def test_facade_support_requires_the_full_tool_gate() -> None:
    class NoGate:
        def supports_formal_live_voice(self) -> bool:
            return True

        async def process_formal_live_voice_stream(self, execution):  # pragma: no cover
            yield None

    assert facade_supports_speculation(FakeFacade([]))
    assert not facade_supports_speculation(NoGate())
    with pytest.raises(SpeculativeDialogueViolation) as refusal:
        SpeculativeDialogue(facade=NoGate(), execution=_execution())
    assert refusal.value.reason == "SPECULATION_UNAVAILABLE"
    with pytest.raises(SpeculativeDialogueViolation) as bad_session:
        SpeculativeDialogue(
            facade=FakeFacade([]), execution=_execution(internal_session_id="lv-formal-real")
        )
    assert bad_session.value.reason == "SPECULATION_SESSION_INVALID"
