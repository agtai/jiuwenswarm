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
    CONTRACT_VERSION,
    ContextRef,
    MAX_SAFE_INTEGER,
    ResponseRef,
    TerminalOutcome,
    TurnCommit,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.conversation_runtime import (
    InteractionState,
    ResponseState,
)
from jiuwenswarm.server.live_voice.conversation_runtime_loop import (
    ConversationRuntimeLoop,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    MAX_NATIVE_AUDIO_PROPOSAL_BATCH,
    MAX_NATIVE_TRANSCRIPT_UTF8_BYTES,
    NativeAudioObservation,
    NativeDelegateProposal,
    NativeInteractionBinding,
    NativePresentationCursor,
    NativeTurnCommit,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    MAX_NATIVE_AUDIO_DELTA_BYTES,
    MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES,
    NATIVE_PCM_SAMPLE_RATE,
    NativeAudioOutput,
    NativeProviderDone,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import (
    UnifiedCommittedInputRoute,
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
_MAX_NATIVE_RESPONSE_AUDIO_ITEMS = 64


class NativeInteractionRuntimeError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class NativeResponseAdmission:
    provider_response_id: str
    response: ResponseRef


@dataclass(frozen=True, slots=True)
class NativeAudioAdmission:
    accepted: bool
    unit: PresentationUnit


@dataclass(frozen=True, slots=True)
class NativeBargeAdmission:
    applied: bool
    response: ResponseRef
    cursor: NativePresentationCursor | None
    cancel_command_id: str


@dataclass(frozen=True, slots=True)
class NativeHistoryAdmission:
    response: ResponseRef
    transcript: str
    presented_at: str


@dataclass(frozen=True, slots=True)
class NativeDelegateAdmission:
    proposal: NativeDelegateProposal
    turn_commit: TurnCommit
    source_response: ResponseRef


@dataclass(frozen=True, slots=True)
class NativeDelegateResult:
    turn_commit: TurnCommit
    canonical_text: str
    route: UnifiedCommittedInputRoute
    response: ResponseRef


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
    audio_by_sequence: dict[int, NativeAudioObservation] = field(default_factory=dict)
    audio_units_by_sequence: dict[int, PresentationUnit] = field(default_factory=dict)
    audio_samples_by_item: dict[tuple[str, int], int] = field(default_factory=dict)
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
        owns_runtime: bool = True,
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
        if type(owns_runtime) is not bool:
            raise TypeError("owns_runtime must be boolean")
        self._binding = binding
        self._runtime = runtime
        self._owns_runtime = owns_runtime
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
        self._audio_event_ids: dict[tuple[str, int], NativeAudioObservation] = {}
        self._audio_event_responses: dict[str, str] = {}
        self._audio_admission_count = 0
        self._done_event_ids: dict[str, NativeProviderDone] = {}
        self._barges: dict[
            str,
            tuple[ResponseRef, NativePresentationCursor | None, NativeBargeAdmission],
        ] = {}
        self._delegates_by_call: dict[str, NativeDelegateAdmission] = {}
        self._delegate_event_calls: dict[str, str] = {}
        self._delegate_results: dict[str, NativeDelegateResult] = {}

    async def start(self) -> bool:
        async with self._lock:
            if self._closed:
                raise NativeInteractionRuntimeError(
                    "NATIVE_RUNTIME_CLOSED", "closed Native Runtime cannot restart"
                )
            if self._started:
                return False
            if self._owns_runtime:
                if not await self._runtime.start():
                    raise NativeInteractionRuntimeError(
                        "NATIVE_RUNTIME_UNAVAILABLE",
                        "Conversation Runtime did not accept Native start",
                    )
                await self._runtime.open_interaction(self._binding.interaction_id)
            else:
                snapshot = self._runtime.snapshot()
                interaction = next(
                    (
                        item
                        for item in snapshot.conversation.interactions
                        if item.interaction_id == self._binding.interaction_id
                    ),
                    None,
                )
                if (
                    not snapshot.started
                    or not snapshot.accepting
                    or snapshot.closed
                    or interaction is None
                    or interaction.state is not InteractionState.OPEN
                ):
                    raise NativeInteractionRuntimeError(
                        "NATIVE_RUNTIME_UNAVAILABLE",
                        "shared Conversation Runtime is not open for the Native binding",
                    )
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

    async def admit_delegate(
        self,
        proposal: NativeDelegateProposal,
        *,
        committed_at: str,
        context_refs: tuple[ContextRef, ...] = (),
    ) -> tuple[bool, NativeDelegateAdmission]:
        """Convert one exact Runtime-admitted proposal into standard input."""

        async with self._lock:
            self._require_open()
            if not isinstance(proposal, NativeDelegateProposal):
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_INVALID",
                    "delegate must use NativeDelegateProposal",
                )
            if proposal.binding != self._binding:
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_BINDING_MISMATCH",
                    "delegate must match the exact Native activation binding",
                )
            if type(context_refs) is not tuple or any(
                not isinstance(ref, ContextRef) for ref in context_refs
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_CONTEXT_INVALID",
                    "delegate context must contain canonical ContextRef values",
                )
            retained_response = self._current_response
            if (
                retained_response is None
                or retained_response.cancelled
                or retained_response.done is not None
                or proposal.turn_id != self._current_turn_id
                or proposal.turn_id not in self._turns_by_id
                or proposal.response_generation
                != retained_response.admission.response.response_generation
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_RESPONSE_STALE",
                    "delegate requires the exact current Native response generation",
                )
            prior = self._delegates_by_call.get(proposal.provider_call_id)
            prior_event_call = self._delegate_event_calls.get(
                proposal.provider_event_id
            )
            if prior is not None or prior_event_call is not None:
                if (
                    prior is not None
                    and prior.proposal == proposal
                    and prior_event_call == proposal.provider_call_id
                    and prior.turn_commit.context_refs == context_refs
                ):
                    return False, prior
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_CALL_CONFLICT",
                    "Provider delegate call or event cannot change meaning",
                )
            self._require_record_capacity(
                len(self._delegates_by_call), "NATIVE_DELEGATE_LEDGER_FULL"
            )
            identity = {
                "binding": proposal.binding.to_dict(),
                "native_turn_id": proposal.turn_id,
                "response_generation": proposal.response_generation,
                "provider_event_id": proposal.provider_event_id,
                "provider_call_id": proposal.provider_call_id,
                "provider_item_id": proposal.provider_item_id,
                "context_refs": [ref.to_dict() for ref in context_refs],
                "request_sha256": hashlib.sha256(
                    proposal.request_text.encode("utf-8")
                ).hexdigest(),
            }
            digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
            provenance = {
                "source": "openai_realtime_native_delegate",
                "contract_version": proposal.contract_version,
                "activation_id": self._binding.activation_id,
                "activation_generation": self._binding.activation_generation,
                "correlation_id": self._binding.correlation_id,
                "native_turn_id": proposal.turn_id,
                "provider_event_id": proposal.provider_event_id,
                "provider_call_id": proposal.provider_call_id,
                "provider_item_id": proposal.provider_item_id,
                "source_response_generation": proposal.response_generation,
            }
            try:
                turn_commit = TurnCommit.from_dict(
                    {
                        "contract_version": CONTRACT_VERSION,
                        "commit_id": f"native-delegate-commit-{digest}",
                        "turn_id": f"native-delegate-turn-{digest}",
                        "interaction_id": self._binding.interaction_id,
                        "text": proposal.request_text,
                        "hypothesis_provenance": provenance,
                        "scope": self._binding.scope.to_dict(),
                        "context_refs": [ref.to_dict() for ref in context_refs],
                        "committed_at": committed_at,
                    }
                )
            except Exception as exc:
                raise NativeInteractionRuntimeError(
                    getattr(exc, "reason", "NATIVE_DELEGATE_COMMIT_INVALID"),
                    "delegate could not form a standard TurnCommit",
                ) from exc
            admission = NativeDelegateAdmission(
                proposal=proposal,
                turn_commit=turn_commit,
                source_response=retained_response.admission.response,
            )
            self._delegates_by_call[proposal.provider_call_id] = admission
            self._delegate_event_calls[proposal.provider_event_id] = (
                proposal.provider_call_id
            )
            return True, admission

    async def accept_delegate_result(
        self,
        admission: NativeDelegateAdmission,
        *,
        canonical_text: str,
        route: UnifiedCommittedInputRoute,
    ) -> NativeDelegateResult:
        """Pre-admit the response generation used for a Jiuwen result."""

        async with self._lock:
            self._require_open()
            if not isinstance(admission, NativeDelegateAdmission):
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_ADMISSION_INVALID",
                    "delegate result requires one retained Runtime admission",
                )
            retained = self._delegates_by_call.get(admission.proposal.provider_call_id)
            if retained != admission:
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_ADMISSION_STALE",
                    "delegate result does not match retained Runtime authority",
                )
            text = self._delegate_result_text(canonical_text)
            if not isinstance(route, UnifiedCommittedInputRoute):
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_ROUTE_INVALID",
                    "delegate result must retain the unified committed-input route",
                )
            prior = self._delegate_results.get(admission.proposal.provider_call_id)
            if prior is not None:
                if (
                    prior.turn_commit == admission.turn_commit
                    and prior.canonical_text == text
                    and prior.route is route
                ):
                    return prior
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_RESULT_CONFLICT",
                    "delegate result cannot change its route or canonical text",
                )
            response_digest = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "provider_call_id": admission.proposal.provider_call_id,
                        "turn_commit_id": admission.turn_commit.commit_id,
                        "route": route.value,
                        "result_sha256": hashlib.sha256(
                            text.encode("utf-8")
                        ).hexdigest(),
                    }
                )
            ).hexdigest()
            response_id = f"native-delegate-response-{response_digest}"
            response, _event = await self._runtime.accept_response(
                admission.proposal.turn_id,
                response_id,
                history_policy=HistorySurfacePolicy.NATIVE_AUDIO,
                minimum_generation=admission.source_response.response_generation + 1,
            )
            await self._runtime.transition_response(response, ResponseState.GENERATING)
            result = NativeDelegateResult(
                turn_commit=admission.turn_commit,
                canonical_text=text,
                route=route,
                response=response,
            )
            self._delegate_results[admission.proposal.provider_call_id] = result
            return result

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
            self._retire_terminal_predecessor_audio_locked()
            admission = NativeResponseAdmission(provider_id, ref)
            retained = _RuntimeResponse(admission, self._current_turn_id)
            self._responses_by_provider[provider_id] = retained
            self._responses_by_ref[ref] = retained
            self._response_ids[runtime_response_id] = provider_id
            self._current_response = retained
            return admission

    async def bind_delegate_provider_response(
        self,
        provider_response_id: str,
        response: ResponseRef,
    ) -> NativeResponseAdmission:
        """Bind Provider's post-function response to its pre-admitted Runtime ref."""

        async with self._lock:
            self._require_open()
            provider_id = _identity(provider_response_id, "provider_response_id")
            if not isinstance(response, ResponseRef):
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_RESPONSE_INVALID",
                    "delegate Provider response requires a canonical ResponseRef",
                )
            result = next(
                (
                    retained
                    for retained in self._delegate_results.values()
                    if retained.response == response
                ),
                None,
            )
            if result is None:
                raise NativeInteractionRuntimeError(
                    "NATIVE_DELEGATE_RESPONSE_UNKNOWN",
                    "delegate Provider response was not pre-admitted by Runtime",
                )
            prior = self._responses_by_provider.get(provider_id)
            if prior is not None:
                if prior.admission.response == response:
                    return prior.admission
                raise NativeInteractionRuntimeError(
                    "NATIVE_PROVIDER_RESPONSE_CONFLICT",
                    "Provider response cannot change its Runtime response binding",
                )
            prior_provider = self._response_ids.get(response.response_id)
            if prior_provider is not None:
                raise NativeInteractionRuntimeError(
                    "NATIVE_RUNTIME_RESPONSE_ID_CONFLICT",
                    "Runtime response identity cannot bind another Provider response",
                )
            native_turn_id = _identity(
                result.turn_commit.hypothesis_provenance.get("native_turn_id"),
                "native_turn_id",
            )
            self._retire_terminal_predecessor_audio_locked()
            admission = NativeResponseAdmission(provider_id, response)
            retained_response = _RuntimeResponse(admission, native_turn_id)
            self._responses_by_provider[provider_id] = retained_response
            self._responses_by_ref[response] = retained_response
            self._response_ids[response.response_id] = provider_id
            self._current_response = retained_response
            return admission

    def _retire_terminal_predecessor_audio_locked(self) -> None:
        predecessor = self._current_response
        if predecessor is None or (
            predecessor.done is None and not predecessor.cancelled
        ):
            return
        retired_event_ids = {
            observation.provider_event_id
            for observation in predecessor.audio_by_sequence.values()
        }
        for observation in predecessor.audio_by_sequence.values():
            event_key = (observation.provider_event_id, observation.sequence)
            if self._audio_event_ids.get(event_key) == observation:
                self._audio_event_ids.pop(event_key, None)
        for event_id in retired_event_ids:
            if (
                self._audio_event_responses.get(event_id)
                == predecessor.admission.provider_response_id
            ):
                self._audio_event_responses.pop(event_id, None)
        predecessor.audio_by_sequence.clear()
        predecessor.audio_units_by_sequence.clear()
        predecessor.audio_samples_by_item.clear()

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
            self._validate_audio_output(output, retained)
            observation = NativeAudioObservation(
                provider_event_id=output.provider_event_id,
                provider_response_id=output.provider_response_id,
                provider_item_id=output.provider_item_id,
                content_index=output.content_index,
                sequence=output.sequence,
                sample_count=len(output.pcm16) // 2,
                content_sha256=hashlib.sha256(output.pcm16).hexdigest(),
                response=output.response,
            )
            accepted, _unit = await self._accept_audio_observation_locked(
                observation, retained
            )
            return accepted

    async def accept_audio_observation(
        self, observation: NativeAudioObservation
    ) -> NativeAudioAdmission | None:
        """Admit digest-only audio metadata and return Runtime media authority."""

        async with self._lock:
            self._require_open()
            if not isinstance(observation, NativeAudioObservation):
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_INVALID",
                    "audio observation must use NativeAudioObservation",
                )
            retained = self._responses_by_provider.get(observation.provider_response_id)
            if (
                retained is None
                or retained is not self._current_response
                or retained.admission.response != observation.response
                or retained.cancelled
                or retained.done is not None
            ):
                return None
            accepted, unit = await self._accept_audio_observation_locked(
                observation, retained
            )
            return NativeAudioAdmission(accepted=accepted, unit=unit)

    async def accept_audio_observations(
        self, observations: tuple[NativeAudioObservation, ...]
    ) -> tuple[NativeAudioAdmission, ...] | None:
        """Preflight and admit one bounded, ordered audio-only E2A batch."""

        async with self._lock:
            self._require_open()
            if (
                type(observations) is not tuple
                or not 0 < len(observations) <= MAX_NATIVE_AUDIO_PROPOSAL_BATCH
                or any(
                    not isinstance(observation, NativeAudioObservation)
                    for observation in observations
                )
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_BATCH_INVALID",
                    "audio batch must be a bounded tuple of observations",
                )
            first = observations[0]
            retained = self._responses_by_provider.get(first.provider_response_id)
            if (
                retained is None
                or retained is not self._current_response
                or retained.admission.response != first.response
                or retained.cancelled
                or retained.done is not None
            ):
                return None
            self._preflight_audio_observations_locked(observations, retained)
            admissions: list[NativeAudioAdmission] = []
            for observation in observations:
                accepted, unit = await self._accept_audio_observation_locked(
                    observation, retained
                )
                admissions.append(NativeAudioAdmission(accepted=accepted, unit=unit))
            return tuple(admissions)

    def _preflight_audio_observations_locked(
        self,
        observations: tuple[NativeAudioObservation, ...],
        retained: _RuntimeResponse,
    ) -> None:
        expected_input_sequence = observations[0].sequence
        simulated_next_sequence = retained.next_audio_sequence
        simulated_item_id = retained.provider_item_id
        simulated_content_index = retained.content_index
        simulated_items = set(retained.audio_samples_by_item)
        new_count = 0
        for observation in observations:
            self._validate_audio_observation(observation, retained)
            if (
                observation.provider_response_id
                != retained.admission.provider_response_id
                or observation.sequence != expected_input_sequence
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_SEQUENCE_GAP",
                    "Native audio batch must be contiguous for one response",
                )
            expected_input_sequence += 1
            prior_sequence = retained.audio_by_sequence.get(observation.sequence)
            event_key = (observation.provider_event_id, observation.sequence)
            prior_event = self._audio_event_ids.get(event_key)
            prior_event_response = self._audio_event_responses.get(
                observation.provider_event_id
            )
            if (
                prior_event_response is not None
                and prior_event_response != observation.provider_response_id
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_REPLAY_CONFLICT",
                    "Native Provider audio event cannot cross responses",
                )
            if prior_sequence is not None or prior_event is not None:
                if prior_sequence == observation and prior_event == observation:
                    continue
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_REPLAY_CONFLICT",
                    "Native audio sequence or Provider event cannot change meaning",
                )
            if observation.sequence != simulated_next_sequence:
                raise NativeInteractionRuntimeError(
                    "NATIVE_AUDIO_SEQUENCE_GAP",
                    "Native audio sequence must be contiguous",
                )
            incoming_item = (
                observation.provider_item_id,
                observation.content_index,
            )
            simulated_item = (
                None
                if simulated_item_id is None or simulated_content_index is None
                else (simulated_item_id, simulated_content_index)
            )
            if incoming_item != simulated_item:
                if incoming_item not in simulated_items:
                    if len(simulated_items) >= _MAX_NATIVE_RESPONSE_AUDIO_ITEMS:
                        raise NativeInteractionRuntimeError(
                            "NATIVE_AUDIO_ITEMS_FULL",
                            "Native response exceeds the bounded audio item count",
                        )
                    simulated_items.add(incoming_item)
            self._require_record_capacity(
                len(self._audio_event_ids) + new_count,
                "NATIVE_AUDIO_LEDGER_FULL",
            )
            simulated_item_id = observation.provider_item_id
            simulated_content_index = observation.content_index
            simulated_next_sequence += 1
            new_count += 1

    async def _accept_audio_observation_locked(
        self,
        observation: NativeAudioObservation,
        retained: _RuntimeResponse,
    ) -> tuple[bool, PresentationUnit]:
        self._validate_audio_observation(observation, retained)
        prior_sequence = retained.audio_by_sequence.get(observation.sequence)
        event_key = (observation.provider_event_id, observation.sequence)
        prior_event = self._audio_event_ids.get(event_key)
        prior_event_response = self._audio_event_responses.get(
            observation.provider_event_id
        )
        if (
            prior_event_response is not None
            and prior_event_response != observation.provider_response_id
        ):
            raise NativeInteractionRuntimeError(
                "NATIVE_AUDIO_REPLAY_CONFLICT",
                "Native Provider audio event cannot cross responses",
            )
        if prior_sequence is not None or prior_event is not None:
            if prior_sequence == observation and prior_event == observation:
                return False, retained.audio_units_by_sequence[observation.sequence]
            raise NativeInteractionRuntimeError(
                "NATIVE_AUDIO_REPLAY_CONFLICT",
                "Native audio sequence or Provider event cannot change meaning",
            )
        if observation.sequence != retained.next_audio_sequence:
            raise NativeInteractionRuntimeError(
                "NATIVE_AUDIO_SEQUENCE_GAP",
                "Native audio sequence must be contiguous",
            )
        incoming_item = (observation.provider_item_id, observation.content_index)
        current_item = (
            None
            if retained.provider_item_id is None or retained.content_index is None
            else (retained.provider_item_id, retained.content_index)
        )
        if incoming_item != current_item:
            if incoming_item not in retained.audio_samples_by_item:
                if (
                    len(retained.audio_samples_by_item)
                    >= _MAX_NATIVE_RESPONSE_AUDIO_ITEMS
                ):
                    raise NativeInteractionRuntimeError(
                        "NATIVE_AUDIO_ITEMS_FULL",
                        "Native response exceeds the bounded audio item count",
                    )
        self._require_record_capacity(
            len(self._audio_event_ids), "NATIVE_AUDIO_LEDGER_FULL"
        )
        # NATIVE_AUDIO has no source text.  Under that policy only, the
        # existing source span fields carry contiguous 24 kHz PCM samples.
        unit = PresentationUnit(
            ref=observation.response,
            surface=PresentationSurface.AUDIO,
            unit_id=self._audio_unit_id(observation),
            seq=observation.sequence,
            source_start_utf8=retained.next_sample_cursor,
            source_end_utf8=(retained.next_sample_cursor + observation.sample_count),
            content_ref=f"sha256:{observation.content_sha256}",
        )
        if not retained.speaking:
            await self._runtime.transition_response(
                observation.response, ResponseState.SPEAKING
            )
            retained.speaking = True
        await self._runtime.produce_unit(unit)
        accepted, effect = await self._runtime.enqueue_unit(
            observation.response, PresentationSurface.AUDIO, unit.unit_id
        )
        if not accepted or effect is None:
            raise NativeInteractionRuntimeError(
                "NATIVE_AUDIO_ENQUEUE_NOT_APPLIED",
                "new Native audio did not create one Runtime media effect",
            )
        retained.provider_item_id = observation.provider_item_id
        retained.content_index = observation.content_index
        retained.audio_by_sequence[observation.sequence] = observation
        retained.audio_units_by_sequence[observation.sequence] = unit
        retained.audio_samples_by_item[incoming_item] = (
            retained.audio_samples_by_item.get(incoming_item, 0)
            + observation.sample_count
        )
        self._audio_event_ids[event_key] = observation
        self._audio_event_responses[observation.provider_event_id] = (
            observation.provider_response_id
        )
        retained.next_audio_sequence += 1
        retained.next_sample_cursor += observation.sample_count
        self._audio_admission_count += 1
        return True, unit

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
            await self._reconcile_history_locked(retained)
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
            return await self._reconcile_history_locked(retained)

    async def history_admission(
        self, response: ResponseRef
    ) -> NativeHistoryAdmission | None:
        """Return the exact reconciled history fact without replaying Browser ACK."""

        async with self._lock:
            self._require_open()
            if not isinstance(response, ResponseRef):
                raise NativeInteractionRuntimeError(
                    "NATIVE_HISTORY_RESPONSE_INVALID",
                    "Native history lookup requires one exact ResponseRef",
                )
            retained = self._responses_by_ref.get(response)
            if retained is None or retained is not self._current_response:
                return None
            return retained.history

    async def _reconcile_history_locked(
        self, retained: _RuntimeResponse
    ) -> NativeHistoryAdmission | None:
        if retained.history is not None:
            return retained.history
        if (
            retained.cancelled
            or retained.done is None
            or not retained.done.completed
            or retained.done.transcript is None
        ):
            return None
        response = retained.admission.response
        if not await self._runtime.presentation_complete(
            response, PresentationSurface.AUDIO
        ):
            return None
        records = sorted(
            (
                record
                for record in self._runtime.snapshot().presentation.records
                if record.unit.ref == response
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
        admission = NativeHistoryAdmission(
            response,
            retained.done.transcript,
            presented_at,
        )
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
            cursor_item = (cursor.provider_item_id, cursor.content_index)
            received_samples = retained.audio_samples_by_item.get(cursor_item)
            if received_samples is None:
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_CURSOR_MISMATCH",
                    "barge-in cursor must match the exact Provider audio item",
                )
            received_ms = received_samples * 1_000 // NATIVE_PCM_SAMPLE_RATE
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

    async def fence_response(
        self,
        *,
        action_id: str,
        response: ResponseRef,
    ) -> NativeBargeAdmission:
        """Fence one exact response when Audio I/O has no played cursor."""

        async with self._lock:
            self._require_open()
            parsed_action_id = _identity(action_id, "action_id")
            if not isinstance(response, ResponseRef):
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_INPUT_INVALID",
                    "cursorless fence requires one exact ResponseRef",
                )
            prior = self._barges.get(parsed_action_id)
            if prior is not None:
                if prior[0] == response and prior[1] is None:
                    return prior[2]
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_ACTION_CONFLICT",
                    "barge action cannot change response or cursor policy",
                )
            retained = self._responses_by_ref.get(response)
            if (
                retained is None
                or retained is not self._current_response
                or retained.cancelled
                or retained.done is not None
            ):
                raise NativeInteractionRuntimeError(
                    "NATIVE_BARGE_RESPONSE_STALE",
                    "cursorless fence requires the exact current active response",
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
                cursor=None,
                cancel_command_id=parsed_action_id,
            )
            self._barges[parsed_action_id] = (response, None, admission)
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
            if self._owns_runtime:
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
            audio_count=self._audio_admission_count,
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

    def _validate_audio_output(
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

    def _validate_audio_observation(
        self, observation: NativeAudioObservation, retained: _RuntimeResponse
    ) -> None:
        if observation.response != retained.admission.response:
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
    def _delegate_result_text(value: object) -> str:
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
                "NATIVE_DELEGATE_RESULT_INVALID",
                "delegate result must be canonical bounded text",
            )
        try:
            length = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            length = MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES + 1
        if length > MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES:
            raise NativeInteractionRuntimeError(
                "NATIVE_DELEGATE_RESULT_INVALID",
                "delegate result is oversized",
            )
        return value

    @staticmethod
    def _audio_unit_id(output: NativeAudioOutput | NativeAudioObservation) -> str:
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
    "NativeAudioAdmission",
    "NativeBargeAdmission",
    "NativeHistoryAdmission",
    "NativeInteractionRuntimeError",
    "NativeInteractionRuntimeOwner",
    "NativeInteractionRuntimeSnapshot",
    "NativeResponseAdmission",
]
