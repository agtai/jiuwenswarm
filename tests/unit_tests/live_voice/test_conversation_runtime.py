# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContractViolation,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.conversation_runtime import (
    CancelState,
    ConversationRuntime,
    ConversationRuntimeViolation,
    InteractionState,
    ResponseState,
)


FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "live_voice_a_packages"
    / "conversation_runtime.json"
)


def scope() -> ScopeRef:
    return ScopeRef("subject-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def commit(*, commit_id: str = "commit-1", text: str = "do the work") -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": commit_id,
            "turn_id": "turn-1",
            "interaction_id": "interaction-1",
            "text": text,
            "hypothesis_provenance": {"provider": "fake-sr", "seq": 1},
            "scope": scope().to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-04T08:00:00Z",
        }
    )


def prepared() -> ConversationRuntime:
    runtime = ConversationRuntime(scope())
    runtime.open_interaction("interaction-1")
    runtime.start_turn("interaction-1", "turn-1")
    accepted, _ = runtime.commit_turn(commit())
    assert accepted is True
    return runtime


def test_server_events_match_shared_replica_fixture() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    runtime = prepared()
    ref, _ = runtime.accept_response("turn-1", "response-1")
    runtime.transition_response(ref, ResponseState.GENERATING)
    runtime.transition_response(ref, ResponseState.SPEAKING)
    runtime.transition_response(
        ref, ResponseState.TERMINAL, outcome=TerminalOutcome.COMPLETED
    )
    runtime.transition_interaction("interaction-1", InteractionState.CLOSED)

    assert [event.to_dict() for event in runtime.events()] == fixture["events"]
    snapshot = runtime.snapshot()
    assert (
        snapshot.interactions[0].state.value == fixture["expected"]["interaction_state"]
    )
    assert snapshot.turns[0].state.value == fixture["expected"]["turn_state"]
    assert snapshot.responses[0].state.value == fixture["expected"]["response_state"]
    assert snapshot.responses[0].outcome is TerminalOutcome.COMPLETED


def test_turn_commit_is_once_only_and_concurrent_safe() -> None:
    runtime = ConversationRuntime(scope())
    runtime.open_interaction("interaction-1")
    runtime.start_turn("interaction-1", "turn-1")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: runtime.commit_turn(commit())[0], range(24)))
    assert results.count(True) == 1
    assert results.count(False) == 23
    assert (
        len(
            [
                event
                for event in runtime.events()
                if event.event_type == "turn.committed"
            ]
        )
        == 1
    )

    with pytest.raises(ContractViolation) as raised:
        runtime.commit_turn(commit(text="changed"))
    assert raised.value.reason == "TURN_COMMIT_CONFLICT"


def test_replacement_fences_old_output_and_generation_increases() -> None:
    runtime = prepared()
    first, _ = runtime.accept_response("turn-1", "response-1")
    assert runtime.apply_output(first, "audio.enqueue").response_id == "response-1"
    second, _ = runtime.accept_response("turn-1", "response-2")
    assert second.response_generation == first.response_generation + 1
    with pytest.raises(ContractViolation) as raised:
        runtime.apply_output(first, "history.append")
    assert raised.value.reason == "STALE_RESPONSE_OUTPUT"
    assert runtime.apply_output(second, "ui.render").response_id == "response-2"


def test_cancel_acknowledgement_is_not_terminal_and_has_no_task_effect() -> None:
    runtime = prepared()
    ref, _ = runtime.accept_response("turn-1", "response-1")
    runtime.transition_response(ref, ResponseState.GENERATING)
    _, effect = runtime.request_response_cancel(ref)
    event = runtime.acknowledge_response_cancel(ref)
    record = runtime.snapshot().responses[0]

    assert effect.effect_type == "response.cancel"
    assert event.event_type == "response.cancel_acknowledged"
    assert record.cancel_state is CancelState.ACKNOWLEDGED
    assert record.state is ResponseState.GENERATING
    assert all("task" not in item.effect_type for item in [effect])


