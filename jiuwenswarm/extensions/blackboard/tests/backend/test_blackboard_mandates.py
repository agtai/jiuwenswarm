"""Mandates: the state machine, the session-turn rule, receipts, document locks and the sweeper."""

from __future__ import annotations

import asyncio
import itertools

import pytest

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import BUSY, CONFLICT, FORBIDDEN, BlackboardError
from jiuwenswarm.extensions.blackboard.host.api import mandates as api
from jiuwenswarm.extensions.blackboard.host.store import mandates


async def _scene(world):
    alice, _ = await world.user("Alice")
    bob, _ = await world.user("Bob")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, bob, "editor")
    doc_id = await world.doc(alice, workspace_id)
    return alice, bob, workspace_id, doc_id


def _ops(block: str = "b1") -> list[dict]:
    return [{"op": "replace", "block_id": block, "digest": "d0", "markdown": "New text."}]


async def test_every_transition_is_allowed_or_refused_as_the_table_says(world):
    alice, _, workspace_id, _ = await _scene(world)
    statuses = list(mandates.TRANSITIONS)
    for start, target in itertools.product(statuses, statuses):
        mandate_id = await world.mandate(alice, workspace_id, status=start)
        allowed = target in mandates.TRANSITIONS[start]
        try:
            await world.store.transact(lambda c: mandates.set_status(c, mandate_id, target))
        except BlackboardError as exc:
            assert not allowed, (start, target)
            assert exc.code == CONFLICT
        else:
            assert allowed, (start, target)


async def test_an_edit_begins_a_session_mandate_and_leaves_a_receipt(world):
    alice, _, workspace_id, doc_id = await _scene(world)
    result = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), note="Tighten the intro", session_id="s1", turn_id="t1")
    assert result["suggestion_ids"] and result["blocks_after"] == [{"id": "b1", "digest": "d1"}]
    listed = (await world.call(alice, p.MANDATE_LIST, workspace_id=workspace_id))["mandates"]
    assert len(listed) == 1
    mandate = listed[0]
    assert (mandate["origin"], mandate["status"], mandate["instruction"]) == ("workspace_session", "running", "Tighten the intro")
    receipt = mandate["receipts"][0]
    assert receipt["status"] == "applied" and receipt["before"][0]["markdown"] == "old" and receipt["suggestion_ids"]
    assert await world.store.read(lambda c: mandates.lock_holder(c, doc_id)) == mandate["id"]
    # The agent's author is the requester as an agent, under the mandate.
    _, body = world.ctx.docs.named("edits")[0]
    assert body["author"] == {"id": alice.id, "kind": "agent"} and body["mandateId"] == mandate["id"]
    assert p.EV_SUGGESTIONS_CHANGED in world.hub.events() and p.EV_MANDATE_UPDATED in world.hub.events()


async def test_the_same_turn_reuses_its_mandate_and_the_next_turn_ends_it(world):
    alice, _, workspace_id, doc_id = await _scene(world)
    first = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t1")
    again = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops("b2"), session_id="s1", turn_id="t1")
    assert again["mandate_id"] == first["mandate_id"]
    later = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t2")
    assert later["mandate_id"] != first["mandate_id"]
    old = await world.store.read(lambda c: mandates.get(c, first["mandate_id"]))
    assert (old.status, old.status_reason) == ("done", "next_turn")
    assert await world.store.read(lambda c: mandates.lock_holder(c, doc_id)) == later["mandate_id"]


