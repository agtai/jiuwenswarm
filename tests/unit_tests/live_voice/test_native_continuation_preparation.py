import asyncio
import json

import pytest

from jiuwenswarm.server.live_voice import native_continuation_preparation as preparation
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    NativeEngineEvent, NativePresentationCursor, NativeProviderState, OpenAIRealtimeNativeInteractionError,
)
from tests.unit_tests.live_voice.test_openai_realtime_native_engine import (
    accept_basic_turn, action_payload, active_engine, business_context, business_function, config as engine_config,
    input_committed, output_audio_delta, output_audio_done, output_transcript_done, provider_event,
    response_created, response_done, response_ref, speech_started, speech_stopped, work_event,
)


async def preparing_engine(*, confirm=True, prepare=True, event_queue_capacity=16, session_config=None,
                           predecessor_status="completed"):
    fresh = {"context": business_context(), "work_events": []}
    async def refresh():
        return fresh
    engine, socket, _ = active_engine(speech_started("s1", "u1", 0),
        speech_stopped("e1", "u1", 500), input_committed("c1", "u1"), response_created("r1", "p1"),
        event_queue_capacity=event_queue_capacity, session_config=session_config)
    engine.configure_business_context(business_context(), refresh=refresh,
                                      continuation_preparation=True, receipt_projection=True)
    await engine.start()
    _, _, commit = await accept_basic_turn(engine)
    await engine.acknowledge_business_turn(commit.turn_commit.turn_id)
    assert action_payload(await engine.next_event())["provider_response_id"] == "p1"
    await engine.admit_response("p1", response_ref(1))
    socket.push(output_audio_delta("a1", "p1", "audio1", 0))
    assert (await engine.next_event()).audio.response == response_ref(1)
    socket.push(response_done("d1", "p1", status=predecessor_status))
    assert (await engine.next_event()).provider_done.response == response_ref(1)
    if not prepare:
        return engine, socket, fresh
    fresh["work_events"] = [work_event()]
    await engine.update_business_context(fresh["context"], fresh["work_events"])
    assert len([v for v in socket.sent if v["type"] == "response.create"]) == 2
    if confirm:
        socket.push(response_created("r2", "p2"))
        assert await engine.next_event() == NativeEngineEvent()
    return engine, socket, fresh


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["completed", "incomplete", "failed", "cancelled"])
async def test_terminal_pcm_keeps_owner_after_transport_completion_until_actual_rendered_ack(terminal):
    engine, socket, _ = await preparing_engine(predecessor_status=terminal)
    try:
        predecessor = engine._responses["p1"]
        assert engine._response_draining(predecessor)
        assert engine._responses["p2"].runtime_ref is None
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await complete_audio(engine, socket)
        # A drained server queue or transport ACK cannot release browser PCM.
        assert await engine.acknowledge_delivery(response_ref(1))
        assert not await engine.acknowledge_delivery(response_ref(1))
        await asyncio.sleep(0)
        assert not predecessor.presentation_acknowledged
        assert engine._response_draining(predecessor)
        assert engine._current_response_id == "p1"
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await engine.acknowledge_presentation(response_ref(99))
        await engine.acknowledge_presentation(response_ref(1))
        assert predecessor.presentable is (terminal == "completed")
        assert action_payload(await next_output(engine))["provider_response_id"] == "p2"
        await engine.admit_response("p2", response_ref(2))
        assert (await next_output(engine)).audio.response == response_ref(2)
        assert not engine._delegates
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["incomplete", "failed", "cancelled"])
async def test_terminal_partial_pcm_remains_stoppable_and_cannot_be_acknowledged_early(terminal):
    engine, socket, _ = await preparing_engine(prepare=False, predecessor_status=terminal)
    try:
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await engine.acknowledge_presentation(response_ref(1))
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await engine.acknowledge_delivery(response_ref(99))
        stop = await feed(engine, socket, speech_started("s2", "u2", 700))
        assert stop.action.operation == "STOP"
        assert action_payload(stop)["provider_response_id"] == "p1"
        await engine.stop_foreground(response_ref(1))
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await engine.acknowledge_presentation(response_ref(1))
        assert len(requests(socket)) == 1
        assert not engine._delegates
    finally:
        await engine.close()


def requests(socket):
    return [event for event in socket.sent if event["type"] == "response.create"]


async def feed(engine, socket, event):
    socket.push(event)
    # A local continuation-failure wake is independent of the Provider reader.
    before = len(engine._processed_event_ids)
    for _ in range(4):
        result = await engine.next_event()
        if len(engine._processed_event_ids) > before:
            if engine._continuation_scheduler is not None:
                await asyncio.wait_for(asyncio.shield(engine._continuation_scheduler), .5)
            return result
    raise AssertionError("Provider event was not consumed")


def audio_terminal(event_id="d2", *, transcript="", item_id="audio2"):
    event = response_done(event_id, "p2")
    event["response"]["output"] = [{"id": item_id, "type": "message", "role": "assistant",
        "status": "completed", "content": [{"type": "audio", "transcript": transcript}]}]
    return event


def function_terminal(call, event_id="d2"):
    event = response_done(event_id, "p2")
    event["response"]["output"] = [{"id": call["item_id"], "type": "function_call", "status": "completed",
        "name": call["name"], "call_id": call["call_id"], "arguments": call["arguments"]}]
    return event


async def complete_audio(engine, socket, *, transcript=""):
    await feed(engine, socket, output_audio_done("audio-done-2", "p2", "audio2"))
    await feed(engine, socket, output_transcript_done("transcript-done-2", "p2", "audio2", transcript))
    return await feed(engine, socket, audio_terminal(transcript=transcript))


async def next_output(engine):
    for _ in range(16):
        event = await engine.next_event()
        if event != NativeEngineEvent():
            return event
    raise AssertionError("No bounded output became available")


@pytest.mark.asyncio
@pytest.mark.parametrize("speaker_interrupts", [False, True])
@pytest.mark.parametrize("unemitted_partial", [False, True])
async def test_silent_predecessor_waits_for_runtime_terminal_without_stalling_reader(speaker_interrupts, unemitted_partial):
    engine, socket, _ = active_engine(speech_started("s1", "u1", 0),
        speech_stopped("e1", "u1", 500), input_committed("c1", "u1"), response_created("r1", "p1"),
        settle_silent_delivery=False)
    async def refresh():
        return {"context": business_context(), "work_events": [work_event()]}
    engine.configure_business_context(business_context(), refresh=refresh, continuation_preparation=True)
    await engine.start()
    try:
        _, _, commit = await accept_basic_turn(engine)
        await engine.acknowledge_business_turn(commit.turn_commit.turn_id)
        await engine.next_event()
        await engine.admit_response("p1", response_ref(1))
        if unemitted_partial:
            event = await feed(engine, socket, output_audio_delta("partial", "p1", "audio1", 0, pcm16=b"\x01\x00" * 100))
            assert event.audio is None
        done = await feed(engine, socket, response_done("done", "p1", status="failed" if unemitted_partial else "completed"))
        assert done.provider_done is not None
        assert not engine._response_draining(engine._responses["p1"])
        # Gateway/Runtime terminal RPC is held here, independent of media drain.
        await engine.update_business_context(business_context(), [work_event()])
        assert len(requests(socket)) == 1
        assert engine.snapshot().released_audio_count == 0
        if speaker_interrupts:
            listen = await feed(engine, socket, speech_started("s2", "u2", 700))
            assert listen.action.operation == "LISTEN"
        await engine.acknowledge_delivery(response_ref(1))
        assert len(requests(socket)) == (1 if speaker_interrupts else 2)
        assert not engine._delegates and engine.snapshot().released_audio_count == 0
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_prepared_done_has_no_authority_until_exact_played_ack_and_wakes_idle_reader():
    engine, socket, _ = await preparing_engine()
    try:
        for event in (output_audio_delta("a2", "p2", "audio2", 0),
                      output_audio_done("audio-done-2", "p2", "audio2"),
                      output_transcript_done("t2", "p2", "audio2", "Verified result"),
                      audio_terminal(transcript="Verified result")):
            assert await feed(engine, socket, event) == NativeEngineEvent()
        assert engine._current_response_id == "p1"
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1
        assert len(requests(socket)) == 2
        with pytest.raises(OpenAIRealtimeNativeInteractionError) as error:
            await engine.admit_response("p2", response_ref(2))
        assert error.value.reason == "NATIVE_PREPARED_RESPONSE_NOT_PROPOSED"
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await engine.acknowledge_presentation(response_ref(99))
        waiting = asyncio.create_task(engine.next_event())
        await asyncio.sleep(0)
        await engine.acknowledge_presentation(response_ref(1))
        speak = await asyncio.wait_for(waiting, .5)
        assert action_payload(speak)["provider_response_id"] == "p2"
        assert engine._responses["p2"].runtime_ref is None
        await engine.admit_response("p2", response_ref(2))
        audio = await engine.next_event()
        assert audio.audio.response == response_ref(2)
        assert (await next_output(engine)).generated_transcript.text == "Verified result"
        done = await next_output(engine)
        assert done.provider_done.completed and done.provider_done.response == response_ref(2)
        assert not await engine.acknowledge_presentation(response_ref(1))
        assert not engine._responses["p2"].presentation_acknowledged
        await feed(engine, socket, response_done("late-d1", "p1"))
        assert not engine._responses["p2"].presentation_acknowledged
    finally:
        await engine.close()
        assert engine._provider_receive_task is None


