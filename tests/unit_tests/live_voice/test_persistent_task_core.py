# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CommandEnvelope,
    ContractViolation,
    ErrorCode,
    InputCommitState,
    LifecycleKind,
    QueryEnvelope,
    ResultEnvelope,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
    WorkProgressEventV2,
    canonical_json_bytes,
    validate_transition,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    ExecutorRetryReadiness,
    FormalAttemptState,
    FormalTaskSpec,
    FormalTaskState,
    FormalTaskViolation,
    OutboxKind,
    OutboxState,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskEvent,
    PersistentTaskRecord,
    ReconciliationState,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    TaskAdjustmentDeliveryResult,
    TaskAdjustmentSettlement,
    TaskAdjustmentState,
    TaskEventAuthoritySnapshot,
    TaskMutationDisposition,
    TaskResultArtifact,
    TaskResultAvailability,
    TaskResultRecord,
    TaskRetryAuthoritySnapshot,
    TaskRetryProductRequestFingerprint,
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


def test_task_event_authority_snapshot_is_publicly_exported() -> None:
    from jiuwenswarm.server.live_voice import formal_task_models

    assert "TaskEventAuthoritySnapshot" in formal_task_models.__all__
    assert formal_task_models.TaskEventAuthoritySnapshot is TaskEventAuthoritySnapshot


def test_formal_task_states_match_the_shared_transition_contract() -> None:
    expected = {
        FormalTaskState.ACCEPTED: frozenset(
            {
                FormalTaskState.RUNNING,
                FormalTaskState.BLOCKED,
                FormalTaskState.DECISION_REQUIRED,
                FormalTaskState.TERMINAL,
            }
        ),
        FormalTaskState.RUNNING: frozenset(
            {
                FormalTaskState.BLOCKED,
                FormalTaskState.DECISION_REQUIRED,
                FormalTaskState.TERMINAL,
            }
        ),
        FormalTaskState.BLOCKED: frozenset(
            {
                FormalTaskState.RUNNING,
                FormalTaskState.DECISION_REQUIRED,
                FormalTaskState.TERMINAL,
            }
        ),
        FormalTaskState.DECISION_REQUIRED: frozenset(
            {
                FormalTaskState.RUNNING,
                FormalTaskState.BLOCKED,
                FormalTaskState.TERMINAL,
            }
        ),
        FormalTaskState.TERMINAL: frozenset(),
    }

    assert set(expected) == set(FormalTaskState)
    for current in FormalTaskState:
        for target in FormalTaskState:
            outcome = (
                TerminalOutcome.COMPLETED
                if target is FormalTaskState.TERMINAL
                else None
            )
            if target in expected[current]:
                validate_transition(
                    LifecycleKind.TASK,
                    current.value,
                    target.value,
                    outcome=outcome,
                )
            else:
                with pytest.raises(ContractViolation) as rejected:
                    validate_transition(
                        LifecycleKind.TASK,
                        current.value,
                        target.value,
                        outcome=outcome,
                    )
                assert rejected.value.reason == "INVALID_LIFECYCLE_TRANSITION"


def test_formal_task_spec_constraints_round_trip_and_legacy_absence_is_empty(
    tmp_path: Path,
) -> None:
    invocation = _create(tmp_path)
    spec = FormalTaskSpec(
        name="Bounded revision",
        instruction="Change one project file.",
        origin=invocation.envelope.origin,
        context=_context(tmp_path),
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        required_capabilities=("task.create",),
        side_effect_class="project_mutation",
        constraints=("Keep tests green.", "Do not access the network."),
        attributes=(
            ("model_config_version", "catalog-v1"),
            ("model_identity", "default#0"),
        ),
    )

    encoded = spec.to_dict()

    assert encoded["constraints"] == [
        "Keep tests green.",
        "Do not access the network.",
    ]
    assert FormalTaskSpec.from_dict(encoded) == spec
    legacy = dict(encoded)
    del legacy["constraints"]
    assert FormalTaskSpec.from_dict(legacy).constraints == ()


@pytest.mark.parametrize(
    "constraints",
    [
        ({"not": "text"},),
        ("contains\x00nul",),
        ("x" * 1_025,),
        tuple(f"constraint-{index}" for index in range(17)),
        ("x" * 1_024, "y" * 1_024, "z" * 1_024, "w" * 1_024, "overflow"),
    ],
)
def test_formal_task_spec_constraints_enforce_closed_utf8_bounds(
    tmp_path: Path,
    constraints: tuple[object, ...],
) -> None:
    invocation = _create(tmp_path)

    with pytest.raises(FormalTaskViolation) as rejected:
        FormalTaskSpec(
            name="Bounded revision",
            instruction="Change one project file.",
            origin=invocation.envelope.origin,
            context=_context(tmp_path),
            executor_id=FORMAL_PROJECT_EXECUTOR_ID,
            required_capabilities=("task.create",),
            side_effect_class="project_mutation",
            constraints=constraints,
        )

    assert rejected.value.reason == "INVALID_TASK_CONSTRAINTS"


def test_command_result_extension_helper_is_exact_and_payload_free(
    tmp_path: Path,
) -> None:
    from jiuwenswarm.server.live_voice import formal_task_models

    invocation = _create(tmp_path, instruction="private command instruction")
    extensions = formal_task_models.command_result_extensions(
        formal_task_models.TaskCommandDisposition.APPLIED,
        admission_event_id="event-requested",
        settlement_event_id="event-applied",
    )

    assert extensions == {
        "live_voice.command": {
            "disposition": "applied",
            "admission_event_id": "event-requested",
            "settlement_event_id": "event-applied",
        }
    }
    encoded = json.dumps(extensions, sort_keys=True)
    assert invocation.envelope.payload["instruction"] not in encoded


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
        interaction_id=f"interaction-1{identity_suffix}",
        turn_id=turn_id,
        commit_id=commit_id,
        name="Formal project task",
        instruction=instruction,
        context=_context(project),
        attributes={
            "model_identity": "default#0",
            "model_config_version": "catalog-v1",
        },
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


def _adjust(
    task_id: str,
    adjustment: str,
    *,
    command_id: str = "command-adjust",
    request_id: str = "request-adjust",
) -> tuple[CommandEnvelope, TaskAuthorizationGrant]:
    base = _cancel(task_id)
    payload = base.envelope.to_dict()
    payload.update(
        {
            "request_id": request_id,
            "command_id": command_id,
            "command_type": "task.adjust",
            "required_capabilities": ["task.adjust"],
            "payload": {"adjustment": adjustment},
        }
    )
    return (
        CommandEnvelope.from_dict(payload),
        _grant("task.adjust", command_id=command_id, target=task_id),
    )


def _wave2_command(
    task_id: str,
    command_type: str,
    payload: dict[str, object],
    *,
    command_id: str,
    request_id: str | None = None,
) -> tuple[CommandEnvelope, TaskAuthorizationGrant]:
    base = _cancel(task_id).envelope.to_dict()
    base.update(
        {
            "request_id": request_id or f"request-{command_id}",
            "command_id": command_id,
            "command_type": command_type,
            "required_capabilities": [command_type],
            "payload": payload,
        }
    )
    return (
        CommandEnvelope.from_dict(base),
        _grant(command_type, command_id=command_id, target=task_id),
    )


def _forge_command_payload_scalar(
    command: CommandEnvelope,
    field: str,
    value: object,
) -> CommandEnvelope:
    """Bypass the wire parser to pressure-test a direct Store trust boundary."""

    forged = replace(command)
    frozen_payload = command._payload  # type: ignore[attr-defined]
    items = dict(frozen_payload.items)
    items[field] = value
    object.__setattr__(
        forged,
        "_payload",
        type(frozen_payload)(tuple(sorted(items.items()))),
    )
    return forged


def _successor_command(
    predecessor: PersistentTaskRecord,
    terminal_event: PersistentTaskEvent,
    *,
    result_sha256: str | None,
    command_id: str = "command-successor",
) -> tuple[CommandEnvelope, TaskAuthorizationGrant]:
    return _wave2_command(
        predecessor.task_id,
        "task.create_successor",
        {
            "expected_predecessor_revision_number": predecessor.revision_number,
            "expected_predecessor_event_head": predecessor.event_head,
            "predecessor_terminal_event_id": terminal_event.event_id,
            "predecessor_outcome": predecessor.outcome.value,
            "predecessor_result_sha256": result_sha256,
            "name": "Successor revision",
            "instruction": "Apply the explicit successor revision.",
            "constraints": ["Preserve predecessor truth."],
            "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
            "side_effect_class": "project_mutation",
            "attributes": {
                "model_identity": "default#0",
                "model_config_version": "catalog-v1",
            },
        },
        command_id=command_id,
    )


def _retry(
    task_id: str,
    previous_attempt_id: str,
    previous_outcome: TerminalOutcome,
    attempt_number: int,
    *,
    command_id: str | None = None,
    correlation_id: str = "correlation-1",
) -> tuple[CommandEnvelope, TaskAuthorizationGrant]:
    retry_command_id = command_id or f"command-retry-{attempt_number}"
    product_request = _retry_product_request_fingerprint(
        command_id=retry_command_id,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    command = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": f"request-retry-{attempt_number}",
            "command_id": retry_command_id,
            "command_type": "task.retry",
            "issued_at": NOW,
            "scope": _scope().to_dict(),
            "correlation_id": correlation_id,
            "causation_id": None,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": task_id},
            "context_refs": [],
            "required_capabilities": ["task.retry"],
            "payload": {
                "previous_attempt_id": previous_attempt_id,
                "previous_outcome": previous_outcome.value,
                "attempt_number": attempt_number,
            },
            "extensions": product_request.to_extensions(),
        }
    )
    return command, _grant("task.retry", command_id=retry_command_id, target=task_id)


def _retry_product_request_fingerprint(
    *,
    command_id: str,
    task_id: str,
    issued_at: str = NOW,
    correlation_id: str = "correlation-1",
    causation_id: str | None = None,
    confirmation_id: str = "confirm-1",
) -> TaskRetryProductRequestFingerprint:
    """Model the product ledger facts; never include request_id or server facts."""

    product_owned_facts = {
        "operation": "task.retry",
        "scope": _scope().to_dict(),
        "command_id": command_id,
        "task_id": task_id,
        "issued_at": issued_at,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
        "confirmation_id": confirmation_id,
    }
    assert "request_id" not in product_owned_facts
    assert "payload" not in product_owned_facts
    assert "context" not in product_owned_facts
    return TaskRetryProductRequestFingerprint(
        hashlib.sha256(canonical_json_bytes(product_owned_facts)).hexdigest()
    )


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


def _list_tasks(*, cursor: str | None = None, limit: int | None = None):
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.list",
        request_id="request-list",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant("task.list", command_id=None, target=None),
        cursor=cursor,
        limit=limit,
    )
    return FormalTaskPolicyAdapter().map(intent)


def _result(task_id: str):
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.result",
        request_id="request-result",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant("task.result", command_id=None, target=task_id),
        task_id=task_id,
    )
    return FormalTaskPolicyAdapter().map(intent)


def _events(task_id: str, after_seq: int, *, limit: int | None = None):
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
        limit=limit,
    )
    return FormalTaskPolicyAdapter().map(intent)


def _observations(
    item: PersistentOutboxItem,
    *,
    outcome: TerminalOutcome | None = None,
    result_text: str | None = None,
    result_artifacts: tuple[TaskResultArtifact, ...] = (),
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
                result_text=(
                    result_text if state is FormalAttemptState.TERMINAL else None
                ),
                result_artifacts=(
                    result_artifacts if state is FormalAttemptState.TERMINAL else ()
                ),
            )
        )
    return tuple(result)


def _downgrade_fixture_to_v1(database: Path) -> None:
    """Rebuild the exact v1 Task/attempt shape from the current schema."""

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE task_event_consumption")
        connection.execute("DROP INDEX uq_task_events_exact")
        connection.execute("DROP TABLE task_results")
        connection.execute("DROP TABLE current_background_tasks")
        connection.execute(
            """CREATE TABLE tasks_v1 (
                task_id TEXT PRIMARY KEY, scope_key TEXT NOT NULL,
                scope_json TEXT NOT NULL, spec_json TEXT NOT NULL,
                state TEXT NOT NULL, outcome TEXT,
                attempt_id TEXT NOT NULL UNIQUE, correlation_id TEXT NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                dispatch_fenced INTEGER NOT NULL DEFAULT 0,
                event_head INTEGER NOT NULL, reconciliation_state TEXT,
                reconciliation_reason TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """INSERT INTO tasks_v1(
                task_id, scope_key, scope_json, spec_json, state, outcome,
                attempt_id, correlation_id, cancel_requested, dispatch_fenced,
                event_head, reconciliation_state, reconciliation_reason,
                created_at, updated_at)
                SELECT task_id, scope_key, scope_json, spec_json, state, outcome,
                       attempt_id, correlation_id, cancel_requested, dispatch_fenced,
                       event_head, reconciliation_state, reconciliation_reason,
                       created_at, updated_at FROM tasks"""
        )
        connection.execute(
            """CREATE TABLE attempts_v1 (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE
                    REFERENCES tasks(task_id) ON DELETE CASCADE,
                executor_id TEXT NOT NULL, executor_ref TEXT,
                state TEXT NOT NULL, outcome TEXT,
                source_seq INTEGER NOT NULL DEFAULT -1,
                updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """INSERT INTO attempts_v1(
                attempt_id, task_id, executor_id, executor_ref, state,
                outcome, source_seq, updated_at)
                SELECT attempt_id, task_id, executor_id, executor_ref, state,
                       outcome, source_seq, updated_at FROM attempts"""
        )
        connection.execute("DROP TABLE attempts")
        connection.execute("ALTER TABLE attempts_v1 RENAME TO attempts")
        connection.execute("DROP TABLE tasks")
        connection.execute("ALTER TABLE tasks_v1 RENAME TO tasks")
        connection.execute("CREATE INDEX idx_tasks_scope ON tasks(scope_key, task_id)")
        connection.execute("CREATE INDEX idx_tasks_state ON tasks(state, task_id)")
        connection.execute("UPDATE metadata SET value='1' WHERE key='schema_version'")
        connection.commit()


def _downgrade_fixture_to_v4(database: Path) -> None:
    """Rebuild exact Task 2 v4 shape without changing durable lifecycle facts."""

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE task_event_consumption")
        connection.execute("DROP INDEX uq_task_events_exact")
        connection.execute(
            """CREATE TABLE attempts_v4 (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
                executor_id TEXT NOT NULL, executor_ref TEXT,
                state TEXT NOT NULL, outcome TEXT,
                source_seq INTEGER NOT NULL DEFAULT -1, updated_at TEXT NOT NULL,
                UNIQUE(task_id, attempt_number))"""
        )
        connection.execute(
            """INSERT INTO attempts_v4(
                   attempt_id, task_id, attempt_number, executor_id, executor_ref,
                   state, outcome, source_seq, updated_at)
               SELECT attempt_id, task_id, attempt_number, executor_id, executor_ref,
                      state, outcome, source_seq, updated_at FROM attempts"""
        )
        connection.execute("DROP TABLE attempts")
        connection.execute("ALTER TABLE attempts_v4 RENAME TO attempts")
        connection.execute("UPDATE metadata SET value='4' WHERE key='schema_version'")
        connection.commit()


def _downgrade_fixture_to_v3(database: Path) -> None:
    """Rebuild the exact D-085 v3 Task shape without changing durable facts."""

    _downgrade_fixture_to_v4(database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """CREATE TABLE tasks_v3 (
                task_id TEXT PRIMARY KEY, scope_key TEXT NOT NULL,
                scope_json TEXT NOT NULL, spec_json TEXT NOT NULL,
                state TEXT NOT NULL, outcome TEXT,
                attempt_id TEXT NOT NULL UNIQUE, correlation_id TEXT NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                dispatch_fenced INTEGER NOT NULL DEFAULT 0,
                event_head INTEGER NOT NULL, reconciliation_state TEXT,
                reconciliation_reason TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """INSERT INTO tasks_v3(
                task_id, scope_key, scope_json, spec_json, state, outcome,
                attempt_id, correlation_id, cancel_requested, dispatch_fenced,
                event_head, reconciliation_state, reconciliation_reason,
                created_at, updated_at)
                SELECT task_id, scope_key, scope_json, spec_json, state, outcome,
                       attempt_id, correlation_id, cancel_requested, dispatch_fenced,
                       event_head, reconciliation_state, reconciliation_reason,
                       created_at, updated_at FROM tasks"""
        )
        connection.execute("DROP TABLE tasks")
        connection.execute("ALTER TABLE tasks_v3 RENAME TO tasks")
        connection.execute("CREATE INDEX idx_tasks_scope ON tasks(scope_key, task_id)")
        connection.execute("CREATE INDEX idx_tasks_state ON tasks(state, task_id)")
        connection.execute("UPDATE metadata SET value='3' WHERE key='schema_version'")
        connection.commit()


def _downgrade_fixture_to_v2(database: Path) -> None:
    """Rebuild the exact D-058 v2 shape without changing durable facts."""

    _downgrade_fixture_to_v3(database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE task_results")
        connection.execute("DROP TABLE current_background_tasks")
        connection.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
        connection.commit()


def _database_dump(database: Path) -> tuple[str, ...]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.iterdump())


def _task_authority_dump(database: Path) -> tuple[tuple[str, tuple[tuple, ...]], ...]:
    """Snapshot every mutable Task surface except the command decision ledger."""

    tables = (
        "tasks",
        "attempts",
        "task_events",
        "executor_events",
        "outbox",
        "current_background_tasks",
        "task_results",
    )
    with sqlite3.connect(database) as connection:
        return tuple(
            (table, tuple(connection.execute(f"SELECT * FROM {table} ORDER BY rowid")))
            for table in tables
        )


def _database_authority_bytes(database: Path) -> bytes:
    """Return every persisted SQLite cell as bytes for privacy assertions."""

    with sqlite3.connect(database) as connection:
        tables = tuple(
            row[0]
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name NOT LIKE 'sqlite_%'
                   ORDER BY name"""
            )
        )
        values: list[bytes] = []
        for table in tables:
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                values.extend(
                    value if isinstance(value, bytes) else str(value).encode("utf-8")
                    for value in row
                    if value is not None
                )
    return b"\x00".join(values)


def _rehash_decision_binding(binding: dict[str, object]) -> bytes:
    authority = binding["authority"]
    assert type(authority) is dict
    binding["authority_sha256"] = hashlib.sha256(
        canonical_json_bytes(authority)
    ).hexdigest()
    if "binding_sha256" in binding:
        unsigned = {
            key: value for key, value in binding.items() if key != "binding_sha256"
        }
        binding["binding_sha256"] = hashlib.sha256(
            canonical_json_bytes(unsigned)
        ).hexdigest()
    return canonical_json_bytes(binding)


def _predecessor_dump(database: Path, task_id: str) -> tuple[tuple[str, tuple], ...]:
    """Snapshot every byte-bearing row owned by one immutable predecessor."""

    statements = {
        "task": ("SELECT * FROM tasks WHERE task_id=?", (task_id,)),
        "attempts": (
            "SELECT * FROM attempts WHERE task_id=? ORDER BY attempt_number",
            (task_id,),
        ),
        "events": (
            "SELECT * FROM task_events WHERE task_id=? ORDER BY seq",
            (task_id,),
        ),
        "executor_events": (
            """SELECT e.* FROM executor_events AS e JOIN attempts AS a
               ON a.attempt_id=e.attempt_id WHERE a.task_id=?
               ORDER BY e.source_seq, e.source_event_id""",
            (task_id,),
        ),
        "outbox": (
            "SELECT * FROM outbox WHERE task_id=? ORDER BY outbox_id",
            (task_id,),
        ),
        "result": (
            "SELECT * FROM task_results WHERE task_id=? ORDER BY source_event_id",
            (task_id,),
        ),
    }
    with sqlite3.connect(database) as connection:
        return tuple(
            (name, tuple(connection.execute(sql, parameters)))
            for name, (sql, parameters) in statements.items()
        )


def _successor_fixture(
    tmp_path: Path,
    database_name: str,
    *,
    outcome: TerminalOutcome = TerminalOutcome.CANCELLED,
) -> tuple[
    Path,
    SqliteTaskStore,
    _Executor,
    PersistentTaskCore,
    PersistentTaskRecord,
    PersistentTaskEvent,
    str | None,
]:
    database = tmp_path / database_name
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
    assert created.ok
    dispatch = store.claim_outbox("successor-fixture")
    assert dispatch is not None
    result_text: str | None = None
    artifacts: tuple[TaskResultArtifact, ...] = ()
    if outcome is TerminalOutcome.COMPLETED:
        result_path = tmp_path / f"{database.stem}-result.txt"
        result_path.write_text("immutable result\n", encoding="utf-8")
        result_text = "immutable result"
        artifacts = (
            TaskResultArtifact(
                result_path.name,
                hashlib.sha256(result_path.read_bytes()).hexdigest(),
            ),
        )
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(
            dispatch,
            outcome=outcome,
            result_text=result_text,
            result_artifacts=artifacts,
        ),
    )
    predecessor = store.get_task(dispatch.task_id, _scope())
    terminal_event = store.events(predecessor.task_id, _scope())[-1]
    availability, result, _reason = store.task_result(predecessor.task_id, _scope())
    digest = (
        hashlib.sha256(canonical_json_bytes(result.to_dict())).hexdigest()
        if availability is TaskResultAvailability.AVAILABLE and result is not None
        else None
    )
    return database, store, executor, core, predecessor, terminal_event, digest


def test_v1_schema_migrates_atomically_and_preserves_active_attempt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    result = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert result.ok and result.result is not None
    task_id = str(result.result["task_id"])
    attempt_id = str(result.result["attempt_id"])
    before = store.counts()
    _downgrade_fixture_to_v1(database)

    reopened = SqliteTaskStore(database)

    assert reopened.counts() == before
    assert reopened.get_task(task_id, _scope()).attempt_id == attempt_id
    assert reopened.get_attempt(attempt_id).attempt_number == 1
    assert (
        reopened.get_current_background_task(_scope(), session_id=_scope().session_id)
        is None
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("5",)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(attempts)")}
        assert "attempt_number" in columns
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("lifecycle", ["terminal", "claimed"])
def test_v1_schema_migration_preserves_terminal_or_claimed_state_across_reopen(
    tmp_path: Path, lifecycle: str
) -> None:
    database = tmp_path / f"migration-{lifecycle}.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    item = store.claim_outbox(f"migration-{lifecycle}")
    assert item is not None
    if lifecycle == "terminal":
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{attempt_id}",
            observations=_observations(item, outcome=TerminalOutcome.COMPLETED),
        )
    before_counts = store.counts()
    before_task = store.get_task(task_id, _scope())
    before_attempt = store.get_attempt(attempt_id)
    with sqlite3.connect(database) as connection:
        before_outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE attempt_id=?
            """,
            (attempt_id,),
        ).fetchone()
    _downgrade_fixture_to_v1(database)

    migrated = SqliteTaskStore(database)
    reopened = SqliteTaskStore(database)

    assert migrated.counts() == before_counts
    assert reopened.counts() == before_counts
    assert reopened.get_task(task_id, _scope()) == before_task
    migrated_attempt = reopened.get_attempt(attempt_id)
    assert migrated_attempt == before_attempt
    assert migrated_attempt.attempt_number == 1
    with sqlite3.connect(database) as connection:
        after_outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE attempt_id=?
            """,
            (attempt_id,),
        ).fetchone()
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert after_outbox == before_outbox


@pytest.mark.parametrize(
    "failpoint",
    [
        "migration.v1_to_v2.before_create",
        "migration.v1_to_v2.after_create",
        "migration.v1_to_v2.after_copy",
        "migration.v1_to_v2.after_drop",
        "migration.v1_to_v2.after_rename",
        "migration.v1_to_v2.before_metadata",
    ],
)
def test_v1_schema_migration_failpoints_restore_exact_v1(
    tmp_path: Path, failpoint: str
) -> None:
    database = tmp_path / f"{failpoint}.sqlite"
    SqliteTaskStore(database)
    _downgrade_fixture_to_v1(database)

    def fail(name: str) -> None:
        if name == failpoint:
            raise RuntimeError(name)

    with pytest.raises(RuntimeError, match=failpoint):
        SqliteTaskStore(database, failpoint=fail)

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("1",)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(attempts)")}
        assert "attempt_number" not in columns
        assert "attempts_v2" not in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def test_v3_schema_migrates_create_lineage_without_relabelling_task_truth(
    tmp_path: Path,
) -> None:
    database = tmp_path / "v3-lineage.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        current_background_session_id=_scope().session_id,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    before_task = store.get_task(task_id, _scope())
    before_counts = store.counts()
    _downgrade_fixture_to_v3(database)

    migrated = SqliteTaskStore(database)
    reopened = SqliteTaskStore(database)

    assert migrated.counts() == reopened.counts() == before_counts
    assert reopened.get_task(task_id, _scope()) == before_task
    selection = reopened.get_current_background_task(
        _scope(), session_id=_scope().session_id
    )
    assert selection is not None and selection.task_id == task_id
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("5",)
        assert connection.execute(
            """SELECT create_command_id, predecessor_task_id, revision_number
               FROM tasks WHERE task_id=?""",
            (task_id,),
        ).fetchone() == (invocation.envelope.command_id, None, 1)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    "failpoint",
    [
        "migration.v3_to_v4.before_columns",
        "migration.v3_to_v4.after_columns",
        "migration.v3_to_v4.before_backfill",
        "migration.v3_to_v4.after_backfill",
        "migration.v3_to_v4.after_indexes",
        "migration.v3_to_v4.before_metadata",
    ],
)
def test_v3_schema_migration_failpoints_restore_exact_v3(
    tmp_path: Path, failpoint: str
) -> None:
    database = tmp_path / f"{failpoint}.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    _downgrade_fixture_to_v3(database)
    before = _database_dump(database)

    def fail(name: str) -> None:
        if name == failpoint:
            raise RuntimeError(name)

    with pytest.raises(RuntimeError, match=failpoint):
        SqliteTaskStore(database, failpoint=fail)

    assert _database_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("3",)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        assert "create_command_id" not in columns
        assert "predecessor_task_id" not in columns
        assert "revision_number" not in columns

    assert SqliteTaskStore(database).counts()["tasks"] == 1


