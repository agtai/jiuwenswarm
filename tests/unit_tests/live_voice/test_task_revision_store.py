# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CommandEnvelope,
    OriginRef,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskSpec,
    FormalTaskState,
    FormalTaskViolation,
    OutboxKind,
    OutboxState,
    PersistentOutboxItem,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
)
from jiuwenswarm.server.live_voice.task_revision import (
    RevisionApplicationState,
    RevisionFenceAck,
    TaskRevisionCommand,
    TaskRevisionConstraints,
    TaskRevisionExecutionAck,
    TaskRevisionGrant,
    TaskRevisionOperation,
    TaskRevisionVerifierResult,
    TaskRevisionVerifierState,
)
from jiuwenswarm.server.live_voice.task_revision_store import (
    RevisionOutboxState,
    SqliteTaskRevisionStore,
)
from jiuwenswarm.server.live_voice.task_event_subscription import TaskEventSubscription
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore


NOW = "2026-08-13T10:00:00Z"
FORMAL_PROJECT_EXECUTOR_ID = "jiuwenswarm_code_agent.project_code"


def _scope() -> ScopeRef:
    return ScopeRef("user-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def _context(project: Path) -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="gateway.project_registry",
        stable_id="project-1",
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value="clean-base-1",
        scope=_scope(),
        permissions=("task.execute", "project.write"),
        expires_at="2026-08-13T11:00:00Z",
        redaction_policy_id="live_voice.s8_5.fixture.v1",
    )


def _create_command(command_id: str = "command-create") -> CommandEnvelope:
    return CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-create",
            "command_id": command_id,
            "command_type": "task.create",
            "issued_at": NOW,
            "scope": _scope().to_dict(),
            "correlation_id": "correlation-1",
            "causation_id": None,
            "origin": {
                "kind": "committed_turn",
                "turn_id": "turn-create",
                "commit_id": "commit-create",
            },
            "target_ref": {"kind": "task", "id": f"create:{command_id}"},
            "context_refs": [],
            "required_capabilities": ["task.create"],
            "payload": {},
            "extensions": {},
        }
    )


def _spec(project: Path) -> FormalTaskSpec:
    return FormalTaskSpec(
        name="Calculator fix",
        instruction="Fix the calculator defect.",
        origin=OriginRef("committed_turn", "turn-create", "commit-create"),
        context=_context(project),
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        required_capabilities=("task.create",),
        side_effect_class="project_mutation",
        attributes=(
            ("model_config_version", "catalog-v1"),
            ("model_identity", "default#0"),
        ),
    )


def _cancel_command(task_id: str) -> CommandEnvelope:
    return CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-cancel",
            "command_id": "command-cancel",
            "command_type": "task.cancel",
            "issued_at": "2026-08-13T10:00:30Z",
            "scope": _scope().to_dict(),
            "correlation_id": "correlation-1",
            "causation_id": None,
            "origin": {
                "kind": "committed_turn",
                "turn_id": "turn-cancel",
                "commit_id": "commit-cancel",
            },
            "target_ref": {"kind": "task", "id": task_id},
            "context_refs": [],
            "required_capabilities": ["task.cancel"],
            "payload": {},
            "extensions": {},
        }
    )


def _observations(
    item: PersistentOutboxItem,
    *,
    executor_ref: str | None = None,
    terminal: TerminalOutcome | None = None,
) -> tuple[ExecutorObservation, ...]:
    reference = executor_ref or f"executor:{item.attempt_id}"
    states = [
        (0, FormalAttemptState.ACCEPTED, None),
        (1, FormalAttemptState.RUNNING, None),
    ]
    if terminal is not None:
        states.append((2, FormalAttemptState.TERMINAL, terminal))
    return tuple(
        ExecutorObservation(
            resolution=ExecutorResolution.KNOWN,
            executor_id=FORMAL_PROJECT_EXECUTOR_ID,
            executor_ref=reference,
            task_id=item.task_id,
            attempt_id=item.attempt_id,
            source_event_id=f"{reference}:{seq}",
            source_seq=seq,
            attempt_state=state,
            attempt_outcome=outcome,
            occurred_at=f"2026-08-13T10:00:0{seq}Z",
            raw_status=state.value,
        )
        for seq, state, outcome in states
        if seq > item.source_seq
    )


