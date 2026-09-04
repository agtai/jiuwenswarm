"""Long-lived real adapter/route checks; wire transport is explicitly simulated."""

import asyncio
import base64
import gc
import json
import weakref
from dataclasses import replace

import pytest

from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry,
)
from jiuwenswarm.gateway.live_voice.streaming_speech_route import (
    StreamingRecognitionRouteOwner,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    OpenAIStreamingSpeechProvider,
    SpeechDegradationReason,
    SpeechRouteTier,
    StreamingSpeechSelection,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    RecognitionStreamRequest,
    RecognitionTurnDetection,
    StreamingSpeechViolation,
    SpeechResponseAuthority,
    authorize_stream_request,
)
from jiuwenswarm.server.live_voice.speech_ports import SynthesisEventKind
from tests.unit_tests.live_voice.test_openai_streaming_speech import (
    FakeSocket,
    FakeSseStream,
    config,
    recognition_ref,
    recognition_frame,
    synthesis_request,
    session_updated_event,
    assert_zero_business_effects,
)
from tests.unit_tests.gateway.test_streaming_speech_route import (
    _trust_activation,
    _activation_params,
)


def admitted_capture(index=0, *, current=lambda: True):
    ref = replace(recognition_ref(), session_id=f"media-{index}")
    return authorize_stream_request(
        RecognitionStreamRequest(ref, RecognitionTurnDetection.manual()),
        is_current=current,
    )


@pytest.mark.asyncio
async def test_one_registry_route_and_adapter_survive_160_capture_lifetimes(
    monkeypatch,
):
    monkeypatch.setenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS", "voice.example.test")
    sockets = []

    async def socket_factory(*_args):
        socket = FakeSocket((session_updated_event(),))
        sockets.append(socket)
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=socket_factory)

    async def selector():
        return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)

    owner = StreamingRecognitionRouteOwner(selector)
    now = [1000.0]
    registry = DedicatedMediaProductRegistry(
        enabled=True, authority_ttl_seconds=10, monotonic=lambda: now[0]
    )
    registry.set_provider_available(True)

    async def forbidden_receipt(**_kwargs):
        raise AssertionError("aborted capture must not commit a turn")

    registry.configure_streaming_recognition(owner, receipt_issuer=forbidden_receipt)
    first_request = None
    refs = []
    for index in range(1, 161):
        _trust_activation(registry, index)
        activation = registry.activate(
            params=_activation_params(index),
            request_origin="https://voice.example.test",
            connection_id="connection-1",
            user_id="user-1",
        )
        record = registry.consume_ticket(
            str(activation["media_ticket"]), request_origin="https://voice.example.test"
        )
        assert record is not None
        await registry.begin_streaming_recognition(record)
        handle = record.streaming_recognition_handle
        assert handle is not None
        request = provider._recognition[
            (handle.ref.session_id, handle.ref.session_generation)
        ].request
        first_request = first_request or request
        refs.append(weakref.ref(request.authority))
        await provider.send_recognition_audio(recognition_frame(handle.ref))
        await registry.abort_streaming_recognition(record)
        assert owner._handles == {}
        assert provider.conformance.snapshot().retained_recognition == 0
        assert provider.conformance.snapshot().retained_identity_tombstones == 0
        assert len(registry._records) == 1
        now[0] += 11  # actual authority expiry, not a Provider history reset
    with pytest.raises(StreamingSpeechViolation):
        await provider.open_recognition(first_request, timeout_seconds=1)
    assert len(sockets) == 160 and all(socket.closed for socket in sockets)
    gc.collect()
    assert sum(ref() is not None for ref in refs) <= 2
    assert provider.cleanup_snapshot.clean
    assert_zero_business_effects(provider)
    await owner.close()


