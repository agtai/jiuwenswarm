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