def test_late_cancel_ack_reconciles_unknown_without_timeout_downgrade() -> None:
    runtime = prepared()
    ref, _ = runtime.accept_response("turn-1", "response-1")
    runtime.transition_response(ref, ResponseState.GENERATING)
    runtime.request_response_cancel(ref)
    unknown = runtime.mark_response_cancel_unknown(ref)
    acknowledged = runtime.acknowledge_response_cancel(ref)

    assert unknown is not None
    assert unknown.event_type == "response.cancel_result_unknown"
    assert acknowledged is not None
    assert acknowledged.event_type == "response.cancel_acknowledged"
    assert runtime.mark_response_cancel_unknown(ref) is None
    assert runtime.acknowledge_response_cancel(ref) is None
    record = runtime.snapshot().responses[0]
    assert record.cancel_state is CancelState.ACKNOWLEDGED
    assert record.state is ResponseState.GENERATING


def test_illegal_transitions_and_wrong_response_tuple_fail_closed() -> None:
    runtime = prepared()
    ref, _ = runtime.accept_response("turn-1", "response-1")
    before = runtime.fingerprint()
    with pytest.raises(ContractViolation):
        runtime.transition_response(ref, ResponseState.SPEAKING)
    assert runtime.fingerprint() == before

    stale = ResponseRef(
        ref.interaction_id, ref.response_id, ref.response_generation + 1
    )
    with pytest.raises(ConversationRuntimeViolation) as raised:
        runtime.request_response_cancel(stale)
    assert raised.value.reason == "STALE_RESPONSE_REFERENCE"
    assert runtime.fingerprint() == before


def test_disabled_runtime_has_zero_state_and_effects() -> None:
    runtime = ConversationRuntime(scope(), enabled=False)
    with pytest.raises(ConversationRuntimeViolation) as raised:
        runtime.open_interaction("interaction-1")
    assert raised.value.reason == "FEATURE_DISABLED"
    assert runtime.snapshot().last_seq == 0
    assert runtime.snapshot().interactions == ()


def test_closed_interaction_cannot_accept_a_new_response() -> None:
    runtime = prepared()
    runtime.transition_interaction("interaction-1", InteractionState.CLOSED)
    before = runtime.fingerprint()
    with pytest.raises(ConversationRuntimeViolation) as raised:
        runtime.accept_response("turn-1", "response-1")
    assert raised.value.reason == "INTERACTION_NOT_OPEN"
    assert runtime.fingerprint() == before


def test_fenced_old_response_can_record_terminal_without_output() -> None:
    runtime = prepared()
    first, _ = runtime.accept_response("turn-1", "response-1")
    runtime.transition_response(first, ResponseState.GENERATING)
    second, _ = runtime.accept_response("turn-1", "response-2")
    runtime.transition_response(
        first, ResponseState.TERMINAL, outcome=TerminalOutcome.INTERRUPTED
    )
    assert runtime.snapshot().responses[0].outcome is TerminalOutcome.INTERRUPTED
    with pytest.raises(ContractViolation):
        runtime.apply_output(first, "audio.enqueue")
    assert runtime.apply_output(second, "audio.enqueue").response_id == "response-2"


def test_interaction_close_fences_output_without_task_cancel() -> None:
    runtime = prepared()
    ref, _ = runtime.accept_response("turn-1", "response-1")
    runtime.transition_interaction("interaction-1", InteractionState.CLOSED)
    with pytest.raises(ContractViolation) as raised:
        runtime.apply_output(ref, "audio.enqueue")
    assert raised.value.reason == "STALE_RESPONSE_OUTPUT"
    assert all("task" not in event.event_type for event in runtime.events())


def test_output_selector_rejects_mutating_business_effects() -> None:
    runtime = prepared()
    ref, _ = runtime.accept_response("turn-1", "response-1")
    before = runtime.fingerprint()
    with pytest.raises(ConversationRuntimeViolation) as raised:
        runtime.apply_output(ref, "task.create")
    assert raised.value.reason == "UNSUPPORTED_OUTPUT_EFFECT"
    assert runtime.fingerprint() == before
