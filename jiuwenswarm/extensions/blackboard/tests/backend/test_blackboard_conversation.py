"""Comments and the workspace chat: storage, the mention rule, comment-task scope and queue."""

from __future__ import annotations

import pytest

from jiuwenswarm.extensions.blackboard.common import mentions
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, FORBIDDEN, INVALID
from jiuwenswarm.extensions.blackboard.host.api import dispatch
from jiuwenswarm.extensions.blackboard.host.store import mandates
from jiuwenswarm.extensions.blackboard.tests.backend.support import ANCHOR

AGENT = [{"kind": "agent"}]


async def _scene(world):
    alice, _ = await world.user("Alice")
    bob, _ = await world.user("Bob")
    carol, _ = await world.user("Carol")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, bob, "editor")
    await world.add(workspace_id, carol, "commenter")
    doc_id = await world.doc(alice, workspace_id, title="Plan")
    return alice, bob, carol, workspace_id, doc_id


def _runs(world, user_id: str) -> list[str]:
    return [payload["mandate_id"] for event, payload, _, users in world.hub.published if event == p.EV_MANDATE_RUN and users == (user_id,)]


def test_the_agent_is_named_only_when_text_and_composer_agree():
    assert mentions.names_agent("@jiuwen shorten this", AGENT)
    assert mentions.names_agent("Please, @Jiuwen: shorten this", AGENT)
    assert not mentions.names_agent("@jiuwen shorten this", [])
    assert not mentions.names_agent("shorten this", AGENT)
    assert not mentions.names_agent("mail me at bob@jiuwen.dev", AGENT)
    assert not mentions.names_agent("@jiuwenish is not the agent", AGENT)
    assert mentions.without_agent("@jiuwen   shorten this") == "shorten this"
    assert mentions.parse([{"kind": "user", "id": "u1"}, {"kind": "agent"}, {"kind": "agent"}]) == [
        {"kind": "user", "id": "u1"},
        {"kind": "agent"},
    ]
    with pytest.raises(Exception):
        mentions.parse([{"kind": "robot"}])


async def test_a_comment_opens_a_thread_on_the_passage(world):
    alice, bob, _, _, doc_id = await _scene(world)
    created = await world.thread(alice, doc_id, body="Is this date right?\nIt moved twice.")
    thread = created["thread"]
    assert thread["anchor"] == {**ANCHOR, "block_to": "b1", "status": "ok"}
    assert created["comment"]["body"] == "Is this date right?\nIt moved twice." and created["comment"]["mandate_id"] is None
    await world.call(bob, p.COMMENT_REPLY, thread_id=thread["id"], body="Yes, Friday.")

    listed = (await world.call(bob, p.COMMENT_LIST, doc_id=doc_id))["threads"]
    assert [t["id"] for t in listed] == [thread["id"]]
    assert [(c["author_name"], c["body"]) for c in listed[0]["comments"]] == [
        ("Alice", "Is this date right?\nIt moved twice."),
        ("Bob", "Yes, Friday."),
    ]
    assert p.EV_THREAD_UPDATED in world.hub.events()

    bad = await world.fails(alice, p.COMMENT_CREATE, doc_id=doc_id, anchor={**ANCHOR, "quote": ""}, body="x")
    assert bad.code == INVALID
    # A long selection is kept whole; only an absurd one is refused.
    long = "Ship on Friday. " * 1000
    kept = await world.thread(alice, doc_id, anchor={"quote": long, "length": len(long)})
    assert kept["thread"]["anchor"]["quote"] == long
    huge = await world.fails(alice, p.COMMENT_CREATE, doc_id=doc_id, anchor={**ANCHOR, "quote": "x" * 100_001}, body="x")
    assert huge.code == INVALID


