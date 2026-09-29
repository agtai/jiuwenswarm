"""The workspace chat (milestone 5).

``@jiuwen`` in a message by an editor or owner gives the agent a task on the whole workspace; the
agent answers in the chat. Anyone from commenter up may post.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from jiuwenswarm.extensions.blackboard.common import mentions as mention
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, BlackboardError
from jiuwenswarm.extensions.blackboard.common.roles import role_at_least
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api import dispatch
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.comments import body_text
from jiuwenswarm.extensions.blackboard.host.api.feed import coded, post_chat, publish_chat
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.store import chat, users

PAGE = 50


@method(p.CHAT_POST)
async def chat_post(call: Call) -> dict[str, Any]:
    workspace_id = v.required_str(call.params, "workspace_id")
    body = body_text(call.params.get("body"))
    mentions = mention.parse(call.params.get("mentions"))
    session_id = call.params.get("session_id") if isinstance(call.params.get("session_id"), str) else None

    def work(conn: sqlite3.Connection) -> tuple[dict[str, Any], str]:
        workspace, member = require_member(conn, call.uid, workspace_id, "commenter")
        if workspace.archived_at is not None:
            raise BlackboardError(CONFLICT, "the workspace is archived", {"workspace_id": workspace_id})
        message = chat.add(
            conn, workspace_id=workspace_id, author_id=call.uid, author_kind="person", kind="message", body=body, mentions=mentions
        )
        return message.to_dict(users.names(conn, [call.uid]).get(call.uid)), member.role

    message, role = await call.ctx.store.transact(work)
    mandate_id = None
    if mention.names_agent(body, mentions) and role_at_least(role, "editor"):
        mandate = await dispatch.begin(
            call.ctx,
            workspace_id=workspace_id,
            origin="workspace_chat",
            origin_ref={"message_id": message["id"]},
            requester_id=call.uid,
            instruction=mention.without_agent(body),
            scope={},
            reply_target={"kind": "chat"},
            session_id=session_id.strip() if session_id and session_id.strip() else None,
        )
        mandate_id = mandate.id
        await call.ctx.store.transact(lambda c: chat.set_mandate(c, message["id"], mandate.id))
        message = {**message, "mandate_id": mandate_id}
    await publish_chat(call.ctx, workspace_id, message)
    if mention.names_agent(body, mentions) and mandate_id is None:
        await post_chat(
            call.ctx,
            workspace_id=workspace_id,
            author_id=call.uid,
            author_kind="system",
            kind="notice",
            body=coded("agent_forbidden"),
        )
    return {"message": message}


@method(p.CHAT_LIST)
async def chat_list(call: Call) -> dict[str, Any]:
    """A page of messages, oldest first; `before` a message id pages further back."""
    workspace_id = v.required_str(call.params, "workspace_id")
    limit = v.int_in_range(call.params.get("limit"), "limit", low=1, high=100, default=PAGE)
    before = call.params.get("before") if isinstance(call.params.get("before"), str) else None

    def work(conn: sqlite3.Connection) -> dict[str, Any]:
        require_member(conn, call.uid, workspace_id, "viewer")
        rows = chat.page(conn, workspace_id, before=before, limit=limit + 1)
        more = len(rows) > limit
        rows = rows[1:] if more else rows
        names = users.names(conn, [m.author_id for m in rows])
        return {"messages": [m.to_dict(names.get(m.author_id)) for m in rows], "has_more": more}

    return {"workspace_id": workspace_id, **await call.ctx.store.read(work)}
