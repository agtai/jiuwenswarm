"""``POST /blackboard/rpc``: one dispatcher over the method table.

Body ``{method, params}``; reply ``{ok: true, payload}`` or
``{ok: false, error: {code, message, details}}``. Unauthenticated calls get
HTTP 401, malformed bodies 400, everything else 200.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from jiuwenswarm.extensions.blackboard.common.errors import INTERNAL, INVALID, UNAUTHORIZED, BlackboardError
from jiuwenswarm.extensions.blackboard.common.protocol import NO_AUTH_METHODS
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.methods import METHODS, Call, unknown_method

logger = logging.getLogger(__name__)


def _error(exc: BlackboardError, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": False, "error": exc.to_dict()}, status_code=status)


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


async def handle_rpc(ctx: HostContext, request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError:
        return _error(BlackboardError(INVALID, "the body must be JSON"), 400)
    if not isinstance(body, dict) or not isinstance(body.get("method"), str):
        return _error(BlackboardError(INVALID, "the body must be {method, params}"), 400)
    name: str = body["method"]
    params: Any = body.get("params") or {}
    if not isinstance(params, dict):
        return _error(BlackboardError(INVALID, "params must be an object"), 400)
    handler = METHODS.get(name)
    if handler is None:
        return _error(unknown_method(name))

    user = None
    if name not in NO_AUTH_METHODS:
        try:
            user = await ctx.authenticate(bearer_token(request))
        except BlackboardError as exc:
            return _error(exc, 401 if exc.code == UNAUTHORIZED else 403)

    try:
        payload = await handler(Call(ctx=ctx, user=user, params=params))
    except BlackboardError as exc:
        return _error(exc)
    except Exception:  # noqa: BLE001 - the caller gets a stable code, the log gets the trace
        logger.exception("blackboard: method %s failed", name)
        return _error(BlackboardError(INTERNAL, "the host could not complete the request"))
    return JSONResponse({"ok": True, "payload": payload})
