# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    MAX_SAFE_INTEGER,
    Assurance,
    CommandEnvelope,
    ContractViolation,
    OriginRef,
    ProducerRef,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskSpec,
    FormalTaskViolation,
    PersistentTaskEvent,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    TaskRetryProductRequestFingerprint,
    TaskRetryAuthoritySnapshot,
)
from jiuwenswarm.server.live_voice.durability_recovery_facts import (
    ExecutorRecoveryFacts,
)
from jiuwenswarm.server.live_voice.progress_notification_arbiter import (
    ForegroundFact,
    ForegroundSnapshot,
    ProgressNotificationArbiter,
    SpeechPolicy,
)
from jiuwenswarm.server.live_voice.task_event_subscription import (
    TaskEventSubscription,
)
from jiuwenswarm.server.live_voice.task_progress_return import (
    TASK_PROGRESS_PRESENTABLE_EVENTS,
    TaskProgressHandoffKind,
    TaskProgressNotificationIntent,
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
    TaskProgressReturnBridge,
    TaskProgressReturnReason,
    TaskProgressReturnState,
    TaskProgressReturnViolation,
    TaskProgressSourceDecision,
    TaskProgressTextEvent,
    TaskEventAuthorityProgressSource,
    _evidence_id,
    project_task_progress_event,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore

NOW = "2026-08-06T10:00:00Z"
EXPIRY = "2026-08-06T11:00:00Z"
AFTER_EXPIRY = "2026-08-06T12:00:00Z"
_DEFAULT_AUTHORIZATION = object()


def _scope(
    *,
    subject_id: str = "subject-1",
    project_id: str = "project-1",
    session_id: str = "session-1",
) -> ScopeRef:
    return ScopeRef(
        subject_id,
        project_id,
        session_id,
        Assurance.AUTHENTICATED,
    )


def _grant(
    *,
    task_id: str = "task-1",
    scope: ScopeRef | None = None,
    expires_at: str = EXPIRY,
) -> TaskAuthorizationGrant:
    granted_scope = scope or _scope()
    return TaskAuthorizationGrant(
        principal_id=granted_scope.subject_id,
        scope=granted_scope,
        operation="task.events",
        command_id=None,
        target_task_id=task_id,
        allowed_capabilities=frozenset({"task.events"}),
        confirmation_id=None,
        confirmed=False,
        expires_at=expires_at,
    )


def _binding(
    origin_kind: TaskProgressOriginKind,
    *,
    task_id: str = "task-1",
    scope: ScopeRef | None = None,
    correlation_id: str = "correlation-1",
    generation: int = 7,
) -> TaskProgressOriginBinding:
    current_scope = scope or _scope()
    assert current_scope.project_id is not None
    assert current_scope.session_id is not None
    return TaskProgressOriginBinding(
        scope=current_scope,
        task_id=task_id,
        session_id=current_scope.session_id,
        project_id=current_scope.project_id,
        correlation_id=correlation_id,
        origin_kind=origin_kind,
        origin_id=f"{origin_kind.value}-origin-1",
        generation_kind="conversation_generation",
        generation_id="conversation-1",
        generation=generation,
        source_instance_id="task-core-1",
        progress_producer=ProducerRef(
            component="task_progress_return",
            instance_id="task-progress-return-1",
            authority="adapter",
        ),
        progress_adapter="task_progress_return.v1",
    )


def _event(
    seq: int,
    event_type: str,
    state: str,
    *,
    task_id: str = "task-1",
    scope: ScopeRef | None = None,
    correlation_id: str = "correlation-1",
    event_id: str | None = None,
    producer: str = "task_core",
    outcome: str | None = None,
    details: dict[str, object] | None = None,
) -> PersistentTaskEvent:
    return PersistentTaskEvent(
        event_id=event_id or f"event-{seq}",
        task_id=task_id,
        attempt_id="attempt-1",
        scope=scope or _scope(),
        seq=seq,
        event_type=event_type,
        state=state,
        outcome=outcome,
        producer=producer,
        source_event_id=None,
        causation_id=f"cause-{seq}",
        correlation_id=correlation_id,
        occurred_at=NOW,
        details=details or {},
    )


def _lifecycle_events(*, start_seq: int = 0) -> list[PersistentTaskEvent]:
    return [
        _event(start_seq, "task.accepted", "accepted"),
        _event(start_seq + 1, "task.running", "running"),
        _event(
            start_seq + 2,
            "task.terminal",
            "terminal",
            outcome="completed",
        ),
    ]


def _foreground() -> ForegroundSnapshot:
    return ForegroundSnapshot(
        interaction=ForegroundFact.SAFE,
        response=ForegroundFact.SAFE,
        presentation=ForegroundFact.SAFE,
        speech_policy=SpeechPolicy.ALLOW_CANDIDATE,
    )


def _busy_foreground() -> ForegroundSnapshot:
    return ForegroundSnapshot(
        interaction=ForegroundFact.SAFE,
        response=ForegroundFact.BUSY,
        presentation=ForegroundFact.SAFE,
        speech_policy=SpeechPolicy.ALLOW_CANDIDATE,
    )


@dataclass(frozen=True, slots=True)
class _SubscriptionSnapshot:
    task_id: str


class _SubscriptionDouble:
    """Exact live subscription surface; no replay or fabricated prefix."""

    def __init__(
        self,
        events: list[PersistentTaskEvent] | None = None,
        *,
        task_id: str = "task-1",
        start_result: bool = True,
        close_gate: asyncio.Event | None = None,
        close_failures: int = 0,
    ) -> None:
        self.events = deque(events or [])
        self.task_id = task_id
        self.start_result = start_result
        self.start_calls = 0
        self.next_calls = 0
        self.close_calls = 0
        self.close_gate = close_gate
        self.close_failures = close_failures
        self.blocked = asyncio.Event()
        self._closed = asyncio.Event()
        self._changed = asyncio.Event()

    def snapshot(self) -> _SubscriptionSnapshot:
        return _SubscriptionSnapshot(task_id=self.task_id)

    async def start(self) -> bool:
        self.start_calls += 1
        return self.start_result

    async def next_event(self) -> PersistentTaskEvent:
        self.next_calls += 1
        while True:
            if self.events:
                return self.events.popleft()
            if self._closed.is_set():
                raise StopAsyncIteration
            self._changed.clear()
            if self.events or self._closed.is_set():
                continue
            # Deterministic barrier: the reader is parked exactly where the real
            # TaskEventSubscription awaits its change signal.
            self.blocked.set()
            try:
                await self._changed.wait()
            finally:
                self.blocked.clear()

    def publish(self, event: PersistentTaskEvent) -> None:
        self.events.append(event)
        self._changed.set()

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("injected subscription close failure")
        self._closed.set()
        self._changed.set()


class _PreparedSourceDouble:
    """Package-contract evidence only; not a formal authority handoff."""

    handoff_kind = TaskProgressHandoffKind.PACKAGE_CONTRACT_TEST
    evidence_id = "package-contract:prepared-contiguous-projection:1"

    def __init__(
        self,
        subscription: _SubscriptionDouble,
        events: list[PersistentTaskEvent],
        *,
        start_result: bool = True,
        close_failures: int = 0,
    ) -> None:
        self.subscription = cast(TaskEventSubscription, subscription)
        self.events = deque(events)
        self.start_result = start_result
        self.start_calls = 0
        self.next_calls = 0
        self.close_calls = 0
        self.close_failures = close_failures
        self.blocked = asyncio.Event()
        self._closed = asyncio.Event()
        self._changed = asyncio.Event()

    async def start(self) -> bool:
        self.start_calls += 1
        return self.start_result

    async def next_event(self) -> PersistentTaskEvent:
        self.next_calls += 1
        while True:
            if self.events:
                return self.events.popleft()
            if self._closed.is_set():
                raise StopAsyncIteration
            self._changed.clear()
            if self.events or self._closed.is_set():
                continue
            # Deterministic barrier: the reader is parked exactly where the real
            # TaskEventSubscription awaits its change signal.
            self.blocked.set()
            try:
                await self._changed.wait()
            finally:
                self.blocked.clear()

    def publish(self, event: PersistentTaskEvent) -> None:
        self.events.append(event)
        self._changed.set()

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("injected prepared source close failure")
        self._closed.set()
        self._changed.set()


class _RetainedDetachPreparedSourceDouble(_PreparedSourceDouble):
    """Prepared source whose detach outlives its own close() call.

    PreparedTaskProgressSource is a Protocol, and its close() contract does not
    promise that a parked read has ended by the time close() returns - only
    that the detach has been asked for.  The real TaskEventSubscription does
    detach in stages: DETACHING and a change signal first, its own poll worker
    exits, CLOSED and a second change signal after that, so "the source was
    closed" and "the parked read has ended" are two different instants there
    too.  It is fair to say, though, that the shipped subscription awaits its
    own poll worker inside close(), so on that concrete seam both signals land
    before close() returns and the gap is not observable from outside.

    This double therefore does not reproduce the shipped seam; it deliberately
    widens that same gap past close()'s return, which is the widest behaviour
    the Protocol still permits, so the bridge's invariant is pinned at the
    Protocol boundary rather than at one implementation's happen-to-be timing.
    Without the join, the bridge's own correctness on the shipped seam rests on
    an unpromised callback ordering; with it, the property holds for any
    conforming source.

    `detach_turns` is a count of event-loop turns, not wall-clock time: the loop
    is single threaded, so the release lands on a later turn by construction and
    not by a race.  Every value from one turn upward has the same meaning here.
    """

    detach_turns = 4

    def __init__(
        self,
        subscription: _SubscriptionDouble,
        events: list[PersistentTaskEvent],
    ) -> None:
        super().__init__(subscription, events)
        self.detach_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        self.close_calls += 1
        if self.detach_task is None:
            self.detach_task = asyncio.get_running_loop().create_task(
                self._finish_detach()
            )

    async def _finish_detach(self) -> None:
        for _ in range(self.detach_turns):
            await asyncio.sleep(0)
        self._closed.set()
        self._changed.set()


async def _wait_settled(bridge: TaskProgressReturnBridge) -> None:
    for _ in range(200):
        if not bridge.snapshot().worker_pending:
            return
        await asyncio.sleep(0)
    raise AssertionError("task progress bridge did not settle")


async def _wait_until(predicate) -> None:
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")


def _worker_task(task_id: str) -> asyncio.Task[None]:
    """The bridge's owner-loop worker, found by the exact name the bridge gives it."""

    return next(
        task
        for task in asyncio.all_tasks()
        if task.get_name() == f"live-voice-task-progress:{task_id}"
    )


def _authority_task(
    tmp_path: Path,
) -> tuple[SqliteTaskStore, str, str]:
    store = SqliteTaskStore(tmp_path / "authority-progress.sqlite")
    scope = _scope()
    context = ResolvedTaskContext(
        source="test.project_registry",
        stable_id=scope.project_id or "project-1",
        uri=tmp_path.resolve().as_uri(),
        revision_kind="version",
        revision_value="revision-1",
        scope=scope,
        permissions=("task.execute", "project.write"),
        expires_at=EXPIRY,
        redaction_policy_id="test-redaction-v1",
    )
    command = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-authority-progress",
            "command_id": "command-authority-progress",
            "command_type": "task.create",
            "issued_at": NOW,
            "scope": scope.to_dict(),
            "correlation_id": "correlation-authority-progress",
            "causation_id": None,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {
                "kind": "task",
                "id": "create:command-authority-progress",
            },
            "context_refs": [],
            "required_capabilities": ["task.create"],
            "payload": {},
            "extensions": {},
        }
    )
    result = store.create(
        command,
        FormalTaskSpec(
            name="authority progress",
            instruction="Perform one bounded task.",
            origin=OriginRef("structured", None, None),
            context=context,
            executor_id="executor-1",
            required_capabilities=("task.create",),
            side_effect_class="project_mutation",
            attributes=(),
        ),
        observed_at=NOW,
    )
    assert result.ok and result.result is not None
    return (
        store,
        str(result.result["task_id"]),
        command.correlation_id,
    )


def _advance_authority_task_running(store: SqliteTaskStore, task_id: str) -> None:
    task = store.get_task(task_id, _scope())
    item = store.claim_outbox("authority-progress-worker")
    assert item is not None
    assert item.task_id == task_id
    executor_ref = f"authority-progress:{task.attempt_id}"
    store.complete_outbox(
        item,
        executor_ref=executor_ref,
        observations=(
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=task.spec.executor_id,
                executor_ref=executor_ref,
                task_id=task_id,
                attempt_id=task.attempt_id,
                source_event_id=f"{executor_ref}:0",
                source_seq=0,
                attempt_state=FormalAttemptState.ACCEPTED,
                attempt_outcome=None,
                occurred_at=NOW,
                raw_status="accepted",
            ),
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=task.spec.executor_id,
                executor_ref=executor_ref,
                task_id=task_id,
                attempt_id=task.attempt_id,
                source_event_id=f"{executor_ref}:1",
                source_seq=1,
                attempt_state=FormalAttemptState.RUNNING,
                attempt_outcome=None,
                occurred_at=NOW,
                raw_status="running",
            ),
        ),
    )


