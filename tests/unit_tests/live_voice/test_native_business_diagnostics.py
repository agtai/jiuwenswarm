"""Passive Native milestones keep business and presentation authority unchanged."""
import asyncio
import json

import pytest

from jiuwenswarm.common import live_voice_audio_diagnostics as sink
from jiuwenswarm.common import live_voice_profiling as profile
from jiuwenswarm.server.live_voice import openai_realtime_native_engine as native
from jiuwenswarm.server.live_voice import openai_realtime_session as transport
from scripts.live_voice.analyze_demo_profile import sanitize_record
from tests.unit_tests.live_voice.test_native_business_contract import action
from tests.unit_tests.live_voice.test_openai_realtime_native_engine import (
    admitted_business_engine, business_function, function_outputs,
    output_audio_delta, output_audio_done, response_created, response_done, response_ref,
)


@pytest.mark.parametrize("value,expected", [
    (None, {"argument_type": "null"}),
    (42, {"argument_type": "integer"}),
    (True, {"argument_type": "boolean"}),
    ([], {"argument_type": "array"}),
    ({"PRIVATE_KEY": "PRIVATE_VALUE"}, {"argument_type": "object"}),
    ("  ", {"argument_type": "string", "argument_blank": True, "argument_utf8_bytes": 2}),
    ("私密资料", {"argument_type": "string", "argument_blank": False, "argument_utf8_bytes": 12}),
    ("PRIVATE\u0000VALUE", {"argument_type": "string", "argument_has_nul": True}),
    ("\ud800", {"argument_type": "string", "argument_utf8_valid": False}),
])
def test_rejected_argument_shape_contains_only_closed_metadata(value, expected):
    fields = native._business_argument_shape(json.dumps({"action": {"instruction": value}}), "action.instruction")
    assert fields["argument_field"] == "action.instruction" and fields["argument_present"] is True
    assert all(fields[key] == item for key, item in expected.items())
    assert "PRIVATE" not in repr(fields) and "私密" not in repr(fields)