def _running_task(
    tmp_path: Path,
) -> tuple[SqliteTaskStore, str, str, str]:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    result = store.create(_create_command(), _spec(tmp_path), observed_at=NOW)
    assert result.result is not None
    task_id = str(result.result["task_id"])
    attempt_id = str(result.result["attempt_id"])
    dispatch = store.claim_outbox("initial-dispatch")
    assert dispatch is not None
    executor_ref = f"executor:{attempt_id}"
    store.complete_outbox(
        dispatch,
        executor_ref=executor_ref,
        observations=_observations(dispatch, executor_ref=executor_ref),
    )
    assert store.get_task(task_id, _scope()).state is FormalTaskState.RUNNING
    return store, task_id, attempt_id, executor_ref


def _command(task_id: str, attempt_id: str, *, command_id: str = "revise-1"):
    return TaskRevisionCommand(
        command_id=command_id,
        operation=TaskRevisionOperation.PROVIDE_INPUT,
        scope=_scope(),
        task_id=task_id,
        expected_task_revision=1,
        expected_attempt_id=attempt_id,
        origin_commit_id="commit-revision-1",
        facts=("negative inputs retain their current behavior",),
    )


def _grant(command: TaskRevisionCommand) -> TaskRevisionGrant:
    return TaskRevisionGrant(
        principal_id="user-1",
        scope=_scope(),
        operation=command.operation,
        command_id=command.command_id,
        task_id=command.task_id,
        expected_task_revision=command.expected_task_revision,
        expected_attempt_id=command.expected_attempt_id,
        command_fingerprint=command.fingerprint(),
        confirmation_id="confirmation-1",
        confirmed=True,
        expires_at="2026-08-13T10:05:00Z",
    )


def _ack(command: TaskRevisionCommand, executor_ref: str, **changes: object):
    values: dict[str, object] = {
        "command_id": command.command_id,
        "task_id": command.task_id,
        "predecessor_revision": command.expected_task_revision,
        "predecessor_attempt_id": command.expected_attempt_id,
        "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
        "executor_ref": executor_ref,
        "cleanup_id": "cleanup-1",
        "checkout_identity": "fixture-clean-base-1",
        "unapplied_changes_discarded": True,
        "acknowledged_at": "2026-08-13T10:01:00Z",
    }
    values.update(changes)
    return RevisionFenceAck(**values)  # type: ignore[arg-type]


def _revision_rows(
    database: Path,
) -> tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]:
    with sqlite3.connect(database) as connection:
        tables = (
            "tasks",
            "attempts",
            "task_events",
            "s85_task_revisions",
            "s85_revision_commands",
            "s85_revision_outbox",
            "s85_revision_fence_acks",
            "s85_revision_dispatch_outbox",
            "s85_revision_execution_acks",
        )
        return tuple(
            (
                table,
                tuple(
                    tuple(row)
                    for row in connection.execute(
                        f"SELECT * FROM {table} ORDER BY rowid"  # noqa: S608
                    ).fetchall()
                ),
            )
            for table in tables
        )


def test_feature_off_store_creates_no_revision_schema(tmp_path: Path) -> None:
    database = tmp_path / "off.sqlite3"
    SqliteTaskStore(database)

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert not any(name.startswith("s85_") for name in tables)


