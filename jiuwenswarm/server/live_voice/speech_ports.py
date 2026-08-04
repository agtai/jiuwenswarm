# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Provider-neutral deterministic speech recognition and synthesis ports."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, replace
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseFence, ResponseRef


class SpeechPortViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class SpeechMode(StrEnum):
    BATCH = "batch"
    STREAM = "stream"


class RecognitionEventKind(StrEnum):
    PARTIAL = "partial"
    FINAL = "final"
    CANCELLED = "cancelled"


class SynthesisEventKind(StrEnum):
    STARTED = "started"
    CHUNK = "chunk"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ProviderRef:
    provider_id: str
    implementation_class: str
    fallback_from: str | None = None


@dataclass(frozen=True, slots=True)
class SpeechCapability:
    provider: ProviderRef
    recognition_modes: frozenset[SpeechMode]
    synthesis_modes: frozenset[SpeechMode]
    available: bool = True


@dataclass(frozen=True, slots=True)
class RecognitionAlternative:
    raw_text: str
    display_text: str
    confidence: float | None


@dataclass(frozen=True, slots=True)
class RecognitionHypothesis:
    alternatives: tuple[RecognitionAlternative, ...]
    selected_index: int = 0

    @property
    def selected(self) -> RecognitionAlternative:
        return self.alternatives[self.selected_index]


@dataclass(frozen=True, slots=True)
class RecognitionEvent:
    session_id: str
    generation: int
    seq: int
    kind: RecognitionEventKind
    provider: ProviderRef
    hypothesis: RecognitionHypothesis | None


@dataclass(frozen=True, slots=True)
class RecognitionSession:
    session_id: str
    generation: int
    mode: SpeechMode
    provider: ProviderRef
    terminal: bool = False
    next_seq: int = 0


@dataclass(frozen=True, slots=True)
class ResolvedRecognition:
    raw_text: str
    display_text: str
    confidence: float | None
    selected_index: int
    provider: ProviderRef


@dataclass(frozen=True, slots=True)
class CriticalSpeechDecision:
    eligible: bool
    clarification_required: bool
    blocked: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class RenderTransform:
    transform: str
    source_start: int
    source_end: int
    rendered_text: str


@dataclass(frozen=True, slots=True)
class RenderPlan:
    display_text: str
    display_sha256: str
    spoken_text: str
    transforms: tuple[RenderTransform, ...]


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    request_id: str
    response: ResponseRef
    unit_id: str
    span_start: int
    span_end: int
    render_plan: RenderPlan
    mode: SpeechMode


@dataclass(frozen=True, slots=True)
class SynthesisEvent:
    request_id: str
    response: ResponseRef
    unit_id: str
    seq: int
    kind: SynthesisEventKind
    provider: ProviderRef
    audio: bytes | None = None


