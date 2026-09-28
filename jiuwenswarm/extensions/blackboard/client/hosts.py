"""Hosts this jiuwenswarm has joined, with the member token for each.

Kept in ``<data root>/blackboard/client/hosts.json`` rather than config.yaml, so
tokens do not show up wherever config is displayed. Both processes read it; the
AgentServer's tools (milestone 4) use the same entries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jiuwenswarm.extensions.blackboard.common.jsonstore import JsonStore
from jiuwenswarm.extensions.blackboard.common.clock import now_iso


@dataclass(frozen=True)
class HostEntry:
    id: str
    host_uid: str
    name: str
    url: str
    token: str
    user_id: str
    display_name: str = ""
    doc_url: str = ""
    is_self: bool = False
    added_at: str = field(default_factory=now_iso)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HostEntry":
        known = {f.name: data[f.name] for f in fields(cls) if f.name in data}
        return cls(**known)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def public(self) -> dict[str, Any]:
        """What the browser may see: everything but the token."""
        data = self.to_dict()
        data.pop("token", None)
        return data


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


class HostRegistry:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, lambda: {"hosts": [], "default_host": ""})

    def _data(self) -> dict[str, Any]:
        return self._store.read()

    def entries(self) -> list[HostEntry]:
        out = []
        for raw in self._data().get("hosts", []):
            if isinstance(raw, dict):
                try:
                    out.append(HostEntry.from_dict(raw))
                except TypeError:
                    continue
        return out

    def get(self, host_id: str) -> HostEntry | None:
        return next((e for e in self.entries() if e.id == host_id), None)

    def default_id(self) -> str:
        data = self._data()
        default = data.get("default_host") or ""
        ids = [e.id for e in self.entries()]
        if default in ids:
            return default
        return ids[0] if ids else ""

    def find(self, *, host_uid: str | None = None, url: str | None = None) -> HostEntry | None:
        entries = self.entries()
        if host_uid:
            match = next((e for e in entries if e.host_uid == host_uid), None)
            if match is not None:
                return match
        if url:
            wanted = normalize_url(url)
            return next((e for e in entries if normalize_url(e.url) == wanted), None)
        return None

    async def upsert(self, entry: HostEntry, *, make_default: bool = False) -> HostEntry:
        def mutate(data: dict[str, Any]) -> None:
            hosts = [h for h in data.get("hosts", []) if isinstance(h, dict) and h.get("id") != entry.id]
            hosts.append(entry.to_dict())
            data["hosts"] = hosts
            if make_default or not data.get("default_host"):
                data["default_host"] = entry.id

        await self._store.update(mutate)
        return entry

    async def remove(self, host_id: str) -> bool:
        def mutate(data: dict[str, Any]) -> bool:
            before = len(data.get("hosts", []))
            data["hosts"] = [h for h in data.get("hosts", []) if isinstance(h, dict) and h.get("id") != host_id]
            if data.get("default_host") == host_id:
                data["default_host"] = data["hosts"][0]["id"] if data["hosts"] else ""
            return len(data["hosts"]) != before

        return await self._store.update(mutate)

    async def set_default(self, host_id: str) -> None:
        def mutate(data: dict[str, Any]) -> None:
            data["default_host"] = host_id

        await self._store.update(mutate)
