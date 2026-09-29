"""Starts and stops the host: store, secrets, operator user, the HTTP server and the document service."""

from __future__ import annotations

import asyncio
import contextlib
import getpass
import logging
import socket
from pathlib import Path
from typing import Any, Callable

import uvicorn

from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.common.tokens import hash_token, new_member_token
from jiuwenswarm.extensions.blackboard.host.api.app import build_app
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.events import EventHub
from jiuwenswarm.extensions.blackboard.host.docservice_manager import DocServiceManager
from jiuwenswarm.extensions.blackboard.host.secrets import load_or_create
from jiuwenswarm.extensions.blackboard.host.store import Store, meta, users, workspaces
from jiuwenswarm.extensions.blackboard.host.store.models import User

logger = logging.getLogger(__name__)

STARTUP_TIMEOUT_S = 10.0
SWEEP_INTERVAL_S = 30.0


class _Server(uvicorn.Server):
    """uvicorn without signal capture: the Gateway owns Ctrl+C, the plugin stops this server."""

    @contextlib.contextmanager
    def capture_signals(self):  # type: ignore[override]
        yield


class HostStartError(RuntimeError):
    pass


def _bind(host: str, port: int) -> socket.socket:
    family, kind, proto, _, address = socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )[0]
    sock = socket.socket(family, kind, proto)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            # Windows: no other socket may bind this port while the host has it.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(address)
        sock.listen(128)
        sock.setblocking(False)
    except OSError:
        sock.close()
        raise
    return sock


