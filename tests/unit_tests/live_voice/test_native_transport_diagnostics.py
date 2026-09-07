"""P0 timing is passive, bounded and tied to the producing activation."""
import asyncio
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.live_voice_profiling import _CURRENT
from jiuwenswarm.server.live_voice import openai_realtime_native_engine as native
from jiuwenswarm.server.live_voice import openai_realtime_session as transport
from test_openai_realtime_native_engine import (
    admitted_business_engine, business_function, provider_event, speech_started, speech_stopped, input_committed,
)
from test_openai_realtime_session import (
    CapturingFactory, ScriptedRealtimeSocket, event, negotiated_events, realtime_config, session_update,
)
from test_demo_profiling import row
from scripts.live_voice import analyze_demo_profile as report


@pytest.mark.asyncio
@pytest.mark.parametrize("sink_fails", [False, True])
async def test_transport_timing_distinguishes_lock_send_and_receive_without_payload(monkeypatch, sink_fails):
    records = []
    def observe(name, origin, **fields):
        if sink_fails:
            raise RuntimeError("PRIVATE_SINK_FAILURE")
        records.append({"event": name, **origin, **fields})
        if fields["milestone"] == "socket_send_started":
            ticks[0] += 0.2  # Sink work must not be misattributed to transport.
    monkeypatch.setattr(transport, "profile_snapshot_event", observe)
    ticks = [10.0]
    monkeypatch.setattr(transport, "time", SimpleNamespace(perf_counter=lambda: ticks[0]))
    socket = ScriptedRealtimeSocket(negotiated_events())
    session = transport.OpenAIRealtimeSession(realtime_config(), socket_factory=CapturingFactory(socket),
        diagnostic_origin={"session_id": "origin", "activation_id": "a1", "PRIVATE_KEY": "PRIVATE_VALUE"})
    token = _CURRENT.set({"session_id": "unrelated-session", "work_id": "unrelated-work"})
    try:
        await session.open(session_update=session_update())
        await session._send_lock.acquire()
        blocked = asyncio.create_task(session.send_event("response.create", {"response": {"instructions": "PRIVATE_PROMPT"}}))
        await asyncio.sleep(0)
        assert not any(r.get("status") == "response.create" for r in records)
        assert session._send_lock._waiters
        ticks[0] += 0.02
        session._send_lock.release()
        sent_id = await blocked
        socket.push(event("input_audio_buffer.speech_stopped", "endpoint", item_id="i1", audio_end_ms=900))
        assert (await session.receive_event()).event_id == "endpoint"
        # High-frequency data is not logged, regardless of payload contents.
        await session.send_event("input_audio_buffer.append", {"audio": "PRIVATE_AUDIO"})
        if sink_fails:
            assert not records
        else:
            assert all(r["session_id"] == "origin" and r["activation_id"] == "a1" for r in records)
            assert "PRIVATE" not in repr(records) and "unrelated" not in repr(records)
            sent = [r for r in records if r["source_event_id"] == sent_id]
            assert [r["milestone"] for r in sent] == ["socket_send_started", "socket_send_completed"]
            assert sent[0]["lock_wait_ms"] == pytest.approx(20)
            assert sent[0]["encode_ms"] >= 0 and sent[1]["socket_send_ms"] == 0
            received = next(r for r in records if r["source_event_id"] == "endpoint")
            assert received["received_monotonic_ms"] > 0 and received["decode_ms"] >= 0
            assert not any(r["status"] == "input_audio_buffer.append" for r in records)
    finally:
        _CURRENT.reset(token)
        await session.close()
    assert socket.close_calls == 1


@pytest.mark.asyncio
async def test_transport_without_origin_stays_silent_and_failed_send_never_claims_completion(monkeypatch):
    records = []
    monkeypatch.setattr(transport, "profile_snapshot_event", lambda *args, **fields: records.append(fields))
    socket = ScriptedRealtimeSocket(negotiated_events(), send_failure_type="response.create")
    session = transport.OpenAIRealtimeSession(realtime_config(), socket_factory=CapturingFactory(socket))
    await session.open(session_update=session_update())
    assert records == []
    session._diagnostic_origin = {"session_id": "origin"}
    with pytest.raises(transport.OpenAIRealtimeSessionError, match="send failed"):
        await session.send_event("response.create", {})
    assert [r["milestone"] for r in records] == ["socket_send_started"]
    await session.close()


