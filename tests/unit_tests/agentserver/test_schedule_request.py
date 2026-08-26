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
    def __init__(
        self, instance: object | None, project_root: str | None = None
    ) -> None:
        self.instance = instance
        self.project_root = project_root
        self.ensure_calls = 0
        self.get_instance_calls = 0

    def get_instance(self) -> object | None:
        self.get_instance_calls += 1
        return self.instance

    async def ensure_instance(self) -> object | None:
        self.ensure_calls += 1
        return self.instance

    def get_project_execution_root(self) -> str | None:
        return self.project_root

    async def process_background_code_task_stream(self, _request):
        if False:
            yield None


class _ControlledAgentFacade(_AgentFacade):
    def __init__(
        self,
        outcomes: list[object | None],
        *,
        events: list[str] | None = None,
        project_root: str | None = None,
    ) -> None:
        super().__init__(None, project_root)
        self._outcomes = list(outcomes)
        self._events = events

    async def ensure_instance(self) -> object | None:
        self.ensure_calls += 1
        if self._events is not None:
            self._events.append("ensure")
        if not self._outcomes:
            raise AssertionError("unexpected execution-agent initialization")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        self.instance = outcome
        return outcome


class _SingleflightAgentFacade(_AgentFacade):
    def __init__(self, ensured_instance: object) -> None:
        super().__init__(None)
        self._ensured_instance = ensured_instance
        self._ensure_lock = asyncio.Lock()
        self._both_entered = asyncio.Event()
        self.build_calls = 0

    async def ensure_instance(self) -> object:
        self.ensure_calls += 1
        if self.ensure_calls == 2:
            self._both_entered.set()
        if self.instance is not None:
            return self.instance
        async with self._ensure_lock:
            if self.instance is None:
                self.build_calls += 1
                await self._both_entered.wait()
                self.instance = self._ensured_instance
            return self.instance


class _ConcurrentAgentManager:
    def __init__(
        self,
        agents: dict[str, _AgentFacade],
        *,
        events: list[str] | None = None,
    ) -> None:
        self.agents = agents
        self.pinned: list[_AgentFacade] = []
        self.unpinned: list[_AgentFacade] = []
        self.get_agent_calls: list[dict] = []
        self._events = events

    async def get_agent(self, *, channel_id: str, **kwargs) -> _AgentFacade:
        await asyncio.sleep(0)
        self.get_agent_calls.append({"channel_id": channel_id, **kwargs})
        if self._events is not None:
            self._events.append("get_agent")
        return self.agents[channel_id]

    def pin_agent(self, agent: _AgentFacade) -> None:
        self.pinned.append(agent)
        if self._events is not None:
            self._events.append("pin")

    def unpin_agent(self, agent: _AgentFacade) -> None:
        self.unpinned.append(agent)
        if self._events is not None:
            self._events.append("unpin")


