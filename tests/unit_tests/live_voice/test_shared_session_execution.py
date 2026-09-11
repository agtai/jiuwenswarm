"""Configured output ownership shared across entry points, without a scheduler."""
import asyncio
import json
from contextlib import aclosing
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk, PermissionContext
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.gateway.routing.keys import AgentRef
from jiuwenswarm.server.runtime.session_execution import SessionExecutionService, SessionExecutionUnavailable


def request(**kwargs):
    return AgentRequest(**{"request_id": "execution", "channel_id": "web", "session_id": "session",
        "req_method": ReqMethod.CHAT_SEND, "is_stream": True, "params": {"query": "report", "mode": "agent"},
        **kwargs})


def chunk(req, number=0, **kwargs):
    return AgentResponseChunk(request_id=req.request_id, channel_id=req.channel_id,
        payload={"event_type": "chat.delta", "content": str(number)}, **kwargs)


def service(**kwargs):
    manager = SimpleNamespace(pin_agent=Mock(), unpin_agent=Mock())
    return SessionExecutionService(manager, **kwargs)


async def settled(entry):
    await asyncio.wait_for(asyncio.shield(entry.task), 2)
    # done callback also owns pin release and the stream-closed fact.
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_two_subscribers_share_one_frozen_execution_and_isolated_events():
    calls, seen = [], []
    release = asyncio.Event()
    async def produce(req):
        calls.append(req)
        await release.wait()
        original = chunk(req, agent_ref=AgentRef("agent", "a"), metadata={"tag": [1]})
        yield original
        original.payload["content"] = "producer mutation"
    owner = SimpleNamespace(process_message_stream=produce)
    hub = service()
    req = request(permission_context=PermissionContext(web_user_id="u"), agent_ref=AgentRef("agent", "a"))
    async def read(change=False):
        async with aclosing(hub.stream(owner, req)) as output:
            async for event in output:
                seen.append(deepcopy(event))
                if change:
                    event.payload["content"] = "observer mutation"
                    event.metadata["tag"].append(2)
    readers = [asyncio.create_task(read(True)), asyncio.create_task(read())]
    await asyncio.sleep(0)
    req.params["query"] = "caller mutation"
    release.set()
    await asyncio.wait_for(asyncio.gather(*readers), 2)
    assert len(calls) == 1 and calls[0].params["query"] == "report"
    assert [event.payload["content"] for event in seen] == ["0", "0"]
    assert all(event.metadata == {"tag": [1]} for event in seen)
    fact = hub.observe(owner, session_id="session", execution_id="execution")
    assert fact["events"][0]["payload"]["content"] == "0"
    assert fact["events"][0]["agent_ref"] == {"mode": "agent", "id": "a"}
    assert fact["stream_closed"] and fact["stream_outcome"] == "ended"
    assert fact["business_completion"] == "consult_capability_owner"
    hub.manager.pin_agent.assert_called_once_with(owner)
    hub.manager.unpin_agent.assert_called_once_with(owner)


@pytest.mark.asyncio
async def test_slow_text_observer_gets_every_event_with_bounded_backpressure():
    produced = []
    async def produce(req):
        for number in range(12):
            produced.append(number)
            yield chunk(req, number)
    owner, hub = SimpleNamespace(process_message_stream=produce), service(max_events=2)
    async with aclosing(hub.stream(owner, request())) as output:
        first = await anext(output)
        await asyncio.sleep(0)
        assert len(produced) < 12
        received = [first.payload["content"]]
        async for event in output:
            await asyncio.sleep(0)
            received.append(event.payload["content"])
    assert received == [str(number) for number in range(12)]
    fact = hub.observe(owner, session_id="session", execution_id="execution")
    assert fact["history_truncated"] and len(fact["events"]) == 2
    with pytest.raises(SessionExecutionUnavailable, match="OBSERVATION_LOST"):
        await anext(hub.stream(owner, request()))


@pytest.mark.asyncio
async def test_oversized_projection_is_omitted_but_original_text_reaches_wire_owner():
    async def produce(req):
        yield chunk(req, "x" * 1000)
    owner, hub = SimpleNamespace(process_message_stream=produce), service(max_event_bytes=32)
    events = [event async for event in hub.stream(owner, request())]
    assert events[0].payload["content"] == "x" * 1000
    fact = hub.observe(owner, session_id="session", execution_id="execution")
    assert fact["events"] == [] and fact["history_truncated"]
    assert fact["stream_outcome"] == "ended"


