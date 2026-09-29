"""Every workspace method against every role, called the way the RPC endpoint calls it."""

from __future__ import annotations

import pytest

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import FORBIDDEN, NOT_FOUND, NOT_MEMBER
from jiuwenswarm.extensions.blackboard.common.roles import ROLES, role_at_least
from jiuwenswarm.extensions.blackboard.host.store import mandates
from jiuwenswarm.extensions.blackboard.tests.backend.support import ANCHOR

# method -> (lowest role allowed, extra params). "<carol>", "<code>", "<doc>" and "<ref>" are filled
# in per case.
WORKSPACE_METHODS = {
    p.MEMBER_LIST: ("viewer", {}),
    p.WORKSPACE_RENAME: ("owner", {"title": "Renamed"}),
    p.WORKSPACE_ARCHIVE: ("owner", {}),
    p.WORKSPACE_UNARCHIVE: ("owner", {}),
    p.WORKSPACE_DELETE: ("owner", {}),
    p.MEMBER_SET_ROLE: ("owner", {"user_id": "<carol>", "role": "viewer"}),
    p.MEMBER_REMOVE: ("owner", {"user_id": "<carol>"}),
    p.INVITE_CREATE: ("owner", {"role": "viewer"}),
    p.INVITE_LIST: ("owner", {}),
    p.INVITE_REVOKE: ("owner", {"code": "<code>"}),
    p.DOC_LIST: ("viewer", {}),
    p.DOC_CREATE: ("editor", {"title": "Plan"}),
    p.DOC_RENAME: ("editor", {"doc_id": "<doc>", "title": "Renamed"}),
    p.DOC_ARCHIVE: ("editor", {"doc_id": "<doc>"}),
    p.DOC_SET_INSTRUCTIONS: ("editor", {"doc_id": "<doc>"}),
    p.DOC_PIN: ("editor", {"doc_id": "<doc>", "pinned": True}),
    p.DOC_IMPORT_MARKDOWN: ("editor", {"doc_id": "<doc>", "markdown": "# Plan"}),
    p.DOC_TOKEN: ("viewer", {"doc_id": "<doc>"}),
    p.DOC_READ: ("viewer", {"doc_id": "<doc>"}),
    p.REFERENCE_LIST: ("viewer", {}),
    p.REFERENCE_URL: ("viewer", {"reference_id": "<ref>"}),
    p.REFERENCE_REMOVE: ("editor", {"reference_id": "<ref>"}),
    p.REFERENCE_SET_NOTE: ("editor", {"reference_id": "<ref>", "note": "Read first"}),
    p.MANDATE_LIST: ("viewer", {}),
    # Someone else's mandate; its own requester may always cancel it.
    p.MANDATE_CANCEL: ("editor", {"mandate_id": "<mandate>"}),
    p.SUGGESTION_LIST: ("viewer", {"doc_id": "<doc>"}),
    p.SUGGESTION_DECIDE: ("editor", {"doc_id": "<doc>", "suggestion_ids": ["s_x"], "action": "reject"}),
    p.COMMENT_CREATE: ("commenter", {"doc_id": "<doc>", "anchor": ANCHOR, "body": "Nice"}),
    p.COMMENT_REPLY: ("commenter", {"thread_id": "<thread>", "body": "Agreed"}),
    p.COMMENT_RESOLVE: ("commenter", {"thread_id": "<thread>"}),
    p.COMMENT_REOPEN: ("commenter", {"thread_id": "<resolved_thread>"}),
    p.COMMENT_LIST: ("viewer", {"doc_id": "<doc>"}),
    p.CHAT_POST: ("commenter", {"body": "Hello"}),
    p.CHAT_LIST: ("viewer", {}),
    p.DECISION_LIST: ("viewer", {}),
    p.DECISION_GET: ("viewer", {"decision_id": "<decision>"}),
    # Someone else's question: any editor may propose an answer or withdraw it.
    p.DECISION_ANSWER: ("editor", {"decision_id": "<decision>", "option": 0}),
    p.DECISION_CANCEL: ("editor", {"decision_id": "<decision>"}),
    p.MANDATE_RESOLVE_UNKNOWN: ("editor", {"mandate_id": "<unknown_mandate>", "status": "done"}),
    p.HISTORY_LIST: ("viewer", {"doc_id": "<doc>"}),
    p.HISTORY_GET: ("viewer", {"doc_id": "<doc>", "version_id": "<version>"}),
    p.HISTORY_DIFF: ("viewer", {"doc_id": "<doc>", "to": "<version>"}),
    p.HISTORY_SAVE: ("editor", {"doc_id": "<doc>", "label": "Checkpoint"}),
    p.HISTORY_RESTORE: ("editor", {"doc_id": "<doc>", "version_id": "<version>"}),
    p.DOC_EXPORT: ("viewer", {"doc_id": "<doc>", "format": "md"}),
}

# Only a comment's author edits it and only a task's requester accepts an answer; their own tests
# (test_blackboard_conversation.py, test_blackboard_dispatch.py) cover them.
PERSONAL_METHODS = {p.COMMENT_EDIT, p.DECISION_ACCEPT}


