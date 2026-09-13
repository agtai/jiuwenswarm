# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import asyncio
import copy
import json

import pytest

from jiuwenswarm.common.schema.message import EventType, Message, ReqMethod
from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web.web_connect import (
    WebChannel,
    WebChannelConfig,
)
from jiuwenswarm.gateway.routing.keys import RoutingKey
from jiuwenswarm.gateway.routing.session_sharing import RoutingTarget


@pytest.mark.asyncio
async def test_web_channel_persists_frontend_context_usage_off_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "jiuwenswarm.gateway.channel_manager.web.web_connect.get_logs_dir",
        lambda: tmp_path,
    )
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    frame = {
        "event": "context.usage",
        "payload": {"session_id": "sess-context", "tokens_used": 12},
    }

    await channel._persist_frontend_context_usage(frame)

    records = (tmp_path / "context_usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(record) for record in records] == [frame]


def test_web_channel_rotates_frontend_context_usage_log(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "jiuwenswarm.gateway.channel_manager.web.web_connect.get_logs_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "jiuwenswarm.gateway.channel_manager.web.web_connect._CONTEXT_USAGE_MAX_BYTES",
        12,
    )
    monkeypatch.setattr(
        "jiuwenswarm.gateway.channel_manager.web.web_connect._CONTEXT_USAGE_BACKUP_COUNT",
        2,
    )

    WebChannel._write_frontend_context_usage("first")
    WebChannel._write_frontend_context_usage("second")

    assert (tmp_path / "context_usage.jsonl").read_text(encoding="utf-8") == "second\n"
    assert (tmp_path / "context_usage.jsonl.1").read_text(encoding="utf-8") == "first\n"
    assert not (tmp_path / "context_usage.jsonl.2").exists()


class _FakeClient:
    def __init__(self):
        self.frames = []
        self.closed = False
        self.remote_address = ("127.0.0.1", 12345)

    async def send(self, data):
        self.frames.append(json.loads(data))


def test_web_channel_exposes_heartbeat_marker_without_routing_metadata():
    automation = {
        "kind": "heartbeat",
        "job_id": "hb-1",
        "run_id": "run-1",
        "trigger": "scheduler",
    }
    msg = Message(
        id="run-1",
        type="event",
        channel_id="web",
        session_id="session-1",
        params={},
        timestamp=1.0,
        ok=True,
        payload={"event_type": "chat.final", "content": "done"},
        event_type=EventType.CHAT_FINAL,
        metadata={"automation": automation, "ws_id": "private-route"},
    )

    payload = WebChannel._build_event_payload(msg, "chat.final")
    frame = WebChannel._serialize_frame(object.__new__(WebChannel), msg)

    assert payload["metadata"] == {"automation": automation}
    assert frame["payload"]["metadata"] == {"automation": automation}
    assert "ws_id" not in payload["metadata"]
    assert "ws_id" not in frame["payload"]["metadata"]


def _private_native_activation_payload() -> dict[str, object]:
    return {
        "request_id": "request-native-activation",
        "ok": True,
        "result": {
            "status": "active",
            "session_id": "session-native",
            "correlation_id": "correlation-native",
            "interaction_id": "interaction-native",
            "activation_id": "activation-native",
            "activation_generation": 1,
            "_native_gateway": {
                "contract_version": "live-voice.native-interaction.v1",
                "binding": {},
                "capability": "a" * 64,
            },
        },
        "error": None,
        "product_composition": {"enabled": True},
    }


class _NativeActivationCompensator:
    def __init__(self) -> None:
        self.aborted = asyncio.Event()
        self.abort_calls: list[dict[str, object]] = []

    def observe_activation_response(self, payload, **_kwargs):
        sanitized = copy.deepcopy(payload)
        descriptor = sanitized["result"].pop("_native_gateway")
        assert descriptor
        sanitized["result"]["native_interaction"] = {
            "contract_version": "live-voice.native-interaction.v1",
            "engine": "openai-realtime-native",
            "model": "gpt-realtime-2.1-mini",
        }
        return sanitized

    async def abort_activation_response(self, payload, **kwargs):
        self.abort_calls.append({"payload": payload, **kwargs})
        self.aborted.set()
        return {"kind": "close", "status": "closed", "accepted": True}


def test_web_channel_preserves_goal_structured_payloads():
    goal = {
        "goal_id": "goal-1",
        "session_id": "sess-goal",
        "objective": "ship it",
        "status": "active",
    }
    messages = [
        (
            "goal.snapshot",
            Message(
                id="req-goal-get",
                type="event",
                channel_id="web",
                session_id="sess-goal",
                params={},
                timestamp=0.0,
                ok=True,
                payload={"event_type": "goal.snapshot", "action": "get", "goal": goal},
                event_type=EventType.GOAL_SNAPSHOT,
            ),
            {
                "event_type": "goal.snapshot",
                "action": "get",
                "goal": goal,
                "session_id": "sess-goal",
                "request_id": "req-goal-get",
            },
        ),
        (
            "goal.updated",
            Message(
                id="req-goal-run",
                type="event",
                channel_id="web",
                session_id="sess-goal",
                params={},
                timestamp=0.0,
                ok=True,
                payload={"event_type": "goal.updated", "goal": goal},
                event_type=EventType.GOAL_UPDATED,
            ),
            {
                "event_type": "goal.updated",
                "goal": goal,
                "session_id": "sess-goal",
                "request_id": "req-goal-run",
            },
        ),
        (
            "runtime.accepted",
            Message(
                id="req-goal-set",
                type="event",
                channel_id="web",
                session_id="sess-goal",
                params={},
                timestamp=0.0,
                ok=True,
                payload={"event_type": "runtime.accepted", "request_id": "req-goal-set"},
                event_type=EventType.RUNTIME_ACCEPTED,
            ),
            {"event_type": "runtime.accepted", "request_id": "req-goal-set", "session_id": "sess-goal"},
        ),
        (
            "execution.error",
            Message(
                id="req-goal-run",
                type="event",
                channel_id="web",
                session_id="sess-goal",
                params={},
                timestamp=0.0,
                ok=True,
                payload={
                    "event_type": "execution.error",
                    "code": "round_execution_error",
                    "message": "round failed",
                    "goal": None,
                },
                event_type=EventType.EXECUTION_ERROR,
            ),
            {
                "event_type": "execution.error",
                "code": "round_execution_error",
                "message": "round failed",
                "goal": None,
                "session_id": "sess-goal",
                "request_id": "req-goal-run",
            },
        ),
    ]

    for event_name, msg, expected in messages:
        assert WebChannel._build_event_payload(msg, event_name) == expected


@pytest.mark.asyncio
async def test_web_channel_preserves_live_voice_task_progress_delivery_binding():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="test_user",
        session_id="session-1",
        agent_ref=None,
    )
    scope = {
        "subject_id": "principal-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "assurance": "authenticated",
    }
    source_event = {
        "contract_version": "live-voice.contract.v2",
        "event_id": "source-7",
        "event_type": "task.running",
        "producer": {
            "component": "task_core",
            "instance_id": "agent_server.p3_core",
            "authority": "task_core",
        },
        "stream_ref": {"kind": "task", "id": "task-1"},
        "seq": 7,
        "occurred_at": "2030-01-01T00:00:00Z",
        "scope": scope,
        "correlation_id": "correlation-1",
        "causation_id": "cause-7",
        "required_capabilities": [],
        "payload": {"state": "running"},
        "extensions": {
            "jiuwenswarm.task_progress_return": {
                "consumer_scope_rebound": True,
                "persistent_attempt_id": "attempt-1",
                "persistent_correlation_id": "correlation-1",
                "persistent_event_producer": "task_core",
                "persistent_event_seq": 7,
                "persistent_event_type": "task.running",
                "persistent_scope": scope,
                "persistent_source_event_id": None,
            }
        },
    }
    progress_event = {
        "contract_version": "live-voice.contract.v2",
        "event_id": "progress-7",
        "event_type": "work.progress",
        "producer": {
            "component": "product_p3_voice",
            "instance_id": "session-1:interaction-1:3",
            "authority": "adapter",
        },
        "stream_ref": {"kind": "task", "id": "task-1"},
        "seq": 7,
        "occurred_at": "2030-01-01T00:00:00Z",
        "scope": scope,
        "correlation_id": "correlation-1",
        "causation_id": "source-7",
        "required_capabilities": [],
        "payload": {
            "work_ref": {"kind": "task", "id": "task-1"},
            "source": {
                "authority": "task_core",
                "event_id": "source-7",
                "source_work_ref": {"kind": "task", "id": "task-1"},
                "adapter": "agent_server.product_p3_voice.v1",
            },
            "seq": 7,
            "state": "running",
            "outcome": None,
            "summary": {"knowledge": "unknown"},
            "blocking_question": {"knowledge": "unknown"},
            "artifact_refs": {"knowledge": "unknown"},
            "urgency": "unknown",
            "speakability": "not_speakable",
        },
        "extensions": {
            "jiuwenswarm.task_progress_return": {
                "consumer_scope_rebound": True,
                "persistent_correlation_id": "correlation-1",
                "persistent_event_seq": 7,
                "persistent_scope": scope,
            }
        },
    }
    payload = {
        "event_type": "live_voice.task.progress",
        "delivery_id": "delivery-1",
        "session_id": "session-1",
        "task_id": "task-1",
        "project_id": "project-1",
        "correlation_id": "correlation-1",
        "origin_id": "interaction-1",
        "origin_kind": "voice",
        "requested_origin_kind": "voice",
        "effective_origin_kind": "text",
        "delivery_mode": "text_fallback",
        "fallback_reason": "TASK_PROGRESS_AUDIO_PLAYOUT_FAILED",
        "generation_kind": "web_task_progress_generation",
        "generation_id": "generation-1",
        "generation": 3,
        "source_event": source_event,
        "progress_event": progress_event,
        "evidence_id": "evidence-7",
        "presentation_class": "text",
        "response_ref": {
            "interaction_id": "interaction-1",
            "response_id": "response-7",
            "response_generation": 4,
        },
        "unit_id": "unit-7",
        "expected_event_head": 7,
        "result_source_event_id": None,
        "state": "running",
    }
    msg = Message(
        id="progress-1",
        type="event",
        channel_id="web",
        session_id="session-1",
        params={},
        timestamp=0.0,
        ok=True,
        payload=payload,
        event_type=EventType.LIVE_VOICE_TASK_PROGRESS,
    )

    routing_target = RoutingTarget(
        intent="live_voice_product_progress",
        routing_keys=[routing_key],
        member_names=(),
    )

    await channel.register_ws(client, routing_key)
    try:
        await channel.send(msg, routing_target=routing_target)
        for _ in range(20):
            if client.frames:
                break
            await asyncio.sleep(0.005)
        assert client.frames == [
            {
                "type": "event",
                "event": "live_voice.task.progress",
                "payload": {**payload, "session_id": "session-1"},
            }
        ]
    finally:
        await channel.unregister_ws(client)


