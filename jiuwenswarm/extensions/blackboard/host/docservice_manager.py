"""Runs the document service (Node, ``host/docservice``) for the host and talks to its internal API.

The service is started with ``subprocess.Popen`` and waited on in a thread rather than with asyncio
subprocesses, which need a Proactor event loop on Windows. It is stopped through
``POST /api/shutdown`` so pending saves are flushed (on Windows "terminate" is a hard kill), and it
exits by itself when this process dies (``BB_PARENT_PID``).
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import httpx

from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.common.errors import UNAVAILABLE, BlackboardError
from jiuwenswarm.extensions.blackboard.host.secrets import HostSecrets

logger = logging.getLogger(__name__)

MIN_NODE = (22, 5)  # node:sqlite; desktop builds bundle Node 22.11
SQLITE_WITHOUT_FLAG = (22, 13)
BUNDLE = Path(__file__).resolve().parent / "docservice" / "dist" / "server.mjs"
HEALTH_TIMEOUT_S = 20.0
STOP_TIMEOUT_S = 5.0
BACKOFF_MAX_S = 30.0


class NodeProblem(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def node_version(text: str) -> tuple[int, int] | None:
    match = re.match(r"v?(\d+)\.(\d+)", text.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def node_args(version: str, bundle: Path) -> list[str]:
    """Arguments for running the bundle with this Node version."""
    args = ["--disable-warning=ExperimentalWarning"]
    parsed = node_version(version)
    if parsed is not None and parsed < SQLITE_WITHOUT_FLAG:
        args.append("--experimental-sqlite")
    return [*args, str(bundle)]


def locate_node(configured: str = "") -> tuple[str, str]:
    """(path, version) of a Node that can run the service, or NodeProblem."""
    candidate = configured or shutil.which("node")
    if not candidate:
        raise NodeProblem("node_missing", "install Node.js 22.5 or later, or set blackboard.host.node_path")
    try:
        result = subprocess.run([candidate, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise NodeProblem("node_missing", f"cannot run {candidate}: {exc}") from exc
    version = (result.stdout or "").strip()
    parsed = node_version(version)
    if result.returncode != 0 or parsed is None:
        raise NodeProblem("node_missing", f"{candidate} did not report a version")
    if parsed < MIN_NODE:
        raise NodeProblem("node_too_old", f"Node {version} found; 22.5 or later is needed")
    return candidate, version


class DocServiceClient:
    """The service's internal HTTP API (127.0.0.1 only, X-BB-Secret)."""

    def __init__(self, port: int, secret: str, *, timeout: float = 60.0) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self._secret = secret
        self._timeout = timeout

    async def request(self, method: str, path: str, *, json: Any = None, params: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method, self.base + path, json=json, params=params, headers={"X-BB-Secret": self._secret}
                )
        except httpx.HTTPError as exc:
            raise BlackboardError(UNAVAILABLE, "the document service is not reachable", {"error": str(exc)}) from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code == 200:
            return body
        code = body.get("code") if isinstance(body, dict) else None
        raise BlackboardError(
            str(code or UNAVAILABLE),
            str(body.get("message") if isinstance(body, dict) else "") or f"document service answered {response.status_code}",
            body.get("details") if isinstance(body, dict) and isinstance(body.get("details"), dict) else {},
        )

    async def health(self) -> dict:
        return await self.request("GET", "/api/health")

    async def create(self, doc_id: str, author: dict, markdown: str | None = None) -> dict:
        return await self.request("POST", "/api/docs", json={"docId": doc_id, "markdown": markdown, "author": author})

    async def delete(self, doc_id: str) -> dict:
        return await self.request("DELETE", f"/api/docs/{doc_id}")

    async def markdown(self, doc_id: str, *, view: str = "accepted", range_: str | None = None) -> dict:
        params = {"view": view, **({"range": range_} if range_ else {})}
        return await self.request("GET", f"/api/docs/{doc_id}/markdown", params=params)

    async def import_markdown(self, doc_id: str, markdown: str, author: dict) -> dict:
        return await self.request("POST", f"/api/docs/{doc_id}/import", json={"markdown": markdown, "author": author})

    async def presence(self, doc_id: str) -> dict:
        return await self.request("GET", f"/api/docs/{doc_id}/presence")

    async def recheck(self, doc_id: str, user_id: str | None = None, *, role: str | None = None, revoke: bool = False) -> dict:
        body = {"userId": user_id, "role": role, "revoke": revoke}
        return await self.request("POST", f"/api/docs/{doc_id}/recheck", json=body)


