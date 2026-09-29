"""Rows of the host store as immutable dataclasses."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class User:
    id: str
    display_name: str
    is_operator: bool
    status: str
    created_at: str
    last_seen_at: str | None
    external_id: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "User":
        return cls(
            id=row["id"],
            display_name=row["display_name"],
            is_operator=bool(row["is_operator"]),
            status=row["status"],
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
            external_id=row["external_id"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "is_operator": self.is_operator,
            "disabled": self.status != "active",
            "created_at": self.created_at,
            "last_seen_at": self.last_seen_at,
        }


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    title: str
    created_by: str
    created_at: str
    archived_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Workspace":
        return cls(
            id=row["id"],
            name=row["name"],
            title=row["title"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            archived_at=row["archived_at"],
        )

    def to_dict(self, role: str | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "created_at": self.created_at,
            "archived": self.archived_at is not None,
        }
        if role is not None:
            data["role"] = role
        return data


@dataclass(frozen=True)
class Member:
    workspace_id: str
    user_id: str
    role: str
    joined_at: str
    display_name: str
    status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Member":
        return cls(
            workspace_id=row["workspace_id"],
            user_id=row["user_id"],
            role=row["role"],
            joined_at=row["joined_at"],
            display_name=row["display_name"],
            status=row["status"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "role": self.role,
            "joined_at": self.joined_at,
            "disabled": self.status != "active",
        }


@dataclass(frozen=True)
class Invite:
    code: str
    workspace_id: str
    role: str
    created_by: str
    created_at: str
    expires_at: str | None  # None: never expires
    max_uses: int | None  # None: no limit
    uses: int
    revoked_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Invite":
        return cls(
            code=row["code"],
            workspace_id=row["workspace_id"],
            role=row["role"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            max_uses=int(row["max_uses"]) if row["max_uses"] is not None else None,
            uses=int(row["uses"]),
            revoked_at=row["revoked_at"],
        )

    def state(self, now: str) -> str:
        """active | revoked | expired | used_up (ISO strings in UTC compare in order)."""
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and self.expires_at <= now:
            return "expired"
        if self.max_uses is not None and self.uses >= self.max_uses:
            return "used_up"
        return "active"


@dataclass(frozen=True)
class Doc:
    id: str
    workspace_id: str
    title: str
    is_instructions: bool
    is_pinned: bool
    created_by: str
    created_at: str
    archived_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Doc":
        return cls(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            is_instructions=bool(row["is_instructions"]),
            is_pinned=bool(row["is_pinned"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
            archived_at=row["archived_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "is_instructions": self.is_instructions,
            "is_pinned": self.is_pinned,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "archived": self.archived_at is not None,
        }


@dataclass(frozen=True)
class Reference:
    id: str
    workspace_id: str
    kind: str
    name: str
    mime: str
    size: int
    stored_path: str
    note: str
    uploaded_by: str
    uploaded_at: str
    removed_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Reference":
        return cls(
            id=row["id"],
            workspace_id=row["workspace_id"],
            kind=row["kind"],
            name=row["name"],
            mime=row["mime"],
            size=int(row["size"]),
            stored_path=row["stored_path"],
            note=row["note"],
            uploaded_by=row["uploaded_by"],
            uploaded_at=row["uploaded_at"],
            removed_at=row["removed_at"],
        )

    def to_dict(self, uploader_name: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "kind": self.kind,
            "name": self.name,
            "mime": self.mime,
            "size": self.size,
            "note": self.note,
            "uploaded_by": self.uploaded_by,
            "uploaded_by_name": uploader_name,
            "uploaded_at": self.uploaded_at,
        }


def _json(text: str | None, default: Any) -> Any:
    return json.loads(text) if text else default


@dataclass(frozen=True)
class Mandate:
    id: str
    workspace_id: str
    origin: str
    origin_ref: dict[str, Any]
    requester_id: str
    session_id: str | None
    instruction: str
    scope: dict[str, Any]
    permission_mode: str
    reply_target: dict[str, Any]
    status: str
    status_reason: str | None
    turn_count: int
    created_at: str
    started_at: str | None
    finished_at: str | None
    last_activity_at: str | None
    # A dispatched mandate's current turn (comment and chat origins).
    dispatched_at: str | None = None
    claimed_at: str | None = None
    turn_id: str | None = None
    answer: dict[str, Any] | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Mandate":
        return cls(
            id=row["id"],
            workspace_id=row["workspace_id"],
            origin=row["origin"],
            origin_ref=_json(row["origin_ref"], {}),
            requester_id=row["requester_id"],
            session_id=row["session_id"],
            instruction=row["instruction"],
            scope=_json(row["scope"], {}),
            permission_mode=row["permission_mode"],
            reply_target=_json(row["reply_target"], {}),
            status=row["status"],
            status_reason=row["status_reason"],
            turn_count=int(row["turn_count"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            last_activity_at=row["last_activity_at"],
            dispatched_at=row["dispatched_at"],
            claimed_at=row["claimed_at"],
            turn_id=row["turn_id"],
            answer=_json(row["answer"], None),
        )

    def to_dict(self, requester_name: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "origin": self.origin,
            "requester_id": self.requester_id,
            "requester_name": requester_name,
            "instruction": self.instruction,
            "scope": self.scope,
            "permission_mode": self.permission_mode,
            "status": self.status,
            "status_reason": self.status_reason,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_activity_at": self.last_activity_at,
            "origin_ref": self.origin_ref,
            "reply_target": self.reply_target,
            "turn_count": self.turn_count,
            "claimed_at": self.claimed_at,
        }


@dataclass(frozen=True)
class Receipt:
    id: str
    mandate_id: str
    doc_id: str
    status: str
    ops: list[dict[str, Any]]
    note: str
    before: list[dict[str, Any]] | None
    after: list[dict[str, Any]] | None
    suggestion_ids: list[str]
    error: dict[str, Any] | None
    created_at: str
    applied_at: str | None
    version_id: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Receipt":
        return cls(
            id=row["id"],
            mandate_id=row["mandate_id"],
            doc_id=row["doc_id"],
            status=row["status"],
            ops=_json(row["ops"], []),
            note=row["note"],
            before=_json(row["before"], None),
            after=_json(row["after"], None),
            suggestion_ids=_json(row["suggestion_ids"], []),
            error=_json(row["error"], None),
            created_at=row["created_at"],
            applied_at=row["applied_at"],
            version_id=row["version_id"] if "version_id" in row.keys() else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mandate_id": self.mandate_id,
            "doc_id": self.doc_id,
            "status": self.status,
            "ops": self.ops,
            "note": self.note,
            "before": self.before,
            "after": self.after,
            "suggestion_ids": self.suggestion_ids,
            "error": self.error,
            "created_at": self.created_at,
            "applied_at": self.applied_at,
            "version_id": self.version_id,
        }


@dataclass(frozen=True)
class Thread:
    id: str
    workspace_id: str
    doc_id: str
    anchor: dict[str, Any]
    created_by: str
    created_at: str
    resolved_at: str | None
    resolved_by: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Thread":
        return cls(
            id=row["id"],
            workspace_id=row["workspace_id"],
            doc_id=row["doc_id"],
            anchor=_json(row["anchor"], {}),
            created_by=row["created_by"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            resolved_by=row["resolved_by"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "doc_id": self.doc_id,
            "anchor": self.anchor,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
        }


@dataclass(frozen=True)
class Comment:
    id: str
    thread_id: str
    author_id: str
    author_kind: str
    body: str
    mentions: list[dict[str, str]]
    scope_switch: bool
    mandate_id: str | None
    decision_id: str | None
    created_at: str
    edited_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Comment":
        return cls(
            id=row["id"],
            thread_id=row["thread_id"],
            author_id=row["author_id"],
            author_kind=row["author_kind"],
            body=row["body"],
            mentions=_json(row["mentions"], []),
            scope_switch=bool(row["scope_switch"]),
            mandate_id=row["mandate_id"],
            decision_id=row["decision_id"],
            created_at=row["created_at"],
            edited_at=row["edited_at"],
        )

    def to_dict(self, author_name: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "author_id": self.author_id,
            "author_kind": self.author_kind,
            "author_name": author_name,
            "body": self.body,
            "mentions": self.mentions,
            "scope_switch": self.scope_switch,
            "mandate_id": self.mandate_id,
            "decision_id": self.decision_id,
            "created_at": self.created_at,
            "edited_at": self.edited_at,
        }


@dataclass(frozen=True)
class ChatMessage:
    id: str
    workspace_id: str
    author_id: str
    author_kind: str
    kind: str
    body: str
    mentions: list[dict[str, str]]
    mandate_id: str | None
    decision_id: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ChatMessage":
        return cls(
            id=row["id"],
            workspace_id=row["workspace_id"],
            author_id=row["author_id"],
            author_kind=row["author_kind"],
            kind=row["kind"],
            body=row["body"],
            mentions=_json(row["mentions"], []),
            mandate_id=row["mandate_id"],
            decision_id=row["decision_id"],
            created_at=row["created_at"],
        )

    def to_dict(self, author_name: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "author_id": self.author_id,
            "author_kind": self.author_kind,
            "author_name": author_name,
            "kind": self.kind,
            "body": self.body,
            "mentions": self.mentions,
            "mandate_id": self.mandate_id,
            "decision_id": self.decision_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class Decision:
    id: str
    workspace_id: str
    mandate_id: str
    requester_id: str
    doc_id: str | None
    block_id: str | None
    block_digest: str | None
    quote: str | None
    question: str
    options: list[dict[str, str]]
    recommended: int | None
    status: str
    answer: dict[str, Any] | None
    answered_by: str | None
    answered_at: str | None
    accepted_by: str | None
    accepted_at: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Decision":
        return cls(
            id=row["id"],
            workspace_id=row["workspace_id"],
            mandate_id=row["mandate_id"],
            requester_id=row["requester_id"],
            doc_id=row["doc_id"],
            block_id=row["block_id"],
            block_digest=row["block_digest"],
            quote=row["quote"],
            question=row["question"],
            options=_json(row["options"], []),
            recommended=row["recommended"],
            status=row["status"],
            answer=_json(row["answer"], None),
            answered_by=row["answered_by"],
            answered_at=row["answered_at"],
            accepted_by=row["accepted_by"],
            accepted_at=row["accepted_at"],
            created_at=row["created_at"],
        )

    def answer_label(self) -> str:
        """The chosen option's label, or the free text."""
        if not self.answer:
            return ""
        option = self.answer.get("option")
        if isinstance(option, int) and 0 <= option < len(self.options):
            return self.options[option]["label"]
        return str(self.answer.get("text") or "")

    def to_dict(self, names: dict[str, str] | None = None) -> dict[str, Any]:
        names = names or {}
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "mandate_id": self.mandate_id,
            "requester_id": self.requester_id,
            "requester_name": names.get(self.requester_id),
            "doc_id": self.doc_id,
            "block_id": self.block_id,
            "block_digest": self.block_digest,
            "quote": self.quote,
            "question": self.question,
            "options": self.options,
            "recommended": self.recommended,
            "status": self.status,
            "answer": self.answer,
            "answer_label": self.answer_label(),
            "answered_by": self.answered_by,
            "answered_by_name": names.get(self.answered_by or ""),
            "answered_at": self.answered_at,
            "accepted_by": self.accepted_by,
            "accepted_by_name": names.get(self.accepted_by or ""),
            "accepted_at": self.accepted_at,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class Bot:
    id: str
    name: str
    created_by: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Bot":
        return cls(
            id=row["id"],
            name=row["name"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
            revoked_at=row["revoked_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "revoked": self.revoked_at is not None,
        }


@dataclass(frozen=True)
class Identity:
    platform: str
    external_id: str
    user_id: str
    display_name: str | None
    bot_id: str | None
    linked_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Identity":
        return cls(
            platform=row["platform"],
            external_id=row["external_id"],
            user_id=row["user_id"],
            display_name=row["display_name"],
            bot_id=row["bot_id"],
            linked_at=row["linked_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "external_id": self.external_id,
            "display_name": self.display_name,
            "linked_at": self.linked_at,
        }