@pytest.mark.asyncio
async def test_prepared_function_has_zero_delegate_effect_before_promotion():
    engine, socket, _ = await preparing_engine()
    try:
        assert await feed(engine, socket, business_function("f2", "p2", "call2")) == NativeEngineEvent()
        assert engine.snapshot().delegate_count == 0 and not engine._delegates
        await feed(engine, socket, function_terminal(business_function("f2", "p2", "call2")))
        await engine.acknowledge_presentation(response_ref(1))
        assert action_payload(await engine.next_event())["provider_response_id"] == "p2"
        await engine.admit_response("p2", response_ref(2))
        assert (await engine.next_event()).delegate.provider_call_id == "call2"
        assert engine.snapshot().delegate_count == 1
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_overflow_preserves_old_playback_and_retries_only_after_exact_cleanup_and_ack(monkeypatch):
    monkeypatch.setattr(preparation, "MAX_PREPARED_OUTPUT_BYTES", 1024)
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        assert engine._prepared.output.discarded
        assert not engine._responses["p1"].cancelled
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
        assert [event["response_id"] for event in socket.sent if event["type"] == "response.cancel"] == ["p2"]
        await feed(engine, socket, response_done("d2", "p2", status="cancelled"))
        truncations = [event for event in socket.sent if event["type"] == "conversation.item.truncate"]
        assert [(event["item_id"], event["audio_end_ms"]) for event in truncations] == [("audio2", 0)]
        await feed(engine, socket, provider_event("conversation.item.truncated", "wrong", item_id="audio1", content_index=0, audio_end_ms=0))
        assert len(requests(socket)) == 2
        await feed(engine, socket, provider_event("conversation.item.truncated", "right", item_id="audio2", content_index=0, audio_end_ms=0))
        assert len(requests(socket)) == 2
        await engine.acknowledge_presentation(response_ref(1))
        assert len(requests(socket)) == 3
        socket.push(response_created("r3", "p3"))
        assert action_payload(await engine.next_event())["provider_response_id"] == "p3"
        assert engine.snapshot().state is not NativeProviderState.FAILED
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_unadmitted_function_cleanup_is_explicitly_unsupported_and_no_new_generation():
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, business_function("f2", "p2", "call2"))
        stop = await feed(engine, socket, speech_started("s2", "u2", 700))
        assert stop.action.operation == "STOP"
        assert action_payload(stop)["provider_response_id"] == "p1"
        await engine.stop_foreground(response_ref(1))
        # LISTEN is the second ordered speech-start action.
        assert (await engine.next_event()).action.operation == "LISTEN"
        await feed(engine, socket, response_done("d2", "p2", status="cancelled"))
        failures = []
        while (failure := engine.take_continuation_failure()) is not None:
            failures.append(failure[1])
        assert "NATIVE_PREPARED_CONTEXT_CLEANUP_UNSUPPORTED" in failures
        assert "NATIVE_PREPARED_RESPONSE_INTERRUPTED" not in failures
        await feed(engine, socket, speech_stopped("e2", "u2", 1200))
        commit = await feed(engine, socket, input_committed("c2", "u2"))
        await engine.acknowledge_business_turn(commit.turn_commit.turn_id)
        assert len(requests(socket)) == 2 and not engine._delegates
        assert not [event for event in socket.sent if event["type"] == "conversation.item.delete"]
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["failed", "cancelled", "incomplete"])
async def test_noncomplete_preparation_never_mints_completed_result(terminal):
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        assert await feed(engine, socket, response_done("d2", "p2", status=terminal)) == NativeEngineEvent()
        await engine.acknowledge_presentation(response_ref(1))
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1
        assert len(requests(socket)) == 2
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_work_revision_removed_during_refresh_cannot_promote():
    engine, socket, fresh = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await complete_audio(engine, socket)
        fresh["work_events"] = []
        await engine.acknowledge_presentation(response_ref(1))
        assert engine._prepared.output.discarded
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1
        assert engine.take_continuation_failure() is None
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_membership_loss_between_speak_and_admission_cleans_unpublished_buffer():
    engine, socket, fresh = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await complete_audio(engine, socket)
        await engine.acknowledge_presentation(response_ref(1))
        assert action_payload(await engine.next_event())["provider_response_id"] == "p2"
        fresh["work_events"] = []
        await engine.update_business_context(fresh["context"], [])
        assert engine._prepared.output.discarded and not engine._prepared_replay
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await engine.admit_response("p2", response_ref(2))
        assert engine.snapshot().released_audio_count == 1
        assert engine.take_continuation_failure() is None
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_normal_speech_interrupt_retires_prepared_audio_without_request_failure():
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        stop = await feed(engine, socket, speech_started("s2", "u2", 700))
        assert stop.action.operation == "STOP"
        assert action_payload(stop)["provider_response_id"] == "p1"
        assert engine.take_continuation_failure() is None
        assert engine._prepared.output.discarded
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1
        assert not engine._delegates
        await engine.stop_foreground(response_ref(1))
        assert (await engine.next_event()).action.operation == "LISTEN"
        await feed(engine, socket, response_done("d2", "p2", status="cancelled"))
        assert engine.take_continuation_failure() is None
        assert len(requests(socket)) == 2
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_projected_sibling_receipts_keep_exact_replay_and_one_fresh_complete_context():
    from jiuwenswarm.server.live_voice.native_business_observation import canonical_native_receipt
    from tests.unit_tests.live_voice.test_native_business_observation import receipt
    fresh = {"context": business_context(), "work_events": []}
    async def refresh():
        return fresh
    engine, socket, _ = active_engine(speech_started("s1", "u1", 0), speech_stopped("e1", "u1", 500),
        input_committed("c1", "u1"), response_created("r1", "p1"), business_function("f1", "p1", "call1"),
        business_function("f2", "p1", "call2"), response_done("d1", "p1"))
    engine.configure_business_context(business_context(), refresh=refresh, receipt_projection=True,
                                      continuation_preparation=True)
    await engine.start()
    try:
        _, _, commit = await accept_basic_turn(engine)
        await engine.acknowledge_business_turn(commit.turn_commit.turn_id)
        await engine.next_event()
        await engine.admit_response("p1", response_ref(1))
        await engine.next_event()
        await engine.next_event()
        await engine.next_event()
        canonical = canonical_native_receipt(receipt())
        await engine.send_delegate_result("call1", response_ref(1), canonical)
        assert len(requests(socket)) == 1
        fresh["context"] = {**business_context(), "context_id": "b" * 64,
                            "history": [{"role": "user", "content": "latest committed request", "delivery": "committed"}]}
        await engine.send_delegate_result("call2", response_ref(1), canonical)
        assert len(requests(socket)) == 2
        output = [event["item"] for event in socket.sent if event["type"] == "conversation.item.create"]
        tool_outputs = [json.loads(item["output"]) for item in output if item["type"] == "function_call_output"]
        assert len(tool_outputs) == 2 and all("context" not in item for item in tool_outputs)
        assert all(item["work"] == receipt()["work"] for item in tool_outputs)
        snapshots = [json.loads(item["content"][0]["text"])["native_business_context"]
                     for item in output if item["type"] == "message"]
        assert snapshots == [business_context(), fresh["context"]]
        before = tuple(socket.sent)
        await engine.send_delegate_result("call1", response_ref(1), canonical)
        assert tuple(socket.sent) == before
        with pytest.raises(OpenAIRealtimeNativeInteractionError) as conflict:
            await engine.send_delegate_result("call1", response_ref(1), canonical_native_receipt({**receipt(), "extra": True}))
        assert conflict.value.reason == "NATIVE_DELEGATE_RESULT_CONFLICT"
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("observation", ["equivalent", "newer", "refresh_newer", "interrupted"])
async def test_receipt_refresh_observation_preserves_one_current_successor(observation):
    from jiuwenswarm.server.live_voice.native_business_observation import canonical_native_receipt
    entered, release = asyncio.Event(), asyncio.Event()
    latest = {"context": business_context(), "work_events": []}
    async def refresh():
        entered.set()
        await release.wait()
        return latest
    engine, socket, _ = active_engine(speech_started("s1", "u1", 0), speech_stopped("e1", "u1", 500),
        input_committed("c1", "u1"), response_created("r1", "p1"),
        business_function("f1", "p1", "call1"), response_done("d1", "p1"))
    engine.configure_business_context(business_context(), refresh=refresh,
        receipt_projection=True, continuation_preparation=True)
    await engine.start()
    send = observer = None
    try:
        _, _, commit = await accept_basic_turn(engine)
        await engine.acknowledge_business_turn(commit.turn_commit.turn_id)
        await engine.next_event()
        await engine.admit_response("p1", response_ref(1))
        await engine.next_event()
        await engine.next_event()
        canonical = canonical_native_receipt({"contract_version": "live-voice.native-business.v1",
            "operation": "work.start", "work": {"state": "running", "revision": 1},
            "context": business_context()})
        send = asyncio.create_task(engine.send_delegate_result("call1", response_ref(1), canonical))
        await asyncio.wait_for(entered.wait(), .5)
        observed = business_context()
        if observation in {"newer", "refresh_newer"}:
            observed["context_id"] = "b" * 64
            observed["history"] = [{"role": "user", "content": "latest fact", "delivery": "committed"}]
        observer = asyncio.create_task(engine.update_business_context(observed, []))
        await asyncio.sleep(0)
        latest["context"] = observed
        if observation == "refresh_newer":
            latest["context"] = {**observed, "context_id": "c" * 64,
                "history": [{"role": "user", "content": "newest receipt fact", "delivery": "committed"}]}
        if observation == "interrupted":
            socket.push(speech_started("s2", "u2", 700))
            assert (await engine.next_event()).action.operation == "STOP"
            await engine.stop_foreground(response_ref(1))
        release.set()
        await asyncio.wait_for(asyncio.gather(send, observer), .5)
        for _ in range(3):
            await engine._request_pending_provider_response()
        assert len(requests(socket)) == (1 if observation == "interrupted" else 2)
        outputs = [e["item"] for e in socket.sent if e["type"] == "conversation.item.create"]
        assert len([i for i in outputs if i["type"] == "function_call_output"]) == 1
        if observation != "interrupted":
            snapshots = [json.loads(i["content"][0]["text"])["native_business_context"]
                         for i in outputs if i["type"] == "message"]
            assert snapshots[-1] == latest["context"]
        assert engine.snapshot().released_audio_count == 0
        assert engine.snapshot().delegate_count == 1
    finally:
        release.set()
        await asyncio.gather(*(t for t in (send, observer) if t is not None), return_exceptions=True)
        await engine.close()


