"""Dispatched mandates: claim, report, replies, questions and answers, timeouts, the chat context."""

from __future__ import annotations

import json

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, FORBIDDEN
from jiuwenswarm.extensions.blackboard.host.api import dispatch
from jiuwenswarm.extensions.blackboard.host.store import decisions, mandates

AGENT = [{"kind": "agent"}]


async def _scene(world):
    alice, _ = await world.user("Alice")
    bob, _ = await world.user("Bob")
    carol, _ = await world.user("Carol")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, bob, "editor")
    await world.add(workspace_id, carol, "commenter")
    listed = await world.call(alice, p.DOC_LIST, workspace_id=workspace_id)
    instructions = next(d["id"] for d in listed["docs"] if d["is_instructions"])
    doc_id = await world.doc(alice, workspace_id, title="Plan", markdown="# Plan\n\nShip on Friday.\n")
    return alice, bob, carol, workspace_id, doc_id, instructions


async def _chat_task(world, user, workspace_id, body="@jiuwen add a Risks section"):
    message = (await world.call(user, p.CHAT_POST, workspace_id=workspace_id, body=body, mentions=AGENT))["message"]
    return message["mandate_id"]


async def _mandate(world, mandate_id):
    return await world.store.read(lambda c: mandates.get(c, mandate_id))


def _stops(world, user_id):
    return [payload for event, payload, _, users in world.hub.published if event == p.EV_MANDATE_STOP and users == (user_id,)]


async def _chat(world, user, workspace_id):
    return (await world.call(user, p.CHAT_LIST, workspace_id=workspace_id))["messages"]


async def test_the_requesters_jiuwenswarm_claims_the_turn_with_its_material(world):
    alice, bob, _, workspace_id, doc_id, instructions = await _scene(world)
    world.ctx.docs.docs[instructions] = "Write plainly."
    thread = await world.thread(bob, doc_id, body="@jiuwen shorten this", mentions=AGENT)
    mandate_id = thread["comment"]["mandate_id"]
    assert (await world.call(bob, p.MANDATE_PENDING))["runs"] == [
        {"mandate_id": mandate_id, "workspace_id": workspace_id, "workspace_title": "Launch plan", "session_id": None}
    ]
    assert (await world.fails(alice, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="s1")).code == FORBIDDEN

    claimed = await world.call(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="sess-b")
    prompt = claimed["prompt"]
    assert claimed["turn_id"] and claimed["mandate"]["requester_name"] == "Bob"
    assert (prompt["origin"], prompt["instruction"], prompt["requester"]) == ("comment", "shorten this", "Bob")
    assert prompt["instructions_doc"]["markdown"] == "Write plainly."
    assert prompt["scope"] == {"doc_id": doc_id, "block_from": "b1", "block_to": "b1", "doc_title": "Plan"}
    assert prompt["passage"] == "# Plan\n\nShip on Friday.\n" and prompt["quote"] == "the launch date"
    assert [t["body"] for t in prompt["thread"]] == ["@jiuwen shorten this"]
    assert ("markdown", doc_id, {"view": "accepted", "range": "b1..b1"}) in world.ctx.docs.calls
    mandate = await _mandate(world, mandate_id)
    assert (mandate.session_id, mandate.turn_count) == ("sess-b", 1)
    assert (await world.call(bob, p.MANDATE_PENDING))["runs"] == []
    assert (await world.fails(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="sess-b")).code == CONFLICT


async def test_a_comment_task_replies_in_its_thread_and_the_chat_gets_a_line(world):
    alice, bob, _, workspace_id, doc_id, _ = await _scene(world)
    thread = await world.thread(bob, doc_id, body="@jiuwen shorten this", mentions=AGENT)
    mandate_id = thread["comment"]["mandate_id"]
    turn = (await world.call(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="s"))["turn_id"]
    # A report for another turn is ignored.
    assert (await world.call(bob, p.MANDATE_REPORT, mandate_id=mandate_id, turn_id="turn_old", status="done", text="x"))["ignored"]
    await world.call(bob, p.MANDATE_REPORT, mandate_id=mandate_id, turn_id=turn, status="done", text="Cut it to two sentences.")

    assert (await _mandate(world, mandate_id)).status == "done"
    assert await world.store.read(lambda c: mandates.lock_holder(c, doc_id)) is None
    comments = (await world.call(alice, p.COMMENT_LIST, doc_id=doc_id))["threads"][0]["comments"]
    assert [(c["author_kind"], c["author_name"], c["body"]) for c in comments][-1] == ("agent", "Bob", "Cut it to two sentences.")
    assert comments[0]["mandate_status"] == "done"
    summary = (await _chat(world, alice, workspace_id))[-1]
    assert (summary["kind"], summary["author_kind"]) == ("summary", "agent")
    assert json.loads(summary["body"]) == {
        "code": "thread_reply",
        "doc_id": doc_id,
        "doc_title": "Plan",
        "thread_id": thread["thread"]["id"],
        "excerpt": "Cut it to two sentences.",
    }


