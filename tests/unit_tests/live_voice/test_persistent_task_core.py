# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CommandEnvelope,
    ErrorCode,
    InputCommitState,
    QueryEnvelope,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
    WorkProgressEventV2,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskViolation,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskRecord,
    ReconciliationState,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    utc_now,
)
from jiuwenswarm.server.live_voice.persistent_task_core import (
    PersistentTaskCore,
    project_task_event,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    FORMAL_PROJECT_EXECUTOR_ID,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.live_voice.voice_task_policy import (
    FormalTaskPolicyAdapter,
    FormalTaskPolicyInput,
)

NOW = "2026-08-05T12:00:00Z"
EXPIRY = "2026-08-05T13:00:00Z"


def _scope() -> ScopeRef:
    return ScopeRef("user-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def _grant(
    operation: str,
    *,
    command_id: str | None,
    target: str | None,
) -> TaskAuthorizationGrant:
    return TaskAuthorizationGrant(
        principal_id="user-1",
        scope=_scope(),
        operation=operation,
        command_id=command_id,
        target_task_id=target,
        allowed_capabilities=frozenset({operation}),
        confirmation_id="confirm-1" if command_id is not None else None,
        confirmed=command_id is not None,
        expires_at=EXPIRY,
    )


def _context(project: Path) -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="gateway.project_registry",
        stable_id="project-1",
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value="a77516a0",
        scope=_scope(),
        permissions=("task.execute", "project.write"),
        expires_at=EXPIRY,
        redaction_policy_id="live_voice.project.v1",
    )


def _create(
    project: Path,
    *,
    instruction: str = "Change one project file.",
    identity_suffix: str = "",
):
    command_id = f"command-create{identity_suffix}"
    commit_id = f"commit-1{identity_suffix}"
    turn_id = f"turn-1{identity_suffix}"
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="voice",
        operation="task.create",
        request_id=f"request-create{identity_suffix}",
        command_id=command_id,
        issued_at=NOW,
        scope=_scope(),
        correlation_id=f"correlation-1{identity_suffix}",
        authorization=_grant("task.create", command_id=command_id, target=None),
        turn_id=turn_id,
        commit_id=commit_id,
        name="Formal project task",
        instruction=instruction,
        context=_context(project),
        destructive=True,
        confirmed=True,
        confirmation_id="confirm-1",
    )
    commits = TurnCommitLedger()
    commits.accept(
        TurnCommit.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "commit_id": commit_id,
                "turn_id": turn_id,
                "interaction_id": f"interaction-1{identity_suffix}",
                "text": instruction,
                "hypothesis_provenance": {"provider": "test"},
                "scope": _scope().to_dict(),
                "context_refs": [],
                "committed_at": NOW,
            }
        )
    )
    return FormalTaskPolicyAdapter(commits).map(intent)


def _cancel(task_id: str):
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.cancel",
        request_id="request-cancel",
        command_id="command-cancel",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant(
            "task.cancel", command_id="command-cancel", target=task_id
        ),
        task_id=task_id,
        destructive=True,
        confirmed=True,
        confirmation_id="confirm-1",
    )
    return FormalTaskPolicyAdapter().map(intent)


def _status(task_id: str):
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.status",
        request_id="request-status",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant("task.status", command_id=None, target=task_id),
        task_id=task_id,
    )
    return FormalTaskPolicyAdapter().map(intent)


def _events(task_id: str, after_seq: int):
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.events",
        request_id="request-events",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant("task.events", command_id=None, target=task_id),
        task_id=task_id,
        after_seq=after_seq,
    )
    return FormalTaskPolicyAdapter().map(intent)


