# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Opt-in real presentation/cursor proof against exact clean AgentCore."""

from __future__ import annotations

from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CommandEnvelope,
    ResponseRef,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    PersistentTaskEvent,
    TaskAuthorizationGrant,
    TaskUnreadPage,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_presentation_adapter import (
    OpenJiuwenTaskPresentationAdapterError,
    OpenJiuwenTaskPresentationCursorAdapter,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    TaskPresentationConsumptionOwner,
    TaskPresentationRuntimeReceipt,
    TaskPresentationViolation,
    TextPresentationAdoptionAck,
)
from tests.integration.live_voice.test_openjiuwen_task_facade_candidate import (
    EXPIRY,
    SCOPE,
    TASK,
    _authority,
    _bind_agent,
    _build_agent,
    _require_candidate_import_source,
    _require_exact_candidate,
    _seed,
)

EXECUTION = "presentation-execution-1"
PROFILE = "3" * 64
OWNER = "presentation-runtime-1"
RESPONSE = ResponseRef("presentation-interaction", "presentation-response", 1)
NOW = "2030-01-01T00:00:00Z"


class _RuntimeAuthority:
    def __call__(
        self,
        response: ResponseRef,
        reservation_id: str | None,
        phase: str,
    ) -> TaskPresentationRuntimeReceipt:
        expected = "presentation-runtime-reservation"
        if phase == "reserve":
            if response != RESPONSE or reservation_id is not None:
                raise TaskPresentationViolation("STALE_RUNTIME", "stale runtime")
            return TaskPresentationRuntimeReceipt(response, expected, phase, True)
        if response != RESPONSE or reservation_id != expected:
            raise TaskPresentationViolation("STALE_RUNTIME", "stale runtime")
        return TaskPresentationRuntimeReceipt(response, expected, phase, True)


async def _seed_terminal(agent) -> None:
    from openjiuwen.agent_teams.schema.task import ExecutionOutcome

    binding = agent.task_authority.binding
    task = agent.team_backend.db.task
    prepared = await task.prepare_execution(
        TASK,
        EXECUTION,
        PROFILE,
        0,
        0,
        team_name=binding.team_name,
    )
    assert prepared.ok and prepared.record is not None
    admitted = await task.start_execution(
        TASK,
        binding.member_name,
        EXECUTION,
        PROFILE,
        0,
        OWNER,
        1,
        prepared.record.execution_version,
        team_name=binding.team_name,
    )
    assert admitted.ok and admitted.record is not None
    settled = await task.settle_execution(
        TASK,
        EXECUTION,
        admitted.record.execution_version,
        ExecutionOutcome.FAILED,
        team_name=binding.team_name,
    )
    assert settled.ok and settled.record is not None


def _product_page(unread) -> TaskUnreadPage:
    events = []
    for event in unread.events:
        terminal = event.sequence == unread.head_sequence
        events.append(
            PersistentTaskEvent(
                event_id=event.event_id,
                task_id=TASK,
                attempt_id=EXECUTION,
                scope=SCOPE,
                seq=event.sequence - 1,
                event_type="task.terminal" if terminal else "attempt.accepted",
                state="terminal" if terminal else "accepted",
                outcome="failed" if terminal else None,
                producer="task_core",
                source_event_id=event.event_id if terminal else None,
                causation_id=event.causation_id,
                correlation_id=event.correlation_id,
                occurred_at="2030-01-01T00:00:00Z",
                details={},
            )
        )
    return TaskUnreadPage(
        task_id=TASK,
        presentation_class="text",
        watermark=unread.cursor.sequence - 1,
        acked_event_id=unread.cursor.event_id,
        head_seq=unread.head_sequence - 1,
        events=tuple(events),
        next_after_seq=unread.next_after_sequence,
        has_more=unread.has_more,
    )


