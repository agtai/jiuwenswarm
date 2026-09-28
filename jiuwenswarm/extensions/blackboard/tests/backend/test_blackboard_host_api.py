"""The host's HTTP API and event stream, on a real server."""

from __future__ import annotations

import asyncio
import json
import socket

import httpx
import pytest
import websockets

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.host.api import methods
from jiuwenswarm.extensions.blackboard.host.runtime import HostRuntime, HostStartError
from jiuwenswarm.extensions.blackboard.host.store import users
from jiuwenswarm.extensions.blackboard.tests.backend.support import eventually, free_port, rpc


async def _alice(host) -> tuple[str, str]:
    operator = await host.operator("Alice")
    return operator.id, await host.rotate_token(operator.id)


async def _join(host, owner_token: str, workspace_id: str, name: str, role: str = "editor") -> tuple[str, str]:
    _, created = await rpc(host.base, p.INVITE_CREATE, {"workspace_id": workspace_id, "role": role}, owner_token)
    _, accepted = await rpc(host.base, p.INVITE_ACCEPT, {"code": created["payload"]["invite"]["code"], "display_name": name})
    return accepted["payload"]["user_id"], accepted["payload"]["token"]


class Listener:
    """One member's event stream."""

    def __init__(self, ws) -> None:  # noqa: ANN001
        self.ws = ws
        self.frames: list[dict] = []
        self._task = asyncio.create_task(self._read())

    @classmethod
    async def connect(cls, host, token: str) -> "Listener":
        ws = await websockets.connect(host.base.replace("http://", "ws://") + p.EVENTS_PATH)
        await ws.send(json.dumps({"type": "auth", "token": token}))
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready"
        return cls(ws)

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                self.frames.append(json.loads(raw))
        except websockets.ConnectionClosed:
            pass

    def events(self) -> list[tuple[str, dict]]:
        return [(f["event"], f["payload"]) for f in self.frames if f.get("type") == "event"]

    async def close(self) -> None:
        await self.ws.close()
        await self._task


async def test_health(host):
    async with httpx.AsyncClient() as client:
        body = (await client.get(host.base + p.HEALTH_PATH)).json()
    assert body["ok"] is True and body["version"] == "0.1.0" and body["host_uid"] == host.ctx.host_uid
    # The fixture runs without a built document service.
    assert body["docservice"]["status"] == "unavailable" and body["docservice"]["reason"] == "not_built"


async def test_rpc_needs_a_member_token(host):
    status, body = await rpc(host.base, p.ME)
    assert status == 401 and body["error"]["code"] == "unauthorized"
    status, body = await rpc(host.base, p.ME, token="bbm_not-a-token")
    assert status == 401 and body["error"]["code"] == "unauthorized"

    _, token = await _alice(host)
    status, body = await rpc(host.base, p.ME, token=token)
    assert status == 200 and body["ok"] is True and body["payload"]["display_name"] == "Alice"
    assert body["payload"]["is_operator"] is True


async def test_a_disabled_user_gets_403(host):
    user_id, token = await _alice(host)
    await host.store.transact(lambda c: users.set_status(c, user_id, "disabled"))
    status, body = await rpc(host.base, p.ME, token=token)
    assert status == 403 and body["error"]["code"] == "disabled"


async def test_malformed_requests(host):
    async with httpx.AsyncClient() as client:
        url = host.base + p.RPC_PATH
        response = await client.post(url, content=b"not json", headers={"content-type": "application/json"})
        assert response.status_code == 400 and response.json()["error"]["code"] == "invalid"
        response = await client.post(url, json=["blackboard.me"])
        assert response.status_code == 400
        response = await client.post(url, json={"method": p.ME, "params": [1, 2]})
        assert response.status_code == 400
    status, body = await rpc(host.base, "blackboard.nope")
    assert status == 200 and body["error"] == {
        "code": "invalid",
        "message": "unknown method: blackboard.nope",
        "details": {"method": "blackboard.nope"},
    }


async def test_an_unexpected_failure_is_reported_as_internal(host, monkeypatch):
    async def broken(call):  # noqa: ANN001
        raise RuntimeError("secret detail")

    monkeypatch.setitem(methods.METHODS, p.ME, broken)
    _, token = await _alice(host)
    status, body = await rpc(host.base, p.ME, token=token)
    assert status == 200 and body["error"]["code"] == "internal"
    assert "secret detail" not in json.dumps(body)


async def test_joining_over_http(host):
    _, alice = await _alice(host)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch-plan", "title": "Launch plan"}, alice)
    workspace_id = created["payload"]["workspace"]["id"]
    bob_id, bob = await _join(host, alice, workspace_id, "Bob")

    _, members = await rpc(host.base, p.MEMBER_LIST, {"workspace_id": workspace_id}, bob)
    assert [(m["display_name"], m["role"]) for m in members["payload"]["members"]] == [("Alice", "owner"), ("Bob", "editor")]
    _, refused = await rpc(host.base, p.INVITE_CREATE, {"workspace_id": workspace_id, "role": "viewer"}, bob)
    assert refused["error"]["code"] == "forbidden"
    assert bob_id.startswith("u_")


async def test_the_join_page_explains_the_link(host):
    _, alice = await _alice(host)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "team", "title": "Team <b>plans</b>"}, alice)
    workspace_id = created["payload"]["workspace"]["id"]
    _, invite = await rpc(host.base, p.INVITE_CREATE, {"workspace_id": workspace_id, "role": "viewer"}, alice)
    code = invite["payload"]["invite"]["code"]

    async with httpx.AsyncClient() as client:
        page = (await client.get(f"{host.base}{p.JOIN_PATH}{code}")).text
        assert "You are invited to Team &lt;b&gt;plans&lt;/b&gt;" in page and "join as viewer" in page
        assert f"{host.base}/blackboard/join/{code}" in page
        await rpc(host.base, p.INVITE_REVOKE, {"workspace_id": workspace_id, "code": code}, alice)
        assert "It is revoked." in (await client.get(f"{host.base}{p.JOIN_PATH}{code}")).text
        assert "not valid" in (await client.get(f"{host.base}{p.JOIN_PATH}{'a' * 20}")).text


