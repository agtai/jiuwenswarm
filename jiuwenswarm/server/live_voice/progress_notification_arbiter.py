# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded WorkProgress notification arbitration for Conversation Runtime.

This module selects notification delivery candidates.  It deliberately has no UI,
audio, TTS, lifecycle, timer, network, or persistence effect port.  A caller must
acknowledge a successfully consumed candidate; an observer failure therefore leaves
the exact pending item available for a later drain.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CONTRACT_VERSION,
    ContractViolation,
    ErrorCode,
    EventEnvelope,
    IdentityKind,
    IdentityRef,
    ProducerRef,
    ScopeRef,
    Speakability,
    TerminalOutcome,
    WorkProgressEventV2,
    WorkSourceAuthority,
    WorkState,
    canonical_json_bytes,
)

from .formal_task_models import PersistentTaskEvent


class ProgressNotificationArbiterViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class ForegroundFact(StrEnum):
    SAFE = "safe"
    BUSY = "busy"
    UNKNOWN = "unknown"


class SpeechPolicy(StrEnum):
    ALLOW_CANDIDATE = "allow_candidate"
    DISPLAY_ONLY = "display_only"
    UNKNOWN = "unknown"


class NotificationDisposition(StrEnum):
    DISPLAY_NOW = "display_now"
    DEFERRED = "deferred"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    BACKPRESSURE = "backpressure"
    FEATURE_DISABLED = "feature_disabled"


class SpeechDisposition(StrEnum):
    NOT_A_CANDIDATE = "not_a_candidate"
    SPEAK_WHEN_SAFE_CANDIDATE = "speak_when_safe_candidate"


class NoProjectionAdvanceDisposition(StrEnum):
    ADVANCED = "advanced"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    BACKPRESSURE = "backpressure"
    FEATURE_DISABLED = "feature_disabled"


@dataclass(frozen=True, slots=True)
class ForegroundSnapshot:
    """Facts supplied by the current interaction/presentation owners.

    ``UNKNOWN`` never proves that interruption or speech is safe.  These values are
    observations only; the arbiter does not read or mutate Conversation Runtime.
    """

    interaction: ForegroundFact
    response: ForegroundFact
    presentation: ForegroundFact
    speech_policy: SpeechPolicy = SpeechPolicy.UNKNOWN


@dataclass(frozen=True, slots=True)
class ProgressNotificationBinding:
    """Authenticated product binding expected for one source-backed projection."""

    scope: ScopeRef
    work_ref: IdentityRef
    correlation_id: str
    source_producer: ProducerRef
    source_work_ref: IdentityRef
    source_authority: WorkSourceAuthority
    progress_producer: ProducerRef
    progress_adapter: str | None


_NO_PROJECTION_ADVANCE_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class _VerifiedNoProjectionAdvance:
    """Package-internal capability for one authority-verified source position."""

    source_event: PersistentTaskEvent
    binding: ProgressNotificationBinding

    def __init__(
        self,
        source_event: PersistentTaskEvent,
        binding: ProgressNotificationBinding,
        *,
        _token: object,
    ) -> None:
        if _token is not _NO_PROJECTION_ADVANCE_TOKEN:
            raise ProgressNotificationArbiterViolation(
                "INVALID_NO_PROJECTION_CAPABILITY",
                "no-projection capability must be minted by its package owner",
                ErrorCode.PERMISSION_DENIED,
            )
        object.__setattr__(self, "source_event", source_event)
        object.__setattr__(self, "binding", binding)