def test_extension_rejects_partial_or_unknown_owned_schema(tmp_path: Path) -> None:
    database = tmp_path / "corrupt-extension.sqlite3"
    store = SqliteTaskStore(database)
    SqliteTaskRevisionStore(store)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            ALTER TABLE s85_revision_dispatch_outbox
            RENAME COLUMN last_error TO corrupt_last_error
            """
        )

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskRevisionStore(SqliteTaskStore(database))

    assert rejected.value.reason == "TASK_REVISION_SCHEMA_UNSUPPORTED"


def test_extension_rejects_weakened_unresolved_ownership_index(
    tmp_path: Path,
) -> None:
    database = tmp_path / "weak-index.sqlite3"
    store = SqliteTaskStore(database)
    SqliteTaskRevisionStore(store)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP INDEX idx_s85_one_fence_per_task")
        connection.execute(
            """
            CREATE UNIQUE INDEX idx_s85_one_fence_per_task
            ON s85_revision_commands(task_id)
            WHERE application_state='fencing'
            """
        )

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskRevisionStore(SqliteTaskStore(database))

    assert rejected.value.reason == "TASK_REVISION_SCHEMA_UNSUPPORTED"


def test_exact_incubator_v1_schema_migrates_to_execution_ack_v2(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    SqliteTaskRevisionStore(store)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("DROP TABLE s85_revision_execution_acks")
        connection.execute(
            "UPDATE s85_revision_metadata SET value='1' WHERE key='schema_version'"
        )

    reopened = SqliteTaskRevisionStore(SqliteTaskStore(store.database_path))

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT value FROM s85_revision_metadata WHERE key='schema_version'"
        ).fetchone() == ("2",)
        assert connection.execute(
            "SELECT COUNT(*) FROM s85_revision_execution_acks"
        ).fetchone() == (0,)
    assert reopened.database_path == store.database_path


def test_request_is_atomic_and_does_not_start_successor_before_cleanup_ack(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, _executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    before = store.counts()

    receipt = revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )

    assert receipt.application_state is RevisionApplicationState.FENCING
    assert receipt.predecessor_revision == 1
    assert receipt.successor_revision == 2
    assert receipt.successor_attempt_id is None
    expected_counts = dict(before)
    expected_counts["task_events"] += 1
    assert store.counts() == expected_counts
    assert store.get_task(task_id, _scope()).attempt_id == attempt_id
    requested = store.events(task_id, _scope())[-1]
    assert requested.event_type == "task.revision_requested"
    assert requested.details["predecessor_attempt_id"] == attempt_id
    truth = revisions.truth(task_id, _scope())
    assert truth.current_revision.task_revision == 1
    assert truth.pending_receipt == receipt


def test_read_target_is_side_effect_free_and_exposes_only_store_identity(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, _executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    before = _revision_rows(store.database_path)

    target = revisions.read_target(task_id, _scope())

    assert target.task_id == task_id
    assert target.task_revision == 1
    assert target.attempt_id == attempt_id
    assert target.attempt_number == 1
    assert target.task_state == FormalTaskState.RUNNING.value
    assert target.pending_command_id is None
    assert _revision_rows(store.database_path) == before

    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )

    pending = revisions.read_target(task_id, _scope())
    assert pending.pending_command_id == command.command_id

    fence = revisions.claim_fence("fence-worker")
    assert fence is not None
    applied = revisions.complete_fence(fence, _ack(command, _executor_ref))
    successor = revisions.read_target(task_id, _scope())
    assert successor.task_revision == 2
    assert successor.attempt_id == applied.successor_attempt_id
    assert successor.attempt_number == 2
    assert successor.pending_command_id is None


@pytest.mark.asyncio
async def test_requested_event_replays_as_nonprojecting_authority_fact(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, _executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    authorization = TaskAuthorizationGrant(
        principal_id=_scope().subject_id,
        scope=_scope(),
        operation="task.events",
        command_id=None,
        target_task_id=task_id,
        allowed_capabilities=frozenset({"task.events"}),
        confirmation_id=None,
        confirmed=False,
        expires_at="2026-08-13T11:00:00Z",
    )
    subscription = TaskEventSubscription(
        source=store,
        authorization=authorization,
        scope=_scope(),
        task_id=task_id,
        enabled=True,
        authority_atomic_replay=True,
        queue_capacity=32,
        clock=lambda: NOW,
    )

    assert await subscription.start() is True
    task = store.get_task(task_id, _scope())
    events = [await subscription.next_event() for _ in range(task.event_head + 1)]
    assert events[-1].event_type == "task.revision_requested"
    assert events[-1].attempt_id == attempt_id
    await subscription.close()


def test_exact_replay_has_no_duplicate_fence_or_revision(tmp_path: Path) -> None:
    store, task_id, attempt_id, _executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    first = revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )

    replay = revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("other",)),
        observed_at=NOW,
    )

    assert replay == replace(first, replayed=True)
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM s85_revision_commands"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM s85_revision_outbox"
        ).fetchone() == (1,)


def test_command_id_conflict_and_stale_revision_have_zero_base_mutation(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, _executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    before = store.counts()
    stale = replace(
        _command(task_id, attempt_id, command_id="revise-stale"),
        expected_task_revision=2,
    )
    with pytest.raises(FormalTaskViolation) as rejected:
        revisions.request_revision(
            stale,
            _grant(stale),
            initial_constraints=TaskRevisionConstraints(("src", "tests")),
            observed_at=NOW,
        )
    assert rejected.value.reason == "TASK_REVISION_PRECONDITION_STALE"
    assert store.counts() == before

    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    before = store.counts()

    changed = replace(command, facts=("different fact",))
    with pytest.raises(FormalTaskViolation) as conflict:
        revisions.request_revision(
            changed,
            _grant(changed),
            initial_constraints=TaskRevisionConstraints(("src", "tests")),
            observed_at=NOW,
        )
    assert conflict.value.reason == "IDEMPOTENCY_CONFLICT"

    assert store.counts() == before


def test_predecessor_late_terminal_is_quarantined_while_fence_is_pending(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    attempt = store.get_attempt(attempt_id)
    item = PersistentOutboxItem(
        outbox_id="late-diagnostic",
        kind=OutboxKind.ATTEMPT_DISPATCH,
        task_id=task_id,
        attempt_id=attempt_id,
        command_id="late",
        scope=_scope(),
        spec=store.get_task(task_id, _scope()).spec,
        executor_ref=executor_ref,
        source_seq=attempt.source_seq,
        state=OutboxState.CLAIMED,
        delivery_count=1,
    )

    # Only the observation identity/state is consumed here; the synthetic item
    # cannot be dispatched and carries no mutation authority of its own.
    receipt = store.apply_observations(
        _observations(
            item,
            executor_ref=executor_ref,
            terminal=TerminalOutcome.COMPLETED,
        )
    )

    assert receipt.events == ()
    assert store.get_attempt(attempt_id).state is FormalAttemptState.RUNNING
    assert store.get_attempt(attempt_id).outcome is None
    task = store.get_task(task_id, _scope())
    assert task.state is FormalTaskState.RUNNING
    assert task.outcome is None
    assert all(
        event.event_type != "task.terminal" for event in store.events(task_id, _scope())
    )
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=32)
    assert snapshot.task.state is FormalTaskState.RUNNING
    assert snapshot.attempt.state is FormalAttemptState.RUNNING


def test_late_completed_predecessor_is_preserved_but_superseded(tmp_path: Path) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = revisions.claim_fence("fence-worker")
    assert fence is not None
    attempt = store.get_attempt(attempt_id)
    item = PersistentOutboxItem(
        outbox_id="late-diagnostic",
        kind=OutboxKind.ATTEMPT_DISPATCH,
        task_id=task_id,
        attempt_id=attempt_id,
        command_id="late",
        scope=_scope(),
        spec=store.get_task(task_id, _scope()).spec,
        executor_ref=executor_ref,
        source_seq=attempt.source_seq,
        state=OutboxState.CLAIMED,
        delivery_count=1,
    )
    store.apply_observations(
        _observations(
            item,
            executor_ref=executor_ref,
            terminal=TerminalOutcome.COMPLETED,
        )
    )

    applied = revisions.complete_fence(fence, _ack(command, executor_ref))

    assert store.get_attempt(attempt_id).outcome is TerminalOutcome.COMPLETED
    assert store.get_task(task_id, _scope()).attempt_id == applied.successor_attempt_id
    boundary = store.events(task_id, _scope())[-1]
    assert boundary.event_type == "task.revision_applied"
    assert boundary.details["previous_outcome"] == TerminalOutcome.COMPLETED.value
    assert (
        store.event_authority_snapshot(task_id, _scope(), max_events=32).events[0]
        == boundary
    )


def test_cleanup_ack_atomically_creates_one_clean_successor_and_dispatch(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    requested = revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = revisions.claim_fence("fence-worker")
    assert fence is not None and fence.outbox_id == requested.fence_outbox_id

    applied = revisions.complete_fence(fence, _ack(command, executor_ref))

    assert applied.application_state is RevisionApplicationState.APPLIED
    assert applied.successor_attempt_id not in {None, attempt_id}
    assert applied.dispatch_outbox_id is not None
    task = store.get_task(task_id, _scope())
    assert task.state is FormalTaskState.ACCEPTED
    assert task.attempt_id == applied.successor_attempt_id
    assert "Committed additive facts" in task.spec.instruction
    predecessor = store.get_attempt(attempt_id)
    assert predecessor.state is FormalAttemptState.TERMINAL
    assert predecessor.outcome is TerminalOutcome.INTERRUPTED
    successor = store.get_attempt(str(applied.successor_attempt_id))
    assert successor.attempt_number == 2
    truth = revisions.truth(task_id, _scope())
    assert truth.current_revision.task_revision == 2
    assert truth.current_revision.attempt_id == successor.attempt_id
    assert truth.cleanup_ack is not None
    assert truth.cleanup_ack.cleanup_id == "cleanup-1"
    assert truth.pending_receipt is None
    boundary = store.events(task_id, _scope())[-1]
    assert boundary.event_type == "task.revision_applied"
    assert boundary.attempt_id == successor.attempt_id
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=32)
    assert snapshot.events[0] == boundary
    assert snapshot.attempt == successor
    with pytest.raises(FormalTaskViolation) as retry_mixing:
        store.read_current_retry_authority(scope=_scope(), task_id=task_id)
    assert retry_mixing.value.reason == "TASK_RETRY_REVISION_MIXING_UNSUPPORTED"


def test_cleanup_ack_mismatch_or_unknown_never_creates_successor(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = revisions.claim_fence("fence-worker")
    assert fence is not None
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as mismatch:
        revisions.complete_fence(
            fence,
            _ack(command, executor_ref, checkout_identity="other", task_id="other"),
        )
    assert mismatch.value.reason == "TASK_REVISION_FENCE_ACK_MISMATCH"
    assert store.counts() == before

    unknown = revisions.mark_fence_unknown(fence, reason="cleanup timeout")
    assert unknown.application_state is RevisionApplicationState.UNKNOWN
    assert unknown.successor_attempt_id is None
    assert store.get_task(task_id, _scope()).attempt_id == attempt_id

    replacement = _command(task_id, attempt_id, command_id="revision-after-unknown")
    before = _revision_rows(store.database_path)
    with pytest.raises(FormalTaskViolation) as unresolved:
        revisions.request_revision(
            replacement,
            _grant(replacement),
            initial_constraints=TaskRevisionConstraints(("src", "tests")),
            observed_at=NOW,
        )
    assert unresolved.value.reason == "TASK_REVISION_ALREADY_PENDING"
    assert _revision_rows(store.database_path) == before

    attempt = store.get_attempt(attempt_id)
    item = PersistentOutboxItem(
        outbox_id="unknown-diagnostic",
        kind=OutboxKind.ATTEMPT_DISPATCH,
        task_id=task_id,
        attempt_id=attempt_id,
        command_id="unknown-diagnostic",
        scope=_scope(),
        spec=store.get_task(task_id, _scope()).spec,
        executor_ref=executor_ref,
        source_seq=attempt.source_seq,
        state=OutboxState.CLAIMED,
        delivery_count=1,
    )
    mutation = store.apply_observations(
        _observations(
            item,
            executor_ref=executor_ref,
            terminal=TerminalOutcome.COMPLETED,
        )
    )
    assert mutation.events == ()
    assert store.get_task(task_id, _scope()).state is FormalTaskState.RUNNING
    assert all(
        event.event_type != "task.terminal" for event in store.events(task_id, _scope())
    )


def test_cancel_race_supersedes_revision_without_successor(tmp_path: Path) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = revisions.claim_fence("fence-worker")
    assert fence is not None
    store.cancel(_cancel_command(task_id), observed_at="2026-08-13T10:00:30Z")

    rejected = revisions.complete_fence(fence, _ack(command, executor_ref))

    assert rejected.application_state is RevisionApplicationState.REJECTED
    assert rejected.successor_attempt_id is None
    task = store.get_task(task_id, _scope())
    assert task.attempt_id == attempt_id
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM s85_revision_dispatch_outbox"
        ).fetchone() == (0,)


def test_cancel_before_fence_claim_has_zero_executor_cleanup_effect(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, _executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    store.cancel(_cancel_command(task_id), observed_at="2026-08-13T10:00:30Z")

    assert revisions.claim_fence("fence-worker") is None
    with sqlite3.connect(store.database_path) as connection:
        connection.row_factory = sqlite3.Row
        command_row = connection.execute(
            "SELECT * FROM s85_revision_commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone()
        outbox_row = connection.execute(
            "SELECT * FROM s85_revision_outbox WHERE command_id=?",
            (command.command_id,),
        ).fetchone()
    assert command_row is not None
    assert command_row["application_state"] == RevisionApplicationState.REJECTED.value
    assert outbox_row is not None
    assert outbox_row["state"] == RevisionOutboxState.DELIVERED.value
    assert outbox_row["delivery_count"] == 1
    assert outbox_row["claim_token"] is None


def test_corrupt_successor_lineage_rejects_before_dispatch_claim(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = revisions.claim_fence("fence-worker")
    assert fence is not None
    revisions.complete_fence(fence, _ack(command, executor_ref))
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            UPDATE s85_revision_dispatch_outbox
            SET command_id='corrupt-command'
            WHERE command_id=?
            """,
            (command.command_id,),
        )

    with pytest.raises(FormalTaskViolation) as rejected:
        revisions.claim_successor_dispatch("dispatch-worker")

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT state FROM s85_revision_dispatch_outbox"
        ).fetchone() == (OutboxState.PENDING.value,)


