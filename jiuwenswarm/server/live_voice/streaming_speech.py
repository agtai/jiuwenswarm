# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Provider-neutral conformance boundary for native streaming Speech.

This module deliberately stops at the Speech Provider boundary.  It validates
native streaming sessions and returns Provider-control data, but it does not
commit a Turn, mutate Conversation/history/chat state, or dispatch Agent, Tool,
or Task work.  A polled batch operation is never accepted as a streaming
capability.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Collection
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    ResponseRef,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEventKind,
    RecognitionHypothesis,
    SpeechMode,
    SynthesisEventKind,
)


MAX_STREAM_TIMEOUT_SECONDS = 300.0
MAX_AUDIO_SAMPLES_PER_FRAME = 96_000
MAX_ID_CHARS = 256
MAX_CANCEL_REASON_CHARS = 256
MAX_RECOGNITION_ALTERNATIVES = 8
MAX_RECOGNITION_TEXT_CHARS = 16_000
MAX_SYNTHESIS_TEXT_CHARS = 4_000


class StreamingSpeechViolation(ValueError):
    """A fail-closed streaming Provider/session conformance violation."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ProviderTransport(StrEnum):
    NATIVE_STREAM = "native_stream"
    BATCH_REQUEST = "batch_request"
    POLLING = "polling"
    UNSUPPORTED = "unsupported"


class CapabilityProvenance(StrEnum):
    """How a streaming capability fact was established.

    ``UNAVAILABLE`` is an explicit acceptance gap, not a negative runtime
    result and never release credit.  In particular, a transport close or
    input-buffer clear must not be promoted to a Provider cancel ACK.
    """

    PROVIDER_NATIVE = "provider_native"
    ADAPTER_DERIVED = "adapter_derived"
    TRANSPORT_OBSERVED = "transport_observed"
    UNAVAILABLE = "unavailable"


class ProviderControlKind(StrEnum):
    CANCEL_RECOGNITION = "cancel_recognition"
    CANCEL_SYNTHESIS = "cancel_synthesis"


class RecognitionTurnDetectionMode(StrEnum):
    MANUAL = "manual"
    SERVER_VAD = "server_vad"
    SEMANTIC_VAD = "semantic_vad"


class RecognitionTurnBoundaryKind(StrEnum):
    SPEECH_STARTED = "speech_started"
    SPEECH_STOPPED = "speech_stopped"
    COMMITTED = "committed"


class RecognitionTimingBasis(StrEnum):
    EXACT_SOURCE_CURSOR = "exact_source_cursor"
    PROVIDER_TIME = "provider_time"


class RecognitionCommitDisposition(StrEnum):
    CLIENT_COMMIT_SENT = "client_commit_sent"
    SERVER_VAD_PENDING = "server_vad_pending"
    SERVER_VAD_OBSERVED = "server_vad_observed"
    SEMANTIC_VAD_PENDING = "semantic_vad_pending"
    SEMANTIC_VAD_OBSERVED = "semantic_vad_observed"


@dataclass(frozen=True, slots=True)
class ServerVadConfig:
    threshold: float = 0.5
    prefix_padding_ms: int = 300
    # The Provider default of 500 ms cuts ordinary breath pauses into separate
    # turns. Keep server VAD's already-proven event contract, but allow a
    # natural sentence-internal pause before committing the user's turn.
    silence_duration_ms: int = 1_200
    create_response: bool = False
    interrupt_response: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, (int, float))
            or not math.isfinite(self.threshold)
            or not 0 < self.threshold < 1
        ):
            raise StreamingSpeechViolation(
                "INVALID_SERVER_VAD", "server VAD threshold must be in (0, 1)"
            )
        _uint(self.prefix_padding_ms, "server_vad.prefix_padding_ms")
        _uint(self.silence_duration_ms, "server_vad.silence_duration_ms")
        if not 0 < self.prefix_padding_ms <= 5_000:
            raise StreamingSpeechViolation(
                "INVALID_SERVER_VAD", "server VAD prefix padding is out of bounds"
            )
        if not 0 < self.silence_duration_ms <= 10_000:
            raise StreamingSpeechViolation(
                "INVALID_SERVER_VAD", "server VAD silence duration is out of bounds"
            )
        if self.create_response is not False or self.interrupt_response is not False:
            raise StreamingSpeechViolation(
                "SERVER_VAD_BUSINESS_AUTHORITY_FORBIDDEN",
                "Speech turn detection cannot create or interrupt Agent responses",
            )


class SemanticVadEagerness(StrEnum):
    AUTO = "auto"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class SemanticVadConfig:
    eagerness: SemanticVadEagerness = SemanticVadEagerness.AUTO
    create_response: bool = False
    interrupt_response: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.eagerness, SemanticVadEagerness):
            raise StreamingSpeechViolation("INVALID_SEMANTIC_VAD", "semantic VAD eagerness is invalid")
        if self.create_response is not False or self.interrupt_response is not False:
            raise StreamingSpeechViolation("SEMANTIC_VAD_BUSINESS_AUTHORITY_FORBIDDEN", "Speech turn detection cannot create or interrupt Agent responses")


@dataclass(frozen=True, slots=True)
class RecognitionTurnDetection:
    mode: RecognitionTurnDetectionMode
    server_vad: ServerVadConfig | None = None
    semantic_vad: SemanticVadConfig | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, RecognitionTurnDetectionMode):
            raise StreamingSpeechViolation(
                "INVALID_TURN_DETECTION", "recognition turn detection mode is invalid"
            )
        if self.mode is RecognitionTurnDetectionMode.MANUAL:
            if self.server_vad is not None or self.semantic_vad is not None:
                raise StreamingSpeechViolation(
                    "INVALID_TURN_DETECTION", "manual turn detection cannot carry VAD"
                )
        elif self.mode is RecognitionTurnDetectionMode.SERVER_VAD:
            if not isinstance(self.server_vad, ServerVadConfig) or self.semantic_vad is not None:
                raise StreamingSpeechViolation("INVALID_TURN_DETECTION", "server VAD mode requires only its typed config")
        elif not isinstance(self.semantic_vad, SemanticVadConfig) or self.server_vad is not None:
            raise StreamingSpeechViolation("INVALID_TURN_DETECTION", "semantic VAD mode requires only its typed config")

    @classmethod
    def manual(cls) -> "RecognitionTurnDetection":
        return cls(RecognitionTurnDetectionMode.MANUAL)

    @classmethod
    def server_vad_default(cls) -> "RecognitionTurnDetection":
        return cls(RecognitionTurnDetectionMode.SERVER_VAD, ServerVadConfig())

    @classmethod
    def semantic_vad_configured(cls, eagerness: SemanticVadEagerness) -> "RecognitionTurnDetection":
        return cls(RecognitionTurnDetectionMode.SEMANTIC_VAD, semantic_vad=SemanticVadConfig(eagerness))

    @classmethod
    def server_vad_barge_in(cls) -> "RecognitionTurnDetection":
        """Retain a wider speech prefix only for capture overlapping TTS."""

        return cls(
            RecognitionTurnDetectionMode.SERVER_VAD,
            ServerVadConfig(prefix_padding_ms=800),
        )


@dataclass(frozen=True, slots=True)
class RecognitionProviderSupport:
    modes: frozenset[SpeechMode]
    transport: ProviderTransport
    ordered_events: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE
    exact_audio_cursor: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE
    provider_cancel_ack: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE
    native_partials: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE
    server_vad: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE
    semantic_vad: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE


@dataclass(frozen=True, slots=True)
class SynthesisProviderSupport:
    modes: frozenset[SpeechMode]
    transport: ProviderTransport
    ordered_events: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE
    exact_audio_cursor: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE
    provider_cancel_ack: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE
    chunk_text_spans: CapabilityProvenance = CapabilityProvenance.UNAVAILABLE


@dataclass(frozen=True, slots=True)
class StreamingProviderCapability:
    provider: ProviderRef
    recognition: RecognitionProviderSupport
    synthesis: SynthesisProviderSupport
    available: bool = True

    @property
    def has_declared_acceptance_gaps(self) -> bool:
        """Whether unavailable facts explicitly block capability completeness.

        ``False`` is not Alpha Gate credit; runtime and immutable evidence remain
        separate requirements.
        """

        return bool(self.acceptance_gaps)

    @property
    def acceptance_gaps(self) -> tuple[str, ...]:
        """Stable fields that remain unavailable for formal Alpha acceptance."""

        gaps: list[str] = [] if self.available else ["provider.available"]
        for direction, support, fields in (
            (
                "recognition",
                self.recognition,
                (
                    "ordered_events",
                    "exact_audio_cursor",
                    "provider_cancel_ack",
                    "native_partials",
                ),
            ),
            (
                "synthesis",
                self.synthesis,
                (
                    "ordered_events",
                    "exact_audio_cursor",
                    "provider_cancel_ack",
                    "chunk_text_spans",
                ),
            ),
        ):
            if SpeechMode.STREAM not in support.modes:
                gaps.append(f"{direction}.stream_mode")
            if support.transport is not ProviderTransport.NATIVE_STREAM:
                gaps.append(f"{direction}.native_transport")
            gaps.extend(
                f"{direction}.{field_name}"
                for field_name in fields
                if getattr(support, field_name) is CapabilityProvenance.UNAVAILABLE
            )
        return tuple(gaps)


@dataclass(frozen=True, slots=True)
class CaptureRef:
    capture_id: str
    capture_generation: int
    sample_rate_hz: int


@dataclass(frozen=True, slots=True)
class RecognitionStreamRef:
    session_id: str
    session_generation: int
    capture: CaptureRef


@dataclass(frozen=True, slots=True)
class RecognitionStreamRequest:
    ref: RecognitionStreamRef
    turn_detection: RecognitionTurnDetection


@dataclass(frozen=True, slots=True)
class RecognitionAudioFrame:
    ref: RecognitionStreamRef
    seq: int
    sample_cursor: int
    sample_count: int
    pcm_f32le: bytes


@dataclass(frozen=True, slots=True)
class StreamingRecognitionEvent:
    ref: RecognitionStreamRef
    provider: ProviderRef
    seq: int
    audio_cursor: int | None
    kind: RecognitionEventKind
    hypothesis: RecognitionHypothesis | None = None
    timing_basis: RecognitionTimingBasis = RecognitionTimingBasis.EXACT_SOURCE_CURSOR
    timing_provenance: CapabilityProvenance = CapabilityProvenance.ADAPTER_DERIVED


@dataclass(frozen=True, slots=True)
class RecognitionTurnBoundaryEvent:
    ref: RecognitionStreamRef
    provider: ProviderRef
    seq: int
    kind: RecognitionTurnBoundaryKind
    provider_item_id: str = field(repr=False)
    provider_start_ms: int | None = None
    provider_end_ms: int | None = None
    timing_basis: RecognitionTimingBasis = RecognitionTimingBasis.PROVIDER_TIME
    timing_provenance: CapabilityProvenance = CapabilityProvenance.ADAPTER_DERIVED


StreamingRecognitionOutput = StreamingRecognitionEvent | RecognitionTurnBoundaryEvent


@dataclass(frozen=True, slots=True)
class TextSpan:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class SynthesisStreamRef:
    stream_id: str
    stream_generation: int
    response: ResponseRef
    unit_id: str
    unit_seq: int


@dataclass(frozen=True, slots=True)
class SynthesisStreamRequest:
    ref: SynthesisStreamRef
    display_text: str
    spoken_text: str
    display_span: TextSpan
    sample_rate_hz: int
    # Maximum idle interval until the next valid Provider synthesis event.
    # This is deliberately not a whole-stream duration budget.
    event_timeout_seconds: float


@dataclass(frozen=True, slots=True)
class StreamingSynthesisEvent:
    ref: SynthesisStreamRef
    provider: ProviderRef
    seq: int
    sample_cursor: int
    kind: SynthesisEventKind
    sample_rate_hz: int
    sample_count: int = 0
    pcm_s16le: bytes | None = None
    display_span: TextSpan | None = None
    spoken_span: TextSpan | None = None


class NativeStreamingSpeechProvider(Protocol):
    """Provider-neutral operational port implemented by streaming Adapters."""

    @property
    def capability(self) -> StreamingProviderCapability: ...

    @property
    def conformance(self) -> StreamingSpeechConformance: ...

    @property
    def synthesis_model(self) -> str: ...

    @property
    def synthesis_voice(self) -> str | None: ...

    async def open_recognition(
        self, request: RecognitionStreamRequest, *, timeout_seconds: float
    ) -> None: ...

    async def send_recognition_audio(self, frame: RecognitionAudioFrame) -> None: ...

    async def commit_recognition(
        self, ref: RecognitionStreamRef
    ) -> RecognitionCommitDisposition: ...

    async def next_recognition_event(
        self, ref: RecognitionStreamRef, *, timeout_seconds: float
    ) -> StreamingRecognitionOutput: ...

    async def cancel_recognition(
        self, ref: RecognitionStreamRef, *, reason: str = "caller_cancel"
    ) -> None: ...

    async def open_synthesis(self, request: SynthesisStreamRequest) -> None: ...

    async def next_synthesis_event(
        self, ref: SynthesisStreamRef, *, timeout_seconds: float
    ) -> StreamingSynthesisEvent: ...

    async def cancel_synthesis(
        self, ref: SynthesisStreamRef, *, reason: str = "caller_cancel"
    ) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ProviderCancelControl:
    kind: ProviderControlKind
    ref: RecognitionStreamRef | SynthesisStreamRef
    reason: str
    business_cancel: bool = False


@dataclass(frozen=True, slots=True)
class StreamingSpeechSnapshot:
    enabled: bool
    closed: bool
    active_recognition: int
    active_synthesis: int
    retained_recognition: int
    retained_synthesis: int
    pending_provider_controls: int
    retained_identity_tombstones: int
    retained_synthesis_unit_identities: int
    agent_dispatches: int = 0
    tool_dispatches: int = 0
    task_mutations: int = 0
    chat_mutations: int = 0
    turn_commits: int = 0


@dataclass(slots=True)
class _RecognitionState:
    ref: RecognitionStreamRef
    turn_detection: RecognitionTurnDetection
    deadline: float
    next_frame_seq: int = 0
    next_audio_cursor: int = 0
    next_event_seq: int = 0
    provider_audio_cursor: int = 0
    input_fenced: bool = False
    output_fenced: bool = False
    cancel_requested: bool = False
    terminal: bool = False
    turn_started: bool = False
    turn_stopped: bool = False
    provider_committed: bool = False
    provider_item_id: str | None = field(default=None, repr=False)
    provider_start_ms: int | None = None
    provider_end_ms: int | None = None


@dataclass(slots=True)
class _SynthesisState:
    request: SynthesisStreamRequest
    event_deadline: float
    next_event_seq: int = 0
    next_audio_cursor: int = 0
    next_display_cursor: int = 0
    next_spoken_cursor: int = 0
    started: bool = False
    output_fenced: bool = False
    cancel_requested: bool = False
    terminal: bool = False


_RecognitionKey = tuple[str, int]
_SynthesisKey = tuple[str, int]
_ControlKey = tuple[ProviderControlKind, str, int]


class StreamingSpeechConformance:
    """Deterministic native-stream validator with bounded active retention.

    Provider callbacks are data passed to ``accept_*_event``; this class never
    invokes Provider or business callbacks.  Cancellation outputs are explicit
    ``ProviderCancelControl`` values and always carry ``business_cancel=False``.
    Exact identities are retained for this instance's lifetime.  Once an
    identity ledger reaches its configured bound, new identities fail closed;
    an old identity is never evicted and therefore can never be reused as ABA.
    Synthesis unit identities follow the same rule for the lifetime of their
    exact response, which itself cannot be reactivated after supersession.
    """

    def __init__(
        self,
        capability: StreamingProviderCapability,
        *,
        enabled: bool,
        max_recognition_sessions: int = 8,
        max_synthesis_sessions: int = 8,
        max_identity_tombstones: int = 64,
        max_synthesis_units_per_response: int = 1_024,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        _validate_capability(capability)
        self._max_recognition_sessions = _positive_int(
            max_recognition_sessions, "max_recognition_sessions"
        )
        self._max_synthesis_sessions = _positive_int(
            max_synthesis_sessions, "max_synthesis_sessions"
        )
        self._max_identity_tombstones = _positive_int(
            max_identity_tombstones, "max_identity_tombstones"
        )
        self._max_synthesis_units_per_response = _positive_int(
            max_synthesis_units_per_response,
            "max_synthesis_units_per_response",
        )
        if type(enabled) is not bool:
            raise StreamingSpeechViolation(
                "INVALID_FEATURE_FLAG", "enabled must be a boolean"
            )
        if not callable(monotonic):
            raise StreamingSpeechViolation(
                "INVALID_MONOTONIC_CLOCK", "monotonic must be callable"
            )
        self._capability = capability
        self._enabled = enabled
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._closed = False
        self._recognition: dict[_RecognitionKey, _RecognitionState] = {}
        self._synthesis: dict[_SynthesisKey, _SynthesisState] = {}
        self._recognition_generations: OrderedDict[str, int] = OrderedDict()
        self._synthesis_generations: OrderedDict[str, int] = OrderedDict()
        self._active_responses: OrderedDict[str, ResponseRef] = OrderedDict()
        self._response_generations: OrderedDict[str, int] = OrderedDict()
        self._response_ids: OrderedDict[str, None] = OrderedDict()
        self._next_unit_seq: dict[ResponseRef, int] = {}
        self._used_synthesis_units: dict[ResponseRef, OrderedDict[str, None]] = {}
        self._pending_controls: OrderedDict[_ControlKey, ProviderCancelControl] = (
            OrderedDict()
        )

    @property
    def capability(self) -> StreamingProviderCapability:
        return self._capability

    def start_recognition(
        self,
        request: RecognitionStreamRequest | RecognitionStreamRef,
        *,
        timeout_seconds: float,
    ) -> None:
        with self._lock:
            self._require_start_allowed(recognition=True)
            if isinstance(request, RecognitionStreamRef):
                request = RecognitionStreamRequest(
                    request, RecognitionTurnDetection.manual()
                )
            _validate_recognition_request(request)
            if (
                request.turn_detection.mode is RecognitionTurnDetectionMode.SERVER_VAD
                and self._capability.recognition.server_vad
                is not CapabilityProvenance.PROVIDER_NATIVE
            ):
                raise StreamingSpeechViolation(
                    "SERVER_VAD_UNAVAILABLE",
                    "recognition Provider cannot honor server VAD",
                )
            ref = request.ref
            _validate_recognition_ref(ref)
            timeout = _timeout_seconds(timeout_seconds)
            if len(self._recognition) >= self._max_recognition_sessions:
                raise StreamingSpeechViolation(
                    "RECOGNITION_CAPACITY_EXHAUSTED",
                    "recognition session capacity is exhausted",
                )
            active = next(
                (
                    state
                    for state in self._recognition.values()
                    if state.ref.session_id == ref.session_id
                ),
                None,
            )
            if active is not None:
                raise StreamingSpeechViolation(
                    "RECOGNITION_SESSION_CONFLICT",
                    "a recognition session id cannot overlap another generation",
                )
            last_generation = self._recognition_generations.get(ref.session_id)
            if (
                last_generation is not None
                and ref.session_generation <= last_generation
            ):
                raise StreamingSpeechViolation(
                    "STALE_RECOGNITION_GENERATION",
                    "recognition generation must increase when an id is reused",
                )
            self._require_identity_capacity(
                self._recognition_generations,
                ref.session_id,
                reason="RECOGNITION_IDENTITY_CAPACITY_EXHAUSTED",
                message="recognition identity ledger capacity is exhausted",
            )
            self._recognition[_recognition_key(ref)] = _RecognitionState(
                ref=ref,
                turn_detection=request.turn_detection,
                deadline=self._deadline(timeout),
            )
            self._retain_generation(
                self._recognition_generations,
                ref.session_id,
                ref.session_generation,
            )

    def accept_audio_frame(self, frame: RecognitionAudioFrame) -> None:
        with self._lock:
            if not isinstance(frame, RecognitionAudioFrame):
                raise StreamingSpeechViolation(
                    "INVALID_RECOGNITION_AUDIO_FRAME",
                    "recognition audio frame has the wrong type",
                )
            state = self._require_recognition(frame.ref)
            try:
                self._require_live_recognition(state)
                _uint(frame.seq, "frame.seq")
                _uint(frame.sample_cursor, "frame.sample_cursor")
                sample_count = _bounded_sample_count(
                    frame.sample_count, "frame.sample_count"
                )
                if type(frame.pcm_f32le) is not bytes or (
                    len(frame.pcm_f32le) != sample_count * 4
                ):
                    raise StreamingSpeechViolation(
                        "INVALID_PCM_F32_FRAME",
                        "recognition frames must be exact mono pcm_f32le samples",
                    )
                if frame.seq != state.next_frame_seq:
                    reason = (
                        "DUPLICATE_AUDIO_FRAME"
                        if frame.seq < state.next_frame_seq
                        else "AUDIO_FRAME_GAP"
                    )
                    raise StreamingSpeechViolation(
                        reason, "recognition frame sequence must be contiguous"
                    )
                if frame.sample_cursor != state.next_audio_cursor:
                    reason = (
                        "AUDIO_CURSOR_REWIND"
                        if frame.sample_cursor < state.next_audio_cursor
                        else "AUDIO_CURSOR_GAP"
                    )
                    raise StreamingSpeechViolation(
                        reason, "recognition audio cursor must be contiguous"
                    )
                if state.next_audio_cursor > MAX_SAFE_INTEGER - sample_count:
                    raise StreamingSpeechViolation(
                        "RECOGNITION_AUDIO_CURSOR_EXHAUSTED",
                        "recognition audio cursor exceeded the safe integer range",
                    )
                if state.next_frame_seq == MAX_SAFE_INTEGER:
                    raise StreamingSpeechViolation(
                        "RECOGNITION_FRAME_SEQUENCE_EXHAUSTED",
                        "recognition frame sequence exceeded the safe integer range",
                    )
                state.next_frame_seq += 1
                state.next_audio_cursor += sample_count
            except StreamingSpeechViolation as error:
                if error.reason not in {
                    "RECOGNITION_ALREADY_TERMINAL",
                    "RECOGNITION_STREAM_TIMEOUT",
                    "RECOGNITION_INPUT_FENCED",
                }:
                    self._fail_recognition(state, error.reason)
                raise

    def accept_recognition_event(
        self, event: StreamingRecognitionEvent
    ) -> StreamingRecognitionEvent:
        with self._lock:
            if not isinstance(event, StreamingRecognitionEvent):
                raise StreamingSpeechViolation(
                    "INVALID_RECOGNITION_EVENT",
                    "recognition event has the wrong type",
                )
            state = self._require_recognition(event.ref)
            self._require_not_terminal_recognition(state)
            try:
                if not (
                    state.cancel_requested
                    and event.kind is RecognitionEventKind.CANCELLED
                ):
                    self._require_before_deadline_recognition(state)
                if event.provider != self._capability.provider:
                    raise StreamingSpeechViolation(
                        "RECOGNITION_PROVIDER_MISMATCH",
                        "recognition event must retain the selected Provider",
                    )
                _uint(event.seq, "recognition_event.seq")
                if event.seq != state.next_event_seq:
                    reason = (
                        "DUPLICATE_RECOGNITION_EVENT"
                        if event.seq < state.next_event_seq
                        else "RECOGNITION_EVENT_GAP"
                    )
                    raise StreamingSpeechViolation(
                        reason,
                        "recognition Provider event sequence must be contiguous",
                    )
                if event.audio_cursor is None:
                    if (
                        event.timing_basis is not RecognitionTimingBasis.PROVIDER_TIME
                        or event.timing_provenance
                        is not CapabilityProvenance.ADAPTER_DERIVED
                        or self._capability.recognition.server_vad
                        is not CapabilityProvenance.PROVIDER_NATIVE
                        or not state.provider_committed
                    ):
                        raise StreamingSpeechViolation(
                            "UNPROVEN_RECOGNITION_TIMING",
                            "cursorless recognition requires committed Provider-time VAD",
                        )
                else:
                    _uint(event.audio_cursor, "recognition_event.audio_cursor")
                    if (
                        event.timing_basis
                        is not RecognitionTimingBasis.EXACT_SOURCE_CURSOR
                        or event.timing_provenance
                        is not CapabilityProvenance.ADAPTER_DERIVED
                        or event.audio_cursor < state.provider_audio_cursor
                        or event.audio_cursor > state.next_audio_cursor
                    ):
                        raise StreamingSpeechViolation(
                            "INVALID_RECOGNITION_AUDIO_CURSOR",
                            "recognition cursor must be exact, monotonic, and submitted",
                        )
                if (
                    state.output_fenced
                    and event.kind is not RecognitionEventKind.CANCELLED
                ):
                    raise StreamingSpeechViolation(
                        "RECOGNITION_OUTPUT_FENCED",
                        "recognition output is fenced after cancel, timeout, or failure",
                    )
                if event.kind in {
                    RecognitionEventKind.PARTIAL,
                    RecognitionEventKind.FINAL,
                }:
                    _validate_hypothesis(event.hypothesis)
                    if event.audio_cursor == 0:
                        raise StreamingSpeechViolation(
                            "EMPTY_RECOGNITION_AUDIO_RANGE",
                            "recognition text must identify a declared source-audio boundary",
                        )
                elif event.kind is RecognitionEventKind.CANCELLED:
                    if (
                        self._capability.recognition.provider_cancel_ack
                        is not CapabilityProvenance.PROVIDER_NATIVE
                    ):
                        raise StreamingSpeechViolation(
                            "UNPROVEN_RECOGNITION_CANCEL_ACK",
                            "a Provider CANCELLED event requires declared cancel-ACK provenance",
                        )
                    if event.hypothesis is not None:
                        raise StreamingSpeechViolation(
                            "CANCELLED_HYPOTHESIS_FORBIDDEN",
                            "cancelled recognition cannot carry text",
                        )
                else:
                    raise StreamingSpeechViolation(
                        "INVALID_RECOGNITION_EVENT_KIND",
                        "recognition Provider event kind is unsupported",
                    )
                if state.next_event_seq == MAX_SAFE_INTEGER:
                    raise StreamingSpeechViolation(
                        "RECOGNITION_EVENT_SEQUENCE_EXHAUSTED",
                        "recognition event sequence exceeded the safe integer range",
                    )
                state.next_event_seq += 1
                if event.audio_cursor is not None:
                    state.provider_audio_cursor = event.audio_cursor
                if event.kind in {
                    RecognitionEventKind.FINAL,
                    RecognitionEventKind.CANCELLED,
                }:
                    state.terminal = True
                    state.output_fenced = True
                return event
            except StreamingSpeechViolation as error:
                if error.reason not in {
                    "RECOGNITION_STREAM_TIMEOUT",
                    "RECOGNITION_OUTPUT_FENCED",
                }:
                    self._fail_recognition(state, error.reason)
                raise

    def accept_recognition_boundary(
        self, event: RecognitionTurnBoundaryEvent
    ) -> RecognitionTurnBoundaryEvent:
        """Validate one Provider-time boundary without creating business effects."""

        with self._lock:
            if not isinstance(event, RecognitionTurnBoundaryEvent):
                raise StreamingSpeechViolation(
                    "INVALID_TURN_BOUNDARY", "turn boundary has the wrong type"
                )
            state = self._require_recognition(event.ref)
            self._require_not_terminal_recognition(state)
            try:
                self._require_before_deadline_recognition(state)
                if (
                    state.turn_detection.mode
                    is not RecognitionTurnDetectionMode.SERVER_VAD
                    or self._capability.recognition.server_vad
                    is not CapabilityProvenance.PROVIDER_NATIVE
                ):
                    raise StreamingSpeechViolation(
                        "TURN_BOUNDARY_UNNEGOTIATED",
                        "Provider turn boundaries require negotiated server VAD",
                    )
                if event.provider != self._capability.provider:
                    raise StreamingSpeechViolation(
                        "RECOGNITION_PROVIDER_MISMATCH",
                        "turn boundary must retain the selected Provider",
                    )
                _uint(event.seq, "turn_boundary.seq")
                if event.seq != state.next_event_seq:
                    reason = (
                        "DUPLICATE_RECOGNITION_EVENT"
                        if event.seq < state.next_event_seq
                        else "RECOGNITION_EVENT_GAP"
                    )
                    raise StreamingSpeechViolation(
                        reason, "recognition Provider event sequence must be contiguous"
                    )
                _identifier(event.provider_item_id, "turn_boundary.provider_item_id")
                if (
                    event.timing_basis is not RecognitionTimingBasis.PROVIDER_TIME
                    or event.timing_provenance
                    is not CapabilityProvenance.ADAPTER_DERIVED
                ):
                    raise StreamingSpeechViolation(
                        "UNPROVEN_RECOGNITION_TIMING",
                        "server VAD boundaries are Provider-time adapter observations",
                    )
                if event.kind is RecognitionTurnBoundaryKind.SPEECH_STARTED:
                    if (
                        state.turn_started
                        or event.provider_start_ms is None
                        or event.provider_end_ms is not None
                    ):
                        raise StreamingSpeechViolation(
                            "INVALID_TURN_BOUNDARY_ORDER",
                            "speech_started must be the first exact boundary",
                        )
                    _uint(event.provider_start_ms, "turn_boundary.provider_start_ms")
                    state.turn_started = True
                    state.provider_item_id = event.provider_item_id
                    state.provider_start_ms = event.provider_start_ms
                elif event.kind is RecognitionTurnBoundaryKind.SPEECH_STOPPED:
                    if (
                        not state.turn_started
                        or state.turn_stopped
                        or event.provider_item_id != state.provider_item_id
                        or event.provider_start_ms is not None
                        or event.provider_end_ms is None
                    ):
                        raise StreamingSpeechViolation(
                            "INVALID_TURN_BOUNDARY_ORDER",
                            "speech_stopped must close the observed speech item",
                        )
                    _uint(event.provider_end_ms, "turn_boundary.provider_end_ms")
                    assert state.provider_start_ms is not None
                    if event.provider_end_ms < state.provider_start_ms:
                        raise StreamingSpeechViolation(
                            "INVALID_TURN_BOUNDARY_TIME",
                            "speech stop precedes speech start",
                        )
                    state.turn_stopped = True
                    state.input_fenced = True
                    state.provider_end_ms = event.provider_end_ms
                elif event.kind is RecognitionTurnBoundaryKind.COMMITTED:
                    if (
                        not state.turn_stopped
                        or state.provider_committed
                        or event.provider_item_id != state.provider_item_id
                        or event.provider_start_ms is not None
                        or event.provider_end_ms is not None
                    ):
                        raise StreamingSpeechViolation(
                            "INVALID_TURN_BOUNDARY_ORDER",
                            "server commit must follow the stopped speech item",
                        )
                    state.provider_committed = True
                else:
                    raise StreamingSpeechViolation(
                        "INVALID_TURN_BOUNDARY", "turn boundary kind is unsupported"
                    )
                if state.next_event_seq == MAX_SAFE_INTEGER:
                    raise StreamingSpeechViolation(
                        "RECOGNITION_EVENT_SEQUENCE_EXHAUSTED",
                        "recognition event sequence exceeded the safe integer range",
                    )
                state.next_event_seq += 1
                return event
            except StreamingSpeechViolation as error:
                if error.reason != "RECOGNITION_STREAM_TIMEOUT":
                    self._fail_recognition(state, error.reason)
                raise

    def request_recognition_cancel(
        self, ref: RecognitionStreamRef, *, reason: str = "caller_cancel"
    ) -> None:
        with self._lock:
            state = self._require_recognition(ref)
            self._require_not_terminal_recognition(state)
            if state.cancel_requested:
                raise StreamingSpeechViolation(
                    "RECOGNITION_CANCEL_ALREADY_REQUESTED",
                    "recognition cancel is already retained",
                )
            self._request_recognition_cancel(
                state,
                _bounded_text(reason, "reason", max_chars=MAX_CANCEL_REASON_CHARS),
            )

    def provider_closed_recognition(self, ref: RecognitionStreamRef) -> None:
        with self._lock:
            state = self._require_recognition(ref)
            state.output_fenced = True
            state.terminal = True

    def activate_response(self, response: ResponseRef) -> None:
        with self._lock:
            self._require_start_allowed(recognition=False)
            _validate_response_ref(response)
            prior_generation = self._response_generations.get(response.interaction_id)
            if (
                prior_generation is not None
                and response.response_generation <= prior_generation
            ):
                raise StreamingSpeechViolation(
                    "STALE_RESPONSE_GENERATION",
                    "response generation must strictly increase per interaction",
                )
            if response.response_id in self._response_ids:
                raise StreamingSpeechViolation(
                    "RESPONSE_ID_REUSED", "response identifiers cannot be reused"
                )
            self._require_identity_capacity(
                self._response_generations,
                response.interaction_id,
                reason="RESPONSE_IDENTITY_CAPACITY_EXHAUSTED",
                message="response interaction identity ledger capacity is exhausted",
            )
            self._require_identity_capacity(
                self._response_ids,
                response.response_id,
                reason="RESPONSE_IDENTITY_CAPACITY_EXHAUSTED",
                message="response identifier ledger capacity is exhausted",
            )
            prior = self._active_responses.get(response.interaction_id)
            if prior is None:
                self._make_response_capacity()
            if prior is not None:
                for state in self._synthesis.values():
                    if (
                        state.request.ref.response.interaction_id
                        == response.interaction_id
                        and not state.terminal
                    ):
                        self._fail_synthesis(state, "STALE_RESPONSE")
                self._next_unit_seq.pop(prior, None)
                self._used_synthesis_units.pop(prior, None)
            self._active_responses[response.interaction_id] = response
            self._active_responses.move_to_end(response.interaction_id)
            self._next_unit_seq[response] = 0
            self._used_synthesis_units[response] = OrderedDict()
            self._retain_generation(
                self._response_generations,
                response.interaction_id,
                response.response_generation,
            )
            self._response_ids[response.response_id] = None
            self._response_ids.move_to_end(response.response_id)

    def start_synthesis(self, request: SynthesisStreamRequest) -> None:
        with self._lock:
            self._require_start_allowed(recognition=False)
            _validate_synthesis_request(request)
            if len(self._synthesis) >= self._max_synthesis_sessions:
                raise StreamingSpeechViolation(
                    "SYNTHESIS_CAPACITY_EXHAUSTED",
                    "synthesis session capacity is exhausted",
                )
            ref = request.ref
            active_response = self._active_responses.get(ref.response.interaction_id)
            if active_response != ref.response:
                raise StreamingSpeechViolation(
                    "STALE_SYNTHESIS_RESPONSE",
                    "synthesis must bind the exact active response generation",
                )
            expected_unit_seq = self._next_unit_seq.get(ref.response)
            if expected_unit_seq is None or ref.unit_seq != expected_unit_seq:
                raise StreamingSpeechViolation(
                    "SYNTHESIS_UNIT_SEQUENCE_GAP",
                    "synthesis units must start in exact response order",
                )
            used_units = self._used_synthesis_units.get(ref.response)
            if used_units is None:
                raise StreamingSpeechViolation(
                    "STALE_SYNTHESIS_RESPONSE",
                    "synthesis response unit identity ledger is not retained",
                )
            if ref.unit_id in used_units:
                raise StreamingSpeechViolation(
                    "SYNTHESIS_UNIT_REUSED",
                    "a response unit identifier cannot be synthesized twice",
                )
            if len(used_units) >= self._max_synthesis_units_per_response:
                raise StreamingSpeechViolation(
                    "SYNTHESIS_UNIT_IDENTITY_CAPACITY_EXHAUSTED",
                    "synthesis response unit identity ledger capacity is exhausted",
                )
            active = next(
                (
                    state
                    for state in self._synthesis.values()
                    if state.request.ref.stream_id == ref.stream_id
                ),
                None,
            )
            if active is not None:
                raise StreamingSpeechViolation(
                    "SYNTHESIS_STREAM_CONFLICT",
                    "a synthesis stream id cannot overlap another generation",
                )
            last_generation = self._synthesis_generations.get(ref.stream_id)
            if last_generation is not None and ref.stream_generation <= last_generation:
                raise StreamingSpeechViolation(
                    "STALE_SYNTHESIS_GENERATION",
                    "synthesis generation must increase when an id is reused",
                )
            self._require_identity_capacity(
                self._synthesis_generations,
                ref.stream_id,
                reason="SYNTHESIS_IDENTITY_CAPACITY_EXHAUSTED",
                message="synthesis identity ledger capacity is exhausted",
            )
            self._synthesis[_synthesis_key(ref)] = _SynthesisState(
                request=request,
                event_deadline=self._deadline(request.event_timeout_seconds),
                next_display_cursor=request.display_span.start,
            )
            self._next_unit_seq[ref.response] = expected_unit_seq + 1
            used_units[ref.unit_id] = None
            self._retain_generation(
                self._synthesis_generations, ref.stream_id, ref.stream_generation
            )

    def accept_synthesis_event(
        self, event: StreamingSynthesisEvent
    ) -> StreamingSynthesisEvent:
        with self._lock:
            if not isinstance(event, StreamingSynthesisEvent):
                raise StreamingSpeechViolation(
                    "INVALID_SYNTHESIS_EVENT",
                    "synthesis event has the wrong type",
                )
            state = self._require_synthesis(event.ref)
            self._require_not_terminal_synthesis(state)
            try:
                if not (
                    state.cancel_requested
                    and event.kind is SynthesisEventKind.CANCELLED
                ):
                    self._require_before_deadline_synthesis(state)
                if event.provider != self._capability.provider:
                    raise StreamingSpeechViolation(
                        "SYNTHESIS_PROVIDER_MISMATCH",
                        "synthesis event must retain the selected Provider",
                    )
                _uint(event.seq, "synthesis_event.seq")
                _uint(event.sample_cursor, "synthesis_event.sample_cursor")
                sample_rate_hz = _positive_int(
                    event.sample_rate_hz, "synthesis_event.sample_rate_hz"
                )
                if sample_rate_hz != state.request.sample_rate_hz:
                    raise StreamingSpeechViolation(
                        "SYNTHESIS_SAMPLE_RATE_MISMATCH",
                        "synthesis event changed its requested sample rate",
                    )
                if event.seq != state.next_event_seq:
                    reason = (
                        "DUPLICATE_SYNTHESIS_EVENT"
                        if event.seq < state.next_event_seq
                        else "SYNTHESIS_EVENT_GAP"
                    )
                    raise StreamingSpeechViolation(
                        reason, "synthesis Provider event sequence must be contiguous"
                    )
                if event.sample_cursor != state.next_audio_cursor:
                    reason = (
                        "SYNTHESIS_AUDIO_CURSOR_REWIND"
                        if event.sample_cursor < state.next_audio_cursor
                        else "SYNTHESIS_AUDIO_CURSOR_GAP"
                    )
                    raise StreamingSpeechViolation(
                        reason, "synthesis audio cursor must be contiguous"
                    )
                if (
                    state.output_fenced
                    and event.kind is not SynthesisEventKind.CANCELLED
                ):
                    raise StreamingSpeechViolation(
                        "SYNTHESIS_OUTPUT_FENCED",
                        "synthesis output is fenced after cancel, timeout, or failure",
                    )
                if event.kind is SynthesisEventKind.STARTED:
                    self._accept_synthesis_started(state, event)
                elif event.kind is SynthesisEventKind.CHUNK:
                    self._accept_synthesis_chunk(state, event)
                elif event.kind is SynthesisEventKind.COMPLETED:
                    self._accept_synthesis_completed(state, event)
                elif event.kind is SynthesisEventKind.CANCELLED:
                    self._accept_synthesis_cancelled(state, event)
                else:
                    raise StreamingSpeechViolation(
                        "INVALID_SYNTHESIS_EVENT_KIND",
                        "synthesis Provider event kind is unsupported",
                    )
                if state.next_event_seq == MAX_SAFE_INTEGER:
                    raise StreamingSpeechViolation(
                        "SYNTHESIS_EVENT_SEQUENCE_EXHAUSTED",
                        "synthesis event sequence exceeded the safe integer range",
                    )
                state.next_event_seq += 1
                if not state.terminal:
                    state.event_deadline = self._deadline(
                        state.request.event_timeout_seconds
                    )
                return event
            except StreamingSpeechViolation as error:
                if error.reason not in {
                    "SYNTHESIS_STREAM_TIMEOUT",
                    "SYNTHESIS_OUTPUT_FENCED",
                }:
                    self._fail_synthesis(state, error.reason)
                raise

    def request_synthesis_cancel(
        self, ref: SynthesisStreamRef, *, reason: str = "caller_cancel"
    ) -> None:
        with self._lock:
            state = self._require_synthesis(ref)
            self._require_not_terminal_synthesis(state)
            if state.cancel_requested:
                raise StreamingSpeechViolation(
                    "SYNTHESIS_CANCEL_ALREADY_REQUESTED",
                    "synthesis cancel is already retained",
                )
            self._request_synthesis_cancel(
                state,
                _bounded_text(reason, "reason", max_chars=MAX_CANCEL_REASON_CHARS),
            )

    def provider_closed_synthesis(self, ref: SynthesisStreamRef) -> None:
        with self._lock:
            state = self._require_synthesis(ref)
            state.output_fenced = True
            state.terminal = True

    def expire(self) -> int:
        """Fence expired sessions and retain exact Provider cancel controls."""

        with self._lock:
            now = self._now()
            expired = 0
            for recognition_state in self._recognition.values():
                if (
                    not recognition_state.terminal
                    and not recognition_state.cancel_requested
                    and now >= recognition_state.deadline
                ):
                    self._request_recognition_cancel(recognition_state, "timeout")
                    expired += 1
            for synthesis_state in self._synthesis.values():
                if (
                    not synthesis_state.terminal
                    and not synthesis_state.cancel_requested
                    and now >= synthesis_state.event_deadline
                ):
                    self._request_synthesis_cancel(synthesis_state, "timeout")
                    expired += 1
            return expired

    def take_provider_controls(self) -> tuple[ProviderCancelControl, ...]:
        with self._lock:
            controls = tuple(self._pending_controls.values())
            self._pending_controls.clear()
            return controls

    def close(self) -> StreamingSpeechSnapshot:
        """Fence new work and retain non-terminal Provider sessions for teardown."""

        with self._lock:
            if not self._closed:
                self._closed = True
                for recognition_state in self._recognition.values():
                    if (
                        not recognition_state.terminal
                        and not recognition_state.cancel_requested
                    ):
                        self._request_recognition_cancel(
                            recognition_state, "service_close"
                        )
                for synthesis_state in self._synthesis.values():
                    if (
                        not synthesis_state.terminal
                        and not synthesis_state.cancel_requested
                    ):
                        self._request_synthesis_cancel(synthesis_state, "service_close")
            return self._snapshot_unlocked()

    def reap_terminal(self) -> tuple[int, int]:
        """Release only streams with a Provider terminal/closed observation."""

        with self._lock:
            recognition_keys = [
                key for key, state in self._recognition.items() if state.terminal
            ]
            synthesis_keys = [
                key for key, state in self._synthesis.items() if state.terminal
            ]
            for recognition_key in recognition_keys:
                del self._recognition[recognition_key]
            for synthesis_key in synthesis_keys:
                del self._synthesis[synthesis_key]
            retired_controls = {
                (ProviderControlKind.CANCEL_RECOGNITION, key[0], key[1])
                for key in recognition_keys
            } | {
                (ProviderControlKind.CANCEL_SYNTHESIS, key[0], key[1])
                for key in synthesis_keys
            }
            for control_key in retired_controls:
                self._pending_controls.pop(control_key, None)
            return len(recognition_keys), len(synthesis_keys)

    def snapshot(self) -> StreamingSpeechSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> StreamingSpeechSnapshot:
        return StreamingSpeechSnapshot(
            enabled=self._enabled,
            closed=self._closed,
            active_recognition=sum(
                not state.terminal and not state.output_fenced
                for state in self._recognition.values()
            ),
            active_synthesis=sum(
                not state.terminal and not state.output_fenced
                for state in self._synthesis.values()
            ),
            retained_recognition=len(self._recognition),
            retained_synthesis=len(self._synthesis),
            pending_provider_controls=len(self._pending_controls),
            # Every never-evicted identity ledger is counted. Omitting one lets
            # a capacity monitor under-report retention and meet
            # RESPONSE_IDENTITY_CAPACITY_EXHAUSTED without warning.
            retained_identity_tombstones=(
                len(self._recognition_generations)
                + len(self._synthesis_generations)
                + len(self._response_generations)
                + len(self._response_ids)
            ),
            retained_synthesis_unit_identities=sum(
                len(units) for units in self._used_synthesis_units.values()
            ),
        )

    def _accept_synthesis_started(
        self, state: _SynthesisState, event: StreamingSynthesisEvent
    ) -> None:
        if state.started:
            self._fail_synthesis(state, "SYNTHESIS_ALREADY_STARTED")
            raise StreamingSpeechViolation(
                "SYNTHESIS_ALREADY_STARTED", "synthesis started can occur only once"
            )
        if not _empty_synthesis_payload(event):
            self._fail_synthesis(state, "STARTED_PAYLOAD_FORBIDDEN")
            raise StreamingSpeechViolation(
                "STARTED_PAYLOAD_FORBIDDEN",
                "synthesis started cannot carry audio or text spans",
            )
        state.started = True

    def _accept_synthesis_chunk(
        self, state: _SynthesisState, event: StreamingSynthesisEvent
    ) -> None:
        if not state.started:
            self._fail_synthesis(state, "SYNTHESIS_NOT_STARTED")
            raise StreamingSpeechViolation(
                "SYNTHESIS_NOT_STARTED", "audio chunks require a started event"
            )
        sample_count = _bounded_sample_count(
            event.sample_count, "synthesis_event.sample_count"
        )
        if (
            type(event.pcm_s16le) is not bytes
            or len(event.pcm_s16le) != sample_count * 2
        ):
            self._fail_synthesis(state, "INVALID_PCM_S16_CHUNK")
            raise StreamingSpeechViolation(
                "INVALID_PCM_S16_CHUNK",
                "synthesis chunks must be exact mono pcm_s16le samples",
            )
        span_provenance = self._capability.synthesis.chunk_text_spans
        if event.display_span is None or event.spoken_span is None:
            if not (
                span_provenance is CapabilityProvenance.UNAVAILABLE
                and event.display_span is None
                and event.spoken_span is None
            ):
                self._fail_synthesis(state, "SYNTHESIS_TEXT_SPAN_REQUIRED")
                raise StreamingSpeechViolation(
                    "SYNTHESIS_TEXT_SPAN_REQUIRED",
                    "chunk spans must be a complete pair and match declared provenance",
                )
            self._advance_synthesis_audio(state, sample_count)
            return
        request = state.request
        display = event.display_span
        spoken = event.spoken_span
        _validate_span(display, "synthesis_event.display_span")
        _validate_span(spoken, "synthesis_event.spoken_span")
        if (
            display.start != state.next_display_cursor
            or display.end > request.display_span.end
        ):
            self._fail_synthesis(state, "SYNTHESIS_DISPLAY_SPAN_GAP")
            raise StreamingSpeechViolation(
                "SYNTHESIS_DISPLAY_SPAN_GAP",
                "chunk display spans must be contiguous within the exact unit",
            )
        if spoken.start != state.next_spoken_cursor or spoken.end > len(
            request.spoken_text
        ):
            self._fail_synthesis(state, "SYNTHESIS_SPOKEN_SPAN_GAP")
            raise StreamingSpeechViolation(
                "SYNTHESIS_SPOKEN_SPAN_GAP",
                "chunk spoken spans must be contiguous within the exact unit",
            )
        if spoken.length <= 0:
            self._fail_synthesis(state, "EMPTY_SYNTHESIS_SPOKEN_SPAN")
            raise StreamingSpeechViolation(
                "EMPTY_SYNTHESIS_SPOKEN_SPAN",
                "an audio chunk must identify non-empty spoken text",
            )
        self._advance_synthesis_audio(state, sample_count)
        state.next_display_cursor = display.end
        state.next_spoken_cursor = spoken.end

    def _advance_synthesis_audio(
        self, state: _SynthesisState, sample_count: int
    ) -> None:
        if state.next_audio_cursor > MAX_SAFE_INTEGER - sample_count:
            self._fail_synthesis(state, "SYNTHESIS_AUDIO_CURSOR_EXHAUSTED")
            raise StreamingSpeechViolation(
                "SYNTHESIS_AUDIO_CURSOR_EXHAUSTED",
                "synthesis audio cursor exceeded the safe integer range",
            )
        state.next_audio_cursor += sample_count

    def _accept_synthesis_completed(
        self, state: _SynthesisState, event: StreamingSynthesisEvent
    ) -> None:
        if not state.started or state.next_audio_cursor == 0:
            self._fail_synthesis(state, "EMPTY_SYNTHESIS_COMPLETION")
            raise StreamingSpeechViolation(
                "EMPTY_SYNTHESIS_COMPLETION",
                "completed synthesis requires started non-empty audio",
            )
        if not _empty_synthesis_payload(event):
            self._fail_synthesis(state, "TERMINAL_SYNTHESIS_PAYLOAD_FORBIDDEN")
            raise StreamingSpeechViolation(
                "TERMINAL_SYNTHESIS_PAYLOAD_FORBIDDEN",
                "terminal synthesis events cannot carry audio or text spans",
            )
        if (
            self._capability.synthesis.chunk_text_spans
            is not CapabilityProvenance.UNAVAILABLE
            and (
                state.next_display_cursor != state.request.display_span.end
                or state.next_spoken_cursor != len(state.request.spoken_text)
            )
        ):
            self._fail_synthesis(state, "INCOMPLETE_SYNTHESIS_TEXT_PROVENANCE")
            raise StreamingSpeechViolation(
                "INCOMPLETE_SYNTHESIS_TEXT_PROVENANCE",
                "completed synthesis must close its display and spoken spans",
            )
        state.output_fenced = True
        state.terminal = True

    def _accept_synthesis_cancelled(
        self, state: _SynthesisState, event: StreamingSynthesisEvent
    ) -> None:
        if (
            self._capability.synthesis.provider_cancel_ack
            is not CapabilityProvenance.PROVIDER_NATIVE
        ):
            self._fail_synthesis(state, "UNPROVEN_SYNTHESIS_CANCEL_ACK")
            raise StreamingSpeechViolation(
                "UNPROVEN_SYNTHESIS_CANCEL_ACK",
                "a Provider CANCELLED event requires declared cancel-ACK provenance",
            )
        if not _empty_synthesis_payload(event):
            self._fail_synthesis(state, "TERMINAL_SYNTHESIS_PAYLOAD_FORBIDDEN")
            raise StreamingSpeechViolation(
                "TERMINAL_SYNTHESIS_PAYLOAD_FORBIDDEN",
                "cancelled synthesis cannot carry audio or text spans",
            )
        state.output_fenced = True
        state.terminal = True

    def _require_start_allowed(self, *, recognition: bool) -> None:
        self._require_operational()
        support = (
            self._capability.recognition if recognition else self._capability.synthesis
        )
        if SpeechMode.STREAM not in support.modes:
            raise StreamingSpeechViolation(
                "STREAMING_RECOGNITION_UNSUPPORTED"
                if recognition
                else "STREAMING_SYNTHESIS_UNSUPPORTED",
                "the Provider does not advertise native streaming for this direction",
            )

    def _require_operational(self) -> None:
        if not self._enabled:
            raise StreamingSpeechViolation(
                "STREAMING_SPEECH_DISABLED", "streaming Speech feature is disabled"
            )
        if self._closed:
            raise StreamingSpeechViolation(
                "STREAMING_SPEECH_CLOSED", "streaming Speech conformance is closed"
            )
        if not self._capability.available:
            raise StreamingSpeechViolation(
                "STREAMING_PROVIDER_UNAVAILABLE",
                "streaming Speech Provider is unavailable",
            )

    def _require_recognition(self, ref: RecognitionStreamRef) -> _RecognitionState:
        _validate_recognition_ref(ref)
        state = self._recognition.get(_recognition_key(ref))
        if state is None:
            active = next(
                (
                    candidate
                    for candidate in self._recognition.values()
                    if candidate.ref.session_id == ref.session_id
                ),
                None,
            )
            if active is not None or ref.session_id in self._recognition_generations:
                raise StreamingSpeechViolation(
                    "STALE_RECOGNITION_SESSION",
                    "recognition callback does not match the retained generation",
                )
            raise StreamingSpeechViolation(
                "RECOGNITION_SESSION_NOT_FOUND",
                "recognition session is not retained",
            )
        if state.ref != ref:
            self._fail_recognition(state, "RECOGNITION_CAPTURE_MISMATCH")
            raise StreamingSpeechViolation(
                "RECOGNITION_CAPTURE_MISMATCH",
                "recognition callback changed the exact capture identity",
            )
        return state

    def _require_synthesis(self, ref: SynthesisStreamRef) -> _SynthesisState:
        _validate_synthesis_ref(ref)
        state = self._synthesis.get(_synthesis_key(ref))
        if state is None:
            active = next(
                (
                    candidate
                    for candidate in self._synthesis.values()
                    if candidate.request.ref.stream_id == ref.stream_id
                ),
                None,
            )
            if active is not None or ref.stream_id in self._synthesis_generations:
                raise StreamingSpeechViolation(
                    "STALE_SYNTHESIS_STREAM",
                    "synthesis callback does not match the retained generation",
                )
            raise StreamingSpeechViolation(
                "SYNTHESIS_STREAM_NOT_FOUND", "synthesis stream is not retained"
            )
        if state.request.ref != ref:
            self._fail_synthesis(state, "SYNTHESIS_IDENTITY_MISMATCH")
            raise StreamingSpeechViolation(
                "SYNTHESIS_IDENTITY_MISMATCH",
                "synthesis callback changed response, generation, unit, or sequence",
            )
        return state

    def _require_live_recognition(self, state: _RecognitionState) -> None:
        self._require_not_terminal_recognition(state)
        self._require_before_deadline_recognition(state)
        if state.output_fenced or state.input_fenced:
            raise StreamingSpeechViolation(
                "RECOGNITION_INPUT_FENCED",
                "recognition input is fenced after EOT, cancel, timeout, or failure",
            )

    @staticmethod
    def _require_not_terminal_recognition(state: _RecognitionState) -> None:
        if state.terminal:
            raise StreamingSpeechViolation(
                "RECOGNITION_ALREADY_TERMINAL",
                "recognition cannot accept input or output after terminal",
            )

    @staticmethod
    def _require_not_terminal_synthesis(state: _SynthesisState) -> None:
        if state.terminal:
            raise StreamingSpeechViolation(
                "SYNTHESIS_ALREADY_TERMINAL",
                "synthesis cannot accept output after terminal",
            )

    def _require_before_deadline_recognition(self, state: _RecognitionState) -> None:
        if self._now() >= state.deadline:
            if not state.cancel_requested:
                self._request_recognition_cancel(state, "timeout")
            raise StreamingSpeechViolation(
                "RECOGNITION_STREAM_TIMEOUT",
                "recognition session crossed its absolute deadline",
            )

    def _require_before_deadline_synthesis(self, state: _SynthesisState) -> None:
        if self._now() >= state.event_deadline:
            if not state.cancel_requested:
                self._request_synthesis_cancel(state, "timeout")
            raise StreamingSpeechViolation(
                "SYNTHESIS_STREAM_TIMEOUT",
                "synthesis session crossed its next-event deadline",
            )

    def _fail_recognition(self, state: _RecognitionState, reason: str) -> None:
        if not state.terminal and not state.cancel_requested:
            self._request_recognition_cancel(
                state, f"conformance_failure:{reason.lower()}"
            )
        else:
            state.output_fenced = True

    def _fail_synthesis(self, state: _SynthesisState, reason: str) -> None:
        if not state.terminal and not state.cancel_requested:
            self._request_synthesis_cancel(
                state, f"conformance_failure:{reason.lower()}"
            )
        else:
            state.output_fenced = True

    def _request_recognition_cancel(
        self, state: _RecognitionState, reason: str
    ) -> None:
        state.output_fenced = True
        state.cancel_requested = True
        control = ProviderCancelControl(
            ProviderControlKind.CANCEL_RECOGNITION, state.ref, reason
        )
        self._retain_control(control)

    def _request_synthesis_cancel(self, state: _SynthesisState, reason: str) -> None:
        state.output_fenced = True
        state.cancel_requested = True
        control = ProviderCancelControl(
            ProviderControlKind.CANCEL_SYNTHESIS, state.request.ref, reason
        )
        self._retain_control(control)

    def _retain_control(self, control: ProviderCancelControl) -> None:
        ref = control.ref
        if isinstance(ref, RecognitionStreamRef):
            identity = ref.session_id
            generation = ref.session_generation
        else:
            identity = ref.stream_id
            generation = ref.stream_generation
        key = (control.kind, identity, generation)
        self._pending_controls.setdefault(key, control)

    def _retain_generation(
        self, store: OrderedDict[str, int], identity: str, generation: int
    ) -> None:
        store[identity] = generation
        store.move_to_end(identity)

    def _require_identity_capacity(
        self,
        store: Collection[str],
        identity: str,
        *,
        reason: str,
        message: str,
    ) -> None:
        if identity not in store and len(store) >= self._max_identity_tombstones:
            raise StreamingSpeechViolation(reason, message)

    def _make_response_capacity(self) -> None:
        while len(self._active_responses) >= self._max_identity_tombstones:
            removable = next(
                (
                    (interaction_id, response)
                    for interaction_id, response in self._active_responses.items()
                    if not any(
                        state.request.ref.response == response
                        for state in self._synthesis.values()
                    )
                ),
                None,
            )
            if removable is None:
                raise StreamingSpeechViolation(
                    "RESPONSE_CAPACITY_EXHAUSTED",
                    "all retained response identities still own synthesis streams",
                )
            interaction_id, response = removable
            del self._active_responses[interaction_id]
            self._next_unit_seq.pop(response, None)
            self._used_synthesis_units.pop(response, None)

    def _now(self) -> float:
        now = self._monotonic()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
        ):
            raise StreamingSpeechViolation(
                "INVALID_MONOTONIC_TIME",
                "monotonic clock must return a finite number",
            )
        return float(now)

    def _deadline(self, timeout_seconds: float) -> float:
        deadline = self._now() + timeout_seconds
        if not math.isfinite(deadline):
            raise StreamingSpeechViolation(
                "INVALID_STREAM_DEADLINE",
                "stream deadline must remain finite",
            )
        return deadline


def _validate_capability(capability: StreamingProviderCapability) -> None:
    if not isinstance(capability, StreamingProviderCapability):
        raise StreamingSpeechViolation(
            "INVALID_STREAMING_CAPABILITY",
            "streaming capability has the wrong type",
        )
    provider = capability.provider
    if not isinstance(provider, ProviderRef):
        raise StreamingSpeechViolation(
            "INVALID_PROVIDER_REF", "Provider reference has the wrong type"
        )
    _identifier(provider.provider_id, "provider.provider_id")
    if provider.implementation_class not in {
        "formal",
        "fallback",
        "demo_substitute",
        "unsupported",
    }:
        raise StreamingSpeechViolation(
            "INVALID_IMPLEMENTATION_CLASS",
            "Provider implementation class is invalid",
        )
    if provider.implementation_class == "fallback" and not provider.fallback_from:
        raise StreamingSpeechViolation(
            "FALLBACK_PROVENANCE_REQUIRED",
            "fallback streaming Speech must identify its formal predecessor",
        )
    if provider.fallback_from is not None:
        _identifier(provider.fallback_from, "provider.fallback_from")
    if (
        provider.implementation_class != "fallback"
        and provider.fallback_from is not None
    ):
        raise StreamingSpeechViolation(
            "UNEXPECTED_FALLBACK_PROVENANCE",
            "only fallback streaming Speech can name a predecessor",
        )
    if type(capability.available) is not bool:
        raise StreamingSpeechViolation(
            "INVALID_PROVIDER_AVAILABILITY", "available must be a boolean"
        )
    if not isinstance(capability.recognition, RecognitionProviderSupport):
        raise StreamingSpeechViolation(
            "INVALID_RECOGNITION_SUPPORT",
            "recognition support has the wrong type",
        )
    if not isinstance(capability.synthesis, SynthesisProviderSupport):
        raise StreamingSpeechViolation(
            "INVALID_SYNTHESIS_SUPPORT",
            "synthesis support has the wrong type",
        )
    _validate_modes(capability.recognition.modes, "recognition")
    _validate_modes(capability.synthesis.modes, "synthesis")
    if provider.implementation_class == "unsupported" and (
        capability.available
        or capability.recognition.modes
        or capability.synthesis.modes
    ):
        raise StreamingSpeechViolation(
            "UNSUPPORTED_PROVIDER_CAPABILITY_CONTRADICTION",
            "an unsupported Provider cannot be available or advertise Speech modes",
        )
    _validate_recognition_support(capability.recognition)
    _validate_synthesis_support(capability.synthesis)


def _validate_modes(modes: frozenset[SpeechMode], direction: str) -> None:
    if type(modes) is not frozenset or any(
        type(mode) is not SpeechMode for mode in modes
    ):
        raise StreamingSpeechViolation(
            "INVALID_SPEECH_MODES", f"{direction} modes must be a SpeechMode frozenset"
        )


def _validate_recognition_support(support: RecognitionProviderSupport) -> None:
    if not isinstance(support, RecognitionProviderSupport):
        raise StreamingSpeechViolation(
            "INVALID_RECOGNITION_SUPPORT",
            "recognition support has the wrong type",
        )
    if type(support.transport) is not ProviderTransport:
        raise StreamingSpeechViolation(
            "INVALID_PROVIDER_TRANSPORT",
            "recognition transport is invalid",
        )
    for capability_field, value in (
        ("ordered_events", support.ordered_events),
        ("exact_audio_cursor", support.exact_audio_cursor),
        ("provider_cancel_ack", support.provider_cancel_ack),
        ("native_partials", support.native_partials),
        ("server_vad", support.server_vad),
    ):
        if type(value) is not CapabilityProvenance:
            raise StreamingSpeechViolation(
                "INVALID_CAPABILITY_PROVENANCE",
                f"recognition.{capability_field} must use CapabilityProvenance",
            )
    if support.provider_cancel_ack not in {
        CapabilityProvenance.PROVIDER_NATIVE,
        CapabilityProvenance.UNAVAILABLE,
    }:
        raise StreamingSpeechViolation(
            "INVALID_CANCEL_ACK_PROVENANCE",
            "recognition cancel ACK must be Provider-native or unavailable",
        )
    if support.server_vad not in {
        CapabilityProvenance.PROVIDER_NATIVE,
        CapabilityProvenance.UNAVAILABLE,
    }:
        raise StreamingSpeechViolation(
            "INVALID_SERVER_VAD_PROVENANCE",
            "recognition server VAD must be Provider-native or unavailable",
        )
    if support.native_partials not in {
        CapabilityProvenance.PROVIDER_NATIVE,
        CapabilityProvenance.UNAVAILABLE,
    }:
        raise StreamingSpeechViolation(
            "INVALID_NATIVE_PARTIAL_PROVENANCE",
            "native recognition partials must be Provider-native or unavailable",
        )
    streaming = SpeechMode.STREAM in support.modes
    if streaming and support.transport is ProviderTransport.POLLING:
        raise StreamingSpeechViolation(
            "POLLING_NOT_STREAMING",
            "polled batch recognition cannot be advertised as streaming",
        )
    if streaming and support.transport is not ProviderTransport.NATIVE_STREAM:
        raise StreamingSpeechViolation(
            "NATIVE_RECOGNITION_STREAM_REQUIRED",
            "streaming recognition requires a native Provider session",
        )
    required = (support.ordered_events, support.exact_audio_cursor)
    if streaming and CapabilityProvenance.UNAVAILABLE in required:
        raise StreamingSpeechViolation(
            "INCOMPLETE_RECOGNITION_STREAM_CAPABILITY",
            "streaming recognition requires truthful event ordering and cursor provenance",
        )
    if not streaming and (
        support.transport is ProviderTransport.NATIVE_STREAM
        or any(
            value is not CapabilityProvenance.UNAVAILABLE
            for value in (
                support.ordered_events,
                support.exact_audio_cursor,
                support.provider_cancel_ack,
                support.native_partials,
                support.server_vad,
            )
        )
    ):
        raise StreamingSpeechViolation(
            "RECOGNITION_CAPABILITY_CONTRADICTION",
            "recognition stream guarantees require SpeechMode.STREAM",
        )
    if bool(support.modes) == (support.transport is ProviderTransport.UNSUPPORTED):
        raise StreamingSpeechViolation(
            "RECOGNITION_CAPABILITY_CONTRADICTION",
            "recognition modes and unsupported transport disagree",
        )


def _validate_synthesis_support(support: SynthesisProviderSupport) -> None:
    if not isinstance(support, SynthesisProviderSupport):
        raise StreamingSpeechViolation(
            "INVALID_SYNTHESIS_SUPPORT",
            "synthesis support has the wrong type",
        )
    if type(support.transport) is not ProviderTransport:
        raise StreamingSpeechViolation(
            "INVALID_PROVIDER_TRANSPORT",
            "synthesis transport is invalid",
        )
    for capability_field, value in (
        ("ordered_events", support.ordered_events),
        ("exact_audio_cursor", support.exact_audio_cursor),
        ("provider_cancel_ack", support.provider_cancel_ack),
        ("chunk_text_spans", support.chunk_text_spans),
    ):
        if type(value) is not CapabilityProvenance:
            raise StreamingSpeechViolation(
                "INVALID_CAPABILITY_PROVENANCE",
                f"synthesis.{capability_field} must use CapabilityProvenance",
            )
    if support.provider_cancel_ack not in {
        CapabilityProvenance.PROVIDER_NATIVE,
        CapabilityProvenance.UNAVAILABLE,
    }:
        raise StreamingSpeechViolation(
            "INVALID_CANCEL_ACK_PROVENANCE",
            "synthesis cancel ACK must be Provider-native or unavailable",
        )
    streaming = SpeechMode.STREAM in support.modes
    if streaming and support.transport is ProviderTransport.POLLING:
        raise StreamingSpeechViolation(
            "POLLING_NOT_STREAMING",
            "polled batch synthesis cannot be advertised as streaming",
        )
    if streaming and support.transport is not ProviderTransport.NATIVE_STREAM:
        raise StreamingSpeechViolation(
            "NATIVE_SYNTHESIS_STREAM_REQUIRED",
            "streaming synthesis requires a native Provider session",
        )
    required = (support.ordered_events, support.exact_audio_cursor)
    if streaming and CapabilityProvenance.UNAVAILABLE in required:
        raise StreamingSpeechViolation(
            "INCOMPLETE_SYNTHESIS_STREAM_CAPABILITY",
            "streaming synthesis requires truthful event ordering and cursor provenance",
        )
    if not streaming and (
        support.transport is ProviderTransport.NATIVE_STREAM
        or any(
            value is not CapabilityProvenance.UNAVAILABLE
            for value in (
                support.ordered_events,
                support.exact_audio_cursor,
                support.provider_cancel_ack,
                support.chunk_text_spans,
            )
        )
    ):
        raise StreamingSpeechViolation(
            "SYNTHESIS_CAPABILITY_CONTRADICTION",
            "synthesis stream guarantees require SpeechMode.STREAM",
        )
    if bool(support.modes) == (support.transport is ProviderTransport.UNSUPPORTED):
        raise StreamingSpeechViolation(
            "SYNTHESIS_CAPABILITY_CONTRADICTION",
            "synthesis modes and unsupported transport disagree",
        )


def _validate_recognition_ref(ref: RecognitionStreamRef) -> None:
    if not isinstance(ref, RecognitionStreamRef):
        raise StreamingSpeechViolation(
            "INVALID_RECOGNITION_REF", "recognition ref has the wrong type"
        )
    _identifier(ref.session_id, "recognition_ref.session_id")
    _uint(ref.session_generation, "recognition_ref.session_generation")
    if not isinstance(ref.capture, CaptureRef):
        raise StreamingSpeechViolation(
            "INVALID_CAPTURE_REF", "recognition capture has the wrong type"
        )
    _identifier(ref.capture.capture_id, "recognition_ref.capture.capture_id")
    _uint(ref.capture.capture_generation, "recognition_ref.capture.capture_generation")
    _positive_int(ref.capture.sample_rate_hz, "recognition_ref.capture.sample_rate_hz")


def _validate_recognition_request(request: RecognitionStreamRequest) -> None:
    if not isinstance(request, RecognitionStreamRequest):
        raise StreamingSpeechViolation(
            "INVALID_RECOGNITION_REQUEST", "recognition request has the wrong type"
        )
    _validate_recognition_ref(request.ref)
    if not isinstance(request.turn_detection, RecognitionTurnDetection):
        raise StreamingSpeechViolation(
            "INVALID_TURN_DETECTION", "recognition turn detection is untyped"
        )


def _validate_synthesis_ref(ref: SynthesisStreamRef) -> None:
    if not isinstance(ref, SynthesisStreamRef):
        raise StreamingSpeechViolation(
            "INVALID_SYNTHESIS_REF", "synthesis ref has the wrong type"
        )
    _identifier(ref.stream_id, "synthesis_ref.stream_id")
    _uint(ref.stream_generation, "synthesis_ref.stream_generation")
    if not isinstance(ref.response, ResponseRef):
        raise StreamingSpeechViolation(
            "INVALID_RESPONSE_REF", "synthesis response has the wrong type"
        )
    _validate_response_ref(ref.response)
    _identifier(ref.unit_id, "synthesis_ref.unit_id")
    _uint(ref.unit_seq, "synthesis_ref.unit_seq")


def _validate_response_ref(ref: ResponseRef) -> None:
    if not isinstance(ref, ResponseRef):
        raise StreamingSpeechViolation(
            "INVALID_RESPONSE_REF", "response reference has the wrong type"
        )
    _identifier(ref.interaction_id, "response_ref.interaction_id")
    _identifier(ref.response_id, "response_ref.response_id")
    _uint(ref.response_generation, "response_ref.response_generation")


def _validate_synthesis_request(request: SynthesisStreamRequest) -> None:
    if not isinstance(request, SynthesisStreamRequest):
        raise StreamingSpeechViolation(
            "INVALID_SYNTHESIS_REQUEST", "synthesis request has the wrong type"
        )
    _validate_synthesis_ref(request.ref)
    display = _bounded_text(
        request.display_text,
        "synthesis.display_text",
        max_chars=MAX_SYNTHESIS_TEXT_CHARS,
    )
    _bounded_text(
        request.spoken_text,
        "synthesis.spoken_text",
        max_chars=MAX_SYNTHESIS_TEXT_CHARS,
    )
    _validate_span(request.display_span, "synthesis.display_span")
    if request.display_span.length != len(display):
        raise StreamingSpeechViolation(
            "DISPLAY_SPAN_TEXT_MISMATCH",
            "unit display span length must match its exact display text",
        )
    _positive_int(request.sample_rate_hz, "synthesis.sample_rate_hz")
    _timeout_seconds(request.event_timeout_seconds)


def _validate_span(span: TextSpan, field: str) -> None:
    if not isinstance(span, TextSpan):
        raise StreamingSpeechViolation("INVALID_TEXT_SPAN", f"{field} has wrong type")
    _uint(span.start, f"{field}.start")
    _uint(span.end, f"{field}.end")
    if span.end < span.start:
        raise StreamingSpeechViolation(
            "INVALID_TEXT_SPAN", f"{field}.end cannot precede start"
        )


def _validate_hypothesis(hypothesis: RecognitionHypothesis | None) -> None:
    if not isinstance(hypothesis, RecognitionHypothesis) or not hypothesis.alternatives:
        raise StreamingSpeechViolation(
            "EMPTY_HYPOTHESIS", "recognition text events require alternatives"
        )
    if (
        type(hypothesis.alternatives) is not tuple
        or len(hypothesis.alternatives) > MAX_RECOGNITION_ALTERNATIVES
    ):
        raise StreamingSpeechViolation(
            "RECOGNITION_ALTERNATIVE_LIMIT_EXCEEDED",
            "recognition alternatives must be a bounded immutable tuple",
        )
    if type(hypothesis.selected_index) is not int or not (
        0 <= hypothesis.selected_index < len(hypothesis.alternatives)
    ):
        raise StreamingSpeechViolation(
            "INVALID_ALTERNATIVE_INDEX", "selected recognition alternative is absent"
        )
    for alternative in hypothesis.alternatives:
        if not isinstance(alternative, RecognitionAlternative):
            raise StreamingSpeechViolation(
                "INVALID_RECOGNITION_ALTERNATIVE",
                "recognition alternative has the wrong type",
            )
        _bounded_text(
            alternative.raw_text,
            "recognition.raw_text",
            max_chars=MAX_RECOGNITION_TEXT_CHARS,
        )
        _bounded_text(
            alternative.display_text,
            "recognition.display_text",
            max_chars=MAX_RECOGNITION_TEXT_CHARS,
        )
        confidence = alternative.confidence
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise StreamingSpeechViolation(
                "INVALID_CONFIDENCE", "recognition confidence must be in [0, 1]"
            )


def _empty_synthesis_payload(event: StreamingSynthesisEvent) -> bool:
    return (
        event.sample_count == 0
        and event.pcm_s16le is None
        and event.display_span is None
        and event.spoken_span is None
    )


def _recognition_key(ref: RecognitionStreamRef) -> _RecognitionKey:
    return ref.session_id, ref.session_generation


def _synthesis_key(ref: SynthesisStreamRef) -> _SynthesisKey:
    return ref.stream_id, ref.stream_generation


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StreamingSpeechViolation(
            "INVALID_REQUIRED_TEXT", f"{field} must be a non-empty string"
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise StreamingSpeechViolation(
            "INVALID_UNICODE_SCALAR", f"{field} contains invalid Unicode"
        ) from exc
    return value


def _bounded_text(value: object, field: str, *, max_chars: int) -> str:
    text = _required_text(value, field)
    if len(text) > max_chars:
        raise StreamingSpeechViolation(
            "TEXT_LIMIT_EXCEEDED",
            f"{field} exceeds its bounded character limit",
        )
    return text


def _identifier(value: object, field: str) -> str:
    return _bounded_text(value, field, max_chars=MAX_ID_CHARS)


def _uint(value: object, field: str) -> int:
    if type(value) is not int or value < 0 or value > MAX_SAFE_INTEGER:
        raise StreamingSpeechViolation(
            "INVALID_UNSIGNED_INTEGER",
            f"{field} must be an integer between zero and {MAX_SAFE_INTEGER}",
        )
    return value


def _positive_int(value: object, field: str) -> int:
    parsed = _uint(value, field)
    if parsed == 0:
        raise StreamingSpeechViolation(
            "INVALID_POSITIVE_INTEGER", f"{field} must be positive"
        )
    return parsed


def _bounded_sample_count(value: object, field: str) -> int:
    count = _positive_int(value, field)
    if count > MAX_AUDIO_SAMPLES_PER_FRAME:
        raise StreamingSpeechViolation(
            "AUDIO_FRAME_LIMIT_EXCEEDED",
            f"{field} exceeds the bounded streaming frame size",
        )
    return count


def _timeout_seconds(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        or value > MAX_STREAM_TIMEOUT_SECONDS
    ):
        raise StreamingSpeechViolation(
            "INVALID_STREAM_TIMEOUT",
            f"timeout must be finite and in (0, {MAX_STREAM_TIMEOUT_SECONDS}]",
        )
    return float(value)