def test_v3_corrupt_create_lineage_fails_without_partial_promotion(
    tmp_path: Path,
) -> None:
    database = tmp_path / "v3-corrupt-lineage.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    _downgrade_fixture_to_v3(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE task_events SET causation_id='missing-create' WHERE task_id=?",
            (task_id,),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    ("schema_version", "downgrade"),
    [
        (1, _downgrade_fixture_to_v1),
        (2, _downgrade_fixture_to_v2),
        (3, _downgrade_fixture_to_v3),
    ],
)
@pytest.mark.parametrize(
    "damage",
    [
        "task_state",
        "task_spec",
        "attempt_state",
        "event_head",
        "illegal_transition",
        "nonterminal_outcome",
        "control_event",
        "orphan_control_authority",
        "dispatch_rejection_outbox",
        "lost_reconciliation_outbox",
        "executor_authority",
        "unknown_event",
    ],
)
def test_legacy_semantic_corruption_fails_without_partial_v4_promotion(
    tmp_path: Path,
    schema_version: int,
    downgrade: Callable[[Path], None],
    damage: str,
) -> None:
    database = tmp_path / f"v{schema_version}-corrupt-{damage}.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    core = PersistentTaskCore(store, _Executor())
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    if damage in {
        "control_event",
        "orphan_control_authority",
        "unknown_event",
    }:
        dispatch = store.claim_outbox("complete-control-dispatch")
        assert dispatch is not None
        store.complete_outbox(
            dispatch,
            executor_ref=f"legacy:{dispatch.attempt_id}",
            observations=_observations(dispatch),
        )
        adjustment, adjustment_grant = _adjust(
            task_id,
            "Keep this bounded.",
            command_id=f"command-{damage}",
            request_id=f"request-{damage}",
        )
        adjusted = core.execute(
            adjustment,
            adjustment_grant,
            now=NOW,
        )
        assert adjusted.ok
    elif damage == "dispatch_rejection_outbox":
        dispatch = store.claim_outbox("reject-dispatch")
        assert dispatch is not None
        store.reject_outbox(
            dispatch,
            FormalTaskViolation(
                "EXECUTOR_DISPATCH_UNSUPPORTED",
                "Executor cannot accept this bounded dispatch",
                ErrorCode.UNSUPPORTED,
            ),
        )
    elif damage == "lost_reconciliation_outbox":
        resolved = store.resolve_lost_attempt(
            task_id,
            str(created.result["attempt_id"]),
            "EXECUTOR_ATTEMPT_LOST",
        )
        assert resolved.disposition is TaskMutationDisposition.APPLIED
    elif damage == "executor_authority":
        dispatch = store.claim_outbox("complete-dispatch")
        assert dispatch is not None
        store.complete_outbox(
            dispatch,
            executor_ref=f"legacy:{dispatch.attempt_id}",
            observations=_observations(dispatch),
        )
    downgrade(database)
    with sqlite3.connect(database) as connection:
        if damage == "task_state":
            connection.execute(
                "UPDATE tasks SET state='corrupt-state' WHERE task_id=?",
                (task_id,),
            )
        elif damage == "task_spec":
            connection.execute(
                "UPDATE tasks SET spec_json='{}' WHERE task_id=?",
                (task_id,),
            )
        elif damage == "attempt_state":
            connection.execute(
                "UPDATE attempts SET state='corrupt-state' WHERE task_id=?",
                (task_id,),
            )
        elif damage == "event_head":
            connection.execute(
                "UPDATE tasks SET event_head=event_head + 1 WHERE task_id=?",
                (task_id,),
            )
        elif damage in {"illegal_transition", "nonterminal_outcome"}:
            outcome = "completed" if damage == "nonterminal_outcome" else None
            repeats = 1 if damage == "nonterminal_outcome" else 2
            for seq in range(1, repeats + 1):
                connection.execute(
                    """
                    INSERT INTO task_events(
                        task_id, seq, event_id, attempt_id, scope_json,
                        event_type, state, outcome, producer, source_event_id,
                        causation_id, correlation_id, occurred_at, details_json)
                    SELECT task_id, ?, ?, attempt_id, scope_json,
                           'task.running', 'running', ?, 'task_core', NULL,
                           ?, correlation_id, occurred_at, '{}'
                    FROM task_events WHERE task_id=? AND seq=0
                    """,
                    (
                        seq,
                        f"corrupt-event-{seq}",
                        outcome,
                        f"corrupt-cause-{seq}",
                        task_id,
                    ),
                )
            connection.execute(
                """UPDATE tasks SET state='running', outcome=?, event_head=?
                   WHERE task_id=?""",
                (outcome, repeats, task_id),
            )
        elif damage == "control_event":
            connection.execute(
                """UPDATE task_events SET producer='forged-control'
                   WHERE task_id=? AND event_type='task.adjust_requested'""",
                (task_id,),
            )
        elif damage == "orphan_control_authority":
            connection.execute(
                """UPDATE task_events
                   SET causation_id='missing-adjust-command',
                       details_json='{"command_id":"missing-adjust-command"}'
                   WHERE task_id=? AND event_type='task.adjust_requested'""",
                (task_id,),
            )
        elif damage in {
            "dispatch_rejection_outbox",
            "lost_reconciliation_outbox",
        }:
            connection.execute(
                """UPDATE outbox SET state='pending', last_error=NULL,
                       claimed_by=NULL, claimed_at=NULL, claim_token=NULL
                   WHERE task_id=? AND kind='attempt.dispatch'""",
                (task_id,),
            )
        elif damage == "executor_authority":
            connection.execute(
                "DELETE FROM executor_events WHERE attempt_id=(SELECT attempt_id FROM tasks WHERE task_id=?)",
                (task_id,),
            )
        else:
            connection.execute(
                """UPDATE task_events SET event_type='task.unknown'
                   WHERE task_id=? AND event_type='task.adjust_requested'""",
                (task_id,),
            )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == (str(schema_version),)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        assert "create_command_id" not in columns
        assert "predecessor_task_id" not in columns
        assert "revision_number" not in columns


def test_forged_running_internal_terminal_fails_closed_on_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forged-running-terminal.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task_id = str(created.result["task_id"])
    resolved = store.resolve_lost_attempt(
        task_id,
        str(created.result["attempt_id"]),
        "EXECUTOR_ATTEMPT_LOST",
    )
    assert resolved.disposition is TaskMutationDisposition.APPLIED
    with sqlite3.connect(database) as connection:
        connection.execute(
            """UPDATE task_events
               SET causation_id='forged-reconciliation',
                   details_json='{"reason":"FORGED_RECONCILIATION"}'
               WHERE task_id=? AND event_type IN ('attempt.terminal', 'task.terminal')
                 AND producer='task_core.reconciliation'""",
            (task_id,),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


def test_v4_orphan_control_event_fails_closed_on_restart(tmp_path: Path) -> None:
    database = tmp_path / "v4-orphan-control-event.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    core = PersistentTaskCore(store, _Executor())
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    dispatch = store.claim_outbox("complete-control-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    adjustment, adjustment_grant = _adjust(
        task_id,
        "Keep this bounded.",
        command_id="command-control-authority",
        request_id="request-control-authority",
    )
    assert core.execute(adjustment, adjustment_grant, now=NOW).ok
    with sqlite3.connect(database) as connection:
        connection.execute(
            """UPDATE task_events
               SET causation_id='missing-adjust-command',
                   details_json='{"command_id":"missing-adjust-command"}'
               WHERE task_id=? AND event_type='task.adjust_requested'""",
            (task_id,),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    "damage",
    ["dispatch_rejection_outbox", "lost_reconciliation_outbox", "executor_authority"],
)
def test_v4_forged_authority_fails_closed_on_restart(
    tmp_path: Path, damage: str
) -> None:
    database = tmp_path / f"v4-forged-{damage}.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    if damage == "dispatch_rejection_outbox":
        dispatch = store.claim_outbox("reject-dispatch")
        assert dispatch is not None
        store.reject_outbox(
            dispatch,
            FormalTaskViolation(
                "EXECUTOR_DISPATCH_UNSUPPORTED",
                "Executor cannot accept this bounded dispatch",
                ErrorCode.UNSUPPORTED,
            ),
        )
    elif damage == "lost_reconciliation_outbox":
        resolved = store.resolve_lost_attempt(
            task_id,
            attempt_id,
            "EXECUTOR_ATTEMPT_LOST",
        )
        assert resolved.disposition is TaskMutationDisposition.APPLIED
    else:
        dispatch = store.claim_outbox("complete-dispatch")
        assert dispatch is not None
        store.complete_outbox(
            dispatch,
            executor_ref=f"legacy:{dispatch.attempt_id}",
            observations=_observations(dispatch),
        )
    with sqlite3.connect(database) as connection:
        if damage in {"dispatch_rejection_outbox", "lost_reconciliation_outbox"}:
            connection.execute(
                """UPDATE outbox SET state='pending', last_error=NULL,
                       claimed_by=NULL, claimed_at=NULL, claim_token=NULL
                   WHERE task_id=? AND kind='attempt.dispatch'""",
                (task_id,),
            )
        else:
            connection.execute(
                "DELETE FROM executor_events WHERE attempt_id=?",
                (attempt_id,),
            )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


def test_legacy_v4_cancel_results_reopen_and_replay_without_rewrite(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-v4-cancel-results.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("legacy-cancel-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    first = _cancel(dispatch.task_id)
    admitted = core.execute(first.envelope, first.authorization, now=NOW)
    assert admitted.ok and admitted.result is not None
    repeat_command = replace(
        first.envelope,
        request_id="request-legacy-cancel-repeat",
        command_id="command-legacy-cancel-repeat",
    )
    repeat_grant = replace(
        first.authorization,
        command_id=repeat_command.command_id,
    )
    repeated = core.execute(repeat_command, repeat_grant, now=NOW)
    assert repeated.ok and repeated.result is not None

    with sqlite3.connect(database) as connection:
        for command_id, applied in (
            (first.envelope.command_id, True),
            (repeat_command.command_id, False),
        ):
            row = connection.execute(
                "SELECT result_json FROM commands WHERE command_id=?",
                (command_id,),
            ).fetchone()
            assert row is not None
            payload = json.loads(row[0])
            payload["extensions"] = {}
            payload["result"]["applied"] = applied
            connection.execute(
                "UPDATE commands SET result_json=? WHERE command_id=?",
                (json.dumps(payload, sort_keys=True), command_id),
            )
        connection.commit()
    before = _database_dump(database)

    reopened = SqliteTaskStore(database)
    replay_core = PersistentTaskCore(reopened, _Executor())
    first_replay = replay_core.execute(
        replace(first.envelope, request_id="request-legacy-cancel-first-replay"),
        first.authorization,
        now=NOW,
    )
    repeat_replay = replay_core.execute(
        replace(repeat_command, request_id="request-legacy-cancel-repeat-replay"),
        repeat_grant,
        now=NOW,
    )

    assert first_replay.ok and first_replay.result is not None
    assert first_replay.result["applied"] is True
    assert first_replay.extensions == {}
    assert repeat_replay.ok and repeat_replay.result is not None
    assert repeat_replay.result["applied"] is False
    assert repeat_replay.extensions == {}
    assert _database_dump(database) == before
    with sqlite3.connect(database) as connection:
        legacy_results = tuple(
            connection.execute(
                "SELECT command_id, result_json FROM commands "
                "WHERE command_id IN (?, ?) ORDER BY command_id",
                (first.envelope.command_id, repeat_command.command_id),
            )
        )

    cancel_item = reopened.claim_outbox("legacy-cancel-delivery")

    assert cancel_item is not None
    assert cancel_item.kind is OutboxKind.ATTEMPT_CANCEL
    with sqlite3.connect(database) as connection:
        assert tuple(
            connection.execute(
                "SELECT command_id, result_json FROM commands "
                "WHERE command_id IN (?, ?) ORDER BY command_id",
                (first.envelope.command_id, repeat_command.command_id),
            )
        ) == legacy_results


@pytest.mark.parametrize(
    "legacy_state",
    [
        TaskAdjustmentState.PENDING,
        TaskAdjustmentState.APPLIED,
        TaskAdjustmentState.REJECTED,
    ],
)
def test_legacy_v4_adjustment_results_reopen_and_replay_without_rewrite(
    tmp_path: Path,
    legacy_state: TaskAdjustmentState,
) -> None:
    database = tmp_path / f"legacy-v4-adjust-{legacy_state.value}.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("legacy-adjust-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    command, grant = _adjust(
        dispatch.task_id,
        "Preserve one historical adjustment ledger.",
        command_id=f"command-legacy-adjust-{legacy_state.value}",
        request_id=f"request-legacy-adjust-{legacy_state.value}",
    )
    admitted = core.execute(command, grant, now=NOW)
    assert admitted.ok and admitted.result is not None
    reason = "NOT_APPLICABLE" if legacy_state is TaskAdjustmentState.REJECTED else None
    if legacy_state is not TaskAdjustmentState.PENDING:
        item = store.claim_outbox(f"legacy-adjust-{legacy_state.value}")
        assert item is not None and item.executor_ref is not None
        store.complete_adjustment_outbox(
            item,
            TaskAdjustmentDeliveryResult(
                item.executor_ref,
                item.command_id,
                legacy_state,
                reason,
            ),
            observed_at=NOW,
        )

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["ok"] = True
        payload["error"] = None
        payload["result"] = {
            **admitted.result,
            "adjustment_state": legacy_state.value,
            "reason": reason,
        }
        payload["extensions"] = {}
        connection.execute(
            "UPDATE commands SET result_json=? WHERE command_id=?",
            (json.dumps(payload, sort_keys=True), command.command_id),
        )
        connection.commit()
    before = _database_dump(database)

    reopened = SqliteTaskStore(database)
    replay = PersistentTaskCore(reopened, _Executor()).execute(
        replace(command, request_id=f"request-legacy-{legacy_state.value}-replay"),
        grant,
        now=NOW,
    )

    assert replay.ok and replay.result is not None
    assert replay.result["adjustment_state"] == legacy_state.value
    assert replay.result["reason"] == reason
    assert replay.extensions == {}
    assert _database_dump(database) == before


def test_v4_duplicate_adjustment_disposition_fails_closed_on_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "v4-duplicate-adjustment-disposition.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task_id = str(created.result["task_id"])
    adjustment, adjustment_grant = _adjust(
        task_id,
        "Keep this bounded.",
        command_id="command-duplicate-disposition",
        request_id="request-duplicate-disposition",
    )
    assert core.execute(adjustment, adjustment_grant, now=NOW).ok
    adjustment_item = store.claim_outbox("complete-adjustment")
    assert adjustment_item is not None and adjustment_item.executor_ref is not None
    store.complete_adjustment_outbox(
        adjustment_item,
        TaskAdjustmentDeliveryResult(
            adjustment_item.executor_ref,
            adjustment_item.command_id,
            TaskAdjustmentState.APPLIED,
            None,
        ),
        observed_at=NOW,
    )
    with sqlite3.connect(database) as connection:
        head = connection.execute(
            "SELECT event_head FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO task_events(
                   task_id, seq, event_id, attempt_id, scope_json, event_type,
                   state, outcome, producer, source_event_id, causation_id,
                   correlation_id, occurred_at, details_json)
               SELECT task_id, ?, 'event-duplicate-disposition', attempt_id,
                      scope_json, event_type, state, outcome, producer,
                      source_event_id, causation_id, correlation_id, occurred_at,
                      details_json
               FROM task_events
               WHERE task_id=? AND event_type='task.adjust_applied'""",
            (head + 1, task_id),
        )
        connection.execute(
            "UPDATE tasks SET event_head=? WHERE task_id=?", (head + 1, task_id)
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


@pytest.mark.parametrize("schema_version", [3, 4])
def test_corrupt_task_result_fails_closed_before_promotion_or_reopen(
    tmp_path: Path, schema_version: int
) -> None:
    database = tmp_path / f"v{schema_version}-corrupt-task-result.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    artifact_path = tmp_path / "result.txt"
    artifact_path.write_text("bounded result\n", encoding="utf-8")
    artifact = TaskResultArtifact(
        relative_path="result.txt",
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
    )
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(
            dispatch,
            outcome=TerminalOutcome.COMPLETED,
            result_text="bounded result",
            result_artifacts=(artifact,),
        ),
    )
    if schema_version == 3:
        _downgrade_fixture_to_v3(database)
    elif schema_version == 4:
        _downgrade_fixture_to_v4(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE task_results SET result_text='' ")
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == (str(schema_version),)


@pytest.mark.parametrize(
    ("settlement", "expected_outcome"),
    [
        ("dispatch_rejection", TerminalOutcome.FAILED),
        ("lost_reconciliation", TerminalOutcome.INTERRUPTED),
    ],
)
def test_store_owned_accepted_attempt_terminal_settlement_reopens(
    tmp_path: Path,
    settlement: str,
    expected_outcome: TerminalOutcome,
) -> None:
    database = tmp_path / f"accepted-terminal-{settlement}.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])

    if settlement == "dispatch_rejection":
        dispatch = store.claim_outbox("reject-dispatch")
        assert dispatch is not None
        store.reject_outbox(
            dispatch,
            FormalTaskViolation(
                "EXECUTOR_DISPATCH_UNSUPPORTED",
                "Executor cannot accept this bounded dispatch",
                ErrorCode.UNSUPPORTED,
            ),
        )
    else:
        resolved = store.resolve_lost_attempt(
            task_id,
            attempt_id,
            "EXECUTOR_ATTEMPT_LOST",
        )
        assert resolved.disposition is TaskMutationDisposition.APPLIED

    reopened = SqliteTaskStore(database)

    task = reopened.get_task(task_id, _scope())
    attempt = reopened.get_attempt(attempt_id)
    assert task.state is FormalTaskState.TERMINAL
    assert task.outcome is expected_outcome
    assert attempt.state is FormalAttemptState.TERMINAL
    assert attempt.outcome is expected_outcome


def test_lost_reconciliation_fences_a_claimed_cancel_before_lease_reaping(
    tmp_path: Path,
) -> None:
    database = tmp_path / "claimed-cancel-lost.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task_id = str(created.result["task_id"])
    cancel = _cancel(task_id)
    assert core.execute(cancel.envelope, cancel.authorization, now=NOW).ok
    claimed_cancel = store.claim_outbox("claimed-cancel")
    assert claimed_cancel is not None
    assert claimed_cancel.kind is OutboxKind.ATTEMPT_CANCEL

    resolved = store.resolve_lost_attempt(
        task_id,
        str(created.result["attempt_id"]),
        "EXECUTOR_ATTEMPT_LOST",
    )

    assert resolved.disposition is TaskMutationDisposition.APPLIED
    assert store.reset_expired_outbox_claims(claimed_before="9999-01-01T00:00:00Z") == 0
    assert store.claim_outbox("must-not-redeliver") is None
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT state, claimed_by, claimed_at, claim_token, last_error "
            "FROM outbox WHERE outbox_id=?",
            (claimed_cancel.outbox_id,),
        ).fetchone() == (
            OutboxState.SUPPRESSED.value,
            None,
            None,
            None,
            "EXECUTOR_ATTEMPT_LOST",
        )
    reopened = SqliteTaskStore(database)
    assert reopened.get_task(task_id, _scope()).outcome is TerminalOutcome.INTERRUPTED


@pytest.mark.parametrize(
    ("task_state", "operation", "expected_kind"),
    [
        (FormalTaskState.DECISION_REQUIRED, "cancel", OutboxKind.ATTEMPT_CANCEL),
    ],
)
def test_control_outbox_accepts_nonterminal_task_projection_over_running_attempt(
    tmp_path: Path,
    task_state: FormalTaskState,
    operation: str,
    expected_kind: OutboxKind,
) -> None:
    database = tmp_path / f"control-{task_state.value}.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task_id = str(created.result["task_id"])
    with sqlite3.connect(database) as connection:
        head = connection.execute(
            "SELECT event_head FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO task_events(
                   task_id, seq, event_id, attempt_id, scope_json, event_type,
                   state, outcome, producer, source_event_id, causation_id,
                   correlation_id, occurred_at, details_json)
               SELECT task_id, ?, ?, attempt_id, scope_json, ?, ?, NULL,
                      'task_core', NULL, ?, correlation_id, ?, '{}'
               FROM tasks WHERE task_id=?""",
            (
                head + 1,
                f"event-{task_state.value}",
                f"task.{task_state.value}",
                task_state.value,
                f"policy-{task_state.value}",
                NOW,
                task_id,
            ),
        )
        connection.execute(
            "UPDATE tasks SET state=?, event_head=? WHERE task_id=?",
            (task_state.value, head + 1, task_id),
        )
        connection.commit()

    if operation == "adjust":
        command, grant = _adjust(
            task_id,
            "Keep this bounded.",
            command_id="command-blocked-adjust",
            request_id="request-blocked-adjust",
        )
    else:
        cancellation = _cancel(task_id)
        command, grant = cancellation.envelope, cancellation.authorization
    assert core.execute(command, grant, now=NOW).ok

    item = store.claim_outbox(f"claim-{operation}")

    assert item is not None and item.kind is expected_kind
    assert store.release_outbox(item, "TEST_RELEASE") is True
    assert SqliteTaskStore(database).get_task(task_id, _scope()).state is task_state


@pytest.mark.parametrize("schema_version", [3, 4])
@pytest.mark.parametrize("damage", ["spec", "executor_ref"])
def test_corrupt_control_outbox_binding_fails_before_promotion_or_reopen(
    tmp_path: Path, schema_version: int, damage: str
) -> None:
    database = tmp_path / f"v{schema_version}-corrupt-control-{damage}.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task_id = str(created.result["task_id"])
    adjustment, adjustment_grant = _adjust(
        task_id,
        "Keep this bounded.",
        command_id=f"command-control-{damage}",
        request_id=f"request-control-{damage}",
    )
    adjusted = core.execute(adjustment, adjustment_grant, now=NOW)
    assert adjusted.ok and adjusted.result is not None
    outbox_id = str(adjusted.result["outbox_id"])
    if schema_version == 3:
        _downgrade_fixture_to_v3(database)
    elif schema_version == 4:
        _downgrade_fixture_to_v4(database)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM outbox WHERE outbox_id=?", (outbox_id,)
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        if damage == "spec":
            payload["spec"]["instruction"] = "Forged instruction."
        else:
            payload["executor_ref"] = "legacy:foreign-attempt"
        connection.execute(
            "UPDATE outbox SET payload_json=? WHERE outbox_id=?",
            (json.dumps(payload, sort_keys=True), outbox_id),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == (str(schema_version),)


def test_repeat_cancel_without_a_second_event_or_outbox_reopens(
    tmp_path: Path,
) -> None:
    database = tmp_path / "repeat-cancel.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task_id = str(created.result["task_id"])
    first = _cancel(task_id)
    assert core.execute(first.envelope, first.authorization, now=NOW).ok
    second_command_id = "command-cancel-repeat"
    second = replace(
        first.envelope,
        request_id="request-cancel-repeat",
        command_id=second_command_id,
    )
    second_grant = replace(first.authorization, command_id=second_command_id)

    repeated = core.execute(second, second_grant, now=NOW)

    assert repeated.ok and repeated.result is not None
    assert repeated.result["applied"] is False
    assert SqliteTaskStore(database).get_task(task_id, _scope()).cancel_requested


def test_cancel_request_is_accepted_until_authoritative_cancelled_settlement(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cancel-settlement.sqlite"
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
    dispatch = store.claim_outbox("cancel-running")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    cancellation = _cancel(dispatch.task_id)

    accepted = core.execute(
        cancellation.envelope, cancellation.authorization, now=NOW
    )

    assert accepted.ok and accepted.result is not None
    assert accepted.result["applied"] is False
    cancel_events = [
        event
        for event in store.events(dispatch.task_id, _scope())
        if event.event_type == "task.cancel_requested"
    ]
    assert len(cancel_events) == 1
    assert accepted.extensions["live_voice.command"] == {
        "disposition": "accepted",
        "admission_event_id": cancel_events[0].event_id,
        "settlement_event_id": None,
    }
    cancel_item = store.claim_outbox("cancel-delivery")
    assert cancel_item is not None and cancel_item.kind is OutboxKind.ATTEMPT_CANCEL
    store.apply_observations(
        _observations(cancel_item, outcome=TerminalOutcome.CANCELLED)
    )
    final = core.execute(
        replace(cancellation.envelope, request_id="request-cancel-final-replay"),
        cancellation.authorization,
        now=NOW,
    )
    assert final.ok and final.result is not None
    assert final.result["applied"] is True
    assert final.result["state"] == FormalTaskState.TERMINAL.value
    terminal_event = store.events(dispatch.task_id, _scope())[-1]
    assert terminal_event.event_type == "task.terminal"
    assert terminal_event.outcome == TerminalOutcome.CANCELLED.value
    assert final.extensions["live_voice.command"] == {
        "disposition": "applied",
        "admission_event_id": cancel_events[0].event_id,
        "settlement_event_id": terminal_event.event_id,
    }
    assert SqliteTaskStore(database).get_task(
        dispatch.task_id, _scope()
    ).outcome is TerminalOutcome.CANCELLED
    assert executor.cancels == []


def test_negative_cancel_ledger_cannot_block_another_task_cancel_settlement(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cancel-negative-coexistence.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    first_create = _create(tmp_path)
    first_created = core.execute(
        first_create.envelope,
        first_create.authorization,
        context=first_create.context,
        now=NOW,
    )
    assert first_created.ok and first_created.result is not None
    first_dispatch = store.claim_outbox("first-terminal")
    assert first_dispatch is not None
    store.complete_outbox(
        first_dispatch,
        executor_ref=f"legacy:{first_dispatch.attempt_id}",
        observations=_observations(
            first_dispatch, outcome=TerminalOutcome.COMPLETED
        ),
    )
    first_cancel = _cancel(first_dispatch.task_id)
    first_conflict = core.execute(
        first_cancel.envelope, first_cancel.authorization, now=NOW
    )
    assert not first_conflict.ok and first_conflict.error is not None
    assert first_conflict.error.reason == "TASK_ALREADY_TERMINAL"

    second_create = _create(tmp_path, identity_suffix="-cancel-second")
    second_created = core.execute(
        second_create.envelope,
        second_create.authorization,
        context=second_create.context,
        now=NOW,
    )
    assert second_created.ok and second_created.result is not None
    second_dispatch = store.claim_outbox("second-running")
    assert second_dispatch is not None
    store.complete_outbox(
        second_dispatch,
        executor_ref=f"legacy:{second_dispatch.attempt_id}",
        observations=_observations(second_dispatch),
    )
    second_cancel, second_grant = _wave2_command(
        second_dispatch.task_id,
        "task.cancel",
        {},
        command_id="command-cancel-second-task",
    )
    accepted = core.execute(second_cancel, second_grant, now=NOW)
    assert accepted.ok
    cancel_item = store.claim_outbox("second-cancel")
    assert cancel_item is not None and cancel_item.kind is OutboxKind.ATTEMPT_CANCEL

    store.apply_observations(
        _observations(cancel_item, outcome=TerminalOutcome.CANCELLED)
    )

    assert store.get_task(
        second_dispatch.task_id, _scope()
    ).outcome is TerminalOutcome.CANCELLED
    first_replay = core.execute(
        replace(first_cancel.envelope, request_id="request-first-cancel-replay"),
        first_cancel.authorization,
        now=NOW,
    )
    assert first_replay.error == first_conflict.error


@pytest.mark.parametrize(
    "outcome", [TerminalOutcome.COMPLETED, TerminalOutcome.FAILED]
)
def test_cancel_terminal_race_never_claims_false_applied(
    tmp_path: Path, outcome: TerminalOutcome
) -> None:
    database = tmp_path / f"cancel-race-{outcome.value}.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    dispatch = store.claim_outbox("cancel-race-running")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    cancellation = _cancel(dispatch.task_id)
    requested = core.execute(
        cancellation.envelope, cancellation.authorization, now=NOW
    )
    assert requested.ok and requested.result is not None
    assert requested.result["applied"] is False
    cancel_item = store.claim_outbox("cancel-race-delivery")
    assert cancel_item is not None
    store.apply_observations(_observations(cancel_item, outcome=outcome))

    replay = core.execute(
        replace(cancellation.envelope, request_id="request-cancel-race-replay"),
        cancellation.authorization,
        now=NOW,
    )

    assert replay.ok and replay.result is not None
    assert replay.result["applied"] is False
    assert replay.extensions["live_voice.command"]["disposition"] == "accepted"
    next_cancel = replace(
        cancellation.envelope,
        request_id="request-cancel-after-terminal",
        command_id="command-cancel-after-terminal",
    )
    next_grant = replace(
        cancellation.authorization, command_id="command-cancel-after-terminal"
    )
    before = _task_authority_dump(database)
    conflict = core.execute(next_cancel, next_grant, now=NOW)
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "TASK_ALREADY_TERMINAL"
    assert conflict.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (next_cancel.command_id,),
        ).fetchone() == (1,)
    reopened = SqliteTaskStore(database)
    durable_replay = PersistentTaskCore(reopened, _Executor()).execute(
        replace(next_cancel, request_id="request-cancel-terminal-replay"),
        next_grant,
        now=NOW,
    )
    assert durable_replay.error == conflict.error
    assert durable_replay.extensions == conflict.extensions
    assert _task_authority_dump(database) == before


def test_release_after_terminal_suppresses_claim_and_completed_blocks_new_retry(
    tmp_path: Path,
) -> None:
    database = tmp_path / "release-after-terminal.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    cancellation = _cancel(task_id)
    assert core.execute(cancellation.envelope, cancellation.authorization, now=NOW).ok
    claimed_cancel = store.claim_outbox("claimed-cancel")
    assert claimed_cancel is not None
    assert claimed_cancel.kind is OutboxKind.ATTEMPT_CANCEL
    store.apply_observations(
        _observations(claimed_cancel, outcome=TerminalOutcome.COMPLETED)
    )

    assert store.release_outbox(claimed_cancel, "LATE_DELIVERY_FAILURE") is True
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT state, last_error FROM outbox WHERE outbox_id=?",
            (claimed_cancel.outbox_id,),
        ).fetchone() == (
            OutboxState.SUPPRESSED.value,
            "TASK_TERMINAL_BEFORE_DELIVERY",
        )
    reopened = SqliteTaskStore(database)
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.COMPLETED, 2)
    before = _task_authority_dump(database)
    retry_executor = _Executor()

    retried = PersistentTaskCore(reopened, retry_executor).execute(
        retry,
        grant,
        context=_context(tmp_path),
        now=NOW,
    )

    assert not retried.ok and retried.error is not None
    assert retried.error.reason == "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"
    assert _task_authority_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (retry.command_id,),
        ).fetchone() == (1,)
    assert retry_executor.retry_readiness_calls == []


@pytest.mark.parametrize("schema_version", [3, 4])
def test_corrupt_repeat_cancel_state_fails_before_promotion_or_reopen(
    tmp_path: Path, schema_version: int
) -> None:
    database = tmp_path / f"v{schema_version}-corrupt-repeat-cancel.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("complete-dispatch")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task_id = str(created.result["task_id"])
    first = _cancel(task_id)
    assert core.execute(first.envelope, first.authorization, now=NOW).ok
    repeat_command_id = "command-cancel-repeat-corrupt"
    repeated = core.execute(
        replace(
            first.envelope,
            request_id="request-cancel-repeat-corrupt",
            command_id=repeat_command_id,
        ),
        replace(first.authorization, command_id=repeat_command_id),
        now=NOW,
    )
    assert repeated.ok and repeated.result is not None
    if schema_version == 3:
        _downgrade_fixture_to_v3(database)
    elif schema_version == 4:
        _downgrade_fixture_to_v4(database)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (repeat_command_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["result"]["state"] = "corrupt-state"
        connection.execute(
            "UPDATE commands SET result_json=? WHERE command_id=?",
            (json.dumps(payload), repeat_command_id),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == (str(schema_version),)


def test_v4_repeat_cancel_missing_applied_flag_fails_closed_on_reopen(
    tmp_path: Path,
) -> None:
    database = tmp_path / "v4-repeat-cancel-missing-applied.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("repeat-corrupt-running")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    first = _cancel(dispatch.task_id)
    assert core.execute(first.envelope, first.authorization, now=NOW).ok
    repeated, repeated_grant = _wave2_command(
        dispatch.task_id,
        "task.cancel",
        {},
        command_id="command-repeat-missing-applied",
    )
    assert core.execute(repeated, repeated_grant, now=NOW).ok
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (repeated.command_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        del payload["result"]["applied"]
        connection.execute(
            "UPDATE commands SET result_json=? WHERE command_id=?",
            (json.dumps(payload, sort_keys=True), repeated.command_id),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    "damage",
    ["accepted_state", "create_command", "revision_lineage"],
)
def test_v4_corrupt_revision_or_create_lineage_fails_closed_on_restart(
    tmp_path: Path,
    damage: str,
) -> None:
    database = tmp_path / f"v4-corrupt-{damage}.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    with sqlite3.connect(database) as connection:
        if damage == "accepted_state":
            connection.execute(
                "UPDATE task_events SET state='running' WHERE task_id=? AND seq=0",
                (task_id,),
            )
        elif damage == "create_command":
            connection.execute(
                "UPDATE tasks SET create_command_id='missing-create' WHERE task_id=?",
                (task_id,),
            )
        else:
            connection.execute(
                "UPDATE tasks SET revision_number=2 WHERE task_id=?",
                (task_id,),
            )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert _database_dump(database) == before


def test_fresh_schema_bootstrap_failure_leaves_no_partial_ddl(tmp_path: Path) -> None:
    database = tmp_path / "bootstrap-fail.sqlite"

    def fail(name: str) -> None:
        if name == "initialize.bootstrap.before_metadata":
            raise RuntimeError(name)

    with pytest.raises(RuntimeError, match="initialize.bootstrap.before_metadata"):
        SqliteTaskStore(database, failpoint=fail)

    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            == []
        )
    reopened = SqliteTaskStore(database)
    assert reopened.counts() == {
        "commands": 0,
        "tasks": 0,
        "attempts": 0,
        "task_events": 0,
        "executor_events": 0,
        "outbox": 0,
    }


def test_unknown_schema_is_rejected_without_ddl(tmp_path: Path) -> None:
    database = tmp_path / "unknown.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', '99')"
        )
        connection.execute("CREATE TABLE sentinel(value TEXT)")
        connection.execute("INSERT INTO sentinel(value) VALUES('unchanged')")
        connection.commit()
    before = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM sentinel").fetchall() == [
            ("unchanged",)
        ]
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        } == {"metadata", "sentinel"}


