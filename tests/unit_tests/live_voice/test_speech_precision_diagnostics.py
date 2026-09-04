"""Deterministic diagnostic oracles; no physical-audio acceptance credit."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from jiuwenswarm.server.live_voice import batch_speech as batch
from jiuwenswarm.server.live_voice import openai_streaming_speech as streaming
from jiuwenswarm.server.live_voice import speech_http_diagnostics as http_diagnostics
from tests.unit_tests.live_voice.test_batch_speech import (
    CONTEXT, _recognize_request, _service, _cancel_request,
)
from tests.unit_tests.live_voice.test_openai_streaming_speech import (
    FakeSocket, config, recognition_ref, recognition_frame, second_recognition_frame,
    session_updated_event, server_vad_wire, authorized_request,
    RecognitionStreamRequest, RecognitionTurnDetection, assert_zero_business_effects,
)
from tests.unit_tests.live_voice.speech_authority_support import speech_test_issuer


@pytest.mark.asyncio
async def test_stop_arrival_lock_and_publication_are_distinct_without_extra_audio(monkeypatch):
    records = []
    received = asyncio.Event()
    send_entered, release_send = asyncio.Event(), asyncio.Event()
    clock = [100.0]

    def observe(event, **fields):
        records.append((event, fields))
        if event == "adapter_stop_received":
            received.set()

    class BlockedSocket(FakeSocket):
        async def send(self, message):
            if json.loads(message)["type"] == "input_audio_buffer.append":
                send_entered.set()
                await release_send.wait()
            await super().send(message)

    socket = BlockedSocket((session_updated_event(server_vad_wire()),))
    async def factory(*args):
        return socket
    provider = streaming.OpenAIStreamingSpeechProvider(config(), socket_factory=factory)
    ref = recognition_ref()
    monkeypatch.setattr(streaming, "record_audio_diagnostic", observe)
    # Replace only this module's clock object, not asyncio's deadline clock.
    monkeypatch.setattr(streaming, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    try:
        await provider.open_recognition(authorized_request(RecognitionStreamRequest(
            ref, RecognitionTurnDetection.server_vad_default())), timeout_seconds=2)
        socket.push({"type": "input_audio_buffer.speech_started", "item_id": "private-item", "audio_start_ms": 10})
        await provider.next_recognition_event(ref, timeout_seconds=1)
        send = asyncio.create_task(provider.send_recognition_audio(recognition_frame(ref)))
        await asyncio.wait_for(send_entered.wait(), 1)
        clock[0] += 0.1
        socket.push({"type": "input_audio_buffer.speech_stopped", "item_id": "private-item", "audio_end_ms": 50})
        await asyncio.wait_for(received.wait(), 1)
        assert not any(e == "adapter_stop_published" for e, _ in records)
        late_send = asyncio.create_task(provider.send_recognition_audio(second_recognition_frame(ref)))
        clock[0] += 0.2
        release_send.set()
        await asyncio.gather(send, late_send)
        await provider.next_recognition_event(ref, timeout_seconds=1)
        acquired = next(f for e, f in records if e == "adapter_stop_lock_acquired")
        published = next(f for e, f in records if e == "adapter_stop_published")
        sent = next(f for e, f in records if e == "adapter_socket_send_settled" and f["frame_seq"] == 0)
        assert acquired["lock_wait_ms"] == pytest.approx(200)
        assert published["elapsed_ms"] == pytest.approx(200)
        assert sent["socket_send_ms"] == pytest.approx(300)
        assert sent["encode_ms"] == 0 and sent["lock_wait_ms"] == 0
        assert [m["type"] for m in socket.sent].count("input_audio_buffer.append") == 1
        assert [m["type"] for m in socket.sent].count("input_audio_buffer.commit") == 0
        assert "private-item" not in repr(records)
        assert_zero_business_effects(provider)
    finally:
        release_send.set()
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed,expected", [
    ({"type": "input_audio_buffer.speech_stopped", "item_id": "private-item", "audio_end_ms": 50}, "SPEECH_PROVIDER_TURN_ORDER"),
    ({"type": "PRIVATE_UNKNOWN_EVENT", "secret": "PRIVATE_KEY"}, "SPEECH_PROVIDER_UNKNOWN_EVENT"),
    ("PRIVATE_INVALID_JSON", "SPEECH_PROVIDER_INVALID_JSON"),
])
async def test_protocol_diagnostic_keeps_subcode_not_content(monkeypatch, malformed, expected):
    records = []
    monkeypatch.setattr(streaming, "record_audio_diagnostic", lambda e, **f: records.append((e, f)))
    socket = FakeSocket((session_updated_event(server_vad_wire()),))
    async def factory(*args):
        return socket
    provider = streaming.OpenAIStreamingSpeechProvider(config(), socket_factory=factory)
    ref = recognition_ref()
    try:
        await provider.open_recognition(authorized_request(RecognitionStreamRequest(
            ref, RecognitionTurnDetection.server_vad_default())), timeout_seconds=2)
        socket.push(malformed)
        await asyncio.wait_for(socket.closed_event.wait(), 1)
        failure = next(f for e, f in records if e == "adapter_receive_failed")
        assert failure["failure_code"] == expected
        assert failure["capture_id"] == ref.capture.capture_id
        assert failure["media_session_id"] == ref.session_id
        assert failure["speech_started"] is False
        assert "PRIVATE" not in repr(records) and "private-item" not in repr(records)
        assert [m["type"] for m in socket.sent].count("input_audio_buffer.append") == 0
        assert_zero_business_effects(provider)
    finally:
        await provider.close()


def http_provider(handler):
    return batch.OpenAICompatibleBatchSpeechProvider(
        batch.OpenAICompatibleSpeechConfig("https://speech.example.test/v1", "PRIVATE_KEY", "stt", None, None),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_type,label", [
    (httpx.ConnectTimeout, "connect"), (httpx.ReadTimeout, "read"),
    (httpx.WriteTimeout, "write"), (httpx.PoolTimeout, "pool"),
])
async def test_http_timeout_is_not_outer_deadline_and_never_issues_receipt(monkeypatch, timeout_type, label):
    records, calls = [], []
    for module in (batch, http_diagnostics):
        monkeypatch.setattr(module, "record_audio_diagnostic", lambda e, **f: records.append((e, f)))
    async def handle(request):
        calls.append(1)
        await request.extensions["trace"]("http11.receive_response_headers.started", {"secret": "PRIVATE_KEY"})
        raise timeout_type("PRIVATE_BODY", request=request)
    service = _service(http_provider(handle))
    result = await service.recognize(_recognize_request(), CONTEXT)
    assert result["error"]["reason"] == "SPEECH_PROVIDER_TIMEOUT"
    assert len(calls) == 1 and len(service._voice_commit_receipts) == 0
    assert next(f for e, f in records if e == "batch_http_timeout")["timeout_kind"] == label
    assert not any(e == "batch_operation_deadline" for e, _ in records)
    assert all(f.get("operation_id") == "operation-r0" for _, f in records)
    assert "PRIVATE" not in repr(records)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_outer_deadline_or_cancel_keeps_http_phase_and_fences_receipt(monkeypatch, cancel):
    records, calls = [], []
    entered, cancelled = asyncio.Event(), asyncio.Event()
    for module in (batch, http_diagnostics):
        monkeypatch.setattr(module, "record_audio_diagnostic", lambda e, **f: records.append((e, f)))
    async def handle(request):
        calls.append(1)
        await request.extensions["trace"]("http11.receive_response_headers.started", {})
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
    service = _service(http_provider(handle))
    request = _recognize_request(timeout_ms=100 if not cancel else 1000)
    task = asyncio.create_task(service.recognize(request, CONTEXT))
    await asyncio.wait_for(entered.wait(), 1)
    if cancel:
        await service.cancel(_cancel_request("operation-r0"), CONTEXT)
    result = await task
    await asyncio.wait_for(cancelled.wait(), 1)
    assert result["error"]["code"] == ("CANCELLED" if cancel else "TIMEOUT")
    assert len(calls) == 1 and len(service._voice_commit_receipts) == 0
    assert any(e == ("batch_operation_cancelled" if cancel else "batch_operation_deadline") for e, _ in records)
    assert next(f for e, f in records if e == "batch_http_cancelled")["http_phase"] == "receive_response_headers"
    assert not any(e == "batch_http_timeout" for e, _ in records)
    replay = await service.recognize(request, CONTEXT)
    assert replay["error"]["code"] == result["error"]["code"] and len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("deadline", [False, True])
async def test_real_httpcore_phase_hooks_success_and_deadline(monkeypatch, deadline):
    records = []
    monkeypatch.setattr(http_diagnostics, "record_audio_diagnostic", lambda e, **f: records.append((e, f)))
    finished = asyncio.Event()
    async def serve(reader, writer):
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            size = next(int(h.split(b":", 1)[1]) for h in headers.split(b"\r\n") if h.lower().startswith(b"content-length:"))
            await reader.readexactly(size)
            if deadline:
                await reader.read()  # Client cancellation closes this exact connection.
                return
            body = b'{"text":"hello"}'
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            finished.set()
    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        provider = batch.OpenAICompatibleBatchSpeechProvider(
            batch.OpenAICompatibleSpeechConfig(f"http://127.0.0.1:{port}", "PRIVATE_KEY", "stt", None, None),
            client_factory=lambda: httpx.AsyncClient(trust_env=False))
        service = _service(provider)
        result = await service.recognize(_recognize_request(timeout_ms=300 if deadline else 3000), CONTEXT)
        if deadline:
            assert result["error"]["code"] == "TIMEOUT" and len(service._voice_commit_receipts) == 0
            cancelled = next(f for e, f in records if e == "batch_http_cancelled")
            assert cancelled["http_phase"] == "receive_response_headers"
        else:
            assert result["ok"] and len(service._voice_commit_receipts) == 1
        phases = {f["http_phase"] for e, f in records if e == "batch_http_phase"}
        assert {"connect_tcp", "send_request_body", "receive_response_headers"} <= phases
        if not deadline:
            assert "receive_response_body" in phases
        assert "PRIVATE" not in repr(records)
        await asyncio.wait_for(finished.wait(), 1)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_http_observer_is_bounded_and_throwing_sink_cannot_fail_transport(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_SINK")
    monkeypatch.setattr(http_diagnostics, "record_audio_diagnostic", fail)
    observer = http_diagnostics.SpeechHttpDiagnostics("operation", batch.RECOGNIZE_OPERATION)
    for _ in range(2000):
        await observer.trace("http11.send_request_body.started", {"raw": "PRIVATE_BODY"})
        await observer.trace("PRIVATE_UNKNOWN", {})
    assert len(observer._seen) == 1
    service = _service(http_provider(lambda request: httpx.Response(
        200, stream=httpx.ByteStream(b'{"text":"hello"}'))))
    result = await service.recognize(_recognize_request(), CONTEXT)
    assert result["ok"] and len(service._voice_commit_receipts) == 1