def _command(delivery):
    command = CommandEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "request_id": "presentation-candidate-request",
            "command_id": "presentation-candidate-advance",
            "command_type": "task.ack_events",
            "issued_at": NOW,
            "scope": SCOPE.to_dict(),
            "correlation_id": "candidate-integration",
            "causation_id": delivery.event_id,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": TASK},
            "context_refs": [],
            "required_capabilities": ["task.ack_events"],
            "payload": {
                "presentation_class": "text",
                "acked_through_seq": delivery.event_seq,
                "acked_event_id": delivery.event_id,
                "expected_event_head": delivery.expected_event_head,
            },
            "extensions": {},
        }
    )
    grant = TaskAuthorizationGrant(
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
        operation="task.ack_events",
        command_id=command.command_id,
        target_task_id=TASK,
        allowed_capabilities=frozenset({"task.ack_events"}),
        confirmation_id=None,
        confirmed=False,
        expires_at=EXPIRY,
        policy_bypass="server_task_presentation_v1",
    )
    return command, grant


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exact_candidate_product_ack_advances_and_replays_after_reopen(
    tmp_path: Path,
) -> None:
    candidate, expected = _require_exact_candidate()
    _require_candidate_import_source(candidate)
    assert len(expected) == 40
    database_path = tmp_path / "agentcore-presentation.sqlite3"
    legacy_store_path = tmp_path / "legacy-task-store.sqlite3"

    from openjiuwen.agent_teams.spawn.shared_resources import cleanup_shared_resources

    owner = TaskPresentationConsumptionOwner(_RuntimeAuthority())
    first_agent = await _build_agent(database_path)
    try:
        first_facade = await _bind_agent(first_agent, fail_after_first_advance=True)
        await _seed(first_agent)
        await _seed_terminal(first_agent)
        unread = await first_facade.read_unread(
            _authority("task.unread_events"),
            TASK,
            "text",
        )
        voice = await first_facade.read_unread(
            _authority("task.unread_events"),
            TASK,
            "voice",
        )
        assert unread is not None and voice is not None
        assert unread.head_sequence == 4
        delivery = owner.reserve_next(
            _product_page(unread),
            scope=SCOPE,
            response_ref=RESPONSE,
            delivery_id="presentation-candidate-delivery",
            unit_id="presentation-candidate-unit",
        )
        assert delivery.event_seq == 3 and delivery.attempt_id == EXECUTION
        assert owner.mark_text_adopted(
            TextPresentationAdoptionAck.from_delivery(
                delivery,
                adopted_at="2030-01-01T00:00:01Z",
            )
        )
        command, grant = _command(delivery)
        with pytest.raises(OpenJiuwenTaskPresentationAdapterError) as lost:
            await OpenJiuwenTaskPresentationCursorAdapter(first_facade).consume(
                owner,
                delivery,
                command,
                grant,
                _authority("task.ack_events"),
                unread,
                observed_at=NOW,
            )
        assert lost.value.reason == "AGENTCORE_CURSOR_ADVANCE_FAILED"
    finally:
        first_agent.session_manager.release_session()
        await first_agent.team_backend.db.close()
        cleanup_shared_resources()

    second_agent = await _build_agent(database_path)
    try:
        second_facade = await _bind_agent(second_agent)
        replay = await OpenJiuwenTaskPresentationCursorAdapter(second_facade).consume(
            owner,
            delivery,
            command,
            grant,
            _authority("task.ack_events"),
            unread,
            observed_at=NOW,
        )
        assert replay.ok and replay.result is not None
        assert replay.result["advanced"] is True
        assert replay.result["replayed"] is True

        text_after = await second_facade.read_unread(
            _authority("task.unread_events"), TASK, "text"
        )
        voice_after = await second_facade.read_unread(
            _authority("task.unread_events"), TASK, "voice"
        )
        assert text_after is not None and text_after.cursor.sequence == 4
        assert voice_after is not None and voice_after.cursor.sequence == 0
    finally:
        second_agent.session_manager.release_session()
        await second_agent.team_backend.db.close()
        cleanup_shared_resources()

    assert database_path.exists()
    assert not legacy_store_path.exists()
