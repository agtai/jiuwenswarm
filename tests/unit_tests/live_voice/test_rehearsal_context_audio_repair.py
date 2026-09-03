"""Focused boundaries from the recorded interrupted-context rehearsal."""
import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ContextRef, ScopeRef
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.product_composition_registry import AgentServerProductCompositionRegistry
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextEntry, FormalContextSnapshot, finalize_spoken_answer,
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
async def test_short_dialogue_skips_revision_and_bad_revision_does_not_lose_answer():
    calls = []
    async def invoke(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content="invalid", tool_calls=[{"name": "write_file"}])
    model = SimpleNamespace(invoke=invoke)
    assert await finalize_spoken_answer(model, envelope="q", candidate="answer", tool_results=[]) == "answer"
    assert not calls
    assert await finalize_spoken_answer(model, envelope="q", candidate="answer", tool_results=[{}]) == "answer"
    assert len(calls) == 1


def test_observability_uses_installed_setup_exports(monkeypatch):
    from jiuwenswarm.agents.harness import agent_observability as module
    from openjiuwen.agent_teams.observability import setup
    monkeypatch.setattr(module, "_agent_observability_active", False)
    assert module.open_agent_run_span() is None
    monkeypatch.setattr(module, "_agent_observability_active", True)
    monkeypatch.setattr(setup, "is_initialized", lambda: False)
    assert callable(setup.get_tracer)
    assert module.open_agent_run_span() is None
