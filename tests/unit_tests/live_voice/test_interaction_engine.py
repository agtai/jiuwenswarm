# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.interaction_engine import (
    CASCADE_ACTION_OPERATIONS,
    CASCADE_GOLDEN_SCRIPT,
    CascadeActionOperation,
    CascadeObservation,
    CascadeObservationKind,
    InteractionAction,
    InteractionEnginePort,
    InteractionEngineViolation,
    INTERACTION_ACTION_OPERATIONS,
    ScriptedCascadeInteractionEngine,
)


def test_native_and_cascade_share_one_closed_action_vocabulary() -> None:
    assert INTERACTION_ACTION_OPERATIONS == frozenset(
        {"LISTEN", "SILENCE", "TURN_COMMIT", "SPEAK", "STOP", "REVISE", "DELEGATE"}
    )


_CASCADE_SCOPE = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)
_CASCADE_GOLDEN_ORACLE = (
    ("speech.started", "LISTEN"),
    ("speech.partial", "LISTEN"),
    ("speech.silence", "SILENCE"),
    ("speech.end_of_turn", "TURN_COMMIT"),
    ("response.delta", "SPEAK"),
    ("speech.barge_in_confirmed", "STOP"),
    ("interaction.revision_requested", "REVISE"),
    ("interaction.delegation_requested", "DELEGATE"),
    ("speech.echo_rejected", "SILENCE"),
    ("speech.double_talk_rejected", "LISTEN"),
)


def _observation(
    sequence: int,
    kind: CascadeObservationKind,
    *,
    observation_id: str | None = None,
    interaction_id: str = "interaction-1",
    generation: int = 7,
    scope: ScopeRef = _CASCADE_SCOPE,
) -> CascadeObservation:
    return CascadeObservation(
        observation_id or f"observation-{sequence}",
        sequence,
        interaction_id,
        generation,
        scope,
        kind,
    )


def test_capability_checked_action_is_immutable_and_idempotent() -> None:
    scope = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)
    port = InteractionEnginePort(frozenset({"interaction.respond"}))
    action = InteractionAction(
        "action-1", "interaction.respond", "interaction-1", scope, (("tone", "brief"),)
    )
    assert port.propose(action) == (True, action)
    assert port.propose(action) == (False, action)
    assert port.accepted() == (action,)


def test_unsupported_and_conflicting_actions_have_zero_new_effects() -> None:
    scope = ScopeRef("subject", None, "session", Assurance.AUTHENTICATED)
    port = InteractionEnginePort(frozenset({"interaction.respond"}))
    with pytest.raises(InteractionEngineViolation) as raised:
        port.propose(InteractionAction("a", "task.create", "i", scope))
    assert raised.value.reason == "CAPABILITY_UNSUPPORTED"
    assert port.accepted() == ()
    port.propose(InteractionAction("a", "interaction.respond", "i", scope))
    with pytest.raises(InteractionEngineViolation) as raised:
        port.propose(InteractionAction("a", "interaction.respond", "other", scope))
    assert raised.value.reason == "ACTION_ID_CONFLICT"
    assert len(port.accepted()) == 1


def test_exact_scope_and_bounded_action_ledger_fail_closed() -> None:
    exact = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)
    other = ScopeRef("subject", "other", "session", Assurance.AUTHENTICATED)
    port = InteractionEnginePort(
        frozenset({"interaction.barge_in"}), scope=exact, max_actions=1
    )

    with pytest.raises(InteractionEngineViolation) as wrong_scope:
        port.propose(
            InteractionAction("action-wrong", "interaction.barge_in", "i", other)
        )
    assert wrong_scope.value.reason == "ACTION_SCOPE_MISMATCH"
    assert port.accepted() == ()

    first = InteractionAction("action-1", "interaction.barge_in", "i", exact)
    assert port.propose(first) == (True, first)
    assert port.propose(first) == (False, first)
    with pytest.raises(InteractionEngineViolation) as full:
        port.propose(InteractionAction("action-2", "interaction.barge_in", "i", exact))
    assert full.value.reason == "ACTION_LEDGER_FULL"
    assert port.accepted() == (first,)


