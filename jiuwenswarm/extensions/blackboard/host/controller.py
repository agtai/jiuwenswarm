"""Keeps the host running as the settings say, and gives its operator a host entry."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings, env_overrides
from jiuwenswarm.extensions.blackboard.host.runtime import HostRuntime, default_operator_name

if TYPE_CHECKING:
    from jiuwenswarm.extensions.blackboard.client.runtime import ClientRuntime

logger = logging.getLogger(__name__)

_LOOPBACK = ("127.0.0.1", "localhost", "::1")


class HostController:
    def __init__(
        self,
        data_dir: Path,
        version: str,
        load_settings: Callable[[], HostSettings],
        save_settings: Callable[[dict[str, Any]], HostSettings],
        client: "ClientRuntime",
        broadcast: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._data_dir = Path(data_dir)
        self._version = version
        self._save_settings = save_settings
        self._client = client
        self._broadcast = broadcast
        self._settings = load_settings()
        self.runtime: HostRuntime | None = None
        self.error: str | None = None
        # The name members see, known once the host has started.
        self.name: str | None = None

    @property
    def settings(self) -> HostSettings:
        return self._settings

    @property
    def running(self) -> bool:
        return self.runtime is not None and self.runtime.running

    async def start_if_enabled(self) -> None:
        if self._settings.enabled:
            await self.start()

    async def start(self) -> None:
        if self.running:
            return
        runtime = HostRuntime(lambda: self._settings, self._data_dir, self._version, self._docs_changed)
        try:
            ctx = await runtime.start()
            operator = await runtime.operator(default_operator_name(self._settings))
            token = await self._operator_token(runtime, ctx.host_uid, operator.id)
            self.name = await ctx.host_name()
            await self._client.ensure_self_entry(
                host_uid=ctx.host_uid,
                url=self._settings.local_url(),
                user_id=operator.id,
                token=token,
                name=self.name,
                display_name=operator.display_name,
            )
        except Exception as exc:  # noqa: BLE001 - reported in the panel; the client part keeps running
            logger.exception("blackboard: the host did not start")
            self.error = str(exc)
            await runtime.stop()
            self.runtime = None
        else:
            self.runtime = runtime
            self.error = None
        await self._broadcast(p.EV_HOST_STATUS, self.status())

    def _docs_changed(self) -> None:
        with contextlib.suppress(RuntimeError):  # no running loop: the Gateway is shutting down
            asyncio.get_running_loop().create_task(self._broadcast(p.EV_HOST_STATUS, self.status()))

    async def _operator_token(self, runtime: HostRuntime, host_uid: str, operator_id: str) -> str:
        """Reuse the operator's token if this instance still holds it; otherwise issue a new one."""
        entry = self._client.registry.find(host_uid=host_uid)
        if entry is not None and entry.user_id == operator_id:
            if await runtime.operator_token_matches(operator_id, entry.token):
                return entry.token
        return await runtime.rotate_token(operator_id)

    async def stop(self) -> None:
        if self.runtime is not None:
            await self.runtime.stop()
            self.runtime = None
        await self._broadcast(p.EV_HOST_STATUS, self.status())

    async def apply_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        old = self._settings
        # The core config writer blocks on a file lock; keep it off the event loop.
        self._settings = await asyncio.to_thread(self._save_settings, updates)
        new = self._settings
        if not new.enabled:
            if self.running:
                await self.stop()
            else:
                await self._broadcast(p.EV_HOST_STATUS, self.status())
        elif not self.running:
            await self.start()
        elif (new.bind, new.port) != (old.bind, old.port):
            await self.stop()
            await self.start()
        else:
            if new.name != old.name:
                await self._announce_name()
            if _docs_settings(new) != _docs_settings(old):
                assert self.runtime is not None
                await self.runtime.restart_docs()
            await self._broadcast(p.EV_HOST_STATUS, self.status())
        return self.status()

    async def _announce_name(self) -> None:
        """Pass a new host name to this instance's own entry and to every connected member."""
        ctx = self.runtime.ctx if self.runtime is not None else None
        if ctx is None:
            return
        self.name = await ctx.host_name()
        await self._client.rename_host(ctx.host_uid, self.name)
        await ctx.hub.publish_all(p.EV_HOST_UPDATED, {"name": self.name})

    async def health(self) -> dict[str, Any]:
        """What /blackboard/health reports, for the settings dialog."""
        ctx = self.runtime.ctx if self.runtime is not None else None
        if ctx is None:
            return {"ok": False}
        from jiuwenswarm.extensions.blackboard.host.api.ops import health

        return await health(ctx)

    def status(self) -> dict[str, Any]:
        runtime_status = self.runtime.status() if self.runtime is not None else {"running": False}
        settings = self._settings
        return {
            **runtime_status,
            "enabled": settings.enabled,
            "name": self.name if self.running else None,
            "settings": settings.to_dict(),
            "base_url": settings.base_url(),
            "error": self.error,
            # A loopback bind or a missing public address keeps other machines out.
            "reachable_from_other_machines": bool(settings.public_url) and settings.bind not in _LOOPBACK,
            # Settings fixed by BLACKBOARD_HOST_* variables; changing them in the dialog has no effect.
            "env_overrides": env_overrides(os.environ),
        }


def _docs_settings(settings: HostSettings) -> tuple:
    """What the document service is started with; a change restarts it."""
    return (
        settings.doc_port,
        settings.doc_api_port,
        settings.node_path,
        settings.allowed_origins,
        settings.allow_any_origin,
        settings.version_retention_days,
    )