@pytest.mark.asyncio
async def test_cancel_before_prepared_created_keeps_late_successor_unadmitted():
    engine, socket, _ = await preparing_engine(confirm=False)
    try:
        # Retained preparation identity survives a later user turn; no new call
        # or Runtime response is allocated by delayed Provider output.
        await engine.stop_foreground(response_ref(1))
        assert await feed(engine, socket, response_created("late-r2", "p2")) == NativeEngineEvent()
        await feed(engine, socket, output_audio_delta("late-a2", "p2", "audio2", 0))
        await feed(engine, socket, response_done("late-d2", "p2", status="cancelled"))
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1 and engine.snapshot().delegate_count == 0
        assert len(requests(socket)) == 2
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_ack_before_terminal_keeps_preparation_unadmitted_until_complete():
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await engine.acknowledge_presentation(response_ref(1))
        assert engine._prepared is not None and engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1
        await complete_audio(engine, socket)
        assert action_payload(await engine.next_event())["provider_response_id"] == "p2"
        await engine.admit_response("p2", response_ref(2))
        assert (await engine.next_event()).audio.response == response_ref(2)
        assert (await next_output(engine)).provider_done.completed
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_paced_drain_observes_speech_before_next_pcm_and_fences_all_remaining_output():
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0, pcm16=b"\x01\x00" * 480 * 4))
        await complete_audio(engine, socket)
        await engine.acknowledge_presentation(response_ref(1))
        await engine.next_event()
        await engine.admit_response("p2", response_ref(2))
        assert (await engine.next_event()).audio.sequence == 0
        # Credit is available immediately, but socket control must win first.
        socket.push(speech_started("s2", "u2", 700))
        stop = await engine.next_event()
        assert stop.action.operation == "STOP" and action_payload(stop)["provider_response_id"] == "p2"
        await engine.stop_foreground(response_ref(2))
        assert (await engine.next_event()).action.operation == "LISTEN"
        assert engine.snapshot().released_audio_count == 2
        assert not engine._prepared_replay and not engine._pending_events
        assert engine._responses["p2"].done and not engine._responses["p2"].presentation_acknowledged
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await engine.acknowledge_presentation(response_ref(2))
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_prepared_pcm_uses_bounded_startup_credit_without_per_frame_wait():
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0, pcm16=b"\x01\x00" * 480 * 4))
        await complete_audio(engine, socket)
        await engine.acknowledge_presentation(response_ref(1))
        await engine.next_event()
        await engine.admit_response("p2", response_ref(2))
        start = asyncio.get_running_loop().time()
        assert [(await engine.next_event()).audio.sequence for _ in range(4)] == [0, 1, 2, 3]
        # All four frames fit the 320 ms window. Their sample deadline remains
        # behind now; no timer sleeps were required to replenish the player.
        assert engine._prepared_next_audio_at <= start
        assert (await next_output(engine)).provider_done.completed
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, True])
async def test_preparation_deadline_discards_without_assuming_terminal_or_cleanup(confirm):
    engine, socket, _ = await preparing_engine(confirm=confirm)
    try:
        request = engine._prepared.request if confirm else engine._inflight_response_request
        request.preparation_deadline = asyncio.get_running_loop().time() + .01
        async def observe_expiry():
            while request.preparation_deadline is not None:
                assert await engine.next_event() == NativeEngineEvent()
        await asyncio.wait_for(observe_expiry(), .2)
        reasons = []
        while (failure := engine.take_continuation_failure()) is not None:
            reasons.append(failure[1])
        assert ("NATIVE_PREPARED_RESPONSE_TIMEOUT" if confirm else "NATIVE_PREPARED_RESPONSE_CONFIRMATION_TIMEOUT") in reasons
        assert len(requests(socket)) == 2 and not engine._responses["p1"].cancelled
        if confirm:
            assert engine._prepared.output.discarded
            assert [event["response_id"] for event in socket.sent if event["type"] == "response.cancel"] == ["p2"]
        else:
            assert request.retired and not [event for event in socket.sent if event["type"] == "response.cancel"]
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_source_close_cancels_single_receive_and_never_releases_prepared_output():
    engine, socket, _ = await preparing_engine()
    await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
    waiting = asyncio.create_task(engine.next_event())
    await asyncio.sleep(0)
    assert await engine.close()
    await asyncio.gather(waiting, return_exceptions=True)
    assert engine._provider_receive_task is None and engine._prepared is None
    assert engine.snapshot().released_audio_count == 1
    with pytest.raises(OpenAIRealtimeNativeInteractionError):
        await engine.next_event()


