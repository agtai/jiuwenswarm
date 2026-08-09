# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import json
from pathlib import Path

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
from jiuwenswarm.server.live_voice import product_w2_observability as w2_module
from jiuwenswarm.server.live_voice.p3_authenticated_composition import P3RouteResult


class _WebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


class _IterableWebSocket(_WebSocket):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.remote_address = (name, 1)
        self.closed = asyncio.Event()
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self.closed.set()

    async def __aiter__(self):
        await self.closed.wait()
        return
        yield ""  # pragma: no cover - makes this an async generator


class _Composition:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def handle(self, **kwargs):
        self.calls.append(kwargs)
        return P3RouteResult(True, {"ok": True, "result": {"task_id": "task-1"}})


class _Observer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.reconciliation_calls: list[tuple[object, object]] = []
        self.close_calls = 0

    async def observe_route(self, **kwargs: object) -> bool:
        self.calls.append(kwargs)
        return True

    async def observe_reconciliation_event(
        self, event: object, attempt: object
    ) -> bool:
        self.reconciliation_calls.append((event, attempt))
        return True

    async def close(self) -> None:
        self.close_calls += 1


class _LifecycleComposition:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.start_calls = 0
        self.stop_calls = 0
        self.mutation_authority_ready = False

    async def start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("startup reconcile failed")

    async def stop(self) -> None:
        self.stop_calls += 1


class _ProductRegistry:
    def __init__(self, *, p3_text_enabled: bool = True, stop_failures: int = 0) -> None:
        self.p2_enabled = True
        self.p3_text_enabled = p3_text_enabled
        self.p3_mutation_enabled = True
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

    async def handle_p2_submit(self, **kwargs):
        self.calls.append(("p2.submit", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"accepted": True}})

    async def handle_p2_notification_next(self, **kwargs):
        self.calls.append(("p2.notification.next", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"kind": "agent.output"}})

    async def handle_p2_presentation_ack(self, **kwargs):
        self.calls.append(("p2.presentation.ack", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"accepted": True}})

    async def handle_p2_barge_in(self, **kwargs):
        self.calls.append(("p2.barge_in", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"applied": True}})

    async def handle_p3_confirmation_issue(self, **kwargs):
        self.calls.append(("p3.confirmation.issue", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"issued": True}})

    async def handle_p3_mutation(self, **kwargs):
        self.calls.append(("p3.mutate", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"accepted": True}})

    async def handle_p3_progress_activate(self, **kwargs):
        self.calls.append(("progress.activate", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"active": True}})

    async def handle_p3_progress_close(self, **kwargs):
        self.calls.append(("progress.close", kwargs))
        return P3RouteResult(True, {"ok": True, "result": {"closed": True}})

    async def handle_p3_progress_ack(self, **kwargs):
        self.calls.append(("progress.ack", kwargs))
        return P3RouteResult(
            True,
            {
                "ok": True,
                "result": {
                    "status": "acknowledged",
                    "acknowledgement": "web_ui_text_consumed",
                    "task_id": kwargs["params"].get("task_id"),
                    "attempt_id": "attempt-1",
                    "correlation_id": kwargs["params"].get("correlation_id"),
                },
            },
        )

    async def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_failures:
            self.stop_failures -= 1
            raise RuntimeError("injected product cleanup failure")


class _QueuedQueryRegistry(_ProductRegistry):
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        super().__init__()
        self._payloads = list(payloads)

    async def handle_p3_query(self, **kwargs):
        self.calls.append(("query", kwargs))
        return P3RouteResult(True, self._payloads.pop(0))


class _StaleMutationRegistry(_ProductRegistry):
    async def handle_p3_mutation(self, **kwargs):
        self.calls.append(("p3.mutate", kwargs))
        return P3RouteResult(
            False,
            {
                "request_id": kwargs["request_id"],
                "ok": False,
                "result": None,
                "error": {
                    "code": "STALE",
                    "reason": "PRODUCT_W2_STALE_FAULT_INJECTED",
                    "message": "the externally frozen W2 plan injected a stale retry fault",
                },
            },
        )


