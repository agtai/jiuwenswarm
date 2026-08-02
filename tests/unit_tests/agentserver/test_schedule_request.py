from __future__ import annotations

import asyncio
import json

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server import agent_ws_server as agent_ws_server_module
from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))


class _ScheduleServerHarness(AgentWebSocketServer):
    async def handle_schedule_request_for_test(
        self,
        ws: _FakeWebSocket,
        request: AgentRequest,
        send_lock: asyncio.Lock,
        action: str,
    ) -> None:
        await self._handle_schedule_request(ws, request, send_lock, action)

    def _resolve_model(self, _model_name=None):
        return None


class _FailIfAskedForAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def get_agent(self, **_kwargs):
        self.calls += 1
        raise AssertionError("schedule cleanup must not acquire an Agent")


class _ScheduleService:
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.deleted: list[str] = []
        self.cancel_kwargs: list[dict] = []
        self.status_kwargs: list[dict] = []
        self.delete_kwargs: list[dict] = []
        self.logs_calls: list[dict] = []

    async def cancel_scheduled_task(self, task_id: str, **kwargs) -> dict[str, str]:
        self.cancelled.append(task_id)
        self.cancel_kwargs.append(kwargs)
        return {"task_id": task_id, "status": "cancelled"}

    async def get_scheduled_task_status(self, task_id: str, **kwargs) -> dict[str, str]:
        self.status_kwargs.append(kwargs)
        return {"task_id": task_id, "status": "pending"}

    async def delete_scheduled_task(self, task_id: str, **kwargs) -> dict[str, str]:
        self.deleted.append(task_id)
        self.delete_kwargs.append(kwargs)
        return {"task_id": task_id}

    async def get_scheduled_task_logs(
        self,
        task_id: str,
        log_type: str,
        history_index: int,
        offset: int,
        limit: int,
        **kwargs,
    ) -> dict:
        self.logs_calls.append(
            {
                "task_id": task_id,
                "log_type": log_type,
                "history_index": history_index,
                "offset": offset,
                "limit": limit,
                **kwargs,
            }
        )
        return {"logs": []}


class _AgentFacade:
    def __init__(self, instance: object) -> None:
        self.instance = instance

    def get_instance(self) -> object:
        return self.instance


class _ConcurrentAgentManager:
    def __init__(self, agents: dict[str, _AgentFacade]) -> None:
        self.agents = agents
        self.pinned: list[_AgentFacade] = []
        self.unpinned: list[_AgentFacade] = []
        self.get_agent_calls: list[dict] = []

    async def get_agent(self, *, channel_id: str, **kwargs) -> _AgentFacade:
        await asyncio.sleep(0)
        self.get_agent_calls.append({"channel_id": channel_id, **kwargs})
        return self.agents[channel_id]

    def pin_agent(self, agent: _AgentFacade) -> None:
        self.pinned.append(agent)

    def unpin_agent(self, agent: _AgentFacade) -> None:
        self.unpinned.append(agent)


class _ConcurrentRunService:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._both_started = asyncio.Event()

    async def _capture(
        self,
        query,
        model,
        pipeline,
        execution_agent,
        context_release,
        execution_target,
        owner_scope=None,
        origin_namespace=None,
        idempotency_key=None,
        model_intent=None,
    ) -> dict[str, str]:
        self.calls.append(
            {
                "query": query,
                "model": model,
                "pipeline": pipeline,
                "execution_agent": execution_agent,
                "context_release": context_release,
                "execution_target": execution_target,
                "owner_scope": owner_scope,
                "origin_namespace": origin_namespace,
                "idempotency_key": idempotency_key,
                "model_intent": model_intent,
            }
        )
        if len(self.calls) == 2:
            self._both_started.set()
        await self._both_started.wait()
        suffix = "a" if query == "任务 A" else "b"
        return {"task_id": f"sch_{suffix}", "status": "running"}

    async def run_task(
        self,
        query,
        model,
        pipeline,
        *,
        execution_agent,
        context_release,
        execution_target,
        owner_scope=None,
        origin_namespace=None,
        idempotency_key=None,
        model_intent=None,
    ) -> dict[str, str]:
        return await self._capture(
            query,
            model,
            pipeline,
            execution_agent,
            context_release,
            execution_target,
            owner_scope,
            origin_namespace,
            idempotency_key,
            model_intent,
        )

    async def create_scheduled_task(
        self,
        query,
        _interval_hours,
        _run_immediately,
        model,
        pipeline,
        *,
        execution_agent,
        context_release,
        execution_target,
        owner_scope=None,
    ) -> dict[str, str]:
        return await self._capture(
            query,
            model,
            pipeline,
            execution_agent,
            context_release,
            execution_target,
            owner_scope,
        )