@pytest.mark.asyncio
async def test_multiple_prepared_audio_items_fail_closed_and_cleanup_requires_both_identities():
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await feed(engine, socket, output_audio_delta("a3", "p2", "audio3", 0, output_index=1))
        assert engine._prepared.output.discarded
        await feed(engine, socket, response_done("d2", "p2"))
        assert {event["item_id"] for event in socket.sent if event["type"] == "conversation.item.truncate"} == {"audio2", "audio3"}
        await feed(engine, socket, provider_event("conversation.item.truncated", "ack2", item_id="audio2", content_index=0, audio_end_ms=0))
        assert engine._prepared is not None and not engine._prepared.output.cleanup_complete
        assert engine.snapshot().released_audio_count == 1 and not engine._responses["p1"].cancelled
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_prepared_item_cannot_reuse_predecessor_identity_or_truncate_old_playback():
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("wrong-item", "p2", "audio1", 0))
        await feed(engine, socket, response_done("d2", "p2", status="cancelled"))
        assert engine._prepared.output.discarded and engine._prepared.output.cleanup_unsupported
        assert not [event for event in socket.sent if event["type"] == "conversation.item.truncate"]
        assert not engine._responses["p1"].cancelled and engine.snapshot().released_audio_count == 1
        assert not engine._responses["p1"].presentation_acknowledged
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_closed_terminal_message_matches_prepared_audio_and_metadata():
    engine, socket, _ = await preparing_engine()
    try:
        item = {"id": "audio2", "type": "message", "role": "assistant", "status": "in_progress", "content": []}
        await feed(engine, socket, provider_event("response.output_item.added", "item-added", response_id="p2", output_index=0, item=item))
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await feed(engine, socket, output_audio_done("audio-done-2", "p2", "audio2"))
        await feed(engine, socket, output_transcript_done("t2", "p2", "audio2", "verified"))
        done = response_done("d2", "p2")
        done["response"]["output"] = [{**item, "status": "completed", "content": [{"type": "audio", "transcript": "verified"}]}]
        await feed(engine, socket, done)
        assert not engine._prepared.output.discarded
        await engine.acknowledge_presentation(response_ref(1))
        assert action_payload(await engine.next_event())["provider_response_id"] == "p2"
        await engine.admit_response("p2", response_ref(2))
        assert (await engine.next_event()).audio.response == response_ref(2)
        await next_output(engine)
        assert (await next_output(engine)).provider_done.completed
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_terminal_cannot_hide_an_observed_unrepresented_provider_item():
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, provider_event("response.output_item.added", "item-added", response_id="p2", output_index=0,
            item={"id": "unrepresented", "type": "message", "role": "assistant", "status": "in_progress", "content": []}))
        await feed(engine, socket, response_done("d2", "p2"))
        await engine.acknowledge_presentation(response_ref(1))
        assert engine._prepared.output.discarded and engine._prepared.output.cleanup_unsupported
        assert engine._responses["p2"].runtime_ref is None and engine.snapshot().released_audio_count == 1
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["audio", "function", "transcript", "done"])
@pytest.mark.parametrize("admitted", [False, True])
async def test_fresh_post_terminal_events_never_join_verified_prepared_replay(kind, admitted):
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await complete_audio(engine, socket, transcript="verified")
        if admitted:
            await engine.acknowledge_presentation(response_ref(1))
            assert action_payload(await next_output(engine))["provider_response_id"] == "p2"
            await engine.admit_response("p2", response_ref(2))
        late = {
            "audio": output_audio_delta("late-a2", "p2", "audio2", 0),
            "function": business_function("late-f2", "p2", "unexpected-call"),
            "transcript": output_transcript_done("late-t2", "p2", "audio2", "unverified"),
            "done": audio_terminal("late-d2", transcript="verified"),
        }[kind]
        socket.push(late)
        if admitted:
            # The retained socket reader is the only receiver. Wait until its
            # event is decoded, without creating a second next_event consumer.
            receiver = engine._provider_receive_task
            assert receiver is not None
            await asyncio.wait((receiver,), timeout=.5)
            assert receiver.done()
        with pytest.raises(OpenAIRealtimeNativeInteractionError) as error:
            # Local wakes do not represent Provider consumption.
            for _ in range(4):
                assert await engine.next_event() == NativeEngineEvent()
        assert error.value.reason == "NATIVE_PREPARED_OUTPUT_AFTER_TERMINAL"
        assert engine.snapshot().released_audio_count == 1
        assert not engine._delegates and engine.snapshot().delegate_count == 0
        assert not engine._responses["p2"].presentation_acknowledged
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["missing_manifest", "wrong_transcript", "missing_audio_done",
    "missing_transcript_done", "duplicate_audio_done", "duplicate_transcript_done", "wrong_index",
    "partial_final_conflict", "control_character", "oversized_transcript", "frame_expansion",
    "unrepresented_function", "function_index", "item_done_conflict"])
async def test_preparation_preflight_rejects_before_any_successor_authority(defect):
    engine, socket, _ = await preparing_engine()
    try:
        if defect == "frame_expansion":
            delta = output_audio_delta("a2", "p2", "audio2", 0, pcm16=b"\x01\x00" * 480 * 17)
        else:
            delta = output_audio_delta("a2", "p2", "audio2", 0)
        if defect in {"unrepresented_function", "function_index"}:
            call = business_function("f2", "p2", "call2")
            if defect == "function_index":
                call["output_index"] = 1
            await feed(engine, socket, call)
            done = response_done("d2", "p2") if defect == "unrepresented_function" else function_terminal(call)
        else:
            if defect == "wrong_index":
                delta["output_index"] = 1
            await feed(engine, socket, delta)
            if defect != "missing_audio_done":
                done_audio = output_audio_done("audio-done-2", "p2", "audio2", output_index=delta["output_index"])
                await feed(engine, socket, done_audio)
                if defect == "duplicate_audio_done":
                    await feed(engine, socket, {**done_audio, "event_id": "duplicate-audio-done"})
            transcript = "\u200bhidden" if defect == "control_character" else (
                "x" * 65537 if defect == "oversized_transcript" else "verified")
            if defect == "partial_final_conflict":
                await feed(engine, socket, provider_event("response.output_audio_transcript.delta", "partial-t2",
                    response_id="p2", item_id="audio2", output_index=0, content_index=0, delta="different"))
            if defect != "missing_transcript_done":
                transcript_done = output_transcript_done("t2", "p2", "audio2", transcript, output_index=delta["output_index"])
                await feed(engine, socket, transcript_done)
                if defect == "duplicate_transcript_done":
                    await feed(engine, socket, {**transcript_done, "event_id": "duplicate-transcript-done"})
            done = audio_terminal(transcript="other" if defect == "wrong_transcript" else transcript)
            if defect == "missing_manifest":
                done["response"]["output"] = []
            if defect == "item_done_conflict":
                item = audio_terminal(transcript="other")["response"]["output"][0]
                await feed(engine, socket, provider_event("response.output_item.done", "item-done",
                    response_id="p2", output_index=0, item=item))
        await feed(engine, socket, done)
        await engine.acknowledge_presentation(response_ref(1))
        assert engine._prepared.output.discarded
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
        assert engine.snapshot().delegate_count == 0 and len(requests(socket)) == 2
        assert not engine._responses["p1"].cancelled and not engine._responses["p2"].presentation_acknowledged
        assert not any(action.operation == "SPEAK" and dict(action.payload).get("provider_response_id") == "p2"
                       for action in engine._action_port.accepted())
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_ack_first_terminal_schedules_refresh_without_blocking_single_reader_control():
    engine, socket, fresh = await preparing_engine()
    entered, release, stopped = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen = []
    async def refresh():
        entered.set()
        await release.wait()
        return fresh
    async def sole_reader():
        while True:
            event = await engine.next_event()
            seen.append(event)
            if event.action is not None and event.action.operation == "STOP":
                await engine.stop_foreground(response_ref(1))
            if event.action is not None and event.action.operation == "LISTEN":
                stopped.set()
    reader = None
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await feed(engine, socket, output_audio_done("audio-done-2", "p2", "audio2"))
        await feed(engine, socket, output_transcript_done("t2", "p2", "audio2", "verified"))
        await engine.acknowledge_presentation(response_ref(1))
        engine._business_refresh = refresh
        reader = asyncio.create_task(sole_reader())
        socket.push(audio_terminal(transcript="verified"))
        await asyncio.wait_for(entered.wait(), .5)
        scheduler = engine._continuation_scheduler
        for _ in range(20):
            assert engine._schedule_provider_response() is scheduler
        socket.push(speech_started("s2", "u2", 700))
        await asyncio.wait_for(stopped.wait(), .5)
        assert engine._input_item_id == "u2" and not release.is_set()
        assert scheduler is engine._continuation_scheduler and not scheduler.done()
        release.set()
        await asyncio.wait_for(scheduler, .5)
        assert engine._prepared.output.discarded and not engine._prepared_replay
        assert not any(event.action and event.action.operation == "SPEAK" for event in seen)
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        release.set()
        if reader is not None:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("resists_cancel", [False, True])