def test_successor_dispatch_uses_durable_sidecar_and_updates_authoritative_state(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = revisions.claim_fence("fence-worker")
    assert fence is not None
    applied = revisions.complete_fence(fence, _ack(command, executor_ref))
    dispatch = revisions.claim_successor_dispatch("dispatch-worker")
    assert dispatch is not None
    assert dispatch.item.attempt_id == applied.successor_attempt_id
    successor_ref = f"executor:{dispatch.item.attempt_id}"

    revisions.complete_successor_dispatch(
        dispatch,
        ExecutorDeliveryResult(
            successor_ref,
            _observations(dispatch.item, executor_ref=successor_ref),
        ),
    )

    truth = revisions.truth(task_id, _scope())
    assert truth.task.state is FormalTaskState.RUNNING
    assert truth.attempt.state is FormalAttemptState.RUNNING
    assert truth.attempt.executor_ref == successor_ref
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=32)
    assert [event.event_type for event in snapshot.events] == [
        "task.revision_applied",
        "attempt.accepted",
        "attempt.running",
        "task.running",
    ]


def test_reopen_preserves_revision_truth_and_does_not_rerun(tmp_path: Path) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = revisions.claim_fence("fence-worker")
    assert fence is not None
    revisions.complete_fence(fence, _ack(command, executor_ref))

    reopened_store = SqliteTaskStore(store.database_path)
    reopened = SqliteTaskRevisionStore(reopened_store)
    truth = reopened.truth(task_id, _scope())

    assert truth.current_revision.task_revision == 2
    assert truth.cleanup_ack is not None
    dispatch = reopened.claim_successor_dispatch("restart-worker")
    assert dispatch is not None
    assert reopened.claim_successor_dispatch("duplicate-worker") is None