def _finish_authority_task(store: SqliteTaskStore, task_id: str) -> None:
    task = store.get_task(task_id, _scope())
    executor_ref = f"authority-progress:{task.attempt_id}"
    store.apply_observations(
        (
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=task.spec.executor_id,
                executor_ref=executor_ref,
                task_id=task_id,
                attempt_id=task.attempt_id,
                source_event_id=f"{executor_ref}:2",
                source_seq=2,
                attempt_state=FormalAttemptState.TERMINAL,
                attempt_outcome=TerminalOutcome.COMPLETED,
                occurred_at=NOW,
                raw_status="completed",
            ),
        )
    )


def _append_authority_adjustments(
    store: SqliteTaskStore, task_id: str, *, count: int
) -> None:
    task = store.get_task(task_id, _scope())
    for ordinal in range(count):
        command_id = f"command-authority-adjust-{ordinal}"
        command = CommandEnvelope.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "request_id": f"request-authority-adjust-{ordinal}",
                "command_id": command_id,
                "command_type": "task.adjust",
                "issued_at": NOW,
                "scope": task.scope.to_dict(),
                "correlation_id": task.correlation_id,
                "causation_id": None,
                "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
                "target_ref": {"kind": "task", "id": task_id},
                "context_refs": [],
                "required_capabilities": ["task.adjust"],
                "payload": {"adjustment": f"Adjustment {ordinal}."},
                "extensions": {},
            }
        )
        admitted = store.adjust(command, observed_at=NOW)
        assert admitted.ok


def _ack_authority_task_head(
    store: SqliteTaskStore,
    task_id: str,
    *,
    presentation_class: str,
) -> None:
    task = store.get_task(task_id, _scope())
    terminal = store.events(task_id, task.scope)[-1]
    assert terminal.seq == task.event_head
    command = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-authority-consume-head",
            "command_id": "command-authority-consume-head",
            "command_type": "task.ack_events",
            "issued_at": NOW,
            "scope": task.scope.to_dict(),
            "correlation_id": task.correlation_id,
            "causation_id": terminal.event_id,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": task_id},
            "context_refs": [],
            "required_capabilities": ["task.ack_events"],
            "payload": {
                "presentation_class": presentation_class,
                "acked_through_seq": terminal.seq,
                "acked_event_id": terminal.event_id,
                "expected_event_head": terminal.seq,
            },
            "extensions": {},
        }
    )
    acknowledged = store.ack_events(
        command,
        observed_at="2026-08-06T10:00:01Z",
    )
    assert acknowledged.ok


def _ack_authority_task_through(
    store: SqliteTaskStore,
    task_id: str,
    *,
    presentation_class: str,
    through_seq: int,
) -> None:
    task = store.get_task(task_id, _scope())
    event = store.events(task_id, task.scope)[through_seq]
    assert event.seq == through_seq
    command = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": f"request-authority-consume-{presentation_class}-{through_seq}",
            "command_id": f"command-authority-consume-{presentation_class}-{through_seq}",
            "command_type": "task.ack_events",
            "issued_at": NOW,
            "scope": task.scope.to_dict(),
            "correlation_id": task.correlation_id,
            "causation_id": event.event_id,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": task_id},
            "context_refs": [],
            "required_capabilities": ["task.ack_events"],
            "payload": {
                "presentation_class": presentation_class,
                "acked_through_seq": event.seq,
                "acked_event_id": event.event_id,
                "expected_event_head": task.event_head,
            },
            "extensions": {},
        }
    )
    acknowledged = store.ack_events(
        command,
        observed_at="2026-08-06T10:00:01Z",
    )
    assert acknowledged.ok


def _append_authority_presentable_cycles(
    store: SqliteTaskStore,
    task_id: str,
    *,
    count: int,
) -> None:
    """Build a verifier-clean Store fixture for the closed Task state machine."""

    task = store.get_task(task_id, _scope())
    assert task.state.value == "running"
    with store._transaction() as connection:
        row = store._require_task_row_by_id(connection, task_id)
        state = "running"
        for ordinal in range(count):
            state = (
                "blocked"
                if state == "decision_required" or ordinal == 0
                else "decision_required"
            )
            store._append_event(
                connection,
                row,
                event_type=f"task.{state}",
                state=state,
                outcome=None,
                producer="task_core",
                source_event_id=None,
                causation_id=f"authority-presentable-cycle-{ordinal}",
                occurred_at=NOW,
                details={"summary": f"bounded lifecycle cycle {ordinal}"},
                update_task=True,
            )
            row = store._require_task_row_by_id(connection, task_id)
    store.consumer_progress_authority_page(
        task_id,
        task.scope,
        presentation_class="voice",
        limit=1,
    )


def _recovery_authority_task(
    tmp_path: Path,
) -> tuple[SqliteTaskStore, str, ScopeRef, str]:
    from tests.unit_tests.live_voice.test_p3_4_durability_store import (
        EXPIRY as RECOVERY_EXPIRY,
        NOW as RECOVERY_NOW,
        _observations,
        _recovery_authorization,
        _safe_recovery_prefix,
        _selected_task,
    )

    store, selection, task, binding = _selected_task(tmp_path)
    checkpoint_prefix = _safe_recovery_prefix(store, task, binding)
    item = store.claim_outbox("recovery-progress-producer", observed_at=RECOVERY_NOW)
    assert item is not None
    observations = tuple(
        replace(
            observation,
            adapter_id=selection.adapter_id,
            capability_profile_digest=selection.capability_profile_digest,
            occurred_at=RECOVERY_NOW,
        )
        for observation in _observations(item, outcome=TerminalOutcome.INTERRUPTED)
    )
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )
    authority = store.read_durable_recovery_authority(
        scope=task.scope,
        task_id=task.task_id,
    )
    claim = store.claim_durability_mutator(
        scope=task.scope,
        task_id=task.task_id,
        owner_id="recovery-progress-worker",
        observed_at=RECOVERY_NOW,
        expires_at=RECOVERY_EXPIRY,
    )
    assert claim is not None
    effects = store.read_durability_effects(binding)
    facts = ExecutorRecoveryFacts.create(
        scope=task.scope,
        task_id=task.task_id,
        producer_attempt_id=task.attempt_id,
        candidate_recovery_attempt_id="attempt-progress-recovery",
        profile=binding.profile,
        recovery_generation=1,
        executor_epoch_id="direct-progress-epoch",
        executor_owner_generation=1,
        observed_at=RECOVERY_NOW,
        expires_at=RECOVERY_EXPIRY,
        evidence_digest="9" * 64,
    )
    recovered = store.recover_durable_attempt(
        authority,
        recovery_id="recovery-progress-1",
        recovery_facts=facts,
        checkpoint_head=checkpoint_prefix.head,
        checkpoint_prefix_digest=checkpoint_prefix.prefix_digest,
        effect_head=effects.head,
        effect_prefix_digest=effects.prefix_digest,
        authorization=_recovery_authorization(
            store,
            binding,
            facts,
            recovery_id="recovery-progress-1",
            owner_id="recovery-progress-worker",
            claim=claim,
        ),
        observed_at=RECOVERY_NOW,
    )
    assert recovered.attempt_id == "attempt-progress-recovery"
    current = store.get_task(task.task_id, task.scope)
    assert current.attempt_id == recovered.attempt_id
    return store, task.task_id, task.scope, task.correlation_id


def _retry_authority_task(store: SqliteTaskStore, task_id: str) -> str:
    task = store.get_task(task_id, _scope())
    assert task.outcome is TerminalOutcome.COMPLETED
    command = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-authority-retry",
            "command_id": "command-authority-retry",
            "command_type": "task.retry",
            "issued_at": NOW,
            "scope": task.scope.to_dict(),
            "correlation_id": task.correlation_id,
            "causation_id": None,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": task.task_id},
            "context_refs": [],
            "required_capabilities": ["task.retry"],
            "payload": {
                "previous_attempt_id": task.attempt_id,
                "previous_outcome": "completed",
                "attempt_number": 2,
            },
            "extensions": TaskRetryProductRequestFingerprint("a" * 64).to_extensions(),
        }
    )
    spec = replace(
        task.spec,
        context=replace(task.spec.context, revision_value="revision-2"),
    )
    authority = store.read_retry_authority(command)
    assert isinstance(authority, TaskRetryAuthoritySnapshot)
    result = store.retry(command, spec, authority, observed_at=NOW)
    assert result.ok and result.result is not None
    return str(result.result["attempt_id"])


def _cancel_and_retry_authority_task(store: SqliteTaskStore, task_id: str) -> str:
    task = store.get_task(task_id, _scope())
    cancel = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-authority-cancel-before-retry",
            "command_id": "command-authority-cancel-before-retry",
            "command_type": "task.cancel",
            "issued_at": NOW,
            "scope": task.scope.to_dict(),
            "correlation_id": task.correlation_id,
            "causation_id": None,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": task.task_id},
            "context_refs": [],
            "required_capabilities": ["task.cancel"],
            "payload": {},
            "extensions": {},
        }
    )
    cancelled = store.cancel(cancel, observed_at=NOW)
    assert cancelled.ok
    predecessor = store.get_task(task_id, _scope())
    assert predecessor.outcome is TerminalOutcome.CANCELLED
    retry = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-authority-retry-cancelled",
            "command_id": "command-authority-retry-cancelled",
            "command_type": "task.retry",
            "issued_at": NOW,
            "scope": predecessor.scope.to_dict(),
            "correlation_id": predecessor.correlation_id,
            "causation_id": None,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": predecessor.task_id},
            "context_refs": [],
            "required_capabilities": ["task.retry"],
            "payload": {
                "previous_attempt_id": predecessor.attempt_id,
                "previous_outcome": "cancelled",
                "attempt_number": 2,
            },
            "extensions": TaskRetryProductRequestFingerprint("b" * 64).to_extensions(),
        }
    )
    spec = replace(
        predecessor.spec,
        context=replace(predecessor.spec.context, revision_value="revision-2"),
    )
    authority = store.read_retry_authority(retry)
    assert isinstance(authority, TaskRetryAuthoritySnapshot)
    result = store.retry(retry, spec, authority, observed_at=NOW)
    assert result.ok and result.result is not None
    return str(result.result["attempt_id"])


def _bridge(
    *,
    origin_kind: TaskProgressOriginKind,
    subscription: _SubscriptionDouble,
    prepared_source: _PreparedSourceDouble | None = None,
    enabled: bool = True,
    authorization: TaskAuthorizationGrant | None | object = _DEFAULT_AUTHORIZATION,
    binding: TaskProgressOriginBinding | None = None,
    generation_is_current=lambda _binding: True,
    arbiter: ProgressNotificationArbiter | None = None,
    voice_events: list[TaskProgressNotificationIntent] | None = None,
    text_events: list[TaskProgressTextEvent] | None = None,
    allow_package_contract_handoff: bool = False,
    validation_capacity: int = 256,
    clock=lambda: NOW,
) -> TaskProgressReturnBridge:
    selected_binding = binding or _binding(origin_kind)
    selected_voice_events = voice_events if voice_events is not None else []
    selected_text_events = text_events if text_events is not None else []

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        selected_voice_events.append(intent)

    async def text_sink(event: TaskProgressTextEvent) -> None:
        selected_text_events.append(event)

    return TaskProgressReturnBridge(
        enabled=enabled,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared_source,
        authorization=(
            _grant()
            if authorization is _DEFAULT_AUTHORIZATION
            else cast(TaskAuthorizationGrant | None, authorization)
        ),
        binding=selected_binding,
        generation_is_current=generation_is_current,
        arbiter=arbiter or ProgressNotificationArbiter(),
        foreground=_foreground,
        voice_sink=voice_sink,
        text_sink=text_sink,
        allow_package_contract_handoff=allow_package_contract_handoff,
        validation_capacity=validation_capacity,
        clock=clock,
    )


