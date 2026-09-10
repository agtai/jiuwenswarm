from __future__ import annotations

from pathlib import Path

from jiuwenswarm.agents.harness.common.tools import wiki_tools


def test_publishes_every_content_page_with_the_prefix(tmp_path):
    # index.md and log.md are deliberately excluded; see
    # test_wiki_publish_filter.py for that contract.
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "bigbird.md").write_text("# BigBird")
    (wiki / "sparse_attention.md").write_text("# Sparse attention")
    memory = tmp_path / "memory"

    published = wiki_tools.publish_wiki_pages(wiki, memory)

    names = sorted(p.name for p in published)
    assert names == ["wiki__bigbird.md", "wiki__sparse_attention.md"]
    assert (memory / "wiki__bigbird.md").read_text() == "# BigBird"


def test_creates_the_memory_directory_when_absent(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "a.md").write_text("a")
    memory = tmp_path / "does" / "not" / "exist"

    wiki_tools.publish_wiki_pages(wiki, memory)

    assert (memory / "wiki__a.md").is_file()


def test_republishing_overwrites_the_previous_copy(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    page = wiki / "a.md"
    page.write_text("first")
    memory = tmp_path / "memory"
    wiki_tools.publish_wiki_pages(wiki, memory)

    page.write_text("second")
    wiki_tools.publish_wiki_pages(wiki, memory)

    assert (memory / "wiki__a.md").read_text() == "second"


def test_ignores_non_markdown_and_subdirectories(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "sub").mkdir(parents=True)
    (wiki / "a.md").write_text("a")
    (wiki / "notes.txt").write_text("t")
    (wiki / "sub" / "b.md").write_text("b")
    memory = tmp_path / "memory"

    published = wiki_tools.publish_wiki_pages(wiki, memory)

    assert [p.name for p in published] == ["wiki__a.md"]


def test_returns_empty_list_when_the_wiki_directory_is_missing(tmp_path):
    assert wiki_tools.publish_wiki_pages(tmp_path / "nope", tmp_path / "memory") == []
