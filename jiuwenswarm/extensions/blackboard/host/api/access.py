"""Role checks. Every method handler runs one of these inside its transaction."""

from __future__ import annotations

import sqlite3

from jiuwenswarm.extensions.blackboard.common.errors import FORBIDDEN, NOT_MEMBER, BlackboardError, not_found
from jiuwenswarm.extensions.blackboard.common.roles import role_at_least
from jiuwenswarm.extensions.blackboard.host.store import workspaces
from jiuwenswarm.extensions.blackboard.host.store.models import Member, Workspace


def require_member(
    conn: sqlite3.Connection,
    user_id: str,
    workspace_id: str,
    at_least: str = "viewer",
) -> tuple[Workspace, Member]:
    workspace = workspaces.get(conn, workspace_id)
    if workspace is None:
        raise not_found("no such workspace", workspace_id=workspace_id)
    member = workspaces.membership(conn, workspace_id, user_id)
    if member is None:
        raise BlackboardError(NOT_MEMBER, "you are not a member of this workspace", {"workspace_id": workspace_id})
    if not role_at_least(member.role, at_least):
        raise BlackboardError(
            FORBIDDEN,
            f"this needs the {at_least} role or higher; you are {member.role}",
            {"workspace_id": workspace_id, "required": at_least, "role": member.role},
        )
    return workspace, member
