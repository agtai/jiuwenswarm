"""Mandates, their receipts and document locks."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, BlackboardError, not_found
from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.host.store.models import Mandate, Receipt
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso

# Every state change a mandate may make; anything else is refused.
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"waiting_for_answer", "done", "failed", "unknown", "cancelled"}),
    "waiting_for_answer": frozenset({"running", "cancelled"}),
    "unknown": frozenset({"done", "failed"}),
    "done": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "refused": frozenset(),
}
ACTIVE = ("queued", "running", "waiting_for_answer")
FINISHED = frozenset({"done", "failed", "cancelled", "refused"})


def create(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    origin: str,
    origin_ref: dict[str, Any],
    requester_id: str,
    session_id: str | None,
    instruction: str,
    scope: dict[str, Any],
    reply_target: dict[str, Any],
    status: str = "running",
) -> Mandate:
    now = now_iso()
    mandate_id = new_id("m")
    conn.execute(
        "INSERT INTO mandates (id, workspace_id, origin, origin_ref, requester_id, session_id, instruction, scope,"
        " reply_target, status, created_at, started_at, last_activity_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            mandate_id,
            workspace_id,
            origin,
            json.dumps(origin_ref),
            requester_id,
            session_id,
            instruction,
            json.dumps(scope),
            json.dumps(reply_target),
            status,
            now,
            now if status == "running" else None,
            now,
        ),
    )
    mandate = get(conn, mandate_id)
    assert mandate is not None
    return mandate


def get(conn: sqlite3.Connection, mandate_id: str) -> Mandate | None:
    row = conn.execute("SELECT * FROM mandates WHERE id = ?", (mandate_id,)).fetchone()
    return Mandate.from_row(row) if row else None


def list_for_workspace(
    conn: sqlite3.Connection, workspace_id: str, *, statuses: tuple[str, ...] | None = None, limit: int = 50
) -> list[tuple[Mandate, str | None]]:
    query = (
        "SELECT m.*, u.display_name AS requester_name FROM mandates m LEFT JOIN users u ON u.id = m.requester_id"
        " WHERE m.workspace_id = ?"
    )
    args: list[Any] = [workspace_id]
    if statuses:
        query += f" AND m.status IN ({','.join('?' * len(statuses))})"
        args.extend(statuses)
    query += " ORDER BY m.created_at DESC LIMIT ?"
    args.append(limit)
    return [(Mandate.from_row(r), r["requester_name"]) for r in conn.execute(query, args).fetchall()]


def running_for_session(conn: sqlite3.Connection, requester_id: str, session_id: str) -> list[Mandate]:
    rows = conn.execute(
        "SELECT * FROM mandates WHERE requester_id = ? AND session_id = ? AND origin = 'workspace_session'"
        " AND status = 'running'",
        (requester_id, session_id),
    ).fetchall()
    return [Mandate.from_row(r) for r in rows]


def stopped_in_turn(
    conn: sqlite3.Connection, requester_id: str, session_id: str, turn_id: str, workspace_id: str
) -> Mandate | None:
    """A session mandate of this turn in this workspace that someone cancelled."""
    rows = conn.execute(
        "SELECT * FROM mandates WHERE requester_id = ? AND session_id = ? AND origin = 'workspace_session'"
        " AND status = 'cancelled'",
        (requester_id, session_id),
    ).fetchall()
    return next(
        (m for m in map(Mandate.from_row, rows) if m.origin_ref.get("turn_id") == turn_id and m.workspace_id == workspace_id),
        None,
    )


def idle_session_mandates(conn: sqlite3.Connection, before: str) -> list[Mandate]:
    rows = conn.execute(
        "SELECT * FROM mandates WHERE origin = 'workspace_session' AND status = 'running' AND last_activity_at < ?",
        (before,),
    ).fetchall()
    return [Mandate.from_row(r) for r in rows]


def set_status(conn: sqlite3.Connection, mandate_id: str, status: str, reason: str | None = None) -> Mandate:
    """Move a mandate to `status` if the state machine allows it; finished states release its locks."""
    mandate = get(conn, mandate_id)
    if mandate is None:
        raise not_found("no such mandate", mandate_id=mandate_id)
    if status not in TRANSITIONS.get(mandate.status, frozenset()):
        raise BlackboardError(
            CONFLICT, f"a {mandate.status} mandate cannot become {status}", {"mandate_id": mandate_id, "status": mandate.status}
        )
    now = now_iso()
    finished = now if status in FINISHED else None
    conn.execute(
        "UPDATE mandates SET status = ?, status_reason = ?, last_activity_at = ?,"
        " started_at = COALESCE(started_at, CASE WHEN ? = 'running' THEN ? END),"
        " finished_at = COALESCE(?, finished_at) WHERE id = ?",
        (status, reason, now, status, now, finished, mandate_id),
    )
    if status in FINISHED or status == "unknown":
        release_locks(conn, mandate_id)
    updated = get(conn, mandate_id)
    assert updated is not None
    return updated


def touch(conn: sqlite3.Connection, mandate_id: str) -> None:
    conn.execute("UPDATE mandates SET last_activity_at = ? WHERE id = ?", (now_iso(), mandate_id))


# ---- locks ----


def lock_holder(conn: sqlite3.Connection, doc_id: str) -> str | None:
    row = conn.execute("SELECT mandate_id FROM doc_locks WHERE doc_id = ?", (doc_id,)).fetchone()
    return row["mandate_id"] if row else None


def try_lock(conn: sqlite3.Connection, doc_id: str, mandate_id: str) -> bool:
    holder = lock_holder(conn, doc_id)
    if holder == mandate_id:
        return True
    if holder is not None:
        return False
    conn.execute("INSERT INTO doc_locks (doc_id, mandate_id, acquired_at) VALUES (?, ?, ?)", (doc_id, mandate_id, now_iso()))
    return True


def locked_docs(conn: sqlite3.Connection, mandate_id: str) -> list[str]:
    return [r["doc_id"] for r in conn.execute("SELECT doc_id FROM doc_locks WHERE mandate_id = ?", (mandate_id,)).fetchall()]


def release_locks(conn: sqlite3.Connection, mandate_id: str) -> list[str]:
    docs = locked_docs(conn, mandate_id)
    conn.execute("DELETE FROM doc_locks WHERE mandate_id = ?", (mandate_id,))
    return docs


# ---- receipts ----


def add_receipt(conn: sqlite3.Connection, *, mandate_id: str, doc_id: str, ops: list[dict[str, Any]], note: str) -> Receipt:
    receipt_id = new_id("rc")
    conn.execute(
        "INSERT INTO receipts (id, mandate_id, doc_id, status, ops, note, created_at) VALUES (?, ?, ?, 'pending', ?, ?, ?)",
        (receipt_id, mandate_id, doc_id, json.dumps(ops), note, now_iso()),
    )
    receipt = get_receipt(conn, receipt_id)
    assert receipt is not None
    return receipt


def get_receipt(conn: sqlite3.Connection, receipt_id: str) -> Receipt | None:
    row = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
    return Receipt.from_row(row) if row else None


def finish_receipt(
    conn: sqlite3.Connection,
    receipt_id: str,
    *,
    applied: bool,
    before: list[dict[str, Any]] | None = None,
    after: list[dict[str, Any]] | None = None,
    suggestion_ids: list[str] | None = None,
    error: dict[str, Any] | None = None,
) -> Receipt:
    conn.execute(
        "UPDATE receipts SET status = ?, before = ?, after = ?, suggestion_ids = ?, error = ?, applied_at = ? WHERE id = ?",
        (
            "applied" if applied else "aborted",
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            json.dumps(suggestion_ids or []),
            json.dumps(error) if error is not None else None,
            now_iso() if applied else None,
            receipt_id,
        ),
    )
    receipt = get_receipt(conn, receipt_id)
    assert receipt is not None
    return receipt


def receipts_for(conn: sqlite3.Connection, mandate_ids: list[str]) -> dict[str, list[Receipt]]:
    out: dict[str, list[Receipt]] = {m: [] for m in mandate_ids}
    if not mandate_ids:
        return out
    rows = conn.execute(
        f"SELECT * FROM receipts WHERE mandate_id IN ({','.join('?' * len(mandate_ids))}) ORDER BY created_at",
        mandate_ids,
    ).fetchall()
    for row in rows:
        out[row["mandate_id"]].append(Receipt.from_row(row))
    return out


# ---- dispatched turns (comment and chat mandates) ----

DISPATCHED_ORIGINS = ("comment", "workspace_chat")


def mark_dispatched(conn: sqlite3.Connection, mandate_id: str) -> None:
    """A new turn is offered to the requester's jiuwenswarm; nothing has picked it up yet."""
    conn.execute(
        "UPDATE mandates SET dispatched_at = ?, claimed_at = NULL, turn_id = NULL WHERE id = ?",
        (now_iso(), mandate_id),
    )


