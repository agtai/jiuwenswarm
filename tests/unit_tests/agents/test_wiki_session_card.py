from __future__ import annotations

import pytest

from openjiuwen.core.session.agent import Session
from openjiuwen.core.single_agent.schema.agent_card import AgentCard


def test_a_session_without_a_card_cannot_report_its_agent_id():
    """Pins the kernel behaviour the fix depends on.

    ``get_agent_id`` reads ``self._card.id``. The wiki maintainer's session was
    built without a card, so every write_file/edit_file/bash raised this AFTER
    successfully writing the file -- 167 times in a single three-paper run. The
    agent then burned turns re-reading files to check writes it had already made,
    and `bash date` failing is why every log.md entry is dated [unknown].
    """
    session = Session(session_id="no-card")
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'id'"):
        session.get_agent_id()


def test_a_session_with_a_card_reports_an_agent_id():
    session = Session(session_id="with-card", card=AgentCard(name="wiki_agent", description="d"))
    assert session.get_agent_id()


def test_llm_wiki_builds_its_session_with_the_agent_card(monkeypatch, tmp_path):
    """The regression test proper: LLMWiki must hand its card to the Session."""
    from jiuwenswarm.agents.harness.common.tools import wiki_tools

    monkeypatch.setattr(wiki_tools, "create_deep_agent", lambda **kwargs: object())
    wiki = wiki_tools.LLMWiki(workspace=str(tmp_path), model=object())

    assert wiki._session.get_agent_id() == wiki.agent_card.id
