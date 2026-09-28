"""Host-wide values, such as the host's stable id."""

from __future__ import annotations

import sqlite3

from jiuwenswarm.extensions.blackboard.common.ids import new_id


def get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def ensure_host_uid(conn: sqlite3.Connection) -> str:
    """A random id that identifies this host's data, so a client can tell two
    addresses of the same host apart from two different hosts."""
    value = get(conn, "host_uid")
    if value is None:
        value = new_id("host")
        set_value(conn, "host_uid", value)
    return value
