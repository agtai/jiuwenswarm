"""The workspace chat: messages and where the agent's chat context starts."""

from __future__ import annotations

import json
import sqlite3

from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.host.store.models import ChatMessage
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso


def add(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    author_id: str,
    author_kind: str,
    kind: str,
    body: str,
    mentions: list[dict[str, str]] | None = None,
    mandate_id: str | None = None,
    decision_id: str | None = None,
) -> ChatMessage:
    message_id = new_id("cm")
    conn.execute(
        "INSERT INTO chat_messages (id, workspace_id, author_id, author_kind, kind, body, mentions, mandate_id,"
        " decision_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (message_id, workspace_id, author_id, author_kind, kind, body, json.dumps(mentions or []), mandate_id, decision_id, now_iso()),
    )
    message = get(conn, message_id)
    assert message is not None
    return message


def get(conn: sqlite3.Connection, message_id: str) -> ChatMessage | None:
    row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
    return ChatMessage.from_row(row) if row else None


def set_mandate(conn: sqlite3.Connection, message_id: str, mandate_id: str) -> None:
    conn.execute("UPDATE chat_messages SET mandate_id = ? WHERE id = ?", (mandate_id, message_id))


def page(conn: sqlite3.Connection, workspace_id: str, *, before: str | None, limit: int) -> list[ChatMessage]:
    """Up to `limit` messages older than `before` (a message id), oldest first. Messages are ordered
    as they were stored: ids made in the same millisecond do not sort by time."""
    query = "SELECT * FROM chat_messages WHERE workspace_id = ?"
    args: list = [workspace_id]
    if before:
        query += " AND rowid < (SELECT rowid FROM chat_messages WHERE id = ?)"
        args.append(before)
    rows = conn.execute(query + " ORDER BY rowid DESC LIMIT ?", (*args, limit)).fetchall()
    return [ChatMessage.from_row(r) for r in reversed(rows)]


def said_since(conn: sqlite3.Connection, workspace_id: str, *, limit: int) -> list[ChatMessage]:
    """People's messages that did not give the agent a task, the newest `limit` of those no agent turn
    has been shown yet, oldest first."""
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE workspace_id = ? AND kind = 'message' AND author_kind = 'person'"
        " AND mandate_id IS NULL AND rowid > ? ORDER BY rowid DESC LIMIT ?",
        (workspace_id, seen_up_to(conn, workspace_id), limit),
    ).fetchall()
    return [ChatMessage.from_row(r) for r in reversed(rows)]


def seen_up_to(conn: sqlite3.Connection, workspace_id: str) -> int:
    row = conn.execute("SELECT seen_up_to FROM workspace_chat_state WHERE workspace_id = ?", (workspace_id,)).fetchone()
    return int(row["seen_up_to"]) if row else 0


def mark_seen(conn: sqlite3.Connection, workspace_id: str) -> None:
    """An agent turn has been shown everything said so far."""
    conn.execute(
        "INSERT INTO workspace_chat_state (workspace_id, seen_up_to)"
        " SELECT ?, COALESCE(MAX(rowid), 0) FROM chat_messages WHERE workspace_id = ?"
        " ON CONFLICT(workspace_id) DO UPDATE SET seen_up_to = excluded.seen_up_to",
        (workspace_id, workspace_id),
    )