class _ConnectionCleanupRegistry:
    def __init__(self) -> None:
        self.calls = 0
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()

    async def close_active_routes(self) -> None:
        self.calls += 1
        if self.calls == 1:
            self.first_started.set()
            await self.release_first.wait()


class _ConnectionAgentManager:
    def __init__(self) -> None:
        self.cancel_calls = 0

    async def cancel_all_inflight_work(self, **_kwargs: object) -> None:
        self.cancel_calls += 1


def _server(composition) -> AgentWebSocketServer:
    server = object.__new__(AgentWebSocketServer)
    server._live_voice_p3_composition = composition
    server._live_voice_product_composition = None
    return server


@pytest.mark.asyncio
async def test_gateway_replacement_waits_for_old_cleanup_before_becoming_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = object.__new__(AgentWebSocketServer)
    registry = _ConnectionCleanupRegistry()
    manager = _ConnectionAgentManager()
    server._gateway_connection_lifecycle_lock = asyncio.Lock()
    server._gateway_connection_generation = 0
    server._current_ws = None
    server._current_send_lock = None
    server._current_ws_done = None
    server._live_voice_product_composition = registry
    server._agent_manager = manager
    server._session_stream_tasks = {}
    server._ping_interval = 20
    server._ping_timeout = 20
    server._clear_ws_acp_client_capabilities = lambda _ws: None

    async def stop_scheduler() -> None:
        return None

    async def cancel_team(**_kwargs: object) -> None:
        return None

    server._stop_scheduler = stop_scheduler
    monkeypatch.setattr(
        "jiuwenswarm.agents.harness.team.cancel_all_team_stream_tasks_across_managers",
        cancel_team,
    )
    old_ws = _IterableWebSocket("old")
    new_ws = _IterableWebSocket("new")

    old_handler = asyncio.create_task(server._connection_handler(old_ws))
    for _ in range(20):
        if server._current_ws is old_ws:
            break
        await asyncio.sleep(0)
    replacement = asyncio.create_task(server._connection_handler(new_ws))
    await asyncio.wait_for(registry.first_started.wait(), timeout=1)

    assert old_ws.close_calls == 1
    assert server._current_ws is old_ws
    assert new_ws.sent == []
    assert replacement.done() is False

    registry.release_first.set()
    for _ in range(20):
        if server._current_ws is new_ws:
            break
        await asyncio.sleep(0)

    assert server._current_ws is new_ws
    assert len(new_ws.sent) == 1
    assert json.loads(new_ws.sent[0])["event"] == "connection.ack"
    assert old_handler.done() is True
    assert registry.calls == 1

    await new_ws.close()
    await asyncio.wait_for(replacement, timeout=1)
    assert server._current_ws is None
    assert registry.calls == 2


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
async def test_formal_query_observation_uses_authoritative_task_correlation() -> None:
    def event(
        *,
        event_id: str,
        seq: int,
        state: str,
        correlation_id: str,
        task_id: str = "task-1",
    ) -> dict[str, object]:
        return {
            "event_id": event_id,
            "task_id": task_id,
            "attempt_id": "attempt-1",
            "seq": seq,
            "state": state,
            "outcome": "completed" if state == "terminal" else None,
            "correlation_id": correlation_id,
            "occurred_at": f"2026-08-09T16:0{seq}:00Z",
        }

    registry = _QueuedQueryRegistry(
        [
            {
                "ok": True,
                "result": {
                    "task_id": "task-1",
                    "events": [
                        {
                            "task_id": "task-1",
                            "attempt_id": "attempt-1",
                            "correlation_id": "correlation-malformed",
                        }
                    ],
                },
            },
            {
                "ok": True,
                "result": {
                    "task_id": "task-1",
                    "events": [
                        event(
                            event_id="event-conflict-1",
                            seq=1,
                            state="running",
                            correlation_id="correlation-foreign",
                        ),
                        event(
                            event_id="event-conflict-2",
                            seq=2,
                            state="running",
                            correlation_id="correlation-other",
                        ),
                    ],
                },
            },
            {
                "ok": True,
                "result": {
                    "task_id": "task-foreign",
                    "events": [
                        event(
                            event_id="event-foreign-target",
                            seq=2,
                            state="running",
                            correlation_id="correlation-foreign-target",
                            task_id="task-foreign",
                        )
                    ],
                },
            },
            {
                "ok": True,
                "result": {
                    "task_id": "task-1",
                    "events": [
                        event(
                            event_id="event-running",
                            seq=3,
                            state="running",
                            correlation_id="correlation-task",
                        )
                    ],
                },
            },
            {
                "ok": True,
                "result": {
                    "task_id": "task-1",
                    "events": [
                        event(
                            event_id="event-terminal",
                            seq=4,
                            state="terminal",
                            correlation_id="correlation-task",
                        )
                    ],
                },
            },
        ]
    )
    observer = _Observer()
    server = _server(object())
    server._live_voice_product_composition = registry
    server._live_voice_w2_observability = observer
    ws = _WebSocket()

    for request_id in (
        "transport-events-malformed",
        "transport-events-conflict",
        "transport-events-foreign-target",
        "transport-events-running",
        "transport-events-terminal",
    ):
        await server._handle_live_voice_p3_request(
            ws,
            AgentRequest(
                request_id=request_id,
                channel_id="web",
                session_id="session-1",
                req_method=ReqMethod.LIVE_VOICE_TASK_EVENTS,
                params={"task_id": "task-1", "after_seq": -1},
            ),
            asyncio.Lock(),
        )

    assert [call["request_id"] for call in observer.calls] == [
        "transport-events-running",
        "transport-events-terminal",
    ]
    assert [call["correlation_id"] for call in observer.calls] == [
        "correlation-task",
        "correlation-task",
    ]
    assert all(call["task_id"] == "task-1" for call in observer.calls)
    assert all(call["attempt_id"] == "attempt-1" for call in observer.calls)
    assert [call["task_event_facts"][0]["state"] for call in observer.calls] == [
        "running",
        "terminal",
    ]


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
        "live_voice.composition.p2.submit",
        "live_voice.composition.p2.notification.next",
        "live_voice.composition.p2.presentation.ack",
        "live_voice.composition.p2.barge_in",
        "live_voice.composition.p3.confirmation.issue",
        "live_voice.composition.p3.mutate",
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
    captured: list[dict[str, object]] = []
    commit_ledger = object()
    server = _server(object())
    server._agent_manager = object()
    server._live_voice_turn_commit_ledger = commit_ledger
    monkeypatch.setenv(product_module.PRODUCT_COMPOSITION_ENABLE_ENV, "1")
    monkeypatch.setattr(
        product_module,
        "create_product_composition_registry_from_environment",
        lambda **kwargs: captured.append(kwargs) or registry,
    )

    await server._start_live_voice_product_composition()
    await server._stop_live_voice_product_composition()
    await server._stop_live_voice_product_composition()

    assert registry.stop_calls == 1
    assert server._live_voice_product_composition is None
    assert captured[0]["commit_ledger"] is commit_ledger


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
async def test_agentserver_defers_p3_owner_stop_until_product_cleanup_succeeds() -> (
    None
):
    order: list[str] = []

    class OrderedRegistry(_ProductRegistry):
        async def stop(self) -> None:
            await super().stop()
            order.append("product")

    class OrderedComposition(_LifecycleComposition):
        async def stop(self) -> None:
            order.append("p3")
            await super().stop()

    class OrderedObserver(_Observer):
        async def close(self) -> None:
            order.append("evidence")
            await super().close()

    registry = OrderedRegistry(stop_failures=1)
    composition = OrderedComposition()
    observer = OrderedObserver()
    server = _server(composition)
    server._live_voice_product_composition = registry
    server._live_voice_w2_observability = observer
    server._server = None
    server._checkpointer_warmup_task = None

    await server.stop()

    assert registry.stop_calls == 1
    assert composition.stop_calls == 0
    assert observer.close_calls == 0
    assert server._live_voice_p3_composition is composition
    assert server._live_voice_w2_observability is observer
    assert order == []

    await server.stop()

    assert registry.stop_calls == 2
    assert composition.stop_calls == 1
    assert observer.close_calls == 1
    assert server._live_voice_product_composition is None
    assert server._live_voice_p3_composition is None
    assert server._live_voice_w2_observability is None
    assert order == ["product", "p3", "evidence"]


