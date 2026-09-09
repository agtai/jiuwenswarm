from __future__ import annotations

from jiuwenswarm.server.runtime.agent_adapter import interface_deep


def _names(tools):
    return sorted(t.card.name for t in tools)


def test_shared_tools_include_the_wiki_and_pdf_tools():
    assert _names(interface_deep.SHARED_AGENT_TOOLS) == [
        "read_pdf",
        "wiki_ingest",
        "wiki_query",
    ]


def test_wiki_lint_is_deliberately_not_registered():
    # It only lints an existing wiki and the PoC does not use it; keeping it out
    # keeps three tool cards off every agent's prompt instead of four.
    assert "wiki_lint" not in _names(interface_deep.SHARED_AGENT_TOOLS)
