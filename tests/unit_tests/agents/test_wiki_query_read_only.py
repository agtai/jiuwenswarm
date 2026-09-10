from __future__ import annotations

import inspect

from jiuwenswarm.agents.harness.common.tools import wiki_tools
from jiuwenswarm.agents.harness.common.tools.wiki_tools import build_query_prompt, wiki_query

_WRITE_BACK_MARKER = "you may write it back as a wiki page"


def test_a_query_is_read_only_by_default():
    """Answering must not mutate the library unless the caller asks for it.

    The write-back used to be unconditional, and it reached the maintainer subagent
    through build_query_prompt -- a layer the channel's own "frozen library" rule does
    not govern, since that rule is addressed to the main agent. A real run created a
    page, registered it in index.md and appended to log.md while merely answering.
    """
    prompt = build_query_prompt("who wrote this?")
    assert _WRITE_BACK_MARKER not in prompt
    assert "do NOT create, edit or delete any file" in prompt


def test_write_back_is_still_available_when_explicitly_allowed():
    prompt = build_query_prompt("who wrote this?", allow_write=True)
    assert _WRITE_BACK_MARKER in prompt
    assert "schema/AGENT.md" in prompt


def test_the_tool_defaults_to_read_only():
    """The default lives on the tool signature, where a caller can see it."""
    assert inspect.signature(wiki_query._func).parameters["allow_write"].default is False


async def test_query_passes_the_flag_through(monkeypatch, tmp_path):
    seen = {}

    class _Agent:
        async def invoke(self, payload, session=None):
            seen["query"] = payload["query"]
            return {"output": "ok"}

    monkeypatch.setattr(wiki_tools, "create_deep_agent", lambda **kwargs: _Agent())
    wiki = wiki_tools.LLMWiki(workspace=str(tmp_path), model=object())

    await wiki.query(question="q")
    assert _WRITE_BACK_MARKER not in seen["query"]

    await wiki.query(question="q", allow_write=True)
    assert _WRITE_BACK_MARKER in seen["query"]
