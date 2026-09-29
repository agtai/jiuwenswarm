"""The agent's side: the tools a session gets, attached or not, and a real edit."""

from __future__ import annotations

from jiuwenswarm.extensions.blackboard import extension as extension_module
from jiuwenswarm.extensions.blackboard.client.hosts import HostEntry, HostRegistry
from jiuwenswarm.extensions.blackboard.client.sessions import SessionAttachments
from jiuwenswarm.extensions.blackboard.client.toolkit.bridge import to_openjiuwen
from jiuwenswarm.extensions.blackboard.client.toolkit.tools import MandateRef, SessionTools, WorkspaceRef
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.extension import BlackboardApplicationPlugin
from jiuwenswarm.extensions.sdk import AgentToolContext
from jiuwenswarm.extensions.blackboard.tests.backend.support import Instance, free_port, rpc

READ_TOOLS = {
    "blackboard_list_workspaces",
    "blackboard_list_docs",
    "blackboard_read",
    "blackboard_list_references",
    "blackboard_read_reference",
    "blackboard_list_decisions",
    "blackboard_read_chat",
}
TOOL_NAMES = READ_TOOLS | {"blackboard_edit"}


async def _joined(tmp_path) -> None:
    await HostRegistry(tmp_path / "client" / "hosts.json").upsert(HostEntry(id="h1", host_uid="u1", name="Team", url="http://x", token="t", user_id="u"))


async def test_every_session_reads_and_attached_ones_edit(tmp_path, monkeypatch):
    monkeypatch.setattr(extension_module, "blackboard_dir", lambda: tmp_path)
    plugin = BlackboardApplicationPlugin()
    ctx = AgentToolContext(session_id="sess-1", request_id="r1")
    # No host joined: no Blackboard tools at all.
    assert plugin.agent_tools(ctx) == []
    assert plugin.agent_tools(AgentToolContext(session_id=None)) == []

    await _joined(tmp_path)
    reading = plugin.agent_tools(ctx)
    assert {t.card.name for t in reading} == READ_TOOLS
    assert "Reading only" in next(t for t in reading if t.card.name == "blackboard_list_workspaces").card.description

    attachments = SessionAttachments(tmp_path / "client" / "sessions.json")
    await attachments.attach("sess-1", "h1", "ws1", "Launch plan")
    tools = plugin.agent_tools(ctx)
    assert {t.card.name for t in tools} == TOOL_NAMES
    assert '"Launch plan" (ws1)' in next(t for t in tools if t.card.name == "blackboard_list_workspaces").card.description
    # The same instances turn after turn; only the turn id moves.
    again = plugin.agent_tools(AgentToolContext(session_id="sess-1", request_id="r2"))
    assert again is tools and plugin._toolsets["sess-1"][1].turn_id == "r2"

    # A second workspace rebuilds the tools for both.
    await attachments.attach("sess-1", "h2", "ws2", "Research")
    both = plugin.agent_tools(AgentToolContext(session_id="sess-1", request_id="r3"))
    assert both is not tools and [w.workspace_id for w in plugin._toolsets["sess-1"][1].workspaces] == ["ws1", "ws2"]

    await attachments.detach("sess-1")
    assert {t.card.name for t in plugin.agent_tools(ctx)} == READ_TOOLS


