"""Helpers shared by the Blackboard backend tests."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import httpx

from jiuwenswarm.extensions.blackboard.client.rpc import register_rpcs
from jiuwenswarm.extensions.blackboard.client.runtime import ClientRuntime
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings, validate_updates
from jiuwenswarm.extensions.blackboard.common.errors import BlackboardError
from jiuwenswarm.extensions.blackboard.common.tokens import hash_token, new_member_token
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.methods import METHODS, Call
from jiuwenswarm.extensions.blackboard.host.controller import HostController
from jiuwenswarm.extensions.blackboard.host.store import Store, invites, users, workspaces
from jiuwenswarm.extensions.blackboard.host.store.models import User


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def eventually(predicate: Callable[[], Any], timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


class RecordingHub:
    """Stands in for EventHub and records who each event is for."""

    connection_count = 0

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any], str | None, tuple[str, ...]]] = []

    async def publish(self, event, payload, *, workspace_id=None, user_ids=()):  # noqa: ANN001
        self.published.append((event, dict(payload), workspace_id, tuple(user_ids)))

    async def close_all(self) -> None:
        return None

    def events(self) -> list[str]:
        return [event for event, *_ in self.published]


class HostWorld:
    """A host store and the method table, called without HTTP."""

    def __init__(self, ctx: HostContext, hub: RecordingHub) -> None:
        self.ctx = ctx
        self.hub = hub
        self.store: Store = ctx.store

    async def user(self, name: str, *, operator: bool = False) -> tuple[User, str]:
        token = new_member_token()
        user = await self.store.transact(
            lambda c: users.create(c, display_name=name, token_hash=hash_token(token), is_operator=operator)
        )
        return user, token

    async def call(self, user: User | None, method: str, **params: Any) -> dict[str, Any]:
        return await METHODS[method](Call(ctx=self.ctx, user=user, params=params))

    async def fails(self, user: User | None, method: str, **params: Any) -> BlackboardError:
        try:
            await self.call(user, method, **params)
        except BlackboardError as exc:
            return exc
        raise AssertionError(f"{method} did not fail")

    async def workspace(self, owner: User, name: str = "launch-plan", title: str = "Launch plan") -> str:
        result = await self.call(owner, p.WORKSPACE_CREATE, name=name, title=title)
        return result["workspace"]["id"]

    async def add(self, workspace_id: str, user: User, role: str) -> None:
        await self.store.transact(lambda c: workspaces.add_member(c, workspace_id, user.id, role))

    async def invite(self, owner: User, workspace_id: str, role: str = "editor", **params: Any) -> str:
        result = await self.call(owner, p.INVITE_CREATE, workspace_id=workspace_id, role=role, **params)
        return result["invite"]["code"]

    async def sql(self, statement: str, *args: Any) -> None:
        await self.store.transact(lambda c: c.execute(statement, args))

    async def invite_row(self, code: str):
        return await self.store.read(lambda c: invites.get(c, code))


async def rpc(base: str, method: str, params: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base}{p.RPC_PATH}", json={"method": method, "params": params or {}}, headers=headers)
    return response.status_code, response.json()


class FakeChannel:
    """The parts of the web channel the plugin uses."""

    def __init__(self) -> None:
        self.methods: dict[str, Any] = {}
        self.local_only: set[str] = set()
        self.events: list[tuple[str, dict[str, Any]]] = []

    def register_method(self, name, handler, *, local_only=False) -> None:  # noqa: ANN001
        self.methods[name] = handler
        if local_only:
            self.local_only.add(name)

    async def send_response(self, ws, req_id, *, ok, payload=None, error=None, code=None) -> None:  # noqa: ANN001
        ws.append({"id": req_id, "ok": ok, "payload": payload, "error": error, "code": code})

    async def broadcast_event(self, event: str, payload: dict[str, Any]) -> None:
        self.events.append((event, payload))

    async def call(self, name: str, params: dict | None = None) -> dict[str, Any]:
        replies: list[dict[str, Any]] = []
        await self.methods[name](replies, "req-1", params or {}, None)
        return replies[0]

    async def ok(self, name: str, params: dict | None = None) -> dict[str, Any]:
        reply = await self.call(name, params)
        assert reply["ok"], reply
        return reply["payload"]

    def named(self, event: str) -> list[dict[str, Any]]:
        return [payload for name, payload in self.events if name == event]


class Instance:
    """One jiuwenswarm's Blackboard parts (client and host) behind a fake web channel."""

    def __init__(self, root: Path, settings: HostSettings) -> None:
        self.channel = FakeChannel()
        self.settings = settings
        self.client = ClientRuntime(root / "client" / "hosts.json", self.channel.broadcast_event)
        self.host = HostController(
            root / "host", "0.1.0", lambda: self.settings, self._save, self.client, self.channel.broadcast_event
        )
        register_rpcs(self.channel, self.client, self.host)

    def _save(self, updates: dict[str, Any]) -> HostSettings:
        self.settings = replace(self.settings, **validate_updates(updates))
        return self.settings

    async def start(self) -> None:
        await self.client.start()
        await self.host.start_if_enabled()

    async def stop(self) -> None:
        await self.host.stop()
        await self.client.stop()
