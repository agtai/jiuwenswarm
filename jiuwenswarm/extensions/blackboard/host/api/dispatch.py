"""Mandates from a comment or the chat (milestone 5): the host offers each turn to the requester's
own jiuwenswarm, which picks it up, runs it in a workspace session and reports how it ended.

A turn goes: ``mark_dispatched`` and a ``blackboard.mandate.run`` event to the requester; the
dispatcher calls ``blackboard.mandate.claim`` (the host hands over the prompt's material and the turn
id), runs the turn, and calls ``blackboard.mandate.report``. The agent's final answer becomes its
reply in the thread or the chat. A question the agent asked in the turn leaves the mandate waiting
for an answer; the accepted answer starts the next turn in the same session.

Comment mandates hold their document from the start, so a second one on the same document waits in
a queue; chat mandates take documents as they edit them, like workspace-session mandates.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from jiuwenswarm.extensions.blackboard.common import mentions as mention
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, FORBIDDEN, BlackboardError, invalid, not_found
from jiuwenswarm.extensions.blackboard.common.roles import role_at_least
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.feed import coded, excerpt, post_chat, post_comment
from jiuwenswarm.extensions.blackboard.host.api.mandates import finish_mandate, publish_mandate
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.store import chat, comments, decisions, docs, mandates, users, workspaces
from jiuwenswarm.extensions.blackboard.host.store.models import Mandate
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso

logger = logging.getLogger(__name__)

# At most this many comment mandates wait for one document.
MAX_QUEUE = 20
# An offered turn nobody picked up fails after this long (the requester's jiuwenswarm is off).
CLAIM_TIMEOUT_S = 600.0
# A picked-up turn with no report becomes Unknown after this long; the dispatcher gives up at 540 s.
# BB_TURN_TIMEOUT_S shortens it for the end-to-end checks.
TURN_TIMEOUT_S = float(os.environ.get("BB_TURN_TIMEOUT_S") or 600.0)
# The chat context of a chat mandate's turn: people's messages since the agent's last turn.
CHAT_CONTEXT_MESSAGES = 40
CHAT_CONTEXT_CHARS = 8000
INSTRUCTIONS_CHARS = 12000
# A longer selection is left out of the prompt: the passage, which is in it anyway, is enough.
QUOTE_IN_PROMPT = 2000
MAX_REPLY = 8000
NO_INSTRUCTION = "(no instruction given)"


def _ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="milliseconds")


# ---- starting ----


async def begin(
    ctx: HostContext,
    *,
    workspace_id: str,
    origin: str,
    origin_ref: dict[str, Any],
    requester_id: str,
    instruction: str,
    scope: dict[str, Any],
    reply_target: dict[str, Any],
    session_id: str | None,
) -> Mandate:
    """Record a comment or chat mandate; a comment mandate whose document is busy waits its turn."""

    def work(conn: sqlite3.Connection) -> Mandate:
        fields = {
            "workspace_id": workspace_id,
            "origin": origin,
            "origin_ref": origin_ref,
            "requester_id": requester_id,
            "session_id": session_id,
            "instruction": instruction or NO_INSTRUCTION,
            "scope": scope,
            "reply_target": reply_target,
        }
        if origin == "comment":
            doc_id = scope["doc_id"]
            waiting = mandates.queued_for_doc(conn, doc_id)
            if waiting or mandates.lock_holder(conn, doc_id) is not None:
                if len(waiting) >= MAX_QUEUE:
                    raise BlackboardError("queue_full", "too many agent tasks wait for this document", {"doc_id": doc_id})
                return mandates.create(conn, status="queued", **fields)
            mandate = mandates.create(conn, status="running", **fields)
            mandates.try_lock(conn, doc_id, mandate.id)
        else:
            mandate = mandates.create(conn, status="running", **fields)
        mandates.mark_dispatched(conn, mandate.id)
        found = mandates.get(conn, mandate.id)
        assert found is not None
        return found

    mandate = await ctx.store.transact(work)
    if mandate.status == "running":
        await offer(ctx, mandate)
    await publish_mandate(ctx, mandate)
    return mandate


async def offer(ctx: HostContext, mandate: Mandate) -> None:
    """Tell the requester's jiuwenswarm there is a turn to run; it claims it to get the details."""
    workspace = await ctx.store.read(lambda c: workspaces.get(c, mandate.workspace_id))
    await ctx.hub.publish(
        p.EV_MANDATE_RUN,
        {
            "mandate_id": mandate.id,
            "workspace_id": mandate.workspace_id,
            "workspace_title": workspace.title if workspace else "",
            "session_id": mandate.session_id,
        },
        user_ids=[mandate.requester_id],
    )


