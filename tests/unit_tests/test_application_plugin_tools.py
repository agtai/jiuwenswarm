"""Tools that application plugins offer to the agent (``ApplicationPluginExtension.agent_tools``)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from jiuwenswarm.extensions.registry import ExtensionRegistry
from jiuwenswarm.extensions.sdk import AgentToolContext, ApplicationPluginExtension
from jiuwenswarm.extensions.types import ExtensionMetadata
from jiuwenswarm.server.runtime.agent_adapter.plugin_tools import PluginToolAttacher, collect_plugin_tools


def _tool(name: str | None) -> Any:
    return SimpleNamespace(card=SimpleNamespace(name=name))


class _Plugin(ApplicationPluginExtension):
    def __init__(self, plugin_id: str, offer: Any, *, enabled: bool = True) -> None:
        self.plugin_id = plugin_id
        self.offer = offer
        self.enabled = enabled
        self.contexts: list[AgentToolContext] = []

    @property
    def metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            id=self.plugin_id,
            name=self.plugin_id,
            version="1.0.0",
            description="",
            author="tests",
            min_jiuwenswarm_version="0.2.5",
            dependencies={},
            config_schema=None,
            package_type="application",
        )

    async def initialize(self, config) -> None:  # noqa: ANN001
        return None

    async def shutdown(self) -> None:
        return None

    def is_enabled(self) -> bool:
        return self.enabled

    def agent_tools(self, ctx: AgentToolContext) -> list[Any]:
        self.contexts.append(ctx)
        if isinstance(self.offer, Exception):
            raise self.offer
        return list(self.offer)


def _registry(*plugins: _Plugin) -> ExtensionRegistry:
    registry = ExtensionRegistry(MagicMock(), {}, MagicMock())
    for plugin in plugins:
        registry.register_application_plugin(plugin)
    return registry


class _Manager:
    def __init__(self) -> None:
        self.cards: list[Any] = []
        self.removed: list[str] = []

    def add(self, card: Any) -> None:
        self.cards.append(card)

    def remove_ability(self, name: str) -> None:
        self.removed.append(name)
        self.cards = [c for c in self.cards if c.name != name]


def test_plugins_offer_no_tools_by_default():
    plugin = _Plugin("quiet", [])
    assert ApplicationPluginExtension.agent_tools(plugin, AgentToolContext()) == []


def test_collect_skips_disabled_and_broken_plugins_and_keeps_the_first_name():
    first, second, nameless = _tool("board_read"), _tool("board_read"), _tool(None)
    registry = _registry(
        _Plugin("a", [first, nameless]),
        _Plugin("b", [second, _tool("board_write")]),
        _Plugin("off", [_tool("hidden")], enabled=False),
        _Plugin("broken", RuntimeError("boom")),
    )
    tools = collect_plugin_tools(registry, AgentToolContext(session_id="s1"))
    assert list(tools) == ["board_read", "board_write"]
    assert tools["board_read"] is first


def test_the_attacher_follows_what_plugins_offer():
    read, write = _tool("board_read"), _tool("board_write")
    plugin = _Plugin("board", [read, write])
    registry = _registry(plugin)
    manager, registered = _Manager(), []
    attacher = PluginToolAttacher()

    def update(target: _Manager = manager) -> None:
        attacher.update(registry=registry, ctx=AgentToolContext(), ability_manager=target, register=registered.append)

    update()
    assert registered == [read, write] and [c.name for c in manager.cards] == ["board_read", "board_write"]

    update()
    assert registered == [read, write] and manager.removed == []

    replacement = _tool("board_read")
    plugin.offer = [replacement]
    update()
    assert manager.removed == ["board_read", "board_write"]
    assert registered[-1] is replacement and attacher.names == {"board_read"}

    # A rebuilt agent has a fresh manager: everything is attached again.
    fresh = _Manager()
    update(fresh)
    assert fresh.cards == [replacement.card] and fresh.removed == []

    attacher.update(registry=None, ctx=AgentToolContext(), ability_manager=fresh, register=registered.append)
    assert fresh.removed == ["board_read"] and attacher.names == set()


def test_the_adapter_hands_the_request_to_the_plugins(monkeypatch):
    from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter

    tool = _tool("board_read")
    plugin = _Plugin("board", [tool])
    monkeypatch.setattr(ExtensionRegistry, "get_instance", classmethod(lambda cls: _registry(plugin)))
    manager, registered = _Manager(), []
    adapter = SimpleNamespace(
        _plugin_tools=PluginToolAttacher(),
        _instance=SimpleNamespace(ability_manager=manager),
        _register_agent_owned_tool=lambda t, owner: registered.append((t, owner)),
        _tool_owner_id=lambda: "owner-1",
    )
    config = JiuWenSwarmDeepAdapter._RuntimeConfig(
        session_id="s1", channel_id="web", request_id="r1", request_metadata={"source": "blackboard"}
    )

    JiuWenSwarmDeepAdapter._update_plugin_tools(adapter, config)

    assert plugin.contexts == [
        AgentToolContext(session_id="s1", channel_id="web", request_id="r1", user_id=None, metadata={"source": "blackboard"})
    ]
    assert registered == [(tool, "owner-1")] and manager.cards == [tool.card]

    # A failing attach is logged, and the turn goes on.
    adapter._instance = SimpleNamespace(ability_manager=None)
    JiuWenSwarmDeepAdapter._update_plugin_tools(adapter, config)