async def test_anchors_are_checked_and_moved_anchors_are_kept(world):
    alice, _, _, _, doc_id = await _scene(world)
    thread_id = (await world.thread(alice, doc_id))["thread"]["id"]
    world.ctx.docs.anchor_results["the launch date"] = {"status": "ok", "block_id": "b7", "block_to": "b7", "start": "NEW1", "end": "NEW2", "offset": 0}
    listed = (await world.call(alice, p.COMMENT_LIST, doc_id=doc_id))["threads"]
    assert listed[0]["anchor"]["block_id"] == "b7" and listed[0]["anchor"]["start"] == "NEW1"
    # Stored: the next list starts from the moved anchor.
    world.ctx.docs.anchor_results.clear()
    again = (await world.call(alice, p.COMMENT_LIST, doc_id=doc_id))["threads"][0]["anchor"]
    assert (again["block_id"], again["status"]) == ("b7", "ok")
    world.ctx.docs.anchor_results["the launch date"] = {"status": "orphaned"}
    assert (await world.call(alice, p.COMMENT_LIST, doc_id=doc_id))["threads"][0]["anchor"]["status"] == "orphaned"
    assert thread_id


async def test_an_editors_mention_gives_the_agent_the_passage(world):
    alice, bob, _, workspace_id, doc_id = await _scene(world)
    created = await world.thread(bob, doc_id, body="@jiuwen shorten this", mentions=AGENT, anchor={"block_to": "b3"})
    mandate_id = created["comment"]["mandate_id"]
    mandate = await world.store.read(lambda c: mandates.get(c, mandate_id))
    assert (mandate.origin, mandate.status, mandate.instruction) == ("comment", "running", "shorten this")
    assert mandate.scope == {"doc_id": doc_id, "block_from": "b1", "block_to": "b3"}
    assert mandate.reply_target == {"kind": "thread", "id": created["thread"]["id"]}
    assert await world.store.read(lambda c: mandates.lock_holder(c, doc_id)) == mandate_id
    # Offered to Bob's own jiuwenswarm only.
    assert _runs(world, bob.id) == [mandate_id] and _runs(world, alice.id) == []

    whole = await world.thread(alice, doc_id, body="@jiuwen fix the tone everywhere", mentions=AGENT, scope_switch=True)
    wide = await world.store.read(lambda c: mandates.get(c, whole["comment"]["mandate_id"]))
    assert wide.scope == {"doc_id": doc_id} and wide.status == "queued"
    assert workspace_id


async def test_a_commenters_mention_or_a_pasted_one_starts_nothing(world):
    alice, _, carol, _, doc_id = await _scene(world)
    by_commenter = await world.thread(carol, doc_id, body="@jiuwen shorten this", mentions=AGENT)
    assert by_commenter["comment"]["mandate_id"] is None
    thread = (await world.call(alice, p.COMMENT_LIST, doc_id=doc_id))["threads"][0]
    assert [c["author_kind"] for c in thread["comments"]] == ["person", "system"]
    assert '"agent_forbidden"' in thread["comments"][1]["body"]
    pasted = await world.thread(alice, doc_id, body="@jiuwen shorten this")
    assert pasted["comment"]["mandate_id"] is None
    assert await world.store.read(lambda c: mandates.list_for_workspace(c, thread["workspace_id"])) == []


async def test_comment_tasks_wait_their_turn_and_resolving_drops_a_waiting_one(world):
    alice, bob, _, _, doc_id = await _scene(world)
    first = (await world.thread(alice, doc_id, body="@jiuwen one", mentions=AGENT))["comment"]["mandate_id"]
    second = await world.thread(bob, doc_id, body="@jiuwen two", mentions=AGENT)
    third = (await world.thread(alice, doc_id, body="@jiuwen three", mentions=AGENT))["comment"]["mandate_id"]
    listed = {m["id"]: m for m in (await world.call(alice, p.MANDATE_LIST, workspace_id=second["thread"]["workspace_id"]))["mandates"]}
    assert (listed[second["comment"]["mandate_id"]]["queue_position"], listed[third]["queue_position"]) == (1, 2)

    # Bob resolves his thread while its task waits: it is dropped, and the third goes next.
    await world.call(bob, p.COMMENT_RESOLVE, thread_id=second["thread"]["id"])
    dropped = await world.store.read(lambda c: mandates.get(c, second["comment"]["mandate_id"]))
    assert (dropped.status, dropped.status_reason) == ("cancelled", "already_handled")
    await world.call(alice, p.MANDATE_CANCEL, mandate_id=first)
    started = await world.store.read(lambda c: mandates.get(c, third))
    assert started.status == "running" and await world.store.read(lambda c: mandates.lock_holder(c, doc_id)) == third
    assert _runs(world, alice.id) == [first, third]


