"""Reading from any session (milestone 7): naming workspaces, the access each request gets, and a
shared bot that reads for the connected person who wrote."""

from __future__ import annotations

from typing import Any

import pytest

from jiuwenswarm.extensions.blackboard import extension as extension_module
from jiuwenswarm.extensions.blackboard.client.bots import BotEntry, BotRegistry, parse_bot_link
from jiuwenswarm.extensions.blackboard.client.hosts import HostEntry, HostRegistry
from jiuwenswarm.extensions.blackboard.client.sessions import SessionAttachments
from jiuwenswarm.extensions.blackboard.client.toolkit import tools as tools_module
from jiuwenswarm.extensions.blackboard.client.toolkit.tools import Access, SessionTools, WorkspaceRef, forget_directory
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import BlackboardError
from jiuwenswarm.extensions.blackboard.extension import BlackboardApplicationPlugin
from jiuwenswarm.extensions.sdk import AgentToolContext
from jiuwenswarm.extensions.blackboard.tests.backend.support import rpc


@pytest.fixture(autouse=True)
def _fresh_directory():
    forget_directory()
    yield
    forget_directory()


def _workspace(workspace_id: str, name: str, title: str, role: str = "editor") -> dict[str, Any]:
    return {"id": workspace_id, "name": name, "title": title, "role": role, "archived": False}


async def _toolkit(tmp_path, hosts: dict[str, list[dict[str, Any]]], attached: list[WorkspaceRef] | None = None) -> tuple[SessionTools, list]:
    """A toolkit whose hosts answer from `hosts`; returns it and the calls it made."""
    registry = HostRegistry(tmp_path / "hosts.json")
    for host_id in hosts:
        await registry.upsert(HostEntry(host_id, host_id, host_id.upper(), f"http://{host_id}", "t", "u"))
    calls: list[tuple[str, str, dict]] = []

    async def fake_call(ws, method, params, timeout=30.0):  # noqa: ANN001
        calls.append((ws.host_id, method, params))
        if method == p.ME:
            return {"workspaces": hosts[ws.host_id], "host": {"name": ws.host_id.upper()}}
        if method == p.DOC_LIST:
            return {"docs": [{"id": f"d_{params['workspace_id']}", "title": "Plan", "is_instructions": False, "is_pinned": False}]}
        if method == p.DOC_READ:
            return {"markdown": "<!-- block:b1 -->\nShip.", "blocks": [{"id": "b1", "digest": "x", "hasPendingSuggestions": True}]}
        if method == p.SUGGESTION_LIST:
            return {"suggestions": [{"id": "s1", "author": {"id": "u2", "kind": "agent"}, "inserted": "Friday", "deleted": "", "blockIds": ["b1"]}, {"id": "s2", "blockIds": ["b9"]}]}
        if method == p.CHAT_LIST:
            return {"messages": [{"author_kind": "agent", "author_name": "Bob", "kind": "message", "body": "Done.", "created_at": "t"}], "has_more": True}
        return {}

    toolkit = SessionTools(registry=registry, session_id="s1", workspaces=attached or [])
    toolkit._call = fake_call  # type: ignore[method-assign]
    return toolkit, calls


async def test_workspaces_are_found_by_bb_name_title_or_id(tmp_path):
    toolkit, calls = await _toolkit(tmp_path, {"h1": [_workspace("ws1", "launch-plan", "Launch plan"), _workspace("ws2", "research", "Research")]})
    run = {spec.name: spec.func for spec in toolkit.specs()}
    for given in ("@bb:launch-plan", "launch-plan", "Launch Plan", "ws1"):
        listed = await run["blackboard_list_docs"](workspace=given)
        assert [w["id"] for w in listed["workspaces"]] == ["ws1"], given
        assert listed["workspaces"][0]["workspace"] == "@bb:launch-plan"
    # The workspaces are asked once and then remembered.
    assert [c for c in calls if c[1] == p.ME] == [("h1", p.ME, {})]

    missing = await run["blackboard_list_docs"]()
    assert missing["code"] == "workspace_required" and [w["workspace"] for w in missing["details"]["workspaces"]] == ["@bb:launch-plan", "@bb:research"]
    unknown = await run["blackboard_list_docs"](workspace="@bb:nope")
    assert unknown["code"] == "workspace_required" and len(unknown["details"]["workspaces"]) == 2

    everything = await run["blackboard_list_workspaces"]()
    assert everything["workspaces"][0] == {"workspace": "@bb:launch-plan", "id": "ws1", "title": "Launch plan", "host": "H1", "role": "editor", "editable_here": False}