async def start_queued(ctx: HostContext, doc_ids: list[str]) -> None:
    """Start the next comment mandate waiting for each document that became free."""
    for doc_id in doc_ids:

        def work(conn: sqlite3.Connection, doc_id: str = doc_id) -> tuple[Mandate | None, list[Mandate]]:
            dropped: list[Mandate] = []
            if mandates.lock_holder(conn, doc_id) is not None:
                return None, dropped
            for queued in mandates.queued_for_doc(conn, doc_id):
                thread = comments.get_thread(conn, str(queued.origin_ref.get("thread_id", "")))
                if thread is None or thread.resolved_at is not None:
                    dropped.append(mandates.set_status(conn, queued.id, "cancelled", "already_handled"))
                    continue
                if mandates.try_lock(conn, doc_id, queued.id):
                    mandates.set_status(conn, queued.id, "running")
                    mandates.mark_dispatched(conn, queued.id)
                    return mandates.get(conn, queued.id), dropped
            return None, dropped

        started, dropped = await ctx.store.transact(work)
        for mandate in dropped:
            await publish_mandate(ctx, mandate)
        if started is not None:
            await offer(ctx, started)
            await publish_mandate(ctx, started)


async def after_finish(ctx: HostContext, before: Mandate, after: Mandate, released: list[str]) -> None:
    """What follows a mandate's end: stop a running turn, close its question, tell the workspace,
    and let the next comment mandate have the documents."""
    if before.origin in mandates.DISPATCHED_ORIGINS:
        if after.status == "cancelled" and before.status == "running" and before.claimed_at:
            await ctx.hub.publish(
                p.EV_MANDATE_STOP, {"mandate_id": after.id, "turn_id": before.turn_id}, user_ids=[after.requester_id]
            )
        open_decision = await ctx.store.read(lambda c: decisions.open_for_mandate(c, after.id))
        if open_decision is not None:
            await ctx.store.transact(lambda c: decisions.cancel(c, open_decision.id))
            await publish_decision(ctx, open_decision.workspace_id, open_decision.id, "cancelled")
        if after.status in ("failed", "unknown", "cancelled") and before.status != "queued":
            await _tell(ctx, after)
    if released:
        await start_queued(ctx, released)


async def _tell(ctx: HostContext, mandate: Mandate) -> None:
    """A mandate that did not finish normally leaves a line where its request was made."""
    code = {"failed": "agent_failed", "unknown": "agent_unknown", "cancelled": "agent_cancelled"}[mandate.status]
    reason = mandate.status_reason or ""
    params: dict[str, Any] = {"reason": reason}
    if reason.startswith("cancelled by "):
        by = reason.removeprefix("cancelled by ")
        params["by"] = (await ctx.store.read(lambda c: users.names(c, [by]))).get(by, "")
    body = coded(code, **params)
    if mandate.origin == "comment":
        thread = await ctx.store.read(lambda c: comments.get_thread(c, str(mandate.origin_ref.get("thread_id", ""))))
        if thread is not None:
            await post_comment(ctx, thread, author_id=mandate.requester_id, author_kind="system", body=body, mandate_id=mandate.id)
    if mandate.status in ("failed", "unknown") or mandate.origin == "workspace_chat":
        await post_chat(
            ctx,
            workspace_id=mandate.workspace_id,
            author_id=mandate.requester_id,
            author_kind="system",
            kind="notice",
            body=body,
            mandate_id=mandate.id,
        )


async def publish_decision(ctx: HostContext, workspace_id: str, decision_id: str, status: str) -> None:
    await ctx.hub.publish(
        p.EV_DECISION_UPDATED,
        {"workspace_id": workspace_id, "decision_id": decision_id, "status": status},
        workspace_id=workspace_id,
    )