@pytest.mark.parametrize(
    "boundary",
    [
        "revision.request.after_initial_revision",
        "revision.request.after_command",
        "revision.request.after_fence_outbox",
        "revision.request.after_requested_event",
    ],
)
def test_request_failpoints_roll_back_every_revision_effect(
    tmp_path: Path, boundary: str
) -> None:
    store, task_id, attempt_id, _executor_ref = _running_task(tmp_path)

    def failpoint(name: str) -> None:
        if name == boundary:
            raise RuntimeError(boundary)

    revisions = SqliteTaskRevisionStore(store, failpoint=failpoint)
    before = _revision_rows(store.database_path)
    command = _command(task_id, attempt_id)

    with pytest.raises(RuntimeError, match=boundary):
        revisions.request_revision(
            command,
            _grant(command),
            initial_constraints=TaskRevisionConstraints(("src", "tests")),
            observed_at=NOW,
        )

    assert _revision_rows(store.database_path) == before


@pytest.mark.parametrize(
    "boundary",
    [
        "revision.complete.after_predecessor",
        "revision.complete.after_successor_attempt",
        "revision.complete.after_task_pointer",
        "revision.complete.after_boundary_event",
        "revision.complete.after_dispatch_outbox",
        "revision.complete.after_successor_revision",
        "revision.complete.after_cleanup_ack",
        "revision.complete.after_command",
        "revision.complete.after_fence_outbox",
    ],
)
def test_complete_failpoints_restore_exact_claimed_predecessor(
    tmp_path: Path, boundary: str
) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    setup = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    setup.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = setup.claim_fence("fence-worker")
    assert fence is not None
    before = _revision_rows(store.database_path)

    def failpoint(name: str) -> None:
        if name == boundary:
            raise RuntimeError(boundary)

    revisions = SqliteTaskRevisionStore(store, failpoint=failpoint)
    with pytest.raises(RuntimeError, match=boundary):
        revisions.complete_fence(fence, _ack(command, executor_ref))

    assert _revision_rows(store.database_path) == before
    assert store.get_task(task_id, _scope()).attempt_id == attempt_id