def test_missing_and_unparseable_arguments_are_distinguished_without_reading_values():
    missing = native._business_argument_shape('{"action":{}}', "action.instruction")
    assert missing == {"argument_field": "action.instruction", "argument_present": False, "argument_type": "missing"}
    for malformed in ("{", " " * 16385, 123):
        fields = native._business_argument_shape(malformed, "action.instruction")
        assert fields == {"argument_field": "action.instruction", "argument_type": "unknown"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_sink", [False, True])
async def test_argument_rejection_diagnostic_is_passive_exact_and_private(monkeypatch, failing_sink):
    records = []
    def observe(event, snapshot, **fields):
        if failing_sink:
            raise RuntimeError("PRIVATE_SINK_ERROR")
        records.append({**snapshot, **fields})
    monkeypatch.setattr(native, "profile_snapshot_event", observe)
    invalid = business_function("bad", "p1", "bad-call")
    invalid["arguments"] = json.dumps({"request_text": "PRIVATE_USER_REQUEST",
        "action": action("work.start", target_id=None, instruction=123)})
    engine, socket, _ = await admitted_business_engine(invalid, invalid)
    try:
        assert (await engine.next_event()).delegate is None
        outputs = list(function_outputs(socket))
        assert len(outputs) == 1 and json.loads(outputs[0]["output"])["execution_started"] is False
        assert (await engine.next_event()).delegate is None
        assert function_outputs(socket) == outputs
        assert engine.snapshot().delegate_count == 0 and engine._delegates == {}
        assert engine.snapshot().released_audio_count == 0
        assert not engine._responses["p1"].presentation_acknowledged
        assert "PRIVATE" not in repr(records)
        rejected = [r for r in records if r["milestone"] == "arguments_rejected"]
        if failing_sink:
            assert not records
        else:
            assert len(rejected) == 1
            assert rejected[0]["argument_type"] == "integer"
            assert rejected[0]["argument_field"] == "action.instruction"
            assert rejected[0]["session_id"] == "session-native"
            assert rejected[0]["activation_id"] == "native-activation-1"
            assert rejected[0]["response_id"] == "runtime-response-1"
            assert rejected[0]["provider_response_id"] == "p1"
            assert rejected[0]["provider_call_id"] == "bad-call"
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_timeline_distinguishes_send_confirmation_audio_and_actual_ack(monkeypatch):
    records = []
    monkeypatch.setattr(native, "profile_snapshot_event", lambda event, snapshot, **fields: records.append({**snapshot, **fields}))
    engine, socket, _ = await admitted_business_engine(business_function("f1", "p1", "call1"))
    try:
        assert (await engine.next_event()).delegate is not None
        await engine.send_delegate_result("call1", response_ref(1), '{"fact":"PRIVATE_RESULT"}')
        sent_before = tuple(socket.sent)
        for _ in range(4):
            await engine._request_pending_provider_response()
        assert tuple(socket.sent) == sent_before
        waits = [r for r in records if r["milestone"] == "response_wait" and r["reason"] == "response_generation"]
        assert len(waits) == 1
        assert not any(r["milestone"] == "presentation_acknowledged" for r in records)
        socket.push(response_done("done1", "p1"))
        await engine.next_event()
        socket.push(response_created("created2", "p2"))
        await engine.next_event()
        await engine.admit_response("p2", response_ref(2))
        socket.push(output_audio_delta("a1", "p2", "audio2", 0))
        socket.push(output_audio_delta("a2", "p2", "audio2", 0))
        await engine.next_event()
        await engine.next_event()
        socket.push(output_audio_done("ad", "p2", "audio2"))
        await engine.next_event()
        socket.push(response_done("done2", "p2"))
        await engine.next_event()
        assert any(r.get("reason") == "actual_playback" for r in records)
        assert not any(r["milestone"] == "presentation_acknowledged" for r in records)
        assert await engine.acknowledge_presentation(response_ref(2)) is True
        assert await engine.acknowledge_presentation(response_ref(2)) is False
        milestones = [r["milestone"] for r in records]
        assert milestones.index("response_send_started") < milestones.index("response_sent") < milestones.index("response_created")
        assert milestones.index("receipt_prepare_started") < milestones.index("receipt_send_started")
        assert milestones.index("receipt_send_started") < milestones.index("receipt_sent") < milestones.index("successor_queued")
        assert milestones.count("provider_first_audio") == 1
        assert milestones.count("presentation_acknowledged") == 1
        assert "PRIVATE" not in repr(records)
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_sink", [False, True])
async def test_audio_supply_timing_joins_provider_delta_without_changing_pcm_or_ack(monkeypatch, failing_sink):
    rows = []
    def observe(event, snapshot, **fields):
        if failing_sink:
            raise RuntimeError("PRIVATE_SINK_ERROR")
        rows.append({**snapshot, **fields})
    monkeypatch.setattr(native, "profile_snapshot_event", observe)
    monkeypatch.setattr(transport, "profile_snapshot_event", observe)
    engine, socket, _ = await admitted_business_engine()
    try:
        audio = []
        for index in range(2):
            socket.push(output_audio_delta(f"audio-{index}", "p1", "audio-item", 0))
            audio.append((await engine.next_event()).audio)
        assert [item.sequence for item in audio] == [0, 1]
        assert all(item.pcm16 == b"\x01\x00" * 480 for item in audio)
        assert not engine._responses["p1"].presentation_acknowledged
        assert not engine._delegates
        assert "PRIVATE" not in repr(rows)
        if not failing_sink:
            mapped = [row for row in rows if row["milestone"] == "provider_audio_mapped"]
            received = [row for row in rows if row.get("status") == "response.output_audio.delta"]
            assert [row["source_event_id"] for row in mapped] == ["audio-0", "audio-1"]
            assert [row["source_event_id"] for row in received] == ["audio-0", "audio-1"]
            assert [(row["frame_seq"], row["frame_count"]) for row in mapped] == [(0, 1), (1, 1)]
            assert all(row["received_monotonic_ms"] > 0 for row in received)
            assert not any(key in row for row in rows for key in ("delta", "pcm16", "text"))
        else:
            assert rows == []
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_new_diagnostics_survive_real_sink_and_offline_export_without_payload(monkeypatch):
    lines = []
    await asyncio.to_thread(sink._QUEUE.join)
    monkeypatch.setattr(sink._LOGGER, "info", lambda template, *args: lines.append(template % args))
    sink.record_audio_diagnostic("native_business_timeline", milestone="arguments_rejected",
        session_id="session-native", provider_response_id="provider-1", provider_call_id="call-1",
        argument_field="action.instruction", argument_type="string", argument_present=True,
        argument_chars=2, argument_utf8_bytes=6, argument_utf8_valid=True, argument_blank=False,
        argument_has_nul=False, arguments="PRIVATE_ARGUMENT", result="PRIVATE_RESULT")
    sink.record_audio_diagnostic("native_business_timeline", argument_field="PRIVATE_FIELD", argument_type="PRIVATE_TYPE")
    await asyncio.to_thread(sink._QUEUE.join)
    assert "PRIVATE" not in repr(lines)
    rows = [sanitize_record(json.loads(line.split(" ", 1)[1])) for line in lines]
    fields = next(row["fields"] for row in rows if row["fields"].get("provider_call_id") == "call-1")
    assert fields["argument_field"] == "action.instruction" and fields["argument_utf8_bytes"] == 6
    assert fields["provider_response_id"] == "provider-1"
    assert all(row["clock_id"] and row["monotonic_ms"] > 0 for row in rows)


@pytest.mark.asyncio
async def test_engine_diagnostics_do_not_inherit_an_unrelated_async_origin(monkeypatch):
    records = []
    monkeypatch.setattr(profile, "record_audio_diagnostic", lambda event, **fields: records.append((event, fields)))
    token = profile._CURRENT.set({"work_id": "foreign-work", "provider_call_id": "foreign-call", "turn_id": "foreign-turn"})
    engine = None
    try:
        engine, _, _ = await admitted_business_engine(business_function("f1", "p1", "call1"))
        await engine.next_event()
        rows = [fields for event, fields in records if event == "native_business_timeline"]
        assert rows and all(fields["_inherit_context"] is False for fields in rows)
        assert "foreign" not in repr(rows)
        assert all(fields["session_id"] == "session-native" for fields in rows)
    finally:
        if engine is not None:
            await engine.close()
        profile._CURRENT.reset(token)