@pytest.mark.asyncio
async def test_web_channel_preserves_symphony_status_payload():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="test_user",
        session_id="sess-1",
        agent_ref=None,
    )

    msg = Message(
        id="req-1",
        type="event",
        channel_id="web",
        session_id="sess-1",
        params={},
        timestamp=0.0,
        ok=True,
        payload={
            "source": "symphony_compose_graph",
            "operation_id": "call-1",
            "phase": "checking_score",
            "content": "Symphony status",
            "status": "in_progress",
        },
        event_type=EventType.CHAT_SYMPHONY_STATUS,
    )

    # 创建 RoutingTarget 包含 routing_keys
    routing_target = RoutingTarget(
        intent="godview",  # 必需参数
        routing_keys=[routing_key],
        member_names=(),
    )

    # 走真实 _register 建 ws 映射 + 起 per-ws writer（send 现在是非阻塞入队）
    await channel.register_ws(client, routing_key)
    try:
        await channel.send(msg, routing_target=routing_target)
        # writer 异步送出，flush 一下再断言
        for _ in range(20):
            if client.frames:
                break
            await asyncio.sleep(0.005)
        assert client.frames == [
            {
                "type": "event",
                "event": "chat.symphony_status",
                "payload": {
                    "source": "symphony_compose_graph",
                    "operation_id": "call-1",
                    "phase": "checking_score",
                    "content": "Symphony status",
                    "status": "in_progress",
                    "session_id": "sess-1",
                },
            }
        ]
    finally:
        await channel.unregister_ws(client)


