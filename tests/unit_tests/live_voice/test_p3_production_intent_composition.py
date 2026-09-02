# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CONTRACT_VERSION,
    InputCommitState,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.executor_capabilities import (
    TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
    TaskExecutionRequirements,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    AdmissionDisposition,
    AdmissionPolicy,
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskViolation,
    PersistedExecutorSelection,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    TaskResultAvailability,
    TaskResultArtifact,
)
from jiuwenswarm.server.live_voice.p3_production_intent_composition import (
    CallLocalProductionOriginAuthority,
    CallLocalProductionConfirmationConsumer,
    StoreProductionTaskAuthorityReader,
    production_context_fingerprint,
    production_model_binding_fingerprint,
)
from jiuwenswarm.server.live_voice.p3_confirmation import (
    BoundedP3ConfirmationOwner,
    P3ConfirmationBinding,
    P3ConfirmationOwnerContext,
    TrustedP3ConfirmationIssue,
)
from jiuwenswarm.server.live_voice.p3_product_confirmation import (
    ProductP3ConfirmationForwarder,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    FORMAL_PROJECT_EXECUTOR_ID,
)
from jiuwenswarm.server.live_voice.production_task_classifier import (
    ProductionTaskIntentClassifier,
)
from jiuwenswarm.server.live_voice.production_task_intent import (
    ProductionConfirmationBinding,
    ProductionIntentOrigin,
    ProductionTaskPolicyOutcome,
    ProductionTaskResolution,
    ProductionTaskIntentRequest,
    build_production_origin_binding,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.live_voice.voice_task_policy import (
    FormalTaskPolicyAdapter,
    FormalTaskPolicyInput,
)


SCOPE = ScopeRef(
    subject_id="user-1",
    project_id="project-1",
    session_id="session-1",
    assurance=Assurance.AUTHENTICATED,
)
NOW = "2026-08-21T10:00:00Z"
EXPIRY = "2026-08-21T11:00:00Z"


class _SeedExecutor:
    executor_id = FORMAL_PROJECT_EXECUTOR_ID


def _commit(text: str) -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": "commit-production-origin",
            "turn_id": "turn-production-origin",
            "interaction_id": "interaction-production-origin",
            "text": text,
            "hypothesis_provenance": {},
            "scope": SCOPE.to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-21T10:00:00Z",
        }
    )


def _context(project: Path) -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="agent_server.session_project_registry",
        stable_id=SCOPE.project_id,
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value="source-v1",
        scope=SCOPE,
        permissions=("task.execute", "project.write"),
        expires_at=EXPIRY,
        redaction_policy_id="live_voice.p3alpha.project.v1",
    )


def _grant(command_id: str) -> TaskAuthorizationGrant:
    return TaskAuthorizationGrant(
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
        operation="task.create",
        command_id=command_id,
        target_task_id=None,
        allowed_capabilities=frozenset({"task.create"}),
        confirmation_id=f"confirmation:{command_id}",
        confirmed=True,
        expires_at=EXPIRY,
    )


def _seed_selected_task(
    store: SqliteTaskStore,
    project: Path,
    *,
    suffix: str,
) -> tuple[str, str]:
    command_id = f"command-create-{suffix}"
    commit = TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": f"commit-create-{suffix}",
            "turn_id": f"turn-create-{suffix}",
            "interaction_id": f"interaction-create-{suffix}",
            "text": "Create one bounded synthetic report.",
            "hypothesis_provenance": {"provider": "test"},
            "scope": SCOPE.to_dict(),
            "context_refs": [],
            "committed_at": NOW,
        }
    )
    commits = TurnCommitLedger()
    assert commits.accept(commit)
    invocation = FormalTaskPolicyAdapter(commits).map(
        FormalTaskPolicyInput(
            state=InputCommitState.COMMITTED,
            source="text",
            operation="task.create",
            request_id=f"request-create-{suffix}",
            command_id=command_id,
            issued_at=NOW,
            scope=SCOPE,
            correlation_id=f"correlation-create-{suffix}",
            authorization=_grant(command_id),
            interaction_id=commit.interaction_id,
            turn_id=commit.turn_id,
            commit_id=commit.commit_id,
            origin_commit_sha256=hashlib.sha256(commit.canonical_bytes()).hexdigest(),
            source_start=0,
            source_end=len(commit.text),
            name=f"Synthetic report {suffix}",
            instruction=commit.text,
            context=_context(project),
            attributes={
                "model_identity": "default#0",
                "model_config_version": "catalog-v1",
            },
            destructive=True,
            confirmed=True,
            confirmation_id=f"confirmation:{command_id}",
        )
    )
    profile = DirectProjectCodeExecutorAdapter.capability_profile()
    requirements = TaskExecutionRequirements(
        schema_version=TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
        executor_id=profile.executor_id,
        operation_versions=profile.operation_versions,
        durability_level=profile.durability_level,
        side_effect_class="project-mutation",
        project_serialization="exclusive",
    )
    selection = PersistedExecutorSelection.from_values(
        adapter_id=profile.adapter_id,
        capability_profile=profile.to_dict(),
        execution_requirements=requirements.to_dict(),
    )
    result = PersistentTaskCore(store, _SeedExecutor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=selection,
        admission_policy=AdmissionPolicy(),
    )
    assert result.ok and result.result is not None
    return str(result.result["task_id"]), str(result.result["attempt_id"])


