"""Server push to members' instances over one WebSocket each.

A connection authenticates with its first frame (``{type: 'auth', token}``), so
the member token never appears in a URL or an access log. An event scoped to a
workspace goes only to that workspace's members.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable

from fastapi import WebSocket, WebSocketDisconnect

from jiuwenswarm.extensions.blackboard.common.errors import BlackboardError

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_S = 10.0
QUEUE_LIMIT = 1000


@dataclass
class _Connection:
    user_id: str
    queue: asyncio.Queue
    websocket: WebSocket


class EventHub:
    def __init__(self, member_ids: Callable[[str], Awaitable[list[str]]]) -> None:
        self._member_ids = member_ids
        self._connections: dict[int, _Connection] = {}
        self._background: set[asyncio.Task] = set()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def publish(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        workspace_id: str | None = None,
        user_ids: Iterable[str] = (),
    ) -> None:
        targets = set(user_ids)
        if workspace_id is not None:
            targets.update(await self._member_ids(workspace_id))
        if not targets:
            return
        connections = [(k, c) for k, c in list(self._connections.items()) if c.user_id in targets]
        self._deliver({"type": "event", "event": event, "payload": payload}, connections)

    async def publish_all(self, event: str, payload: dict[str, Any]) -> None:
        """Send an event to every connected member, for changes to the host itself."""
        self._deliver({"type": "event", "event": event, "payload": payload}, list(self._connections.items()))

    def _deliver(self, frame: dict[str, Any], connections: list[tuple[int, _Connection]]) -> None:
        for key, connection in connections:
            try:
                connection.queue.put_nowait(frame)
            except asyncio.QueueFull:
                # A client this far behind reconnects and fetches state again.
                logger.warning("blackboard: closing a slow event connection for %s", connection.user_id)
                self._connections.pop(key, None)
                task = asyncio.create_task(_close(connection.websocket, 4408, "too slow"))
                self._background.add(task)
                task.add_done_callback(self._background.discard)

    async def serve(
        self,
        websocket: WebSocket,
        authenticate: Callable[[str | None], Awaitable[Any]],
        hello: Callable[[], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        await websocket.accept()
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_S)
        except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
            await _close(websocket, 4401, "authenticate first")
            return
        token = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
        try:
            user = await authenticate(token)
        except BlackboardError as exc:
            await _send(websocket, {"type": "error", **exc.to_dict()})
            await _close(websocket, 4401, exc.code)
            return

        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_LIMIT)
        key = id(websocket)
        self._connections[key] = _Connection(user_id=user.id, queue=queue, websocket=websocket)
        ready: dict[str, Any] = {"type": "ready", "user_id": user.id}
        if hello is not None:
            # Current host details, so a member who was offline sees a rename.
            ready["host"] = await hello()
        await _send(websocket, ready)
        sender = asyncio.create_task(self._send_loop(websocket, queue), name="blackboard.events.send")
        try:
            while True:
                message = await websocket.receive_json()
                if isinstance(message, dict) and message.get("type") == "ping":
                    queue.put_nowait({"type": "pong"})
        except (WebSocketDisconnect, ValueError, RuntimeError):
            pass
        finally:
            self._connections.pop(key, None)
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)

    async def _send_loop(self, websocket: WebSocket, queue: asyncio.Queue) -> None:
        while True:
            frame = await queue.get()
            await websocket.send_json(frame)

    async def close_all(self) -> None:
        connections = list(self._connections.values())
        self._connections.clear()
        await asyncio.gather(*(_close(c.websocket, 1001, "host stopping") for c in connections), return_exceptions=True)


async def _send(websocket: WebSocket, frame: dict[str, Any]) -> None:
    try:
        await websocket.send_json(frame)
    except (RuntimeError, WebSocketDisconnect):
        pass


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        pass
