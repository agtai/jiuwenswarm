"""Blackboard's tools for an agent.

Every session of a member can read the workspaces the member belongs to, on every host this
jiuwenswarm joined (milestone 7); a session attached to a workspace can also edit it, and a turn the
dispatcher started on a comment or chat task can ask the workspace a question. On a jiuwenswarm that
serves a team's IM as a shared bot, an IM request reads with the bot's credentials on behalf of the
person who wrote, once they connected their IM account (``blackboard_link_identity``).

Framework-free: every tool is an async function that returns a dict and never raises, so the model
reads each error and can act on it. ``bridge.py`` turns them into openjiuwen tools. The calls go to
the workspace's host from the AgentServer process.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from jiuwenswarm.extensions.blackboard.client.hosts import HostRegistry
from jiuwenswarm.extensions.blackboard.client.link import call_host
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import INTERNAL, NOT_FOUND, NOT_LINKED, BlackboardError

if TYPE_CHECKING:
    from jiuwenswarm.extensions.blackboard.client.bots import BotRegistry

logger = logging.getLogger(__name__)

# The host may wait up to a minute for another agent to let go of a document.
EDIT_TIMEOUT_S = 90.0
# How long the list of readable workspaces is trusted before it is asked again.
DIRECTORY_TTL_S = 300.0
CHAT_LIMIT = 30
AGENT_HEADERS = {p.AGENT_HEADER: "1"}

WORKSPACE_REQUIRED = "workspace_required"
AMBIGUOUS_WORKSPACE = "ambiguous_workspace"
READ_ONLY = "read_only"
NAMING = "Workspaces are named as @bb:<name> in messages; pass that (or the workspace's title or id) as `workspace`."


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
    name: str = ""
    host_name: str = ""
    role: str = ""


@dataclass(frozen=True)
class MandateRef:
    """The comment or chat task a dispatched turn works on."""

    host_id: str
    workspace_id: str
    mandate_id: str
    origin: str = ""


@dataclass(frozen=True)
class Access:
    """Whose Blackboard a request reads: the member's own (``member``), a connected IM account's
    through the shared bot (``bot``, with ``on_behalf`` "<platform>:<platform user id>"), or nobody's
    (``denied``, with the reason the tools give)."""

    kind: str = "member"
    on_behalf: str = ""
    reason: str = ""


# The readable workspaces per access and set of hosts, shared by every session of the process.
_DIRECTORY: dict[tuple[Any, ...], tuple[float, list[WorkspaceRef]]] = {}


def forget_directory() -> None:
    _DIRECTORY.clear()


def _label(w: WorkspaceRef) -> dict[str, Any]:
    return {"workspace": f"@bb:{w.name}" if w.name else w.workspace_id, "id": w.workspace_id, "title": w.title, "host": w.host_name, "role": w.role}


@dataclass
class SessionTools:
    registry: HostRegistry | None
    session_id: str
    # The workspaces this session is attached to: the ones it may edit.
    workspaces: list[WorkspaceRef]
    # The current request id; set before every turn, so edits of one turn share a mandate.
    turn_id: str = ""
    # Set for a turn the dispatcher started on a comment or chat task: edits go under its mandate,
    # and the agent may ask the workspace a question.
    mandate: MandateRef | None = None
    bots: "BotRegistry | None" = None
    access: Access = field(default_factory=Access)
    # Which workspace a document or reference id belongs to, learned from the lists.
    _homes: dict[str, WorkspaceRef] = field(default_factory=dict)

    # ---- hosts and workspaces ----

    def _hosts(self) -> list[tuple[str, str, str, str]]:
        """(host id, host name, url, token) for the current access."""
        if self.access.kind == "bot":
            return [(b.id, b.host_name, b.url, b.token) for b in (self.bots.entries() if self.bots else [])]
        return [(e.id, e.name, e.url, e.token) for e in (self.registry.entries() if self.registry else [])]

    async def _call(self, ws: WorkspaceRef, method: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        if self.access.kind == "denied":
            raise BlackboardError(NOT_LINKED, self.access.reason)
        host = next((h for h in self._hosts() if h[0] == ws.host_id), None)
        if host is None:
            raise BlackboardError(NOT_FOUND, "this jiuwenswarm no longer knows the workspace's host", {"workspace": ws.workspace_id})
        headers = dict(AGENT_HEADERS)
        if self.access.kind == "bot":
            headers[p.ON_BEHALF_HEADER] = self.access.on_behalf
        return await call_host(host[2], method, params, token=host[3], timeout=timeout, headers=headers)

    async def _directory(self, refresh: bool = False) -> list[WorkspaceRef]:
        hosts = self._hosts()
        key = (self.access.kind, self.access.on_behalf, tuple((h[0], h[2]) for h in hosts))
        cached = _DIRECTORY.get(key)
        if cached is not None and not refresh and cached[0] > time.monotonic():
            return cached[1]
        found: list[WorkspaceRef] = []
        problems: list[BlackboardError] = []
        for host_id, host_name, _, _ in hosts:
            try:
                me = await self._call(WorkspaceRef(host_id, ""), p.ME, {})
            except BlackboardError as exc:
                problems.append(exc)
                continue
            name = host_name or str((me.get("host") or {}).get("name") or "")
            for w in me.get("workspaces", []):
                found.append(WorkspaceRef(host_id, w["id"], w.get("title", ""), w.get("name", ""), name, w.get("role", "")))
        if not found and problems:
            raise problems[0]
        _DIRECTORY[key] = (time.monotonic() + DIRECTORY_TTL_S, found)
        return found

    async def _resolve(self, workspace: str | None) -> list[WorkspaceRef]:
        """The workspaces a tool works on: the named one, else the attached ones, else the only one."""
        if not workspace:
            if self.workspaces:
                return self.workspaces
            known = await self._directory()
            if len(known) == 1:
                return known
            raise BlackboardError(
                WORKSPACE_REQUIRED,
                "say which workspace, as @bb:<name>",
                {"workspaces": [_label(w) for w in known]},
            )
        wanted = workspace.strip()
        if wanted.lower().startswith("@bb:"):
            wanted = wanted[4:].strip()
        attached = [w for w in self.workspaces if w.workspace_id == wanted]
        if attached:
            return attached
        known: list[WorkspaceRef] = []
        for refresh in (False, True):
            known = await self._directory(refresh=refresh)
            matches = (
                [w for w in known if w.workspace_id == wanted]
                or [w for w in known if w.name and w.name == wanted.lower()]
                or [w for w in known if w.title.lower() == wanted.lower()]
            )
            if len(matches) == 1:
                return matches
            if len(matches) > 1:
                raise BlackboardError(
                    AMBIGUOUS_WORKSPACE,
                    "several workspaces have this name on different hosts; pass the id of the one you mean",
                    {"candidates": [_label(w) for w in matches]},
                )
        raise BlackboardError(
            WORKSPACE_REQUIRED,
            f"no workspace you can read is called {workspace}",
            {"workspaces": [_label(w) for w in known]},
        )

    async def _home(self, item: str, refresh: Callable[[], Awaitable[Any]], kind: str, workspace: str | None = None) -> WorkspaceRef:
        if item not in self._homes:
            # Lists the named workspace, the attached ones, or the only one; asks which when unclear.
            await refresh(workspace)
        home = self._homes.get(item)
        if home is None:
            raise BlackboardError(NOT_FOUND, f"no {kind} with this id in the workspaces looked at", {kind: item})
        return home

    def _attached(self, ws: WorkspaceRef) -> bool:
        return any((w.host_id, w.workspace_id) == (ws.host_id, ws.workspace_id) for w in self.workspaces)

    # ---- reading ----

    async def list_workspaces(self) -> dict[str, Any]:
        known = await self._directory(refresh=True)
        return {"workspaces": [{**_label(w), "editable_here": self._attached(w)} for w in known]}

    async def list_docs(self, workspace: str | None = None) -> dict[str, Any]:
        out = []
        for ws in await self._resolve(workspace):
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
                    **({"workspace": f"@bb:{ws.name}"} if ws.name else {}),
                    "docs": docs,
                    "instructions_doc": next((d["id"] for d in docs if d["is_instructions"]), None),
                }
            )
        return {"workspaces": out}

    async def read(self, doc: str, view: str = "accepted", range: str | None = None, workspace: str | None = None) -> dict[str, Any]:  # noqa: A002
        ws = await self._home(doc, self.list_docs, "doc", workspace)
        params: dict[str, Any] = {"doc_id": doc, "view": view if view in ("accepted", "proposed") else "accepted"}
        if range:
            params["range"] = range
        result = await self._call(ws, p.DOC_READ, params)
        blocks = [
            {"id": b["id"], "digest": b["digest"], "pending_suggestions": b.get("hasPendingSuggestions", False)}
            for b in result.get("blocks", [])
        ]
        out: dict[str, Any] = {"doc": doc, "workspace": ws.workspace_id, "view": params["view"], "markdown": result.get("markdown", ""), "blocks": blocks}
        if any(b["pending_suggestions"] for b in blocks):
            out["pending_suggestions"] = await self._pending(ws, doc, {b["id"] for b in blocks})
        if not self._attached(ws):
            out["read_only"] = True
        return out

    async def _pending(self, ws: WorkspaceRef, doc: str, block_ids: set[str]) -> list[dict[str, Any]]:
        listed = await self._call(ws, p.SUGGESTION_LIST, {"doc_id": doc})
        out = []
        for s in listed.get("suggestions", []):
            if not block_ids & set(s.get("blockIds") or []):
                continue
            author = s.get("author") or {}
            kind = "replace" if s.get("inserted") and s.get("deleted") else "insert" if s.get("inserted") else "delete"
            out.append(
                {
                    "id": s.get("id"),
                    "kind": kind,
                    "by": {"kind": author.get("kind"), "user_id": author.get("id")},
                    "inserted": s.get("inserted", ""),
                    "deleted": s.get("deleted", ""),
                    "blocks": s.get("blockIds") or [],
                }
            )
        return out

    async def list_references(self, workspace: str | None = None) -> dict[str, Any]:
        out = []
        for ws in await self._resolve(workspace):
            result = await self._call(ws, p.REFERENCE_LIST, {"workspace_id": ws.workspace_id})
            refs = [
                {"id": r["id"], "name": r["name"], "kind": r["kind"], "mime": r["mime"], "size": r["size"], "note": r["note"]}
                for r in result.get("references", [])
            ]
            for r in refs:
                self._homes[r["id"]] = ws
            out.append({"id": ws.workspace_id, "title": ws.title, "references": refs})
        return {"workspaces": out}

    async def read_reference(self, reference: str, workspace: str | None = None) -> dict[str, Any]:
        ws = await self._home(reference, self.list_references, "reference", workspace)
        result = await self._call(ws, p.REFERENCE_READ, {"reference_id": reference})
        return {
            "reference": reference,
            "name": result.get("name"),
            "kind": result.get("kind"),
            "truncated": bool(result.get("truncated")),
            "text": result.get("text", ""),
        }

    async def list_decisions(self, workspace: str | None = None, status: str | None = None) -> dict[str, Any]:
        out = []
        for ws in await self._resolve(workspace):
            params: dict[str, Any] = {"workspace_id": ws.workspace_id}
            if status:
                params["status"] = status
            result = await self._call(ws, p.DECISION_LIST, params)
            decisions = [
                {
                    "id": d["id"],
                    "question": d["question"],
                    "options": [o.get("label") for o in d.get("options", [])],
                    "status": d["status"],
                    "answer": d.get("answer_label") or None,
                    "answered_by": d.get("answered_by_name"),
                    "accepted_by": d.get("accepted_by_name"),
                    "asked_for": d.get("requester_name"),
                    "created_at": d.get("created_at"),
                }
                for d in result.get("decisions", [])
            ]
            out.append({"id": ws.workspace_id, "title": ws.title, "decisions": decisions})
        return {"workspaces": out}

    async def read_chat(self, workspace: str | None = None, limit: int = CHAT_LIMIT) -> dict[str, Any]:
        [ws, *_] = await self._resolve(workspace)
        count = max(1, min(100, int(limit or CHAT_LIMIT)))
        result = await self._call(ws, p.CHAT_LIST, {"workspace_id": ws.workspace_id, "limit": count})

        def author(m: dict[str, Any]) -> str:
            name = m.get("author_name") or ""
            return f"{name}'s agent" if m.get("author_kind") == "agent" else name if m.get("author_kind") == "person" else "Blackboard"

        messages = [
            {"at": m.get("created_at"), "from": author(m), "kind": m.get("kind"), "text": m.get("body", "")}
            for m in result.get("messages", [])
        ]
        return {"workspace": ws.workspace_id, "title": ws.title, "messages": messages, "more_before": bool(result.get("has_more"))}

    # ---- changing (attached sessions and dispatched turns) ----

    async def edit(self, doc: str, ops: list[dict[str, Any]], note: str = "") -> dict[str, Any]:
        ws = await self._home(doc, self.list_docs, "doc")
        if not self._attached(ws) and self.mandate is None:
            raise BlackboardError(
                READ_ONLY,
                "this session can only read that workspace; to change it, attach a web chat session to it or comment with @jiuwen",
                {"doc": doc},
            )
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
        if result.get("changed") is False:
            return {**result, "message": "Nothing changed: the Markdown you sent equals the current text of these blocks."}
        return {
            **result,
            "message": "Your changes are suggestions now; the people in the workspace accept or reject them. When you are done, sum up what you suggested in one or two short sentences, naming sections by their headings, not by block ids.",
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

    # ---- a shared bot connecting the person who wrote ----

    async def link_identity(self, code: str) -> dict[str, Any]:
        if self.access.kind != "bot":
            raise BlackboardError("not_a_bot", "only a shared bot connects IM accounts")
        platform, _, external_id = self.access.on_behalf.partition(":")
        problems: list[BlackboardError] = []
        for host_id, host_name, url, token in self._hosts():
            try:
                result = await call_host(
                    url, p.IDENTITY_LINK, {"code": code, "platform": platform, "external_id": external_id}, token=token, headers=AGENT_HEADERS
                )
            except BlackboardError as exc:
                problems.append(exc)
                continue
            forget_directory()
            user = result.get("user") or {}
            return {
                "connected_as": user.get("display_name"),
                "host": result.get("host") or host_name,
                "replaced": bool(result.get("replaced")),
                "message": f"Connected as {user.get('display_name')} on {result.get('host') or host_name}.",
            }
        if problems:
            raise problems[0]
        raise BlackboardError(NOT_FOUND, "this jiuwenswarm is not a bot of any Blackboard host")

    # ---- the tools the model sees ----

    def specs(self) -> list[ToolSpec]:
        specs = self._read_specs()
        if self.workspaces and self.access.kind == "member":
            specs.insert(3, self._edit_spec())
        if self.mandate is not None:
            specs.append(self._ask_spec())
        if self.access.kind == "bot":
            specs.append(self._link_spec())
        return specs

    def _workspace_param(self) -> dict[str, Any]:
        if self.workspaces:
            default = "left out: the workspaces this session works on"
        else:
            default = "required when you can read more than one workspace"
        return {"type": "string", "description": f"@bb:<name>, the workspace's title, or its id; {default}"}

    def _read_specs(self) -> list[ToolSpec]:
        if self.workspaces and self.access.kind == "member":
            titles = ", ".join(f'"{w.title}" ({w.workspace_id})' if w.title else w.workspace_id for w in self.workspaces)
            scope = f"This session works on {titles}, and can edit only those; other workspaces it can only read. "
            # Without this the model looks for "the section on X" in local files.
            where = (
                f"This session works on {titles}. When the person mentions a document, section, heading or passage "
                "without saying where it is, it is in there: find it with this tool and blackboard_read before "
                "anything else. These are Blackboard documents, not files on this computer. "
            )
        else:
            scope = "Reading only: changing a workspace needs a web chat session attached to it. "
            where = ""
        workspace = self._workspace_param()
        return [
            ToolSpec(
                "blackboard_list_workspaces",
                f"List the Blackboard workspaces you can read, on every host, with their @bb:<name>. {scope}{NAMING}",
                {"type": "object", "properties": {}},
                self._safe(self.list_workspaces, ()),
            ),
            ToolSpec(
                "blackboard_list_docs",
                f"{where}List a workspace's documents. Each workspace's instructions document says what it is for and "
                f"how to write there; read it before you edit anything in that workspace. {NAMING}",
                {"type": "object", "properties": {"workspace": workspace}},
                self._safe(self.list_docs, ("workspace",)),
            ),
            ToolSpec(
                "blackboard_read",
                "Read a document as Markdown, as accepted (pending suggestions left out; `pending_suggestions` lists "
                "them). Every top-level block starts with a <!-- block:<id> --> line, and `blocks` gives each block's "
                "digest, which blackboard_edit needs. view 'proposed' shows pending suggestions as if accepted. Block, "
                "document and workspace ids are for the tools only: when you talk to people, name documents and "
                "sections by their titles and headings, never by id.",
                {
                    "type": "object",
                    "properties": {
                        "doc": {"type": "string", "description": "document id from blackboard_list_docs"},
                        "workspace": workspace,
                        "view": {"type": "string", "enum": ["accepted", "proposed"]},
                        "range": {"type": "string", "description": "optional '<first block id>..<last block id>'"},
                    },
                    "required": ["doc"],
                },
                self._safe(self.read, ("doc", "view", "range", "workspace")),
            ),
            ToolSpec(
                "blackboard_list_references",
                f"List the reference files people uploaded to a workspace. {NAMING}",
                {"type": "object", "properties": {"workspace": workspace}},
                self._safe(self.list_references, ("workspace",)),
            ),
            ToolSpec(
                "blackboard_read_reference",
                "Read a reference file's text by its id: text, Markdown, CSV, JSON, PDF and Word files. Images and "
                "other kinds cannot be read (unsupported_reference).",
                {
                    "type": "object",
                    "properties": {
                        "reference": {"type": "string", "description": "reference id from blackboard_list_references"},
                        "workspace": workspace,
                    },
                    "required": ["reference"],
                },
                self._safe(self.read_reference, ("reference", "workspace")),
            ),
            ToolSpec(
                "blackboard_list_decisions",
                "List a workspace's decisions: the questions agents asked, the options, and who answered and accepted "
                f"what. status: open, proposed, answered or cancelled. {NAMING}",
                {
                    "type": "object",
                    "properties": {
                        "workspace": workspace,
                        "status": {"type": "string", "enum": ["open", "proposed", "answered", "cancelled"]},
                    },
                },
                self._safe(self.list_decisions, ("workspace", "status")),
            ),
            ToolSpec(
                "blackboard_read_chat",
                f"Read a workspace chat's latest messages, oldest first (30 unless limit says otherwise). {NAMING}",
                {
                    "type": "object",
                    "properties": {"workspace": workspace, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                },
                self._safe(self.read_chat, ("workspace", "limit")),
            ),
        ]

    def _edit_spec(self) -> ToolSpec:
        return ToolSpec(
            "blackboard_edit",
            "Change a document of a workspace this session works on. Give the whole batch in one call. Every op "
            "names a block id, and replace and delete also need the digest you got from blackboard_read; if a block "
            "changed since you read it the whole batch is refused (stale) and you must read again. A block with "
            "someone else's pending suggestions cannot be replaced or deleted until they are accepted or rejected "
            "(pending_suggestions: tell the person, do not retry); your own pending suggestions in a block are "
            "replaced by your new text. If the document is busy, or someone stopped this run (no_mandate), say so "
            "and stop. Edits become suggestions that people accept or reject. Limits on what you may edit come back "
            "only as read_only, out_of_scope or no_mandate; internal is a fault on the host (try once more at most, "
            "then tell the person), and unsupported_edit means to use insert_after and delete instead of replace.",
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
                                "markdown": {"type": "string", "description": "new content for replace and insert ops; may hold several blocks"},
                            },
                            "required": ["op", "block_id"],
                        },
                    },
                    "note": {"type": "string", "description": "one line about the change, shown to the people"},
                },
                "required": ["doc", "ops"],
            },
            self._safe(self.edit, ("doc", "ops", "note")),
        )

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

    def _link_spec(self) -> ToolSpec:
        return ToolSpec(
            "blackboard_link_identity",
            "Connect the IM account of the person writing to their Blackboard user, so you can read their "
            "workspaces for them. Use it when they send a link code, for example '@bb link 7K3M-2Q9F' or just the "
            "code; they get the code in the jiuwenswarm web app (Blackboard settings, Connected IM accounts). If "
            "a Blackboard tool answers not_linked, tell them how to get a code.",
            {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "the link code, such as 7K3M-2Q9F"}},
                "required": ["code"],
            },
            self._safe(self.link_identity, ("code",)),
        )

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
