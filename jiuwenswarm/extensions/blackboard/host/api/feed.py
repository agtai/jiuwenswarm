"""Posting to the workspace chat and to comment threads, with the events members need.

People's messages and the agent's replies are plain text. Notices and summaries the host writes are
JSON with a ``code`` and its parameters, so each browser shows them in its own language; the agent
never reads them.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.store import chat, comments, users
from jiuwenswarm.extensions.blackboard.host.store.models import Comment, Thread

# How much of an agent's thread reply the chat's summary line quotes.
SUMMARY_EXCERPT = 120


def coded(code: str, **params: Any) -> str:
    return json.dumps({"code": code, **params}, ensure_ascii=False)


def comment_view(conn: sqlite3.Connection, comment: Comment) -> dict[str, Any]:
    names = users.names(conn, [comment.author_id])
    return comment.to_dict(names.get(comment.author_id))


async def post_chat(
    ctx: HostContext,
    *,
    workspace_id: str,
    author_id: str,
    author_kind: str,
    kind: str,
    body: str,
    mentions: list[dict[str, str]] | None = None,
    mandate_id: str | None = None,
    decision_id: str | None = None,
) -> dict[str, Any]:
    def work(conn: sqlite3.Connection) -> dict[str, Any]:
        message = chat.add(
            conn,
            workspace_id=workspace_id,
            author_id=author_id,
            author_kind=author_kind,
            kind=kind,
            body=body,
            mentions=mentions,
            mandate_id=mandate_id,
            decision_id=decision_id,
        )
        return message.to_dict(users.names(conn, [author_id]).get(author_id))

    message = await ctx.store.transact(work)
    await publish_chat(ctx, workspace_id, message)
    return message


async def publish_chat(ctx: HostContext, workspace_id: str, message: dict[str, Any]) -> None:
    await ctx.hub.publish(p.EV_CHAT_MESSAGE, {"workspace_id": workspace_id, "message": message}, workspace_id=workspace_id)


async def post_comment(
    ctx: HostContext,
    thread: Thread,
    *,
    author_id: str,
    author_kind: str,
    body: str,
    mandate_id: str | None = None,
    decision_id: str | None = None,
) -> dict[str, Any]:
    def work(conn: sqlite3.Connection) -> dict[str, Any]:
        comment = comments.add_comment(
            conn,
            thread_id=thread.id,
            author_id=author_id,
            author_kind=author_kind,
            body=body,
            mandate_id=mandate_id,
            decision_id=decision_id,
        )
        return comment_view(conn, comment)

    comment = await ctx.store.transact(work)
    await publish_thread(ctx, thread)
    return comment


async def publish_thread(ctx: HostContext, thread: Thread) -> None:
    await ctx.hub.publish(
        p.EV_THREAD_UPDATED,
        {"workspace_id": thread.workspace_id, "doc_id": thread.doc_id, "thread_id": thread.id},
        workspace_id=thread.workspace_id,
    )


def excerpt(text: str, limit: int = SUMMARY_EXCERPT) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."