class _FailedMutationService:
    def __init__(self, *, raises: bool) -> None:
        self.raises = raises
        self.context_release = None

    async def _result(self, context_release):
        self.context_release = context_release
        if self.raises:
            raise RuntimeError("mutation failed")
        return {"error": "mutation rejected"}

    async def run_task(
        self,
        _query,
        _model,
        _pipeline,
        *,
        execution_agent,
        context_release,
        execution_target,
        owner_scope=None,
        origin_namespace=None,
        idempotency_key=None,
        model_intent=None,
    ):
        assert execution_agent is not None
        assert execution_target is not None
        return await self._result(context_release)

    async def create_scheduled_task(
        self,
        _query,
        _interval_hours,
        _run_immediately,
        _model,
        _pipeline,
        *,
        execution_agent,
        context_release,
        execution_target,
        owner_scope=None,
    ):
        assert execution_agent is not None
        assert execution_target is not None
        return await self._result(context_release)


class _OwnerScopeService:
    def __init__(self) -> None:
        self.run_kwargs: dict | None = None
        self.list_kwargs: dict | None = None

    async def run_task(
        self,
        _query,
        _model,
        _pipeline,
        **kwargs,
    ) -> dict[str, str]:
        self.run_kwargs = kwargs
        return {"task_id": "sch_scoped", "status": "running"}

    async def list_scheduled_tasks(self, **kwargs) -> list[dict]:
        self.list_kwargs = kwargs
        return []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "run"])
@pytest.mark.parametrize("raises", [False, True])
async def test_schedule_mutation_failure_releases_agent_pin_once(
    monkeypatch,
    action: str,
    raises: bool,
) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    facade = _AgentFacade(object())
    manager = _ConcurrentAgentManager({"web": facade})
    service = _FailedMutationService(raises=raises)
    server._agent_manager = manager
    server._scheduler_service = service
    monkeypatch.setattr(
        agent_ws_server_module,
        "encode_agent_response_for_wire",
        lambda response, response_id: {
            "type": "res",
            "id": response_id,
            "ok": response.ok,
            "payload": response.payload,
        },
    )
    ws = _FakeWebSocket()
    request = AgentRequest(
        request_id=f"req-{action}-{raises}",
        channel_id="web",
        session_id="session",
        params={
            "mode": "auto_harness",
            "query": "受控任务",
            "interval_hours": 4,
        },
    )

    await server.handle_schedule_request_for_test(
        ws,
        request,
        asyncio.Lock(),
        action,
    )

    assert manager.pinned == [facade]
    assert manager.unpinned == [facade]
    assert service.context_release is not None
    service.context_release()
    assert manager.unpinned == [facade]
    assert ws.sent[0]["ok"] is (not raises)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "run"])
async def test_concurrent_schedule_mutations_capture_distinct_session_targets(
    monkeypatch,
    action: str,
) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    deep_a = object()
    deep_b = object()
    facade_a = _AgentFacade(deep_a)
    facade_b = _AgentFacade(deep_b)
    manager = _ConcurrentAgentManager({"web-a": facade_a, "web-b": facade_b})
    service = _ConcurrentRunService()
    server._agent_manager = manager
    server._scheduler_service = service
    monkeypatch.setattr(
        agent_ws_server_module,
        "encode_agent_response_for_wire",
        lambda response, response_id: {
            "type": "res",
            "id": response_id,
            "ok": response.ok,
            "payload": response.payload,
        },
    )
    ws_a = _FakeWebSocket()
    ws_b = _FakeWebSocket()
    request_a = AgentRequest(
        request_id="req-a",
        channel_id="web-a",
        session_id="session-a",
        params={
            "mode": "auto_harness",
            "query": "任务 A",
            "project_dir": "D:/work/project-a",
            "project_id": "project-a",
            "interval_hours": 4,
        },
    )
    request_b = AgentRequest(
        request_id="req-b",
        channel_id="web-b",
        session_id="session-b",
        params={
            "mode": "auto_harness",
            "query": "任务 B",
            "project_dir": "D:/work/project-b",
            "project_id": "project-b",
            "interval_hours": 4,
        },
    )

    await asyncio.gather(
        server.handle_schedule_request_for_test(
            ws_a,
            request_a,
            asyncio.Lock(),
            action,
        ),
        server.handle_schedule_request_for_test(
            ws_b,
            request_b,
            asyncio.Lock(),
            action,
        ),
    )

    calls = {call["query"]: call for call in service.calls}
    assert calls["任务 A"]["execution_agent"] is deep_a
    assert calls["任务 B"]["execution_agent"] is deep_b
    assert calls["任务 A"]["execution_target"] == {
        "project_dir": "D:/work/project-a",
        "project_id": "project-a",
        "origin_session_id": "session-a",
        "origin_channel_id": "web-a",
    }
    assert calls["任务 B"]["execution_target"] == {
        "project_dir": "D:/work/project-b",
        "project_id": "project-b",
        "origin_session_id": "session-b",
        "origin_channel_id": "web-b",
    }
    assert calls["任务 A"]["owner_scope"] == {
        "channel_id": "web-a",
        "session_id": "session-a",
        "app_id": "",
    }
    assert calls["任务 B"]["owner_scope"] == {
        "channel_id": "web-b",
        "session_id": "session-b",
        "app_id": "",
    }
    get_agent_calls = {call["channel_id"]: call for call in manager.get_agent_calls}
    assert get_agent_calls["web-a"]["project_dir"] == "D:/work/project-a"
    assert get_agent_calls["web-b"]["project_dir"] == "D:/work/project-b"
    assert manager.pinned == [facade_a, facade_b]
    calls["任务 A"]["context_release"]()
    calls["任务 B"]["context_release"]()
    assert manager.unpinned == [facade_a, facade_b]