def test_initialize_rollback_failure_preserves_stable_schema_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "rollback-failure.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', '2')"
        )
        connection.commit()
    before = database.read_bytes()
    real_connect = sqlite3.connect

    class RollbackFailingConnection(sqlite3.Connection):
        def rollback(self) -> None:
            raise sqlite3.OperationalError("injected rollback failure")

    def connect_with_rollback_failure(*args: object, **kwargs: object) -> object:
        kwargs["factory"] = RollbackFailingConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect_with_rollback_failure)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert rejected.value.code is ErrorCode.UNSUPPORTED
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    "damage",
    [
        "metadata_only",
        "missing_table",
        "missing_attempt_number",
        "fake_owned_table",
        "missing_required_index",
        "missing_attempt_bound",
    ],
)
def test_supported_schema_versions_require_complete_authoritative_shape(
    tmp_path: Path, damage: str
) -> None:
    database = tmp_path / f"schema-{damage}.sqlite"
    if damage == "metadata_only":
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', '2')"
            )
            connection.commit()
    else:
        SqliteTaskStore(database)
        if damage == "missing_attempt_number":
            _downgrade_fixture_to_v1(database)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE metadata SET value='2' WHERE key='schema_version'"
                )
                connection.commit()
        else:
            with sqlite3.connect(database) as connection:
                connection.execute("PRAGMA foreign_keys=OFF")
                if damage == "missing_table":
                    connection.execute("DROP TABLE commands")
                elif damage == "fake_owned_table":
                    connection.execute("DROP TABLE outbox")
                    connection.execute("CREATE TABLE outbox(fake TEXT)")
                elif damage == "missing_required_index":
                    connection.execute("DROP INDEX idx_tasks_scope")
                else:
                    connection.execute(
                        """CREATE TABLE attempts_without_bound (
                            attempt_id TEXT PRIMARY KEY,
                            task_id TEXT NOT NULL REFERENCES tasks(task_id)
                                ON DELETE CASCADE,
                            attempt_number INTEGER NOT NULL,
                            executor_id TEXT NOT NULL, executor_ref TEXT,
                            state TEXT NOT NULL, outcome TEXT,
                            source_seq INTEGER NOT NULL DEFAULT -1,
                            updated_at TEXT NOT NULL,
                            UNIQUE(task_id, attempt_number))"""
                    )
                    connection.execute("DROP TABLE attempts")
                    connection.execute(
                        "ALTER TABLE attempts_without_bound RENAME TO attempts"
                    )
                connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert _database_dump(database) == before


def test_fresh_task_schema_coexists_with_unrelated_component_tables(
    tmp_path: Path,
) -> None:
    database = tmp_path / "shared-components.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE p3_confirmations(confirmation_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO p3_confirmations(confirmation_id) VALUES('confirmation-1')"
        )
        connection.commit()

    store = SqliteTaskStore(database)

    assert store.counts() == {
        "commands": 0,
        "tasks": 0,
        "attempts": 0,
        "task_events": 0,
        "executor_events": 0,
        "outbox": 0,
    }
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT confirmation_id FROM p3_confirmations"
        ).fetchall() == [("confirmation-1",)]
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("5",)


def test_concurrent_initializers_converge_on_schema_v5(tmp_path: Path) -> None:
    database = tmp_path / "concurrent.sqlite"

    with ThreadPoolExecutor(max_workers=2) as pool:
        stores = tuple(pool.map(lambda _index: SqliteTaskStore(database), range(2)))

    assert all(store.counts()["attempts"] == 0 for store in stores)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("5",)


def test_current_background_selection_allows_concurrent_tasks_and_replays_exactly(
    tmp_path: Path,
) -> None:
    database = tmp_path / "current-race.sqlite"
    invocations = (
        _create(tmp_path, identity_suffix="-a"),
        _create(tmp_path, identity_suffix="-b"),
    )

    def submit(index: int):
        invocation = invocations[index]
        return PersistentTaskCore(SqliteTaskStore(database), _Executor()).execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
            current_background_session_id=_scope().session_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(submit, range(2)))

    assert all(result.ok and result.result is not None for result in results)
    task_ids = {str(result.result["task_id"]) for result in results if result.result}
    assert len(task_ids) == 2
    store = SqliteTaskStore(database)
    assert store.counts() == {
        "commands": 2,
        "tasks": 2,
        "attempts": 2,
        "task_events": 2,
        "executor_events": 0,
        "outbox": 2,
    }
    current = store.get_current_background_task(
        _scope(), session_id=_scope().session_id
    )
    assert current is not None
    assert current.task_id in task_ids

    assert submit(0) == results[0]
    assert submit(1) == results[1]
    assert store.counts()["tasks"] == 2


@pytest.mark.asyncio
async def test_multi_task_pages_restart_and_selection_hint_never_redirects(
    tmp_path: Path,
) -> None:
    database = tmp_path / "multi-task-pages.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    task_ids: list[str] = []
    for suffix in ("-a", "-b", "-c"):
        invocation = _create(tmp_path, identity_suffix=suffix)
        created = core.execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
            current_background_session_id=_scope().session_id,
        )
        assert created.ok and created.result is not None
        task_ids.append(str(created.result["task_id"]))

    selection = store.get_current_background_task(
        _scope(), session_id=_scope().session_id
    )
    assert selection is not None and selection.task_id == task_ids[-1]
    for index in range(3):
        assert await core.drain_outbox_once(worker_id=f"dispatch-{index}") is True
    assert await core.drain_outbox_once(worker_id="dispatch-empty") is False

    first_task = task_ids[0]
    first_head = store.get_task(first_task, _scope()).event_head
    other_heads = {
        task_id: store.get_task(task_id, _scope()).event_head
        for task_id in task_ids[1:]
    }
    adjustment, grant = _adjust(
        first_task,
        "Keep this exact Task independently addressable.",
        command_id="command-adjust-noncurrent",
        request_id="request-adjust-noncurrent",
    )
    adjusted = core.execute(
        adjustment,
        grant,
        now=NOW,
    )
    assert adjusted.ok and adjusted.result is not None
    assert store.get_task(first_task, _scope()).event_head == first_head + 1
    assert {
        task_id: store.get_task(task_id, _scope()).event_head
        for task_id in task_ids[1:]
    } == other_heads
    selection = store.get_current_background_task(
        _scope(), session_id=_scope().session_id
    )
    assert selection is not None and selection.task_id == task_ids[-1]

    before_queries = store.counts()
    expected_order = [task.task_id for task in store.list_tasks(_scope())]
    observed_order: list[str] = []
    cursor: str | None = None
    while True:
        invocation = _list_tasks(cursor=cursor, limit=1)
        page = core.query(
            invocation.envelope,
            invocation.authorization,
            now=NOW,
        )
        assert page.ok and page.result is not None
        assert page.result["cursor"] == cursor
        observed_order.extend(str(task["task_id"]) for task in page.result["tasks"])
        if not page.result["has_more"]:
            assert page.result["next_cursor"] is None
            break
        cursor = str(page.result["next_cursor"])

    assert observed_order == expected_order
    reopened_core = PersistentTaskCore(SqliteTaskStore(database), executor)
    event_page = _events(first_task, -1, limit=2)
    first_events = reopened_core.query(
        event_page.envelope,
        event_page.authorization,
        now=NOW,
    )
    assert first_events.ok and first_events.result is not None
    assert first_events.result["has_more"] is True
    assert first_events.result["truncated"] is True
    assert first_events.result["cursor_replay_supported"] is True
    event_cursor = int(first_events.result["next_after_seq"])

    reopened_core = PersistentTaskCore(SqliteTaskStore(database), executor)
    next_page = _events(first_task, event_cursor, limit=500)
    remaining_events = reopened_core.query(
        next_page.envelope,
        next_page.authorization,
        now=NOW,
    )
    assert remaining_events.ok and remaining_events.result is not None
    all_event_sequences = [
        int(event["seq"]) for event in first_events.result["events"]
    ] + [int(event["seq"]) for event in remaining_events.result["events"]]
    assert all_event_sequences == list(
        range(store.get_task(first_task, _scope()).event_head + 1)
    )
    assert remaining_events.result["has_more"] is False
    assert remaining_events.result["next_after_seq"] is None

    stale_cursor = _list_tasks(cursor="task-does-not-exist", limit=1)
    rejected = reopened_core.query(
        stale_cursor.envelope,
        stale_cursor.authorization,
        now=NOW,
    )
    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_NOT_FOUND"

    future_event_cursor = _events(
        first_task,
        store.get_task(first_task, _scope()).event_head + 1,
        limit=1,
    )
    rejected = reopened_core.query(
        future_event_cursor.envelope,
        future_event_cursor.authorization,
        now=NOW,
    )
    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_EVENT_CURSOR_STALE"
    assert store.counts() == before_queries


def test_store_rejects_illegal_task_transition_before_any_write(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "illegal-task-transition.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        current_background_session_id=_scope().session_id,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    before_counts = store.counts()
    before_task = store.get_task(task_id, _scope())
    assert before_task is not None

    with pytest.raises(FormalTaskViolation) as rejected:
        with store._transaction() as connection:
            task = connection.execute(
                "SELECT * FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            assert task is not None
            store._append_event(
                connection,
                task,
                event_type="task.running",
                state=FormalTaskState.ACCEPTED.value,
                outcome=None,
                producer="task_core",
                source_event_id="source-illegal-repeat",
                causation_id="source-illegal-repeat",
                occurred_at=NOW,
                details={},
                update_task=True,
            )

    assert rejected.value.reason == "INVALID_LIFECYCLE_TRANSITION"
    assert store.counts() == before_counts
    assert store.get_task(task_id, _scope()) == before_task


def test_addressed_result_reads_noncurrent_terminal_task_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "addressed-result.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    first_create = _create(tmp_path, identity_suffix="-result-a")
    first_created = core.execute(
        first_create.envelope,
        first_create.authorization,
        context=first_create.context,
        now=NOW,
        current_background_session_id=_scope().session_id,
    )
    assert first_created.ok and first_created.result is not None
    first_task = str(first_created.result["task_id"])
    item = store.claim_outbox("terminal-result")
    assert item is not None and item.task_id == first_task
    artifact_path = tmp_path / "canonical-result.txt"
    artifact_path.write_text("Bounded canonical result.\n", encoding="utf-8")
    artifact = TaskResultArtifact(
        relative_path=artifact_path.name,
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
    )
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(
            item,
            outcome=TerminalOutcome.COMPLETED,
            result_text="Bounded canonical result.",
            result_artifacts=(artifact,),
        ),
    )

    second_create = _create(tmp_path, identity_suffix="-result-b")
    second_created = core.execute(
        second_create.envelope,
        second_create.authorization,
        context=second_create.context,
        now=NOW,
        current_background_session_id=_scope().session_id,
    )
    assert second_created.ok and second_created.result is not None
    second_task = str(second_created.result["task_id"])
    selection = store.get_current_background_task(
        _scope(), session_id=_scope().session_id
    )
    assert selection is not None and selection.task_id == second_task

    before_queries = store.counts()
    reopened = PersistentTaskCore(SqliteTaskStore(database), _Executor())
    result_query = _result(first_task)
    available = reopened.query(
        result_query.envelope,
        result_query.authorization,
        now=NOW,
    )
    assert available.ok and available.result is not None
    assert available.result["task_id"] == first_task
    assert available.result["availability"] == "available"
    assert available.result["reason"] == "TASK_RESULT_AVAILABLE"
    assert available.result["task_result"]["result_text"] == "Bounded canonical result."

    foreign_scope = ScopeRef(
        "user-2", "project-2", "session-2", Assurance.AUTHENTICATED
    )
    foreign_payload = result_query.envelope.to_dict()
    foreign_payload["request_id"] = "request-result-foreign"
    foreign_payload["scope"] = foreign_scope.to_dict()
    foreign_payload["correlation_id"] = "correlation-foreign"
    foreign_query = QueryEnvelope.from_dict(foreign_payload)
    foreign_grant = TaskAuthorizationGrant(
        principal_id="user-2",
        scope=foreign_scope,
        operation="task.result",
        command_id=None,
        target_task_id=first_task,
        allowed_capabilities=frozenset({"task.result"}),
        confirmation_id=None,
        confirmed=False,
        expires_at=EXPIRY,
    )
    denied = reopened.query(foreign_query, foreign_grant, now=NOW)
    assert not denied.ok and denied.error is not None
    assert denied.error.reason == "TASK_NOT_FOUND"
    assert first_task not in denied.error.message
    assert store.counts() == before_queries


def test_predispatch_update_atomically_rewrites_spec_and_dispatch_on_v4(
    tmp_path: Path,
) -> None:
    database = tmp_path / "update.sqlite"
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
    attempt_id = str(created.result["attempt_id"])
    command, grant = _wave2_command(
        task_id,
        "task.update",
        {
            "attempt_id": attempt_id,
            "expected_event_head": 0,
            "instruction": "Apply the bounded revised goal.",
            "constraints": ["Keep tests green.", "Do not use the network."],
        },
        command_id="command-update",
    )

    updated = core.execute(command, grant, now=NOW)

    assert updated.ok and updated.result is not None
    assert updated.result == {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "state": FormalTaskState.ACCEPTED.value,
        "applied": True,
        "outbox_id": created.result["outbox_id"],
    }
    task = store.get_task(task_id, _scope())
    attempt = store.get_attempt(attempt_id)
    assert task.state is FormalTaskState.ACCEPTED
    assert attempt.state is FormalAttemptState.ACCEPTED
    assert task.spec.instruction == "Apply the bounded revised goal."
    assert task.spec.constraints == (
        "Keep tests green.",
        "Do not use the network.",
    )
    events = store.events(task_id, _scope(), after_seq=-1)
    assert [event.event_type for event in events] == [
        "task.accepted",
        "task.update_requested",
        "task.update_applied",
    ]
    assert all("revised goal" not in json.dumps(event.to_dict()) for event in events)
    assert updated.extensions["live_voice.command"] == {
        "disposition": "applied",
        "admission_event_id": events[1].event_id,
        "settlement_event_id": events[2].event_id,
    }
    dispatch = store.claim_outbox("updated-dispatch")
    assert dispatch is not None
    assert dispatch.outbox_id == created.result["outbox_id"]
    assert dispatch.spec == task.spec
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("5",)
    reopened = SqliteTaskStore(database)
    assert reopened.get_task(task_id, _scope()).spec == task.spec


def test_predispatch_update_after_retry_reopens_with_exact_mutable_spec(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, retry_grant = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.CANCELLED,
        2,
        command_id="command-update-after-retry",
    )
    retried = core.execute(
        retry,
        retry_grant,
        context=replace(_context(tmp_path), revision_value="retry-revision"),
        now=NOW,
    )
    assert retried.ok and retried.result is not None
    task = store.get_task(task_id, _scope())
    attempt_b = str(retried.result["attempt_id"])
    command, grant = _wave2_command(
        task_id,
        "task.update",
        {
            "attempt_id": attempt_b,
            "expected_event_head": task.event_head,
            "instruction": "Update the accepted retry before dispatch.",
            "constraints": ["Preserve the cancelled predecessor."],
        },
        command_id="command-update-retried-attempt",
    )

    updated = core.execute(command, grant, now=NOW)

    assert updated.ok and updated.result is not None
    assert executor.dispatches == []
    reopened = SqliteTaskStore(store.database_path)
    reopened_task = reopened.get_task(task_id, _scope())
    assert reopened_task.attempt_id == attempt_b
    assert reopened_task.spec.instruction == command.payload["instruction"]
    assert reopened_task.spec.constraints == (
        "Preserve the cancelled predecessor.",
    )
    dispatch = reopened.claim_outbox("updated-retry-dispatch")
    assert dispatch is not None
    assert dispatch.attempt_id == attempt_b
    assert dispatch.spec == reopened_task.spec


def test_predispatch_update_replays_but_changed_fingerprint_is_zero_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "update-replay.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    command, grant = _wave2_command(
        task_id,
        "task.update",
        {
            "attempt_id": attempt_id,
            "expected_event_head": 0,
            "instruction": "Revised once.",
            "constraints": None,
        },
        command_id="command-update-replay",
    )
    first = core.execute(command, grant, now=NOW)
    assert first.ok
    replay = core.execute(
        replace(command, request_id="request-update-replay-2"), grant, now=NOW
    )
    assert replay.ok and replay.request_id == "request-update-replay-2"
    assert replay.result == first.result
    assert replay.extensions == first.extensions
    before_conflict = _database_dump(database)
    changed = CommandEnvelope.from_dict(
        {
            **command.to_dict(),
            "request_id": "request-update-changed",
            "payload": {
                **command.payload,
                "instruction": "Different bytes.",
            },
        }
    )

    conflict = core.execute(changed, grant, now=NOW)

    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "IDEMPOTENCY_CONFLICT"
    assert _database_dump(database) == before_conflict


def test_update_verifier_ignores_same_command_id_outbox_in_another_scope(
    tmp_path: Path,
) -> None:
    database = tmp_path / "update-cross-scope-command.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    shared_command_id = "command-update-cross-scope"
    update, update_grant = _wave2_command(
        task_id,
        "task.update",
        {
            "attempt_id": attempt_id,
            "expected_event_head": 0,
            "instruction": "Scope-local revised instruction.",
            "constraints": None,
        },
        command_id=shared_command_id,
    )
    applied = core.execute(update, update_grant, now=NOW)
    assert applied.ok

    foreign_scope = ScopeRef(
        "user-2", "project-2", "session-2", Assurance.AUTHENTICATED
    )
    foreign_base = _create(tmp_path, identity_suffix="-cross-scope")
    foreign_raw = foreign_base.envelope.to_dict()
    foreign_raw.update(
        {
            "request_id": "request-create-cross-scope",
            "command_id": shared_command_id,
            "scope": foreign_scope.to_dict(),
            "correlation_id": "correlation-cross-scope",
            "target_ref": {
                "kind": "task",
                "id": f"create:{shared_command_id}",
            },
        }
    )
    foreign_command = CommandEnvelope.from_dict(foreign_raw)
    foreign_context = replace(
        _context(tmp_path),
        stable_id="project-2",
        scope=foreign_scope,
    )
    foreign_spec = FormalTaskSpec(
        name=foreign_command.payload["name"],
        instruction=foreign_command.payload["instruction"],
        origin=foreign_command.origin,
        context=foreign_context,
        executor_id=foreign_command.payload["executor_id"],
        required_capabilities=tuple(foreign_command.required_capabilities),
        side_effect_class=foreign_command.payload["side_effect_class"],
        attributes=tuple(sorted(foreign_command.payload["attributes"].items())),
    )
    foreign_created = store.create(foreign_command, foreign_spec, observed_at=NOW)
    assert foreign_created.ok and foreign_created.result is not None
    foreign_task_id = str(foreign_created.result["task_id"])
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM outbox WHERE command_id=?",
            (shared_command_id,),
        ).fetchone() == (1,)
    before = _database_dump(database)

    reopened = SqliteTaskStore(database)

    assert reopened.get_task(task_id, _scope()).spec.instruction == (
        "Scope-local revised instruction."
    )
    claimed = [reopened.claim_outbox(f"cross-scope-{index}") for index in range(2)]
    assert {item.task_id for item in claimed if item is not None} == {
        task_id,
        foreign_task_id,
    }
    assert _database_dump(database) != before