def test_projection_preserves_source_truth_and_omits_unknown_business_facts() -> None:
    binding = _binding(TaskProgressOriginKind.TEXT)
    task_event = _event(
        9,
        "task.running",
        "running",
        details={
            "summary": "Source supplied summary",
            "percent": 90,
            "error": "must not escape",
            "completed": True,
        },
    )

    projected = project_task_progress_event(task_event, binding)

    assert projected.source_event.event_id == task_event.event_id
    assert projected.source_event.seq == task_event.seq
    assert projected.source_event.producer.component == "task_core"
    assert (
        projected.source_event.extensions["jiuwenswarm.task_progress_return"][
            "persistent_event_producer"
        ]
        == task_event.producer
    )
    assert projected.source_event.correlation_id == task_event.correlation_id
    assert projected.progress_event.seq == task_event.seq
    assert projected.progress_event.causation_id == task_event.event_id
    assert projected.progress_event.correlation_id == task_event.correlation_id
    assert projected.progress_event.payload["state"] == "running"
    assert projected.progress_event.payload["outcome"] is None
    assert projected.progress_event.payload["summary"] == {
        "knowledge": "known",
        "value": "Source supplied summary",
    }
    assert projected.progress_event.payload["blocking_question"] == {
        "knowledge": "unknown"
    }
    assert projected.progress_event.payload["artifact_refs"] == {"knowledge": "unknown"}
    assert projected.progress_event.payload["speakability"] == "not_speakable"
    assert "percent" not in projected.progress_event.payload
    assert "error" not in projected.progress_event.payload
    assert "completed" not in projected.progress_event.payload


def test_progress_evidence_id_is_bounded_for_canonical_transport() -> None:
    binding = replace(
        _binding(TaskProgressOriginKind.TEXT),
        task_id="task-" + ("t" * 120),
        correlation_id="correlation-" + ("c" * 120),
        generation_id="generation-" + ("g" * 120),
    )
    task_event = _event(
        9,
        "task.running",
        "running",
        task_id=binding.task_id,
        correlation_id=binding.correlation_id,
        event_id="event-" + ("e" * 120),
    )

    evidence_id = _evidence_id(binding, task_event)

    assert evidence_id.startswith("task-progress-return:")
    assert len(evidence_id) <= 256
    assert evidence_id == _evidence_id(binding, task_event)
    assert evidence_id != _evidence_id(
        binding,
        replace(task_event, event_id="event-other"),
    )


@pytest.mark.asyncio
async def test_voice_package_contract_routes_typed_intents_through_arbiter() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
        arbiter=arbiter,
        voice_events=voice_events,
        text_events=text_events,
        allow_package_contract_handoff=True,
    )

    activation = await bridge.activate()
    await _wait_settled(bridge)

    assert activation.active is True
    assert activation.handoff_kind is TaskProgressHandoffKind.PACKAGE_CONTRACT_TEST
    assert activation.handoff_evidence_id == prepared.evidence_id
    assert activation.lease is not None
    assert [intent.task_event.seq for intent in voice_events] == [0, 1, 2]
    assert all(
        intent.progress_event.payload["speakability"] == "not_speakable"
        for intent in voice_events
    )
    assert all(
        intent.origin.origin_kind is TaskProgressOriginKind.VOICE
        for intent in voice_events
    )
    assert all(intent.origin.origin_id == "voice-origin-1" for intent in voice_events)
    assert all(intent.origin.generation == 7 for intent in voice_events)
    assert text_events == []
    assert subscription.start_calls == 0
    assert prepared.start_calls == 1
    assert prepared.close_calls == 1
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert arbiter.snapshot().accepted_events == 3


@pytest.mark.asyncio
async def test_deferred_voice_waits_for_explicit_safe_drain_and_acks_once() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    voice_events: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter()
    foreground = _busy_foreground()

    def foreground_supplier() -> ForegroundSnapshot:
        return foreground

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        voice_events.append(intent)

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=foreground_supplier,
        voice_sink=voice_sink,
        text_sink=lambda _event: _noop(),
        allow_package_contract_handoff=True,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.lease is not None
    await _wait_settled(bridge)

    assert voice_events == []
    assert bridge.snapshot().voice_intents == 0
    assert bridge.snapshot().state is TaskProgressReturnState.ACTIVE
    assert arbiter.snapshot().pending_notifications == 1

    foreground = _foreground()
    assert await activation.lease.drain_voice() == 1
    assert len(voice_events) == 1
    assert voice_events[0].task_event.event_type == "task.terminal"
    assert voice_events[0].decision.reason.startswith("drain_")
    assert bridge.snapshot().voice_intents == 1
    assert bridge.snapshot().voice_drains == 1
    assert bridge.snapshot().pending_voice_intents == 0
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert arbiter.snapshot().pending_notifications == 0

    assert await activation.lease.drain_voice() == 0
    assert len(voice_events) == 1
    assert bridge.snapshot().voice_drains == 1
    await activation.lease.close()


@pytest.mark.asyncio
async def test_voice_drain_serializes_sink_against_source_delivery() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, [_lifecycle_events()[0]])
    arbiter = ProgressNotificationArbiter()
    foreground = _busy_foreground()
    first_sink_started = asyncio.Event()
    release_first_sink = asyncio.Event()
    sink_calls: list[int] = []
    active_sinks = 0
    maximum_active_sinks = 0

    def foreground_supplier() -> ForegroundSnapshot:
        return foreground

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        nonlocal active_sinks, maximum_active_sinks
        active_sinks += 1
        maximum_active_sinks = max(maximum_active_sinks, active_sinks)
        sink_calls.append(intent.task_event.seq)
        if len(sink_calls) == 1:
            first_sink_started.set()
            await release_first_sink.wait()
        active_sinks -= 1

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=foreground_supplier,
        voice_sink=voice_sink,
        text_sink=lambda _event: _noop(),
        allow_package_contract_handoff=True,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.lease is not None
    await _wait_until(lambda: bridge.snapshot().pending_voice_intents == 1)
    foreground = _foreground()
    drain = asyncio.create_task(activation.lease.drain_voice())
    await first_sink_started.wait()

    prepared.publish(_event(1, "task.running", "running"))
    await _wait_until(lambda: bridge.snapshot().projected_events == 2)
    assert sink_calls == [0]
    assert active_sinks == 1

    release_first_sink.set()
    assert await drain == 1
    await _wait_until(lambda: bridge.snapshot().voice_intents == 2)

    assert sink_calls == [0, 1]
    assert maximum_active_sinks == 1
    assert arbiter.snapshot().pending_notifications == 0
    await activation.lease.close()


@pytest.mark.asyncio
async def test_text_live_route_preserves_raw_sequence_and_skips_control_event() -> None:
    control = _event(
        8,
        "attempt.running",
        "running",
        producer="executor-1",
    )
    running = _event(9, "task.running", "running")
    terminal = _event(10, "task.terminal", "terminal", outcome="completed")
    subscription = _SubscriptionDouble([control, running, terminal])
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
        arbiter=arbiter,
        voice_events=voice_events,
        text_events=text_events,
    )

    activation = await bridge.activate()
    await _wait_settled(bridge)

    assert activation.active is True
    assert activation.handoff_kind is None
    assert [event.task_event.seq for event in text_events] == [9, 10]
    assert [event.source_event.event_id for event in text_events] == [
        running.event_id,
        terminal.event_id,
    ]
    assert [event.progress_event.seq for event in text_events] == [9, 10]
    assert all(
        event.origin.origin_kind is TaskProgressOriginKind.TEXT for event in text_events
    )
    assert voice_events == []
    assert subscription.start_calls == 1
    assert subscription.close_calls == 1
    snapshot = bridge.snapshot()
    assert snapshot.source_events == 3
    assert snapshot.projected_events == 2
    assert snapshot.unprojected_events == 1
    assert snapshot.reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert snapshot.last_source_decision_id is TaskProgressSourceDecision.PROJECTED
    assert snapshot.last_source_evidence_id is not None
    assert arbiter.snapshot().accepted_events == 0


@pytest.mark.asyncio
async def test_voice_without_authority_handoff_is_unavailable_with_zero_effects() -> (
    None
):
    subscription = _SubscriptionDouble(_lifecycle_events())
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        voice_events=voice_events,
        text_events=text_events,
    )

    activation = await bridge.activate()

    assert activation.active is False
    assert (
        activation.reason_id is TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
    )
    assert activation.lease is None
    assert subscription.start_calls == 0
    assert subscription.next_calls == 0
    assert subscription.close_calls == 0
    assert voice_events == []
    assert text_events == []
    assert bridge.snapshot().worker_pending is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "authorization", "current", "reason"),
    [
        (False, _grant(), True, TaskProgressReturnReason.FEATURE_DISABLED),
        (True, None, True, TaskProgressReturnReason.AUTHORIZATION_REJECTED),
        (True, _grant(), False, TaskProgressReturnReason.STALE_GENERATION),
    ],
)
async def test_fail_closed_activation_has_zero_subscription_or_sink_effects(
    enabled: bool,
    authorization: TaskAuthorizationGrant | None,
    current: bool,
    reason: TaskProgressReturnReason,
) -> None:
    subscription = _SubscriptionDouble(_lifecycle_events())
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
        enabled=enabled,
        authorization=authorization,
        generation_is_current=lambda _binding: current,
        voice_events=voice_events,
        text_events=text_events,
    )
    activation = await bridge.activate()

    assert activation.active is False
    assert activation.reason_id is reason
    assert subscription.start_calls == 0
    assert subscription.next_calls == 0
    assert subscription.close_calls == 0
    assert voice_events == []
    assert text_events == []
    assert bridge.snapshot().worker_pending is False


@pytest.mark.asyncio
async def test_wrong_scope_and_wrong_subscription_task_reject_before_start() -> None:
    foreign_scope = _scope(subject_id="subject-2")
    for binding, authorization, task_id in (
        (_binding(TaskProgressOriginKind.TEXT), _grant(scope=foreign_scope), "task-1"),
        (_binding(TaskProgressOriginKind.TEXT), _grant(), "task-2"),
    ):
        subscription = _SubscriptionDouble(_lifecycle_events(), task_id=task_id)
        bridge = _bridge(
            origin_kind=TaskProgressOriginKind.TEXT,
            subscription=subscription,
            authorization=authorization,
            binding=binding,
        )

        activation = await bridge.activate()

        assert activation.active is False
        assert activation.reason_id in {
            TaskProgressReturnReason.AUTHORIZATION_REJECTED,
            TaskProgressReturnReason.INVALID_BINDING,
        }
        assert subscription.start_calls == 0
        assert subscription.next_calls == 0
        assert subscription.close_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_dimension", ["task", "scope", "correlation"])
async def test_cross_scope_events_fail_without_sink_output(
    foreign_dimension: str,
) -> None:
    event = _event(12, "task.running", "running")
    if foreign_dimension == "task":
        event = replace(event, task_id="task-2")
    elif foreign_dimension == "scope":
        event = replace(event, scope=_scope(subject_id="subject-2"))
    else:
        event = replace(event, correlation_id="correlation-2")
    subscription = _SubscriptionDouble([event])
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
        text_events=text_events,
    )

    activation = await bridge.activate()
    assert activation.active is True
    await _wait_settled(bridge)

    assert text_events == []
    assert bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        bridge.snapshot().reason_id
        is TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION
    )


@pytest.mark.asyncio
async def test_prepared_voice_cross_task_rejects_before_arbiter_or_sink() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(
        subscription,
        [_event(0, "task.accepted", "accepted", task_id="task-2")],
    )
    voice_events: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
        arbiter=arbiter,
        voice_events=voice_events,
        allow_package_contract_handoff=True,
    )

    assert (await bridge.activate()).active is True
    await _wait_settled(bridge)

    assert voice_events == []
    assert arbiter.snapshot().accepted_events == 0
    assert (
        bridge.snapshot().last_source_decision_id
        is TaskProgressSourceDecision.BINDING_REJECTED
    )


@pytest.mark.asyncio
async def test_stale_generation_after_first_text_event_fences_later_sink() -> None:
    subscription = _SubscriptionDouble(_lifecycle_events(start_seq=20)[1:])
    current = True
    text_events: list[TaskProgressTextEvent] = []

    def generation_is_current(_binding: TaskProgressOriginBinding) -> bool:
        return current

    async def text_sink(event: TaskProgressTextEvent) -> None:
        nonlocal current
        text_events.append(event)
        current = False

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=None,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.TEXT),
        generation_is_current=generation_is_current,
        arbiter=ProgressNotificationArbiter(),
        foreground=_foreground,
        voice_sink=lambda _intent: _noop(),
        text_sink=text_sink,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.active is True
    await _wait_settled(bridge)

    assert [event.task_event.seq for event in text_events] == [21]
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.STALE_GENERATION
    assert bridge.snapshot().rejected_events == 1