async def test_the_event_stream_needs_an_auth_frame_first(host):
    url = host.base.replace("http://", "ws://") + p.EVENTS_PATH
    for first in ({"type": "hello"}, {"type": "auth", "token": "bbm_wrong"}):
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps(first))
            frame = json.loads(await ws.recv())
            assert frame["type"] == "error" and frame["code"] == "unauthorized"
            with pytest.raises(websockets.ConnectionClosed) as closed:
                await ws.recv()
            assert closed.value.rcvd.code == 4401


async def test_the_ready_frame_carries_the_host_name(host):
    _, token = await _alice(host)
    async with websockets.connect(host.base.replace("http://", "ws://") + p.EVENTS_PATH) as ws:
        await ws.send(json.dumps({"type": "auth", "token": token}))
        ready = json.loads(await ws.recv())
    assert ready["type"] == "ready"
    assert ready["host"]["name"] == "Alice's Blackboard"
    assert ready["host"]["host_uid"] == host.ctx.host_uid


async def test_events_reach_only_the_members_concerned(host):
    _, alice = await _alice(host)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch-plan", "title": "Launch plan"}, alice)
    workspace_id = created["payload"]["workspace"]["id"]
    bob_id, bob = await _join(host, alice, workspace_id, "Bob")
    _, carol = await _join(host, alice, workspace_id, "Carol")
    # Dave is a user of this host with a workspace of his own, but not a member of launch-plan.
    dave_id, dave = await _join(host, alice, workspace_id, "Dave")
    _, own = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "daves", "title": "Dave's"}, dave)
    dave_workspace = own["payload"]["workspace"]["id"]
    _, left = await rpc(host.base, p.MEMBER_REMOVE, {"workspace_id": workspace_id, "user_id": dave_id}, dave)
    assert left["ok"]

    tokens = {"alice": alice, "bob": bob, "carol": carol, "dave": dave}
    listeners = {name: await Listener.connect(host, token) for name, token in tokens.items()}
    assert host.status()["connections"] == 4

    await rpc(host.base, p.MEMBER_SET_ROLE, {"workspace_id": workspace_id, "user_id": bob_id, "role": "viewer"}, alice)
    # Each stream is in order, so once Dave's own event is in, any stray event for him would be too.
    await rpc(host.base, p.WORKSPACE_RENAME, {"workspace_id": dave_workspace, "title": "Dave's notes"}, dave)

    await eventually(
        lambda: listeners["dave"].events()
        and listeners["alice"].events()
        and listeners["carol"].events()
        and len(listeners["bob"].events()) == 3
    )
    updated = (p.EV_MEMBER_UPDATED, {"workspace_id": workspace_id})
    assert listeners["dave"].events() == [(p.EV_WORKSPACE_UPDATED, {"workspace_id": dave_workspace})]
    assert listeners["alice"].events() == [updated]
    assert listeners["carol"].events() == [updated]
    assert listeners["bob"].events() == [
        updated,
        (p.EV_MEMBER_ROLE_CHANGED, {"workspace_id": workspace_id, "user_id": bob_id, "role": "viewer"}),
        (p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id}),
    ]

    await listeners["carol"].ws.send(json.dumps({"type": "ping"}))
    await eventually(lambda: any(f.get("type") == "pong" for f in listeners["carol"].frames))

    for listener in listeners.values():
        await listener.close()
    await eventually(lambda: host.status()["connections"] == 0)


async def test_stopping_the_host_closes_event_streams(tmp_path):
    settings = HostSettings(enabled=True, port=free_port())
    runtime = HostRuntime(lambda: settings, tmp_path, "0.1.0")
    await runtime.start()
    runtime.base = settings.base_url()  # type: ignore[attr-defined]
    _, token = await _alice(runtime)
    listener = await Listener.connect(runtime, token)
    await runtime.stop()
    await asyncio.wait_for(listener._task, timeout=5)
    assert listener.ws.close_code == 1001
    assert runtime.status()["running"] is False


async def test_a_restarted_host_keeps_its_data(tmp_path):
    settings = HostSettings(enabled=True, port=free_port())
    first = HostRuntime(lambda: settings, tmp_path, "0.1.0")
    ctx = await first.start()
    uid = ctx.host_uid
    operator = await first.operator("Alice")
    token = await first.rotate_token(operator.id)
    await rpc(settings.base_url(), p.WORKSPACE_CREATE, {"name": "kept", "title": "Kept"}, token)
    await first.stop()

    second = HostRuntime(lambda: settings, tmp_path, "0.1.0")
    await second.start()
    try:
        assert second.ctx.host_uid == uid
        assert (await second.operator("Someone else")).id == operator.id
        assert await second.operator_token_matches(operator.id, token)
        _, body = await rpc(settings.base_url(), p.WORKSPACE_LIST, token=token)
        assert [w["name"] for w in body["payload"]["workspaces"]] == ["kept"]
    finally:
        await second.stop()


async def test_a_busy_port_is_reported_and_leaves_nothing_open(tmp_path):
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        settings = HostSettings(enabled=True, port=port)
        runtime = HostRuntime(lambda: settings, tmp_path, "0.1.0")
        with pytest.raises(HostStartError, match=f"127.0.0.1:{port}"):
            await runtime.start()
    assert runtime.running is False and runtime.store is None