@pytest.mark.parametrize(
    "payload_change",
    [
        {"attempt_id": "attempt-stale"},
        {"expected_event_head": 1},
    ],
)
def test_predispatch_update_stale_authority_has_zero_effects(
    tmp_path: Path, payload_change: dict[str, object]
) -> None:
    database = tmp_path / "update-stale.sqlite"
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
    payload: dict[str, object] = {
        "attempt_id": str(created.result["attempt_id"]),
        "expected_event_head": 0,
        "instruction": "Must not persist.",
        "constraints": None,
        **payload_change,
    }
    command, grant = _wave2_command(
        task_id,
        "task.update",
        payload,
        command_id=f"command-update-stale-{next(iter(payload_change))}",
    )
    before = _task_authority_dump(database)

    rejected = core.execute(command, grant, now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_UPDATE_PRECONDITION_STALE"
    assert rejected.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone() == (1,)
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    reopened = SqliteTaskStore(database)
    replay = PersistentTaskCore(reopened, executor).execute(
        replace(command, request_id=f"request-replay-{command.command_id}"),
        grant,
        now=NOW,
    )
    assert replay.error == rejected.error
    assert replay.observed_at == rejected.observed_at
    assert replay.extensions == rejected.extensions
    changed = CommandEnvelope.from_dict(
        {
            **command.to_dict(),
            "request_id": f"request-changed-{command.command_id}",
            "payload": {**command.payload, "instruction": "Different rejected bytes."},
        }
    )
    changed_result = PersistentTaskCore(reopened, executor).execute(
        changed, grant, now=NOW
    )
    assert not changed_result.ok and changed_result.error is not None
    assert changed_result.error.reason == "IDEMPOTENCY_CONFLICT"
    assert _task_authority_dump(database) == before


def test_predispatch_update_rejects_claimed_dispatch_without_effects(
    tmp_path: Path,
) -> None:
    database = tmp_path / "update-claimed.sqlite"
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
    claimed = store.claim_outbox("update-race")
    assert claimed is not None
    command, grant = _wave2_command(
        claimed.task_id,
        "task.update",
        {
            "attempt_id": claimed.attempt_id,
            "expected_event_head": 0,
            "instruction": "Too late.",
            "constraints": None,
        },
        command_id="command-update-claimed",
    )
    before = _task_authority_dump(database)

    rejected = core.execute(command, grant, now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_UPDATE_PRECONDITION_STALE"
    assert rejected.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone() == (1,)
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    assert store.release_outbox(claimed, "retry later") is True
    reopened = SqliteTaskStore(database)
    replay = PersistentTaskCore(reopened, executor).execute(
        replace(command, request_id="request-update-claimed-replay"),
        grant,
        now=NOW,
    )
    assert replay.error == rejected.error
    assert replay.observed_at == rejected.observed_at


@pytest.mark.parametrize(
    "failpoint",
    [
        "update.after_requested_event",
        "update.after_task",
        "update.after_outbox",
        "update.after_applied_event",
        "update.after_command",
    ],
)
def test_predispatch_update_failpoints_roll_back_every_owned_surface(
    tmp_path: Path, failpoint: str
) -> None:
    enabled = False

    def fail(name: str) -> None:
        if enabled and name == failpoint:
            raise RuntimeError(name)

    database = tmp_path / f"{failpoint}.sqlite"
    store = SqliteTaskStore(database, failpoint=fail)
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
    command, grant = _wave2_command(
        str(created.result["task_id"]),
        "task.update",
        {
            "attempt_id": str(created.result["attempt_id"]),
            "expected_event_head": 0,
            "instruction": "Rollback me.",
            "constraints": ["No residue."],
        },
        command_id=f"command-{failpoint}",
    )
    before = _database_dump(database)
    enabled = True

    with pytest.raises(RuntimeError, match=failpoint):
        core.execute(command, grant, now=NOW)

    assert _database_dump(database) == before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    SqliteTaskStore(database)


def test_two_store_connections_allow_one_predispatch_update_winner(
    tmp_path: Path,
) -> None:
    database = tmp_path / "update-concurrent.sqlite"
    first_store = SqliteTaskStore(database)
    first_core = PersistentTaskCore(first_store, _Executor())
    invocation = _create(tmp_path)
    created = first_core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    second_store = SqliteTaskStore(database)
    second_core = PersistentTaskCore(second_store, _Executor())
    first_command, first_grant = _wave2_command(
        task_id,
        "task.update",
        {
            "attempt_id": attempt_id,
            "expected_event_head": 0,
            "instruction": "Winner one.",
            "constraints": None,
        },
        command_id="command-update-race-one",
    )
    second_command, second_grant = _wave2_command(
        task_id,
        "task.update",
        {
            "attempt_id": attempt_id,
            "expected_event_head": 0,
            "instruction": "Winner two.",
            "constraints": None,
        },
        command_id="command-update-race-two",
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(first_core.execute, first_command, first_grant, now=NOW),
            pool.submit(second_core.execute, second_command, second_grant, now=NOW),
        )
        results = tuple(future.result(timeout=10) for future in futures)

    assert sum(result.ok for result in results) == 1
    loser_index = next(index for index, result in enumerate(results) if not result.ok)
    loser = results[loser_index]
    loser_command = (first_command, second_command)[loser_index]
    loser_grant = (first_grant, second_grant)[loser_index]
    assert loser.error is not None
    assert loser.error.reason == "TASK_UPDATE_PRECONDITION_STALE"
    assert loser.extensions == {
        "live_voice.command": {
            "disposition": "conflict",
            "admission_event_id": None,
            "settlement_event_id": None,
        }
    }
    events = first_store.events(task_id, _scope(), after_seq=-1)
    assert [event.event_type for event in events].count("task.update_requested") == 1
    assert [event.event_type for event in events].count("task.update_applied") == 1
    authority_after = _task_authority_dump(database)
    reopened = SqliteTaskStore(database)
    replay_executor = _Executor()
    replay = PersistentTaskCore(reopened, replay_executor).execute(
        replace(loser_command, request_id="request-update-race-loser-replay"),
        loser_grant,
        now=NOW,
    )
    assert replay.error == loser.error
    assert replay.extensions == loser.extensions
    assert _task_authority_dump(database) == authority_after
    assert replay_executor.dispatches == []
    assert replay_executor.cancels == []
    assert replay_executor.adjustments == []
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id IN (?, ?)",
            (first_command.command_id, second_command.command_id),
        ).fetchone() == (2,)
    dispatch = reopened.claim_outbox("update-race-winner")
    assert dispatch is not None
    assert dispatch.spec == reopened.get_task(task_id, _scope()).spec


@pytest.mark.parametrize(
    "command_type",
    ["task.update", "task.adjust", "task.pause", "task.cancel"],
)
def test_corrupt_current_attempt_never_persists_a_business_decision(
    tmp_path: Path,
    command_type: str,
) -> None:
    database = tmp_path / f"corrupt-current-{command_type}.sqlite"
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
    attempt_id = str(created.result["attempt_id"])
    payloads: dict[str, dict[str, object]] = {
        "task.update": {
            "attempt_id": attempt_id,
            "expected_event_head": 0,
            "instruction": "Must roll back with corrupt authority.",
            "constraints": None,
        },
        "task.adjust": {"adjustment": "Must not be admitted."},
        "task.pause": {
            "attempt_id": attempt_id,
            "expected_event_head": 0,
            "reason": None,
        },
        "task.cancel": {},
    }
    command, grant = _wave2_command(
        task_id,
        command_type,
        payloads[command_type],
        command_id=f"command-corrupt-{command_type}",
    )
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM attempts WHERE attempt_id=?", (attempt_id,))
        connection.commit()
    before = _database_dump(database)

    rejected = core.execute(command, grant, now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_STORE_CORRUPT"
    assert rejected.error.code is ErrorCode.RESULT_UNKNOWN
    assert rejected.extensions["live_voice.command"]["disposition"] == "unknown"
    assert _database_dump(database) == before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


@pytest.mark.parametrize(
    ("command_type", "extra_payload"),
    [
        ("task.pause", {"reason": "Hold briefly."}),
        ("task.resume", {"reason": None}),
        (
            "task.reprioritize",
            {"priority": "high", "reason": "Important, but unsupported."},
        ),
    ],
)
def test_unimplemented_running_controls_are_durable_unsupported_zero_effects(
    tmp_path: Path, command_type: str, extra_payload: dict[str, object]
) -> None:
    database = tmp_path / f"{command_type}.sqlite"
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
    dispatch = store.claim_outbox("unsupported-control")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    task = store.get_task(dispatch.task_id, _scope())
    command, grant = _wave2_command(
        task.task_id,
        command_type,
        {
            "attempt_id": task.attempt_id,
            "expected_event_head": task.event_head,
            **extra_payload,
        },
        command_id=f"command-{command_type}",
    )
    before = _task_authority_dump(database)

    decision = core.execute(command, grant, now=NOW)

    assert not decision.ok and decision.error is not None
    expected_reason = (
        "TASK_CONTROL_STATE_CONFLICT"
        if command_type == "task.reprioritize"
        else "TASK_CONTROL_UNSUPPORTED"
    )
    expected_disposition = (
        "conflict" if command_type == "task.reprioritize" else "unsupported"
    )
    assert decision.error.reason == expected_reason
    assert decision.extensions == {
        "live_voice.command": {
            "disposition": expected_disposition,
            "admission_event_id": None,
            "settlement_event_id": None,
        }
    }
    assert _task_authority_dump(database) == before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    replay = core.execute(
        replace(command, request_id=f"request-replay-{command_type}"),
        grant,
        now=NOW,
    )
    assert replay.request_id == f"request-replay-{command_type}"
    assert replay.error == decision.error
    assert replay.extensions == decision.extensions
    assert SqliteTaskStore(database).get_task(task.task_id, _scope()) == task


@pytest.mark.parametrize(
    ("command_type", "expected_reason"),
    [
        ("task.pause", "TASK_CONTROL_UNSUPPORTED"),
        ("task.resume", "TASK_CONTROL_UNSUPPORTED"),
        ("task.reprioritize", "TASK_CONTROL_STATE_CONFLICT"),
        ("task.provide_input", "TASK_CONTROL_STATE_CONFLICT"),
        ("task.update", "TASK_UPDATE_PRECONDITION_STALE"),
        ("task.adjust", "TASK_ADJUSTMENT_STATE_CONFLICT"),
        ("task.cancel", "TASK_ALREADY_TERMINAL"),
        ("task.create_successor", "TASK_SUCCESSOR_PRECONDITION_CONFLICT"),
    ],
)
def test_command_local_correlation_negative_decisions_reopen_replay_and_conflict(
    tmp_path: Path,
    command_type: str,
    expected_reason: str,
) -> None:
    """A later command correlation is not the Task creation correlation."""

    if command_type == "task.cancel":
        store, executor, core, task_id, _attempt_id = _terminal_task(tmp_path)
        task = store.get_task(task_id, _scope())
    else:
        database = tmp_path / f"command-correlation-{command_type}.sqlite"
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
        task = store.get_task(str(created.result["task_id"]), _scope())
        if command_type in {"task.pause", "task.resume", "task.reprioritize"}:
            dispatch = store.claim_outbox(f"command-correlation-{command_type}")
            assert dispatch is not None
            store.complete_outbox(
                dispatch,
                executor_ref=f"legacy:{dispatch.attempt_id}",
                observations=_observations(dispatch),
            )
            task = store.get_task(task.task_id, _scope())

    current_event = store.events(task.task_id, _scope())[-1]
    payloads: dict[str, dict[str, object]] = {
        "task.pause": {
            "attempt_id": task.attempt_id,
            "expected_event_head": task.event_head,
            "reason": "Pause at this command boundary.",
        },
        "task.resume": {
            "attempt_id": task.attempt_id,
            "expected_event_head": task.event_head,
            "reason": None,
        },
        "task.reprioritize": {
            "attempt_id": task.attempt_id,
            "expected_event_head": task.event_head,
            "priority": "high",
            "reason": "Use this command-local correlation.",
        },
        "task.provide_input": {
            "attempt_id": task.attempt_id,
            "expected_event_head": task.event_head,
            "responds_to_event_id": current_event.event_id,
            "text": "A valid but currently inapplicable response.",
        },
        "task.update": {
            "attempt_id": task.attempt_id,
            "expected_event_head": task.event_head + 1,
            "instruction": "A stale update with a command-local correlation.",
            "constraints": None,
        },
        "task.adjust": {"adjustment": "A non-running adjustment."},
        "task.cancel": {},
        "task.create_successor": {
            "expected_predecessor_revision_number": task.revision_number,
            "expected_predecessor_event_head": task.event_head,
            "predecessor_terminal_event_id": current_event.event_id,
            "predecessor_outcome": TerminalOutcome.CANCELLED.value,
            "predecessor_result_sha256": None,
            "name": "Command-local successor",
            "instruction": "Preserve the predecessor and create one revision.",
            "constraints": ["Do not mutate predecessor bytes."],
            "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
            "side_effect_class": "project_mutation",
            "attributes": {
                "model_identity": "default#0",
                "model_config_version": "catalog-v1",
            },
        },
    }
    command_id = f"command-local-correlation-{command_type}"
    command, grant = _wave2_command(
        task.task_id,
        command_type,
        payloads[command_type],
        command_id=command_id,
    )
    command_raw = command.to_dict()
    command_raw["correlation_id"] = f"correlation-command-{command_type}"
    command = CommandEnvelope.from_dict(command_raw)
    context = _context(tmp_path) if command_type == "task.create_successor" else None
    authority_before = _task_authority_dump(store.database_path)

    decision = core.execute(command, grant, context=context, now=NOW)

    assert not decision.ok and decision.error is not None
    assert decision.error.reason == expected_reason
    assert _task_authority_dump(store.database_path) == authority_before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    ledger_after_decision = _database_dump(store.database_path)

    reopened_core = PersistentTaskCore(SqliteTaskStore(store.database_path), executor)
    replay = reopened_core.execute(
        replace(command, request_id=f"request-replay-{command_id}"),
        grant,
        context=context,
        now=NOW,
    )

    assert replay.request_id == f"request-replay-{command_id}"
    assert replay.error == decision.error
    assert replay.observed_at == decision.observed_at
    assert replay.extensions == decision.extensions
    assert _database_dump(store.database_path) == ledger_after_decision

    changed_raw = command.to_dict()
    changed_raw.update(
        {
            "request_id": f"request-changed-correlation-{command_id}",
            "correlation_id": f"correlation-command-changed-{command_type}",
        }
    )
    changed = CommandEnvelope.from_dict(changed_raw)
    conflict = reopened_core.execute(
        changed,
        grant,
        context=context,
        now=NOW,
    )

    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "IDEMPOTENCY_CONFLICT"
    assert _database_dump(store.database_path) == ledger_after_decision
    assert _task_authority_dump(store.database_path) == authority_before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


@pytest.mark.parametrize(
    ("command_type", "expected_reason"),
    [
        ("task.provide_input", "TASK_CONTROL_STATE_CONFLICT"),
        ("task.update", "TASK_UPDATE_PRECONDITION_STALE"),
        ("task.adjust", "TASK_ADJUSTMENT_STATE_CONFLICT"),
        ("task.create_successor", "TASK_SUCCESSOR_PRECONDITION_CONFLICT"),
    ],
)
def test_durable_negative_binding_never_persists_sensitive_command_content(
    tmp_path: Path,
    command_type: str,
    expected_reason: str,
) -> None:
    """Removing negative-ledger sanitization must expose the sentinel and fail."""

    database = tmp_path / f"redacted-{command_type}.sqlite"
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
    task = store.get_task(str(created.result["task_id"]), _scope())
    sentinel = f"PRIVATE_{command_type.replace('.', '_').upper()}_7B91C2"
    payloads: dict[str, dict[str, object]] = {
        "task.provide_input": {
            "attempt_id": task.attempt_id,
            "expected_event_head": task.event_head,
            "responds_to_event_id": "event-not-current",
            "text": sentinel,
        },
        "task.update": {
            "attempt_id": task.attempt_id,
            "expected_event_head": task.event_head + 1,
            "instruction": sentinel,
            "constraints": [sentinel],
        },
        "task.adjust": {"adjustment": sentinel},
        "task.create_successor": {
            "expected_predecessor_revision_number": task.revision_number,
            "expected_predecessor_event_head": task.event_head,
            "predecessor_terminal_event_id": "event-not-terminal",
            "predecessor_outcome": TerminalOutcome.CANCELLED.value,
            "predecessor_result_sha256": None,
            "name": "Successor revision",
            "instruction": sentinel,
            "constraints": [sentinel],
            "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
            "side_effect_class": "project_mutation",
            "attributes": {
                "model_identity": "default#0",
                "model_config_version": "catalog-v1",
            },
        },
    }
    command, grant = _wave2_command(
        task.task_id,
        command_type,
        payloads[command_type],
        command_id=f"command-redacted-{command_type}",
    )
    context = _context(tmp_path) if command_type == "task.create_successor" else None
    before = _task_authority_dump(database)

    decision = core.execute(command, grant, context=context, now=NOW)

    assert not decision.ok and decision.error is not None
    assert decision.error.reason == expected_reason
    assert _task_authority_dump(database) == before
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT fingerprint, result_json FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone()
    assert row is not None
    assert sentinel.encode("utf-8") not in row[0]
    assert sentinel not in row[1]
    assert sentinel.encode("utf-8") not in _database_authority_bytes(database)
    assert sentinel not in json.dumps(decision.to_dict())

    reopened_core = PersistentTaskCore(SqliteTaskStore(database), executor)
    replay = reopened_core.execute(
        replace(command, request_id=f"request-redacted-replay-{command_type}"),
        grant,
        context=context,
        now=NOW,
    )
    assert replay.error == decision.error
    assert replay.observed_at == decision.observed_at
    assert _task_authority_dump(database) == before

    changed_payload = command.payload
    if command_type == "task.provide_input":
        changed_payload["text"] = f"{sentinel}_CHANGED"
    elif command_type == "task.update":
        changed_payload["instruction"] = f"{sentinel}_CHANGED"
    elif command_type == "task.adjust":
        changed_payload["adjustment"] = f"{sentinel}_CHANGED"
    else:
        changed_payload["instruction"] = f"{sentinel}_CHANGED"
    changed = CommandEnvelope.from_dict(
        {
            **command.to_dict(),
            "request_id": f"request-redacted-changed-{command_type}",
            "payload": changed_payload,
        }
    )
    changed_result = reopened_core.execute(
        changed,
        grant,
        context=context,
        now=NOW,
    )
    assert not changed_result.ok and changed_result.error is not None
    assert changed_result.error.reason == "IDEMPOTENCY_CONFLICT"
    assert f"{sentinel}_CHANGED".encode("utf-8") not in _database_authority_bytes(
        database
    )
    assert _task_authority_dump(database) == before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


@pytest.mark.parametrize(
    "corruption",
    [
        "authority_reason",
        "authority_state",
        "task_correlation",
        "payload_authority",
        "binding_type",
        "version",
        "digest",
        "malformed",
    ],
)
def test_durable_negative_binding_tampering_fails_closed_on_reopen(
    tmp_path: Path,
    corruption: str,
) -> None:
    store, executor, core, task_id, _attempt_id = _terminal_task(tmp_path)
    database = store.database_path
    cancel = _cancel(task_id)
    decision = core.execute(
        cancel.envelope,
        cancel.authorization,
        now=NOW,
    )
    assert not decision.ok and decision.error is not None
    assert decision.error.reason == "TASK_ALREADY_TERMINAL"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT fingerprint FROM commands WHERE command_id=?",
            (cancel.envelope.command_id,),
        ).fetchone()
        assert row is not None
        binding = json.loads(row[0])
        authority = binding["authority"]
        if corruption == "authority_reason":
            authority["reason"] = "TASK_CONTROL_UNSUPPORTED"
            fingerprint = _rehash_decision_binding(binding)
        elif corruption == "authority_state":
            authority["task"]["state"] = FormalTaskState.RUNNING.value
            fingerprint = _rehash_decision_binding(binding)
        elif corruption == "task_correlation":
            authority["task"]["correlation_id"] = "correlation-forged-task"
            fingerprint = _rehash_decision_binding(binding)
        elif corruption == "payload_authority":
            authority["payload"]["payload_sha256"] = "0" * 64
            fingerprint = _rehash_decision_binding(binding)
        elif corruption == "binding_type":
            binding["binding_type"] = "live_voice.unknown_binding"
            fingerprint = canonical_json_bytes(binding)
        elif corruption == "version":
            binding["version"] = 2
            fingerprint = canonical_json_bytes(binding)
        elif corruption == "digest":
            binding["command_sha256"] = "A" * 64
            fingerprint = canonical_json_bytes(binding)
        else:
            fingerprint = b'{"malformed":true}'
        connection.execute(
            "UPDATE commands SET fingerprint=? WHERE command_id=?",
            (fingerprint, cancel.envelope.command_id),
        )
        connection.commit()
    before_dump = _database_dump(database)
    before_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before_dump
    assert database.read_bytes() == before_bytes
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_forged_terminal_cancel_decision_over_running_history_fails_closed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forged-terminal-cancel.sqlite"
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
    dispatch = store.claim_outbox("forged-terminal-cancel")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    running = store.get_task(dispatch.task_id, _scope())
    assert running.state is FormalTaskState.RUNNING
    pause, pause_grant = _wave2_command(
        running.task_id,
        "task.pause",
        {
            "attempt_id": running.attempt_id,
            "expected_event_head": running.event_head,
            "reason": None,
        },
        command_id="command-forged-terminal-cancel",
    )
    unsupported = core.execute(pause, pause_grant, now=NOW)
    assert not unsupported.ok and unsupported.error is not None
    assert unsupported.error.reason == "TASK_CONTROL_UNSUPPORTED"
    cancel, _cancel_grant = _wave2_command(
        running.task_id,
        "task.cancel",
        {},
        command_id=pause.command_id,
    )
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT fingerprint, result_json FROM commands WHERE command_id=?",
            (pause.command_id,),
        ).fetchone()
        assert row is not None
        binding = json.loads(row[0])
        result = json.loads(row[1])
        binding["command_type"] = "task.cancel"
        binding["command_sha256"] = hashlib.sha256(
            cancel.fingerprint()
        ).hexdigest()
        binding["replay_sha256"] = binding["command_sha256"]
        authority = binding["authority"]
        authority["reason"] = "TASK_ALREADY_TERMINAL"
        authority["payload"] = SqliteTaskStore._decision_payload_authority(cancel)
        result["error"] = ContractViolation(
            ErrorCode.CONFLICT,
            "TASK_ALREADY_TERMINAL",
            "terminal tasks cannot accept cancellation",
        ).error.to_dict()
        result["extensions"]["live_voice.command"]["disposition"] = "conflict"
        connection.execute(
            """UPDATE commands SET command_type=?, fingerprint=?, result_json=?
               WHERE command_id=?""",
            (
                "task.cancel",
                _rehash_decision_binding(binding),
                json.dumps(result, sort_keys=True),
                pause.command_id,
            ),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before
    assert executor.cancels == []
    assert executor.adjustments == []


def test_provide_input_requires_exact_current_decision_event_then_is_unsupported(
    tmp_path: Path,
) -> None:
    database = tmp_path / "provide-input.sqlite"
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
    dispatch = store.claim_outbox("provide-input")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    running = store.get_task(dispatch.task_id, _scope())
    premature, premature_grant = _wave2_command(
        running.task_id,
        "task.provide_input",
        {
            "attempt_id": running.attempt_id,
            "expected_event_head": running.event_head,
            "responds_to_event_id": "event-not-current",
            "text": "Sensitive answer must not leak.",
        },
        command_id="command-input-premature",
    )
    before_premature = _task_authority_dump(database)

    conflict = core.execute(premature, premature_grant, now=NOW)

    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "TASK_CONTROL_STATE_CONFLICT"
    assert conflict.extensions == {
        "live_voice.command": {
            "disposition": "conflict",
            "admission_event_id": None,
            "settlement_event_id": None,
        }
    }
    assert _task_authority_dump(database) == before_premature

    decision_event_id = "event-input-required"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO task_events(
                   task_id, seq, event_id, attempt_id, scope_json, event_type,
                   state, outcome, producer, source_event_id, causation_id,
                   correlation_id, occurred_at, details_json)
               SELECT task_id, event_head + 1, ?, attempt_id, scope_json,
                      'task.decision_required', 'decision_required', NULL,
                      'task_core', NULL, 'policy-input', correlation_id, ?, '{}'
               FROM tasks WHERE task_id=?""",
            (decision_event_id, NOW, running.task_id),
        )
        connection.execute(
            """UPDATE tasks SET state='decision_required',
                   event_head=event_head + 1, updated_at=? WHERE task_id=?""",
            (NOW, running.task_id),
        )
        connection.commit()
    decision_task = store.get_task(running.task_id, _scope())
    command, grant = _wave2_command(
        running.task_id,
        "task.provide_input",
        {
            "attempt_id": decision_task.attempt_id,
            "expected_event_head": decision_task.event_head,
            "responds_to_event_id": decision_event_id,
            "text": "Sensitive answer must not leak.",
        },
        command_id="command-input-exact",
    )
    before = _task_authority_dump(database)

    unsupported = core.execute(command, grant, now=NOW)

    assert not unsupported.ok and unsupported.error is not None
    assert unsupported.error.reason == "TASK_CONTROL_UNSUPPORTED"
    assert unsupported.extensions == {
        "live_voice.command": {
            "disposition": "unsupported",
            "admission_event_id": None,
            "settlement_event_id": None,
        }
    }
    assert _task_authority_dump(database) == before
    assert "Sensitive answer" not in json.dumps(unsupported.to_dict())
    with sqlite3.connect(database) as connection:
        stored_result = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone()[0]
    assert "Sensitive answer" not in stored_result
    SqliteTaskStore(database)


def test_unimplemented_control_stale_attempt_and_terminal_are_durable_conflicts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "control-conflicts.sqlite"
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
    stale, stale_grant = _wave2_command(
        task_id,
        "task.pause",
        {
            "attempt_id": "attempt-wrong",
            "expected_event_head": 0,
            "reason": None,
        },
        command_id="command-pause-stale",
    )
    before_stale = _task_authority_dump(database)
    stale_result = core.execute(stale, stale_grant, now=NOW)
    assert not stale_result.ok and stale_result.error is not None
    assert stale_result.error.reason == "TASK_CONTROL_PRECONDITION_STALE"
    assert stale_result.extensions == {
        "live_voice.command": {
            "disposition": "conflict",
            "admission_event_id": None,
            "settlement_event_id": None,
        }
    }
    assert _task_authority_dump(database) == before_stale

    dispatch = store.claim_outbox("terminal-control")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch, outcome=TerminalOutcome.COMPLETED),
    )
    terminal = store.get_task(task_id, _scope())
    resume, resume_grant = _wave2_command(
        task_id,
        "task.resume",
        {
            "attempt_id": terminal.attempt_id,
            "expected_event_head": terminal.event_head,
            "reason": None,
        },
        command_id="command-resume-terminal",
    )
    before_terminal = _task_authority_dump(database)
    terminal_result = core.execute(resume, resume_grant, now=NOW)
    assert not terminal_result.ok and terminal_result.error is not None
    assert terminal_result.error.reason == "TASK_CONTROL_STATE_CONFLICT"
    assert terminal_result.extensions == {
        "live_voice.command": {
            "disposition": "conflict",
            "admission_event_id": None,
            "settlement_event_id": None,
        }
    }
    assert _task_authority_dump(database) == before_terminal
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    SqliteTaskStore(database)


@pytest.mark.parametrize(
    "state",
    [
        FormalTaskState.ACCEPTED,
        FormalTaskState.BLOCKED,
        FormalTaskState.DECISION_REQUIRED,
    ],
)
def test_adjust_is_positive_only_while_task_and_attempt_are_running(
    tmp_path: Path, state: FormalTaskState
) -> None:
    database = tmp_path / f"adjust-{state.value}.sqlite"
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
    if state is not FormalTaskState.ACCEPTED:
        dispatch = store.claim_outbox("adjust-state")
        assert dispatch is not None
        store.complete_outbox(
            dispatch,
            executor_ref=f"legacy:{dispatch.attempt_id}",
            observations=_observations(dispatch),
        )
        with sqlite3.connect(database) as connection:
            head = connection.execute(
                "SELECT event_head FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO task_events(
                       task_id, seq, event_id, attempt_id, scope_json, event_type,
                       state, outcome, producer, source_event_id, causation_id,
                       correlation_id, occurred_at, details_json)
                   SELECT task_id, ?, ?, attempt_id, scope_json, ?, ?, NULL,
                          'task_core', NULL, ?, correlation_id, ?, '{}'
                   FROM tasks WHERE task_id=?""",
                (
                    head + 1,
                    f"event-adjust-{state.value}",
                    f"task.{state.value}",
                    state.value,
                    f"policy-adjust-{state.value}",
                    NOW,
                    task_id,
                ),
            )
            connection.execute(
                "UPDATE tasks SET state=?, event_head=? WHERE task_id=?",
                (state.value, head + 1, task_id),
            )
            connection.commit()
    command, grant = _adjust(
        task_id,
        "Must not reach Executor.",
        command_id=f"command-adjust-{state.value}",
        request_id=f"request-adjust-{state.value}",
    )
    before = _task_authority_dump(database)

    conflict = core.execute(command, grant, now=NOW)

    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "TASK_ADJUSTMENT_STATE_CONFLICT"
    assert conflict.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone() == (1,)
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    replay = PersistentTaskCore(SqliteTaskStore(database), executor).execute(
        replace(command, request_id=f"request-adjust-replay-{state.value}"),
        grant,
        now=NOW,
    )
    assert replay.error == conflict.error
    assert replay.extensions == conflict.extensions
    assert _task_authority_dump(database) == before


@pytest.mark.parametrize(
    "outcome",
    [
        TerminalOutcome.COMPLETED,
        TerminalOutcome.FAILED,
        TerminalOutcome.CANCELLED,
        TerminalOutcome.INTERRUPTED,
    ],
)
def test_successor_creates_new_revision_and_never_mutates_predecessor(
    tmp_path: Path, outcome: TerminalOutcome
) -> None:
    database = tmp_path / f"successor-{outcome.value}.sqlite"
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
    dispatch = store.claim_outbox("successor-predecessor")
    assert dispatch is not None
    result_text: str | None = None
    artifacts: tuple[TaskResultArtifact, ...] = ()
    if outcome is TerminalOutcome.COMPLETED:
        result_path = tmp_path / "successor-result.txt"
        result_path.write_text("immutable predecessor result\n", encoding="utf-8")
        result_text = "immutable predecessor result"
        artifacts = (
            TaskResultArtifact(
                relative_path=result_path.name,
                sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
            ),
        )
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(
            dispatch,
            outcome=outcome,
            result_text=result_text,
            result_artifacts=artifacts,
        ),
    )
    predecessor = store.get_task(dispatch.task_id, _scope())
    terminal_event = store.events(predecessor.task_id, _scope())[-1]
    assert terminal_event.event_type == "task.terminal"
    availability, task_result, _reason = store.task_result(
        predecessor.task_id, _scope()
    )
    if outcome is TerminalOutcome.COMPLETED:
        assert availability is TaskResultAvailability.AVAILABLE
        assert task_result is not None
        result_sha256 = hashlib.sha256(
            canonical_json_bytes(task_result.to_dict())
        ).hexdigest()
    else:
        assert availability is TaskResultAvailability.UNAVAILABLE
        assert task_result is None
        result_sha256 = None
    command, grant = _successor_command(
        predecessor,
        terminal_event,
        result_sha256=result_sha256,
        command_id=f"command-successor-{outcome.value}",
    )
    before = _predecessor_dump(database, predecessor.task_id)

    successor_result = core.execute(
        command,
        grant,
        context=replace(_context(tmp_path), revision_value="successor-revision"),
        now=NOW,
    )

    assert successor_result.ok and successor_result.result is not None
    assert successor_result.extensions["live_voice.command"]["disposition"] == (
        "accepted"
    )
    successor_id = str(successor_result.result["task_id"])
    assert successor_id != predecessor.task_id
    successor = store.get_task(successor_id, _scope())
    assert successor.predecessor_task_id == predecessor.task_id
    assert successor.revision_number == predecessor.revision_number + 1
    assert successor.state is FormalTaskState.ACCEPTED
    assert successor.spec.constraints == ("Preserve predecessor truth.",)
    assert _predecessor_dump(database, predecessor.task_id) == before
    events = store.events(successor_id, _scope())
    assert len(events) == 1 and events[0].event_type == "task.accepted"
    assert successor_result.extensions["live_voice.command"] == {
        "disposition": "accepted",
        "admission_event_id": events[0].event_id,
        "settlement_event_id": None,
    }
    successor_dispatch = store.claim_outbox("successor-dispatch")
    assert successor_dispatch is not None
    assert successor_dispatch.task_id == successor_id
    assert successor_dispatch.spec == successor.spec
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    reopened = SqliteTaskStore(database)
    assert reopened.get_task(successor_id, _scope()) == successor
    assert _predecessor_dump(database, predecessor.task_id) == before


