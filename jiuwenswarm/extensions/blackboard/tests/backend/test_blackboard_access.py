"""Every workspace method against every role, called the way the RPC endpoint calls it."""

from __future__ import annotations

import pytest

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import FORBIDDEN, NOT_FOUND, NOT_MEMBER
from jiuwenswarm.extensions.blackboard.common.roles import ROLES, role_at_least

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
}


def test_the_table_covers_every_workspace_method():
    no_workspace = {p.ME, p.ME_SET_NAME, p.WORKSPACE_LIST, p.WORKSPACE_CREATE}
    assert set(WORKSPACE_METHODS) == set(p.HOST_METHODS) - no_workspace


async def _scene(world, role: str | None):
    alice, _ = await world.user("Alice")
    bob, _ = await world.user("Bob")
    carol, _ = await world.user("Carol")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, carol, "editor")
    if role is not None:
        await world.add(workspace_id, bob, role)
    code = await world.invite(alice, workspace_id)
    fill = {
        "<carol>": carol.id,
        "<code>": code,
        "<doc>": await world.doc(alice, workspace_id),
        "<ref>": await world.reference(alice, workspace_id),
    }
    return alice, bob, carol, workspace_id, fill


def _params(extra: dict, workspace_id: str, fill: dict) -> dict:
    return {"workspace_id": workspace_id, **{k: fill.get(v, v) if isinstance(v, str) else v for k, v in extra.items()}}


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
    missing = {"<carol>": "u_missing", "<code>": "c" * 20, "<doc>": "d_missing", "<ref>": "r_missing"}
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