@pytest.mark.asyncio
async def test_first_argument_delta_is_bounded_per_response_and_has_zero_authority(monkeypatch):
    records = []
    monkeypatch.setattr(transport, "profile_snapshot_event", lambda *args, **fields: None)
    monkeypatch.setattr(native, "profile_snapshot_event", lambda event, snapshot, **fields: records.append({**snapshot, **fields}))
    engine, socket, _ = await admitted_business_engine()
    try:
        for index in range(12):
            item = f"item{min(index, 9)}"
            socket.push(provider_event("response.function_call_arguments.delta", f"delta{index}",
                response_id="p1", item_id=item, delta="PRIVATE_ARGUMENTS", unexpected="PRIVATE_PAYLOAD"))
            emitted = await engine.next_event()
            assert emitted.delegate is None and emitted.audio is None and emitted.action is None
        for index, changes in enumerate(({"response_id": []}, {"response_id": "wrong"}, {"item_id": []}, {"delta": None})):
            payload = {"response_id": "p1", "item_id": "x", "delta": "PRIVATE", **changes}
            socket.push(provider_event("response.function_call_arguments.delta", f"bad{index}", **payload))
            assert (await engine.next_event()).delegate is None
        first = [r for r in records if r["milestone"] == "arguments_first_delta"]
        assert len(first) == 8 and len({r["provider_item_id"] for r in first}) == 8
        assert all(r["provider_response_id"] == "p1" and r["response_id"] == "runtime-response-1" for r in first)
        assert engine._delegates == {} and engine.snapshot().released_audio_count == 0
        assert "PRIVATE" not in repr(records)
        socket.push(business_function("complete", "p1", "call1"))
        assert (await engine.next_event()).delegate is not None
        assert any(r["milestone"] == "arguments_completed" and r["provider_call_id"] == "call1" and r["provider_item_id"] for r in records)
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_second_endpoint_joins_input_item_without_borrowing_prior_turn(monkeypatch):
    records = []
    monkeypatch.setattr(native, "profile_snapshot_event", lambda event, snapshot, **fields: records.append({**snapshot, **fields}))
    monkeypatch.setattr(transport, "profile_snapshot_event", lambda *args, **fields: None)
    engine, socket, _ = await admitted_business_engine()
    prior_turn = engine._current_turn_id
    try:
        socket.push(speech_started("start2", "input2", 600))
        await engine.next_event()
        while engine._pending_events:
            await engine.next_event()
        socket.push(speech_stopped("end2", "input2", 900))
        await engine.next_event()
        endpoint = next(r for r in records if r.get("source_event_id") == "end2")
        assert endpoint["provider_item_id"] == "input2" and endpoint.get("turn_id") is None
        socket.push(input_committed("commit2", "input2"))
        await engine.next_event()
        committed = next(r for r in records if r.get("source_event_id") == "commit2")
        assert committed["provider_item_id"] == "input2"
        assert committed["turn_id"] == engine._current_turn_id != prior_turn
        assert committed["turn_commit_id"]
        assert engine._delegates == {} and engine.snapshot().released_audio_count == 0
    finally:
        await engine.close()


def test_offline_native_timings_never_pair_reused_client_ids_across_activations_or_clocks():
    def observation(seq, ms, milestone, activation="a1", clock="process-a", **fields):
        return row("native_transport_timeline", seq, ms, clock=clock, session_id="session", activation_id=activation,
                   source_event_id="client_event_00000001", status="response.create", milestone=milestone, **fields)
    rows = [observation(1, 10, "socket_send_started"),
            observation(2, 100, "socket_send_completed", activation="a2"),
            observation(3, 11, "socket_send_completed", clock="process-b"),
            observation(4, 15, "socket_send_completed", socket_send_ms=5),
            observation(5, 20, "socket_send_started", activation="open")]
    for seq, ms, milestone in ((6, 30, "arguments_first_delta"), (7, 37, "arguments_completed")):
        rows.append(row("native_business_timeline", seq, ms, session_id="session", activation_id="a1",
                        provider_response_id="p1", provider_item_id="i1", milestone=milestone))
    result = report.build_report(rows)
    spans = result["spans"]
    assert len([span for span in spans if span["state"] == "start_missing"]) == 2
    assert len([span for span in spans if span["state"] == "open_or_truncated"]) == 1
    assert [span["duration_ms"] for span in spans if span["duration_ms"] is not None] == [5, 7]
    assert result["coverage"]["Native transport / endpoint"] == 5
