"""The client part: invite links, the host registry, host links and joining."""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.extensions.blackboard.client.hosts import HostEntry, HostRegistry
from jiuwenswarm.extensions.blackboard.client.invite_link import parse_invite_link
from jiuwenswarm.extensions.blackboard.client.link import HostLink, call_host, events_url
from jiuwenswarm.extensions.blackboard.client.runtime import ClientRuntime
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import (
    INVALID,
    NOT_FOUND,
    UNAUTHORIZED,
    UNAVAILABLE,
    BlackboardError,
)
from jiuwenswarm.extensions.blackboard.tests.backend.support import eventually, free_port, rpc

CODE = "abcdefghijklmnopqrst"


@pytest.mark.parametrize(
    "link,expected",
    [
        (f"http://127.0.0.1:19011/blackboard/join/{CODE}", ("http://127.0.0.1:19011", CODE)),
        (f"  https://bb.example.com/blackboard/join/{CODE}/ ", ("https://bb.example.com", CODE)),
        (f"https://example.com/team/blackboard/join/{CODE}", ("https://example.com/team", CODE)),
    ],
)
def test_invite_links(link, expected):
    assert parse_invite_link(link) == expected


@pytest.mark.parametrize(
    "link",
    [
        "",
        "   ",
        None,
        f"ftp://host/blackboard/join/{CODE}",
        "https://host/other/page",
        "https://host/blackboard/join/short",
        f"https://host/blackboard/join/{CODE.upper()}",
    ],
)
def test_text_that_is_not_an_invite_link(link):
    with pytest.raises(BlackboardError) as caught:
        parse_invite_link(link)
    assert caught.value.code == INVALID and caught.value.details == {"field": "url"}


def _entry(entry_id: str = "h1", uid: str = "host_1", url: str = "http://127.0.0.1:19011", **extra) -> HostEntry:
    return HostEntry(id=entry_id, host_uid=uid, name="Team", url=url, token=f"bbm_{entry_id}", user_id="u_1", **extra)


async def test_the_registry_keeps_hosts_and_a_default(tmp_path):
    registry = HostRegistry(tmp_path / "client" / "hosts.json")
    assert registry.entries() == [] and registry.default_id() == ""

    await registry.upsert(_entry())
    await registry.upsert(_entry("h2", "host_2", "https://BB.example.com/"))
    assert registry.default_id() == "h1"
    assert registry.find(url="https://bb.example.com").id == "h2"
    # The host uid wins over the address: one host can be reached at two addresses.
    assert registry.find(host_uid="host_2", url="http://127.0.0.1:19011").id == "h2"
    assert registry.find(host_uid="host_9") is None

    await registry.set_default("h2")
    assert registry.default_id() == "h2"
    assert await registry.remove("h2") is True
    assert registry.default_id() == "h1"
    assert await registry.remove("h2") is False
    assert "token" not in registry.get("h1").public()


