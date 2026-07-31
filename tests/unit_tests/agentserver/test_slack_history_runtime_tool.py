# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""Per-request registration tests for the Slack history tool."""

from __future__ import annotations

import asyncio
from contextvars import Context
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from jiuwenswarm.server.runtime.agent_adapter import interface_deep as interface_module


_TOOL_NAME = "get_current_slack_channel_history"


class _FakeAbilityManager:
    def __init__(self) -> None:
        self._cards: dict[str, Any] = {}

    def list(self) -> list[Any]:
        return list(self._cards.values())

    def add(self, card: Any) -> None:
        self._cards[card.name] = card

    def remove(self, name: str) -> None:
        self._cards.pop(name, None)


class _FakeResourceManager:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def add_tool(self, tool: Any) -> None:
        if tool.card.id in self.tools:
            raise AssertionError(f"duplicate tool id: {tool.card.id}")
        self.tools[tool.card.id] = tool


class _FakeSlackHistoryToolkit:
    instances: list["_FakeSlackHistoryToolkit"] = []

    def __init__(
        self,
        *,
        metadata: dict[str, Any] | None = None,
        metadata_provider: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        self.metadata = dict(metadata or {})
        self.metadata_provider = metadata_provider
        self.updates: list[dict[str, Any]] = []
        tool_id = f"{_TOOL_NAME}-{len(self.instances)}"
        self.tool = SimpleNamespace(card=SimpleNamespace(id=tool_id, name=_TOOL_NAME))
        self.instances.append(self)

    def update_runtime_context(
        self,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.metadata = dict(metadata or {})
        self.updates.append(self.metadata)

    def get_tools(self) -> list[Any]:
        return [self.tool]


def _make_adapter() -> tuple[Any, _FakeAbilityManager]:
    adapter = object.__new__(interface_module.JiuWenSwarmDeepAdapter)
    ability_manager = _FakeAbilityManager()
    adapter._instance = SimpleNamespace(ability_manager=ability_manager)
    adapter._send_file_toolkit = None
    adapter._slack_history_toolkit = None
    adapter._slack_history_tools = []
    adapter._runtime_cron_tool_context = interface_module._RuntimeCronToolContext(
        tool_scope=f"test_{id(adapter):x}",
    )
    adapter._build_cron_tools = lambda: []
    adapter._resolve_prompt_channel = lambda _session_id: "web"
    return adapter, ability_manager


async def _update_tools(
    adapter: Any,
    *,
    channel_id: str,
    metadata: dict[str, Any] | None,
) -> None:
    channel_token = interface_module._CRON_TOOL_CHANNEL_ID.set(channel_id)
    metadata_token = interface_module._CRON_TOOL_METADATA.set(metadata)
    bound_token = interface_module._CRON_TOOL_BOUND.set(True)
    try:
        adapter._runtime_cron_tool_context.remember_current_binding()
        await adapter._update_session_tools(
            session_id="session-1",
            request_id="request-1",
            channel_id=channel_id,
        )
    finally:
        interface_module._CRON_TOOL_BOUND.reset(bound_token)
        interface_module._CRON_TOOL_METADATA.reset(metadata_token)
        interface_module._CRON_TOOL_CHANNEL_ID.reset(channel_token)


async def _read_provider(
    toolkit: _FakeSlackHistoryToolkit,
    *,
    channel_id: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    channel_token = interface_module._CRON_TOOL_CHANNEL_ID.set(channel_id)
    metadata_token = interface_module._CRON_TOOL_METADATA.set(metadata)
    bound_token = interface_module._CRON_TOOL_BOUND.set(True)
    try:
        await asyncio.sleep(0)
        assert toolkit.metadata_provider is not None
        return toolkit.metadata_provider()
    finally:
        interface_module._CRON_TOOL_BOUND.reset(bound_token)
        interface_module._CRON_TOOL_METADATA.reset(metadata_token)
        interface_module._CRON_TOOL_CHANNEL_ID.reset(channel_token)


@pytest.fixture(autouse=True)
def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> _FakeResourceManager:
    _FakeSlackHistoryToolkit.instances.clear()
    resource_manager = _FakeResourceManager()
    monkeypatch.setattr(
        interface_module, "SlackHistoryToolkit", _FakeSlackHistoryToolkit
    )
    monkeypatch.setattr(
        interface_module,
        "Runner",
        SimpleNamespace(resource_mgr=resource_manager),
    )
    monkeypatch.setattr(
        interface_module,
        "get_config",
        lambda: {
            "channels": {
                "slack": {
                    "send_file_allowed": False,
                    "history_digest_channel_ids": ["C-ONE", "C-TWO", "C-THREE"],
                },
                "web": {"send_file_allowed": False},
            }
        },
    )
    return resource_manager


@pytest.mark.asyncio
async def test_slack_history_tool_uses_context_local_metadata_for_every_request() -> (
    None
):
    adapter, abilities = _make_adapter()

    await _update_tools(
        adapter,
        channel_id="slack",
        metadata={
            "slack_channel_id": "C-ONE",
            "slack_user_id": "U-ONE",
            "slack_history_digest_allowed": True,
        },
    )

    assert [card.name for card in abilities.list()] == [_TOOL_NAME]
    assert len(_FakeSlackHistoryToolkit.instances) == 1
    toolkit = _FakeSlackHistoryToolkit.instances[0]
    assert toolkit.metadata == {}
    assert toolkit.updates == []

    first, second, non_slack = await asyncio.gather(
        _read_provider(
            toolkit,
            channel_id="slack",
            metadata={
                "slack_channel_id": "C-ONE",
                "slack_user_id": "U-ONE",
                "slack_history_digest_allowed": True,
            },
        ),
        _read_provider(
            toolkit,
            channel_id="slack",
            metadata={
                "slack_channel_id": "C-TWO",
                "slack_user_id": "U-TWO",
                "slack_history_digest_allowed": True,
            },
        ),
        _read_provider(
            toolkit,
            channel_id="web",
            metadata={"slack_channel_id": "C-HIDDEN"},
        ),
    )

    assert first == {
        "slack_channel_id": "C-ONE",
        "slack_user_id": "U-ONE",
        "slack_history_digest_allowed": True,
    }
    assert second == {
        "slack_channel_id": "C-TWO",
        "slack_user_id": "U-TWO",
        "slack_history_digest_allowed": True,
    }
    assert non_slack == {}


@pytest.mark.asyncio
async def test_slack_history_tool_keeps_trusted_metadata_across_worker_boundary() -> (
    None
):
    adapter, _abilities = _make_adapter()
    metadata = {
        "slack_channel_id": "C-ONE",
        "slack_channel_type": "channel",
        "slack_user_id": "U-ONE",
        "slack_history_digest_allowed": True,
    }

    await _update_tools(adapter, channel_id="slack", metadata=metadata)

    toolkit = _FakeSlackHistoryToolkit.instances[0]
    assert toolkit.metadata_provider is not None

    async def _invoke_from_worker() -> dict[str, Any] | None:
        await asyncio.sleep(0)
        return toolkit.metadata_provider()

    provided = await Context().run(asyncio.create_task, _invoke_from_worker())

    assert provided == metadata


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel_id", "metadata"),
    [
        ("web", {"slack_channel_id": "C-ONE"}),
        ("slack", {"slack_channel_id": "C-NOT-ALLOWED"}),
        ("slack", {}),
        ("slack", None),
    ],
)
async def test_slack_history_tool_is_not_registered_outside_current_slack_channel(
    channel_id: str,
    metadata: dict[str, Any] | None,
) -> None:
    adapter, abilities = _make_adapter()

    await _update_tools(adapter, channel_id=channel_id, metadata=metadata)

    assert abilities.list() == []
    assert _FakeSlackHistoryToolkit.instances == []


@pytest.mark.asyncio
async def test_registered_slack_history_tool_stays_stable_across_transports() -> None:
    adapter, abilities = _make_adapter()
    abilities.add(SimpleNamespace(id="unrelated-tool", name="unrelated_tool"))

    await _update_tools(
        adapter,
        channel_id="slack",
        metadata={
            "slack_channel_id": "C-ONE",
            "slack_history_digest_allowed": True,
        },
    )
    await _update_tools(
        adapter,
        channel_id="web",
        metadata={"slack_channel_id": "C-ONE"},
    )
    assert {card.name for card in abilities.list()} == {"unrelated_tool", _TOOL_NAME}
    toolkit = _FakeSlackHistoryToolkit.instances[0]
    assert toolkit.metadata_provider is not None
    assert toolkit.metadata_provider() == {}

    await _update_tools(
        adapter,
        channel_id="slack",
        metadata={
            "slack_channel_id": "C-THREE",
            "slack_history_digest_allowed": True,
        },
    )

    assert {card.name for card in abilities.list()} == {"unrelated_tool", _TOOL_NAME}
    assert len(_FakeSlackHistoryToolkit.instances) == 1
    assert _FakeSlackHistoryToolkit.instances[0].updates == []
    assert toolkit.metadata_provider() == {
        "slack_channel_id": "C-THREE",
        "slack_history_digest_allowed": True,
    }


@pytest.mark.asyncio
async def test_slack_history_tool_is_isolated_between_session_adapters(
    _patch_runtime: _FakeResourceManager,
) -> None:
    first_adapter, first_abilities = _make_adapter()
    second_adapter, second_abilities = _make_adapter()

    await _update_tools(
        first_adapter,
        channel_id="slack",
        metadata={
            "slack_channel_id": "C-ONE",
            "slack_history_digest_allowed": True,
        },
    )
    await _update_tools(
        second_adapter,
        channel_id="slack",
        metadata={
            "slack_channel_id": "C-TWO",
            "slack_history_digest_allowed": True,
        },
    )

    assert len(_patch_runtime.tools) == 2
    assert [card.name for card in first_abilities.list()] == [_TOOL_NAME]
    assert [card.name for card in second_abilities.list()] == [_TOOL_NAME]

    await _update_tools(
        first_adapter,
        channel_id="web",
        metadata={"slack_channel_id": "C-ONE"},
    )

    assert [card.name for card in first_abilities.list()] == [_TOOL_NAME]
    assert [card.name for card in second_abilities.list()] == [_TOOL_NAME]
    assert _FakeSlackHistoryToolkit.instances[0].updates == []
    assert _FakeSlackHistoryToolkit.instances[1].updates == []
    first_provider = _FakeSlackHistoryToolkit.instances[0].metadata_provider
    second_provider = _FakeSlackHistoryToolkit.instances[1].metadata_provider
    assert first_provider is not None
    assert second_provider is not None
    assert first_provider() == {}
    assert second_provider() == {
        "slack_channel_id": "C-TWO",
        "slack_history_digest_allowed": True,
    }
