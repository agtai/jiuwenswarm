"""Formal Work uses the common producer while keeping exact output authority."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import FormalAgentExecution
from jiuwenswarm.server.runtime.session_execution import SessionExecutionUnavailable
from tests.unit_tests.live_voice.test_agent_conversation_runtime import (
    LowerFormalAdapter, ScriptedFormalAdapter, facade,
)
from tests.unit_tests.live_voice.test_native_work_runtime import agent_input
from tests.unit_tests.live_voice.test_shared_session_execution import service


def execution(**kwargs):
    committed, context = agent_input()
    return FormalAgentExecution(**dict(request_id="work:r1", channel_id="web",
        internal_session_id="lv-formal-work-test", commit=committed, context=context,
        read_only_tools=True, model_identity="model#0", model_config_version="version", **kwargs))


@pytest.mark.asyncio
async def test_replay_coalesces_and_conflicting_formal_or_wire_request_never_executes():
    lower = LowerFormalAdapter(release=asyncio.Event())
    agent, hub = facade(lower), service()
    original = execution()
    entry = hub.start_formal(agent, original)
    assert hub.start_formal(agent, original) is entry
    with pytest.raises(SessionExecutionUnavailable, match="REQUEST_CONFLICT"):
        hub.start_formal(agent, replace(original, model_config_version="changed"))
    with pytest.raises(SessionExecutionUnavailable, match="REQUEST_CONFLICT"):
        hub.start(agent, AgentRequest(request_id=original.request_id, channel_id="web",
            session_id=original.commit.scope.session_id, metadata={"formal": original}))
    await asyncio.wait_for(lower.started.wait(), 1)
    hub.disconnect(channel_id="web", session_id=original.commit.scope.session_id)
    assert not entry.cancellation_requested
    lower.release.set()
    assert await hub.wait_formal(entry) == "formal answer"
    assert lower.calls == 1 and lower.legacy_calls == 0
    assert len(hub._records) == 1
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("payloads,reason", [
    ((), "RESULT_UNAVAILABLE"),
    (({"event_type": "chat.delta", "content": "partial"},), "RESULT_UNAVAILABLE"),
    (({"event_type": "chat.final", "content": "one"},
      {"event_type": "chat.final", "content": "two"}), "DUPLICATE_AGENT_FINAL"),
    (({"event_type": "chat.final", "content": "one"},
      {"event_type": "chat.error", "content": "failed"}), "RESULT_UNAVAILABLE"),
    (({"event_type": "chat.final", "content": "x" * 131073},), "RESULT_TOO_LARGE"),
])
async def test_eof_duplicates_errors_and_oversized_results_do_not_complete(payloads, reason):
    agent, hub = facade(ScriptedFormalAdapter(payloads)), service()
    entry = hub.start_formal(agent, execution())
    with pytest.raises(SessionExecutionUnavailable, match=reason):
        await hub.wait_formal(entry)
    assert entry.stream_outcome == "failed"
    hub.manager.unpin_agent.assert_called_once_with(agent)
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("alter", [{"request_id": "foreign"}, {"channel_id": "foreign"}, {"payload": []}])
async def test_wrong_identity_and_payload_never_enter_public_observation(alter):
    async def source(spec):
        yield AgentResponseChunk(**{**dict(request_id=spec.request_id, channel_id=spec.channel_id,
            payload={"event_type": "chat.final", "content": "foreign secret"}), **alter})
    agent, hub = SimpleNamespace(process_formal_live_voice_stream=source), service()
    entry = hub.start_formal(agent, execution())
    with pytest.raises(SessionExecutionUnavailable, match="INVALID_FORMAL_AGENT_OUTPUT"):
        await hub.wait_formal(entry)
    assert entry.sequence == 0
    await hub.close()


@pytest.mark.asyncio
async def test_tool_less_split_control_markup_is_never_projected():
    lower = ScriptedFormalAdapter((
        {"event_type": "chat.delta", "content": "<｜\u200b"},
        {"event_type": "chat.delta", "content": "｜DS"},
        {"event_type": "chat.final", "content": "ML||invoke>"},
    ))
    agent, hub = facade(lower), service()
    entry = hub.start_formal(agent, execution(allow_tools=False))
    with pytest.raises(SessionExecutionUnavailable, match="CONTROL_MARKUP_REJECTED"):
        await hub.wait_formal(entry)
    assert entry.sequence == 0
    assert lower.requests[0].metadata["formal_live_voice_tools_allowed"] is False
    await hub.close()


@pytest.mark.asyncio
async def test_cleanup_failure_invalidates_even_a_valid_final_and_releases_pin():
    async def source(spec):
        try:
            yield AgentResponseChunk(request_id=spec.request_id, channel_id=spec.channel_id,
                payload={"event_type": "chat.final", "content": "provisional"})
        finally:
            raise OSError("cleanup failed")
    agent, hub = SimpleNamespace(process_formal_live_voice_stream=source), service()
    entry = hub.start_formal(agent, execution())
    with pytest.raises(SessionExecutionUnavailable):
        await hub.wait_formal(entry)
    assert entry.stream_outcome != "ended"
    hub.manager.unpin_agent.assert_called_once_with(agent)
    await hub.close()


@pytest.mark.asyncio
async def test_native_formal_cancel_and_text_share_owner_with_independent_settlement():
    lower = LowerFormalAdapter(final="forbidden native final", release=asyncio.Event(),
                               cancel_cleanup_release=asyncio.Event())
    agent, hub = facade(lower), service()
    native = execution()
    text_started, text_release = asyncio.Event(), asyncio.Event()
    text_requests = []

    async def text_stream(request):
        text_requests.append(request)
        text_started.set()
        await text_release.wait()
        yield AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
            payload={"event_type": "chat.final", "content": "ordinary text answer"})

    # This test owns the common producer/cancellation seam. The formal branch
    # still traverses the real facade, while Text records its independent entry.
    agent.process_message_stream = text_stream
    text_request = AgentRequest(request_id="text-r1", channel_id="web",
        session_id=native.commit.scope.session_id, params={"query": "ordinary text", "mode": "code.normal"})
    text_entry = hub.start(agent, text_request)
    native_entry = hub.start_formal(agent, native)
    try:
        await asyncio.wait_for(asyncio.gather(text_started.wait(), lower.started.wait()), 1)
        assert native_entry.agent is text_entry.agent is agent
        assert lower.requests[0].session_id == native.internal_session_id
        assert text_requests[0].session_id == native.commit.scope.session_id
        assert text_requests[0].params["mode"] == "code.normal"
        assert hub.cancel_formal(native_entry) is native_entry.task
        await asyncio.wait_for(lower.cancelled.wait(), 1)
        assert not native_entry.task.done() and not text_entry.cancellation_requested
        hub.manager.unpin_agent.assert_not_called()
        assert hub.cancel_formal(native_entry) is native_entry.task
        assert hub.start_formal(agent, native) is native_entry
        assert lower.calls == lower.cancel_calls == 1

        text_release.set()
        await asyncio.wait_for(asyncio.shield(text_entry.task), 1)
        assert text_entry.stream_outcome == "ended" and text_entry.stream_closed
        assert not native_entry.task.done()
        text_observation = hub.observe(agent, session_id=text_request.session_id, execution_id=text_request.request_id)
        assert text_observation["events"][0]["payload"]["content"] == "ordinary text answer"
        assert hub.manager.unpin_agent.call_count == 1
        lower.cancel_cleanup_release.set()
        with pytest.raises(SessionExecutionUnavailable):
            await hub.wait_formal(native_entry)
        assert native_entry.stream_outcome == "cancelled" and native_entry.sequence == 0
        assert len(text_requests) == 1 and lower.calls == lower.cancel_calls == 1
        assert hub.manager.pin_agent.call_count == hub.manager.unpin_agent.call_count == 2
    finally:
        text_release.set()
        lower.cancel_cleanup_release.set()
        await hub.close()


@pytest.mark.asyncio
async def test_gateway_loss_preserves_actual_formal_child_and_cancels_unrelated_text():
    from collections import Counter
    from unittest.mock import AsyncMock, Mock
    from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter
    from jiuwenswarm.server.runtime.agent_manager import AgentManager

    native = execution()
    lower = LowerFormalAdapter(final="retained result", release=asyncio.Event())
    def child(session_id):
        result = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
        result._is_session_scoped_adapter, result._parent_session_id = True, session_id
        result._instance = SimpleNamespace(abort=AsyncMock())
        result._stream_event_rail = Mock()
        result._active_session_ids = Counter({session_id: 1})
        result._cancel_scheduler_running_tasks = Mock()
        return result
    retained = child(native.internal_session_id)
    retained.process_formal_live_voice_stream_impl = lower.process_formal_live_voice_stream_impl
    unrelated = child("ordinary-text-session")
    root = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
    root._is_session_scoped_adapter = False
    root._session_adapters = {native.internal_session_id: retained, "ordinary-text-session": unrelated}
    root._get_or_create_session_adapter = AsyncMock(side_effect=lambda sid: root._session_adapters[sid])
    root.cleanup_session_adapter = AsyncMock(return_value=True)
    agent = facade(root)
    manager = AgentManager()
    manager.agents = {"web": {"configured-code-owner": agent}}
    hub = manager.executions
    entry = hub.start_formal(agent, native)
    ordinary = asyncio.create_task(asyncio.Event().wait())
    agent._session_manager._session_tasks["ordinary-text-session"] = ordinary
    try:
        await asyncio.wait_for(lower.started.wait(), 1)
        assert lower.requests[0].session_id == native.internal_session_id
        await manager.cancel_all_inflight_work("Gateway transport lost")
        retained._instance.abort.assert_not_awaited()
        retained._stream_event_rail.abort.assert_not_called()
        assert ordinary.cancelled()
        unrelated._instance.abort.assert_awaited_once()
        unrelated._stream_event_rail.abort.assert_called_once_with("ordinary-text-session")
        assert not entry.task.done() and not entry.cancellation_requested
        assert hub.retained_sessions(agent) == frozenset({native.commit.scope.session_id, native.internal_session_id})
        lower.release.set()
        assert await hub.wait_formal(entry) == "retained result"
        root.cleanup_session_adapter.assert_awaited_once_with(native.internal_session_id)
        assert not hub.retained_sessions(agent) and not manager._agent_pins
    finally:
        lower.release.set()
        ordinary.cancel()
        await asyncio.gather(ordinary, return_exceptions=True)
        await hub.close()