async def test_a_chat_task_answers_in_the_chat_and_failures_leave_a_notice(world):
    alice, bob, _, workspace_id, _, _ = await _scene(world)
    first = await _chat_task(world, bob, workspace_id)
    turn = (await world.call(bob, p.MANDATE_CLAIM, mandate_id=first, session_id="s"))["turn_id"]
    await world.call(bob, p.MANDATE_REPORT, mandate_id=first, turn_id=turn, status="done", text="Added the section.")
    reply = (await _chat(world, alice, workspace_id))[-1]
    assert (reply["author_kind"], reply["author_name"], reply["body"], reply["mandate_id"]) == ("agent", "Bob", "Added the section.", first)

    second = await _chat_task(world, bob, workspace_id, "@jiuwen try again")
    turn = (await world.call(bob, p.MANDATE_CLAIM, mandate_id=second, session_id="s"))["turn_id"]
    await world.call(bob, p.MANDATE_REPORT, mandate_id=second, turn_id=turn, status="failed", reason="model unavailable")
    notice = (await _chat(world, alice, workspace_id))[-1]
    assert (notice["kind"], json.loads(notice["body"])) == ("notice", {"code": "agent_failed", "reason": "model unavailable"})


async def test_cancelling_a_running_turn_stops_it_on_the_requesters_machine(world):
    alice, bob, _, workspace_id, doc_id, _ = await _scene(world)
    mandate_id = (await world.thread(bob, doc_id, body="@jiuwen shorten", mentions=AGENT))["comment"]["mandate_id"]
    turn = (await world.call(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="s"))["turn_id"]
    await world.call(alice, p.MANDATE_CANCEL, mandate_id=mandate_id)
    assert _stops(world, bob.id) == [{"mandate_id": mandate_id, "turn_id": turn}]
    late = await world.call(bob, p.MANDATE_REPORT, mandate_id=mandate_id, turn_id=turn, status="done", text="Done anyway")
    assert late == {"mandate_id": mandate_id, "ignored": True, "status": "cancelled"}
    last = (await world.call(alice, p.COMMENT_LIST, doc_id=doc_id))["threads"][0]["comments"][-1]
    assert (last["author_kind"], json.loads(last["body"])) == ("system", {"code": "agent_cancelled", "reason": f"cancelled by {alice.id}", "by": "Alice"})
    assert workspace_id


async def test_a_question_waits_for_an_accepted_answer_and_restarts_the_session(world):
    alice, bob, carol, workspace_id, _, _ = await _scene(world)
    mandate_id = await _chat_task(world, bob, workspace_id)
    turn = (await world.call(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="sess-b"))["turn_id"]
    decision_id = await world.ask(bob, mandate_id)
    assert (await world.fails(bob, p.DECISION_CREATE, mandate_id=mandate_id, question="Another?", options=[{"label": "x"}, {"label": "y"}])).code == "already_asked"
    question = (await _chat(world, alice, workspace_id))[-1]
    assert (question["kind"], question["decision_id"], question["body"]) == ("question", decision_id, "Which risks?")
    await world.call(bob, p.MANDATE_REPORT, mandate_id=mandate_id, turn_id=turn, status="done", text="I asked which risks to cover.")
    assert (await _mandate(world, mandate_id)).status == "waiting_for_answer"
    # The turn's closing text is not posted while the question is open.
    assert (await _chat(world, alice, workspace_id))[-1]["id"] == question["id"]

    # A commenter cannot answer; Alice's answer is a proposal until Bob accepts it.
    assert (await world.fails(carol, p.DECISION_ANSWER, decision_id=decision_id, option=1)).code == FORBIDDEN
    proposed = (await world.call(alice, p.DECISION_ANSWER, decision_id=decision_id, option=1))["decision"]
    assert (proposed["status"], proposed["answer_label"], proposed["answered_by_name"]) == ("proposed", "B", "Alice")
    assert (await _mandate(world, mandate_id)).status == "waiting_for_answer"
    assert (await world.fails(alice, p.DECISION_ACCEPT, decision_id=decision_id)).code == FORBIDDEN
    accepted = (await world.call(bob, p.DECISION_ACCEPT, decision_id=decision_id))["decision"]
    assert (accepted["status"], accepted["accepted_by_name"], accepted["answered_by_name"]) == ("answered", "Bob", "Alice")

    restarted = await _mandate(world, mandate_id)
    assert restarted.status == "running" and restarted.claimed_at is None
    assert (await world.call(bob, p.MANDATE_PENDING))["runs"] == [
        {"mandate_id": mandate_id, "workspace_id": workspace_id, "workspace_title": "Launch plan", "session_id": "sess-b"}
    ]
    again = await world.call(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="sess-b")
    answer = again["prompt"]["answer"]
    assert (answer["chosen"], answer["answered_by"], answer["accepted_by"], answer["question"]) == ("B", "Alice", "Bob", "Which risks?")
    await world.call(bob, p.MANDATE_REPORT, mandate_id=mandate_id, turn_id=again["turn_id"], status="done", text="Added the section.")
    assert (await _mandate(world, mandate_id)).status == "done"
    kinds = [m["kind"] for m in await _chat(world, alice, workspace_id)]
    assert kinds[-3:] == ["answer", "notice", "message"]