@pytest.mark.asyncio
async def test_central_registry_owns_read_only_query_but_not_p3_mutation() -> None:
    composition = _Composition()
    registry = _ProductRegistry()
    server = _server(composition)
    server._live_voice_product_composition = registry
    observer = _Observer()
    server._live_voice_w2_observability = observer
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
    # The central registry owns the business query, but this synthetic result
    # does not carry an authority-owned Task correlation.  Transport identity
    # must not be promoted into cumulative W2 evidence.
    assert observer.calls == []


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
@pytest.mark.parametrize(
    ("method", "label", "includes_channel"),
    [
        (ReqMethod.LIVE_VOICE_COMPOSITION_P2_SUBMIT, "p2.submit", True),
        (
            ReqMethod.LIVE_VOICE_COMPOSITION_P2_NOTIFICATION_NEXT,
            "p2.notification.next",
            False,
        ),
        (
            ReqMethod.LIVE_VOICE_COMPOSITION_P2_PRESENTATION_ACK,
            "p2.presentation.ack",
            False,
        ),
        (
            ReqMethod.LIVE_VOICE_COMPOSITION_P2_BARGE_IN,
            "p2.barge_in",
            False,
        ),
        (
            ReqMethod.LIVE_VOICE_COMPOSITION_P3_CONFIRMATION_ISSUE,
            "p3.confirmation.issue",
            False,
        ),
        (ReqMethod.LIVE_VOICE_COMPOSITION_P3_MUTATE, "p3.mutate", False),
    ],
)
async def test_product_business_methods_dispatch_only_exact_rpc_context(
    method: ReqMethod,
    label: str,
    includes_channel: bool,
) -> None:
    registry = _ProductRegistry()
    server = _server(object())
    server._live_voice_product_composition = registry
    ws = _WebSocket()
    request = AgentRequest(
        request_id="request-business",
        channel_id="web",
        session_id="session-1",
        req_method=method,
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

    expected = {
        "params": {
            "auth_token": "opaque",
            "session_id": "session-1",
            "correlation_id": "correlation-1",
        },
        "request_id": "request-business",
        "session_id": "session-1",
    }
    if includes_channel:
        expected["channel_id"] = "web"
    assert registry.calls == [(label, expected)]
    assert json.loads(ws.sent[0])["status"] == "succeeded"


@pytest.mark.asyncio
async def test_product_progress_ack_preserves_exact_rpc_context() -> None:
    registry = _ProductRegistry()
    server = _server(object())
    server._live_voice_product_composition = registry
    observer = _Observer()
    server._live_voice_w2_observability = observer
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
            "correlation_id": "correlation-task",
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
                    "correlation_id": "correlation-task",
                    "delivery_id": "delivery-1",
                },
                "request_id": "request-progress-ack",
                "session_id": "session-1",
                "channel_id": "web",
            },
        )
    ]
    assert json.loads(ws.sent[0])["status"] == "succeeded"
    assert len(observer.calls) == 1
    assert observer.calls[0]["operation"] == (
        "live_voice.composition.p3.progress.ack"
    )
    assert observer.calls[0]["task_id"] == "task-1"
    assert observer.calls[0]["attempt_id"] == "attempt-1"
    assert observer.calls[0]["correlation_id"] == "correlation-task"
    assert observer.calls[0]["result_ok"] is True


