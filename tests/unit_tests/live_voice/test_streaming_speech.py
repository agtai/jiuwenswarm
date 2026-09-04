# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.unit_tests.live_voice.speech_authority_support import (
    authorized_request,
    response_authority,
    begin_recognition,
    speech_test_issuer,
)

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEventKind,
    RecognitionHypothesis,
    SpeechMode,
    SynthesisEventKind,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    CapabilityProvenance,
    CaptureRef,
    ProviderControlKind,
    ProviderTransport,
    RecognitionAudioFrame,
    RecognitionProviderSupport,
    RecognitionStreamRequest,
    RecognitionStreamRef,
    RecognitionTimingBasis,
    RecognitionTurnBoundaryEvent,
    RecognitionTurnBoundaryKind,
    RecognitionTurnDetection,
    StreamingProviderCapability,
    StreamingRecognitionEvent,
    StreamingSpeechConformance,
    StreamingSpeechViolation,
    StreamingSynthesisEvent,
    SynthesisProviderSupport,
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)


PROVIDER = ProviderRef("native-stream-provider", "formal")


def native_capability(*, available: bool = True) -> StreamingProviderCapability:
    return StreamingProviderCapability(
        provider=PROVIDER,
        recognition=RecognitionProviderSupport(
            modes=frozenset({SpeechMode.BATCH, SpeechMode.STREAM}),
            transport=ProviderTransport.NATIVE_STREAM,
            ordered_events=CapabilityProvenance.PROVIDER_NATIVE,
            exact_audio_cursor=CapabilityProvenance.PROVIDER_NATIVE,
            provider_cancel_ack=CapabilityProvenance.PROVIDER_NATIVE,
            native_partials=CapabilityProvenance.PROVIDER_NATIVE,
        ),
        synthesis=SynthesisProviderSupport(
            modes=frozenset({SpeechMode.BATCH, SpeechMode.STREAM}),
            transport=ProviderTransport.NATIVE_STREAM,
            ordered_events=CapabilityProvenance.PROVIDER_NATIVE,
            exact_audio_cursor=CapabilityProvenance.PROVIDER_NATIVE,
            provider_cancel_ack=CapabilityProvenance.PROVIDER_NATIVE,
            chunk_text_spans=CapabilityProvenance.PROVIDER_NATIVE,
        ),
        available=available,
    )


def batch_capability() -> StreamingProviderCapability:
    return StreamingProviderCapability(
        provider=ProviderRef("batch-provider", "formal"),
        recognition=RecognitionProviderSupport(
            frozenset({SpeechMode.BATCH}), ProviderTransport.BATCH_REQUEST
        ),
        synthesis=SynthesisProviderSupport(
            frozenset({SpeechMode.BATCH}), ProviderTransport.BATCH_REQUEST
        ),
    )


def recognition_ref(
    *,
    session_id: str = "recognition-1",
    session_generation: int = 0,
    capture_id: str = "capture-1",
    capture_generation: int = 0,
) -> RecognitionStreamRef:
    return RecognitionStreamRef(
        session_id,
        session_generation,
        CaptureRef(capture_id, capture_generation, 48_000),
    )


def frame(
    ref: RecognitionStreamRef,
    *,
    seq: int,
    cursor: int,
    samples: int = 4,
) -> RecognitionAudioFrame:
    return RecognitionAudioFrame(ref, seq, cursor, samples, b"\x00" * samples * 4)


def hypothesis(text: str = "你好") -> RecognitionHypothesis:
    return RecognitionHypothesis(
        (RecognitionAlternative(text, text, 0.91),), selected_index=0
    )


def recognition_event(
    ref: RecognitionStreamRef,
    *,
    seq: int,
    cursor: int,
    kind: RecognitionEventKind,
    selected: RecognitionHypothesis | None = None,
    provider: ProviderRef = PROVIDER,
) -> StreamingRecognitionEvent:
    return StreamingRecognitionEvent(
        ref,
        provider,
        seq,
        cursor,
        kind,
        selected,
    )


def response(
    *,
    interaction_id: str = "interaction-1",
    response_id: str = "response-1",
    generation: int = 0,
) -> ResponseRef:
    return ResponseRef(interaction_id, response_id, generation)


def synthesis_request(
    *,
    response_ref: ResponseRef | None = None,
    stream_id: str = "synthesis-1",
    stream_generation: int = 0,
    unit_id: str = "unit-1",
    unit_seq: int = 0,
    display_text: str = "API",
    spoken_text: str = "A P I",
    display_start: int = 10,
    event_timeout_seconds: float = 5.0,
) -> SynthesisStreamRequest:
    selected_response = response_ref or response()
    return SynthesisStreamRequest(
        ref=SynthesisStreamRef(
            stream_id,
            stream_generation,
            selected_response,
            unit_id,
            unit_seq,
        ),
        display_text=display_text,
        spoken_text=spoken_text,
        display_span=TextSpan(display_start, display_start + len(display_text)),
        sample_rate_hz=24_000,
        event_timeout_seconds=event_timeout_seconds,
    )


def synthesis_event(
    request: SynthesisStreamRequest,
    *,
    seq: int,
    cursor: int,
    kind: SynthesisEventKind,
    samples: int = 0,
    display_span: TextSpan | None = None,
    spoken_span: TextSpan | None = None,
    provider: ProviderRef = PROVIDER,
) -> StreamingSynthesisEvent:
    return StreamingSynthesisEvent(
        ref=request.ref,
        provider=provider,
        seq=seq,
        sample_cursor=cursor,
        kind=kind,
        sample_rate_hz=request.sample_rate_hz,
        sample_count=samples,
        pcm_s16le=None if samples == 0 else b"\x00" * samples * 2,
        display_span=display_span,
        spoken_span=spoken_span,
    )


def assert_zero_authority_effects(runtime: StreamingSpeechConformance) -> None:
    snapshot = runtime.snapshot()
    assert snapshot.agent_dispatches == 0
    assert snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == 0
    assert snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0
    assert not hasattr(runtime, "commit_turn")
    assert not hasattr(runtime, "dispatch_agent")
    assert not hasattr(runtime, "dispatch_tool")
    assert not hasattr(runtime, "mutate_task")
    assert not hasattr(runtime, "write_chat")


