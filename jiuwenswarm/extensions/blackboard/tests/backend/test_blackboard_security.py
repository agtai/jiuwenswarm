"""Milestone 8 hardening: replacing a token, disabling a person, which pages may open the events
socket, edit and upload limits, tokens kept out of the log, ids instead of paths, and settings from
the environment."""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
import websockets

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings, env_overrides, host_settings_from, validate_updates
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, DISABLED, FORBIDDEN, RATE_LIMITED, BlackboardError
from jiuwenswarm.extensions.blackboard.common.logs import RedactingFormatter, redact
from jiuwenswarm.extensions.blackboard.common.origins import origin_allowed
from jiuwenswarm.extensions.blackboard.common.tokens import mint_doc_token, new_member_token, verify_doc_token
from jiuwenswarm.extensions.blackboard.host.api.ratelimit import EDITS_PER_MINUTE, UPLOADS_PER_MINUTE
from jiuwenswarm.extensions.blackboard.host.runtime import HostRuntime
from jiuwenswarm.extensions.blackboard.tests.backend.support import Instance, free_port, rpc
from jiuwenswarm.extensions.blackboard.tests.backend.test_blackboard_host_api import Listener


async def _team(host):
    """Alice runs the host; Bob is an editor of her workspace."""
    alice = await host.operator("Alice")
    token = await host.rotate_token(alice.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"}, token)
    workspace_id = created["payload"]["workspace"]["id"]
    _, invite = await rpc(host.base, p.INVITE_CREATE, {"workspace_id": workspace_id, "role": "editor"}, token)
    _, joined = await rpc(host.base, p.INVITE_ACCEPT, {"code": invite["payload"]["invite"]["code"], "display_name": "Bob"})
    return token, workspace_id, joined["payload"]["token"], joined["payload"]["user_id"]


async def _closed(listener: Listener) -> int | None:
    await asyncio.wait_for(listener._task, timeout=5)
    return listener.ws.close_code


async def test_replacing_a_token_ends_the_old_one_and_its_connections(host):
    _, _, bob, _ = await _team(host)
    listener = await Listener.connect(host, bob)
    _, rotated = await rpc(host.base, p.ME_ROTATE_TOKEN, {}, bob)
    fresh = rotated["payload"]["token"]
    assert fresh.startswith("bbm_") and fresh != bob
    assert await _closed(listener) == 4401
    assert (await rpc(host.base, p.ME, {}, bob))[0] == 401
    assert (await rpc(host.base, p.ME, {}, fresh))[0] == 200


async def test_the_operator_disables_and_enables_a_person(host):
    alice, workspace_id, bob, bob_id = await _team(host)
    _, listed = await rpc(host.base, p.USER_LIST, {}, alice)
    people = {u["display_name"]: u for u in listed["payload"]["users"]}
    assert people["Alice"]["is_operator"] and people["Bob"]["workspaces"] == 1
    _, refused = await rpc(host.base, p.USER_LIST, {}, bob)
    assert refused["error"]["code"] == FORBIDDEN
    _, itself = await rpc(host.base, p.USER_SET_STATUS, {"user_id": people["Alice"]["id"], "status": "disabled"}, alice)
    assert itself["error"]["code"] == CONFLICT

    listener = await Listener.connect(host, bob)
    _, done = await rpc(host.base, p.USER_SET_STATUS, {"user_id": bob_id, "status": "disabled"}, alice)
    assert done["payload"]["user"]["disabled"] is True
    assert await _closed(listener) == 4401
    _, blocked = await rpc(host.base, p.WORKSPACE_LIST, {}, bob)
    assert blocked["error"]["code"] == DISABLED
    _, members = await rpc(host.base, p.MEMBER_LIST, {"workspace_id": workspace_id}, alice)
    assert [m["disabled"] for m in members["payload"]["members"] if m["user_id"] == bob_id] == [True]

    await rpc(host.base, p.USER_SET_STATUS, {"user_id": bob_id, "status": "active"}, alice)
    _, back = await rpc(host.base, p.WORKSPACE_LIST, {}, bob)
    assert [w["id"] for w in back["payload"]["workspaces"]] == [workspace_id]


async def test_disabling_closes_the_person_s_open_documents(world):
    alice, _ = await world.user("Alice", operator=True)
    bob, _ = await world.user("Bob")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, bob, "editor")
    doc_id = await world.doc(alice, workspace_id)
    await world.call(alice, p.USER_SET_STATUS, user_id=bob.id, status="disabled")
    assert ("recheck", doc_id, {"user_id": bob.id, "role": None, "revoke": True}) in world.ctx.docs.calls
    assert world.hub.closed_users == [bob.id]


async def test_web_pages_need_an_allowed_origin(tmp_path):
    settings = HostSettings(
        enabled=True, port=free_port(), doc_port=free_port(), doc_api_port=free_port(), allowed_origins=("https://team.example.com",)
    )
    runtime = HostRuntime(lambda: settings, tmp_path / "host", "0.1.0")
    await runtime.start()
    try:
        alice = await runtime.operator("Alice")
        token = await runtime.rotate_token(alice.id)
        url = settings.base_url().replace("http://", "ws://") + p.EVENTS_PATH
        for origin in (None, "http://127.0.0.1:5173", "https://team.example.com"):
            async with websockets.connect(url, origin=origin) as ws:
                await ws.send('{"type": "auth", "token": "%s"}' % token)
                assert '"ready"' in await ws.recv()
        with pytest.raises(websockets.InvalidStatus):
            async with websockets.connect(url, origin="https://evil.example"):
                pass
    finally:
        await runtime.stop()
    assert not origin_allowed("https://evil.example", (), False)
    assert origin_allowed("https://evil.example", (), True)