@pytest.mark.asyncio
async def test_one_adapter_synthesizes_160_responses_and_forgets_terminal_history():
    streams = []

    async def factory(*_args):
        stream = FakeSseStream(
            (
                "data: "
                + json.dumps(
                    {
                        "type": "speech.audio.delta",
                        "audio": base64.b64encode(b"\0" * 8).decode(),
                    }
                ),
                "",
                'data: {"type":"speech.audio.done"}',
                "",
            )
        )
        streams.append(stream)
        return stream

    provider = OpenAIStreamingSpeechProvider(config(), sse_factory=factory)
    current = [None]
    first = None
    refs = []
    for index in range(160):
        raw = synthesis_request(generation=index)
        raw = replace(raw, ref=replace(raw.ref, stream_id=f"stream-{index}"))
        current[0] = raw.ref.response
        response = raw.ref.response
        scope = SpeechResponseAuthority(
            response, lambda response=response: current[0] == response
        )
        request = authorize_stream_request(
            replace(raw, response_authority=scope),
            is_current=lambda response=response: current[0] == response,
        )
        first = first or request
        refs.append(weakref.ref(scope))
        provider.conformance.activate_response(scope)
        await provider.open_synthesis(request)
        while (
            await provider.next_synthesis_event(request.ref, timeout_seconds=1)
        ).kind is not SynthesisEventKind.COMPLETED:
            pass
        assert provider.conformance.snapshot().retained_synthesis == 0
        assert provider.conformance._active_responses == {}
        assert provider.conformance.snapshot().retained_identity_tombstones == 0
    with pytest.raises(StreamingSpeechViolation):
        await provider.open_synthesis(first)
    assert len(streams) == 160 and all(stream.closed for stream in streams)
    gc.collect()
    assert sum(ref() is not None for ref in refs) <= 2
    assert provider.cleanup_snapshot.clean
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_real_capacity_recovers_and_missing_expired_duplicate_admission_opens_nothing():
    sockets = []

    async def factory(*_args):
        socket = FakeSocket((session_updated_event(),))
        sockets.append(socket)
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=factory)
    requests = [admitted_capture(index) for index in range(9)]
    for request in requests[:8]:
        await provider.open_recognition(request, timeout_seconds=2)
    with pytest.raises(StreamingSpeechViolation) as full:
        await provider.open_recognition(requests[8], timeout_seconds=2)
    assert full.value.reason == "RECOGNITION_CAPACITY_EXHAUSTED"
    assert (
        provider.degradation_facts[-1].reason
        is SpeechDegradationReason.RESOURCE_CAPACITY
    )
    assert len(sockets) == 8
    await provider.cancel_recognition(requests[0].ref)
    await provider.open_recognition(requests[8], timeout_seconds=2)
    for request in requests[1:]:
        await provider.cancel_recognition(request.ref)
    absent = replace(admitted_capture(99), authority=None)
    expired = admitted_capture(100, current=lambda: False)
    for request in (absent, expired, requests[0]):
        with pytest.raises(StreamingSpeechViolation):
            await provider.open_recognition(request, timeout_seconds=2)
    assert len(sockets) == 9
    request = admitted_capture(101)
    results = await asyncio.gather(
        *(provider.open_recognition(request, timeout_seconds=2) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(result is None for result in results) == 1
    assert len(sockets) == 10
    await provider.cancel_recognition(request.ref)
    assert provider.cleanup_snapshot.clean
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_revocation_during_connect_closes_late_socket_without_delivery():
    entered, release = asyncio.Event(), asyncio.Event()
    socket = FakeSocket((session_updated_event(),))

    async def factory(*_args):
        entered.set()
        await release.wait()
        return socket

    provider = OpenAIStreamingSpeechProvider(config(), socket_factory=factory)
    request = admitted_capture()
    opening = asyncio.create_task(provider.open_recognition(request, timeout_seconds=2))
    await entered.wait()
    request.authority.revoke()
    release.set()
    with pytest.raises(StreamingSpeechViolation) as stale:
        await opening
    assert stale.value.reason == "SPEECH_AUTHORITY_EXPIRED"
    assert socket.closed and socket.sent == []
    assert provider.conformance.snapshot().retained_recognition == 0
    assert (
        provider.degradation_facts[-1].reason
        is SpeechDegradationReason.AUTHORITY_EXPIRED
    )
    assert_zero_business_effects(provider)
    await provider.close()


@pytest.mark.asyncio
async def test_unconsumed_terminal_queues_still_use_capacity_after_another_stream_retires():
    count = 0

    async def factory(*_args):
        nonlocal count
        count += 1
        return FakeSseStream(
            (
                "data: "
                + json.dumps(
                    {
                        "type": "speech.audio.delta",
                        "audio": base64.b64encode(b"\0" * 8).decode(),
                    }
                ),
                "",
                'data: {"type":"speech.audio.done"}',
                "",
            )
        )

    provider = OpenAIStreamingSpeechProvider(config(), sse_factory=factory)
    requests = []
    for index in range(9):
        raw = synthesis_request(generation=index)
        raw = replace(raw, ref=replace(raw.ref, stream_id=f"queued-{index}"))
        scope = SpeechResponseAuthority(raw.ref.response, lambda: True)
        requests.append(
            authorize_stream_request(
                replace(raw, response_authority=scope), is_current=lambda: True
            )
        )

    async def open_and_finish(request):
        provider.conformance.activate_response(request.response_authority)
        await provider.open_synthesis(request)
        await provider._synthesis[
            (request.ref.stream_id, request.ref.stream_generation)
        ].task

    await open_and_finish(requests[0])
    await open_and_finish(requests[1])
    while (
        await provider.next_synthesis_event(requests[1].ref, timeout_seconds=1)
    ).kind is not SynthesisEventKind.COMPLETED:
        pass
    assert provider.conformance.snapshot().retained_synthesis == 1
    # Same stream id cannot overlap retained generations. Independent streams
    # keep their terminal queues until the owning consumer retires them.
    for index in range(2, 9):
        raw = requests[index]
        raw = replace(
            raw, authority=None, ref=replace(raw.ref, stream_id=f"queued-{index}")
        )
        requests[index] = authorize_stream_request(raw, is_current=lambda: True)
        await open_and_finish(requests[index])
    extra_raw = replace(
        synthesis_request(generation=99),
        ref=replace(synthesis_request(generation=99).ref, stream_id="extra"),
    )
    scope = SpeechResponseAuthority(extra_raw.ref.response, lambda: True)
    extra = authorize_stream_request(
        replace(extra_raw, response_authority=scope), is_current=lambda: True
    )
    provider.conformance.activate_response(scope)
    with pytest.raises(StreamingSpeechViolation) as full:
        await provider.open_synthesis(extra)
    assert full.value.reason == "SYNTHESIS_CAPACITY_EXHAUSTED"
    assert count == 9
    assert provider.conformance.snapshot().retained_synthesis == 8
    await provider.close()
    assert provider.cleanup_snapshot.clean