def claim(conn: sqlite3.Connection, mandate_id: str, session_id: str) -> str:
    """The requester's jiuwenswarm starts the offered turn in `session_id`; returns the turn's id."""
    turn_id = new_id("turn")
    now = now_iso()
    conn.execute(
        "UPDATE mandates SET claimed_at = ?, turn_id = ?, session_id = ?, turn_count = turn_count + 1,"
        " last_activity_at = ? WHERE id = ?",
        (now, turn_id, session_id, now, mandate_id),
    )
    return turn_id


def set_answer(conn: sqlite3.Connection, mandate_id: str, answer: dict[str, Any] | None) -> None:
    conn.execute("UPDATE mandates SET answer = ? WHERE id = ?", (json.dumps(answer) if answer else None, mandate_id))


def pending_for(conn: sqlite3.Connection, requester_id: str) -> list[Mandate]:
    """Turns offered to this person's jiuwenswarm that it has not picked up."""
    rows = conn.execute(
        "SELECT * FROM mandates WHERE requester_id = ? AND status = 'running' AND origin IN ('comment', 'workspace_chat')"
        " AND dispatched_at IS NOT NULL AND claimed_at IS NULL ORDER BY dispatched_at",
        (requester_id,),
    ).fetchall()
    return [Mandate.from_row(r) for r in rows]


