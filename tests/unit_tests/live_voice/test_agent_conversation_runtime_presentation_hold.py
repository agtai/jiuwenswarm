# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Presentation holds: nothing of a speculative response reaches a consumer early."""

from __future__ import annotations

import asyncio

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.agent_conversation_runtime import (
    _PRESENTATION_HOLD_CAPACITY,
    AgentConversationNotification,
    AgentConversationRuntimeViolation,
)
from tests.unit_tests.live_voice.test_agent_conversation_runtime import (
    LowerFormalAdapter,
    RecordingHistoryWriter,
    runtime,
)


def _ref(response_id: str = "response-speculative") -> ResponseRef:
    return ResponseRef(
        interaction_id="interaction-hold",
        response_id=response_id,
        response_generation=1,
    )


def _notice(ref: ResponseRef, seq: int) -> AgentConversationNotification:
    return AgentConversationNotification(
        kind="work.progress",
        request_id=f"request-{seq}",
        round_id="round-hold",
        response_ref=ref,
    )


def _drain(current) -> list[AgentConversationNotification]:
    drained: list[AgentConversationNotification] = []
    while True:
        queued = current._notifications.get_nowait()
        if queued is None:
            return drained
        drained.append(queued)


@pytest.mark.asyncio
async def test_release_publishes_parked_notifications_in_order_then_flows_normally() -> None:
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter())
    assert await current.start() is True
    ref = _ref()
    gate: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    current.hold_presentation(ref, gate)
    for seq in range(3):
        current._publish(_notice(ref, seq))
    other = _ref("response-unrelated")
    current._publish(_notice(other, 99))
    assert [item.request_id for item in _drain(current)] == ["request-99"], "an unrelated response is never held"
    assert current.presentation_hold_snapshot() == {"held": 1, "parked": 3, "suppressed": 0, "discards": 0}

    gate.set_result("release")
    await asyncio.sleep(0)
    current._publish(_notice(ref, 3))
    drained = _drain(current)
    assert [item.request_id for item in drained] == ["request-0", "request-1", "request-2", "request-3"]
    assert [item.publish_seq for item in drained] == sorted(item.publish_seq for item in drained)
    assert current.presentation_hold_snapshot() == {"held": 0, "parked": 0, "suppressed": 0, "discards": 0}
    await current.close(timeout_seconds=0.2)


@pytest.mark.asyncio
async def test_discard_drops_parked_and_later_notifications_and_counts_once() -> None:
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter())
    assert await current.start() is True
    ref = _ref()
    gate: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    current.hold_presentation(ref, gate)
    current._publish(_notice(ref, 0))
    current._publish(_notice(ref, 1))
    gate.set_result("discard")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    current._publish(_notice(ref, 2))
    assert _drain(current) == []
    assert current.presentation_hold_snapshot() == {"held": 0, "parked": 0, "suppressed": 1, "discards": 1}
    # A response that never reached CR cannot be fenced; suppression alone
    # keeps every later notice out, and the discard task settles quietly.
    await asyncio.gather(*current._presentation_hold_tasks, return_exceptions=True)
    current._publish(_notice(ref, 3))
    assert _drain(current) == []
    await current.close(timeout_seconds=0.2)


@pytest.mark.asyncio
async def test_failed_or_cancelled_gate_is_a_discard() -> None:
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter())
    assert await current.start() is True
    loop = asyncio.get_running_loop()
    failed_ref, cancelled_ref = _ref("response-failed"), _ref("response-cancelled")
    failed_gate: asyncio.Future[str] = loop.create_future()
    cancelled_gate: asyncio.Future[str] = loop.create_future()
    current.hold_presentation(failed_ref, failed_gate)
    current.hold_presentation(cancelled_ref, cancelled_gate)
    current._publish(_notice(failed_ref, 0))
    current._publish(_notice(cancelled_ref, 1))
    failed_gate.set_exception(RuntimeError("semantic resolution failed"))
    cancelled_gate.cancel()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert _drain(current) == []
    assert current.presentation_hold_snapshot()["discards"] == 2
    await asyncio.gather(*current._presentation_hold_tasks, return_exceptions=True)
    await current.close(timeout_seconds=0.2)


@pytest.mark.asyncio
async def test_hold_capacity_overflow_fails_closed_to_discard() -> None:
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter(), notification_capacity=4)
    assert await current.start() is True
    ref = _ref()
    gate: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    current.hold_presentation(ref, gate)
    for seq in range(_PRESENTATION_HOLD_CAPACITY + 1):
        current._publish(_notice(ref, seq))
    assert gate.done() and gate.result() == "discard"
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert _drain(current) == []
    assert current.presentation_hold_snapshot()["discards"] == 1
    await asyncio.gather(*current._presentation_hold_tasks, return_exceptions=True)
    await current.close(timeout_seconds=0.2)


@pytest.mark.asyncio
async def test_already_released_gate_needs_no_hold_and_publishes_immediately() -> None:
    # The decision can settle before the dispatch reaches the hold; nothing
    # the response produces is provisional any more, so it flows normally.
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter())
    assert await current.start() is True
    ref = _ref()
    released: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    released.set_result("release")
    current.hold_presentation(ref, released)
    assert current.presentation_hold_snapshot() == {"held": 0, "parked": 0, "suppressed": 0, "discards": 0}
    current._publish(_notice(ref, 0))
    assert [item.request_id for item in _drain(current)] == ["request-0"]
    await current.close(timeout_seconds=0.2)


@pytest.mark.asyncio
async def test_already_discarded_failed_or_cancelled_gate_refuses_the_hold() -> None:
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter())
    assert await current.start() is True
    loop = asyncio.get_running_loop()
    discarded: asyncio.Future[str] = loop.create_future()
    discarded.set_result("discard")
    failed: asyncio.Future[str] = loop.create_future()
    failed.set_exception(RuntimeError("semantic resolution failed"))
    cancelled: asyncio.Future[str] = loop.create_future()
    cancelled.cancel()
    for index, gate in enumerate((discarded, failed, cancelled)):
        with pytest.raises(AgentConversationRuntimeViolation) as refusal:
            current.hold_presentation(_ref(f"response-settled-{index}"), gate)
        assert refusal.value.reason == "PRESENTATION_HOLD_DISCARDED"
    assert current.presentation_hold_snapshot()["held"] == 0
    await current.close(timeout_seconds=0.2)


@pytest.mark.asyncio
async def test_hold_rejects_non_future_gates_and_duplicate_holds() -> None:
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter())
    assert await current.start() is True
    loop = asyncio.get_running_loop()
    ref = _ref()
    with pytest.raises(AgentConversationRuntimeViolation) as failure:
        current.hold_presentation(ref, "release")  # type: ignore[arg-type]
    assert failure.value.reason == "INVALID_PRESENTATION_HOLD"
    gate: asyncio.Future[str] = loop.create_future()
    current.hold_presentation(ref, gate)
    with pytest.raises(AgentConversationRuntimeViolation) as duplicate:
        current.hold_presentation(ref, loop.create_future())
    assert duplicate.value.reason == "PRESENTATION_HOLD_CONFLICT"
    gate.set_result("release")
    await asyncio.sleep(0)
    await current.close(timeout_seconds=0.2)
