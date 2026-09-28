"""The client part in the Gateway: known hosts, their links, joining, and event forwarding."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any, Awaitable, Callable

from jiuwenswarm.extensions.blackboard.client.hosts import HostEntry, HostRegistry
from jiuwenswarm.extensions.blackboard.client.invite_link import parse_invite_link
from jiuwenswarm.extensions.blackboard.client.link import HostLink, call_host
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.clock import now_iso
from jiuwenswarm.extensions.blackboard.common.errors import INVALID, BlackboardError, not_found
from jiuwenswarm.extensions.blackboard.common.ids import new_id

logger = logging.getLogger(__name__)

Broadcast = Callable[[str, dict[str, Any]], Awaitable[None]]


class ClientRuntime:
    def __init__(self, hosts_file: Path, broadcast: Broadcast) -> None:
        self.registry = HostRegistry(hosts_file)
        self._broadcast = broadcast
        self._links: dict[str, HostLink] = {}
        self._join_lock = asyncio.Lock()

    async def start(self) -> None:
        for entry in self.registry.entries():
            self._open_link(entry)

    async def stop(self) -> None:
        links = list(self._links.values())
        self._links.clear()
        await asyncio.gather(*(link.stop() for link in links), return_exceptions=True)

    def _open_link(self, entry: HostEntry) -> HostLink:
        link = HostLink(entry.id, entry.url, entry.token, self._on_event, self._on_status, self._on_ready)
        self._links[entry.id] = link
        link.start()
        return link

    async def _reopen_link(self, entry: HostEntry) -> None:
        old = self._links.pop(entry.id, None)
        if old is not None:
            await old.stop()
        self._open_link(entry)

    async def _on_event(self, host_id: str, event: str, payload: dict[str, Any]) -> None:
        if event == p.EV_HOST_UPDATED:
            await self._rename_entry(host_id, payload.get("name"))
            return
        await self._broadcast(event, {**payload, "host": host_id})

    async def _on_status(self, host_id: str, status: str) -> None:
        await self._broadcast(p.EV_HOSTS_UPDATED, {"host": host_id, "status": status})

    async def _on_ready(self, host_id: str, host: dict[str, Any]) -> None:
        # The host's current name, in case it was renamed while this link was down.
        await self._rename_entry(host_id, host.get("name"))

    async def _rename_entry(self, host_id: str, name: Any) -> None:
        entry = self.registry.get(host_id)
        if entry is None or not isinstance(name, str) or not name.strip() or name == entry.name:
            return
        await self.registry.upsert(replace(entry, name=name.strip()))
        await self._broadcast(p.EV_HOSTS_UPDATED, {"host": host_id})

    # ---- views and calls ----

    def hosts_view(self) -> dict[str, Any]:
        default = self.registry.default_id()
        hosts = []
        for entry in self.registry.entries():
            link = self._links.get(entry.id)
            hosts.append(
                {
                    **entry.public(),
                    "is_default": entry.id == default,
                    "status": link.status if link else "stopped",
                }
            )
        return {"hosts": hosts, "default_host": default}

    def _entry(self, host_id: str | None) -> HostEntry:
        chosen = host_id or self.registry.default_id()
        if not chosen:
            raise not_found("join a Blackboard host first")
        entry = self.registry.get(chosen)
        if entry is None:
            raise not_found("unknown host", host=chosen)
        return entry

    async def call(self, host_id: str | None, method: str, params: dict[str, Any]) -> dict[str, Any]:
        entry = self._entry(host_id)
        link = self._links.get(entry.id) or self._open_link(entry)
        return await link.call(method, params)

    # ---- changes ----

    async def join(self, link_text: str, display_name: str | None = None) -> dict[str, Any]:
        base_url, code = parse_invite_link(link_text)
        async with self._join_lock:
            known = self.registry.find(url=base_url)
            params: dict[str, Any] = {"code": code}
            if known is not None:
                params["token"] = known.token
            if display_name:
                params["display_name"] = display_name
            result = await call_host(base_url, p.INVITE_ACCEPT, params)
            host = result.get("host") if isinstance(result.get("host"), dict) else {}
            host_uid = str(host.get("host_uid") or "")
            existing = self.registry.find(host_uid=host_uid, url=base_url)
            token = result.get("token") or (existing.token if existing else None)
            if not token:
                raise BlackboardError(INVALID, "the host did not return a member token")
            entry = HostEntry(
                id=existing.id if existing else new_id("h"),
                host_uid=host_uid,
                name=existing.name if existing else str(host.get("name") or base_url),
                url=existing.url if existing else base_url,
                token=token,
                user_id=str(result.get("user_id") or ""),
                display_name=str(result.get("display_name") or ""),
                doc_url=str(host.get("doc_public_url") or ""),
                is_self=existing.is_self if existing else False,
                added_at=existing.added_at if existing else now_iso(),
            )
            await self.registry.upsert(entry)
            if existing is None or existing.token != token or existing.url != entry.url:
                await self._reopen_link(entry)
        await self._broadcast(p.EV_HOSTS_UPDATED, {"host": entry.id})
        return {"host": entry.id, "workspace": result.get("workspace"), "joined": result.get("joined", True)}

    async def ensure_self_entry(
        self, *, host_uid: str, url: str, user_id: str, token: str, name: str, display_name: str
    ) -> HostEntry:
        """The entry through which the host's operator uses their own host."""
        existing = self.registry.find(host_uid=host_uid)
        entry = HostEntry(
            id=existing.id if existing else new_id("h"),
            host_uid=host_uid,
            name=name,
            url=url,
            token=token,
            user_id=user_id,
            display_name=display_name,
            doc_url=existing.doc_url if existing else "",
            is_self=True,
            added_at=existing.added_at if existing else now_iso(),
        )
        changed = existing is None or existing.to_dict() != entry.to_dict()
        if changed:
            await self.registry.upsert(entry)
        if changed or entry.id not in self._links:
            await self._reopen_link(entry)
            await self._broadcast(p.EV_HOSTS_UPDATED, {"host": entry.id})
        return entry

    async def rename_host(self, host_uid: str, name: str) -> None:
        """This instance's own host was renamed; its entry follows."""
        entry = self.registry.find(host_uid=host_uid)
        if entry is not None:
            await self._rename_entry(entry.id, name)

    async def remove(self, host_id: str) -> None:
        if self.registry.get(host_id) is None:
            raise not_found("unknown host", host=host_id)
        await self.registry.remove(host_id)
        link = self._links.pop(host_id, None)
        if link is not None:
            await link.stop()
        await self._broadcast(p.EV_HOSTS_UPDATED, {"host": host_id, "removed": True})

    async def set_default(self, host_id: str) -> None:
        if self.registry.get(host_id) is None:
            raise not_found("unknown host", host=host_id)
        await self.registry.set_default(host_id)
        await self._broadcast(p.EV_HOSTS_UPDATED, {"host": host_id})
