"""Workspaces and memberships."""

from __future__ import annotations

import sqlite3

from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.host.store.models import Member, Workspace
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso


def create(conn: sqlite3.Connection, *, name: str, title: str, created_by: str) -> Workspace:
    """Create a workspace; its creator becomes the owner."""
    workspace_id = new_id("ws")
    created_at = now_iso()
    conn.execute(
        "INSERT INTO workspaces (id, name, title, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (workspace_id, name, title, created_by, created_at),
    )
    conn.execute(
        "INSERT INTO memberships (workspace_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
        (workspace_id, created_by, created_at),
    )
    workspace = get(conn, workspace_id)
    assert workspace is not None
    return workspace


def get(conn: sqlite3.Connection, workspace_id: str) -> Workspace | None:
    row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    return Workspace.from_row(row) if row else None


def by_name(conn: sqlite3.Connection, name: str) -> Workspace | None:
    row = conn.execute("SELECT * FROM workspaces WHERE name = ?", (name,)).fetchone()
    return Workspace.from_row(row) if row else None


def list_for_user(conn: sqlite3.Connection, user_id: str) -> list[tuple[Workspace, str]]:
    rows = conn.execute(
        "SELECT w.*, m.role AS member_role FROM workspaces w"
        " JOIN memberships m ON m.workspace_id = w.id"
        " WHERE m.user_id = ? ORDER BY w.archived_at IS NOT NULL, w.title COLLATE NOCASE",
        (user_id,),
    ).fetchall()
    return [(Workspace.from_row(row), row["member_role"]) for row in rows]


def rename(conn: sqlite3.Connection, workspace_id: str, title: str) -> None:
    conn.execute("UPDATE workspaces SET title = ? WHERE id = ?", (title, workspace_id))


def set_archived(conn: sqlite3.Connection, workspace_id: str, archived: bool) -> None:
    conn.execute(
        "UPDATE workspaces SET archived_at = ? WHERE id = ?",
        (now_iso() if archived else None, workspace_id),
    )


def delete(conn: sqlite3.Connection, workspace_id: str) -> None:
    # Memberships and invites go with it (ON DELETE CASCADE).
    conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))


def membership(conn: sqlite3.Connection, workspace_id: str, user_id: str) -> Member | None:
    row = conn.execute(
        "SELECT m.*, u.display_name, u.status FROM memberships m JOIN users u ON u.id = m.user_id"
        " WHERE m.workspace_id = ? AND m.user_id = ?",
        (workspace_id, user_id),
    ).fetchone()
    return Member.from_row(row) if row else None


def add_member(conn: sqlite3.Connection, workspace_id: str, user_id: str, role: str) -> Member:
    conn.execute(
        "INSERT INTO memberships (workspace_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
        (workspace_id, user_id, role, now_iso()),
    )
    member = membership(conn, workspace_id, user_id)
    assert member is not None
    return member


def set_role(conn: sqlite3.Connection, workspace_id: str, user_id: str, role: str) -> None:
    conn.execute(
        "UPDATE memberships SET role = ? WHERE workspace_id = ? AND user_id = ?",
        (role, workspace_id, user_id),
    )


def remove_member(conn: sqlite3.Connection, workspace_id: str, user_id: str) -> None:
    conn.execute("DELETE FROM memberships WHERE workspace_id = ? AND user_id = ?", (workspace_id, user_id))


def members(conn: sqlite3.Connection, workspace_id: str) -> list[Member]:
    rows = conn.execute(
        "SELECT m.*, u.display_name, u.status FROM memberships m JOIN users u ON u.id = m.user_id"
        " WHERE m.workspace_id = ?"
        " ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'editor' THEN 1 WHEN 'commenter' THEN 2 ELSE 3 END,"
        " u.display_name COLLATE NOCASE",
        (workspace_id,),
    ).fetchall()
    return [Member.from_row(row) for row in rows]


def member_user_ids(conn: sqlite3.Connection, workspace_id: str) -> list[str]:
    rows = conn.execute("SELECT user_id FROM memberships WHERE workspace_id = ?", (workspace_id,)).fetchall()
    return [row["user_id"] for row in rows]


def owner_count(conn: sqlite3.Connection, workspace_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM memberships WHERE workspace_id = ? AND role = 'owner'", (workspace_id,)
    ).fetchone()
    return int(row[0])