def assert_one_provider_cancel(
    runtime: StreamingSpeechConformance,
    *,
    kind: ProviderControlKind,
    expected_ref: RecognitionStreamRef | SynthesisStreamRef,
) -> None:
    controls = runtime.take_provider_controls()
    assert len(controls) == 1
    assert controls[0].kind is kind
    assert controls[0].ref == expected_ref
    assert controls[0].business_cancel is False


def test_native_capability_is_truthful_and_polling_cannot_claim_streaming() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    assert runtime.capability.has_declared_acceptance_gaps is False
    assert runtime.capability.acceptance_gaps == ()
    assert runtime.capability.recognition.transport is ProviderTransport.NATIVE_STREAM
    assert (
        runtime.capability.synthesis.chunk_text_spans
        is CapabilityProvenance.PROVIDER_NATIVE
    )

    dishonest = replace(
        native_capability().recognition,
        transport=ProviderTransport.POLLING,
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        StreamingSpeechConformance(
            replace(native_capability(), recognition=dishonest), enabled=True
        )
    assert raised.value.reason == "POLLING_NOT_STREAMING"
    assert_zero_authority_effects(runtime)


def test_server_vad_default_tolerates_a_natural_breath_pause() -> None:
    detection = RecognitionTurnDetection.server_vad_default()

    assert detection.server_vad is not None
    assert detection.server_vad.threshold == 0.5
    assert detection.server_vad.prefix_padding_ms == 300
    assert detection.server_vad.silence_duration_ms == 1_200
    assert detection.server_vad.create_response is False
    assert detection.server_vad.interrupt_response is False


def test_server_vad_barge_in_retains_wider_prefix_without_changing_authority() -> None:
    detection = RecognitionTurnDetection.server_vad_barge_in()

    assert detection.server_vad is not None
    assert detection.server_vad.threshold == 0.5
    assert detection.server_vad.prefix_padding_ms == 800
    assert detection.server_vad.silence_duration_ms == 1_200
    assert detection.server_vad.create_response is False
    assert detection.server_vad.interrupt_response is False
    assert (
        RecognitionTurnDetection.server_vad_default().server_vad.prefix_padding_ms
        == 300
    )


def test_server_vad_boundaries_require_same_item_and_cursorless_final() -> None:
    capability = replace(
        native_capability(),
        recognition=replace(
            native_capability().recognition,
            server_vad=CapabilityProvenance.PROVIDER_NATIVE,
        ),
    )
    runtime = StreamingSpeechConformance(capability, enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(
        authorized_request(
            RecognitionStreamRequest(ref, RecognitionTurnDetection.server_vad_default())
        ),
        timeout_seconds=5,
    )
    runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    for boundary in (
        RecognitionTurnBoundaryEvent(
            ref,
            PROVIDER,
            0,
            RecognitionTurnBoundaryKind.SPEECH_STARTED,
            "provider-item-1",
            provider_start_ms=100,
        ),
        RecognitionTurnBoundaryEvent(
            ref,
            PROVIDER,
            1,
            RecognitionTurnBoundaryKind.SPEECH_STOPPED,
            "provider-item-1",
            provider_end_ms=700,
        ),
        RecognitionTurnBoundaryEvent(
            ref,
            PROVIDER,
            2,
            RecognitionTurnBoundaryKind.COMMITTED,
            "provider-item-1",
        ),
    ):
        assert runtime.accept_recognition_boundary(boundary) is boundary
    final = StreamingRecognitionEvent(
        ref=ref,
        provider=PROVIDER,
        seq=3,
        audio_cursor=None,
        kind=RecognitionEventKind.FINAL,
        hypothesis=hypothesis("provider final"),
        timing_basis=RecognitionTimingBasis.PROVIDER_TIME,
    )
    assert runtime.accept_recognition_event(final) is final
    snapshot = runtime.snapshot()
    assert snapshot.agent_dispatches == snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0


def test_server_vad_request_requires_exact_provider_capability_before_allocation() -> (
    None
):
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    with pytest.raises(StreamingSpeechViolation) as unavailable:
        runtime.start_recognition(
            authorized_request(
                RecognitionStreamRequest(
                    recognition_ref(), RecognitionTurnDetection.server_vad_default()
                )
            ),
            timeout_seconds=5,
        )
    assert unavailable.value.reason == "SERVER_VAD_UNAVAILABLE"
    assert runtime.snapshot().active_recognition == 0
    assert_zero_authority_effects(runtime)


def test_server_vad_wrong_item_fails_closed_and_fences_input() -> None:
    capability = replace(
        native_capability(),
        recognition=replace(
            native_capability().recognition,
            server_vad=CapabilityProvenance.PROVIDER_NATIVE,
        ),
    )
    runtime = StreamingSpeechConformance(capability, enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(
        authorized_request(
            RecognitionStreamRequest(ref, RecognitionTurnDetection.server_vad_default())
        ),
        timeout_seconds=5,
    )
    runtime.accept_recognition_boundary(
        RecognitionTurnBoundaryEvent(
            ref,
            PROVIDER,
            0,
            RecognitionTurnBoundaryKind.SPEECH_STARTED,
            "provider-item-1",
            provider_start_ms=100,
        )
    )
    with pytest.raises(StreamingSpeechViolation) as wrong_item:
        runtime.accept_recognition_boundary(
            RecognitionTurnBoundaryEvent(
                ref,
                PROVIDER,
                1,
                RecognitionTurnBoundaryKind.SPEECH_STOPPED,
                "provider-item-forged",
                provider_end_ms=700,
            )
        )
    assert wrong_item.value.reason == "INVALID_TURN_BOUNDARY_ORDER"
    with pytest.raises(StreamingSpeechViolation) as fenced:
        runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    assert fenced.value.reason == "RECOGNITION_INPUT_FENCED"
    snapshot = runtime.snapshot()
    assert snapshot.agent_dispatches == snapshot.tool_dispatches == 0
    assert snapshot.task_mutations == snapshot.chat_mutations == 0
    assert snapshot.turn_commits == 0


@pytest.mark.parametrize(
    ("direction", "support"),
    [
        (
            "recognition",
            replace(
                native_capability().recognition,
                exact_audio_cursor=CapabilityProvenance.UNAVAILABLE,
            ),
        ),
        (
            "synthesis",
            replace(
                native_capability().synthesis,
                ordered_events=CapabilityProvenance.UNAVAILABLE,
            ),
        ),
    ],
)
def test_incomplete_stream_capability_fails_closed(direction, support) -> None:
    capability = native_capability()
    with pytest.raises(StreamingSpeechViolation) as raised:
        StreamingSpeechConformance(
            replace(capability, **{direction: support}), enabled=True
        )
    assert raised.value.reason.startswith("INCOMPLETE_")


def test_batch_capability_cannot_claim_stream_only_guarantees() -> None:
    capability = batch_capability()
    misleading = replace(
        capability.recognition,
        ordered_events=CapabilityProvenance.ADAPTER_DERIVED,
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        StreamingSpeechConformance(
            replace(capability, recognition=misleading), enabled=True
        )
    assert raised.value.reason == "RECOGNITION_CAPABILITY_CONTRADICTION"


def test_unsupported_recognition_cannot_claim_server_vad() -> None:
    capability = batch_capability()
    contradictory = RecognitionProviderSupport(
        modes=frozenset(),
        transport=ProviderTransport.UNSUPPORTED,
        server_vad=CapabilityProvenance.PROVIDER_NATIVE,
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        StreamingSpeechConformance(
            replace(capability, recognition=contradictory), enabled=True
        )
    assert raised.value.reason == "RECOGNITION_CAPABILITY_CONTRADICTION"


def test_unavailable_optional_provenance_remains_an_explicit_streaming_gap() -> None:
    capability = replace(
        native_capability(),
        recognition=replace(
            native_capability().recognition,
            exact_audio_cursor=CapabilityProvenance.TRANSPORT_OBSERVED,
            provider_cancel_ack=CapabilityProvenance.UNAVAILABLE,
        ),
        synthesis=replace(
            native_capability().synthesis,
            exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
            provider_cancel_ack=CapabilityProvenance.UNAVAILABLE,
            chunk_text_spans=CapabilityProvenance.UNAVAILABLE,
        ),
    )
    runtime = StreamingSpeechConformance(capability, enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=1)
    runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    runtime.request_recognition_cancel(ref)
    with pytest.raises(StreamingSpeechViolation) as unavailable_ack:
        runtime.accept_recognition_event(
            recognition_event(
                ref,
                seq=0,
                cursor=4,
                kind=RecognitionEventKind.CANCELLED,
            )
        )
    assert unavailable_ack.value.reason == "UNPROVEN_RECOGNITION_CANCEL_ACK"
    runtime.provider_closed_recognition(ref)

    request = synthesis_request()
    runtime.activate_response(response_authority(request.ref.response))
    runtime.start_synthesis(authorized_request(request))
    runtime.accept_synthesis_event(
        synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=4,
        )
    )
    runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=2,
            cursor=4,
            kind=SynthesisEventKind.COMPLETED,
        )
    )
    assert (
        runtime.capability.synthesis.chunk_text_spans
        is CapabilityProvenance.UNAVAILABLE
    )
    assert_zero_authority_effects(runtime)


@pytest.mark.parametrize("direction", ["recognition", "synthesis"])
def test_transport_observation_cannot_claim_provider_cancel_ack(direction: str) -> None:
    capability = native_capability()
    dishonest = replace(
        getattr(capability, direction),
        provider_cancel_ack=CapabilityProvenance.TRANSPORT_OBSERVED,
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        StreamingSpeechConformance(
            replace(capability, **{direction: dishonest}), enabled=True
        )
    assert raised.value.reason == "INVALID_CANCEL_ACK_PROVENANCE"


def test_unsupported_provider_cannot_advertise_available_stream_modes() -> None:
    capability = replace(
        native_capability(),
        provider=ProviderRef("unsupported-provider", "unsupported"),
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        StreamingSpeechConformance(capability, enabled=True)
    assert raised.value.reason == "UNSUPPORTED_PROVIDER_CAPABILITY_CONTRADICTION"


def test_batch_only_capability_is_not_upgraded_to_streaming() -> None:
    runtime = StreamingSpeechConformance(batch_capability(), enabled=True)
    with pytest.raises(StreamingSpeechViolation) as recognition_error:
        runtime.start_recognition(
            authorized_request(recognition_ref()), timeout_seconds=1
        )
    assert recognition_error.value.reason == "STREAMING_RECOGNITION_UNSUPPORTED"

    with pytest.raises(StreamingSpeechViolation) as synthesis_error:
        runtime.start_synthesis(authorized_request(synthesis_request()))
    assert synthesis_error.value.reason == "STREAMING_SYNTHESIS_UNSUPPORTED"
    assert runtime.snapshot().retained_recognition == 0
    assert runtime.snapshot().retained_synthesis == 0
    assert_zero_authority_effects(runtime)


def test_flag_off_rejects_before_allocating_response_or_sessions() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=False)
    with pytest.raises(StreamingSpeechViolation) as activation:
        runtime.activate_response(response_authority(response()))
    assert activation.value.reason == "STREAMING_SPEECH_DISABLED"
    with pytest.raises(StreamingSpeechViolation) as recognition:
        runtime.start_recognition(
            authorized_request(recognition_ref()), timeout_seconds=1
        )
    assert recognition.value.reason == "STREAMING_SPEECH_DISABLED"
    snapshot = runtime.snapshot()
    assert snapshot.active_recognition == snapshot.retained_recognition == 0
    assert snapshot.active_synthesis == snapshot.retained_synthesis == 0
    assert snapshot.pending_provider_controls == 0
    assert snapshot.retained_identity_tombstones == 0
    assert snapshot.retained_synthesis_unit_identities == 0
    assert_zero_authority_effects(runtime)


def test_response_activation_retains_only_bounded_live_authority():
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    for index in range(512):
        runtime.activate_response(
            response_authority(
                response(interaction_id=f"i-{index}", response_id=f"r-{index}")
            )
        )
        assert runtime.snapshot().retained_identity_tombstones == 0
        assert len(runtime._active_responses) <= 1
    assert_zero_authority_effects(runtime)


def test_unavailable_provider_rejects_without_session_side_effects() -> None:
    runtime = StreamingSpeechConformance(
        native_capability(available=False), enabled=True
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.start_recognition(
            authorized_request(recognition_ref()), timeout_seconds=1
        )
    assert raised.value.reason == "STREAMING_PROVIDER_UNAVAILABLE"
    assert runtime.snapshot().retained_recognition == 0
    assert_zero_authority_effects(runtime)


def test_recognition_positive_order_exact_capture_cursor_final_and_reuse() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    runtime.accept_audio_frame(frame(ref, seq=1, cursor=4))

    partial = runtime.accept_recognition_event(
        recognition_event(
            ref,
            seq=0,
            cursor=4,
            kind=RecognitionEventKind.PARTIAL,
            selected=hypothesis("你"),
        )
    )
    final = runtime.accept_recognition_event(
        recognition_event(
            ref,
            seq=1,
            cursor=8,
            kind=RecognitionEventKind.FINAL,
            selected=hypothesis(),
        )
    )
    assert partial.ref.capture == ref.capture
    assert final.hypothesis is not None
    assert final.hypothesis.selected.display_text == "你好"
    assert runtime.snapshot().active_recognition == 0

    with pytest.raises(StreamingSpeechViolation) as late:
        runtime.accept_audio_frame(frame(ref, seq=2, cursor=8))
    assert late.value.reason == "RECOGNITION_ALREADY_TERMINAL"
    assert runtime.reap_terminal() == (1, 0)

    with pytest.raises(StreamingSpeechViolation) as stale:
        runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    assert stale.value.reason == "SPEECH_AUTHORITY_EXPIRED"
    replacement = recognition_ref(session_generation=1, capture_generation=1)
    runtime.start_recognition(authorized_request(replacement), timeout_seconds=5)
    assert runtime.snapshot().active_recognition == 1
    with pytest.raises(StreamingSpeechViolation) as late_old_generation:
        runtime.accept_recognition_event(
            recognition_event(
                ref,
                seq=2,
                cursor=8,
                kind=RecognitionEventKind.CANCELLED,
            )
        )
    assert late_old_generation.value.reason == "STALE_RECOGNITION_SESSION"
    assert_zero_authority_effects(runtime)


@pytest.mark.parametrize(
    ("bad_frame", "reason"),
    [
        (
            lambda ref: frame(ref, seq=1, cursor=0),
            "AUDIO_FRAME_GAP",
        ),
        (
            lambda ref: frame(ref, seq=0, cursor=4),
            "AUDIO_CURSOR_GAP",
        ),
        (
            lambda ref: replace(frame(ref, seq=0, cursor=0), pcm_f32le=b"bad"),
            "INVALID_PCM_F32_FRAME",
        ),
    ],
)
def test_bad_capture_frames_fail_close_and_only_request_provider_cancel(
    bad_frame, reason
) -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_audio_frame(bad_frame(ref))
    assert raised.value.reason == reason
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    with pytest.raises(StreamingSpeechViolation) as fenced:
        runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    assert fenced.value.reason == "RECOGNITION_INPUT_FENCED"
    assert_zero_authority_effects(runtime)


def test_capture_identity_mismatch_fails_exact_retained_session() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    wrong = recognition_ref(capture_id="foreign-capture")
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_audio_frame(frame(wrong, seq=0, cursor=0))
    assert raised.value.reason == "RECOGNITION_CAPTURE_MISMATCH"
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    assert_zero_authority_effects(runtime)


def test_duplicate_audio_frame_fails_close_after_one_accepted_frame() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    accepted = frame(ref, seq=0, cursor=0)
    runtime.accept_audio_frame(accepted)
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_audio_frame(accepted)
    assert raised.value.reason == "DUPLICATE_AUDIO_FRAME"
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    assert_zero_authority_effects(runtime)


def test_concurrent_duplicate_audio_frame_is_linearized_and_fails_closed() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    duplicate = frame(ref, seq=0, cursor=0)

    def submit() -> str:
        try:
            runtime.accept_audio_frame(duplicate)
        except StreamingSpeechViolation as error:
            return error.reason
        return "accepted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result() for future in [executor.submit(submit) for _ in range(2)]
        ]
    assert sorted(results) == ["DUPLICATE_AUDIO_FRAME", "accepted"]
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    assert_zero_authority_effects(runtime)


@pytest.mark.parametrize(
    ("bad_event", "reason"),
    [
        (
            lambda ref: recognition_event(
                ref,
                seq=1,
                cursor=4,
                kind=RecognitionEventKind.PARTIAL,
                selected=hypothesis(),
            ),
            "RECOGNITION_EVENT_GAP",
        ),
        (
            lambda ref: recognition_event(
                ref,
                seq=0,
                cursor=5,
                kind=RecognitionEventKind.PARTIAL,
                selected=hypothesis(),
            ),
            "INVALID_RECOGNITION_AUDIO_CURSOR",
        ),
        (
            lambda ref: recognition_event(
                ref,
                seq=0,
                cursor=4,
                kind=RecognitionEventKind.PARTIAL,
                selected=hypothesis(),
                provider=ProviderRef("wrong-provider", "formal"),
            ),
            "RECOGNITION_PROVIDER_MISMATCH",
        ),
    ],
)
def test_recognition_provider_gap_cursor_and_provider_mismatch_fail_close(
    bad_event, reason
) -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_recognition_event(bad_event(ref))
    assert raised.value.reason == reason
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    assert_zero_authority_effects(runtime)


def test_duplicate_recognition_event_fails_close_without_committing_partial() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    partial = recognition_event(
        ref,
        seq=0,
        cursor=4,
        kind=RecognitionEventKind.PARTIAL,
        selected=hypothesis("部分"),
    )
    runtime.accept_recognition_event(partial)
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_recognition_event(partial)
    assert raised.value.reason == "DUPLICATE_RECOGNITION_EVENT"
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    assert_zero_authority_effects(runtime)


def test_invalid_recognition_hypothesis_fails_close() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    invalid = RecognitionHypothesis((RecognitionAlternative("raw", "display", True),))
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_recognition_event(
            recognition_event(
                ref,
                seq=0,
                cursor=4,
                kind=RecognitionEventKind.FINAL,
                selected=invalid,
            )
        )
    assert raised.value.reason == "INVALID_CONFIDENCE"
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    assert_zero_authority_effects(runtime)


def test_recognition_cancel_fences_late_output_and_accepts_exact_cancel_ack() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=5)
    runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    runtime.request_recognition_cancel(ref, reason="local_stop")
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    with pytest.raises(StreamingSpeechViolation) as late:
        runtime.accept_recognition_event(
            recognition_event(
                ref,
                seq=0,
                cursor=4,
                kind=RecognitionEventKind.PARTIAL,
                selected=hypothesis(),
            )
        )
    assert late.value.reason == "RECOGNITION_OUTPUT_FENCED"
    cancelled = runtime.accept_recognition_event(
        recognition_event(
            ref,
            seq=0,
            cursor=4,
            kind=RecognitionEventKind.CANCELLED,
        )
    )
    assert cancelled.kind is RecognitionEventKind.CANCELLED
    assert runtime.reap_terminal() == (1, 0)
    assert_zero_authority_effects(runtime)


def test_recognition_timeout_fences_output_but_accepts_exact_provider_cancel_ack() -> (
    None
):
    now = [10.0]
    runtime = StreamingSpeechConformance(
        native_capability(), enabled=True, monotonic=lambda: now[0]
    )
    ref = recognition_ref()
    runtime.start_recognition(authorized_request(ref), timeout_seconds=1)
    now[0] = 11.0
    assert runtime.expire() == 1
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_RECOGNITION,
        expected_ref=ref,
    )
    assert runtime.reap_terminal() == (0, 0)
    assert runtime.snapshot().retained_recognition == 1
    with pytest.raises(StreamingSpeechViolation) as late:
        runtime.accept_audio_frame(frame(ref, seq=0, cursor=0))
    assert late.value.reason == "RECOGNITION_STREAM_TIMEOUT"
    runtime.accept_recognition_event(
        recognition_event(
            ref,
            seq=0,
            cursor=0,
            kind=RecognitionEventKind.CANCELLED,
        )
    )
    assert runtime.reap_terminal() == (1, 0)
    assert_zero_authority_effects(runtime)


def test_recognition_capacity_is_bounded_and_released_only_after_terminal_cleanup() -> (
    None
):
    runtime = StreamingSpeechConformance(
        native_capability(), enabled=True, max_recognition_sessions=1
    )
    first = recognition_ref()
    second = recognition_ref(session_id="recognition-2")
    runtime.start_recognition(authorized_request(first), timeout_seconds=5)
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.start_recognition(authorized_request(second), timeout_seconds=5)
    assert raised.value.reason == "RECOGNITION_CAPACITY_EXHAUSTED"
    runtime.request_recognition_cancel(first)
    runtime.take_provider_controls()
    with pytest.raises(StreamingSpeechViolation) as retained:
        runtime.start_recognition(authorized_request(second), timeout_seconds=5)
    assert retained.value.reason == "RECOGNITION_CAPACITY_EXHAUSTED"
    runtime.provider_closed_recognition(first)
    runtime.reap_terminal()
    runtime.start_recognition(authorized_request(second), timeout_seconds=5)
    assert runtime.snapshot().active_recognition == 1
    assert_zero_authority_effects(runtime)


def test_synthesis_positive_chunks_preserve_exact_response_unit_and_text_spans() -> (
    None
):
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))

    started = runtime.accept_synthesis_event(
        synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    first = runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=2,
            display_span=TextSpan(10, 13),
            spoken_span=TextSpan(0, 2),
        )
    )
    second = runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=2,
            cursor=2,
            kind=SynthesisEventKind.CHUNK,
            samples=3,
            display_span=TextSpan(13, 13),
            spoken_span=TextSpan(2, 5),
        )
    )
    completed = runtime.accept_synthesis_event(
        synthesis_event(request, seq=3, cursor=5, kind=SynthesisEventKind.COMPLETED)
    )
    assert [started.seq, first.seq, second.seq, completed.seq] == [0, 1, 2, 3]
    assert first.ref.response == response_ref
    assert first.ref.unit_id == "unit-1"
    assert first.display_span == TextSpan(10, 13)
    assert second.spoken_span == TextSpan(2, 5)
    assert runtime.snapshot().active_synthesis == 0
    with pytest.raises(StreamingSpeechViolation) as late:
        runtime.accept_synthesis_event(
            synthesis_event(
                request,
                seq=4,
                cursor=5,
                kind=SynthesisEventKind.CHUNK,
                samples=1,
                display_span=TextSpan(13, 13),
                spoken_span=TextSpan(5, 5),
            )
        )
    assert late.value.reason == "SYNTHESIS_ALREADY_TERMINAL"
    assert runtime.reap_terminal() == (0, 1)
    assert_zero_authority_effects(runtime)