async def _noop() -> None:
    return None


@pytest.mark.asyncio
async def test_duplicate_is_idempotent_but_gap_and_out_of_order_fail_closed() -> None:
    accepted = _event(30, "task.accepted", "accepted")
    running = _event(31, "task.running", "running")
    terminal = _event(32, "task.terminal", "terminal", outcome="completed")
    duplicate_subscription = _SubscriptionDouble(
        [accepted, accepted, running, terminal]
    )
    duplicate_events: list[TaskProgressTextEvent] = []
    duplicate_bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=duplicate_subscription,
        text_events=duplicate_events,
    )

    assert (await duplicate_bridge.activate()).active is True
    await _wait_settled(duplicate_bridge)

    assert [event.task_event.seq for event in duplicate_events] == [30, 31, 32]
    assert duplicate_bridge.snapshot().duplicate_events == 1

    for invalid in (
        _event(32, "task.running", "running"),
        _event(30, "task.running", "running", event_id="conflict-30"),
    ):
        subscription = _SubscriptionDouble([accepted, invalid])
        events: list[TaskProgressTextEvent] = []
        bridge = _bridge(
            origin_kind=TaskProgressOriginKind.TEXT,
            subscription=subscription,
            text_events=events,
        )

        assert (await bridge.activate()).active is True
        await _wait_settled(bridge)

        assert [event.task_event.seq for event in events] == [30]
        assert bridge.snapshot().state is TaskProgressReturnState.FAILED
        assert (
            bridge.snapshot().reason_id
            is TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION
        )
        expected_decision = (
            TaskProgressSourceDecision.SEQUENCE_GAP
            if invalid.seq > accepted.seq
            else TaskProgressSourceDecision.SEQUENCE_CONFLICT
        )
        assert bridge.snapshot().last_source_decision_id is expected_decision


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["attempt.accepted", "task.unknown"])
async def test_package_voice_source_rejects_nonprojectable_or_unknown_event(
    event_type: str,
) -> None:
    subscription = _SubscriptionDouble()
    control = _event(
        0,
        event_type,
        "accepted",
        producer="executor-1",
    )
    prepared = _PreparedSourceDouble(subscription, [control])
    voice_events: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
        arbiter=arbiter,
        voice_events=voice_events,
        allow_package_contract_handoff=True,
    )

    assert (await bridge.activate()).active is True
    await _wait_settled(bridge)

    assert voice_events == []
    assert bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert bridge.snapshot().unprojected_events == 0
    assert (
        bridge.snapshot().reason_id
        is TaskProgressReturnReason.SOURCE_EVENT_NOT_PROJECTABLE
    )
    assert (
        bridge.snapshot().last_source_decision_id
        is TaskProgressSourceDecision.NOT_PROJECTABLE
    )
    assert prepared.close_calls == 1
    assert arbiter.snapshot().no_projection_advances == 0


@pytest.mark.asyncio
async def test_concrete_authority_source_is_the_only_atomic_voice_handoff(
    tmp_path: Path,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    before = store.counts()
    binding = _binding(
        TaskProgressOriginKind.VOICE,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    grant = _grant(task_id=task_id)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    voice_events: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        arbiter=arbiter,
        voice_events=voice_events,
    )

    activation = await bridge.activate()
    assert activation.active is True
    assert activation.handoff_kind is TaskProgressHandoffKind.AUTHORITY_ATOMIC
    assert activation.handoff_evidence_id is not None
    assert activation.lease is not None
    await _wait_until(lambda: len(voice_events) == 2)
    assert [item.task_event.seq for item in voice_events] == [0, 3]
    assert [item.task_event.event_type for item in voice_events] == [
        "task.accepted",
        "task.running",
    ]
    assert bridge.snapshot().unprojected_events == 2
    assert bridge.snapshot().projected_events == 2
    assert bridge.snapshot().state is TaskProgressReturnState.ACTIVE
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.ACTIVATED
    assert bridge.snapshot().voice_intents == 2
    arbiter_snapshot = arbiter.snapshot()
    assert arbiter_snapshot.no_projection_advances == 2
    assert arbiter_snapshot.accepted_events == 2
    assert arbiter_snapshot.pending_notifications == 0
    assert source.subscription.snapshot().cursor_replay_supported is True
    assert store.counts() == before
    await activation.lease.close()
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED


@pytest.mark.asyncio
async def test_concrete_authority_source_replays_store_prefix_for_text_projection(
    tmp_path: Path,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    before = store.counts()
    binding = _binding(
        TaskProgressOriginKind.TEXT,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    grant = _grant(task_id=task_id)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        text_events=text_events,
    )

    activation = await bridge.activate()
    assert activation.active is True
    # Text remains a display projection; the exact Store handoff is internal.
    assert activation.handoff_kind is None
    assert activation.handoff_evidence_id is None
    assert activation.lease is not None
    await _wait_until(lambda: len(text_events) == 2)
    assert [item.task_event.seq for item in text_events] == [0, 3]
    assert [item.task_event.event_type for item in text_events] == [
        "task.accepted",
        "task.running",
    ]
    snapshot = bridge.snapshot()
    assert snapshot.unprojected_events == 2
    assert snapshot.projected_events == 2
    assert snapshot.text_events == 2
    assert snapshot.voice_intents == 0
    assert store.counts() == before
    await activation.lease.close()
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED


@pytest.mark.asyncio
@pytest.mark.parametrize("presentation_class", ["text", "voice"])
async def test_consumer_authority_source_skips_consumed_prefix_beyond_queue_capacity(
    tmp_path: Path,
    presentation_class: str,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    _append_authority_adjustments(store, task_id, count=127)
    _finish_authority_task(store, task_id)
    terminal = store.get_task(task_id, _scope())
    assert terminal.event_head >= 256
    _ack_authority_task_head(store, task_id, presentation_class=presentation_class)
    reconnect_scope = _scope(session_id="session-consumer-reconnect")
    grant = _grant(task_id=task_id, scope=reconnect_scope)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=reconnect_scope,
        task_id=task_id,
        queue_capacity=16,
        validation_capacity=64,
        poll_interval=0.001,
        clock=lambda: NOW,
        consumer_scope=True,
        presentation_class=presentation_class,
    )

    assert await source.start() is True
    with pytest.raises(StopAsyncIteration):
        await source.next_event()
    snapshot = source.subscription.snapshot()
    assert snapshot.start_head_seq == terminal.event_head
    assert snapshot.segment_start_seq == terminal.event_head + 1
    assert snapshot.source_reads == 1
    assert snapshot.tracked_events == 0
    assert snapshot.state.name == "CLOSED"
    assert correlation_id == terminal.correlation_id


@pytest.mark.asyncio
@pytest.mark.parametrize("presentation_class", ["text", "voice"])
async def test_consumer_authority_source_pages_one_frozen_unread_suffix(
    tmp_path: Path,
    presentation_class: str,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    _ack_authority_task_head(store, task_id, presentation_class=presentation_class)
    _append_authority_adjustments(store, task_id, count=257)
    running = store.get_task(task_id, _scope())
    assert running.event_head == 260
    reconnect_scope = _scope(session_id="session-consumer-paged")
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=_grant(task_id=task_id, scope=reconnect_scope),
        scope=reconnect_scope,
        task_id=task_id,
        queue_capacity=32,
        validation_capacity=300,
        poll_interval=0.001,
        clock=lambda: NOW,
        consumer_scope=True,
        presentation_class=presentation_class,
    )

    assert await source.start() is True
    replayed = [await source.next_event() for _ in range(257)]
    assert [event.seq for event in replayed] == list(range(4, 261))
    snapshot = source.subscription.snapshot()
    assert snapshot.start_head_seq == running.event_head
    assert snapshot.segment_start_seq == 4
    assert snapshot.source_reads == 9
    assert snapshot.tracked_events == 257
    assert snapshot.queued_events == 0
    assert correlation_id == running.correlation_id
    await source.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("presentation_class", ["text", "voice"])
async def test_consumer_frozen_page_follows_terminal_appended_after_start(
    tmp_path: Path,
    presentation_class: str,
) -> None:
    store, task_id, _correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    _append_authority_adjustments(store, task_id, count=12)
    frozen = store.get_task(task_id, _scope())
    consumer_scope = _scope(session_id="session-consumer-terminal-race")
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=_grant(task_id=task_id, scope=consumer_scope),
        scope=consumer_scope,
        task_id=task_id,
        queue_capacity=4,
        validation_capacity=8,
        poll_interval=0.001,
        consumer_scope=True,
        presentation_class=presentation_class,
        clock=lambda: NOW,
    )

    assert await source.start() is True
    assert source.subscription.snapshot().start_head_seq == frozen.event_head
    _finish_authority_task(store, task_id)
    terminal = store.get_task(task_id, _scope())
    assert terminal.event_head > frozen.event_head
    before_read = store.counts()

    replayed: list[PersistentTaskEvent] = []
    for _ in range(terminal.event_head + 2):
        try:
            replayed.append(await source.next_event())
        except StopAsyncIteration:
            break

    assert [event.seq for event in replayed] == list(range(terminal.event_head + 1))
    assert replayed[-1].event_type == "task.terminal"
    assert replayed[-1].seq == terminal.event_head
    assert source.subscription.snapshot().terminal_event_delivered is True
    assert store.counts() == before_read


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin_kind",
    [TaskProgressOriginKind.TEXT, TaskProgressOriginKind.VOICE],
)
async def test_consumer_bridge_resumes_fresh_process_from_nonzero_watermark(
    tmp_path: Path,
    origin_kind: TaskProgressOriginKind,
) -> None:
    store, task_id, _correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    presentation_class = (
        "voice" if origin_kind is TaskProgressOriginKind.VOICE else "text"
    )
    _ack_authority_task_through(
        store,
        task_id,
        presentation_class=presentation_class,
        through_seq=0,
    )
    consumer_scope = _scope(session_id="session-consumer-process-restart")
    grant = _grant(task_id=task_id, scope=consumer_scope)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=consumer_scope,
        task_id=task_id,
        queue_capacity=4,
        validation_capacity=8,
        poll_interval=0.001,
        consumer_scope=True,
        presentation_class=presentation_class,
        clock=lambda: NOW,
    )
    delivered_voice: list[TaskProgressNotificationIntent] = []
    delivered_text: list[TaskProgressTextEvent] = []
    before = store.counts()
    bridge = _bridge(
        origin_kind=origin_kind,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=_binding(
            origin_kind,
            task_id=task_id,
            scope=consumer_scope,
            correlation_id="correlation-consumer-process-restart",
        ),
        arbiter=ProgressNotificationArbiter(events_per_stream=2),
        voice_events=delivered_voice,
        text_events=delivered_text,
        validation_capacity=8,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.active
    for _ in range(500):
        delivered = delivered_voice or delivered_text
        if delivered or bridge.snapshot().state is not TaskProgressReturnState.ACTIVE:
            break
        await asyncio.sleep(0.001)
    delivered = delivered_voice or delivered_text
    assert [item.task_event.seq for item in delivered] == [3]
    assert bridge.snapshot().state is TaskProgressReturnState.ACTIVE
    assert bridge.snapshot().unprojected_events == 2
    assert store.counts() == before
    assert activation.lease is not None
    await activation.lease.close()


@pytest.mark.asyncio
async def test_consumer_source_accepts_only_known_monotonic_cursor_advance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, task_id, _correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=_grant(task_id=task_id),
        scope=_scope(),
        task_id=task_id,
        queue_capacity=8,
        validation_capacity=16,
        poll_interval=0.001,
        clock=lambda: NOW,
        consumer_scope=True,
        presentation_class="text",
    )
    assert await source.start()
    initial = tuple([await source.next_event() for _ in range(4)])
    assert [event.seq for event in initial] == [0, 1, 2, 3]
    _ack_authority_task_through(
        store,
        task_id,
        presentation_class="text",
        through_seq=3,
    )
    after_ack_counts = store.counts()
    real_page = store.consumer_progress_authority_page
    followup_reads = 0

    def read_page(*args: object, **kwargs: object):
        nonlocal followup_reads
        page = real_page(*args, **kwargs)
        followup_reads += 1
        if followup_reads == 1:
            return page
        lifecycle = page.cursor_baseline.lifecycle_event
        assert lifecycle is not None
        return replace(
            page,
            cursor_baseline=replace(
                page.cursor_baseline,
                lifecycle_event=replace(lifecycle, occurred_at=AFTER_EXPIRY),
            ),
        )

    monkeypatch.setattr(store, "consumer_progress_authority_page", read_page)
    with pytest.raises(FormalTaskViolation) as raised:
        await asyncio.wait_for(source.next_event(), timeout=1)

    assert raised.value.reason == "TASK_EVENT_CONSUMER_CURSOR_STALE"
    assert followup_reads == 2
    assert source.subscription.snapshot().failure_reason == (
        "TASK_EVENT_CONSUMER_CURSOR_STALE"
    )
    assert store.counts() == after_ack_counts
    await source.close()


