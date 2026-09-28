"""Tools that application plugins offer per request (``ApplicationPluginExtension.agent_tools``).

Kept out of ``interface_deep.py`` so the attach and detach rules can be tested
without building an agent.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def collect_plugin_tools(registry: Any, ctx: Any) -> dict[str, Any]:
    """Tools of every enabled application plugin, by tool name.

    A plugin that raises is skipped; a name offered twice keeps the first tool.
    """
    tools: dict[str, Any] = {}
    for plugin in registry.get_application_plugins():
        try:
            if not plugin.is_enabled():
                continue
            offered = plugin.agent_tools(ctx) or []
        except Exception:  # noqa: BLE001 - one broken plugin must not break the request
            logger.exception("application plugin %s failed to offer tools", getattr(plugin, "plugin_id", "?"))
            continue
        for tool in offered:
            name = getattr(getattr(tool, "card", None), "name", None)
            if not name:
                logger.warning("application plugin %s offered a tool without a name", plugin.plugin_id)
                continue
            if name in tools:
                logger.warning("tool %s is offered by two application plugins; keeping the first", name)
                continue
            tools[name] = tool
    return tools


class PluginToolAttacher:
    """Keeps one agent's plugin tools in step with what the plugins offer."""

    def __init__(self) -> None:
        self._attached: dict[str, Any] = {}
        self._manager: Any = None

    @property
    def names(self) -> set[str]:
        return set(self._attached)

    def update(
        self,
        *,
        registry: Any,
        ctx: Any,
        ability_manager: Any,
        register: Callable[[Any], None],
    ) -> None:
        if ability_manager is not self._manager:
            # A rebuilt agent starts with a fresh ability manager that holds none of our tools.
            self._attached.clear()
            self._manager = ability_manager
        wanted = collect_plugin_tools(registry, ctx) if registry is not None else {}
        for name, tool in list(self._attached.items()):
            if wanted.get(name) is not tool:
                # remove_ability also drops the instance from the global resource manager.
                ability_manager.remove_ability(name)
                del self._attached[name]
        for name, tool in wanted.items():
            if name in self._attached:
                continue
            register(tool)
            ability_manager.add(tool.card)
            self._attached[name] = tool
