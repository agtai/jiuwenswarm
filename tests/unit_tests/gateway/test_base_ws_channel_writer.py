"""Writer-loop serialization keeps every emitted frame strict-JSON parseable."""

from __future__ import annotations

import asyncio
import json

import pytest

from jiuwenswarm.gateway.routing.base_ws_channel import BaseWsChannel


class _FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


def _strict_json_loads(payload: str):
    def _reject_constant(name: str):
        raise ValueError(f"non-finite JSON token: {name}")

    return json.loads(payload, parse_constant=_reject_constant)


class _WriterChannel(BaseWsChannel):
    """Concrete writer harness: only the inherited _writer_loop is under test."""

    def __init__(self) -> None:
        self.channel_id = "test-ws"
        self._send_queues = {}

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    def _serialize_frame(self, msg, routing_target, member_names=None):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_writer_drops_non_finite_frames_and_keeps_serving() -> None:
    channel = _WriterChannel()
    queue: asyncio.Queue = asyncio.Queue()
    channel._send_queues = {"ws1": queue}
    ws = _FakeWs()
    await queue.put({"id": "bad", "value": float("nan")})
    await queue.put({"id": "good", "value": 1.5})
    await queue.put(None)

    await channel._writer_loop(ws, "ws1")

    assert len(ws.sent) == 1
    assert _strict_json_loads(ws.sent[0]) == {"id": "good", "value": 1.5}