@pytest.mark.asyncio
async def test_legacy_implicit_session_preserves_request_and_default_owner():
    calls = []
    async def produce(req):
        calls.append(req)
        yield chunk(req)
    owner, hub, req = SimpleNamespace(process_message_stream=produce), service(), request(session_id=None)
    await settled(hub.start(owner, req))
    assert calls[0].session_id is None and req.session_id is None
    assert hub.list(owner, session_id="default")["executions"][0]["execution_id"] == req.request_id


@pytest.mark.asyncio
async def test_exact_replay_coalesces_and_conflict_rejects_without_new_effect():
    calls = []
    async def produce(req):
        calls.append(req)
        yield chunk(req)
    owner, hub, req = SimpleNamespace(process_message_stream=produce), service(), request()
    entry = hub.start(owner, req)
    assert hub.start(owner, deepcopy(req), retained=True) is entry
    assert entry.retained is False
    await settled(entry)
    assert hub.start(owner, req) is entry
    changed = deepcopy(req)
    changed.permission_context = PermissionContext(web_user_id="different")
    with pytest.raises(SessionExecutionUnavailable, match="REQUEST_CONFLICT"):
        hub.start(owner, changed)
    assert len(calls) == 1
    assert hub.list(SimpleNamespace(), session_id="session")["executions"] == []
    for wrong_owner, wrong_session in ((SimpleNamespace(), "session"), (owner, "other")):
        with pytest.raises(SessionExecutionUnavailable, match="NOT_OBSERVED"):
            hub.observe(wrong_owner, session_id=wrong_session, execution_id="execution")
    hub.manager.pin_agent.assert_called_once()


@pytest.mark.asyncio
async def test_text_detach_cancels_once_and_holds_pin_through_actual_cleanup():
    cleaning, release = asyncio.Event(), asyncio.Event()
    cancellations = []
    async def produce(req):
        try:
            yield chunk(req)
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancellations.append("repeated cancel")
                raise
    owner, hub = SimpleNamespace(process_message_stream=produce), service()
    output = hub.stream(owner, request())
    await anext(output)
    closing = asyncio.create_task(output.aclose())
    await asyncio.wait_for(cleaning.wait(), 2)
    assert not await hub.close(timeout=0)
    closing.cancel()  # Observer disappears again while producer is cleaning up.
    await closing
    assert cancellations == []
    hub.manager.unpin_agent.assert_not_called()
    assert hub.list(owner, session_id="session")["executions"][0]["stream_closed"] is False
    release.set()
    assert await hub.close(timeout=2)
    await asyncio.sleep(0)
    hub.manager.unpin_agent.assert_called_once_with(owner)
    assert hub.list(owner, session_id="session")["executions"][0]["stream_outcome"] == "cancelled"


@pytest.mark.asyncio
async def test_retained_execution_survives_output_detach_and_reaches_real_eof():
    release, cleaned = asyncio.Event(), asyncio.Event()
    async def produce(req):
        try:
            yield chunk(req)
            await release.wait()
            yield chunk(req, "result", is_complete=True)
        finally:
            cleaned.set()
    owner, hub, req = SimpleNamespace(process_message_stream=produce), service(), request()
    entry = hub.start(owner, req, retained=True)
    output = hub.stream(owner, req)
    await anext(output)
    await output.aclose()
    assert not entry.task.done() and not cleaned.is_set()
    hub.manager.unpin_agent.assert_not_called()
    release.set()
    await settled(entry)
    fact = hub.observe(owner, session_id="session", execution_id="execution")
    assert fact["events"][-1]["payload"]["content"] == "result"
    assert fact["stream_outcome"] == "ended" and cleaned.is_set()


@pytest.mark.asyncio
async def test_cancel_before_producer_enters_releases_pin_but_does_not_run_agent():
    calls = []
    async def produce(req):
        calls.append(req)
        yield chunk(req)
    owner, hub = SimpleNamespace(process_message_stream=produce), service()
    hub.start(owner, request(), retained=True)
    assert await hub.close(timeout=2)
    await asyncio.sleep(0)
    assert calls == []
    hub.manager.unpin_agent.assert_called_once_with(owner)
    with pytest.raises(SessionExecutionUnavailable, match="SERVICE_CLOSED"):
        hub.start(owner, request(request_id="new"))