@pytest.mark.asyncio
async def test_product_retry_stale_fault_projects_one_failed_task_observation() -> None:
    registry = _StaleMutationRegistry()
    server = _server(object())
    server._live_voice_product_composition = registry
    observer = _Observer()
    server._live_voice_w2_observability = observer
    ws = _WebSocket()
    request = AgentRequest(
        request_id="request-retry-stale-fault",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.LIVE_VOICE_COMPOSITION_P3_MUTATE,
        params={
            "auth_token": "opaque",
            "session_id": "session-1",
            "operation": "task.retry",
            "command_id": "command-retry-stale-fault",
            "confirmation_id": "confirmation-retry-stale-fault",
            "issued_at": "2030-01-01T00:00:00Z",
            "correlation_id": "correlation-retry-stale-fault",
            "task_id": "task-1",
        },
    )

    await server._handle_live_voice_product_request(ws, request, asyncio.Lock())

    assert len(observer.calls) == 1
    projected = observer.calls[0]
    assert projected["operation"] == "live_voice.composition.p3.mutate"
    assert projected["task_operation"] == "task.retry"
    assert projected["task_id"] == "task-1"
    assert projected["correlation_id"] == "correlation-retry-stale-fault"
    assert projected["result_ok"] is False
    assert projected["error_code"] == "STALE"
    assert json.loads(ws.sent[0])["status"] == "failed"


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
    captured: list[dict[str, object]] = []
    server = _server(None)
    server._agent_manager = object()
    monkeypatch.delenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED", raising=False
    )
    monkeypatch.setattr(
        p3_module,
        "create_p3_composition_from_environment",
        lambda **kwargs: captured.append(kwargs) or composition,
    )

    await server._start_live_voice_p3_composition()
    await server._stop_live_voice_p3_composition()
    await server._stop_live_voice_p3_composition()

    assert composition.start_calls == 1
    assert composition.stop_calls == 1
    assert server._live_voice_p3_composition is None
    assert captured[0]["confirmation_verifier"] is None
    assert captured[0]["commit_ledger"] is not None
    assert callable(captured[0]["reconciliation_event_sink"])
    assert server._live_voice_p3_confirmation_owner is None
    assert server._live_voice_p3_confirmation_forwarder is None
    assert server._live_voice_turn_commit_ledger is None


