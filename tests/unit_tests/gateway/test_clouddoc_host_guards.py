"""Host-layer guards for co-scribe: the file fence and the routing titles.

Both enforce at the layer that owns the resource (the 2026-08-13 principle,
generalized): the mandate machinery guards the cloud document; these guard the
host's side of it -- its own persisted files against generic tools, and the
model's tool routing against file-looking titles.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as _NS

import pytest

from jiuwenswarm.agents.harness.common.rails.clouddoc_file_guard_rail import (
    CloudDocFileGuardRail,
    _is_guarded_path,
)


class _Ctx:
    def __init__(self, tool_name, tool_args):
        self.inputs = {"tool_name": tool_name, "tool_args": tool_args,
                       "tool_call": _NS(id="tc-1")}
        self.extra = {}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/home/u/.jiuwenswarm/config/clouddoc-workmode.md",
    "~/.jiuwenswarm/config/clouddoc-receipts.json",
    "clouddoc-watches.json",
    "/x/clouddoc-watches-audit.jsonl",
    "/home/u/.jiuwenswarm/config/clouddoc-keys/feishu.json",
    "C:\\\\u\\\\clouddoc-state.json",
])
async def test_generic_writes_to_coscribe_files_are_refused(path):
    ctx = _Ctx("edit_file", {"file_path": path, "new_string": "x", "old_string": "y"})
    await CloudDocFileGuardRail().before_tool_call(ctx)
    assert ctx.extra.get("_skip_tool") is True
    assert "CLOUDDOC_FILE_GUARDED" in ctx.inputs["tool_result"]
    assert "clouddoc_workmode_edit" in ctx.inputs["tool_msg"].content


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args", [
    ("read_file", {"file_path": "/home/u/.jiuwenswarm/config/clouddoc-workmode.md"}),
    ("edit_file", {"file_path": "/home/u/project/clouddocs.md"}),
    ("edit_file", {"file_path": "/home/u/notes/readme.md"}),
    ("write_file", {"file_path": "/home/u/project/my-clouddoc-notes/plan.md"}),
])
async def test_reads_and_unrelated_paths_pass(tool, args):
    ctx = _Ctx(tool, args)
    await CloudDocFileGuardRail().before_tool_call(ctx)
    assert ctx.extra.get("_skip_tool") is None


def test_guarded_path_shapes():
    assert _is_guarded_path("clouddoc-anything.json")
    assert _is_guarded_path("a/clouddoc-keys/k.json")
    assert _is_guarded_path("a/clouddoc-keys")  # the key dir itself is guarded too
    assert not _is_guarded_path("myclouddoc-notes.md")
    assert not _is_guarded_path(None)


def test_read_card_carries_the_adopted_titles(tmp_path, monkeypatch):
    """The routing evidence: registered titles appear in the read card, capped."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc import kinds as kinds_mod
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import CloudDocToolkit

    state = tmp_path / "clouddoc-state.json"
    docs = {f"d{i}": {"panel_meta": {"title": f"文档{i}"}} for i in range(14)}
    state.write_text(json.dumps({"docs": docs}), encoding="utf-8")
    monkeypatch.setattr(kinds_mod, "get_clouddoc_state_path", lambda: state)

    class _P:
        kind = "fake"
        receipt_sink = None
        def parse_doc_ref(self, r): return r
        def doc_url(self, d, k=""): return d

    kit = CloudDocToolkit(_P(), turn_address=lambda: "x",
                          watched_docs=lambda: [f"d{i}" for i in range(14)])
    card = next(t.card for t in kit.get_tools() if t.card.name == "clouddoc_read")
    assert "《文档0》" in card.description and "等 14 篇" in card.description
    assert "《文档13》" not in card.description  # capped at 12

    kit2 = CloudDocToolkit(_P(), turn_address=lambda: "x", watched_docs=lambda: [])
    card2 = next(t.card for t in kit2.get_tools() if t.card.name == "clouddoc_read")
    assert "当前已纳管" not in card2.description
