"""The plugin as the Gateway sees it, and two jiuwenswarm instances working together."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jiuwenswarm.extensions.application_host import application_plugin_manifest
from jiuwenswarm.extensions.blackboard import extension
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings, validate_updates
from jiuwenswarm.extensions.blackboard.tests.backend.support import FakeChannel, Instance, eventually, free_port
from jiuwenswarm.extensions.loader import ExtensionLoader
from jiuwenswarm.extensions.registry import ExtensionRegistry
from jiuwenswarm.extensions.sdk import ApplicationPluginServices

PLUGIN_DIR = Path(extension.__file__).parent
LOCAL_METHODS = {p.HOSTS_LIST, p.HOSTS_JOIN, p.HOSTS_REMOVE, p.HOSTS_SET_DEFAULT, p.HOST_STATUS, p.HOST_SET_SETTINGS}


async def test_the_loader_registers_the_plugin_and_its_page():
    registry = ExtensionRegistry(MagicMock(), {}, MagicMock())
    loaded = await ExtensionLoader(registry).load_extension(PLUGIN_DIR)
    assert loaded and loaded[0].plugin_id == "blackboard"
    assert registry.get_application_plugin("blackboard") is loaded[0]

    (page,) = [e for e in application_plugin_manifest(registry)["plugins"] if e["plugin_id"] == "blackboard"]
    assert (page["nav_key"], page["render_mode"], page["component"]) == ("app:blackboard", "bundled", "blackboard")
    assert page["title_i18n_key"] == "blackboard.nav" and page["enabled"] is True
    assert set(page["permissions"]) == {"outbound_network", "agent_tools"}
    # Always on, right below Tasks in the rail, with its own icon.
    assert page["nav_after"] == "chat"
    # The bundled page and its rail icon are found by this id.
    index = (PLUGIN_DIR / "frontend" / "index.tsx").read_text(encoding="utf-8")
    assert "export const applicationPluginId = 'blackboard';" in index
    assert "as applicationPluginNavIcon" in index


@pytest.fixture
def plugin_env(tmp_path, monkeypatch):
    """Point the plugin at a temporary data root and an in-memory config."""
    state = {"settings": HostSettings(port=free_port(), operator_name="Alice")}

    def save(updates):  # noqa: ANN001
        state["settings"] = replace(state["settings"], **validate_updates(updates))
        return state["settings"]

    monkeypatch.setattr(extension, "blackboard_dir", lambda: tmp_path / "blackboard")
    monkeypatch.setattr(extension, "setup_file_logging", lambda directory: None)
    monkeypatch.setattr(extension, "load_host_settings", lambda: state["settings"])
    monkeypatch.setattr(extension, "save_host_settings", save)
    return state


async def _bound(plugin_env) -> tuple[extension.BlackboardApplicationPlugin, FakeChannel]:
    plugin = extension.BlackboardApplicationPlugin()
    channel = FakeChannel()
    plugin.bind_web_channel(channel, ApplicationPluginServices())
    await asyncio.gather(*plugin._tasks)
    return plugin, channel


async def test_binding_registers_local_methods_only(plugin_env):
    plugin, channel = await _bound(plugin_env)
    try:
        assert set(channel.methods) == LOCAL_METHODS | set(p.HOST_METHODS)
        assert channel.local_only == set(channel.methods)
        assert await channel.ok(p.HOSTS_LIST) == {"hosts": [], "default_host": ""}
        status = await channel.ok(p.HOST_STATUS)
        assert status["running"] is False and status["enabled"] is False
        assert status["reachable_from_other_machines"] is False

        # Host methods need a host to talk to.
        reply = await channel.call(p.ME)
        assert (reply["ok"], reply["code"]) == (False, "not_found")
        reply = await channel.call(p.ME, {"host": 42})
        assert (reply["code"], reply["payload"]) == ("invalid", {"details": {"field": "host"}})
    finally:
        await plugin.shutdown()


async def test_a_host_enabled_in_config_starts_with_the_gateway(plugin_env):
    plugin_env["settings"] = replace(plugin_env["settings"], enabled=True)
    plugin, channel = await _bound(plugin_env)
    try:
        status = await channel.ok(p.HOST_STATUS)
        assert status["running"] is True and status["error"] is None
        (entry,) = (await channel.ok(p.HOSTS_LIST))["hosts"]
        assert entry["is_self"] is True and entry["name"] == "Alice's Blackboard"
        await eventually(lambda: plugin.client.hosts_view()["hosts"][0]["status"] == "connected")
        me = await channel.ok(p.ME)
        assert me["display_name"] == "Alice" and me["is_operator"] is True
    finally:
        await plugin.shutdown()


async def test_settings_are_checked_before_they_are_saved(plugin_env):
    plugin, channel = await _bound(plugin_env)
    try:
        for params, field in [
            ({"settings": {"port": "abc"}}, "port"),
            ({"settings": {"port": 70000}}, "port"),
            ({"settings": {"public_url": "ftp://x"}}, "public_url"),
            ({"settings": "enabled"}, "settings"),
        ]:
            reply = await channel.call(p.HOST_SET_SETTINGS, params)
            assert reply["code"] == "invalid" and reply["payload"]["details"]["field"] == field, params
        reply = await channel.call(p.HOST_SET_SETTINGS, {"settings": {"colour": "red"}})
        assert reply["code"] == "invalid" and reply["payload"]["details"]["fields"] == ["colour"]
        assert plugin_env["settings"].port != 70000
    finally:
        await plugin.shutdown()


async def test_a_busy_port_is_shown_and_can_be_fixed(plugin_env):
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", plugin_env["settings"].port))
        blocker.listen(1)
        plugin, channel = await _bound(plugin_env)
        try:
            status = await channel.ok(p.HOST_SET_SETTINGS, {"settings": {"enabled": True}})
            assert status["running"] is False and "cannot listen" in status["error"]
            assert channel.named(p.EV_HOST_STATUS)[-1]["error"] == status["error"]
            # The client part keeps working.
            assert await channel.ok(p.HOSTS_LIST) == {"hosts": [], "default_host": ""}

            status = await channel.ok(p.HOST_SET_SETTINGS, {"settings": {"port": free_port()}})
            assert status["running"] is True and status["error"] is None
        finally:
            await plugin.shutdown()


async def test_renaming_the_blackboard_reaches_members(tmp_path):
    alice = Instance(tmp_path / "alice", HostSettings(port=free_port(), operator_name="Alice"))
    bob = Instance(tmp_path / "bob", HostSettings())
    await alice.start()
    await bob.start()
    try:
        await alice.channel.ok(p.HOST_SET_SETTINGS, {"settings": {"enabled": True}})
        created = await alice.channel.ok(p.WORKSPACE_CREATE, {"name": "launch-plan", "title": "Launch plan"})
        invite = await alice.channel.ok(p.INVITE_CREATE, {"workspace_id": created["workspace"]["id"], "role": "editor"})
        await bob.channel.ok(p.HOSTS_JOIN, {"url": invite["url"], "display_name": "Bob"})

        def bob_sees() -> str:
            return bob.client.hosts_view()["hosts"][0]["name"]

        await eventually(lambda: bob.client.hosts_view()["hosts"][0]["status"] == "connected")
        assert bob_sees() == "Alice's Blackboard"

        status = await alice.channel.ok(p.HOST_SET_SETTINGS, {"settings": {"name": "  Launch   team "}})
        assert status["name"] == "Launch team" and status["settings"]["name"] == "Launch team"
        (own,) = (await alice.channel.ok(p.HOSTS_LIST))["hosts"]
        assert own["name"] == "Launch team"
        await eventually(lambda: bob_sees() == "Launch team")
        assert bob.channel.named(p.EV_HOSTS_UPDATED)

        # Renamed while Bob's instance was away: he gets the name when his link reconnects.
        await bob.client.stop()
        await alice.channel.ok(p.HOST_SET_SETTINGS, {"settings": {"name": ""}})
        await bob.client.start()
        await eventually(lambda: bob_sees() == "Alice's Blackboard")
    finally:
        await alice.stop()
        await bob.stop()


async def test_two_instances(tmp_path):
    """Alice hosts, Bob joins with a link, and changes on the host reach Bob's browser."""
    alice = Instance(tmp_path / "alice", HostSettings(port=free_port(), operator_name="Alice"))
    bob = Instance(tmp_path / "bob", HostSettings())
    await alice.start()
    await bob.start()
    try:
        status = await alice.channel.ok(p.HOST_SET_SETTINGS, {"settings": {"enabled": True}})
        assert status["running"] is True and alice.settings.enabled is True
        (own,) = (await alice.channel.ok(p.HOSTS_LIST))["hosts"]
        assert own["is_self"] is True

        created = await alice.channel.ok(p.WORKSPACE_CREATE, {"name": "launch-plan", "title": "Launch plan"})
        workspace_id = created["workspace"]["id"]
        invite = await alice.channel.ok(p.INVITE_CREATE, {"workspace_id": workspace_id, "role": "editor"})
        assert invite["url"].startswith(f"http://127.0.0.1:{alice.settings.port}/blackboard/join/")

        joined = await bob.channel.ok(p.HOSTS_JOIN, {"url": invite["url"], "display_name": "Bob"})
        assert joined["joined"] is True and joined["workspace"]["role"] == "editor"
        host_id = joined["host"]
        await eventually(lambda: bob.client.hosts_view()["hosts"][0]["status"] == "connected")
        assert [w["id"] for w in (await bob.channel.ok(p.WORKSPACE_LIST))["workspaces"]] == [workspace_id]

        members = (await alice.channel.ok(p.MEMBER_LIST, {"workspace_id": workspace_id}))["members"]
        bob_id = next(m["user_id"] for m in members if m["display_name"] == "Bob")
        bob.channel.events.clear()
        await alice.channel.ok(p.MEMBER_SET_ROLE, {"workspace_id": workspace_id, "user_id": bob_id, "role": "viewer"})
        await eventually(lambda: bob.channel.named(p.EV_MEMBER_ROLE_CHANGED))
        assert bob.channel.named(p.EV_MEMBER_ROLE_CHANGED) == [
            {"workspace_id": workspace_id, "user_id": bob_id, "role": "viewer", "host": host_id}
        ]

        reply = await bob.channel.call(p.WORKSPACE_RENAME, {"workspace_id": workspace_id, "title": "Mine now"})
        assert (reply["ok"], reply["code"]) == (False, "forbidden")
        reply = await bob.channel.call(p.HOSTS_JOIN, {"url": "https://example.com/nope"})
        assert reply["code"] == "invalid"

        # A new port restarts the host, and Alice's own entry follows it.
        port = free_port()
        status = await alice.channel.ok(p.HOST_SET_SETTINGS, {"settings": {"port": port}})
        assert status["listening"] == f"127.0.0.1:{port}"
        (own,) = (await alice.channel.ok(p.HOSTS_LIST))["hosts"]
        assert own["url"] == f"http://127.0.0.1:{port}"
        await eventually(lambda: alice.client.hosts_view()["hosts"][0]["status"] == "connected")
        assert len((await alice.channel.ok(p.WORKSPACE_LIST))["workspaces"]) == 1

        # Turning hosting off keeps the entry; its link goes offline.
        status = await alice.channel.ok(p.HOST_SET_SETTINGS, {"settings": {"enabled": False}})
        assert status["running"] is False
        await eventually(lambda: alice.client.hosts_view()["hosts"][0]["status"] == "offline", timeout=15)
    finally:
        await alice.stop()
        await bob.stop()