async def test_a_full_queue_refuses_more_tasks(world, monkeypatch):
    monkeypatch.setattr(dispatch, "MAX_QUEUE", 2)
    alice, _, _, _, doc_id = await _scene(world)
    for n in range(3):
        await world.thread(alice, doc_id, body=f"@jiuwen task {n}", mentions=AGENT)
    assert (await world.fails(alice, p.COMMENT_CREATE, doc_id=doc_id, anchor=ANCHOR, body="@jiuwen more", mentions=AGENT)).code == "queue_full"


async def test_replies_edits_and_resolution(world):
    alice, bob, carol, _, doc_id = await _scene(world)
    created = await world.thread(carol, doc_id, body="Typo here")
    thread_id, comment_id = created["thread"]["id"], created["comment"]["id"]
    assert (await world.fails(bob, p.COMMENT_EDIT, comment_id=comment_id, body="Not mine")).code == FORBIDDEN
    edited = await world.call(carol, p.COMMENT_EDIT, comment_id=comment_id, body="Typo in the date")
    assert edited["comment"]["body"] == "Typo in the date" and edited["comment"]["edited_at"]

    await world.call(carol, p.COMMENT_RESOLVE, thread_id=thread_id)
    assert (await world.fails(alice, p.COMMENT_REPLY, thread_id=thread_id, body="Late")).code == CONFLICT
    assert (await world.fails(alice, p.COMMENT_RESOLVE, thread_id=thread_id)).code == CONFLICT
    assert (await world.call(alice, p.COMMENT_LIST, doc_id=doc_id))["threads"] == []
    assert len((await world.call(alice, p.COMMENT_LIST, doc_id=doc_id, include_resolved=True))["threads"]) == 1
    await world.call(alice, p.COMMENT_REOPEN, thread_id=thread_id)
    await world.call(alice, p.COMMENT_REPLY, thread_id=thread_id, body="Fixed?")

    tasked = await world.thread(alice, doc_id, body="@jiuwen fix", mentions=AGENT)
    assert (await world.fails(alice, p.COMMENT_EDIT, comment_id=tasked["comment"]["id"], body="changed")).code == CONFLICT


async def test_chat_messages_page_and_mentions_start_workspace_tasks(world):
    alice, bob, carol, workspace_id, _ = await _scene(world)
    for n in range(55):
        await world.call(carol, p.CHAT_POST, workspace_id=workspace_id, body=f"note {n}")
    page = await world.call(alice, p.CHAT_LIST, workspace_id=workspace_id)
    assert page["has_more"] and len(page["messages"]) == 50 and page["messages"][-1]["body"] == "note 54"
    older = await world.call(alice, p.CHAT_LIST, workspace_id=workspace_id, before=page["messages"][0]["id"])
    assert [m["body"] for m in older["messages"]] == [f"note {n}" for n in range(5)] and not older["has_more"]

    asked = (await world.call(bob, p.CHAT_POST, workspace_id=workspace_id, body="@jiuwen add a Risks section", mentions=AGENT))["message"]
    mandate = await world.store.read(lambda c: mandates.get(c, asked["mandate_id"]))
    assert (mandate.origin, mandate.scope, mandate.reply_target, mandate.instruction) == (
        "workspace_chat",
        {},
        {"kind": "chat"},
        "add a Risks section",
    )
    assert _runs(world, bob.id) == [asked["mandate_id"]]

    refused = (await world.call(carol, p.CHAT_POST, workspace_id=workspace_id, body="@jiuwen do it", mentions=AGENT))["message"]
    assert refused["mandate_id"] is None
    last = (await world.call(alice, p.CHAT_LIST, workspace_id=workspace_id))["messages"][-1]
    assert (last["author_kind"], last["kind"]) == ("system", "notice") and '"agent_forbidden"' in last["body"]
    assert (await world.fails(alice, p.CHAT_POST, workspace_id=workspace_id, body="   ")).code == INVALID
