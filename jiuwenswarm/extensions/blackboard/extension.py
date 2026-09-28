"""Blackboard as an application plugin.

The same plugin runs in two roles. Every jiuwenswarm runs the client part: it
keeps a link to each host this person joined and proxies the browser's calls.
An instance with ``blackboard.host.enabled`` also runs the host part: the store
and the HTTP API that members' instances connect to.

``initialize()`` runs in the Gateway and in the AgentServer; ``bind_web_channel``
only in the Gateway, which is where both parts live. ``shutdown()`` is not
called by either process today, so nothing here depends on it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from jiuwenswarm.extensions.sdk import (
    ApplicationPluginExtension,
    ApplicationPluginServices,
    FrontendContribution,
)
from jiuwenswarm.extensions.blackboard.client.rpc import register_rpcs
from jiuwenswarm.extensions.blackboard.client.runtime import ClientRuntime
from jiuwenswarm.extensions.blackboard.common.config import load_host_settings, save_host_settings
from jiuwenswarm.extensions.blackboard.common.logs import setup_file_logging
from jiuwenswarm.extensions.blackboard.common.paths import blackboard_dir, client_dir, host_dir
from jiuwenswarm.extensions.blackboard.host.controller import HostController

logger = logging.getLogger(__name__)


class BlackboardApplicationPlugin(ApplicationPluginExtension):
    plugin_id = "blackboard"

    def __init__(self) -> None:
        self.client: ClientRuntime | None = None
        self.host: HostController | None = None
        self._tasks: set[asyncio.Task] = set()

    async def initialize(self, config: Any) -> None:
        del config

    def is_enabled(self) -> bool:
        # Blackboard is part of every instance and has no off switch.
        return True

    async def shutdown(self) -> None:
        if self.host is not None:
            await self.host.stop()
        if self.client is not None:
            await self.client.stop()

    def _version(self) -> str:
        try:
            return self.metadata.version or "0.1.0"
        except (ValueError, FileNotFoundError):
            return "0.1.0"

    def bind_web_channel(self, channel: Any, services: ApplicationPluginServices) -> None:
        del services  # the agent client is used from milestone 4 on
        data_dir = blackboard_dir()
        setup_file_logging(data_dir)

        async def broadcast(event: str, payload: dict[str, Any]) -> None:
            try:
                await channel.broadcast_event(event, payload)
            except Exception:  # noqa: BLE001 - a push that fails must not break the caller
                logger.exception("blackboard: broadcast of %s failed", event)

        self.client = ClientRuntime(client_dir(data_dir) / "hosts.json", broadcast)
        self.host = HostController(
            host_dir(data_dir),
            version=self._version(),
            load_settings=load_host_settings,
            save_settings=save_host_settings,
            client=self.client,
            broadcast=broadcast,
        )
        register_rpcs(channel, self.client, self.host)
        self._spawn(self._start())

    async def _start(self) -> None:
        assert self.client is not None and self.host is not None
        await self.client.start()
        await self.host.start_if_enabled()

    def _spawn(self, coro: Any) -> None:
        task = asyncio.get_running_loop().create_task(coro, name="blackboard.start")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def frontend_contributions(self) -> tuple[FrontendContribution, ...]:
        return (
            FrontendContribution(
                id="blackboard",
                nav_key="app:blackboard",
                title="Blackboard",
                title_i18n_key="blackboard.nav",
                render_mode="bundled",
                component="blackboard",
                position=70,
                nav_after="chat",
            ),
        )


async def register_extensions(registry: Any) -> list[BlackboardApplicationPlugin]:
    extension = BlackboardApplicationPlugin()
    registry.register_application_plugin(extension)
    return [extension]