@pytest.mark.asyncio
async def test_web_channel_preserves_client_is_stream_on_command_goal():
    """Web must not drop top-level is_stream (needed for streaming command.goal set)."""
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    seen = {}

    async def capture(msg):
        seen["is_stream"] = bool(msg.is_stream)
        seen["method"] = getattr(msg.req_method, "value", msg.req_method)
        return True

    channel.on_message(capture)
    raw = json.dumps(
        {
            "type": "req",
            "id": "req-goal-set",
            "method": "command.goal",
            "is_stream": True,
            "params": {
                "session_id": "sess-goal",
                "action": "set",
                "objective": "keep going",
                "overwrite_confirmed": True,
                "mode": "agent",
            },
        }
    )
    await channel._handle_raw_message(client, raw, {})
    await channel.unregister_ws(client)

    assert seen["method"] == "command.goal"
    assert seen["is_stream"] is True


@pytest.mark.asyncio
async def test_web_channel_chat_send_ack_before_forward_callback_finishes():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    callback_started = asyncio.Event()
    release_callback = asyncio.Event()

    async def chat_send_ack(ws, req_id, params, session_id):
        await channel.send_response(
            ws,
            req_id,
            ok=True,
            payload={"accepted": True, "session_id": session_id},
        )

    async def slow_forward_callback(msg):
        callback_started.set()
        await release_callback.wait()
        return True

    channel.register_method("chat.send", chat_send_ack)
    channel.on_message(slow_forward_callback)

    raw = json.dumps(
        {
            "type": "req",
            "id": "req-chat",
            "method": "chat.send",
            "params": {"session_id": "sess-chat", "content": "hello"},
        }
    )
    task = asyncio.create_task(channel._handle_raw_message(client, raw, {}))
    try:
        await asyncio.wait_for(callback_started.wait(), timeout=1)
        assert client.frames == [
            {
                "type": "res",
                "id": "req-chat",
                "ok": True,
                "payload": {"accepted": True, "session_id": "sess-chat"},
            }
        ]
    finally:
        release_callback.set()
        await task
        await channel.unregister_ws(client)