def _observations(
    item: PersistentOutboxItem,
    *,
    outcome: TerminalOutcome | None = None,
) -> tuple[ExecutorObservation, ...]:
    target_seq = 2 if outcome is not None else 1
    states = (
        (FormalAttemptState.ACCEPTED, None),
        (FormalAttemptState.RUNNING, None),
        (FormalAttemptState.TERMINAL, outcome),
    )
    result = []
    for seq in range(item.source_seq + 1, target_seq + 1):
        state, state_outcome = states[seq]
        result.append(
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=FORMAL_PROJECT_EXECUTOR_ID,
                executor_ref=f"legacy:{item.attempt_id}",
                task_id=item.task_id,
                attempt_id=item.attempt_id,
                source_event_id=f"legacy:{item.attempt_id}:{seq}",
                source_seq=seq,
                attempt_state=state,
                attempt_outcome=state_outcome,
                occurred_at=utc_now(),
                raw_status=("success" if outcome else "running"),
            )
        )
    return tuple(result)


class _Executor:
    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(self) -> None:
        self.dispatches: list[str] = []
        self.cancels: list[str] = []
        self.fail_dispatches = 0
        self.status_resolution: ExecutorResolution | None = None

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.dispatches.append(item.attempt_id)
        if self.fail_dispatches:
            self.fail_dispatches -= 1
            raise RuntimeError("transient delivery failure")
        return ExecutorDeliveryResult(f"legacy:{item.attempt_id}", _observations(item))

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.cancels.append(item.attempt_id)
        return ExecutorDeliveryResult(
            f"legacy:{item.attempt_id}",
            _observations(item, outcome=TerminalOutcome.CANCELLED),
        )

    async def status(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        if self.status_resolution is None:
            return ExecutorDeliveryResult(attempt.executor_ref or "", ())
        return ExecutorObservation(
            resolution=self.status_resolution,
            executor_id=self.executor_id,
            executor_ref=attempt.executor_ref,
            task_id=task.task_id,
            attempt_id=attempt.attempt_id,
            source_event_id=None,
            source_seq=None,
            attempt_state=None,
            attempt_outcome=None,
            occurred_at=utc_now(),
            raw_status=None,
            error=f"STATUS_{self.status_resolution.value.upper()}",
        )


@pytest.mark.parametrize(
    "failpoint",
    [
        "create.before_ids",
        "create.after_task",
        "create.after_event",
        "create.after_outbox",
        "create.after_command",
    ],
)
def test_create_is_atomic_at_every_persistence_boundary(
    tmp_path: Path, failpoint: str
) -> None:
    def fail(name: str) -> None:
        if name == failpoint:
            raise RuntimeError(name)

    store = SqliteTaskStore(tmp_path / f"{failpoint}.sqlite", failpoint=fail)
    invocation = _create(tmp_path)

    with pytest.raises(RuntimeError, match=failpoint):
        PersistentTaskCore(store, _Executor()).execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
        )

    assert store.counts() == {
        "commands": 0,
        "tasks": 0,
        "attempts": 0,
        "task_events": 0,
        "executor_events": 0,
        "outbox": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failpoint",
    [
        "cancel.after_snapshot",
        "cancel.after_request_event",
        "cancel.after_outbox_or_terminal",
        "cancel.after_command",
    ],
)
async def test_active_cancel_is_atomic_at_every_persistence_boundary(
    tmp_path: Path, failpoint: str
) -> None:
    enabled = False

    def fail(name: str) -> None:
        if enabled and name == failpoint:
            raise RuntimeError(name)

    store = SqliteTaskStore(tmp_path / f"{failpoint}.sqlite", failpoint=fail)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    persisted = store.get_task(str(created.result["task_id"]), _scope())
    assert persisted.spec.origin.to_dict() == {
        "kind": "committed_turn",
        "turn_id": "turn-1",
        "commit_id": "commit-1",
    }
    await core.drain_outbox()
    task_id = str(created.result["task_id"])
    before_counts = store.counts()
    before_task = store.get_task(task_id, _scope())
    before_events = store.events(task_id, _scope())
    enabled = True
    cancel = _cancel(task_id)

    with pytest.raises(RuntimeError, match=failpoint):
        core.execute(cancel.envelope, cancel.authorization, now=NOW)

    assert store.counts() == before_counts
    assert store.get_task(task_id, _scope()) == before_task
    assert store.events(task_id, _scope()) == before_events
    assert executor.cancels == []


