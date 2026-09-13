# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ContractViolation,
    ResponseRef,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEventKind,
    RecognitionHypothesis,
    RecognitionPort,
    RenderTransform,
    SpeechCapability,
    SpeechMode,
    SpeechPortViolation,
    SynthesisEventKind,
    SynthesisPort,
    SynthesisRequest,
)


def capability(*, fallback: bool = False) -> SpeechCapability:
    return SpeechCapability(
        ProviderRef(
            "fallback-speech" if fallback else "formal-speech",
            "fallback" if fallback else "formal",
            "formal-speech" if fallback else None,
        ),
        frozenset({SpeechMode.BATCH, SpeechMode.STREAM}),
        frozenset({SpeechMode.BATCH, SpeechMode.STREAM}),
    )


def hypothesis(confidence=0.9) -> RecognitionHypothesis:
    return RecognitionHypothesis(
        (
            RecognitionAlternative("raw one", "Raw one", confidence),
            RecognitionAlternative("raw two", "Raw two", None),
        )
    )


def test_recognition_partial_final_order_and_immutable_text() -> None:
    port = RecognitionPort(capability())
    session = port.start("session-1", SpeechMode.STREAM)
    source = hypothesis()
    partial = port.emit(
        session.session_id,
        session.generation,
        RecognitionEventKind.PARTIAL,
        source,
    )
    final = port.emit(
        session.session_id,
        session.generation,
        RecognitionEventKind.FINAL,
        source,
    )
    assert (partial.seq, final.seq) == (0, 1)
    assert final.hypothesis.selected.raw_text == "raw one"
    assert final.hypothesis.selected.display_text == "Raw one"
    with pytest.raises(AttributeError):
        final.hypothesis.selected.raw_text = "mutated"
    with pytest.raises(SpeechPortViolation) as raised:
        port.emit(
            session.session_id,
            session.generation,
            RecognitionEventKind.PARTIAL,
            source,
        )
    assert raised.value.reason == "RECOGNITION_ALREADY_TERMINAL"


def test_final_is_evidence_not_agent_tool_or_task_dispatch() -> None:
    port = RecognitionPort(capability())
    session = port.start("session-1", SpeechMode.BATCH)
    event = port.emit(
        session.session_id,
        session.generation,
        RecognitionEventKind.FINAL,
        hypothesis(),
    )
    assert event.kind is RecognitionEventKind.FINAL
    assert not hasattr(event, "turn_commit")
    assert not hasattr(port, "dispatch_agent")
    assert not hasattr(port, "dispatch_tool")
    assert not hasattr(port, "dispatch_task")


def test_resolver_keeps_raw_and_display_and_unknown_confidence_requires_clarification() -> (
    None
):
    port = RecognitionPort(capability(fallback=True))
    session = port.start("session-1", SpeechMode.STREAM)
    event = port.emit(
        session.session_id,
        session.generation,
        RecognitionEventKind.FINAL,
        hypothesis(),
    )
    resolved = port.resolve(event, selected_index=1)
    decision = port.critical_decision(
        RecognitionEventKind.FINAL and event, minimum_confidence=0.8
    )
    unknown_event = type(event)(
        event.session_id,
        event.generation,
        event.seq,
        event.kind,
        event.provider,
        RecognitionHypothesis((RecognitionAlternative("x", "X", None),)),
    )
    unknown = port.critical_decision(unknown_event, minimum_confidence=0.8)
    assert resolved.raw_text == "raw two"
    assert resolved.display_text == "Raw two"
    assert resolved.provider.implementation_class == "fallback"
    assert decision.eligible is True
    assert unknown.clarification_required is True
    assert unknown.reason == "CONFIDENCE_UNKNOWN"


def test_cancel_is_terminal_and_stale_generation_rejects() -> None:
    port = RecognitionPort(capability())
    first = port.start("session-1", SpeechMode.STREAM)
    cancelled = port.emit(
        first.session_id, first.generation, RecognitionEventKind.CANCELLED
    )
    assert cancelled.kind is RecognitionEventKind.CANCELLED
    second = port.start("session-1", SpeechMode.STREAM)
    assert second.generation == first.generation + 1
    with pytest.raises(SpeechPortViolation) as raised:
        port.emit(
            first.session_id,
            first.generation,
            RecognitionEventKind.PARTIAL,
            hypothesis(),
        )
    assert raised.value.reason == "STALE_RECOGNITION_SESSION"


