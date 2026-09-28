"""Reference files uploaded to a workspace. The bytes are on disk; these rows describe them."""

from __future__ import annotations

import sqlite3

from jiuwenswarm.extensions.blackboard.host.store.models import Reference
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso


def create(
    conn: sqlite3.Connection,
    *,
    reference_id: str,
    workspace_id: str,
    kind: str,
    name: str,
    mime: str,
    size: int,
    stored_path: str,
    note: str,
    uploaded_by: str,
) -> Reference:
    conn.execute(
        "INSERT INTO references_ (id, workspace_id, kind, name, mime, size, stored_path, note, uploaded_by, uploaded_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (reference_id, workspace_id, kind, name, mime, size, stored_path, note, uploaded_by, now_iso()),
    )
    reference = get(conn, reference_id)
    assert reference is not None
    return reference


def get(conn: sqlite3.Connection, reference_id: str) -> Reference | None:
    row = conn.execute("SELECT * FROM references_ WHERE id = ?", (reference_id,)).fetchone()
    return Reference.from_row(row) if row else None


def list_for_workspace(conn: sqlite3.Connection, workspace_id: str) -> list[tuple[Reference, str | None]]:
    rows = conn.execute(
        "SELECT r.*, u.display_name AS uploader_name FROM references_ r LEFT JOIN users u ON u.id = r.uploaded_by"
        " WHERE r.workspace_id = ? AND r.removed_at IS NULL ORDER BY r.uploaded_at DESC",
        (workspace_id,),
    ).fetchall()
    return [(Reference.from_row(row), row["uploader_name"]) for row in rows]


def remove(conn: sqlite3.Connection, reference_id: str) -> None:
    conn.execute("UPDATE references_ SET removed_at = ? WHERE id = ?", (now_iso(), reference_id))


def set_note(conn: sqlite3.Connection, reference_id: str, note: str) -> None:
    conn.execute("UPDATE references_ SET note = ? WHERE id = ?", (note, reference_id))
