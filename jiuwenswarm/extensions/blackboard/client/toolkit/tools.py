"""Blackboard's tools for an agent in a session attached to one or more workspaces.

Framework-free: every tool is an async function that returns a dict and never raises, so the model
reads each error and can act on it. ``bridge.py`` turns them into openjiuwen tools. The calls go to the
workspace's host with the person's member token, from the AgentServer process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from jiuwenswarm.extensions.blackboard.client.hosts import HostRegistry
from jiuwenswarm.extensions.blackboard.client.link import call_host
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import INTERNAL, NOT_FOUND, BlackboardError

logger = logging.getLogger(__name__)

# The host may wait up to a minute for another agent to let go of a document.
EDIT_TIMEOUT_S = 90.0
MAX_REFERENCE_BYTES = 200_000
TEXT_MIMES = ("text/", "application/json", "application/xml", "application/x-yaml", "application/yaml")


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class WorkspaceRef:
    host_id: str
    workspace_id: str
    title: str = ""


@dataclass(frozen=True)
class MandateRef:
    """The comment or chat task a dispatched turn works on."""

    host_id: str
    workspace_id: str
    mandate_id: str
    origin: str = ""


@dataclass
class SessionTools:
    registry: HostRegistry
    session_id: str
    workspaces: list[WorkspaceRef]
    # The current request id; set before every turn, so edits of one turn share a mandate.
    turn_id: str = ""
    # Set for a turn the dispatcher started on a comment or chat task: edits go under its mandate,
    # and the agent may ask the workspace a question.
    mandate: MandateRef | None = None
    # Which workspace a document or reference id belongs to, learned from the lists.
    _homes: dict[str, WorkspaceRef] = field(default_factory=dict)

    async def _call(self, ws: WorkspaceRef, method: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        entry = self.registry.get(ws.host_id)
        if entry is None:
            raise BlackboardError(NOT_FOUND, "this jiuwenswarm no longer knows the workspace's host", {"workspace": ws.workspace_id})
        return await call_host(entry.url, method, params, token=entry.token, timeout=timeout)

    def _chosen(self, workspace: str | None) -> list[WorkspaceRef]:
        if not workspace:
            return self.workspaces
        chosen = [w for w in self.workspaces if w.workspace_id == workspace]
        if not chosen:
            raise BlackboardError(
                NOT_FOUND,
                "this session does not work on that workspace",
                {"workspace": workspace, "workspaces": [w.workspace_id for w in self.workspaces]},
            )
        return chosen

    async def _home(self, item: str, refresh: Callable[[], Awaitable[Any]], kind: str) -> WorkspaceRef:
        if item not in self._homes:
            await refresh()
        home = self._homes.get(item)
        if home is None:
            raise BlackboardError(NOT_FOUND, f"no {kind} with this id in this session's workspaces", {kind: item})
        return home

    async def list_docs(self, workspace: str | None = None) -> dict[str, Any]:
        out = []
        for ws in self._chosen(workspace):
            result = await self._call(ws, p.DOC_LIST, {"workspace_id": ws.workspace_id})
            docs = [
                {"id": d["id"], "title": d["title"], "is_instructions": d["is_instructions"], "is_pinned": d["is_pinned"]}
                for d in result.get("docs", [])
            ]
            for d in docs:
                self._homes[d["id"]] = ws
            out.append(
                {
                    "id": ws.workspace_id,
                    "title": ws.title,
                    "docs": docs,
                    "instructions_doc": next((d["id"] for d in docs if d["is_instructions"]), None),
                }
            )
        return {"workspaces": out}

    async def read(self, doc: str, view: str = "accepted", range: str | None = None) -> dict[str, Any]:  # noqa: A002
        ws = await self._home(doc, self.list_docs, "doc")
        params: dict[str, Any] = {"doc_id": doc, "view": view if view in ("accepted", "proposed") else "accepted"}
        if range:
            params["range"] = range
        result = await self._call(ws, p.DOC_READ, params)
        return {
            "doc": doc,
            "workspace": ws.workspace_id,
            "view": params["view"],
            "markdown": result.get("markdown", ""),
            "blocks": [
                {"id": b["id"], "digest": b["digest"], "pending_suggestions": b.get("hasPendingSuggestions", False)}
                for b in result.get("blocks", [])
            ],
        }

    async def edit(self, doc: str, ops: list[dict[str, Any]], note: str = "") -> dict[str, Any]:
        ws = await self._home(doc, self.list_docs, "doc")
        params: dict[str, Any] = {"doc_id": doc, "ops": ops, "note": note}
        if self.mandate is not None:
            if (ws.host_id, ws.workspace_id) != (self.mandate.host_id, self.mandate.workspace_id):
                raise BlackboardError(
                    "out_of_scope",
                    "this task is for another workspace; edit only its documents",
                    {"doc": doc, "workspace": self.mandate.workspace_id},
                )
            params["mandate_id"] = self.mandate.mandate_id
        else:
            params.update(session_id=self.session_id, turn_id=self.turn_id)
        result = await self._call(ws, p.EDIT, params, timeout=EDIT_TIMEOUT_S)
        return {
            **result,
            "message": "Your changes are suggestions now; the people in the workspace accept or reject them.",
        }

    async def ask(
        self,
        question: str,
        options: list[dict[str, Any]],
        recommended: int | None = None,
        doc: str | None = None,
        block_id: str | None = None,
    ) -> dict[str, Any]:
        if self.mandate is None:
            raise BlackboardError("no_mandate", "questions go to the workspace only in tasks from a comment or the chat")
        ws = WorkspaceRef(self.mandate.host_id, self.mandate.workspace_id)
        params: dict[str, Any] = {"mandate_id": self.mandate.mandate_id, "question": question, "options": options}
        if recommended is not None:
            params["recommended"] = recommended
        if doc:
            params.update(doc_id=doc, block_id=block_id)
        return await self._call(ws, p.DECISION_CREATE, params)

    async def list_references(self, workspace: str | None = None) -> dict[str, Any]:
        out = []
        for ws in self._chosen(workspace):
            result = await self._call(ws, p.REFERENCE_LIST, {"workspace_id": ws.workspace_id})
            refs = [
                {"id": r["id"], "name": r["name"], "kind": r["kind"], "mime": r["mime"], "size": r["size"], "note": r["note"]}
                for r in result.get("references", [])
            ]
            for r in refs:
                self._homes[r["id"]] = ws
            out.append({"id": ws.workspace_id, "title": ws.title, "references": refs})
        return {"workspaces": out}

    async def read_reference(self, reference: str) -> dict[str, Any]:
        ws = await self._home(reference, self.list_references, "reference")
        listed = await self._call(ws, p.REFERENCE_LIST, {"workspace_id": ws.workspace_id})
        ref = next((r for r in listed.get("references", []) if r["id"] == reference), None)
        if ref is None:
            raise BlackboardError(NOT_FOUND, "no reference has this id", {"reference": reference})
        if not ref["mime"].startswith(TEXT_MIMES):
            return {"reference": reference, "name": ref["name"], "readable": False, "message": f"{ref['mime']} files cannot be read as text."}
        link = await self._call(ws, p.REFERENCE_URL, {"reference_id": reference})
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(link["url"])
        if response.status_code != 200:
            raise BlackboardError(NOT_FOUND, "the file could not be fetched", {"status": response.status_code})
        data = response.content[:MAX_REFERENCE_BYTES]
        return {
            "reference": reference,
            "name": ref["name"],
            "readable": True,
            "truncated": len(response.content) > MAX_REFERENCE_BYTES,
            "text": data.decode("utf-8", errors="replace"),
        }

    def specs(self) -> list[ToolSpec]:
        specs = self._specs()
        if self.mandate is not None:
            specs.append(self._ask_spec())
        return specs

    def _ask_spec(self) -> ToolSpec:
        return ToolSpec(
            "blackboard_ask",
            "Ask the people in the workspace a question you need answered before you can go on, with 2 to 4 "
            "options. Any editor may answer; the person who gave you the task accepts the answer. After calling "
            "this, end your turn at once: you will be started again with the answer.",
            {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "the question, at most 1000 characters"},
                    "options": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "the choice, at most 120 characters"},
                                "description": {"type": "string", "description": "what it means, optional"},
                            },
                            "required": ["label"],
                        },
                    },
                    "recommended": {"type": "integer", "description": "index of the option you recommend, optional"},
                    "doc": {"type": "string", "description": "the document the question is about, optional"},
                    "block_id": {"type": "string", "description": "the block the question is about, optional"},
                },
                "required": ["question", "options"],
            },
            self._safe(self.ask, ("question", "options", "recommended", "doc", "block_id")),
        )

    def _specs(self) -> list[ToolSpec]:
        titles = ", ".join(f'"{w.title}" ({w.workspace_id})' if w.title else w.workspace_id for w in self.workspaces)
        where = f"the Blackboard workspaces this session works on: {titles}"
        workspace_param = {"type": "string", "description": "optional workspace id; all of the session's workspaces when left out"}
        return [
            ToolSpec(
                "blackboard_list_docs",
                f"List the documents of {where}. Each workspace's instructions document says what it is for and "
                "how to write there; read it before you edit anything in that workspace.",
                {"type": "object", "properties": {"workspace": workspace_param}},
                self._safe(self.list_docs, ("workspace",)),
            ),
            ToolSpec(
                "blackboard_read",
                "Read a document as Markdown. Every top-level block starts with a "
                "<!-- block:<id> --> line, and `blocks` gives each block's digest; blackboard_edit needs both. "
                "view 'proposed' shows pending suggestions as if they were accepted.",
                {
                    "type": "object",
                    "properties": {
                        "doc": {"type": "string", "description": "document id from blackboard_list_docs"},
                        "view": {"type": "string", "enum": ["accepted", "proposed"]},
                        "range": {"type": "string", "description": "optional '<first block id>..<last block id>'"},
                    },
                    "required": ["doc"],
                },
                self._safe(self.read, ("doc", "view", "range")),
            ),
            ToolSpec(
                "blackboard_edit",
                "Change a workspace document. Give the whole batch in one call. Every op names a block id, and "
                "replace and delete also need the digest you got from blackboard_read; if a block changed since "
                "you read it the whole batch is refused (stale) and you must read again. A block with someone "
                "else's pending suggestions cannot be replaced or deleted until they are accepted or rejected "
                "(pending_suggestions: tell the person, do not retry); your own pending suggestions in a block "
                "are replaced by your new text. If the document is busy, or someone stopped this run (no_mandate), "
                "say so and stop. Edits become suggestions that people accept or reject.",
                {
                    "type": "object",
                    "properties": {
                        "doc": {"type": "string", "description": "document id from blackboard_list_docs"},
                        "ops": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 50,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "op": {"type": "string", "enum": ["replace", "insert_after", "insert_before", "delete"]},
                                    "block_id": {"type": "string"},
                                    "digest": {"type": "string", "description": "required for replace and delete"},
                                    "markdown": {
                                        "type": "string",
                                        "description": "new content for replace and insert ops; may hold several blocks",
                                    },
                                },
                                "required": ["op", "block_id"],
                            },
                        },
                        "note": {"type": "string", "description": "one line about the change, shown to the people"},
                    },
                    "required": ["doc", "ops"],
                },
                self._safe(self.edit, ("doc", "ops", "note")),
            ),
            ToolSpec(
                "blackboard_list_references",
                f"List the reference files people uploaded to {where}.",
                {"type": "object", "properties": {"workspace": workspace_param}},
                self._safe(self.list_references, ("workspace",)),
            ),
            ToolSpec(
                "blackboard_read_reference",
                "Read a text reference file (plain text, Markdown, CSV, JSON and the like) by its id.",
                {
                    "type": "object",
                    "properties": {"reference": {"type": "string", "description": "reference id from blackboard_list_references"}},
                    "required": ["reference"],
                },
                self._safe(self.read_reference, ("reference",)),
            ),
        ]

    @staticmethod
    def _safe(fn: Callable[..., Awaitable[dict[str, Any]]], accepted: tuple[str, ...]) -> Callable[..., Awaitable[dict[str, Any]]]:
        async def run(**kwargs: Any) -> dict[str, Any]:
            args = {k: v for k, v in kwargs.items() if k in accepted and v is not None}
            try:
                return {"ok": True, **await fn(**args)}
            except BlackboardError as exc:
                return {"ok": False, **exc.to_dict()}
            except TypeError as exc:
                return {"ok": False, "code": "invalid", "message": str(exc), "details": {}}
            except Exception as exc:  # noqa: BLE001 - the model gets a message instead of a crashed turn
                logger.exception("blackboard: tool %s failed", getattr(fn, "__name__", "?"))
                return {"ok": False, "code": INTERNAL, "message": str(exc) or type(exc).__name__, "details": {}}

        run.__name__ = getattr(fn, "__name__", "run")
        return run
