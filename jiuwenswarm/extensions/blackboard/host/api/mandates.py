"""Mandates on the host: agents edit documents under a recorded, scoped, locked mandate whose every
batch leaves a receipt.

This module serves the `workspace_session` origin (milestone 4): a person talks to their agent in a
session attached to the workspace, and the agent's first `blackboard.edit` in a turn begins the
mandate. Comment and chat mandates (milestone 5, ``dispatch.py``) reuse the records, locks, receipts
and ``blackboard.edit``.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import BUSY, CONFLICT, FORBIDDEN, BlackboardError, invalid, not_found
from jiuwenswarm.extensions.blackboard.common.roles import role_at_least
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.api.ratelimit import EDITS_PER_MINUTE
from jiuwenswarm.extensions.blackboard.host.store import docs, mandates, users
from jiuwenswarm.extensions.blackboard.host.store.models import Doc, Mandate, Receipt

logger = logging.getLogger(__name__)

LOCK_WAIT_S = 60.0
# A workspace-session mandate ends this long after its last edit, or when the session's next turn edits.
SESSION_IDLE_S = 120.0
MAX_NOTE = 300
DEFAULT_INSTRUCTION = "A request from a workspace session"


def _agent_label(name: str | None) -> str:
    return f"{name}'s agent" if name else "Agent"


async def publish_mandate(ctx: HostContext, mandate: Mandate) -> None:
    await ctx.hub.publish(
        p.EV_MANDATE_UPDATED,
        {"workspace_id": mandate.workspace_id, "mandate_id": mandate.id, "status": mandate.status},
        workspace_id=mandate.workspace_id,
    )


async def _clear_presence(ctx: HostContext, doc_ids: list[str]) -> None:
    if ctx.docs is None or not ctx.docs.running:
        return
    for doc_id in doc_ids:
        try:
            await ctx.doc_client().agent_presence(doc_id, {"status": None})
        except BlackboardError as exc:
            logger.debug("blackboard: clearing presence on %s failed: %s", doc_id, exc.message)


async def finish_mandate(ctx: HostContext, mandate_id: str, status: str, reason: str | None = None) -> Mandate:
    """End a mandate: record the state, let go of its documents, take its caret away, and let the
    dispatch layer stop its turn and start whoever waits for the documents."""
    from jiuwenswarm.extensions.blackboard.host.api.dispatch import after_finish

    def work(conn: sqlite3.Connection) -> tuple[Mandate, Mandate, list[str]]:
        before = mandates.get(conn, mandate_id)
        if before is None:
            raise not_found("no such mandate", mandate_id=mandate_id)
        held = mandates.locked_docs(conn, mandate_id)
        return before, mandates.set_status(conn, mandate_id, status, reason), held

    before, mandate, held = await ctx.store.transact(work)
    await _clear_presence(ctx, held)
    await ctx.lock_waits.released()
    await publish_mandate(ctx, mandate)
    await after_finish(ctx, before, mandate, held if status != "waiting_for_answer" else [])
    return mandate


async def sweep_idle_mandates(ctx: HostContext) -> int:
    """Workspace-session mandates end two minutes after their last edit."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=SESSION_IDLE_S)).isoformat(timespec="milliseconds")
    idle = await ctx.store.read(lambda c: mandates.idle_session_mandates(c, cutoff))
    for mandate in idle:
        try:
            await finish_mandate(ctx, mandate.id, "done", "idle")
        except BlackboardError as exc:
            logger.debug("blackboard: sweeping %s failed: %s", mandate.id, exc.message)
    return len(idle)


# ---- listing and cancelling ----


@method(p.MANDATE_LIST)
async def mandate_list(call: Call) -> dict[str, Any]:
    workspace_id = v.required_str(call.params, "workspace_id")
    active = bool(call.params.get("active_only"))

    def work(conn: sqlite3.Connection):
        require_member(conn, call.uid, workspace_id, "viewer")
        rows = mandates.list_for_workspace(conn, workspace_id, statuses=mandates.ACTIVE if active else None)
        return rows, mandates.receipts_for(conn, [m.id for m, _ in rows])

    rows, receipts = await call.ctx.store.read(work)
    open_ids = await _open_suggestions(call.ctx, receipts)
    positions = await call.ctx.store.read(lambda c: _queue_positions(c, [m for m, _ in rows]))
    return {
        "workspace_id": workspace_id,
        "mandates": [
            {
                **m.to_dict(name),
                "receipts": [r.to_dict() for r in receipts.get(m.id, [])],
                "pending": _pending(receipts.get(m.id, []), open_ids),
                "queue_position": positions.get(m.id),
            }
            for m, name in rows
        ],
    }


