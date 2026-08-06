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
from jiuwenswarm.server.live_voice import product_composition_registry as product_module
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


class _ProductRegistry:
    def __init__(
        self, *, p3_text_enabled: bool = True, stop_failures: int = 0
    ) -> None:
        self.p2_enabled = True
        self.p3_text_enabled = p3_text_enabled
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.stop_calls = 0
        self.stop_failures = stop_failures

    async def handle_p3_query(self, **kwargs):
        self.calls.append(("query", kwargs))
        return P3RouteResult(
            True,
            {"ok": True, "result": {"task_id": "task-central"}},
        )

    async def handle_p2_activate(self, **kwargs):
        self.calls.append(("p2.activate", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"active": True}})

    async def handle_p2_close(self, **kwargs):
        self.calls.append(("p2.close", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"closed": True}})

    async def handle_p3_progress_activate(self, **kwargs):
        self.calls.append(("progress.activate", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"active": True}})

    async def handle_p3_progress_close(self, **kwargs):
        self.calls.append(("progress.close", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"closed": True}})

    async def handle_p3_progress_ack(self, **kwargs):
        self.calls.append(("progress.ack", kwargs))
        return P3RouteResult(
            True, {"ok": True, "result": {"status": "acknowledged"}}
        )

    async def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_failures:
            self.stop_failures -= 1
            raise RuntimeError("injected product cleanup failure")


def _server(composition) -> AgentWebSocketServer:
    server = object.__new__(AgentWebSocketServer)
    server._live_voice_p3_composition = composition
    server._live_voice_product_composition = None
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


def test_all_product_composition_methods_are_forwarded_without_local_handlers() -> None:
    methods = {
        method.value
        for method in ReqMethod
        if method.value.startswith("live_voice.composition.")
    }
    assert methods == {
        "live_voice.composition.p2.activate",
        "live_voice.composition.p2.close",
        "live_voice.composition.p3.progress.activate",
        "live_voice.composition.p3.progress.close",
        "live_voice.composition.p3.progress.ack",
    }
    assert methods <= _FORWARD_REQ_METHODS
    assert methods <= _FORWARD_NO_LOCAL_HANDLER_METHODS


@pytest.mark.asyncio
async def test_product_master_flag_off_does_not_invoke_registry_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    server = _server(object())
    server._agent_manager = object()
    monkeypatch.delenv(product_module.PRODUCT_COMPOSITION_ENABLE_ENV, raising=False)
    monkeypatch.setattr(
        product_module,
        "create_product_composition_registry_from_environment",
        lambda **kwargs: calls.append(kwargs),
    )

    await server._start_live_voice_product_composition()

    assert calls == []
    assert server._live_voice_product_composition is None


@pytest.mark.asyncio
async def test_agentserver_owns_enabled_product_registry_start_and_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _ProductRegistry()
    server = _server(object())
    server._agent_manager = object()
    monkeypatch.setenv(product_module.PRODUCT_COMPOSITION_ENABLE_ENV, "1")
    monkeypatch.setattr(
        product_module,
        "create_product_composition_registry_from_environment",
        lambda **_kwargs: registry,
    )

    await server._start_live_voice_product_composition()
    await server._stop_live_voice_product_composition()
    await server._stop_live_voice_product_composition()

    assert registry.stop_calls == 1
    assert server._live_voice_product_composition is None


@pytest.mark.asyncio
async def test_agentserver_retains_failed_product_cleanup_owner_for_retry() -> None:
    registry = _ProductRegistry(stop_failures=1)
    server = _server(object())
    server._live_voice_product_composition = registry

    await server._stop_live_voice_product_composition()

    assert server._live_voice_product_composition is registry
    await server._stop_live_voice_product_composition()

    assert registry.stop_calls == 2
    assert server._live_voice_product_composition is None


@pytest.mark.asyncio
async def test_agentserver_defers_p3_owner_stop_until_product_cleanup_succeeds() -> None:
    registry = _ProductRegistry(stop_failures=1)
    composition = _LifecycleComposition()
    server = _server(composition)
    server._live_voice_product_composition = registry
    server._server = None
    server._checkpointer_warmup_task = None

    await server.stop()

    assert registry.stop_calls == 1
    assert composition.stop_calls == 0
    assert server._live_voice_p3_composition is composition

    await server.stop()

    assert registry.stop_calls == 2
    assert composition.stop_calls == 1
    assert server._live_voice_product_composition is None
    assert server._live_voice_p3_composition is None


