"""The shared-bot credentials this jiuwenswarm holds (milestone 7).

A jiuwenswarm installed as a bot in a team's IM workspace connects to a host with a bot link from the
host's operator (``<host url>/blackboard/bot#<bot token>``). Kept in
``<data root>/blackboard/client/bots.json``, apart from ``hosts.json``: a bot has no member token, gets
no events, and is used only for IM requests, on behalf of the person who wrote.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.clock import now_iso
from jiuwenswarm.extensions.blackboard.common.errors import invalid
from jiuwenswarm.extensions.blackboard.common.jsonstore import JsonStore
from jiuwenswarm.extensions.blackboard.common.tokens import BOT_TOKEN_PREFIX


@dataclass(frozen=True)
class BotEntry:
    id: str
    host_uid: str
    host_name: str
    url: str
    token: str
    bot_id: str
    bot_name: str
    added_at: str = field(default_factory=now_iso)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BotEntry":
        return cls(**{f.name: data[f.name] for f in fields(cls) if f.name in data})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def public(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("token", None)
        return data


def parse_bot_link(link: str) -> tuple[str, str]:
    """``(host base url, bot token)`` from a bot link; the base may sit under a path prefix."""
    if not isinstance(link, str) or not link.strip():
        raise invalid("paste the bot link", field="link")
    parsed = urlparse(link.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise invalid("a bot link starts with http:// or https://", field="link")
    path = parsed.path.rstrip("/")
    if not path.endswith(p.BOT_PATH) or not parsed.fragment.startswith(BOT_TOKEN_PREFIX):
        raise invalid("this is not a Blackboard bot link", field="link")
    return f"{parsed.scheme}://{parsed.netloc}{path[: -len(p.BOT_PATH)]}".rstrip("/"), parsed.fragment


class BotRegistry:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, lambda: {"bots": []})

    def entries(self) -> list[BotEntry]:
        out = []
        for raw in self._store.read().get("bots", []):
            if isinstance(raw, dict):
                try:
                    out.append(BotEntry.from_dict(raw))
                except TypeError:
                    continue
        return out

    def get(self, entry_id: str) -> BotEntry | None:
        return next((e for e in self.entries() if e.id == entry_id), None)

    async def upsert(self, entry: BotEntry) -> BotEntry:
        """One bot per host: a new link for the same host replaces the old one."""

        def mutate(data: dict[str, Any]) -> None:
            kept = [b for b in data.get("bots", []) if isinstance(b, dict) and b.get("host_uid") != entry.host_uid and b.get("id") != entry.id]
            data["bots"] = [*kept, entry.to_dict()]

        await self._store.update(mutate)
        return entry

    async def remove(self, entry_id: str) -> bool:
        def mutate(data: dict[str, Any]) -> bool:
            before = len(data.get("bots", []))
            data["bots"] = [b for b in data.get("bots", []) if isinstance(b, dict) and b.get("id") != entry_id]
            return len(data["bots"]) != before

        return await self._store.update(mutate)
