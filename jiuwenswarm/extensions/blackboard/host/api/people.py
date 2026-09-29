"""People on the host (milestone 8): replacing one's own member token, and the operator turning a
person's access to the whole host off and on again.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, FORBIDDEN, BlackboardError, invalid, not_found
from jiuwenswarm.extensions.blackboard.common.tokens import hash_token, new_member_token
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.store import users, workspaces

logger = logging.getLogger(__name__)

STATUSES = ("active", "disabled")


@method(p.ME_ROTATE_TOKEN)
async def me_rotate_token(call: Call) -> dict[str, Any]:
    """A new member token for the caller; the old one stops working at once, and connections made
    with it are closed. Only the person's own jiuwenswarm calls this, and keeps the new token."""
    token = new_member_token()
    await call.ctx.store.transact(lambda c: users.set_token_hash(c, call.uid, hash_token(token)))
    await call.ctx.hub.close_user(call.uid, "token replaced")
    logger.info("blackboard: %s replaced their member token", call.uid)
    return {"token": token}


@method(p.USER_LIST)
async def user_list(call: Call) -> dict[str, Any]:
    _operator(call)

    def work(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        return [
            {**u.to_dict(), "workspaces": len(workspaces.list_for_user(conn, u.id))} for u in users.list_all(conn)
        ]

    return {"users": await call.ctx.store.read(work)}


@method(p.USER_SET_STATUS)
async def user_set_status(call: Call) -> dict[str, Any]:
    """Disabling someone ends everything at once: their calls, their events, their open documents,
    and a shared bot's reads for them. Their memberships stay, so enabling them again restores it."""
    _operator(call)
    user_id = v.required_str(call.params, "user_id")
    status = call.params.get("status")
    if status not in STATUSES:
        raise invalid("status is active or disabled", field="status")
    if user_id == call.uid:
        raise BlackboardError(CONFLICT, "the operator cannot disable themselves")

    def work(conn: sqlite3.Connection) -> list[str]:
        target = users.get(conn, user_id)
        if target is None:
            raise not_found("no such user on this host", user_id=user_id)
        users.set_status(conn, user_id, status)
        return [w.id for w, _ in workspaces.list_for_user(conn, user_id)]

    workspace_ids = await call.ctx.store.transact(work)
    if status == "disabled":
        await call.ctx.hub.close_user(user_id, "disabled")
    from jiuwenswarm.extensions.blackboard.host.api.documents import recheck_docs

    for workspace_id in workspace_ids:
        if status == "disabled":
            await recheck_docs(call.ctx, workspace_id, user_id, revoke=True)
        await call.ctx.hub.publish(p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
    logger.info("blackboard: %s set %s to %s", call.uid, user_id, status)
    user = await call.ctx.store.read(lambda c: users.get(c, user_id))
    assert user is not None
    return {"user": user.to_dict()}


def _operator(call: Call) -> None:
    if call.user is None or not call.user.is_operator:
        raise BlackboardError(FORBIDDEN, "only the host's operator manages people on the host")
