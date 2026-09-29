from __future__ import annotations

import sqlite3

import pytest

from jiuwenswarm.extensions.blackboard.common.tokens import hash_token
from jiuwenswarm.extensions.blackboard.host.store import Store, invites, meta, users, workspaces
from jiuwenswarm.extensions.blackboard.host.store.migrations import LATEST_VERSION
from jiuwenswarm.extensions.blackboard.host.store.models import Invite


async def _user(store: Store, name: str):
    return await store.transact(lambda c: users.create(c, display_name=name, token_hash=hash_token(name)))


async def test_open_migrates_once_and_keeps_the_host_uid(tmp_path):
    path = tmp_path / "blackboard.db"
    store = Store(path)
    assert await store.open() == LATEST_VERSION
    uid = await store.transact(meta.ensure_host_uid)
    assert uid.startswith("host_")
    await _user(store, "Alice")
    await store.close()

    reopened = Store(path)
    assert await reopened.open() == LATEST_VERSION
    assert await reopened.transact(meta.ensure_host_uid) == uid
    assert await reopened.read(lambda c: users.by_token_hash(c, hash_token("Alice"))) is not None
    rows = await reopened.read(lambda c: c.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0])
    assert rows == LATEST_VERSION
    await reopened.close()


async def test_a_closed_store_refuses_work(tmp_path):
    store = Store(tmp_path / "blackboard.db")
    with pytest.raises(RuntimeError):
        await store.read(lambda c: None)
    await store.open()
    await store.close()
    with pytest.raises(RuntimeError):
        await store.transact(lambda c: None)


async def test_a_failed_transaction_leaves_nothing_behind(store):
    def work(conn):
        users.create(conn, display_name="Alice", token_hash="h1")
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await store.transact(work)
    assert await store.read(lambda c: users.by_token_hash(c, "h1")) is None


async def test_creating_a_workspace_makes_its_creator_owner(store):
    alice = await _user(store, "Alice")
    ws = await store.transact(lambda c: workspaces.create(c, name="launch-plan", title="Launch plan", created_by=alice.id))
    member = await store.read(lambda c: workspaces.membership(c, ws.id, alice.id))
    assert member.role == "owner"
    assert ws.to_dict("owner") == {
        "id": ws.id,
        "name": "launch-plan",
        "title": "Launch plan",
        "created_at": ws.created_at,
        "archived": False,
        "role": "owner",
    }
    with pytest.raises(sqlite3.IntegrityError):
        await store.transact(lambda c: workspaces.create(c, name="launch-plan", title="Again", created_by=alice.id))


async def test_workspaces_list_active_first_then_by_title(store):
    alice = await _user(store, "Alice")
    ids = {}
    for name, title in [("zeta", "zeta"), ("alpha", "Alpha"), ("beta", "beta")]:
        ws = await store.transact(lambda c, n=name, t=title: workspaces.create(c, name=n, title=t, created_by=alice.id))
        ids[name] = ws.id
    await store.transact(lambda c: workspaces.set_archived(c, ids["alpha"], True))
    rows = await store.read(lambda c: workspaces.list_for_user(c, alice.id))
    assert [w.name for w, _ in rows] == ["beta", "zeta", "alpha"]
    assert rows[-1][0].archived_at is not None


async def test_members_are_listed_by_role_then_name(store):
    alice = await _user(store, "Alice")
    ws = await store.transact(lambda c: workspaces.create(c, name="team", title="Team", created_by=alice.id))
    for name, role in [("dave", "viewer"), ("Bob", "editor"), ("carol", "commenter"), ("adam", "editor")]:
        user = await _user(store, name)
        await store.transact(lambda c, u=user, r=role: workspaces.add_member(c, ws.id, u.id, r))
    members = await store.read(lambda c: workspaces.members(c, ws.id))
    assert [(m.display_name, m.role) for m in members] == [
        ("Alice", "owner"),
        ("adam", "editor"),
        ("Bob", "editor"),
        ("carol", "commenter"),
        ("dave", "viewer"),
    ]
    assert await store.read(lambda c: workspaces.owner_count(c, ws.id)) == 1


async def test_deleting_a_workspace_takes_memberships_and_invites_with_it(store):
    alice = await _user(store, "Alice")
    ws = await store.transact(lambda c: workspaces.create(c, name="team", title="Team", created_by=alice.id))
    invite = await store.transact(
        lambda c: invites.create(
            c, workspace_id=ws.id, role="editor", created_by=alice.id, expires_at="2999-01-01T00:00:00.000Z", max_uses=1
        )
    )
    await store.transact(lambda c: workspaces.delete(c, ws.id))
    assert await store.read(lambda c: workspaces.member_user_ids(c, ws.id)) == []
    assert await store.read(lambda c: invites.get(c, invite.code)) is None


