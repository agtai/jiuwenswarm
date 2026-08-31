# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""WebChannel `_ws_sessions` 仅追踪显式 session（Issue #2334）。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web.web_connect import (
    WebChannel,
    WebChannelConfig,
)


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent_frames: list[dict[str, Any]] = []
        self.remote_address = ("127.0.0.1", 12345)

    async def send(self, data: str) -> None:
        self.sent_frames.append(json.loads(data))


def _req(*, req_id: str, method: str, params: dict[str, Any] | None = None) -> str:
    return json.dumps(
        {
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params or {},
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_ws_sessions_tracks_explicit_session_id():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    ws = _FakeWebSocket()
    channel.on_message(lambda msg: None)

    await channel._handle_raw_message(
        ws,
        _req(
            req_id="req-chat",
            method="chat.send",
            params={"session_id": "sess-real", "content": "hi"},
        ),
        {},
    )

    assert channel._ws_sessions.get(id(ws)) == {"sess-real"}


@pytest.mark.asyncio
async def test_ws_sessions_ignores_temporary_session_without_explicit_id():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    ws = _FakeWebSocket()
    seen = []

    channel.on_message(lambda msg: seen.append(msg))

    await channel._handle_raw_message(
        ws,
        _req(req_id="req-config", method="config.get", params={}),
        {},
    )

    assert id(ws) not in channel._ws_sessions
    assert len(seen) == 1
    assert seen[0].session_id.startswith("sess_")


@pytest.mark.asyncio
async def test_ws_sessions_does_not_accumulate_temp_ids_across_requests():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    ws = _FakeWebSocket()
    channel.on_message(lambda msg: None)

    await channel._handle_raw_message(
        ws,
        _req(
            req_id="req-1",
            method="chat.send",
            params={"session_id": "sess-a", "content": "a"},
        ),
        {},
    )
    for i in range(5):
        await channel._handle_raw_message(
            ws,
            _req(req_id=f"req-poll-{i}", method="skills.list", params={}),
            {},
        )
    await channel._handle_raw_message(
        ws,
        _req(
            req_id="req-2",
            method="chat.send",
            params={"session_id": "sess-b", "content": "b"},
        ),
        {},
    )
    await channel._handle_raw_message(
        ws,
        _req(req_id="req-history", method="history.get", params={}),
        {},
    )

    assert channel._ws_sessions.get(id(ws)) == {"sess-a", "sess-b"}


@pytest.mark.asyncio
async def test_ws_sessions_ignores_empty_string_session_id():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    ws = _FakeWebSocket()
    channel.on_message(lambda msg: None)

    await channel._handle_raw_message(
        ws,
        _req(
            req_id="req-empty-sid",
            method="config.get",
            params={"session_id": ""},
        ),
        {},
    )

    assert id(ws) not in channel._ws_sessions


@pytest.mark.asyncio
async def test_stop_closes_streaming_owner_before_bounded_diagnostics() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    calls: list[str] = []

    class _StreamingOwner:
        async def close(self) -> None:
            calls.append("streaming_owner")

    class _MediaRegistry:
        async def close_media_leaf_cleanup(self) -> bool:
            calls.append("media_tasks")
            return True

        def close_streaming_diagnostics(self) -> bool:
            calls.append("streaming_diagnostics")
            return True

    channel.live_voice_streaming_synthesis_owner = _StreamingOwner()
    channel.live_voice_media_registry = _MediaRegistry()

    await channel.stop()

    # F16: 媒体叶子先唤醒并有界 join,之后才轮到 Provider 与诊断。
    assert calls == ["media_tasks", "streaming_owner", "streaming_diagnostics"]
    assert channel.live_voice_streaming_synthesis_owner is None


@pytest.mark.asyncio
async def test_stop_fails_truthfully_when_media_task_cleanup_is_incomplete() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    calls: list[str] = []

    from types import SimpleNamespace

    class _MediaRegistry:
        async def close_media_leaf_cleanup(self) -> bool:
            calls.append("media_tasks")
            return False

        def close_streaming_diagnostics(self) -> bool:
            calls.append("streaming_diagnostics")
            return True

        @property
        def media_leaf_cleanup_snapshot(self) -> SimpleNamespace:
            # F16: 完成度由所有唤醒动作之后的最终快照裁定。
            return SimpleNamespace(cleanup_complete=False)

    channel.live_voice_media_registry = _MediaRegistry()

    with pytest.raises(RuntimeError, match="media task cleanup is incomplete"):
        await channel.stop()

    assert calls == ["media_tasks", "streaming_diagnostics"]


@pytest.mark.asyncio
async def test_stop_closes_both_streaming_directions_before_diagnostics() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    calls: list[str] = []

    class _Owner:
        def __init__(self, name: str) -> None:
            self.name = name

        async def close(self) -> None:
            calls.append(self.name)

    class _MediaRegistry:
        def close_streaming_observability(self) -> None:
            calls.append("stt_diagnostics")

        def close_streaming_diagnostics(self) -> bool:
            calls.append("tts_diagnostics")
            return True

    channel.live_voice_streaming_synthesis_owner = _Owner("tts_owner")
    channel.live_voice_streaming_speech_owner = _Owner("stt_owner")
    batch = _Owner("batch_owner")
    channel.live_voice_owned_speech_service = batch
    channel.live_voice_speech_service = batch
    channel.live_voice_media_registry = _MediaRegistry()

    await channel.stop()

    assert calls == [
        "tts_owner",
        "stt_owner",
        "batch_owner",
        "stt_diagnostics",
        "tts_diagnostics",
    ]
    assert channel.live_voice_streaming_synthesis_owner is None
    assert channel.live_voice_streaming_speech_owner is None
    assert channel.live_voice_owned_speech_service is None
    assert channel.live_voice_speech_service is None


@pytest.mark.asyncio
async def test_stop_retains_first_failure_but_attempts_every_cleanup_owner() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    calls: list[str] = []

    class _FailingStreamingOwner:
        async def close(self) -> None:
            calls.append("streaming_owner")
            raise RuntimeError("streaming owner close failed")

    class _MediaRegistry:
        def close_streaming_diagnostics(self) -> bool:
            calls.append("streaming_diagnostics")
            raise RuntimeError("diagnostic close failed")

    class _FailingClient:
        async def close(self, *, code: int, reason: str) -> None:
            assert (code, reason) == (1001, "server shutdown")
            calls.append("client")
            raise RuntimeError("client close failed")

    class _Server:
        def close(self) -> None:
            calls.append("server_close")
            raise RuntimeError("server close failed")

        async def wait_closed(self) -> None:
            calls.append("server_wait_closed")
            raise RuntimeError("server wait-closed failed")

    async def failing_writer_cleanup() -> None:
        calls.append("writers")
        raise RuntimeError("writer cleanup failed")

    channel.live_voice_streaming_synthesis_owner = _FailingStreamingOwner()
    channel.live_voice_media_registry = _MediaRegistry()
    channel._clients_by_key[object()] = [_FailingClient()]  # type: ignore[index]
    server = _Server()
    channel._server = server
    channel._shutdown_all_writers = failing_writer_cleanup  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="streaming owner close failed"):
        await channel.stop()

    assert calls == [
        "streaming_owner",
        "streaming_diagnostics",
        "client",
        "server_close",
        "server_wait_closed",
        "writers",
    ]
    assert channel.live_voice_streaming_synthesis_owner is None
    assert channel._clients_by_key == {}
    assert channel._server is server


@pytest.mark.asyncio
async def test_stop_finishes_cleanup_before_rethrowing_process_control() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    calls: list[str] = []

    class _CancelledStreamingOwner:
        async def close(self) -> None:
            calls.append("streaming_owner")
            raise asyncio.CancelledError

    class _MediaRegistry:
        def close_streaming_diagnostics(self) -> bool:
            calls.append("streaming_diagnostics")
            return True

    class _Client:
        async def close(self, *, code: int, reason: str) -> None:
            assert (code, reason) == (1001, "server shutdown")
            calls.append("client")

    async def close_writers() -> None:
        calls.append("writers")

    channel.live_voice_streaming_synthesis_owner = _CancelledStreamingOwner()
    channel.live_voice_media_registry = _MediaRegistry()
    channel._clients_by_key[object()] = [_Client()]  # type: ignore[index]
    channel._shutdown_all_writers = close_writers  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await channel.stop()

    assert calls == [
        "streaming_owner",
        "streaming_diagnostics",
        "client",
        "writers",
    ]
    assert channel.live_voice_streaming_synthesis_owner is None
    assert channel._clients_by_key == {}