async def test_a_dispatched_turn_edits_under_its_task_and_may_ask(tmp_path, monkeypatch):
    monkeypatch.setattr(extension_module, "blackboard_dir", lambda: tmp_path)
    plugin = BlackboardApplicationPlugin()
    await _joined(tmp_path)
    await SessionAttachments(tmp_path / "client" / "sessions.json").attach("s1", "h1", "ws1", "Launch")
    meta = {"blackboard": {"host": "h1", "workspace_id": "ws1", "mandate_id": "m1", "origin": "comment", "workspace_title": "Launch"}}
    tools = plugin.agent_tools(AgentToolContext(session_id="s1", channel_id="__blackboard__", request_id="r1", metadata=meta))
    assert {t.card.name for t in tools} == TOOL_NAMES | {"blackboard_ask"}
    toolkit = plugin._toolsets["s1"][1]
    assert toolkit.mandate == MandateRef("h1", "ws1", "m1", "comment")
    # The same metadata on another channel is not a dispatched turn.
    plain = plugin.agent_tools(AgentToolContext(session_id="s1", channel_id="web", request_id="r2", metadata=meta))
    toolkit = plugin._toolsets["s1"][1]
    assert {t.card.name for t in plain} == TOOL_NAMES and toolkit.mandate is None

    sent: list[tuple[str, dict]] = []

    async def fake_call(ws, method, params, timeout=30.0):  # noqa: ANN001
        sent.append((method, params))
        return {"mandate_id": params.get("mandate_id"), "decision_id": "dc1"}

    toolkit._call = fake_call  # type: ignore[method-assign]
    toolkit.mandate = MandateRef("h1", "ws1", "m1", "comment")
    toolkit._homes.update({"d1": WorkspaceRef("h1", "ws1"), "d9": WorkspaceRef("h2", "ws9")})
    await toolkit.edit("d1", [{"op": "delete", "block_id": "b1", "digest": "x"}])
    assert sent[-1] == (p.EDIT, {"doc_id": "d1", "ops": [{"op": "delete", "block_id": "b1", "digest": "x"}], "note": "", "mandate_id": "m1"})
    run = {spec.name: spec.func for spec in toolkit.specs()}
    assert (await run["blackboard_edit"](doc="d9", ops=[]))["code"] == "out_of_scope"
    asked = await run["blackboard_ask"](question="Which?", options=[{"label": "a"}, {"label": "b"}], recommended=0)
    assert asked["ok"] and sent[-1] == (p.DECISION_CREATE, {"mandate_id": "m1", "question": "Which?", "options": [{"label": "a"}, {"label": "b"}], "recommended": 0})


def test_the_model_sees_the_tools_and_json_results():
    from openjiuwen.core.foundation.tool import ToolExposure
    from openjiuwen.core.single_agent.ability_manager import AbilityManager

    toolkit = SessionTools(registry=None, session_id="s1", workspaces=[WorkspaceRef("h1", "ws1", "Plan")])
    manager = AbilityManager()
    manager.set_tool_exposure_policy(progressive_tool_enabled=True)
    for tool in to_openjiuwen(toolkit.specs(), owner="s1"):
        manager.add(tool.card)
        assert tool.card.exposure == ToolExposure.DIRECT
        assert tool.render_for_llm({"ok": True, "title": "Plan"}) == '{"ok": true, "title": "Plan"}'


