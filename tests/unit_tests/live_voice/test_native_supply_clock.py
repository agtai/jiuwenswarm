"""Prepared supply credit uses sample time, not processing time per frame."""
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice import openai_realtime_native_engine as native
from tests.unit_tests.live_voice.test_openai_realtime_native_engine import active_engine, response_ref


def test_processing_cost_does_not_accumulate_into_prepared_sample_deadline(monkeypatch):
    engine, _, _ = active_engine()
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(native.asyncio, "get_running_loop", lambda: SimpleNamespace(time=lambda: clock.now))
    engine._prepared_delivery_id = "p1"
    engine._prepared_next_audio_at = 100.0
    audio = native.NativeAudioOutput(provider_event_id="audio1", provider_response_id="p1",
        provider_item_id="item1", content_index=0, sequence=0, pcm16=b"\x01\x00" * 480,
        response=response_ref(1), provider_sample_count=480)
    event = native.NativeEngineEvent(audio=audio)
    for _ in range(100):
        clock.now += .005
        engine._release_event(event)
    assert engine._prepared_next_audio_at == pytest.approx(102.0)
    assert engine.snapshot().released_audio_count == 100


def test_long_stall_cannot_accumulate_unbounded_catchup_credit(monkeypatch):
    engine, _, _ = active_engine()
    monkeypatch.setattr(native.asyncio, "get_running_loop", lambda: SimpleNamespace(time=lambda: 200.0))
    engine._prepared_delivery_id = "p1"
    engine._prepared_next_audio_at = 100.0
    audio = native.NativeAudioOutput(provider_event_id="audio1", provider_response_id="p1",
        provider_item_id="item1", content_index=0, sequence=0, pcm16=b"\x01\x00" * 480,
        response=response_ref(1), provider_sample_count=120)
    engine._release_event(native.NativeEngineEvent(audio=audio))
    # Count real Provider samples, excluding transport padding on a final frame.
    assert engine._prepared_next_audio_at == pytest.approx(200.0 - .320 + .005)
