"""Invite codes that let a person join a workspace with a given role."""

from __future__ import annotations

import sqlite3

from jiuwenswarm.extensions.blackboard.common.tokens import new_invite_code
from jiuwenswarm.extensions.blackboard.host.store.models import Invite
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso


def create(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    role: str,
    created_by: str,
    expires_at: str | None,
    max_uses: int | None,
) -> Invite:
    code = new_invite_code()
    conn.execute(
        "INSERT INTO invites (code, workspace_id, role, created_by, created_at, expires_at, max_uses)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, workspace_id, role, created_by, now_iso(), expires_at, max_uses),
    )
    invite = get(conn, code)
    assert invite is not None
    return invite


def get(conn: sqlite3.Connection, code: str) -> Invite | None:
    row = conn.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone()
    return Invite.from_row(row) if row else None


def list_for_workspace(conn: sqlite3.Connection, workspace_id: str) -> list[Invite]:
    rows = conn.execute(
        "SELECT * FROM invites WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)
    ).fetchall()
    return [Invite.from_row(row) for row in rows]


def revoke(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("UPDATE invites SET revoked_at = ? WHERE code = ? AND revoked_at IS NULL", (now_iso(), code))


def use(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("UPDATE invites SET uses = uses + 1 WHERE code = ?", (code,))
