"""Reference files: upload over HTTP, list, open by link, remove; and the local upload RPC."""

from __future__ import annotations

import base64
from dataclasses import replace

import httpx

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.tests.backend.support import Instance, free_port, rpc


async def _setup(host):
    operator = await host.operator("Alice")
    token = await host.rotate_token(operator.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"}, token)
    return token, created["payload"]["workspace"]["id"]


async def _upload(host, token: str, workspace_id: str, content: bytes, name: str = "brief.txt") -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{host.base}{p.FILES_PATH}{workspace_id}",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (name, content, "text/plain")},
            data={"note": "Read first"},
        )
    return response.json()


async def test_upload_open_and_remove(host):
    token, workspace_id = await _setup(host)
    uploaded = await _upload(host, token, workspace_id, b"hello")
    reference = uploaded["payload"]["reference"]
    assert (reference["name"], reference["size"], reference["kind"], reference["note"]) == ("brief.txt", 5, "file", "Read first")

    _, listed = await rpc(host.base, p.REFERENCE_LIST, {"workspace_id": workspace_id}, token)
    assert [r["id"] for r in listed["payload"]["references"]] == [reference["id"]]
    _, link = await rpc(host.base, p.REFERENCE_URL, {"reference_id": reference["id"]}, token)
    url = link["payload"]["url"]
    async with httpx.AsyncClient() as client:
        assert (await client.get(url)).content == b"hello"
        assert (await client.get(url.replace(reference["id"], "r_other"))).status_code == 401
        assert (await client.get(url[:-3] + "abc")).status_code == 401

        await rpc(host.base, p.REFERENCE_REMOVE, {"reference_id": reference["id"]}, token)
        assert (await client.get(url)).status_code == 404
    assert not any((host.ctx.files_dir / workspace_id).iterdir())


async def test_viewers_cannot_upload_and_the_size_limit_holds(host):
    token, workspace_id = await _setup(host)
    _, invite = await rpc(host.base, p.INVITE_CREATE, {"workspace_id": workspace_id, "role": "viewer"}, token)
    _, joined = await rpc(host.base, p.INVITE_ACCEPT, {"code": invite["payload"]["invite"]["code"], "display_name": "Bob"})
    denied = await _upload(host, joined["payload"]["token"], workspace_id, b"x")
    assert denied["error"]["code"] == "forbidden"

    host.ctx.get_settings = lambda: replace(HostSettings(), max_upload_mb=1)
    too_big = await _upload(host, token, workspace_id, b"x" * (1024 * 1024 + 1))
    assert too_big["error"]["code"] == "invalid" and too_big["error"]["details"]["limit_mb"] == 1


async def test_the_browser_uploads_through_its_own_jiuwenswarm(tmp_path):
    instance = Instance(tmp_path, HostSettings(enabled=True, port=free_port()))
    await instance.start()
    try:
        workspace = await instance.channel.ok(p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"})
        workspace_id = workspace["workspace"]["id"]
        data = base64.b64encode(b"\x89PNG....").decode()
        result = await instance.channel.ok(
            p.REFERENCE_UPLOAD, {"workspace_id": workspace_id, "name": "shot.png", "mime": "image/png", "data": data}
        )
        assert result["reference"]["kind"] == "image" and result["reference"]["size"] == 8
        bad = await instance.channel.call(p.REFERENCE_UPLOAD, {"workspace_id": workspace_id, "name": "x", "data": "%%"})
        assert bad["code"] == "invalid"
    finally:
        await instance.stop()