def test_concurrent_distinct_revisions_admit_one_fence(tmp_path: Path) -> None:
    store, task_id, attempt_id, _executor_ref = _running_task(tmp_path)
    first = SqliteTaskRevisionStore(store)
    second = SqliteTaskRevisionStore(SqliteTaskStore(store.database_path))
    commands = (
        _command(task_id, attempt_id, command_id="revision-a"),
        _command(task_id, attempt_id, command_id="revision-b"),
    )

    def request(pair: tuple[SqliteTaskRevisionStore, TaskRevisionCommand]):
        revisions, command = pair
        try:
            return revisions.request_revision(
                command,
                _grant(command),
                initial_constraints=TaskRevisionConstraints(("src", "tests")),
                observed_at=NOW,
            )
        except FormalTaskViolation as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(request, zip((first, second), commands, strict=True)))

    assert sum(isinstance(result, FormalTaskViolation) for result in results) == 1
    rejected = next(
        result for result in results if isinstance(result, FormalTaskViolation)
    )
    assert rejected.reason == "TASK_REVISION_ALREADY_PENDING"
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM s85_revision_commands"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM s85_revision_outbox"
        ).fetchone() == (1,)


def _execution_ack(
    task_id: str,
    attempt_id: str,
    executor_ref: str,
    **changes: object,
) -> TaskRevisionExecutionAck:
    values: dict[str, object] = {
        "task_id": task_id,
        "task_revision": 2,
        "attempt_id": attempt_id,
        "executor_ref": executor_ref,
        "fixture_identity": "fixture-clean-base-1",
        "execution_ack": True,
        "changed_paths": ("src/result.py",),
        "diff_summary": "1 changed path(s)",
        "verifier": TaskRevisionVerifierResult(
            "python-check",
            TaskRevisionVerifierState.PASSED,
            0,
            False,
            "0" * 64,
            "1 passed",
        ),
        "cleanup_state": "successor_cleanup_resolved",
        "forbidden_side_effect_count": 0,
        "verified_success": True,
    }
    values.update(changes)
    return TaskRevisionExecutionAck(**values)  # type: ignore[arg-type]