async def test_one_turn_in_two_workspaces_runs_one_mandate_in_each(world):
    alice, _, workspace_id, doc_id = await _scene(world)
    other_doc = await world.doc(alice, await world.workspace(alice, name="other"))
    first = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t1")
    second = await world.call(alice, p.EDIT, doc_id=other_doc, ops=_ops(), session_id="s1", turn_id="t1")
    assert second["mandate_id"] != first["mandate_id"]
    assert (await world.store.read(lambda c: mandates.get(c, first["mandate_id"]))).status == "running"
    # Stopping one run leaves the other workspace's edits alone.
    await world.call(alice, p.MANDATE_CANCEL, mandate_id=first["mandate_id"])
    assert (await world.fails(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t1")).code == "no_mandate"
    again = await world.call(alice, p.EDIT, doc_id=other_doc, ops=_ops(), session_id="s1", turn_id="t1")
    assert again["mandate_id"] == second["mandate_id"]


async def test_a_refused_batch_is_an_aborted_receipt_and_the_error_reaches_the_agent(world):
    alice, _, workspace_id, doc_id = await _scene(world)
    world.ctx.docs.edit_error = BlackboardError("stale", "changed", {"changed_blocks": [{"id": "b1"}]})
    error = await world.fails(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t1")
    assert error.code == "stale" and error.details["changed_blocks"] == [{"id": "b1"}] and error.details["receipt_id"]
    receipt = (await world.call(alice, p.MANDATE_LIST, workspace_id=workspace_id))["mandates"][0]["receipts"][0]
    assert receipt["status"] == "aborted" and receipt["error"]["code"] == "stale"


async def test_who_may_edit(world):
    alice, bob, workspace_id, doc_id = await _scene(world)
    carol, _ = await world.user("Carol")
    await world.add(workspace_id, carol, "viewer")
    assert (await world.fails(carol, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s3")).code == FORBIDDEN
    theirs = await world.mandate(alice, workspace_id)
    assert (await world.fails(bob, p.EDIT, doc_id=doc_id, ops=_ops(), mandate_id=theirs)).code == "no_mandate"
    other_doc = await world.doc(alice, workspace_id, "Other")
    scoped = await world.mandate(alice, workspace_id, scope={"doc_id": other_doc})
    assert (await world.fails(alice, p.EDIT, doc_id=doc_id, ops=_ops(), mandate_id=scoped)).code == "out_of_scope"
    await world.call(alice, p.DOC_ARCHIVE, doc_id=other_doc)
    assert (await world.fails(alice, p.EDIT, doc_id=other_doc, ops=_ops(), session_id="s1")).code == CONFLICT


async def test_a_second_agent_waits_for_the_lock_and_then_hears_busy(world, monkeypatch):
    monkeypatch.setattr(api, "LOCK_WAIT_S", 0.3)
    alice, bob, workspace_id, doc_id = await _scene(world)
    first = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t1")
    error = await world.fails(bob, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s2", turn_id="t1")
    assert error.code == BUSY and error.details["queue_position"] == 1
    # Importing over an agent's edits is refused too.
    assert (await world.fails(alice, p.DOC_IMPORT_MARKDOWN, doc_id=doc_id, markdown="# New\n")).code == BUSY

    # While Bob waits, Alice's mandate is cancelled; Bob gets the document.
    monkeypatch.setattr(api, "LOCK_WAIT_S", 5.0)
    waiting = asyncio.create_task(world.call(bob, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s2", turn_id="t2"))
    await asyncio.sleep(0.1)
    assert not waiting.done()
    await world.call(bob, p.MANDATE_CANCEL, mandate_id=first["mandate_id"])
    result = await asyncio.wait_for(waiting, 5)
    assert await world.store.read(lambda c: mandates.lock_holder(c, doc_id)) == result["mandate_id"]
    assert any(body.get("status") is None for _, body in world.ctx.docs.named("presence"))


async def test_waiters_take_the_lock_in_order(world, monkeypatch):
    monkeypatch.setattr(api, "LOCK_WAIT_S", 5.0)
    alice, _, workspace_id, doc_id = await _scene(world)
    users = []
    for i in range(4):
        user, _ = await world.user(f"Agent owner {i}")
        await world.add(workspace_id, user, "editor")
        users.append(user)
    holder = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s0", turn_id="t")
    order: list[int] = []

    async def edit(i: int) -> None:
        result = await world.call(users[i], p.EDIT, doc_id=doc_id, ops=_ops(), session_id=f"s{i + 1}", turn_id="t")
        order.append(i)
        await api.finish_mandate(world.ctx, result["mandate_id"], "done")

    tasks = []
    for i in range(4):
        tasks.append(asyncio.create_task(edit(i)))
        await asyncio.sleep(0.05)
    await api.finish_mandate(world.ctx, holder["mandate_id"], "done")
    await asyncio.wait_for(asyncio.gather(*tasks), 10)
    assert order == [0, 1, 2, 3]


async def test_idle_session_mandates_end_and_let_go(world):
    alice, _, workspace_id, doc_id = await _scene(world)
    result = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t1")
    await world.sql("UPDATE mandates SET last_activity_at = '2000-01-01T00:00:00.000+00:00'")
    assert await api.sweep_idle_mandates(world.ctx) == 1
    mandate = await world.store.read(lambda c: mandates.get(c, result["mandate_id"]))
    assert (mandate.status, mandate.status_reason) == ("done", "idle")
    assert await world.store.read(lambda c: mandates.lock_holder(c, doc_id)) is None


async def test_cancel_and_decide(world):
    alice, bob, workspace_id, doc_id = await _scene(world)
    result = await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t1")
    listed = await world.call(bob, p.SUGGESTION_LIST, doc_id=doc_id)
    assert [s["id"] for s in listed["suggestions"]] == result["suggestion_ids"]
    run = (await world.call(bob, p.MANDATE_LIST, workspace_id=workspace_id))["mandates"][0]
    assert run["pending"] == {doc_id: result["suggestion_ids"]}
    decided = await world.call(bob, p.SUGGESTION_DECIDE, doc_id=doc_id, suggestion_ids=[*result["suggestion_ids"], "s_gone"], action="accept")
    assert decided["decided"] == result["suggestion_ids"] and decided["missing"] == ["s_gone"]
    assert (await world.call(bob, p.MANDATE_LIST, workspace_id=workspace_id))["mandates"][0]["pending"] == {}

    # Alice cancels her own mandate; a finished mandate cannot be cancelled again.
    await world.call(alice, p.MANDATE_CANCEL, mandate_id=result["mandate_id"])
    assert (await world.fails(alice, p.MANDATE_CANCEL, mandate_id=result["mandate_id"])).code == CONFLICT
    later = await world.fails(alice, p.EDIT, doc_id=doc_id, ops=_ops(), mandate_id=result["mandate_id"])
    assert later.code == "no_mandate"
    # The stopped turn cannot start another mandate; the next turn can.
    same_turn = await world.fails(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t1")
    assert same_turn.code == "no_mandate" and same_turn.details["mandate_id"] == result["mandate_id"]
    assert (await world.call(alice, p.EDIT, doc_id=doc_id, ops=_ops(), session_id="s1", turn_id="t2"))["mandate_id"] != result["mandate_id"]


@pytest.mark.parametrize("bad", [[], "x", [{"op": "replace"}] * 51])
async def test_malformed_ops_are_invalid(world, bad):
    alice, _, _, doc_id = await _scene(world)
    assert (await world.fails(alice, p.EDIT, doc_id=doc_id, ops=bad, session_id="s1")).code == "invalid"