def _queue_positions(conn: sqlite3.Connection, listed: list[Mandate]) -> dict[str, int]:
    """For each waiting comment mandate, its place in its document's queue (1 is next)."""
    out: dict[str, int] = {}
    for doc_id in {str(m.scope.get("doc_id")) for m in listed if m.status == "queued"}:
        for position, waiting in enumerate(mandates.queued_for_doc(conn, doc_id), start=1):
            out[waiting.id] = position
    return out


async def _open_suggestions(ctx: HostContext, receipts: dict[str, list[Receipt]]) -> dict[str, set[str]]:
    """The suggestions still open in each document the receipts changed; a document the service
    cannot answer for is left out, so its receipts count as pending."""
    doc_ids = {r.doc_id for rows in receipts.values() for r in rows if r.status == "applied" and r.suggestion_ids}
    open_ids: dict[str, set[str]] = {}
    for doc_id in sorted(doc_ids):
        try:
            result = await ctx.doc_client().suggestions(doc_id)
        except BlackboardError:
            continue
        open_ids[doc_id] = {s["id"] for s in result.get("suggestions", [])}
    return open_ids


def _pending(receipts: list[Receipt], open_ids: dict[str, set[str]]) -> dict[str, list[str]]:
    """Doc id -> the mandate's suggestions nobody has decided on yet."""
    pending: dict[str, list[str]] = {}
    for r in receipts:
        if r.status != "applied":
            continue
        still = [i for i in r.suggestion_ids if r.doc_id not in open_ids or i in open_ids[r.doc_id]]
        if still:
            pending.setdefault(r.doc_id, []).extend(still)
    return pending


@method(p.MANDATE_CANCEL)
async def mandate_cancel(call: Call) -> dict[str, Any]:
    """The requester, or any editor of the workspace, may stop a mandate."""
    mandate_id = v.required_str(call.params, "mandate_id")

    def check(conn: sqlite3.Connection) -> Mandate:
        mandate = mandates.get(conn, mandate_id)
        if mandate is None:
            raise not_found("no such mandate", mandate_id=mandate_id)
        require_member(conn, call.uid, mandate.workspace_id, "viewer" if mandate.requester_id == call.uid else "editor")
        if mandate.status not in mandates.ACTIVE:
            raise BlackboardError(CONFLICT, f"the mandate is already {mandate.status}", {"mandate_id": mandate_id})
        return mandate

    await call.ctx.store.read(check)
    mandate = await finish_mandate(call.ctx, mandate_id, "cancelled", f"cancelled by {call.uid}")
    return {"mandate": mandate.to_dict()}


# ---- suggestions ----


def _doc_for(conn: sqlite3.Connection, user_id: str, doc_id: str, at_least: str) -> Doc:
    doc = docs.get(conn, doc_id)
    if doc is None:
        raise not_found("no such document", doc_id=doc_id)
    workspace, _ = require_member(conn, user_id, doc.workspace_id, at_least)
    if at_least != "viewer" and (workspace.archived_at is not None or doc.archived_at is not None):
        raise BlackboardError(CONFLICT, "the document or its workspace is archived", {"doc_id": doc_id})
    return doc