def _start_selected_task(
    store: SqliteTaskStore,
    *,
    task_id: str,
    attempt_id: str,
    suffix: str,
) -> tuple[str, PersistedExecutorSelection]:
    item = store.claim_outbox(f"worker-{suffix}", observed_at=NOW)
    assert item is not None and item.task_id == task_id
    assert item.attempt_id == attempt_id and item.selection is not None
    executor_ref = f"executor-ref-{suffix}"
    store.complete_outbox(
        item,
        executor_ref=executor_ref,
        observations=(
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=item.spec.executor_id,
                executor_ref=executor_ref,
                task_id=task_id,
                attempt_id=attempt_id,
                source_event_id=f"executor-running-{suffix}",
                source_seq=0,
                attempt_state=FormalAttemptState.RUNNING,
                attempt_outcome=None,
                occurred_at=NOW,
                raw_status="running",
                adapter_id=item.selection.adapter_id,
                capability_profile_digest=item.selection.capability_profile_digest,
            ),
        ),
    )
    return executor_ref, item.selection


def _complete_selected_task(
    store: SqliteTaskStore,
    *,
    task_id: str,
    attempt_id: str,
    executor_ref: str,
    selection: PersistedExecutorSelection,
    suffix: str,
) -> None:
    store.apply_observations(
        (
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=FORMAL_PROJECT_EXECUTOR_ID,
                executor_ref=executor_ref,
                task_id=task_id,
                attempt_id=attempt_id,
                source_event_id=f"executor-terminal-{suffix}",
                source_seq=1,
                attempt_state=FormalAttemptState.TERMINAL,
                attempt_outcome=TerminalOutcome.COMPLETED,
                occurred_at=NOW,
                raw_status="completed",
                result_text=f"completed result {suffix}",
                result_artifacts=(
                    TaskResultArtifact(
                        relative_path=f"result-{suffix}.txt",
                        sha256=hashlib.sha256(suffix.encode("utf-8")).hexdigest(),
                    ),
                ),
                adapter_id=selection.adapter_id,
                capability_profile_digest=selection.capability_profile_digest,
            ),
        )
    )


def test_call_local_natural_origin_requires_exact_accepted_commit_and_semantics() -> (
    None
):
    classifier = ProductionTaskIntentClassifier()
    commit = _commit("Cancel task tsk_task_a.")
    proposal = classifier.classify_natural(
        commit.text,
        origin=ProductionIntentOrigin.NATURAL_TEXT,
        committed=True,
        source_confidence=0.99,
    )
    request = ProductionTaskIntentRequest(
        origin=ProductionIntentOrigin.NATURAL_TEXT,
        scope=SCOPE,
        command_id="command-production-origin",
        proposal=proposal,
        commit=commit,
        source_id=commit.turn_id,
    )
    expected = build_production_origin_binding(request)
    ledger = TurnCommitLedger()
    assert ledger.accept(commit)
    authority = CallLocalProductionOriginAuthority(
        expected_binding=expected,
        commit_ledger=ledger,
    )

    receipt = authority.verify_origin(expected)

    assert receipt.principal_id == SCOPE.subject_id
    assert receipt.binding_fingerprint == expected.fingerprint
    with pytest.raises(ValueError, match="ORIGIN_BINDING_MISMATCH"):
        authority.verify_origin(replace(expected, source_id="turn-forged"))
    with pytest.raises(ValueError, match="ORIGIN_BINDING_MISMATCH"):
        authority.verify_origin(
            replace(
                expected,
                extractions=(
                    replace(expected.extractions[0], value_sha256="0" * 64),
                    *expected.extractions[1:],
                ),
            )
        )