class RecognitionPort:
    def __init__(self, capability: SpeechCapability) -> None:
        _validate_capability(capability)
        self._capability = capability
        self._lock = threading.RLock()
        self._sessions: dict[str, RecognitionSession] = {}
        self._last_generation: dict[str, int] = {}

    def start(self, session_id: str, mode: SpeechMode) -> RecognitionSession:
        with self._lock:
            self._require_available(mode, recognition=True)
            if not session_id.strip():
                raise SpeechPortViolation(
                    "INVALID_SESSION_ID", "session_id must be non-empty"
                )
            generation = self._last_generation.get(session_id, -1) + 1
            session = RecognitionSession(
                session_id, generation, mode, self._capability.provider
            )
            self._sessions[session_id] = session
            self._last_generation[session_id] = generation
            return session

    def emit(
        self,
        session_id: str,
        generation: int,
        kind: RecognitionEventKind,
        hypothesis: RecognitionHypothesis | None = None,
    ) -> RecognitionEvent:
        with self._lock:
            session = self._require_session(session_id, generation)
            if session.terminal:
                raise SpeechPortViolation(
                    "RECOGNITION_ALREADY_TERMINAL",
                    "a recognition session cannot emit after its terminal event",
                )
            if kind in {RecognitionEventKind.PARTIAL, RecognitionEventKind.FINAL}:
                self._validate_hypothesis(hypothesis)
            elif hypothesis is not None:
                raise SpeechPortViolation(
                    "CANCELLED_HYPOTHESIS_FORBIDDEN",
                    "cancelled recognition cannot carry a hypothesis",
                )
            event = RecognitionEvent(
                session_id,
                generation,
                session.next_seq,
                kind,
                session.provider,
                hypothesis,
            )
            terminal = kind in {
                RecognitionEventKind.FINAL,
                RecognitionEventKind.CANCELLED,
            }
            self._sessions[session_id] = replace(
                session, terminal=terminal, next_seq=session.next_seq + 1
            )
            return event

    @staticmethod
    def resolve(
        event: RecognitionEvent, *, selected_index: int | None = None
    ) -> ResolvedRecognition:
        if (
            event.kind
            not in {
                RecognitionEventKind.PARTIAL,
                RecognitionEventKind.FINAL,
            }
            or event.hypothesis is None
        ):
            raise SpeechPortViolation(
                "HYPOTHESIS_REQUIRED", "only hypothesis events can be resolved"
            )
        index = (
            event.hypothesis.selected_index
            if selected_index is None
            else selected_index
        )
        if type(index) is not int or not 0 <= index < len(
            event.hypothesis.alternatives
        ):
            raise SpeechPortViolation(
                "INVALID_ALTERNATIVE_INDEX", "selected alternative is unavailable"
            )
        alternative = event.hypothesis.alternatives[index]
        return ResolvedRecognition(
            alternative.raw_text,
            alternative.display_text,
            alternative.confidence,
            index,
            event.provider,
        )

    @staticmethod
    def critical_decision(
        event: RecognitionEvent, *, minimum_confidence: float
    ) -> CriticalSpeechDecision:
        if type(minimum_confidence) not in {int, float} or not (
            0 <= minimum_confidence <= 1
        ):
            raise SpeechPortViolation(
                "INVALID_CONFIDENCE_THRESHOLD",
                "minimum confidence must be between zero and one",
            )
        if event.kind is not RecognitionEventKind.FINAL or event.hypothesis is None:
            return CriticalSpeechDecision(False, False, True, "FINAL_REQUIRED")
        selected = event.hypothesis.selected
        if selected.confidence is None:
            return CriticalSpeechDecision(False, True, False, "CONFIDENCE_UNKNOWN")
        if selected.confidence < minimum_confidence:
            return CriticalSpeechDecision(False, True, False, "LOW_CONFIDENCE")
        return CriticalSpeechDecision(True, False, False, None)

    def _require_available(self, mode: SpeechMode, *, recognition: bool) -> None:
        modes = (
            self._capability.recognition_modes
            if recognition
            else self._capability.synthesis_modes
        )
        if not self._capability.available:
            raise SpeechPortViolation(
                "SPEECH_PROVIDER_UNAVAILABLE", "speech provider is unavailable"
            )
        if mode not in modes:
            raise SpeechPortViolation(
                "SPEECH_MODE_UNSUPPORTED", f"speech mode {mode.value!r} is unsupported"
            )

    def _require_session(self, session_id: str, generation: int) -> RecognitionSession:
        session = self._sessions.get(session_id)
        if session is None or session.generation != generation:
            raise SpeechPortViolation(
                "STALE_RECOGNITION_SESSION",
                "recognition event must match the exact session generation",
            )
        return session

    @staticmethod
    def _validate_hypothesis(
        hypothesis: RecognitionHypothesis | None,
    ) -> None:
        if hypothesis is None or not hypothesis.alternatives:
            raise SpeechPortViolation(
                "EMPTY_HYPOTHESIS", "recognition hypothesis requires alternatives"
            )
        if not 0 <= hypothesis.selected_index < len(hypothesis.alternatives):
            raise SpeechPortViolation(
                "INVALID_ALTERNATIVE_INDEX", "selected alternative is unavailable"
            )
        for alternative in hypothesis.alternatives:
            if not alternative.raw_text.strip() or not alternative.display_text.strip():
                raise SpeechPortViolation(
                    "EMPTY_RECOGNITION_TEXT",
                    "raw and display recognition text must be non-empty",
                )
            if alternative.confidence is not None and (
                type(alternative.confidence) not in {int, float}
                or not 0 <= alternative.confidence <= 1
            ):
                raise SpeechPortViolation(
                    "INVALID_CONFIDENCE", "confidence must be between zero and one"
                )


