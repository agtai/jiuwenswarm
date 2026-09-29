"""Document methods (milestone 3). Rows live in the host store; content lives in the document service."""

from __future__ import annotations

import contextlib
import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import BUSY, CONFLICT, BlackboardError, invalid, not_found
from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.common.tokens import mint_doc_token
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.store import docs, mandates, workspaces
from jiuwenswarm.extensions.blackboard.host.store.models import Doc, Member, Workspace

logger = logging.getLogger(__name__)

DOC_TOKEN_TTL_S = 3600
INSTRUCTIONS_TITLE = "Instructions"
INSTRUCTIONS_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "instructions.md"
MAX_IMPORT_CHARS = 5_000_000


def _person(user_id: str) -> dict[str, str]:
    return {"id": user_id, "kind": "person"}


def _doc_for(conn: sqlite3.Connection, user_id: str, doc_id: str, at_least: str) -> tuple[Doc, Workspace, Member]:
    doc = docs.get(conn, doc_id)
    if doc is None:
        raise not_found("no such document", doc_id=doc_id)
    workspace, member = require_member(conn, user_id, doc.workspace_id, at_least)
    return doc, workspace, member


def _writable_doc(conn: sqlite3.Connection, user_id: str, doc_id: str) -> Doc:
    doc, workspace, _ = _doc_for(conn, user_id, doc_id, "editor")
    if workspace.archived_at is not None:
        raise BlackboardError(CONFLICT, "the workspace is archived", {"workspace_id": workspace.id})
    if doc.archived_at is not None:
        raise BlackboardError(CONFLICT, "the document is archived", {"doc_id": doc.id})
    return doc


def _markdown(params: dict[str, Any], *, required: bool) -> str | None:
    value = params.get("markdown")
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise invalid("markdown must be text", field="markdown")
    if len(value) > MAX_IMPORT_CHARS:
        raise invalid("the Markdown is too long", field="markdown")
    return value


async def _publish(ctx: HostContext, doc: Doc, **extra: Any) -> None:
    await ctx.hub.publish(
        p.EV_DOC_UPDATED, {"workspace_id": doc.workspace_id, "doc_id": doc.id, **extra}, workspace_id=doc.workspace_id
    )


async def _create(
    ctx: HostContext,
    *,
    workspace_id: str,
    title: str,
    created_by: str,
    markdown: str | None,
    instructions: bool = False,
) -> tuple[Doc, bool]:
    """Create the content first, then the row, so a row never points at missing content."""
    client = ctx.doc_client()
    doc_id = new_id("d")
    created = await client.create(doc_id, _person(created_by), markdown)

    def work(conn: sqlite3.Connection) -> Doc:
        return docs.create(
            conn,
            doc_id=doc_id,
            workspace_id=workspace_id,
            title=title,
            created_by=created_by,
            is_instructions=instructions,
            is_pinned=instructions,
        )

    try:
        doc = await ctx.store.transact(work)
    except BaseException:
        with contextlib.suppress(BlackboardError):
            await client.delete(doc_id)
        raise
    await _publish(ctx, doc)
    return doc, bool(created.get("rawHtml"))


async def ensure_instructions(ctx: HostContext, workspace_id: str) -> None:
    """Every workspace has a pinned instructions document, created once the document service runs."""
    if ctx.docs is None or not ctx.docs.running:
        return
    existing = await ctx.store.read(lambda c: docs.instructions(c, workspace_id))
    workspace = await ctx.store.read(lambda c: workspaces.get(c, workspace_id))
    if existing is not None or workspace is None:
        return
    try:
        await _create(
            ctx,
            workspace_id=workspace_id,
            title=INSTRUCTIONS_TITLE,
            created_by=workspace.created_by,
            markdown=INSTRUCTIONS_TEMPLATE.read_text(encoding="utf-8"),
            instructions=True,
        )
    except sqlite3.IntegrityError:
        # Another request created it at the same moment.
        pass
    except BlackboardError as exc:
        logger.warning("blackboard: no instructions document for %s yet: %s", workspace_id, exc.message)


async def recheck_docs(
    ctx: HostContext, workspace_id: str, user_id: str | None = None, *, role: str | None = None, revoke: bool = False
) -> None:
    """Tell the document service about an access change: one member's new role or removal, or
    (without a user) that everyone's open documents should show a fresh token."""
    if ctx.docs is None or not ctx.docs.running:
        return
    doc_ids = await ctx.store.read(lambda c: docs.ids_for_workspace(c, workspace_id))
    for doc_id in doc_ids:
        try:
            await ctx.doc_client().recheck(doc_id, user_id, role=role, revoke=revoke)
        except BlackboardError as exc:
            logger.warning("blackboard: recheck of %s failed: %s", doc_id, exc.message)


async def delete_workspace_content(ctx: HostContext, workspace_id: str, doc_ids: list[str]) -> None:
    if ctx.docs is not None and ctx.docs.running:
        for doc_id in doc_ids:
            try:
                await ctx.doc_client().delete(doc_id)
            except BlackboardError as exc:
                logger.warning("blackboard: could not delete document %s: %s", doc_id, exc.message)
    if ctx.files_dir is not None:
        shutil.rmtree(ctx.files_dir / workspace_id, ignore_errors=True)


