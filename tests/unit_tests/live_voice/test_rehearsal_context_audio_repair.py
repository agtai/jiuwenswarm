"""Focused boundaries from the recorded interrupted-context rehearsal."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ContextRef, ScopeRef
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.product_composition_registry import AgentServerProductCompositionRegistry
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextEntry, FormalContextSnapshot, finalize_spoken_answer,
    spoken_revision_reason, spoken_revision_request_options,
    spoken_revision_unavailable_notice,
)


def context(roles):
    scope = ScopeRef("repair-subject", "repair-project", "repair-session", Assurance.AUTHENTICATED)
    return FormalContextSnapshot(scope, tuple(FormalContextEntry(ContextRef.from_dict({
        "source": f"live_voice.cr_{'committed_user' if role == 'U' else 'presented_assistant'}",
        "stable_id": f"entry-{i}", "uri": f"live-voice-cr://context/{i}",
        "revision": {"kind": "snapshot", "value": f"revision-{i}"}, "scope": scope.to_dict(),
        "permissions": ["agent.context.read"], "expires_at": None,
        "redaction": {"policy_id": "live_voice.presented_text.v1", "redacted": False, "fields": []},
        "extensions": {},
    }), f"{role}-{i}") for i, role in enumerate(roles)))


@pytest.mark.parametrize("roles,retained", [("UUA", "UUA"), ("UUUUUUUA", "UUUUUUA"), ("UAUAUAUA", "UAUAUA")])
def test_task_receipt_preserves_unanswered_questions_and_evicts_whole_groups(roles, retained):
    snapshot = context(roles)
    entries = AgentServerProductCompositionRegistry._reserve_task_result_context_slot(snapshot)
    assert entries == snapshot.entries[-len(retained):]
    assert len(entries) < 8


@pytest.mark.parametrize("roles", ["A", "UAA"])
def test_orphan_answer_stays_rejected(roles):
    with pytest.raises(FormalTaskViolation, match="orphan"):
        AgentServerProductCompositionRegistry._reserve_task_result_context_slot(context(roles))


@pytest.mark.asyncio
async def test_spoken_revision_is_tool_free_and_does_not_change_source():
    calls = []
    async def invoke(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=json.dumps({"text": "The deadline is 16:10.", "detailed_requested": False}), tool_calls=[])
    result = await finalize_spoken_answer(SimpleNamespace(invoke=invoke), envelope="original request",
        candidate="old draft " * 80, tool_results=[{"content": "Original document"}])
    assert result == "The deadline is 16:10."
    assert len(calls) == 1 and calls[0]["tools"] == []
    assert json.loads(calls[0]["messages"][1].content)["formal_envelope"] == "original request"


@pytest.mark.asyncio
async def test_short_dialogue_skips_revision_and_bad_revision_does_not_promote_unchecked_draft():
    calls = []
    async def invoke(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content="invalid", tool_calls=[{"name": "write_file"}])
    model = SimpleNamespace(invoke=invoke)
    assert await finalize_spoken_answer(model, envelope="q", candidate="answer", tool_results=[]) == "answer"
    assert not calls
    # A short answer with tool results but nothing to recompute is already speakable.
    assert await finalize_spoken_answer(model, envelope="q", candidate="answer", tool_results=[{}]) == "answer"
    assert not calls
    # Numbers backed by tool results still go through the bounded verification.
    assert await finalize_spoken_answer(model, envelope="q", candidate="共 3 天", tool_results=[{}]) == spoken_revision_unavailable_notice()
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate,results", [("PRIVATE_DRAFT " * 80, []), ("费用 120 元 PRIVATE_DRAFT", [{}])])
@pytest.mark.parametrize("failure", ["timeout", "provider", "invalid", "empty", "oversize", "tools", "missing_model"])
async def test_revision_failure_is_short_truthful_tool_free_and_content_free(candidate, results, failure, monkeypatch, caplog):
    from jiuwenswarm.server.runtime.agent_adapter import formal_live_voice as module
    monkeypatch.setattr(module, "LENGTH_REVISION_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(module, "ARITHMETIC_REVISION_TIMEOUT_SECONDS", 0.01)
    calls = []
    cancelled = []

    async def invoke(**kwargs):
        calls.append(kwargs)
        if failure == "timeout":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        if failure == "provider":
            raise RuntimeError("PRIVATE_PROVIDER_SECRET")
        content = "bad json" if failure == "invalid" else json.dumps({
            "text": "" if failure == "empty" else "x" * 201 if failure == "oversize" else "unchecked",
            "detailed_requested": False,
        })
        return SimpleNamespace(content=content, tool_calls=[{"name": "write_file"}] if failure == "tools" else [])

    output = await finalize_spoken_answer(None if failure == "missing_model" else SimpleNamespace(invoke=invoke),
        envelope="PRIVATE_ENVELOPE", candidate=candidate, tool_results=results,
        request_id="existing-request-1", language="en")
    assert output == spoken_revision_unavailable_notice("en")
    assert len(output) <= 200 and "PRIVATE" not in output
    assert len(calls) == (0 if failure == "missing_model" else 1)
    assert all(call["tools"] == [] for call in calls)
    assert all("Independently recompute" in call["messages"][0].content for call in calls)
    assert "PRIVATE" not in caplog.text
    assert "existing-request-1" not in caplog.text
    if failure == "timeout":
        assert cancelled == [True]


@pytest.mark.asyncio
async def test_cancelled_revision_never_returns_fallback_or_draft():
    entered = asyncio.Event()
    async def invoke(**kwargs):
        entered.set()
        await asyncio.Event().wait()
    task = asyncio.create_task(finalize_spoken_answer(SimpleNamespace(invoke=invoke),
        envelope="q", candidate="long" * 100, tool_results=[]))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_spoken_revision_reason_only_for_length_or_tool_backed_arithmetic():
    assert spoken_revision_reason("x" * 200, []) is None
    assert spoken_revision_reason("x" * 201, []) == "length"
    assert spoken_revision_reason("工作区干净", [{"content": "## master"}]) is None
    assert spoken_revision_reason("x" * 201, [{"content": "log"}]) == "length"
    # Time or cost quantities backed by tool results are the arithmetic path.
    for text in ("耗时 12 分钟", "共 3 天", "16:10 出发", "费用 120 元", "$45 total", "2026-09-04 截止", "2.5 hours"):
        assert spoken_revision_reason(text, [{"content": "log"}]) == "arithmetic", text
    # Bare counts, ordinals and identifiers are not arithmetic, tool results or not.
    for text in ("已创建 1 个任务", "第 2 步完成", "共 3 个文件", "版本 v2", "编号 12345"):
        assert spoken_revision_reason(text, [{"content": "log"}]) is None, text
    assert spoken_revision_reason("耗时 12 分钟", []) is None


def test_long_tool_backed_figures_are_verified_not_merely_shortened():
    """A >200-char draft with tool-backed time/cost figures takes the arithmetic path."""
    long_arithmetic = "从 16:10 出发，路上 45 分钟，费用 120 元，来得及。" + "另外还有一些背景说明。" * 20
    assert len(long_arithmetic) > 200
    assert spoken_revision_reason(long_arithmetic, [{"content": "timetable"}]) == "arithmetic"
    # Without tool results the same long draft is only a brevity problem.
    assert spoken_revision_reason(long_arithmetic, []) == "length"
    # A long tool-backed draft without any quantity is also only a brevity problem.
    assert spoken_revision_reason("工作区干净，没有未提交的改动。" * 20, [{"content": "log"}]) == "length"


@pytest.mark.asyncio
async def test_long_tool_backed_draft_uses_arithmetic_budget_and_options(monkeypatch):
    """The arithmetic path's timeout and request options apply, not the length path's."""
    from jiuwenswarm.server.runtime.agent_adapter import formal_live_voice as module
    monkeypatch.setattr(module, "LENGTH_REVISION_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(module, "ARITHMETIC_REVISION_TIMEOUT_SECONDS", 5)
    seen = {}

    def options(model, reason):
        seen["reason"] = reason
        return {}

    monkeypatch.setattr(module, "spoken_revision_request_options", options)

    async def slow_but_within_arithmetic_budget(**kwargs):
        await asyncio.sleep(0.1)
        return SimpleNamespace(
            content=json.dumps({"text": "最晚 15:00 出发，费用 120 元。", "detailed_requested": False}),
            tool_calls=[],
        )

    long_arithmetic = "从 16:10 出发，路上 45 分钟，费用 120 元，来得及。" + "另外还有一些背景说明。" * 20
    spoken = await finalize_spoken_answer(SimpleNamespace(invoke=slow_but_within_arithmetic_budget),
        envelope="q", candidate=long_arithmetic, tool_results=[{"content": "timetable"}])
    assert seen["reason"] == "arithmetic"
    assert spoken == "最晚 15:00 出发，费用 120 元。"


def test_spoken_revision_reasoning_only_on_arithmetic_path(monkeypatch):
    from jiuwenswarm.common import reasoning_injector

    monkeypatch.setattr(
        reasoning_injector, "bounded_semantic_request_options",
        lambda client, config: {"extra_body": {"thinking": {"type": "disabled"}}},
    )
    model = SimpleNamespace(model_client_config=SimpleNamespace(model_dump=lambda: {}), model_config=None)
    assert spoken_revision_request_options(model, "length") == {"extra_body": {"thinking": {"type": "disabled"}}}
    arithmetic = spoken_revision_request_options(model, "arithmetic")
    assert arithmetic["extra_body"]["thinking"] == {"type": "enabled"}
    assert arithmetic["reasoning_effort"] == "low"
    assert spoken_revision_request_options(SimpleNamespace(), "length") == {}


def test_observability_uses_installed_setup_exports(monkeypatch):
    from jiuwenswarm.agents.harness import agent_observability as module
    from openjiuwen.agent_teams.observability import setup
    monkeypatch.setattr(module, "_agent_observability_active", False)
    assert module.open_agent_run_span() is None
    monkeypatch.setattr(module, "_agent_observability_active", True)
    monkeypatch.setattr(setup, "is_initialized", lambda: False)
    assert callable(setup.get_tracer)
    assert module.open_agent_run_span() is None