@pytest.mark.asyncio
async def test_w2_owner_is_ready_before_p3_startup_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    captured: list[dict[str, object]] = []
    observer = _Observer()

    class Composition(_LifecycleComposition):
        async def start(self) -> None:
            assert server._live_voice_w2_observability is observer
            order.append("p3")
            await super().start()

    composition = Composition()
    server = _server(None)
    server._agent_manager = object()
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED", "1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_ENABLED", "1")
    monkeypatch.setattr(
        w2_module,
        "create_product_w2_observability_owner_from_environment",
        lambda: order.append("w2") or observer,
    )
    monkeypatch.setattr(
        p3_module,
        "create_p3_composition_from_environment",
        lambda **kwargs: captured.append(kwargs) or composition,
    )

    await server._start_live_voice_w2_observability()
    await server._start_live_voice_p3_composition()
    sink = captured[0]["reconciliation_event_sink"]
    assert callable(sink)
    await sink("event", "attempt")

    assert order == ["w2", "p3"]
    assert observer.reconciliation_calls == [("event", "attempt")]
    await server._stop_live_voice_p3_composition()


@pytest.mark.asyncio
async def test_agentserver_allocates_product_confirmation_owner_only_when_all_flags_on(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    composition = _LifecycleComposition()
    composition.mutation_authority_ready = True
    captured: list[dict[str, object]] = []
    server = _server(None)
    server._agent_manager = object()
    for name in (
        "JIUWENSWARM_LIVE_VOICE_P3_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setattr(
        p3_module,
        "resolve_p3_database_path_from_environment",
        lambda: tmp_path / "formal_tasks.sqlite3",
    )
    monkeypatch.setattr(
        p3_module,
        "create_p3_composition_from_environment",
        lambda **kwargs: captured.append(kwargs) or composition,
    )

    await server._start_live_voice_p3_composition()

    assert server._live_voice_p3_confirmation_owner is not None
    assert server._live_voice_p3_confirmation_forwarder is not None
    assert captured[0]["confirmation_verifier"] is (
        server._live_voice_p3_confirmation_forwarder
    )
    await server._stop_live_voice_p3_composition()
    assert server._live_voice_p3_confirmation_owner is None
    assert server._live_voice_p3_confirmation_forwarder is None


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
