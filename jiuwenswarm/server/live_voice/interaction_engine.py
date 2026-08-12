# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Capability-checked interaction intentions without lifecycle ownership.

The scripted Cascade implementation in this module is a deterministic contract
fake.  It consumes already-classified observations and proposes intentions; it
does not classify raw audio, choose product VAD/EOT parameters, or hold any
Conversation Runtime, Agent, Tool, Task, history, audio, or cancel authority.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    ScopeRef,
    canonical_json_bytes,
)


_MAX_OPERATION_COUNT = 64
_MAX_OPERATION_CHARS = 128
_MAX_OPERATION_UTF8_BYTES = 512
_MAX_IDENTITY_CHARS = 256
_MAX_IDENTITY_UTF8_BYTES = 1024
_MAX_PAYLOAD_ENTRIES = 32
_MAX_PAYLOAD_KEY_CHARS = 128
_MAX_PAYLOAD_KEY_UTF8_BYTES = 512
_MAX_PAYLOAD_VALUE_CHARS = 1024
_MAX_PAYLOAD_VALUE_UTF8_BYTES = 4096
_MAX_ACTIONS = 1024
_MAX_OBSERVATIONS = 1024


class InteractionEngineViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class InteractionAction:
    action_id: str
    operation: str
    interaction_id: str
    scope: ScopeRef
    payload: tuple[tuple[str, str], ...] = ()


class CascadeActionOperation(StrEnum):
    """Frozen intention vocabulary shared by Cascade conformance scenarios."""

    LISTEN = "LISTEN"
    SILENCE = "SILENCE"
    TURN_COMMIT = "TURN_COMMIT"
    SPEAK = "SPEAK"
    STOP = "STOP"
    REVISE = "REVISE"
    DELEGATE = "DELEGATE"


CASCADE_ACTION_OPERATIONS = frozenset(
    operation.value for operation in CascadeActionOperation
)


class CascadeObservationKind(StrEnum):
    """Provider-neutral facts accepted by the deterministic contract fake.

    ``ECHO_REJECTED`` and ``DOUBLE_TALK_REJECTED`` are upstream classification
    results, not policy thresholds selected by this module.  Likewise,
    ``BARGE_IN_CONFIRMED`` is an input fact; the resulting ``STOP`` value remains
    an intention for Conversation Runtime to validate and route.
    """

    SPEECH_STARTED = "speech.started"
    PARTIAL_TRANSCRIPT = "speech.partial"
    SILENCE_OBSERVED = "speech.silence"
    END_OF_TURN = "speech.end_of_turn"
    RESPONSE_DELTA = "response.delta"
    BARGE_IN_CONFIRMED = "speech.barge_in_confirmed"
    REVISION_REQUESTED = "interaction.revision_requested"
    DELEGATION_REQUESTED = "interaction.delegation_requested"
    ECHO_REJECTED = "speech.echo_rejected"
    DOUBLE_TALK_REJECTED = "speech.double_talk_rejected"


CASCADE_GOLDEN_SCRIPT = (
    (CascadeObservationKind.SPEECH_STARTED, CascadeActionOperation.LISTEN),
    (CascadeObservationKind.PARTIAL_TRANSCRIPT, CascadeActionOperation.LISTEN),
    (CascadeObservationKind.SILENCE_OBSERVED, CascadeActionOperation.SILENCE),
    (CascadeObservationKind.END_OF_TURN, CascadeActionOperation.TURN_COMMIT),
    (CascadeObservationKind.RESPONSE_DELTA, CascadeActionOperation.SPEAK),
    (CascadeObservationKind.BARGE_IN_CONFIRMED, CascadeActionOperation.STOP),
    (CascadeObservationKind.REVISION_REQUESTED, CascadeActionOperation.REVISE),
    (CascadeObservationKind.DELEGATION_REQUESTED, CascadeActionOperation.DELEGATE),
    (CascadeObservationKind.ECHO_REJECTED, CascadeActionOperation.SILENCE),
    (CascadeObservationKind.DOUBLE_TALK_REJECTED, CascadeActionOperation.LISTEN),
)
# This vector freezes observation-to-intention conformance only.  It is not a
# valid CR lifecycle trace and does not imply that every action occurs within
# one product response.
_CASCADE_ACTION_BY_OBSERVATION = dict(CASCADE_GOLDEN_SCRIPT)
if set(_CASCADE_ACTION_BY_OBSERVATION) != set(CascadeObservationKind):
    # Fail at import rather than letting a newly added observation kind reach a
    # lookup that has no frozen intention for it.
    raise InteractionEngineViolation(
        "INCOMPLETE_CASCADE_SCRIPT",
        "every CascadeObservationKind requires one frozen golden intention",
    )