async def test_edit_batches_per_run_are_limited(world):
    alice, _ = await world.user("Alice")
    workspace_id = await world.workspace(alice)
    doc_id = await world.doc(alice, workspace_id)
    ops = [{"op": "replace", "block_id": "b1", "digest": "d0", "markdown": "New text."}]
    for _ in range(EDITS_PER_MINUTE):
        await world.call(alice, p.EDIT, doc_id=doc_id, ops=ops, session_id="s1", turn_id="t1")
    refused = await world.fails(alice, p.EDIT, doc_id=doc_id, ops=ops, session_id="s1", turn_id="t1")
    assert refused.code == RATE_LIMITED


async def test_uploads_per_person_are_limited_and_stored_by_id(host):
    alice, workspace_id, _, _ = await _team(host)

    async def upload(name: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{host.base}{p.FILES_PATH}{workspace_id}",
                headers={"Authorization": f"Bearer {alice}"},
                files={"file": (name, b"hello", "text/plain")},
            )
        return response.json()

    first = await upload("../../../evil.txt")
    stored = list((host.ctx.files_dir).rglob("*"))
    assert all(path.is_relative_to(host.ctx.files_dir / workspace_id) or path == host.ctx.files_dir / workspace_id for path in stored)
    assert [path.name for path in stored if path.is_file()] == [f"{first['payload']['reference']['id']}.txt"]
    for n in range(UPLOADS_PER_MINUTE - 1):
        assert "payload" in await upload(f"brief-{n}.txt")
    assert (await upload("one-more.txt"))["error"]["code"] == RATE_LIMITED

    async with httpx.AsyncClient() as client:
        for path in (f"{p.FILES_PATH}{workspace_id}/..%2F..%2Fsecrets.json", f"{p.FILES_PATH}..%2Fhost/x", f"{p.EXPORT_PATH}..%2F..%2Fsecrets.json"):
            assert (await client.get(f"{host.base}{path}?t=x")).status_code in (401, 404)


async def test_document_tokens_carry_the_person_s_name(world):
    alice, _ = await world.user("Alice")
    workspace_id = await world.workspace(alice)
    doc_id = await world.doc(alice, workspace_id)
    minted = await world.call(alice, p.DOC_TOKEN, doc_id=doc_id)
    claims = verify_doc_token(minted["token"], world.ctx.secrets.doc_secret)
    assert (claims["uid"], claims["name"], claims["role"]) == (alice.id, "Alice", "owner")


def test_tokens_never_reach_the_log(tmp_path):
    member, bot = new_member_token(), "bbb_" + "x" * 43
    doc = mint_doc_token({"uid": "u1", "ws": "w1", "doc": "d1", "role": "editor"}, "secret", ttl_seconds=60)
    text = f"joined with {member}; bot {bot}; doc {doc}; link /blackboard/files/w1/r1?t={doc}&x=1; Bearer {member}"
    cleaned = redact(text)
    for secret in (member, bot, doc):
        assert secret not in cleaned
    assert "bbm_[redacted]" in cleaned and "?t=[redacted]&x=1" in cleaned

    record = logging.LogRecord("jiuwenswarm.extensions.blackboard", logging.ERROR, __file__, 1, "call with %s failed", (member,), None)
    assert member not in RedactingFormatter("%(message)s").format(record)


def test_settings_from_the_environment():
    env = {
        "BLACKBOARD_HOST_ENABLED": "1",
        "BLACKBOARD_HOST_BIND": "0.0.0.0",
        "BLACKBOARD_HOST_ALLOWED_ORIGINS": "https://Jiuwen.example.com/, https://b.example:8443",
        "BLACKBOARD_HOST_VERSION_RETENTION_DAYS": "90",
        "UNRELATED": "x",
    }
    settings = host_settings_from({"blackboard": {"host": {"enabled": False, "port": 19111}}}, env)
    assert (settings.enabled, settings.bind, settings.port, settings.version_retention_days) == (True, "0.0.0.0", 19111, 90)
    assert settings.allowed_origins == ("https://jiuwen.example.com", "https://b.example:8443")
    assert env_overrides(env) == ["allowed_origins", "bind", "enabled", "version_retention_days"]
    for bad in ({"allowed_origins": ["https://a.example/app"]}, {"version_retention_days": -1}, {"allowed_origins": ["ftp://a"]}):
        with pytest.raises(BlackboardError):
            validate_updates(bad)


async def test_this_jiuwenswarm_replaces_its_own_token_and_keeps_working(tmp_path):
    instance = Instance(tmp_path, HostSettings(enabled=True, port=free_port()))
    await instance.start()
    try:
        await instance.channel.ok(p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"})
        before = instance.client.registry.entries()[0]
        await instance.channel.ok(p.HOSTS_ROTATE_TOKEN, {"host": before.id})
        after = instance.client.registry.get(before.id)
        assert after is not None and after.token != before.token
        assert (await rpc(instance.settings.base_url(), p.ME, {}, before.token))[0] == 401
        listed = await instance.channel.ok(p.WORKSPACE_LIST, {})
        assert [w["name"] for w in listed["workspaces"]] == ["launch"]
    finally:
        await instance.stop()
