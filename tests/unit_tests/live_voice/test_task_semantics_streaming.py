# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Early-route announcement of the semantic resolver while its decision streams."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.production_task_intent import TaskAuthorityRead
from jiuwenswarm.server.live_voice.task_semantics import (
    TaskSemanticContext,
    TaskSemanticResolver,
    _route_hint_from_partial,
)
from tests.support.live_voice.semantic_model import decision as dialogue_decision
from tests.unit_tests.live_voice.test_product_composition_registry import (
    _fixture_production_task_fact,
)
from tests.unit_tests.live_voice.test_task_semantics import (
    _Catalog,
    _Model,
    _commit,
    _context,
    _output,
)


def _pieces(text: str, size: int = 9) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


class _StreamingModel(_Model):
    """A model whose primary call streams; ``pause`` holds the tail after the route."""

    def __init__(self, output, *, pause: asyncio.Event | None = None, retry_output=None, **kwargs):
        super().__init__(output, **kwargs)
        self.pause = pause
        self.retry_output = retry_output
        self.stream_calls = 0

    async def stream(self, **kwargs):
        self.stream_calls += 1
        self.calls.append(kwargs)
        emitted = ""
        for piece in _pieces(self.output):
            emitted += piece
            yield SimpleNamespace(content=piece, tool_calls=self.tool_calls)
            # Hold the tail only once the route value itself has been emitted,
            # so the announcement can fire while the decision is still open.
            if self.pause is not None and '"route": "dialogue"' in emitted and not self.pause.is_set():
                await self.pause.wait()

    async def invoke(self, **kwargs):
        if self.retry_output is not None:
            self.calls.append(kwargs)
            return SimpleNamespace(content=self.retry_output, tool_calls=[])
        return await super().invoke(**kwargs)


def _dialogue_json(commit) -> str:
    return json.dumps(dialogue_decision({"commit": {"text": commit.text}}))


def test_route_hint_reads_only_a_leading_route_value():
    assert _route_hint_from_partial('{"route": "dialogue", "operation": nu') == "dialogue"
    assert _route_hint_from_partial('{"route":"task"') == "task"
    assert _route_hint_from_partial('{"route": "clarification"}') == "clarification"
    assert _route_hint_from_partial('{"rou') is None
    assert _route_hint_from_partial('{"route": "dia') is None
    assert _route_hint_from_partial('{"route": "elsewhere"}') is None
    assert _route_hint_from_partial('{"message": "route"}') is None


@pytest.mark.asyncio
async def test_route_is_announced_before_the_decision_completes():
    commit = _commit("今天天气怎么样？")
    pause = asyncio.Event()
    model = _StreamingModel(_dialogue_json(commit), pause=pause)
    announced: list[str] = []
    announced_event = asyncio.Event()

    def route_hint(route: str) -> None:
        announced.append(route)
        announced_event.set()

    resolver = TaskSemanticResolver(_Catalog(model))
    pending = asyncio.create_task(resolver.resolve(commit, _context(commit), route_hint=route_hint))
    await asyncio.wait_for(announced_event.wait(), timeout=2)
    await asyncio.sleep(0)
    assert announced == ["dialogue"]
    assert not pending.done(), "the decision must still be streaming when the route is announced"
    pause.set()
    result = await asyncio.wait_for(pending, timeout=2)
    assert result.route == "dialogue"
    assert model.stream_calls == 1
    assert announced == ["dialogue"], "the announcement fires exactly once"
    assert all(call["tools"] == [] for call in model.calls)


@pytest.mark.asyncio
async def test_unary_model_keeps_the_old_path_and_never_announces():
    commit = _commit("今天天气怎么样？")
    model = _Model(_dialogue_json(commit))
    announced: list[str] = []
    result = await TaskSemanticResolver(_Catalog(model)).resolve(
        commit, _context(commit), route_hint=announced.append
    )
    assert result.route == "dialogue"
    assert announced == []
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_no_hint_means_no_streaming_even_when_the_model_can_stream():
    commit = _commit("今天天气怎么样？")
    model = _StreamingModel(_dialogue_json(commit))
    result = await TaskSemanticResolver(_Catalog(model)).resolve(commit, _context(commit))
    assert result.route == "dialogue"
    assert model.stream_calls == 0 and len(model.calls) == 1


@pytest.mark.asyncio
async def test_structural_retry_pins_the_announced_route_and_a_contradiction_fails_closed():
    commit = _commit()
    broken = '{"route": "dialogue", "operation": null, "arguments": {'
    model = _StreamingModel(broken, retry_output=json.dumps(_output(commit)))
    announced: list[str] = []
    with pytest.raises(FormalTaskViolation) as failure:
        await TaskSemanticResolver(_Catalog(model)).resolve(
            commit, _context(commit), route_hint=announced.append
        )
    assert failure.value.reason == "SEMANTIC_ROUTE_HINT_MISMATCH"
    assert announced == ["dialogue"]
    assert model.stream_calls == 1 and len(model.calls) == 2
    retry_instructions = model.calls[1]["messages"][0].content
    assert "'dialogue'" in retry_instructions and "is binding" in retry_instructions


@pytest.mark.asyncio
async def test_streamed_tool_calls_are_still_forbidden():
    commit = _commit("今天天气怎么样？")
    model = _StreamingModel(_dialogue_json(commit), tool_calls=[{"name": "write_file"}])
    with pytest.raises(FormalTaskViolation) as failure:
        await TaskSemanticResolver(_Catalog(model)).resolve(
            commit, _context(commit), route_hint=lambda route: None
        )
    assert failure.value.reason == "SEMANTIC_TOOL_CALL_FORBIDDEN"


@pytest.mark.asyncio
async def test_a_context_with_an_existing_task_is_never_announced():
    # A dialogue answer over existing Tasks is grounded with fresh Task facts
    # only after the decision; a speculative dispatch would bypass that, so
    # the resolver stays unary and silent whenever the context holds a Task.
    commit = _commit("今天天气怎么样？")
    model = _StreamingModel(_dialogue_json(commit))
    context = TaskSemanticContext(
        TaskAuthorityRead(commit.scope, "read-1", (_fixture_production_task_fact("task-existing"),)),
        "conversation",
    )
    announced: list[str] = []
    result = await TaskSemanticResolver(_Catalog(model)).resolve(
        commit, context, route_hint=announced.append
    )
    assert result.route == "dialogue"
    assert announced == []
    assert model.stream_calls == 0 and len(model.calls) == 1
