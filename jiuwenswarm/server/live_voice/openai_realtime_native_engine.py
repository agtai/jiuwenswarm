# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Authority-free OpenAI Realtime Native interaction event mapper.

The engine owns one continuous Provider session and converts a closed subset of
GA Realtime events into bounded proposals.  It never commits Agent, Tool, Task,
history, presentation, or audio effects: Runtime admission is required before
Provider audio can leave this boundary.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import logging
import unicodedata
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    ResponseRef,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.interaction_engine import (
    INTERACTION_ACTION_OPERATIONS,
    InteractionAction,
    InteractionEnginePort,
    InteractionEngineViolation,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeContractLedger,
    NativeDelegateProposal,
    NativeInteractionBinding,
    NativeInteractionContractViolation,
    NativePresentationCursor,
    NativeTurnCommit,
)
from jiuwenswarm.server.live_voice.openai_realtime_session import (
    OpenAIRealtimeEvent,
    OpenAIRealtimeSession,
    OpenAIRealtimeSessionConfig,
    OpenAIRealtimeSessionError,
    RealtimeSocketFactory,
)


NATIVE_PCM_SAMPLE_RATE = 24_000
NATIVE_AUDIO_FRAME_BYTES = (NATIVE_PCM_SAMPLE_RATE // 50) * 2
MAX_NATIVE_INPUT_AUDIO_BYTES = 96_000
MAX_NATIVE_AUDIO_DELTA_BYTES = 96_000
MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES = 65_536
_MAX_ENGINE_CAPACITY = 4_096
_MAX_NATIVE_ACTIONS = 1_024
_MAX_PROVIDER_AUDIO_ITEMS = 64
_MAX_IDENTITY_CHARS = 256
_MAX_IDENTITY_UTF8_BYTES = 1_024


logger = logging.getLogger(__name__)


def _provider_error_label(value: object) -> str:
    if value is None:
        return "none"
    if type(value) is not str or not value or len(value) > 96 or not value.isascii():
        return "other"
    if any(not (character.isalnum() or character in "._-") for character in value):
        return "other"
    return value


class OpenAIRealtimeNativeInteractionError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class NativeProviderState(StrEnum):
    NEW = "new"
    STARTING = "starting"
    READY = "ready"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    TURN_COMMITTED = "turn_committed"
    RESPONSE_PENDING = "response_pending"
    SPEAKING = "speaking"
    DELEGATING = "delegating"
    DELEGATE_WAIT = "delegate_wait"
    CANCELLING = "cancelling"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class NativeInputAudioFrame:
    seq: int
    sample_cursor: int
    pcm16: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.seq) is not int or not 0 <= self.seq <= MAX_SAFE_INTEGER:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_INPUT_AUDIO_SEQUENCE_INVALID",
                "input audio sequence must be an unsigned safe integer",
            )
        if (
            type(self.sample_cursor) is not int
            or not 0 <= self.sample_cursor <= MAX_SAFE_INTEGER
        ):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_INPUT_AUDIO_CURSOR_INVALID",
                "input audio cursor must be an unsigned safe integer",
            )
        if (
            type(self.pcm16) is not bytes
            or not self.pcm16
            or len(self.pcm16) % 2
            or len(self.pcm16) > MAX_NATIVE_INPUT_AUDIO_BYTES
        ):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_INPUT_AUDIO_INVALID",
                "input audio must be bounded non-empty PCM16 bytes",
            )


@dataclass(frozen=True, slots=True)
class NativeAudioOutput:
    provider_event_id: str
    provider_response_id: str
    provider_item_id: str
    content_index: int
    sequence: int
    pcm16: bytes = field(repr=False)
    response: ResponseRef
    # The Browser frame may be zero-padded to 20 ms.  This retains only the
    # actual Provider audio samples represented by that frame.
    provider_sample_count: int | None = None


@dataclass(frozen=True, slots=True)
class NativeProviderDone:
    provider_event_id: str
    provider_response_id: str
    response: ResponseRef
    completed: bool
    transcript: str | None
    transcript_event_id: str | None


@dataclass(frozen=True, slots=True)
class NativeEngineEvent:
    action: InteractionAction | None = None
    turn_commit: NativeTurnCommit | None = None
    audio: NativeAudioOutput | None = field(default=None, repr=False)
    delegate: NativeDelegateProposal | None = field(default=None, repr=False)
    provider_done: NativeProviderDone | None = None


@dataclass(frozen=True, slots=True)
class NativeEngineSnapshot:
    state: NativeProviderState
    next_input_sequence: int
    next_input_sample_cursor: int
    turn_count: int
    response_count: int
    pending_audio_count: int
    released_audio_count: int
    emitted_event_count: int
    retained_action_count: int
    delegate_count: int
    primary_error_reason: str | None


@dataclass(slots=True)
class _ProviderAudioItem:
    output_index: int
    provider_item_id: str
    content_index: int
    received_samples: int = 0
    transcript: str | None = None
    transcript_event_id: str | None = None
    transcript_done: bool = False
    done: bool = False
    audio_buffer: bytearray = field(default_factory=bytearray, repr=False)
    audio_buffer_event_id: str | None = None


@dataclass(slots=True)
class _ProviderResponse:
    provider_response_id: str
    turn_id: str
    runtime_ref: ResponseRef | None = None
    audio_items: dict[int, _ProviderAudioItem] = field(default_factory=dict)
    next_audio_sequence: int = 0
    done: bool = False
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class _BufferedAudio:
    provider_event_id: str
    provider_response_id: str
    provider_item_id: str
    content_index: int
    sequence: int
    pcm16: bytes = field(repr=False)
    provider_sample_count: int


@dataclass(frozen=True, slots=True)
class _DelegateWait:
    proposal: NativeDelegateProposal
    response: ResponseRef


@dataclass(frozen=True, slots=True)
class _DelegateResult:
    response: ResponseRef
    digest: str
    event_ids: tuple[str, str]


_EVENT_KEYS = {
    "error": frozenset({"type", "event_id", "error"}),
    "conversation.item.truncated": frozenset(
        {"type", "event_id", "item_id", "content_index", "audio_end_ms"}
    ),
    "input_audio_buffer.speech_started": frozenset(
        {"type", "event_id", "audio_start_ms", "item_id"}
    ),
    "input_audio_buffer.speech_stopped": frozenset(
        {"type", "event_id", "audio_end_ms", "item_id"}
    ),
    "input_audio_buffer.committed": frozenset(
        {"type", "event_id", "previous_item_id", "item_id"}
    ),
    "response.created": frozenset({"type", "event_id", "response"}),
    "response.output_audio.delta": frozenset(
        {
            "type",
            "event_id",
            "response_id",
            "item_id",
            "output_index",
            "content_index",
            "delta",
        }
    ),
    "response.output_audio.done": frozenset(
        {
            "type",
            "event_id",
            "response_id",
            "item_id",
            "output_index",
            "content_index",
        }
    ),
    "response.output_audio_transcript.done": frozenset(
        {
            "type",
            "event_id",
            "response_id",
            "item_id",
            "output_index",
            "content_index",
            "transcript",
        }
    ),
    "response.function_call_arguments.done": frozenset(
        {
            "type",
            "event_id",
            "response_id",
            "item_id",
            "output_index",
            "call_id",
            "name",
            "arguments",
        }
    ),
    "response.done": frozenset({"type", "event_id", "response"}),
}
_RESPONSE_RESOURCE_KEYS = frozenset(
    {
        "object",
        "id",
        "status",
        "status_details",
        "output",
        "conversation_id",
        "output_modalities",
        "max_output_tokens",
        "audio",
        "usage",
        "metadata",
    }
)