def test_successor_exact_replay_changed_fingerprint_and_second_revision_loser(
    tmp_path: Path,
) -> None:
    database, store, executor, core, predecessor, terminal_event, digest = (
        _successor_fixture(tmp_path, "successor-replay.sqlite")
    )
    command, grant = _successor_command(
        predecessor, terminal_event, result_sha256=digest
    )
    predecessor_before = _predecessor_dump(database, predecessor.task_id)
    first = core.execute(command, grant, context=_context(tmp_path), now=NOW)
    assert first.ok and first.result is not None
    after_first = _database_dump(database)
    authority_after_first = _task_authority_dump(database)

    replay = core.execute(
        replace(command, request_id="request-successor-replay"),
        grant,
        context=_context(tmp_path),
        now=NOW,
    )

    assert replay.ok and replay.request_id == "request-successor-replay"
    assert replay.result == first.result
    assert replay.extensions == first.extensions
    assert _database_dump(database) == after_first
    changed = CommandEnvelope.from_dict(
        {
            **command.to_dict(),
            "request_id": "request-successor-changed",
            "payload": {**command.payload, "instruction": "Different revision."},
        }
    )
    conflict = core.execute(changed, grant, context=_context(tmp_path), now=NOW)
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "IDEMPOTENCY_CONFLICT"
    assert _database_dump(database) == after_first
    second, second_grant = _successor_command(
        predecessor,
        terminal_event,
        result_sha256=digest,
        command_id="command-successor-second",
    )
    second_result = core.execute(
        second, second_grant, context=_context(tmp_path), now=NOW
    )
    assert not second_result.ok and second_result.error is not None
    assert second_result.error.reason == "TASK_SUCCESSOR_PRECONDITION_CONFLICT"
    assert second_result.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(database) == authority_after_first
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (second.command_id,),
        ).fetchone() == (1,)
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    SqliteTaskStore(database)


@pytest.mark.parametrize("case", ["nonterminal", "unknown", "digest"])
def test_successor_ineligible_or_stale_predecessor_has_zero_effects(
    tmp_path: Path, case: str
) -> None:
    if case == "nonterminal":
        database = tmp_path / "successor-nonterminal.sqlite"
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
        predecessor = store.get_task(str(created.result["task_id"]), _scope())
        command, grant = _wave2_command(
            predecessor.task_id,
            "task.create_successor",
            {
                "expected_predecessor_revision_number": 1,
                "expected_predecessor_event_head": predecessor.event_head,
                "predecessor_terminal_event_id": "event-not-terminal",
                "predecessor_outcome": "cancelled",
                "predecessor_result_sha256": None,
                "name": "Successor revision",
                "instruction": "Must not be created.",
                "constraints": [],
                "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
                "side_effect_class": "project_mutation",
                "attributes": {
                    "model_identity": "default#0",
                    "model_config_version": "catalog-v1",
                },
            },
            command_id="command-successor-nonterminal",
        )
    else:
        outcome = (
            TerminalOutcome.UNKNOWN
            if case == "unknown"
            else TerminalOutcome.COMPLETED
        )
        (
            database,
            store,
            executor,
            core,
            predecessor,
            terminal_event,
            digest,
        ) = _successor_fixture(
            tmp_path, f"successor-{case}.sqlite", outcome=outcome
        )
        command, grant = _successor_command(
            predecessor,
            terminal_event,
            result_sha256=("0" * 64 if case == "digest" else digest),
            command_id=f"command-successor-{case}",
        )
    before = _task_authority_dump(database)
    predecessor_before = _predecessor_dump(database, predecessor.task_id)

    rejected = core.execute(command, grant, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason in {
        "TASK_SUCCESSOR_PRECONDITION_CONFLICT",
        "TASK_SUCCESSOR_RESULT_CONFLICT",
    }
    assert rejected.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(database) == before
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone() == (1,)
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    SqliteTaskStore(database)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("predecessor_outcome", "not-a-terminal-outcome"),
        ("predecessor_outcome", 1),
        ("expected_predecessor_revision_number", True),
        ("expected_predecessor_revision_number", 0),
        ("expected_predecessor_event_head", True),
        ("expected_predecessor_event_head", -1),
        ("predecessor_terminal_event_id", ""),
        ("predecessor_result_sha256", 42),
        ("predecessor_result_sha256", "A" * 64),
        ("name", ""),
        ("instruction", ""),
        ("constraints", "not-an-array"),
        ("executor_id", ""),
        ("side_effect_class", "not-a-side-effect-class"),
        ("attributes", "not-an-object"),
    ],
)
def test_direct_store_rejects_malformed_successor_before_transaction_or_ledger(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    """Removing Store-local shape validation must admit a forged wire object."""

    database, store, executor, _core, predecessor, event, digest = (
        _successor_fixture(tmp_path, f"successor-malformed-{field}-{type(value).__name__}.sqlite")
    )
    command, _grant_value = _successor_command(
        predecessor,
        event,
        result_sha256=digest,
        command_id=f"command-successor-malformed-{field}-{type(value).__name__}",
    )
    forged = _forge_command_payload_scalar(command, field, value)
    spec = FormalTaskSpec(
        name=command.payload["name"],
        instruction=command.payload["instruction"],
        origin=command.origin,
        context=_context(tmp_path),
        executor_id=command.payload["executor_id"],
        required_capabilities=tuple(command.required_capabilities),
        side_effect_class=command.payload["side_effect_class"],
        constraints=tuple(command.payload["constraints"]),
        attributes=tuple(sorted(command.payload["attributes"].items())),
    )
    before_dump = _database_dump(database)
    before_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as rejected:
        store.create_successor(forged, spec, observed_at=NOW)

    assert rejected.value.code is ErrorCode.INVALID_ARGUMENT
    assert rejected.value.reason == "TASK_SUCCESSOR_INVALID"
    assert _database_dump(database) == before_dump
    assert database.read_bytes() == before_bytes
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (forged.command_id,),
        ).fetchone() == (0,)
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_unknown_successor_predecessor_conflict_is_durable_and_replays_after_reopen(
    tmp_path: Path,
) -> None:
    database, store, executor, core, predecessor, event, digest = _successor_fixture(
        tmp_path,
        "successor-unknown-durable-conflict.sqlite",
        outcome=TerminalOutcome.UNKNOWN,
    )
    assert digest is None
    command, grant = _successor_command(
        predecessor,
        event,
        result_sha256=None,
        command_id="command-successor-unknown-durable-conflict",
    )
    authority_before = _task_authority_dump(database)
    predecessor_before = _predecessor_dump(database, predecessor.task_id)

    conflict = core.execute(command, grant, context=_context(tmp_path), now=NOW)

    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "TASK_SUCCESSOR_PRECONDITION_CONFLICT"
    assert conflict.extensions["live_voice.command"] == {
        "disposition": "conflict",
        "admission_event_id": None,
        "settlement_event_id": None,
    }
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone() == (1,)
    assert _task_authority_dump(database) == authority_before
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []

    reopened = SqliteTaskStore(database)
    replay = PersistentTaskCore(reopened, executor).execute(
        replace(command, request_id="request-successor-unknown-replay"),
        grant,
        context=_context(tmp_path),
        now=NOW,
    )

    assert not replay.ok and replay.error == conflict.error
    assert replay.request_id == "request-successor-unknown-replay"
    assert replay.observed_at == conflict.observed_at
    assert replay.extensions == conflict.extensions
    assert _task_authority_dump(database) == authority_before
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before


def test_completed_successor_predecessor_without_result_is_durable_conflict(
    tmp_path: Path,
) -> None:
    database = tmp_path / "successor-completed-without-result.sqlite"
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
    dispatch = store.claim_outbox("successor-no-result-predecessor")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch, outcome=TerminalOutcome.COMPLETED),
    )
    predecessor = store.get_task(dispatch.task_id, _scope())
    terminal_event = store.events(predecessor.task_id, _scope())[-1]
    availability, task_result, _reason = store.task_result(
        predecessor.task_id, _scope()
    )
    assert availability is TaskResultAvailability.UNAVAILABLE
    assert task_result is None
    command, grant = _successor_command(
        predecessor,
        terminal_event,
        result_sha256="0" * 64,
        command_id="command-successor-completed-without-result",
    )
    authority_before = _task_authority_dump(database)
    predecessor_before = _predecessor_dump(database, predecessor.task_id)

    conflict = core.execute(command, grant, context=_context(tmp_path), now=NOW)

    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "TASK_SUCCESSOR_RESULT_CONFLICT"
    assert conflict.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(database) == authority_before
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    SqliteTaskStore(database)


