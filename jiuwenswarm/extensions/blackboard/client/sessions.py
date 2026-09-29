"""Sessions attached to workspaces. The agent in an attached session gets Blackboard's tools for those
workspaces. The Gateway writes the file; the AgentServer reads it before every request."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from jiuwenswarm.extensions.blackboard.common.clock import now_iso
from jiuwenswarm.extensions.blackboard.common.jsonstore import JsonStore


@dataclass(frozen=True)
class Attachment:
    session_id: str
    host: str
    workspace_id: str
    attached_at: str
    title: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Attachment":
        return cls(
            session_id=str(raw["session_id"]),
            host=str(raw["host"]),
            workspace_id=str(raw["workspace_id"]),
            attached_at=str(raw.get("attached_at", "")),
            title=str(raw.get("title", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _entries(raw: Any) -> list[dict[str, Any]]:
    # One attachment per session was stored as a dict before sessions could hold several.
    if isinstance(raw, dict):
        return [raw]
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


class SessionAttachments:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, lambda: {"sessions": {}})

    def _all(self) -> list[Attachment]:
        out = []
        for raw in (self._store.read().get("sessions") or {}).values():
            for entry in _entries(raw):
                try:
                    out.append(Attachment.from_dict(entry))
                except (KeyError, TypeError):
                    continue
        return out

    def for_session(self, session_id: str) -> list[Attachment]:
        return [a for a in self._all() if a.session_id == session_id]

    def list(self, *, host: str | None = None, workspace_id: str | None = None) -> list[Attachment]:
        return [
            a
            for a in self._all()
            if (host is None or a.host == host) and (workspace_id is None or a.workspace_id == workspace_id)
        ]

    async def attach(self, session_id: str, host: str, workspace_id: str, title: str = "") -> Attachment:
        """Add a workspace to the session's; attaching one it already has keeps the first attachment."""
        attachment = Attachment(session_id=session_id, host=host, workspace_id=workspace_id, attached_at=now_iso(), title=title)

        def mutate(data: dict[str, Any]) -> Attachment:
            sessions = data.setdefault("sessions", {})
            entries = _entries(sessions.get(session_id))
            for entry in entries:
                if (entry.get("host"), entry.get("workspace_id")) == (host, workspace_id):
                    sessions[session_id] = entries
                    return Attachment.from_dict(entry)
            sessions[session_id] = [*entries, attachment.to_dict()]
            return attachment

        return await self._store.update(mutate)

    async def detach(self, session_id: str, host: str | None = None, workspace_id: str | None = None) -> list[Attachment]:
        """Remove one workspace from the session, or all of them; returns what was removed."""

        def mutate(data: dict[str, Any]) -> list[Attachment]:
            sessions = data.setdefault("sessions", {})
            entries = _entries(sessions.get(session_id))
            gone = [
                e
                for e in entries
                if (host is None or e.get("host") == host) and (workspace_id is None or e.get("workspace_id") == workspace_id)
            ]
            kept = [e for e in entries if e not in gone]
            if kept:
                sessions[session_id] = kept
            else:
                sessions.pop(session_id, None)
            return [Attachment.from_dict(e) for e in gone]

        return await self._store.update(mutate)

    async def detach_host(self, host: str) -> None:
        def mutate(data: dict[str, Any]) -> None:
            sessions = data.setdefault("sessions", {})
            for session_id in list(sessions):
                kept = [e for e in _entries(sessions[session_id]) if e.get("host") != host]
                if kept:
                    sessions[session_id] = kept
                else:
                    del sessions[session_id]

        await self._store.update(mutate)
