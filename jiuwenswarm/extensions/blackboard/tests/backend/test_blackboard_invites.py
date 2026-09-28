"""Invites, joining, ownership rules, and who each change is pushed to."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import (
    CONFLICT,
    DISABLED,
    EXPIRED,
    INVALID,
    NOT_FOUND,
    BlackboardError,
)
from jiuwenswarm.extensions.blackboard.host.store import users


async def _owner_and_workspace(world):
    alice, _ = await world.user("Alice", operator=True)
    return alice, await world.workspace(alice)


async def test_a_new_person_joins_and_gets_a_member_token(world):
    alice, workspace_id = await _owner_and_workspace(world)
    code = await world.invite(alice, workspace_id, role="commenter", max_uses=2)
    world.hub.published.clear()

    result = await world.call(None, p.INVITE_ACCEPT, code=code, display_name="Bob")

    assert result["joined"] is True
    assert result["workspace"]["id"] == workspace_id and result["workspace"]["role"] == "commenter"
    assert result["token"].startswith("bbm_")
    assert result["host"]["name"] == "Alice's Blackboard"
    bob = await world.ctx.authenticate(result["token"])
    assert bob.id == result["user_id"] and bob.display_name == "Bob"
    assert (await world.invite_row(code)).uses == 1
    assert world.hub.published == [
        (p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id, ()),
        (p.EV_ME_UPDATED, {}, None, (bob.id,)),
    ]


async def test_a_new_person_needs_a_display_name(world):
    alice, workspace_id = await _owner_and_workspace(world)
    code = await world.invite(alice, workspace_id)
    error = await world.fails(None, p.INVITE_ACCEPT, code=code)
    assert error.code == INVALID and error.details == {"field": "display_name"}
    assert (await world.invite_row(code)).uses == 0


async def test_a_used_up_link_still_returns_the_workspace_to_its_members(world):
    alice, workspace_id = await _owner_and_workspace(world)
    code = await world.invite(alice, workspace_id, max_uses=1)
    first = await world.call(None, p.INVITE_ACCEPT, code=code, display_name="Bob")
    world.hub.published.clear()

    again = await world.call(None, p.INVITE_ACCEPT, code=code, token=first["token"])
    assert again["joined"] is False and "token" not in again
    assert again["workspace"]["role"] == "editor"
    assert world.hub.published == []

    error = await world.fails(None, p.INVITE_ACCEPT, code=code, display_name="Carol")
    assert error.code == EXPIRED and error.details == {"state": "used_up"}


async def test_a_known_user_joins_another_workspace_without_a_new_token(world):
    alice, workspace_id = await _owner_and_workspace(world)
    bob, bob_token = await world.user("Bob")
    code = await world.invite(alice, workspace_id, role="viewer")
    result = await world.call(None, p.INVITE_ACCEPT, code=code, token=bob_token, display_name="ignored")
    assert result["joined"] is True and result["user_id"] == bob.id and "token" not in result
    assert result["display_name"] == "Bob"


@pytest.mark.parametrize("state", ["revoked", "expired", "archived"])
async def test_links_that_cannot_be_used(world, state):
    alice, workspace_id = await _owner_and_workspace(world)
    code = await world.invite(alice, workspace_id)
    if state == "revoked":
        await world.call(alice, p.INVITE_REVOKE, workspace_id=workspace_id, code=code)
    elif state == "expired":
        await world.sql("UPDATE invites SET expires_at = '2000-01-01T00:00:00.000Z' WHERE code = ?", code)
    else:
        await world.call(alice, p.WORKSPACE_ARCHIVE, workspace_id=workspace_id)
    error = await world.fails(None, p.INVITE_ACCEPT, code=code, display_name="Bob")
    assert error.code == EXPIRED and error.details == {"state": state}


async def test_an_unknown_code_or_a_disabled_user_is_refused(world):
    alice, workspace_id = await _owner_and_workspace(world)
    assert (await world.fails(None, p.INVITE_ACCEPT, code="a" * 20, display_name="Bob")).code == NOT_FOUND

    bob, bob_token = await world.user("Bob")
    await world.store.transact(lambda c: users.set_status(c, bob.id, "disabled"))
    code = await world.invite(alice, workspace_id)
    assert (await world.fails(None, p.INVITE_ACCEPT, code=code, token=bob_token)).code == DISABLED
    with pytest.raises(BlackboardError) as caught:
        await world.ctx.authenticate(bob_token)
    assert caught.value.code == DISABLED


@pytest.mark.parametrize(
    "params,field",
    [
        ({"role": "owner"}, "role"),
        ({"role": "admin"}, "role"),
        ({"expires_in_minutes": 0}, "expires_in_minutes"),
        ({"expires_in_minutes": 30 * 24 * 60 + 1}, "expires_in_minutes"),
        ({"expires_in_minutes": True}, "expires_in_minutes"),
        ({"max_uses": 0}, "max_uses"),
        ({"max_uses": 101}, "max_uses"),
        ({"max_uses": "many"}, "max_uses"),
    ],
)
async def test_invite_limits(world, params, field):
    alice, workspace_id = await _owner_and_workspace(world)
    values = {"role": "editor", **params}
    error = await world.fails(alice, p.INVITE_CREATE, workspace_id=workspace_id, **values)
    assert error.code == INVALID and error.details["field"] == field


async def test_invite_defaults_and_open_links(world):
    alice, workspace_id = await _owner_and_workspace(world)

    default = (await world.call(alice, p.INVITE_CREATE, workspace_id=workspace_id, role="editor"))["invite"]
    created = datetime.fromisoformat(default["created_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(default["expires_at"].replace("Z", "+00:00"))
    assert abs((expires - created) - timedelta(days=7)) < timedelta(seconds=5)
    assert default["max_uses"] is None

    short = (await world.call(alice, p.INVITE_CREATE, workspace_id=workspace_id, role="editor", expires_in_minutes=30))["invite"]
    created = datetime.fromisoformat(short["created_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(short["expires_at"].replace("Z", "+00:00"))
    assert abs((expires - created) - timedelta(minutes=30)) < timedelta(seconds=5)

    # Never expires and no limit: people keep joining until an owner revokes it.
    forever = await world.call(
        alice, p.INVITE_CREATE, workspace_id=workspace_id, role="viewer", expires_in_minutes=None, max_uses=None
    )
    assert (forever["invite"]["expires_at"], forever["invite"]["max_uses"]) == (None, None)
    code = forever["invite"]["code"]
    for name in ("Bob", "Carol", "Dave"):
        assert (await world.call(None, p.INVITE_ACCEPT, code=code, display_name=name))["joined"] is True
    assert (await world.invite_row(code)).state("2999-01-01T00:00:00.000Z") == "active"


async def test_invites_list_their_state_and_link(world):
    alice, workspace_id = await _owner_and_workspace(world)
    created = await world.call(alice, p.INVITE_CREATE, workspace_id=workspace_id, role="viewer", max_uses=3)
    assert created["url"] == f"http://127.0.0.1:19999/blackboard/join/{created['invite']['code']}"
    revoked = await world.invite(alice, workspace_id)
    await world.call(alice, p.INVITE_REVOKE, workspace_id=workspace_id, code=revoked)

    listed = await world.call(alice, p.INVITE_LIST, workspace_id=workspace_id)
    states = {i["code"]: i["state"] for i in listed["invites"]}
    assert states == {created["invite"]["code"]: "active", revoked: "revoked"}
    assert all(i["url"].endswith(i["code"]) for i in listed["invites"])


async def test_an_invite_is_revoked_only_in_its_own_workspace(world):
    alice, workspace_id = await _owner_and_workspace(world)
    other = await world.workspace(alice, name="other", title="Other")
    code = await world.invite(alice, other)
    error = await world.fails(alice, p.INVITE_REVOKE, workspace_id=workspace_id, code=code)
    assert error.code == NOT_FOUND
    assert (await world.invite_row(code)).revoked_at is None


async def test_a_workspace_keeps_at_least_one_owner(world):
    alice, workspace_id = await _owner_and_workspace(world)
    for method, params in [
        (p.MEMBER_SET_ROLE, {"user_id": alice.id, "role": "editor"}),
        (p.MEMBER_REMOVE, {"user_id": alice.id}),
    ]:
        assert (await world.fails(alice, method, workspace_id=workspace_id, **params)).code == CONFLICT

    bob, _ = await world.user("Bob")
    await world.add(workspace_id, bob, "owner")
    await world.call(alice, p.MEMBER_SET_ROLE, workspace_id=workspace_id, user_id=alice.id, role="editor")
    assert (await world.fails(bob, p.MEMBER_REMOVE, workspace_id=workspace_id, user_id=bob.id)).code == CONFLICT


async def test_setting_the_same_role_changes_nothing(world):
    alice, workspace_id = await _owner_and_workspace(world)
    bob, _ = await world.user("Bob")
    await world.add(workspace_id, bob, "editor")
    world.hub.published.clear()
    result = await world.call(alice, p.MEMBER_SET_ROLE, workspace_id=workspace_id, user_id=bob.id, role="editor")
    assert result["changed"] is False and world.hub.published == []


async def test_an_archived_workspace_takes_no_new_members_or_roles(world):
    alice, workspace_id = await _owner_and_workspace(world)
    bob, _ = await world.user("Bob")
    await world.add(workspace_id, bob, "editor")
    await world.call(alice, p.WORKSPACE_ARCHIVE, workspace_id=workspace_id)
    assert (await world.fails(alice, p.INVITE_CREATE, workspace_id=workspace_id, role="viewer")).code == CONFLICT
    error = await world.fails(alice, p.MEMBER_SET_ROLE, workspace_id=workspace_id, user_id=bob.id, role="viewer")
    assert error.code == CONFLICT
    await world.call(alice, p.WORKSPACE_UNARCHIVE, workspace_id=workspace_id)
    await world.call(alice, p.MEMBER_SET_ROLE, workspace_id=workspace_id, user_id=bob.id, role="viewer")


async def test_delete_needs_an_archived_workspace_and_tells_every_member(world):
    alice, workspace_id = await _owner_and_workspace(world)
    bob, _ = await world.user("Bob")
    await world.add(workspace_id, bob, "viewer")
    code = await world.invite(alice, workspace_id)
    assert (await world.fails(alice, p.WORKSPACE_DELETE, workspace_id=workspace_id)).code == CONFLICT

    await world.call(alice, p.WORKSPACE_ARCHIVE, workspace_id=workspace_id)
    world.hub.published.clear()
    await world.call(alice, p.WORKSPACE_DELETE, workspace_id=workspace_id)
    (event, payload, scope, targets), = world.hub.published
    assert (event, payload, scope) == (p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id, "deleted": True}, None)
    assert set(targets) == {alice.id, bob.id}
    assert await world.invite_row(code) is None
    assert (await world.call(bob, p.WORKSPACE_LIST))["workspaces"] == []


async def test_workspace_names_are_checked_and_unique(world):
    alice, _ = await _owner_and_workspace(world)
    for name in ["ab", "Launch", "-plan", "plan-", "a--b", "a" * 41, None]:
        error = await world.fails(alice, p.WORKSPACE_CREATE, name=name, title="T")
        assert error.code == INVALID and error.details == {"field": "name"}, name
    error = await world.fails(alice, p.WORKSPACE_CREATE, name="launch-plan", title="Again")
    assert error.code == CONFLICT
    for title in ["", "   ", "x" * 121]:
        assert (await world.fails(alice, p.WORKSPACE_CREATE, name="fresh", title=title)).code == INVALID


async def test_role_changes_reach_the_member_concerned(world):
    alice, workspace_id = await _owner_and_workspace(world)
    bob, _ = await world.user("Bob")
    await world.add(workspace_id, bob, "editor")
    world.hub.published.clear()

    await world.call(alice, p.MEMBER_SET_ROLE, workspace_id=workspace_id, user_id=bob.id, role="viewer")
    assert world.hub.published == [
        (p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id, ()),
        (p.EV_MEMBER_ROLE_CHANGED, {"workspace_id": workspace_id, "user_id": bob.id, "role": "viewer"}, None, (bob.id,)),
        (p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id}, None, (bob.id,)),
    ]

    world.hub.published.clear()
    await world.call(alice, p.MEMBER_REMOVE, workspace_id=workspace_id, user_id=bob.id)
    assert world.hub.published == [
        (p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id, ()),
        (p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id, "removed": True}, None, (bob.id,)),
    ]


async def test_a_new_display_name_reaches_every_workspace_of_the_user(world):
    alice, first = await _owner_and_workspace(world)
    second = await world.workspace(alice, name="second", title="Second")
    world.hub.published.clear()
    await world.call(alice, p.ME_SET_NAME, display_name="Alicia")
    assert world.hub.published[0] == (p.EV_ME_UPDATED, {}, None, (alice.id,))
    assert {scope for _, _, scope, _ in world.hub.published[1:]} == {first, second}
    members = await world.call(alice, p.MEMBER_LIST, workspace_id=first)
    assert members["members"][0]["display_name"] == "Alicia"