class _ConcurrentRunService:
    def __init__(
        self,
        *,
        expected_calls: int = 2,
        events: list[str] | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self._expected_calls = expected_calls
        self._events = events
        self._expected_started = asyncio.Event()

    async def _capture(
        self,
        action,
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
        if self._events is not None:
            self._events.append(f"mutate:{action}")
        self.calls.append(
            {
                "action": action,
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
        if len(self.calls) == self._expected_calls:
            self._expected_started.set()
        await self._expected_started.wait()
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
            "run",
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
            "create",
            query,
            model,
            pipeline,
            execution_agent,
            context_release,
            execution_target,
            owner_scope,
        )


class _IssueWatchService:
    def __init__(self) -> None:
        self.updated_agents: list[_AgentFacade] = []
        self.watch_calls: list[dict] = []

    async def update_agent_instance(self, agent: _AgentFacade) -> None:
        self.updated_agents.append(agent)

    async def watch_gitcode_issues_once(self, params, model) -> dict[str, str]:
        self.watch_calls.append({"params": params, "model": model})
        return {"status": "checked"}


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
    def __init__(self, list_result=None) -> None:
        self.run_kwargs: dict | None = None
        self.list_kwargs: dict | None = None
        self.list_result = [] if list_result is None else list_result

    async def run_task(
        self,
        _query,
        _model,
        _pipeline,
        **kwargs,
    ) -> dict[str, str]:
        self.run_kwargs = kwargs
        return {"task_id": "sch_scoped", "status": "running"}

    async def list_scheduled_tasks(self, **kwargs):
        self.list_kwargs = kwargs
        return self.list_result


def _patch_wire_encoder(monkeypatch) -> None:
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


def _mutation_request(
    *,
    request_id: str,
    channel_id: str = "web",
    session_id: str = "session",
    query: str = "受控任务",
    project_dir: str = "D:/work/project",
    project_id: str = "project",
) -> AgentRequest:
    return AgentRequest(
        request_id=request_id,
        channel_id=channel_id,
        session_id=session_id,
        params={
            "mode": "auto_harness",
            "query": query,
            "project_dir": project_dir,
            "project_id": project_id,
            "interval_hours": 4,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "run"])
async def test_cold_schedule_mutation_ensures_agent_before_pin_and_service(
    monkeypatch,
    action: str,
) -> None:
    events: list[str] = []
    ensured = object()
    facade = _ControlledAgentFacade([ensured], events=events)
    manager = _ConcurrentAgentManager({"web": facade}, events=events)
    service = _ConcurrentRunService(expected_calls=1, events=events)
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    server._agent_manager = manager
    server._scheduler_service = service
    _patch_wire_encoder(monkeypatch)
    ws = _FakeWebSocket()

    await server.handle_schedule_request_for_test(
        ws,
        _mutation_request(request_id=f"req-cold-{action}"),
        asyncio.Lock(),
        action,
    )

    assert facade.ensure_calls == 1
    assert facade.get_instance_calls == 0
    assert len(service.calls) == 1
    assert service.calls[0]["execution_agent"] is ensured
    assert events == ["get_agent", "ensure", "pin", f"mutate:{action}"]
    assert manager.pinned == [facade]
    assert manager.unpinned == []
    assert ws.sent[0]["ok"] is True
    service.calls[0]["context_release"]()
    assert manager.unpinned == [facade]
    assert events[-1] == "unpin"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "run"])
@pytest.mark.parametrize("failure", ["raise", "none"])
async def test_schedule_initialization_failure_can_retry_without_stale_mutation(
    monkeypatch,
    action: str,
    failure: str,
) -> None:
    events: list[str] = []
    ensured = object()
    first = RuntimeError("cold initialization failed") if failure == "raise" else None
    facade = _ControlledAgentFacade([first, ensured], events=events)
    manager = _ConcurrentAgentManager({"web": facade}, events=events)
    service = _ConcurrentRunService(expected_calls=1, events=events)
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    server._agent_manager = manager
    server._scheduler_service = service
    _patch_wire_encoder(monkeypatch)
    first_ws = _FakeWebSocket()

    await server.handle_schedule_request_for_test(
        first_ws,
        _mutation_request(request_id=f"req-first-{failure}-{action}"),
        asyncio.Lock(),
        action,
    )

    assert first_ws.sent[0]["ok"] is False
    assert facade.ensure_calls == 1
    assert facade.get_instance_calls == 0
    assert service.calls == []
    assert manager.pinned == []
    assert manager.unpinned == []
    assert events == ["get_agent", "ensure"]

    retry_ws = _FakeWebSocket()
    await server.handle_schedule_request_for_test(
        retry_ws,
        _mutation_request(request_id=f"req-retry-{failure}-{action}"),
        asyncio.Lock(),
        action,
    )

    assert facade.ensure_calls == 2
    assert facade.get_instance_calls == 0
    assert len(service.calls) == 1
    assert service.calls[0]["execution_agent"] is ensured
    assert manager.pinned == [facade]
    assert retry_ws.sent[0]["ok"] is True
    assert events == [
        "get_agent",
        "ensure",
        "get_agent",
        "ensure",
        "pin",
        f"mutate:{action}",
    ]
    service.calls[0]["context_release"]()
    assert manager.unpinned == [facade]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "run"])