@method(p.SUGGESTION_LIST)
async def suggestion_list(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")
    await call.ctx.store.read(lambda c: _doc_for(c, call.uid, doc_id, "viewer"))
    result = await call.ctx.doc_client().suggestions(doc_id)
    return {"doc_id": doc_id, "suggestions": result.get("suggestions", [])}


@method(p.SUGGESTION_DECIDE)
async def suggestion_decide(call: Call) -> dict[str, Any]:
    """Accept or reject suggestions; editors and owners decide."""
    doc_id = v.required_str(call.params, "doc_id")
    action = call.params.get("action")
    if action not in ("accept", "reject"):
        raise invalid("action is accept or reject", field="action")
    ids = call.params.get("suggestion_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids) or len(ids) > 200:
        raise invalid("suggestion_ids is a list of up to 200 ids", field="suggestion_ids")
    doc = await call.ctx.store.read(lambda c: _doc_for(c, call.uid, doc_id, "editor"))
    client = call.ctx.doc_client()
    decided: list[str] = []
    missing: list[str] = []
    for suggestion_id in dict.fromkeys(ids):
        try:
            await client.decide(doc_id, suggestion_id, action, actor=call.uid)
            decided.append(suggestion_id)
        except BlackboardError as exc:
            if exc.code != "not_found":
                raise
            missing.append(suggestion_id)
    if decided:
        await call.ctx.hub.publish(
            p.EV_SUGGESTIONS_CHANGED, {"workspace_id": doc.workspace_id, "doc_id": doc_id}, workspace_id=doc.workspace_id
        )
    return {"doc_id": doc_id, "action": action, "decided": decided, "missing": missing}


# ---- the agent's edits ----


def _read_ops(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 50:
        raise invalid("ops is a list of 1 to 50 operations", field="ops")
    out = []
    for i, op in enumerate(value):
        if not isinstance(op, dict):
            raise invalid(f"op {i} is not an object", field="ops")
        out.append(
            {
                "op": op.get("op"),
                "blockId": op.get("block_id") if op.get("block_id") is not None else op.get("blockId"),
                "digest": op.get("digest"),
                "markdown": op.get("markdown"),
            }
        )
    return out


def _mandate_for_edit(conn: sqlite3.Connection, call: Call, doc: Doc) -> tuple[Mandate, list[Mandate], bool]:
    """The mandate this edit belongs to: the one named, else this turn's session mandate, else a new one.

    Returns it, the session's older mandates that end now, and whether it was created here.
    """
    mandate_id = call.params.get("mandate_id")
    if mandate_id:
        mandate = mandates.get(conn, str(mandate_id))
        if mandate is None or mandate.requester_id != call.uid:
            raise BlackboardError("no_mandate", "no such mandate of yours", {"mandate_id": mandate_id})
        if mandate.status != "running":
            raise BlackboardError("no_mandate", f"the mandate is {mandate.status}", {"mandate_id": mandate_id, "status": mandate.status})
        if mandate.workspace_id != doc.workspace_id:
            raise BlackboardError("out_of_scope", "the document is in another workspace", {"doc_id": doc.id})
        return mandate, [], False

    session_id = v.required_str(call.params, "session_id")
    turn_id = str(call.params.get("turn_id") or "")
    running = mandates.running_for_session(conn, call.uid, session_id)
    for mandate in running:
        if mandate.workspace_id == doc.workspace_id and mandate.origin_ref.get("turn_id") == turn_id:
            return mandate, [], False
    stopped = mandates.stopped_in_turn(conn, call.uid, session_id, turn_id, doc.workspace_id) if turn_id else None
    if stopped is not None:
        raise BlackboardError(
            "no_mandate",
            "this run was stopped; make no more edits in this turn and tell the person",
            {"mandate_id": stopped.id, "status": stopped.status},
        )
    note = call.params.get("note")
    mandate = mandates.create(
        conn,
        workspace_id=doc.workspace_id,
        origin="workspace_session",
        origin_ref={"session_id": session_id, "turn_id": turn_id},
        requester_id=call.uid,
        session_id=session_id,
        instruction=note.strip()[:MAX_NOTE] if isinstance(note, str) and note.strip() else DEFAULT_INSTRUCTION,
        scope={},
        reply_target={"kind": "session", "id": session_id},
    )
    # A session may work on several workspaces: only runs of earlier turns end here.
    return mandate, [m for m in running if m.origin_ref.get("turn_id") != turn_id], True


@method(p.EDIT)
async def edit(call: Call) -> dict[str, Any]:
    """A batch of block operations from the caller's agent, written as suggestions under a mandate."""
    ctx = call.ctx
    doc_id = v.required_str(call.params, "doc_id")
    ops = _read_ops(call.params.get("ops"))
    note = v.text(call.params.get("note") or "", "note", max_len=MAX_NOTE, min_len=0)

    def begin(conn: sqlite3.Connection) -> tuple[Doc, Mandate, list[Mandate], bool]:
        doc = docs.get(conn, doc_id)
        if doc is None:
            raise not_found("no such document", doc_id=doc_id)
        workspace, member = require_member(conn, call.uid, doc.workspace_id, "viewer")
        if not role_at_least(member.role, "editor"):
            raise BlackboardError(FORBIDDEN, "your role does not allow edits", {"role": member.role})
        if workspace.archived_at is not None or doc.archived_at is not None:
            raise BlackboardError(CONFLICT, "the document or its workspace is archived", {"doc_id": doc_id})
        mandate, older, created = _mandate_for_edit(conn, call, doc)
        scoped_doc = mandate.scope.get("doc_id")
        if scoped_doc and scoped_doc != doc_id:
            raise BlackboardError("out_of_scope", "the mandate is for another document", {"doc_id": doc_id, "scope": mandate.scope})
        return doc, mandate, older, created

    doc, mandate, older, created = await ctx.store.transact(begin)
    ctx.limits.check(f"edit:{mandate.id}", EDITS_PER_MINUTE)
    for previous in older:
        await finish_mandate(ctx, previous.id, "done", "next_turn")
    if created:
        await publish_mandate(ctx, mandate)

    async def try_lock() -> bool:
        return await ctx.store.transact(lambda c: mandates.try_lock(c, doc_id, mandate.id))

    position = await ctx.lock_waits.acquire(doc_id, mandate.id, try_lock, LOCK_WAIT_S)
    if position is not None:
        raise BlackboardError(BUSY, "another agent is editing this document", {"doc_id": doc_id, "queue_position": position})

    receipt = await ctx.store.transact(lambda c: mandates.add_receipt(c, mandate_id=mandate.id, doc_id=doc_id, ops=ops, note=note))
    requester = await ctx.store.read(lambda c: users.get(c, call.uid))
    client = ctx.doc_client()
    try:
        await client.agent_presence(
            doc_id,
            {"agentId": call.uid, "label": _agent_label(requester.display_name if requester else None), "status": "writing", "blockId": ops[0]["blockId"]},
        )
    except BlackboardError as exc:
        logger.debug("blackboard: agent presence on %s failed: %s", doc_id, exc.message)

    scope = mandate.scope
    body = {
        "mandateId": mandate.id,
        "author": {"id": call.uid, "kind": "agent"},
        "mode": mandate.permission_mode,
        "allowed": {"blockFrom": scope["block_from"], "blockTo": scope["block_to"]} if scope.get("block_from") else None,
        "ops": ops,
    }
    try:
        result = await client.edits(doc_id, body)
    except BlackboardError as exc:
        await ctx.store.transact(
            lambda c: (
                mandates.finish_receipt(c, receipt.id, applied=False, error=exc.to_dict()),
                mandates.touch(c, mandate.id),
            )
        )
        raise BlackboardError(exc.code, exc.message, {**exc.details, "mandate_id": mandate.id, "receipt_id": receipt.id}) from exc

    def applied(conn: sqlite3.Connection):
        mandates.touch(conn, mandate.id)
        return mandates.finish_receipt(
            conn,
            receipt.id,
            applied=True,
            before=result.get("before"),
            after=result.get("after"),
            suggestion_ids=result.get("suggestionIds"),
            version_id=result.get("versionId"),
        )

    first = await ctx.store.transact(lambda c: (applied(c), _applied_count(c, mandate.id) == 1)[1])
    await ctx.hub.publish(p.EV_SUGGESTIONS_CHANGED, {"workspace_id": doc.workspace_id, "doc_id": doc_id}, workspace_id=doc.workspace_id)
    await publish_mandate(ctx, mandate)
    if first and mandate.origin == "workspace_session":
        # The request stays in the person's session; the workspace sees that their agent is at work.
        from jiuwenswarm.extensions.blackboard.host.api.feed import coded, post_chat

        await post_chat(
            ctx,
            workspace_id=doc.workspace_id,
            author_id=mandate.requester_id,
            author_kind="system",
            kind="notice",
            body=coded("session_edit", doc_id=doc_id, doc_title=doc.title),
            mandate_id=mandate.id,
        )
    return {
        "mandate_id": mandate.id,
        "receipt_id": receipt.id,
        "changed": bool(result.get("changed")),
        "suggestion_ids": result.get("suggestionIds", []),
        "blocks_after": [{"id": b["id"], "digest": b["digest"]} for b in result.get("after", [])],
    }


def _applied_count(conn: sqlite3.Connection, mandate_id: str) -> int:
    row = conn.execute("SELECT COUNT(*) FROM receipts WHERE mandate_id = ? AND status = 'applied'", (mandate_id,)).fetchone()
    return int(row[0])