def test_call_local_structured_origin_is_exact_and_never_uses_turn_ledger() -> None:
    proposal = ProductionTaskIntentClassifier().parse_structured(
        {
            "operation": "task.cancel",
            "target": "tsk_task_a",
            "arguments": {},
        },
        committed=True,
        source_confidence=1.0,
    )
    request = ProductionTaskIntentRequest(
        origin=ProductionIntentOrigin.STRUCTURED,
        scope=SCOPE,
        command_id="command-structured-origin",
        proposal=proposal,
        source_id="structured-request-1",
    )
    expected = build_production_origin_binding(request)
    authority = CallLocalProductionOriginAuthority(expected_binding=expected)

    receipt = authority.verify_origin(expected)

    assert receipt.binding_fingerprint == expected.fingerprint
    with pytest.raises(ValueError, match="ORIGIN_BINDING_MISMATCH"):
        authority.verify_origin(replace(expected, structured_semantic_sha256="0" * 64))


def test_natural_origin_rejects_when_call_local_commit_authority_lost() -> None:
    commit = _commit("Cancel task tsk_task_a.")
    proposal = ProductionTaskIntentClassifier().classify_natural(
        commit.text,
        origin=ProductionIntentOrigin.VOICE,
        committed=True,
        source_confidence=0.99,
    )
    request = ProductionTaskIntentRequest(
        origin=ProductionIntentOrigin.VOICE,
        scope=SCOPE,
        command_id="command-missing-origin",
        proposal=proposal,
        commit=commit,
        source_id=commit.turn_id,
    )
    expected = build_production_origin_binding(request)
    authority = CallLocalProductionOriginAuthority(
        expected_binding=expected,
        commit_ledger=TurnCommitLedger(),
    )

    with pytest.raises(ValueError, match="ORIGIN_COMMIT_NOT_ACCEPTED"):
        authority.verify_origin(expected)


def test_store_reader_projects_bounded_real_store_authority_without_writes(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "production-reader.sqlite3")
    task_id, attempt_id = _seed_selected_task(store, tmp_path, suffix="a")
    persisted = store.get_task(task_id, SCOPE)
    context_fingerprint = production_context_fingerprint(persisted.spec.context)
    model_fingerprint = production_model_binding_fingerprint(
        dict(persisted.spec.attributes)
    )
    before = store.counts()
    reader = StoreProductionTaskAuthorityReader(
        store=store,
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
        visible_task_capacity=32,
        authority_context_fingerprint=context_fingerprint,
    )

    authority = reader.list_visible_tasks(SCOPE)

    assert authority.scope == SCOPE
    assert len(authority.tasks) == 1
    fact = authority.tasks[0]
    assert fact.task_id == fact.stable_reference == task_id
    assert fact.attempt_id == attempt_id
    assert fact.event_head == 0
    assert fact.dispatch_control == "unclaimed"
    assert fact.admission_fingerprint is not None
    assert authority.authority_context_fingerprint == context_fingerprint
    assert fact.context_fingerprint == context_fingerprint
    assert fact.model_binding_fingerprint == model_fingerprint
    assert {
        "task.get",
        "task.list",
        "task.status",
        "task.events",
        "task.result",
        "task.update",
        "task.reprioritize",
        "task.cancel",
    } <= fact.supported_operations
    assert {
        "task.provide_input",
        "task.pause",
        "task.resume",
        "task.adjust",
    }.isdisjoint(fact.supported_operations)
    assert reader.get_task(SCOPE, task_id) == fact
    assert reader.task_status(SCOPE, task_id) == fact
    assert reader.event_head(SCOPE, task_id) == (fact.event_head, fact.event_head_id)
    assert reader.result_digest(SCOPE, task_id) is None
    assert store.counts() == before