def test_same_create_is_idempotent_across_store_instances_and_threads(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    stores = (SqliteTaskStore(database), SqliteTaskStore(database))
    invocation = _create(tmp_path)

    def execute(index: int):
        return PersistentTaskCore(stores[index], _Executor()).execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, (0, 1)))

    assert all(result.ok for result in results)
    assert results[0].result == results[1].result
    assert stores[0].counts() == {
        "commands": 1,
        "tasks": 1,
        "attempts": 1,
        "task_events": 1,
        "executor_events": 0,
        "outbox": 1,
    }


def test_missing_authorization_and_conflicting_replay_have_zero_new_effects(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)

    denied = core.execute(
        invocation.envelope, None, context=invocation.context, now=NOW
    )
    assert not denied.ok
    assert denied.error is not None
    assert denied.error.reason == "FORMAL_TASK_AUTHORIZATION_REQUIRED"
    assert sum(store.counts().values()) == 0

    accepted = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    before = store.counts()
    conflict = _create(tmp_path, instruction="Different intent under same command id.")
    rejected = core.execute(
        conflict.envelope,
        conflict.authorization,
        context=conflict.context,
        now=NOW,
    )

    assert accepted.ok
    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.reason == "IDEMPOTENCY_CONFLICT"
    assert store.counts() == before
    assert executor.dispatches == []


