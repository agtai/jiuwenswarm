"""Comment threads anchored to passages of a document, and their comments."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.host.store.models import Comment, Thread
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso


def create_thread(conn: sqlite3.Connection, *, workspace_id: str, doc_id: str, anchor: dict[str, Any], created_by: str) -> Thread:
    thread_id = new_id("t")
    conn.execute(
        "INSERT INTO threads (id, workspace_id, doc_id, anchor, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (thread_id, workspace_id, doc_id, json.dumps(anchor), created_by, now_iso()),
    )
    thread = get_thread(conn, thread_id)
    assert thread is not None
    return thread


def get_thread(conn: sqlite3.Connection, thread_id: str) -> Thread | None:
    row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
    return Thread.from_row(row) if row else None


def threads_for_doc(conn: sqlite3.Connection, doc_id: str, *, include_resolved: bool = False) -> list[Thread]:
    query = "SELECT * FROM threads WHERE doc_id = ?"
    if not include_resolved:
        query += " AND resolved_at IS NULL"
    return [Thread.from_row(r) for r in conn.execute(query + " ORDER BY rowid", (doc_id,)).fetchall()]


def set_anchor(conn: sqlite3.Connection, thread_id: str, anchor: dict[str, Any]) -> None:
    conn.execute("UPDATE threads SET anchor = ? WHERE id = ?", (json.dumps(anchor), thread_id))


def set_resolved(conn: sqlite3.Connection, thread_id: str, user_id: str | None) -> None:
    if user_id is None:
        conn.execute("UPDATE threads SET resolved_at = NULL, resolved_by = NULL WHERE id = ?", (thread_id,))
    else:
        conn.execute("UPDATE threads SET resolved_at = ?, resolved_by = ? WHERE id = ?", (now_iso(), user_id, thread_id))


def add_comment(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    author_id: str,
    author_kind: str,
    body: str,
    mentions: list[dict[str, str]] | None = None,
    scope_switch: bool = False,
    mandate_id: str | None = None,
    decision_id: str | None = None,
) -> Comment:
    comment_id = new_id("c")
    conn.execute(
        "INSERT INTO comments (id, thread_id, author_id, author_kind, body, mentions, scope_switch, mandate_id,"
        " decision_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            comment_id,
            thread_id,
            author_id,
            author_kind,
            body,
            json.dumps(mentions or []),
            int(scope_switch),
            mandate_id,
            decision_id,
            now_iso(),
        ),
    )
    comment = get_comment(conn, comment_id)
    assert comment is not None
    return comment


def get_comment(conn: sqlite3.Connection, comment_id: str) -> Comment | None:
    row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    return Comment.from_row(row) if row else None


def set_mandate(conn: sqlite3.Connection, comment_id: str, mandate_id: str) -> None:
    conn.execute("UPDATE comments SET mandate_id = ? WHERE id = ?", (mandate_id, comment_id))


def edit_comment(conn: sqlite3.Connection, comment_id: str, body: str) -> None:
    conn.execute("UPDATE comments SET body = ?, edited_at = ? WHERE id = ?", (body, now_iso(), comment_id))


def comments_for(conn: sqlite3.Connection, thread_ids: list[str]) -> dict[str, list[Comment]]:
    out: dict[str, list[Comment]] = {t: [] for t in thread_ids}
    if not thread_ids:
        return out
    rows = conn.execute(
        f"SELECT * FROM comments WHERE thread_id IN ({','.join('?' * len(thread_ids))}) ORDER BY rowid",
        thread_ids,
    ).fetchall()
    for row in rows:
        out[row["thread_id"]].append(Comment.from_row(row))
    return out