@pytest.mark.asyncio
async def test_consumer_source_accepts_delayed_ack_after_validation_rollover(
    tmp_path: Path,
) -> None:
    store, task_id, _correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    _append_authority_adjustments(store, task_id, count=8)
    task = store.get_task(task_id, _scope())
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=_grant(task_id=task_id),
        scope=_scope(),
        task_id=task_id,
        queue_capacity=4,
        validation_capacity=4,
        poll_interval=0.001,
        clock=lambda: NOW,
        consumer_scope=True,
        presentation_class="text",
    )
    assert await source.start()
    replayed = tuple([await source.next_event() for _ in range(task.event_head + 1)])
    assert [event.seq for event in replayed] == list(range(task.event_head + 1))
    assert source.subscription.snapshot().tracked_events == 4
    _ack_authority_task_through(
        store,
        task_id,
        presentation_class="text",
        through_seq=0,
    )
    after_ack_counts = store.counts()
    reads_before = source.subscription.snapshot().source_reads

    pending = asyncio.create_task(source.next_event())
    for _ in range(500):
        if source.subscription.snapshot().source_reads > reads_before or pending.done():
            break
        await asyncio.sleep(0.001)
    assert source.subscription.snapshot().source_reads > reads_before or pending.done()
    await asyncio.sleep(0.01)

    assert not pending.done()
    assert source.subscription.snapshot().state.value == "active"
    assert source.subscription.snapshot().failure_reason is None
    assert source.subscription.snapshot().tracked_events == 4
    assert store.counts() == after_ack_counts
    await source.close()
    with pytest.raises(StopAsyncIteration):
        await pending


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin_kind",
    [TaskProgressOriginKind.TEXT, TaskProgressOriginKind.VOICE],
)
async def test_consumer_bridge_projects_real_store_recovery_attempt_boundary(
    tmp_path: Path,
    origin_kind: TaskProgressOriginKind,
) -> None:
    store, task_id, task_scope, _correlation_id = _recovery_authority_task(tmp_path)
    task = store.get_task(task_id, task_scope)
    consumer_scope = ScopeRef(
        task.scope.subject_id,
        task.scope.project_id,
        "session-consumer-recovery",
        Assurance.AUTHENTICATED,
    )
    grant = _grant(task_id=task_id, scope=consumer_scope)
    presentation_class = (
        "voice" if origin_kind is TaskProgressOriginKind.VOICE else "text"
    )
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=consumer_scope,
        task_id=task_id,
        queue_capacity=4,
        validation_capacity=8,
        poll_interval=0.001,
        consumer_scope=True,
        presentation_class=presentation_class,
        clock=lambda: NOW,
    )
    delivered_voice: list[TaskProgressNotificationIntent] = []
    delivered_text: list[TaskProgressTextEvent] = []
    before = store.counts()
    bridge = _bridge(
        origin_kind=origin_kind,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=_binding(
            origin_kind,
            task_id=task_id,
            scope=consumer_scope,
            correlation_id="correlation-consumer-recovery",
        ),
        arbiter=ProgressNotificationArbiter(),
        voice_events=delivered_voice,
        text_events=delivered_text,
        validation_capacity=8,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.active
    expected = [
        event.seq
        for event in store.events(task_id, task.scope)
        if event.event_type in TASK_PROGRESS_PRESENTABLE_EVENTS
    ]
    for _ in range(1000):
        delivered = delivered_voice or delivered_text
        if (
            len(delivered) == len(expected)
            or bridge.snapshot().state is not TaskProgressReturnState.ACTIVE
        ):
            break
        await asyncio.sleep(0.001)
    delivered = delivered_voice or delivered_text
    assert [item.task_event.seq for item in delivered] == expected
    assert delivered[-1].task_event.event_type == "task.recovery_accepted"
    assert bridge.snapshot().state is TaskProgressReturnState.ACTIVE
    assert store.counts() == before
    assert activation.lease is not None
    await activation.lease.close()


@pytest.mark.asyncio
async def test_consumer_voice_rolls_more_than_256_presentable_store_events(
    tmp_path: Path,
) -> None:
    store, task_id, _correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    _append_authority_presentable_cycles(store, task_id, count=257)
    task = store.get_task(task_id, _scope())
    consumer_scope = _scope(session_id="session-consumer-presentable-window")
    grant = _grant(task_id=task_id, scope=consumer_scope)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=consumer_scope,
        task_id=task_id,
        queue_capacity=32,
        validation_capacity=32,
        poll_interval=0.001,
        consumer_scope=True,
        presentation_class="voice",
        clock=lambda: NOW,
    )
    delivered: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter(events_per_stream=16)
    before = store.counts()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=_binding(
            TaskProgressOriginKind.VOICE,
            task_id=task_id,
            scope=consumer_scope,
            correlation_id="correlation-consumer-presentable-window",
        ),
        arbiter=arbiter,
        voice_events=delivered,
        validation_capacity=32,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.active
    expected_count = sum(
        event.event_type in TASK_PROGRESS_PRESENTABLE_EVENTS
        for event in store.events(task_id, _scope())
    )
    for _ in range(4000):
        if (
            len(delivered) == expected_count
            or bridge.snapshot().state is not TaskProgressReturnState.ACTIVE
        ):
            break
        await asyncio.sleep(0.001)

    assert len(delivered) == expected_count
    assert delivered[-1].task_event.seq == task.event_head
    assert bridge.snapshot().state is TaskProgressReturnState.ACTIVE
    assert len(bridge._seen_ids) <= 32
    assert source.subscription.snapshot().tracked_events <= 32
    assert arbiter.snapshot().accepted_events == expected_count
    assert store.counts() == before
    assert activation.lease is not None
    await activation.lease.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin_kind",
    [TaskProgressOriginKind.TEXT, TaskProgressOriginKind.VOICE],
)
async def test_consumer_bridge_replays_unread_across_cancelled_retry_attempts(
    tmp_path: Path,
    origin_kind: TaskProgressOriginKind,
) -> None:
    store, task_id, _correlation_id = _authority_task(tmp_path)
    attempt_b = _cancel_and_retry_authority_task(store, task_id)
    authority_events = store.events(task_id, _scope())
    assert authority_events[-1].event_type == "task.retry_accepted"
    assert authority_events[-1].attempt_id == attempt_b
    expected = [
        event.seq
        for event in authority_events
        if event.event_type in TASK_PROGRESS_PRESENTABLE_EVENTS
    ]
    assert len({event.attempt_id for event in authority_events}) == 2
    consumer_scope = _scope(session_id="session-consumer-retry-reconnect")
    grant = _grant(task_id=task_id, scope=consumer_scope)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=consumer_scope,
        task_id=task_id,
        queue_capacity=4,
        validation_capacity=8,
        poll_interval=0.001,
        consumer_scope=True,
        presentation_class=(
            "voice" if origin_kind is TaskProgressOriginKind.VOICE else "text"
        ),
        clock=lambda: NOW,
    )
    delivered_voice: list[TaskProgressNotificationIntent] = []
    delivered_text: list[TaskProgressTextEvent] = []
    before = store.counts()
    bridge = _bridge(
        origin_kind=origin_kind,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=_binding(
            origin_kind,
            task_id=task_id,
            scope=consumer_scope,
            correlation_id="correlation-consumer-retry-reconnect",
        ),
        voice_events=delivered_voice,
        text_events=delivered_text,
        validation_capacity=8,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.active
    for _ in range(1000):
        delivered = delivered_voice or delivered_text
        if (
            len(delivered) == len(expected)
            or bridge.snapshot().state is not TaskProgressReturnState.ACTIVE
        ):
            break
        await asyncio.sleep(0.001)
    delivered = delivered_voice or delivered_text
    assert [item.task_event.seq for item in delivered] == expected
    assert bridge.snapshot().state is TaskProgressReturnState.ACTIVE
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.ACTIVATED
    assert store.counts() == before
    assert activation.lease is not None
    await activation.lease.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin_kind",
    [TaskProgressOriginKind.TEXT, TaskProgressOriginKind.VOICE],
)
async def test_consumer_bridge_rolls_validation_across_large_unread_gap(
    tmp_path: Path,
    origin_kind: TaskProgressOriginKind,
) -> None:
    store, task_id, _correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    _append_authority_adjustments(store, task_id, count=257)
    running = store.get_task(task_id, _scope())
    assert running.event_head == 260
    consumer_scope = _scope(session_id="session-consumer-large-gap")
    grant = _grant(task_id=task_id, scope=consumer_scope)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=consumer_scope,
        task_id=task_id,
        queue_capacity=32,
        validation_capacity=32,
        poll_interval=0.001,
        consumer_scope=True,
        presentation_class=(
            "voice" if origin_kind is TaskProgressOriginKind.VOICE else "text"
        ),
        clock=lambda: NOW,
    )
    delivered_voice: list[TaskProgressNotificationIntent] = []
    delivered_text: list[TaskProgressTextEvent] = []
    before = store.counts()
    bridge = _bridge(
        origin_kind=origin_kind,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=_binding(
            origin_kind,
            task_id=task_id,
            scope=consumer_scope,
            correlation_id="correlation-consumer-large-gap",
        ),
        voice_events=delivered_voice,
        text_events=delivered_text,
        validation_capacity=32,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.active
    for _ in range(2000):
        snapshot = bridge.snapshot()
        if (
            snapshot.source_events == running.event_head + 1
            or snapshot.state is not TaskProgressReturnState.ACTIVE
        ):
            break
        await asyncio.sleep(0.001)
    snapshot = bridge.snapshot()
    assert snapshot.source_events == running.event_head + 1
    assert snapshot.state is TaskProgressReturnState.ACTIVE
    delivered = delivered_voice or delivered_text
    assert [item.task_event.seq for item in delivered] == [0, 3]
    assert len(bridge._seen_ids) <= 32
    assert source.subscription.snapshot().tracked_events <= 32
    assert store.counts() == before
    assert activation.lease is not None
    await activation.lease.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin_kind",
    [TaskProgressOriginKind.TEXT, TaskProgressOriginKind.VOICE],
)
async def test_consumer_authority_rebinds_delivery_without_rewriting_store_event(
    tmp_path: Path,
    origin_kind: TaskProgressOriginKind,
) -> None:
    store, task_id, original_correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    before = store.counts()
    consumer_scope = _scope(session_id="session-reconnected")
    binding = _binding(
        origin_kind,
        task_id=task_id,
        scope=consumer_scope,
        correlation_id="correlation-reconnected",
    )
    grant = _grant(task_id=task_id, scope=consumer_scope)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=consumer_scope,
        task_id=task_id,
        poll_interval=0.001,
        consumer_scope=True,
        presentation_class=(
            "voice" if origin_kind is TaskProgressOriginKind.VOICE else "text"
        ),
        clock=lambda: NOW,
    )
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=origin_kind,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        arbiter=arbiter,
        voice_events=voice_events,
        text_events=text_events,
    )

    activation = await bridge.activate()
    assert activation.active
    await _wait_until(lambda: len(voice_events or text_events) == 2)
    delivered = voice_events or text_events
    assert [item.task_event.seq for item in delivered] == [0, 3]
    for item in delivered:
        assert item.origin.scope == consumer_scope
        assert item.task_event.scope == _scope()
        assert item.task_event.correlation_id == original_correlation_id
        assert item.source_event.scope == consumer_scope
        assert item.source_event.correlation_id == "correlation-reconnected"
        assert item.progress_event.scope == consumer_scope
        assert item.progress_event.correlation_id == "correlation-reconnected"
        extension = item.source_event.extensions["jiuwenswarm.task_progress_return"]
        assert extension["persistent_scope"] == _scope().to_dict()
        assert extension["persistent_correlation_id"] == original_correlation_id
        assert extension["consumer_scope_rebound"] is True
    if origin_kind is TaskProgressOriginKind.VOICE:
        assert arbiter.snapshot().no_projection_advances == 2
        assert arbiter.snapshot().accepted_events == 2
    assert store.counts() == before
    assert activation.lease is not None
    await activation.lease.close()