@method(p.DOC_LIST)
async def doc_list(call: Call) -> dict[str, Any]:
    workspace_id = v.required_str(call.params, "workspace_id")
    await call.ctx.store.read(lambda c: require_member(c, call.uid, workspace_id, "viewer"))
    await ensure_instructions(call.ctx, workspace_id)
    include_archived = bool(call.params.get("include_archived"))
    rows = await call.ctx.store.read(lambda c: docs.list_for_workspace(c, workspace_id, include_archived=include_archived))
    return {"workspace_id": workspace_id, "docs": [d.to_dict() for d in rows], "docservice": call.ctx.docservice_status()}


@method(p.DOC_CREATE)
async def doc_create(call: Call) -> dict[str, Any]:
    workspace_id = v.required_str(call.params, "workspace_id")
    title = v.title(call.params.get("title"))
    markdown = _markdown(call.params, required=False)

    def check(conn: sqlite3.Connection) -> None:
        workspace, _ = require_member(conn, call.uid, workspace_id, "editor")
        if workspace.archived_at is not None:
            raise BlackboardError(CONFLICT, "the workspace is archived", {"workspace_id": workspace_id})

    await call.ctx.store.read(check)
    doc, raw_html = await _create(call.ctx, workspace_id=workspace_id, title=title, created_by=call.uid, markdown=markdown)
    return {"doc": doc.to_dict(), "raw_html": raw_html}


@method(p.DOC_RENAME)
async def doc_rename(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")
    title = v.title(call.params.get("title"))

    def work(conn: sqlite3.Connection) -> Doc:
        doc = _writable_doc(conn, call.uid, doc_id)
        docs.rename(conn, doc_id, title)
        return doc

    doc = await call.ctx.store.transact(work)
    await _publish(call.ctx, doc)
    return {"doc_id": doc_id, "title": title}


@method(p.DOC_ARCHIVE)
async def doc_archive(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")

    def work(conn: sqlite3.Connection) -> Doc:
        doc = _writable_doc(conn, call.uid, doc_id)
        if doc.is_instructions:
            raise BlackboardError(CONFLICT, "make another document the instructions before archiving this one", {"doc_id": doc_id})
        docs.archive(conn, doc_id)
        return doc

    doc = await call.ctx.store.transact(work)
    await _publish(call.ctx, doc, archived=True)
    return {"doc_id": doc_id, "archived": True}


@method(p.DOC_SET_INSTRUCTIONS)
async def doc_set_instructions(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")

    def work(conn: sqlite3.Connection) -> Doc:
        doc = _writable_doc(conn, call.uid, doc_id)
        docs.set_instructions(conn, doc.workspace_id, doc_id)
        return doc

    doc = await call.ctx.store.transact(work)
    await _publish(call.ctx, doc)
    return {"doc_id": doc_id, "is_instructions": True}


@method(p.DOC_PIN)
async def doc_pin(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")
    pinned = call.params.get("pinned")
    if not isinstance(pinned, bool):
        raise invalid("pinned must be true or false", field="pinned")

    def work(conn: sqlite3.Connection) -> Doc:
        doc = _writable_doc(conn, call.uid, doc_id)
        docs.set_pinned(conn, doc_id, pinned)
        return doc

    doc = await call.ctx.store.transact(work)
    await _publish(call.ctx, doc)
    return {"doc_id": doc_id, "is_pinned": pinned}


@method(p.DOC_IMPORT_MARKDOWN)
async def doc_import_markdown(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")
    markdown = _markdown(call.params, required=True)

    def check(conn: sqlite3.Connection) -> Doc:
        doc = _writable_doc(conn, call.uid, doc_id)
        if mandates.lock_holder(conn, doc_id) is not None:
            raise BlackboardError(BUSY, "an agent is editing this document; try again when it is done", {"doc_id": doc_id})
        return doc

    doc = await call.ctx.store.read(check)
    result = await call.ctx.doc_client().import_markdown(doc_id, markdown or "", _person(call.uid))
    await _publish(call.ctx, doc)
    return {"doc_id": doc_id, "blocks": len(result.get("blocks", [])), "raw_html": bool(result.get("rawHtml"))}


@method(p.DOC_TOKEN)
async def doc_token(call: Call) -> dict[str, Any]:
    """A short-lived token for the document service, carrying the caller's current role.

    Archived documents and documents of an archived workspace open read-only.
    """
    doc_id = v.required_str(call.params, "doc_id")
    doc, workspace, member = await call.ctx.store.read(lambda c: _doc_for(c, call.uid, doc_id, "viewer"))
    call.ctx.doc_client()  # a token is no use while the service is down
    frozen = doc.archived_at is not None or workspace.archived_at is not None
    role = "viewer" if frozen else member.role
    claims = {"uid": call.uid, "ws": doc.workspace_id, "doc": doc_id, "role": role}
    return {
        "token": mint_doc_token(claims, call.ctx.secrets.doc_secret, ttl_seconds=DOC_TOKEN_TTL_S),
        "url": call.ctx.settings.doc_url(),
        "role": role,
        "frozen": frozen,
        "expires_in": DOC_TOKEN_TTL_S,
    }


@method(p.DOC_READ)
async def doc_read(call: Call) -> dict[str, Any]:
    doc_id = v.required_str(call.params, "doc_id")
    view = call.params.get("view") or "accepted"
    if view not in ("accepted", "proposed"):
        raise invalid("view is accepted or proposed", field="view")
    range_ = call.params.get("range")
    if range_ is not None and not isinstance(range_, str):
        raise invalid("range is <block id>..<block id>", field="range")
    await call.ctx.store.read(lambda c: _doc_for(c, call.uid, doc_id, "viewer"))
    result = await call.ctx.doc_client().markdown(doc_id, view=view, range_=range_)
    return {"doc_id": doc_id, **result}