def test_store_reader_rejects_foreign_scope_and_capacity_without_writes(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "production-reader-bounds.sqlite3")
    first, _ = _seed_selected_task(store, tmp_path, suffix="a")
    _seed_selected_task(store, tmp_path, suffix="b")
    before = store.counts()
    reader = StoreProductionTaskAuthorityReader(
        store=store,
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
        visible_task_capacity=1,
    )
    foreign = ScopeRef(
        subject_id=SCOPE.subject_id,
        project_id=SCOPE.project_id,
        session_id="session-foreign",
        assurance=Assurance.AUTHENTICATED,
    )

    with pytest.raises(FormalTaskViolation) as capacity:
        reader.list_visible_tasks(SCOPE)
    with pytest.raises(FormalTaskViolation) as scope:
        reader.get_task(foreign, first)

    assert capacity.value.reason == "PRODUCTION_TASK_AUTHORITY_CAPACITY_EXCEEDED"
    assert scope.value.reason == "PRODUCTION_TASK_AUTHORITY_SCOPE_MISMATCH"
    assert store.counts() == before


def test_store_reader_deferred_dispatch_supports_reprioritize_not_update(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "production-reader-deferred.sqlite3")
    task_id, _attempt_id = _seed_selected_task(store, tmp_path, suffix="deferred")
    item = store.claim_outbox("worker-deferred", observed_at=NOW)
    assert item is not None and item.task_id == task_id
    assert (
        store.defer_admission(
            item,
            reason="EXECUTOR_PROJECT_BUSY",
            policy=AdmissionPolicy(),
            observed_at=NOW,
        )
        is AdmissionDisposition.DEFERRED
    )
    reader = StoreProductionTaskAuthorityReader(
        store=store,
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
    )

    deferred = reader.get_task(SCOPE, task_id)

    assert deferred is not None and deferred.dispatch_control == "unclaimed"
    assert "task.reprioritize" in deferred.supported_operations
    assert "task.update" not in deferred.supported_operations


def test_store_reader_reconciliation_never_advertises_queue_control(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "production-reader-reconcile.sqlite3")
    task_id, attempt_id = _seed_selected_task(store, tmp_path, suffix="reconcile")
    store.mark_reconciliation_pending(
        task_id,
        attempt_id,
        "TEST_RECONCILIATION_PENDING",
    )
    reader = StoreProductionTaskAuthorityReader(
        store=store,
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
    )

    fact = reader.get_task(SCOPE, task_id)

    assert fact is not None and fact.dispatch_control == "taken_over"
    assert {"task.update", "task.reprioritize"}.isdisjoint(fact.supported_operations)


def test_store_reader_keeps_cancel_pending_decision_task_readable(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production-reader-decision-cancel.sqlite3"
    store = SqliteTaskStore(database)
    task_id, attempt_id = _seed_selected_task(store, tmp_path, suffix="decision")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """UPDATE attempts SET state='running', executor_ref=?, source_seq=0
               WHERE attempt_id=?""",
            ("executor-ref-decision", attempt_id),
        )
        connection.execute(
            """UPDATE outbox SET state='delivered', delivery_count=1,
                      claimed_by=NULL, claimed_at=NULL, claim_token=NULL
               WHERE task_id=? AND attempt_id=? AND kind='attempt.dispatch'""",
            (task_id, attempt_id),
        )
        connection.execute(
            """INSERT INTO task_events(
                   task_id, seq, event_id, attempt_id, scope_json, event_type,
                   state, outcome, producer, source_event_id, causation_id,
                   correlation_id, occurred_at, details_json)
               SELECT task_id, event_head + 1, ?, attempt_id, scope_json,
                      'task.decision_required', 'decision_required', NULL,
                      'task_core', NULL, 'decision-required', correlation_id, ?, '{}'
               FROM tasks WHERE task_id=?""",
            ("event-decision-required", NOW, task_id),
        )
        connection.execute(
            """UPDATE tasks SET state='decision_required',
                      event_head=event_head + 1, updated_at=? WHERE task_id=?""",
            (NOW, task_id),
        )
        connection.execute(
            """INSERT INTO task_events(
                   task_id, seq, event_id, attempt_id, scope_json, event_type,
                   state, outcome, producer, source_event_id, causation_id,
                   correlation_id, occurred_at, details_json)
               SELECT task_id, event_head + 1, ?, attempt_id, scope_json,
                      'task.cancel_requested', 'decision_required', NULL,
                      'task_core.control', NULL, 'cancel-decision', correlation_id,
                      ?, '{}'
               FROM tasks WHERE task_id=?""",
            ("event-decision-cancel", NOW, task_id),
        )
        connection.execute(
            """UPDATE tasks SET cancel_requested=1, event_head=event_head + 1,
                      updated_at=? WHERE task_id=?""",
            (NOW, task_id),
        )
        connection.commit()
    reader = StoreProductionTaskAuthorityReader(
        store=store,
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
    )

    fact = reader.get_task(SCOPE, task_id)

    assert fact is not None and fact.state.value == "decision_required"
    assert fact.event_head_id == "event-decision-cancel"
    assert fact.decision_required_event_id is None
    assert "task.provide_input" not in fact.supported_operations
    assert "task.cancel" not in fact.supported_operations