@pytest.mark.asyncio
async def test_retry_segment_projects_from_authority_owned_nonzero_baseline(
    tmp_path: Path,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    _finish_authority_task(store, task_id)
    attempt_b = _retry_authority_task(store, task_id)
    task = store.get_task(task_id, _scope())
    assert task.attempt_id == attempt_b
    boundary = store.events(
        task_id,
        task.scope,
        after_seq=-1,
        attempt_id=attempt_b,
    )[0]
    assert boundary.seq > 0
    binding = _binding(
        TaskProgressOriginKind.VOICE,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    grant = _grant(task_id=task_id)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    voice_events: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        arbiter=arbiter,
        voice_events=voice_events,
    )

    activation = await bridge.activate()
    assert activation.active is True and activation.lease is not None
    await _wait_until(lambda: len(voice_events) == 1)

    projected = voice_events[0]
    assert projected.task_event == boundary
    assert projected.task_event.event_type == "task.retry_accepted"
    assert projected.source_event.seq == boundary.seq
    assert projected.progress_event.seq == boundary.seq
    assert projected.source_event.payload == {
        "state": "accepted",
        "command_id": "command-authority-retry",
        "retry_of_attempt_id": boundary.details["retry_of_attempt_id"],
        "previous_outcome": "completed",
        "attempt_number": 2,
    }
    snapshot = source.subscription.snapshot()
    assert snapshot.segment_start_seq == boundary.seq
    assert snapshot.attempt_id == attempt_b
    assert snapshot.attempt_number == 2
    assert arbiter.snapshot().accepted_events == 1
    assert bridge.snapshot().gap_events == 0
    assert bridge.snapshot().out_of_order_events == 0
    await activation.lease.close()


@pytest.mark.asyncio
async def test_concrete_authority_reconciliation_terminal_closes_shared_sequence(
    tmp_path: Path,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    task = store.get_task(task_id, _scope())
    assert task.attempt_id is not None
    store.resolve_lost_attempt(task_id, task.attempt_id, "executor lease lost")
    before = store.counts()
    binding = _binding(
        TaskProgressOriginKind.VOICE,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    grant = _grant(task_id=task_id)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    voice_events: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        arbiter=arbiter,
        voice_events=voice_events,
    )

    activation = await bridge.activate()
    assert activation.active is True
    await _wait_settled(bridge)

    assert [item.task_event.seq for item in voice_events] == [0, 3, 5]
    assert [item.task_event.event_type for item in voice_events] == [
        "task.accepted",
        "task.running",
        "task.terminal",
    ]
    terminal = voice_events[-1]
    assert terminal.task_event.producer == "task_core.reconciliation"
    assert terminal.source_event.producer.component == "task_core"
    assert (
        terminal.source_event.extensions["jiuwenswarm.task_progress_return"][
            "persistent_event_producer"
        ]
        == "task_core.reconciliation"
    )
    bridge_snapshot = bridge.snapshot()
    assert bridge_snapshot.unprojected_events == 3
    assert bridge_snapshot.projected_events == 3
    assert bridge_snapshot.voice_intents == 3
    assert bridge_snapshot.state is TaskProgressReturnState.CLOSED
    assert bridge_snapshot.reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    arbiter_snapshot = arbiter.snapshot()
    assert arbiter_snapshot.no_projection_advances == 3
    assert arbiter_snapshot.accepted_events == 3
    assert arbiter_snapshot.pending_notifications == 0
    assert store.counts() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["authorization", "generation"])
async def test_exact_authority_no_projection_rechecks_current_fences(
    tmp_path: Path,
    fence: str,
) -> None:
    current_time = NOW
    generation_current = True
    store, task_id, correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    binding = _binding(
        TaskProgressOriginKind.VOICE,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    grant = _grant(task_id=task_id)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    arbiter = ProgressNotificationArbiter()
    voice_events: list[TaskProgressNotificationIntent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        generation_is_current=lambda _binding: generation_current,
        arbiter=arbiter,
        voice_events=voice_events,
        clock=lambda: current_time,
    )
    original_next = TaskEventAuthorityProgressSource.next_event

    async def fenced_next(
        authority_source: TaskEventAuthorityProgressSource,
    ) -> PersistentTaskEvent:
        nonlocal current_time, generation_current
        event = await original_next(authority_source)
        if event.seq == 1:
            if fence == "authorization":
                current_time = AFTER_EXPIRY
            else:
                generation_current = False
        return event

    with patch.object(TaskEventAuthorityProgressSource, "next_event", fenced_next):
        assert (await bridge.activate()).active is True
        await _wait_settled(bridge)

    snapshot = bridge.snapshot()
    assert snapshot.state is TaskProgressReturnState.FAILED
    assert snapshot.reason_id is (
        TaskProgressReturnReason.AUTHORIZATION_REJECTED
        if fence == "authorization"
        else TaskProgressReturnReason.STALE_GENERATION
    )
    assert snapshot.projected_events == 1
    assert snapshot.unprojected_events == 0
    assert [item.task_event.seq for item in voice_events] == [0]
    assert arbiter.snapshot().accepted_events == 1
    assert arbiter.snapshot().no_projection_advances == 0


@pytest.mark.asyncio
async def test_close_race_before_exact_no_projection_has_zero_arbiter_advance(
    tmp_path: Path,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    _advance_authority_task_running(store, task_id)
    binding = _binding(
        TaskProgressOriginKind.VOICE,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    grant = _grant(task_id=task_id)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    arbiter = ProgressNotificationArbiter()
    voice_events: list[TaskProgressNotificationIntent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        arbiter=arbiter,
        voice_events=voice_events,
    )
    second_dequeued = asyncio.Event()
    release_second = asyncio.Event()
    original_next = TaskEventAuthorityProgressSource.next_event

    async def paused_next(
        authority_source: TaskEventAuthorityProgressSource,
    ) -> PersistentTaskEvent:
        event = await original_next(authority_source)
        if event.seq == 1:
            second_dequeued.set()
            await release_second.wait()
        return event

    with patch.object(TaskEventAuthorityProgressSource, "next_event", paused_next):
        activation = await bridge.activate()
        assert activation.lease is not None
        await second_dequeued.wait()
        close_task = asyncio.create_task(activation.lease.close())
        await _wait_until(
            lambda: bridge.snapshot().state is TaskProgressReturnState.DETACHING
        )
        release_second.set()
        await close_task

    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert [item.task_event.seq for item in voice_events] == [0]
    assert arbiter.snapshot().accepted_events == 1
    assert arbiter.snapshot().no_projection_advances == 0


@pytest.mark.asyncio
async def test_authority_source_subclass_cannot_claim_formal_voice_route(
    tmp_path: Path,
) -> None:
    calls = {"matches": 0, "start": 0, "next": 0}

    class AuthoritySourceSubclass(TaskEventAuthorityProgressSource):
        def matches(self, _binding: TaskProgressOriginBinding) -> bool:
            calls["matches"] += 1
            return True

        async def start(self) -> bool:
            calls["start"] += 1
            return True

        async def next_event(self) -> PersistentTaskEvent:
            calls["next"] += 1
            return _lifecycle_events()[0]

    store, task_id, correlation_id = _authority_task(tmp_path)
    binding = _binding(
        TaskProgressOriginKind.VOICE,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    grant = _grant(task_id=task_id)
    arbiter = ProgressNotificationArbiter()
    voice_events: list[TaskProgressNotificationIntent] = []
    source = AuthoritySourceSubclass(
        store=store,
        authorization=grant,
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        arbiter=arbiter,
        voice_events=voice_events,
    )

    activation = await bridge.activate()

    assert activation.active is False
    assert (
        activation.reason_id is TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
    )
    assert calls == {"matches": 0, "start": 0, "next": 0}
    assert voice_events == []
    assert arbiter.snapshot().accepted_events == 0
    assert source.subscription.snapshot().start_head_seq is None


def test_authority_source_rejects_sqlite_store_subclass(tmp_path: Path) -> None:
    class SqliteStoreSubclass(SqliteTaskStore):
        pass

    with pytest.raises(TaskProgressReturnViolation) as raised:
        TaskEventAuthorityProgressSource(
            store=SqliteStoreSubclass(tmp_path / "forged-authority.sqlite"),
            authorization=_grant(),
            scope=_scope(),
            task_id="task-1",
        )

    assert raised.value.reason == "INVALID_TASK_PROGRESS_AUTHORITY_SOURCE"


@pytest.mark.asyncio
async def test_concrete_authority_source_rejects_distinct_longer_grant(
    tmp_path: Path,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    binding = _binding(
        TaskProgressOriginKind.VOICE,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=_grant(task_id=task_id, expires_at=AFTER_EXPIRY),
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    arbiter = ProgressNotificationArbiter()
    voice_events: list[TaskProgressNotificationIntent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=_grant(task_id=task_id),
        binding=binding,
        arbiter=arbiter,
        voice_events=voice_events,
    )

    activation = await bridge.activate()

    assert activation.active is False
    assert (
        activation.reason_id is TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
    )
    assert source.subscription.snapshot().start_head_seq is None
    assert arbiter.snapshot().accepted_events == 0
    assert voice_events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin_kind",
    [TaskProgressOriginKind.VOICE, TaskProgressOriginKind.TEXT],
)
async def test_queued_event_after_bridge_grant_expiry_has_zero_effects(
    origin_kind: TaskProgressOriginKind,
) -> None:
    current_time = NOW
    subscription = _SubscriptionDouble()
    prepared = (
        _PreparedSourceDouble(subscription, [])
        if origin_kind is TaskProgressOriginKind.VOICE
        else None
    )
    arbiter = ProgressNotificationArbiter()
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=origin_kind,
        subscription=subscription,
        prepared_source=prepared,
        arbiter=arbiter,
        voice_events=voice_events,
        text_events=text_events,
        allow_package_contract_handoff=origin_kind is TaskProgressOriginKind.VOICE,
        clock=lambda: current_time,
    )

    assert (await bridge.activate()).active is True
    await _wait_until(
        lambda: (
            (prepared.next_calls if prepared is not None else subscription.next_calls)
            == 1
        )
    )
    current_time = AFTER_EXPIRY
    if prepared is not None:
        prepared.publish(_lifecycle_events()[0])
    else:
        subscription.publish(_lifecycle_events()[0])
    await _wait_settled(bridge)

    assert bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        bridge.snapshot().reason_id is TaskProgressReturnReason.AUTHORIZATION_REJECTED
    )
    assert bridge.snapshot().source_events == 0
    assert voice_events == []
    assert text_events == []
    assert arbiter.snapshot().accepted_events == 0
    assert (
        prepared.close_calls if prepared is not None else subscription.close_calls
    ) == 1


@pytest.mark.asyncio
async def test_deferred_voice_drain_after_grant_expiry_has_zero_new_effects() -> None:
    current_time = NOW
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    arbiter = ProgressNotificationArbiter()
    foreground = _busy_foreground()
    voice_events: list[TaskProgressNotificationIntent] = []

    def foreground_supplier() -> ForegroundSnapshot:
        return foreground

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        voice_events.append(intent)

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=foreground_supplier,
        voice_sink=voice_sink,
        text_sink=lambda _event: _noop(),
        allow_package_contract_handoff=True,
        clock=lambda: current_time,
    )
    activation = await bridge.activate()
    assert activation.lease is not None
    await _wait_settled(bridge)
    before = arbiter.snapshot()
    assert before.pending_notifications == 1

    current_time = AFTER_EXPIRY
    foreground = _foreground()
    assert await activation.lease.drain_voice() == 0

    assert bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        bridge.snapshot().reason_id is TaskProgressReturnReason.AUTHORIZATION_REJECTED
    )
    assert voice_events == []
    assert arbiter.snapshot() == before
    assert prepared.close_calls == 1


@pytest.mark.asyncio
async def test_cancelled_close_during_atomic_snapshot_start_is_retained(
    tmp_path: Path,
) -> None:
    store, task_id, correlation_id = _authority_task(tmp_path)
    before = store.counts()
    binding = _binding(
        TaskProgressOriginKind.VOICE,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    grant = _grant(task_id=task_id)
    source = TaskEventAuthorityProgressSource(
        store=store,
        authorization=grant,
        scope=binding.scope,
        task_id=task_id,
        poll_interval=0.001,
        clock=lambda: NOW,
    )
    arbiter = ProgressNotificationArbiter()
    voice_events: list[TaskProgressNotificationIntent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=cast(_SubscriptionDouble, source.subscription),
        prepared_source=cast(_PreparedSourceDouble, source),
        authorization=grant,
        binding=binding,
        arbiter=arbiter,
        voice_events=voice_events,
    )
    snapshot_entered = threading.Event()
    release_snapshot = threading.Event()
    original_snapshot = store.event_authority_snapshot
    original_close = TaskEventAuthorityProgressSource.close
    close_calls = 0

    def blocked_snapshot(target_task_id: str, scope: ScopeRef, *, max_events: int):
        snapshot_entered.set()
        assert release_snapshot.wait(timeout=5)
        return original_snapshot(target_task_id, scope, max_events=max_events)

    async def counted_close(authority_source: TaskEventAuthorityProgressSource) -> None:
        nonlocal close_calls
        close_calls += 1
        await original_close(authority_source)

    with (
        patch.object(store, "event_authority_snapshot", side_effect=blocked_snapshot),
        patch.object(TaskEventAuthorityProgressSource, "close", counted_close),
    ):
        activation_task = asyncio.create_task(bridge.activate())
        assert await asyncio.to_thread(snapshot_entered.wait, 2)
        close_waiter = asyncio.create_task(bridge.close())
        await _wait_until(lambda: close_calls == 1)
        close_waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await close_waiter
        release_snapshot.set()
        activation = await asyncio.wait_for(activation_task, timeout=2)
        await _wait_until(
            lambda: bridge.snapshot().state is TaskProgressReturnState.CLOSED
        )

    assert activation.active is False
    assert activation.reason_id is TaskProgressReturnReason.CONSUMER_DETACHED
    assert close_calls == 1
    assert bridge.snapshot().worker_pending is False
    assert source.subscription.snapshot().worker_pending is False
    assert voice_events == []
    assert arbiter.snapshot().accepted_events == 0
    assert store.counts() == before


@pytest.mark.asyncio
async def test_prepared_voice_test_lease_requires_explicit_package_test_switch() -> (
    None
):
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
    )

    activation = await bridge.activate()

    assert activation.active is False
    assert (
        activation.reason_id is TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
    )
    assert prepared.start_calls == 0
    assert prepared.next_calls == 0
    assert prepared.close_calls == 0


@pytest.mark.asyncio
async def test_reserved_atomic_handoff_kind_cannot_claim_formal_voice_route() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    prepared.handoff_kind = TaskProgressHandoffKind.AUTHORITY_ATOMIC
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
        allow_package_contract_handoff=True,
    )

    activation = await bridge.activate()

    assert activation.active is False
    assert (
        activation.reason_id is TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
    )
    assert activation.handoff_kind is TaskProgressHandoffKind.AUTHORITY_ATOMIC
    assert prepared.start_calls == 0
    assert prepared.next_calls == 0
    assert prepared.close_calls == 0


@pytest.mark.asyncio
async def test_detach_close_is_idempotent_and_has_no_business_cancel_port() -> None:
    subscription = _SubscriptionDouble()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
    )

    activation = await bridge.activate()
    assert activation.active is True
    assert activation.lease is not None
    await activation.lease.close()
    await activation.lease.close()

    assert subscription.start_calls == 1
    assert subscription.close_calls == 1
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.CONSUMER_DETACHED
    assert bridge.snapshot().voice_intents == 0
    assert bridge.snapshot().text_events == 0


