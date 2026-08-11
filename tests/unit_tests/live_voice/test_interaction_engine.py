# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.interaction_engine import (
    InteractionAction,
    InteractionEnginePort,
    InteractionEngineViolation,
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