@pytest.mark.parametrize(
    ("operations", "scope", "max_actions", "reason"),
    [
        ({"interaction.barge_in"}, None, 1, "INVALID_CAPABILITIES"),
        (frozenset({"interaction.barge_in"}), object(), 1, "INVALID_SCOPE"),
        (frozenset({"interaction.barge_in"}), None, True, "INVALID_CAPACITY"),
        (frozenset({" interaction.barge_in"}), None, 1, "INVALID_CAPABILITIES"),
        (frozenset({"x" * 129}), None, 1, "INVALID_CAPABILITIES"),
        (
            frozenset(f"operation.{index}" for index in range(65)),
            None,
            1,
            "INVALID_CAPABILITIES",
        ),
        (frozenset({"interaction.barge_in"}), None, 1025, "INVALID_CAPACITY"),
        (
            frozenset({"interaction.barge_in"}),
            ScopeRef(" subject", None, "session", Assurance.AUTHENTICATED),
            1,
            "INVALID_SCOPE",
        ),
    ],
)
def test_invalid_leaf_configuration_has_zero_action_effects(
    operations: object, scope: object, max_actions: object, reason: str
) -> None:
    with pytest.raises(InteractionEngineViolation) as invalid:
        InteractionEnginePort(
            operations,  # type: ignore[arg-type]
            scope=scope,  # type: ignore[arg-type]
            max_actions=max_actions,  # type: ignore[arg-type]
        )
    assert invalid.value.reason == reason


@pytest.mark.parametrize(
    ("action", "reason"),
    [
        (
            InteractionAction(
                "action",
                [],  # type: ignore[arg-type]
                "interaction",
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
            ),
            "INVALID_ACTION",
        ),
        (
            InteractionAction(
                " action",
                "interaction.respond",
                "interaction",
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
            ),
            "INVALID_ACTION_IDENTITY",
        ),
        (
            InteractionAction(
                "action",
                "interaction.respond",
                "i" * 257,
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
            ),
            "INVALID_ACTION_IDENTITY",
        ),
        (
            InteractionAction(
                "action",
                " interaction.respond",
                "interaction",
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
            ),
            "INVALID_ACTION",
        ),
        (
            InteractionAction(
                "action",
                "interaction.respond",
                "interaction",
                ScopeRef("subject ", None, "session", Assurance.AUTHENTICATED),
            ),
            "INVALID_SCOPE",
        ),
        (
            InteractionAction(
                "action",
                "interaction.respond",
                "interaction",
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
                tuple((f"key-{index}", "value") for index in range(33)),
            ),
            "INVALID_ACTION",
        ),
        (
            InteractionAction(
                "action",
                "interaction.respond",
                "interaction",
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
                ((" key", "value"),),
            ),
            "INVALID_ACTION",
        ),
        (
            InteractionAction(
                "action",
                "interaction.respond",
                "interaction",
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
                (("k" * 129, "value"),),
            ),
            "INVALID_ACTION",
        ),
        (
            InteractionAction(
                "action",
                "interaction.respond",
                "interaction",
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
                (("key", "v" * 1025),),
            ),
            "INVALID_ACTION",
        ),
        (
            InteractionAction(
                "action",
                "interaction.respond",
                "interaction",
                ScopeRef("subject", None, "session", "authenticated"),  # type: ignore[arg-type]
            ),
            "INVALID_SCOPE",
        ),
        (
            InteractionAction(
                "action",
                "interaction.respond",
                "interaction",
                ScopeRef("subject", None, "session", Assurance.AUTHENTICATED),
                [["key", "value"]],  # type: ignore[arg-type,list-item]
            ),
            "INVALID_ACTION",
        ),
    ],
)
def test_malformed_action_has_zero_effects(
    action: InteractionAction, reason: str
) -> None:
    port = InteractionEnginePort(frozenset({"interaction.respond"}))
    with pytest.raises(InteractionEngineViolation) as invalid:
        port.propose(action)
    assert invalid.value.reason == reason
    assert port.accepted() == ()