async def test_the_requesters_own_answer_or_a_replacement_is_final(world):
    alice, bob, _, workspace_id, _, _ = await _scene(world)
    mandate_id = await _chat_task(world, bob, workspace_id)
    turn = (await world.call(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="s"))["turn_id"]
    decision_id = await world.ask(bob, mandate_id)
    await world.call(bob, p.MANDATE_REPORT, mandate_id=mandate_id, turn_id=turn, status="done", text="")
    await world.call(alice, p.DECISION_ANSWER, decision_id=decision_id, option=0)
    replaced = (await world.call(bob, p.DECISION_ANSWER, decision_id=decision_id, text="Only the legal risk"))["decision"]
    assert (replaced["status"], replaced["answer_label"], replaced["answered_by_name"]) == ("answered", "Only the legal risk", "Bob")
    assert (await _mandate(world, mandate_id)).status == "running"
    assert (await world.fails(alice, p.DECISION_ANSWER, decision_id=decision_id, option=1)).code == CONFLICT


async def test_an_answer_accepted_during_the_turn_starts_the_next_turn_when_it_ends(world):
    _, bob, _, workspace_id, _, _ = await _scene(world)
    mandate_id = await _chat_task(world, bob, workspace_id)
    turn = (await world.call(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="s"))["turn_id"]
    decision_id = await world.ask(bob, mandate_id)
    await world.call(bob, p.DECISION_ANSWER, decision_id=decision_id, option=2)
    assert (await _mandate(world, mandate_id)).status == "running"
    await world.call(bob, p.MANDATE_REPORT, mandate_id=mandate_id, turn_id=turn, status="done", text="Asked.")
    mandate = await _mandate(world, mandate_id)
    assert mandate.status == "running" and mandate.claimed_at is None and mandate.answer["chosen"] == "C"


async def test_cancelling_the_question_or_the_task_ends_both(world):
    alice, bob, _, workspace_id, _, _ = await _scene(world)
    first = await _chat_task(world, bob, workspace_id)
    await world.call(bob, p.MANDATE_CLAIM, mandate_id=first, session_id="s")
    question = await world.ask(bob, first)
    await world.call(alice, p.DECISION_CANCEL, decision_id=question)
    assert (await _mandate(world, first)).status == "cancelled"

    second = await _chat_task(world, bob, workspace_id)
    await world.call(bob, p.MANDATE_CLAIM, mandate_id=second, session_id="s")
    other = await world.ask(bob, second)
    await world.call(bob, p.MANDATE_CANCEL, mandate_id=second)
    assert (await world.store.read(lambda c: decisions.get(c, other))).status == "cancelled"
    assert p.EV_DECISION_UPDATED in world.hub.events()
    listed = (await world.call(alice, p.DECISION_LIST, workspace_id=workspace_id))["decisions"]
    assert {d["status"] for d in listed} == {"cancelled"}


async def test_only_dispatched_running_tasks_may_ask(world):
    alice, bob, _, workspace_id, _, _ = await _scene(world)
    session_mandate = await world.mandate(bob, workspace_id)
    assert (await world.fails(bob, p.DECISION_CREATE, mandate_id=session_mandate, question="Q?", options=[{"label": "a"}, {"label": "b"}])).code == CONFLICT
    chat_mandate = await _chat_task(world, bob, workspace_id)
    assert (await world.fails(alice, p.DECISION_CREATE, mandate_id=chat_mandate, question="Q?", options=[{"label": "a"}, {"label": "b"}])).code == FORBIDDEN
    bad = await world.fails(bob, p.DECISION_CREATE, mandate_id=chat_mandate, question="Q?", options=[{"label": "only one"}])
    assert bad.code == "invalid"