async def test_close_during_promotion_refresh_cannot_revive_and_owns_bounded_scheduler(resists_cancel):
    engine, socket, fresh = await preparing_engine()
    entered, release = asyncio.Event(), asyncio.Event()
    async def refresh():
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            if not resists_cancel:
                raise
            await release.wait()
        return fresh
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await complete_audio(engine, socket)
        engine._business_refresh = refresh
        ack = asyncio.create_task(engine.acknowledge_presentation(response_ref(1)))
        await asyncio.wait_for(entered.wait(), .5)
        scheduler = engine._continuation_scheduler
        before = tuple(socket.sent)
        closed = await asyncio.wait_for(engine.close(), .3)
        assert closed is (not resists_cancel)
        assert await asyncio.wait_for(ack, .2)
        assert not engine._prepared_replay and engine._promoting is None and not engine._pending_events
        release.set()
        await asyncio.wait_for(asyncio.shield(scheduler), .5)
        await asyncio.sleep(0)
        assert engine._continuation_scheduler is None
        assert await engine.close()
        assert engine.snapshot().state is NativeProviderState.CLOSED
        assert tuple(socket.sent) == before and engine._schedule_provider_response() is None
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        release.set()
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["exception", "timeout"])
async def test_scheduler_fault_wakes_waiting_single_reader_and_never_publishes(monkeypatch, fault):
    from jiuwenswarm.server.live_voice import openai_realtime_native_engine as module
    engine, socket, _ = await preparing_engine()
    entered = asyncio.Event()
    async def refresh():
        entered.set()
        if fault == "exception":
            raise RuntimeError("injected context failure")
        await asyncio.Event().wait()
    reader = None
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await feed(engine, socket, output_audio_done("audio-done-2", "p2", "audio2"))
        await feed(engine, socket, output_transcript_done("t2", "p2", "audio2", ""))
        await engine.acknowledge_presentation(response_ref(1))
        engine._business_refresh = refresh
        monkeypatch.setattr(module, "_CONTINUATION_SCHEDULER_TIMEOUT_SECONDS", .02)
        async def sole_reader():
            while True:
                assert await engine.next_event() == NativeEngineEvent()
        reader = asyncio.create_task(sole_reader())
        socket.push(audio_terminal())
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await asyncio.wait_for(reader, .5)
        reason = "NATIVE_CONTINUATION_SCHEDULER_FAILED" if fault == "exception" else "NATIVE_CONTINUATION_SCHEDULER_TIMEOUT"
        assert engine.snapshot().primary_error_reason == reason
        assert engine.take_continuation_failure()[1] == reason
        assert engine._schedule_provider_response() is None and engine._prepared.output.discarded
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        if reader is not None:
            await asyncio.gather(reader, return_exceptions=True)
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("name,arguments,operation", [
    ("jiuwen_context_get", {"request_text": "Read current context", "context_id": None}, "context.get"),
    ("jiuwen_work_get", {"request_text": "Read completed analysis", "context_id": "a" * 64,
        "target_id": "work-1"}, "work.get"),
    ("jiuwen_task_create", {"request_text": "Create a report", "context_id": "a" * 64,
        "name": "Report", "instruction": "Create the requested report"}, "task.create"),
    ("jiuwen_business", None, "context.get"),
])
async def test_prepared_named_and_legacy_tools_preserve_receive_time_and_delegate_only_after_admission(
        monkeypatch, name, arguments, operation):
    from jiuwenswarm.server.live_voice import openai_realtime_native_engine as module
    observed = []
    monkeypatch.setattr(module, "profile_snapshot_event", lambda event, identities, **fields:
        observed.append((dict(identities), fields, asyncio.get_running_loop().time())))
    engine, socket, _ = await preparing_engine()
    try:
        call = business_function("f2", "p2", "call2")
        call["name"] = name
        if arguments is not None:
            call["arguments"] = json.dumps(arguments)
        delta = provider_event("response.function_call_arguments.delta", "argument-delta-2", response_id="p2",
            item_id=call["item_id"], output_index=0, call_id=call["call_id"], delta=call["arguments"])
        await feed(engine, socket, delta)
        await feed(engine, socket, call)
        await feed(engine, socket, function_terminal(call))
        before = [(identities, fields, when) for identities, fields, when in observed
                  if identities.get("provider_response_id") == "p2"
                  and fields.get("milestone") in {"arguments_first_delta", "arguments_completed"}]
        assert [fields["milestone"] for _, fields, _ in before] == ["arguments_first_delta", "arguments_completed"]
        assert all(identities.get("response_id") is None and identities.get("response_generation") is None
                   for identities, _, _ in before)
        assert engine.snapshot().delegate_count == 0 and not engine._delegates
        await asyncio.sleep(.03)
        await engine.acknowledge_presentation(response_ref(1))
        assert action_payload(await next_output(engine))["provider_response_id"] == "p2"
        await engine.admit_response("p2", response_ref(2))
        admission_time = asyncio.get_running_loop().time()
        delegate = (await next_output(engine)).delegate
        assert delegate.business.operation == operation and delegate.provider_call_id == "call2"
        assert engine.snapshot().delegate_count == 1
        after = [(identities, fields, when) for identities, fields, when in observed
                 if identities.get("provider_response_id") == "p2"
                 and fields.get("milestone") in {"arguments_first_delta", "arguments_completed"}]
        assert after == before and before[-1][2] <= admission_time - .02
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_first_prepared_audio_profile_uses_receive_time_without_future_runtime_identity(monkeypatch):
    from jiuwenswarm.server.live_voice import openai_realtime_native_engine as module
    observed = []
    monkeypatch.setattr(module, "profile_snapshot_event", lambda event, identities, **fields:
        observed.append((dict(identities), fields, asyncio.get_running_loop().time())))
    engine, socket, _ = await preparing_engine()
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        await complete_audio(engine, socket)
        received = [(identities, fields, when) for identities, fields, when in observed
                    if identities.get("provider_response_id") == "p2" and fields.get("milestone") == "provider_first_audio"]
        assert len(received) == 1 and received[0][1]["source_event_id"] == "a2"
        assert received[0][0].get("response_id") is None and received[0][0].get("response_generation") is None
        await asyncio.sleep(.03)
        await engine.acknowledge_presentation(response_ref(1))
        await next_output(engine)
        await engine.admit_response("p2", response_ref(2))
        assert (await next_output(engine)).audio.response == response_ref(2)
        assert asyncio.get_running_loop().time() - received[0][2] >= .02
        assert [(identities, fields, when) for identities, fields, when in observed
                if identities.get("provider_response_id") == "p2" and fields.get("milestone") == "provider_first_audio"] == received
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("retirement", ["close", "work_removed", "speech"])
async def test_refresh_before_work_creation_cannot_send_facts_from_retired_source(retirement):
    engine, socket, fresh = await preparing_engine(prepare=False)
    entered, release = asyncio.Event(), asyncio.Event()
    async def refresh():
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return fresh
    update = None
    try:
        engine._business_refresh = refresh
        fresh["work_events"] = [work_event()]
        before = tuple(socket.sent)
        update = asyncio.create_task(engine.update_business_context(fresh["context"], fresh["work_events"]))
        await asyncio.wait_for(entered.wait(), .5)
        scheduler = engine._continuation_scheduler
        retirement_task = None
        if retirement == "close":
            assert not await engine.close()
        elif retirement == "work_removed":
            retirement_task = asyncio.create_task(engine.update_business_context(fresh["context"], []))
            await asyncio.sleep(0)
            assert engine._work_events == {}
        else:
            socket.push(speech_started("s2", "u2", 700))
            event = await engine.next_event()
            assert event.action.operation == "STOP"
            await engine.stop_foreground(response_ref(1))
        release.set()
        await asyncio.wait_for(scheduler, .5)
        await asyncio.wait_for(update, .5)
        if retirement_task is not None:
            await asyncio.wait_for(retirement_task, .5)
        assert tuple(socket.sent) == before and engine._inflight_response_request is None
        assert engine._prepared is None and engine.snapshot().released_audio_count == 1
    finally:
        release.set()
        if update is not None:
            await asyncio.gather(update, return_exceptions=True)
        await engine.close()


