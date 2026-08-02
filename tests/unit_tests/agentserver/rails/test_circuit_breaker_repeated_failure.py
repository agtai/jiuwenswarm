from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from openjiuwen.core.single_agent.rail.base import InvokeInputs, ToolCallInputs
from openjiuwen.harness.tools.base_tool import ToolOutput

from jiuwenswarm.agents.harness.common.rails.execution_guard.circuit_breaker_rail import (
    CircuitBreakerConfig,
    CircuitBreakerRail,
)


_COMMAND = "git log -1 --format=%ad --date=format:'%m月%d日'"
_OOM_ERROR = "fatal: Out of memory, realloc failed"
_OOM_RESULT = {
    "success": False,
    "data": {
        "status": "error",
        "result_type": "error",
        "exit_code": 1,
        "stderr": _OOM_ERROR,
    },
    "error": _OOM_ERROR,
}


def _rail(**overrides: Any) -> CircuitBreakerRail:
    values = {"legacy_detectors_enabled": False}
    values.update(overrides)
    return CircuitBreakerRail(CircuitBreakerConfig(**values), language="en")


def _new_ctx(conversation_id: str = "conversation-a") -> SimpleNamespace:
    force_finishes: list[dict[str, Any]] = []
    return SimpleNamespace(
        inputs=InvokeInputs(query="run the command", conversation_id=conversation_id),
        extra={},
        exception=None,
        request_force_finish=force_finishes.append,
        force_finishes=force_finishes,
    )


async def _start(
    rail: CircuitBreakerRail,
    conversation_id: str = "conversation-a",
) -> SimpleNamespace:
    ctx = _new_ctx(conversation_id)
    await rail.before_invoke(ctx)
    return ctx


async def _record(
    rail: CircuitBreakerRail,
    ctx: SimpleNamespace,
    *,
    tool_name: str = "bash",
    arguments: Any | None = None,
    result: Any = _OOM_RESULT,
    exception: Exception | None = None,
) -> None:
    args = (
        {"command": _COMMAND, "description": "inspect commit date"}
        if arguments is None
        else arguments
    )
    tool_call = SimpleNamespace(
        id="tool-call",
        name=tool_name,
        arguments=args,
    )
    ctx.inputs = ToolCallInputs(
        tool_call=tool_call,
        tool_name=tool_name,
        tool_args=args,
        tool_result=result,
    )
    ctx.exception = exception
    await rail.after_tool_call(ctx)


@pytest.mark.asyncio
async def test_third_same_failure_ignores_description_and_force_finishes_once() -> None:
    rail = _rail()
    ctx = await _start(rail)

    for index, description in enumerate(("first wording", "second wording"), start=1):
        await _record(
            rail,
            ctx,
            arguments={"command": _COMMAND, "description": description},
        )
        assert ctx.force_finishes == [], f"attempt {index} must remain allowed"

    await _record(
        rail,
        ctx,
        arguments={"description": "third wording", "command": _COMMAND},
    )

    assert len(ctx.force_finishes) == 1
    assert ctx.force_finishes[0]["result_type"] == "answer"
    assert "failed 3 consecutive times" in ctx.force_finishes[0]["output"]

    await _record(rail, ctx)
    assert len(ctx.force_finishes) == 1, "a tripped invoke must force-finish only once"


@pytest.mark.asyncio
async def test_fake_sequential_loop_stops_before_a_fourth_execution() -> None:
    rail = _rail()
    ctx = await _start(rail)
    executions = 0

    for _ in range(10):
        executions += 1
        await _record(rail, ctx)
        if ctx.force_finishes:
            break

    assert executions == 3
    assert len(ctx.force_finishes) == 1


@pytest.mark.asyncio
async def test_equivalent_dict_json_and_tool_output_share_a_failure_signature() -> None:
    rail = _rail()
    ctx = await _start(rail)
    payload = {
        "success": False,
        "data": {"status": "error", "exit_code": 1},
        "error": _OOM_ERROR,
    }
    representations = (
        payload,
        json.dumps(payload),
        ToolOutput(
            success=False,
            data={"status": "error", "exit_code": 1},
            error=_OOM_ERROR,
        ),
    )

    for representation in representations:
        await _record(rail, ctx, result=representation)

    assert len(ctx.force_finishes) == 1


@pytest.mark.asyncio
async def test_success_resets_the_failure_tail_and_later_failures_can_recover() -> None:
    rail = _rail()
    ctx = await _start(rail)

    await _record(rail, ctx)
    await _record(rail, ctx)
    await _record(rail, ctx, result={"success": True, "data": {"stdout": "ok"}})
    await _record(rail, ctx)
    await _record(rail, ctx)
    assert ctx.force_finishes == []

    await _record(rail, ctx)
    assert len(ctx.force_finishes) == 1


