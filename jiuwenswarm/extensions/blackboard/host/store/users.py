"""Users: host records created by invitation, authenticated by a member token."""

from __future__ import annotations

import sqlite3

from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.host.store.models import User
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso


def create(
    conn: sqlite3.Connection,
    *,
    display_name: str,
    token_hash: str,
    is_operator: bool = False,
    external_id: str | None = None,
) -> User:
    user_id = new_id("u")
    conn.execute(
        "INSERT INTO users (id, display_name, token_hash, external_id, is_operator, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, display_name, token_hash, external_id, 1 if is_operator else 0, now_iso()),
    )
    user = get(conn, user_id)
    assert user is not None
    return user


def get(conn: sqlite3.Connection, user_id: str) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User.from_row(row) if row else None


def by_token_hash(conn: sqlite3.Connection, token_hash: str) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE token_hash = ?", (token_hash,)).fetchone()
    return User.from_row(row) if row else None


def operator(conn: sqlite3.Connection) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE is_operator = 1 ORDER BY created_at LIMIT 1").fetchone()
    return User.from_row(row) if row else None


def token_hash_of(conn: sqlite3.Connection, user_id: str) -> str | None:
    row = conn.execute("SELECT token_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["token_hash"] if row else None


def set_name(conn: sqlite3.Connection, user_id: str, display_name: str) -> None:
    conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))


def set_token_hash(conn: sqlite3.Connection, user_id: str, token_hash: str) -> None:
    conn.execute("UPDATE users SET token_hash = ? WHERE id = ?", (token_hash, user_id))


def set_status(conn: sqlite3.Connection, user_id: str, status: str) -> None:
    conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))


def touch(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now_iso(), user_id))


def names(conn: sqlite3.Connection, user_ids: set[str] | list[str]) -> dict[str, str]:
    """Display names by user id, for the ids that exist."""
    ids = sorted({i for i in user_ids if i})
    if not ids:
        return {}
    rows = conn.execute(f"SELECT id, display_name FROM users WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    return {r["id"]: r["display_name"] for r in rows}