def test_synthesis_units_require_exact_contiguous_sequence_and_unique_id() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    runtime.activate_response(response_authority(response_ref))
    first = synthesis_request(response_ref=response_ref)
    runtime.start_synthesis(authorized_request(first))

    skipped = synthesis_request(
        response_ref=response_ref,
        stream_id="synthesis-2",
        unit_id="unit-2",
        unit_seq=2,
    )
    with pytest.raises(StreamingSpeechViolation) as gap:
        runtime.start_synthesis(authorized_request(skipped))
    assert gap.value.reason == "SYNTHESIS_UNIT_SEQUENCE_GAP"

    reused = synthesis_request(
        response_ref=response_ref,
        stream_id="synthesis-2",
        unit_id="unit-1",
        unit_seq=1,
    )
    with pytest.raises(StreamingSpeechViolation) as duplicate:
        runtime.start_synthesis(authorized_request(reused))
    assert duplicate.value.reason == "SYNTHESIS_UNIT_REUSED"

    second = replace(reused, ref=replace(reused.ref, unit_id="unit-2"))
    runtime.start_synthesis(authorized_request(second))
    assert runtime.snapshot().active_synthesis == 2
    assert_zero_authority_effects(runtime)


def test_completed_synthesis_unit_id_cannot_be_reused_after_reap() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref, unit_id="unit-retained")
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    runtime.accept_synthesis_event(
        synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=2,
            display_span=request.display_span,
            spoken_span=TextSpan(0, len(request.spoken_text)),
        )
    )
    runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=2,
            cursor=2,
            kind=SynthesisEventKind.COMPLETED,
        )
    )
    assert runtime.reap_terminal() == (0, 1)

    reused = synthesis_request(
        response_ref=response_ref,
        stream_id="synthesis-next",
        unit_id=request.ref.unit_id,
        unit_seq=1,
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.start_synthesis(authorized_request(reused))
    assert raised.value.reason == "SYNTHESIS_UNIT_REUSED"
    assert runtime.snapshot().retained_synthesis == 0
    assert runtime.snapshot().retained_synthesis_unit_identities == 1
    assert_zero_authority_effects(runtime)


@pytest.mark.parametrize("terminal_kind", ["cancelled", "provider_closed"])
def test_cancelled_or_closed_synthesis_unit_id_cannot_be_reused_after_reap(
    terminal_kind: str,
) -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref, unit_id="unit-retained")
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    if terminal_kind == "cancelled":
        runtime.accept_synthesis_event(
            synthesis_event(
                request,
                seq=0,
                cursor=0,
                kind=SynthesisEventKind.CANCELLED,
            )
        )
    else:
        runtime.provider_closed_synthesis(request.ref)
    assert runtime.reap_terminal() == (0, 1)

    reused = synthesis_request(
        response_ref=response_ref,
        stream_id="synthesis-next",
        unit_id=request.ref.unit_id,
        unit_seq=1,
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.start_synthesis(authorized_request(reused))
    assert raised.value.reason == "SYNTHESIS_UNIT_REUSED"
    assert runtime.snapshot().retained_synthesis == 0
    assert runtime.snapshot().retained_synthesis_unit_identities == 1
    assert_zero_authority_effects(runtime)


def test_synthesis_unit_identity_capacity_is_atomic_and_scoped_to_response() -> None:
    runtime = StreamingSpeechConformance(
        native_capability(),
        enabled=True,
        max_synthesis_units_per_response=2,
    )
    response_ref = response()
    runtime.activate_response(response_authority(response_ref))
    for index in range(2):
        request = synthesis_request(
            response_ref=response_ref,
            stream_id=f"synthesis-{index}",
            unit_id=f"unit-{index}",
            unit_seq=index,
        )
        runtime.start_synthesis(authorized_request(request))
        runtime.provider_closed_synthesis(request.ref)
        assert runtime.reap_terminal() == (0, 1)

    before = runtime.snapshot()
    overflow = synthesis_request(
        response_ref=response_ref,
        stream_id="synthesis-overflow",
        unit_id="unit-overflow",
        unit_seq=2,
    )
    with pytest.raises(StreamingSpeechViolation) as capacity:
        runtime.start_synthesis(authorized_request(overflow))
    assert capacity.value.reason == "SYNTHESIS_UNIT_IDENTITY_CAPACITY_EXHAUSTED"
    after = runtime.snapshot()
    assert after.retained_synthesis == 0
    assert after.retained_identity_tombstones == before.retained_identity_tombstones
    assert before.retained_synthesis_unit_identities == 0
    assert len(response_authority(response_ref)._used_units) == 2
    assert after.retained_synthesis_unit_identities == 2
    assert after.pending_provider_controls == 0

    replacement_response = response(response_id="response-2", generation=1)
    runtime.activate_response(response_authority(replacement_response))
    replacement = synthesis_request(
        response_ref=replacement_response,
        stream_id="synthesis-replacement",
        unit_id="unit-0",
        unit_seq=0,
    )
    runtime.start_synthesis(authorized_request(replacement))
    assert runtime.snapshot().active_synthesis == 1
    assert runtime.snapshot().retained_synthesis_unit_identities == 1
    assert_zero_authority_effects(runtime)


@pytest.mark.parametrize(
    ("bad_event", "reason"),
    [
        (
            lambda request: synthesis_event(
                request, seq=1, cursor=0, kind=SynthesisEventKind.STARTED
            ),
            "SYNTHESIS_EVENT_GAP",
        ),
        (
            lambda request: synthesis_event(
                request,
                seq=0,
                cursor=0,
                kind=SynthesisEventKind.CHUNK,
                samples=1,
                display_span=TextSpan(10, 11),
                spoken_span=TextSpan(0, 1),
            ),
            "SYNTHESIS_NOT_STARTED",
        ),
        (
            lambda request: synthesis_event(
                request,
                seq=0,
                cursor=1,
                kind=SynthesisEventKind.STARTED,
            ),
            "SYNTHESIS_AUDIO_CURSOR_GAP",
        ),
        (
            lambda request: synthesis_event(
                request,
                seq=0,
                cursor=0,
                kind=SynthesisEventKind.STARTED,
                provider=ProviderRef("wrong-provider", "formal"),
            ),
            "SYNTHESIS_PROVIDER_MISMATCH",
        ),
        (
            lambda request: replace(
                synthesis_event(
                    request,
                    seq=0,
                    cursor=0,
                    kind=SynthesisEventKind.STARTED,
                ),
                sample_rate_hz=request.sample_rate_hz + 1,
            ),
            "SYNTHESIS_SAMPLE_RATE_MISMATCH",
        ),
    ],
)
def test_synthesis_order_start_cursor_and_provider_faults_fail_close(
    bad_event, reason
) -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_synthesis_event(bad_event(request))
    assert raised.value.reason == reason
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=request.ref,
    )
    assert_zero_authority_effects(runtime)