def test_practical_identity_and_payload_boundaries_remain_accepted() -> None:
    operation = "o" * 128
    exact = ScopeRef(
        "s" * 256,
        "p" * 256,
        "n" * 256,
        Assurance.AUTHENTICATED,
    )
    port = InteractionEnginePort(frozenset({operation}), scope=exact, max_actions=1024)
    action = InteractionAction(
        "a" * 256,
        operation,
        "i" * 256,
        exact,
        tuple(("k" * 128, "v" * 1024) for _ in range(32)),
    )
    assert port.propose(action) == (True, action)
    assert port.propose(action) == (False, action)
    assert port.accepted() == (action,)


def test_scripted_cascade_golden_conformance_freezes_every_intention() -> None:
    assert CASCADE_ACTION_OPERATIONS == frozenset(
        {
            "LISTEN",
            "SILENCE",
            "TURN_COMMIT",
            "SPEAK",
            "STOP",
            "REVISE",
            "DELEGATE",
        }
    )
    assert (
        tuple(
            (observation.value, action.value)
            for observation, action in CASCADE_GOLDEN_SCRIPT
        )
        == _CASCADE_GOLDEN_ORACLE
    )
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
    )
    port = InteractionEnginePort(CASCADE_ACTION_OPERATIONS, scope=_CASCADE_SCOPE)

    actions = []
    for sequence, (observation_value, expected_operation) in enumerate(
        _CASCADE_GOLDEN_ORACLE, start=1
    ):
        observation_kind = CascadeObservationKind(observation_value)
        accepted, action = engine.observe(_observation(sequence, observation_kind))
        assert accepted is True
        assert action.operation == expected_operation
        assert action.interaction_id == "interaction-1"
        assert action.scope == _CASCADE_SCOPE
        assert dict(action.payload) == {
            "observation_id": f"observation-{sequence}",
            "observation_kind": observation_kind.value,
            "observation_sequence": str(sequence),
            "response_generation": "7",
            "authority": "intention-only",
        }
        assert port.propose(action) == (True, action)
        actions.append(action)

    assert engine.retained_actions() == tuple(actions)
    assert port.accepted() == tuple(actions)
    snapshot = engine.snapshot()
    assert snapshot.next_observation_sequence == len(actions) + 1
    assert snapshot.retained_observation_identities == len(actions)


def test_partial_echo_and_rejected_double_talk_never_commit_or_stop() -> None:
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
    )
    kinds = (
        CascadeObservationKind.PARTIAL_TRANSCRIPT,
        CascadeObservationKind.ECHO_REJECTED,
        CascadeObservationKind.DOUBLE_TALK_REJECTED,
    )

    actions = tuple(
        engine.observe(_observation(sequence, kind))[1]
        for sequence, kind in enumerate(kinds, start=1)
    )

    assert tuple(action.operation for action in actions) == (
        CascadeActionOperation.LISTEN.value,
        CascadeActionOperation.SILENCE.value,
        CascadeActionOperation.LISTEN.value,
    )
    assert all(
        action.operation
        not in {
            CascadeActionOperation.TURN_COMMIT.value,
            CascadeActionOperation.STOP.value,
        }
        for action in actions
    )


def test_exact_duplicate_replays_but_sequence_gap_fails_closed() -> None:
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
    )
    first = _observation(1, CascadeObservationKind.SPEECH_STARTED)
    accepted, action = engine.observe(first)
    assert accepted is True
    assert engine.observe(first) == (False, action)

    with pytest.raises(InteractionEngineViolation) as sequence_gap:
        engine.observe(_observation(3, CascadeObservationKind.END_OF_TURN))
    assert sequence_gap.value.reason == "OBSERVATION_SEQUENCE_GAP"
    assert engine.retained_actions() == (action,)
    assert engine.snapshot().next_observation_sequence == 2


