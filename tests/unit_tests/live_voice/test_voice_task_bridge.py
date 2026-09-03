# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    InputCommitState,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import (
    TaskIntent,
    VoiceTaskBridge,
    VoiceTaskBridgeViolation,
)


SCOPE = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)


def create_intent(**overrides) -> TaskIntent:
    values = {
        "state": InputCommitState.COMMITTED,
        "operation": "task.create",
        "request_id": "request-1",
        "command_id": "command-1",
        "scope": SCOPE,
        "origin_commit_id": "commit-1",
        "name": "inventory",
        "instruction": "check inventory",
    }
    values.update(overrides)
    return TaskIntent(**values)


def test_committed_create_maps_to_command_without_executing_task() -> None:
    bridge = VoiceTaskBridge()
    command = bridge.map(create_intent(), SCOPE)
    assert command.operation == "task.create"
    assert command.spec.name == "inventory"
    assert command.target_task_id is None
    assert not hasattr(bridge, "task_store")
    assert not hasattr(bridge, "tts")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"state": InputCommitState.PARTIAL}, "INPUT_NOT_COMMITTED"),
        ({"state": InputCommitState.UNCOMMITTED}, "INPUT_NOT_COMMITTED"),
        ({"ambiguous": True}, "TASK_INTENT_AMBIGUOUS"),
        ({"destructive": True}, "TASK_CONFIRMATION_REQUIRED"),
        ({"origin_commit_id": None}, "COMMITTED_ORIGIN_REQUIRED"),
    ],
)
def test_unsafe_intents_reject_before_command(changes, reason) -> None:
    bridge = VoiceTaskBridge()
    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        bridge.map(create_intent(**changes), SCOPE)
    assert raised.value.reason == reason


def test_cross_scope_and_inexact_cancel_reject() -> None:
    bridge = VoiceTaskBridge()
    foreign = ScopeRef("other", "project", "session", Assurance.AUTHENTICATED)
    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        bridge.map(create_intent(scope=foreign), SCOPE)
    assert raised.value.reason == "TASK_SCOPE_MISMATCH"
    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        bridge.map(
            create_intent(
                operation="task.cancel", name=None, instruction=None, task_id=None
            ),
            SCOPE,
        )
    assert raised.value.reason == "EXACT_TASK_REQUIRED"


def test_confirmed_exact_cancel_maps_without_terminal_claim() -> None:
    command = VoiceTaskBridge().map(
        create_intent(
            operation="task.cancel",
            task_id="task-1",
            name=None,
            instruction=None,
            destructive=True,
            confirmed=True,
        ),
        SCOPE,
    )
    assert command.operation == "task.cancel"
    assert command.target_task_id == "task-1"
    assert command.spec is None