async def test_the_registry_survives_a_damaged_file(tmp_path):
    path = tmp_path / "hosts.json"
    path.write_text("{not json", encoding="utf-8")
    registry = HostRegistry(path)
    assert registry.entries() == []

    data = {
        "hosts": [{"id": "broken"}, {**_entry().to_dict(), "added_later": True}, "junk"],
        "default_host": "gone",
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    assert [e.id for e in registry.entries()] == ["h1"]
    assert registry.default_id() == "h1"


def test_events_url():
    assert events_url("http://127.0.0.1:19011") == "ws://127.0.0.1:19011" + p.EVENTS_PATH
    assert events_url("https://bb.example.com/team") == "wss://bb.example.com/team" + p.EVENTS_PATH
    with pytest.raises(ValueError):
        events_url("ftp://host")


async def test_call_host_turns_answers_into_payloads_or_errors(host):
    operator = await host.operator("Alice")
    token = await host.rotate_token(operator.id)
    assert (await call_host(host.base, p.ME, {}, token=token))["display_name"] == "Alice"

    with pytest.raises(BlackboardError) as caught:
        await call_host(host.base, p.ME, {})
    assert caught.value.code == UNAUTHORIZED

    # Not a Blackboard answer (a 404 page of another service).
    with pytest.raises(BlackboardError) as caught:
        await call_host(host.base + "/elsewhere", p.ME, {}, token=token)
    assert caught.value.code == UNAVAILABLE and "404" in caught.value.message


async def test_an_unreachable_host_is_unavailable():
    base = f"http://127.0.0.1:{free_port()}"
    with pytest.raises(BlackboardError) as caught:
        await call_host(base, p.ME, {}, retries=1)
    assert caught.value.code == UNAVAILABLE and caught.value.details["url"] == base


async def test_a_link_reports_its_status(host):
    operator = await host.operator("Alice")
    token = await host.rotate_token(operator.id)
    seen: dict[str, list[str]] = {}

    async def on_status(host_id, status):  # noqa: ANN001
        seen.setdefault(host_id, []).append(status)

    async def on_event(host_id, event, payload):  # noqa: ANN001
        return None

    good = HostLink("good", host.base, token, on_event, on_status)
    refused = HostLink("refused", host.base, "bbm_wrong", on_event, on_status)
    offline = HostLink("offline", f"http://127.0.0.1:{free_port()}", token, on_event, on_status)
    links = (good, refused, offline)
    for link in links:
        link.start()
    try:
        await eventually(lambda: good.status == "connected")
        await eventually(lambda: refused.status == "unauthorized")
        await eventually(lambda: offline.status == "offline", timeout=15)
    finally:
        for link in links:
            await link.stop()
    assert seen["good"] == ["connected"]
    assert seen["refused"] == ["unauthorized"]
    assert good.status == "stopped"


async def _team(host) -> tuple[str, str, str]:
    """Alice's token, her workspace, and a one-time editor invite link to it."""
    operator = await host.operator("Alice")
    alice = await host.rotate_token(operator.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch-plan", "title": "Launch plan"}, alice)
    workspace_id = created["payload"]["workspace"]["id"]
    _, invite = await rpc(host.base, p.INVITE_CREATE, {"workspace_id": workspace_id, "role": "editor"}, alice)
    return alice, workspace_id, invite["payload"]["url"]


async def test_joining_a_host_and_following_its_events(host, tmp_path):
    alice, workspace_id, link = await _team(host)
    events: list[tuple[str, dict]] = []

    async def broadcast(event, payload):  # noqa: ANN001
        events.append((event, payload))

    client = ClientRuntime(tmp_path / "hosts.json", broadcast)
    await client.start()
    try:
        joined = await client.join(link, "Bob")
        host_id = joined["host"]
        assert joined["joined"] is True and joined["workspace"]["id"] == workspace_id
        entry = client.registry.get(host_id)
        assert entry.host_uid == host.ctx.host_uid and entry.token.startswith("bbm_")
        assert (entry.name, entry.display_name, entry.is_self) == ("Alice's Blackboard", "Bob", False)
        view = client.hosts_view()
        assert view["default_host"] == host_id and "token" not in view["hosts"][0]
        await eventually(lambda: client.hosts_view()["hosts"][0]["status"] == "connected")

        assert (await client.call(None, p.ME, {}))["display_name"] == "Bob"

        await rpc(host.base, p.WORKSPACE_RENAME, {"workspace_id": workspace_id, "title": "Plan"}, alice)
        forwarded = (p.EV_WORKSPACE_UPDATED, {"workspace_id": workspace_id, "host": host_id})
        await eventually(lambda: forwarded in events)

        # The same (now used-up) link again: the stored token is sent and nothing new is made.
        again = await client.join(link)
        assert (again["host"], again["joined"]) == (host_id, False)
        assert client.registry.get(host_id).token == entry.token
        assert len(client.registry.entries()) == 1

        await client.remove(host_id)
        assert client.hosts_view() == {"hosts": [], "default_host": ""}
        assert events[-1] == (p.EV_HOSTS_UPDATED, {"host": host_id, "removed": True})
        with pytest.raises(BlackboardError) as caught:
            await client.call(None, p.ME, {})
        assert caught.value.code == NOT_FOUND
    finally:
        await client.stop()


async def test_joining_needs_a_real_link_and_known_hosts_only(tmp_path):
    async def broadcast(event, payload):  # noqa: ANN001
        return None

    client = ClientRuntime(tmp_path / "hosts.json", broadcast)
    with pytest.raises(BlackboardError) as caught:
        await client.join("https://example.com/not-an-invite")
    assert caught.value.code == INVALID
    for action in (client.remove, client.set_default):
        with pytest.raises(BlackboardError) as caught:
            await action("h_missing")
        assert caught.value.code == NOT_FOUND


async def test_the_self_entry_is_reopened_only_when_it_changes(host, tmp_path):
    events: list[tuple[str, dict]] = []

    async def broadcast(event, payload):  # noqa: ANN001
        events.append((event, payload))

    client = ClientRuntime(tmp_path / "hosts.json", broadcast)
    operator = await host.operator("Alice")
    token = await host.rotate_token(operator.id)
    values = dict(
        host_uid=host.ctx.host_uid,
        url=host.base,
        user_id=operator.id,
        token=token,
        name="Alice's Blackboard",
        display_name="Alice",
    )
    try:
        entry = await client.ensure_self_entry(**values)
        assert entry.is_self and client.registry.default_id() == entry.id
        await eventually(lambda: client.hosts_view()["hosts"][0]["status"] == "connected")
        count = len(events)
        assert (await client.ensure_self_entry(**values)).id == entry.id
        assert len(events) == count
        assert (await client.call(entry.id, p.ME, {}))["is_operator"] is True
    finally:
        await client.stop()