@pytest.mark.asyncio
async def test_web_channel_failure_res_uses_payload_message_as_top_level_error():
    """Unary failures that only set payload.message still surface top-level error."""
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="test_user",
        session_id="sess-goal",
        agent_ref=None,
    )
    await channel.register_ws(client, routing_key)
    try:
        msg = Message(
            id="req-goal-pause",
            type="res",
            channel_id="web",
            session_id="sess-goal",
            params={},
            timestamp=0.0,
            ok=False,
            payload={
                "action": "pause",
                "message": "目标不存在，无法暂停",
                "code": "goal_error",
                "goal": None,
            },
            metadata={"ws_id": getattr(client, "_jiuwen_ws_id", "")},
        )
        await channel.send(msg)
        for _ in range(20):
            if client.frames:
                break
            await asyncio.sleep(0.005)

        assert len(client.frames) == 1
        frame = client.frames[0]
        assert frame["type"] == "res"
        assert frame["ok"] is False
        assert frame["error"] == "目标不存在，无法暂停"
        assert frame["code"] == "goal_error"
        assert frame["payload"]["message"] == "目标不存在，无法暂停"
    finally:
        await channel.unregister_ws(client)


@pytest.mark.asyncio
async def test_web_channel_routes_rpc_response_by_request_ws_id():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    other_client = _FakeClient()
    routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="test_user",
        session_id="sess-real",
        agent_ref=None,
    )
    other_routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="other_user",
        session_id="sess-other",
        agent_ref=None,
    )

    await channel.register_ws(client, routing_key)
    await channel.register_ws(other_client, other_routing_key)
    try:
        msg = Message(
            id="req-graph",
            type="res",
            channel_id="web",
            session_id="sess-temp",
            params={},
            timestamp=0.0,
            ok=True,
            payload={"success": True},
            metadata={"ws_id": getattr(client, "_jiuwen_ws_id", "")},
        )

        await channel.send(msg)
        for _ in range(20):
            if client.frames:
                break
            await asyncio.sleep(0.005)

        assert client.frames == [
            {
                "type": "res",
                "id": "req-graph",
                "ok": True,
                "payload": {"success": True},
            }
        ]
        assert other_client.frames == []
    finally:
        await channel.unregister_ws(client)
        await channel.unregister_ws(other_client)


@pytest.mark.asyncio
async def test_native_activation_without_exact_socket_is_compensated() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    native = _NativeActivationCompensator()
    channel.live_voice_native_runtime_client = native
    msg = Message(
        id="request-native-activation",
        type="res",
        channel_id="web",
        session_id="session-native",
        params={},
        timestamp=0.0,
        ok=True,
        payload=_private_native_activation_payload(),
        metadata={
            "ws_id": "missing-web-connection",
            "method": ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
        },
    )

    await channel.send(msg)
    await asyncio.wait_for(native.aborted.wait(), timeout=1.0)

    assert len(native.abort_calls) == 1
    assert native.abort_calls[0]["connection_id"] == "missing-web-connection"
    assert native.abort_calls[0]["routed_session_id"] == "session-native"


