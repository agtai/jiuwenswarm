# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import json

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.gateway.channel_manager.web.app_web_handlers import (
    _FORWARD_NO_LOCAL_HANDLER_METHODS,
    _FORWARD_REQ_METHODS,
)
from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
from jiuwenswarm.server.live_voice import p3_authenticated_composition as p3_module
from jiuwenswarm.server.live_voice.p3_authenticated_composition import P3RouteResult


class _WebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


class _Composition:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def handle(self, **kwargs):
        self.calls.append(kwargs)
        return P3RouteResult(True, {"ok": True, "result": {"task_id": "task-1"}})


class _LifecycleComposition:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("startup reconcile failed")

    async def stop(self) -> None:
        self.stop_calls += 1


def _server(composition) -> AgentWebSocketServer:
    server = object.__new__(AgentWebSocketServer)
    server._live_voice_p3_composition = composition
    return server


@pytest.mark.asyncio
async def test_formal_route_passes_only_rpc_context_to_composition() -> None:
    composition = _Composition()
    server = _server(composition)
    ws = _WebSocket()
    request = AgentRequest(
        request_id="request-1",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.LIVE_VOICE_TASK_CREATE,
        params={
            "auth_token": "opaque",
            "session_id": "session-1",
            "mode": "agent",
            "agent_type": "default",
            "agent_ref": {"mode": "agent", "id": "default"},
        },
    )

    await server._handle_live_voice_p3_request(ws, request, asyncio.Lock())

    assert composition.calls == [
        {
            "operation": "task.create",
            "params": {"auth_token": "opaque", "session_id": "session-1"},
            "request_id": "request-1",
            "session_id": "session-1",
        }
    ]
    wire = json.loads(ws.sent[0])
    assert wire["status"] == "succeeded"
    assert wire["body"]["result"]["result"]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_formal_route_is_fail_closed_when_composition_is_not_ready() -> None:
    server = _server(None)
    ws = _WebSocket()
    request = AgentRequest(
        request_id="request-disabled",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.LIVE_VOICE_TASK_LIST,
        params={"auth_token": "opaque", "session_id": "session-1"},
    )

    await server._handle_live_voice_p3_request(ws, request, asyncio.Lock())

    wire = json.loads(ws.sent[0])
    assert wire["status"] == "failed"
    assert wire["body"]["details"]["error"] == {
        "code": "UNAVAILABLE",
        "reason": "FORMAL_TASK_ROUTE_DISABLED",
        "message": "formal task route is unavailable",
    }


def test_all_formal_methods_have_req_method_values() -> None:
    methods = {
        method.value
        for method in ReqMethod
        if method.value.startswith("live_voice.task.")
    }
    assert methods == {
        "live_voice.task.create",
        "live_voice.task.get",
        "live_voice.task.list",
        "live_voice.task.status",
        "live_voice.task.cancel",
        "live_voice.task.events",
    }
    assert methods <= _FORWARD_REQ_METHODS
    assert methods <= _FORWARD_NO_LOCAL_HANDLER_METHODS


@pytest.mark.asyncio
async def test_agentserver_owns_formal_composition_start_and_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition = _LifecycleComposition()
    server = _server(None)
    server._agent_manager = object()
    monkeypatch.setattr(
        p3_module,
        "create_p3_composition_from_environment",
        lambda **_kwargs: composition,
    )

    await server._start_live_voice_p3_composition()
    await server._stop_live_voice_p3_composition()
    await server._stop_live_voice_p3_composition()

    assert composition.start_calls == 1
    assert composition.stop_calls == 1
    assert server._live_voice_p3_composition is None


@pytest.mark.asyncio
async def test_agentserver_cleans_failed_formal_composition_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition = _LifecycleComposition(fail_start=True)
    server = _server(None)
    server._agent_manager = object()
    monkeypatch.setattr(
        p3_module,
        "create_p3_composition_from_environment",
        lambda **_kwargs: composition,
    )

    await server._start_live_voice_p3_composition()

    assert composition.start_calls == 1
    assert composition.stop_calls == 1
    assert server._live_voice_p3_composition is None