@pytest.mark.asyncio
async def test_actual_manager_cleanup_waits_for_shared_producer_before_disposing_agent(monkeypatch):
    from jiuwenswarm.server.runtime.agent_manager import AgentManager
    from unittest.mock import AsyncMock
    release, cleaning, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def produce(req):
        try:
            started.set()
            yield chunk(req)
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
    owner = SimpleNamespace(process_message_stream=produce, cleanup=AsyncMock())
    manager = AgentManager()
    manager.agents = {"web": {"agent": owner}}
    entry = manager.executions.start(owner, request(), retained=True)
    await asyncio.wait_for(started.wait(), 2)
    close = manager.executions.close
    monkeypatch.setattr(manager.executions, "close", lambda: close(timeout=0))
    with pytest.raises(RuntimeError, match="have not settled"):
        await manager.cleanup()
    await asyncio.wait_for(cleaning.wait(), 2)
    owner.cleanup.assert_not_called()
    assert manager._agent_pins[id(owner)] == 1
    assert manager.agents["web"]["agent"] is owner
    release.set()
    await asyncio.gather(entry.task, return_exceptions=True)
    await manager.cleanup()
    owner.cleanup.assert_awaited_once()
    assert manager.agents == {} and manager._agent_pins == {}


@pytest.mark.asyncio
async def test_failed_producer_keeps_partial_events_and_never_claims_completion():
    async def produce(req):
        yield chunk(req)
        raise RuntimeError("provider unavailable")
    owner, hub = SimpleNamespace(process_message_stream=produce), service()
    received = []
    with pytest.raises(SessionExecutionUnavailable, match="EXECUTION_UNAVAILABLE"):
        async for event in hub.stream(owner, request()):
            received.append(event)
    assert len(received) == 1
    fact = hub.observe(owner, session_id="session", execution_id="execution")
    assert fact["stream_closed"] and fact["stream_outcome"] == "failed"
    hub.manager.unpin_agent.assert_called_once()


@pytest.mark.asyncio
async def test_failed_aclose_is_distinct_from_clean_eof():
    class Output:
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise StopAsyncIteration
        async def aclose(self):
            raise RuntimeError("cleanup failed")
    owner, hub = SimpleNamespace(process_message_stream=lambda req: Output()), service()
    with pytest.raises(SessionExecutionUnavailable, match="EXECUTION_UNAVAILABLE"):
        await anext(hub.stream(owner, request()))
    assert hub.observe(owner, session_id="session", execution_id="execution")["stream_outcome"] == "cleanup_failed"
    hub.manager.unpin_agent.assert_called_once()


@pytest.mark.asyncio
async def test_real_facade_keeps_one_history_writer_and_shared_tool_interaction_events(monkeypatch):
    from jiuwenswarm.server.runtime.agent_adapter import interface as facade_module
    calls, history = [], []
    events = [
        {"event_type": "chat.delta", "content": "working"},
        {"event_type": "chat.interrupt", "interrupts": [{"id": "question", "value": "Choose a file"}]},
        {"event_type": "chat.final", "content": "done"},
    ]
    class Adapter:
        async def process_message_stream_impl(self, *args, **kwargs):
            calls.append((args, kwargs))
            for payload in events:
                yield AgentResponseChunk("execution", "web", deepcopy(payload))
    monkeypatch.setattr(facade_module.JiuWenSwarm, "_ensure_adapter", lambda *args, **kwargs: Adapter())
    monkeypatch.setattr(facade_module, "get_config", lambda: {"preferred_language": "zh", "memory": {"mode": "disabled"}})
    monkeypatch.setattr(facade_module, "get_memory_mode", lambda config: "disabled")
    monkeypatch.setattr(facade_module, "append_history_record", lambda **kwargs: history.append(kwargs))
    monkeypatch.setattr(facade_module, "_schedule_symphony_session_feedback", lambda *args: None)
    hub, owner, req = service(), facade_module.JiuWenSwarm(), request()
    text = [event async for event in hub.stream(owner, req)]
    replay = [event async for event in hub.stream(owner, req)]
    observation = hub.observe(owner, session_id="session", execution_id="execution")
    assert text == replay and text[-1].is_complete
    assert len(calls) == 1
    assert sum(item["role"] == "user" for item in history) == 1
    assert sum(item["role"] == "assistant" and item.get("content") == "done" for item in history) == 1
    assert any(event["payload"].get("interrupts") == events[1]["interrupts"] for event in observation["events"])
    assert observation["business_completion"] == "consult_capability_owner"


