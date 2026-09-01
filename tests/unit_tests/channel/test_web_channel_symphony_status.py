import asyncio
import json

import pytest

from jiuwenswarm.common.schema.message import EventType, Message
from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web.web_connect import (
    WebChannel,
    WebChannelConfig,
)
from jiuwenswarm.gateway.routing.keys import RoutingKey
from jiuwenswarm.gateway.routing.session_sharing import RoutingTarget


class _FakeClient:
    def __init__(self):
        self.frames = []
        self.closed = False
        self.remote_address = ("127.0.0.1", 12345)

    async def send(self, data):
        self.frames.append(json.loads(data))


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
            {"event_type": "goal.snapshot", "action": "get", "goal": goal, "session_id": "sess-goal"},
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
            {"event_type": "goal.updated", "goal": goal, "session_id": "sess-goal"},
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
