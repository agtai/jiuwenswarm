from __future__ import annotations

from jiuwenswarm.agents.harness.common.tools import wiki_tools


def test_navigation_pages_are_not_published(tmp_path):
    """index.md and log.md are navigation, not knowledge.

    Published, they compete with content in the memory index and win often --
    they name every topic. Worse, their chunks carry no source anchor, so a
    retrieval that lands on one leaves the agent unable to cite anything.
    """
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text("# Wiki Index")
    (wiki / "log.md").write_text("# Wiki Log")
    (wiki / "sparse_attention.md").write_text("# Sparse attention")
    memory = tmp_path / "memory"

    published = wiki_tools.publish_wiki_pages(wiki, memory)

    assert [p.name for p in published] == ["wiki__sparse_attention.md"]
    assert not (memory / "wiki__index.md").exists()
    assert not (memory / "wiki__log.md").exists()


def test_a_page_merely_named_like_the_index_is_still_published(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "auto-index.md").write_text("# Auto-Index")
    (wiki / "changelog.md").write_text("# Changelog")
    memory = tmp_path / "memory"

    names = sorted(p.name for p in wiki_tools.publish_wiki_pages(wiki, memory))

    assert names == ["wiki__auto-index.md", "wiki__changelog.md"]


def test_stale_navigation_copies_are_removed_on_republish(tmp_path):
    """A wiki published before this rule keeps index.md in memory forever."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "a.md").write_text("a")
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "wiki__index.md").write_text("stale")
    (memory / "wiki__log.md").write_text("stale")

    wiki_tools.publish_wiki_pages(wiki, memory)

    assert not (memory / "wiki__index.md").exists()
    assert not (memory / "wiki__log.md").exists()


def test_query_prompt_searches_before_reading():
    """wiki_query must not read the whole wiki: it does not scale."""
    prompt = wiki_tools.build_query_prompt("o que e X?")
    assert "grep" in prompt
    assert "index.md" in prompt
    assert "o que e X?" in prompt


def test_query_prompt_makes_a_write_follow_the_schema_rules():
    # Only reachable with allow_write=True now: a query is read-only by default, so
    # there is no write for the schema rules to govern unless the caller asks for one.
    prompt = wiki_tools.build_query_prompt("q", allow_write=True)
    assert "AGENT.md" in prompt