def test_store_reader_converges_completion_between_task_and_result_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteTaskStore(tmp_path / "production-reader-result-race.sqlite3")
    task_id, attempt_id = _seed_selected_task(store, tmp_path, suffix="result-race")
    executor_ref, selection = _start_selected_task(
        store,
        task_id=task_id,
        attempt_id=attempt_id,
        suffix="result-race",
    )
    original_result = store.task_result
    completed = False

    def complete_before_result_read(observed_task_id: str, observed_scope: ScopeRef):
        nonlocal completed
        if not completed:
            completed = True
            _complete_selected_task(
                store,
                task_id=task_id,
                attempt_id=attempt_id,
                executor_ref=executor_ref,
                selection=selection,
                suffix="result-race",
            )
        return original_result(observed_task_id, observed_scope)

    monkeypatch.setattr(store, "task_result", complete_before_result_read)
    reader = StoreProductionTaskAuthorityReader(
        store=store,
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
    )

    authority = reader.list_visible_tasks(SCOPE)
    fact = next(item for item in authority.tasks if item.task_id == task_id)

    assert completed
    assert fact.state.value == "terminal"
    assert fact.outcome is TerminalOutcome.COMPLETED
    assert fact.result_digest is not None


def test_store_reader_persistent_generation_churn_fails_closed_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteTaskStore(tmp_path / "production-reader-persistent-race.sqlite3")
    _seed_selected_task(store, tmp_path, suffix="persistent-race")
    original_page = store.list_task_read_snapshots_page
    call_count = 0

    def alternating_page(scope: ScopeRef, *, limit: int, cursor: str | None = None):
        nonlocal call_count
        page = original_page(scope, limit=limit, cursor=cursor)
        call_count += 1
        if call_count % 2 == 1:
            return page
        rows, next_cursor, has_more = page
        task, attempt, admission = rows[0]
        assert admission is not None
        changed = replace(admission, queued=not admission.queued)
        return (((task, attempt, changed),), next_cursor, has_more)

    monkeypatch.setattr(store, "list_task_read_snapshots_page", alternating_page)
    reader = StoreProductionTaskAuthorityReader(
        store=store,
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
    )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as stale:
        reader.list_visible_tasks(SCOPE)

    assert stale.value.reason == "PRODUCTION_TASK_AUTHORITY_CHANGED"
    assert call_count == 6
    assert store.counts() == before


def test_store_reader_projects_completed_result_digest(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "production-reader-result.sqlite3")
    task_id, attempt_id = _seed_selected_task(store, tmp_path, suffix="result")
    executor_ref, selection = _start_selected_task(
        store,
        task_id=task_id,
        attempt_id=attempt_id,
        suffix="result",
    )
    _complete_selected_task(
        store,
        task_id=task_id,
        attempt_id=attempt_id,
        executor_ref=executor_ref,
        selection=selection,
        suffix="result",
    )
    availability, result, _reason = store.task_result(task_id, SCOPE)
    assert result is not None
    expected = hashlib.sha256(canonical_json_bytes(result.to_dict())).hexdigest()
    reader = StoreProductionTaskAuthorityReader(
        store=store,
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
    )

    fact = reader.get_task(SCOPE, task_id)

    assert availability.value == "available"
    assert fact is not None and fact.result_digest == expected
    assert fact.terminal_event_id == fact.event_head_id
    assert "task.create_successor" in fact.supported_operations


