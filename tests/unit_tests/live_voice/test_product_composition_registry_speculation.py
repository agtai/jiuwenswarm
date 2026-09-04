# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Unified submit speculates the dialogue candidate at submit and settles it on the decision."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.speculative_dialogue import SpeculativeDialogue
from tests.support.live_voice.semantic_model import decision
from tests.unit_tests.live_voice.test_product_composition_registry import (
    ErrorCode,
    _close_unified_route,
    _Facade,
    _p2_params,
    _registry,
    _unified_final_params,
)


class _GatedFacade(_Facade):
    """The formal seam with the tool execution gate; the stream waits on ``release``."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.paused: list[str] = []
        self.resumed: list[str] = []
        self.aborted: list[str] = []
        self.sessions: list[str] = []

    async def process_formal_live_voice_stream(self, execution):
        async with self._calls_changed:
            self.calls += 1
            self.executions.append(execution)
            self._calls_changed.notify_all()
        self.sessions.append(execution.internal_session_id)
        self.started.set()
        yield AgentResponseChunk(
            request_id=execution.request_id,
            channel_id=execution.channel_id,
            payload={"event_type": "chat.delta", "content": "早 "},
            is_complete=False,
        )
        await self.release.wait()
        yield AgentResponseChunk(
            request_id=execution.request_id,
            channel_id=execution.channel_id,
            payload={"event_type": "chat.final", "content": "早 speculated answer"},
            is_complete=True,
        )

    def pause_formal_tools(self, session_id: str) -> None:
        self.paused.append(session_id)

    def resume_formal_tools(self, session_id: str) -> None:
        self.resumed.append(session_id)

    def abort_formal_tools(self, session_id: str) -> None:
        self.aborted.append(session_id)


async def _wait_until(predicate, *, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition was not met in time")
        await asyncio.sleep(0.01)


async def _activate(registry) -> None:
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-speculation-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok


def _runtime_of(registry):
    route = next(iter(registry._p2_routes.values()))
    return route.activation_lease._runtime


def _gated(tmp_path: Path):
    registry, composition, manager, _pushed = _registry(tmp_path, unified=True)
    facade = _GatedFacade()
    manager.agent = facade
    return registry, composition, manager, facade


def _blocking_resolver(composition, release: asyncio.Event):
    original = composition.resolve_production_semantics

    async def resolve(*args, **kwargs):
        await release.wait()
        return await original(*args, **kwargs)

    return resolve


async def _submit(registry, *, stem: str):
    return await registry.handle_unified_submit(
        params=_unified_final_params(stem=stem, text="你好。"),
        request_id=f"request-{stem}",
        session_id="session-product",
        channel_id="web",
    )


@pytest.mark.asyncio
async def test_dialogue_candidate_starts_at_submit_and_is_attached_after_the_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, composition, manager, facade = _gated(tmp_path)
    await _activate(registry)
    decide = asyncio.Event()
    monkeypatch.setattr(composition, "resolve_production_semantics", _blocking_resolver(composition, decide))
    submission = asyncio.create_task(_submit(registry, stem="speculate-dialogue"))
    # The model works while the decision is open ...
    await asyncio.wait_for(facade.started.wait(), timeout=3)
    assert not submission.done()
    session = facade.sessions[0]
    assert session.startswith("lv-formal-spec-")
    assert facade.paused == [session] and facade.resumed == [] and facade.aborted == []
    runtime = _runtime_of(registry)
    # ... and nothing of it exists anywhere a consumer could see.
    assert runtime.snapshot().queued_notifications == 0
    assert runtime.speculation_snapshot()["pending"] == 1

    decide.set()
    result = await asyncio.wait_for(submission, timeout=5)
    assert result.ok, result.payload
    assert facade.calls == 1, "the admitted round took the candidate over"
    assert facade.resumed == [session] and facade.aborted == []
    facade.release.set()
    await _wait_until(lambda: runtime.snapshot().queued_notifications > 0)
    # The candidate settles when its round finishes consuming it.
    await _wait_until(lambda: runtime.speculation_snapshot()["pending"] == 0)
    await _close_unified_route(registry, stem="p3-off-create")


@pytest.mark.asyncio
async def test_a_failed_decision_discards_the_candidate_before_anything_executes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, composition, manager, facade = _gated(tmp_path)
    await _activate(registry)

    async def failing_resolve(*args, **kwargs):
        await asyncio.wait_for(facade.started.wait(), timeout=3)
        raise FormalTaskViolation(
            "SEMANTIC_OUTPUT_INVALID", "model output failed validation twice", ErrorCode.INVALID_ARGUMENT
        )

    monkeypatch.setattr(composition, "resolve_production_semantics", failing_resolve)
    result = await _submit(registry, stem="speculate-failure")
    assert not result.ok
    assert result.payload["error"]["reason"] == "SEMANTIC_OUTPUT_INVALID"
    session = facade.sessions[0]
    assert facade.paused == [session] and facade.aborted == [session] and facade.resumed == []
    runtime = _runtime_of(registry)
    assert runtime.snapshot().queued_notifications == 0
    assert runtime.speculation_snapshot()["pending"] == 0
    await _close_unified_route(registry, stem="p3-off-create")


@pytest.mark.asyncio
async def test_a_task_decision_discards_the_candidate_before_the_task_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, composition, manager, facade = _gated(tmp_path)
    await _activate(registry)
    composition.semantic_program = lambda data: decision(
        data,
        "task.create",
        {
            "name": "Synthetic release notes",
            "instruction": "Draft release notes from the supplied synthetic dependencies.",
        },
    )
    decide = asyncio.Event()
    monkeypatch.setattr(composition, "resolve_production_semantics", _blocking_resolver(composition, decide))
    submission = asyncio.create_task(_submit(registry, stem="speculate-task"))
    await asyncio.wait_for(facade.started.wait(), timeout=3)
    session = facade.sessions[0]
    decide.set()
    await asyncio.wait_for(submission, timeout=10)
    # Whatever the Task path did, the candidate never became a dialogue turn:
    # it was aborted, and the spoken confirmation ran as a fresh round.
    assert facade.aborted == [session] and facade.resumed == []
    assert facade.calls == 2
    facade.release.set()
    runtime = _runtime_of(registry)
    assert runtime.speculation_snapshot()["pending"] == 0
    assert all(
        not execution.internal_session_id.startswith("lv-formal-spec-") or execution is facade.executions[0]
        for execution in facade.executions
    )
    await _close_unified_route(registry, stem="p3-off-create")


@pytest.mark.asyncio
async def test_no_speculation_with_pending_context_visible_tasks_or_at_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, composition, manager, facade = _gated(tmp_path)
    await _activate(registry)

    original_pending = registry._semantic_continuity.pending
    probes = {"count": 0}

    async def one_pending(scope):
        # The admissibility probe sees a pending context; the resolver does not.
        probes["count"] += 1
        if probes["count"] == 1:
            return ({"source_id": "pending-1"},)
        return await original_pending(scope)

    monkeypatch.setattr(registry._semantic_continuity, "pending", one_pending)
    result = await _submit(registry, stem="serial-pending")
    assert result.ok, result.payload
    assert facade.paused == [] and facade.calls == 1
    monkeypatch.undo()

    monkeypatch.setattr(composition, "count_scope_tasks", lambda scope: 1)
    facade.release.set()
    result = await _submit(registry, stem="serial-tasks")
    assert result.ok, result.payload
    assert facade.paused == [] and facade.calls == 2
    monkeypatch.undo()

    registry._speculations_in_flight = registry._MAX_SPECULATIONS_IN_FLIGHT
    try:
        result = await _submit(registry, stem="serial-capacity")
    finally:
        registry._speculations_in_flight = 0
    assert result.ok, result.payload
    assert facade.paused == [] and facade.calls == 3
    await _close_unified_route(registry, stem="p3-off-create")


@pytest.mark.asyncio
async def test_an_unattachable_candidate_falls_back_to_a_fresh_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, composition, manager, facade = _gated(tmp_path)
    await _activate(registry)
    monkeypatch.setattr(SpeculativeDialogue, "attachable", lambda self, execution: False)
    facade.release.set()
    result = await _submit(registry, stem="speculate-fallback")
    assert result.ok, result.payload
    assert facade.calls == 2
    assert facade.sessions[0].startswith("lv-formal-spec-")
    assert facade.aborted == [facade.sessions[0]] and facade.resumed == []
    assert not facade.sessions[1].startswith("lv-formal-spec-")
    await _close_unified_route(registry, stem="p3-off-create")
