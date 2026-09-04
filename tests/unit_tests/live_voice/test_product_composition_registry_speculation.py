# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Speculative dialogue dispatch on the announced route inside unified submit."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from tests.unit_tests.live_voice.test_product_composition_registry import (
    ErrorCode,
    _close_unified_route,
    _p2_params,
    _registry,
    _unified_final_params,
)


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


@pytest.mark.asyncio
async def test_dialogue_announcement_dispatches_the_agent_before_the_decision_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, composition, manager, _pushed = _registry(tmp_path, unified=True)
    await _activate(registry)
    original = composition.resolve_production_semantics
    release = asyncio.Event()
    hints: list[str] = []

    async def announcing_resolve(*args, route_hint=None, **kwargs):
        assert route_hint is not None, "the registry must offer the early-route callback"
        route_hint("dialogue")
        hints.append("dialogue")
        await release.wait()
        return await original(*args, route_hint=None, **kwargs)

    monkeypatch.setattr(composition, "resolve_production_semantics", announcing_resolve)
    submission = asyncio.create_task(
        registry.handle_unified_submit(
            params=_unified_final_params(stem="speculate-dialogue", text="你好。"),
            request_id="request-speculate-dialogue",
            session_id="session-product",
            channel_id="web",
        )
    )
    # The Agent starts on the announcement while the decision is still open,
    # and nothing it produced has reached the notification stream yet.
    await _wait_until(lambda: manager.agent.calls == 1)
    assert not submission.done()
    runtime = _runtime_of(registry)
    assert runtime.presentation_hold_snapshot()["held"] == 1
    # Non-vacuous: wait until the Agent really produced output, then prove
    # that output is parked rather than published.
    await _wait_until(lambda: runtime.presentation_hold_snapshot()["parked"] >= 1)
    assert runtime.snapshot().queued_notifications == 0

    release.set()
    result = await asyncio.wait_for(submission, timeout=5)
    assert result.ok, result.payload
    assert manager.agent.calls == 1
    assert manager.agent.executions[0].commit.text == "你好。"
    assert manager.agent.executions[0].allow_tools is True
    await _wait_until(lambda: runtime.presentation_hold_snapshot()["held"] == 0)
    assert runtime.presentation_hold_snapshot()["discards"] == 0
    assert hints == ["dialogue"]
    await _close_unified_route(registry, stem="p3-off-create")


@pytest.mark.asyncio
async def test_non_dialogue_announcement_never_speculates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, composition, manager, _pushed = _registry(tmp_path, unified=True)
    await _activate(registry)
    original = composition.resolve_production_semantics
    release = asyncio.Event()

    async def task_announcing_resolve(*args, route_hint=None, **kwargs):
        route_hint("task")
        await release.wait()
        return await original(*args, route_hint=None, **kwargs)

    monkeypatch.setattr(composition, "resolve_production_semantics", task_announcing_resolve)
    submission = asyncio.create_task(
        registry.handle_unified_submit(
            params=_unified_final_params(stem="speculate-task-hint", text="你好。"),
            request_id="request-speculate-task-hint",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.sleep(0.2)
    assert manager.agent.calls == 0, "a non-dialogue announcement must not start the Agent"
    assert _runtime_of(registry).presentation_hold_snapshot()["held"] == 0
    release.set()
    result = await asyncio.wait_for(submission, timeout=5)
    assert result.ok, result.payload
    assert manager.agent.calls == 1
    await _close_unified_route(registry, stem="p3-off-create")


@pytest.mark.asyncio
async def test_failed_decision_discards_the_speculative_response_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, composition, manager, _pushed = _registry(tmp_path, unified=True)
    await _activate(registry)
    release = asyncio.Event()

    async def failing_resolve(*args, route_hint=None, **kwargs):
        route_hint("dialogue")
        await release.wait()
        raise FormalTaskViolation(
            "SEMANTIC_OUTPUT_INVALID", "model output failed validation twice", ErrorCode.INVALID_ARGUMENT
        )

    monkeypatch.setattr(composition, "resolve_production_semantics", failing_resolve)
    submission = asyncio.create_task(
        registry.handle_unified_submit(
            params=_unified_final_params(stem="speculate-discard", text="你好。"),
            request_id="request-speculate-discard",
            session_id="session-product",
            channel_id="web",
        )
    )
    await _wait_until(lambda: manager.agent.calls == 1)
    runtime = _runtime_of(registry)
    await _wait_until(lambda: runtime.presentation_hold_snapshot()["parked"] >= 1)
    assert runtime.snapshot().queued_notifications == 0
    release.set()
    result = await asyncio.wait_for(submission, timeout=5)
    assert not result.ok
    assert result.payload["error"]["reason"] == "SEMANTIC_OUTPUT_INVALID"
    await _wait_until(lambda: runtime.presentation_hold_snapshot()["discards"] == 1)
    await asyncio.sleep(0.1)
    # The discarded response never reaches the stream: no token, no final,
    # no stale notice and no terminal for something the client never saw.
    assert runtime.snapshot().queued_notifications == 0
    assert runtime.presentation_hold_snapshot()["held"] == 0
    await _close_unified_route(registry, stem="p3-off-create")