def test_store_reader_rejects_corrupt_auxiliary_authority_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteTaskStore(tmp_path / "reader-corrupt.sqlite3")
    task_id, _attempt_id = _seed_selected_task(store, tmp_path, suffix="corrupt-reader")
    page = store.list_task_read_snapshots_page(SCOPE, limit=64)
    assert len(page[0]) == 1
    task, attempt, admission = page[0][0]
    assert attempt.selection is not None
    original_events_page = store.events_page
    head_page = original_events_page(
        task_id,
        SCOPE,
        after_seq=task.event_head - 1,
        limit=1,
    )
    before = store.counts()

    with monkeypatch.context() as scoped:
        corrupt_selection = replace(
            attempt.selection,
            adapter_id="forged-production-adapter",
        )
        corrupt_page = (
            ((task, replace(attempt, selection=corrupt_selection), admission),),
            None,
            False,
        )
        scoped.setattr(
            store,
            "list_task_read_snapshots_page",
            lambda *_args, **_kwargs: corrupt_page,
        )
        with pytest.raises(FormalTaskViolation) as profile_error:
            StoreProductionTaskAuthorityReader(
                store=store,
                principal_id=SCOPE.subject_id,
                scope=SCOPE,
            ).list_visible_tasks(SCOPE)
        assert profile_error.value.reason == (
            "PRODUCTION_TASK_CAPABILITY_AUTHORITY_CORRUPT"
        )

    with monkeypatch.context() as scoped:
        corrupt_event = replace(head_page[0][0], task_id="foreign-task")
        scoped.setattr(
            store,
            "events_page",
            lambda *_args, **_kwargs: (
                (corrupt_event,),
                head_page[1],
                head_page[2],
                head_page[3],
            ),
        )
        with pytest.raises(FormalTaskViolation) as head_error:
            StoreProductionTaskAuthorityReader(
                store=store,
                principal_id=SCOPE.subject_id,
                scope=SCOPE,
            ).list_visible_tasks(SCOPE)
        assert head_error.value.reason == "PRODUCTION_TASK_EVENT_AUTHORITY_CORRUPT"

    with monkeypatch.context() as scoped:
        scoped.setattr(
            store,
            "task_result",
            lambda *_args, **_kwargs: (
                TaskResultAvailability.AVAILABLE,
                None,
                None,
            ),
        )
        with pytest.raises(FormalTaskViolation) as result_error:
            StoreProductionTaskAuthorityReader(
                store=store,
                principal_id=SCOPE.subject_id,
                scope=SCOPE,
            ).list_visible_tasks(SCOPE)
        assert result_error.value.reason == "PRODUCTION_TASK_RESULT_AUTHORITY_CORRUPT"

    with monkeypatch.context() as scoped:
        corrupt_task = replace(
            task,
            predecessor_task_id="missing-predecessor",
            revision_number=2,
        )
        corrupt_page = (((corrupt_task, attempt, admission),), None, False)
        scoped.setattr(
            store,
            "list_task_read_snapshots_page",
            lambda *_args, **_kwargs: corrupt_page,
        )
        with pytest.raises(FormalTaskViolation) as lineage_error:
            StoreProductionTaskAuthorityReader(
                store=store,
                principal_id=SCOPE.subject_id,
                scope=SCOPE,
            ).list_visible_tasks(SCOPE)
        assert lineage_error.value.reason == (
            "PRODUCTION_TASK_LINEAGE_AUTHORITY_INCOMPLETE"
        )

    assert store.counts() == before