class SynthesisPort:
    def __init__(self, capability: SpeechCapability) -> None:
        _validate_capability(capability)
        self._capability = capability
        self._lock = threading.RLock()
        self._requests: dict[str, tuple[SynthesisRequest, int, bool]] = {}
        self._response_fence = ResponseFence()

    def activate_response(self, response: ResponseRef) -> None:
        self._response_fence.begin(response)

    @staticmethod
    def create_render_plan(
        display_text: str,
        spoken_text: str,
        transforms: tuple[RenderTransform, ...] = (),
    ) -> RenderPlan:
        if not display_text.strip() or not spoken_text.strip():
            raise SpeechPortViolation(
                "EMPTY_SYNTHESIS_TEXT", "display and spoken text must be non-empty"
            )
        for transform in transforms:
            if (
                type(transform.source_start) is not int
                or type(transform.source_end) is not int
                or transform.source_start < 0
                or transform.source_end < transform.source_start
                or transform.source_end > len(display_text)
            ):
                raise SpeechPortViolation(
                    "INVALID_RENDER_SPAN", "render transform span is invalid"
                )
        return RenderPlan(
            display_text,
            hashlib.sha256(display_text.encode("utf-8")).hexdigest(),
            spoken_text,
            transforms,
        )

    def start(self, request: SynthesisRequest) -> SynthesisEvent:
        with self._lock:
            RecognitionPort(self._capability)._require_available(
                request.mode, recognition=False
            )
            if not request.request_id.strip() or not request.unit_id.strip():
                raise SpeechPortViolation(
                    "INVALID_SYNTHESIS_ID", "synthesis identifiers must be non-empty"
                )
            validated_plan = self.create_render_plan(
                request.render_plan.display_text,
                request.render_plan.spoken_text,
                request.render_plan.transforms,
            )
            if validated_plan != request.render_plan:
                raise SpeechPortViolation(
                    "DISPLAY_HASH_MISMATCH",
                    "render plan does not match its display text",
                )
            if (
                request.span_start < 0
                or request.span_end < request.span_start
                or request.span_end > len(request.render_plan.display_text)
            ):
                raise SpeechPortViolation(
                    "INVALID_SYNTHESIS_SPAN", "synthesis display span is invalid"
                )
            if request.request_id in self._requests:
                raise SpeechPortViolation(
                    "SYNTHESIS_REQUEST_REUSED",
                    "synthesis request identifiers cannot be reused",
                )
            self._response_fence.apply_if_current(request.response, lambda: None)
            self._requests[request.request_id] = (request, 1, False)
            return SynthesisEvent(
                request.request_id,
                request.response,
                request.unit_id,
                0,
                SynthesisEventKind.STARTED,
                self._capability.provider,
            )

    def emit_chunk(self, request_id: str, audio: bytes) -> SynthesisEvent:
        return self._emit(request_id, SynthesisEventKind.CHUNK, audio)

    def complete(self, request_id: str) -> SynthesisEvent:
        return self._emit(request_id, SynthesisEventKind.COMPLETED, None)

    def cancel(self, request_id: str) -> SynthesisEvent:
        return self._emit(request_id, SynthesisEventKind.CANCELLED, None)

    def _emit(
        self,
        request_id: str,
        kind: SynthesisEventKind,
        audio: bytes | None,
    ) -> SynthesisEvent:
        with self._lock:
            entry = self._requests.get(request_id)
            if entry is None:
                raise SpeechPortViolation(
                    "SYNTHESIS_REQUEST_NOT_FOUND", "synthesis request does not exist"
                )
            request, seq, terminal = entry
            if terminal:
                raise SpeechPortViolation(
                    "SYNTHESIS_ALREADY_TERMINAL",
                    "synthesis cannot emit after a terminal event",
                )
            if kind is SynthesisEventKind.CHUNK:
                self._response_fence.apply_if_current(request.response, lambda: None)
            if kind is SynthesisEventKind.CHUNK:
                if type(audio) is not bytes or not audio:
                    raise SpeechPortViolation(
                        "INVALID_AUDIO_CHUNK", "audio chunk must be non-empty bytes"
                    )
            elif audio is not None:
                raise SpeechPortViolation(
                    "TERMINAL_AUDIO_FORBIDDEN",
                    "terminal synthesis events cannot carry audio",
                )
            now_terminal = kind in {
                SynthesisEventKind.COMPLETED,
                SynthesisEventKind.CANCELLED,
            }
            self._requests[request_id] = (request, seq + 1, now_terminal)
            return SynthesisEvent(
                request.request_id,
                request.response,
                request.unit_id,
                seq,
                kind,
                self._capability.provider,
                audio,
            )


def _validate_capability(capability: SpeechCapability) -> None:
    provider = capability.provider
    if not provider.provider_id.strip():
        raise SpeechPortViolation(
            "INVALID_PROVIDER_ID", "provider_id must be non-empty"
        )
    if provider.implementation_class not in {
        "formal",
        "fallback",
        "demo_substitute",
        "unsupported",
    }:
        raise SpeechPortViolation(
            "INVALID_IMPLEMENTATION_CLASS", "speech implementation class is invalid"
        )
    if provider.implementation_class == "fallback" and not provider.fallback_from:
        raise SpeechPortViolation(
            "FALLBACK_PROVENANCE_REQUIRED",
            "fallback speech must identify the replaced provider",
        )
    if (
        provider.implementation_class != "fallback"
        and provider.fallback_from is not None
    ):
        raise SpeechPortViolation(
            "UNEXPECTED_FALLBACK_PROVENANCE",
            "only fallback speech may identify a replaced provider",
        )