@dataclass(frozen=True, slots=True)
class CascadeObservation:
    """One exact, already-classified input fact for a bound response generation."""

    observation_id: str
    observation_sequence: int
    interaction_id: str
    response_generation: int
    scope: ScopeRef
    kind: CascadeObservationKind


@dataclass(frozen=True, slots=True)
class ScriptedCascadeSnapshot:
    interaction_id: str
    response_generation: int
    next_observation_sequence: int
    released_through: int
    retained_observations: int
    retained_actions: int
    retained_observation_identities: int


@dataclass(frozen=True, slots=True)
class _CascadeRecord:
    observation: CascadeObservation
    action: InteractionAction


@dataclass(frozen=True, slots=True)
class _CascadeIdentityBinding:
    observation_sequence: int
    kind: CascadeObservationKind


def _is_canonical_text(value: object, *, max_chars: int, max_utf8_bytes: int) -> bool:
    if (
        type(value) is not str
        or not value
        or len(value) > max_chars
        or value != value.strip()
    ):
        return False
    try:
        return len(value.encode("utf-8")) <= max_utf8_bytes
    except UnicodeEncodeError:
        return False


def _canonical_scope(value: object) -> ScopeRef:
    if not isinstance(value, ScopeRef):
        raise InteractionEngineViolation(
            "INVALID_SCOPE", "scope must be a canonical ScopeRef"
        )
    try:
        canonical = ScopeRef.from_dict(value.to_dict())
    except Exception:
        raise InteractionEngineViolation(
            "INVALID_SCOPE", "scope must be a canonical ScopeRef"
        ) from None
    if any(
        item is not None
        and not _is_canonical_text(
            item,
            max_chars=_MAX_IDENTITY_CHARS,
            max_utf8_bytes=_MAX_IDENTITY_UTF8_BYTES,
        )
        for item in (
            canonical.subject_id,
            canonical.project_id,
            canonical.session_id,
        )
    ):
        raise InteractionEngineViolation(
            "INVALID_SCOPE", "scope identities must be canonical bounded strings"
        )
    return canonical


def _require_canonical_identity(value: object, name: str) -> str:
    if not _is_canonical_text(
        value,
        max_chars=_MAX_IDENTITY_CHARS,
        max_utf8_bytes=_MAX_IDENTITY_UTF8_BYTES,
    ):
        raise InteractionEngineViolation(
            "INVALID_OBSERVATION_IDENTITY", f"{name} must be a canonical identity"
        )
    return value