@pytest.mark.parametrize(
    "corruption,expected_reason",
    (
        ("revision", "PRODUCTION_TASK_LINEAGE_AUTHORITY_INCOMPLETE"),
        ("duplicate", "PRODUCTION_TASK_LINEAGE_AUTHORITY_CORRUPT"),
    ),
)
def test_store_reader_rejects_revision_and_duplicate_successor_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
    expected_reason: str,
) -> None:
    store = SqliteTaskStore(tmp_path / f"reader-lineage-{corruption}.sqlite3")
    first_id, _ = _seed_selected_task(store, tmp_path, suffix=f"{corruption}-a")
    second_id, _ = _seed_selected_task(store, tmp_path, suffix=f"{corruption}-b")
    if corruption == "duplicate":
        _seed_selected_task(store, tmp_path, suffix=f"{corruption}-c")
    page, cursor, more = store.list_task_read_snapshots_page(SCOPE, limit=64)
    by_id = {item[0].task_id: item for item in page}
    first_revision = by_id[first_id][0].revision_number
    changed = []
    successor_index = 0
    for task, attempt, admission in page:
        if task.task_id == first_id:
            changed.append((task, attempt, admission))
            continue
        if corruption == "revision" and task.task_id == second_id:
            changed_task = replace(
                task,
                predecessor_task_id=first_id,
                revision_number=first_revision + 2,
            )
        else:
            successor_index += 1
            changed_task = replace(
                task,
                predecessor_task_id=first_id,
                revision_number=first_revision + 1,
            )
        changed.append((changed_task, attempt, admission))
    if corruption == "duplicate":
        assert successor_index == 2
    frozen_page = (tuple(changed), cursor, more)
    before = store.counts()
    monkeypatch.setattr(
        store,
        "list_task_read_snapshots_page",
        lambda *_args, **_kwargs: frozen_page,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        StoreProductionTaskAuthorityReader(
            store=store,
            principal_id=SCOPE.subject_id,
            scope=SCOPE,
        ).list_visible_tasks(SCOPE)

    assert raised.value.reason == expected_reason
    assert store.counts() == before


def test_confirmation_consumer_yields_one_exact_call_local_claim(
    tmp_path: Path,
) -> None:
    production = ProductionConfirmationBinding(
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
        command_id="command-production-confirmed",
        origin=ProductionIntentOrigin.STRUCTURED,
        origin_receipt_id="origin.production-confirmed",
        origin_binding_fingerprint="a" * 64,
        operation="task.cancel",
        target_task_id="task-production-confirmed",
        target_attempt_id="attempt-production-confirmed",
        arguments_sha256=hashlib.sha256(b"{}").hexdigest(),
        task_set_fingerprint="b" * 64,
        capability_profile_digest="c" * 64,
        context_fingerprint="d" * 64,
        model_binding_fingerprint="e" * 64,
    )
    p3_binding = P3ConfirmationBinding(
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
        operation=production.operation,
        command_id=production.command_id,
        target_task_id=production.target_task_id,
        intent_fingerprint=production.fingerprint,
    )
    owner_context = P3ConfirmationOwnerContext(
        session_id=SCOPE.session_id,
        correlation_id="correlation-production-confirmed",
        owner_generation=1,
    )
    owner = BoundedP3ConfirmationOwner(
        tmp_path / "production-confirmations.sqlite3",
        enabled=True,
    )
    owner.issue(
        TrustedP3ConfirmationIssue(
            binding=p3_binding,
            owner=owner_context,
            expires_at="2026-08-21T10:02:00Z",
            confirmation_id="confirmation-production-confirmed",
        ),
        now=NOW,
    )
    validated = owner.validate_for_forwarding(
        "confirmation-production-confirmed",
        p3_binding,
        owner_context,
        now=NOW,
    )
    consumer = CallLocalProductionConfirmationConsumer(
        expected_binding=production,
        validated=validated,
        forwarder=ProductP3ConfirmationForwarder(owner),
        now=NOW,
    )

    current = replace(production, task_set_fingerprint="f" * 64)
    assert current != production
    assert current.fingerprint == production.fingerprint
    assert (
        replace(current, target_attempt_id="attempt-production-retried").fingerprint
        != production.fingerprint
    )
    consumed = consumer.verify_and_consume("confirmation-production-confirmed", current)
    resolution = ProductionTaskResolution(
        classification="task_intent",
        operation=production.operation,
        target_task_id=production.target_task_id,
        arguments={},
        confirmation="confirmed",
        outcome=ProductionTaskPolicyOutcome.PROPOSED,
        reason="TASK_MUTATION_PROPOSED",
        command_id=production.command_id,
        origin_receipt_id=production.origin_receipt_id,
        origin_binding_fingerprint=production.origin_binding_fingerprint,
        task_set_fingerprint=current.task_set_fingerprint,
        authority_fingerprint="d" * 64,
        confirmation_consumption_id=consumed.consumption_id,
        confirmation_binding=current,
    )

    claim = consumer.claim_for(resolution)

    assert consumed.replayed is False
    assert claim.production_binding == production
    assert claim.p3_binding == p3_binding
    assert claim.verified.confirmation_id == consumed.confirmation_id
    assert claim.resolution_fingerprint == resolution.fingerprint
    with pytest.raises(FormalTaskViolation) as replay:
        consumer.claim_for(resolution)
    with pytest.raises(FormalTaskViolation) as second_consume:
        consumer.verify_and_consume(consumed.confirmation_id, production)
    assert replay.value.reason == "PRODUCTION_CONFIRMATION_CLAIM_REPLAY"
    assert second_consume.value.reason == "PRODUCTION_CONFIRMATION_CONSUME_REPLAY"