def test_execution_ack_is_immutable_store_truth_and_never_inferred(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    revisions = SqliteTaskRevisionStore(store)
    command = _command(task_id, attempt_id)
    revisions.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src", "tests")),
        observed_at=NOW,
    )
    fence = revisions.claim_fence("fence-worker")
    assert fence is not None
    applied = revisions.complete_fence(fence, _ack(command, executor_ref))
    dispatch = revisions.claim_successor_dispatch("dispatch-worker")
    assert dispatch is not None
    successor_ref = f"executor:{dispatch.item.attempt_id}"
    revisions.complete_successor_dispatch(
        dispatch,
        ExecutorDeliveryResult(
            successor_ref,
            _observations(
                dispatch.item,
                executor_ref=successor_ref,
                terminal=TerminalOutcome.COMPLETED,
            ),
        ),
    )
    assert applied.successor_attempt_id is not None
    ack = _execution_ack(task_id, applied.successor_attempt_id, successor_ref)

    assert revisions.record_execution_ack(_scope(), ack) == ack
    assert revisions.record_execution_ack(_scope(), ack) == ack
    truth = revisions.truth(task_id, _scope())
    assert truth.execution_ack == ack
    assert truth.to_dict()["execution"] == ack.to_dict()
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=32)
    recorded = snapshot.events[-1]
    assert recorded.event_type == "task.revision_execution_recorded"
    assert recorded.details["verified_success"] is True
    assert recorded.details["verifier_result"] == "passed"

    conflicting = _execution_ack(
        task_id,
        applied.successor_attempt_id,
        successor_ref,
        diff_summary="forged changed summary",
    )
    with pytest.raises(FormalTaskViolation) as conflict:
        revisions.record_execution_ack(_scope(), conflicting)
    assert conflict.value.reason == "TASK_REVISION_EXECUTION_ACK_CONFLICT"
    assert revisions.truth(task_id, _scope()).execution_ack == ack