async def test_turns_nobody_picks_up_fail_and_silent_turns_become_unknown(world, monkeypatch):
    alice, bob, _, workspace_id, doc_id, _ = await _scene(world)
    unclaimed = await _chat_task(world, bob, workspace_id)
    silent = (await world.thread(bob, doc_id, body="@jiuwen shorten", mentions=AGENT))["comment"]["mandate_id"]
    await world.call(bob, p.MANDATE_CLAIM, mandate_id=silent, session_id="s")
    monkeypatch.setattr(dispatch, "CLAIM_TIMEOUT_S", -1)
    monkeypatch.setattr(dispatch, "TURN_TIMEOUT_S", -1)
    assert await dispatch.sweep_dispatched(world.ctx) == 2
    assert ((await _mandate(world, unclaimed)).status, (await _mandate(world, unclaimed)).status_reason) == ("failed", "not_picked_up")
    assert (await _mandate(world, silent)).status == "unknown"
    assert await world.store.read(lambda c: mandates.lock_holder(c, doc_id)) is None
    notices = [json.loads(m["body"])["code"] for m in await _chat(world, alice, workspace_id) if m["kind"] == "notice"]
    assert notices == ["agent_failed", "agent_unknown"]

    assert (await world.fails(bob, p.MANDATE_RESOLVE_UNKNOWN, mandate_id=unclaimed, status="done")).code == CONFLICT
    resolved = await world.call(alice, p.MANDATE_RESOLVE_UNKNOWN, mandate_id=silent, status="done")
    assert (resolved["mandate"]["status"], resolved["mandate"]["status_reason"]) == ("done", f"resolved by {alice.id}")


async def test_a_requester_who_is_no_longer_an_editor_cannot_start_the_turn(world):
    alice, bob, _, workspace_id, _, _ = await _scene(world)
    mandate_id = await _chat_task(world, bob, workspace_id)
    await world.call(alice, p.MEMBER_SET_ROLE, workspace_id=workspace_id, user_id=bob.id, role="commenter")
    assert (await world.fails(bob, p.MANDATE_CLAIM, mandate_id=mandate_id, session_id="s")).code == FORBIDDEN
    mandate = await _mandate(world, mandate_id)
    assert (mandate.status, mandate.status_reason) == ("failed", "not_an_editor")


async def test_the_chat_context_is_what_people_said_since_the_agents_last_turn(world, monkeypatch):
    monkeypatch.setattr(dispatch, "CHAT_CONTEXT_MESSAGES", 3)
    alice, bob, carol, workspace_id, _, _ = await _scene(world)
    for body in ("one", "two", "three", "four"):
        await world.call(carol, p.CHAT_POST, workspace_id=workspace_id, body=body)
    await world.call(carol, p.CHAT_POST, workspace_id=workspace_id, body="@jiuwen me too", mentions=AGENT)
    first = await _chat_task(world, bob, workspace_id)
    prompt = (await world.call(bob, p.MANDATE_CLAIM, mandate_id=first, session_id="s"))["prompt"]
    # The newest three, oldest first; the refused mention, the task itself and the notice are left out.
    assert prompt["chat"] == ["Carol: two", "Carol: three", "Carol: four"]

    await world.call(alice, p.CHAT_POST, workspace_id=workspace_id, body="five")
    second = await _chat_task(world, bob, workspace_id, "@jiuwen and now")
    assert (await world.call(bob, p.MANDATE_CLAIM, mandate_id=second, session_id="s"))["prompt"]["chat"] == ["Alice: five"]

    monkeypatch.setattr(dispatch, "CHAT_CONTEXT_CHARS", 12)
    for body in ("aaaa", "bbbbbbbbbb"):
        await world.call(alice, p.CHAT_POST, workspace_id=workspace_id, body=body)
    third = await _chat_task(world, bob, workspace_id, "@jiuwen last")
    assert (await world.call(bob, p.MANDATE_CLAIM, mandate_id=third, session_id="s"))["prompt"]["chat"] == []

async def test_a_long_selection_stays_out_of_the_prompt(world):
    _, bob, _, _, doc_id, _ = await _scene(world)
    long = "Ship on Friday. " * 200
    thread = await world.thread(bob, doc_id, body="@jiuwen shorten this", mentions=AGENT, anchor={"quote": long, "length": len(long)})
    claimed = await world.call(bob, p.MANDATE_CLAIM, mandate_id=thread["comment"]["mandate_id"], session_id="sess-b")
    assert "quote" not in claimed["prompt"] and claimed["prompt"]["passage"]