@pytest.mark.parametrize(
    ("scope", "interaction_id", "generation", "sequence"),
    [
        (
            ScopeRef("subject", "other-project", "session", Assurance.AUTHENTICATED),
            "interaction-1",
            7,
            1,
        ),
        (_CASCADE_SCOPE, "interaction-2", 7, 1),
        (_CASCADE_SCOPE, "interaction-1", 8, 1),
        (_CASCADE_SCOPE, "interaction-1", 7, 2),
    ],
    ids=("scope", "interaction", "generation", "sequence"),
)
def test_action_id_collision_resistance_covers_every_binding_dimension(
    scope: ScopeRef, interaction_id: str, generation: int, sequence: int
) -> None:
    def action_for(
        exact_scope: ScopeRef,
        exact_interaction_id: str,
        exact_generation: int,
        target_sequence: int,
    ) -> InteractionAction:
        engine = ScriptedCascadeInteractionEngine(
            scope=exact_scope,
            interaction_id=exact_interaction_id,
            response_generation=exact_generation,
        )
        action: InteractionAction | None = None
        for item_sequence in range(1, target_sequence + 1):
            _, action = engine.observe(
                _observation(
                    item_sequence,
                    CascadeObservationKind.SPEECH_STARTED,
                    observation_id=f"observation-{item_sequence}",
                    interaction_id=exact_interaction_id,
                    generation=exact_generation,
                    scope=exact_scope,
                )
            )
        assert action is not None
        return action

    baseline = action_for(_CASCADE_SCOPE, "interaction-1", 7, 1)
    variant = action_for(scope, interaction_id, generation, sequence)

    assert variant.action_id != baseline.action_id


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [
        (
            replace(
                _observation(1, CascadeObservationKind.SPEECH_STARTED),
                kind=CascadeObservationKind.END_OF_TURN,
            ),
            "OBSERVATION_ID_CONFLICT",
        ),
        (
            replace(
                _observation(1, CascadeObservationKind.SPEECH_STARTED),
                observation_id="different-observation",
            ),
            "OBSERVATION_SEQUENCE_CONFLICT",
        ),
        (
            replace(
                _observation(1, CascadeObservationKind.SPEECH_STARTED),
                observation_id="different-observation",
                kind=CascadeObservationKind.END_OF_TURN,
            ),
            "OBSERVATION_SEQUENCE_CONFLICT",
        ),
    ],
    ids=("kind", "identity", "identity-and-kind"),
)
def test_same_binding_and_sequence_cannot_rebind_identity_or_kind(
    replacement: CascadeObservation, reason: str
) -> None:
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
    )
    first = _observation(1, CascadeObservationKind.SPEECH_STARTED)
    _, action = engine.observe(first)

    with pytest.raises(InteractionEngineViolation) as conflict:
        engine.observe(replacement)

    assert conflict.value.reason == reason
    assert engine.retained_actions() == (action,)
    assert engine.snapshot().next_observation_sequence == 2


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (
            _observation(
                1,
                CascadeObservationKind.SPEECH_STARTED,
                scope=ScopeRef(
                    "subject", "other-project", "session", Assurance.AUTHENTICATED
                ),
            ),
            "OBSERVATION_SCOPE_MISMATCH",
        ),
        (
            _observation(
                1,
                CascadeObservationKind.SPEECH_STARTED,
                interaction_id="other-interaction",
            ),
            "OBSERVATION_INTERACTION_MISMATCH",
        ),
        (
            _observation(1, CascadeObservationKind.SPEECH_STARTED, generation=6),
            "STALE_RESPONSE_GENERATION",
        ),
        (
            _observation(1, CascadeObservationKind.SPEECH_STARTED, generation=8),
            "RESPONSE_GENERATION_MISMATCH",
        ),
    ],
)
def test_wrong_binding_and_stale_generation_have_zero_authority_effects(
    observation: CascadeObservation, reason: str
) -> None:
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
    )

    with pytest.raises(InteractionEngineViolation) as rejected:
        engine.observe(observation)

    assert rejected.value.reason == reason
    # This fake has no authority collaborators; a retained intention is its only
    # possible externally consumable output.
    assert engine.retained_actions() == ()
    snapshot = engine.snapshot()
    assert snapshot.next_observation_sequence == 1
    assert snapshot.released_through == 0
    assert snapshot.retained_observations == 0
    assert snapshot.retained_actions == 0
    assert snapshot.retained_observation_identities == 0