async def continue_with_answer(ctx: HostContext, mandate_id: str, answer: dict[str, Any]) -> None:
    """An accepted answer: the next turn starts with it, now or when the current turn ends."""

    def work(conn: sqlite3.Connection) -> Mandate | None:
        mandate = mandates.get(conn, mandate_id)
        if mandate is None or mandate.status not in ("running", "waiting_for_answer"):
            return None
        mandates.set_answer(conn, mandate_id, answer)
        if mandate.status == "waiting_for_answer":
            mandates.set_status(conn, mandate_id, "running")
            mandates.mark_dispatched(conn, mandate_id)
            return mandates.get(conn, mandate_id)
        return None

    restarted = await ctx.store.transact(work)
    if restarted is not None:
        await offer(ctx, restarted)
        await publish_mandate(ctx, restarted)


# ---- the dispatcher's calls ----


def _own(conn: sqlite3.Connection, call: Call, mandate_id: str) -> Mandate:
    mandate = mandates.get(conn, mandate_id)
    if mandate is None:
        raise not_found("no such mandate", mandate_id=mandate_id)
    if mandate.requester_id != call.uid:
        raise BlackboardError(FORBIDDEN, "this mandate belongs to someone else", {"mandate_id": mandate_id})
    return mandate


@method(p.MANDATE_PENDING)
async def mandate_pending(call: Call) -> dict[str, Any]:
    """Turns offered to the caller's jiuwenswarm while it was away."""

    def work(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        runs = []
        for m in mandates.pending_for(conn, call.uid):
            workspace = workspaces.get(conn, m.workspace_id)
            runs.append(
                {
                    "mandate_id": m.id,
                    "workspace_id": m.workspace_id,
                    "workspace_title": workspace.title if workspace else "",
                    "session_id": m.session_id,
                }
            )
        return runs

    return {"runs": await call.ctx.store.read(work)}


@method(p.MANDATE_CLAIM)
async def mandate_claim(call: Call) -> dict[str, Any]:
    """Pick up the offered turn: the caller runs it in `session_id`; returns the turn's material."""
    mandate_id = v.required_str(call.params, "mandate_id")
    session_id = v.required_str(call.params, "session_id")

    def check(conn: sqlite3.Connection) -> bool:
        mandate = _own(conn, call, mandate_id)
        member = workspaces.membership(conn, mandate.workspace_id, call.uid)
        return member is not None and role_at_least(member.role, "editor")

    if not await call.ctx.store.read(check):
        # The requester is no longer an editor: the task cannot run.
        await finish_mandate(call.ctx, mandate_id, "failed", "not_an_editor")
        raise BlackboardError(FORBIDDEN, "only editors and owners can give the agent a task", {"mandate_id": mandate_id})

    def work(conn: sqlite3.Connection) -> tuple[Mandate, str, dict[str, Any]]:
        mandate = _own(conn, call, mandate_id)
        if mandate.status != "running" or mandate.claimed_at is not None or mandate.dispatched_at is None:
            raise BlackboardError(CONFLICT, "there is no turn to pick up", {"mandate_id": mandate_id, "status": mandate.status})
        turn_id = mandates.claim(conn, mandate_id, session_id)
        material = _material(conn, mandate)
        # The answer is delivered with this turn; another one arriving later starts the next turn.
        mandates.set_answer(conn, mandate_id, None)
        claimed = mandates.get(conn, mandate_id)
        assert claimed is not None
        return claimed, turn_id, material

    mandate, turn_id, material = await call.ctx.store.transact(work)
    material.update(await _documents(call.ctx, mandate, material))
    return {"mandate": mandate.to_dict(material["requester"]), "turn_id": turn_id, "session_id": session_id, "prompt": material}


def _material(conn: sqlite3.Connection, mandate: Mandate) -> dict[str, Any]:
    """What the store knows for the prompt; documents are read afterwards, outside the transaction."""
    workspace = workspaces.get(conn, mandate.workspace_id)
    names = users.names(conn, [mandate.requester_id])
    material: dict[str, Any] = {
        "requester": names.get(mandate.requester_id, ""),
        "origin": mandate.origin,
        "instruction": mandate.instruction,
        "workspace": {"id": mandate.workspace_id, "title": workspace.title if workspace else "", "name": workspace.name if workspace else ""},
        "docs": [{"id": d.id, "title": d.title, "is_instructions": d.is_instructions} for d in docs.list_for_workspace(conn, mandate.workspace_id)],
        "scope": dict(mandate.scope),
        "answer": mandate.answer,
        "thread": [],
        "chat": [],
    }
    doc_id = mandate.scope.get("doc_id")
    if doc_id:
        doc = docs.get(conn, doc_id)
        material["scope"]["doc_title"] = doc.title if doc else ""
    if mandate.origin == "comment":
        thread_id = str(mandate.origin_ref.get("thread_id", ""))
        thread_comments = comments.comments_for(conn, [thread_id]).get(thread_id, [])
        authors = users.names(conn, [c.author_id for c in thread_comments])
        material["thread"] = [
            {"author": authors.get(c.author_id, ""), "kind": c.author_kind, "body": c.body}
            for c in thread_comments
            if c.author_kind != "system"
        ]
        thread = comments.get_thread(conn, thread_id)
        quote = str(thread.anchor.get("quote", "")) if thread is not None else ""
        if len(quote) <= QUOTE_IN_PROMPT:
            material["quote"] = quote
    elif mandate.origin == "workspace_chat":
        said = [
            m
            for m in chat.said_since(conn, mandate.workspace_id, limit=CHAT_CONTEXT_MESSAGES * 2)
            if not mention.names_agent(m.body, m.mentions)
        ][-CHAT_CONTEXT_MESSAGES:]
        speakers = users.names(conn, [m.author_id for m in said])
        lines: list[str] = []
        total = 0
        for message in reversed(said):
            line = f"{speakers.get(message.author_id, 'Someone')}: {message.body}"
            if total + len(line) > CHAT_CONTEXT_CHARS:
                break
            lines.append(line)
            total += len(line)
        material["chat"] = list(reversed(lines))
        chat.mark_seen(conn, mandate.workspace_id)
    return material


async def _documents(ctx: HostContext, mandate: Mandate, material: dict[str, Any]) -> dict[str, Any]:
    """The instructions document and, for a passage, the passage itself, read from the document service."""
    out: dict[str, Any] = {"instructions_doc": None, "passage": None}
    if ctx.docs is None or not ctx.docs.running:
        return out
    client = ctx.doc_client()
    instructions = next((d for d in material["docs"] if d["is_instructions"]), None)
    if instructions is not None:
        try:
            result = await client.markdown(instructions["id"])
            text = result.get("markdown", "")
            out["instructions_doc"] = {"id": instructions["id"], "title": instructions["title"], "markdown": text[:INSTRUCTIONS_CHARS]}
        except BlackboardError as exc:
            logger.warning("blackboard: reading the instructions of %s failed: %s", mandate.workspace_id, exc.message)
    scope = mandate.scope
    if scope.get("doc_id") and scope.get("block_from"):
        try:
            result = await client.markdown(scope["doc_id"], range_=f"{scope['block_from']}..{scope.get('block_to') or scope['block_from']}")
            out["passage"] = result.get("markdown", "")
        except BlackboardError as exc:
            logger.warning("blackboard: reading the passage of %s failed: %s", mandate.id, exc.message)
    return out


@method(p.MANDATE_REPORT)
async def mandate_report(call: Call) -> dict[str, Any]:
    """How the turn ended: `done` with the agent's final answer, `failed` with a reason, or `unknown`."""
    mandate_id = v.required_str(call.params, "mandate_id")
    turn_id = v.required_str(call.params, "turn_id")
    status = call.params.get("status")
    if status not in ("done", "failed", "unknown"):
        raise invalid("status is done, failed or unknown", field="status")
    text = call.params.get("text") or ""
    if not isinstance(text, str):
        raise invalid("text must be text", field="text")
    text = text.strip()[:MAX_REPLY]
    reason = str(call.params.get("reason") or "")[:300] or None

    def check(conn: sqlite3.Connection) -> tuple[Mandate, bool]:
        mandate = _own(conn, call, mandate_id)
        return mandate, decisions.open_for_mandate(conn, mandate_id) is not None

    mandate, asked = await call.ctx.store.read(check)
    if mandate.status != "running" or mandate.turn_id != turn_id:
        # The mandate was stopped, or this is an older turn's late report.
        return {"mandate_id": mandate_id, "ignored": True, "status": mandate.status}

    if status == "done" and text and not asked:
        await _reply(call.ctx, mandate, text)
    if status == "done" and asked:
        def wait(conn: sqlite3.Connection) -> Mandate:
            return mandates.set_status(conn, mandate_id, "waiting_for_answer")

        waiting = await call.ctx.store.transact(wait)
        await publish_mandate(call.ctx, waiting)
        return {"mandate_id": mandate_id, "status": waiting.status}
    if status == "done" and mandate.answer is not None:
        # An answer was accepted while this turn ran; the next turn starts with it.
        await call.ctx.store.transact(lambda c: mandates.mark_dispatched(c, mandate_id))
        again = await call.ctx.store.read(lambda c: mandates.get(c, mandate_id))
        assert again is not None
        await offer(call.ctx, again)
        return {"mandate_id": mandate_id, "status": again.status}
    if status == "done" and not text and mandate.origin == "comment":
        thread = await call.ctx.store.read(lambda c: comments.get_thread(c, str(mandate.origin_ref.get("thread_id", ""))))
        if thread is not None:
            await post_comment(call.ctx, thread, author_id=mandate.requester_id, author_kind="system", body=coded("agent_done_silently"), mandate_id=mandate.id)
    finished = await finish_mandate(call.ctx, mandate_id, status, reason)
    return {"mandate_id": mandate_id, "status": finished.status}


async def _reply(ctx: HostContext, mandate: Mandate, text: str) -> None:
    """The agent's final answer, where the request was made."""
    if mandate.origin == "comment":

        def lookup(conn: sqlite3.Connection):
            thread = comments.get_thread(conn, str(mandate.origin_ref.get("thread_id", "")))
            doc = docs.get(conn, thread.doc_id) if thread else None
            return thread, doc

        thread, doc = await ctx.store.read(lookup)
        if thread is None:
            return
        await post_comment(ctx, thread, author_id=mandate.requester_id, author_kind="agent", body=text, mandate_id=mandate.id)
        await post_chat(
            ctx,
            workspace_id=mandate.workspace_id,
            author_id=mandate.requester_id,
            author_kind="agent",
            kind="summary",
            body=coded("thread_reply", doc_id=thread.doc_id, doc_title=doc.title if doc else "", thread_id=thread.id, excerpt=excerpt(text)),
            mandate_id=mandate.id,
        )
    elif mandate.origin == "workspace_chat":
        await post_chat(
            ctx,
            workspace_id=mandate.workspace_id,
            author_id=mandate.requester_id,
            author_kind="agent",
            kind="message",
            body=text,
            mandate_id=mandate.id,
        )


@method(p.MANDATE_RESOLVE_UNKNOWN)
async def mandate_resolve_unknown(call: Call) -> dict[str, Any]:
    """An editor says how a mandate that stopped answering really ended, after checking its receipts."""
    mandate_id = v.required_str(call.params, "mandate_id")
    status = call.params.get("status")
    if status not in ("done", "failed"):
        raise invalid("status is done or failed", field="status")

    def check(conn: sqlite3.Connection) -> Mandate:
        mandate = mandates.get(conn, mandate_id)
        if mandate is None:
            raise not_found("no such mandate", mandate_id=mandate_id)
        require_member(conn, call.uid, mandate.workspace_id, "editor")
        if mandate.status != "unknown":
            raise BlackboardError(CONFLICT, f"the mandate is {mandate.status}, not unknown", {"mandate_id": mandate_id})
        return mandate

    await call.ctx.store.read(check)
    finished = await finish_mandate(call.ctx, mandate_id, status, f"resolved by {call.uid}")
    return {"mandate": finished.to_dict()}


# ---- the sweeper ----


async def sweep_dispatched(ctx: HostContext) -> int:
    """Turns nobody picked up fail; picked-up turns that never reported become Unknown."""
    unclaimed = await ctx.store.read(lambda c: mandates.unclaimed_before(c, _ago(CLAIM_TIMEOUT_S)))
    silent = await ctx.store.read(lambda c: mandates.claimed_before(c, _ago(TURN_TIMEOUT_S)))
    for mandate in unclaimed:
        await _sweep_one(ctx, mandate.id, "failed", "not_picked_up")
    for mandate in silent:
        await _sweep_one(ctx, mandate.id, "unknown", "no_result")
    return len(unclaimed) + len(silent)


async def _sweep_one(ctx: HostContext, mandate_id: str, status: str, reason: str) -> None:
    try:
        await finish_mandate(ctx, mandate_id, status, reason)
    except BlackboardError as exc:
        logger.debug("blackboard: sweeping %s failed: %s", mandate_id, exc.message)