@pytest.mark.asyncio
async def test_cancelled_close_waiter_does_not_cancel_detach_cleanup() -> None:
    close_gate = asyncio.Event()
    subscription = _SubscriptionDouble(close_gate=close_gate)
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
    )
    activation = await bridge.activate()
    assert activation.lease is not None
    first_waiter = asyncio.create_task(activation.lease.close())
    await asyncio.sleep(0)
    first_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_waiter

    close_gate.set()
    await activation.lease.close()

    assert subscription.close_calls == 1
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.CONSUMER_DETACHED


@pytest.mark.asyncio
async def test_failed_text_detach_remains_retryable_by_the_exact_lease() -> None:
    subscription = _SubscriptionDouble(close_failures=1)
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
    )
    activation = await bridge.activate()
    assert activation.lease is not None
    await _wait_until(lambda: subscription.next_calls == 1)

    with pytest.raises(RuntimeError, match="injected subscription close failure"):
        await activation.lease.close()

    assert bridge.snapshot().state is TaskProgressReturnState.DETACHING
    await activation.lease.close()

    assert subscription.close_calls == 2
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.CONSUMER_DETACHED


@pytest.mark.asyncio
async def test_voice_sink_failure_is_not_acknowledged_or_retried() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, [_lifecycle_events()[0]])
    calls = 0
    arbiter = ProgressNotificationArbiter()

    async def failing_sink(_intent: TaskProgressNotificationIntent) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("notification-intent consumer unavailable")

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=_foreground,
        voice_sink=failing_sink,
        text_sink=lambda _event: _noop(),
        allow_package_contract_handoff=True,
        clock=lambda: NOW,
    )

    assert (await bridge.activate()).active is True
    await _wait_settled(bridge)

    assert calls == 1
    assert bridge.snapshot().voice_intents == 0
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.VOICE_SINK_FAILED
    assert arbiter.snapshot().accepted_events == 1
    assert arbiter.snapshot().pending_notifications == 1


@pytest.mark.asyncio
async def test_sink_failure_settles_without_later_delivery() -> None:
    subscription = _SubscriptionDouble(_lifecycle_events(start_seq=40))
    calls = 0

    async def failing_sink(_event: TaskProgressTextEvent) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("sink unavailable")

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=None,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.TEXT),
        generation_is_current=lambda _binding: True,
        arbiter=ProgressNotificationArbiter(),
        foreground=_foreground,
        voice_sink=lambda _intent: _noop(),
        text_sink=failing_sink,
        clock=lambda: NOW,
    )

    assert (await bridge.activate()).active is True
    await _wait_settled(bridge)

    assert calls == 1
    assert bridge.snapshot().text_events == 0
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.TEXT_SINK_FAILED


@dataclass
class _ParkedVoiceHarness:
    """Voice bridge parked in the source read holding exactly one deferral."""

    bridge: TaskProgressReturnBridge
    prepared: _PreparedSourceDouble
    subscription: _SubscriptionDouble
    arbiter: ProgressNotificationArbiter
    voice_events: list[TaskProgressNotificationIntent]
    text_events: list[TaskProgressTextEvent]
    foreground: list[ForegroundSnapshot]
    clock: list[str]


def _parked_voice_harness(
    *,
    close_failures: int = 0,
    failing_voice_sink: bool = False,
    prepared_factory: Callable[[_SubscriptionDouble], _PreparedSourceDouble]
    | None = None,
) -> _ParkedVoiceHarness:
    subscription = _SubscriptionDouble()
    prepared = (
        prepared_factory(subscription)
        if prepared_factory is not None
        else _PreparedSourceDouble(
            subscription,
            [_lifecycle_events()[0]],
            close_failures=close_failures,
        )
    )
    arbiter = ProgressNotificationArbiter()
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    foreground = [_busy_foreground()]
    clock = [NOW]

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        if failing_voice_sink:
            raise RuntimeError("notification-intent consumer unavailable")
        voice_events.append(intent)

    async def text_sink(event: TaskProgressTextEvent) -> None:
        text_events.append(event)

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=lambda: foreground[0],
        voice_sink=voice_sink,
        text_sink=text_sink,
        allow_package_contract_handoff=True,
        clock=lambda: clock[0],
    )
    return _ParkedVoiceHarness(
        bridge=bridge,
        prepared=prepared,
        subscription=subscription,
        arbiter=arbiter,
        voice_events=voice_events,
        text_events=text_events,
        foreground=foreground,
        clock=clock,
    )


@pytest.mark.asyncio
async def test_arbiter_failure_during_parked_read_still_closes_source_and_worker() -> (
    None
):
    harness = _parked_voice_harness()
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await harness.prepared.blocked.wait()

    assert harness.bridge.snapshot().state is TaskProgressReturnState.ACTIVE
    assert harness.bridge.snapshot().worker_pending is True
    assert harness.bridge.snapshot().pending_voice_intents == 1
    assert harness.prepared.close_calls == 0

    harness.foreground[0] = _foreground()
    with patch.object(
        harness.arbiter, "drain", side_effect=RuntimeError("arbiter unavailable")
    ):
        assert await activation.lease.drain_voice() == 0

    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.ARBITER_REJECTED
    )
    assert harness.prepared.blocked.is_set() is True
    assert harness.prepared.close_calls == 0
    assert harness.bridge.snapshot().worker_pending is True

    await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert harness.prepared.close_calls == 1
    assert harness.bridge.snapshot().worker_pending is False
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.ARBITER_REJECTED
    )
    assert harness.voice_events == []
    assert harness.text_events == []
    assert harness.bridge.snapshot().voice_intents == 0
    assert harness.bridge.snapshot().voice_drains == 0
    assert harness.arbiter.snapshot().accepted_events == 1


@pytest.mark.asyncio
async def test_emit_failure_during_parked_read_converges_on_repeated_close() -> None:
    harness = _parked_voice_harness(failing_voice_sink=True)
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await harness.prepared.blocked.wait()

    harness.foreground[0] = _foreground()
    assert await activation.lease.drain_voice() == 0

    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id
        is TaskProgressReturnReason.VOICE_SINK_FAILED
    )
    assert harness.prepared.blocked.is_set() is True
    assert harness.prepared.close_calls == 0
    assert harness.bridge.snapshot().worker_pending is True

    await asyncio.wait_for(activation.lease.close(), timeout=5)
    await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert harness.prepared.close_calls == 1
    assert harness.bridge.snapshot().worker_pending is False
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id
        is TaskProgressReturnReason.VOICE_SINK_FAILED
    )
    assert harness.voice_events == []
    assert harness.bridge.snapshot().voice_intents == 0
    assert harness.bridge.snapshot().voice_drains == 0


@pytest.mark.asyncio
async def test_failed_cleanup_during_parked_read_retries_and_keeps_business_truth() -> (
    None
):
    harness = _parked_voice_harness(close_failures=1)
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await harness.prepared.blocked.wait()

    harness.foreground[0] = _foreground()
    with patch.object(
        harness.arbiter, "drain", side_effect=RuntimeError("arbiter unavailable")
    ):
        assert await activation.lease.drain_voice() == 0
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED

    with pytest.raises(RuntimeError, match="injected prepared source close failure"):
        await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert harness.prepared.close_calls == 1
    assert harness.bridge.snapshot().worker_pending is True
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.ARBITER_REJECTED
    )

    await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert harness.prepared.close_calls == 2
    assert harness.bridge.snapshot().worker_pending is False
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.ARBITER_REJECTED
    )
    assert harness.voice_events == []
    assert harness.bridge.snapshot().voice_intents == 0


@pytest.mark.asyncio
async def test_terminal_delivery_with_failed_self_close_still_detaches_the_source() -> (
    None
):
    subscription = _SubscriptionDouble(_lifecycle_events(), close_failures=1)
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
        text_events=text_events,
    )

    activation = await bridge.activate()
    assert activation.lease is not None
    await _wait_settled(bridge)

    assert [event.task_event.seq for event in text_events] == [0, 1, 2]
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert subscription.close_calls == 1

    await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert subscription.close_calls == 2
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert len(text_events) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("settled", ["feature_disabled", "start_refused"])
async def test_close_on_a_settled_bridge_adds_zero_source_effects(
    settled: str,
) -> None:
    subscription = _SubscriptionDouble(start_result=settled != "start_refused")
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
        enabled=settled != "feature_disabled",
    )

    activation = await bridge.activate()
    assert activation.active is False
    expected_close_calls = 0 if settled == "feature_disabled" else 1
    assert subscription.close_calls == expected_close_calls

    await asyncio.wait_for(bridge.close(), timeout=5)
    await asyncio.wait_for(bridge.close(), timeout=5)

    assert subscription.close_calls == expected_close_calls
    assert subscription.start_calls == (0 if settled == "feature_disabled" else 1)
    assert bridge.snapshot().state is (
        TaskProgressReturnState.DISABLED
        if settled == "feature_disabled"
        else TaskProgressReturnState.UNAVAILABLE
    )
    assert bridge.snapshot().reason_id is (
        TaskProgressReturnReason.FEATURE_DISABLED
        if settled == "feature_disabled"
        else TaskProgressReturnReason.SOURCE_FAILED
    )
    assert bridge.snapshot().worker_pending is False


