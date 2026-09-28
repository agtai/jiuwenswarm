"""Documents of a workspace. The content lives in the document service; these rows hold the rest."""

from __future__ import annotations

import sqlite3

from jiuwenswarm.extensions.blackboard.host.store.models import Doc
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso


def create(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    workspace_id: str,
    title: str,
    created_by: str,
    is_instructions: bool = False,
    is_pinned: bool = False,
) -> Doc:
    conn.execute(
        "INSERT INTO docs (id, workspace_id, title, is_instructions, is_pinned, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_id, workspace_id, title, int(is_instructions), int(is_pinned), created_by, now_iso()),
    )
    doc = get(conn, doc_id)
    assert doc is not None
    return doc


def get(conn: sqlite3.Connection, doc_id: str) -> Doc | None:
    row = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    return Doc.from_row(row) if row else None


def list_for_workspace(conn: sqlite3.Connection, workspace_id: str, *, include_archived: bool = False) -> list[Doc]:
    query = "SELECT * FROM docs WHERE workspace_id = ?"
    if not include_archived:
        query += " AND archived_at IS NULL"
    # The instructions document first, then pinned ones, then by title.
    query += " ORDER BY is_instructions DESC, is_pinned DESC, title COLLATE NOCASE"
    return [Doc.from_row(row) for row in conn.execute(query, (workspace_id,)).fetchall()]


def ids_for_workspace(conn: sqlite3.Connection, workspace_id: str) -> list[str]:
    return [row["id"] for row in conn.execute("SELECT id FROM docs WHERE workspace_id = ?", (workspace_id,)).fetchall()]


def instructions(conn: sqlite3.Connection, workspace_id: str) -> Doc | None:
    row = conn.execute("SELECT * FROM docs WHERE workspace_id = ? AND is_instructions = 1", (workspace_id,)).fetchone()
    return Doc.from_row(row) if row else None


def rename(conn: sqlite3.Connection, doc_id: str, title: str) -> None:
    conn.execute("UPDATE docs SET title = ? WHERE id = ?", (title, doc_id))


def archive(conn: sqlite3.Connection, doc_id: str) -> None:
    conn.execute("UPDATE docs SET archived_at = ? WHERE id = ?", (now_iso(), doc_id))


def set_pinned(conn: sqlite3.Connection, doc_id: str, pinned: bool) -> None:
    conn.execute("UPDATE docs SET is_pinned = ? WHERE id = ?", (int(pinned), doc_id))


def set_instructions(conn: sqlite3.Connection, workspace_id: str, doc_id: str) -> None:
    # The unique index allows one instructions document per workspace: clear the old one first.
    conn.execute("UPDATE docs SET is_instructions = 0 WHERE workspace_id = ? AND is_instructions = 1", (workspace_id,))
    conn.execute("UPDATE docs SET is_instructions = 1 WHERE id = ?", (doc_id,))