@pytest.mark.parametrize(
    ("chunk_transform", "reason"),
    [
        (
            lambda event: replace(event, pcm_s16le=b"bad"),
            "INVALID_PCM_S16_CHUNK",
        ),
        (
            lambda event: replace(event, display_span=None),
            "SYNTHESIS_TEXT_SPAN_REQUIRED",
        ),
        (
            lambda event: replace(event, display_span=TextSpan(11, 13)),
            "SYNTHESIS_DISPLAY_SPAN_GAP",
        ),
        (
            lambda event: replace(event, spoken_span=TextSpan(1, 5)),
            "SYNTHESIS_SPOKEN_SPAN_GAP",
        ),
    ],
)
def test_synthesis_chunk_payload_and_span_faults_fail_close(
    chunk_transform, reason
) -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    runtime.accept_synthesis_event(
        synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    valid_chunk = synthesis_event(
        request,
        seq=1,
        cursor=0,
        kind=SynthesisEventKind.CHUNK,
        samples=2,
        display_span=TextSpan(10, 13),
        spoken_span=TextSpan(0, 5),
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_synthesis_event(chunk_transform(valid_chunk))
    assert raised.value.reason == reason
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=request.ref,
    )
    assert_zero_authority_effects(runtime)


def test_duplicate_synthesis_event_fails_close_after_started() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    started = synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    runtime.accept_synthesis_event(started)
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_synthesis_event(started)
    assert raised.value.reason == "DUPLICATE_SYNTHESIS_EVENT"
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=request.ref,
    )
    assert_zero_authority_effects(runtime)


