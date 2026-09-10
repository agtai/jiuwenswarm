from __future__ import annotations

import pytest

from jiuwenswarm.agents.harness.common.tools import wiki_tools
from jiuwenswarm.agents.harness.common.tools.wiki_tools import wiki_query


@pytest.fixture
def empty_agent_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(wiki_tools, "get_agent_workspace_dir", lambda: tmp_path)
    return tmp_path


async def test_an_omitted_workspace_names_the_path_it_tried(empty_agent_workspace):
    """The message must say WHERE it looked, not just that nothing was there.

    A real run called wiki_query with no workspace argument. The default resolves to
    <agent workspace>/.llm_wiki, which is not where the papers wiki lives, so the tool
    returned "the workspace '' does not have an initialized LLM Wiki -- use wiki_ingest
    first". That diagnosis is wrong and the suggested action is destructive-ish: the
    wiki existed, under a different path. The model had to guess, and only got it right
    on the second attempt.
    """
    out = await wiki_query._func(query="anything")

    assert "Error" in out
    assert str(empty_agent_workspace / ".llm_wiki") in out, "must name the resolved path"
    assert "no workspace was given" in out, "must say the argument was missing"


async def test_a_wrong_workspace_also_names_the_resolved_path(empty_agent_workspace):
    out = await wiki_query._func(query="anything", workspace="wikis/papers")

    assert str(empty_agent_workspace / "wikis" / "papers" / ".llm_wiki") in out


async def test_it_no_longer_tells_the_caller_to_ingest_when_the_path_is_the_problem(
    empty_agent_workspace,
):
    """`wiki_ingest` first is right for an empty corpus and wrong for a wrong path."""
    out = await wiki_query._func(query="anything")

    assert "pass the workspace" in out.lower()
