# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""F16: WebChannel 关停必须先唤醒媒体叶子、再关它们依赖的 Provider,
完成度由所有唤醒动作之后的最终状态裁定,且并发 stop 共享一个结局。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from jiuwenswarm.gateway.channel_manager.web.web_connect import WebChannel


class _FakeRegistry:
    def __init__(self, order: list[str]) -> None:
        self._order = order
        self.cleanup_complete = True

    def stop_all_leaves(self) -> int:
        self._order.append("stop_all_leaves")
        return 1

    async def close_expiry_sweeper(self) -> None:
        self._order.append("close_expiry_sweeper")

    async def close_media_leaf_cleanup(self, **_kwargs) -> bool:
        self._order.append("close_media_leaf_cleanup")
        return self.cleanup_complete

    def close_streaming_observability(self) -> None:
        self._order.append("close_streaming_observability")

    def close_streaming_diagnostics(self) -> bool:
        self._order.append("close_streaming_diagnostics")
        return True

    @property
    def media_leaf_cleanup_snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(cleanup_complete=self.cleanup_complete)


class _FakeStreamingOwner:
    def __init__(self, order: list[str], label: str) -> None:
        self._order = order
        self._label = label

    async def close(self) -> None:
        self._order.append(self._label)


def _channel(order: list[str], registry: _FakeRegistry) -> WebChannel:
    channel = object.__new__(WebChannel)
    channel._running = True
    channel._clients_by_key = {}
    channel._server = None
    channel.live_voice_streaming_synthesis_owner = _FakeStreamingOwner(
        order, "close_streaming_synthesis_owner"
    )
    channel.live_voice_streaming_speech_owner = _FakeStreamingOwner(
        order, "close_streaming_speech_owner"
    )
    channel.live_voice_owned_speech_service = _FakeStreamingOwner(
        order, "close_speech_service"
    )
    channel.live_voice_speech_service = channel.live_voice_owned_speech_service
    channel.live_voice_media_registry = registry

    async def _shutdown_all_writers() -> None:
        order.append("shutdown_writers")

    channel._shutdown_all_writers = _shutdown_all_writers
    return channel


@pytest.mark.asyncio
async def test_shutdown_wakes_leaves_and_joins_before_closing_providers() -> None:
    order: list[str] = []
    registry = _FakeRegistry(order)
    channel = _channel(order, registry)

    await channel.stop()

    assert order[:3] == [
        "stop_all_leaves",
        "close_expiry_sweeper",
        "close_media_leaf_cleanup",
    ], order
    assert order.index("close_media_leaf_cleanup") < order.index(
        "close_streaming_synthesis_owner"
    )
    assert order.index("close_streaming_synthesis_owner") < order.index(
        "close_streaming_diagnostics"
    )


@pytest.mark.asyncio
async def test_concurrent_stop_calls_share_one_settlement() -> None:
    order: list[str] = []
    registry = _FakeRegistry(order)
    channel = _channel(order, registry)

    await asyncio.gather(channel.stop(), channel.stop())
    await channel.stop()

    assert order.count("close_streaming_synthesis_owner") == 1
    assert order.count("stop_all_leaves") == 1


@pytest.mark.asyncio
async def test_incomplete_verdict_is_taken_from_final_state() -> None:
    order: list[str] = []
    registry = _FakeRegistry(order)
    registry.cleanup_complete = False
    channel = _channel(order, registry)

    with pytest.raises(RuntimeError, match="media task cleanup is incomplete"):
        await channel.stop()
