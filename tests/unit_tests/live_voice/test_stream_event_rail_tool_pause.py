# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""The rail's tools-only pause holds tool calls while model calls keep running."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from jiuwenswarm.agents.harness.common.rails.stream_event_rail import (
    JiuSwarmStreamEventRail,
)


def _ctx(rail: JiuSwarmStreamEventRail, sid: str) -> SimpleNamespace:
    return SimpleNamespace(extra={rail._SID_KEY: sid}, session=None, inputs=None, context=None)


@pytest.mark.asyncio
async def test_tools_only_pause_blocks_tool_calls_until_resumed_and_leaves_the_model_gate_open() -> None:
    rail = JiuSwarmStreamEventRail()
    sid = "lv-formal-spec-rail-1"
    rail.pause_tools(sid)
    # The model-call gate is untouched: a paused candidate still runs its model.
    assert rail._get_pause_event(sid).is_set()
    assert not rail._get_tool_pause_event(sid).is_set()
    waiter = asyncio.create_task(rail.before_tool_call(_ctx(rail, sid)))
    await asyncio.sleep(0.05)
    assert not waiter.done(), "a tool call must wait while the candidate is paused"
    rail.resume_tools(sid)
    await asyncio.wait_for(waiter, timeout=1)
    assert rail._get_tool_pause_event(sid).is_set()


@pytest.mark.asyncio
async def test_abort_wakes_a_parked_tool_call_as_a_cancellation() -> None:
    rail = JiuSwarmStreamEventRail()
    sid = "lv-formal-spec-rail-2"
    rail.pause_tools(sid)
    waiter = asyncio.create_task(rail.before_tool_call(_ctx(rail, sid)))
    await asyncio.sleep(0.05)
    assert not waiter.done()
    rail.abort(sid)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(waiter, timeout=1)


@pytest.mark.asyncio
async def test_cleanup_forgets_the_tools_only_pause() -> None:
    rail = JiuSwarmStreamEventRail()
    sid = "lv-formal-spec-rail-3"
    rail.pause_tools(sid)
    rail.cleanup_session(sid)
    assert sid not in rail._tool_pause_events
    assert rail._get_tool_pause_event(sid).is_set(), "a fresh session starts unpaused"
