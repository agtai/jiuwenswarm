"""The FastAPI app the host serves on ``blackboard.host.bind:port``."""

from __future__ import annotations

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, Response

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.origins import origin_allowed
from jiuwenswarm.extensions.blackboard.host.api import chat as _chat  # noqa: F401 - registers methods
from jiuwenswarm.extensions.blackboard.host.api import comments as _comments  # noqa: F401 - registers methods
from jiuwenswarm.extensions.blackboard.host.api import decisions as _decisions  # noqa: F401 - registers methods
from jiuwenswarm.extensions.blackboard.host.api import dispatch as _dispatch  # noqa: F401 - registers methods
from jiuwenswarm.extensions.blackboard.host.api import documents as _documents  # noqa: F401 - registers methods
from jiuwenswarm.extensions.blackboard.host.api import history
from jiuwenswarm.extensions.blackboard.host.api import identities as _identities  # noqa: F401 - registers methods
from jiuwenswarm.extensions.blackboard.host.api import mandates as _mandates  # noqa: F401 - registers methods
from jiuwenswarm.extensions.blackboard.host.api import ops
from jiuwenswarm.extensions.blackboard.host.api import people as _people  # noqa: F401 - registers methods
from jiuwenswarm.extensions.blackboard.host.api import references
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.pages import join_page
from jiuwenswarm.extensions.blackboard.host.api.rpc import handle_rpc
from jiuwenswarm.extensions.blackboard.host.store import invites, workspaces
from jiuwenswarm.extensions.blackboard.host.store.store import now_iso


def build_app(ctx: HostContext) -> FastAPI:
    app = FastAPI(title="Blackboard host", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.blackboard = ctx

    @app.post(p.RPC_PATH)
    async def rpc(request: Request) -> JSONResponse:
        return await handle_rpc(ctx, request)

    @app.websocket(p.EVENTS_PATH)
    async def events(websocket: WebSocket) -> None:
        # Members' instances send no Origin; a web page must be one the host allows.
        settings = ctx.settings
        if not origin_allowed(websocket.headers.get("origin"), settings.allowed_origins, settings.allow_any_origin):
            await websocket.close(code=4403, reason="origin not allowed")
            return
        await ctx.hub.serve(websocket, ctx.authenticate, ctx.host_info)

    @app.get(p.JOIN_PATH + "{code}")
    async def join(code: str) -> HTMLResponse:
        def lookup(conn):
            invite = invites.get(conn, code)
            if invite is None:
                return None, None, "not_found"
            workspace = workspaces.get(conn, invite.workspace_id)
            state = invite.state(now_iso())
            if workspace is None or workspace.archived_at is not None:
                state = "archived" if state == "active" else state
            return (workspace.title if workspace else None), invite.role, state

        title, role, state = await ctx.store.read(lookup)
        return HTMLResponse(join_page(ctx.invite_url(code), title, role, state))

    @app.post(p.FILES_PATH + "{workspace_id}")
    async def upload(workspace_id: str, request: Request) -> JSONResponse:
        return await references.upload(ctx, workspace_id, request)

    @app.get(p.FILES_PATH + "{workspace_id}/{reference_id}")
    async def download(workspace_id: str, reference_id: str, t: str | None = None) -> Response:
        return await references.download(ctx, workspace_id, reference_id, t)

    @app.get(p.EXPORT_PATH + "{export_id}")
    async def export_download(export_id: str, t: str | None = None) -> Response:
        return await history.download_export(ctx, export_id, t)

    @app.post(p.VERSIONS_HOOK_PATH)
    async def versions_hook(request: Request) -> JSONResponse:
        return await history.versions_hook(ctx, request)

    @app.get(p.HEALTH_PATH)
    async def health() -> JSONResponse:
        return JSONResponse(await ops.health(ctx))

    return app