def queued_for_doc(conn: sqlite3.Connection, doc_id: str) -> list[Mandate]:
    """Comment mandates waiting for the document, first come first served."""
    rows = conn.execute(
        "SELECT * FROM mandates WHERE status = 'queued' AND origin = 'comment'"
        " AND json_extract(scope, '$.doc_id') = ? ORDER BY rowid",
        (doc_id,),
    ).fetchall()
    return [Mandate.from_row(r) for r in rows]


def for_thread(conn: sqlite3.Connection, thread_id: str, statuses: tuple[str, ...]) -> list[Mandate]:
    rows = conn.execute(
        f"SELECT * FROM mandates WHERE origin = 'comment' AND json_extract(origin_ref, '$.thread_id') = ?"
        f" AND status IN ({','.join('?' * len(statuses))}) ORDER BY rowid",
        (thread_id, *statuses),
    ).fetchall()
    return [Mandate.from_row(r) for r in rows]


def unclaimed_before(conn: sqlite3.Connection, cutoff: str) -> list[Mandate]:
    rows = conn.execute(
        "SELECT * FROM mandates WHERE status = 'running' AND origin IN ('comment', 'workspace_chat')"
        " AND claimed_at IS NULL AND dispatched_at < ?",
        (cutoff,),
    ).fetchall()
    return [Mandate.from_row(r) for r in rows]


def claimed_before(conn: sqlite3.Connection, cutoff: str) -> list[Mandate]:
    rows = conn.execute(
        "SELECT * FROM mandates WHERE status = 'running' AND origin IN ('comment', 'workspace_chat')"
        " AND claimed_at IS NOT NULL AND claimed_at < ?",
        (cutoff,),
    ).fetchall()
    return [Mandate.from_row(r) for r in rows]
