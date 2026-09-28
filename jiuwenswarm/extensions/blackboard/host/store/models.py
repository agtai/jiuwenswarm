"""Rows of the host store as immutable dataclasses."""

from __future__ import annotations

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
