"""The doc-crew group's one-pen discipline, as code (D20's first enforcement).

The group's protocol says only the scribe writes; for the leader and the
reviewer that must be a rail, not persona text (the guardrail principle:
safety rules are code). These tests pin three things: the packaged group
declares the rail for exactly the non-scribe members, the loader carries the
declaration into the member templates, and the rail itself refuses by effect
class -- so a write tool added later is covered the day it declares its class.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

GROUP = Path("jiuwenswarm/resources/agent/workspace/plugins/agent_groups/doc-crew")


def _load_rail_cls(member: str):
    p = GROUP / "agents" / member / "rails" / "one_pen_rail.py"
    spec = importlib.util.spec_from_file_location(f"one_pen_{member}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OnePenRail


def test_the_pen_belongs_to_the_scribe_alone():
    for member, has_rail in (("leader", True), ("reviewer", True), ("scribe", False)):
        m = json.loads((GROUP / "agents" / member / "manifest.json").read_text("utf-8"))
        declared = any(r.get("class") == "OnePenRail" for r in m.get("rails") or [])
        assert declared is has_rail, f"{member}: rail declared={declared}"


def test_the_loader_carries_the_rail_into_the_templates():
    from jiuwenswarm.agents.swarm.agent_group import load_agent_group_package

    templates = load_agent_group_package(GROUP)

    def has_one_pen(t):
        return any(
            r.type == "harness.rail.file" and r.params.get("class_name") == "OnePenRail"
            for r in t.rails
        )

    assert has_one_pen(templates["leader"])
    assert has_one_pen(templates["reviewer"])
    assert not templates["scribe"].rails, "执笔人不受一支笔轨约束"


def _ctx(tool_name: str, args: dict | None = None):
    tool_call = SimpleNamespace(id="tc1", arguments=args or {})
    inputs = SimpleNamespace(tool_name=tool_name, tool_call=tool_call,
                             tool_args=args or {}, tool_result=None, tool_msg=None)
    return SimpleNamespace(inputs=inputs, extra={})


@pytest.mark.asyncio
async def test_the_rail_refuses_every_write_class_and_only_those():
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        EFFECT_CLASSES,
    )

    rail = _load_rail_cls("leader")()
    blocked = {"revertible_write", "irreversible_write", "grant"}
    for tool, klass in EFFECT_CLASSES.items():
        ctx = _ctx(tool, {"doc_id": "d1"})
        await rail.before_tool_call(ctx)
        if klass in blocked:
            assert ctx.extra.get("_skip_tool") is True, f"{tool} ({klass}) 应被拒"
        else:
            assert "_skip_tool" not in ctx.extra, f"{tool} ({klass}) 不应被拒"
    # non-clouddoc tools pass untouched
    ctx = _ctx("execute_command", {})
    await rail.before_tool_call(ctx)
    assert "_skip_tool" not in ctx.extra


@pytest.mark.asyncio
async def test_an_undeclared_clouddoc_tool_reads_as_a_write():
    """Subtraction rails read silence as refusal (the D16 floor's logic)."""
    rail = _load_rail_cls("reviewer")()
    ctx = _ctx("clouddoc_future_tool", {"doc_id": "d1"})
    await rail.before_tool_call(ctx)
    assert ctx.extra.get("_skip_tool") is True