def test_discarded_preparation_retains_only_bounded_cleanup_identities():
    from jiuwenswarm.server.live_voice.openai_realtime_session import OpenAIRealtimeEvent
    output = preparation.PreparedProviderOutput("p2")
    output.discard()
    for index in range(65):
        data = output_audio_delta(f"a{index}", "p2", f"audio{index}", 0)
        event = OpenAIRealtimeEvent(data["type"], data["event_id"], json.dumps(data).encode("utf-8"))
        if index < 64:
            output.observe(event, data)
        else:
            with pytest.raises(preparation.PreparedOutputViolation) as error:
                output.observe(event, data)
            assert error.value.reason == "NATIVE_PREPARED_CLEANUP_IDENTITY_OVERFLOW"
    assert len(output.audio_targets) == 64 and output.cleanup_unsupported
    assert not output.events and not output._item_done and not output._transcript_partial and not output._calls


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_send", ["facts", "response_create"])
async def test_scheduler_socket_failure_wakes_reader_even_if_send_already_marked_engine_failed(failing_send):
    engine, socket, fresh = await preparing_engine(prepare=False)
    reader = None
    try:
        reader = asyncio.create_task(engine.next_event())
        await asyncio.sleep(0)
        socket.fail_send_at = socket.send_calls + (1 if failing_send == "facts" else 2)
        fresh["work_events"] = [work_event()]
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await engine.update_business_context(fresh["context"], fresh["work_events"])
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await asyncio.wait_for(reader, .5)
        assert engine.snapshot().state is NativeProviderState.FAILED
        assert engine.take_continuation_failure()[1] == engine.snapshot().primary_error_reason
        assert engine._schedule_provider_response() is None and engine._prepared is None
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        if reader is not None:
            await asyncio.gather(reader, return_exceptions=True)
        await engine.close()


def captured_audio_shape_events():
    """2026-09-07 real gpt-realtime-2 synthetic capture, stable IDs/zero PCM.

    Retains the captured event ordering, chunk sample counts, padding field,
    phase, metadata and terminal shape; no remote calls or private input.
    """
    transcript = "The verified task result is ready."
    added = {"content": [], "id": "audio2", "phase": "final_answer", "role": "assistant",
             "status": "in_progress", "type": "message"}
    completed = {**added, "status": "completed", "content": [{"type": "output_audio", "transcript": transcript}]}
    yield provider_event("response.output_item.added", "captured-item-added", response_id="p2", output_index=0, item=added)
    yield provider_event("response.content_part.added", "captured-part-added", response_id="p2", item_id="audio2",
                         output_index=0, content_index=0, part={"type": "audio", "transcript": ""})
    for index, text in enumerate(["The", " verified", " task", " result", " is", " ready"]):
        yield provider_event("response.output_audio_transcript.delta", f"captured-text-{index}", response_id="p2",
            item_id="audio2", output_index=0, content_index=0, delta=text, obfuscation="opaque-padding")
    yield output_audio_delta("captured-audio-0", "p2", "audio2", 0, pcm16=bytes(19200))
    yield provider_event("response.output_audio_transcript.delta", "captured-text-6", response_id="p2",
        item_id="audio2", output_index=0, content_index=0, delta=".", obfuscation="opaque-padding")
    for index, count in enumerate([19200, 19200, 19200, 19200, 4800], 1):
        yield output_audio_delta(f"captured-audio-{index}", "p2", "audio2", 0, pcm16=bytes(count))
    yield output_audio_done("captured-audio-done", "p2", "audio2")
    yield output_transcript_done("captured-transcript-done", "p2", "audio2", transcript)
    yield provider_event("response.content_part.done", "captured-part-done", response_id="p2", item_id="audio2",
                         output_index=0, content_index=0, part={"type": "audio", "transcript": transcript})
    yield provider_event("response.output_item.done", "captured-item-done", response_id="p2", output_index=0, item=completed)
    done = response_done("captured-done", "p2")
    done["response"]["output"] = [completed]
    yield done


@pytest.mark.asyncio
async def test_captured_realtime_audio_shape_is_verified_before_paced_admitted_replay():
    engine, socket, _ = await preparing_engine(event_queue_capacity=256)
    try:
        for event in captured_audio_shape_events():
            assert await feed(engine, socket, event) == NativeEngineEvent()
        assert not engine._prepared.output.discarded and engine._prepared.output.terminal
        assert engine._responses["p2"].runtime_ref is None and engine.snapshot().released_audio_count == 1
        await engine.acknowledge_presentation(response_ref(1))
        assert action_payload(await next_output(engine))["provider_response_id"] == "p2"
        await engine.admit_response("p2", response_ref(2))
        samples, done = 0, None
        while done is None:
            event = await next_output(engine)
            if event.audio is not None:
                samples += event.audio.provider_sample_count
            done = event.provider_done
        assert samples == 50400 and done.completed and done.transcript == "The verified task result is ready."
        assert engine.snapshot().delegate_count == 0 and not engine._responses["p2"].presentation_acknowledged
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["commentary", "null_phase", "unknown_field", "text", "transcript_conflict"])
async def test_captured_terminal_alias_does_not_admit_commentary_unknown_fields_or_changed_facts(defect):
    engine, socket, _ = await preparing_engine(event_queue_capacity=256)
    try:
        events = list(captured_audio_shape_events())
        terminal = events[-1]["response"]["output"][0]
        if defect == "commentary":
            terminal["phase"] = "commentary"
        elif defect == "null_phase":
            terminal["phase"] = None
        elif defect == "unknown_field":
            terminal["unknown"] = True
        elif defect == "text":
            terminal["content"][0] = {"type": "text", "text": "unverified commentary"}
        else:
            terminal["content"][0]["transcript"] = "changed result"
        for event in events:
            await feed(engine, socket, event)
        assert engine._prepared.output.discarded and engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        await engine.close()


async def consume_provider_control(engine, socket, event):
    """One sequential next_event consumer; deliberately does not await scheduler."""
    socket.push(event)
    for _ in range(8):
        result = await engine.next_event()
        if event["event_id"] in engine._processed_event_ids:
            return result
    raise AssertionError("Provider control was not consumed by the sole reader")


def truncate_ack(event_id="early-ack", **changes):
    return provider_event("conversation.item.truncated", event_id, **{
        "item_id": "audio2", "content_index": 0, "audio_end_ms": 0, **changes})


def control_error(event_id, request_id, *, cancel=False, **changes):
    return provider_event("error", event_id, error={
        "type": "invalid_request_error", "code": "response_cancel_not_active" if cancel else "invalid_value",
        "message": "Synthetic control error", "param": None, "event_id": request_id, **changes})


