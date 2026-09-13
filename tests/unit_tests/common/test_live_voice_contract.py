# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Conformance tests for the first shared Live Voice contract gate."""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.common.schema.live_voice_contract import (
    CONTRACT_VERSION,
    CancelScope,
    ContractValidationError,
    InputCommitState,
    SideEffectTarget,
    WorkProgressEvent,
    WorkProgressOutcome,
    WorkProgressState,
    parse_cancel_scope,
    require_committed_input,
)


def _progress_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "work_ref": "task:task-123",
        "provenance": "executor:event-456",
        "seq": 0,
        "state": "running",
    }
    payload.update(overrides)
    return payload


def test_contract_version_is_explicit_and_serialized() -> None:
    event = WorkProgressEvent(
        work_ref="round:round-1",
        provenance="harness:event-1",
        seq=0,
        state=WorkProgressState.ACCEPTED,
    )

    assert CONTRACT_VERSION == "live-voice.contract.v1"
    assert event.to_dict()["contract_version"] == CONTRACT_VERSION
    json.dumps(event.to_dict())


def test_cancel_scopes_are_exact_and_distinct() -> None:
    expected = {
        "playback.stop",
        "response.cancel",
        "round.cancel",
        "task.cancel",
    }

    values = [scope.value for scope in CancelScope]

    assert set(values) == expected
    assert len(values) == len(set(values)) == 4
    assert [parse_cancel_scope(value).value for value in values] == values


@pytest.mark.parametrize(
    "value",
    ["playback.cancel", "response.stop", "task.cancel ", "TASK.CANCEL", ""],
)
def test_cancel_scope_parser_does_not_normalize_or_widen(value: str) -> None:
    with pytest.raises(ContractValidationError, match="invalid cancel_scope"):
        parse_cancel_scope(value)


def test_work_progress_states_and_outcomes_are_exact() -> None:
    assert {state.value for state in WorkProgressState} == {
        "accepted",
        "running",
        "blocked",
        "decision_required",
        "terminal",
    }
    assert {outcome.value for outcome in WorkProgressOutcome} == {
        "completed",
        "failed",
        "cancelled",
        "interrupted",
        "unknown",
    }


def test_progress_rejects_unknown_state() -> None:
    with pytest.raises(ContractValidationError, match="invalid state 'done'"):
        WorkProgressEvent.from_dict(_progress_payload(state="done"))


@pytest.mark.parametrize("outcome", list(WorkProgressOutcome))
def test_terminal_progress_requires_and_round_trips_valid_outcome(
    outcome: WorkProgressOutcome,
) -> None:
    event = WorkProgressEvent.from_dict(
        _progress_payload(state="terminal", outcome=outcome.value)
    )

    assert event.state is WorkProgressState.TERMINAL
    assert event.outcome is outcome
    assert WorkProgressEvent.from_dict(event.to_dict()) == event


def test_terminal_progress_rejects_missing_outcome() -> None:
    with pytest.raises(
        ContractValidationError,
        match="terminal work progress requires a valid outcome",
    ):
        WorkProgressEvent.from_dict(_progress_payload(state="terminal"))


def test_terminal_progress_rejects_unknown_outcome() -> None:
    with pytest.raises(ContractValidationError, match="invalid outcome 'succeeded'"):
        WorkProgressEvent.from_dict(
            _progress_payload(state="terminal", outcome="succeeded")
        )


@pytest.mark.parametrize(
    "state",
    [
        WorkProgressState.ACCEPTED,
        WorkProgressState.RUNNING,
        WorkProgressState.BLOCKED,
        WorkProgressState.DECISION_REQUIRED,
    ],
)
def test_non_terminal_progress_forbids_fabricated_outcome(
    state: WorkProgressState,
) -> None:
    with pytest.raises(ContractValidationError, match="must not include outcome"):
        WorkProgressEvent(
            work_ref="task:task-123",
            provenance="executor:event-456",
            seq=1,
            state=state,
            outcome=WorkProgressOutcome.COMPLETED,
        )


@pytest.mark.parametrize("field", ["work_ref", "provenance"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_progress_requires_non_empty_work_ref_and_provenance(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ContractValidationError, match=field):
        WorkProgressEvent.from_dict(_progress_payload(**{field: value}))


@pytest.mark.parametrize("seq", [-1, True, 1.5, "1"])
def test_progress_requires_non_negative_integer_sequence(seq: object) -> None:
    with pytest.raises(ContractValidationError, match="non-negative integer"):
        WorkProgressEvent.from_dict(_progress_payload(seq=seq))


@pytest.mark.parametrize(
    "field",
    ["contract_version", "work_ref", "provenance", "seq", "state"],
)
def test_progress_rejects_missing_required_fields(field: str) -> None:
    payload = _progress_payload()
    del payload[field]

    with pytest.raises(
        ContractValidationError,
        match=rf"missing required field\(s\): {field}",
    ):
        WorkProgressEvent.from_dict(payload)


def test_progress_rejects_wrong_version_and_unknown_fields() -> None:
    with pytest.raises(ContractValidationError, match="unsupported contract_version"):
        WorkProgressEvent.from_dict(_progress_payload(contract_version="v2"))

    with pytest.raises(ContractValidationError, match="unknown field"):
        WorkProgressEvent.from_dict(_progress_payload(percent=50))


@pytest.mark.parametrize(
    "input_state",
    [InputCommitState.PARTIAL, InputCommitState.UNCOMMITTED],
)
@pytest.mark.parametrize("target", list(SideEffectTarget))
def test_partial_and_uncommitted_input_cannot_trigger_side_effects(
    input_state: InputCommitState,
    target: SideEffectTarget,
) -> None:
    with pytest.raises(
        ContractValidationError,
        match=rf"{target.value} side effects require input_state='committed'",
    ):
        require_committed_input(input_state, side_effect=target)


@pytest.mark.parametrize("target", list(SideEffectTarget))
def test_committed_input_can_cross_each_side_effect_boundary(
    target: SideEffectTarget,
) -> None:
    require_committed_input("committed", side_effect=target.value)


def test_commit_gate_rejects_unknown_state_and_target() -> None:
    with pytest.raises(ContractValidationError, match="invalid input_state"):
        require_committed_input("final", side_effect="agent")

    with pytest.raises(ContractValidationError, match="invalid side_effect"):
        require_committed_input("committed", side_effect="network")