@pytest.mark.asyncio
async def test_native_observer_failure_compensates_and_returns_error() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="native-user",
        session_id="session-native",
        agent_ref=None,
    )
    await channel.register_ws(client, routing_key)

    class _FailingNativeObserver(_NativeActivationCompensator):
        def observe_activation_response(self, *_args, **_kwargs):
            raise RuntimeError("native observer failed")

    native = _FailingNativeObserver()
    channel.live_voice_native_runtime_client = native
    msg = Message(
        id="request-native-observer",
        type="res",
        channel_id="web",
        session_id="session-native",
        params={},
        timestamp=0.0,
        ok=True,
        payload=_private_native_activation_payload(),
        metadata={
            "ws_id": getattr(client, "_jiuwen_ws_id", ""),
            "method": ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
        },
    )
    try:
        await channel.send(msg)
        await asyncio.wait_for(native.aborted.wait(), timeout=1.0)
        for _ in range(20):
            if client.frames:
                break
            await asyncio.sleep(0)

        assert len(native.abort_calls) == 1
        assert len(client.frames) == 1
        assert client.frames[0]["ok"] is False
        assert client.frames[0]["payload"]["error"]["reason"] == (
            "NATIVE_GATEWAY_ACTIVATION_INVALID"
        )
    finally:
        await channel.unregister_ws(client)


@pytest.mark.asyncio
async def test_native_media_observer_failure_compensates_and_returns_error() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="native-user",
        session_id="session-native",
        agent_ref=None,
    )
    await channel.register_ws(client, routing_key)
    native = _NativeActivationCompensator()
    channel.live_voice_native_runtime_client = native

    class _FailingMediaObserver:
        def observe_agent_response(self, *_args, **_kwargs):
            raise RuntimeError("media observer failed")

    channel.live_voice_media_registry = _FailingMediaObserver()
    msg = Message(
        id="request-native-media-observer",
        type="res",
        channel_id="web",
        session_id="session-native",
        params={},
        timestamp=0.0,
        ok=True,
        payload=_private_native_activation_payload(),
        metadata={
            "ws_id": getattr(client, "_jiuwen_ws_id", ""),
            "method": ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
        },
    )
    try:
        await channel.send(msg)
        await asyncio.wait_for(native.aborted.wait(), timeout=1.0)
        for _ in range(20):
            if client.frames:
                break
            await asyncio.sleep(0)

        assert len(native.abort_calls) == 1
        assert len(client.frames) == 1
        assert client.frames[0]["ok"] is False
        assert client.frames[0]["payload"]["error"]["reason"] == (
            "NATIVE_GATEWAY_ACTIVATION_INVALID"
        )
    finally:
        await channel.unregister_ws(client)


@pytest.mark.asyncio
async def test_web_channel_routes_event_by_request_ws_id_before_session_bucket():
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    other_client = _FakeClient()
    old_routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="test_user",
        session_id="sess-old",
        agent_ref=None,
    )
    new_routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="test_user",
        session_id="sess-new",
        agent_ref=None,
    )
    other_old_routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="other_user",
        session_id="sess-old",
        agent_ref=None,
    )

    await channel.register_ws(client, old_routing_key)
    await channel.register_ws(client, new_routing_key)
    await channel.register_ws(other_client, other_old_routing_key)
    try:
        msg = Message(
            id="req-usage",
            type="event",
            channel_id="web",
            session_id="sess-old",
            params={},
            timestamp=0.0,
            ok=True,
            payload={
                "event_type": "chat.usage_summary",
                "session_id": "sess-old",
                "usage": {"total_tokens": 7},
            },
            event_type=EventType.CHAT_USAGE_SUMMARY,
            metadata={"ws_id": getattr(client, "_jiuwen_ws_id", "")},
        )

        await channel.send(msg)
        for _ in range(20):
            if client.frames:
                break
            await asyncio.sleep(0.005)

        assert len(client.frames) == 1
        assert client.frames[0]["type"] == "event"
        assert client.frames[0]["event"] == "chat.usage_summary"
        assert client.frames[0]["payload"]["session_id"] == "sess-old"
        assert other_client.frames == []
    finally:
        await channel.unregister_ws(client)
        await channel.unregister_ws(other_client)