@pytest.mark.asyncio
async def test_active_and_observer_capacity_fail_before_new_execution():
    calls = []
    async def produce(req):
        calls.append(req)
        yield chunk(req)
        await asyncio.Event().wait()
    owner, hub = SimpleNamespace(process_message_stream=produce), service(max_records=1, max_active=1, max_observers=1)
    output = hub.stream(owner, request())
    await anext(output)
    with pytest.raises(SessionExecutionUnavailable, match="OBSERVER_CAPACITY"):
        await anext(hub.stream(owner, request()))
    with pytest.raises(SessionExecutionUnavailable, match="STREAM_CAPACITY"):
        hub.start(owner, request(request_id="second"))
    assert len(calls) == 1
    await output.aclose()
    assert await hub.close()


@pytest.mark.asyncio
async def test_only_closed_unobserved_records_can_be_evicted():
    async def produce(req):
        yield chunk(req)
    owner, hub = SimpleNamespace(process_message_stream=produce), service(max_records=1, max_active=1)
    old = hub.start(owner, request(), retained=True)
    await settled(old)
    await settled(hub.start(owner, request(request_id="next"), retained=True))
    assert [item["execution_id"] for item in hub.list(owner, session_id="session")["executions"]] == ["next"]
    with pytest.raises(SessionExecutionUnavailable, match="NOT_OBSERVED"):
        hub.observe(owner, session_id="session", execution_id="execution")


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["x" * 120_000, "界" * 35_000, "😀" * 20_000], ids=["ascii", "cjk", "emoji"])
async def test_large_human_prompt_is_omitted_whole_and_receipt_fits_real_journal(tmp_path, text):
    from jiuwenswarm.server.live_voice.unified_committed_input import SqliteUnifiedCommittedInputJournal
    from jiuwenswarm.server.live_voice.native_business_observation import canonical_native_receipt
    async def produce(req):
        yield chunk(req, "earlier")
        yield AgentResponseChunk(req.request_id, req.channel_id,
            {"event_type": "chat.interrupt", "interrupts": [{"id": "question", "value": text}]})
    owner, hub = SimpleNamespace(process_message_stream=produce), service()
    await settled(hub.start(owner, request(), retained=True))
    fact = hub.observe(owner, session_id="session", execution_id="execution")
    assert fact["events"] == [] and fact["history_truncated"]
    assert fact["events_omitted"] == fact["last_sequence"] == 2
    assert fact["event_range"] == {"first_sequence": None, "last_sequence": None}
    result = {"operation": "agent.get", "contract_version": "live-voice.native-business.v1", **fact}
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "commands.sqlite")
    arguments = {"voice_identity_sha256": "a" * 64, "fingerprint": b"a" * 32}
    journal.admit(request_id="bounded", created_at="2026-09-09T01:00:00Z", **arguments)
    assert journal.complete(result=result, completed_at="2026-09-09T01:00:01Z", **arguments) == result
    assert len(canonical_native_receipt(result).encode()) < 524_288


@pytest.mark.asyncio
async def test_projection_limits_whole_event_suffix_and_large_inventory():
    async def produce(req):
        for number in range(5):
            yield chunk(req, str(number) + "界" * 12_000)
    owner, hub = SimpleNamespace(process_message_stream=produce), service()
    for number in range(3):
        await settled(hub.start(owner, request(request_id=str(number), params={"model_name": "界" * 20_000}), retained=True))
    fact = hub.observe(owner, session_id="session", execution_id="2")
    assert fact["history_truncated"] and 0 < len(fact["events"]) < 5
    assert fact["events_omitted"] + len(fact["events"]) == 5
    assert fact["event_range"]["last_sequence"] == 5
    assert fact["event_range"]["first_sequence"] == 6 - len(fact["events"])
    assert all(len(event["payload"]["content"]) == 12_001 for event in fact["events"])
    inventory = hub.list(owner, session_id="session")
    assert inventory["inventory_truncated"] and inventory["total_observed"] == 3
    assert inventory["executions"][-1]["execution_id"] == "2"
    for projection in (fact, inventory):
        assert len(json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode()) <= hub.PROJECTION_UTF8_BYTES
        assert len(json.dumps(projection, ensure_ascii=True, separators=(",", ":")).encode()) <= hub.PROJECTION_ASCII_BYTES