async def test_concurrent_cold_schedule_mutations_share_one_agent_build(
    monkeypatch,
    action: str,
) -> None:
    ensured = object()
    facade = _SingleflightAgentFacade(ensured)
    manager = _ConcurrentAgentManager({"web": facade})
    service = _ConcurrentRunService()
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    server._agent_manager = manager
    server._scheduler_service = service
    _patch_wire_encoder(monkeypatch)

    await asyncio.gather(
        server.handle_schedule_request_for_test(
            _FakeWebSocket(),
            _mutation_request(
                request_id="req-same-a",
                session_id="session-a",
                query="任务 A",
                project_dir="D:/work/project-a",
                project_id="project-a",
            ),
            asyncio.Lock(),
            action,
        ),
        server.handle_schedule_request_for_test(
            _FakeWebSocket(),
            _mutation_request(
                request_id="req-same-b",
                session_id="session-b",
                query="任务 B",
                project_dir="D:/work/project-b",
                project_id="project-b",
            ),
            asyncio.Lock(),
            action,
        ),
    )

    assert facade.ensure_calls == 2
    assert facade.build_calls == 1
    assert facade.get_instance_calls == 0
    calls = {call["query"]: call for call in service.calls}
    assert calls["任务 A"]["execution_agent"] is ensured
    assert calls["任务 B"]["execution_agent"] is ensured
    assert calls["任务 A"]["execution_target"]["origin_session_id"] == "session-a"
    assert calls["任务 B"]["execution_target"]["origin_session_id"] == "session-b"
    assert calls["任务 A"]["execution_target"]["project_id"] == "project-a"
    assert calls["任务 B"]["execution_target"]["project_id"] == "project-b"
    assert calls["任务 A"]["owner_scope"]["session_id"] == "session-a"
    assert calls["任务 B"]["owner_scope"]["session_id"] == "session-b"
    assert manager.pinned == [facade, facade]
    calls["任务 A"]["context_release"]()
    calls["任务 B"]["context_release"]()
    assert manager.unpinned == [facade, facade]


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
    assert facade.ensure_calls == 1
    assert facade.get_instance_calls == 0
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
    assert facade_a.ensure_calls == 1
    assert facade_b.ensure_calls == 1
    assert facade_a.get_instance_calls == 0
    assert facade_b.get_instance_calls == 0
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
async def test_issue_watch_keeps_service_agent_without_initializing_execution_agent(
    monkeypatch,
) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    facade = _AgentFacade(None)
    manager = _ConcurrentAgentManager({"web": facade})
    service = _IssueWatchService()
    server._agent_manager = manager
    server._scheduler_service = service
    _patch_wire_encoder(monkeypatch)
    ws = _FakeWebSocket()
    request = AgentRequest(
        request_id="req-issue-watch",
        channel_id="web",
        session_id="session",
        params={"mode": "auto_harness", "repository": "example/repository"},
    )

    await server.handle_schedule_request_for_test(
        ws,
        request,
        asyncio.Lock(),
        "issue_watch_once",
    )

    assert facade.ensure_calls == 0
    assert facade.get_instance_calls == 0
    assert service.updated_agents == [facade]
    assert service.watch_calls == [{"params": request.params, "model": None}]
    assert manager.pinned == [facade]
    assert ws.sent[0]["ok"] is True


@pytest.mark.asyncio
async def test_schedule_run_and_list_derive_owner_scope_from_request(
    monkeypatch,
) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    facade = _AgentFacade(object(), "D:/work/project-a")
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
            "mode": "code",
            "query": "受控任务",
            "model_name": "demo-model",
            "pipeline": "project_code_pipeline",
            "project_dir": "D:/work/project-a",
            "project_id": "project-a",
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
    assert service.run_kwargs["project_executor"] is facade
    assert service.run_kwargs["effective_execution_root"] == "D:/work/project-a"
    assert manager.get_agent_calls[0]["mode"] == "code"
    assert facade.ensure_calls == 1
    assert facade.get_instance_calls == 0

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
    assert facade.ensure_calls == 1

    assert service.run_kwargs["context_release"] is not None
    service.run_kwargs["context_release"]()
    assert manager.unpinned == [facade]


@pytest.mark.asyncio
async def test_schedule_list_preserves_store_unavailable_response(monkeypatch) -> None:
    server = _ScheduleServerHarness.__new__(_ScheduleServerHarness)
    service = _OwnerScopeService(
        {
            "error": "任务存储未初始化",
            "code": "TASK_STORE_UNAVAILABLE",
        }
    )
    server._agent_manager = _FailIfAskedForAgent()
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
        request_id="req-list-unavailable",
        channel_id="web",
        session_id="session-real",
        metadata={"app_id": "desktop-real"},
        params={
            "origin_namespace": "live_voice",
            "idempotency_key": "command-1",
            "project_dir": "D:/work/project-a",
            "project_id": "project-a",
        },
    )

    await server.handle_schedule_request_for_test(
        ws,
        request,
        asyncio.Lock(),
        "list",
    )

    assert ws.sent[0]["ok"] is True
    assert ws.sent[0]["payload"] == {
        "error": "任务存储未初始化",
        "code": "TASK_STORE_UNAVAILABLE",
    }
