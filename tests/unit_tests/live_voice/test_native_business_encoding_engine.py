"""Provider receipt compaction cannot change original Native replay authority."""
import asyncio
import hashlib
import json

import pytest

from jiuwenswarm.server.live_voice import openai_realtime_native_engine as native
from tests.unit_tests.live_voice.test_openai_realtime_native_engine import (
    accept_basic_turn, active_engine, admitted_business_engine, business_function,
    function_done, function_outputs, input_committed, response_created, response_done,
    response_ref, speech_started, speech_stopped,
)


@pytest.mark.asyncio
async def test_provider_encoding_preserves_original_digest_concurrent_replay_and_full_facts():
    engine, socket, _ = await admitted_business_engine(business_function("f1", "p1", "call1"), response_done("done1", "p1"))
    try:
        assert (await engine.next_event()).delegate is not None
        await engine.next_event()
        facts = {"result_text": "真实中文结果和完整尾部 🚀", "context": {"revision": 3}}
        original = json.dumps(facts, ensure_ascii=True, separators=(",", ":"))
        ids = await asyncio.gather(*[engine.send_delegate_result("call1", response_ref(1), original) for _ in range(3)])
        assert ids[0] == ids[1] == ids[2]
        outputs = function_outputs(socket)
        assert len(outputs) == 1 and outputs[0]["call_id"] == "call1"
        delivered = outputs[0]["output"]
        assert json.loads(delivered) == facts
        assert len(delivered.encode("utf-8")) < len(original.encode("utf-8"))
        assert engine._delegate_results["call1"].digest == hashlib.sha256(original.encode("utf-8")).hexdigest()
        before = tuple(socket.sent)
        with pytest.raises(native.OpenAIRealtimeNativeInteractionError) as changed:
            await engine.send_delegate_result("call1", response_ref(1), delivered)
        assert changed.value.reason == "NATIVE_DELEGATE_RESULT_CONFLICT"
        assert tuple(socket.sent) == before
        assert engine.snapshot().delegate_count == 1 and engine.snapshot().released_audio_count == 0
        assert not engine._responses["p1"].presentation_acknowledged
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_wrong_source_oversized_and_stopped_receipts_never_enter_encoder(monkeypatch):
    calls = []
    monkeypatch.setattr(native, "compact_native_business_output", lambda value: calls.append(value) or value)
    engine, socket, _ = await admitted_business_engine(business_function("f1", "p1", "call1"))
    try:
        await engine.next_event()
        before = tuple(socket.sent)
        with pytest.raises(native.OpenAIRealtimeNativeInteractionError) as wrong:
            await engine.send_delegate_result("call1", response_ref(2), '{"truth":true}')
        assert wrong.value.reason == "NATIVE_DELEGATE_SOURCE_MISMATCH"
        oversized = json.dumps({"text": "中" * 90000}, ensure_ascii=True)
        with pytest.raises(native.OpenAIRealtimeNativeInteractionError) as large:
            await engine.send_delegate_result("call1", response_ref(1), oversized)
        assert large.value.reason == "NATIVE_DELEGATE_RESULT_INVALID"
        assert not calls and tuple(socket.sent) == before
        await engine.retire_delegate("call1", interrupted=True)
        before = tuple(socket.sent)
        with pytest.raises(native.OpenAIRealtimeNativeInteractionError) as retired:
            await engine.send_delegate_result("call1", response_ref(1), '{"truth":true}')
        assert retired.value.reason == "NATIVE_DELEGATE_INTERRUPTED"
        assert not calls and tuple(socket.sent) == before
        assert engine.snapshot().released_audio_count == 0 and not engine._delegate_results
        assert not engine._responses["p1"].presentation_acknowledged
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_legacy_delegate_and_diagnostics_are_unchanged(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Native-business-only code reached by legacy route")
    monkeypatch.setattr(native, "compact_native_business_output", forbidden)
    monkeypatch.setattr(native, "profile_snapshot_event", forbidden)
    engine, socket, _ = active_engine(speech_started("s", "u", 0), speech_stopped("e", "u", 20),
        input_committed("c", "u"), response_created("r", "p1"), function_done("f", "p1"), response_done("d", "p1"))
    try:
        await engine.start()
        await accept_basic_turn(engine)
        await engine.next_event()
        await engine.admit_response("p1", response_ref(1))
        await engine.next_event()
        await engine.next_event()
        original = json.dumps({"result": "原样回执"}, ensure_ascii=True)
        await engine.send_delegate_result("call-1", response_ref(1), original)
        assert function_outputs(socket)[0]["output"] == original
        assert engine._last_business_wait is None
    finally:
        await engine.close()
