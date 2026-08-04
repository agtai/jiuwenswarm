# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContractViolation,
    ErrorCode,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.task_core import (
    AuthorizationContext,
    TaskCommand,
    TaskCore,
    TaskCoreViolation,
    TaskQuery,
    TaskSpec,
    TaskState,
    project_work_progress,
)
from jiuwenswarm.server.live_voice.executor_port import ExecutorPort, ExecutorState


def scope(subject: str = "subject-1") -> ScopeRef:
    return ScopeRef(subject, "project-1", "session-1", Assurance.AUTHENTICATED)


def auth(
    current: ScopeRef | None = None, operations: frozenset[str] | None = None
) -> AuthorizationContext:
    current = scope() if current is None else current
    return AuthorizationContext(
        current.subject_id,
        current,
        operations
        or frozenset(
            {
                "task.create",
                "task.cancel",
                "task.get",
                "task.list",
                "task.status",
                "task.events",
                "task.execute",
            }
        ),
    )


def create_command(
    *,
    request_id: str = "request-1",
    command_id: str = "command-1",
    instruction: str = "check inventory",
) -> TaskCommand:
    return TaskCommand(
        request_id,
        command_id,
        "task.create",
        scope(),
        None,
        TaskSpec("inventory", instruction),
        "commit-1",
    )


def test_create_records_task_attempt_event_result_and_dispatch_atomically() -> None:
    core = TaskCore()
    result = core.execute(create_command(), auth())
    snapshot = core.snapshot()
    assert result.applied is True
    assert result.task_id == snapshot.tasks[0].task_id
    assert result.attempt_id == snapshot.attempts[0].attempt_id
    assert snapshot.tasks[0].state is TaskState.ACCEPTED
    assert snapshot.events[0].event_type == "task.accepted"
    assert snapshot.dispatch_intents[0].command_id == "command-1"
    assert snapshot.mutation_version == 1


def test_replay_is_idempotent_and_concurrent() -> None:
    core = TaskCore()
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(
            pool.map(
                lambda i: core.execute(create_command(request_id=f"r-{i}"), auth()),
                range(30),
            )
        )
    assert sum(result.applied for result in results) == 1
    assert len({result.task_id for result in results}) == 1
    snapshot = core.snapshot()
    assert len(snapshot.tasks) == 1
    assert len(snapshot.attempts) == 1
    assert len(snapshot.dispatch_intents) == 1


def test_command_fingerprint_conflict_has_zero_mutation() -> None:
    core = TaskCore()
    core.execute(create_command(), auth())
    before = core.snapshot()
    with pytest.raises(TaskCoreViolation) as raised:
        core.execute(create_command(instruction="changed"), auth())
    assert raised.value.reason == "COMMAND_FINGERPRINT_CONFLICT"
    assert core.snapshot() == before


def test_cancel_acknowledgement_is_not_terminal() -> None:
    core = TaskCore()
    created = core.execute(create_command(), auth())
    cancelled = core.execute(
        TaskCommand(
            "request-2",
            "command-2",
            "task.cancel",
            scope(),
            created.task_id,
            None,
            "commit-2",
        ),
        auth(),
    )
    task = core.query(TaskQuery("q", "task.get", scope(), created.task_id), auth())
    assert cancelled.cancel_acknowledged is True
    assert task.cancel_requested is True
    assert task.dispatch_fenced is True
    assert task.state is TaskState.ACCEPTED
    assert task.outcome is None
    assert len(core.snapshot().cancel_intents) == 1


def test_repeated_cancel_identity_does_not_emit_second_control_intent() -> None:
    core = TaskCore()
    created = core.execute(create_command(), auth())
    first = TaskCommand(
        "request-2",
        "command-2",
        "task.cancel",
        scope(),
        created.task_id,
        None,
        "commit-2",
    )
    second = TaskCommand(
        "request-3",
        "command-3",
        "task.cancel",
        scope(),
        created.task_id,
        None,
        "commit-3",
    )
    assert core.execute(first, auth()).applied is True
    assert core.execute(second, auth()).applied is False
    assert len(core.snapshot().cancel_intents) == 1


def test_attempt_is_only_terminal_evidence_for_task() -> None:
    core = TaskCore()
    created = core.execute(create_command(), auth())
    with pytest.raises(TaskCoreViolation) as raised:
        core.transition_task(created.task_id, TaskState.TERMINAL, auth())
    assert raised.value.reason == "ATTEMPT_EVIDENCE_REQUIRED"
    core.mark_attempt_running(created.task_id, created.attempt_id, auth())
    attempt_event, task_event = core.finish_attempt(
        created.task_id,
        created.attempt_id,
        TerminalOutcome.COMPLETED,
        auth(),
    )
    assert attempt_event.event_type == "attempt.terminal"
    assert task_event.event_type == "task.terminal"
    task = core.query(TaskQuery("q", "task.status", scope(), created.task_id), auth())
    assert task.state is TaskState.TERMINAL
    assert task.outcome is TerminalOutcome.COMPLETED