@pytest.mark.asyncio
async def test_central_registry_owns_read_only_query_but_not_p3_mutation() -> None:
    composition = _Composition()
    registry = _ProductRegistry()
    server = _server(composition)
    server._live_voice_product_composition = registry
    ws = _WebSocket()

    query = AgentRequest(
        request_id="request-query",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.LIVE_VOICE_TASK_LIST,
        params={
            "auth_token": "opaque",
            "session_id": "session-1",
            "mode": "agent",
        },
    )
    mutation = AgentRequest(
        request_id="request-mutation",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.LIVE_VOICE_TASK_CREATE,
        params={"auth_token": "opaque", "session_id": "session-1"},
    )

    await server._handle_live_voice_p3_request(ws, query, asyncio.Lock())
    await server._handle_live_voice_p3_request(ws, mutation, asyncio.Lock())

    assert registry.calls == [
        (
            "query",
            {
                "operation": "task.list",
                "params": {"auth_token": "opaque", "session_id": "session-1"},
                "request_id": "request-query",
                "session_id": "session-1",
            },
        )
    ]
    assert composition.calls == [
        {
            "operation": "task.create",
            "params": {"auth_token": "opaque", "session_id": "session-1"},
            "request_id": "request-mutation",
            "session_id": "session-1",
        }
    ]


@pytest.mark.asyncio
async def test_product_p2_route_preserves_only_rpc_context() -> None:
    registry = _ProductRegistry()
    server = _server(object())
    server._live_voice_product_composition = registry
    ws = _WebSocket()
    request = AgentRequest(
        request_id="request-p2",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE,
        params={
            "auth_token": "opaque",
            "session_id": "session-1",
            "correlation_id": "correlation-1",
            "mode": "agent",
            "agent_type": "default",
            "agent_ref": {"mode": "agent", "id": "default"},
        },
    )

    await server._handle_live_voice_product_request(ws, request, asyncio.Lock())

    assert registry.calls == [
        (
            "p2.activate",
            {
                "params": {
                    "auth_token": "opaque",
                    "session_id": "session-1",
                    "correlation_id": "correlation-1",
                },
                "request_id": "request-p2",
                "session_id": "session-1",
                "channel_id": "web",
            },
        )
    ]
    assert json.loads(ws.sent[0])["status"] == "succeeded"


@pytest.mark.asyncio
async def test_product_progress_ack_preserves_exact_rpc_context() -> None:
    registry = _ProductRegistry()
    server = _server(object())
    server._live_voice_product_composition = registry
    ws = _WebSocket()
    request = AgentRequest(
        request_id="request-progress-ack",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.LIVE_VOICE_COMPOSITION_P3_PROGRESS_ACK,
        params={
            "auth_token": "opaque",
            "session_id": "session-1",
            "task_id": "task-1",
            "delivery_id": "delivery-1",
            "mode": "agent",
        },
    )

    await server._handle_live_voice_product_request(ws, request, asyncio.Lock())

    assert registry.calls == [
        (
            "progress.ack",
            {
                "params": {
                    "auth_token": "opaque",
                    "session_id": "session-1",
                    "task_id": "task-1",
                    "delivery_id": "delivery-1",
                },
                "request_id": "request-progress-ack",
                "session_id": "session-1",
                "channel_id": "web",
            },
        )
    ]
    assert json.loads(ws.sent[0])["status"] == "succeeded"


@pytest.mark.asyncio
async def test_product_route_is_fail_closed_when_registry_is_disabled() -> None:
    server = _server(object())
    ws = _WebSocket()
    request = AgentRequest(
        request_id="request-product-disabled",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.LIVE_VOICE_COMPOSITION_P3_PROGRESS_ACTIVATE,
        params={},
    )

    await server._handle_live_voice_product_request(ws, request, asyncio.Lock())

    wire = json.loads(ws.sent[0])
    assert wire["status"] == "failed"
    assert wire["body"]["details"]["error"]["reason"] == (
        "PRODUCT_COMPOSITION_DISABLED"
    )


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