@pytest.mark.asyncio
async def test_successor_bridge_after_a_residual_close_replays_its_own_source() -> None:
    """Same-lifetime characterization, not durability evidence.

    The bridge keeps no cross-process state, so a successor after a residual
    close is a fresh instance over a fresh source rather than a resumed one.
    """

    harness = _parked_voice_harness()
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await harness.prepared.blocked.wait()
    harness.foreground[0] = _foreground()
    with patch.object(
        harness.arbiter, "drain", side_effect=RuntimeError("arbiter unavailable")
    ):
        assert await activation.lease.drain_voice() == 0
    await asyncio.wait_for(activation.lease.close(), timeout=5)
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED

    successor = _parked_voice_harness()
    successor_activation = await successor.bridge.activate()
    assert successor_activation.active is True
    assert successor_activation.lease is not None
    await successor.prepared.blocked.wait()
    successor.foreground[0] = _foreground()

    assert await successor_activation.lease.drain_voice() == 1
    assert [intent.task_event.seq for intent in successor.voice_events] == [0]
    assert successor.bridge.snapshot().voice_drains == 1
    assert harness.voice_events == []

    await asyncio.wait_for(successor_activation.lease.close(), timeout=5)


@pytest.mark.asyncio
async def test_expired_grant_drain_during_parked_read_joins_the_worker_on_close() -> (
    None
):
    """The scenario close()'s own comment names: a failed drain, then close().

    A drain that rejects settles the business reason and detaches the source
    while the worker is still parked inside the read it started earlier.  The
    source half being settled is not the poll being over, so close() owes this
    scenario both halves.  Against a source whose detach outlives its close()
    call, the parked read is released strictly after close() reached the
    source: only the explicit worker join makes the returned close() an honest
    statement about the poll, and skipping the join solely on this
    preserve-the-settled-reason path leaves the poll running behind it.
    """

    harness = _parked_voice_harness(
        prepared_factory=lambda subscription: _RetainedDetachPreparedSourceDouble(
            subscription, [_lifecycle_events()[0]]
        )
    )
    prepared = harness.prepared
    assert isinstance(prepared, _RetainedDetachPreparedSourceDouble)
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await prepared.blocked.wait()

    harness.clock[0] = AFTER_EXPIRY
    harness.foreground[0] = _foreground()
    assert await activation.lease.drain_voice() == 0

    # The rejected drain detached the source itself, so the source half is
    # settled while the worker is still parked in the read it started earlier.
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id
        is TaskProgressReturnReason.AUTHORIZATION_REJECTED
    )
    assert prepared.close_calls == 1
    assert harness.bridge.snapshot().worker_pending is True
    # A barrier, not a race: the detach still owes the parked read its release,
    # so a close() that returned here would return over a running poll.
    assert prepared.detach_task is not None
    assert prepared.detach_task.done() is False

    # The timeout is a deadlock guard, not a settling delay: wait_for runs the
    # coroutine inline here, so close() still observes the unsettled worker.
    # Without it a close() that skipped the join would hang this case on the
    # parked read instead of reporting which half of the claim broke.
    await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert harness.bridge.snapshot().worker_pending is False
    assert prepared.detach_task.done() is True
    assert prepared.close_calls == 1
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id
        is TaskProgressReturnReason.AUTHORIZATION_REJECTED
    )
    assert harness.voice_events == []
    assert harness.text_events == []
    assert harness.bridge.snapshot().voice_intents == 0
    assert harness.bridge.snapshot().voice_drains == 0


@pytest.mark.asyncio
async def test_unsafe_generation_evidence_failure_is_contained_by_the_worker() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, [])
    arbiter = ProgressNotificationArbiter()
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    binding = _binding(TaskProgressOriginKind.VOICE, generation=MAX_SAFE_INTEGER + 1)

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        voice_events.append(intent)

    async def text_sink(event: TaskProgressTextEvent) -> None:
        text_events.append(event)

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=binding,
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=_foreground,
        voice_sink=voice_sink,
        text_sink=text_sink,
        allow_package_contract_handoff=True,
        clock=lambda: NOW,
    )

    # Unchanged fail-closed disposition: minting activation evidence for a
    # generation outside the cross-language safe range still raises.
    with pytest.raises(ContractViolation):
        await bridge.activate()

    worker = next(
        task
        for task in asyncio.all_tasks()
        if task.get_name() == f"live-voice-task-progress:{binding.task_id}"
    )
    prepared.publish(_lifecycle_events()[0])
    await _wait_settled(bridge)

    # Containment: the worker settles its own failure instead of ending as a
    # task whose exception nobody ever retrieves.
    assert worker.done() is True
    assert worker.cancelled() is False
    assert worker.exception() is None
    assert bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.SOURCE_FAILED
    assert prepared.close_calls == 1

    # Contained, never silently successful, and with zero delivered effects.
    assert voice_events == []
    assert text_events == []
    assert bridge.snapshot().projected_events == 0
    assert bridge.snapshot().voice_intents == 0
    assert bridge.snapshot().voice_drains == 0
    assert bridge.snapshot().text_events == 0
    assert arbiter.snapshot().accepted_events == 0
    assert arbiter.snapshot().pending_notifications == 0

    await bridge.close()

    assert prepared.close_calls == 1
    assert bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.SOURCE_FAILED


@pytest.mark.asyncio
async def test_cancelled_worker_stays_cancelled_instead_of_being_contained() -> None:
    """Containment owns background failure only; caller cancellation propagates.

    The worker is a bare task on the owner loop, so any loop shutdown or task
    group teardown cancels it.  A containment handler that also absorbed the
    cancel would report the cancelled worker as a normal completion, and the
    supervisor that asked for the cancel would never learn the task honoured it.
    """

    harness = _parked_voice_harness()
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await harness.prepared.blocked.wait()
    worker = _worker_task("task-1")
    assert harness.bridge.snapshot().worker_pending is True

    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker

    # The cancel is still reported as a cancel, not as a completed worker.
    assert worker.cancelled() is True
    assert harness.bridge.snapshot().worker_pending is False

    # Containment truth and cleanup are unchanged by the propagation.
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert harness.bridge.snapshot().reason_id is TaskProgressReturnReason.SOURCE_FAILED
    assert harness.prepared.close_calls == 1
    assert harness.voice_events == []
    assert harness.text_events == []
    assert harness.bridge.snapshot().voice_intents == 0

    await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert harness.prepared.close_calls == 1
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert harness.bridge.snapshot().reason_id is TaskProgressReturnReason.SOURCE_FAILED


@pytest.mark.asyncio
async def test_partly_attached_source_is_still_detached_by_a_later_close() -> None:
    """A source that start() may have half attached counts as opened from then on.

    activate() marks the source opened before awaiting start(), so a start()
    that raises - and whose compensating close() also fails, escaping activate()
    - still leaves close() obliged to reach the source.  Marking the source
    opened only after a successful start would let close() decide there is
    nothing to clean up and strand a source that start() had already attached.
    """

    harness = _parked_voice_harness(close_failures=1)

    with (
        patch.object(
            harness.prepared,
            "start",
            side_effect=RuntimeError("prepared source start unavailable"),
        ),
        pytest.raises(RuntimeError, match="injected prepared source close failure"),
    ):
        await harness.bridge.activate()

    # activate()'s own compensating close failed, so the source is still attached.
    assert harness.prepared.close_calls == 1
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.HANDOFF_REJECTED
    )
    assert harness.bridge.snapshot().worker_pending is False

    await asyncio.wait_for(harness.bridge.close(), timeout=5)

    # The detach actually reaches the source instead of returning early.
    assert harness.prepared.close_calls == 2
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.HANDOFF_REJECTED
    )

    # Idempotent afterwards: a detached source is not closed a third time.
    await asyncio.wait_for(harness.bridge.close(), timeout=5)

    assert harness.prepared.close_calls == 2
    assert harness.voice_events == []
    assert harness.text_events == []


@pytest.mark.asyncio
async def test_close_joins_a_worker_whose_source_detaches_after_close_returns() -> None:
    """close() returning means the worker settled, not that it probably will.

    The source's detach finishes on a later event-loop turn, so the parked read
    is released strictly after source close returned.  Only the explicit worker
    join makes the returned close() an honest statement about the worker.
    """

    harness = _parked_voice_harness(
        prepared_factory=lambda subscription: _RetainedDetachPreparedSourceDouble(
            subscription, [_lifecycle_events()[0]]
        )
    )
    prepared = harness.prepared
    assert isinstance(prepared, _RetainedDetachPreparedSourceDouble)
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await prepared.blocked.wait()
    assert harness.bridge.snapshot().worker_pending is True

    await asyncio.wait_for(activation.lease.close(), timeout=5)

    # Both owned children are settled the moment close() returns.
    assert harness.bridge.snapshot().worker_pending is False
    assert prepared.detach_task is not None
    assert prepared.detach_task.done() is True
    assert prepared.close_calls == 1
    assert harness.bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert (
        harness.bridge.snapshot().reason_id
        is TaskProgressReturnReason.CONSUMER_DETACHED
    )
    assert harness.voice_events == []
    assert harness.text_events == []


@pytest.mark.asyncio
async def test_worker_containment_keeps_the_earlier_settled_business_truth() -> None:
    """An earlier settled truth wins over the worker's own later containment.

    A consumer drain can settle a specific business failure while the worker is
    still parked in the source read.  When that worker later hits an escaping
    failure of its own, containment must record nothing new: relabelling the
    reason as a generic source failure would erase the truth the consumer is
    owed and was already told.
    """

    harness = _parked_voice_harness()
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await harness.prepared.blocked.wait()
    worker = _worker_task("task-1")

    harness.foreground[0] = _foreground()
    with patch.object(
        harness.arbiter, "drain", side_effect=RuntimeError("arbiter unavailable")
    ):
        assert await activation.lease.drain_voice() == 0

    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.ARBITER_REJECTED
    )
    assert harness.bridge.snapshot().worker_pending is True

    # The source now hands the still-parked worker an event whose evidence falls
    # outside the cross-language safe range, so the worker's own read path
    # raises after the consumer failure has already been settled.
    harness.prepared.publish(_event(MAX_SAFE_INTEGER + 1, "task.running", "running"))
    await _wait_settled(harness.bridge)

    # Contained, never silently successful, and never relabelled.
    assert worker.done() is True
    assert worker.cancelled() is False
    assert worker.exception() is None
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.ARBITER_REJECTED
    )
    assert harness.prepared.close_calls == 1
    assert harness.voice_events == []
    assert harness.text_events == []
    assert harness.bridge.snapshot().voice_intents == 0
    assert harness.bridge.snapshot().voice_drains == 0

    await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert harness.prepared.close_calls == 1
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        harness.bridge.snapshot().reason_id is TaskProgressReturnReason.ARBITER_REJECTED
    )


@pytest.mark.asyncio
async def test_worker_containment_covers_a_failure_that_is_not_a_violation() -> None:
    """Containment owns any escaping failure, not one exception flavour.

    The worker's own delivery lane calls the arbiter's acknowledge port with no
    handler of its own around it, and the arbiter is a construction parameter
    with no type guard, so an unavailable one raises a plain RuntimeError
    straight out of the worker body.  A containment clause narrowed to the
    violation type the source itself raises still passes every source-shaped
    regression while leaving exactly this failure ending the task with an
    exception nobody retrieves - and leaving the bridge advertising ACTIVE
    while it holds it.
    """

    harness = _parked_voice_harness(
        prepared_factory=lambda subscription: _PreparedSourceDouble(subscription, [])
    )
    activation = await harness.bridge.activate()
    assert activation.lease is not None
    await harness.prepared.blocked.wait()
    worker = _worker_task("task-1")
    assert harness.bridge.snapshot().state is TaskProgressReturnState.ACTIVE

    # A safe foreground makes the published event a display-now delivery, so
    # the worker reaches the acknowledge port on its own lane rather than
    # through a consumer drain.
    harness.foreground[0] = _foreground()
    with patch.object(
        harness.arbiter,
        "acknowledge",
        side_effect=RuntimeError("notification arbiter unavailable"),
    ):
        harness.prepared.publish(_lifecycle_events()[0])
        await _wait_settled(harness.bridge)

    # Contained: the worker retrieves its own failure instead of ending as a
    # task whose exception nobody ever takes.
    assert worker.done() is True
    assert worker.cancelled() is False
    assert worker.exception() is None

    # And never silently successful: the bridge stops claiming it is active.
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert harness.bridge.snapshot().reason_id is TaskProgressReturnReason.SOURCE_FAILED
    assert harness.prepared.close_calls == 1

    # The intent reached the sink but was never acknowledged, so it is never
    # counted as delivered progress and no other lane advanced.
    assert len(harness.voice_events) == 1
    assert harness.bridge.snapshot().voice_intents == 0
    assert harness.bridge.snapshot().voice_drains == 0
    assert harness.bridge.snapshot().text_events == 0
    assert harness.text_events == []

    await asyncio.wait_for(activation.lease.close(), timeout=5)

    assert harness.prepared.close_calls == 1
    assert harness.bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert harness.bridge.snapshot().reason_id is TaskProgressReturnReason.SOURCE_FAILED
