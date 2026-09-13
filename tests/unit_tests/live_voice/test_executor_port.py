# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.executor_port import (
    ExecutorPort,
    ExecutorPortViolation,
    ExecutorState,
)
from jiuwenswarm.server.live_voice.task_core import DispatchIntent, TaskSpec


def intent(instruction: str = "work") -> DispatchIntent:
    return DispatchIntent(
        "task-1",
        "attempt-1",
        "command-1",
        ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED),
        TaskSpec("name", instruction),
    )


def test_duplicate_delivery_is_idempotent_and_status_truthful() -> None:
    port = ExecutorPort()
    capabilities = port.capabilities()
    assert capabilities.supports_start is True
    assert capabilities.supports_status is True
    assert capabilities.supports_cancel_ack is True
    assert capabilities.supports_restart_recovery is False
    accepted, status = port.dispatch(intent())
    assert accepted is True
    assert status.state is ExecutorState.ACCEPTED
    accepted, replay = port.dispatch(intent())
    assert accepted is False
    assert replay == status
    running = port.start("attempt-1")
    assert running.state is ExecutorState.RUNNING
    terminal = port.finish("attempt-1", TerminalOutcome.COMPLETED)
    assert terminal.state is ExecutorState.TERMINAL
    assert terminal.outcome is TerminalOutcome.COMPLETED


def test_cancel_ack_is_not_terminal_and_unknown_is_none() -> None:
    port = ExecutorPort()
    assert port.status("unknown") is None
    port.dispatch(intent())
    status = port.cancel("attempt-1")
    assert status.cancel_acknowledged is True
    assert status.state is ExecutorState.ACCEPTED
    assert status.outcome is None


def test_conflicting_delivery_has_no_replacement() -> None:
    port = ExecutorPort()
    port.dispatch(intent())
    with pytest.raises(ExecutorPortViolation) as raised:
        port.dispatch(intent("changed"))
    assert raised.value.reason == "ATTEMPT_DELIVERY_CONFLICT"
    assert port.status("attempt-1").state is ExecutorState.ACCEPTED
