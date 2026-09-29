"""Shared IM bots and the IM accounts people connect to their users (milestone 7)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.common.tokens import new_link_code
from jiuwenswarm.extensions.blackboard.host.store.models import Bot, Identity
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso

LINK_CODE_TTL = timedelta(minutes=15)


def create(conn: sqlite3.Connection, *, name: str, token_hash: str, created_by: str) -> Bot:
    bot_id = new_id("bot")
    conn.execute(
        "INSERT INTO bots (id, name, token_hash, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (bot_id, name, token_hash, created_by, now_iso()),
    )
    bot = get(conn, bot_id)
    assert bot is not None
    return bot


def get(conn: sqlite3.Connection, bot_id: str) -> Bot | None:
    row = conn.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
    return Bot.from_row(row) if row else None


def by_token_hash(conn: sqlite3.Connection, token_hash: str) -> Bot | None:
    row = conn.execute("SELECT * FROM bots WHERE token_hash = ?", (token_hash,)).fetchone()
    return Bot.from_row(row) if row else None


def list_all(conn: sqlite3.Connection) -> list[Bot]:
    return [Bot.from_row(r) for r in conn.execute("SELECT * FROM bots ORDER BY rowid").fetchall()]


def revoke(conn: sqlite3.Connection, bot_id: str) -> None:
    conn.execute("UPDATE bots SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (now_iso(), bot_id))


def touch(conn: sqlite3.Connection, bot_id: str) -> None:
    conn.execute("UPDATE bots SET last_used_at = ? WHERE id = ?", (now_iso(), bot_id))


# ---- link codes ----


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_code(conn: sqlite3.Connection, user_id: str) -> tuple[str, str]:
    """A fresh code for the person; their earlier codes stop working. Returns (code, expires_at)."""
    now = datetime.now(timezone.utc)
    conn.execute("DELETE FROM im_link_codes WHERE user_id = ? OR expires_at < ?", (user_id, _iso(now)))
    code = new_link_code()
    expires_at = _iso(now + LINK_CODE_TTL)
    conn.execute("INSERT INTO im_link_codes (code, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)", (code, user_id, _iso(now), expires_at))
    return code, expires_at


def take_code(conn: sqlite3.Connection, code: str) -> str | None:
    """The user a live code belongs to; the code is used up either way."""
    row = conn.execute("SELECT user_id, expires_at FROM im_link_codes WHERE code = ?", (code,)).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM im_link_codes WHERE code = ?", (code,))
    return row["user_id"] if row["expires_at"] > now_iso() else None


# ---- connected IM accounts ----


def identity(conn: sqlite3.Connection, platform: str, external_id: str) -> Identity | None:
    row = conn.execute("SELECT * FROM im_identities WHERE platform = ? AND external_id = ?", (platform, external_id)).fetchone()
    return Identity.from_row(row) if row else None


def link(
    conn: sqlite3.Connection, *, platform: str, external_id: str, user_id: str, display_name: str | None, bot_id: str
) -> Identity | None:
    """Connect the account to the user; returns the connection it replaced, if any."""
    previous = identity(conn, platform, external_id)
    conn.execute(
        "INSERT INTO im_identities (platform, external_id, user_id, display_name, bot_id, linked_at) VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(platform, external_id) DO UPDATE SET user_id = excluded.user_id, display_name = excluded.display_name,"
        " bot_id = excluded.bot_id, linked_at = excluded.linked_at",
        (platform, external_id, user_id, display_name, bot_id, now_iso()),
    )
    return previous


def unlink(conn: sqlite3.Connection, user_id: str, platform: str, external_id: str) -> bool:
    cursor = conn.execute(
        "DELETE FROM im_identities WHERE user_id = ? AND platform = ? AND external_id = ?", (user_id, platform, external_id)
    )
    return cursor.rowcount > 0


def for_user(conn: sqlite3.Connection, user_id: str) -> list[Identity]:
    rows = conn.execute("SELECT * FROM im_identities WHERE user_id = ? ORDER BY linked_at", (user_id,)).fetchall()
    return [Identity.from_row(r) for r in rows]