def test_incomplete_synthesis_completion_fails_closed() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    runtime.accept_synthesis_event(
        synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=1,
            display_span=TextSpan(10, 11),
            spoken_span=TextSpan(0, 1),
        )
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_synthesis_event(
            synthesis_event(request, seq=2, cursor=1, kind=SynthesisEventKind.COMPLETED)
        )
    assert raised.value.reason == "INCOMPLETE_SYNTHESIS_TEXT_PROVENANCE"
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=request.ref,
    )
    assert_zero_authority_effects(runtime)


def test_wrong_synthesis_response_unit_identity_fails_exact_stream() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    foreign_ref = replace(request.ref, unit_id="foreign-unit")
    foreign_event = replace(
        synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED),
        ref=foreign_ref,
    )
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_synthesis_event(foreign_event)
    assert raised.value.reason == "SYNTHESIS_IDENTITY_MISMATCH"
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=request.ref,
    )
    assert_zero_authority_effects(runtime)


def test_stale_synthesis_generation_does_not_fence_current_generation() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    first_response = response()
    first = synthesis_request(response_ref=first_response)
    runtime.activate_response(response_authority(first_response))
    runtime.start_synthesis(authorized_request(first))
    runtime.provider_closed_synthesis(first.ref)
    runtime.reap_terminal()

    second_response = response(response_id="response-2", generation=1)
    second = synthesis_request(
        response_ref=second_response,
        stream_generation=1,
    )
    runtime.activate_response(response_authority(second_response))
    runtime.start_synthesis(authorized_request(second))
    with pytest.raises(StreamingSpeechViolation) as raised:
        runtime.accept_synthesis_event(
            synthesis_event(first, seq=0, cursor=0, kind=SynthesisEventKind.CANCELLED)
        )
    assert raised.value.reason == "STALE_SYNTHESIS_STREAM"
    runtime.accept_synthesis_event(
        synthesis_event(second, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    assert runtime.snapshot().active_synthesis == 1
    assert_zero_authority_effects(runtime)


def test_new_response_fences_old_chunks_but_not_new_stream() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    first_response = response()
    first = synthesis_request(response_ref=first_response)
    runtime.activate_response(response_authority(first_response))
    runtime.start_synthesis(authorized_request(first))
    runtime.accept_synthesis_event(
        synthesis_event(first, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )

    second_response = response(response_id="response-2", generation=1)
    runtime.activate_response(response_authority(second_response))
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=first.ref,
    )
    with pytest.raises(StreamingSpeechViolation) as stale:
        runtime.accept_synthesis_event(
            synthesis_event(
                first,
                seq=1,
                cursor=0,
                kind=SynthesisEventKind.CHUNK,
                samples=1,
                display_span=TextSpan(10, 13),
                spoken_span=TextSpan(0, 5),
            )
        )
    assert stale.value.reason == "SYNTHESIS_OUTPUT_FENCED"

    second = synthesis_request(
        response_ref=second_response,
        stream_id="synthesis-2",
        unit_id="unit-2",
    )
    runtime.start_synthesis(authorized_request(second))
    runtime.accept_synthesis_event(
        synthesis_event(second, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    assert runtime.snapshot().active_synthesis == 1
    assert_zero_authority_effects(runtime)


def test_synthesis_cancel_and_noncooperative_provider_retained_cleanup() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    response_ref = response()
    request = synthesis_request(response_ref=response_ref)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    runtime.request_synthesis_cancel(request.ref, reason="local_hard_stop")
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=request.ref,
    )
    assert runtime.reap_terminal() == (0, 0)
    assert runtime.snapshot().retained_synthesis == 1
    with pytest.raises(StreamingSpeechViolation) as late:
        runtime.accept_synthesis_event(
            synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
        )
    assert late.value.reason == "SYNTHESIS_OUTPUT_FENCED"
    runtime.provider_closed_synthesis(request.ref)
    assert runtime.reap_terminal() == (0, 1)
    assert_zero_authority_effects(runtime)


def test_synthesis_cancel_accepts_exact_provider_ack_after_deadline() -> None:
    now = [5.0]
    runtime = StreamingSpeechConformance(
        native_capability(), enabled=True, monotonic=lambda: now[0]
    )
    response_ref = response()
    request = synthesis_request(response_ref=response_ref, event_timeout_seconds=1)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))
    runtime.request_synthesis_cancel(request.ref)
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=request.ref,
    )
    now[0] = 6.0
    cancelled = runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=0,
            cursor=0,
            kind=SynthesisEventKind.CANCELLED,
        )
    )
    assert cancelled.kind is SynthesisEventKind.CANCELLED
    assert runtime.reap_terminal() == (0, 1)
    assert runtime.take_provider_controls() == ()
    assert_zero_authority_effects(runtime)