def test_forged_successor_conflict_over_exact_eligible_history_fails_closed(
    tmp_path: Path,
) -> None:
    database, store, executor, core, predecessor, event, digest = _successor_fixture(
        tmp_path,
        "successor-forged-conflict.sqlite",
        outcome=TerminalOutcome.COMPLETED,
    )
    assert digest is not None
    command_id = "command-successor-forged-conflict"
    wrong, grant = _successor_command(
        predecessor,
        event,
        result_sha256="0" * 64,
        command_id=command_id,
    )
    conflict = core.execute(wrong, grant, context=_context(tmp_path), now=NOW)
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "TASK_SUCCESSOR_RESULT_CONFLICT"
    exact, _exact_grant = _successor_command(
        predecessor,
        event,
        result_sha256=digest,
        command_id=command_id,
    )
    exact_spec = FormalTaskSpec(
        name=exact.payload["name"],
        instruction=exact.payload["instruction"],
        origin=exact.origin,
        context=_context(tmp_path),
        executor_id=exact.payload["executor_id"],
        required_capabilities=tuple(exact.required_capabilities),
        side_effect_class=exact.payload["side_effect_class"],
        constraints=tuple(exact.payload["constraints"]),
        attributes=tuple(sorted(exact.payload["attributes"].items())),
    )
    exact_replay_fingerprint = canonical_json_bytes(
        {
            "command": json.loads(exact.fingerprint()),
            "resolved_spec": exact_spec.to_dict(),
        }
    )
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT fingerprint, result_json FROM commands WHERE command_id=?",
            (command_id,),
        ).fetchone()
        assert row is not None
        binding = json.loads(row[0])
        result = json.loads(row[1])
        binding["command_sha256"] = hashlib.sha256(
            exact.fingerprint()
        ).hexdigest()
        binding["replay_sha256"] = hashlib.sha256(
            exact_replay_fingerprint
        ).hexdigest()
        authority = binding["authority"]
        authority["reason"] = "TASK_SUCCESSOR_PRECONDITION_CONFLICT"
        authority["payload"] = SqliteTaskStore._decision_payload_authority(exact)
        result["error"] = ContractViolation(
            ErrorCode.CONFLICT,
            "TASK_SUCCESSOR_PRECONDITION_CONFLICT",
            "successor requires exact eligible immutable predecessor truth",
        ).error.to_dict()
        connection.execute(
            "UPDATE commands SET fingerprint=?, result_json=? WHERE command_id=?",
            (
                _rehash_decision_binding(binding),
                json.dumps(result, sort_keys=True),
                command_id,
            ),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_successor_rejects_corrupt_predecessor_lineage_with_zero_effects(
    tmp_path: Path,
) -> None:
    database, store, executor, core, predecessor, event, digest = _successor_fixture(
        tmp_path, "successor-corrupt-lineage.sqlite"
    )
    command, grant = _successor_command(
        predecessor,
        event,
        result_sha256=digest,
        command_id="command-successor-corrupt-lineage",
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE task_events SET details_json=? WHERE task_id=? AND seq=0",
            ('{"command_id":"wrong-create-command"}', predecessor.task_id),
        )
        connection.commit()
    before = _database_dump(database)
    predecessor_before = _predecessor_dump(database, predecessor.task_id)

    rejected = core.execute(command, grant, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_STORE_CORRUPT"
    assert rejected.error.code is ErrorCode.RESULT_UNKNOWN
    assert rejected.extensions["live_voice.command"]["disposition"] == "unknown"
    assert _database_dump(database) == before
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_predecessor_attempt_callbacks_cannot_mutate_successor_revision(
    tmp_path: Path,
) -> None:
    database = tmp_path / "successor-old-attempt-callback.sqlite"
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
    predecessor_dispatch = store.claim_outbox("successor-old-attempt")
    assert predecessor_dispatch is not None
    predecessor_observations = _observations(
        predecessor_dispatch, outcome=TerminalOutcome.CANCELLED
    )
    store.complete_outbox(
        predecessor_dispatch,
        executor_ref=f"legacy:{predecessor_dispatch.attempt_id}",
        observations=predecessor_observations,
    )
    predecessor = store.get_task(predecessor_dispatch.task_id, _scope())
    terminal_event = store.events(predecessor.task_id, _scope())[-1]
    command, grant = _successor_command(
        predecessor,
        terminal_event,
        result_sha256=None,
        command_id="command-successor-old-attempt",
    )
    successor_result = core.execute(
        command, grant, context=_context(tmp_path), now=NOW
    )
    assert successor_result.ok and successor_result.result is not None
    successor_id = str(successor_result.result["task_id"])
    successor_before = store.get_task(successor_id, _scope())
    authority_before = _task_authority_dump(database)
    predecessor_before = _predecessor_dump(database, predecessor.task_id)

    duplicate = store.apply_observations(predecessor_observations)
    pending = store.mark_reconciliation_pending(
        predecessor.task_id, predecessor.attempt_id, "late predecessor callback"
    )
    resolved = store.mark_reconciliation_resolved(
        predecessor.task_id, predecessor.attempt_id, "late predecessor callback"
    )
    lost = store.resolve_lost_attempt(
        predecessor.task_id, predecessor.attempt_id, "late predecessor callback"
    )
    with pytest.raises(FormalTaskViolation) as lost_claim:
        store.complete_outbox(
            predecessor_dispatch,
            executor_ref=f"legacy:{predecessor_dispatch.attempt_id}",
            observations=predecessor_observations,
        )

    assert duplicate.disposition is TaskMutationDisposition.NOOP
    assert pending.disposition is TaskMutationDisposition.NOOP
    assert resolved.disposition is TaskMutationDisposition.NOOP
    assert lost.disposition is TaskMutationDisposition.NOOP
    assert lost_claim.value.reason == "OUTBOX_CLAIM_LOST"
    assert _task_authority_dump(database) == authority_before
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before
    assert store.get_task(successor_id, _scope()) == successor_before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_two_store_connections_allow_one_successor_winner(tmp_path: Path) -> None:
    database, first_store, first_executor, first_core, predecessor, event, digest = (
        _successor_fixture(tmp_path, "successor-race.sqlite")
    )
    second_store = SqliteTaskStore(database)
    second_executor = _Executor()
    second_core = PersistentTaskCore(second_store, second_executor)
    first_command, first_grant = _successor_command(
        predecessor,
        event,
        result_sha256=digest,
        command_id="command-successor-race-one",
    )
    second_command, second_grant = _successor_command(
        predecessor,
        event,
        result_sha256=digest,
        command_id="command-successor-race-two",
    )
    predecessor_before = _predecessor_dump(database, predecessor.task_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(
                first_core.execute,
                first_command,
                first_grant,
                context=_context(tmp_path),
                now=NOW,
            ),
            pool.submit(
                second_core.execute,
                second_command,
                second_grant,
                context=_context(tmp_path),
                now=NOW,
            ),
        )
        results = tuple(future.result(timeout=10) for future in futures)

    assert sum(result.ok for result in results) == 1
    loser = next(result for result in results if not result.ok)
    assert loser.error is not None
    assert loser.error.reason == "TASK_SUCCESSOR_PRECONDITION_CONFLICT"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE predecessor_task_id=?",
            (predecessor.task_id,),
        ).fetchone() == (1,)
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before
    assert first_executor.dispatches == []
    assert second_executor.dispatches == []
    SqliteTaskStore(database)


@pytest.mark.parametrize(
    "failpoint",
    [
        "successor.before_ids",
        "successor.after_command",
        "successor.after_task",
        "successor.after_attempt",
        "successor.after_event",
        "successor.after_outbox",
    ],
)
def test_successor_failpoints_roll_back_and_preserve_predecessor(
    tmp_path: Path, failpoint: str
) -> None:
    database, seed, executor, _core, predecessor, event, digest = (
        _successor_fixture(tmp_path, f"{failpoint}.sqlite")
    )
    enabled = False

    def fail(name: str) -> None:
        if enabled and name == failpoint:
            raise RuntimeError(name)

    store = SqliteTaskStore(database, failpoint=fail)
    core = PersistentTaskCore(store, executor)
    command, grant = _successor_command(
        predecessor,
        event,
        result_sha256=digest,
        command_id=f"command-{failpoint}",
    )
    before = _database_dump(database)
    predecessor_before = _predecessor_dump(database, predecessor.task_id)
    enabled = True

    with pytest.raises(RuntimeError, match=failpoint):
        core.execute(command, grant, context=_context(tmp_path), now=NOW)

    assert _database_dump(database) == before
    assert _predecessor_dump(database, predecessor.task_id) == predecessor_before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    assert seed.get_task(predecessor.task_id, _scope()) == predecessor
    SqliteTaskStore(database)


@pytest.mark.asyncio
async def test_adjustment_admission_replay_conflict_and_final_event_keep_v5(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    create = _create(tmp_path)
    created = core.execute(
        create.envelope,
        create.authorization,
        context=create.context,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert created.ok and created.result is not None
    assert await core.drain_outbox_once(worker_id="dispatch") is True
    task_id = str(created.result["task_id"])
    command, grant = _adjust(task_id, "Move the museum visit to 09:30.")

    admitted = core.execute(
        command,
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    replay = core.execute(
        replace(command, request_id="request-adjust-replay"),
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert admitted.ok and admitted.result is not None
    assert admitted.result["adjustment_state"] == "pending"
    assert replay.ok and replay.result == admitted.result
    conflict, conflict_grant = _adjust(
        task_id,
        "Delete the itinerary.",
        command_id=command.command_id,
        request_id="request-adjust-conflict",
    )
    rejected_conflict = core.execute(
        conflict,
        conflict_grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert not rejected_conflict.ok
    assert rejected_conflict.error is not None
    assert rejected_conflict.error.reason == "IDEMPOTENCY_CONFLICT"

    requested = [
        event
        for event in store.events(task_id, _scope(), after_seq=-1)
        if event.event_type == "task.adjust_requested"
    ]
    assert len(requested) == 1
    assert dict(requested[0].details) == {"command_id": command.command_id}
    assert "09:30" not in json.dumps(requested[0].to_dict())
    assert admitted.extensions["live_voice.command"] == {
        "disposition": "accepted",
        "admission_event_id": requested[0].event_id,
        "settlement_event_id": None,
    }

    assert await core.drain_outbox_once(worker_id="adjust") is True
    final = core.execute(
        replace(command, request_id="request-adjust-final-replay"),
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert final.ok and final.result is not None
    assert final.result["adjustment_state"] == "applied"
    assert final.result["reason"] is None
    adjustment_events = [
        event
        for event in store.events(task_id, _scope(), after_seq=-1)
        if event.event_type.startswith("task.adjust_")
    ]
    assert [event.event_type for event in adjustment_events] == [
        "task.adjust_requested",
        "task.adjust_applied",
    ]
    assert final.extensions["live_voice.command"] == {
        "disposition": "applied",
        "admission_event_id": adjustment_events[0].event_id,
        "settlement_event_id": adjustment_events[1].event_id,
    }
    assert all(
        event.producer == "task_core.control"
        and event.causation_id == command.command_id
        and "09:30" not in json.dumps(event.to_dict())
        for event in adjustment_events
    )
    assert executor.adjustments == [command.command_id]
    assert executor.adjustment_settlements == [
        TaskAdjustmentSettlement(TaskAdjustmentState.APPLIED, False)
    ]
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()[0]
            == "5"
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "task_adjustments" not in tables

    artifact_path = tmp_path / "adjusted-final.txt"
    artifact_path.write_text("museum at 09:30\n", encoding="utf-8")
    artifact = TaskResultArtifact(
        relative_path="adjusted-final.txt",
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
    )
    attempt = store.get_attempt(str(created.result["attempt_id"]))
    assert attempt.executor_ref is not None
    store.apply_observations(
        (
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=attempt.executor_id,
                executor_ref=attempt.executor_ref,
                task_id=task_id,
                attempt_id=attempt.attempt_id,
                source_event_id="executor-adjusted-terminal",
                source_seq=2,
                attempt_state=FormalAttemptState.TERMINAL,
                attempt_outcome=TerminalOutcome.COMPLETED,
                occurred_at=utc_now(),
                raw_status="completed",
                result_text="museum at 09:30",
                result_artifacts=(artifact,),
            ),
        )
    )
    events = store.events(task_id, _scope(), after_seq=-1)
    event_types = [event.event_type for event in events]
    assert event_types.index("task.adjust_applied") < event_types.index("task.terminal")
    availability, result, _reason = store.task_result(task_id, _scope())
    assert availability is TaskResultAvailability.AVAILABLE
    assert result is not None and result.result_text == "museum at 09:30"


@pytest.mark.parametrize("malformed_mode", ["result", "raised"])
@pytest.mark.asyncio
async def test_malformed_executor_adjustment_reason_is_canonicalized_before_store(
    tmp_path: Path,
    malformed_mode: str,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    create = _create(tmp_path)
    created = core.execute(
        create.envelope,
        create.authorization,
        context=create.context,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert created.ok and created.result is not None
    assert await core.drain_outbox_once(worker_id="dispatch") is True
    task_id = str(created.result["task_id"])
    command, grant = _adjust(task_id, "Move the museum visit to 09:30.")
    admitted = core.execute(
        command,
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert admitted.ok
    executor.adjustment_state = TaskAdjustmentState.REJECTED
    if malformed_mode == "result":
        executor.adjustment_reason = "not applicable"
    else:
        executor.adjustment_error = FormalTaskViolation(
            "not applicable",
            "custom Executor returned malformed authority evidence",
            ErrorCode.PROTOCOL_VIOLATION,
        )

    assert await core.drain_outbox_once(worker_id="malformed-adjust") is True

    events = [
        event
        for event in store.events(task_id, _scope(), after_seq=-1)
        if event.event_type.startswith("task.adjust_")
    ]
    assert [event.event_type for event in events] == [
        "task.adjust_requested",
        "task.adjust_rejected",
    ]
    assert dict(events[-1].details) == {
        "command_id": command.command_id,
        "reason": "TASK_ADJUSTMENT_RESULT_INVALID",
    }
    final = core.execute(
        replace(command, request_id="request-adjust-rejected-replay"),
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert not final.ok and final.error is not None
    assert final.error.reason == "TASK_ADJUSTMENT_RESULT_INVALID"
    assert final.extensions["live_voice.command"] == {
        "disposition": "rejected",
        "admission_event_id": events[0].event_id,
        "settlement_event_id": events[1].event_id,
    }
    assert "not applicable" not in json.dumps([event.to_dict() for event in events])
    assert executor.adjustment_settlements == [
        TaskAdjustmentSettlement(TaskAdjustmentState.REJECTED, False)
    ]
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            "SELECT state, last_error FROM outbox WHERE command_id=?",
            (command.command_id,),
        ).fetchone()
    assert outbox == ("delivered", "TASK_ADJUSTMENT_RESULT_INVALID")


@pytest.mark.asyncio
async def test_terminal_fence_rejects_pending_adjustment_without_executor_effect(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    create = _create(tmp_path)
    created = core.execute(
        create.envelope,
        create.authorization,
        context=create.context,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert created.ok and created.result is not None
    await core.drain_outbox_once(worker_id="dispatch")
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    command, grant = _adjust(task_id, "Add an unsafe late change.")
    admitted = core.execute(
        command,
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert admitted.ok
    attempt = store.get_attempt(attempt_id)
    artifact_path = tmp_path / "final.txt"
    artifact_path.write_text("immutable\n", encoding="utf-8")
    artifact = TaskResultArtifact(
        relative_path="final.txt",
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
    )
    terminal = ExecutorObservation(
        resolution=ExecutorResolution.KNOWN,
        executor_id=attempt.executor_id,
        executor_ref=attempt.executor_ref,
        task_id=task_id,
        attempt_id=attempt_id,
        source_event_id="executor-terminal",
        source_seq=2,
        attempt_state=FormalAttemptState.TERMINAL,
        attempt_outcome=TerminalOutcome.COMPLETED,
        occurred_at=utc_now(),
        raw_status="completed",
        result_text="immutable result",
        result_artifacts=(artifact,),
    )
    store.apply_observations((terminal,))

    replay = core.execute(
        replace(command, request_id="request-terminal-replay"),
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert not replay.ok and replay.error is not None
    assert replay.error.reason == "TASK_TERMINAL_BEFORE_ADJUSTMENT"
    events = store.events(task_id, _scope(), after_seq=-1)
    types = [event.event_type for event in events]
    assert types.index("task.adjust_rejected") < types.index("task.terminal")
    requested_event = next(
        event for event in events if event.event_type == "task.adjust_requested"
    )
    rejected_event = next(
        event for event in events if event.event_type == "task.adjust_rejected"
    )
    assert replay.extensions["live_voice.command"] == {
        "disposition": "conflict",
        "admission_event_id": requested_event.event_id,
        "settlement_event_id": rejected_event.event_id,
    }
    assert executor.adjustments == []
    result_state, result, _reason = store.task_result(task_id, _scope())
    assert result_state is TaskResultAvailability.AVAILABLE
    assert result is not None and result.result_text == "immutable result"


@pytest.mark.asyncio
async def test_two_store_connections_serialize_same_and_distinct_adjustments(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    first_store = SqliteTaskStore(database)
    executor = _Executor()
    first_core = PersistentTaskCore(first_store, executor)
    create = _create(tmp_path)
    created = first_core.execute(
        create.envelope,
        create.authorization,
        context=create.context,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert created.ok and created.result is not None
    dispatch = first_store.claim_outbox("dispatch")
    assert dispatch is not None
    first_store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    second_store = SqliteTaskStore(database)
    second_core = PersistentTaskCore(second_store, executor)
    task_id = str(created.result["task_id"])
    same_command, same_grant = _adjust(task_id, "Keep lunch vegetarian.")

    def submit_same(core: PersistentTaskCore, request_id: str):
        return core.execute(
            replace(same_command, request_id=request_id),
            same_grant,
            now=NOW,
            current_background_session_id="session-1",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        same_results = tuple(
            pool.map(
                lambda args: submit_same(*args),
                ((first_core, "same-a"), (second_core, "same-b")),
            )
        )
    assert all(result.ok for result in same_results)
    same_events = [
        event
        for event in first_store.events(task_id, _scope(), after_seq=-1)
        if event.event_type == "task.adjust_requested"
    ]
    assert len(same_events) == 1

    command_a, grant_a = _adjust(
        task_id,
        "Add a morning walk.",
        command_id="command-adjust-a",
        request_id="distinct-a",
    )
    command_b, grant_b = _adjust(
        task_id,
        "Move dinner later.",
        command_id="command-adjust-b",
        request_id="distinct-b",
    )

    def submit_distinct(args):
        core, command, grant = args
        return core.execute(
            command,
            grant,
            now=NOW,
            current_background_session_id="session-1",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        distinct = tuple(
            pool.map(
                submit_distinct,
                ((first_core, command_a, grant_a), (second_core, command_b, grant_b)),
            )
        )
    assert all(result.ok for result in distinct)
    requested = [
        event
        for event in first_store.events(task_id, _scope(), after_seq=-1)
        if event.event_type == "task.adjust_requested"
    ]
    assert [event.seq for event in requested] == sorted(
        event.seq for event in requested
    )
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT e.seq, o.command_id FROM outbox AS o
            JOIN task_events AS e
              ON e.task_id=o.task_id AND e.attempt_id=o.attempt_id
             AND e.event_type='task.adjust_requested'
             AND e.causation_id=o.command_id
            WHERE o.kind='attempt.adjust' ORDER BY e.seq
            """
        ).fetchall()
    assert [row[0] for row in rows] == [event.seq for event in requested]
    authoritative_command_order = [row[1] for row in rows]
    for index, expected_command_id in enumerate(authoritative_command_order):
        item = first_store.claim_outbox(f"adjust-order-{index}")
        assert item is not None and item.command_id == expected_command_id
        delivery = await executor.adjust(item)
        settlement = first_store.complete_adjustment_outbox(item, delivery)
        await executor.settle_adjustment(item, settlement)
    assert executor.adjustments == authoritative_command_order


def test_task_result_is_three_state_immutable_after_artifact_changes(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "result.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        current_background_session_id=_scope().session_id,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.NOT_READY,
        None,
        "TASK_RESULT_NOT_READY",
    )

    artifact_path = tmp_path / "itinerary.md"
    artifact_bytes = "第二天最早的固定安排是 08:30 早餐。\n".encode()
    artifact_path.write_bytes(artifact_bytes)
    artifact = TaskResultArtifact(
        relative_path="itinerary.md",
        sha256=hashlib.sha256(artifact_bytes).hexdigest(),
    )
    item = store.claim_outbox("result-worker")
    assert item is not None
    observations = _observations(
        item,
        outcome=TerminalOutcome.COMPLETED,
        result_text="三天行程已完成；第二天 08:30 安排早餐。",
        result_artifacts=(artifact,),
    )
    with pytest.raises(FormalTaskViolation) as missing_artifact:
        replace(observations[-1], result_artifacts=())
    assert missing_artifact.value.reason == "INVALID_TASK_RESULT_STATE"
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )

    availability, record, reason = store.task_result(task_id, _scope())
    assert availability is TaskResultAvailability.AVAILABLE
    assert reason == "TASK_RESULT_AVAILABLE"
    assert record is not None and record.artifacts == (artifact,)
    assert store.apply_observations(observations).events == ()
    with pytest.raises(FormalTaskViolation, match="Executor event identity"):
        store.apply_observations(
            (replace(observations[-1], result_text="conflicting result"),)
        )
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            1,
        )

    artifact_path.write_text("tampered", encoding="utf-8")
    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.AVAILABLE,
        record,
        "TASK_RESULT_AVAILABLE",
    )
    artifact_path.unlink()
    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.AVAILABLE,
        record,
        "TASK_RESULT_AVAILABLE",
    )


def test_nul_executor_result_is_rejected_before_any_terminal_store_write(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "nul-result.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        current_background_session_id=_scope().session_id,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    item = store.claim_outbox("nul-result-worker")
    assert item is not None
    observations = _observations(
        item,
        outcome=TerminalOutcome.COMPLETED,
        result_text="safe result",
        result_artifacts=(
            TaskResultArtifact(relative_path="itinerary.md", sha256="a" * 64),
        ),
    )
    object.__setattr__(observations[-1], "result_text", "unsafe\x00result")

    with pytest.raises(FormalTaskViolation) as invalid:
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=observations,
        )
    assert invalid.value.reason == "INVALID_TASK_RESULT_TEXT"
    task = store.get_task(task_id, _scope())
    assert task is not None
    assert task.state is FormalTaskState.ACCEPTED
    assert task.outcome is None
    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.NOT_READY,
        None,
        "TASK_RESULT_NOT_READY",
    )
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM task_events WHERE event_type='task.terminal'"
        ).fetchone() == (0,)


def test_task_result_record_rejects_nul_and_canonicalizes_utc_offset() -> None:
    artifact = TaskResultArtifact(
        relative_path="itinerary.md",
        sha256="a" * 64,
    )
    with pytest.raises(FormalTaskViolation) as invalid_text:
        TaskResultRecord(
            task_id="task-1",
            attempt_id="attempt-1",
            source_event_id="source-1",
            result_text="unsafe\x00result",
            artifacts=(artifact,),
            completed_at="2030-01-01T08:00:00+08:00",
        )
    assert invalid_text.value.reason == "INVALID_TASK_RESULT_TEXT"

    with pytest.raises(FormalTaskViolation) as invalid_identity:
        TaskResultRecord(
            task_id="task-1",
            attempt_id="attempt-1",
            source_event_id="source\x00id",
            result_text="safe result",
            artifacts=(artifact,),
            completed_at="2030-01-01T00:00:00Z",
        )
    assert invalid_identity.value.reason == "INVALID_TASK_RESULT_IDENTITY"

    record = TaskResultRecord(
        task_id="task-1",
        attempt_id="attempt-1",
        source_event_id="source-1",
        result_text="safe result",
        artifacts=(artifact,),
        completed_at="2030-01-01T08:00:00+08:00",
    )
    assert record.completed_at == "2030-01-01T00:00:00Z"

    astral = TaskResultRecord(
        task_id="😀" * 256,
        attempt_id="attempt-astral",
        source_event_id="source-astral",
        result_text="😀" * 20_000,
        artifacts=(
            TaskResultArtifact(
                relative_path=f"{'😀' * 300}.md",
                sha256="b" * 64,
            ),
        ),
        completed_at="2030-01-01T00:00:00Z",
    )
    assert len(astral.result_text) == 20_000

    with pytest.raises(FormalTaskViolation) as oversized_identity:
        replace(record, task_id="😀" * 257)
    assert oversized_identity.value.reason == "INVALID_TASK_RESULT_IDENTITY"


def _terminal_task(
    tmp_path: Path,
    *,
    outcome: TerminalOutcome = TerminalOutcome.CANCELLED,
) -> tuple[SqliteTaskStore, _Executor, PersistentTaskCore, str, str]:
    store = SqliteTaskStore(tmp_path / "retry.sqlite")
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
    item = store.claim_outbox("terminal-fixture")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item, outcome=outcome),
    )
    return store, executor, core, item.task_id, item.attempt_id


def _formal_cancel_then_retry(
    tmp_path: Path,
    *,
    terminalize_retry: bool = False,
) -> tuple[
    Path,
    SqliteTaskStore,
    _Executor,
    PersistentTaskCore,
    CommandEnvelope,
    TaskAuthorizationGrant,
    ResultEnvelope,
    str,
    str,
    PersistentTaskEvent,
    PersistentTaskEvent | None,
]:
    """Build a formal cancel settlement followed by a live retry epoch."""

    database = tmp_path / "historical-cancel-retry.sqlite"
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
    dispatch_a = store.claim_outbox("historical-cancel-dispatch-a")
    assert dispatch_a is not None
    store.complete_outbox(
        dispatch_a,
        executor_ref=f"legacy:{dispatch_a.attempt_id}",
        observations=_observations(dispatch_a),
    )

    cancellation = _cancel(dispatch_a.task_id)
    accepted = core.execute(
        cancellation.envelope,
        cancellation.authorization,
        now=NOW,
    )
    assert accepted.ok and accepted.result is not None
    assert accepted.result["applied"] is False
    cancel_a = store.claim_outbox("historical-cancel-delivery-a")
    assert cancel_a is not None and cancel_a.kind is OutboxKind.ATTEMPT_CANCEL
    store.complete_outbox(
        cancel_a,
        executor_ref=f"legacy:{dispatch_a.attempt_id}",
        observations=_observations(cancel_a, outcome=TerminalOutcome.CANCELLED),
    )
    events_a = store.events(
        dispatch_a.task_id,
        _scope(),
        attempt_id=dispatch_a.attempt_id,
    )
    settlement_a = events_a[-1]
    assert settlement_a.event_type == "task.terminal"
    assert settlement_a.outcome == TerminalOutcome.CANCELLED.value

    retry, grant = _retry(
        dispatch_a.task_id,
        dispatch_a.attempt_id,
        TerminalOutcome.CANCELLED,
        2,
    )
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    attempt_b = str(retried.result["attempt_id"])
    dispatch_b = store.claim_outbox("historical-cancel-dispatch-b")
    assert dispatch_b is not None
    assert dispatch_b.attempt_id == attempt_b
    store.complete_outbox(
        dispatch_b,
        executor_ref=f"legacy:{attempt_b}",
        observations=_observations(dispatch_b),
    )
    settlement_b: PersistentTaskEvent | None = None
    if terminalize_retry:
        cancel_b_command, cancel_b_grant = _wave2_command(
            dispatch_a.task_id,
            "task.cancel",
            {},
            command_id="command-cancel-b",
        )
        cancel_b_result = core.execute(cancel_b_command, cancel_b_grant, now=NOW)
        assert cancel_b_result.ok and cancel_b_result.result is not None
        cancel_b = store.claim_outbox("historical-cancel-delivery-b")
        assert cancel_b is not None and cancel_b.kind is OutboxKind.ATTEMPT_CANCEL
        assert cancel_b.attempt_id == attempt_b
        store.complete_outbox(
            cancel_b,
            executor_ref=f"legacy:{attempt_b}",
            observations=_observations(cancel_b, outcome=TerminalOutcome.CANCELLED),
        )
        settlement_b = store.events(
            dispatch_a.task_id,
            _scope(),
            attempt_id=attempt_b,
        )[-1]
        assert settlement_b.event_type == "task.terminal"
        assert settlement_b.outcome == TerminalOutcome.CANCELLED.value

    return (
        database,
        store,
        executor,
        core,
        retry,
        grant,
        retried,
        dispatch_a.attempt_id,
        attempt_b,
        settlement_a,
        settlement_b,
    )


def test_historical_cancel_settlement_reopens_and_replays_after_retry_running(
    tmp_path: Path,
) -> None:
    (
        database,
        store,
        executor,
        _core,
        retry,
        grant,
        retried,
        attempt_a,
        attempt_b,
        settlement_a,
        settlement_b,
    ) = _formal_cancel_then_retry(tmp_path)
    assert settlement_b is None
    current = store.get_task(str(retried.result["task_id"]), _scope())
    assert current.attempt_id == attempt_b
    assert current.state is FormalTaskState.RUNNING
    assert store.get_attempt(attempt_a).outcome is TerminalOutcome.CANCELLED
    assert retried.extensions["live_voice.command"]["settlement_event_id"] != (
        settlement_a.event_id
    )
    before = _database_dump(database)
    executor_effects = (
        tuple(executor.dispatches),
        tuple(executor.cancels),
        tuple(executor.retry_readiness_calls),
    )

    reopened = SqliteTaskStore(database)
    replay = PersistentTaskCore(reopened, executor).execute(
        replace(retry, request_id="request-retry-2-replay-after-running"),
        grant,
        context=_context(tmp_path),
        now=NOW,
    )

    assert replay.ok and replay.result == retried.result
    assert replay.command_id == retried.command_id
    assert replay.observed_at == retried.observed_at
    assert replay.extensions == retried.extensions
    assert reopened.get_task(current.task_id, _scope()) == current
    assert reopened.get_attempt(attempt_a).outcome is TerminalOutcome.CANCELLED
    assert reopened.get_attempt(attempt_b).state is FormalAttemptState.RUNNING
    assert _database_dump(database) == before
    assert (
        tuple(executor.dispatches),
        tuple(executor.cancels),
        tuple(executor.retry_readiness_calls),
    ) == executor_effects


@pytest.mark.parametrize(
    ("delivery_count", "last_error"),
    [
        (0, None),
        (0, "FORGED_CANCEL_FAILURE"),
        (42, "FORGED_CANCEL_FAILURE"),
    ],
)
def test_historical_cancel_settlement_rejects_impossible_delivered_outbox(
    tmp_path: Path,
    delivery_count: int,
    last_error: str | None,
) -> None:
    (
        database,
        _store,
        executor,
        _core,
        _retry_command,
        _retry_grant,
        _retried,
        attempt_a,
        _attempt_b,
        _settlement_a,
        _settlement_b,
    ) = _formal_cancel_then_retry(tmp_path)
    with sqlite3.connect(database) as connection:
        canonical = connection.execute(
            """SELECT state, delivery_count, last_error
               FROM outbox WHERE attempt_id=? AND kind=?""",
            (attempt_a, OutboxKind.ATTEMPT_CANCEL.value),
        ).fetchone()
        assert canonical == (OutboxState.DELIVERED.value, 1, None)
        updated = connection.execute(
            """UPDATE outbox SET state=?, delivery_count=?, last_error=?
               WHERE attempt_id=? AND kind=?""",
            (
                OutboxState.DELIVERED.value,
                delivery_count,
                last_error,
                attempt_a,
                OutboxKind.ATTEMPT_CANCEL.value,
            ),
        )
        assert updated.rowcount == 1
        connection.commit()
    before = _database_authority_bytes(database)
    executor_effects = (
        tuple(executor.dispatches),
        tuple(executor.cancels),
        tuple(executor.retry_readiness_calls),
    )

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert _database_authority_bytes(database) == before
    assert (
        tuple(executor.dispatches),
        tuple(executor.cancels),
        tuple(executor.retry_readiness_calls),
    ) == executor_effects


@pytest.mark.parametrize(
    "corruption",
    [
        "cross_epoch_settlement",
        "settlement_cause",
        "settlement_order",
        "settlement_attempt",
        "missing_cancel_request",
        "missing_attempt_source",
        "missing_cancel_outbox",
        "result_flags",
    ],
)
def test_historical_cancel_settlement_rejects_cross_epoch_or_incomplete_authority(
    tmp_path: Path,
    corruption: str,
) -> None:
    (
        database,
        _store,
        executor,
        _core,
        _retry_command,
        _retry_grant,
        _retried,
        attempt_a,
        attempt_b,
        settlement_a,
        settlement_b,
    ) = _formal_cancel_then_retry(tmp_path, terminalize_retry=True)
    assert settlement_b is not None
    with sqlite3.connect(database) as connection:
        if corruption == "cross_epoch_settlement":
            row = connection.execute(
                "SELECT result_json FROM commands WHERE command_id='command-cancel'"
            ).fetchone()
            assert row is not None
            payload = json.loads(row[0])
            payload["observed_at"] = settlement_b.occurred_at
            payload["extensions"]["live_voice.command"]["settlement_event_id"] = (
                settlement_b.event_id
            )
            connection.execute(
                "UPDATE commands SET result_json=? WHERE command_id='command-cancel'",
                (json.dumps(payload, sort_keys=True),),
            )
        elif corruption == "settlement_cause":
            connection.execute(
                "UPDATE task_events SET causation_id='foreign-cause' WHERE event_id=?",
                (settlement_a.event_id,),
            )
        elif corruption == "settlement_order":
            attempt_terminal = connection.execute(
                """SELECT event_id, seq FROM task_events
                   WHERE attempt_id=? AND event_type='attempt.terminal'""",
                (attempt_a,),
            ).fetchone()
            assert attempt_terminal is not None
            connection.execute(
                "UPDATE task_events SET seq=-1 WHERE event_id=?",
                (attempt_terminal[0],),
            )
            connection.execute(
                "UPDATE task_events SET seq=? WHERE event_id=?",
                (attempt_terminal[1], settlement_a.event_id),
            )
            connection.execute(
                "UPDATE task_events SET seq=? WHERE event_id=?",
                (settlement_a.seq, attempt_terminal[0]),
            )
        elif corruption == "settlement_attempt":
            connection.execute(
                "UPDATE task_events SET attempt_id=? WHERE event_id=?",
                (attempt_b, settlement_a.event_id),
            )
        elif corruption == "missing_cancel_request":
            connection.execute(
                """DELETE FROM task_events
                   WHERE attempt_id=? AND event_type='task.cancel_requested'""",
                (attempt_a,),
            )
        elif corruption == "missing_attempt_source":
            terminal_source = connection.execute(
                """SELECT source_event_id FROM task_events
                   WHERE attempt_id=? AND event_type='attempt.terminal'""",
                (attempt_a,),
            ).fetchone()
            assert terminal_source is not None
            connection.execute(
                "DELETE FROM executor_events WHERE source_event_id=?",
                (terminal_source[0],),
            )
        elif corruption == "missing_cancel_outbox":
            connection.execute(
                """DELETE FROM outbox
                   WHERE attempt_id=? AND kind=?""",
                (attempt_a, OutboxKind.ATTEMPT_CANCEL.value),
            )
        else:
            row = connection.execute(
                "SELECT result_json FROM commands WHERE command_id='command-cancel'"
            ).fetchone()
            assert row is not None
            payload = json.loads(row[0])
            payload["result"]["applied"] = False
            connection.execute(
                "UPDATE commands SET result_json=? WHERE command_id='command-cancel'",
                (json.dumps(payload, sort_keys=True),),
            )
        connection.commit()
    before = _database_dump(database)
    executor_effects = (
        tuple(executor.dispatches),
        tuple(executor.cancels),
        tuple(executor.retry_readiness_calls),
    )

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before
    assert (
        tuple(executor.dispatches),
        tuple(executor.cancels),
        tuple(executor.retry_readiness_calls),
    ) == executor_effects


@pytest.mark.parametrize(
    ("outcome", "reason"),
    (
        (TerminalOutcome.CANCELLED, "TASK_CANCELLED"),
        (TerminalOutcome.FAILED, "TASK_FAILED"),
        (TerminalOutcome.INTERRUPTED, "TASK_INTERRUPTED"),
    ),
)
def test_terminal_noncompleted_task_result_is_stably_unavailable(
    tmp_path: Path,
    outcome: TerminalOutcome,
    reason: str,
) -> None:
    store, _executor, _core, task_id, _attempt_id = _terminal_task(
        tmp_path,
        outcome=outcome,
    )

    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.UNAVAILABLE,
        None,
        reason,
    )


def test_retry_a_to_b_is_atomic_and_preserves_exact_history(tmp_path: Path) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    context_b = replace(_context(tmp_path), revision_value="clean-revision-b")

    result = core.execute(retry, grant, context=context_b, now=NOW)

    assert result.ok and result.result is not None
    assert result.result["previous_attempt_id"] == attempt_a
    assert result.result["attempt_number"] == 2
    assert result.result["applied"] is True
    attempt_b = str(result.result["attempt_id"])
    assert attempt_b != attempt_a
    assert store.get_attempt(attempt_a).to_dict()["outcome"] == "cancelled"
    assert store.get_attempt(attempt_a).attempt_number == 1
    assert store.get_attempt(attempt_b).attempt_number == 2
    task = store.get_task(task_id, _scope())
    assert task.attempt_id == attempt_b
    assert task.state is FormalTaskState.ACCEPTED
    assert task.spec.context.revision_value == "clean-revision-b"
    assert executor.retry_readiness_calls == [attempt_a]
    history = store.events(task_id, _scope())
    boundary = history[-1]
    assert boundary.event_type == "task.retry_accepted"
    assert boundary.attempt_id == attempt_b
    assert result.extensions == {
        "live_voice.command": {
            "disposition": "applied",
            "admission_event_id": boundary.event_id,
            "settlement_event_id": boundary.event_id,
        },
        "live_voice.store": {"durability": "sqlite_outbox"},
    }
    assert dict(boundary.details) == {
        "command_id": retry.command_id,
        "retry_of_attempt_id": attempt_a,
        "previous_outcome": "cancelled",
        "attempt_number": 2,
    }
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=20)
    assert snapshot.start_seq == boundary.seq
    assert snapshot.events == (boundary,)


def test_new_retry_admission_requires_cancelled_predecessor_before_executor(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_id = _terminal_task(
        tmp_path, outcome=TerminalOutcome.COMPLETED
    )
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.COMPLETED, 2)
    database = tmp_path / "retry.sqlite"
    before = _task_authority_dump(database)

    rejected = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"
    assert rejected.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (retry.command_id,),
        ).fetchone() == (1,)
    assert executor.retry_readiness_calls == []
    replay = PersistentTaskCore(SqliteTaskStore(database), executor).execute(
        replace(retry, request_id="request-retry-ineligible-replay"),
        grant,
        context=_context(tmp_path),
        now=NOW,
    )
    assert replay.error == rejected.error
    assert replay.extensions == rejected.extensions
    assert executor.retry_readiness_calls == []


def test_retry_preserves_stable_task_and_project_identity_with_zero_effects(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    before = store.counts()

    wrong_project = core.execute(
        retry,
        grant,
        context=replace(
            _context(tmp_path),
            stable_id="project-other",
            revision_value="clean-revision-b",
        ),
        now=NOW,
    )

    assert not wrong_project.ok and wrong_project.error is not None
    assert wrong_project.error.reason == "TASK_RETRY_CONTEXT_IDENTITY_MISMATCH"
    assert store.counts() == before
    assert executor.retry_readiness_calls == []

    authority = store.read_retry_authority(retry)
    assert isinstance(authority, TaskRetryAuthoritySnapshot)
    with pytest.raises(FormalTaskViolation) as replaced_spec:
        store.retry(
            retry,
            replace(authority.task.spec, instruction="replacement instruction"),
            authority,
            observed_at=NOW,
        )

    assert replaced_spec.value.reason == "TASK_RETRY_SPEC_MISMATCH"
    assert store.counts() == before


def test_retry_rejects_foreign_correlation_before_readiness_and_preserves_lineage(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.CANCELLED,
        2,
        correlation_id="correlation-foreign",
    )
    before = store.counts()
    before_dump = _database_dump(store.database_path)
    before_bytes = store.database_path.read_bytes()

    rejected = core.execute(
        retry,
        grant,
        context=replace(_context(tmp_path), revision_value="clean-revision-b"),
        now=NOW,
    )

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_RETRY_PRECONDITION_STALE"
    assert rejected.error.code is ErrorCode.STALE
    assert store.counts() == before
    assert _database_dump(store.database_path) == before_dump
    assert store.database_path.read_bytes() == before_bytes
    assert executor.retry_readiness_calls == []
    assert executor.dispatches == []
    assert executor.cancels == []
    authority = core.read_current_retry_authority(scope=_scope(), task_id=task_id)
    assert authority.task.correlation_id == "correlation-1"
    assert authority.precondition.previous_attempt_id == attempt_a


@pytest.mark.parametrize(
    "corruption",
    ["wrong_task", "wrong_ordinal", "nonterminal", "outcome_mismatch"],
)
def test_retry_event_authority_requires_exact_durable_predecessor(
    tmp_path: Path, corruption: str
) -> None:
    store, _executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    attempt_b = str(retried.result["attempt_id"])
    database = store.database_path

    if corruption == "wrong_task":
        foreign_invocation = _create(tmp_path, identity_suffix="-foreign-lineage")
        foreign = core.execute(
            foreign_invocation.envelope,
            foreign_invocation.authorization,
            context=foreign_invocation.context,
            now=NOW,
        )
        assert foreign.ok and foreign.result is not None
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                """
                SELECT details_json FROM task_events
                WHERE task_id=? AND attempt_id=? AND event_type='task.retry_accepted'
                """,
                (task_id, attempt_b),
            ).fetchone()
            assert row is not None
            details = json.loads(row[0])
            details["retry_of_attempt_id"] = str(foreign.result["attempt_id"])
            connection.execute(
                """
                UPDATE task_events SET details_json=?
                WHERE task_id=? AND attempt_id=? AND event_type='task.retry_accepted'
                """,
                (json.dumps(details, sort_keys=True), task_id, attempt_b),
            )
    else:
        with sqlite3.connect(database) as connection:
            if corruption == "wrong_ordinal":
                connection.execute(
                    "UPDATE attempts SET attempt_number=3 WHERE attempt_id=?",
                    (attempt_a,),
                )
            elif corruption == "nonterminal":
                connection.execute(
                    """
                    UPDATE attempts SET state='running', outcome=NULL
                    WHERE attempt_id=?
                    """,
                    (attempt_a,),
                )
            else:
                connection.execute(
                    "UPDATE attempts SET outcome='completed' WHERE attempt_id=?",
                    (attempt_a,),
                )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as rejected:
        store.event_authority_snapshot(task_id, _scope(), max_events=20)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before


def test_retry_exact_replay_skips_readiness_and_conflict_has_zero_effects(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    context = replace(_context(tmp_path), revision_value="clean-revision-b")
    first = core.execute(retry, grant, context=context, now=NOW)
    assert first.ok and first.result is not None
    before = store.counts()
    calls = list(executor.retry_readiness_calls)

    replay = core.execute(retry, grant, context=context, now=NOW)
    conflicting_retry, conflicting_grant = _retry(
        task_id,
        "different-attempt",
        TerminalOutcome.CANCELLED,
        2,
        command_id=retry.command_id,
    )
    conflict = core.execute(
        conflicting_retry,
        conflicting_grant,
        context=replace(context, revision_value="different-clean-revision"),
        now=NOW,
    )
    correlation_conflict, correlation_grant = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.CANCELLED,
        2,
        command_id=retry.command_id,
        correlation_id="correlation-foreign",
    )
    correlation_rejected = core.execute(
        correlation_conflict,
        correlation_grant,
        context=context,
        now=NOW,
    )

    assert replay.ok and replay.result == first.result
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "IDEMPOTENCY_CONFLICT"
    assert not correlation_rejected.ok and correlation_rejected.error is not None
    assert correlation_rejected.error.reason == "IDEMPOTENCY_CONFLICT"
    assert store.counts() == before
    assert executor.retry_readiness_calls == calls


def test_concurrent_exact_retry_across_store_instances_has_one_successor(
    tmp_path: Path,
) -> None:
    store, executor_a, core_a, task_id, attempt_a = _terminal_task(tmp_path)
    store_b = SqliteTaskStore(store.database_path)
    executor_b = _Executor()
    core_b = PersistentTaskCore(store_b, executor_b)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    context = replace(_context(tmp_path), revision_value="clean-revision-b")
    before = store.counts()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(
            pool.submit(core.execute, retry, grant, context=context, now=NOW)
            for core in (core_a, core_b)
        )
        results = tuple(future.result() for future in futures)

    assert all(result.ok and result.result is not None for result in results)
    assert results[0].result == results[1].result
    assert results[0].result is not None
    successor_id = str(results[0].result["attempt_id"])
    after = store.counts()
    assert after == {
        **before,
        "commands": before["commands"] + 1,
        "attempts": before["attempts"] + 1,
        "task_events": before["task_events"] + 1,
        "outbox": before["outbox"] + 1,
    }
    assert store.get_task(task_id, _scope()).attempt_id == successor_id
    assert [
        event
        for event in store.events(task_id, _scope())
        if event.event_type == "task.retry_accepted"
    ][0].attempt_id == successor_id
    assert sum(
        attempt_id == attempt_a
        for attempt_id in (
            *executor_a.retry_readiness_calls,
            *executor_b.retry_readiness_calls,
        )
    ) in {1, 2}


def test_concurrent_distinct_retries_from_same_epoch_apply_one_and_stale_one(
    tmp_path: Path,
) -> None:
    store, _executor_a, core_a, task_id, attempt_a = _terminal_task(tmp_path)
    core_b = PersistentTaskCore(SqliteTaskStore(store.database_path), _Executor())
    retry_a, grant_a = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.CANCELLED,
        2,
        command_id="command-retry-left",
    )
    retry_b, grant_b = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.CANCELLED,
        2,
        command_id="command-retry-right",
    )
    context = replace(_context(tmp_path), revision_value="clean-revision-b")
    before = store.counts()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(core_a.execute, retry_a, grant_a, context=context, now=NOW),
            pool.submit(core_b.execute, retry_b, grant_b, context=context, now=NOW),
        )
        results = tuple(future.result() for future in futures)

    successes = tuple(result for result in results if result.ok)
    failures = tuple(result for result in results if not result.ok)
    assert len(successes) == len(failures) == 1
    assert failures[0].error is not None
    assert failures[0].error.reason == "TASK_RETRY_PRECONDITION_STALE"
    assert failures[0].extensions["live_voice.command"]["disposition"] == "conflict"
    after = store.counts()
    assert after == {
        **before,
        "commands": before["commands"] + 2,
        "attempts": before["attempts"] + 1,
        "task_events": before["task_events"] + 1,
        "outbox": before["outbox"] + 1,
    }
    boundaries = tuple(
        event
        for event in store.events(task_id, _scope())
        if event.event_type == "task.retry_accepted"
    )
    assert len(boundaries) == 1
    assert store.get_task(task_id, _scope()).attempt_id == boundaries[0].attempt_id
    loser_index = results.index(failures[0])
    loser_command = (retry_a, retry_b)[loser_index]
    loser_grant = (grant_a, grant_b)[loser_index]
    replay_executor = _Executor()
    replay = PersistentTaskCore(
        SqliteTaskStore(store.database_path), replay_executor
    ).execute(
        replace(loser_command, request_id="request-retry-race-loser-replay"),
        loser_grant,
        context=context,
        now=NOW,
    )
    assert replay.error == failures[0].error
    assert replay.extensions == failures[0].extensions
    assert replay_executor.retry_readiness_calls == []
    assert store.counts() == after


def test_retry_a_to_b_to_c_then_old_retry_replay_and_fourth_rejection(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry_b, grant_b = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    context_b = replace(_context(tmp_path), revision_value="clean-revision-b")
    result_b = core.execute(retry_b, grant_b, context=context_b, now=NOW)
    assert result_b.ok and result_b.result is not None
    attempt_b = str(result_b.result["attempt_id"])
    item_b = store.claim_outbox("terminal-b")
    assert item_b is not None and item_b.attempt_id == attempt_b
    store.complete_outbox(
        item_b,
        executor_ref=f"legacy:{attempt_b}",
        observations=_observations(item_b, outcome=TerminalOutcome.CANCELLED),
    )
    retry_c, grant_c = _retry(task_id, attempt_b, TerminalOutcome.CANCELLED, 3)
    context_c = replace(_context(tmp_path), revision_value="clean-revision-c")
    result_c = core.execute(retry_c, grant_c, context=context_c, now=NOW)
    assert result_c.ok and result_c.result is not None
    attempt_c = str(result_c.result["attempt_id"])
    item_c = store.claim_outbox("terminal-c")
    assert item_c is not None and item_c.attempt_id == attempt_c
    store.complete_outbox(
        item_c,
        executor_ref=f"legacy:{attempt_c}",
        observations=_observations(item_c, outcome=TerminalOutcome.CANCELLED),
    )
    before = store.counts()
    authority_before = _task_authority_dump(store.database_path)
    readiness_calls = list(executor.retry_readiness_calls)

    replay_b = core.execute(retry_b, grant_b, context=None, now=NOW)
    fourth, fourth_grant = _retry(
        task_id,
        attempt_c,
        TerminalOutcome.CANCELLED,
        3,
        command_id="command-retry-fourth",
    )
    rejected = core.execute(fourth, fourth_grant, context=context_c, now=NOW)

    assert replay_b.ok and replay_b.result == result_b.result
    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_RETRY_LIMIT_EXCEEDED"
    assert _task_authority_dump(store.database_path) == authority_before
    assert store.counts() == {**before, "commands": before["commands"] + 1}
    assert executor.retry_readiness_calls == readiness_calls
    replay_executor = _Executor()
    replay = PersistentTaskCore(
        SqliteTaskStore(store.database_path), replay_executor
    ).execute(
        replace(fourth, request_id="request-retry-fourth-replay"),
        fourth_grant,
        context=None,
        now=NOW,
    )
    assert replay.error == rejected.error
    assert replay.extensions == rejected.extensions
    assert replay_executor.retry_readiness_calls == []
    assert _task_authority_dump(store.database_path) == authority_before
    history = store.events(task_id, _scope())
    boundaries = [
        event for event in history if event.event_type == "task.retry_accepted"
    ]
    assert [event.attempt_id for event in boundaries] == [attempt_b, attempt_c]
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=20)
    assert snapshot.start_seq == boundaries[-1].seq
    assert all(event.attempt_id == attempt_c for event in snapshot.events)
    page_a = store.events(task_id, _scope(), after_seq=-1)
    page_b = store.events(task_id, _scope(), after_seq=boundaries[0].seq - 1)
    page_c = store.events(task_id, _scope(), after_seq=boundaries[1].seq - 1)
    assert page_a == history
    assert page_b[0] == boundaries[0]
    assert page_c[0] == boundaries[1]
    assert store.events(
        task_id,
        _scope(),
        after_seq=boundaries[0].seq - 1,
        attempt_id=attempt_b,
    ) == tuple(event for event in history if event.attempt_id == attempt_b)


def test_current_retry_authority_derives_server_payload_without_side_effects(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    before_dump = _database_dump(store.database_path)
    before_bytes = store.database_path.read_bytes()

    authority = core.read_current_retry_authority(
        scope=_scope(),
        task_id=task_id,
    )

    assert authority.task.task_id == task_id
    assert authority.attempt.attempt_id == attempt_a
    assert authority.precondition.to_dict() == {
        "previous_attempt_id": attempt_a,
        "previous_outcome": TerminalOutcome.CANCELLED.value,
        "attempt_number": 2,
    }
    assert executor.retry_readiness_calls == []
    assert executor.dispatches == []
    assert executor.cancels == []
    assert _database_dump(store.database_path) == before_dump
    assert store.database_path.read_bytes() == before_bytes
    request_asserted = ScopeRef(
        "user-1",
        "project-1",
        "session-1",
        Assurance.REQUEST_ASSERTED,
    )
    with pytest.raises(FormalTaskViolation) as rejected:
        core.read_current_retry_authority(
            scope=request_asserted,
            task_id=task_id,
        )
    assert rejected.value.reason == "TASK_RETRY_AUTHORITY_FACTS_INVALID"
    assert _database_dump(store.database_path) == before_dump
    assert store.database_path.read_bytes() == before_bytes


def test_retry_requires_one_product_request_fingerprint_before_readiness(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    before_dump = _database_dump(store.database_path)
    before_bytes = store.database_path.read_bytes()

    cases = (
        ({}, "TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_REQUIRED"),
        (
            {**retry.extensions, "product.unbound": {"fact": "changed"}},
            "TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_REQUIRED",
        ),
        (
            {
                next(iter(retry.extensions)): {
                    "sha256": "NOT-A-CANONICAL-SHA256",
                }
            },
            "TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_INVALID",
        ),
    )
    for extensions, reason in cases:
        raw = retry.to_dict()
        raw["extensions"] = extensions
        invalid = CommandEnvelope.from_dict(raw)
        result = core.execute(invalid, grant, context=_context(tmp_path), now=NOW)
        assert not result.ok and result.error is not None
        assert result.error.reason == reason

    assert executor.retry_readiness_calls == []
    assert executor.dispatches == []
    assert executor.cancels == []
    assert _database_dump(store.database_path) == before_dump
    assert store.database_path.read_bytes() == before_bytes


def test_negative_retry_ledger_is_not_misreported_as_an_applied_replay(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_id = _terminal_task(
        tmp_path, outcome=TerminalOutcome.COMPLETED
    )
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.COMPLETED, 2)
    rejected = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"
    before = _database_dump(store.database_path)

    replay = SqliteTaskStore(store.database_path).read_applied_retry_replay(
        scope=_scope(),
        command_id=retry.command_id,
        task_id=task_id,
        product_request=_retry_product_request_fingerprint(
            command_id=retry.command_id,
            task_id=task_id,
        ),
    )

    assert replay is None
    assert _database_dump(store.database_path) == before
    assert executor.retry_readiness_calls == []


def _rewrite_retry_as_completed_legacy_fixture(
    database: Path,
    *,
    predecessor_attempt_id: str,
    retry_attempt_id: str,
    legacy_command: CommandEnvelope,
    preserve_current_disposition: bool,
) -> ResultEnvelope:
    """Rewrite a valid cancelled retry into the exact pre-P3-2 completed shape."""

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        executor_rows = connection.execute(
            "SELECT source_event_id, canonical FROM executor_events WHERE attempt_id=?",
            (predecessor_attempt_id,),
        ).fetchall()
        for row in executor_rows:
            canonical = json.loads(row["canonical"])
            if canonical["attempt_state"] == FormalAttemptState.TERMINAL.value:
                canonical["attempt_outcome"] = TerminalOutcome.COMPLETED.value
                connection.execute(
                    "UPDATE executor_events SET canonical=? WHERE source_event_id=?",
                    (canonical_json_bytes(canonical), row["source_event_id"]),
                )
        connection.execute(
            "UPDATE attempts SET outcome=? WHERE attempt_id=?",
            (TerminalOutcome.COMPLETED.value, predecessor_attempt_id),
        )
        connection.execute(
            """UPDATE task_events SET outcome=?
               WHERE attempt_id=? AND event_type IN ('attempt.terminal', 'task.terminal')""",
            (TerminalOutcome.COMPLETED.value, predecessor_attempt_id),
        )
        boundary = connection.execute(
            """SELECT details_json FROM task_events
               WHERE attempt_id=? AND event_type='task.retry_accepted'""",
            (retry_attempt_id,),
        ).fetchone()
        assert boundary is not None
        details = json.loads(boundary["details_json"])
        details["previous_outcome"] = TerminalOutcome.COMPLETED.value
        connection.execute(
            """UPDATE task_events SET details_json=?
               WHERE attempt_id=? AND event_type='task.retry_accepted'""",
            (
                canonical_json_bytes(details).decode("utf-8"),
                retry_attempt_id,
            ),
        )
        command_row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (legacy_command.command_id,),
        ).fetchone()
        assert command_row is not None
        result_payload = json.loads(command_row["result_json"])
        if not preserve_current_disposition:
            result_payload["extensions"] = {
                "live_voice.store": {"durability": "sqlite_outbox"}
            }
        result_bytes = canonical_json_bytes(result_payload)
        connection.execute(
            """UPDATE commands SET fingerprint=?, result_json=?
               WHERE command_id=?""",
            (
                legacy_command.fingerprint(),
                result_bytes.decode("utf-8"),
                legacy_command.command_id,
            ),
        )
        connection.commit()
    return ResultEnvelope.from_dict(json.loads(result_bytes))


def test_historical_completed_retry_replay_survives_reopen_without_new_admission(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry_b_command_id = "command-retry-2"
    retry_b, grant_b = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.CANCELLED,
        2,
        command_id=retry_b_command_id,
    )
    context_b = replace(_context(tmp_path), revision_value="clean-revision-b")
    result_b = core.execute(retry_b, grant_b, context=context_b, now=NOW)
    assert result_b.ok and result_b.result is not None
    item_b = store.claim_outbox("replay-b")
    assert item_b is not None
    store.complete_outbox(
        item_b,
        executor_ref=f"legacy:{item_b.attempt_id}",
        observations=_observations(item_b, outcome=TerminalOutcome.CANCELLED),
    )
    retry_c, grant_c = _retry(task_id, item_b.attempt_id, TerminalOutcome.CANCELLED, 3)
    context_c = replace(_context(tmp_path), revision_value="clean-revision-c")
    result_c = core.execute(retry_c, grant_c, context=context_c, now=NOW)
    assert result_c.ok
    database = store.database_path
    legacy_retry_b, legacy_grant_b = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.COMPLETED,
        2,
        command_id=retry_b_command_id,
    )
    legacy_result_b = _rewrite_retry_as_completed_legacy_fixture(
        database,
        predecessor_attempt_id=attempt_a,
        retry_attempt_id=item_b.attempt_id,
        legacy_command=legacy_retry_b,
        preserve_current_disposition=False,
    )
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT fingerprint, result_json FROM commands WHERE command_id=?",
            (retry_b_command_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == legacy_retry_b.fingerprint()
    assert json.loads(row[1])["extensions"] == {
        "live_voice.store": {"durability": "sqlite_outbox"}
    }
    assert b"live_voice.command" not in row[1].encode("utf-8")
    product_request = _retry_product_request_fingerprint(
        command_id=retry_b_command_id,
        task_id=task_id,
    )
    del retry_c, grant_c, core, executor, store

    reopened = SqliteTaskStore(database)
    restarted_executor = _Executor()
    restarted_core = PersistentTaskCore(reopened, restarted_executor)
    before_dump = _database_dump(database)
    before_bytes = database.read_bytes()

    replay = restarted_core.read_applied_retry_replay(
        scope=_scope(),
        command_id=retry_b_command_id,
        task_id=task_id,
        product_request=product_request,
    )

    assert replay is not None
    assert replay.original_command.command_id == retry_b_command_id
    assert replay.original_command.payload == {
        "previous_attempt_id": attempt_a,
        "previous_outcome": TerminalOutcome.COMPLETED.value,
        "attempt_number": 2,
    }
    assert replay.original_result == legacy_result_b
    assert replay.precondition.previous_attempt_id == attempt_a
    assert replay.precondition.attempt_number == 2
    assert replay.resulting_spec.context.revision_value == "clean-revision-b"
    assert reopened.get_task(task_id, _scope()).spec.context.revision_value == (
        "clean-revision-c"
    )
    assert _database_dump(database) == before_dump
    assert database.read_bytes() == before_bytes
    assert restarted_executor.retry_readiness_calls == []
    assert restarted_executor.dispatches == []
    assert restarted_executor.cancels == []

    exact_replay = restarted_core.execute(
        legacy_retry_b,
        legacy_grant_b,
        context=None,
        now=NOW,
    )
    assert exact_replay == legacy_result_b
    assert _database_dump(database) == before_dump

    assert (
        restarted_core.read_applied_retry_replay(
            scope=_scope(),
            command_id="command-retry-absent",
            task_id=task_id,
            product_request=_retry_product_request_fingerprint(
                command_id="command-retry-absent",
                task_id=task_id,
            ),
        )
        is None
    )
    conflict = _retry_product_request_fingerprint(
        command_id=retry_b_command_id,
        task_id=task_id,
        correlation_id="changed-correlation",
    )
    with pytest.raises(FormalTaskViolation) as rejected:
        restarted_core.read_applied_retry_replay(
            scope=_scope(),
            command_id=retry_b_command_id,
            task_id=task_id,
            product_request=conflict,
        )
    assert rejected.value.reason == "IDEMPOTENCY_CONFLICT"
    assert _database_dump(database) == before_dump
    assert database.read_bytes() == before_bytes
    assert restarted_executor.retry_readiness_calls == []
    assert restarted_executor.dispatches == []
    assert restarted_executor.cancels == []


def test_current_disposition_cannot_grandfather_a_completed_retry(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry_b, grant_b = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.CANCELLED,
        2,
        command_id="command-current-completed-retry",
    )
    result_b = core.execute(
        retry_b,
        grant_b,
        context=replace(_context(tmp_path), revision_value="clean-revision-b"),
        now=NOW,
    )
    assert result_b.ok and result_b.result is not None
    retry_attempt_id = str(result_b.result["attempt_id"])
    completed_retry, _completed_grant = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.COMPLETED,
        2,
        command_id=retry_b.command_id,
    )
    _rewrite_retry_as_completed_legacy_fixture(
        store.database_path,
        predecessor_attempt_id=attempt_a,
        retry_attempt_id=retry_attempt_id,
        legacy_command=completed_retry,
        preserve_current_disposition=True,
    )
    before = _database_dump(store.database_path)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(store.database_path)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(store.database_path) == before
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.parametrize(
    "corruption",
    [
        "future_ordinal",
        "orphan_attempt",
        "foreign_event",
        "duplicate_create_boundary",
        "missing_create_command",
        "missing_create_dispatch",
    ],
)
def test_retry_read_authority_rejects_incomplete_full_lineage_before_readiness(
    tmp_path: Path, corruption: str
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    database = store.database_path
    if corruption == "foreign_event":
        foreign = _create(tmp_path, identity_suffix="-lineage-foreign")
        foreign_result = core.execute(
            foreign.envelope,
            foreign.authorization,
            context=foreign.context,
            now=NOW,
        )
        assert foreign_result.ok and foreign_result.result is not None
        foreign_attempt = str(foreign_result.result["attempt_id"])
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        if corruption == "future_ordinal":
            connection.execute(
                "UPDATE attempts SET attempt_number=2 WHERE attempt_id=?",
                (attempt_a,),
            )
        elif corruption == "orphan_attempt":
            connection.execute(
                """
                INSERT INTO attempts(
                    attempt_id, task_id, attempt_number, executor_id,
                    executor_ref, state, outcome, source_seq, updated_at)
                SELECT 'attempt-orphan', task_id, 2, executor_id, NULL,
                    'accepted', NULL, -1, updated_at
                FROM attempts WHERE attempt_id=?
                """,
                (attempt_a,),
            )
        elif corruption == "foreign_event":
            connection.execute(
                """
                UPDATE task_events SET attempt_id=?
                WHERE task_id=? AND seq=1
                """,
                (foreign_attempt, task_id),
            )
        elif corruption == "duplicate_create_boundary":
            connection.execute(
                """
                UPDATE task_events SET event_type='task.accepted',
                    state='accepted', outcome=NULL, producer='task_core',
                    source_event_id=NULL, details_json=?
                WHERE task_id=? AND seq=1
                """,
                (json.dumps({"command_id": "command-create"}), task_id),
            )
        elif corruption == "missing_create_command":
            connection.execute("DELETE FROM commands WHERE command_id='command-create'")
        else:
            connection.execute(
                """
                DELETE FROM outbox WHERE task_id=? AND attempt_id=?
                    AND kind='attempt.dispatch'
                """,
                (task_id, attempt_a),
            )
        connection.commit()
    before = _database_dump(database)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)

    rejected = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_STORE_CORRUPT"
    assert executor.retry_readiness_calls == []
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_retry_boundary",
        "duplicate_retry_boundary",
        "missing_retry_command",
        "wrong_retry_result",
        "wrong_retry_dispatch_command",
    ],
)
def test_next_retry_rejects_corrupt_prior_retry_ledger_with_zero_effects(
    tmp_path: Path, corruption: str
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry_b, grant_b = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    result_b = core.execute(retry_b, grant_b, context=_context(tmp_path), now=NOW)
    assert result_b.ok and result_b.result is not None
    attempt_b = str(result_b.result["attempt_id"])
    item_b = store.claim_outbox("prior-retry-ledger")
    assert item_b is not None
    store.complete_outbox(
        item_b,
        executor_ref=f"legacy:{attempt_b}",
        observations=_observations(item_b, outcome=TerminalOutcome.CANCELLED),
    )
    with sqlite3.connect(store.database_path) as connection:
        boundary = connection.execute(
            """
            SELECT seq, details_json FROM task_events
            WHERE task_id=? AND attempt_id=? AND event_type='task.retry_accepted'
            """,
            (task_id, attempt_b),
        ).fetchone()
        assert boundary is not None
        if corruption == "missing_retry_boundary":
            connection.execute(
                """
                UPDATE task_events SET event_type='task.running'
                WHERE task_id=? AND seq=?
                """,
                (task_id, boundary[0]),
            )
        elif corruption == "duplicate_retry_boundary":
            connection.execute(
                """
                UPDATE task_events SET event_type='task.retry_accepted',
                    state='accepted', outcome=NULL, producer='task_core',
                    source_event_id=NULL, causation_id=?, details_json=?
                WHERE task_id=? AND seq=?
                """,
                (
                    retry_b.command_id,
                    boundary[1],
                    task_id,
                    int(boundary[0]) + 1,
                ),
            )
        elif corruption == "missing_retry_command":
            connection.execute(
                "DELETE FROM commands WHERE command_id=?",
                (retry_b.command_id,),
            )
        elif corruption == "wrong_retry_result":
            row = connection.execute(
                "SELECT result_json FROM commands WHERE command_id=?",
                (retry_b.command_id,),
            ).fetchone()
            assert row is not None
            payload = json.loads(row[0])
            payload["result"]["attempt_id"] = "attempt-foreign-result"
            connection.execute(
                "UPDATE commands SET result_json=? WHERE command_id=?",
                (json.dumps(payload, sort_keys=True), retry_b.command_id),
            )
        else:
            connection.execute(
                """
                UPDATE outbox SET command_id='command-create'
                WHERE task_id=? AND attempt_id=? AND kind='attempt.dispatch'
                """,
                (task_id, attempt_b),
            )
        connection.commit()
    before = _database_dump(store.database_path)
    calls = list(executor.retry_readiness_calls)
    retry_c, grant_c = _retry(task_id, attempt_b, TerminalOutcome.CANCELLED, 3)

    rejected = core.execute(retry_c, grant_c, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_STORE_CORRUPT"
    assert executor.retry_readiness_calls == calls
    assert _database_dump(store.database_path) == before


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (TerminalOutcome.FAILED, "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"),
        (TerminalOutcome.INTERRUPTED, "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"),
    ],
)
def test_retry_ineligible_terminal_outcome_has_zero_effects(
    tmp_path: Path, outcome: TerminalOutcome, reason: str
) -> None:
    store, executor, core, task_id, attempt_id = _terminal_task(
        tmp_path, outcome=outcome
    )
    # The strict command contract permits only eligible outcomes; use an eligible
    # asserted value and prove that Store authority still rejects actual truth.
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.CANCELLED, 2)
    before = store.counts()
    authority_before = _task_authority_dump(store.database_path)

    result = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not result.ok and result.error is not None
    assert result.error.reason == reason
    assert result.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(store.database_path) == authority_before
    assert store.counts() == {**before, "commands": before["commands"] + 1}
    assert executor.retry_readiness_calls == []


def test_retry_requires_terminal_and_executor_readiness_with_zero_effects(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "retry-guards.sqlite")
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
    attempt_id = str(created.result["attempt_id"])
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.CANCELLED, 2)
    before = store.counts()
    authority_before = _task_authority_dump(store.database_path)

    nonterminal = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not nonterminal.ok and nonterminal.error is not None
    assert nonterminal.error.reason == "TASK_RETRY_REQUIRES_TERMINAL"
    assert nonterminal.extensions["live_voice.command"]["disposition"] == "conflict"
    assert _task_authority_dump(store.database_path) == authority_before
    assert store.counts() == {**before, "commands": before["commands"] + 1}

    item = store.claim_outbox("terminal-fixture")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item, outcome=TerminalOutcome.CANCELLED),
    )
    executor.retry_ready = False
    pending_retry, pending_grant = _retry(
        task_id,
        attempt_id,
        TerminalOutcome.CANCELLED,
        2,
        command_id="command-retry-readiness-pending",
    )
    before_dump = _database_dump(store.database_path)
    pending = core.execute(
        pending_retry, pending_grant, context=_context(tmp_path), now=NOW
    )
    assert not pending.ok and pending.error is not None
    assert pending.error.reason == "TASK_RETRY_EXECUTOR_CLEANUP_PENDING"
    assert pending.error.message == "Executor predecessor cleanup is not retry-ready"
    assert _database_dump(store.database_path) == before_dump
    executor.retry_ready = True
    executor.retry_readiness_error = FormalTaskViolation(
        "PRIVATE_EXECUTOR_ERROR",
        "credential-like private detail",
        ErrorCode.INTERNAL,
    )
    failed_readiness = core.execute(
        pending_retry, pending_grant, context=_context(tmp_path), now=NOW
    )
    assert not failed_readiness.ok and failed_readiness.error is not None
    assert failed_readiness.error.reason == "TASK_RETRY_EXECUTOR_CLEANUP_PENDING"
    assert failed_readiness.error.message == "Executor retry-readiness is unavailable"
    assert "private" not in failed_readiness.error.message
    assert _database_dump(store.database_path) == before_dump

    class GetterFailureExecutor(_Executor):
        @property
        def retry_readiness(self) -> object:
            raise RuntimeError("private getter detail")

    getter_failure = PersistentTaskCore(store, GetterFailureExecutor()).execute(
        pending_retry, pending_grant, context=_context(tmp_path), now=NOW
    )
    assert not getter_failure.ok and getter_failure.error is not None
    assert getter_failure.error.reason == "TASK_RETRY_EXECUTOR_CLEANUP_PENDING"
    assert getter_failure.error.message == "Executor retry-readiness is unavailable"
    assert "private" not in getter_failure.error.message
    assert _database_dump(store.database_path) == before_dump


@pytest.mark.parametrize(
    ("unsettled_owner", "reason"),
    [
        ("outbox", "TASK_RETRY_OUTBOX_PENDING"),
        ("reconciliation", "TASK_RETRY_RECONCILIATION_PENDING"),
    ],
)
def test_retry_requires_settled_durable_ownership_with_zero_effects(
    tmp_path: Path,
    unsettled_owner: str,
    reason: str,
) -> None:
    store, executor, core, task_id, attempt_id = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.CANCELLED, 2)
    with sqlite3.connect(store.database_path) as connection:
        if unsettled_owner == "outbox":
            connection.execute(
                "UPDATE outbox SET state='pending' WHERE attempt_id=?",
                (attempt_id,),
            )
        else:
            connection.execute(
                """
                UPDATE tasks SET reconciliation_state='pending',
                    reconciliation_reason='cleanup_pending' WHERE task_id=?
                """,
                (task_id,),
            )
        connection.commit()
        before = tuple(connection.iterdump())

    rejected = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == reason
    assert executor.retry_readiness_calls == []
    with sqlite3.connect(store.database_path) as connection:
        assert tuple(connection.iterdump()) == before


def test_old_attempt_facts_are_explicitly_superseded_after_retry(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "stale-observation.sqlite")
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
    item_a = store.claim_outbox("terminal-a")
    assert item_a is not None
    observations_a = _observations(item_a, outcome=TerminalOutcome.CANCELLED)
    store.complete_outbox(
        item_a,
        executor_ref=f"legacy:{item_a.attempt_id}",
        observations=observations_a,
    )
    retry, grant = _retry(
        item_a.task_id, item_a.attempt_id, TerminalOutcome.CANCELLED, 2
    )
    applied = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert applied.ok
    before = store.counts()

    duplicate = store.apply_observations(observations_a)
    assert duplicate.disposition is TaskMutationDisposition.SUPERSEDED
    assert store.counts() == before
    late = replace(
        observations_a[-1],
        source_event_id=f"late:{item_a.attempt_id}",
        source_seq=3,
    )
    stale = store.apply_observations((late,))

    assert stale.disposition is TaskMutationDisposition.SUPERSEDED
    assert stale.attempt.attempt_id == item_a.attempt_id
    assert stale.events == ()
    assert store.counts() == before


def test_old_attempt_outbox_and_reconciliation_callbacks_have_zero_effects(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "stale-callbacks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    item_a = store.claim_outbox("terminal-a")
    assert item_a is not None
    store.complete_outbox(
        item_a,
        executor_ref=f"legacy:{item_a.attempt_id}",
        observations=_observations(item_a, outcome=TerminalOutcome.CANCELLED),
    )
    retry, grant = _retry(
        item_a.task_id, item_a.attempt_id, TerminalOutcome.CANCELLED, 2
    )
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    attempt_b = str(retried.result["attempt_id"])
    before_counts = store.counts()
    before_task = store.get_task(item_a.task_id, _scope())
    before_history = store.events(item_a.task_id, _scope())
    with sqlite3.connect(store.database_path) as connection:
        before_outboxes = connection.execute(
            """
            SELECT outbox_id, state, delivery_count, claimed_by, claim_token
            FROM outbox ORDER BY outbox_id
            """
        ).fetchall()

    superseded_operations = (
        lambda: store.mark_reconciliation_pending(
            item_a.task_id, item_a.attempt_id, "late pending"
        ),
        lambda: store.mark_reconciliation_resolved(
            item_a.task_id, item_a.attempt_id, "late resolved"
        ),
        lambda: store.resolve_lost_attempt(
            item_a.task_id, item_a.attempt_id, "late lost"
        ),
    )
    for operation in superseded_operations:
        receipt = operation()
        assert receipt.disposition is TaskMutationDisposition.SUPERSEDED
        assert receipt.attempt.attempt_id == item_a.attempt_id
        assert receipt.events == ()
    with pytest.raises(FormalTaskViolation) as stale_release:
        store.release_outbox(item_a, "late release")
    assert stale_release.value.reason == "TASK_ATTEMPT_STALE"
    assert stale_release.value.code is ErrorCode.STALE
    with pytest.raises(FormalTaskViolation) as lost_claim:
        store.complete_outbox(
            item_a,
            executor_ref=f"legacy:{item_a.attempt_id}",
            observations=_observations(item_a),
        )
    assert lost_claim.value.reason == "OUTBOX_CLAIM_LOST"

    assert store.counts() == before_counts
    assert store.get_task(item_a.task_id, _scope()) == before_task
    assert store.get_task(item_a.task_id, _scope()).attempt_id == attempt_b
    assert store.events(item_a.task_id, _scope()) == before_history
    assert store.get_attempt(item_a.attempt_id).outcome is TerminalOutcome.CANCELLED
    with sqlite3.connect(store.database_path) as connection:
        after_outboxes = connection.execute(
            """
            SELECT outbox_id, state, delivery_count, claimed_by, claim_token
            FROM outbox ORDER BY outbox_id
            """
        ).fetchall()
    assert after_outboxes == before_outboxes


def test_cancel_after_retry_targets_only_current_attempt(tmp_path: Path) -> None:
    store, _executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    attempt_b = str(retried.result["attempt_id"])
    before_a = store.get_attempt(attempt_a)

    cancel = _cancel(task_id)
    cancelled = core.execute(cancel.envelope, cancel.authorization, now=NOW)

    assert cancelled.ok and cancelled.result is not None
    assert cancelled.result["attempt_id"] == attempt_b
    assert cancelled.result["state"] == FormalTaskState.TERMINAL.value
    assert store.get_attempt(attempt_a) == before_a
    assert store.get_attempt(attempt_a).outcome is TerminalOutcome.CANCELLED
    assert store.get_attempt(attempt_b).outcome is TerminalOutcome.CANCELLED
    current = store.get_task(task_id, _scope())
    assert current.attempt_id == attempt_b
    assert current.outcome is TerminalOutcome.CANCELLED
    assert all(
        event.attempt_id == attempt_b
        for event in store.events(
            task_id,
            _scope(),
            after_seq=-1,
            attempt_id=attempt_b,
        )
    )


@pytest.mark.parametrize(
    "failpoint",
    [
        "retry.before_ids",
        "retry.after_attempt",
        "retry.after_event",
        "retry.after_outbox",
        "retry.after_command",
        "retry.after_task",
    ],
)
def test_retry_failpoints_leave_exact_predecessor_unchanged(
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
    item = store.claim_outbox("terminal-fixture")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item, outcome=TerminalOutcome.CANCELLED),
    )
    retry, grant = _retry(item.task_id, item.attempt_id, TerminalOutcome.CANCELLED, 2)
    before_counts = store.counts()
    before_task = store.get_task(item.task_id, _scope())
    before_events = store.events(item.task_id, _scope())
    enabled = True

    with pytest.raises(RuntimeError, match=failpoint):
        core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert store.counts() == before_counts
    assert store.get_task(item.task_id, _scope()) == before_task
    assert store.events(item.task_id, _scope()) == before_events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "missing_boundary",
        "duplicate_boundary",
        "boundary_details",
        "boundary_state",
        "boundary_not_segment_start",
        "predecessor_outcome",
        "predecessor_number",
    ],
)
async def test_corrupt_retry_dispatch_lineage_fails_before_claim_or_executor(
    tmp_path: Path, corruption: str
) -> None:
    database = tmp_path / f"retry-lineage-{corruption}.sqlite"
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
    attempt_a = str(created.result["attempt_id"])
    dispatch_a = store.claim_outbox("terminal-a")
    assert dispatch_a is not None
    store.complete_outbox(
        dispatch_a,
        executor_ref=f"legacy:{attempt_a}",
        observations=_observations(dispatch_a, outcome=TerminalOutcome.CANCELLED),
    )
    retry, grant = _retry(dispatch_a.task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    retry_outbox_id = str(retried.result["outbox_id"])
    attempt_b = str(retried.result["attempt_id"])

    with sqlite3.connect(database) as connection:
        if corruption == "missing_boundary":
            connection.execute(
                "DELETE FROM task_events WHERE event_type='task.retry_accepted'"
            )
        elif corruption == "duplicate_boundary":
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, seq, event_id, attempt_id, scope_json, event_type,
                    state, outcome, producer, source_event_id, causation_id,
                    correlation_id, occurred_at, details_json
                )
                SELECT task_id, seq + 100, event_id || '-duplicate', attempt_id,
                       scope_json, event_type, state, outcome, producer,
                       source_event_id, causation_id, correlation_id,
                       occurred_at, details_json
                FROM task_events WHERE event_type='task.retry_accepted'
                """
            )
        elif corruption == "boundary_details":
            row = connection.execute(
                """
                SELECT details_json FROM task_events
                WHERE event_type='task.retry_accepted'
                """
            ).fetchone()
            assert row is not None
            details = json.loads(row[0])
            details["retry_of_attempt_id"] = "attempt-foreign"
            connection.execute(
                """
                UPDATE task_events SET details_json=?
                WHERE event_type='task.retry_accepted'
                """,
                (json.dumps(details, sort_keys=True),),
            )
        elif corruption == "boundary_state":
            connection.execute(
                """
                UPDATE task_events SET state='running'
                WHERE event_type='task.retry_accepted'
                """
            )
        elif corruption == "boundary_not_segment_start":
            connection.execute(
                "UPDATE task_events SET attempt_id=? WHERE task_id=? AND seq=0",
                (attempt_b, dispatch_a.task_id),
            )
        elif corruption == "predecessor_outcome":
            connection.execute(
                "UPDATE attempts SET outcome='completed' WHERE attempt_id=?",
                (attempt_a,),
            )
        else:
            connection.execute(
                "UPDATE attempts SET attempt_number=3 WHERE attempt_id=?",
                (attempt_a,),
            )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="retry-worker-corrupt")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (retry_outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert store.get_task(dispatch_a.task_id, _scope()).attempt_id == attempt_b
    assert executor.dispatches == []
    assert executor.cancels == []


class _Executor:
    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(self) -> None:
        self.dispatches: list[str] = []
        self.cancels: list[str] = []
        self.adjustments: list[str] = []
        self.adjustment_state = TaskAdjustmentState.APPLIED
        self.adjustment_reason: str | None = None
        self.adjustment_error: FormalTaskViolation | None = None
        self.adjustment_settlements: list[TaskAdjustmentSettlement] = []
        self.fail_dispatches = 0
        self.status_resolution: ExecutorResolution | None = None
        self.retry_ready = True
        self.retry_readiness_error: Exception | None = None
        self.retry_readiness_calls: list[str] = []

    def retry_readiness(
        self, task: PersistentTaskRecord, attempt: PersistentAttemptRecord
    ) -> ExecutorRetryReadiness:
        self.retry_readiness_calls.append(attempt.attempt_id)
        if self.retry_readiness_error is not None:
            raise self.retry_readiness_error
        assert attempt.outcome is not None
        return ExecutorRetryReadiness(
            task_id=task.task_id,
            previous_attempt_id=attempt.attempt_id,
            previous_outcome=attempt.outcome,
            previous_attempt_number=attempt.attempt_number,
            ready=self.retry_ready,
            reason=("cleanup_complete" if self.retry_ready else "cleanup_pending"),
        )

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

    async def adjust(self, item: PersistentOutboxItem) -> TaskAdjustmentDeliveryResult:
        self.adjustments.append(item.command_id)
        assert item.executor_ref is not None
        if self.adjustment_error is not None:
            raise self.adjustment_error
        return TaskAdjustmentDeliveryResult(
            item.executor_ref,
            item.command_id,
            self.adjustment_state,
            self.adjustment_reason,
        )

    async def settle_adjustment(
        self,
        _item: PersistentOutboxItem,
        settlement: TaskAdjustmentSettlement,
    ) -> None:
        self.adjustment_settlements.append(settlement)

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
    assert results[0].result is not None
    admission = stores[0].events(
        str(results[0].result["task_id"]), _scope(), after_seq=-1
    )[0]
    assert all(
        result.extensions
        == {
            "live_voice.command": {
                "disposition": "accepted",
                "admission_event_id": admission.event_id,
                "settlement_event_id": None,
            },
            "live_voice.store": {"durability": "sqlite_outbox"},
        }
        for result in results
    )
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
async def test_corrupt_task_scope_key_cannot_disclose_or_dispatch(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    secret_instruction = "PRIVATE PROJECT INSTRUCTION: rotate the internal key."
    invocation = _create(tmp_path, instruction=secret_instruction)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    foreign_scope = ScopeRef(
        "foreign-user", "foreign-project", "foreign-session", Assurance.AUTHENTICATED
    )
    foreign_scope_key = json.dumps(
        foreign_scope.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE tasks SET scope_key=? WHERE task_id=?",
            (foreign_scope_key, task_id),
        )
    before = store.counts()
    status = _status(task_id)
    raw_query = status.envelope.to_dict()
    raw_query["scope"] = foreign_scope.to_dict()
    foreign_grant = TaskAuthorizationGrant(
        principal_id="foreign-user",
        scope=foreign_scope,
        operation="task.status",
        command_id=None,
        target_task_id=task_id,
        allowed_capabilities=frozenset({"task.status"}),
        confirmation_id=None,
        confirmed=False,
        expires_at=EXPIRY,
    )

    hidden = core.query(QueryEnvelope.from_dict(raw_query), foreign_grant, now=NOW)

    assert not hidden.ok
    assert hidden.error is not None
    assert hidden.error.reason == "TASK_STORE_CORRUPT"
    assert secret_instruction not in json.dumps(hidden.to_dict())
    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="worker-corrupt")
    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert secret_instruction not in str(raised.value)
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox
            """
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["scope", "executor"])
async def test_corrupt_outbox_binding_fails_before_executor_effect(
    tmp_path: Path,
    corruption: str,
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
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT payload_json FROM outbox").fetchone()
        assert row is not None
        payload = json.loads(row[0])
        if corruption == "scope":
            payload["scope"]["project_id"] = "project-other"
        else:
            payload["spec"]["executor_id"] = "foreign-executor"
        connection.execute(
            "UPDATE outbox SET payload_json=?",
            (json.dumps(payload, sort_keys=True),),
        )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="worker-corrupt")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    assert store.get_attempt(str(created.result["attempt_id"])).executor_ref is None
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox
            """
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "cancel_to_dispatch",
        "dispatch_to_cancel",
        "dispatch_lifecycle",
        "foreign_command",
        "command_payload",
    ],
)
async def test_corrupt_outbox_command_binding_cannot_claim_or_execute(
    tmp_path: Path,
    corruption: str,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    secret_instruction = "PRIVATE PRIMARY TASK INSTRUCTION"
    invocation = _create(tmp_path, instruction=secret_instruction)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    target_outbox_id = str(created.result["outbox_id"])
    if corruption == "cancel_to_dispatch":
        held_dispatch = store.claim_outbox("held-dispatch")
        assert held_dispatch is not None
        cancel = _cancel(task_id)
        acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
        assert acknowledged.ok and acknowledged.result is not None
        target_outbox_id = str(acknowledged.result["outbox_id"])
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET kind=? WHERE outbox_id=?",
                ("attempt.dispatch", target_outbox_id),
            )
    elif corruption == "dispatch_to_cancel":
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET kind=? WHERE outbox_id=?",
                ("attempt.cancel", target_outbox_id),
            )
    elif corruption == "dispatch_lifecycle":
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE tasks SET cancel_requested=1, dispatch_fenced=1
                WHERE task_id=?
                """,
                (task_id,),
            )
    elif corruption == "foreign_command":
        other_invocation = _create(
            tmp_path,
            instruction="Different task instruction.",
            identity_suffix="-foreign-command",
        )
        other = core.execute(
            other_invocation.envelope,
            other_invocation.authorization,
            context=other_invocation.context,
            now=NOW,
        )
        assert other.ok and other.result is not None
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET state=? WHERE outbox_id=?",
                ("suppressed", str(other.result["outbox_id"])),
            )
            connection.execute(
                "UPDATE outbox SET command_id=? WHERE outbox_id=?",
                (other_invocation.envelope.command_id, target_outbox_id),
            )
    else:
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT fingerprint FROM commands WHERE command_id=?",
                (invocation.envelope.command_id,),
            ).fetchone()
            assert row is not None
            fingerprint = json.loads(row[0])
            fingerprint["command"]["payload"]["instruction"] = (
                "FOREIGN COMMAND INSTRUCTION"
            )
            connection.execute(
                "UPDATE commands SET fingerprint=? WHERE command_id=?",
                (
                    json.dumps(fingerprint, sort_keys=True).encode(),
                    invocation.envelope.command_id,
                ),
            )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="worker-corrupt")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert secret_instruction not in str(raised.value)
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (target_outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("durable_state", "corrupt_result_state"),
    [
        (FormalTaskState.ACCEPTED, FormalTaskState.RUNNING),
        (FormalTaskState.RUNNING, FormalTaskState.ACCEPTED),
    ],
)
async def test_corrupt_cancel_result_state_cannot_claim_or_execute(
    tmp_path: Path,
    durable_state: FormalTaskState,
    corrupt_result_state: FormalTaskState,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    secret_instruction = "PRIVATE CANCEL TARGET INSTRUCTION"
    invocation = _create(tmp_path, instruction=secret_instruction)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    if durable_state is FormalTaskState.RUNNING:
        store.complete_outbox(
            dispatch,
            executor_ref=f"legacy:{dispatch.attempt_id}",
            observations=_observations(dispatch),
        )
    cancel = _cancel(task_id)
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok and acknowledged.result is not None
    assert acknowledged.result["state"] == durable_state.value
    cancel_outbox_id = str(acknowledged.result["outbox_id"])
    events = store.events(task_id, _scope())
    cancel_event = next(
        event for event in events if event.event_type == "task.cancel_requested"
    )
    assert cancel_event.state == durable_state.value
    assert cancel_event.causation_id == cancel.envelope.command_id
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (cancel.envelope.command_id,),
        ).fetchone()
        assert row is not None
        result = json.loads(row[0])
        result["result"]["state"] = corrupt_result_state.value
        connection.execute(
            "UPDATE commands SET result_json=? WHERE command_id=?",
            (
                json.dumps(result, sort_keys=True),
                cancel.envelope.command_id,
            ),
        )
    before = store.counts()

    if durable_state is FormalTaskState.ACCEPTED:
        with pytest.raises(FormalTaskViolation) as raised:
            store.complete_outbox(
                dispatch,
                executor_ref=f"legacy:{dispatch.attempt_id}",
                observations=_observations(dispatch),
            )
        assert store.get_attempt(dispatch.attempt_id).executor_ref is None
    else:
        with pytest.raises(FormalTaskViolation) as raised:
            await core.drain_outbox_once(worker_id="cancel-worker")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert secret_instruction not in str(raised.value)
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (cancel_outbox_id,),
        ).fetchone()
        dispatch_outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (dispatch.outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    if durable_state is FormalTaskState.ACCEPTED:
        assert dispatch_outbox == (
            "claimed",
            1,
            "dispatch-worker",
            dispatch.claim_token,
        )
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corrupt_executor_ref", [None, "legacy:other-attempt"])
async def test_corrupt_cancel_outbox_executor_ref_fails_before_executor_effect(
    tmp_path: Path,
    corrupt_executor_ref: str | None,
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
    attempt_id = str(created.result["attempt_id"])
    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{attempt_id}",
        observations=_observations(dispatch),
    )
    cancel = _cancel(task_id)
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok and acknowledged.result is not None
    cancel_outbox_id = str(acknowledged.result["outbox_id"])
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM outbox WHERE outbox_id=?",
            (cancel_outbox_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["executor_ref"] = corrupt_executor_ref
        connection.execute(
            "UPDATE outbox SET payload_json=? WHERE outbox_id=?",
            (json.dumps(payload, sort_keys=True), cancel_outbox_id),
        )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="cancel-worker")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (cancel_outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
async def test_dispatch_completion_does_not_overwrite_corrupt_cancel_binding(
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
    attempt_id = str(created.result["attempt_id"])
    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    cancel = _cancel(task_id)
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok and acknowledged.result is not None
    cancel_outbox_id = str(acknowledged.result["outbox_id"])
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM outbox WHERE outbox_id=?",
            (cancel_outbox_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert payload["executor_ref"] is None
        payload["executor_ref"] = "legacy:foreign-attempt"
        connection.execute(
            "UPDATE outbox SET payload_json=? WHERE outbox_id=?",
            (json.dumps(payload, sort_keys=True), cancel_outbox_id),
        )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        store.complete_outbox(
            dispatch,
            executor_ref=f"legacy:{attempt_id}",
            observations=_observations(dispatch),
        )

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    assert store.get_attempt(attempt_id).executor_ref is None
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT outbox_id, state, delivery_count, claimed_by, claim_token,
                   payload_json
            FROM outbox ORDER BY outbox_id
            """
        ).fetchall()
    by_id = {row[0]: row for row in rows}
    assert by_id[dispatch.outbox_id][1:5] == (
        "claimed",
        1,
        "dispatch-worker",
        dispatch.claim_token,
    )
    assert by_id[cancel_outbox_id][1:5] == ("pending", 0, None, None)
    assert json.loads(by_id[cancel_outbox_id][5])["executor_ref"] == (
        "legacy:foreign-attempt"
    )
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["missing_attempt", "cross_binding"])
async def test_corrupt_outbox_canonical_binding_is_not_hidden(
    tmp_path: Path,
    corruption: str,
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
    attempt_id = str(created.result["attempt_id"])
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT outbox_id FROM outbox WHERE task_id=?", (task_id,)
        ).fetchone()
        assert row is not None
        outbox_id = str(row[0])
    if corruption == "missing_attempt":
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM attempts WHERE attempt_id=?", (attempt_id,))
    else:
        other_invocation = _create(tmp_path, identity_suffix="-other")
        other = core.execute(
            other_invocation.envelope,
            other_invocation.authorization,
            context=other_invocation.context,
            now=NOW,
        )
        assert other.ok and other.result is not None
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET state=? WHERE task_id=?",
                ("suppressed", str(other.result["task_id"])),
            )
            connection.execute(
                "UPDATE outbox SET attempt_id=? WHERE outbox_id=?",
                (str(other.result["attempt_id"]), outbox_id),
            )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="worker-corrupt")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
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
async def test_event_authority_snapshot_is_one_exact_contiguous_store_revision(
    tmp_path: Path,
) -> None:
    event_queries: list[str] = []

    def failpoint(name: str) -> None:
        if name == "event_authority_snapshot.before_events":
            event_queries.append(name)

    store = SqliteTaskStore(tmp_path / "authority-snapshot.sqlite", failpoint=failpoint)
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

    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=64)

    assert snapshot.task.task_id == task_id
    assert snapshot.attempt.attempt_id == snapshot.task.attempt_id
    assert snapshot.cursor == snapshot.task.event_head
    assert [event.seq for event in snapshot.events] == list(range(snapshot.cursor + 1))
    assert all(event.task_id == task_id for event in snapshot.events)
    assert event_queries == ["event_authority_snapshot.before_events"]


@pytest.mark.parametrize("max_events", [0, -1, True])
def test_event_authority_snapshot_rejects_invalid_capacity(
    tmp_path: Path, max_events: int
) -> None:
    store = SqliteTaskStore(tmp_path / f"authority-invalid-{max_events}.sqlite")

    with pytest.raises(FormalTaskViolation) as raised:
        store.event_authority_snapshot("task-1", _scope(), max_events=max_events)

    assert raised.value.reason == "INVALID_TASK_EVENT_AUTHORITY_CAPACITY"
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_event_authority_snapshot_rejects_oversize_before_event_query(
    tmp_path: Path,
) -> None:
    event_queries: list[str] = []

    def failpoint(name: str) -> None:
        if name == "event_authority_snapshot.before_events":
            event_queries.append(name)

    store = SqliteTaskStore(tmp_path / "authority-oversize.sqlite", failpoint=failpoint)
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

    with pytest.raises(FormalTaskViolation) as raised:
        store.event_authority_snapshot(task_id, _scope(), max_events=1)

    assert raised.value.reason == "TASK_EVENT_AUTHORITY_PREFIX_CAPACITY"
    assert raised.value.code is ErrorCode.UNAVAILABLE
    assert event_queries == []


def test_event_authority_snapshot_rejects_a_corrupt_head_without_partial_prefix(
    tmp_path: Path,
) -> None:
    database = tmp_path / "authority-corrupt.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE tasks SET event_head=1 WHERE task_id=?", (task_id,))

    with pytest.raises(FormalTaskViolation) as raised:
        store.event_authority_snapshot(task_id, _scope(), max_events=64)
    assert raised.value.reason == "TASK_STORE_CORRUPT"


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

    future_query = _events(task_id, after_seq=999)
    future_result = core.query(
        future_query.envelope,
        future_query.authorization,
        now=NOW,
    )
    assert not future_result.ok and future_result.error is not None
    assert future_result.error.reason == "TASK_EVENT_CURSOR_STALE"

    query = _events(task_id, after_seq=events[-1].seq)
    result = core.query(query.envelope, query.authorization, now=NOW)
    assert result.ok and result.result is not None
    assert result.result["task_id"] == task_id
    assert result.result["after_seq"] == events[-1].seq
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
    reconciliation_events: list[tuple[object, object]] = []

    async def reconciliation_sink(event: object, attempt: object) -> None:
        reconciliation_events.append((event, attempt))

    restarted = PersistentTaskCore(
        restarted_store,
        restart_executor,
        reconciliation_event_sink=reconciliation_sink,
    )
    summary = await restarted.reconcile()

    task = restarted_store.get_task(str(created.result["task_id"]), _scope())
    assert task.attempt_id == created.result["attempt_id"]
    assert (task.outcome is TerminalOutcome.INTERRUPTED) is terminal
    assert task.reconciliation_state is reconciliation
    assert restarted_store.counts()["attempts"] == 1
    assert restart_executor.dispatches == []
    assert restart_executor.cancels == []
    assert sum(summary[key] for key in ("known", "unavailable", "lost")) == 1
    if resolution is ExecutorResolution.LOST:
        assert [event.event_type for event, _ in reconciliation_events] == [
            "attempt.terminal",
            "task.terminal",
        ]
        assert all(
            event.task_id == task.task_id
            and event.attempt_id == task.attempt_id
            and attempt.task_id == task.task_id
            and attempt.attempt_id == task.attempt_id
            for event, attempt in reconciliation_events
        )
    else:
        assert reconciliation_events == []
    await restarted.reconcile()
    assert len(reconciliation_events) == (2 if terminal else 0)


@pytest.mark.asyncio
async def test_reconciliation_publishes_frozen_predecessor_receipt_after_retry(
    tmp_path: Path,
) -> None:
    class TerminalStatusExecutor(_Executor):
        async def status(
            self,
            task: PersistentTaskRecord,
            attempt: PersistentAttemptRecord,
        ) -> ExecutorObservation:
            return ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=self.executor_id,
                executor_ref=attempt.executor_ref,
                task_id=task.task_id,
                attempt_id=attempt.attempt_id,
                source_event_id=f"status-terminal:{attempt.attempt_id}",
                source_seq=attempt.source_seq + 1,
                attempt_state=FormalAttemptState.TERMINAL,
                attempt_outcome=TerminalOutcome.CANCELLED,
                occurred_at=utc_now(),
                raw_status="cancelled",
            )

    class RetryBeforeReturnStore(SqliteTaskStore):
        after_apply: object | None = None

        def apply_observations(self, observations):  # type: ignore[no-untyped-def]
            receipt = super().apply_observations(observations)
            callback = self.after_apply
            if callback is not None:
                self.after_apply = None
                callback()  # type: ignore[operator]
            return receipt

    seed_store, _seed_executor, _seed_core, task_id, attempt_a = _terminal_task(
        tmp_path
    )
    store = RetryBeforeReturnStore(seed_store.database_path)
    executor = TerminalStatusExecutor()
    core = PersistentTaskCore(store, executor)
    retry_b, grant_b = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    result_b = core.execute(
        retry_b,
        grant_b,
        context=replace(_context(tmp_path), revision_value="barrier-b"),
        now=NOW,
    )
    assert result_b.ok and result_b.result is not None
    attempt_b = str(result_b.result["attempt_id"])
    item_b = store.claim_outbox("barrier-b")
    assert item_b is not None
    store.complete_outbox(
        item_b,
        executor_ref=f"legacy:{attempt_b}",
        observations=_observations(item_b),
    )
    retry_c, grant_c = _retry(task_id, attempt_b, TerminalOutcome.CANCELLED, 3)

    def create_c() -> None:
        result_c = core.execute(
            retry_c,
            grant_c,
            context=replace(_context(tmp_path), revision_value="barrier-c"),
            now=NOW,
        )
        assert result_c.ok and result_c.result is not None

    store.after_apply = create_c
    published: list[tuple[PersistentTaskEvent, PersistentAttemptRecord]] = []

    async def sink(
        event: PersistentTaskEvent, attempt: PersistentAttemptRecord
    ) -> None:
        published.append((event, attempt))

    core._reconciliation_event_sink = sink

    summary = await core.reconcile()

    assert summary["known"] == 1
    assert [event.event_type for event, _ in published] == [
        "attempt.terminal",
        "task.terminal",
    ]
    assert all(
        event.attempt_id == attempt_b and attempt.attempt_id == attempt_b
        for event, attempt in published
    )
    assert all(event.event_type != "task.retry_accepted" for event, _ in published)
    assert store.get_task(task_id, _scope()).attempt_id != attempt_b


@pytest.mark.asyncio
async def test_reconciliation_counts_superseded_status_race_and_continues(
    tmp_path: Path,
) -> None:
    database = tmp_path / "reconcile-status-race.sqlite"
    store = SqliteTaskStore(database)
    seed_core = PersistentTaskCore(store, _Executor())
    for suffix in ("-race-one", "-race-two"):
        invocation = _create(tmp_path, identity_suffix=suffix)
        created = seed_core.execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
        )
        assert created.ok
    await seed_core.drain_outbox()

    class AdvancingStatusExecutor(_Executor):
        def __init__(self) -> None:
            super().__init__()
            self.core: PersistentTaskCore | None = None
            self.advanced = False

        async def status(
            self,
            task: PersistentTaskRecord,
            attempt: PersistentAttemptRecord,
        ) -> ExecutorDeliveryResult | ExecutorObservation:
            if self.advanced:
                return ExecutorDeliveryResult(attempt.executor_ref or "", ())
            self.advanced = True
            terminal = ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=self.executor_id,
                executor_ref=attempt.executor_ref,
                task_id=task.task_id,
                attempt_id=attempt.attempt_id,
                source_event_id=f"racing-terminal:{attempt.attempt_id}",
                source_seq=attempt.source_seq + 1,
                attempt_state=FormalAttemptState.TERMINAL,
                attempt_outcome=TerminalOutcome.CANCELLED,
                occurred_at=utc_now(),
                raw_status="cancelled",
            )
            external = SqliteTaskStore(database)
            external.apply_observations((terminal,))
            retry, grant = _retry(
                task.task_id,
                attempt.attempt_id,
                TerminalOutcome.CANCELLED,
                2,
                command_id=f"command-racing-retry:{attempt.attempt_id}",
                correlation_id=task.correlation_id,
            )
            assert self.core is not None
            retried = self.core.execute(
                retry,
                grant,
                context=replace(_context(tmp_path), revision_value="race-successor"),
                now=NOW,
            )
            assert retried.ok
            return terminal

    executor = AdvancingStatusExecutor()
    core = PersistentTaskCore(store, executor)
    executor.core = core

    summary = await core.reconcile()

    assert summary["superseded"] == 1
    assert summary["known"] == 1
    assert executor.advanced is True


@pytest.mark.asyncio
async def test_reconciliation_sink_failure_cannot_change_durable_task_truth(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sink-failure.sqlite"
    first = PersistentTaskCore(SqliteTaskStore(database), _Executor())
    invocation = _create(tmp_path)
    created = first.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await first.drain_outbox()

    async def failing_sink(_event: object, _attempt: object) -> None:
        raise RuntimeError("evidence sink unavailable")

    executor = _Executor()
    executor.status_resolution = ExecutorResolution.LOST
    store = SqliteTaskStore(database)
    restarted = PersistentTaskCore(
        store,
        executor,
        reconciliation_event_sink=failing_sink,
    )

    summary = await restarted.reconcile()

    task = store.get_task(str(created.result["task_id"]), _scope())
    assert summary["lost"] == 1
    assert task.state is FormalTaskState.TERMINAL
    assert task.outcome is TerminalOutcome.INTERRUPTED