def test_attempt_cannot_skip_running_or_omit_terminal_outcome() -> None:
    core = TaskCore()
    created = core.execute(create_command(), auth())
    before = core.snapshot()
    with pytest.raises(ContractViolation) as raised:
        core.finish_attempt(
            created.task_id, created.attempt_id, TerminalOutcome.COMPLETED, auth()
        )
    assert raised.value.reason == "INVALID_LIFECYCLE_TRANSITION"
    assert core.snapshot() == before

    core.mark_attempt_running(created.task_id, created.attempt_id, auth())
    before = core.snapshot()
    with pytest.raises(ContractViolation) as raised:
        core.finish_attempt(created.task_id, created.attempt_id, None, auth())
    assert raised.value.reason == "TERMINAL_OUTCOME_REQUIRED"
    assert core.snapshot() == before


def test_task_blocked_decision_and_running_transitions_are_legal() -> None:
    core = TaskCore()
    created = core.execute(create_command(), auth())
    blocked = core.transition_task(created.task_id, TaskState.BLOCKED, auth())
    decision = core.transition_task(
        created.task_id, TaskState.DECISION_REQUIRED, auth()
    )
    running = core.transition_task(created.task_id, TaskState.RUNNING, auth())
    assert [blocked.state, decision.state, running.state] == [
        "blocked",
        "decision_required",
        "running",
    ]


def test_queries_are_read_only_and_event_replay_uses_cursor() -> None:
    core = TaskCore()
    created = core.execute(create_command(), auth())
    before = core.snapshot().mutation_version
    assert len(core.query(TaskQuery("l", "task.list", scope()), auth())) == 1
    events = core.query(
        TaskQuery("e", "task.events", scope(), created.task_id, after_seq=-1),
        auth(),
    )
    assert [event.seq for event in events] == [0]
    assert (
        core.query(
            TaskQuery("e2", "task.events", scope(), created.task_id, after_seq=0),
            auth(),
        )
        == ()
    )
    assert core.snapshot().mutation_version == before


def test_work_progress_projection_cannot_mutate_core() -> None:
    core = TaskCore()
    core.execute(create_command(), auth())
    before = core.snapshot()
    progress = project_work_progress(before.events[0])
    assert progress.source_event_id == before.events[0].event_id
    assert progress.state == "accepted"
    assert core.snapshot() == before


def test_terminal_state_is_irreversible() -> None:
    core = TaskCore()
    created = core.execute(create_command(), auth())
    core.mark_attempt_running(created.task_id, created.attempt_id, auth())
    core.finish_attempt(
        created.task_id, created.attempt_id, TerminalOutcome.COMPLETED, auth()
    )
    before = core.snapshot()
    with pytest.raises(ContractViolation) as raised:
        core.transition_task(created.task_id, TaskState.RUNNING, auth())
    assert raised.value.reason == "INVALID_LIFECYCLE_TRANSITION"
    assert core.snapshot() == before


def test_authorization_prevents_disclosure_and_mutation() -> None:
    core = TaskCore()
    created = core.execute(create_command(), auth())
    before = core.snapshot()
    foreign = scope("subject-2")
    with pytest.raises(TaskCoreViolation) as raised:
        core.query(TaskQuery("q", "task.get", foreign, created.task_id), auth(foreign))
    assert raised.value.reason == "TASK_NOT_FOUND"
    assert core.snapshot() == before

    asserted = ScopeRef(
        "subject-1", "project-1", "session-1", Assurance.REQUEST_ASSERTED
    )
    with pytest.raises(TaskCoreViolation) as raised:
        core.execute(
            TaskCommand(
                "r2", "c2", "task.cancel", asserted, created.task_id, None, "commit"
            ),
            auth(asserted),
        )
    assert raised.value.code is ErrorCode.PERMISSION_DENIED
    assert core.snapshot() == before


def test_unsupported_full_p3_command_fails_closed() -> None:
    core = TaskCore()
    command = TaskCommand(
        "request", "command", "task.pause", scope(), "task-1", None, "commit"
    )
    before = core.snapshot()
    with pytest.raises(TaskCoreViolation) as raised:
        core.execute(command, auth(operations=frozenset({"task.pause"})))
    assert raised.value.reason == "UNSUPPORTED_TASK_COMMAND"
    assert core.snapshot() == before


def test_fake_core_and_executor_preserve_task_and_attempt_identity() -> None:
    core = TaskCore()
    executor = ExecutorPort()
    created = core.execute(create_command(), auth())
    dispatch = core.snapshot().dispatch_intents[0]
    accepted, executor_status = executor.dispatch(dispatch)
    assert accepted is True
    assert executor_status.attempt_id == created.attempt_id
    assert executor.start(created.attempt_id).state is ExecutorState.RUNNING
    core.mark_attempt_running(created.task_id, created.attempt_id, auth())
    assert (
        executor.finish(created.attempt_id, TerminalOutcome.COMPLETED).state
        is ExecutorState.TERMINAL
    )
    core.finish_attempt(
        created.task_id, created.attempt_id, TerminalOutcome.COMPLETED, auth()
    )
    task = core.query(TaskQuery("q", "task.get", scope(), created.task_id), auth())
    assert task.task_id == created.task_id
    assert task.attempt_id == created.attempt_id
    assert task.outcome is TerminalOutcome.COMPLETED