def test_the_table_covers_every_workspace_method():
    no_workspace = {p.ME, p.ME_SET_NAME, p.WORKSPACE_LIST, p.WORKSPACE_CREATE}
    assert set(WORKSPACE_METHODS) | PERSONAL_METHODS == set(p.HOST_METHODS) - no_workspace


async def _scene(world, role: str | None):
    alice, _ = await world.user("Alice")
    bob, _ = await world.user("Bob")
    carol, _ = await world.user("Carol")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, carol, "editor")
    if role is not None:
        await world.add(workspace_id, bob, role)
    code = await world.invite(alice, workspace_id)
    doc_id = await world.doc(alice, workspace_id)
    resolved = (await world.thread(alice, doc_id))["thread"]["id"]
    await world.call(alice, p.COMMENT_RESOLVE, thread_id=resolved)
    asking = await world.mandate(alice, workspace_id, origin="workspace_chat", origin_ref={}, reply_target={"kind": "chat"})
    unknown = await world.mandate(alice, workspace_id)
    await world.store.transact(lambda c: mandates.set_status(c, unknown, "unknown"))
    fill = {
        "<carol>": carol.id,
        "<code>": code,
        "<doc>": doc_id,
        "<ref>": await world.reference(alice, workspace_id),
        "<mandate>": await world.mandate(alice, workspace_id),
        "<thread>": (await world.thread(alice, doc_id))["thread"]["id"],
        "<resolved_thread>": resolved,
        "<decision>": await world.ask(alice, asking),
        "<unknown_mandate>": unknown,
        "<version>": world.ctx.docs.add_version(doc_id, "created", [{"id": alice.id, "kind": "person"}])["id"],
    }
    return alice, bob, carol, workspace_id, fill


def _params(extra: dict, workspace_id: str, fill: dict) -> dict:
    return {"workspace_id": workspace_id, **{k: fill.get(v, v) if isinstance(v, str) else v for k, v in extra.items()}}


def test_agent_methods_are_not_offered_to_browsers():
    assert not set(p.AGENT_METHODS) & set(p.HOST_METHODS)


@pytest.mark.parametrize("role", [*ROLES, None])
@pytest.mark.parametrize("method", sorted(WORKSPACE_METHODS))
async def test_role_matrix(world, method, role):
    minimum, extra = WORKSPACE_METHODS[method]
    alice, bob, carol, workspace_id, fill = await _scene(world, role)
    if method == p.WORKSPACE_DELETE:
        await world.call(alice, p.WORKSPACE_ARCHIVE, workspace_id=workspace_id)
    params = _params(extra, workspace_id, fill)

    if role is None:
        assert (await world.fails(bob, method, **params)).code == NOT_MEMBER
    elif role_at_least(role, minimum):
        await world.call(bob, method, **params)
    else:
        error = await world.fails(bob, method, **params)
        assert error.code == FORBIDDEN
        assert error.details == {"workspace_id": workspace_id, "required": minimum, "role": role}


@pytest.mark.parametrize("role", ["viewer", "commenter", "editor"])
async def test_anyone_may_leave(world, role):
    _, bob, _, workspace_id, _ = await _scene(world, role)
    result = await world.call(bob, p.MEMBER_REMOVE, workspace_id=workspace_id, user_id=bob.id)
    assert result["removed"] is True
    assert (await world.fails(bob, p.MEMBER_LIST, workspace_id=workspace_id)).code == NOT_MEMBER


@pytest.mark.parametrize("method", sorted(WORKSPACE_METHODS))
async def test_an_unknown_workspace_is_not_found(world, method):
    alice, _ = await world.user("Alice")
    _, extra = WORKSPACE_METHODS[method]
    missing = {
        "<carol>": "u_missing",
        "<code>": "c" * 20,
        "<doc>": "d_missing",
        "<ref>": "r_missing",
        "<mandate>": "m_missing",
        "<thread>": "t_missing",
        "<resolved_thread>": "t_missing",
        "<decision>": "dc_missing",
        "<unknown_mandate>": "m_missing",
        "<version>": "v_missing",
    }
    params = _params(extra, "ws_missing", missing)
    assert (await world.fails(alice, method, **params)).code == NOT_FOUND


async def test_methods_without_a_workspace_work_for_any_user(world):
    bob, _ = await world.user("Bob")
    me = await world.call(bob, p.ME)
    assert me["user_id"] == bob.id and me["workspaces"] == [] and me["is_operator"] is False
    assert me["host"]["host_uid"] == world.ctx.host_uid
    assert (await world.call(bob, p.WORKSPACE_LIST))["workspaces"] == []
    created = await world.call(bob, p.WORKSPACE_CREATE, name="bobs-notes", title="Notes")
    assert created["workspace"]["role"] == "owner"
    assert (await world.call(bob, p.ME_SET_NAME, display_name="  Robert   B  "))["display_name"] == "Robert B"