def test_bounded_replay_release_reuses_capacity_without_reopening_stale_input() -> None:
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
        max_observations=2,
    )
    first = _observation(1, CascadeObservationKind.SPEECH_STARTED)
    second = _observation(2, CascadeObservationKind.SILENCE_OBSERVED)
    third = _observation(3, CascadeObservationKind.END_OF_TURN)
    engine.observe(first)
    _, second_action = engine.observe(second)

    with pytest.raises(InteractionEngineViolation) as full:
        engine.observe(third)
    assert full.value.reason == "OBSERVATION_LEDGER_FULL"
    assert engine.snapshot().next_observation_sequence == 3

    assert engine.release_through(1) == 1
    assert engine.release_through(1) == 0
    released_snapshot = engine.snapshot()
    assert released_snapshot.retained_observations == 1
    assert released_snapshot.retained_observation_identities == 2
    with pytest.raises(InteractionEngineViolation) as stale:
        engine.observe(first)
    assert stale.value.reason == "STALE_OBSERVATION"
    with pytest.raises(InteractionEngineViolation) as stale_sequence:
        engine.observe(replace(first, observation_id="fresh-replay-id"))
    assert stale_sequence.value.reason == "STALE_OBSERVATION"
    for rebound_kind in (
        CascadeObservationKind.SPEECH_STARTED,
        CascadeObservationKind.END_OF_TURN,
    ):
        with pytest.raises(InteractionEngineViolation) as rebound_identity:
            engine.observe(
                replace(
                    first,
                    observation_sequence=3,
                    kind=rebound_kind,
                )
            )
        assert rebound_identity.value.reason == "OBSERVATION_ID_CONFLICT"
    assert engine.snapshot().next_observation_sequence == 3

    _, third_action = engine.observe(third)
    assert engine.retained_actions() == (second_action, third_action)
    snapshot = engine.snapshot()
    assert snapshot.released_through == 1
    assert snapshot.retained_observation_identities == 3
    with pytest.raises(InteractionEngineViolation) as ahead:
        engine.release_through(4)
    assert ahead.value.reason == "RELEASE_CURSOR_AHEAD"
    assert engine.retained_actions() == (second_action, third_action)


def test_released_identity_tombstones_are_bounded_and_fail_closed() -> None:
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
        max_observations=1,
        max_observation_identities=3,
    )

    for sequence in range(1, 4):
        engine.observe(_observation(sequence, CascadeObservationKind.SPEECH_STARTED))
        assert engine.release_through(sequence) == 1

    snapshot = engine.snapshot()
    assert snapshot.next_observation_sequence == 4
    assert snapshot.released_through == 3
    assert snapshot.retained_observations == 0
    assert snapshot.retained_actions == 0
    assert snapshot.retained_observation_identities == 3

    with pytest.raises(InteractionEngineViolation) as full:
        engine.observe(_observation(4, CascadeObservationKind.SPEECH_STARTED))
    assert full.value.reason == "OBSERVATION_IDENTITY_LEDGER_FULL"
    assert engine.snapshot() == snapshot


def test_every_observation_kind_has_one_frozen_intention() -> None:
    """A kind with no scripted intention would escape as an uncaught KeyError.

    The lookup is guarded and the module refuses to import when the script is
    incomplete, so this pins the completeness the guard depends on.
    """

    assert {kind for kind, _ in CASCADE_GOLDEN_SCRIPT} == set(CascadeObservationKind)


def test_release_cursor_zero_is_a_no_op_at_every_engine_state() -> None:
    """An already-released cursor never raises, including on a fresh engine."""

    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
    )
    assert engine.release_through(0) == 0
    engine.observe(_observation(1, CascadeObservationKind.SPEECH_STARTED))
    assert engine.release_through(0) == 0
    assert engine.snapshot().released_through == 0
    assert engine.snapshot().retained_observations == 1


