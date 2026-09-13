"""Named Provider calls retain correction, replay and audio ownership rules."""
import asyncio
import json

import pytest

from jiuwenswarm.common import live_voice_audio_diagnostics as sink
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import OpenAIRealtimeNativeInteractionError
from test_native_business_tools import SCENARIOS, inputs
from test_openai_realtime_native_engine import (
    admitted_business_engine, business_function, function_done, function_outputs,
    response_created, response_done, response_ref,
)


def named_call(event_id, response_id, call_id, operation, **changes):
    return function_done(event_id, response_id, call_id=call_id, item_id=f"item-{call_id}",
        name="jiuwen_" + operation.replace(".", "_"),
        arguments=json.dumps(inputs(operation, **changes), ensure_ascii=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", SCENARIOS)
async def test_each_named_call_is_admitted_once_with_the_exact_authoritative_operation(operation):
    call = named_call("first", "p1", "call1", operation)
    engine, socket, _ = await admitted_business_engine(call, call)
    try:
        emitted = await engine.next_event()
        assert emitted.delegate.business.operation == operation
        assert emitted.delegate.request_text == inputs(operation)["request_text"]
        assert (await engine.next_event()).delegate is None
        assert engine.snapshot().delegate_count == 1
        assert engine.snapshot().released_audio_count == 0 and not function_outputs(socket)
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_flat_adjustment_error_survives_real_sink_and_correction_does_not_repeat_accepted_sibling(monkeypatch):
    lines = []
    await asyncio.to_thread(sink._QUEUE.join)
    monkeypatch.setattr(sink._LOGGER, "info", lambda template, *args: lines.append(template % args))
    valid = named_call("work", "p1", "work-call", "work.start")
    invalid = named_call("bad", "p1", "adjust-call", "task.adjust", adjustment=None)
    engine, socket, _ = await admitted_business_engine(valid, invalid)
    try:
        assert (await engine.next_event()).delegate.business.operation == "work.start"
        assert (await engine.next_event()).delegate is None
        error = json.loads(function_outputs(socket)[0]["output"])
        assert error["field"] == "adjustment" and error["execution_started"] is False
        assert engine.snapshot().delegate_count == 1 and engine.snapshot().released_audio_count == 0
        await engine.send_delegate_result("work-call", response_ref(1), '{"work_id":"work-accepted","accepted":true}')
        socket.push(response_done("d1", "p1"))
        await engine.next_event()
        request = next(item for item in reversed(socket.sent) if item["type"] == "response.create")
        assert "Never repeat" in request["response"]["instructions"]
        socket.push(response_created("r2", "p2"))
        await engine.next_event()
        await engine.admit_response("p2", response_ref(2))
        socket.push(named_call("corrected", "p2", "corrected-call", "task.adjust"))
        result = await engine.next_event()
        assert result.delegate.business.adjustment == inputs("task.adjust")["adjustment"]
        assert engine.snapshot().delegate_count == 2
        assert list(engine._delegates) == ["work-call", "corrected-call"]
        assert sum(output["call_id"] == "work-call" for output in function_outputs(socket)) == 1
        await asyncio.to_thread(sink._QUEUE.join)
        records = [json.loads(line.split("live_voice_audio_diagnostic ", 1)[1]) for line in lines]
        rejected = [record["fields"] for record in records if record["fields"].get("milestone") == "arguments_rejected"]
        assert len(rejected) == 1
        assert rejected[0]["argument_field"] == "adjustment" and rejected[0]["argument_type"] == "null"
        assert "下午五点" not in repr(records) and "保留约束" not in repr(records)
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_same_call_id_cannot_change_named_operation_or_legacy_representation():
    first = named_call("first", "p1", "call1", "context.get")
    engine, socket, _ = await admitted_business_engine(first)
    try:
        assert (await engine.next_event()).delegate is not None
        socket.push(business_function("changed", "p1", "call1"))
        with pytest.raises(OpenAIRealtimeNativeInteractionError) as failure:
            await engine.next_event()
        assert failure.value.reason == "NATIVE_DELEGATE_CALL_CONFLICT"
        assert engine.snapshot().delegate_count == 1 and not function_outputs(socket)
        assert engine.snapshot().released_audio_count == 0
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_cancelled_response_named_call_has_no_late_business_or_audio_effects():
    engine, socket, _ = await admitted_business_engine()
    try:
        await engine.fence_response(response_ref(1))
        socket.push(named_call("late", "p1", "late-call", "task.cancel"))
        assert (await engine.next_event()).delegate is None
        assert engine._delegates == {} and engine.snapshot().delegate_count == 0
        assert not function_outputs(socket) and engine.snapshot().released_audio_count == 0
        assert not engine._responses["p1"].presentation_acknowledged
    finally:
        await engine.close()
