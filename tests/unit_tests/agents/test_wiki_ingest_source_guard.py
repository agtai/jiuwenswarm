from __future__ import annotations

from pathlib import Path

import pytest

from jiuwenswarm.agents.harness.common.tools import wiki_tools


@pytest.fixture
def fake_roots(tmp_path, monkeypatch):
    """Point both allowed roots at a tmp dir so the guard is testable."""
    sessions = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    sessions.mkdir()
    workspace.mkdir()
    monkeypatch.setattr(wiki_tools, "get_agent_sessions_dir", lambda: sessions)
    monkeypatch.setattr(wiki_tools, "get_agent_workspace_dir", lambda: workspace)
    return sessions, workspace


def test_allows_a_file_under_the_sessions_dir(fake_roots):
    sessions, _ = fake_roots
    uploaded = sessions / "s1" / "uploads" / "paper.pdf"
    uploaded.parent.mkdir(parents=True)
    uploaded.write_text("x")
    assert wiki_tools.source_is_allowed(uploaded) is True


def test_allows_a_file_under_the_agent_workspace(fake_roots):
    _, workspace = fake_roots
    doc = workspace / "notes.md"
    doc.write_text("x")
    assert wiki_tools.source_is_allowed(doc) is True


def test_refuses_a_file_outside_both_roots(fake_roots, tmp_path):
    secret = tmp_path / "config" / ".env"
    secret.parent.mkdir(parents=True)
    secret.write_text("API_KEY=x")
    assert wiki_tools.source_is_allowed(secret) is False


def test_refuses_traversal_out_of_an_allowed_root(fake_roots):
    sessions, _ = fake_roots
    escape = sessions / ".." / "elsewhere.md"
    assert wiki_tools.source_is_allowed(escape) is False


def test_ingestible_suffixes_are_the_three_document_types():
    assert wiki_tools.INGESTIBLE_SUFFIXES == (".pdf", ".md", ".txt")