async def test_one_name_on_two_hosts_is_ambiguous_and_one_workspace_needs_no_name(tmp_path):
    toolkit, _ = await _toolkit(tmp_path, {"h1": [_workspace("ws1", "plan", "Plan")], "h2": [_workspace("ws9", "plan", "Plan")]})
    ambiguous = await toolkit.specs()[1].func(workspace="@bb:plan")
    assert ambiguous["code"] == "ambiguous_workspace" and {c["host"] for c in ambiguous["details"]["candidates"]} == {"H1", "H2"}
    assert (await toolkit.specs()[1].func(workspace="ws9"))["workspaces"][0]["id"] == "ws9"

    forget_directory()
    single, _ = await _toolkit(tmp_path / "one", {"h1": [_workspace("ws1", "plan", "Plan")]})
    assert (await single.list_docs())["workspaces"][0]["id"] == "ws1"


async def test_reading_lists_pending_suggestions_and_editing_needs_an_attachment(tmp_path):
    toolkit, calls = await _toolkit(tmp_path, {"h1": [_workspace("ws1", "plan", "Plan"), _workspace("ws2", "other", "Other")]}, attached=[WorkspaceRef("h1", "ws1", "Plan")])
    run = {spec.name: spec.func for spec in toolkit.specs()}
    assert "blackboard_edit" in run
    read = await run["blackboard_read"](doc="d_ws2", workspace="@bb:other")
    assert read["read_only"] is True
    assert read["pending_suggestions"] == [{"id": "s1", "kind": "insert", "by": {"kind": "agent", "user_id": "u2"}, "inserted": "Friday", "deleted": "", "blocks": ["b1"]}]
    refused = await run["blackboard_edit"](doc="d_ws2", ops=[{"op": "delete", "block_id": "b1", "digest": "x"}])
    assert refused["code"] == "read_only"
    assert "read_only" not in await run["blackboard_read"](doc="d_ws1")
    chat = await run["blackboard_read_chat"](workspace="@bb:other", limit=500)
    assert chat["messages"] == [{"at": "t", "from": "Bob's agent", "kind": "message", "text": "Done."}] and chat["more_before"] is True
    assert (p.CHAT_LIST, {"workspace_id": "ws2", "limit": 100}) in [(m, prm) for _, m, prm in calls]


async def test_each_request_gets_the_access_its_channel_and_sender_allow(tmp_path, monkeypatch):
    monkeypatch.setattr(extension_module, "blackboard_dir", lambda: tmp_path)
    monkeypatch.setattr(extension_module, "load_im_owner_ids", lambda: [])
    plugin = BlackboardApplicationPlugin()
    base = tmp_path / "client"
    await HostRegistry(base / "hosts.json").upsert(HostEntry(id="h1", host_uid="u1", name="Team", url="http://x", token="member", user_id="u"))
    await SessionAttachments(base / "sessions.json").attach("s1", "h1", "ws1", "Launch")

    def names(ctx):
        return {t.card.name for t in plugin.agent_tools(ctx)}

    # A personal jiuwenswarm: its IM channels read with the owner's tokens, and cannot edit.
    web = names(AgentToolContext(session_id="s1", channel_id="web"))
    assert "blackboard_edit" in web
    slack = names(AgentToolContext(session_id="slack_T_C_U1", channel_id="slack", user_id="U1"))
    assert "blackboard_edit" not in slack and "blackboard_link_identity" not in slack
    assert plugin._toolsets["slack_T_C_U1"][1].access == Access("member")

    # With owners configured, another sender reads nothing.
    monkeypatch.setattr(extension_module, "load_im_owner_ids", lambda: ["slack:U_OWNER"])
    plugin.agent_tools(AgentToolContext(session_id="slack_T_C_U1", channel_id="slack", user_id="U1"))
    toolkit = plugin._toolsets["slack_T_C_U1"][1]
    assert toolkit.access.kind == "denied"
    refused = await {s.name: s.func for s in toolkit.specs()}["blackboard_list_workspaces"]()
    assert refused["code"] == "not_linked" and "owner" in refused["message"]
    plugin.agent_tools(AgentToolContext(session_id="slack_T_C_U1", channel_id="slack", user_id="U_OWNER"))
    assert plugin._toolsets["slack_T_C_U1"][1].access == Access("member")

    # A shared bot: IM requests read for the sender through the bot, whatever the session's attachments.
    await BotRegistry(base / "bots.json").upsert(BotEntry("hb1", "u1", "Team", "http://x", "bbb_t", "bot1", "Team bot"))
    bot = names(AgentToolContext(session_id="s1", channel_id="feishu", user_id="ou_7"))
    assert "blackboard_link_identity" in bot and "blackboard_edit" not in bot
    toolkit = plugin._toolsets["s1"][1]
    assert toolkit.access == Access("bot", on_behalf="feishu:ou_7")
    sent: list[dict[str, Any]] = []

    async def fake_call_host(url, method, params, **kwargs):  # noqa: ANN001
        sent.append({"url": url, "method": method, **kwargs})
        return {"workspaces": []}

    monkeypatch.setattr(tools_module, "call_host", fake_call_host)
    await toolkit.list_workspaces()
    assert sent[-1]["token"] == "bbb_t" and sent[-1]["headers"] == {p.AGENT_HEADER: "1", p.ON_BEHALF_HEADER: "feishu:ou_7"}
    # The web app on the same instance still works as the member, with the member's token.
    assert "blackboard_edit" in names(AgentToolContext(session_id="s1", channel_id="web"))
    await plugin._toolsets["s1"][1].list_workspaces()
    assert sent[-1]["token"] == "member" and p.ON_BEHALF_HEADER not in sent[-1]["headers"]


