"""Comment threads on passages of a document (milestone 5).

An anchor is ``{block_id, block_to, digest, start, end, quote, offset, length, status}``: the first
and last block of the selection, the first block's digest, the selection's ends as Yjs relative
positions (base64, made in the browser), the selected text, where it starts in the first block, and
whether it still fits (``ok``), changed underneath (``drifted``) or could not be found (``orphaned``).
The document service resolves anchors against the live document whenever threads are listed.

``@jiuwen`` in a comment by an editor or owner gives the agent a task limited to the passage, or to
the whole document with the scope switch.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import replace
from typing import Any

from jiuwenswarm.extensions.blackboard.common import mentions as mention
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, FORBIDDEN, BlackboardError, invalid, not_found
from jiuwenswarm.extensions.blackboard.common.roles import role_at_least
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api import dispatch
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.feed import coded, comment_view, post_comment, publish_thread
from jiuwenswarm.extensions.blackboard.host.api.mandates import finish_mandate
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.store import comments, docs, mandates, users
from jiuwenswarm.extensions.blackboard.host.store.models import Comment, Doc, Thread

logger = logging.getLogger(__name__)

MAX_BODY = 4000
# The selected text is kept whole, to find the passage again; this only bounds the request.
MAX_QUOTE = 100_000
MAX_POSITION = 2048
ANCHOR_STATUSES = ("ok", "drifted", "orphaned")


def body_text(value: Any) -> str:
    """A comment or message body: line breaks kept, 1 to 4000 characters."""
    if not isinstance(value, str) or not value.strip():
        raise invalid("body is required", field="body")
    text = value.strip()
    if len(text) > MAX_BODY:
        raise invalid(f"body must be at most {MAX_BODY} characters", field="body")
    return text


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise invalid(f"anchor.{field} is required", field=f"anchor.{field}")
    return value.strip()


def _anchor(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise invalid("anchor is {block_id, start, end, quote, offset, length}", field="anchor")
    block_id = _id(value.get("block_id"), "block_id")
    block_to = _id(value.get("block_to"), "block_to") if value.get("block_to") else block_id
    positions = {}
    for end in ("start", "end"):
        position = value.get(end)
        if not isinstance(position, str) or not position or len(position) > MAX_POSITION:
            raise invalid(f"anchor.{end} is a relative position", field=f"anchor.{end}")
        positions[end] = position
    quote = value.get("quote")
    if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE:
        raise invalid(f"anchor.quote is the selected text, at most {MAX_QUOTE} characters", field="anchor.quote")
    numbers = {}
    for field in ("offset", "length"):
        number = value.get(field, 0)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            raise invalid(f"anchor.{field} is a number", field=f"anchor.{field}")
        numbers[field] = number
    digest = value.get("digest")
    return {
        "block_id": block_id,
        "block_to": block_to,
        "digest": digest if isinstance(digest, str) and len(digest) <= 128 else None,
        **positions,
        "quote": quote,
        **numbers,
        "status": "ok",
    }


def _scope(thread: Thread, whole_document: bool) -> dict[str, Any]:
    if whole_document:
        return {"doc_id": thread.doc_id}
    anchor = thread.anchor
    return {"doc_id": thread.doc_id, "block_from": anchor["block_id"], "block_to": anchor.get("block_to") or anchor["block_id"]}


def _writable_doc(conn: sqlite3.Connection, user_id: str, doc_id: str) -> tuple[Doc, str]:
    doc = docs.get(conn, doc_id)
    if doc is None:
        raise not_found("no such document", doc_id=doc_id)
    workspace, member = require_member(conn, user_id, doc.workspace_id, "commenter")
    if workspace.archived_at is not None or doc.archived_at is not None:
        raise BlackboardError(CONFLICT, "the document or its workspace is archived", {"doc_id": doc_id})
    return doc, member.role


def _thread(conn: sqlite3.Connection, thread_id: str) -> Thread:
    thread = comments.get_thread(conn, thread_id)
    if thread is None:
        raise not_found("no such thread", thread_id=thread_id)
    return thread


async def _task(
    ctx: HostContext, thread: Thread, comment: Comment, *, role: str, user_id: str, whole_document: bool, session_id: str | None
) -> str | None:
    """A mention of the agent: a task for an editor or owner, a note for anyone else."""
    if not mention.names_agent(comment.body, comment.mentions):
        return None
    if not role_at_least(role, "editor"):
        await post_comment(ctx, thread, author_id=user_id, author_kind="system", body=coded("agent_forbidden"))
        return None
    mandate = await dispatch.begin(
        ctx,
        workspace_id=thread.workspace_id,
        origin="comment",
        origin_ref={"thread_id": thread.id, "comment_id": comment.id},
        requester_id=user_id,
        instruction=mention.without_agent(comment.body),
        scope=_scope(thread, whole_document),
        reply_target={"kind": "thread", "id": thread.id},
        session_id=session_id,
    )
    await ctx.store.transact(lambda c: comments.set_mandate(c, comment.id, mandate.id))
    return mandate.id


def _session(params: dict[str, Any]) -> str | None:
    value = params.get("session_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


@method(p.COMMENT_CREATE)
async def comment_create(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")
    anchor = _anchor(call.params.get("anchor"))
    body = body_text(call.params.get("body"))
    mentions = mention.parse(call.params.get("mentions"))
    whole_document = call.params.get("scope_switch") is True

    def work(conn: sqlite3.Connection) -> tuple[Thread, Comment, str]:
        doc, role = _writable_doc(conn, call.uid, doc_id)
        thread = comments.create_thread(conn, workspace_id=doc.workspace_id, doc_id=doc.id, anchor=anchor, created_by=call.uid)
        comment = comments.add_comment(
            conn, thread_id=thread.id, author_id=call.uid, author_kind="person", body=body, mentions=mentions, scope_switch=whole_document
        )
        return thread, comment, role

    thread, comment, role = await call.ctx.store.transact(work)
    mandate_id = await _task(
        call.ctx, thread, comment, role=role, user_id=call.uid, whole_document=whole_document, session_id=_session(call.params)
    )
    await publish_thread(call.ctx, thread)
    return {"thread": thread.to_dict(), "comment": {**comment.to_dict(call.user.display_name), "mandate_id": mandate_id}}


@method(p.COMMENT_REPLY)
async def comment_reply(call: Call) -> dict[str, Any]:
    thread_id = v.required_str(call.params, "thread_id")
    body = body_text(call.params.get("body"))
    mentions = mention.parse(call.params.get("mentions"))
    whole_document = call.params.get("scope_switch") is True

    def work(conn: sqlite3.Connection) -> tuple[Thread, Comment, str]:
        thread = _thread(conn, thread_id)
        _, role = _writable_doc(conn, call.uid, thread.doc_id)
        if thread.resolved_at is not None:
            raise BlackboardError(CONFLICT, "the thread is resolved; reopen it first", {"thread_id": thread_id})
        comment = comments.add_comment(
            conn, thread_id=thread.id, author_id=call.uid, author_kind="person", body=body, mentions=mentions, scope_switch=whole_document
        )
        return thread, comment, role

    thread, comment, role = await call.ctx.store.transact(work)
    mandate_id = await _task(
        call.ctx, thread, comment, role=role, user_id=call.uid, whole_document=whole_document, session_id=_session(call.params)
    )
    await publish_thread(call.ctx, thread)
    return {"comment": {**comment.to_dict(call.user.display_name), "mandate_id": mandate_id}}


@method(p.COMMENT_EDIT)
async def comment_edit(call: Call) -> dict[str, Any]:
    """People edit their own comments; the text of a comment that started a task is not changed."""
    comment_id = v.required_str(call.params, "comment_id")
    body = body_text(call.params.get("body"))

    def work(conn: sqlite3.Connection) -> tuple[Thread, dict[str, Any]]:
        comment = comments.get_comment(conn, comment_id)
        if comment is None:
            raise not_found("no such comment", comment_id=comment_id)
        thread = _thread(conn, comment.thread_id)
        _writable_doc(conn, call.uid, thread.doc_id)
        if comment.author_kind != "person" or comment.author_id != call.uid:
            raise BlackboardError(FORBIDDEN, "only the author may edit a comment", {"comment_id": comment_id})
        if comment.mandate_id is not None:
            raise BlackboardError(CONFLICT, "this comment gave the agent a task", {"comment_id": comment_id})
        comments.edit_comment(conn, comment_id, body)
        edited = comments.get_comment(conn, comment_id)
        assert edited is not None
        return thread, comment_view(conn, edited)

    thread, comment = await call.ctx.store.transact(work)
    await publish_thread(call.ctx, thread)
    return {"comment": comment}


async def _set_resolved(call: Call, resolved: bool) -> dict[str, Any]:
    thread_id = v.required_str(call.params, "thread_id")

    def work(conn: sqlite3.Connection) -> tuple[Thread, list[str]]:
        thread = _thread(conn, thread_id)
        _writable_doc(conn, call.uid, thread.doc_id)
        if (thread.resolved_at is not None) == resolved:
            raise BlackboardError(CONFLICT, f"the thread is already {'resolved' if resolved else 'open'}", {"thread_id": thread_id})
        comments.set_resolved(conn, thread_id, call.uid if resolved else None)
        waiting = [m.id for m in mandates.for_thread(conn, thread_id, ("queued",))] if resolved else []
        updated = comments.get_thread(conn, thread_id)
        assert updated is not None
        return updated, waiting

    thread, waiting = await call.ctx.store.transact(work)
    # A task still waiting for the document is no longer wanted once the thread is resolved.
    for mandate_id in waiting:
        await finish_mandate(call.ctx, mandate_id, "cancelled", "already_handled")
    await publish_thread(call.ctx, thread)
    return {"thread": thread.to_dict()}


@method(p.COMMENT_RESOLVE)
async def comment_resolve(call: Call) -> dict[str, Any]:
    return await _set_resolved(call, True)


@method(p.COMMENT_REOPEN)
async def comment_reopen(call: Call) -> dict[str, Any]:
    return await _set_resolved(call, False)


@method(p.COMMENT_LIST)
async def comment_list(call: Call) -> dict[str, Any]:
    """The document's threads with their comments, their anchors checked against the live document."""
    doc_id = v.required_str(call.params, "doc_id")
    include_resolved = call.params.get("include_resolved") is True

    def work(conn: sqlite3.Connection) -> list[Thread]:
        doc = docs.get(conn, doc_id)
        if doc is None:
            raise not_found("no such document", doc_id=doc_id)
        require_member(conn, call.uid, doc.workspace_id, "viewer")
        return comments.threads_for_doc(conn, doc_id, include_resolved=include_resolved)

    threads = await call.ctx.store.read(work)
    threads, positions = await _resolve_anchors(call.ctx, doc_id, threads)

    def details(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        by_thread = comments.comments_for(conn, [t.id for t in threads])
        everyone = {c.author_id for rows in by_thread.values() for c in rows}
        names = users.names(conn, everyone | {t.created_by for t in threads})
        mandate_ids = {c.mandate_id for rows in by_thread.values() for c in rows if c.mandate_id}
        statuses = {m: getattr(mandates.get(conn, m), "status", None) for m in mandate_ids}
        return [
            {
                **t.to_dict(),
                # Where the passage starts now, for ordering threads as the document reads.
                "position": positions.get(t.id),
                "created_by_name": names.get(t.created_by),
                "comments": [
                    {**c.to_dict(names.get(c.author_id)), "mandate_status": statuses.get(c.mandate_id or "")}
                    for c in by_thread.get(t.id, [])
                ],
            }
            for t in threads
        ]

    return {"doc_id": doc_id, "threads": await call.ctx.store.read(details)}


async def _resolve_anchors(ctx: HostContext, doc_id: str, threads: list[Thread]) -> tuple[list[Thread], dict[str, int]]:
    """Check open threads' anchors against the document; store what moved or changed status."""
    open_threads = [t for t in threads if t.resolved_at is None]
    positions: dict[str, int] = {}
    if not open_threads or ctx.docs is None or not ctx.docs.running:
        return threads, positions
    try:
        result = await ctx.doc_client().resolve_anchors(doc_id, [t.anchor for t in open_threads])
    except BlackboardError as exc:
        logger.warning("blackboard: resolving anchors of %s failed: %s", doc_id, exc.message)
        return threads, positions
    resolved = result.get("anchors") or []
    changed: dict[str, dict[str, Any]] = {}
    for thread, found in zip(open_threads, resolved):
        if not isinstance(found, dict) or found.get("status") not in ANCHOR_STATUSES:
            continue
        if isinstance(found.get("from"), int):
            positions[thread.id] = found["from"]
        anchor = {**thread.anchor, "status": found["status"]}
        for key in ("block_id", "block_to", "start", "end", "offset", "digest"):
            if found.get(key) is not None:
                anchor[key] = found[key]
        if anchor != thread.anchor:
            changed[thread.id] = anchor

    if changed:
        await ctx.store.transact(lambda c: [comments.set_anchor(c, tid, a) for tid, a in changed.items()])
    return [replace(t, anchor=changed[t.id]) if t.id in changed else t for t in threads], positions
