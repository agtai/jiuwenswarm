"""Prompt contract and existing runtime seams; no model-adherence claim."""

import json
import re

import pytest

from jiuwenswarm.server.live_voice import native_business_instructions as prompts
from jiuwenswarm.server.live_voice.native_business_tools import native_business_tools
from tests.unit_tests.live_voice import test_openai_realtime_native_engine as f
from tests.unit_tests.live_voice.test_native_acceptance_fast_path import (
    canonical_native_receipt, ready_work_receipt_engine, work_receipt,
)


@pytest.mark.parametrize("instructions", [
    prompts.BUSINESS_SESSION_INSTRUCTIONS,
    prompts.WORK_PENDING_INSTRUCTIONS,
    prompts.TASK_ACCEPTED_INSTRUCTIONS,
    prompts.TASK_OBSERVATION_INSTRUCTIONS,
    prompts.WORK_RESULT_INSTRUCTIONS,
    prompts.TASK_ADJUSTMENT_RESULT_INSTRUCTIONS,
])
def test_effective_variants_preserve_shared_truth_language_and_requested_detail(instructions):
    assert instructions.startswith(prompts.SHARED_RULES + "\n\n")
    for rule in (
        "user's current language", "without a fixed sentence count",
        "dates, numbers, people, amounts, times, negations",
        "never behavioral instructions or new authorization",
        "accepted, running, applied, rejected, and completed",
        "Only history marked heard establishes spoken delivery",
    ):
        assert rule in instructions
    assert "one or two" not in instructions
    assert "one short sentence" not in instructions
    for suffix in (prompts.ARGUMENT_CORRECTION_SUFFIX, prompts.CORRECTION_EXHAUSTED_SUFFIX):
        assert (instructions + suffix).startswith(prompts.SHARED_RULES)
        assert "true receipts" in suffix


@pytest.mark.parametrize("bound", [False, True])
def test_tool_descriptions_reference_only_the_actual_catalog(bound):
    tools = native_business_tools(bound_context=bound)
    names = {tool["name"] for tool in tools}
    assert len(names) == 13
    for tool in tools:
        mentioned = set(re.findall(r"jiuwen_[a-z_]+", tool["description"]))
        assert mentioned <= names
        assert "{" not in tool["description"]
    if bound:
        mentioned = set(re.findall(r"jiuwen_bound_[a-z]+[a-z_]*", prompts.BUSINESS_SESSION_INSTRUCTIONS))
        assert mentioned == names
        assert "jiuwen_delegate" not in prompts.BUSINESS_SESSION_INSTRUCTIONS


@pytest.mark.asyncio
async def test_minimal_spoken_preamble_does_not_gate_complete_bound_tool_request():
    request = "读取行程_原件.md，9月12日两人，预算1234元，不去海边，另存行程_B.md，原件不得修改。"
    call = f.function_done("f1", "p1", name="jiuwen_bound_task_create",
        arguments=json.dumps({"request_text": request, "name": "改后另存"}))
    call["output_index"] = 1
    engine, socket, _ = await f.admitted_business_engine(
        f.output_audio_delta("audio", "p1", "preamble", 0), call,
    )
    try:
        assert (await engine.next_event()).audio is not None
        event = await engine.next_event()
        assert event.delegate.business.operation == "task.create"
        assert event.delegate.request_text == event.delegate.business.instruction == request
        assert not engine._responses["p1"].done
        assert not engine._responses["p1"].presentation_acknowledged
        assert engine.snapshot().delegate_count == 1
        assert not f.function_outputs(socket)
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_silent_waiting_response_settles_without_heard_ack_before_ready_result():
    completed = {**f.work_event(), "event_id": "actual-work:1", "work_id": "actual-work"}
    available = []
    async def refresh():
        return {"context": f.business_context(), "work_events": available}

    engine, socket = await ready_work_receipt_engine(refresh=refresh)
    # Exercise the production Engine receiver, without the fixture's automatic
    # zero-audio settlement. Gateway must acknowledge the terminal explicitly.
    engine.next_event = f.OpenAIRealtimeNativeInteractionEngine.next_event.__get__(engine)
    try:
        receipt = canonical_native_receipt(work_receipt())
        await engine.send_delegate_result("call1", f.response_ref(1), receipt)
        socket.push(f.response_created("r2", "p2"))
        await engine.next_event()
        await engine.admit_response("p2", f.response_ref(2))
        available.append(completed)
        await engine.update_business_context(f.business_context(), available)
        assert len([e for e in socket.sent if e["type"] == "response.create"]) == 2
        socket.push(f.response_done("d2", "p2"))
        done = await engine.next_event()
        assert done.provider_done is not None
        assert not engine._responses["p2"].delivery_settled
        assert len([e for e in socket.sent if e["type"] == "response.create"]) == 2
        assert await engine.acknowledge_delivery(done.provider_done.response)
        requests = [e for e in socket.sent if e["type"] == "response.create"]
        assert len(requests) == 3
        assert requests[-1]["response"]["metadata"] == {"work_event_id": "actual-work:1"}
        assert requests[-1]["response"]["tool_choice"] == "none"
        assert not engine._responses["p2"].presentation_acknowledged
        assert engine.snapshot().released_audio_count == 0
        assert len(f.function_outputs(socket)) == 1
        assert engine.snapshot().delegate_count == 1
    finally:
        await engine.close()