def test_bot_links_are_checked():
    assert parse_bot_link("https://bb.example.com/team/blackboard/bot#bbb_abc") == ("https://bb.example.com/team", "bbb_abc")
    for bad in ("", "ftp://x/blackboard/bot#bbb_a", "https://x/blackboard/join/abc", "https://x/blackboard/bot#bbm_member"):
        with pytest.raises(BlackboardError):
            parse_bot_link(bad)


async def test_a_shared_bot_connects_a_person_and_reads_for_them(host, tmp_path, monkeypatch):
    """Scenario 3 on a shared bot, without the model: the tools a Slack message gets, against a real host."""
    alice = await host.operator("Alice")
    token = await host.rotate_token(alice.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch-plan", "title": "Launch plan"}, token)
    workspace_id = created["payload"]["workspace"]["id"]
    _, made = await rpc(host.base, p.BOT_CREATE, {"name": "Team bot"}, token)

    # The bot's jiuwenswarm keeps the link; it has joined no host as a member.
    monkeypatch.setattr(extension_module, "blackboard_dir", lambda: tmp_path)
    from jiuwenswarm.extensions.blackboard.client.runtime import ClientRuntime

    async def quiet(*_):  # noqa: ANN002
        return None

    client = ClientRuntime(tmp_path / "client" / "hosts.json", quiet)
    connected = await client.connect_bot(made["payload"]["link"])
    assert connected["bot"]["bot_name"] == "Team bot" and "token" not in connected["bot"]

    plugin = BlackboardApplicationPlugin()
    ctx = AgentToolContext(session_id="slack_T_D_U_ALICE", channel_id="slack", user_id="U_ALICE", request_id="r1")
    run = {t.card.name: t for t in plugin.agent_tools(ctx)}
    toolkit = plugin._toolsets["slack_T_D_U_ALICE"][1]
    tools = {s.name: s.func for s in toolkit.specs()}
    assert set(run) >= {"blackboard_list_workspaces", "blackboard_link_identity"}

    before = await tools["blackboard_list_workspaces"]()
    assert before["code"] == "not_linked" and "Connected IM accounts" in before["message"]
    _, code = await rpc(host.base, p.IDENTITY_LINK_CODE, {}, token)
    linked = await tools["blackboard_link_identity"](code=code["payload"]["code"])
    assert linked["ok"] and linked["connected_as"] == "Alice", linked
    after = await tools["blackboard_list_workspaces"]()
    assert [w["workspace"] for w in after["workspaces"]] == ["@bb:launch-plan"]
    docs = await tools["blackboard_list_docs"](workspace="@bb:launch-plan")
    assert docs["ok"] and docs["workspaces"][0]["id"] == workspace_id

    # Another Slack user in the same chat is not Alice.
    plugin.agent_tools(AgentToolContext(session_id="slack_T_D_U_ALICE", channel_id="slack", user_id="U_MALLORY", request_id="r2"))
    other = await tools["blackboard_list_workspaces"]()
    assert other["code"] == "not_linked"
    # Nothing was written for either of them.
    _, chat = await rpc(host.base, p.CHAT_LIST, {"workspace_id": workspace_id}, token)
    _, runs = await rpc(host.base, p.MANDATE_LIST, {"workspace_id": workspace_id}, token)
    assert chat["payload"]["messages"] == [] and runs["payload"]["mandates"] == []