def test_execution_ack_failure_rolls_back_without_verified_success(
    tmp_path: Path,
) -> None:
    store, task_id, attempt_id, executor_ref = _running_task(tmp_path)
    command = _command(task_id, attempt_id)
    setup = SqliteTaskRevisionStore(store)
    setup.request_revision(
        command,
        _grant(command),
        initial_constraints=TaskRevisionConstraints(("src",)),
        observed_at=NOW,
    )
    fence = setup.claim_fence("fence-worker")
    assert fence is not None
    applied = setup.complete_fence(fence, _ack(command, executor_ref))
    dispatch = setup.claim_successor_dispatch("dispatch-worker")
    assert dispatch is not None
    successor_ref = f"executor:{dispatch.item.attempt_id}"
    setup.complete_successor_dispatch(
        dispatch,
        ExecutorDeliveryResult(
            successor_ref,
            _observations(
                dispatch.item,
                executor_ref=successor_ref,
                terminal=TerminalOutcome.COMPLETED,
            ),
        ),
    )

    def failpoint(name: str) -> None:
        if name == "revision.execution.after_ack":
            raise RuntimeError(name)

    revisions = SqliteTaskRevisionStore(store, failpoint=failpoint)
    assert applied.successor_attempt_id is not None
    failed = _execution_ack(
        task_id,
        applied.successor_attempt_id,
        successor_ref,
        verifier=TaskRevisionVerifierResult(
            "python-check",
            TaskRevisionVerifierState.FAILED,
            1,
            False,
            "1" * 64,
            "failed",
        ),
        verified_success=False,
    )
    with pytest.raises(RuntimeError, match="revision.execution.after_ack"):
        revisions.record_execution_ack(_scope(), failed)
    assert setup.truth(task_id, _scope()).execution_ack is None
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM s85_revision_execution_acks"
        ).fetchone() == (0,)