@pytest.mark.parametrize("variation", ["arguments", "tool", "error", "nested"])
@pytest.mark.asyncio
async def test_semantic_variation_breaks_the_consecutive_failure_tail(
    variation: str,
) -> None:
    rail = _rail()
    ctx = await _start(rail)

    await _record(rail, ctx)
    await _record(rail, ctx)

    if variation == "arguments":
        await _record(rail, ctx, arguments={"command": "git status --short"})
    elif variation == "tool":
        await _record(rail, ctx, tool_name="powershell")
    elif variation == "error":
        await _record(
            rail,
            ctx,
            result={**_OOM_RESULT, "error": "fatal: permission denied"},
        )
    else:
        await _record(
            rail,
            ctx,
            result={
                **_OOM_RESULT,
                "data": {**_OOM_RESULT["data"], "exit_code": 137},
            },
        )

    await _record(rail, ctx)
    await _record(rail, ctx)
    assert ctx.force_finishes == []

    await _record(rail, ctx)
    assert len(ctx.force_finishes) == 1


@pytest.mark.asyncio
async def test_distinct_exception_instances_with_same_type_and_message_are_stable() -> (
    None
):
    rail = _rail()
    ctx = await _start(rail)

    for attempt in range(3):
        await _record(
            rail,
            ctx,
            result=None,
            exception=RuntimeError(_OOM_ERROR),
        )
        assert len(ctx.force_finishes) == (1 if attempt == 2 else 0)


def test_unknown_object_fallback_does_not_include_repr_memory_addresses() -> None:
    class UnknownResult:
        __slots__ = ()

    first = CircuitBreakerRail._canonicalize_failure_value(UnknownResult())
    second = CircuitBreakerRail._canonicalize_failure_value(UnknownResult())

    assert first == second
    assert first == {
        "__type__": f"{UnknownResult.__module__}.{UnknownResult.__qualname__}",
    }


@pytest.mark.asyncio
async def test_overlapping_invokes_with_same_conversation_are_isolated() -> None:
    rail = _rail()
    first = await _start(rail, "shared-conversation")
    second = await _start(rail, "shared-conversation")

    for _ in range(2):
        await _record(rail, first)
        await _record(rail, second)
    assert first.force_finishes == []
    assert second.force_finishes == []

    await _record(rail, first)
    assert len(first.force_finishes) == 1
    assert second.force_finishes == []

    await _record(rail, second)
    assert len(second.force_finishes) == 1


@pytest.mark.asyncio
async def test_cleanup_is_session_scoped_and_after_invoke_releases_state() -> None:
    rail = _rail()
    first = await _start(rail, "session-a")
    second = await _start(rail, "session-b")

    for _ in range(2):
        await _record(rail, first)
        await _record(rail, second)

    rail.cleanup_session("session-a")
    await _record(rail, first)
    await _record(rail, second)

    assert first.force_finishes == []
    assert len(second.force_finishes) == 1

    await rail.after_invoke(first)
    await rail.after_invoke(second)
    assert rail._repeated_states == {}


@pytest.mark.asyncio
async def test_cleanup_closes_an_inflight_callback_without_force_finish() -> None:
    rail = _rail()
    ctx = await _start(rail, "session-race")
    state = ctx.extra[rail._REPEATED_FAILURE_STATE_KEY]

    await state.lock.acquire()
    task = asyncio.create_task(_record(rail, ctx))
    await asyncio.sleep(0)
    assert not task.done()

    rail.cleanup_session("session-race")
    state.lock.release()
    await task

    assert state.closed is True
    assert ctx.force_finishes == []


@pytest.mark.asyncio
async def test_repeated_failure_detector_can_be_disabled() -> None:
    rail = _rail(repeated_failure_enabled=False)
    ctx = await _start(rail)

    for _ in range(5):
        await _record(rail, ctx)

    assert ctx.force_finishes == []
    assert rail._REPEATED_FAILURE_STATE_KEY not in ctx.extra


@pytest.mark.asyncio
async def test_custom_threshold_is_honored() -> None:
    rail = _rail(repeated_failure_threshold=2)
    ctx = await _start(rail)

    await _record(rail, ctx)
    assert ctx.force_finishes == []
    await _record(rail, ctx)
    assert len(ctx.force_finishes) == 1


@pytest.mark.parametrize("threshold", [0, -1, True, 1.5])
def test_invalid_threshold_is_rejected(threshold: Any) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        CircuitBreakerConfig(repeated_failure_threshold=threshold)


@pytest.mark.asyncio
async def test_repeated_failure_detector_precedes_legacy_global_breaker() -> None:
    rail = CircuitBreakerRail(
        CircuitBreakerConfig(
            warning_threshold=99,
            critical_threshold=99,
            global_breaker_threshold=3,
            unknown_tool_threshold=99,
            legacy_detectors_enabled=True,
            repeated_failure_enabled=True,
            repeated_failure_threshold=3,
        ),
        language="en",
    )
    ctx = await _start(rail)

    for _ in range(3):
        await _record(rail, ctx)

    assert len(ctx.force_finishes) == 1
    assert "failed 3 consecutive times" in ctx.force_finishes[0]["output"]
    assert "Circuit breaker" not in ctx.force_finishes[0]["output"]