def test_render_plan_preserves_display_span_and_explicit_transforms() -> None:
    transform = RenderTransform(
        "expand.abbreviation", 0, 3, "World Health Organization"
    )
    plan = SynthesisPort.create_render_plan(
        "WHO update", "World Health Organization update", (transform,)
    )
    assert plan.display_text == "WHO update"
    assert plan.spoken_text == "World Health Organization update"
    assert len(plan.display_sha256) == 64
    assert plan.transforms == (transform,)


def test_synthesis_orders_chunks_and_keeps_exact_response_and_fallback() -> None:
    port = SynthesisPort(capability(fallback=True))
    ref = ResponseRef("interaction-1", "response-1", 2)
    port.activate_response(ref)
    plan = port.create_render_plan("Hello", "Hello")
    request = SynthesisRequest(
        "synthesis-1", ref, "unit-1", 0, 5, plan, SpeechMode.STREAM
    )
    started = port.start(request)
    chunk = port.emit_chunk(request.request_id, b"audio")
    completed = port.complete(request.request_id)
    assert [started.seq, chunk.seq, completed.seq] == [0, 1, 2]
    assert chunk.response == ref
    assert chunk.provider.implementation_class == "fallback"
    assert chunk.provider.fallback_from == "formal-speech"
    assert completed.kind is SynthesisEventKind.COMPLETED
    with pytest.raises(SpeechPortViolation) as raised:
        port.emit_chunk(request.request_id, b"late")
    assert raised.value.reason == "SYNTHESIS_ALREADY_TERMINAL"


def test_stale_synthesis_response_produces_no_new_chunk() -> None:
    port = SynthesisPort(capability())
    first = ResponseRef("interaction-1", "response-1", 0)
    second = ResponseRef("interaction-1", "response-2", 1)
    plan = port.create_render_plan("Hello", "Hello")
    port.activate_response(first)
    port.start(
        SynthesisRequest("synthesis-1", first, "unit-1", 0, 5, plan, SpeechMode.STREAM)
    )
    port.activate_response(second)
    with pytest.raises(ContractViolation) as raised:
        port.emit_chunk("synthesis-1", b"late")
    assert raised.value.reason == "STALE_RESPONSE_OUTPUT"


def test_invalid_confidence_threshold_and_fallback_provenance_reject() -> None:
    port = RecognitionPort(capability())
    session = port.start("session", SpeechMode.BATCH)
    event = port.emit(
        session.session_id,
        session.generation,
        RecognitionEventKind.FINAL,
        hypothesis(),
    )
    with pytest.raises(SpeechPortViolation) as raised:
        port.critical_decision(event, minimum_confidence=1.1)
    assert raised.value.reason == "INVALID_CONFIDENCE_THRESHOLD"
    with pytest.raises(SpeechPortViolation) as raised:
        RecognitionPort(
            SpeechCapability(
                ProviderRef("fallback", "fallback"),
                frozenset({SpeechMode.BATCH}),
                frozenset({SpeechMode.BATCH}),
            )
        )
    assert raised.value.reason == "FALLBACK_PROVENANCE_REQUIRED"


def test_boolean_confidence_rejects_and_stale_provider_cancel_can_finish() -> None:
    recognition = RecognitionPort(capability())
    session = recognition.start("session", SpeechMode.BATCH)
    with pytest.raises(SpeechPortViolation) as raised:
        recognition.emit(
            session.session_id,
            session.generation,
            RecognitionEventKind.FINAL,
            RecognitionHypothesis((RecognitionAlternative("x", "X", True),)),
        )
    assert raised.value.reason == "INVALID_CONFIDENCE"

    synthesis = SynthesisPort(capability())
    first = ResponseRef("interaction", "response-1", 0)
    second = ResponseRef("interaction", "response-2", 1)
    plan = synthesis.create_render_plan("X", "X")
    synthesis.activate_response(first)
    synthesis.start(
        SynthesisRequest("synthesis", first, "unit", 0, 1, plan, SpeechMode.STREAM)
    )
    synthesis.activate_response(second)
    cancelled = synthesis.cancel("synthesis")
    assert cancelled.kind is SynthesisEventKind.CANCELLED
    assert cancelled.response == first