async def pending_control_send(monkeypatch, *, cancel=False, pre_intention_ack=False, fail_after_write=False):
    monkeypatch.setattr(preparation, "MAX_PREPARED_OUTPUT_BYTES", 1024)
    engine, socket, _ = await preparing_engine(session_config=engine_config(operation_timeout_seconds=1.0))
    if fail_after_write:
        original_send = socket.send
        async def failing_send(message):
            await original_send(message)
            if json.loads(message)["type"] == ("response.cancel" if cancel else "conversation.item.truncate"):
                raise OSError("Synthetic failure after control bytes were written")
        socket.send = failing_send
    if pre_intention_ack:
        await feed(engine, socket, truncate_ack("unsolicited-before-intention"))
    if cancel:
        socket.block_send_at = socket.send_calls + 1
        await consume_provider_control(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
    else:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        socket.block_send_at = socket.send_calls + 1
        await consume_provider_control(engine, socket, response_done("d2", "p2", status="cancelled"))
    await asyncio.wait_for(socket.send_entered.wait(), .5)
    assert socket.sent[-1]["type"] == ("response.cancel" if cancel else "conversation.item.truncate")
    return engine, socket, engine._prepared, engine._continuation_scheduler


@pytest.mark.asyncio
async def test_early_exact_truncate_ack_counts_only_after_successful_send_and_exact_played_ack(monkeypatch):
    engine, socket, prepared, scheduler = await pending_control_send(monkeypatch)
    try:
        assert prepared.output.pending_truncate == ("audio2", 0)
        await consume_provider_control(engine, socket, truncate_ack())
        await consume_provider_control(engine, socket, truncate_ack("duplicate-early-ack"))
        assert not prepared.output.truncate_sent and not prepared.output.truncate_acknowledged
        assert prepared.output._early_truncate_ack and not prepared.output.cleanup_complete
        assert engine._prepared is prepared and len(requests(socket)) == 2
        socket.release_send.set()
        await asyncio.wait_for(scheduler, .5)
        assert prepared.output.truncate_sent == {("audio2", 0)}
        assert prepared.output.truncate_acknowledged == {("audio2", 0)}
        assert prepared.output.cleanup_complete and prepared.output.pending_truncate is None
        assert engine._prepared is None and len(requests(socket)) == 2
        await engine.acknowledge_presentation(response_ref(1))
        assert len(requests(socket)) == 3 and engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"item_id": "audio1"}, {"item_id": "foreign"}, {"item_id": []}, {"item_id": {}},
    {"content_index": 1}, {"content_index": True}, {"audio_end_ms": 1}, {"audio_end_ms": False},
])
async def test_wrong_or_unsolicited_truncate_receipts_cannot_fill_pending_latch(monkeypatch, changes):
    engine, socket, prepared, scheduler = await pending_control_send(monkeypatch, pre_intention_ack=True)
    try:
        await consume_provider_control(engine, socket, truncate_ack("wrong-early-ack", **changes))
        # Replaying an earlier unsolicited receipt cannot make it newly valid.
        socket.push(truncate_ack("unsolicited-before-intention"))
        assert await engine.next_event() == NativeEngineEvent()
        assert not prepared.output._early_truncate_ack and not prepared.output.truncate_acknowledged
        socket.release_send.set()
        await asyncio.wait_for(scheduler, .5)
        await engine.acknowledge_presentation(response_ref(1))
        assert not prepared.output.cleanup_complete and engine._prepared is prepared and len(requests(socket)) == 2
        await consume_provider_control(engine, socket, truncate_ack("actual-late-ack"))
        await asyncio.wait_for(engine._continuation_scheduler, .5)
        assert prepared.output.cleanup_complete and len(requests(socket)) == 3
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["send_failure", "timeout", "cancelled", "close"])
async def test_early_truncate_ack_never_confirms_failed_unknown_or_closed_send(monkeypatch, outcome):
    engine, socket, prepared, scheduler = await pending_control_send(monkeypatch, fail_after_write=outcome == "send_failure")
    try:
        await consume_provider_control(engine, socket, truncate_ack())
        reader = asyncio.create_task(engine.next_event())
        await asyncio.sleep(0)
        if outcome == "send_failure":
            # The real Session wraps a socket failure after bytes were written.
            socket.release_send.set()
        elif outcome == "timeout":
            await asyncio.wait_for(scheduler, 1.5)
        elif outcome == "cancelled":
            scheduler.cancel()
        else:
            assert await engine.close()
        await asyncio.gather(scheduler, return_exceptions=True)
        await asyncio.wait_for(asyncio.gather(reader, return_exceptions=True), .5)
        assert not prepared.output.truncate_sent and not prepared.output.truncate_acknowledged
        assert not prepared.output.cleanup_complete and prepared.output.pending_truncate is None
        assert not prepared.output._early_truncate_ack and prepared.pending_truncation is None
        assert engine._schedule_provider_response() is None and len(requests(socket)) == 2
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("error_kind", ["exact", "foreign", "conflicting", "malformed", "missing_id"])
async def test_early_truncate_error_reconciles_before_ack_or_fails_closed(monkeypatch, error_kind):
    engine, socket, prepared, scheduler = await pending_control_send(monkeypatch)
    try:
        request_id = socket.sent[-1]["event_id"]
        await consume_provider_control(engine, socket, truncate_ack())
        error = control_error("early-error", "foreign-id" if error_kind == "foreign" else request_id)
        if error_kind == "malformed":
            error["error"]["extra"] = True
        elif error_kind == "missing_id":
            error["error"]["event_id"] = None
        if error_kind in {"malformed", "missing_id"}:
            with pytest.raises(OpenAIRealtimeNativeInteractionError):
                await consume_provider_control(engine, socket, error)
        else:
            await consume_provider_control(engine, socket, error)
            if error_kind == "conflicting":
                with pytest.raises(OpenAIRealtimeNativeInteractionError):
                    await consume_provider_control(engine, socket, control_error("conflicting-error", "other-id"))
        socket.release_send.set()
        await asyncio.wait_for(scheduler, .5)
        assert not prepared.output.truncate_acknowledged and not prepared.output.cleanup_complete
        assert prepared.output.pending_truncate is None and prepared.pending_truncation is None
        if error_kind == "exact":
            assert prepared.output.cleanup_unsupported and not prepared.retry
            assert engine.snapshot().state is not NativeProviderState.FAILED
            await engine.acknowledge_presentation(response_ref(1))
        else:
            assert engine.snapshot().state is NativeProviderState.FAILED
        assert len(requests(socket)) == 2 and engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("done_first", [False, True])
async def test_early_exact_cancel_not_active_is_harmless_only_after_send_receipt_and_real_terminal(monkeypatch, done_first):
    engine, socket, prepared, scheduler = await pending_control_send(monkeypatch, cancel=True)
    try:
        request_id = socket.sent[-1]["event_id"]
        if done_first:
            await consume_provider_control(engine, socket, audio_terminal())
        await consume_provider_control(engine, socket, control_error("early-cancel-error", request_id, cancel=True))
        assert engine._pending_provider_cancel.early_error_event_id == request_id
        assert "p2" not in engine._provider_cancel_receipts
        assert prepared.output.terminal is done_first and len(requests(socket)) == 2
        socket.release_send.set()
        await asyncio.wait_for(scheduler, .5)
        assert engine._pending_provider_cancel is None and engine._provider_cancel_receipts["p2"] == request_id
        assert engine.snapshot().state is not NativeProviderState.FAILED
        if not done_first:
            assert not prepared.output.terminal and not prepared.output.cleanup_complete
            await consume_provider_control(engine, socket, audio_terminal())
            await asyncio.wait_for(engine._continuation_scheduler, .5)
        await engine.acknowledge_presentation(response_ref(1))
        assert len(requests(socket)) == 2  # A cancel error never proves audio cleanup.
        await consume_provider_control(engine, socket, truncate_ack("late-cleanup-ack"))
        await asyncio.wait_for(engine._continuation_scheduler, .5)
        assert len(requests(socket)) == 3 and engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["foreign", "conflicting", "cancelled_send"])