class HostRuntime:
    """One running host. Create a new one to apply changed bind or port settings."""

    def __init__(
        self,
        get_settings: Callable[[], HostSettings],
        data_dir: Path,
        version: str,
        on_docs_change: Callable[[], None] = lambda: None,
    ) -> None:
        self._get_settings = get_settings
        self._on_docs_change = on_docs_change
        self._data_dir = Path(data_dir)
        self._version = version
        self.store: Store | None = None
        self.ctx: HostContext | None = None
        self.listening: tuple[str, int] | None = None
        self._server: _Server | None = None
        self._task: asyncio.Task | None = None
        self.docs: DocServiceManager | None = None
        self._sweeper: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> HostContext:
        settings = self._get_settings()
        store = Store(self._data_dir / "blackboard.db")
        try:
            await store.open()
            host_uid = await store.transact(meta.ensure_host_uid)
            secrets = load_or_create(self._data_dir / "secrets.json")

            async def member_ids(workspace_id: str) -> list[str]:
                return await store.read(lambda c: workspaces.member_user_ids(c, workspace_id))

            ctx = HostContext(
                store=store,
                hub=EventHub(member_ids),
                secrets=secrets,
                host_uid=host_uid,
                version=self._version,
                get_settings=self._get_settings,
                docs=DocServiceManager(
                    data_dir=self._data_dir,
                    get_settings=self._get_settings,
                    secrets=secrets,
                    version=self._version,
                    on_change=self._on_docs_change,
                ),
                files_dir=self._data_dir / "references",
                exports_dir=self._data_dir / "exports",
            )
            try:
                sock = _bind(settings.bind, settings.port)
            except OSError as exc:
                raise HostStartError(f"cannot listen on {settings.bind}:{settings.port}: {exc.strerror or exc}") from exc
            config = uvicorn.Config(
                build_app(ctx),
                log_level="warning",
                access_log=False,
                lifespan="off",
                ws_ping_interval=20.0,
                ws_ping_timeout=60.0,
            )
            server = _Server(config)
            task = asyncio.create_task(self._serve(server, sock), name="blackboard.host.server")
            deadline = asyncio.get_running_loop().time() + STARTUP_TIMEOUT_S
            while not server.started:
                if task.done():
                    task.result()
                    raise HostStartError("the host server stopped during startup")
                if asyncio.get_running_loop().time() > deadline:
                    server.should_exit = True
                    raise HostStartError("the host server did not start in time")
                await asyncio.sleep(0.02)
        except BaseException:
            await store.close()
            raise
        self.store, self.ctx, self._server, self._task = store, ctx, server, task
        self.docs = ctx.docs
        self.listening = sock.getsockname()[:2]
        logger.info("blackboard: host listening on %s:%s (members use %s)", *self.listening, settings.base_url())
        # The host serves members without the document service too; documents wait for it.
        assert self.docs is not None
        self.docs.start()
        from jiuwenswarm.extensions.blackboard.host.api.history import prune_exports

        prune_exports(ctx.exports_dir)
        self._sweeper = asyncio.create_task(self._sweep(ctx), name="blackboard.host.sweeper")
        return ctx

    @staticmethod
    async def _sweep(ctx: HostContext) -> None:
        """End workspace-session mandates that have gone quiet, and dispatched turns that nobody picked
        up or that never reported."""
        from jiuwenswarm.extensions.blackboard.host.api.dispatch import sweep_dispatched
        from jiuwenswarm.extensions.blackboard.host.api.mandates import sweep_idle_mandates

        while True:
            await asyncio.sleep(SWEEP_INTERVAL_S)
            try:
                await sweep_idle_mandates(ctx)
                await sweep_dispatched(ctx)
            except Exception:  # noqa: BLE001 - the next round tries again
                logger.exception("blackboard: sweeping mandates failed")

    async def restart_docs(self) -> None:
        if self.docs is not None:
            await self.docs.stop()
            self.docs.start()

    @staticmethod
    async def _serve(server: _Server, sock: socket.socket) -> None:
        try:
            await server.serve(sockets=[sock])
        except SystemExit as exc:
            # uvicorn exits the process on some startup errors; keep that inside this task.
            raise HostStartError(f"the host server exited ({exc.code})") from None
        finally:
            sock.close()

    async def stop(self) -> None:
        if self._sweeper is not None:
            self._sweeper.cancel()
            self._sweeper = None
        if self.docs is not None:
            await self.docs.stop()
        if self.ctx is not None:
            await self.ctx.hub.close_all()
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, timeout=5.0)
        if self.store is not None:
            await self.store.close()
        self.store = self.ctx = self._server = self._task = self.docs = None
        self.listening = None

    async def operator(self, display_name: str) -> User:
        """The host's own user (the person running it), created on first start."""
        assert self.store is not None

        def work(conn) -> User:
            existing = users.operator(conn)
            if existing is not None:
                return existing
            return users.create(
                conn, display_name=display_name, token_hash=hash_token(new_member_token()), is_operator=True
            )

        return await self.store.transact(work)

    async def operator_token_matches(self, user_id: str, token: str) -> bool:
        assert self.store is not None
        stored = await self.store.read(lambda c: users.token_hash_of(c, user_id))
        return stored == hash_token(token)

    async def rotate_token(self, user_id: str) -> str:
        """Give a user a new member token; the old one stops working at once."""
        assert self.store is not None
        token = new_member_token()
        await self.store.transact(lambda c: users.set_token_hash(c, user_id, hash_token(token)))
        return token

    def status(self) -> dict[str, Any]:
        settings = self._get_settings()
        return {
            "running": self.running,
            "listening": f"{self.listening[0]}:{self.listening[1]}" if self.listening else None,
            "base_url": settings.base_url(),
            "host_uid": self.ctx.host_uid if self.ctx else None,
            "connections": self.ctx.hub.connection_count if self.ctx else 0,
            "docservice": self.ctx.docservice_status() if self.ctx else {"status": "stopped", "reason": None},
        }


def default_operator_name(settings: HostSettings) -> str:
    if settings.operator_name:
        return settings.operator_name
    try:
        return getpass.getuser() or "Host operator"
    except Exception:  # noqa: BLE001
        return "Host operator"