def _require_safe_integer(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > MAX_SAFE_INTEGER:
        raise InteractionEngineViolation(
            "INVALID_OBSERVATION_CURSOR",
            f"{name} must be an integer between {minimum} and {MAX_SAFE_INTEGER}",
        )
    return value


def _cascade_action_id(
    scope: ScopeRef,
    interaction_id: str,
    response_generation: int,
    observation_sequence: int,
) -> str:
    fingerprint = hashlib.sha256(
        canonical_json_bytes(
            {
                "scope": scope.to_dict(),
                "interaction_id": interaction_id,
                "response_generation": response_generation,
                "observation_sequence": observation_sequence,
            }
        )
    ).hexdigest()
    return f"cascade:{fingerprint}"


class InteractionEnginePort:
    def __init__(
        self,
        operations: frozenset[str],
        *,
        scope: ScopeRef | None = None,
        max_actions: int = 256,
    ) -> None:
        if (
            not isinstance(operations, frozenset)
            or not operations
            or len(operations) > _MAX_OPERATION_COUNT
            or any(
                not _is_canonical_text(
                    item,
                    max_chars=_MAX_OPERATION_CHARS,
                    max_utf8_bytes=_MAX_OPERATION_UTF8_BYTES,
                )
                for item in operations
            )
        ):
            raise InteractionEngineViolation(
                "INVALID_CAPABILITIES", "at least one valid operation is required"
            )
        canonical_scope = None if scope is None else _canonical_scope(scope)
        if type(max_actions) is not int or not 0 < max_actions <= _MAX_ACTIONS:
            raise InteractionEngineViolation(
                "INVALID_CAPACITY", "max_actions exceeds the bounded positive range"
            )
        self._operations = frozenset(operations)
        self._scope = canonical_scope
        self._max_actions = max_actions
        self._lock = threading.RLock()
        self._accepted: dict[str, InteractionAction] = {}

    def propose(self, action: InteractionAction) -> tuple[bool, InteractionAction]:
        if not isinstance(action, InteractionAction):
            raise InteractionEngineViolation(
                "INVALID_ACTION", "action must use the canonical InteractionAction type"
            )
        if not _is_canonical_text(
            action.operation,
            max_chars=_MAX_OPERATION_CHARS,
            max_utf8_bytes=_MAX_OPERATION_UTF8_BYTES,
        ):
            raise InteractionEngineViolation(
                "INVALID_ACTION", "action operation must be a non-empty string"
            )
        canonical_scope = _canonical_scope(action.scope)
        if self._scope is not None and canonical_scope != self._scope:
            raise InteractionEngineViolation(
                "ACTION_SCOPE_MISMATCH",
                "action scope must match the exact interaction owner scope",
            )
        if action.operation not in self._operations:
            raise InteractionEngineViolation(
                "CAPABILITY_UNSUPPORTED",
                f"operation {action.operation!r} is unsupported",
            )
        if not _is_canonical_text(
            action.action_id,
            max_chars=_MAX_IDENTITY_CHARS,
            max_utf8_bytes=_MAX_IDENTITY_UTF8_BYTES,
        ) or not _is_canonical_text(
            action.interaction_id,
            max_chars=_MAX_IDENTITY_CHARS,
            max_utf8_bytes=_MAX_IDENTITY_UTF8_BYTES,
        ):
            raise InteractionEngineViolation(
                "INVALID_ACTION_IDENTITY", "action identities must be non-empty"
            )
        if (
            type(action.payload) is not tuple
            or len(action.payload) > _MAX_PAYLOAD_ENTRIES
            or any(
                type(item) is not tuple
                or len(item) != 2
                or not _is_canonical_text(
                    item[0],
                    max_chars=_MAX_PAYLOAD_KEY_CHARS,
                    max_utf8_bytes=_MAX_PAYLOAD_KEY_UTF8_BYTES,
                )
                or not _is_canonical_text(
                    item[1],
                    max_chars=_MAX_PAYLOAD_VALUE_CHARS,
                    max_utf8_bytes=_MAX_PAYLOAD_VALUE_UTF8_BYTES,
                )
                for item in action.payload
            )
        ):
            raise InteractionEngineViolation(
                "INVALID_ACTION", "action payload must be an immutable string tuple"
            )
        with self._lock:
            existing = self._accepted.get(action.action_id)
            if existing is not None:
                if existing == action:
                    return False, existing
                raise InteractionEngineViolation(
                    "ACTION_ID_CONFLICT", "action_id cannot change its meaning"
                )
            if len(self._accepted) >= self._max_actions:
                raise InteractionEngineViolation(
                    "ACTION_LEDGER_FULL",
                    "bounded interaction action ledger is full",
                )
            self._accepted[action.action_id] = action
            return True, action

    def accepted(self) -> tuple[InteractionAction, ...]:
        with self._lock:
            return tuple(self._accepted.values())


class ScriptedCascadeInteractionEngine:
    """Bounded, generation-bound deterministic Cascade conformance fake.

    The caller supplies exact interaction/scope/generation fence facts and
    advances a contiguous observation sequence.  This fake neither allocates
    nor advances a response generation and does not validate CR lifecycle
    ordering.  Exact duplicates replay the prior intention only while its
    replay record is retained; conflicting, stale, cross-scope, unsupported,
    or over-capacity observations fail before the retained intention set
    changes.

    Releasing a contiguous prefix releases the observation/action replay
    records but retains a compact, separately bounded identity binding.  It
    never resets the sequence or response generation, so a released
    observation cannot be replayed or rebound as new work.
    """

    def __init__(
        self,
        *,
        scope: ScopeRef,
        interaction_id: str,
        response_generation: int,
        supported_actions: frozenset[str] = CASCADE_ACTION_OPERATIONS,
        max_observations: int = 256,
        max_observation_identities: int = _MAX_OBSERVATIONS,
    ) -> None:
        canonical_scope = _canonical_scope(scope)
        canonical_interaction_id = _require_canonical_identity(
            interaction_id, "interaction_id"
        )
        canonical_generation = _require_safe_integer(
            response_generation, "response_generation"
        )
        if (
            not isinstance(supported_actions, frozenset)
            or not supported_actions
            or any(type(item) is not str for item in supported_actions)
            or not supported_actions.issubset(CASCADE_ACTION_OPERATIONS)
        ):
            raise InteractionEngineViolation(
                "INVALID_CASCADE_CAPABILITIES",
                "supported_actions must be a non-empty frozen subset of the "
                "Cascade action vocabulary",
            )
        if (
            type(max_observations) is not int
            or not 0 < max_observations <= _MAX_OBSERVATIONS
        ):
            raise InteractionEngineViolation(
                "INVALID_OBSERVATION_CAPACITY",
                "max_observations exceeds the bounded positive range",
            )
        if (
            type(max_observation_identities) is not int
            or not (
                max_observations
                <= max_observation_identities
                <= _MAX_OBSERVATIONS
            )
        ):
            raise InteractionEngineViolation(
                "INVALID_OBSERVATION_IDENTITY_CAPACITY",
                "max_observation_identities must be between max_observations "
                "and the bounded Cascade identity limit",
            )
        self._scope = canonical_scope
        self._interaction_id = canonical_interaction_id
        self._response_generation = canonical_generation
        self._supported_actions = frozenset(supported_actions)
        self._max_observations = max_observations
        self._max_observation_identities = max_observation_identities
        self._lock = threading.RLock()
        self._next_observation_sequence = 1
        self._released_through = 0
        self._records_by_id: dict[str, _CascadeRecord] = {}
        self._records_by_sequence: dict[int, _CascadeRecord] = {}
        self._observation_identities: dict[str, _CascadeIdentityBinding] = {}

    def observe(
        self, observation: CascadeObservation
    ) -> tuple[bool, InteractionAction]:
        if not isinstance(observation, CascadeObservation):
            raise InteractionEngineViolation(
                "INVALID_OBSERVATION",
                "observation must use the canonical CascadeObservation type",
            )
        observation_id = _require_canonical_identity(
            observation.observation_id, "observation_id"
        )
        interaction_id = _require_canonical_identity(
            observation.interaction_id, "interaction_id"
        )
        sequence = _require_safe_integer(
            observation.observation_sequence,
            "observation_sequence",
            minimum=1,
        )
        generation = _require_safe_integer(
            observation.response_generation, "response_generation"
        )
        canonical_scope = _canonical_scope(observation.scope)
        if type(observation.kind) is not CascadeObservationKind:
            raise InteractionEngineViolation(
                "INVALID_OBSERVATION_KIND",
                "kind must use the frozen CascadeObservationKind vocabulary",
            )
        if canonical_scope != self._scope:
            raise InteractionEngineViolation(
                "OBSERVATION_SCOPE_MISMATCH",
                "observation scope must match the exact Cascade binding",
            )
        if interaction_id != self._interaction_id:
            raise InteractionEngineViolation(
                "OBSERVATION_INTERACTION_MISMATCH",
                "observation interaction must match the exact Cascade binding",
            )
        if generation < self._response_generation:
            raise InteractionEngineViolation(
                "STALE_RESPONSE_GENERATION",
                "observation response generation is stale",
            )
        if generation != self._response_generation:
            raise InteractionEngineViolation(
                "RESPONSE_GENERATION_MISMATCH",
                "observation response generation must match the exact binding",
            )

        with self._lock:
            existing = self._records_by_id.get(observation_id)
            if existing is not None:
                if existing.observation == observation:
                    return False, existing.action
                raise InteractionEngineViolation(
                    "OBSERVATION_ID_CONFLICT",
                    "observation_id cannot change its meaning",
                )
            identity_binding = self._observation_identities.get(observation_id)
            if identity_binding is not None:
                if identity_binding == _CascadeIdentityBinding(
                    observation_sequence=sequence,
                    kind=observation.kind,
                ):
                    raise InteractionEngineViolation(
                        "STALE_OBSERVATION",
                        "a released observation cannot replay as new work",
                    )
                raise InteractionEngineViolation(
                    "OBSERVATION_ID_CONFLICT",
                    "a released observation_id cannot change its meaning",
                )
            sequence_record = self._records_by_sequence.get(sequence)
            if sequence_record is not None:
                raise InteractionEngineViolation(
                    "OBSERVATION_SEQUENCE_CONFLICT",
                    "an accepted observation sequence cannot be rebound",
                )
            if sequence < self._next_observation_sequence:
                raise InteractionEngineViolation(
                    "STALE_OBSERVATION",
                    "released or unknown prior observations cannot be replayed",
                )
            if sequence > self._next_observation_sequence:
                raise InteractionEngineViolation(
                    "OBSERVATION_SEQUENCE_GAP",
                    "observations must advance one contiguous sequence",
                )
            if len(self._records_by_sequence) >= self._max_observations:
                raise InteractionEngineViolation(
                    "OBSERVATION_LEDGER_FULL",
                    "bounded Cascade observation ledger is full",
                )
            if len(self._observation_identities) >= self._max_observation_identities:
                raise InteractionEngineViolation(
                    "OBSERVATION_IDENTITY_LEDGER_FULL",
                    "bounded Cascade observation identity ledger is full",
                )
            mapped = _CASCADE_ACTION_BY_OBSERVATION.get(observation.kind)
            if mapped is None:
                raise InteractionEngineViolation(
                    "UNMAPPED_OBSERVATION_KIND",
                    "observation kind has no frozen Cascade intention",
                )
            operation = mapped.value
            if operation not in self._supported_actions:
                raise InteractionEngineViolation(
                    "CAPABILITY_UNSUPPORTED",
                    f"Cascade action {operation!r} is unsupported",
                )
            action = InteractionAction(
                action_id=_cascade_action_id(
                    canonical_scope, interaction_id, generation, sequence
                ),
                operation=operation,
                interaction_id=interaction_id,
                scope=canonical_scope,
                payload=(
                    ("observation_id", observation_id),
                    ("observation_kind", observation.kind.value),
                    ("observation_sequence", str(sequence)),
                    ("response_generation", str(generation)),
                    ("authority", "intention-only"),
                ),
            )
            record = _CascadeRecord(observation, action)
            self._records_by_id[observation_id] = record
            self._records_by_sequence[sequence] = record
            self._observation_identities[observation_id] = _CascadeIdentityBinding(
                observation_sequence=sequence,
                kind=observation.kind,
            )
            self._next_observation_sequence += 1
            return True, action

    def release_through(self, observation_sequence: int) -> int:
        cursor = _require_safe_integer(
            observation_sequence, "observation_sequence"
        )
        with self._lock:
            # An already-released cursor is a no-op at every state, including a
            # fresh engine where cursor 0 would otherwise read as "ahead".
            if cursor <= self._released_through:
                return 0
            if cursor >= self._next_observation_sequence:
                raise InteractionEngineViolation(
                    "RELEASE_CURSOR_AHEAD",
                    "release cursor cannot advance beyond accepted observations",
                )
            released = 0
            for sequence in tuple(self._records_by_sequence):
                if sequence > cursor:
                    continue
                record = self._records_by_sequence.pop(sequence)
                self._records_by_id.pop(record.observation.observation_id, None)
                released += 1
            self._released_through = cursor
            return released

    def retained_actions(self) -> tuple[InteractionAction, ...]:
        with self._lock:
            return tuple(
                self._records_by_sequence[sequence].action
                for sequence in sorted(self._records_by_sequence)
            )

    def snapshot(self) -> ScriptedCascadeSnapshot:
        with self._lock:
            retained = len(self._records_by_sequence)
            return ScriptedCascadeSnapshot(
                interaction_id=self._interaction_id,
                response_generation=self._response_generation,
                next_observation_sequence=self._next_observation_sequence,
                released_through=self._released_through,
                retained_observations=retained,
                retained_actions=retained,
                retained_observation_identities=len(self._observation_identities),
            )
