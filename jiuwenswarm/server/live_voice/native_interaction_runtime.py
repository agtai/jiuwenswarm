# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Conversation Runtime authority owner for Native Realtime proposals.

Provider observations remain authority-free until this owner binds them to the
exact Runtime interaction, turn, response generation, presentation ledger, and
cancel fence.  The owner yields history eligibility but never writes history.
"""

from __future__ import annotations

import asyncio
import hashlib
import unicodedata
from dataclasses import dataclass, field

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    ResponseRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.conversation_runtime import (
    InteractionState,
    ResponseState,
)
from jiuwenswarm.server.live_voice.conversation_runtime_loop import (
    ConversationRuntimeLoop,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    MAX_NATIVE_TRANSCRIPT_UTF8_BYTES,
    NativeInteractionBinding,
    NativePresentationCursor,
    NativeTurnCommit,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    MAX_NATIVE_AUDIO_DELTA_BYTES,
    NATIVE_PCM_SAMPLE_RATE,
    NativeAudioOutput,
    NativeProviderDone,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    HistorySurfacePolicy,
    PresentationAck,
    PresentationState,
    PresentationSurface,
    PresentationUnit,
)


_MAX_IDENTITY_CHARS = 256
_MAX_IDENTITY_UTF8_BYTES = 1_024
_MAX_NATIVE_RUNTIME_RECORDS = 4_096


class NativeInteractionRuntimeError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class NativeResponseAdmission:
    provider_response_id: str
    response: ResponseRef


@dataclass(frozen=True, slots=True)
class NativeBargeAdmission:
    applied: bool
    response: ResponseRef
    cursor: NativePresentationCursor
    cancel_command_id: str


@dataclass(frozen=True, slots=True)
class NativeHistoryAdmission:
    response: ResponseRef
    transcript: str
    presented_at: str


@dataclass(frozen=True, slots=True)
class NativeInteractionRuntimeSnapshot:
    started: bool
    closed: bool
    current_response: ResponseRef | None
    turn_count: int
    response_count: int
    audio_count: int
    done_count: int
    history_count: int
    barge_count: int


@dataclass(slots=True)
class _RuntimeResponse:
    admission: NativeResponseAdmission
    turn_id: str
    next_audio_sequence: int = 0
    next_sample_cursor: int = 0
    provider_item_id: str | None = None
    content_index: int | None = None
    audio_by_sequence: dict[int, NativeAudioOutput] = field(default_factory=dict)
    speaking: bool = False
    done: NativeProviderDone | None = None
    cancelled: bool = False
    history: NativeHistoryAdmission | None = None


def _identity(value: object, field_name: str) -> str:
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
        raise NativeInteractionRuntimeError(
            "NATIVE_RUNTIME_IDENTITY_INVALID",
            f"{field_name} must be a bounded canonical identity",
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        encoded = b"x" * (_MAX_IDENTITY_UTF8_BYTES + 1)
    if len(encoded) > _MAX_IDENTITY_UTF8_BYTES:
        raise NativeInteractionRuntimeError(
            "NATIVE_RUNTIME_IDENTITY_INVALID",
            f"{field_name} must be a bounded canonical identity",
        )
    return value


def _transcript(value: object) -> str | None:
    if value is None:
        return None
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        raise NativeInteractionRuntimeError(
            "NATIVE_TRANSCRIPT_INVALID",
            "Native assistant transcript must be canonical text",
        )
    try:
        length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        length = MAX_NATIVE_TRANSCRIPT_UTF8_BYTES + 1
    if length > MAX_NATIVE_TRANSCRIPT_UTF8_BYTES:
        raise NativeInteractionRuntimeError(
            "NATIVE_TRANSCRIPT_INVALID", "Native assistant transcript is oversized"
        )
    return value


class NativeInteractionRuntimeOwner:
    """The only adapter allowed to turn Native proposals into Runtime writes."""

    def __init__(
        self,
        binding: NativeInteractionBinding,
        *,
        runtime: ConversationRuntimeLoop,
    ) -> None:
        if not isinstance(binding, NativeInteractionBinding):
            raise TypeError("binding must use NativeInteractionBinding")
        if not isinstance(runtime, ConversationRuntimeLoop):
            raise TypeError("runtime must use ConversationRuntimeLoop")
        if runtime.snapshot().conversation.scope != binding.scope:
            raise NativeInteractionRuntimeError(
                "NATIVE_RUNTIME_SCOPE_MISMATCH",
                "Runtime scope must match the exact Native activation binding",
            )
        self._binding = binding
        self._runtime = runtime
        self._lock = asyncio.Lock()
        self._started = False
        self._closed = False
        self._turns_by_id: dict[str, NativeTurnCommit] = {}
        self._turns_by_commit: dict[str, NativeTurnCommit] = {}
        self._current_turn_id: str | None = None
        self._responses_by_provider: dict[str, _RuntimeResponse] = {}
        self._responses_by_ref: dict[ResponseRef, _RuntimeResponse] = {}
        self._response_ids: dict[str, str] = {}
        self._current_response: _RuntimeResponse | None = None
        self._audio_event_ids: dict[str, NativeAudioOutput] = {}
        self._done_event_ids: dict[str, NativeProviderDone] = {}
        self._barges: dict[
            str, tuple[ResponseRef, NativePresentationCursor, NativeBargeAdmission]
        ] = {}

    async def start(self) -> bool:
        async with self._lock:
            if self._closed:
                raise NativeInteractionRuntimeError(
                    "NATIVE_RUNTIME_CLOSED", "closed Native Runtime cannot restart"
                )
            if self._started:
                return False
            if not await self._runtime.start():
                raise NativeInteractionRuntimeError(
                    "NATIVE_RUNTIME_UNAVAILABLE",
                    "Conversation Runtime did not accept Native start",
                )
            await self._runtime.open_interaction(self._binding.interaction_id)
            self._started = True
            return True

    async def accept_turn(self, commit: NativeTurnCommit) -> bool:
        async with self._lock:
            self._require_open()
            if not isinstance(commit, NativeTurnCommit):
                raise NativeInteractionRuntimeError(
                    "NATIVE_TURN_COMMIT_INVALID",
                    "Native turn must use NativeTurnCommit",
                )
            if commit.binding != self._binding:
                raise NativeInteractionRuntimeError(
                    "NATIVE_TURN_BINDING_MISMATCH",
                    "Native turn must match the exact activation binding",
                )
            prior_turn = self._turns_by_id.get(commit.turn_id)
            prior_commit = self._turns_by_commit.get(commit.commit_id)
            if prior_turn is not None or prior_commit is not None:
                if prior_turn == commit and prior_commit == commit:
                    return False
                raise NativeInteractionRuntimeError(
                    "NATIVE_TURN_COMMIT_CONFLICT",
                    "Native turn or commit identity cannot change its meaning",
                )
            self._require_record_capacity(
                len(self._turns_by_id), "NATIVE_TURN_LEDGER_FULL"
            )
            await self._runtime.start_turn(self._binding.interaction_id, commit.turn_id)
            accepted, _ = await self._runtime.commit_native_turn(commit)
            if not accepted:
                raise NativeInteractionRuntimeError(
                    "NATIVE_TURN_COMMIT_NOT_APPLIED",
                    "new Native turn commit was not applied",
                )
            self._turns_by_id[commit.turn_id] = commit
            self._turns_by_commit[commit.commit_id] = commit
            self._current_turn_id = commit.turn_id
            return True

    async def accept_provider_response(
        self, provider_response_id: str, response_id: str
    ) -> NativeResponseAdmission:
        async with self._lock:
            self._require_open()
            provider_id = _identity(provider_response_id, "provider_response_id")
            runtime_response_id = _identity(response_id, "response_id")
            if self._current_turn_id is None:
                raise NativeInteractionRuntimeError(
                    "NATIVE_RESPONSE_BEFORE_TURN",
                    "Native response requires one accepted turn",
                )
            prior = self._responses_by_provider.get(provider_id)
            if prior is not None:
                if prior.admission.response.response_id == runtime_response_id:
                    return prior.admission
                raise NativeInteractionRuntimeError(
                    "NATIVE_PROVIDER_RESPONSE_CONFLICT",
                    "Provider response cannot change its Runtime response binding",
                )
            prior_provider = self._response_ids.get(runtime_response_id)
            if prior_provider is not None:
                raise NativeInteractionRuntimeError(
                    "NATIVE_RUNTIME_RESPONSE_ID_CONFLICT",
                    "Runtime response identity cannot bind another Provider response",
                )
            self._require_record_capacity(
                len(self._responses_by_provider), "NATIVE_RESPONSE_LEDGER_FULL"
            )
            ref, _ = await self._runtime.accept_response(
                self._current_turn_id,
                runtime_response_id,
                history_policy=HistorySurfacePolicy.NATIVE_AUDIO,
                minimum_generation=1,
            )
            await self._runtime.transition_response(ref, ResponseState.GENERATING)
            admission = NativeResponseAdmission(provider_id, ref)
            retained = _RuntimeResponse(admission, self._current_turn_id)
            self._responses_by_provider[provider_id] = retained
            self._responses_by_ref[ref] = retained
            self._response_ids[runtime_response_id] = provider_id
            self._current_response = retained
            return admission

    async def accept_audio(self, output: NativeAudioOutput) -> bool:
        async with self._lock:
            self._require_open()
            if not isinstance(output, NativeAudioOutput):
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_INVALID", "audio must use NativeAudioOutput"
                )
            retained = self._responses_by_provider.get(output.provider_response_id)
            if (
                retained is None
                or retained is not self._current_response
                or retained.admission.response != output.response
                or retained.cancelled
                or retained.done is not None
            ):
                return False
            self._validate_audio(output, retained)
            prior_sequence = retained.audio_by_sequence.get(output.sequence)
            prior_event = self._audio_event_ids.get(output.provider_event_id)
            if prior_sequence is not None or prior_event is not None:
                if prior_sequence == output and prior_event == output:
                    return False
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_REPLAY_CONFLICT",
                    "Native audio sequence or Provider event cannot change meaning",
                )
            if output.sequence != retained.next_audio_sequence:
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_SEQUENCE_GAP",
                    "Native audio sequence must be contiguous",
                )
            if retained.provider_item_id is not None and (
                retained.provider_item_id != output.provider_item_id
                or retained.content_index != output.content_index
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_ITEM_MISMATCH",
                    "Native audio must keep one Provider item and content index",
                )
            self._require_record_capacity(
                len(self._audio_event_ids), "NATIVE_AUDIO_LEDGER_FULL"
            )
            sample_count = len(output.pcm16) // 2
            # NATIVE_AUDIO has no source text.  Under that policy only, the
            # existing source span fields carry contiguous 24 kHz PCM samples.
            unit = PresentationUnit(
                ref=output.response,
                surface=PresentationSurface.AUDIO,
                unit_id=self._audio_unit_id(output),
                seq=output.sequence,
                source_start_utf8=retained.next_sample_cursor,
                source_end_utf8=retained.next_sample_cursor + sample_count,
                content_ref=f"sha256:{hashlib.sha256(output.pcm16).hexdigest()}",
            )
            if not retained.speaking:
                await self._runtime.transition_response(
                    output.response, ResponseState.SPEAKING
                )
                retained.speaking = True
            await self._runtime.produce_unit(unit)
            accepted, effect = await self._runtime.enqueue_unit(
                output.response, PresentationSurface.AUDIO, unit.unit_id
            )
            if not accepted or effect is None:
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_ENQUEUE_NOT_APPLIED",
                    "new Native audio did not create one Runtime media effect",
                )
            retained.provider_item_id = output.provider_item_id
            retained.content_index = output.content_index
            retained.audio_by_sequence[output.sequence] = output
            self._audio_event_ids[output.provider_event_id] = output
            retained.next_audio_sequence += 1
            retained.next_sample_cursor += sample_count
            return True

    async def accept_provider_done(self, observation: NativeProviderDone) -> bool:
        async with self._lock:
            self._require_open()
            if not isinstance(observation, NativeProviderDone):
                raise NativeInteractionRuntimeError(
                    "NATIVE_PROVIDER_DONE_INVALID",
                    "Provider completion must use NativeProviderDone",
                )
            retained = self._responses_by_provider.get(observation.provider_response_id)
            if (
                retained is None
                or retained is not self._current_response
                or retained.admission.response != observation.response
                or retained.cancelled
            ):
                return False
            self._validate_done(observation)
            prior_event = self._done_event_ids.get(observation.provider_event_id)
            if retained.done is not None or prior_event is not None:
                if retained.done == observation and prior_event == observation:
                    return False
                raise NativeInteractionRuntimeError(
                    "NATIVE_PROVIDER_DONE_CONFLICT",
                    "Provider completion cannot change its retained meaning",
                )
            await self._runtime.seal_presentation(
                observation.response,
                PresentationSurface.AUDIO,
                unit_count=retained.next_audio_sequence,
            )
            await self._runtime.transition_response(
                observation.response,
                ResponseState.TERMINAL,
                outcome=(
                    TerminalOutcome.COMPLETED
                    if observation.completed
                    else TerminalOutcome.FAILED
                ),
            )
            retained.done = observation
            self._done_event_ids[observation.provider_event_id] = observation
            return True

    async def acknowledge_audio(
        self, ack: PresentationAck
    ) -> NativeHistoryAdmission | None:
        async with self._lock:
            self._require_open()
            if (
                not isinstance(ack, PresentationAck)
                or ack.surface is not PresentationSurface.AUDIO
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_ACK_INVALID",
                    "Native acknowledgement must target the audio surface",
                )
            retained = self._responses_by_ref.get(ack.ref)
            if (
                retained is None
                or retained is not self._current_response
                or retained.cancelled
            ):
                return None
            if retained.history is not None:
                await self._runtime.acknowledge_presentation(ack)
                return retained.history
            await self._runtime.acknowledge_presentation(ack)
            if retained.done is None or not retained.done.completed:
                return None
            if not await self._runtime.presentation_complete(
                ack.ref, PresentationSurface.AUDIO
            ):
                return None
            transcript = retained.done.transcript
            if transcript is None:
                return None
            records = sorted(
                (
                    record
                    for record in self._runtime.snapshot().presentation.records
                    if record.unit.ref == ack.ref
                    and record.unit.surface is PresentationSurface.AUDIO
                ),
                key=lambda record: record.unit.seq,
            )
            if not records or any(
                record.state is not PresentationState.PRESENTED for record in records
            ):
                return None
            presented_at = records[-1].presented_at
            assert presented_at is not None
            admission = NativeHistoryAdmission(ack.ref, transcript, presented_at)
            retained.history = admission
            return admission

    async def barge_in(
        self,
        *,
        action_id: str,
        response: ResponseRef,
        cursor: NativePresentationCursor,
    ) -> NativeBargeAdmission:
        async with self._lock:
            self._require_open()
            parsed_action_id = _identity(action_id, "action_id")
            if not isinstance(response, ResponseRef) or not isinstance(
                cursor, NativePresentationCursor
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_INPUT_INVALID",
                    "barge-in requires ResponseRef and NativePresentationCursor",
                )
            prior = self._barges.get(parsed_action_id)
            if prior is not None:
                if prior[0] == response and prior[1] == cursor:
                    return prior[2]
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_ACTION_CONFLICT",
                    "barge action cannot change response or played cursor",
                )
            retained = self._responses_by_ref.get(response)
            if (
                retained is None
                or retained is not self._current_response
                or cursor.response != response
                or retained.cancelled
                or retained.done is not None
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_RESPONSE_STALE",
                    "barge-in requires the exact current active response",
                )
            if (
                retained.provider_item_id != cursor.provider_item_id
                or retained.content_index != cursor.content_index
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_CURSOR_MISMATCH",
                    "barge-in cursor must match the exact Provider audio item",
                )
            received_ms = retained.next_sample_cursor * 1_000 // NATIVE_PCM_SAMPLE_RATE
            if cursor.audio_end_ms > received_ms:
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_CURSOR_AHEAD",
                    "played cursor cannot exceed received Native audio",
                )
            result = await self._runtime.barge_in(
                parsed_action_id, response, cancel_response=True
            )
            effects = {
                record.effect.effect_id: record.effect
                for record in self._runtime.snapshot().effects
            }
            applied = any(
                effects[effect_id].effect_type == "response.cancel"
                for effect_id in result.effect_ids
            )
            admission = NativeBargeAdmission(
                applied=applied,
                response=response,
                cursor=cursor,
                cancel_command_id=parsed_action_id,
            )
            self._barges[parsed_action_id] = (response, cursor, admission)
            if applied:
                retained.cancelled = True
            return admission

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            if self._started:
                snapshot = self._runtime.snapshot().conversation
                interaction = next(
                    (
                        item
                        for item in snapshot.interactions
                        if item.interaction_id == self._binding.interaction_id
                    ),
                    None,
                )
                if (
                    interaction is not None
                    and interaction.state is InteractionState.OPEN
                ):
                    await self._runtime.transition_interaction(
                        self._binding.interaction_id, InteractionState.CLOSING
                    )
                    await self._runtime.transition_interaction(
                        self._binding.interaction_id, InteractionState.CLOSED
                    )
            await self._runtime.close()
            self._closed = True

    def snapshot(self) -> NativeInteractionRuntimeSnapshot:
        return NativeInteractionRuntimeSnapshot(
            started=self._started,
            closed=self._closed,
            current_response=(
                None
                if self._current_response is None
                else self._current_response.admission.response
            ),
            turn_count=len(self._turns_by_id),
            response_count=len(self._responses_by_provider),
            audio_count=sum(
                len(response.audio_by_sequence)
                for response in self._responses_by_provider.values()
            ),
            done_count=sum(
                response.done is not None
                for response in self._responses_by_provider.values()
            ),
            history_count=sum(
                response.history is not None
                for response in self._responses_by_provider.values()
            ),
            barge_count=len(self._barges),
        )

    def _validate_audio(
        self, output: NativeAudioOutput, retained: _RuntimeResponse
    ) -> None:
        _identity(output.provider_event_id, "provider_event_id")
        _identity(output.provider_response_id, "provider_response_id")
        _identity(output.provider_item_id, "provider_item_id")
        if (
            type(output.content_index) is not int
            or not 0 <= output.content_index <= MAX_SAFE_INTEGER
            or type(output.sequence) is not int
            or not 0 <= output.sequence <= MAX_SAFE_INTEGER
            or type(output.pcm16) is not bytes
            or not output.pcm16
            or len(output.pcm16) % 2
            or len(output.pcm16) > MAX_NATIVE_AUDIO_DELTA_BYTES
        ):
            raise NativeInteractionRuntimeError(
                "NATIVE_AUDIO_INVALID",
                "Native audio fields must be bounded PCM16 and safe cursors",
            )
        if output.response != retained.admission.response:
            raise NativeInteractionRuntimeError(
                "NATIVE_AUDIO_RESPONSE_MISMATCH",
                "Native audio must match the exact Runtime response tuple",
            )

    def _validate_done(self, observation: NativeProviderDone) -> None:
        _identity(observation.provider_event_id, "provider_event_id")
        _identity(observation.provider_response_id, "provider_response_id")
        if type(observation.completed) is not bool:
            raise NativeInteractionRuntimeError(
                "NATIVE_PROVIDER_DONE_INVALID",
                "Provider completion fact must be boolean",
            )
        transcript = _transcript(observation.transcript)
        provenance = observation.transcript_event_id
        if (transcript is None) != (provenance is None):
            raise NativeInteractionRuntimeError(
                "NATIVE_TRANSCRIPT_PROVENANCE_INVALID",
                "transcript and Provider provenance must be both absent or present",
            )
        if provenance is not None:
            _identity(provenance, "transcript_event_id")

    @staticmethod
    def _audio_unit_id(output: NativeAudioOutput) -> str:
        digest = hashlib.sha256(
            (
                f"{output.response.interaction_id}\0{output.response.response_id}\0"
                f"{output.response.response_generation}\0{output.provider_event_id}\0"
                f"{output.sequence}"
            ).encode("utf-8")
        ).hexdigest()
        return f"native-audio:{digest}"

    def _require_open(self) -> None:
        if not self._started or self._closed:
            raise NativeInteractionRuntimeError(
                "NATIVE_RUNTIME_NOT_OPEN",
                "Native Runtime operation requires an open owner",
            )

    @staticmethod
    def _require_record_capacity(count: int, reason: str) -> None:
        if count >= _MAX_NATIVE_RUNTIME_RECORDS:
            raise NativeInteractionRuntimeError(
                reason, "bounded Native Runtime ledger is full"
            )


__all__ = [
    "NativeBargeAdmission",
    "NativeHistoryAdmission",
    "NativeInteractionRuntimeError",
    "NativeInteractionRuntimeOwner",
    "NativeInteractionRuntimeSnapshot",
    "NativeResponseAdmission",
]
