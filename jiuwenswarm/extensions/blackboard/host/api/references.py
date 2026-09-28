"""References: files members upload to a workspace (milestone 3).

Uploads arrive as multipart on ``POST /blackboard/files/<workspace id>`` with the member token;
downloads use ``GET /blackboard/files/<workspace id>/<reference id>?t=<file token>``, so a browser
can open a file with a plain link for an hour.
"""

from __future__ import annotations

import mimetypes
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import (
    CONFLICT,
    INVALID,
    UNAUTHORIZED,
    BlackboardError,
    invalid,
    not_found,
)
from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.common.tokens import mint_doc_token, verify_doc_token
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.api.rpc import bearer_token
from jiuwenswarm.extensions.blackboard.host.store import references
from jiuwenswarm.extensions.blackboard.host.store.models import Reference

FILE_TOKEN_TTL_S = 3600
MAX_NOTE = 500
_CHUNK = 1024 * 1024
_FORM_OVERHEAD = 64 * 1024


def _reference_for(conn: sqlite3.Connection, user_id: str, reference_id: str, at_least: str) -> Reference:
    reference = references.get(conn, reference_id)
    if reference is None or reference.removed_at is not None:
        raise not_found("no such reference", reference_id=reference_id)
    require_member(conn, user_id, reference.workspace_id, at_least)
    return reference


def _file_path(ctx: HostContext, reference: Reference) -> Path:
    assert ctx.files_dir is not None
    return ctx.files_dir / reference.stored_path


async def _publish(ctx: HostContext, workspace_id: str) -> None:
    await ctx.hub.publish(p.EV_REFERENCE_UPDATED, {"workspace_id": workspace_id}, workspace_id=workspace_id)


def file_url(ctx: HostContext, user_id: str, reference: Reference) -> str:
    claims = {"uid": user_id, "ws": reference.workspace_id, "ref": reference.id, "scope": "file"}
    token = mint_doc_token(claims, ctx.secrets.doc_secret, ttl_seconds=FILE_TOKEN_TTL_S)
    return f"{ctx.settings.base_url()}{p.FILES_PATH}{reference.workspace_id}/{reference.id}?t={token}"


@method(p.REFERENCE_LIST)
async def reference_list(call: Call) -> dict[str, Any]:
    workspace_id = v.required_str(call.params, "workspace_id")

    def work(conn: sqlite3.Connection):
        require_member(conn, call.uid, workspace_id, "viewer")
        return references.list_for_workspace(conn, workspace_id)

    rows = await call.ctx.store.read(work)
    return {
        "workspace_id": workspace_id,
        "references": [r.to_dict(name) for r, name in rows],
        "max_upload_mb": call.ctx.settings.max_upload_mb,
    }


@method(p.REFERENCE_URL)
async def reference_url(call: Call) -> dict[str, Any]:
    reference_id = v.required_str(call.params, "reference_id")
    reference = await call.ctx.store.read(lambda c: _reference_for(c, call.uid, reference_id, "viewer"))
    return {"reference_id": reference_id, "url": file_url(call.ctx, call.uid, reference), "expires_in": FILE_TOKEN_TTL_S}


@method(p.REFERENCE_REMOVE)
async def reference_remove(call: Call) -> dict[str, Any]:
    reference_id = v.required_str(call.params, "reference_id")

    def work(conn: sqlite3.Connection) -> Reference:
        reference = _reference_for(conn, call.uid, reference_id, "editor")
        references.remove(conn, reference_id)
        return reference

    reference = await call.ctx.store.transact(work)
    _file_path(call.ctx, reference).unlink(missing_ok=True)
    await _publish(call.ctx, reference.workspace_id)
    return {"reference_id": reference_id, "removed": True}


@method(p.REFERENCE_SET_NOTE)
async def reference_set_note(call: Call) -> dict[str, Any]:
    reference_id = v.required_str(call.params, "reference_id")
    note = v.text(call.params.get("note", ""), "note", max_len=MAX_NOTE, min_len=0)

    def work(conn: sqlite3.Connection) -> Reference:
        reference = _reference_for(conn, call.uid, reference_id, "editor")
        references.set_note(conn, reference_id, note)
        return reference

    reference = await call.ctx.store.transact(work)
    await _publish(call.ctx, reference.workspace_id)
    return {"reference_id": reference_id, "note": note}


def _error(exc: BlackboardError, status: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": exc.to_dict()}, status_code=status)


async def upload(ctx: HostContext, workspace_id: str, request: Request) -> JSONResponse:
    """Multipart: `file` and an optional `note`. Editors and owners may upload."""
    try:
        user = await ctx.authenticate(bearer_token(request))
    except BlackboardError as exc:
        return _error(exc, 401 if exc.code == UNAUTHORIZED else 403)
    try:
        workspace, _ = await ctx.store.read(lambda c: require_member(c, user.id, workspace_id, "editor"))
        if workspace.archived_at is not None:
            raise BlackboardError(CONFLICT, "the workspace is archived", {"workspace_id": workspace_id})
        limit = ctx.settings.max_upload_mb * 1024 * 1024
        too_big = BlackboardError(
            INVALID, f"files can be at most {ctx.settings.max_upload_mb} MB", {"field": "file", "limit_mb": ctx.settings.max_upload_mb}
        )
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit + _FORM_OVERHEAD:
            raise too_big
        form = await request.form(max_files=1)
        upload_file = form.get("file")
        if upload_file is None or isinstance(upload_file, str):
            raise invalid("send the file in a `file` part", field="file")
        note = v.text(form.get("note") or "", "note", max_len=MAX_NOTE, min_len=0)
        name = v.text(upload_file.filename or "file", "name", max_len=200)
        reference_id = new_id("r")
        suffix = Path(name).suffix[:16] if Path(name).suffix.isascii() else ""
        stored_path = f"{workspace_id}/{reference_id}{suffix}"
        assert ctx.files_dir is not None
        target = ctx.files_dir / stored_path
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with target.open("wb") as out:
                while chunk := await upload_file.read(_CHUNK):
                    size += len(chunk)
                    if size > limit:
                        raise too_big
                    out.write(chunk)
            mime = upload_file.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
            kind = "image" if mime.startswith("image/") else "file"
            reference = await ctx.store.transact(
                lambda c: references.create(
                    c,
                    reference_id=reference_id,
                    workspace_id=workspace_id,
                    kind=kind,
                    name=name,
                    mime=mime,
                    size=size,
                    stored_path=stored_path,
                    note=note,
                    uploaded_by=user.id,
                )
            )
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    except BlackboardError as exc:
        return _error(exc, 200)
    await _publish(ctx, workspace_id)
    return JSONResponse({"ok": True, "payload": {"reference": reference.to_dict(user.display_name)}})


async def download(ctx: HostContext, workspace_id: str, reference_id: str, token: str | None):
    try:
        claims = verify_doc_token(token or "", ctx.secrets.doc_secret)
    except BlackboardError as exc:
        return _error(exc, 401)
    if claims.get("scope") != "file" or claims.get("ws") != workspace_id or claims.get("ref") != reference_id:
        return _error(BlackboardError(UNAUTHORIZED, "this link is for another file"), 401)
    reference = await ctx.store.read(lambda c: references.get(c, reference_id))
    if reference is None or reference.removed_at is not None or reference.workspace_id != workspace_id:
        return _error(not_found("the file was removed"), 404)
    path = _file_path(ctx, reference)
    if not path.exists():
        return _error(not_found("the file is missing on the host"), 404)
    return FileResponse(path, media_type=reference.mime, filename=reference.name, content_disposition_type="inline")