def test_synthesis_event_timeout_slides_after_each_valid_event() -> None:
    now = [3.0]
    runtime = StreamingSpeechConformance(
        native_capability(), enabled=True, monotonic=lambda: now[0]
    )
    response_ref = response()
    request = synthesis_request(response_ref=response_ref, event_timeout_seconds=1)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(request))

    now[0] = 3.75
    runtime.accept_synthesis_event(
        synthesis_event(request, seq=0, cursor=0, kind=SynthesisEventKind.STARTED)
    )
    now[0] = 4.5
    chunk = runtime.accept_synthesis_event(
        synthesis_event(
            request,
            seq=1,
            cursor=0,
            kind=SynthesisEventKind.CHUNK,
            samples=1,
            display_span=TextSpan(10, 11),
            spoken_span=TextSpan(0, 1),
        )
    )

    assert chunk.kind is SynthesisEventKind.CHUNK
    now[0] = 5.49
    assert runtime.expire() == 0
    now[0] = 5.5
    assert runtime.expire() == 1
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=request.ref,
    )
    assert_zero_authority_effects(runtime)


def test_synthesis_timeout_and_capacity_are_bounded() -> None:
    now = [3.0]
    runtime = StreamingSpeechConformance(
        native_capability(),
        enabled=True,
        max_synthesis_sessions=1,
        monotonic=lambda: now[0],
    )
    first_response = response()
    first = synthesis_request(response_ref=first_response, event_timeout_seconds=1)
    runtime.activate_response(response_authority(first_response))
    runtime.start_synthesis(authorized_request(first))
    with pytest.raises(StreamingSpeechViolation) as capacity:
        runtime.start_synthesis(
            authorized_request(
                synthesis_request(
                    response_ref=first_response,
                    stream_id="synthesis-2",
                    unit_id="unit-2",
                    unit_seq=1,
                )
            )
        )
    assert capacity.value.reason == "SYNTHESIS_CAPACITY_EXHAUSTED"
    now[0] = 4.0
    assert runtime.expire() == 1
    assert_one_provider_cancel(
        runtime,
        kind=ProviderControlKind.CANCEL_SYNTHESIS,
        expected_ref=first.ref,
    )
    assert runtime.reap_terminal() == (0, 0)
    runtime.provider_closed_synthesis(first.ref)
    runtime.reap_terminal()
    second_response = response(response_id="response-2", generation=1)
    runtime.activate_response(response_authority(second_response))
    second = synthesis_request(
        response_ref=second_response,
        stream_id="synthesis-2",
        unit_id="unit-2",
    )
    runtime.start_synthesis(authorized_request(second))
    assert runtime.snapshot().active_synthesis == 1
    assert_zero_authority_effects(runtime)