# These GA lifecycle/delta events carry no Native authority.  They are consumed
# only after the shared kernel has validated their bounded JSON envelope.
_HARMLESS_EVENT_TYPES = frozenset(
    {
        "conversation.created",
        "conversation.item.added",
        "conversation.item.done",
        "conversation.item.input_audio_transcription.completed",
        "conversation.item.input_audio_transcription.delta",
        "conversation.item.input_audio_transcription.failed",
        "conversation.item.truncated",
        "input_audio_buffer.cleared",
        "input_audio_buffer.timeout_triggered",
        "rate_limits.updated",
        "response.content_part.added",
        "response.content_part.done",
        "response.function_call_arguments.delta",
        "response.output_audio_transcript.delta",
        "response.output_item.added",
        "response.output_item.done",
        "response.text.delta",
        "response.text.done",
    }
)


def _session_update() -> dict[str, object]:
    return {
        "type": "realtime",
        "output_modalities": ["audio"],
        "instructions": (
            "Respond by voice. Use jiuwen_delegate only when authorized Jiuwen "
            "Agent or Task work is required. Never claim that delegated work ran "
            "until its function result is provided."
        ),
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": NATIVE_PCM_SAMPLE_RATE},
                "turn_detection": {
                    "type": "semantic_vad",
                    "eagerness": "auto",
                    "create_response": False,
                    "interrupt_response": False,
                },
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": NATIVE_PCM_SAMPLE_RATE},
                "voice": "marin",
            },
        },
        "tools": [
            {
                "type": "function",
                "name": "jiuwen_delegate",
                "description": "Delegate authorized Jiuwen Agent or Task work.",
                "parameters": {
                    "type": "object",
                    "properties": {"request_text": {"type": "string"}},
                    "required": ["request_text"],
                    "additionalProperties": False,
                },
            }
        ],
        "tool_choice": "auto",
    }


def _identity(value: object, *, reason: str, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_IDENTITY_CHARS
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        raise OpenAIRealtimeNativeInteractionError(
            reason, f"{field_name} must be a bounded canonical identity"
        )
    try:
        length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        length = _MAX_IDENTITY_UTF8_BYTES + 1
    if length > _MAX_IDENTITY_UTF8_BYTES:
        raise OpenAIRealtimeNativeInteractionError(
            reason, f"{field_name} must be a bounded canonical identity"
        )
    return value


def _cursor(value: object, *, reason: str, field_name: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
        raise OpenAIRealtimeNativeInteractionError(
            reason, f"{field_name} must be an unsigned safe integer"
        )
    return value


def _response_ref(value: object, binding: NativeInteractionBinding) -> ResponseRef:
    if not isinstance(value, ResponseRef):
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_RESPONSE_REF_INVALID", "response must use ResponseRef"
        )
    if value.interaction_id != binding.interaction_id:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_RESPONSE_SCOPE_MISMATCH",
            "response interaction must match the Native binding",
        )
    _identity(
        value.response_id,
        reason="NATIVE_RESPONSE_REF_INVALID",
        field_name="response_id",
    )
    if (
        type(value.response_generation) is not int
        or not 0 < value.response_generation <= MAX_SAFE_INTEGER
    ):
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_RESPONSE_REF_INVALID",
            "response generation must be a positive safe integer",
        )
    return value


def _closed_event(event: OpenAIRealtimeEvent) -> dict[str, object]:
    data = event.to_dict()
    expected = _EVENT_KEYS.get(event.event_type)
    if expected is None:
        if event.event_type in _HARMLESS_EVENT_TYPES:
            return data
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_EVENT_UNSUPPORTED",
            "Provider event type is outside the Native allowlist",
        )
    if set(data) != expected:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_EVENT_NOT_CLOSED",
            "Provider event fields must match the closed Native mapping",
        )
    return data


def _response_envelope(
    value: object, *, done: bool
) -> tuple[str, str, list[object] | None]:
    if not isinstance(value, Mapping) or set(value) != _RESPONSE_RESOURCE_KEYS:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_NOT_CLOSED",
            "Provider response fields must match the closed Native mapping",
        )
    if value["object"] != "realtime.response":
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_INVALID",
            "Provider response must use the Realtime response object",
        )
    response_id = _identity(
        value["id"],
        reason="NATIVE_PROVIDER_RESPONSE_INVALID",
        field_name="provider response id",
    )
    status = _identity(
        value["status"],
        reason="NATIVE_PROVIDER_RESPONSE_INVALID",
        field_name="provider response status",
    )
    candidate = value["output"]
    if type(candidate) is not list:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_INVALID",
            "Provider response output must be a list",
        )
    if not done and candidate:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_INVALID",
            "created Provider response output must be empty",
        )
    _identity(
        value["conversation_id"],
        reason="NATIVE_PROVIDER_RESPONSE_INVALID",
        field_name="Provider conversation id",
    )
    if value["output_modalities"] != ["audio"]:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_INVALID",
            "Native Provider response must use audio output",
        )
    maximum = value["max_output_tokens"]
    if maximum != "inf" and (type(maximum) is not int or not 1 <= maximum <= 4_096):
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_INVALID",
            "Provider response max_output_tokens is invalid",
        )
    audio = value["audio"]
    if not isinstance(audio, Mapping) or set(audio) != {"output"}:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_INVALID",
            "Provider response audio fields are invalid",
        )
    audio_output = audio["output"]
    if not isinstance(audio_output, Mapping) or set(audio_output) != {
        "format",
        "voice",
    }:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_INVALID",
            "Provider response audio output fields are invalid",
        )
    audio_format = audio_output["format"]
    if not isinstance(audio_format, Mapping) or dict(audio_format) != {
        "type": "audio/pcm",
        "rate": NATIVE_PCM_SAMPLE_RATE,
    }:
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_RESPONSE_INVALID",
            "Provider response audio format must be PCM24k",
        )
    _identity(
        audio_output["voice"],
        reason="NATIVE_PROVIDER_RESPONSE_INVALID",
        field_name="Provider voice",
    )
    for field_name in ("status_details", "usage", "metadata"):
        optional_object = value[field_name]
        if optional_object is not None and not isinstance(optional_object, Mapping):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_RESPONSE_INVALID",
                f"Provider response {field_name} must be an object or null",
            )
    output = candidate
    return response_id, status, output


