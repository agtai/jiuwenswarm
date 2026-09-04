# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""The runtime attaches a speculative candidate to the admitted round or discards it."""

from __future__ import annotations

import asyncio

import pytest

from jiuwenswarm.server.live_voice.agent_conversation_runtime import (
    AgentConversationRuntimeViolation,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)
from tests.unit_tests.live_voice.test_agent_conversation_runtime import (
    LowerFormalAdapter,
    RecordingHistoryWriter,
    commit,
    runtime,
)


class _FakeRail:
    def __init__(self) -> None:
        self.paused: list[str] = []
        self.resumed: list[str] = []
        self.aborted: list[str] = []

    def pause_tools(self, session_id: str = "") -> None:
        self.paused.append(session_id)

    def resume_tools(self, session_id: str = "") -> None:
        self.resumed.append(session_id)

    def abort(self, session_id: str = "") -> None:
        self.aborted.append(session_id)


class GatedLowerAdapter(LowerFormalAdapter):
    # A root adapter without per-session children: the facade falls back to
    # the adapter's own rail, which this double exposes directly.
    supports_formal_tool_gate = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stream_event_rail = _FakeRail()


async def _drain(current) -> list:
    drained = []
    while True:
        queued = current._notifications.get_nowait()
        if queued is None:
            return drained
        drained.append(queued)


@pytest.mark.asyncio
async def test_candidate_started_before_the_decision_is_attached_to_the_admitted_round() -> None:
    lower = GatedLowerAdapter(final="speculated answer", release=asyncio.Event())
    current = runtime(lower, RecordingHistoryWriter())
    selected = commit()
    await current.start()
    await current.open_interaction(selected.interaction_id)
    context = FormalContextSnapshot(selected.scope)

    candidate = current.begin_speculative_dialogue(
        request_id="request-1", commit=selected, context=context, channel_id="web"
    )
    await lower.started.wait()
    session = lower.requests[0].session_id
    assert session.startswith("lv-formal-spec-")
    assert lower._stream_event_rail.paused == [session]
    assert lower.calls == 1
    assert current.speculation_snapshot() == {"pending": 1, "states": {"request-1": "pending"}}
    # Nothing exists for the candidate: no response, no notification, no history.
    assert current.snapshot().queued_notifications == 0
    assert await _drain(current) == []

    handle = await current.submit_committed_turn(
        request_id="request-1",
        response_id="response-1",
        correlation_id="correlation-1",
        commit=selected,
        context=context,
        speculation=candidate,
    )
    assert lower._stream_event_rail.resumed == [session]
    lower.release.set()
    await handle.completion
    assert lower.calls == 1, "the admitted round consumed the candidate instead of running again"
    assert lower._stream_event_rail.aborted == []
    assert current.speculation_snapshot()["pending"] == 0
    await asyncio.sleep(0.05)
    assert current.snapshot().queued_notifications >= 1
    await current.close(timeout_seconds=1)


@pytest.mark.asyncio
async def test_a_mismatching_candidate_is_discarded_and_the_round_runs_on_the_real_facade() -> None:
    lower = GatedLowerAdapter(final="real answer")
    current = runtime(lower, RecordingHistoryWriter())
    selected = commit()
    await current.start()
    await current.open_interaction(selected.interaction_id)
    candidate = current.begin_speculative_dialogue(
        request_id="request-1",
        commit=selected,
        context=FormalContextSnapshot(selected.scope),
        channel_id="web",
        allow_tools=False,
    )
    await lower.started.wait()
    spec_session = lower.requests[0].session_id
    handle = await current.submit_committed_turn(
        request_id="request-1",
        response_id="response-1",
        correlation_id="correlation-1",
        commit=selected,
        context=FormalContextSnapshot(selected.scope),
        speculation=candidate,
        allow_tools=True,
    )
    await handle.completion
    assert lower.calls == 2, "tool policy differs: the real facade ran the round"
    assert lower.requests[1].session_id.startswith("lv-formal-") and not lower.requests[1].session_id.startswith("lv-formal-spec-")
    assert lower._stream_event_rail.aborted == [spec_session]
    assert lower._stream_event_rail.resumed == []
    assert candidate.state == "discarded"
    await current.close(timeout_seconds=1)


@pytest.mark.asyncio
async def test_close_discards_pending_candidates_and_ledgers_are_bounded() -> None:
    lower = GatedLowerAdapter(final="answer", release=asyncio.Event())
    current = runtime(lower, RecordingHistoryWriter())
    selected = commit()
    await current.start()
    await current.open_interaction(selected.interaction_id)
    context = FormalContextSnapshot(selected.scope)
    first = current.begin_speculative_dialogue(
        request_id="request-1", commit=selected, context=context, channel_id="web"
    )
    with pytest.raises(AgentConversationRuntimeViolation) as duplicate:
        current.begin_speculative_dialogue(
            request_id="request-1", commit=selected, context=context, channel_id="web"
        )
    assert duplicate.value.reason == "SPECULATION_REQUEST_CONFLICT"
    second = current.begin_speculative_dialogue(
        request_id="request-2", commit=selected, context=context, channel_id="web"
    )
    with pytest.raises(AgentConversationRuntimeViolation) as full:
        current.begin_speculative_dialogue(
            request_id="request-3", commit=selected, context=context, channel_id="web"
        )
    assert full.value.reason == "SPECULATION_CAPACITY_EXCEEDED"
    with pytest.raises(AgentConversationRuntimeViolation) as foreign:
        await current.submit_committed_turn(
            request_id="request-2",
            response_id="response-2",
            correlation_id="correlation-2",
            commit=selected,
            context=context,
            speculation=first,
        )
    assert foreign.value.reason == "SPECULATION_MISMATCH"
    await lower.started.wait()
    await current.close(timeout_seconds=1)
    assert first.state == "discarded" and second.state == "discarded"
    assert current.speculation_snapshot()["pending"] == 0
    assert sorted(lower._stream_event_rail.aborted) == sorted(r.session_id for r in lower.requests)


@pytest.mark.asyncio
async def test_a_facade_without_a_tool_gate_cannot_speculate() -> None:
    lower = LowerFormalAdapter(final="answer")
    current = runtime(lower, RecordingHistoryWriter())
    selected = commit()
    await current.start()
    await current.open_interaction(selected.interaction_id)
    with pytest.raises(AgentConversationRuntimeViolation) as refusal:
        current.begin_speculative_dialogue(
            request_id="request-1",
            commit=selected,
            context=FormalContextSnapshot(selected.scope),
            channel_id="web",
        )
    assert refusal.value.reason == "SPECULATION_UNAVAILABLE"
    assert lower.calls == 0
    await current.close(timeout_seconds=1)