def _mint_verified_no_projection_advance(
    source_event: PersistentTaskEvent,
    binding: ProgressNotificationBinding,
) -> _VerifiedNoProjectionAdvance:
    """Mint an internal capability after the owning bridge checks its lease."""

    return _VerifiedNoProjectionAdvance(
        source_event,
        binding,
        _token=_NO_PROJECTION_ADVANCE_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class NoProjectionAdvanceDecision:
    disposition: NoProjectionAdvanceDisposition
    reason: str
    code: ErrorCode | None = None
    source_event_id: str | None = None
    source_seq: int | None = None


@dataclass(frozen=True, slots=True)
class NotificationDecision:
    disposition: NotificationDisposition
    speech: SpeechDisposition
    reason: str
    code: ErrorCode | None = None
    scope: ScopeRef | None = None
    work_ref: IdentityRef | None = None
    event_id: str | None = None
    source_event_id: str | None = None
    projection_seq: int | None = None
    state: WorkState | None = None
    outcome: TerminalOutcome | None = None
    retained_event_id: str | None = None
    progress: WorkProgressEventV2 | None = None


@dataclass(frozen=True, slots=True)
class ProgressNotificationArbiterSnapshot:
    enabled: bool
    tracked_work_streams: int
    tracked_source_streams: int
    tracked_progress_streams: int
    retained_source_events: int
    retained_progress_events: int
    pending_notifications: int
    terminal_work_streams: int
    accepted_events: int
    coalesced_events: int
    duplicate_events: int
    rejected_events: int
    backpressure_events: int
    no_projection_advances: int
    no_projection_duplicates: int


@dataclass(slots=True)
class _SequenceState:
    next_seq: int
    fingerprints: dict[int, bytes]


@dataclass(slots=True)
class _WorkState:
    sequence: _SequenceState
    last_state: WorkState | None = None
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class _PendingNotification:
    source_event: EventEnvelope
    progress_event: EventEnvelope
    progress: WorkProgressEventV2


class _InputRejected(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


_SourceStreamKey = tuple[str, str, IdentityKind, str]
_ProgressStreamKey = tuple[str, str, IdentityKind, str]
_WorkKey = tuple[ScopeRef, IdentityKind, str]
_NO_PROJECTION_EVENT_TYPES = frozenset(
    {
        "attempt.accepted",
        "attempt.running",
        "attempt.terminal",
        "task.cancel_requested",
    }
)
_NO_PROJECTION_SOURCE_DOMAIN = b"live-voice.no-projection.source.v1\0"
_NO_PROJECTION_PROGRESS_DOMAIN = b"live-voice.no-projection.progress.v1\0"
_NO_PROJECTION_WORK_DOMAIN = b"live-voice.no-projection.work.v1\0"
_NO_PROJECTION_OBSERVATION_DOMAIN = b"live-voice.no-projection.observation.v1\0"


class ProgressNotificationArbiter:
    """Synchronous, memory-only CR-C progress notification arbiter."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        pending_capacity: int = 64,
        stream_capacity: int = 128,
        events_per_stream: int = 256,
    ) -> None:
        if type(enabled) is not bool:
            raise ProgressNotificationArbiterViolation(
                "INVALID_FEATURE_FLAG",
                "enabled must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        for name, value in (
            ("pending_capacity", pending_capacity),
            ("stream_capacity", stream_capacity),
            ("events_per_stream", events_per_stream),
        ):
            if type(value) is not int or value <= 0:
                raise ProgressNotificationArbiterViolation(
                    "INVALID_ARBITER_CAPACITY",
                    f"{name} must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
        self._enabled = enabled
        self._pending_capacity = pending_capacity
        self._stream_capacity = stream_capacity
        self._events_per_stream = events_per_stream
        self._observation_capacity = (
            stream_capacity * events_per_stream + pending_capacity
        )
        self._lock = RLock()
        self._source_streams: dict[_SourceStreamKey, _SequenceState] = {}
        self._progress_streams: dict[_ProgressStreamKey, _SequenceState] = {}
        self._work_streams: dict[_WorkKey, _WorkState] = {}
        self._observed_source_fingerprints: dict[str, bytes] = {}
        self._observed_progress_fingerprints: dict[str, bytes] = {}
        self._observed_source_to_progress: dict[str, str] = {}
        self._observed_progress_to_source: dict[str, str] = {}
        self._observed_no_projection_fingerprints: dict[str, bytes] = {}
        self._decisions: dict[str, NotificationDecision] = {}
        self._pending: dict[_WorkKey, _PendingNotification] = {}
        self._accepted_events = 0
        self._coalesced_events = 0
        self._duplicate_events = 0
        self._rejected_events = 0
        self._backpressure_events = 0
        self._no_projection_advances = 0
        self._no_projection_duplicates = 0

    def offer(
        self,
        source_event: object,
        progress_event: object,
        foreground: object,
        binding: object,
    ) -> NotificationDecision:
        """Offer one source event and its exact WorkProgress projection.

        The method never waits.  Feature-off returns before inspecting any input.
        Rejected and backpressured events do not advance any sequence or lifecycle
        state and may be retried only with their original identities.
        """

        if not self._enabled:
            return NotificationDecision(
                disposition=NotificationDisposition.FEATURE_DISABLED,
                speech=SpeechDisposition.NOT_A_CANDIDATE,
                reason="feature_disabled",
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        with self._lock:
            return self._offer_locked(source_event, progress_event, foreground, binding)

    def _advance_without_projection(
        self,
        advance: object,
    ) -> NoProjectionAdvanceDecision:
        """Package-internally record an authority-verified source position.

        No pending notification, delivery decision, work lifecycle transition, or
        acknowledgement candidate is created.  Feature-off returns before
        inspecting the capability.
        """

        if not self._enabled:
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.FEATURE_DISABLED,
                "feature_disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        with self._lock:
            return self._advance_without_projection_locked(advance)

    def _advance_without_projection_locked(
        self,
        advance: object,
    ) -> NoProjectionAdvanceDecision:
        try:
            event, expected, source_bytes = self._validate_no_projection_advance(
                advance
            )
            evidence_bytes = canonical_json_bytes(
                {
                    "scope": expected.scope.to_dict(),
                    "work_ref": expected.work_ref.to_dict(),
                    "correlation_id": expected.correlation_id,
                    "source_event_id": event.event_id,
                    "source_event_type": event.event_type,
                    "source_seq": event.seq,
                    "source_producer": expected.source_producer.to_dict(),
                    "source_work_ref": expected.source_work_ref.to_dict(),
                    "source_authority": expected.source_authority.value,
                    "progress_producer": expected.progress_producer.to_dict(),
                    "progress_adapter": expected.progress_adapter,
                    "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                }
            )
        except _InputRejected as error:
            self._rejected_events += 1
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.REJECTED,
                error.reason,
                error.code,
            )
        except (AttributeError, ContractViolation, TypeError, ValueError):
            self._rejected_events += 1
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.REJECTED,
                "INVALID_NO_PROJECTION_ADVANCE",
                ErrorCode.PROTOCOL_VIOLATION,
            )

        source_key = (
            expected.source_producer.component,
            expected.source_producer.instance_id,
            expected.source_work_ref.kind,
            expected.source_work_ref.id,
        )
        progress_key = (
            expected.progress_producer.component,
            expected.progress_producer.instance_id,
            expected.work_ref.kind,
            expected.work_ref.id,
        )
        work_key = (expected.scope, expected.work_ref.kind, expected.work_ref.id)
        source_fingerprint = hashlib.sha256(
            _NO_PROJECTION_SOURCE_DOMAIN + evidence_bytes
        ).digest()
        progress_fingerprint = hashlib.sha256(
            _NO_PROJECTION_PROGRESS_DOMAIN + evidence_bytes
        ).digest()
        work_fingerprint = hashlib.sha256(
            _NO_PROJECTION_WORK_DOMAIN + evidence_bytes
        ).digest()
        source_observation_fingerprint = hashlib.sha256(
            _NO_PROJECTION_OBSERVATION_DOMAIN + source_bytes
        ).digest()

        prior_source = self._observed_source_fingerprints.get(event.event_id)
        if prior_source is not None:
            if event.event_id in self._observed_source_to_progress:
                self._rejected_events += 1
                return NoProjectionAdvanceDecision(
                    NoProjectionAdvanceDisposition.REJECTED,
                    "SOURCE_EVENT_PROJECTION_CLASS_CONFLICT",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if prior_source != source_observation_fingerprint:
                self._rejected_events += 1
                return NoProjectionAdvanceDecision(
                    NoProjectionAdvanceDisposition.REJECTED,
                    "SOURCE_EVENT_ID_CONFLICT",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            prior_evidence = self._observed_no_projection_fingerprints.get(
                event.event_id
            )
            if prior_evidence != evidence_bytes:
                self._rejected_events += 1
                return NoProjectionAdvanceDecision(
                    NoProjectionAdvanceDisposition.REJECTED,
                    "NO_PROJECTION_EVIDENCE_CONFLICT",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            self._no_projection_duplicates += 1
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.DUPLICATE,
                "exact_duplicate",
                source_event_id=event.event_id,
                source_seq=event.seq,
            )

        source_sequence = self._source_streams.get(source_key)
        progress_sequence = self._progress_streams.get(progress_key)
        work = self._work_streams.get(work_key)
        sequence_reason = self._no_projection_sequence_reason(
            event.seq,
            source_sequence=source_sequence,
            progress_sequence=progress_sequence,
            work=work,
        )
        if sequence_reason is not None:
            self._rejected_events += 1
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.REJECTED,
                sequence_reason,
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if work is None or work.last_state is None:
            self._rejected_events += 1
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.REJECTED,
                "WORK_ACCEPTED_REQUIRED",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if work.terminal:
            self._rejected_events += 1
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.REJECTED,
                "WORK_EVENT_AFTER_TERMINAL",
                ErrorCode.PROTOCOL_VIOLATION,
            )

        if len(self._observed_source_fingerprints) >= self._observation_capacity:
            self._backpressure_events += 1
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.BACKPRESSURE,
                "SOURCE_OBSERVATION_CAPACITY_EXHAUSTED",
                ErrorCode.UNAVAILABLE,
            )
        capacity_reason = self._no_projection_capacity_reason(
            source_key=source_key,
            progress_key=progress_key,
            work_key=work_key,
        )
        if capacity_reason is not None:
            self._backpressure_events += 1
            return NoProjectionAdvanceDecision(
                NoProjectionAdvanceDisposition.BACKPRESSURE,
                capacity_reason,
                ErrorCode.UNAVAILABLE,
            )

        if source_sequence is None:
            source_sequence = _SequenceState(0, {})
            self._source_streams[source_key] = source_sequence
        if progress_sequence is None:
            progress_sequence = _SequenceState(0, {})
            self._progress_streams[progress_key] = progress_sequence
        self._accept_sequence(source_sequence, event.seq, source_fingerprint)
        self._accept_sequence(progress_sequence, event.seq, progress_fingerprint)
        self._accept_sequence(work.sequence, event.seq, work_fingerprint)
        self._observed_source_fingerprints[event.event_id] = (
            source_observation_fingerprint
        )
        self._observed_no_projection_fingerprints[event.event_id] = evidence_bytes
        self._no_projection_advances += 1
        return NoProjectionAdvanceDecision(
            NoProjectionAdvanceDisposition.ADVANCED,
            "verified_no_projection_advance",
            source_event_id=event.event_id,
            source_seq=event.seq,
        )

    def _offer_locked(
        self,
        source_event: object,
        progress_event: object,
        foreground: object,
        binding: object,
    ) -> NotificationDecision:
        try:
            validated = self._validate_offer(
                source_event, progress_event, foreground, binding
            )
        except _InputRejected as error:
            self._rejected_events += 1
            return self._rejected(error.reason, error.code)

        source, projected, facts, expected, progress = validated
        try:
            source_bytes = source.canonical_bytes()
            progress_bytes = projected.canonical_bytes()
        except (AttributeError, ContractViolation, TypeError, ValueError):
            self._rejected_events += 1
            return self._rejected(
                "INVALID_EVENT_ENVELOPE", ErrorCode.PROTOCOL_VIOLATION
            )

        if source.event_id in self._observed_no_projection_fingerprints:
            self._rejected_events += 1
            return self._rejected(
                "SOURCE_EVENT_PROJECTION_CLASS_CONFLICT",
                ErrorCode.PROTOCOL_VIOLATION,
            )

        observation_reason = self._observe_identity(
            source,
            projected,
            source_bytes=source_bytes,
            progress_bytes=progress_bytes,
        )
        if observation_reason is not None:
            if observation_reason.endswith("OBSERVATION_CAPACITY_EXHAUSTED"):
                self._backpressure_events += 1
                return self._backpressure(
                    observation_reason,
                    progress,
                    projected.scope,
                    source_event_id=source.event_id,
                    event_id=projected.event_id,
                )
            self._rejected_events += 1
            return self._rejected(observation_reason, ErrorCode.PROTOCOL_VIOLATION)
        if projected.event_id in self._decisions:
            decision = self._decisions[projected.event_id]
            self._duplicate_events += 1
            return NotificationDecision(
                disposition=NotificationDisposition.DUPLICATE,
                speech=SpeechDisposition.NOT_A_CANDIDATE,
                reason="exact_duplicate",
                scope=decision.scope,
                work_ref=decision.work_ref,
                event_id=decision.event_id,
                source_event_id=decision.source_event_id,
                projection_seq=decision.projection_seq,
                state=decision.state,
                outcome=decision.outcome,
                retained_event_id=decision.retained_event_id,
                progress=decision.progress,
            )

        source_key = source.stream_key
        progress_key = projected.stream_key
        work_key = (
            expected.scope,
            expected.work_ref.kind,
            expected.work_ref.id,
        )
        capacity_reason = self._capacity_reason(
            source_key=source_key,
            progress_key=progress_key,
            work_key=work_key,
        )
        if capacity_reason is not None:
            self._backpressure_events += 1
            return self._backpressure(
                capacity_reason,
                progress,
                projected.scope,
                source_event_id=source.event_id,
                event_id=projected.event_id,
            )

        source_sequence = self._source_streams.get(source_key)
        progress_sequence = self._progress_streams.get(progress_key)
        work = self._work_streams.get(work_key)
        sequence_reason = self._sequence_reason(
            source,
            projected,
            progress,
            source_sequence=source_sequence,
            progress_sequence=progress_sequence,
            work=work,
        )
        if sequence_reason is not None:
            self._rejected_events += 1
            return self._rejected(sequence_reason, ErrorCode.PROTOCOL_VIOLATION)
        lifecycle_reason = self._lifecycle_reason(work, progress.state)
        if lifecycle_reason is not None:
            self._rejected_events += 1
            return self._rejected(lifecycle_reason, ErrorCode.PROTOCOL_VIOLATION)

        if source_sequence is None:
            source_sequence = _SequenceState(0, {})
            self._source_streams[source_key] = source_sequence
        if progress_sequence is None:
            progress_sequence = _SequenceState(0, {})
            self._progress_streams[progress_key] = progress_sequence
        if work is None:
            work = _WorkState(_SequenceState(0, {}))
            self._work_streams[work_key] = work
        self._accept_sequence(source_sequence, source.seq, source_bytes)
        self._accept_sequence(progress_sequence, projected.seq, progress_bytes)
        self._accept_sequence(work.sequence, progress.seq, progress_bytes)
        work.last_state = progress.state
        work.terminal = progress.state is WorkState.TERMINAL

        pending = _PendingNotification(source, projected, progress)
        prior_pending = self._pending.get(work_key)
        retained = projected.event_id
        suppressed = False
        if prior_pending is None or self._may_replace(
            prior_pending.progress.state, progress.state
        ):
            self._pending[work_key] = pending
        else:
            retained = prior_pending.progress_event.event_id
            suppressed = True
        if prior_pending is not None:
            self._coalesced_events += 1
        self._accepted_events += 1

        if suppressed:
            assert prior_pending is not None
            decision = self._decision(
                prior_pending.progress,
                prior_pending.progress_event.scope,
                source_event_id=prior_pending.source_event.event_id,
                event_id=prior_pending.progress_event.event_id,
                disposition=NotificationDisposition.DEFERRED,
                speech=SpeechDisposition.NOT_A_CANDIDATE,
                reason="protected_pending_notification_retained",
                retained_event_id=retained,
            )
        else:
            decision = self._delivery_decision(
                progress,
                projected.scope,
                facts,
                source_event_id=source.event_id,
                event_id=projected.event_id,
                retained_event_id=retained,
                reason_prefix="offer",
            )
        self._decisions[projected.event_id] = decision
        return decision

    def drain(
        self,
        scope: object,
        foreground: object,
        *,
        max_items: int | None = None,
    ) -> tuple[NotificationDecision, ...]:
        """Return exact-scope delivery candidates without consuming them."""

        if not self._enabled:
            return ()
        with self._lock:
            return self._drain_locked(scope, foreground, max_items=max_items)

    def _drain_locked(
        self,
        scope: object,
        foreground: object,
        *,
        max_items: int | None,
    ) -> tuple[NotificationDecision, ...]:
        try:
            selected_scope = self._validate_authenticated_scope(scope)
            facts = self._validate_foreground(foreground)
        except _InputRejected as error:
            self._rejected_events += 1
            return (self._rejected(error.reason, error.code),)
        if max_items is not None and (type(max_items) is not int or max_items <= 0):
            self._rejected_events += 1
            return (self._rejected("INVALID_DRAIN_LIMIT", ErrorCode.INVALID_ARGUMENT),)
        if not self._foreground_safe(facts):
            return ()
        pending = tuple(
            item for key, item in self._pending.items() if key[0] == selected_scope
        )
        if max_items is not None:
            pending = pending[:max_items]
        return tuple(
            self._delivery_decision(
                item.progress,
                item.progress_event.scope,
                facts,
                source_event_id=item.source_event.event_id,
                event_id=item.progress_event.event_id,
                retained_event_id=item.progress_event.event_id,
                reason_prefix="drain",
            )
            for item in pending
        )

    def acknowledge(self, scope: object, work_ref: object, event_id: object) -> bool:
        """Remove only the exact candidate successfully consumed by its owner."""

        if not self._enabled:
            return False
        with self._lock:
            return self._acknowledge_locked(scope, work_ref, event_id)

    def _acknowledge_locked(
        self, scope: object, work_ref: object, event_id: object
    ) -> bool:
        try:
            selected_scope = self._validate_authenticated_scope(scope)
            if not isinstance(work_ref, IdentityRef):
                raise _InputRejected(
                    "INVALID_ACK_WORK_REF",
                    "acknowledgement requires a canonical work_ref",
                    ErrorCode.INVALID_ARGUMENT,
                )
            canonical_work_ref = IdentityRef.from_dict(work_ref.to_dict())
            if (
                canonical_work_ref != work_ref
                or work_ref.kind not in {IdentityKind.ROUND, IdentityKind.TASK}
                or type(event_id) is not str
                or not event_id.strip()
            ):
                raise _InputRejected(
                    "INVALID_ACK_BINDING",
                    "acknowledgement binding must be exact and canonical",
                    ErrorCode.INVALID_ARGUMENT,
                )
        except (AttributeError, TypeError, ValueError):
            self._rejected_events += 1
            return False
        key = (
            selected_scope,
            canonical_work_ref.kind,
            canonical_work_ref.id,
        )
        pending = self._pending.get(key)
        if pending is None or pending.progress_event.event_id != event_id:
            return False
        self._pending.pop(key)
        return True

    def snapshot(self) -> ProgressNotificationArbiterSnapshot:
        """Return aggregate internal diagnostics without scope or work identifiers."""

        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> ProgressNotificationArbiterSnapshot:
        terminal = sum(item.terminal for item in self._work_streams.values())
        return ProgressNotificationArbiterSnapshot(
            enabled=self._enabled,
            tracked_work_streams=len(self._work_streams),
            tracked_source_streams=len(self._source_streams),
            tracked_progress_streams=len(self._progress_streams),
            retained_source_events=len(self._observed_source_fingerprints),
            retained_progress_events=len(self._observed_progress_fingerprints),
            pending_notifications=len(self._pending),
            terminal_work_streams=terminal,
            accepted_events=self._accepted_events,
            coalesced_events=self._coalesced_events,
            duplicate_events=self._duplicate_events,
            rejected_events=self._rejected_events,
            backpressure_events=self._backpressure_events,
            no_projection_advances=self._no_projection_advances,
            no_projection_duplicates=self._no_projection_duplicates,
        )

    @staticmethod
    def _validate_no_projection_advance(
        advance: object,
    ) -> tuple[PersistentTaskEvent, ProgressNotificationBinding, bytes]:
        if type(advance) is not _VerifiedNoProjectionAdvance:
            raise _InputRejected(
                "INVALID_NO_PROJECTION_ADVANCE",
                "no-projection ingestion requires an internally minted capability",
                ErrorCode.INVALID_ARGUMENT,
            )
        event = advance.source_event
        if type(event) is not PersistentTaskEvent:
            raise _InputRejected(
                "INVALID_NO_PROJECTION_ADVANCE",
                "no-projection evidence requires an exact PersistentTaskEvent",
                ErrorCode.INVALID_ARGUMENT,
            )
        binding = advance.binding
        if type(binding) is not ProgressNotificationBinding:
            raise _InputRejected(
                "INVALID_PROGRESS_BINDING",
                "no-projection ingestion requires an exact product binding",
                ErrorCode.INVALID_ARGUMENT,
            )
        expected = binding
        if (
            type(event.scope) is not ScopeRef
            or type(expected.scope) is not ScopeRef
            or type(expected.work_ref) is not IdentityRef
            or type(expected.source_work_ref) is not IdentityRef
            or type(expected.source_producer) is not ProducerRef
            or type(expected.progress_producer) is not ProducerRef
            or type(expected.source_authority) is not WorkSourceAuthority
            or type(expected.correlation_id) is not str
            or not expected.correlation_id.strip()
            or (
                expected.progress_adapter is not None
                and (
                    type(expected.progress_adapter) is not str
                    or not expected.progress_adapter.strip()
                )
            )
        ):
            raise _InputRejected(
                "INVALID_PROGRESS_BINDING",
                "no-projection binding fields must have exact canonical types",
                ErrorCode.INVALID_ARGUMENT,
            )
        try:
            canonical_event = PersistentTaskEvent(
                event_id=event.event_id,
                task_id=event.task_id,
                attempt_id=event.attempt_id,
                scope=event.scope,
                seq=event.seq,
                event_type=event.event_type,
                state=event.state,
                outcome=event.outcome,
                producer=event.producer,
                source_event_id=event.source_event_id,
                causation_id=event.causation_id,
                correlation_id=event.correlation_id,
                occurred_at=event.occurred_at,
                details=event.details,
            )
            expected_scope = ScopeRef.from_dict(expected.scope.to_dict())
            expected_work = IdentityRef.from_dict(expected.work_ref.to_dict())
            expected_source_work = IdentityRef.from_dict(
                expected.source_work_ref.to_dict()
            )
            expected_source_producer = ProducerRef.from_dict(
                expected.source_producer.to_dict()
            )
            expected_progress_producer = ProducerRef.from_dict(
                expected.progress_producer.to_dict()
            )
            source_bytes = canonical_json_bytes(canonical_event.to_dict())
        except (AttributeError, ContractViolation, TypeError, ValueError) as error:
            raise _InputRejected(
                "INVALID_NO_PROJECTION_ADVANCE",
                "no-projection evidence must use canonical v2 values",
                ErrorCode.INVALID_ARGUMENT,
            ) from error
        if (
            canonical_event != event
            or expected_scope != expected.scope
            or expected_work != expected.work_ref
            or expected_source_work != expected.source_work_ref
            or expected_source_producer != expected.source_producer
            or expected_progress_producer != expected.progress_producer
            or event.scope.assurance is not Assurance.AUTHENTICATED
            or expected.scope.assurance is not Assurance.AUTHENTICATED
            or expected.work_ref.kind is not IdentityKind.TASK
            or expected.source_work_ref.kind is not IdentityKind.TASK
            or expected.source_authority is not WorkSourceAuthority.TASK_CORE
            or expected.source_producer.component != "task_core"
            or expected.source_producer.authority != "task_core"
            or expected.progress_producer.authority != "adapter"
        ):
            raise _InputRejected(
                "INVALID_NO_PROJECTION_ADVANCE",
                "no-projection evidence is not canonical authority data",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if (
            event.scope != expected.scope
            or event.task_id != expected.work_ref.id
            or event.task_id != expected.source_work_ref.id
            or event.correlation_id != expected.correlation_id
        ):
            raise _InputRejected(
                "NO_PROJECTION_BINDING_MISMATCH",
                "no-projection evidence must match the exact product binding",
                ErrorCode.PERMISSION_DENIED,
            )
        if event.event_type not in _NO_PROJECTION_EVENT_TYPES:
            raise _InputRejected(
                "INVALID_NO_PROJECTION_SOURCE_EVENT",
                "source event is not in the canonical no-projection set",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if event.event_type == "task.cancel_requested":
            valid_lifecycle = (
                event.producer == "task_core.control"
                and event.state
                in {"accepted", "running", "blocked", "decision_required"}
                and event.outcome is None
                and event.source_event_id is None
            )
        else:
            expected_state = event.event_type.removeprefix("attempt.")
            internal_terminal = event.producer in {
                "task_core.delivery",
                "task_core.reconciliation",
            }
            executor_event = not event.producer.startswith("task_core")
            exact_executor_source = (
                event.source_event_id is not None
                and event.causation_id == event.source_event_id
            )
            valid_lifecycle = (
                event.state == expected_state
                and (event.state == "terminal") == (event.outcome is not None)
                and (
                    (executor_event and exact_executor_source)
                    or (
                        event.event_type == "attempt.terminal"
                        and internal_terminal
                        and event.source_event_id is None
                    )
                )
            )
        if not valid_lifecycle:
            raise _InputRejected(
                "INVALID_NO_PROJECTION_SOURCE_EVENT",
                "source event producer, lifecycle, or source evidence is invalid",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        return canonical_event, expected, source_bytes

    def _validate_offer(
        self,
        source_event: object,
        progress_event: object,
        foreground: object,
        binding: object,
    ) -> tuple[
        EventEnvelope,
        EventEnvelope,
        ForegroundSnapshot,
        ProgressNotificationBinding,
        WorkProgressEventV2,
    ]:
        if not isinstance(source_event, EventEnvelope) or not isinstance(
            progress_event, EventEnvelope
        ):
            raise _InputRejected(
                "INVALID_EVENT_ENVELOPE",
                "source and progress must be parsed v2 EventEnvelope values",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (
            source_event.contract_version != CONTRACT_VERSION
            or progress_event.contract_version != CONTRACT_VERSION
        ):
            raise _InputRejected(
                "UNSUPPORTED_CONTRACT_VERSION",
                "source and progress must use live-voice.contract.v2",
                ErrorCode.UNSUPPORTED,
            )
        facts = self._validate_foreground(foreground)
        if not isinstance(binding, ProgressNotificationBinding):
            raise _InputRejected(
                "INVALID_PROGRESS_BINDING",
                "notification arbitration requires an exact product binding",
                ErrorCode.INVALID_ARGUMENT,
            )
        expected = binding
        try:
            canonical_scope = ScopeRef.from_dict(expected.scope.to_dict())
            canonical_work = IdentityRef.from_dict(expected.work_ref.to_dict())
            canonical_source_work = IdentityRef.from_dict(
                expected.source_work_ref.to_dict()
            )
            canonical_source_producer = ProducerRef.from_dict(
                expected.source_producer.to_dict()
            )
            canonical_progress_producer = ProducerRef.from_dict(
                expected.progress_producer.to_dict()
            )
        except (AttributeError, ContractViolation, TypeError, ValueError) as error:
            raise _InputRejected(
                "INVALID_PROGRESS_BINDING",
                "notification binding must use canonical v2 values",
                ErrorCode.INVALID_ARGUMENT,
            ) from error
        if (
            canonical_scope != expected.scope
            or canonical_work != expected.work_ref
            or canonical_source_work != expected.source_work_ref
            or canonical_source_producer != expected.source_producer
            or canonical_progress_producer != expected.progress_producer
            or not isinstance(expected.source_authority, WorkSourceAuthority)
            or type(expected.correlation_id) is not str
            or not expected.correlation_id.strip()
            or (
                expected.progress_adapter is not None
                and (
                    type(expected.progress_adapter) is not str
                    or not expected.progress_adapter.strip()
                )
            )
        ):
            raise _InputRejected(
                "INVALID_PROGRESS_BINDING",
                "notification binding contains non-canonical values",
                ErrorCode.INVALID_ARGUMENT,
            )
        if expected.scope.assurance is not Assurance.AUTHENTICATED:
            raise _InputRejected(
                "UNAUTHENTICATED_PROGRESS_SCOPE",
                "notification scope must be authenticated",
                ErrorCode.UNAUTHENTICATED,
            )
        if expected.work_ref.kind not in {IdentityKind.ROUND, IdentityKind.TASK}:
            raise _InputRejected(
                "INVALID_WORK_BINDING",
                "notification work_ref must identify a round or task",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (
            source_event.scope != expected.scope
            or progress_event.scope != expected.scope
        ):
            raise _InputRejected(
                "PROGRESS_SCOPE_MISMATCH",
                "source and projection must match the authenticated scope exactly",
                ErrorCode.PERMISSION_DENIED,
            )
        if (
            source_event.correlation_id != expected.correlation_id
            or progress_event.correlation_id != expected.correlation_id
        ):
            raise _InputRejected(
                "PROGRESS_CORRELATION_MISMATCH",
                "source and projection must match the exact correlation",
                ErrorCode.PERMISSION_DENIED,
            )
        if (
            source_event.producer != expected.source_producer
            or progress_event.producer != expected.progress_producer
            or source_event.stream_ref != expected.source_work_ref
            or progress_event.stream_ref != expected.work_ref
            or source_event.producer.authority != expected.source_authority.value
            or progress_event.producer.authority != "adapter"
        ):
            raise _InputRejected(
                "PROGRESS_PROVENANCE_MISMATCH",
                "source/projection producer and stream bindings must be exact",
                ErrorCode.PERMISSION_DENIED,
            )
        try:
            progress = WorkProgressEventV2.from_dict(
                progress_event.payload, scope=progress_event.scope
            )
        except ContractViolation as error:
            raise _InputRejected(
                error.reason,
                "work.progress payload is not a strict WorkProgressEventV2",
                error.code,
            ) from error
        if progress_event.event_type != "work.progress":
            raise _InputRejected(
                "INVALID_PROGRESS_EVENT_TYPE",
                "projection envelope must have event_type work.progress",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if (
            progress.work_ref != expected.work_ref
            or progress.source.source_work_ref != expected.source_work_ref
            or progress.source.authority is not expected.source_authority
            or progress.source.adapter != expected.progress_adapter
            or progress.source.event_id != source_event.event_id
            or progress_event.causation_id != source_event.event_id
        ):
            raise _InputRejected(
                "PROGRESS_SOURCE_MISMATCH",
                "WorkProgress must retain its exact authoritative source binding",
                ErrorCode.PERMISSION_DENIED,
            )
        self._validate_source_relation(source_event, progress)
        return source_event, progress_event, facts, expected, progress

    @staticmethod
    def _validate_foreground(foreground: object) -> ForegroundSnapshot:
        if (
            not isinstance(foreground, ForegroundSnapshot)
            or not all(
                isinstance(item, ForegroundFact)
                for item in (
                    foreground.interaction,
                    foreground.response,
                    foreground.presentation,
                )
            )
            or not isinstance(foreground.speech_policy, SpeechPolicy)
        ):
            raise _InputRejected(
                "INVALID_FOREGROUND_SNAPSHOT",
                "foreground safety facts must be explicit canonical values",
                ErrorCode.INVALID_ARGUMENT,
            )
        return foreground

    @staticmethod
    def _validate_authenticated_scope(scope: object) -> ScopeRef:
        if not isinstance(scope, ScopeRef):
            raise _InputRejected(
                "INVALID_CONSUMER_SCOPE",
                "notification consumption requires a canonical ScopeRef",
                ErrorCode.INVALID_ARGUMENT,
            )
        try:
            canonical = ScopeRef.from_dict(scope.to_dict())
        except (AttributeError, ContractViolation, TypeError, ValueError) as error:
            raise _InputRejected(
                "INVALID_CONSUMER_SCOPE",
                "notification consumption requires a canonical ScopeRef",
                ErrorCode.INVALID_ARGUMENT,
            ) from error
        if canonical != scope:
            raise _InputRejected(
                "INVALID_CONSUMER_SCOPE",
                "notification consumption requires a canonical ScopeRef",
                ErrorCode.INVALID_ARGUMENT,
            )
        if scope.assurance is not Assurance.AUTHENTICATED:
            raise _InputRejected(
                "UNAUTHENTICATED_CONSUMER_SCOPE",
                "notification consumption requires authenticated scope",
                ErrorCode.UNAUTHENTICATED,
            )
        return scope

    @staticmethod
    def _validate_source_relation(
        source_event: EventEnvelope, progress: WorkProgressEventV2
    ) -> None:
        expected_kind = {
            WorkSourceAuthority.HARNESS: IdentityKind.ROUND,
            WorkSourceAuthority.TASK_CORE: IdentityKind.TASK,
            WorkSourceAuthority.EXECUTOR: IdentityKind.ATTEMPT,
        }[progress.source.authority]
        if source_event.stream_ref.kind is not expected_kind:
            raise _InputRejected(
                "PROGRESS_SOURCE_KIND_MISMATCH",
                "source authority and source work kind must agree",
                ErrorCode.PERMISSION_DENIED,
            )
        if (
            progress.source.source_work_ref.kind
            in {IdentityKind.ROUND, IdentityKind.TASK}
            and progress.source.source_work_ref != progress.work_ref
        ) or (
            progress.source.source_work_ref.kind is IdentityKind.ATTEMPT
            and progress.work_ref.kind is not IdentityKind.TASK
        ):
            raise _InputRejected(
                "PROGRESS_SOURCE_WORK_MISMATCH",
                "source work must be the projected work or its bound task attempt",
                ErrorCode.PERMISSION_DENIED,
            )
        expected_event_type = (
            f"{source_event.stream_ref.kind.value}.{progress.state.value}"
        )
        payload = source_event.payload
        if source_event.event_type != expected_event_type:
            raise _InputRejected(
                "PROGRESS_SOURCE_STATE_MISMATCH",
                "source event type must match projected state",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        source_outcome = payload.get("outcome")
        expected_outcome = None if progress.outcome is None else progress.outcome.value
        if (
            payload.get("state") != progress.state.value
            or source_outcome != expected_outcome
        ):
            raise _InputRejected(
                "PROGRESS_SOURCE_OUTCOME_MISMATCH",
                "source state/outcome must match the projection exactly",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    def _observe_identity(
        self,
        source: EventEnvelope,
        projected: EventEnvelope,
        *,
        source_bytes: bytes,
        progress_bytes: bytes,
    ) -> str | None:
        """Freeze canonical identities and pairings before mutable admission checks.

        An exact observation that was rejected by sequence/lifecycle policy or by
        backpressure may be retried.  Reusing either identity with different bytes
        or a different counterpart remains fail-closed for this arbiter lifetime.
        """

        source_id = source.event_id
        progress_id = projected.event_id
        prior_source = self._observed_source_fingerprints.get(source_id)
        prior_progress = self._observed_progress_fingerprints.get(progress_id)
        prior_projection = self._observed_source_to_progress.get(source_id)
        prior_backing = self._observed_progress_to_source.get(progress_id)

        reason: str | None = None
        if prior_source is not None and prior_source != source_bytes:
            reason = "SOURCE_EVENT_ID_CONFLICT"
        elif prior_progress is not None and prior_progress != progress_bytes:
            reason = "PROGRESS_EVENT_ID_CONFLICT"
        elif prior_projection is not None and prior_projection != progress_id:
            reason = "SOURCE_EVENT_REPROJECTED"
        elif prior_backing is not None and prior_backing != source_id:
            reason = "PROGRESS_SOURCE_REBOUND"

        new_source = prior_source is None
        new_progress = prior_progress is None
        if (
            new_source
            and len(self._observed_source_fingerprints) >= self._observation_capacity
        ):
            return reason or "SOURCE_OBSERVATION_CAPACITY_EXHAUSTED"
        if (
            new_progress
            and len(self._observed_progress_fingerprints) >= self._observation_capacity
        ):
            return reason or "PROGRESS_OBSERVATION_CAPACITY_EXHAUSTED"

        # Record each first-seen identity even when its counterpart is already in a
        # conflicting pairing.  This prevents a rejected rebind attempt from later
        # presenting that new identity with different bytes or another counterpart.
        if new_source:
            self._observed_source_fingerprints[source_id] = source_bytes
            self._observed_source_to_progress[source_id] = progress_id
        if new_progress:
            self._observed_progress_fingerprints[progress_id] = progress_bytes
            self._observed_progress_to_source[progress_id] = source_id
        return reason

    def _capacity_reason(
        self,
        *,
        source_key: _SourceStreamKey,
        progress_key: _ProgressStreamKey,
        work_key: _WorkKey,
    ) -> str | None:
        source = self._source_streams.get(source_key)
        progress = self._progress_streams.get(progress_key)
        work = self._work_streams.get(work_key)
        if source is None and len(self._source_streams) >= self._stream_capacity:
            return "SOURCE_STREAM_CAPACITY_EXHAUSTED"
        if progress is None and len(self._progress_streams) >= self._stream_capacity:
            return "PROGRESS_STREAM_CAPACITY_EXHAUSTED"
        if work is None and len(self._work_streams) >= self._stream_capacity:
            return "WORK_STREAM_CAPACITY_EXHAUSTED"
        if source is not None and len(source.fingerprints) >= self._events_per_stream:
            return "SOURCE_EVENT_CAPACITY_EXHAUSTED"
        if (
            progress is not None
            and len(progress.fingerprints) >= self._events_per_stream
        ):
            return "PROGRESS_EVENT_CAPACITY_EXHAUSTED"
        if (
            work is not None
            and len(work.sequence.fingerprints) >= self._events_per_stream
        ):
            return "WORK_EVENT_CAPACITY_EXHAUSTED"
        if (
            work_key not in self._pending
            and len(self._pending) >= self._pending_capacity
        ):
            return "PENDING_NOTIFICATION_CAPACITY_EXHAUSTED"
        return None

    def _no_projection_capacity_reason(
        self,
        *,
        source_key: _SourceStreamKey,
        progress_key: _ProgressStreamKey,
        work_key: _WorkKey,
    ) -> str | None:
        source = self._source_streams.get(source_key)
        progress = self._progress_streams.get(progress_key)
        work = self._work_streams.get(work_key)
        if source is None and len(self._source_streams) >= self._stream_capacity:
            return "SOURCE_STREAM_CAPACITY_EXHAUSTED"
        if progress is None and len(self._progress_streams) >= self._stream_capacity:
            return "PROGRESS_STREAM_CAPACITY_EXHAUSTED"
        if work is None and len(self._work_streams) >= self._stream_capacity:
            return "WORK_STREAM_CAPACITY_EXHAUSTED"
        if source is not None and len(source.fingerprints) >= self._events_per_stream:
            return "SOURCE_EVENT_CAPACITY_EXHAUSTED"
        if (
            progress is not None
            and len(progress.fingerprints) >= self._events_per_stream
        ):
            return "PROGRESS_EVENT_CAPACITY_EXHAUSTED"
        if (
            work is not None
            and len(work.sequence.fingerprints) >= self._events_per_stream
        ):
            return "WORK_EVENT_CAPACITY_EXHAUSTED"
        return None

    @staticmethod
    def _no_projection_sequence_reason(
        seq: int,
        *,
        source_sequence: _SequenceState | None,
        progress_sequence: _SequenceState | None,
        work: _WorkState | None,
    ) -> str | None:
        checks = (
            ("SOURCE", source_sequence),
            ("PROGRESS_ENVELOPE", progress_sequence),
            ("WORK_PROJECTION", None if work is None else work.sequence),
        )
        for prefix, current in checks:
            expected = 0 if current is None else current.next_seq
            if seq > expected:
                return f"{prefix}_SEQUENCE_GAP"
            if seq < expected:
                return f"{prefix}_SEQUENCE_CONFLICT"
        return None

    @staticmethod
    def _sequence_reason(
        source: EventEnvelope,
        projected: EventEnvelope,
        progress: WorkProgressEventV2,
        *,
        source_sequence: _SequenceState | None,
        progress_sequence: _SequenceState | None,
        work: _WorkState | None,
    ) -> str | None:
        checks = (
            ("SOURCE", source.seq, source_sequence),
            ("PROGRESS_ENVELOPE", projected.seq, progress_sequence),
            ("WORK_PROJECTION", progress.seq, None if work is None else work.sequence),
        )
        for prefix, seq, current in checks:
            expected = 0 if current is None else current.next_seq
            if seq > expected:
                return f"{prefix}_SEQUENCE_GAP"
            if seq < expected:
                return f"{prefix}_SEQUENCE_CONFLICT"
        return None

    @staticmethod
    def _lifecycle_reason(work: _WorkState | None, state: WorkState) -> str | None:
        if work is None or work.last_state is None:
            return None if state is WorkState.ACCEPTED else "WORK_ACCEPTED_REQUIRED"
        if work.terminal:
            return "WORK_EVENT_AFTER_TERMINAL"
        if state is WorkState.ACCEPTED:
            return "WORK_ACCEPTED_REPEATED"
        return None

    @staticmethod
    def _accept_sequence(
        sequence: _SequenceState, seq: int, fingerprint: bytes
    ) -> None:
        sequence.fingerprints[seq] = fingerprint
        sequence.next_seq = seq + 1

    @staticmethod
    def _may_replace(retained: WorkState, incoming: WorkState) -> bool:
        if incoming is WorkState.TERMINAL:
            return True
        if retained is WorkState.TERMINAL:
            return False
        if retained is WorkState.DECISION_REQUIRED:
            return incoming is WorkState.DECISION_REQUIRED
        return True

    @staticmethod
    def _foreground_safe(foreground: ForegroundSnapshot) -> bool:
        return all(
            item is ForegroundFact.SAFE
            for item in (
                foreground.interaction,
                foreground.response,
                foreground.presentation,
            )
        )

    def _delivery_decision(
        self,
        progress: WorkProgressEventV2,
        scope: ScopeRef,
        foreground: ForegroundSnapshot,
        *,
        source_event_id: str,
        event_id: str,
        retained_event_id: str,
        reason_prefix: str,
    ) -> NotificationDecision:
        if not self._foreground_safe(foreground):
            return self._decision(
                progress,
                scope,
                source_event_id=source_event_id,
                event_id=event_id,
                disposition=NotificationDisposition.DEFERRED,
                speech=SpeechDisposition.NOT_A_CANDIDATE,
                reason=f"{reason_prefix}_foreground_not_proven_safe",
                retained_event_id=retained_event_id,
            )
        speech = SpeechDisposition.NOT_A_CANDIDATE
        if (
            foreground.speech_policy is SpeechPolicy.ALLOW_CANDIDATE
            and progress.speakability is not Speakability.NOT_SPEAKABLE
        ):
            speech = SpeechDisposition.SPEAK_WHEN_SAFE_CANDIDATE
        return self._decision(
            progress,
            scope,
            source_event_id=source_event_id,
            event_id=event_id,
            disposition=NotificationDisposition.DISPLAY_NOW,
            speech=speech,
            reason=f"{reason_prefix}_foreground_safe",
            retained_event_id=retained_event_id,
        )

    @staticmethod
    def _decision(
        progress: WorkProgressEventV2,
        scope: ScopeRef,
        *,
        source_event_id: str,
        event_id: str,
        disposition: NotificationDisposition,
        speech: SpeechDisposition,
        reason: str,
        retained_event_id: str,
    ) -> NotificationDecision:
        return NotificationDecision(
            disposition=disposition,
            speech=speech,
            reason=reason,
            scope=scope,
            work_ref=progress.work_ref,
            event_id=event_id,
            source_event_id=source_event_id,
            projection_seq=progress.seq,
            state=progress.state,
            outcome=progress.outcome,
            retained_event_id=retained_event_id,
            progress=progress,
        )

    @staticmethod
    def _rejected(reason: str, code: ErrorCode) -> NotificationDecision:
        return NotificationDecision(
            disposition=NotificationDisposition.REJECTED,
            speech=SpeechDisposition.NOT_A_CANDIDATE,
            reason=reason,
            code=code,
        )

    @staticmethod
    def _backpressure(
        reason: str,
        progress: WorkProgressEventV2,
        scope: ScopeRef,
        *,
        source_event_id: str,
        event_id: str,
    ) -> NotificationDecision:
        return NotificationDecision(
            disposition=NotificationDisposition.BACKPRESSURE,
            speech=SpeechDisposition.NOT_A_CANDIDATE,
            reason=reason,
            code=ErrorCode.UNAVAILABLE,
            scope=scope,
            work_ref=progress.work_ref,
            event_id=event_id,
            source_event_id=source_event_id,
            projection_seq=progress.seq,
            state=progress.state,
            outcome=progress.outcome,
        )


__all__ = [
    "ForegroundFact",
    "ForegroundSnapshot",
    "NoProjectionAdvanceDecision",
    "NoProjectionAdvanceDisposition",
    "NotificationDecision",
    "NotificationDisposition",
    "ProgressNotificationArbiter",
    "ProgressNotificationArbiterSnapshot",
    "ProgressNotificationArbiterViolation",
    "ProgressNotificationBinding",
    "SpeechDisposition",
    "SpeechPolicy",
]