def _processing_status_message(session_id: str, is_processing: bool) -> Message:
    return Message(
        id="req-1",
        type="event",
        channel_id="web",
        session_id=session_id,
        params={},
        timestamp=0.0,
        ok=True,
        payload={
            "event_type": "chat.processing_status",
            "session_id": session_id,
            "is_processing": is_processing,
            "is_complete": not is_processing,
        },
        event_type=EventType.CHAT_PROCESSING_STATUS,
    )


@pytest.mark.asyncio
async def test_web_channel_session_busy_cleared_when_processing_status_routes_via_fanout():
    """回归:集群模式下 busy 映射必须与路由路径解耦。

    场景(code 模式 + 集群模式撤销报 SESSION_BUSY 的根因):
      1. 任务开始:网关 _send_processing_status 发送 is_processing=true,
         无 fan_out_targets → 走旧路径 → busy 置 True;
      2. 任务结束:team_helpers 广播 is_processing=false,事件携带
         fan_out_targets(godview 兜底),经 SessionDispatcher 以
         routing_target 调用 send() → V2 精确路由提前 return。
    若 busy 维护只存在于旧路径,结束事件永远写不进映射,busy 残留 True,
    /ws/git 的 discard/redo 会被 is_session_busy 误判,永远报 SESSION_BUSY
    (前端却显示任务已完成)。
    """
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="test_user",
        session_id="sess-1",
        agent_ref=None,
    )

    await channel.register_ws(client, routing_key)
    try:
        # 1) 任务开始:旧路径(无 routing_target)置 busy=True
        await channel.send(_processing_status_message("sess-1", True))
        assert channel.is_session_busy("sess-1") is True

        # 2) 集群模式任务结束:V2 精确路由(fan_out → routing_target)
        routing_target = RoutingTarget(
            intent="godview",
            routing_keys=[routing_key],
            member_names=(),
        )
        await channel.send(
            _processing_status_message("sess-1", False),
            routing_target=routing_target,
        )
        # busy 必须被清除(修复前残留 True)
        assert channel.is_session_busy("sess-1") is False
        # 前端仍应正常收到结束事件帧(V2 路径经 per-ws writer 异步送出;
        # 开始帧可能先到,这里等的是 is_processing=false 的那一帧)
        def _has_end_frame() -> bool:
            return any(
                frame["event"] == "chat.processing_status"
                and frame["payload"]["is_processing"] is False
                for frame in client.frames
            )

        for _ in range(40):
            if _has_end_frame():
                break
            await asyncio.sleep(0.005)
        assert _has_end_frame()
    finally:
        await channel.unregister_ws(client)


@pytest.mark.asyncio
async def test_web_channel_session_busy_tracks_interrupt_result_via_fanout():
    """interrupt_result 的 busy 维护同样必须与路由路径解耦(V2 路径)。"""
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    client = _FakeClient()
    routing_key = RoutingKey(
        channel_id="web",
        app_id="default",
        user_id="test_user",
        session_id="sess-1",
        agent_ref=None,
    )

    await channel.register_ws(client, routing_key)
    try:
        routing_target = RoutingTarget(
            intent="godview",
            routing_keys=[routing_key],
            member_names=(),
        )

        # resume → busy=True(V2 路径)
        await channel.send(
            Message(
                id="req-1",
                type="event",
                channel_id="web",
                session_id="sess-1",
                params={},
                timestamp=0.0,
                ok=True,
                payload={"event_type": "chat.interrupt_result", "intent": "resume"},
                event_type=EventType.CHAT_INTERRUPT_RESULT,
            ),
            routing_target=routing_target,
        )
        assert channel.is_session_busy("sess-1") is True

        # cancel → busy=False(旧路径,保持既有行为)
        await channel.send(
            Message(
                id="req-1",
                type="event",
                channel_id="web",
                session_id="sess-1",
                params={},
                timestamp=0.0,
                ok=True,
                payload={"event_type": "chat.interrupt_result", "intent": "cancel"},
                event_type=EventType.CHAT_INTERRUPT_RESULT,
            ),
        )
        assert channel.is_session_busy("sess-1") is False
    finally:
        await channel.unregister_ws(client)
