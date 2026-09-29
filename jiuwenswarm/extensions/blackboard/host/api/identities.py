"""Shared IM bots and connected IM accounts (milestone 7).

The host operator makes a bot and gives its link to the jiuwenswarm that runs as a bot in a team's
IM workspace. A person connects their IM account to their user with a code from the web app, which
they send to the bot; from then on the bot reads for them, and only reads (see ``rpc.py``).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import EXPIRED, FORBIDDEN, BlackboardError, invalid, not_found
from jiuwenswarm.extensions.blackboard.common.tokens import hash_token, new_bot_token, normalize_link_code
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.store import bots, users
from jiuwenswarm.extensions.blackboard.host.store.models import Identity

_PLATFORM = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
MAX_EXTERNAL_ID = 200


def _operator(call: Call) -> None:
    if call.user is None or not call.user.is_operator:
        raise BlackboardError(FORBIDDEN, "only the host's operator manages bots")


def _platform(params: dict[str, Any]) -> tuple[str, str]:
    platform, external_id = params.get("platform"), params.get("external_id")
    if not isinstance(platform, str) or not _PLATFORM.match(platform):
        raise invalid("platform is the IM platform's name, such as slack or feishu", field="platform")
    if not isinstance(external_id, str) or not external_id.strip() or len(external_id) > MAX_EXTERNAL_ID:
        raise invalid("external_id is the person's id on the platform", field="external_id")
    return platform, external_id.strip()


@method(p.BOT_CREATE)
async def bot_create(call: Call) -> dict[str, Any]:
    """A new bot; its token and link are shown this once."""
    _operator(call)
    name = v.text(call.params.get("name"), "name", max_len=60)
    token = new_bot_token()
    bot = await call.ctx.store.transact(lambda c: bots.create(c, name=name, token_hash=hash_token(token), created_by=call.uid))
    return {"bot": bot.to_dict(), "token": token, "link": f"{call.ctx.settings.base_url()}{p.BOT_PATH}#{token}"}


@method(p.BOT_LIST)
async def bot_list(call: Call) -> dict[str, Any]:
    _operator(call)
    return {"bots": [b.to_dict() for b in await call.ctx.store.read(bots.list_all)]}


@method(p.BOT_REVOKE)
async def bot_revoke(call: Call) -> dict[str, Any]:
    _operator(call)
    bot_id = v.required_str(call.params, "bot_id")

    def work(conn: sqlite3.Connection) -> None:
        if bots.get(conn, bot_id) is None:
            raise not_found("no such bot", bot_id=bot_id)
        bots.revoke(conn, bot_id)

    await call.ctx.store.transact(work)
    return {"bot_id": bot_id, "revoked": True}


@method(p.BOT_WHOAMI)
async def bot_whoami(call: Call) -> dict[str, Any]:
    """A bot checks its link before keeping it."""
    assert call.bot is not None
    return {"bot": call.bot.to_dict(), "host": await call.ctx.host_info()}


@method(p.IDENTITY_LINK_CODE)
async def identity_link_code(call: Call) -> dict[str, Any]:
    """A code the person sends to a shared bot within 15 minutes."""
    code, expires_at = await call.ctx.store.transact(lambda c: bots.new_code(c, call.uid))
    return {"code": code, "expires_at": expires_at}


@method(p.IDENTITY_LINK)
async def identity_link(call: Call) -> dict[str, Any]:
    """A bot connects the IM account that sent it a code to the code's user."""
    assert call.bot is not None
    bot = call.bot
    platform, external_id = _platform(call.params)
    code = normalize_link_code(str(call.params.get("code") or ""))
    display_name = call.params.get("display_name")
    display_name = display_name.strip()[:120] if isinstance(display_name, str) and display_name.strip() else None

    def work(conn: sqlite3.Connection) -> tuple[str, Identity | None, str]:
        user_id = bots.take_code(conn, code)
        if user_id is None:
            raise BlackboardError(EXPIRED, "this code is unknown or expired; get a new one in the web app")
        previous = bots.link(conn, platform=platform, external_id=external_id, user_id=user_id, display_name=display_name, bot_id=bot.id)
        user = users.get(conn, user_id)
        return user_id, previous, user.display_name if user else ""

    user_id, previous, name = await call.ctx.store.transact(work)
    moved_from = previous.user_id if previous is not None and previous.user_id != user_id else None
    await call.ctx.hub.publish(p.EV_ME_UPDATED, {}, user_ids=[user_id, *([moved_from] if moved_from else [])])
    return {
        "user": {"id": user_id, "display_name": name},
        "host": (await call.ctx.host_info())["name"],
        "platform": platform,
        "replaced": moved_from is not None,
    }


@method(p.IDENTITY_LIST)
async def identity_list(call: Call) -> dict[str, Any]:
    rows = await call.ctx.store.read(lambda c: bots.for_user(c, call.uid))
    return {"identities": [i.to_dict() for i in rows]}


@method(p.IDENTITY_UNLINK)
async def identity_unlink(call: Call) -> dict[str, Any]:
    platform, external_id = _platform(call.params)
    removed = await call.ctx.store.transact(lambda c: bots.unlink(c, call.uid, platform, external_id))
    if not removed:
        raise not_found("this IM account is not connected to you", platform=platform)
    await call.ctx.hub.publish(p.EV_ME_UPDATED, {}, user_ids=[call.uid])
    return {"platform": platform, "external_id": external_id, "removed": True}