async def test_attaching_needs_an_editor_and_one_workspace_per_session(tmp_path):
    instance = Instance(tmp_path, HostSettings(enabled=True, port=free_port()))
    await instance.start()
    try:
        first = (await instance.channel.ok(p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"}))["workspace"]["id"]
        second = (await instance.channel.ok(p.WORKSPACE_CREATE, {"name": "other", "title": "Other"}))["workspace"]["id"]
        attached = await instance.channel.ok(p.SESSION_ATTACH, {"session_id": "s1", "workspace_id": first})
        assert attached["session"]["workspace_id"] == first and attached["session"]["title"] == "Launch"
        again = await instance.channel.ok(p.SESSION_ATTACH, {"session_id": "s1", "workspace_id": first})
        assert again["session"]["attached_at"] == attached["session"]["attached_at"]
        listed = await instance.channel.ok(p.SESSION_LIST, {"workspace_id": first})
        assert [s["session_id"] for s in listed["sessions"]] == ["s1"]
        assert instance.channel.named(p.EV_SESSIONS_UPDATED)

        # A session works on several workspaces; detaching names one of them.
        added = await instance.channel.ok(p.SESSION_ATTACH, {"session_id": "s1", "workspace_id": second})
        assert added["session"]["workspace_id"] == second and added["session"]["title"] == "Other"
        mine = (await instance.channel.ok(p.SESSION_LIST, {"session_id": "s1"}))["sessions"]
        assert [s["workspace_id"] for s in mine] == [first, second] and mine[0]["host_name"]
        await instance.channel.ok(p.SESSION_DETACH, {"session_id": "s1", "workspace_id": first})
        mine = (await instance.channel.ok(p.SESSION_LIST, {"session_id": "s1"}))["sessions"]
        assert [s["workspace_id"] for s in mine] == [second]
        assert (await instance.channel.ok(p.SESSION_LIST, {"session_id": "s9"}))["sessions"] == []
        assert (await instance.channel.ok(p.SESSION_DETACH, {"session_id": "s1"}))["detached"] is True
        assert (await instance.channel.ok(p.SESSION_LIST, {}))["sessions"] == []
        missing = await instance.channel.call(p.SESSION_ATTACH, {"session_id": "s2", "workspace_id": "ws_nope"})
        assert missing["code"] == "not_member"
    finally:
        await instance.stop()


async def test_the_tools_read_and_edit_a_real_document(real_docservice, host, tmp_path):
    assert await host.docs.wait_ready(20)
    operator = await host.operator("Alice")
    token = await host.rotate_token(operator.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"}, token)
    workspace_id = created["payload"]["workspace"]["id"]
    _, made = await rpc(host.base, p.DOC_CREATE, {"workspace_id": workspace_id, "title": "Plan", "markdown": "# Plan\n\nShip it soon.\n"}, token)
    doc_id = made["payload"]["doc"]["id"]

    registry = HostRegistry(tmp_path / "hosts.json")
    await registry.upsert(HostEntry(id="h1", host_uid=host.ctx.host_uid, name="Team", url=host.base, token=token, user_id=operator.id))
    tools = SessionTools(registry=registry, session_id="sess-1", workspaces=[WorkspaceRef("h1", workspace_id, "Launch")], turn_id="t1")
    run = {spec.name: spec.func for spec in tools.specs()}

    # A document id alone finds its workspace, listed or not.
    read = await run["blackboard_read"](doc=doc_id)
    assert read["workspace"] == workspace_id
    listed = await run["blackboard_list_docs"]()
    [space] = listed["workspaces"]
    assert listed["ok"] and space["instructions_doc"] and doc_id in [d["id"] for d in space["docs"]]
    assert (await run["blackboard_list_docs"](workspace="ws_nope"))["code"] == "workspace_required"
    block = read["blocks"][1]
    assert "<!-- block:" in read["markdown"] and "Ship it soon." in read["markdown"]

    edited = await run["blackboard_edit"](
        doc=doc_id, ops=[{"op": "replace", "block_id": block["id"], "digest": block["digest"], "markdown": "Ship it on Friday."}], note="Set a date"
    )
    assert edited["ok"] and edited["suggestion_ids"], edited
    proposed = await run["blackboard_read"](doc=doc_id, view="proposed")
    assert "Ship it on Friday." in proposed["markdown"]

    stale = await run["blackboard_edit"](doc=doc_id, ops=[{"op": "delete", "block_id": block["id"], "digest": block["digest"]}])
    assert stale["ok"] is False and stale["code"] == "stale" and stale["details"]["changed_blocks"]
    assert (await run["blackboard_read_reference"](reference="r_nope"))["code"] == "not_found"
    assert (await run["blackboard_edit"](doc=doc_id, ops="not a list"))["code"] == "invalid"

    _, mandates = await rpc(host.base, p.MANDATE_LIST, {"workspace_id": workspace_id}, token)
    [mandate] = mandates["payload"]["mandates"]
    assert mandate["instruction"] == "Set a date" and [r["status"] for r in mandate["receipts"]] == ["applied", "aborted"]