@pytest.mark.asyncio
async def test_schedule_cancel_does_not_acquire_agent(monkeypatch) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    agent_manager = _FailIfAskedForAgent()
    service = _ScheduleService()
    server._agent_manager = agent_manager
    server._scheduler_service = service
    ws = _FakeWebSocket()
    request = AgentRequest(
        request_id="req-cancel",
        channel_id="web",
        session_id="session-1",
        params={"task_id": "sch_running"},
    )
    monkeypatch.setattr(
        agent_ws_server_module,
        "encode_agent_response_for_wire",
        lambda response, response_id: {
            "type": "res",
            "id": response_id,
            "ok": response.ok,
            "payload": response.payload,
        },
    )

    await server.handle_schedule_request_for_test(
        ws,
        request,
        asyncio.Lock(),
        "cancel",
    )

    assert agent_manager.calls == 0
    assert service.cancelled == ["sch_running"]
    assert service.cancel_kwargs == [
        {
            "requester_owner_scope": {
                "channel_id": "web",
                "session_id": "session-1",
                "app_id": "",
            },
            "requester_execution_target": {
                "project_dir": None,
                "project_id": None,
                "origin_session_id": "session-1",
                "origin_channel_id": "web",
            },
        }
    ]
    assert ws.sent == [
        {
            "type": "res",
            "id": "req-cancel",
            "ok": True,
            "payload": {"task_id": "sch_running", "status": "cancelled"},
        }
    ]


@pytest.mark.asyncio
async def test_schedule_status_passes_real_owner_and_project_without_agent(
    monkeypatch,
) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    agent_manager = _FailIfAskedForAgent()
    service = _ScheduleService()
    server._agent_manager = agent_manager
    server._scheduler_service = service
    ws = _FakeWebSocket()
    request = AgentRequest(
        request_id="req-status",
        channel_id="web",
        session_id="session-1",
        metadata={"app_id": "desktop"},
        params={
            "task_id": "sch_running",
            "project_dir": "D:/work/project-a",
            "project_id": "project-a",
        },
    )
    monkeypatch.setattr(
        agent_ws_server_module,
        "encode_agent_response_for_wire",
        lambda response, response_id: {
            "type": "res",
            "id": response_id,
            "ok": response.ok,
            "payload": response.payload,
        },
    )

    await server.handle_schedule_request_for_test(
        ws,
        request,
        asyncio.Lock(),
        "status",
    )

    assert agent_manager.calls == 0
    assert service.status_kwargs == [
        {
            "requester_owner_scope": {
                "channel_id": "web",
                "session_id": "session-1",
                "app_id": "desktop",
            },
            "requester_execution_target": {
                "project_dir": "D:/work/project-a",
                "project_id": "project-a",
                "origin_session_id": "session-1",
                "origin_channel_id": "web",
            },
        }
    ]
    assert ws.sent[0]["payload"] == {
        "task_id": "sch_running",
        "status": "pending",
    }


@pytest.mark.asyncio
async def test_schedule_delete_does_not_acquire_agent(monkeypatch) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    agent_manager = _FailIfAskedForAgent()
    service = _ScheduleService()
    server._agent_manager = agent_manager
    server._scheduler_service = service
    ws = _FakeWebSocket()
    request = AgentRequest(
        request_id="req-delete",
        channel_id="web",
        session_id="session-1",
        params={"task_id": "sch_finished"},
    )
    monkeypatch.setattr(
        agent_ws_server_module,
        "encode_agent_response_for_wire",
        lambda response, response_id: {
            "type": "res",
            "id": response_id,
            "ok": response.ok,
            "payload": response.payload,
        },
    )

    await server.handle_schedule_request_for_test(
        ws,
        request,
        asyncio.Lock(),
        "delete",
    )

    assert agent_manager.calls == 0
    assert service.deleted == ["sch_finished"]
    assert service.delete_kwargs == [
        {
            "requester_owner_scope": {
                "channel_id": "web",
                "session_id": "session-1",
                "app_id": "",
            },
            "requester_execution_target": {
                "project_dir": None,
                "project_id": None,
                "origin_session_id": "session-1",
                "origin_channel_id": "web",
            },
        }
    ]
    assert ws.sent == [
        {
            "type": "res",
            "id": "req-delete",
            "ok": True,
            "payload": {"task_id": "sch_finished"},
        }
    ]


