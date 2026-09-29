"""Version history and export (milestone 6).

Versions live in the document service, which takes them after edits; the host checks roles, adds
names, and tells the workspace when one is taken (the service calls ``VERSIONS_HOOK_PATH``).
Exports are written to ``<data>/exports/<export id>/<file name>`` and opened by the browser with a
link that works for an hour; exports older than a day are removed when the next one is made.
"""

from __future__ import annotations

import base64
import hmac
import re
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import BUSY, UNAUTHORIZED, UNAVAILABLE, BlackboardError, invalid, not_found
from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.common.tokens import mint_doc_token, verify_doc_token
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.documents import _doc_for, _writable_doc
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.store import decisions, docs, mandates, users
from jiuwenswarm.extensions.blackboard.host.store.models import Doc

EXPORT_TOKEN_TTL_S = 3600
EXPORT_KEEP_S = 24 * 3600
EXPORT_FORMATS = ("md", "docx", "pdf")
MAX_LABEL = 200
_EXPORT_ID = re.compile(r"^x_[0-9A-Z]{26}$")


async def _views(ctx: HostContext, versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The service's versions with the names of their authors and what each agent run was asked."""
    user_ids = {a["id"] for version in versions for a in version.get("authors", [])}
    mandate_ids = {version["mandateId"] for version in versions if version.get("mandateId")}

    def lookup(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[str, str]]:
        found = [mandates.get(conn, m) for m in mandate_ids]
        return users.names(conn, list(user_ids)), {m.id: m.instruction for m in found if m is not None}

    names, instructions = await ctx.store.read(lookup)
    return [
        {
            "id": version["id"],
            "doc_id": version["docId"],
            "created_at": version["createdAt"],
            "reason": version["reason"],
            "authors": [{"id": a["id"], "kind": a["kind"], "name": names.get(a["id"], "")} for a in version.get("authors", [])],
            "mandate_id": version.get("mandateId"),
            "mandate_instruction": instructions.get(version.get("mandateId") or ""),
            "restored_from": version.get("restoredFrom"),
            "label": version.get("label"),
            "size": version.get("size", 0),
        }
        for version in versions
    ]


async def _view(ctx: HostContext, version: dict[str, Any] | None) -> dict[str, Any] | None:
    return (await _views(ctx, [version]))[0] if version else None


def _version_id(params: dict[str, Any], field: str, *, required: bool = True) -> str | None:
    value = params.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise invalid(f"{field} is a version id", field=field)
    return value


@method(p.HISTORY_LIST)
async def history_list(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")
    before = _version_id(call.params, "before", required=False)
    limit = v.int_in_range(call.params.get("limit"), "limit", low=1, high=200, default=50)
    await call.ctx.store.read(lambda c: _doc_for(c, call.uid, doc_id, "viewer"))
    result = await call.ctx.doc_client().versions(doc_id, limit=limit, before=before)
    return {"doc_id": doc_id, "versions": await _views(call.ctx, result.get("versions", [])), "has_more": bool(result.get("hasMore"))}


@method(p.HISTORY_GET)
async def history_get(call: Call) -> dict[str, Any]:
    """One version: its content for a read-only view, or its accepted Markdown to download."""
    doc_id = v.required_str(call.params, "doc_id")
    version_id = _version_id(call.params, "version_id")
    markdown = call.params.get("format") == "markdown"
    await call.ctx.store.read(lambda c: _doc_for(c, call.uid, doc_id, "viewer"))
    result = await call.ctx.doc_client().version(doc_id, version_id, markdown=markdown)
    version = await _view(call.ctx, result.get("version"))
    if markdown:
        return {"doc_id": doc_id, "version": version, "markdown": result.get("markdown", "")}
    return {"doc_id": doc_id, "version": version, "previous": result.get("previous"), "doc": result.get("doc")}


@method(p.HISTORY_DIFF)
async def history_diff(call: Call) -> dict[str, Any]:
    """What changed up to version `to`, from version `from` or else from the version before it."""
    doc_id = v.required_str(call.params, "doc_id")
    to = _version_id(call.params, "to")
    from_ = _version_id(call.params, "from", required=False)
    await call.ctx.store.read(lambda c: _doc_for(c, call.uid, doc_id, "viewer"))
    result = await call.ctx.doc_client().diff(doc_id, to, from_)
    blocks = [
        {
            "id": b.get("id"),
            "type": b.get("type"),
            "status": b.get("status"),
            "markdown": b.get("markdown", ""),
            "inline": b.get("inline"),
            "pending": bool(b.get("pending")),
            "was_pending": bool(b.get("wasPending")),
        }
        for b in result.get("blocks", [])
    ]
    return {"doc_id": doc_id, "from": result.get("from"), "to": result.get("to"), "blocks": blocks, "summary": result.get("summary", {})}


@method(p.HISTORY_SAVE)
async def history_save(call: Call) -> dict[str, Any]:
    """A named version of the document as it is now; editors and owners."""
    doc_id = v.required_str(call.params, "doc_id")
    label = call.params.get("label")
    label = v.text(label, "label", max_len=MAX_LABEL, min_len=0) if label is not None else ""
    await call.ctx.store.read(lambda c: _writable_doc(c, call.uid, doc_id))
    result = await call.ctx.doc_client().save_version(doc_id, {"id": call.uid, "kind": "person"}, label or None)
    return {"doc_id": doc_id, "version": await _view(call.ctx, result.get("version"))}


@method(p.HISTORY_RESTORE)
async def history_restore(call: Call) -> dict[str, Any]:
    """The document becomes a version again; refused while an agent is writing it."""
    doc_id = v.required_str(call.params, "doc_id")
    version_id = _version_id(call.params, "version_id")

    def check(conn: sqlite3.Connection) -> Doc:
        doc = _writable_doc(conn, call.uid, doc_id)
        if mandates.lock_holder(conn, doc_id) is not None:
            raise BlackboardError(BUSY, "an agent is editing this document; try again when it is done", {"doc_id": doc_id})
        return doc

    doc = await call.ctx.store.read(check)
    result = await call.ctx.doc_client().restore(doc_id, version_id, {"id": call.uid, "kind": "person"})
    # Suggestions the version held are pending again.
    await call.ctx.hub.publish(p.EV_SUGGESTIONS_CHANGED, {"workspace_id": doc.workspace_id, "doc_id": doc_id}, workspace_id=doc.workspace_id)
    return {"doc_id": doc_id, "version": await _view(call.ctx, result.get("version"))}


# ---- export ----


def _decisions_for(conn: sqlite3.Connection, doc: Doc) -> list[dict[str, Any]]:
    """Answered questions about the document, or asked by a run that changed it."""
    rows = decisions.answered_for_doc(conn, doc.workspace_id, doc.id)
    names = users.names(conn, [i for d in rows for i in (d.answered_by, d.accepted_by) if i])
    return [
        {
            "question": d.question,
            "answer": d.answer_label(),
            "answeredBy": names.get(d.answered_by or "", ""),
            "acceptedBy": names.get(d.accepted_by, "") if d.accepted_by else None,
        }
        for d in rows
    ]


def prune_exports(exports_dir: Path | None) -> None:
    if exports_dir is None or not exports_dir.is_dir():
        return
    cutoff = time.time() - EXPORT_KEEP_S
    for entry in exports_dir.iterdir():
        try:
            if entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True) if entry.is_dir() else entry.unlink(missing_ok=True)
        except OSError:
            continue


@method(p.DOC_EXPORT)
async def doc_export(call: Call) -> dict[str, Any]:
    """The accepted view (or a version's) as Markdown, Word or PDF, with a link to download it."""
    ctx = call.ctx
    doc_id = v.required_str(call.params, "doc_id")
    fmt = call.params.get("format")
    if fmt not in EXPORT_FORMATS:
        raise invalid("format is md, docx or pdf", field="format")
    version_id = _version_id(call.params, "version_id", required=False)
    with_decisions = call.params.get("include_decisions") is True
    if ctx.exports_dir is None:
        raise BlackboardError(UNAVAILABLE, "this host keeps no exports")

    def gather(conn: sqlite3.Connection) -> tuple[Doc, list[dict[str, Any]]]:
        doc, _, _ = _doc_for(conn, call.uid, doc_id, "viewer")
        return doc, (_decisions_for(conn, doc) if with_decisions else [])

    doc, answered = await ctx.store.read(gather)
    body: dict[str, Any] = {"format": fmt, "title": doc.title, "decisions": answered}
    if version_id:
        body["versionId"] = version_id
    result = await ctx.doc_client().export(doc_id, body)

    prune_exports(ctx.exports_dir)
    export_id = new_id("x")
    folder = ctx.exports_dir / export_id
    folder.mkdir(parents=True, exist_ok=True)
    file_name = str(result.get("fileName") or f"document.{fmt}")
    (folder / file_name).write_bytes(base64.b64decode(result.get("data") or ""))
    claims = {"uid": call.uid, "doc": doc_id, "export": export_id, "scope": "export"}
    token = mint_doc_token(claims, ctx.secrets.doc_secret, ttl_seconds=EXPORT_TOKEN_TTL_S)
    return {
        "doc_id": doc_id,
        "url": f"{ctx.settings.base_url()}{p.EXPORT_PATH}{export_id}?t={token}",
        "file_name": file_name,
        "size": int(result.get("size") or 0),
        "content_type": result.get("contentType"),
    }


def _error(exc: BlackboardError, status: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": exc.to_dict()}, status_code=status)


async def download_export(ctx: HostContext, export_id: str, token: str | None):
    try:
        claims = verify_doc_token(token or "", ctx.secrets.doc_secret)
    except BlackboardError as exc:
        return _error(exc, 401)
    if claims.get("scope") != "export" or claims.get("export") != export_id or not _EXPORT_ID.match(export_id):
        return _error(BlackboardError(UNAUTHORIZED, "this link is for another export"), 401)

    def still_member(conn: sqlite3.Connection) -> None:
        doc = docs.get(conn, str(claims.get("doc")))
        if doc is None:
            raise not_found("the document is gone")
        require_member(conn, str(claims.get("uid")), doc.workspace_id, "viewer")

    try:
        await ctx.store.read(still_member)
    except BlackboardError as exc:
        return _error(exc, 403)
    folder = ctx.exports_dir / export_id if ctx.exports_dir is not None else None
    files = [f for f in folder.iterdir() if f.is_file()] if folder is not None and folder.is_dir() else []
    if not files:
        return _error(not_found("the export is no longer kept; export again"), 404)
    return FileResponse(files[0], filename=files[0].name, content_disposition_type="attachment")


async def versions_hook(ctx: HostContext, request: Request) -> JSONResponse:
    """The document service took a version: tell the workspace."""
    given = request.headers.get("x-bb-secret", "")
    if not hmac.compare_digest(given.encode(), ctx.secrets.api_secret.encode()):
        return _error(BlackboardError(UNAUTHORIZED, "wrong secret"), 401)
    try:
        version = await request.json()
        doc_id = str(version["docId"])
    except (ValueError, KeyError, TypeError):
        return _error(invalid("the body is a version"), 400)
    doc = await ctx.store.read(lambda c: docs.get(c, doc_id))
    if doc is None:
        return _error(not_found("no such document"), 404)
    view = await _view(ctx, version)
    await ctx.hub.publish(p.EV_DOC_VERSIONS, {"workspace_id": doc.workspace_id, "doc_id": doc_id, "version": view}, workspace_id=doc.workspace_id)
    return JSONResponse({"ok": True})
