"""Decisions: the agent's questions, their answers and who accepted them."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.host.store.models import Decision
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso

OPEN = ("open", "proposed")


def create(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    mandate_id: str,
    requester_id: str,
    question: str,
    options: list[dict[str, str]],
    recommended: int | None,
    doc_id: str | None = None,
    block_id: str | None = None,
    block_digest: str | None = None,
    quote: str | None = None,
) -> Decision:
    decision_id = new_id("dc")
    conn.execute(
        "INSERT INTO decisions (id, workspace_id, mandate_id, requester_id, doc_id, block_id, block_digest, quote,"
        " question, options, recommended, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
        (
            decision_id,
            workspace_id,
            mandate_id,
            requester_id,
            doc_id,
            block_id,
            block_digest,
            quote,
            question,
            json.dumps(options),
            recommended,
            now_iso(),
        ),
    )
    decision = get(conn, decision_id)
    assert decision is not None
    return decision


def get(conn: sqlite3.Connection, decision_id: str) -> Decision | None:
    row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
    return Decision.from_row(row) if row else None


def open_for_mandate(conn: sqlite3.Connection, mandate_id: str) -> Decision | None:
    row = conn.execute(
        "SELECT * FROM decisions WHERE mandate_id = ? AND status IN ('open', 'proposed') ORDER BY rowid DESC LIMIT 1",
        (mandate_id,),
    ).fetchone()
    return Decision.from_row(row) if row else None


def list_for_workspace(conn: sqlite3.Connection, workspace_id: str, *, status: str | None = None, limit: int = 100) -> list[Decision]:
    query = "SELECT * FROM decisions WHERE workspace_id = ?"
    args: list[Any] = [workspace_id]
    if status:
        query += " AND status = ?"
        args.append(status)
    rows = conn.execute(query + " ORDER BY rowid DESC LIMIT ?", (*args, limit)).fetchall()
    return [Decision.from_row(r) for r in rows]


def propose(conn: sqlite3.Connection, decision_id: str, answer: dict[str, Any], by: str) -> None:
    conn.execute(
        "UPDATE decisions SET status = 'proposed', answer = ?, answered_by = ?, answered_at = ? WHERE id = ?",
        (json.dumps(answer), by, now_iso(), decision_id),
    )


def accept(conn: sqlite3.Connection, decision_id: str, by: str, answer: dict[str, Any] | None = None) -> None:
    """Record the requester's acceptance; with `answer`, the requester answered themselves."""
    now = now_iso()
    if answer is not None:
        conn.execute(
            "UPDATE decisions SET status = 'answered', answer = ?, answered_by = ?, answered_at = ?, accepted_by = ?,"
            " accepted_at = ? WHERE id = ?",
            (json.dumps(answer), by, now, by, now, decision_id),
        )
    else:
        conn.execute(
            "UPDATE decisions SET status = 'answered', accepted_by = ?, accepted_at = ? WHERE id = ?",
            (by, now, decision_id),
        )


def cancel(conn: sqlite3.Connection, decision_id: str) -> None:
    conn.execute("UPDATE decisions SET status = 'cancelled' WHERE id = ?", (decision_id,))