def test_response_reclamation_never_reactivates_revoked_authority():
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    old = response_authority(response())
    runtime.activate_response(old)
    for index in range(1, 512):
        current = response_authority(
            response(response_id=f"r-{index}", generation=index)
        )
        runtime.activate_response(current)
        assert len(runtime._active_responses) == 1
    with pytest.raises(StreamingSpeechViolation) as denied:
        runtime.activate_response(old)
    assert denied.value.reason == "SPEECH_AUTHORITY_EXPIRED"
    assert runtime.snapshot().active_synthesis == 0
    assert_zero_authority_effects(runtime)


def test_close_fences_new_work_and_retains_both_provider_sessions() -> None:
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    recognition = recognition_ref()
    response_ref = response()
    synthesis = synthesis_request(response_ref=response_ref)
    runtime.start_recognition(authorized_request(recognition), timeout_seconds=5)
    runtime.activate_response(response_authority(response_ref))
    runtime.start_synthesis(authorized_request(synthesis))

    closed = runtime.close()
    assert closed.closed is True
    assert closed.active_recognition == closed.active_synthesis == 0
    assert closed.retained_recognition == closed.retained_synthesis == 1
    controls = runtime.take_provider_controls()
    assert {control.kind for control in controls} == {
        ProviderControlKind.CANCEL_RECOGNITION,
        ProviderControlKind.CANCEL_SYNTHESIS,
    }
    assert all(control.business_cancel is False for control in controls)
    with pytest.raises(StreamingSpeechViolation) as after_close:
        runtime.start_recognition(
            authorized_request(recognition_ref(session_id="recognition-2")),
            timeout_seconds=5,
        )
    assert after_close.value.reason == "STREAMING_SPEECH_CLOSED"

    runtime.provider_closed_recognition(recognition)
    runtime.provider_closed_synthesis(synthesis.ref)
    assert runtime.reap_terminal() == (1, 1)
    assert runtime.close().retained_recognition == 0
    assert runtime.close().retained_synthesis == 0
    assert_zero_authority_effects(runtime)