def test_direct_command_cannot_omit_operation_capability(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    raw = invocation.envelope.to_dict()
    raw["required_capabilities"] = []
    weakened = CommandEnvelope.from_dict(raw)

    rejected = core.execute(
        weakened,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )

    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.reason == "FORMAL_TASK_CAPABILITY_MISMATCH"
    assert sum(store.counts().values()) == 0


def test_direct_envelopes_reject_noncanonical_target_and_hidden_payload(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    raw_create = invocation.envelope.to_dict()
    raw_create["target_ref"] = {"kind": "task", "id": "create:other-command"}
    wrong_target = CommandEnvelope.from_dict(raw_create)

    rejected_create = core.execute(
        wrong_target,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert not rejected_create.ok
    assert rejected_create.error is not None
    assert rejected_create.error.reason == "FORMAL_TASK_TARGET_MISMATCH"
    assert sum(store.counts().values()) == 0

    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    before = store.counts()

    status = _status(task_id)
    raw_status = status.envelope.to_dict()
    raw_status["payload"] = {"repair": True}
    rejected_query = core.query(
        QueryEnvelope.from_dict(raw_status), status.authorization, now=NOW
    )
    assert not rejected_query.ok
    assert rejected_query.error is not None
    assert rejected_query.error.reason == "INVALID_FORMAL_TASK_PAYLOAD"

    assert store.counts() == before
    assert store.get_task(task_id, _scope()).cancel_requested is False


@pytest.mark.parametrize(
    ("context_change", "reason"),
    [
        ({"redacted": True}, "TASK_CONTEXT_REDACTED"),
        (
            {"revision_kind": "unversioned", "revision_value": None},
            "UNVERSIONED_DESTRUCTIVE_CONTEXT",
        ),
        ({"expires_at": "2026-08-05T11:59:59Z"}, "TASK_CONTEXT_EXPIRED"),
    ],
)
def test_unsafe_context_is_rejected_before_persistence(
    tmp_path: Path,
    context_change: dict[str, object],
    reason: str,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    context = replace(invocation.context, **context_change)

    rejected = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=context,
        now=NOW,
    )

    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.reason == reason
    assert sum(store.counts().values()) == 0


@pytest.mark.asyncio
async def test_outbox_retries_the_same_attempt_and_read_query_is_side_effect_free(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    executor.fail_dispatches = 1
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None

    with pytest.raises(RuntimeError, match="transient"):
        await core.drain_outbox_once(worker_id="worker-1")
    assert await core.drain_outbox_once(worker_id="worker-2") is True
    assert executor.dispatches == [
        created.result["attempt_id"],
        created.result["attempt_id"],
    ]

    before = store.counts()
    status = _status(str(created.result["task_id"]))
    result = core.query(status.envelope, status.authorization, now=NOW)
    assert result.ok
    assert store.counts() == before


@pytest.mark.asyncio
async def test_released_outbox_does_not_starve_another_pending_task(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    executor.fail_dispatches = 1
    core = PersistentTaskCore(store, executor)
    first = _create(tmp_path, identity_suffix="-first")
    second = _create(tmp_path, identity_suffix="-second")
    first_result = core.execute(
        first.envelope,
        first.authorization,
        context=first.context,
        now=NOW,
    )
    second_result = core.execute(
        second.envelope,
        second.authorization,
        context=second.context,
        now=NOW,
    )
    assert first_result.ok and second_result.ok

    with pytest.raises(RuntimeError, match="transient"):
        await core.drain_outbox_once(worker_id="worker-1")
    failed_attempt = executor.dispatches[0]

    assert await core.drain_outbox_once(worker_id="worker-2") is True
    assert executor.dispatches[1] != failed_attempt
    assert await core.drain_outbox_once(worker_id="worker-3") is True
    assert executor.dispatches[2] == failed_attempt


def test_executor_duplicate_is_noop_and_conflicting_duplicate_is_rejected(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    item = store.claim_outbox("worker")
    assert item is not None
    observations = _observations(item)
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )
    before = store.counts()

    store.apply_observations(observations)
    assert store.counts() == before

    conflict = replace(observations[0], summary="different canonical fact")
    with pytest.raises(FormalTaskViolation) as raised:
        store.apply_observations((conflict,))
    assert raised.value.reason == "EXECUTOR_EVENT_ID_CONFLICT"
    assert store.counts() == before


def test_wrong_executor_binding_and_sequence_gap_leave_state_unchanged(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    item = store.claim_outbox("worker")
    assert item is not None
    before = store.counts()
    valid = _observations(item)[0]

    with pytest.raises(FormalTaskViolation) as wrong_binding:
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=(replace(valid, executor_id="foreign-executor"),),
        )
    assert wrong_binding.value.reason == "EXECUTOR_OBSERVATION_BINDING_MISMATCH"
    assert store.counts() == before

    with pytest.raises(FormalTaskViolation) as gap:
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=(replace(valid, source_seq=1),),
        )
    assert gap.value.reason == "EXECUTOR_EVENT_SEQUENCE_GAP"
    assert store.counts() == before


@pytest.mark.asyncio
async def test_cancel_before_dispatch_fences_executor_with_zero_external_calls(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    cancel = _cancel(str(created.result["task_id"]))

    cancelled = core.execute(cancel.envelope, cancel.authorization, now=NOW)

    assert cancelled.ok
    assert await core.drain_outbox() == 0
    assert executor.dispatches == []
    assert executor.cancels == []
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is TerminalOutcome.CANCELLED
    assert task.dispatch_fenced is True
    events = store.events(task.task_id, _scope())
    cancel_requested = next(
        event for event in events if event.event_type == "task.cancel_requested"
    )
    assert cancel_requested.scope == _scope()
    assert cancel_requested.causation_id == "command-cancel"
    with pytest.raises(FormalTaskViolation) as raised:
        project_task_event(cancel_requested)
    assert raised.value.reason == "TASK_EVENT_NOT_PROJECTABLE"


@pytest.mark.asyncio
async def test_active_cancel_waits_for_exact_binding_then_calls_executor_once(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None

    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    cancel = _cancel(str(created.result["task_id"]))
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok
    assert store.claim_outbox("cancel-worker") is None

    delivery = await executor.dispatch(dispatch)
    store.complete_outbox(
        dispatch,
        executor_ref=delivery.executor_ref,
        observations=delivery.observations,
    )
    assert await core.drain_outbox(worker_id="cancel-worker") == 1
    assert executor.dispatches == [created.result["attempt_id"]]
    assert executor.cancels == [created.result["attempt_id"]]
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is TerminalOutcome.CANCELLED


@pytest.mark.asyncio
async def test_cancel_after_unknown_dispatch_retries_binding_before_executor_cancel(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    attempt_id = str(created.result["attempt_id"])

    uncertain = store.claim_outbox("first-dispatch")
    assert uncertain is not None
    await executor.dispatch(uncertain)
    assert store.release_outbox(uncertain, "accepted externally; result unavailable")

    cancel = _cancel(str(created.result["task_id"]))
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok and acknowledged.result is not None
    assert acknowledged.result["outbox_id"] is not None
    assert store.get_task(str(created.result["task_id"]), _scope()).outcome is None

    assert await core.drain_outbox(worker_id="reconcile-dispatch") == 2
    assert executor.dispatches == [attempt_id, attempt_id]
    assert executor.cancels == [attempt_id]
    assert (
        store.get_task(str(created.result["task_id"]), _scope()).outcome
        is TerminalOutcome.CANCELLED
    )


@pytest.mark.asyncio
async def test_executor_terminal_truth_suppresses_racing_cancel_side_effect(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    cancel = _cancel(str(created.result["task_id"]))
    assert core.execute(cancel.envelope, cancel.authorization, now=NOW).ok

    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch, outcome=TerminalOutcome.COMPLETED),
    )

    assert await core.drain_outbox(worker_id="cancel-worker") == 0
    assert executor.cancels == []
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is TerminalOutcome.COMPLETED


@pytest.mark.asyncio
async def test_active_cancel_delivery_rejection_preserves_lifecycle_for_reconciliation(
    tmp_path: Path,
) -> None:
    class RejectingCancelExecutor(_Executor):
        async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
            self.cancels.append(item.attempt_id)
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_ACCESS_MISMATCH",
                "cannot prove control of the original attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = RejectingCancelExecutor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    cancel = _cancel(str(created.result["task_id"]))
    assert core.execute(cancel.envelope, cancel.authorization, now=NOW).ok

    assert await core.drain_outbox() == 1
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is None
    assert task.reconciliation_state is ReconciliationState.PENDING
    assert task.reconciliation_reason is not None
    assert "LEGACY_EXECUTOR_ACCESS_MISMATCH" in task.reconciliation_reason


@pytest.mark.asyncio
async def test_restart_delivery_unavailable_keeps_original_outbox_and_marks_pending(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    first = PersistentTaskCore(SqliteTaskStore(database), _Executor())
    invocation = _create(tmp_path)
    created = first.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None

    unavailable_executor = _Executor()
    unavailable_executor.fail_dispatches = 1
    store = SqliteTaskStore(database)
    restarted = PersistentTaskCore(store, unavailable_executor)
    summary = await restarted.reconcile()

    assert summary["delivery_unavailable"] == 1
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is None
    assert task.reconciliation_state is ReconciliationState.PENDING
    assert task.attempt_id == created.result["attempt_id"]
    assert store.counts()["outbox"] == 1


@pytest.mark.asyncio
async def test_restart_does_not_reclaim_a_live_cross_process_outbox_claim(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    live_claim = store.claim_outbox("still-active-worker")
    assert live_claim is not None
    restart_executor = _Executor()

    summary = await PersistentTaskCore(
        SqliteTaskStore(database), restart_executor
    ).reconcile()

    assert summary["reset_claims"] == 0
    assert summary["delivered"] == 0
    assert restart_executor.dispatches == []
    assert store.claim_outbox("overlapping-worker") is None
    assert store.release_outbox(live_claim, "test cleanup") is True


@pytest.mark.asyncio
async def test_restart_reclaims_only_an_expired_claim_and_reuses_the_attempt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    expired = store.claim_outbox("dead-worker")
    assert expired is not None
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE outbox SET claimed_at=? WHERE outbox_id=?",
            ("2000-01-01T00:00:00Z", expired.outbox_id),
        )
    restart_executor = _Executor()

    summary = await PersistentTaskCore(
        SqliteTaskStore(database), restart_executor
    ).reconcile()

    assert summary["reset_claims"] == 1
    assert summary["delivered"] == 1
    assert restart_executor.dispatches == [created.result["attempt_id"]]
    assert store.counts()["attempts"] == 1


def test_reclaimed_outbox_claim_fences_the_stale_worker_result(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    stale = store.claim_outbox("dead-worker")
    assert stale is not None
    assert store.reset_expired_outbox_claims(claimed_before="9999-01-01T00:00:00Z") == 1
    current = store.claim_outbox("replacement-worker")
    assert current is not None

    with pytest.raises(FormalTaskViolation) as raised:
        store.complete_outbox(
            stale,
            executor_ref=f"legacy:{stale.attempt_id}",
            observations=_observations(stale),
        )

    assert raised.value.reason == "OUTBOX_CLAIM_LOST"
    store.complete_outbox(
        current,
        executor_ref=f"legacy:{current.attempt_id}",
        observations=_observations(current),
    )


@pytest.mark.asyncio
async def test_lost_reconciliation_suppresses_retrying_cancel_outbox(
    tmp_path: Path,
) -> None:
    class UncertainCancelExecutor(_Executor):
        async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
            self.cancels.append(item.attempt_id)
            raise FormalTaskViolation(
                "EXECUTOR_CANCEL_UNAVAILABLE",
                "cancel result is unavailable",
                ErrorCode.UNAVAILABLE,
            )

    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = UncertainCancelExecutor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    task_id = str(created.result["task_id"])
    cancel = _cancel(task_id)
    assert core.execute(cancel.envelope, cancel.authorization, now=NOW).ok
    executor.status_resolution = ExecutorResolution.LOST

    summary = await core.reconcile()

    assert summary["delivery_unavailable"] == 1
    assert summary["lost"] == 1
    assert await core.drain_outbox() == 0
    assert executor.cancels == [created.result["attempt_id"]]
    assert store.get_task(task_id, _scope()).outcome is TerminalOutcome.INTERRUPTED


def test_wrong_scope_query_and_wrong_grant_do_not_disclose_or_mutate(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    before = store.counts()
    task_id = str(created.result["task_id"])

    cancel = _cancel(task_id)
    wrong_grant = replace(cancel.authorization, principal_id="other-user")
    denied = core.execute(cancel.envelope, wrong_grant, now=NOW)
    assert not denied.ok
    assert denied.error is not None
    assert denied.error.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"

    foreign_scope = ScopeRef(
        "other-user", "project-1", "session-1", Assurance.AUTHENTICATED
    )
    foreign_query = replace(
        _status(task_id),
        authorization=TaskAuthorizationGrant(
            principal_id="other-user",
            scope=foreign_scope,
            operation="task.status",
            command_id=None,
            target_task_id=task_id,
            allowed_capabilities=frozenset({"task.status"}),
            confirmation_id=None,
            confirmed=False,
            expires_at=EXPIRY,
        ),
    )
    raw_query = foreign_query.envelope.to_dict()
    raw_query["scope"] = foreign_scope.to_dict()
    hidden = core.query(
        QueryEnvelope.from_dict(raw_query), foreign_query.authorization, now=NOW
    )
    assert not hidden.ok
    assert hidden.error is not None
    assert hidden.error.reason == "TASK_NOT_FOUND"
    assert store.counts() == before


def test_corrupt_persisted_spec_fails_closed_without_executor_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    before = store.counts()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE tasks SET spec_json=? WHERE task_id=?",
            ("not-json", task_id),
        )
    status = _status(task_id)

    result = core.query(status.envelope, status.authorization, now=NOW)

    assert not result.ok
    assert result.error is not None
    assert result.error.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    assert executor.dispatches == []
    assert executor.cancels == []


def test_structurally_corrupt_persisted_scope_fails_closed_without_executor_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    before = store.counts()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE tasks SET scope_json=? WHERE task_id=?",
            (
                '{"assurance":"authenticated","project_id":"project-1",'
                '"session_id":"session-1","user_id":42}',
                task_id,
            ),
        )
    status = _status(task_id)

    result = core.query(status.envelope, status.authorization, now=NOW)

    assert not result.ok
    assert result.error is not None
    assert result.error.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
async def test_task_event_projection_is_pure_and_preserves_source(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    invocation = _create(tmp_path)
    core = PersistentTaskCore(store, _Executor())
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    event = next(
        candidate
        for candidate in store.events(str(created.result["task_id"]), _scope())
        if candidate.event_type == "task.running"
    )
    before = store.counts()

    progress = project_task_event(event)

    assert progress["work_ref"] == {"kind": "task", "id": created.result["task_id"]}
    parsed = WorkProgressEventV2.from_dict(progress)
    assert parsed.source.source_work_ref == parsed.work_ref
    assert progress["source"]["event_id"] == event.event_id
    assert progress["source"]["adapter"] is None
    assert progress["urgency"] == "unknown"
    assert progress["speakability"] == "not_speakable"
    assert event.scope == _scope()
    assert event.to_dict()["scope"] == _scope().to_dict()
    assert store.counts() == before


@pytest.mark.asyncio
async def test_attempt_event_cannot_emit_duplicate_progress_and_event_head_is_authoritative(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    task_id = str(created.result["task_id"])
    events = store.events(task_id, _scope())
    attempt_event = next(
        event for event in events if event.event_type.startswith("attempt.")
    )

    with pytest.raises(FormalTaskViolation) as raised:
        project_task_event(attempt_event)
    assert raised.value.reason == "TASK_EVENT_NOT_PROJECTABLE"

    query = _events(task_id, after_seq=999)
    result = core.query(query.envelope, query.authorization, now=NOW)
    assert result.ok and result.result is not None
    assert result.result["events"] == []
    assert result.result["head_seq"] == events[-1].seq


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resolution", "terminal", "reconciliation"),
    [
        (ExecutorResolution.LOST, True, None),
        (ExecutorResolution.UNAVAILABLE, False, ReconciliationState.PENDING),
        (None, False, ReconciliationState.RESOLVED),
    ],
)
async def test_restart_reconciles_only_the_original_attempt(
    tmp_path: Path,
    resolution: ExecutorResolution | None,
    terminal: bool,
    reconciliation: ReconciliationState | None,
) -> None:
    database = tmp_path / f"tasks-{resolution}.sqlite"
    first_executor = _Executor()
    first = PersistentTaskCore(SqliteTaskStore(database), first_executor)
    invocation = _create(tmp_path)
    created = first.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await first.drain_outbox()

    restart_executor = _Executor()
    restart_executor.status_resolution = resolution
    restarted_store = SqliteTaskStore(database)
    restarted = PersistentTaskCore(restarted_store, restart_executor)
    summary = await restarted.reconcile()

    task = restarted_store.get_task(str(created.result["task_id"]), _scope())
    assert task.attempt_id == created.result["attempt_id"]
    assert (task.outcome is TerminalOutcome.INTERRUPTED) is terminal
    assert task.reconciliation_state is reconciliation
    assert restarted_store.counts()["attempts"] == 1
    assert sum(summary[key] for key in ("known", "unavailable", "lost")) == 1
