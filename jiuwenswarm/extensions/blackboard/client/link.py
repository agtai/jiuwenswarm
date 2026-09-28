"""The connection from this jiuwenswarm to one host: RPC over HTTP, events over a WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import httpx
import websockets

from jiuwenswarm.extensions.blackboard.common.errors import (
    DISABLED,
    UNAUTHORIZED,
    UNAVAILABLE,
    BlackboardError,
)
from jiuwenswarm.extensions.blackboard.common.protocol import EVENTS_PATH, RPC_PATH

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_S = 15.0
RETRIES = 3
BACKOFF_MAX_S = 30.0
AUTH_FAILED_RETRY_S = 300.0

EventCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]
StatusCallback = Callable[[str, str], Awaitable[None]]
ReadyCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


def events_url(base_url: str) -> str:
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://"):] + EVENTS_PATH
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://"):] + EVENTS_PATH
    raise ValueError(f"not an http(s) url: {base_url}")


async def call_host(
    base_url: str,
    method: str,
    params: dict[str, Any],
    *,
    token: str | None = None,
    timeout: float = HTTP_TIMEOUT_S,
    retries: int = RETRIES,
) -> dict[str, Any]:
    """One RPC to a host. Retries only when the host cannot be reached."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = {"method": method, "params": params}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(base_url.rstrip("/") + RPC_PATH, json=body, headers=headers)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ReadError) as exc:
            last = exc
            await asyncio.sleep(0.5 * (2**attempt))
            continue
        except httpx.TimeoutException as exc:
            raise BlackboardError(UNAVAILABLE, f"the host did not answer in {timeout:.0f} s", {"url": base_url}) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise BlackboardError(
                UNAVAILABLE, f"the host answered with HTTP {response.status_code}", {"url": base_url}
            ) from exc
        if isinstance(data, dict) and data.get("ok") is True:
            payload = data.get("payload")
            return payload if isinstance(payload, dict) else {}
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            raise BlackboardError.from_dict(data["error"])
        raise BlackboardError(UNAVAILABLE, f"the host answered with HTTP {response.status_code}", {"url": base_url})
    raise BlackboardError(UNAVAILABLE, f"cannot reach the host at {base_url}", {"url": base_url, "error": str(last)})


class HostLink:
    """RPC calls and a live event stream for one known host.

    Status: ``connecting``, ``connected``, ``offline`` (retrying with backoff),
    ``unauthorized`` (the token was refused; retried rarely), ``stopped``.
    """

    def __init__(
        self,
        host_id: str,
        base_url: str,
        token: str,
        on_event: EventCallback,
        on_status: StatusCallback,
        on_ready: ReadyCallback | None = None,
    ) -> None:
        self.host_id = host_id
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._on_event = on_event
        self._on_status = on_status
        self._on_ready = on_ready
        self.status = "connecting"
        self._task: asyncio.Task | None = None

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return await call_host(self.base_url, method, params, token=self._token)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._events_loop(), name=f"blackboard.link.{self.host_id}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.status = "stopped"

    async def _set_status(self, status: str) -> None:
        if status != self.status:
            self.status = status
            try:
                await self._on_status(self.host_id, status)
            except Exception:  # noqa: BLE001
                logger.exception("blackboard: status callback failed")

    async def _events_loop(self) -> None:
        delay = 1.0
        while True:
            retry_after = delay
            try:
                await self._set_status("connecting")
                async with websockets.connect(
                    events_url(self.base_url), open_timeout=10, ping_interval=20, ping_timeout=20, max_size=2**22
                ) as ws:
                    await ws.send(json.dumps({"type": "auth", "token": self._token}))
                    first = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    if first.get("type") == "error":
                        code = first.get("code")
                        if code in (UNAUTHORIZED, DISABLED):
                            await self._set_status("unauthorized")
                            retry_after = AUTH_FAILED_RETRY_S
                            raise _AuthRefused(str(code))
                        raise ConnectionError(f"host refused the event stream: {code}")
                    if self._on_ready is not None and isinstance(first.get("host"), dict):
                        try:
                            await self._on_ready(self.host_id, first["host"])
                        except Exception:  # noqa: BLE001 - host details are a refresh, not a requirement
                            logger.exception("blackboard: ready callback failed")
                    await self._set_status("connected")
                    delay = 1.0
                    async for raw in ws:
                        frame = json.loads(raw)
                        if isinstance(frame, dict) and frame.get("type") == "event":
                            payload = frame.get("payload")
                            await self._on_event(
                                self.host_id, str(frame.get("event")), payload if isinstance(payload, dict) else {}
                            )
            except asyncio.CancelledError:
                raise
            except _AuthRefused:
                pass
            except Exception as exc:  # noqa: BLE001 - any failure means reconnect later
                logger.debug("blackboard: event stream to %s ended: %s", self.base_url, exc)
            if self.status != "unauthorized":
                await self._set_status("offline")
            await asyncio.sleep(retry_after)
            delay = min(delay * 2, BACKOFF_MAX_S)


class _AuthRefused(Exception):
    pass