def _digest_id(prefix: str, value: Mapping[str, object]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"{prefix}:{digest}"


class OpenAIRealtimeNativeInteractionEngine:
    """Map one official Realtime session to bounded Native proposals."""

    def __init__(
        self,
        config: OpenAIRealtimeSessionConfig,
        *,
        binding: NativeInteractionBinding,
        socket_factory: RealtimeSocketFactory | None = None,
        event_queue_capacity: int = 256,
        pending_audio_capacity: int = 64,
    ) -> None:
        if not isinstance(binding, NativeInteractionBinding):
            raise TypeError("binding must use NativeInteractionBinding")
        for value, name in (
            (event_queue_capacity, "event_queue_capacity"),
            (pending_audio_capacity, "pending_audio_capacity"),
        ):
            if type(value) is not int or not 0 < value <= _MAX_ENGINE_CAPACITY:
                raise ValueError(f"{name} must be an integer in [1, 4096]")
        self._binding = binding
        self._session = OpenAIRealtimeSession(config, socket_factory=socket_factory)
        self._event_queue_capacity = event_queue_capacity
        self._pending_audio_capacity = pending_audio_capacity
        self._state = NativeProviderState.NEW
        self._input_audio_lock = asyncio.Lock()
        self._delegate_result_lock = asyncio.Lock()
        self._cancel_lock = asyncio.Lock()
        self._primary_error_reason: str | None = None
        self._pending_events: deque[NativeEngineEvent] = deque()
        self._pending_audio: deque[_BufferedAudio] = deque()
        self._processed_event_ids: set[str] = set()
        self._action_port = InteractionEnginePort(
            INTERACTION_ACTION_OPERATIONS,
            scope=binding.scope,
            max_actions=_MAX_NATIVE_ACTIONS,
        )
        self._contract_ledger = NativeContractLedger(capacity=_MAX_ENGINE_CAPACITY)
        self._next_input_sequence = 0
        self._next_input_sample_cursor = 0
        self._turn_count = 0
        self._emitted_event_count = 0
        self._released_audio_count = 0
        self._delegate_count = 0
        self._input_item_id: str | None = None
        self._input_start_ms: int | None = None
        self._input_end_ms: int | None = None
        self._current_turn_id: str | None = None
        self._pending_direct_response_turn_id: str | None = None
        self._direct_response_requested_turn_ids: set[str] = set()
        self._responses: dict[str, _ProviderResponse] = {}
        self._current_response_id: str | None = None
        self._delegates: dict[str, _DelegateWait] = {}
        self._delegate_results: dict[str, _DelegateResult] = {}
        self._pending_delegate_response: tuple[str, ResponseRef] | None = None
        self._cancelled: dict[
            str, tuple[NativePresentationCursor, tuple[str, str]]
        ] = {}
        self._locally_fenced: set[str] = set()

    async def start(self) -> None:
        if self._state is not NativeProviderState.NEW:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_ENGINE_STATE_INVALID", "Native engine can only start once"
            )
        self._state = NativeProviderState.STARTING
        try:
            await self._session.open(session_update=_session_update())
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            self._state = NativeProviderState.FAILED
            raise
        except OpenAIRealtimeSessionError as exc:
            self._mark_failed(exc.reason)
            raise OpenAIRealtimeNativeInteractionError(exc.reason, str(exc)) from None
        self._state = NativeProviderState.READY

    async def offer_audio(self, frame: NativeInputAudioFrame) -> str:
        self._require_operational()
        if not isinstance(frame, NativeInputAudioFrame):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_INPUT_AUDIO_INVALID",
                "input audio must use NativeInputAudioFrame",
            )
        async with self._input_audio_lock:
            if frame.seq != self._next_input_sequence:
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_INPUT_AUDIO_SEQUENCE_GAP",
                    "input audio sequence must be contiguous",
                )
            if frame.sample_cursor != self._next_input_sample_cursor:
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_INPUT_AUDIO_CURSOR_GAP",
                    "input audio sample cursor must be contiguous",
                )
            try:
                event_id = await self._session.send_event(
                    "input_audio_buffer.append",
                    {"audio": base64.b64encode(frame.pcm16).decode("ascii")},
                )
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                self._state = NativeProviderState.FAILED
                raise
            except OpenAIRealtimeSessionError as exc:
                self._mark_failed(exc.reason)
                raise OpenAIRealtimeNativeInteractionError(
                    exc.reason, str(exc)
                ) from None
            self._next_input_sequence += 1
            self._next_input_sample_cursor += len(frame.pcm16) // 2
            return event_id

    async def next_event(self) -> NativeEngineEvent:
        self._require_operational()
        if self._pending_events:
            return self._release_event(self._pending_events.popleft())
        try:
            provider_event = await self._session.receive_event()
            if provider_event.event_id in self._processed_event_ids:
                return NativeEngineEvent()
            data = _closed_event(provider_event)
            results = self._map_event(provider_event, data)
            self._processed_event_ids.add(provider_event.event_id)
            await self._request_pending_direct_response()
            if not results:
                return NativeEngineEvent()
            if len(results) > self._event_queue_capacity:
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_ENGINE_EVENT_QUEUE_FULL",
                    "Provider event expands beyond the bounded Native queue",
                )
            first, *remaining = results
            self._pending_events.extend(remaining)
            return self._release_event(first)
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            self._state = NativeProviderState.FAILED
            raise
        except OpenAIRealtimeSessionError as exc:
            self._mark_failed(exc.reason)
            raise OpenAIRealtimeNativeInteractionError(exc.reason, str(exc)) from None
        except OpenAIRealtimeNativeInteractionError as exc:
            self._mark_failed(exc.reason)
            raise exc from None

    async def _request_pending_direct_response(self) -> None:
        turn_id = self._pending_direct_response_turn_id
        if turn_id is None:
            return
        current = self._current_response()
        if current is not None and not current.done:
            return
        if turn_id in self._direct_response_requested_turn_ids:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DIRECT_RESPONSE_REQUEST_CONFLICT",
                "one Native turn permits only one direct response request",
            )
        try:
            await self._session.send_event("response.create", {})
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            self._state = NativeProviderState.FAILED
            raise
        except OpenAIRealtimeSessionError as exc:
            self._mark_failed(exc.reason)
            raise OpenAIRealtimeNativeInteractionError(exc.reason, str(exc)) from None
        self._direct_response_requested_turn_ids.add(turn_id)
        self._pending_direct_response_turn_id = None
        self._state = NativeProviderState.RESPONSE_PENDING

    async def admit_response(
        self, provider_response_id: str, response: ResponseRef
    ) -> bool:
        self._require_operational()
        provider_id = _identity(
            provider_response_id,
            reason="NATIVE_PROVIDER_RESPONSE_INVALID",
            field_name="provider response id",
        )
        ref = _response_ref(response, self._binding)
        retained = self._responses.get(provider_id)
        if retained is None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_RESPONSE_NOT_PROPOSED",
                "Provider response must be proposed before Runtime admission",
            )
        if retained.runtime_ref is not None:
            if retained.runtime_ref == ref:
                return False
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_RESPONSE_ADMISSION_CONFLICT",
                "Provider response admission cannot change its Runtime binding",
            )
        releases = [
            buffered
            for buffered in self._pending_audio
            if buffered.provider_response_id == provider_id
        ]
        if len(self._pending_events) + len(releases) > self._event_queue_capacity:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_ENGINE_EVENT_QUEUE_FULL",
                "admitted audio exceeds the bounded Native queue",
            )
        retained.runtime_ref = ref
        retained_audio = deque[_BufferedAudio]()
        for buffered in self._pending_audio:
            if buffered.provider_response_id == provider_id:
                self._pending_events.append(self._audio_event(buffered, ref))
            else:
                retained_audio.append(buffered)
        self._pending_audio = retained_audio
        self._state = NativeProviderState.SPEAKING
        return True

    async def send_delegate_result(
        self, call_id: str, response: ResponseRef, output: str
    ) -> tuple[str, str]:
        self._require_operational()
        async with self._delegate_result_lock:
            return await self._send_delegate_result_locked(call_id, response, output)

    async def _send_delegate_result_locked(
        self, call_id: str, response: ResponseRef, output: str
    ) -> tuple[str, str]:
        self._require_operational()
        parsed_call_id = _identity(
            call_id,
            reason="NATIVE_DELEGATE_CALL_INVALID",
            field_name="Provider call id",
        )
        ref = _response_ref(response, self._binding)
        digest = self._delegate_output_digest(output)
        prior = self._delegate_results.get(parsed_call_id)
        if prior is not None:
            if prior.response == ref and prior.digest == digest:
                return prior.event_ids
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_RESULT_CONFLICT",
                "delegate result cannot change its response or output",
            )
        wait = self._delegates.get(parsed_call_id)
        if wait is None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_CALL_UNKNOWN",
                "delegate result requires one retained proposal",
            )
        if ref.response_generation <= wait.response.response_generation:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_RESPONSE_NOT_NEW",
                "delegate result requires a newer Runtime response generation",
            )
        if self._pending_delegate_response is not None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_RESPONSE_CONFLICT",
                "only one pre-admitted delegate response may be pending",
            )
        try:
            output_event_id = await self._session.send_event(
                "conversation.item.create",
                {
                    "item": {
                        "type": "function_call_output",
                        "call_id": parsed_call_id,
                        "output": output,
                    }
                },
            )
            response_event_id = await self._session.send_event("response.create", {})
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            self._state = NativeProviderState.FAILED
            raise
        except OpenAIRealtimeSessionError as exc:
            self._mark_failed(exc.reason)
            raise OpenAIRealtimeNativeInteractionError(exc.reason, str(exc)) from None
        event_ids = (output_event_id, response_event_id)
        self._delegate_results[parsed_call_id] = _DelegateResult(ref, digest, event_ids)
        self._pending_delegate_response = (wait.proposal.turn_id, ref)
        self._state = NativeProviderState.RESPONSE_PENDING
        return event_ids

    async def cancel_response(
        self, cursor: NativePresentationCursor
    ) -> tuple[str, str]:
        self._require_operational()
        async with self._cancel_lock:
            return await self._cancel_response_locked(cursor)

    async def _cancel_response_locked(
        self, cursor: NativePresentationCursor
    ) -> tuple[str, str]:
        self._require_operational()
        if not isinstance(cursor, NativePresentationCursor):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_CANCEL_CURSOR_INVALID",
                "cancel requires NativePresentationCursor",
            )
        ref = _response_ref(cursor.response, self._binding)
        response = self._find_response(ref)
        prior = self._cancelled.get(response.provider_response_id)
        if prior is not None:
            if prior[0] == cursor:
                return prior[1]
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_CANCEL_CONFLICT", "cancel cursor cannot change on replay"
            )
        matching_items = [
            item
            for item in response.audio_items.values()
            if item.provider_item_id == cursor.provider_item_id
            and item.content_index == cursor.content_index
        ]
        if len(matching_items) != 1:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_CANCEL_CURSOR_MISMATCH",
                "cancel cursor must match the exact Provider output item",
            )
        received_ms = (
            matching_items[0].received_samples * 1_000 // NATIVE_PCM_SAMPLE_RATE
        )
        if cursor.audio_end_ms > received_ms:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_CANCEL_CURSOR_AHEAD",
                "cancel cursor cannot exceed received Provider audio",
            )
        self._state = NativeProviderState.CANCELLING
        try:
            cancel_id = await self._session.send_event(
                "response.cancel", {"response_id": response.provider_response_id}
            )
            truncate_id = await self._session.send_event(
                "conversation.item.truncate",
                {
                    "item_id": cursor.provider_item_id,
                    "content_index": cursor.content_index,
                    "audio_end_ms": cursor.audio_end_ms,
                },
            )
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            self._state = NativeProviderState.FAILED
            raise
        except OpenAIRealtimeSessionError as exc:
            self._mark_failed(exc.reason)
            raise OpenAIRealtimeNativeInteractionError(exc.reason, str(exc)) from None
        ids = (cancel_id, truncate_id)
        self._cancelled[response.provider_response_id] = (cursor, ids)
        response.cancelled = True
        for audio_item in response.audio_items.values():
            audio_item.audio_buffer.clear()
            audio_item.audio_buffer_event_id = None
        self._discard_response_output(response, ref)
        self._state = NativeProviderState.LISTENING
        return ids

    async def fence_response(self, ref: ResponseRef) -> bool:
        """Locally discard one fenced response without mutating Provider state."""

        self._require_operational()
        async with self._cancel_lock:
            parsed = _response_ref(ref, self._binding)
            response = self._find_response(parsed)
            if response.provider_response_id in self._locally_fenced:
                return False
            response.cancelled = True
            for audio_item in response.audio_items.values():
                audio_item.audio_buffer.clear()
                audio_item.audio_buffer_event_id = None
            self._discard_response_output(response, parsed)
            self._locally_fenced.add(response.provider_response_id)
            self._state = NativeProviderState.LISTENING
            return True

    def _discard_response_output(
        self, response: _ProviderResponse, ref: ResponseRef
    ) -> None:
        self._pending_audio = deque(
            item
            for item in self._pending_audio
            if item.provider_response_id != response.provider_response_id
        )
        self._pending_events = deque(
            item
            for item in self._pending_events
            if (item.audio is None or item.audio.response != ref)
            and (item.provider_done is None or item.provider_done.response != ref)
            and (
                item.delegate is None
                or item.delegate.response_generation != ref.response_generation
            )
        )

    async def close(self) -> bool:
        if self._state is NativeProviderState.CLOSED:
            return True
        self._state = NativeProviderState.CLOSING
        try:
            snapshot = await self._session.close()
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            self._state = NativeProviderState.FAILED
            raise
        self._state = (
            NativeProviderState.CLOSED
            if snapshot.close_complete
            else NativeProviderState.CLOSING
        )
        return self._state is NativeProviderState.CLOSED

    def snapshot(self) -> NativeEngineSnapshot:
        return NativeEngineSnapshot(
            state=self._state,
            next_input_sequence=self._next_input_sequence,
            next_input_sample_cursor=self._next_input_sample_cursor,
            turn_count=self._turn_count,
            response_count=len(self._responses),
            pending_audio_count=len(self._pending_audio)
            + sum(
                bool(audio_item.audio_buffer)
                for response in self._responses.values()
                if response.runtime_ref is None
                for audio_item in response.audio_items.values()
            ),
            released_audio_count=self._released_audio_count,
            emitted_event_count=self._emitted_event_count,
            retained_action_count=len(self._action_port.accepted()),
            delegate_count=self._delegate_count,
            primary_error_reason=self._primary_error_reason,
        )

    def _map_event(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        event_type = event.event_type
        if event_type in _HARMLESS_EVENT_TYPES:
            return []
        if event_type == "error":
            self._provider_error(data)
        if event_type == "input_audio_buffer.speech_started":
            return self._speech_started(event, data)
        if event_type == "input_audio_buffer.speech_stopped":
            return self._speech_stopped(event, data)
        if event_type == "input_audio_buffer.committed":
            return self._input_committed(event, data)
        if event_type == "response.created":
            return self._response_created(event, data)
        if event_type == "response.output_audio.delta":
            return self._output_audio(event, data)
        if event_type == "response.output_audio.done":
            return self._output_audio_done(event, data)
        if event_type == "response.output_audio_transcript.done":
            return self._output_transcript(event, data)
        if event_type == "response.function_call_arguments.done":
            return self._function_done(event, data)
        if event_type == "response.done":
            return self._response_done(event, data)
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_EVENT_UNSUPPORTED", "Provider event is unsupported"
        )

    def _provider_error(self, data: dict[str, object]) -> None:
        error = data["error"]
        expected = {"type", "code", "message", "param", "event_id"}
        if not isinstance(error, Mapping) or set(error) != expected:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_EVENT_NOT_CLOSED",
                "Provider error fields must match the closed Native mapping",
            )
        if type(error["type"]) is not str or type(error["message"]) is not str:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_EVENT_NOT_CLOSED",
                "Provider error type and message must be strings",
            )
        for name in ("code", "param", "event_id"):
            if error[name] is not None and type(error[name]) is not str:
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_PROVIDER_EVENT_NOT_CLOSED",
                    "Provider error optional fields must be strings or null",
                )
        logger.error(
            "openai_realtime_native_provider_error type=%s code=%s param=%s "
            "event_id_present=%s",
            _provider_error_label(error["type"]),
            _provider_error_label(error["code"]),
            _provider_error_label(error["param"]),
            error["event_id"] is not None,
        )
        raise OpenAIRealtimeNativeInteractionError(
            "NATIVE_PROVIDER_ERROR", "OpenAI Realtime Provider returned an error"
        )

    def _speech_started(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        item_id = _identity(
            data["item_id"],
            reason="NATIVE_PROVIDER_ITEM_INVALID",
            field_name="input item id",
        )
        start_ms = _cursor(
            data["audio_start_ms"],
            reason="NATIVE_PROVIDER_AUDIO_TIMING_INVALID",
            field_name="audio_start_ms",
        )
        if self._input_item_id is not None and self._input_end_ms is None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_SPEECH_OVERLAP",
                "speech start requires the prior interval to stop",
            )
        operations: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        if self._input_item_id is not None and self._input_end_ms is not None:
            operations.append(("REVISE", (("provider_item_id", item_id),)))
        current = self._current_response()
        if (
            current is not None
            and current.runtime_ref is not None
            and not current.done
            and not current.cancelled
        ):
            operations.append(
                (
                    "STOP",
                    (
                        ("provider_response_id", current.provider_response_id),
                        ("runtime_response_id", current.runtime_ref.response_id),
                        (
                            "response_generation",
                            str(current.runtime_ref.response_generation),
                        ),
                    ),
                )
            )
        operations.append(
            (
                "LISTEN",
                (
                    ("provider_item_id", item_id),
                    ("provider_start_ms", str(start_ms)),
                ),
            )
        )
        if len(operations) > self._event_queue_capacity:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_ENGINE_EVENT_QUEUE_FULL",
                "speech start proposals exceed the bounded event queue",
            )
        self._require_action_capacity(len(operations))
        actions = [
            NativeEngineEvent(
                action=self._action(event.event_id, index, operation, payload)
            )
            for index, (operation, payload) in enumerate(operations)
        ]
        self._input_item_id = item_id
        self._input_start_ms = start_ms
        self._input_end_ms = None
        self._state = NativeProviderState.USER_SPEAKING
        return actions

    def _speech_stopped(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        item_id = _identity(
            data["item_id"],
            reason="NATIVE_PROVIDER_ITEM_INVALID",
            field_name="input item id",
        )
        end_ms = _cursor(
            data["audio_end_ms"],
            reason="NATIVE_PROVIDER_AUDIO_TIMING_INVALID",
            field_name="audio_end_ms",
        )
        if item_id != self._input_item_id:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_ITEM_MISMATCH",
                "speech stop must match the active Provider input item",
            )
        if self._input_start_ms is None or end_ms <= self._input_start_ms:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_AUDIO_TIMING_INVALID",
                "speech stop must end after speech start",
            )
        self._require_action_capacity(1)
        self._input_end_ms = end_ms
        self._state = NativeProviderState.LISTENING
        return [
            NativeEngineEvent(
                action=self._action(
                    event.event_id,
                    0,
                    "SILENCE",
                    (("provider_item_id", item_id),),
                )
            )
        ]

    def _input_committed(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        item_id = _identity(
            data["item_id"],
            reason="NATIVE_PROVIDER_ITEM_INVALID",
            field_name="input item id",
        )
        previous = data["previous_item_id"]
        if previous is not None:
            _identity(
                previous,
                reason="NATIVE_PROVIDER_ITEM_INVALID",
                field_name="previous input item id",
            )
        if item_id != self._input_item_id:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_ITEM_MISMATCH",
                "committed item must match the stopped Provider input item",
            )
        if self._input_start_ms is None or self._input_end_ms is None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_INPUT_COMMIT_BEFORE_STOP",
                "input commit requires one stopped speech interval",
            )
        if self._pending_direct_response_turn_id is not None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DIRECT_RESPONSE_PENDING",
                "only one committed direct turn may await Provider response creation",
            )
        self._require_action_capacity(1)
        self._turn_count += 1
        turn_id = f"native-turn-{self._turn_count:08d}"
        session_id = self._session.snapshot().provider_session_id
        assert session_id is not None
        commit = NativeTurnCommit(
            contract_version=NATIVE_INTERACTION_CONTRACT_VERSION,
            commit_id=_digest_id(
                "native-commit",
                {
                    "binding": self._binding.to_dict(),
                    "turn_id": turn_id,
                    "provider_event_id": event.event_id,
                },
            ),
            binding=self._binding,
            turn_id=turn_id,
            provider_session_id=session_id,
            provider_item_id=item_id,
            provider_event_id=event.event_id,
            causation_id=event.event_id,
            input_audio_start_ms=self._input_start_ms,
            input_audio_end_ms=self._input_end_ms,
            committed_audio_ms=self._input_end_ms - self._input_start_ms,
        )
        self._contract_ledger.accept_commit(commit)
        action = self._action(
            event.event_id,
            0,
            "TURN_COMMIT",
            (("turn_id", turn_id), ("provider_item_id", item_id)),
        )
        self._current_turn_id = turn_id
        self._pending_direct_response_turn_id = turn_id
        self._input_item_id = None
        self._input_start_ms = None
        self._input_end_ms = None
        self._state = NativeProviderState.TURN_COMMITTED
        return [NativeEngineEvent(action=action, turn_commit=commit)]

    def _response_created(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        if self._current_turn_id is None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_RESPONSE_BEFORE_TURN_COMMIT",
                "Provider response requires a committed Native turn",
            )
        provider_id, status, _ = _response_envelope(data["response"], done=False)
        if status != "in_progress":
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_RESPONSE_INVALID",
                "created response must be in progress",
            )
        self._require_action_capacity(1)
        existing = self._responses.get(provider_id)
        if existing is not None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_RESPONSE_CONFLICT",
                "Provider response id cannot be reused",
            )
        prior_turn_response = any(
            response.turn_id == self._current_turn_id
            for response in self._responses.values()
        )
        pending_delegate = self._pending_delegate_response
        if prior_turn_response and (
            pending_delegate is None
            or pending_delegate[0] != self._current_turn_id
        ):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DIRECT_RESPONSE_ALREADY_CREATED",
                "one Native turn permits only one direct Provider response",
            )
        if not prior_turn_response and pending_delegate is not None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_RESPONSE_TURN_MISMATCH",
                "delegate successor must bind the exact source Native turn",
            )
        response = _ProviderResponse(
            provider_response_id=provider_id,
            turn_id=self._current_turn_id,
        )
        if pending_delegate is not None:
            response.runtime_ref = pending_delegate[1]
            self._pending_delegate_response = None
        self._responses[provider_id] = response
        self._current_response_id = provider_id
        self._state = NativeProviderState.RESPONSE_PENDING
        payload = [
            ("provider_response_id", provider_id),
            ("turn_id", self._current_turn_id),
        ]
        if response.runtime_ref is not None:
            payload.extend(
                (
                    ("runtime_response_id", response.runtime_ref.response_id),
                    (
                        "response_generation",
                        str(response.runtime_ref.response_generation),
                    ),
                )
            )
        action = self._action(
            event.event_id,
            0,
            "SPEAK",
            tuple(payload),
        )
        return [NativeEngineEvent(action=action)]

    def _provider_audio_item(
        self,
        response: _ProviderResponse,
        *,
        output_index: int,
        item_id: str,
        content_index: int,
        allow_create: bool,
    ) -> _ProviderAudioItem:
        existing = response.audio_items.get(output_index)
        if existing is not None:
            if (
                existing.provider_item_id != item_id
                or existing.content_index != content_index
            ):
                logger.error(
                    "openai_realtime_native_audio_identity_mismatch "
                    "item_changed=%s content_changed=%s output_index=%s "
                    "response_cancelled=%s response_done=%s",
                    existing.provider_item_id != item_id,
                    existing.content_index != content_index,
                    output_index,
                    response.cancelled,
                    response.done,
                )
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_PROVIDER_ITEM_MISMATCH",
                    "one Provider output index must keep one audio identity",
                )
            return existing
        if not allow_create:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_CANCEL_CURSOR_MISMATCH",
                "presentation cursor must match an emitted Provider audio item",
            )
        if len(response.audio_items) >= _MAX_PROVIDER_AUDIO_ITEMS:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_AUDIO_ITEMS_FULL",
                "Provider response exceeds the bounded audio item count",
        )
        if any(
            item.provider_item_id == item_id
            for item in response.audio_items.values()
        ):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_ITEM_MISMATCH",
                "Provider audio item id cannot move to another output index",
            )
        if response.audio_items:
            prior_index = max(response.audio_items)
            if output_index <= prior_index:
                logger.error(
                    "openai_realtime_native_audio_index_mismatch "
                    "incoming_output_index=%s prior_output_index=%s",
                    output_index,
                    prior_index,
                )
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_PROVIDER_ITEM_MISMATCH",
                    "new Provider audio item indexes must advance",
                )
        created = _ProviderAudioItem(
            output_index=output_index,
            provider_item_id=item_id,
            content_index=content_index,
        )
        response.audio_items[output_index] = created
        return created

    def _output_audio(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        response = self._require_response(data["response_id"])
        if response.cancelled:
            return []
        if response.done:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_STALE_PROVIDER_AUDIO",
                "Provider audio cannot follow response completion or cancel",
            )
        item_id = _identity(
            data["item_id"],
            reason="NATIVE_PROVIDER_ITEM_INVALID",
            field_name="output item id",
        )
        output_index = _cursor(
            data["output_index"],
            reason="NATIVE_PROVIDER_AUDIO_INVALID",
            field_name="output_index",
        )
        content_index = _cursor(
            data["content_index"],
            reason="NATIVE_PROVIDER_AUDIO_INVALID",
            field_name="content_index",
        )
        audio_item = self._provider_audio_item(
            response,
            output_index=output_index,
            item_id=item_id,
            content_index=content_index,
            allow_create=True,
        )
        if audio_item.done:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_STALE_PROVIDER_AUDIO",
                "Provider audio cannot follow audio item completion",
            )
        delta = data["delta"]
        if type(delta) is not str:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_AUDIO_INVALID", "Provider audio must be base64 text"
            )
        try:
            pcm16 = base64.b64decode(delta, validate=True)
        except (binascii.Error, ValueError):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_AUDIO_INVALID", "Provider audio is invalid base64"
            ) from None
        if len(pcm16) > MAX_NATIVE_AUDIO_DELTA_BYTES:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_AUDIO_TOO_LARGE", "Provider audio delta is oversized"
            )
        if not pcm16 or len(pcm16) % 2:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_AUDIO_INVALID", "Provider audio must be PCM16 bytes"
            )
        retained_prefix = bytes(audio_item.audio_buffer)
        combined = retained_prefix + pcm16
        frame_count = len(combined) // NATIVE_AUDIO_FRAME_BYTES
        remainder = combined[frame_count * NATIVE_AUDIO_FRAME_BYTES :]
        if response.runtime_ref is None:
            other_partials = sum(
                bool(candidate_item.audio_buffer)
                for candidate in self._responses.values()
                if candidate.runtime_ref is None
                for candidate_item in candidate.audio_items.values()
                if candidate is not response or candidate_item is not audio_item
            )
            if (
                len(self._pending_audio)
                + other_partials
                + frame_count
                + bool(remainder)
                > self._pending_audio_capacity
            ):
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_PENDING_AUDIO_FULL",
                    "unadmitted Provider audio exceeds the bounded buffer",
                )
        elif frame_count > self._event_queue_capacity:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_ENGINE_EVENT_QUEUE_FULL",
                "Provider audio delta expands beyond the bounded Native queue",
            )
        prefix_event_id = audio_item.audio_buffer_event_id
        buffered_frames: list[_BufferedAudio] = []
        for ordinal in range(frame_count):
            offset = ordinal * NATIVE_AUDIO_FRAME_BYTES
            sequence = response.next_audio_sequence + ordinal
            buffered_frames.append(
                _BufferedAudio(
                    # One Provider delta may contain several 20 ms media
                    # segments, while one segment may cross two deltas.  The
                    # first contributing Provider event remains the exact
                    # causation identity; Runtime disambiguates by sequence.
                    provider_event_id=(
                        prefix_event_id
                        if ordinal == 0 and retained_prefix and prefix_event_id
                        else event.event_id
                    ),
                    provider_response_id=response.provider_response_id,
                    provider_item_id=item_id,
                    content_index=content_index,
                    sequence=sequence,
                    pcm16=combined[offset : offset + NATIVE_AUDIO_FRAME_BYTES],
                    provider_sample_count=NATIVE_AUDIO_FRAME_BYTES // 2,
                )
            )
        audio_item.audio_buffer = bytearray(remainder)
        audio_item.audio_buffer_event_id = event.event_id if remainder else None
        response.next_audio_sequence += frame_count
        audio_item.received_samples += len(pcm16) // 2
        if response.runtime_ref is None:
            self._pending_audio.extend(buffered_frames)
            return []
        self._state = NativeProviderState.SPEAKING
        return [
            self._audio_event(buffered, response.runtime_ref)
            for buffered in buffered_frames
        ]

    def _output_audio_done(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        response = self._require_response(data["response_id"])
        if response.cancelled:
            return []
        self._require_live_response_event(response)
        item_id = _identity(
            data["item_id"],
            reason="NATIVE_PROVIDER_ITEM_INVALID",
            field_name="audio item id",
        )
        output_index = _cursor(
            data["output_index"],
            reason="NATIVE_PROVIDER_AUDIO_INVALID",
            field_name="output_index",
        )
        content_index = _cursor(
            data["content_index"],
            reason="NATIVE_PROVIDER_AUDIO_INVALID",
            field_name="content_index",
        )
        audio_item = self._provider_audio_item(
            response,
            output_index=output_index,
            item_id=item_id,
            content_index=content_index,
            allow_create=True,
        )
        if audio_item.done:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_AUDIO_DONE_CONFLICT",
                "Provider audio item cannot complete twice",
            )
        audio_events = self._flush_audio_buffer(response, audio_item, event.event_id)
        audio_item.done = True
        return audio_events

    def _flush_audio_buffer(
        self,
        response: _ProviderResponse,
        audio_item: _ProviderAudioItem,
        provider_event_id: str,
    ) -> list[NativeEngineEvent]:
        if not audio_item.audio_buffer:
            audio_item.audio_buffer_event_id = None
            return []
        provider_sample_count = len(audio_item.audio_buffer) // 2
        padding = NATIVE_AUDIO_FRAME_BYTES - len(audio_item.audio_buffer)
        buffered = _BufferedAudio(
            provider_event_id=audio_item.audio_buffer_event_id or provider_event_id,
            provider_response_id=response.provider_response_id,
            provider_item_id=audio_item.provider_item_id,
            content_index=audio_item.content_index,
            sequence=response.next_audio_sequence,
            pcm16=bytes(audio_item.audio_buffer) + bytes(padding),
            provider_sample_count=provider_sample_count,
        )
        if response.runtime_ref is None:
            if len(self._pending_audio) + 1 > self._pending_audio_capacity:
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_PENDING_AUDIO_FULL",
                    "unadmitted Provider audio exceeds the bounded buffer",
                )
            self._pending_audio.append(buffered)
            audio_events: list[NativeEngineEvent] = []
        else:
            if self._event_queue_capacity < 1:
                raise OpenAIRealtimeNativeInteractionError(
                    "NATIVE_ENGINE_EVENT_QUEUE_FULL",
                    "Provider audio completion exceeds the Native queue",
                )
            self._state = NativeProviderState.SPEAKING
            audio_events = [self._audio_event(buffered, response.runtime_ref)]
        response.next_audio_sequence += 1
        audio_item.audio_buffer.clear()
        audio_item.audio_buffer_event_id = None
        return audio_events

    def _output_transcript(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        response = self._require_response(data["response_id"])
        if response.cancelled:
            return []
        self._require_live_response_event(response)
        item_id = _identity(
            data["item_id"],
            reason="NATIVE_PROVIDER_ITEM_INVALID",
            field_name="transcript item id",
        )
        output_index = _cursor(
            data["output_index"],
            reason="NATIVE_PROVIDER_TRANSCRIPT_INVALID",
            field_name="output_index",
        )
        content_index = _cursor(
            data["content_index"],
            reason="NATIVE_PROVIDER_TRANSCRIPT_INVALID",
            field_name="content_index",
        )
        audio_item = self._provider_audio_item(
            response,
            output_index=output_index,
            item_id=item_id,
            content_index=content_index,
            allow_create=True,
        )
        if audio_item.transcript_done:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_TRANSCRIPT_CONFLICT",
                "Provider audio transcript cannot complete twice",
            )
        transcript = data["transcript"]
        if type(transcript) is not str:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_TRANSCRIPT_INVALID",
                "complete transcript must be canonical text",
            )
        canonical = transcript.strip().replace("\r\n", "\n").replace("\r", "\n")
        if not canonical:
            # OpenAI also emits transcript.done for interrupted, incomplete,
            # and cancelled responses.  A semantically empty transcript is
            # absence of optional history text, not a Native session failure.
            audio_item.transcript = None
            audio_item.transcript_event_id = None
            audio_item.transcript_done = True
            return []
        forbidden_codepoints = tuple(
            sorted(
                {
                    f"U+{ord(character):04X}"
                    for character in canonical
                    if character != "\n"
                    and unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
                }
            )[:8]
        )
        if forbidden_codepoints:
            logger.error(
                "openai_realtime_native_transcript_control "
                "forbidden_codepoints=%s transcript_utf8_bytes=%s",
                ",".join(forbidden_codepoints),
                len(canonical.encode("utf-8", errors="replace")),
            )
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_TRANSCRIPT_INVALID",
                "complete transcript must be canonical text",
            )
        try:
            transcript_bytes = canonical.encode("utf-8")
        except UnicodeEncodeError:
            transcript_bytes = b"x" * 65_537
        if len(transcript_bytes) > 65_536:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_TRANSCRIPT_INVALID",
                "complete transcript is oversized",
            )
        audio_item.transcript = canonical
        audio_item.transcript_event_id = event.event_id
        audio_item.transcript_done = True
        return []

    def _function_done(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        response = self._require_response(data["response_id"])
        if response.cancelled:
            return []
        self._require_live_response_event(response)
        if response.runtime_ref is None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_BEFORE_ADMISSION",
                "delegate proposal requires Runtime response admission",
            )
        if data["name"] != "jiuwen_delegate":
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_FUNCTION_UNSUPPORTED",
                "Provider function is outside the Native delegate contract",
            )
        self._require_action_capacity(1)
        _cursor(
            data["output_index"],
            reason="NATIVE_DELEGATE_ARGUMENTS_INVALID",
            field_name="output_index",
        )
        call_id = _identity(
            data["call_id"],
            reason="NATIVE_DELEGATE_CALL_INVALID",
            field_name="Provider call id",
        )
        item_id = _identity(
            data["item_id"],
            reason="NATIVE_PROVIDER_ITEM_INVALID",
            field_name="function item id",
        )
        try:
            proposal = NativeDelegateProposal.from_function_call(
                binding=self._binding,
                turn_id=response.turn_id,
                response_generation=response.runtime_ref.response_generation,
                provider_event_id=event.event_id,
                provider_call_id=call_id,
                provider_item_id=item_id,
                arguments=data["arguments"],
            )
            accepted, retained = self._contract_ledger.accept_delegate(proposal)
        except NativeInteractionContractViolation as exc:
            raise OpenAIRealtimeNativeInteractionError(exc.reason, str(exc)) from None
        existing = self._delegates.get(call_id)
        if existing is not None and existing.proposal != retained:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_CALL_CONFLICT",
                "Provider call id cannot change its meaning",
            )
        if accepted:
            self._delegates[call_id] = _DelegateWait(retained, response.runtime_ref)
            self._delegate_count += 1
        self._state = NativeProviderState.DELEGATE_WAIT
        action = self._action(
            event.event_id,
            0,
            "DELEGATE",
            (("provider_call_id", call_id), ("turn_id", response.turn_id)),
        )
        return [NativeEngineEvent(action=action, delegate=retained)]

    def _response_done(
        self, event: OpenAIRealtimeEvent, data: dict[str, object]
    ) -> list[NativeEngineEvent]:
        provider_id, status, _ = _response_envelope(data["response"], done=True)
        response = self._require_response(provider_id)
        if status not in {"completed", "cancelled", "failed", "incomplete"}:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_RESPONSE_INVALID",
                "Provider response has an unsupported terminal status",
            )
        if response.cancelled:
            response.done = True
            self._state = (
                NativeProviderState.TURN_COMMITTED
                if self._pending_direct_response_turn_id is not None
                else NativeProviderState.READY
            )
            return []
        self._require_live_response_event(response)
        if response.runtime_ref is None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_RESPONSE_DONE_BEFORE_ADMISSION",
                "Provider completion requires Runtime response admission",
            )
        audio_events: list[NativeEngineEvent] = []
        partial_items = [
            audio_item
            for _, audio_item in sorted(response.audio_items.items())
            if audio_item.audio_buffer
        ]
        if (
            status in {"completed", "incomplete"}
            and len(partial_items) + 1 > self._event_queue_capacity
        ):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_ENGINE_EVENT_QUEUE_FULL",
                "Provider completion exceeds the bounded Native event queue",
            )
        if status in {"completed", "incomplete"}:
            for audio_item in partial_items:
                audio_events.extend(
                    self._flush_audio_buffer(response, audio_item, event.event_id)
                )
                audio_item.done = True
        for audio_item in response.audio_items.values():
            audio_item.audio_buffer.clear()
            audio_item.audio_buffer_event_id = None
        if len(audio_events) + 1 > self._event_queue_capacity:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_ENGINE_EVENT_QUEUE_FULL",
                "Provider completion exceeds the bounded Native event queue",
            )
        response.done = True
        transcript_items = [
            item
            for _, item in sorted(response.audio_items.items())
            if item.transcript is not None
        ]
        transcript = (
            " ".join(
                (item.transcript or "").replace("\n", " ")
                for item in transcript_items
            )
            if transcript_items
            else None
        )
        transcript_event_id = None
        if len(transcript_items) == 1:
            transcript_event_id = transcript_items[0].transcript_event_id
        elif transcript_items:
            # The terminal response event is the single Provider provenance
            # that covers the ordered output array represented by this text.
            transcript_event_id = event.event_id
        done = NativeProviderDone(
            provider_event_id=event.event_id,
            provider_response_id=provider_id,
            response=response.runtime_ref,
            completed=status == "completed",
            transcript=transcript,
            transcript_event_id=transcript_event_id,
        )
        self._state = NativeProviderState.READY
        return [*audio_events, NativeEngineEvent(provider_done=done)]

    def _action(
        self,
        provider_event_id: str,
        ordinal: int,
        operation: str,
        payload: tuple[tuple[str, str], ...],
    ) -> InteractionAction:
        action_id = _digest_id(
            "native-action",
            {
                "binding": self._binding.to_dict(),
                "provider_event_id": provider_event_id,
                "ordinal": ordinal,
                "operation": operation,
            },
        )
        candidate = InteractionAction(
            action_id=action_id,
            operation=operation,
            interaction_id=self._binding.interaction_id,
            scope=self._binding.scope,
            payload=payload,
        )
        try:
            _, retained = self._action_port.propose(candidate)
        except InteractionEngineViolation as exc:
            raise OpenAIRealtimeNativeInteractionError(exc.reason, str(exc)) from None
        return retained

    def _require_action_capacity(self, count: int) -> None:
        if len(self._action_port.accepted()) + count > _MAX_NATIVE_ACTIONS:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_ACTION_LEDGER_FULL",
                "bounded Native action ledger is full",
            )

    def _audio_event(
        self, buffered: _BufferedAudio, response: ResponseRef
    ) -> NativeEngineEvent:
        return NativeEngineEvent(
            audio=NativeAudioOutput(
                provider_event_id=buffered.provider_event_id,
                provider_response_id=buffered.provider_response_id,
                provider_item_id=buffered.provider_item_id,
                content_index=buffered.content_index,
                sequence=buffered.sequence,
                pcm16=buffered.pcm16,
                response=response,
                provider_sample_count=buffered.provider_sample_count,
            )
        )

    def _release_event(self, event: NativeEngineEvent) -> NativeEngineEvent:
        self._emitted_event_count += 1
        if event.audio is not None:
            self._released_audio_count += 1
        return event

    def _require_response(self, value: object) -> _ProviderResponse:
        provider_id = _identity(
            value,
            reason="NATIVE_PROVIDER_RESPONSE_INVALID",
            field_name="provider response id",
        )
        response = self._responses.get(provider_id)
        if response is None:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_PROVIDER_RESPONSE_MISMATCH",
                "Provider event does not match a proposed response",
            )
        return response

    def _current_response(self) -> _ProviderResponse | None:
        if self._current_response_id is None:
            return None
        return self._responses.get(self._current_response_id)

    def _require_live_response_event(self, response: _ProviderResponse) -> None:
        if response.done or response.cancelled:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_STALE_PROVIDER_RESPONSE_EVENT",
                "Provider authority event cannot follow response completion or cancel",
            )

    def _find_response(self, ref: ResponseRef) -> _ProviderResponse:
        matches = [
            response
            for response in self._responses.values()
            if response.runtime_ref == ref
        ]
        if len(matches) != 1:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_RESPONSE_ADMISSION_MISSING",
                "cancel requires one exact admitted response",
            )
        return matches[0]

    def _delegate_output_digest(self, value: object) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or any(
                unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
                for character in value
            )
        ):
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_RESULT_INVALID",
                "delegate result must be canonical bounded text",
            )
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            encoded = b"x" * (MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES + 1)
        if len(encoded) > MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_DELEGATE_RESULT_INVALID", "delegate result is oversized"
            )
        return hashlib.sha256(encoded).hexdigest()

    def _require_operational(self) -> None:
        if self._state in {
            NativeProviderState.NEW,
            NativeProviderState.STARTING,
            NativeProviderState.CLOSING,
            NativeProviderState.CLOSED,
            NativeProviderState.FAILED,
        }:
            raise OpenAIRealtimeNativeInteractionError(
                "NATIVE_ENGINE_STATE_INVALID",
                "Native engine operation is invalid in the current state",
            )

    def _mark_failed(self, reason: str) -> None:
        if self._primary_error_reason is None:
            self._primary_error_reason = reason
        self._state = NativeProviderState.FAILED
