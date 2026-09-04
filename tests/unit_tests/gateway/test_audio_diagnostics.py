import asyncio
import json
import queue

import pytest

from jiuwenswarm.common import live_voice_audio_diagnostics as diagnostics


@pytest.mark.asyncio
async def test_audio_diagnostics_allowlist_scalars_without_payload_or_secrets(monkeypatch):
    lines = []
    monkeypatch.setattr(diagnostics._LOGGER, "info", lambda template, *args: lines.append(template % args))
    diagnostics.record_audio_diagnostic("capture_progress", session_id="session-a", capture_id="capture-a",
        generation=3, queue_frames=5, transcript="PRIVATE_TEXT", pcm=b"PRIVATE_AUDIO",
        media_ticket="PRIVATE_TICKET", error="PRIVATE_SECRET", received_samples=float("nan"),
        response_id="bad\nPRIVATE_ID")
    diagnostics.record_audio_diagnostic("adapter_receive_failed",
        failure_code="PRIVATE_SECRET", wire_event="PRIVATE_TEXT",
        commit_owner="PRIVATE_AUDIO", http_phase="PRIVATE_ENDPOINT")
    await asyncio.to_thread(diagnostics._QUEUE.join)
    record = next(line for line in lines if "live_voice_audio_diagnostic" in line)
    payload = json.loads(record.split(" ", 1)[1])
    assert payload["fields"] == {"session_id": "session-a", "capture_id": "capture-a", "generation": 3, "queue_frames": 5}
    assert "PRIVATE" not in record
    assert payload["monotonic_ms"] > 0 and payload["observed_at"]
    assert "PRIVATE" not in "\n".join(lines)


@pytest.mark.asyncio
async def test_transport_diagnostics_allowlist_does_not_leak_proxy_or_peer(monkeypatch):
    lines = []
    monkeypatch.setattr(diagnostics._LOGGER, "info", lambda template, *args: lines.append(template % args))
    diagnostics.record_audio_diagnostic("socket_observer_attached", capture_id="capture-a",
        proxy_route_hint="https", peer_loopback=True, flow_observer=True,
        write_buffer_bytes=40000, drain_ms=2000, loop_lag_peak_ms=5,
        oldest_queue_age_ms=9000, pending_audio_ms=9160,
        proxy_url="https://PRIVATE_PASSWORD@proxy.invalid", peer="PRIVATE_IP", headers="PRIVATE_HEADER")
    diagnostics.record_audio_diagnostic("socket_observer_attached", proxy_route_hint="PRIVATE_PROXY")
    await asyncio.to_thread(diagnostics._QUEUE.join)
    assert "PRIVATE" not in repr(lines)
    payload = json.loads(lines[0].split(" ", 1)[1])["fields"]
    assert payload["proxy_route_hint"] == "https" and payload["peer_loopback"] is True
    assert payload["oldest_queue_age_ms"] == 9000 and payload["drain_ms"] == 2000


@pytest.mark.asyncio
async def test_throwing_sink_is_passive_and_bounded_queue_drops_without_wait(monkeypatch):
    await asyncio.to_thread(diagnostics._QUEUE.join)
    def fail(*args, **kwargs):
        raise RuntimeError("sink failed")
    monkeypatch.setattr(diagnostics._LOGGER, "info", fail)
    diagnostics.record_audio_diagnostic("provider_speech_started", generation=1)
    await asyncio.to_thread(diagnostics._QUEUE.join)
    private_queue = queue.Queue(maxsize=2)
    monkeypatch.setattr(diagnostics, "_QUEUE", private_queue)
    monkeypatch.setattr(diagnostics, "_WORKER", object())
    before = diagnostics._DROPPED
    for _ in range(100):
        diagnostics.record_audio_diagnostic("capture_progress", generation=1)
    assert private_queue.qsize() == 2
    assert diagnostics._DROPPED == before + 98