def test_recognition_retirement_allows_unbounded_sequential_use_but_no_replay():
    runtime = StreamingSpeechConformance(
        native_capability(), enabled=True, max_recognition_sessions=1
    )
    first = None
    for index in range(512):
        request = authorized_request(recognition_ref(session_id=f"capture-{index}"))
        first = first or request
        runtime.start_recognition(request, timeout_seconds=5)
        runtime.provider_closed_recognition(request.ref)
        assert runtime.reap_terminal() == (1, 0)
        assert runtime.snapshot().retained_recognition == 0
        assert runtime.snapshot().retained_identity_tombstones == 0
    with pytest.raises(StreamingSpeechViolation) as denied:
        runtime.start_recognition(first, timeout_seconds=5)
    assert denied.value.reason == "SPEECH_AUTHORITY_EXPIRED"
    replacement = authorized_request(
        recognition_ref(
            session_id=first.ref.session_id, session_generation=1, capture_generation=1
        )
    )
    runtime.start_recognition(replacement, timeout_seconds=5)
    with pytest.raises(StreamingSpeechViolation):
        runtime.provider_closed_recognition(first.ref)
    runtime.accept_audio_frame(frame(replacement.ref, seq=0, cursor=0))
    assert runtime.snapshot().active_recognition == 1
    runtime.provider_closed_recognition(replacement.ref)
    runtime.reap_terminal()
    assert_zero_authority_effects(runtime)



def test_synthesis_retirement_allows_many_responses_but_never_replays_old_request():
    runtime = StreamingSpeechConformance(native_capability(), enabled=True)
    first = None
    for index in range(512):
        ref = response(response_id=f"reply-{index}", generation=index)
        runtime.activate_response(response_authority(ref))
        request = authorized_request(
            synthesis_request(response_ref=ref, stream_id=f"speech-{index}")
        )
        first = first or request
        runtime.start_synthesis(request)
        runtime.provider_closed_synthesis(request.ref)
        assert runtime.reap_terminal() == (0, 1)
        assert runtime.snapshot().retained_synthesis == 0
        assert runtime.snapshot().retained_identity_tombstones == 0
        assert runtime._active_responses == {}
    with pytest.raises(StreamingSpeechViolation):
        runtime.start_synthesis(first)
    with pytest.raises(StreamingSpeechViolation):
        runtime.provider_closed_synthesis(first.ref)
    assert runtime.snapshot().active_synthesis == 0
    assert_zero_authority_effects(runtime)