async def test_early_cancel_error_unknown_or_conflicting_send_never_opens_generation(monkeypatch, defect):
    engine, socket, prepared, scheduler = await pending_control_send(monkeypatch, cancel=True)
    try:
        request_id = socket.sent[-1]["event_id"]
        await consume_provider_control(engine, socket, audio_terminal())
        await consume_provider_control(engine, socket,
            control_error("early-cancel-error", "foreign-id" if defect == "foreign" else request_id, cancel=True))
        if defect == "conflicting":
            with pytest.raises(OpenAIRealtimeNativeInteractionError):
                await consume_provider_control(engine, socket, control_error("conflicting-error", "different-id", cancel=True))
        if defect == "cancelled_send":
            scheduler.cancel()
        else:
            socket.release_send.set()
        await asyncio.wait_for(scheduler, .5)
        assert engine.snapshot().state is NativeProviderState.FAILED and engine._pending_provider_cancel is None
        assert "p2" not in engine._provider_cancel_receipts and not prepared.output.cleanup_complete
        assert len(requests(socket)) == 2 and engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
async def test_confirmed_cancel_receipt_takes_precedence_over_pending_truncate_error_latch(monkeypatch):
    engine, socket, prepared, scheduler = await pending_control_send(monkeypatch)
    try:
        prior_cancel_id = engine._provider_cancel_receipts["p2"]
        await consume_provider_control(engine, socket, control_error("late-exact-cancel-error", prior_cancel_id, cancel=True))
        assert prepared.pending_truncation.early_error_event_id is None
        assert not prepared.output.cleanup_unsupported and engine.snapshot().state is not NativeProviderState.FAILED
        await consume_provider_control(engine, socket, truncate_ack())
        socket.release_send.set()
        await asyncio.wait_for(scheduler, .5)
        assert prepared.output.cleanup_complete and engine._pending_provider_cancel is None
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
async def test_external_cancel_send_unknown_outcome_marks_failure_and_wakes_reader_without_scheduler():
    engine, socket, _ = await preparing_engine(session_config=engine_config(operation_timeout_seconds=1.0))
    sender = reader = None
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        assert engine._continuation_scheduler is None
        engine._discard_prepared_continuation("NATIVE_PREPARED_RESPONSE_INTERRUPTED")
        socket.block_send_at = socket.send_calls + 1
        # The existing cancellation helper is also used by public STOP/cursors.
        # Exercise its own failure owner, outside the continuation scheduler.
        sender = asyncio.create_task(engine._cancel_unpresented_response("p2"))
        await asyncio.wait_for(socket.send_entered.wait(), .5)
        async def sole_reader():
            while True:
                assert await engine.next_event() == NativeEngineEvent()
        reader = asyncio.create_task(sole_reader())
        await asyncio.sleep(0)
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        with pytest.raises(OpenAIRealtimeNativeInteractionError):
            await asyncio.wait_for(reader, .5)
        assert engine.snapshot().primary_error_reason == "NATIVE_PROVIDER_CONTROL_SEND_UNCONFIRMED"
        assert engine.snapshot().state is NativeProviderState.FAILED and engine._pending_provider_cancel is None
        assert engine._continuation_scheduler is None and not engine._provider_cancel_receipts
        assert len(requests(socket)) == 2 and engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        if reader is not None:
            await asyncio.gather(reader, return_exceptions=True)
        if sender is not None:
            await asyncio.gather(sender, return_exceptions=True)
        await engine.close()


@pytest.mark.asyncio
async def test_close_retires_external_pending_cancel_intention_before_send_returns():
    engine, socket, _ = await preparing_engine(session_config=engine_config(operation_timeout_seconds=1.0))
    sender = None
    try:
        await feed(engine, socket, output_audio_delta("a2", "p2", "audio2", 0))
        engine._discard_prepared_continuation("NATIVE_PREPARED_RESPONSE_INTERRUPTED")
        socket.block_send_at = socket.send_calls + 1
        sender = asyncio.create_task(engine._cancel_unpresented_response("p2"))
        await asyncio.wait_for(socket.send_entered.wait(), .5)
        assert engine._pending_provider_cancel is not None and engine._continuation_scheduler is None
        assert await engine.close()
        assert engine._pending_provider_cancel is None and engine._prepared is None
        socket.release_send.set()
        await asyncio.wait_for(sender, .5)
        assert engine.snapshot().state is NativeProviderState.CLOSED
        assert not engine._provider_cancel_receipts and engine._schedule_provider_response() is None
        assert len(requests(socket)) == 2 and engine.snapshot().released_audio_count == 1
    finally:
        socket.release_send.set()
        if sender is not None:
            await asyncio.gather(sender, return_exceptions=True)
        await engine.close()


@pytest.mark.asyncio
async def test_stop_and_following_listen_finish_before_unrelated_prepared_truncate_send(monkeypatch):
    engine, socket, prepared, scheduler = await pending_control_send(monkeypatch)
    try:
        stop = await consume_provider_control(engine, socket, speech_started("s2", "u2", 700))
        assert stop.action.operation == "STOP" and action_payload(stop)["provider_response_id"] == "p1"
        # Gateway awaits the complete STOP handler before consuming LISTEN.
        await asyncio.wait_for(engine.stop_foreground(response_ref(1)), .1)
        assert engine._responses["p1"].cancelled and "p1" in engine._locally_fenced
        assert (await asyncio.wait_for(engine.next_event(), .1)).action.operation == "LISTEN"
        assert engine._cancel_lock.locked() and not scheduler.done() and not socket.release_send.is_set()
        assert not engine._prepared_replay and not engine._pending_audio
        assert not any(item.audio is not None or item.provider_done is not None
                       or item.generated_transcript is not None or item.delegate is not None
                       for item in engine._pending_events)
        assert not engine._responses["p1"].presentation_acknowledged
        await consume_provider_control(engine, socket, truncate_ack())
        socket.release_send.set()
        await asyncio.wait_for(scheduler, .5)
        assert prepared.output.cleanup_complete and not prepared.retry
        assert len(requests(socket)) == 2 and engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("seam", ["cancel", "truncate"])
@pytest.mark.parametrize("outcome", ["close", "provider_error", "cancelled_send"])
async def test_public_cursor_control_send_cannot_continue_or_revive_after_close_failure_or_unknown_outcome(seam, outcome):
    engine, socket, _ = active_engine(speech_started("s1", "u1", 0),
        speech_stopped("e1", "u1", 500), input_committed("c1", "u1"), response_created("r1", "p1"),
        output_audio_delta("a1", "p1", "audio1", 0), session_config=engine_config(operation_timeout_seconds=1.0))
    sender = None
    try:
        await engine.start()
        await accept_basic_turn(engine)
        assert action_payload(await engine.next_event())["provider_response_id"] == "p1"
        await engine.admit_response("p1", response_ref(1))
        assert (await engine.next_event()).audio.response == response_ref(1)
        cursor = NativePresentationCursor(response=response_ref(1), provider_item_id="audio1",
            content_index=0, audio_end_ms=10)
        socket.block_send_at = socket.send_calls + (1 if seam == "cancel" else 2)
        sender = asyncio.create_task(engine.cancel_response(cursor))
        await asyncio.wait_for(socket.send_entered.wait(), .5)
        assert socket.sent[-1]["type"] == ("response.cancel" if seam == "cancel" else "conversation.item.truncate")
        written = tuple(socket.sent)
        if outcome == "close":
            assert await engine.close()
        elif outcome == "provider_error":
            with pytest.raises(OpenAIRealtimeNativeInteractionError):
                await consume_provider_control(engine, socket, control_error("fatal-error", "unrelated-client-event"))
        else:
            sender.cancel()
        socket.release_send.set()
        if outcome == "cancelled_send":
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(sender, .5)
        elif seam == "cancel":
            with pytest.raises(OpenAIRealtimeNativeInteractionError):
                await asyncio.wait_for(sender, .5)
        else:
            ids = await asyncio.wait_for(sender, .5)
            assert ids[1] == written[-1]["event_id"]
        assert tuple(socket.sent) == written and not engine._cancelled
        assert engine._pending_provider_cancel is None and engine._schedule_provider_response() is None
        assert engine.snapshot().state is (NativeProviderState.CLOSED if outcome == "close" else NativeProviderState.FAILED)
        assert not engine._responses["p1"].presentation_acknowledged
        assert engine.snapshot().released_audio_count == 1 and not engine._delegates
    finally:
        socket.release_send.set()
        if sender is not None:
            await asyncio.gather(sender, return_exceptions=True)
        await engine.close()