@pytest.mark.asyncio
async def test_schedule_logs_passes_real_owner_and_project_without_agent(
    monkeypatch,
) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    agent_manager = _FailIfAskedForAgent()
    service = _ScheduleService()
    server._agent_manager = agent_manager
    server._scheduler_service = service
    ws = _FakeWebSocket()
    request = AgentRequest(
        request_id="req-logs",
        channel_id="web",
        session_id="session-1",
        metadata={"app_id": "desktop"},
        params={
            "task_id": "sch_running",
            "log_type": "history",
            "history_index": 2,
            "offset": 10,
            "limit": 20,
            "project_dir": "D:/work/project-a",
            "project_id": "project-a",
        },
    )
    monkeypatch.setattr(
        agent_ws_server_module,
        "encode_agent_response_for_wire",
        lambda response, response_id: {
            "type": "res",
            "id": response_id,
            "ok": response.ok,
            "payload": response.payload,
        },
    )

    await server.handle_schedule_request_for_test(
        ws,
        request,
        asyncio.Lock(),
        "logs",
    )

    assert agent_manager.calls == 0
    assert service.logs_calls == [
        {
            "task_id": "sch_running",
            "log_type": "history",
            "history_index": 2,
            "offset": 10,
            "limit": 20,
            "requester_owner_scope": {
                "channel_id": "web",
                "session_id": "session-1",
                "app_id": "desktop",
            },
            "requester_execution_target": {
                "project_dir": "D:/work/project-a",
                "project_id": "project-a",
                "origin_session_id": "session-1",
                "origin_channel_id": "web",
            },
        }
    ]
    assert ws.sent[0]["payload"] == {"logs": []}


@pytest.mark.asyncio
async def test_schedule_run_and_list_derive_owner_scope_from_request(monkeypatch) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    facade = _AgentFacade(object())
    manager = _ConcurrentAgentManager({"web": facade})
    service = _OwnerScopeService()
    server._agent_manager = manager
    server._scheduler_service = service
    monkeypatch.setattr(
        agent_ws_server_module,
        "encode_agent_response_for_wire",
        lambda response, response_id: {
            "type": "res",
            "id": response_id,
            "ok": response.ok,
            "payload": response.payload,
        },
    )
    run_request = AgentRequest(
        request_id="req-scoped-run",
        channel_id="web",
        session_id="session-real",
        metadata={"app_id": "desktop-real"},
        params={
            "mode": "auto_harness",
            "query": "受控任务",
            "model_name": "demo-model",
            "origin_namespace": "live_voice",
            "idempotency_key": "command-1",
            "owner_scope": {
                "channel_id": "spoofed",
                "session_id": "spoofed",
                "app_id": "spoofed",
            },
        },
    )

    await server.handle_schedule_request_for_test(
        _FakeWebSocket(),
        run_request,
        asyncio.Lock(),
        "run",
    )

    assert service.run_kwargs is not None
    assert service.run_kwargs["owner_scope"] == {
        "channel_id": "web",
        "session_id": "session-real",
        "app_id": "desktop-real",
    }
    assert service.run_kwargs["origin_namespace"] == "live_voice"
    assert service.run_kwargs["idempotency_key"] == "command-1"
    assert service.run_kwargs["model_intent"] == "demo-model"

    list_request = AgentRequest(
        request_id="req-scoped-list",
        channel_id="web",
        session_id="session-real",
        metadata={"app_id": "desktop-real"},
        params={
            "origin_namespace": "live_voice",
            "idempotency_key": "command-1",
            "project_dir": "D:/work/project-a",
            "project_id": "project-a",
            "owner_scope": {"session_id": "spoofed"},
        },
    )
    await server.handle_schedule_request_for_test(
        _FakeWebSocket(),
        list_request,
        asyncio.Lock(),
        "list",
    )

    assert service.list_kwargs == {
        "owner_scope": {
            "channel_id": "web",
            "session_id": "session-real",
            "app_id": "desktop-real",
        },
        "requester_execution_target": {
            "project_dir": "D:/work/project-a",
            "project_id": "project-a",
            "origin_session_id": "session-real",
            "origin_channel_id": "web",
        },
        "origin_namespace": "live_voice",
        "idempotency_key": "command-1",
    }

    assert service.run_kwargs["context_release"] is not None
    service.run_kwargs["context_release"]()
    assert manager.unpinned == [facade]