def test_unsupported_cascade_capability_is_fail_closed_and_consumes_no_sequence() -> (
    None
):
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
        supported_actions=frozenset({CascadeActionOperation.LISTEN.value}),
    )

    with pytest.raises(InteractionEngineViolation) as unsupported:
        engine.observe(_observation(1, CascadeObservationKind.END_OF_TURN))
    assert unsupported.value.reason == "CAPABILITY_UNSUPPORTED"
    assert engine.retained_actions() == ()
    assert engine.snapshot().next_observation_sequence == 1

    accepted, action = engine.observe(
        _observation(1, CascadeObservationKind.PARTIAL_TRANSCRIPT)
    )
    assert accepted is True
    assert action.operation == CascadeActionOperation.LISTEN.value


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"supported_actions": {"LISTEN"}}, "INVALID_CASCADE_CAPABILITIES"),
        (
            {"supported_actions": frozenset({"ROUND_CANCEL"})},
            "INVALID_CASCADE_CAPABILITIES",
        ),
        ({"max_observations": True}, "INVALID_OBSERVATION_CAPACITY"),
        ({"max_observations": 1025}, "INVALID_OBSERVATION_CAPACITY"),
        (
            {"max_observation_identities": True},
            "INVALID_OBSERVATION_IDENTITY_CAPACITY",
        ),
        (
            {"max_observation_identities": 1025},
            "INVALID_OBSERVATION_IDENTITY_CAPACITY",
        ),
        (
            {"max_observations": 2, "max_observation_identities": 1},
            "INVALID_OBSERVATION_IDENTITY_CAPACITY",
        ),
        ({"response_generation": -1}, "INVALID_OBSERVATION_CURSOR"),
        ({"interaction_id": " interaction"}, "INVALID_OBSERVATION_IDENTITY"),
    ],
)
def test_invalid_scripted_cascade_configuration_has_zero_actions(
    kwargs: dict[str, object], reason: str
) -> None:
    values: dict[str, object] = {
        "scope": _CASCADE_SCOPE,
        "interaction_id": "interaction-1",
        "response_generation": 7,
    }
    values.update(kwargs)
    with pytest.raises(InteractionEngineViolation) as invalid:
        ScriptedCascadeInteractionEngine(**values)  # type: ignore[arg-type]
    assert invalid.value.reason == reason


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (object(), "INVALID_OBSERVATION"),
        (
            replace(
                _observation(1, CascadeObservationKind.SPEECH_STARTED),
                observation_id=" observation",
            ),
            "INVALID_OBSERVATION_IDENTITY",
        ),
        (
            replace(
                _observation(1, CascadeObservationKind.SPEECH_STARTED),
                observation_sequence=True,
            ),
            "INVALID_OBSERVATION_CURSOR",
        ),
        (
            replace(
                _observation(1, CascadeObservationKind.SPEECH_STARTED),
                kind="speech.started",  # type: ignore[arg-type]
            ),
            "INVALID_OBSERVATION_KIND",
        ),
    ],
)
def test_malformed_observation_has_zero_retained_intentions(
    observation: object, reason: str
) -> None:
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
    )

    with pytest.raises(InteractionEngineViolation) as invalid:
        engine.observe(observation)  # type: ignore[arg-type]

    assert invalid.value.reason == reason
    assert engine.retained_actions() == ()
    assert engine.snapshot().next_observation_sequence == 1


def test_concurrent_exact_observation_proposes_one_intention() -> None:
    engine = ScriptedCascadeInteractionEngine(
        scope=_CASCADE_SCOPE,
        interaction_id="interaction-1",
        response_generation=7,
    )
    observation = _observation(1, CascadeObservationKind.SPEECH_STARTED)

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = tuple(executor.map(lambda _: engine.observe(observation), range(32)))

    assert sum(accepted for accepted, _ in outcomes) == 1
    assert len({action for _, action in outcomes}) == 1
    assert engine.retained_actions() == (outcomes[0][1],)
    assert engine.snapshot().next_observation_sequence == 2