async def test_roles_outside_the_list_are_rejected_by_the_schema(store):
    alice = await _user(store, "Alice")
    bob = await _user(store, "Bob")
    ws = await store.transact(lambda c: workspaces.create(c, name="team", title="Team", created_by=alice.id))
    with pytest.raises(sqlite3.IntegrityError):
        await store.transact(lambda c: workspaces.add_member(c, ws.id, bob.id, "admin"))
    with pytest.raises(sqlite3.IntegrityError):
        await store.transact(
            lambda c: invites.create(
                c, workspace_id=ws.id, role="owner", created_by=alice.id, expires_at="2999-01-01", max_uses=1
            )
        )


def _invite(**overrides) -> Invite:
    values = dict(
        code="c" * 20,
        workspace_id="ws_1",
        role="editor",
        created_by="u_1",
        created_at="2026-01-01T00:00:00.000Z",
        expires_at="2026-02-01T00:00:00.000Z",
        max_uses=2,
        uses=0,
        revoked_at=None,
    )
    values.update(overrides)
    return Invite(**values)


@pytest.mark.parametrize(
    "overrides,state",
    [
        ({}, "active"),
        ({"uses": 2}, "used_up"),
        ({"expires_at": "2026-01-10T00:00:00.000Z"}, "expired"),
        ({"expires_at": "2026-01-10T00:00:00.000Z", "uses": 2}, "expired"),
        ({"revoked_at": "2026-01-02T00:00:00.000Z", "uses": 2}, "revoked"),
        ({"expires_at": None, "max_uses": None, "uses": 500}, "active"),
        ({"expires_at": None, "uses": 2}, "used_up"),
        ({"max_uses": None, "expires_at": "2026-01-10T00:00:00.000Z"}, "expired"),
    ],
)
def test_invite_state(overrides, state):
    assert _invite(**overrides).state("2026-01-15T00:00:00.000Z") == state


@pytest.mark.parametrize("start", range(1, LATEST_VERSION))
async def test_a_store_from_any_earlier_milestone_upgrades_with_its_data(tmp_path, start):
    """A host last run at an earlier milestone's schema opens at the latest one, rows intact."""
    from jiuwenswarm.extensions.blackboard.host.store.migrations import MIGRATIONS

    path = tmp_path / "blackboard.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    for number, statements in MIGRATIONS:
        if number <= start:
            for statement in statements:
                conn.execute(statement)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (number,))
    now = "2026-09-01T00:00:00.000+00:00"
    conn.execute(
        "INSERT INTO users (id, display_name, token_hash, is_operator, created_at) VALUES ('u_a', 'Alice', ?, 1, ?)",
        (hash_token("bbm_old"), now),
    )
    conn.execute("INSERT INTO workspaces (id, name, title, created_by, created_at) VALUES ('w_1', 'launch', 'Launch', 'u_a', ?)", (now,))
    conn.execute("INSERT INTO memberships (workspace_id, user_id, role, joined_at) VALUES ('w_1', 'u_a', 'owner', ?)", (now,))
    conn.execute("INSERT INTO invites (code, workspace_id, role, created_by, created_at) VALUES ('code1', 'w_1', 'editor', 'u_a', ?)", (now,))
    if start >= 2:
        conn.execute("INSERT INTO docs (id, workspace_id, title, created_by, created_at) VALUES ('d_1', 'w_1', 'Plan', 'u_a', ?)", (now,))
    conn.commit()
    conn.close()

    store = Store(path)
    assert await store.open() == LATEST_VERSION
    try:
        user = await store.read(lambda c: users.by_token_hash(c, hash_token("bbm_old")))
        assert user is not None and user.display_name == "Alice" and user.status == "active"
        assert [(w.title, role) for w, role in await store.read(lambda c: workspaces.list_for_user(c, "u_a"))] == [("Launch", "owner")]
        assert (await store.read(lambda c: invites.get(c, "code1"))).role == "editor"
        if start >= 2:
            assert await store.read(lambda c: c.execute("SELECT title FROM docs WHERE id = 'd_1'").fetchone()["title"]) == "Plan"
    finally:
        await store.close()
