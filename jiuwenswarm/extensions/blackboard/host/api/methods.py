"""The host's RPC methods. Each checks the caller's role inside its transaction."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import (
    CONFLICT,
    DISABLED,
    EXPIRED,
    BlackboardError,
    invalid,
    not_found,
)
from jiuwenswarm.extensions.blackboard.common.roles import INVITE_ROLES, validate_role
from jiuwenswarm.extensions.blackboard.common.tokens import hash_token, new_member_token
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.store import docs, invites, users, workspaces
from jiuwenswarm.extensions.blackboard.host.store.models import Invite, User
from jiuwenswarm.extensions.blackboard.common.clock import now_iso

DEFAULT_INVITE_MINUTES = 7 * 24 * 60
MAX_INVITE_MINUTES = 30 * 24 * 60
MAX_INVITE_USES = 100


@dataclass(frozen=True)
class Call:
    ctx: HostContext
    user: User | None
    params: dict[str, Any]

    @property
    def uid(self) -> str:
        assert self.user is not None
        return self.user.id


Handler = Callable[[Call], Awaitable[dict[str, Any]]]
METHODS: dict[str, Handler] = {}


def method(name: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        METHODS[name] = fn
        return fn

    return register


def _workspace_id(params: dict[str, Any]) -> str:
    return v.required_str(params, "workspace_id")


def _documents():
    # documents.py registers its methods through this module, so it is imported late.
    from jiuwenswarm.extensions.blackboard.host.api import documents

    return documents


def _invite_dict(ctx: HostContext, invite: Invite, now: str) -> dict[str, Any]:
    return {
        "code": invite.code,
        "role": invite.role,
        "created_at": invite.created_at,
        "expires_at": invite.expires_at,
        "max_uses": invite.max_uses,
        "uses": invite.uses,
        "state": invite.state(now),
        "url": ctx.invite_url(invite.code),
    }


# ---- me ----


@method(p.ME)
async def me(call: Call) -> dict[str, Any]:
    rows = await call.ctx.store.read(lambda c: workspaces.list_for_user(c, call.uid))
    assert call.user is not None
    return {
        "user_id": call.user.id,
        "display_name": call.user.display_name,
        "is_operator": call.user.is_operator,
        "workspaces": [w.to_dict(role) for w, role in rows],
        "host": await call.ctx.host_info(),
    }


@method(p.ME_SET_NAME)
async def me_set_name(call: Call) -> dict[str, Any]:
    name = v.display_name(call.params.get("display_name"))

    def work(conn: sqlite3.Connection) -> list[str]:
        users.set_name(conn, call.uid, name)
        return [w.id for w, _ in workspaces.list_for_user(conn, call.uid)]

    workspace_ids = await call.ctx.store.transact(work)
    await call.ctx.hub.publish(p.EV_ME_UPDATED, {}, user_ids=[call.uid])
    for workspace_id in workspace_ids:
        await call.ctx.hub.publish(p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
    return {"display_name": name}


# ---- workspaces ----


@method(p.WORKSPACE_LIST)
async def workspace_list(call: Call) -> dict[str, Any]:
    rows = await call.ctx.store.read(lambda c: workspaces.list_for_user(c, call.uid))
    return {"workspaces": [w.to_dict(role) for w, role in rows]}


@method(p.WORKSPACE_CREATE)
async def workspace_create(call: Call) -> dict[str, Any]:
    name = v.workspace_name(call.params.get("name"))
    title = v.title(call.params.get("title"))

    def work(conn: sqlite3.Connection):
        if workspaces.by_name(conn, name) is not None:
            raise BlackboardError(CONFLICT, f"the handle @bb:{name} is already taken on this host", {"field": "name"})
        return workspaces.create(conn, name=name, title=title, created_by=call.uid)

    workspace = await call.ctx.store.transact(work)
    await _documents().ensure_instructions(call.ctx, workspace.id)
    await call.ctx.hub.publish(p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace.id}, workspace_id=workspace.id)
    return {"workspace": workspace.to_dict("owner")}


@method(p.WORKSPACE_RENAME)
async def workspace_rename(call: Call) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)
    title = v.title(call.params.get("title"))

    def work(conn: sqlite3.Connection) -> None:
        require_member(conn, call.uid, workspace_id, "owner")
        workspaces.rename(conn, workspace_id, title)

    await call.ctx.store.transact(work)
    await call.ctx.hub.publish(p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
    return {"workspace_id": workspace_id, "title": title}


async def _set_archived(call: Call, archived: bool) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)

    def work(conn: sqlite3.Connection) -> None:
        require_member(conn, call.uid, workspace_id, "owner")
        workspaces.set_archived(conn, workspace_id, archived)

    await call.ctx.store.transact(work)
    await _documents().recheck_docs(call.ctx, workspace_id)
    await call.ctx.hub.publish(p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
    return {"workspace_id": workspace_id, "archived": archived}


@method(p.WORKSPACE_ARCHIVE)
async def workspace_archive(call: Call) -> dict[str, Any]:
    return await _set_archived(call, True)


@method(p.WORKSPACE_UNARCHIVE)
async def workspace_unarchive(call: Call) -> dict[str, Any]:
    return await _set_archived(call, False)


@method(p.WORKSPACE_DELETE)
async def workspace_delete(call: Call) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)

    def work(conn: sqlite3.Connection) -> tuple[list[str], list[str]]:
        workspace, _ = require_member(conn, call.uid, workspace_id, "owner")
        if workspace.archived_at is None:
            raise BlackboardError(CONFLICT, "archive the workspace before deleting it", {"workspace_id": workspace_id})
        member_ids = workspaces.member_user_ids(conn, workspace_id)
        doc_ids = docs.ids_for_workspace(conn, workspace_id)
        workspaces.delete(conn, workspace_id)
        return member_ids, doc_ids

    member_ids, doc_ids = await call.ctx.store.transact(work)
    await _documents().delete_workspace_content(call.ctx, workspace_id, doc_ids)
    await call.ctx.hub.publish(
        p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id, "deleted": True}, user_ids=member_ids
    )
    return {"workspace_id": workspace_id, "deleted": True}


# ---- members ----


@method(p.MEMBER_LIST)
async def member_list(call: Call) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)

    def work(conn: sqlite3.Connection):
        require_member(conn, call.uid, workspace_id, "viewer")
        return workspaces.members(conn, workspace_id)

    members = await call.ctx.store.read(work)
    return {"workspace_id": workspace_id, "members": [m.to_dict() for m in members]}


@method(p.MEMBER_SET_ROLE)
async def member_set_role(call: Call) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)
    target_id = v.required_str(call.params, "user_id")
    role = validate_role(call.params.get("role"))

    def work(conn: sqlite3.Connection) -> bool:
        workspace, _ = require_member(conn, call.uid, workspace_id, "owner")
        if workspace.archived_at is not None:
            raise BlackboardError(CONFLICT, "the workspace is archived", {"workspace_id": workspace_id})
        target = workspaces.membership(conn, workspace_id, target_id)
        if target is None:
            raise not_found("that user is not a member of this workspace", user_id=target_id)
        if target.role == role:
            return False
        if target.role == "owner" and workspaces.owner_count(conn, workspace_id) == 1:
            raise BlackboardError(CONFLICT, "a workspace needs at least one owner", {"user_id": target_id})
        workspaces.set_role(conn, workspace_id, target_id, role)
        return True

    changed = await call.ctx.store.transact(work)
    if changed:
        await _documents().recheck_docs(call.ctx, workspace_id, target_id, role=role)
        await call.ctx.hub.publish(p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
        await call.ctx.hub.publish(
            p.EV_MEMBER_ROLE_CHANGED,
            {"workspace_id": workspace_id, "user_id": target_id, "role": role},
            user_ids=[target_id],
        )
        await call.ctx.hub.publish(p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id}, user_ids=[target_id])
    return {"workspace_id": workspace_id, "user_id": target_id, "role": role, "changed": changed}


@method(p.MEMBER_REMOVE)
async def member_remove(call: Call) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)
    target_id = v.required_str(call.params, "user_id")

    def work(conn: sqlite3.Connection) -> None:
        # Anyone may leave; removing someone else needs the owner role.
        require_member(conn, call.uid, workspace_id, "viewer" if target_id == call.uid else "owner")
        target = workspaces.membership(conn, workspace_id, target_id)
        if target is None:
            raise not_found("that user is not a member of this workspace", user_id=target_id)
        if target.role == "owner" and workspaces.owner_count(conn, workspace_id) == 1:
            raise BlackboardError(
                CONFLICT, "the last owner cannot leave; make someone else owner first", {"user_id": target_id}
            )
        workspaces.remove_member(conn, workspace_id, target_id)

    await call.ctx.store.transact(work)
    await _documents().recheck_docs(call.ctx, workspace_id, target_id, revoke=True)
    await call.ctx.hub.publish(p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
    await call.ctx.hub.publish(
        p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id, "removed": True}, user_ids=[target_id]
    )
    return {"workspace_id": workspace_id, "user_id": target_id, "removed": True}


# ---- invites ----


@method(p.INVITE_CREATE)
async def invite_create(call: Call) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)
    role = validate_role(call.params.get("role"), INVITE_ROLES)
    # Like Discord: an absent expiry means 7 days and null means never; no max_uses means no limit.
    expires_at: str | None = None
    if call.params.get("expires_in_minutes") is not None or "expires_in_minutes" not in call.params:
        minutes = v.int_in_range(
            call.params.get("expires_in_minutes"),
            "expires_in_minutes",
            low=1,
            high=MAX_INVITE_MINUTES,
            default=DEFAULT_INVITE_MINUTES,
        )
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
    raw_uses = call.params.get("max_uses")
    max_uses = None if raw_uses is None else v.int_in_range(raw_uses, "max_uses", low=1, high=MAX_INVITE_USES, default=1)

    def work(conn: sqlite3.Connection) -> Invite:
        workspace, _ = require_member(conn, call.uid, workspace_id, "owner")
        if workspace.archived_at is not None:
            raise BlackboardError(CONFLICT, "the workspace is archived", {"workspace_id": workspace_id})
        return invites.create(
            conn, workspace_id=workspace_id, role=role, created_by=call.uid, expires_at=expires_at, max_uses=max_uses
        )

    invite = await call.ctx.store.transact(work)
    await call.ctx.hub.publish(p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
    return {"invite": _invite_dict(call.ctx, invite, now_iso()), "url": call.ctx.invite_url(invite.code)}


@method(p.INVITE_LIST)
async def invite_list(call: Call) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)

    def work(conn: sqlite3.Connection) -> list[Invite]:
        require_member(conn, call.uid, workspace_id, "owner")
        return invites.list_for_workspace(conn, workspace_id)

    rows = await call.ctx.store.read(work)
    now = now_iso()
    return {"workspace_id": workspace_id, "invites": [_invite_dict(call.ctx, i, now) for i in rows]}


@method(p.INVITE_REVOKE)
async def invite_revoke(call: Call) -> dict[str, Any]:
    workspace_id = _workspace_id(call.params)
    code = v.required_str(call.params, "code")

    def work(conn: sqlite3.Connection) -> None:
        require_member(conn, call.uid, workspace_id, "owner")
        invite = invites.get(conn, code)
        if invite is None or invite.workspace_id != workspace_id:
            raise not_found("no such invite in this workspace", code=code)
        invites.revoke(conn, code)

    await call.ctx.store.transact(work)
    await call.ctx.hub.publish(p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
    return {"workspace_id": workspace_id, "code": code, "revoked": True}


@method(p.INVITE_ACCEPT)
async def invite_accept(call: Call) -> dict[str, Any]:
    """Join with an invite code. No member token is needed; one is returned for a new user."""
    code = v.required_str(call.params, "code")
    token = call.params.get("token")
    token = token.strip() if isinstance(token, str) and token.strip() else None
    raw_name = call.params.get("display_name")
    now = now_iso()

    def work(conn: sqlite3.Connection) -> dict[str, Any]:
        invite = invites.get(conn, code)
        if invite is None:
            raise not_found("this invite link is not valid")
        workspace = workspaces.get(conn, invite.workspace_id)
        user = users.by_token_hash(conn, hash_token(token)) if token else None
        if user is not None and user.status != "active":
            raise BlackboardError(DISABLED, "this user is disabled on the host")

        # Someone who is already a member gets the workspace back, even from a used-up link.
        existing = workspaces.membership(conn, workspace.id, user.id) if user and workspace else None
        if existing is not None and workspace is not None:
            return {
                "user_id": user.id,
                "display_name": user.display_name,
                "workspace": workspace.to_dict(existing.role),
                "joined": False,
            }

        state = invite.state(now)
        if state != "active":
            raise BlackboardError(EXPIRED, f"this invite link is {state.replace('_', ' ')}", {"state": state})
        if workspace is None or workspace.archived_at is not None:
            raise BlackboardError(EXPIRED, "the workspace of this invite is not available", {"state": "archived"})

        new_token = None
        if user is None:
            name = v.display_name(raw_name)
            new_token = new_member_token()
            user = users.create(conn, display_name=name, token_hash=hash_token(new_token))
        member = workspaces.add_member(conn, workspace.id, user.id, invite.role)
        invites.use(conn, code)
        result: dict[str, Any] = {
            "user_id": user.id,
            "display_name": user.display_name,
            "workspace": workspace.to_dict(member.role),
            "joined": True,
        }
        if new_token is not None:
            result["token"] = new_token
        return result

    result = await call.ctx.store.transact(work)
    result["host"] = await call.ctx.host_info()
    if result["joined"]:
        workspace_id = result["workspace"]["id"]
        await call.ctx.hub.publish(p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)
        await call.ctx.hub.publish(p.EV_ME_UPDATED, {}, user_ids=[result["user_id"]])
    return result


def unknown_method(name: str) -> BlackboardError:
    return invalid(f"unknown method: {name}", method=name)
