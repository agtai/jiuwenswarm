"""A failed required spoken revision never releases the draft, retries, or swallows cancellation.

Doubles mirror ``finalize_spoken_answer``'s actual use of the model: one
``await model.invoke(messages=..., tools=[], **options)`` returning an object
with ``content`` and ``tool_calls``.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.runtime.agent_adapter import formal_live_voice as flv
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    finalize_spoken_answer,
    spoken_revision_failure_notice,
)

LONG_DRAFT = "机器学习是让计算机从数据中学习规律的方法。" * 12  # > 200 chars, no tool results -> length
ARITHMETIC_DRAFT = "从 16:10 出发，路上 45 分钟，费用 120 元，来得及。"  # tool-backed quantities -> arithmetic
TOOL_RESULTS = [{"content": "timetable: departs 16:10; journey 45 min; fare 120 CNY"}]


def _draft_windows(draft: str, size: int = 8):
    return {draft[i:i + size] for i in range(0, max(1, len(draft) - size + 1))}


def _assert_draft_not_released(spoken: str, draft: str):
    assert spoken.strip()
    assert spoken != draft
    assert not (_draft_windows(draft) & _draft_windows(spoken)), "draft text leaked into the spoken notice"


class _Model:
    """Records every invoke; behaviour is injected per test."""

    def __init__(self, behaviour):
        self.calls = []
        self._behaviour = behaviour

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return await self._behaviour(kwargs)


@pytest.mark.asyncio
async def test_length_revision_timeout_speaks_notice_not_draft(monkeypatch):
    monkeypatch.setattr(flv, "LENGTH_REVISION_TIMEOUT_SECONDS", 0.02)

    async def hang(_kwargs):
        await asyncio.sleep(5)

    model = _Model(hang)
    spoken = await finalize_spoken_answer(model, envelope="q", candidate=LONG_DRAFT, tool_results=[])
    assert spoken == spoken_revision_failure_notice("length", LONG_DRAFT)
    _assert_draft_not_released(spoken, LONG_DRAFT)
    assert len(model.calls) == 1 and model.calls[0]["tools"] == []


@pytest.mark.asyncio
async def test_arithmetic_revision_timeout_never_states_unverified_figures(monkeypatch):
    monkeypatch.setattr(flv, "ARITHMETIC_REVISION_TIMEOUT_SECONDS", 0.02)

    async def hang(_kwargs):
        await asyncio.sleep(5)

    model = _Model(hang)
    spoken = await finalize_spoken_answer(model, envelope="q", candidate=ARITHMETIC_DRAFT, tool_results=TOOL_RESULTS)
    assert spoken == spoken_revision_failure_notice("arithmetic", ARITHMETIC_DRAFT)
    _assert_draft_not_released(spoken, ARITHMETIC_DRAFT)
    for figure in ("16:10", "45", "120", "来得及"):
        assert figure not in spoken
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_provider_exception_speaks_notice_without_retry():
    async def explode(_kwargs):
        raise RuntimeError("provider down")

    model = _Model(explode)
    spoken = await finalize_spoken_answer(model, envelope="q", candidate=LONG_DRAFT, tool_results=[])
    assert spoken == spoken_revision_failure_notice("length", LONG_DRAFT)
    _assert_draft_not_released(spoken, LONG_DRAFT)
    assert len(model.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(content="not json", tool_calls=[]),
        SimpleNamespace(content=json.dumps({"text": "", "detailed_requested": False}), tool_calls=[]),
        SimpleNamespace(content=json.dumps({"text": "x" * 201, "detailed_requested": False}), tool_calls=[]),
        SimpleNamespace(content=json.dumps({"text": "ok", "detailed_requested": False, "extra": 1}), tool_calls=[]),
        SimpleNamespace(content=json.dumps({"text": "ok", "detailed_requested": False}), tool_calls=[{"name": "read_file"}]),
    ],
)
async def test_invalid_revision_response_speaks_notice_not_draft(response):
    async def answer(_kwargs):
        return response

    model = _Model(answer)
    spoken = await finalize_spoken_answer(model, envelope="q", candidate=ARITHMETIC_DRAFT, tool_results=TOOL_RESULTS)
    assert spoken == spoken_revision_failure_notice("arithmetic", ARITHMETIC_DRAFT)
    _assert_draft_not_released(spoken, ARITHMETIC_DRAFT)
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_cancellation_propagates_and_produces_no_spoken_output():
    started = asyncio.Event()

    async def wait_forever(_kwargs):
        started.set()
        await asyncio.Event().wait()

    model = _Model(wait_forever)
    task = asyncio.create_task(
        finalize_spoken_answer(model, envelope="q", candidate=LONG_DRAFT, tool_results=[])
    )
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_successful_revision_is_unchanged_by_failure_rule():
    async def answer(_kwargs):
        return SimpleNamespace(
            content=json.dumps({"text": "出发时间 15:00，来得及。", "detailed_requested": False}),
            tool_calls=[],
        )

    model = _Model(answer)
    spoken = await finalize_spoken_answer(model, envelope="q", candidate=ARITHMETIC_DRAFT, tool_results=TOOL_RESULTS)
    assert spoken == "出发时间 15:00，来得及。"
    assert len(model.calls) == 1


def test_failure_notice_follows_the_draft_language_and_names_the_reason():
    zh_length = spoken_revision_failure_notice("length", LONG_DRAFT)
    en_length = spoken_revision_failure_notice("length", "An English draft. " * 20)
    zh_arith = spoken_revision_failure_notice("arithmetic", ARITHMETIC_DRAFT)
    en_arith = spoken_revision_failure_notice("arithmetic", "Leave at 16:10, fare 120 USD, feasible.")
    assert zh_length != zh_arith and en_length != en_arith
    assert "草稿" in zh_length and "复核" in zh_arith
    assert "draft" in en_length and "verif" in en_arith
    for notice in (zh_length, en_length, zh_arith, en_arith):
        assert len(notice) <= 200
    with pytest.raises(KeyError):
        spoken_revision_failure_notice("other", "x")
