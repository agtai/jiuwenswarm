# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Retained conformance implementation; never a production execution owner."""

from __future__ import annotations

import threading
from jiuwenswarm.common.schema.live_voice_contract_v2 import ScopeRef
from jiuwenswarm.server.live_voice.interaction_engine import (
    CASCADE_ACTION_OPERATIONS,
    CascadeObservation,
    CascadeObservationKind,
    InteractionAction,
    InteractionEngineViolation,
    ScriptedCascadeSnapshot,
    _CASCADE_ACTION_BY_OBSERVATION,
    _CascadeIdentityBinding,
    _CascadeRecord,
    _MAX_OBSERVATIONS,
    _canonical_scope,
    _cascade_action_id,
    _require_canonical_identity,
    _require_safe_integer,
)


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
        if type(max_observation_identities) is not int or not (
            max_observations <= max_observation_identities <= _MAX_OBSERVATIONS
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
        cursor = _require_safe_integer(observation_sequence, "observation_sequence")
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
