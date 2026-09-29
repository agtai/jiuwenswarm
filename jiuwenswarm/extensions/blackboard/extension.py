"""Blackboard as an application plugin.

The same plugin runs in two roles. Every jiuwenswarm runs the client part: it
keeps a link to each host this person joined and proxies the browser's calls.
An instance with ``blackboard.host.enabled`` also runs the host part: the store
and the HTTP API that members' instances connect to.

``initialize()`` runs in the Gateway and in the AgentServer; ``bind_web_channel``
only in the Gateway, which is where both parts live. ``agent_tools`` runs in the
AgentServer: a session attached to a workspace gets that workspace's tools.
``shutdown()`` is not called by either process today, so nothing here depends on it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from jiuwenswarm.extensions.sdk import (
    AgentToolContext,
    ApplicationPluginExtension,
    ApplicationPluginServices,
    FrontendContribution,
)
from jiuwenswarm.extensions.blackboard.client.hosts import HostRegistry
from jiuwenswarm.extensions.blackboard.client.sessions import SessionAttachments
from jiuwenswarm.extensions.blackboard.client.toolkit.bridge import to_openjiuwen
from jiuwenswarm.extensions.blackboard.client.toolkit.tools import SessionTools, WorkspaceRef
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
        # AgentServer side: per session, the toolkit and the tools handed to its agent.
        self._toolsets: dict[str, tuple[SessionTools, list[Any]]] = {}
        self._client_files: tuple[SessionAttachments, HostRegistry] | None = None

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

    def agent_tools(self, ctx: AgentToolContext) -> list[Any]:
        if not ctx.session_id:
            return []
        if self._client_files is None:
            base = client_dir(blackboard_dir())
            self._client_files = (SessionAttachments(base / "sessions.json"), HostRegistry(base / "hosts.json"))
        attachments, registry = self._client_files
        workspaces = [WorkspaceRef(a.host, a.workspace_id, a.title) for a in attachments.for_session(ctx.session_id)]
        if not workspaces:
            self._toolsets.pop(ctx.session_id, None)
            return []
        current = self._toolsets.get(ctx.session_id)
        if current is None or current[0].workspaces != workspaces:
            toolkit = SessionTools(registry=registry, session_id=ctx.session_id, workspaces=workspaces)
            current = (toolkit, to_openjiuwen(toolkit.specs(), owner=ctx.session_id))
            self._toolsets[ctx.session_id] = current
        # Edits of one turn share a mandate; the next turn begins another.
        current[0].turn_id = ctx.request_id or ""
        return current[1]

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