class DocServiceManager:
    """Starts the service, restarts it with backoff when it exits, and stops it gracefully."""

    def __init__(
        self,
        *,
        data_dir: Path,
        get_settings: Callable[[], HostSettings],
        secrets: HostSecrets,
        version: str,
        bundle: Path | None = None,
        on_change: Callable[[], None] = lambda: None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._get_settings = get_settings
        self._secrets = secrets
        self._version = version
        self._bundle = Path(bundle) if bundle is not None else BUNDLE
        self._on_change = on_change
        self._process: subprocess.Popen | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._ready = asyncio.Event()
        self.state = "stopped"
        self.reason: str | None = None
        self.detail = ""
        self.restarts = 0
        self.client: DocServiceClient | None = None

    @property
    def running(self) -> bool:
        return self.state == "running"

    def status(self) -> dict[str, Any]:
        return {
            "status": self.state,
            "reason": self.reason,
            "detail": self.detail,
            "pid": self._process.pid if self._process and self._process.poll() is None else None,
            "restarts": self.restarts,
        }

    def require_client(self) -> DocServiceClient:
        if not self.running or self.client is None:
            raise BlackboardError(
                UNAVAILABLE,
                "the document service is not running on this host",
                {"reason": self.reason or self.state},
            )
        return self.client

    async def wait_ready(self, timeout: float) -> bool:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._ready.wait(), timeout)
        return self.running

    def _set(self, state: str, reason: str | None = None, detail: str = "") -> None:
        self.state, self.reason, self.detail = state, reason, detail
        if state == "running":
            self._ready.set()
        else:
            self._ready.clear()
        try:
            self._on_change()
        except Exception:  # noqa: BLE001
            logger.exception("blackboard: docservice status callback failed")

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        settings = self._get_settings()
        try:
            node, version = locate_node(settings.node_path)
        except NodeProblem as exc:
            self._set("unavailable", exc.reason, exc.detail)
            return
        if not self._bundle.exists():
            self._set(
                "unavailable",
                "not_built",
                f"{self._bundle} is missing; run npm install and npm run build in jiuwenswarm/channels/web/frontend",
            )
            return
        logger.info("blackboard: starting the document service with Node %s", version)
        self._stopping = False
        self.client = DocServiceClient(settings.doc_api_port, self._secrets.api_secret)
        command = [node, *node_args(version, self._bundle)]
        self._task = asyncio.get_running_loop().create_task(self._supervise(command), name="blackboard.docservice")
        atexit.register(self._stop_at_exit)

    def _spawn(self, command: list[str]) -> subprocess.Popen:
        settings = self._get_settings()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "BB_DOC_PORT": str(settings.doc_port),
            "BB_DOC_BIND": settings.bind,
            "BB_DOC_API_PORT": str(settings.doc_api_port),
            "BB_DOC_DB": str(self._data_dir / "docs.db"),
            "BB_DOC_SECRET": self._secrets.doc_secret,
            "BB_API_SECRET": self._secrets.api_secret,
            "BB_PARENT_PID": str(os.getpid()),
            "BB_VERSION": self._version,
        }
        log = open(self._data_dir / "docservice.log", "ab")  # noqa: SIM115 - handed to the child
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            return subprocess.Popen(
                command,
                cwd=self._data_dir,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
            )
        finally:
            log.close()

    async def _healthy(self, process: subprocess.Popen) -> bool:
        assert self.client is not None
        deadline = asyncio.get_running_loop().time() + HEALTH_TIMEOUT_S
        while asyncio.get_running_loop().time() < deadline:
            if process.poll() is not None:
                return False
            try:
                await self.client.health()
                return True
            except BlackboardError:
                await asyncio.sleep(0.2)
        return False

    async def _supervise(self, command: list[str]) -> None:
        delay = 1.0
        while not self._stopping:
            self._set("starting")
            process = self._spawn(command)
            self._process = process
            if await self._healthy(process):
                self._set("running")
                delay = 1.0
            else:
                self._set("restarting", "start_failed", "see docservice.log next to the host data")
                if process.poll() is None:
                    process.kill()
            code = await asyncio.to_thread(process.wait)
            if self._stopping:
                break
            logger.warning("blackboard: the document service exited with %s; restarting in %.0f s", code, delay)
            self.restarts += 1
            self._set("restarting", "exited", f"exit code {code}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, BACKOFF_MAX_S)
        self._set("stopped")

    async def stop(self) -> None:
        self._stopping = True
        process = self._process
        if process is not None and process.poll() is None:
            if self.client is not None:
                with contextlib.suppress(BlackboardError):
                    await self.client.request("POST", "/api/shutdown")
            try:
                await asyncio.wait_for(asyncio.to_thread(process.wait), STOP_TIMEOUT_S)
            except asyncio.TimeoutError:
                process.kill()
                await asyncio.to_thread(process.wait)
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self._process = None
        atexit.unregister(self._stop_at_exit)
        self._set("stopped")

    def _stop_at_exit(self) -> None:
        # The Gateway exits without stopping plugins; flush the documents on the way out.
        process = self._process
        if process is None or process.poll() is not None or self.client is None:
            return
        with contextlib.suppress(Exception):
            httpx.post(self.client.base + "/api/shutdown", headers={"X-BB-Secret": self._secrets.api_secret}, timeout=3)
            process.wait(timeout=STOP_TIMEOUT_S)
        if process.poll() is None:
            process.kill()
