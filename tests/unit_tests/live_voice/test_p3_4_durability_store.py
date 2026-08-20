# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import copy
import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ErrorCode,
    ScopeRef,
    TerminalOutcome,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.durability_checkpoint import D1Checkpoint
from jiuwenswarm.server.live_voice.durability_authority import (
    _durability_authorization_payload_digest,
    _mint_durability_mutation_authorization,
)
from jiuwenswarm.server.live_voice.durability_effects import (
    EffectObservationKind,
    ExternalEffectBinding,
    ExternalEffectDispatch,
    ExternalEffectIntent,
    ExternalEffectObservation,
    effect_fact_bytes,
)
from jiuwenswarm.server.live_voice.durability_identity import (
    DurabilityProfileBinding,
)
from jiuwenswarm.server.live_voice.durability_readers import DurabilityReadBinding
from jiuwenswarm.server.live_voice.durability_recovery_facts import (
    ExecutorRecoveryFacts,
)
from jiuwenswarm.server.live_voice.executor_capabilities import (
    EXECUTOR_CAPABILITY_PROFILE_SCHEMA_VERSION,
    ExecutorCapabilityProfile,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskViolation,
    PersistedExecutorSelection,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.project_code_executor import (
    FORMAL_PROJECT_EXECUTOR_ID,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_persistent_task_core import (
    NOW,
    _Executor,
    _cancel,
    _create,
    _downgrade_fixture_to_v1,
    _downgrade_fixture_to_v2,
    _downgrade_fixture_to_v3,
    _downgrade_fixture_to_v4,
    _observations,
    _scope,
    _wave2_command,
)

LATER = "2026-08-05T12:05:00Z"
EXPIRY = "2026-08-05T12:10:00Z"
_V6_TABLES = (
    "durability_recovery_fences",
    "durability_mutator_leases",
    "durability_recoveries",
    "durability_effect_facts",
    "durability_checkpoints",
)


def _profile() -> ExecutorCapabilityProfile:
    return ExecutorCapabilityProfile(
        schema_version=EXECUTOR_CAPABILITY_PROFILE_SCHEMA_VERSION,
        profile_id="test.direct.d2.v1",
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        adapter_id="test.direct",
        adapter_protocol_version="v1",
        operation_versions=(("dispatch", "v1"),),
        durability_level="D2",
        durability_version="v1",
        project_serialization="exclusive",
        max_live_attempts=1,
        enforcement_facts=("side-effect.project-mutation",),
    )


def _selection() -> PersistedExecutorSelection:
    profile = _profile()
    return PersistedExecutorSelection.from_values(
        adapter_id=profile.adapter_id,
        capability_profile=profile.to_dict(),
        execution_requirements={
            "schema_version": "live-voice.task-execution-requirements.v1",
            "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
            "operation_versions": [["dispatch", "v1"]],
            "durability_level": "D2",
            "side_effect_class": "project_mutation",
            "project_serialization": "exclusive",
        },
    )


def _binding(selection: PersistedExecutorSelection) -> DurabilityProfileBinding:
    profile = _profile()
    return DurabilityProfileBinding(
        executor_id=profile.executor_id,
        adapter_id=profile.adapter_id,
        profile_id=profile.profile_id,
        profile_version=profile.adapter_protocol_version,
        profile_digest=selection.capability_profile_digest,
        durability_level=profile.durability_level,
        durability_capability_version=profile.durability_version,
    )


def _selected_task(tmp_path: Path):
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    selection = _selection()
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=selection,
    )
    assert created.ok and created.result is not None
    task = store.get_task(str(created.result["task_id"]), _scope())
    binding = DurabilityReadBinding(
        scope=task.scope,
        task_id=task.task_id,
        origin_attempt_id=task.attempt_id,
        profile=_binding(selection),
    )
    return store, selection, task, binding


def _checkpoint(store: SqliteTaskStore, task, binding) -> D1Checkpoint:
    effects = store.read_durability_effects(binding)
    return D1Checkpoint.create(
        checkpoint_id="checkpoint-1",
        scope=task.scope,
        task_id=task.task_id,
        producer_attempt_id=task.attempt_id,
        checkpoint_sequence=1,
        recovery_generation=0,
        profile=binding.profile,
        complete=True,
        task_spec_digest=hashlib.sha256(task.spec.fingerprint_bytes()).hexdigest(),
        context_version=str(task.spec.context.revision_value),
        context_digest=hashlib.sha256(
            canonical_json_bytes(task.spec.context.to_dict())
        ).hexdigest(),
        input_digest=hashlib.sha256(task.spec.instruction.encode()).hexdigest(),
        state_schema_id="test.direct.patch",
        state_schema_version=1,
        state_bytes=b"canonical-state",
        effect_head=effects.head,
        effect_prefix_digest=effects.prefix_digest,
    )


def _mutation_authorization(
    store: SqliteTaskStore,
    binding: DurabilityReadBinding,
    *,
    operation: str,
    payload_digest: str,
    candidate_attempt_id: str | None = None,
    owner_generation: int = 0,
    owner_id: str = "direct-runtime-unit",
):
    claim = store.claim_durability_mutator(
        scope=binding.scope,
        task_id=binding.task_id,
        owner_id=owner_id,
        observed_at=NOW,
        expires_at=EXPIRY,
    )
    assert claim is not None
    checkpoints = store.read_durability_checkpoints(binding)
    effects = store.read_durability_effects(binding)
    return _mint_durability_mutation_authorization(
        store=store,
        operation=operation,
        scope=binding.scope,
        task_id=binding.task_id,
        producer_attempt_id=binding.origin_attempt_id,
        candidate_attempt_id=candidate_attempt_id,
        profile=binding.profile,
        executor_owner_id="direct-runtime-unit",
        executor_owner_generation=owner_generation,
        checkpoint_head=checkpoints.head,
        checkpoint_prefix_digest=checkpoints.prefix_digest,
        effect_head=effects.head,
        effect_prefix_digest=effects.prefix_digest,
        payload_digest=payload_digest,
        claim_owner_id=owner_id,
        claim_token=claim[0],
        claim_generation=claim[1],
    )


def _append_checkpoint(
    store: SqliteTaskStore,
    binding: DurabilityReadBinding,
    checkpoint: D1Checkpoint,
):
    authorization = _mutation_authorization(
        store,
        binding,
        operation="checkpoint.append",
        payload_digest=hashlib.sha256(checkpoint.canonical_bytes()).hexdigest(),
        owner_generation=checkpoint.recovery_generation,
    )
    return store.append_durability_checkpoint(
        checkpoint,
        observed_at=NOW,
        authorization=authorization,
    )


def _recovery_effect_facts(task, binding):
    effect_binding = ExternalEffectBinding(
        scope=task.scope,
        task_id=task.task_id,
        origin_attempt_id=task.attempt_id,
        profile=binding.profile,
        effect_id="effect-recovery-unit",
        operation_kind="project.apply",
        operation_ordinal=1,
        target_digest="2" * 64,
        intended_effect_digest="3" * 64,
    )
    return (
        ExternalEffectIntent(binding=effect_binding, replay_safe=True),
        ExternalEffectDispatch(
            binding=effect_binding,
            actor_attempt_id=task.attempt_id,
            dispatch_ordinal=1,
            recovery_generation=0,
            provider_operation_key="stable-operation-key",
        ),
        ExternalEffectObservation(
            binding=effect_binding,
            actor_attempt_id=task.attempt_id,
            observation_ordinal=1,
            dispatch_ordinal=1,
            recovery_generation=0,
            kind=EffectObservationKind.NO_EFFECT,
            evidence_digest="4" * 64,
        ),
    )


def _safe_recovery_prefix(store: SqliteTaskStore, task, binding):
    facts = _recovery_effect_facts(task, binding)
    for row_sequence, fact in enumerate(facts, start=1):
        authorization = _mutation_authorization(
            store,
            binding,
            operation="effect.append",
            payload_digest=hashlib.sha256(effect_fact_bytes(fact)).hexdigest(),
        )
        store.append_durability_effect_fact(
            fact,
            row_sequence=row_sequence,
            observed_at=NOW,
            authorization=authorization,
        )
    checkpoint = _checkpoint(store, task, binding)
    return _append_checkpoint(store, binding, checkpoint)


def _recovery_authorization(
    store: SqliteTaskStore,
    binding: DurabilityReadBinding,
    facts: ExecutorRecoveryFacts,
    *,
    recovery_id: str,
    owner_id: str,
    claim: tuple[str, int],
):
    checkpoints = store.read_durability_checkpoints(binding)
    effects = store.read_durability_effects(binding)
    return _mint_durability_mutation_authorization(
        store=store,
        operation="recovery.admit.continue",
        scope=binding.scope,
        task_id=binding.task_id,
        producer_attempt_id=binding.origin_attempt_id,
        candidate_attempt_id=facts.candidate_recovery_attempt_id,
        profile=binding.profile,
        executor_owner_id=facts.executor_epoch_id,
        executor_owner_generation=facts.executor_owner_generation,
        checkpoint_head=checkpoints.head,
        checkpoint_prefix_digest=checkpoints.prefix_digest,
        effect_head=effects.head,
        effect_prefix_digest=effects.prefix_digest,
        payload_digest=_durability_authorization_payload_digest(
            {
                "recovery_id": recovery_id,
                "recovery_facts_sha256": hashlib.sha256(
                    facts.canonical_bytes()
                ).hexdigest(),
            }
        ),
        claim_owner_id=owner_id,
        claim_token=claim[0],
        claim_generation=claim[1],
    )


def test_v6_bootstrap_and_v5_migration_rollback_then_reopen(tmp_path: Path) -> None:
    database = tmp_path / "migration.sqlite"
    SqliteTaskStore(database)
    with sqlite3.connect(database) as connection:
        for table in _V6_TABLES:
            connection.execute(f"DROP TABLE {table}")
        connection.execute("UPDATE metadata SET value='5' WHERE key='schema_version'")

    def fail(name: str) -> None:
        if name == "migration.v5_to_v6.before_metadata":
            raise RuntimeError("expected failpoint")

    with pytest.raises(RuntimeError, match="expected failpoint"):
        SqliteTaskStore(database, failpoint=fail)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("5",)
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='durability_checkpoints'"
            ).fetchone()
            is None
        )

    SqliteTaskStore(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("6",)


def test_populated_v5_migration_preserves_admission_consumer_and_restart_truth(
    tmp_path: Path,
) -> None:
    store, selection, task, _binding_value = _selected_task(tmp_path)
    database = Path(store.database_path)
    claimed = store.claim_outbox("v5-restart-worker", observed_at=NOW)
    assert claimed is not None
    accepted = store.events(task.task_id, task.scope)[0]
    acknowledged = store.ack_events(
        _wave2_command(
            task.task_id,
            "task.ack_events",
            {
                "presentation_class": "text",
                "acked_through_seq": accepted.seq,
                "acked_event_id": accepted.event_id,
                "expected_event_head": accepted.seq,
            },
            command_id="command-v5-consumer",
        )[0],
        observed_at=LATER,
    )
    assert acknowledged.ok
    preserved_tables = (
        "tasks",
        "attempts",
        "task_events",
        "commands",
        "outbox",
        "task_event_consumption",
    )

    def snapshot() -> dict[str, list[tuple[object, ...]]]:
        with sqlite3.connect(database) as connection:
            return {
                table: connection.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                ).fetchall()
                for table in preserved_tables
            }

    before = snapshot()
    assert before["task_event_consumption"]
    assert before["outbox"][0]
    with sqlite3.connect(database) as connection:
        for table in _V6_TABLES:
            connection.execute(f"DROP TABLE {table}")
        connection.execute("UPDATE metadata SET value='5' WHERE key='schema_version'")

    def fail(name: str) -> None:
        if name == "migration.v5_to_v6.before_metadata":
            raise RuntimeError("expected populated-v5 failpoint")

    with pytest.raises(RuntimeError, match="expected populated-v5 failpoint"):
        SqliteTaskStore(database, failpoint=fail)
    assert snapshot() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("5",)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reopened = tuple(pool.map(lambda _index: SqliteTaskStore(database), range(2)))

    assert snapshot() == before
    assert all(
        candidate.get_task(task.task_id, task.scope).attempt_id == task.attempt_id
        for candidate in reopened
    )
    assert all(
        candidate.get_attempt(task.attempt_id).selection == selection
        for candidate in reopened
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("6",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_same_cancel_command_id_is_scoped_across_v5_migration_and_reopen(
    tmp_path: Path,
) -> None:
    database = tmp_path / "scoped-cancel-migration.sqlite"
    store = SqliteTaskStore(database)
    selection = _selection()
    core = PersistentTaskCore(store, _Executor())
    first_invocation = _create(tmp_path, identity_suffix="-scope-one")
    first_created = core.execute(
        first_invocation.envelope,
        first_invocation.authorization,
        context=first_invocation.context,
        now=NOW,
        selection=selection,
    )
    assert first_created.ok and first_created.result is not None
    first = store.get_task(str(first_created.result["task_id"]), _scope())

    second_scope = ScopeRef("user-2", "project-2", "session-2", Assurance.AUTHENTICATED)
    second_invocation = _create(tmp_path, identity_suffix="-scope-two")
    second_created = core.execute(
        replace(second_invocation.envelope, scope=second_scope),
        replace(
            second_invocation.authorization,
            principal_id=second_scope.subject_id,
            scope=second_scope,
        ),
        context=replace(
            second_invocation.context,
            stable_id=second_scope.project_id,
            scope=second_scope,
        ),
        now=NOW,
        selection=selection,
    )
    assert second_created.ok and second_created.result is not None
    second = store.get_task(str(second_created.result["task_id"]), second_scope)

    tasks_by_id = {first.task_id: first, second.task_id: second}
    claimed_task_ids: set[str] = set()
    for owner_id in ("producer-one", "producer-two"):
        item = store.claim_outbox(owner_id, observed_at=NOW)
        assert item is not None and item.task_id in tasks_by_id
        claimed_task_ids.add(item.task_id)
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=tuple(
                replace(
                    observation,
                    adapter_id=selection.adapter_id,
                    capability_profile_digest=selection.capability_profile_digest,
                )
                for observation in _observations(
                    item, outcome=TerminalOutcome.INTERRUPTED
                )
            ),
        )
    assert claimed_task_ids == set(tasks_by_id)

    with sqlite3.connect(database) as connection:
        for table in _V6_TABLES:
            connection.execute(f"DROP TABLE {table}")
        connection.execute("UPDATE metadata SET value='5' WHERE key='schema_version'")

    with ThreadPoolExecutor(max_workers=2) as pool:
        migrated = tuple(pool.map(lambda _index: SqliteTaskStore(database), range(2)))

    shared_command_id = "same-cancel-command"
    first_cancel = replace(
        _cancel(first.task_id).envelope,
        command_id=shared_command_id,
        request_id="cancel-request-scope-one",
        correlation_id="cancel-correlation-scope-one",
    )
    second_cancel = replace(
        _cancel(second.task_id).envelope,
        command_id=shared_command_id,
        request_id="cancel-request-scope-two",
        correlation_id="cancel-correlation-scope-two",
        scope=second_scope,
    )
    assert migrated[0].cancel(first_cancel, observed_at=LATER).error is not None
    assert migrated[1].cancel(second_cancel, observed_at=LATER).error is not None

    reopened = SqliteTaskStore(database)
    assert reopened.get_task(first.task_id, first.scope).attempt_id == first.attempt_id
    assert (
        reopened.get_task(second.task_id, second.scope).attempt_id == second.attempt_id
    )
    with sqlite3.connect(database) as connection:
        fences = connection.execute(
            """SELECT t.scope_key, f.cancel_command_id
               FROM durability_recovery_fences AS f
               JOIN tasks AS t ON t.task_id=f.task_id
               ORDER BY t.scope_key"""
        ).fetchall()
        assert len(fences) == 2
        assert {row[1] for row in fences} == {shared_command_id}
        assert len({row[0] for row in fences}) == 2
        commands = connection.execute(
            """SELECT scope_key, command_id FROM commands
               WHERE command_id=? ORDER BY scope_key""",
            (shared_command_id,),
        ).fetchall()
        assert len(commands) == 2
        assert {row[1] for row in commands} == {shared_command_id}
        assert len({row[0] for row in commands}) == 2
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("6",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    "version,downgrade",
    (
        (1, _downgrade_fixture_to_v1),
        (2, _downgrade_fixture_to_v2),
        (3, _downgrade_fixture_to_v3),
        (4, _downgrade_fixture_to_v4),
    ),
)
def test_v1_v4_reopen_migrates_once_to_v6_with_task_truth_preserved(
    tmp_path: Path,
    version: int,
    downgrade,
) -> None:
    store = SqliteTaskStore(tmp_path / f"v{version}.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task = store.get_task(str(created.result["task_id"]), _scope())
    before = store.get_task(task.task_id, task.scope)
    downgrade(Path(store.database_path))
    with sqlite3.connect(store.database_path) as connection:
        for table in _V6_TABLES:
            connection.execute(f"DROP TABLE {table}")
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == (str(version),)

    reopened = SqliteTaskStore(store.database_path)

    assert reopened.get_task(task.task_id, task.scope).attempt_id == before.attempt_id
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("6",)


def test_two_concurrent_initializers_converge_on_schema_v6(tmp_path: Path) -> None:
    database = tmp_path / "concurrent-initializers.sqlite"
    with ThreadPoolExecutor(max_workers=2) as pool:
        stores = tuple(pool.map(lambda _index: SqliteTaskStore(database), range(2)))

    assert all(store.counts()["attempts"] == 0 for store in stores)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("6",)


def test_checkpoint_is_immutable_and_corruption_fails_reopen(tmp_path: Path) -> None:
    store, _selection_value, task, binding = _selected_task(tmp_path)
    checkpoint = _checkpoint(store, task, binding)

    first = _append_checkpoint(store, binding, checkpoint)
    replay = _append_checkpoint(store, binding, checkpoint)
    assert replay == first
    assert first.records == (checkpoint,)

    changed = D1Checkpoint.create(
        checkpoint_id="checkpoint-changed",
        scope=checkpoint.scope,
        task_id=checkpoint.task_id,
        producer_attempt_id=checkpoint.producer_attempt_id,
        checkpoint_sequence=checkpoint.checkpoint_sequence,
        recovery_generation=checkpoint.recovery_generation,
        profile=checkpoint.profile,
        complete=True,
        task_spec_digest=checkpoint.task_spec_digest,
        context_version=checkpoint.context_version,
        context_digest=checkpoint.context_digest,
        input_digest=checkpoint.input_digest,
        state_schema_id=checkpoint.state_schema_id,
        state_schema_version=checkpoint.state_schema_version,
        state_bytes=b"changed-canonical-state",
        effect_head=checkpoint.effect_head,
        effect_prefix_digest=checkpoint.effect_prefix_digest,
    )
    with pytest.raises(FormalTaskViolation) as conflict:
        _append_checkpoint(store, binding, changed)
    assert conflict.value.reason == "DURABILITY_PREFIX_CONFLICT"

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE durability_checkpoints SET canonical=?",
            (b"{}",),
        )
    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(store.database_path)
    assert rejected.value.reason == "TASK_STORE_CORRUPT"


def test_raw_authority_free_checkpoint_cannot_mutate_store(tmp_path: Path) -> None:
    store, _selection_value, task, binding = _selected_task(tmp_path)
    checkpoint = _checkpoint(store, task, binding)
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as rejected:
        store.append_durability_checkpoint(checkpoint, observed_at=NOW)

    assert rejected.value.reason == "DURABILITY_MUTATION_AUTHORIZATION_REQUIRED"
    assert store.counts() == before
    assert store.read_durability_checkpoints(binding).records == ()
    assert store.read_durability_effects(binding).records == ()

    with pytest.raises(FormalTaskViolation) as effect_rejected:
        store.append_durability_effect_fact(
            _recovery_effect_facts(task, binding)[0],
            row_sequence=1,
            observed_at=NOW,
        )

    assert effect_rejected.value.reason == (
        "DURABILITY_MUTATION_AUTHORIZATION_REQUIRED"
    )
    assert store.counts() == before
    assert store.read_durability_checkpoints(binding).records == ()
    assert store.read_durability_effects(binding).records == ()


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    (
        ("operation", lambda authorization, _foreign: "effect.append"),
        (
            "scope",
            lambda authorization, _foreign: replace(
                authorization.scope, subject_id="foreign-subject"
            ),
        ),
        ("task_id", lambda authorization, _foreign: "task-foreign"),
        (
            "producer_attempt_id",
            lambda authorization, _foreign: "attempt-foreign",
        ),
        (
            "candidate_attempt_id",
            lambda authorization, _foreign: "attempt-candidate",
        ),
        (
            "profile",
            lambda authorization, _foreign: replace(
                authorization.profile, profile_id="foreign-profile"
            ),
        ),
        (
            "executor_owner_id",
            lambda authorization, _foreign: "foreign-runtime",
        ),
        (
            "executor_owner_generation",
            lambda authorization, _foreign: authorization.executor_owner_generation + 1,
        ),
        (
            "checkpoint_head",
            lambda authorization, _foreign: authorization.checkpoint_head + 1,
        ),
        (
            "checkpoint_prefix_digest",
            lambda authorization, _foreign: "a" * 64,
        ),
        (
            "effect_head",
            lambda authorization, _foreign: authorization.effect_head + 1,
        ),
        (
            "effect_prefix_digest",
            lambda authorization, _foreign: "b" * 64,
        ),
        ("payload_digest", lambda authorization, _foreign: "c" * 64),
        ("claim_owner_id", lambda authorization, _foreign: "foreign-claim-owner"),
        ("claim_token", lambda authorization, _foreign: "foreign-claim-token"),
        (
            "claim_generation",
            lambda authorization, _foreign: authorization.claim_generation + 1,
        ),
        ("_store_identity", lambda authorization, foreign: foreign),
    ),
)
def test_changed_receipt_field_is_not_transformable_authority(
    tmp_path: Path,
    field_name: str,
    changed_value,
) -> None:
    store, _selection_value, task, binding = _selected_task(tmp_path)
    checkpoint = _checkpoint(store, task, binding)
    authorization = _mutation_authorization(
        store,
        binding,
        operation="checkpoint.append",
        payload_digest=hashlib.sha256(checkpoint.canonical_bytes()).hexdigest(),
    )
    foreign_store = SqliteTaskStore(tmp_path / "foreign-store.sqlite")
    transformed = replace(
        authorization,
        **{field_name: changed_value(authorization, foreign_store)},
    )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as rejected:
        store.append_durability_checkpoint(
            checkpoint,
            observed_at=NOW,
            authorization=transformed,
        )

    assert rejected.value.reason == "DURABILITY_MUTATION_AUTHORIZATION_INVALID"
    assert store.counts() == before
    assert store.read_durability_checkpoints(binding).records == ()
    assert store.read_durability_effects(binding).records == ()


def test_copied_receipt_is_not_reusable_authority(tmp_path: Path) -> None:
    store, _selection_value, task, binding = _selected_task(tmp_path)
    checkpoint = _checkpoint(store, task, binding)
    authorization = _mutation_authorization(
        store,
        binding,
        operation="checkpoint.append",
        payload_digest=hashlib.sha256(checkpoint.canonical_bytes()).hexdigest(),
    )
    copied = copy.copy(authorization)
    assert copied is not authorization
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as rejected:
        store.append_durability_checkpoint(
            checkpoint,
            observed_at=NOW,
            authorization=copied,
        )

    assert rejected.value.reason == "DURABILITY_MUTATION_AUTHORIZATION_INVALID"
    assert store.counts() == before
    assert store.read_durability_checkpoints(binding).records == ()
    assert store.read_durability_effects(binding).records == ()


def test_two_store_instances_share_one_mutator_claim(tmp_path: Path) -> None:
    first, _selection_value, task, _binding_value = _selected_task(tmp_path)
    second = SqliteTaskStore(first.database_path)

    claimed = first.claim_durability_mutator(
        scope=task.scope,
        task_id=task.task_id,
        owner_id="worker-a",
        observed_at=NOW,
        expires_at=EXPIRY,
    )
    assert claimed is not None
    assert (
        second.claim_durability_mutator(
            scope=task.scope,
            task_id=task.task_id,
            owner_id="worker-b",
            observed_at=LATER,
            expires_at=EXPIRY,
        )
        is None
    )
    assert not second.release_durability_mutator(
        scope=task.scope,
        task_id=task.task_id,
        owner_id="worker-b",
        claim_token=claimed[0],
        claim_generation=claimed[1],
    )


def test_linked_recovery_requires_exact_facts_and_wins_cancel_race_once(
    tmp_path: Path,
) -> None:
    store, selection, task, binding = _selected_task(tmp_path)
    checkpoint_prefix = _safe_recovery_prefix(store, task, binding)
    item = store.claim_outbox("producer", observed_at=NOW)
    assert item is not None
    observations = tuple(
        replace(
            observation,
            adapter_id=selection.adapter_id,
            capability_profile_digest=selection.capability_profile_digest,
        )
        for observation in _observations(item, outcome=TerminalOutcome.INTERRUPTED)
    )
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )
    assert store.get_task(task.task_id, task.scope).outcome is (
        TerminalOutcome.INTERRUPTED
    )
    authority = store.read_durable_recovery_authority(
        scope=task.scope,
        task_id=task.task_id,
    )
    claim = store.claim_durability_mutator(
        scope=task.scope,
        task_id=task.task_id,
        owner_id="recovery-worker",
        observed_at=NOW,
        expires_at=EXPIRY,
    )
    assert claim is not None
    effects = store.read_durability_effects(binding)
    facts = ExecutorRecoveryFacts.create(
        scope=task.scope,
        task_id=task.task_id,
        producer_attempt_id=task.attempt_id,
        candidate_recovery_attempt_id="attempt-linked-recovery",
        profile=binding.profile,
        recovery_generation=1,
        executor_epoch_id="direct-epoch",
        executor_owner_generation=1,
        observed_at=NOW,
        expires_at=EXPIRY,
        evidence_digest="1" * 64,
    )

    before_unauthorized = store.counts()
    before_unauthorized_events = store.events(task.task_id, task.scope)
    with pytest.raises(FormalTaskViolation) as unauthorized:
        store.recover_durable_attempt(
            authority,
            recovery_id="recovery-1",
            recovery_facts=facts,
            checkpoint_head=checkpoint_prefix.head,
            checkpoint_prefix_digest=checkpoint_prefix.prefix_digest,
            effect_head=effects.head,
            effect_prefix_digest=effects.prefix_digest,
            observed_at=NOW,
        )
    assert unauthorized.value.reason == ("DURABILITY_MUTATION_AUTHORIZATION_REQUIRED")
    assert store.counts() == before_unauthorized
    assert store.events(task.task_id, task.scope) == before_unauthorized_events
    assert store.read_durability_checkpoints(binding) == checkpoint_prefix
    assert store.read_durability_effects(binding) == effects

    recovered_attempt = store.recover_durable_attempt(
        authority,
        recovery_id="recovery-1",
        recovery_facts=facts,
        checkpoint_head=checkpoint_prefix.head,
        checkpoint_prefix_digest=checkpoint_prefix.prefix_digest,
        effect_head=effects.head,
        effect_prefix_digest=effects.prefix_digest,
        authorization=_recovery_authorization(
            store,
            binding,
            facts,
            recovery_id="recovery-1",
            owner_id="recovery-worker",
            claim=claim,
        ),
        observed_at=NOW,
    )
    assert recovered_attempt.attempt_id == "attempt-linked-recovery"
    assert store.get_attempt(task.attempt_id).outcome is TerminalOutcome.INTERRUPTED
    assert store.get_task(task.task_id, task.scope).attempt_id == (
        "attempt-linked-recovery"
    )
    assert store.events(task.task_id, task.scope)[-1].event_type == (
        "task.recovery_accepted"
    )
    assert (
        SqliteTaskStore(store.database_path)
        .get_task(task.task_id, task.scope)
        .attempt_id
        == "attempt-linked-recovery"
    )
    prior = checkpoint_prefix.records[-1]
    later_checkpoint = D1Checkpoint.create(
        checkpoint_id="checkpoint-later-tip",
        scope=prior.scope,
        task_id=prior.task_id,
        producer_attempt_id=prior.producer_attempt_id,
        checkpoint_sequence=prior.checkpoint_sequence + 1,
        recovery_generation=prior.recovery_generation,
        profile=prior.profile,
        complete=True,
        task_spec_digest=prior.task_spec_digest,
        context_version=prior.context_version,
        context_digest=prior.context_digest,
        input_digest=prior.input_digest,
        state_schema_id=prior.state_schema_id,
        state_schema_version=prior.state_schema_version,
        state_bytes=prior.state_bytes,
        effect_head=prior.effect_head,
        effect_prefix_digest=prior.effect_prefix_digest,
    )
    _append_checkpoint(store, binding, later_checkpoint)
    before_stale_dispatch = store.counts()
    before_stale_events = store.events(task.task_id, task.scope)
    with pytest.raises(FormalTaskViolation) as stale_dispatch:
        store.read_durable_recovery_dispatch(
            scope=task.scope,
            task_id=task.task_id,
            recovery_attempt_id="attempt-linked-recovery",
        )
    assert stale_dispatch.value.reason == "TASK_RECOVERY_PREFIX_STALE"
    assert store.counts() == before_stale_dispatch
    assert store.events(task.task_id, task.scope) == before_stale_events


def test_recovery_missing_checkpoint_fails_closed_without_task_or_external_effects(
    tmp_path: Path,
) -> None:
    store, _selection_value, task, binding = _selected_task(tmp_path)
    before = store.counts()
    with pytest.raises(FormalTaskViolation) as rejected:
        store.read_durable_recovery_authority(scope=task.scope, task_id=task.task_id)
    assert rejected.value.code in {ErrorCode.CONFLICT, ErrorCode.CAPABILITY_UNAVAILABLE}
    assert store.counts() == before
    assert store.read_durability_effects(binding).records == ()


@pytest.mark.asyncio
async def test_generic_executor_cannot_mint_recovery_or_mutate_any_authority(
    tmp_path: Path,
) -> None:
    store, selection, task, binding = _selected_task(tmp_path)
    checkpoints = _safe_recovery_prefix(store, task, binding)
    effects = store.read_durability_effects(binding)
    item = store.claim_outbox("generic-producer", observed_at=NOW)
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=tuple(
            replace(
                observation,
                adapter_id=selection.adapter_id,
                capability_profile_digest=selection.capability_profile_digest,
            )
            for observation in _observations(item, outcome=TerminalOutcome.INTERRUPTED)
        ),
    )
    before_counts = store.counts()
    before_events = store.events(task.task_id, task.scope)

    with pytest.raises(FormalTaskViolation) as rejected:
        await PersistentTaskCore(store, _Executor()).recover_durable_attempt(
            scope=task.scope,
            task_id=task.task_id,
            operator_id="operator-generic",
            observed_at=NOW,
        )

    assert rejected.value.reason == "EXECUTOR_DURABILITY_UNAVAILABLE"
    assert store.counts() == before_counts
    assert store.events(task.task_id, task.scope) == before_events
    assert store.read_durability_checkpoints(binding) == checkpoints
    assert store.read_durability_effects(binding) == effects


def test_real_cancel_fence_wins_concurrent_recovery_with_zero_recovery_effects(
    tmp_path: Path,
) -> None:
    store, selection, task, binding = _selected_task(tmp_path)
    checkpoint_prefix = _safe_recovery_prefix(store, task, binding)
    item = store.claim_outbox("producer", observed_at=NOW)
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=tuple(
            replace(
                observation,
                adapter_id=selection.adapter_id,
                capability_profile_digest=selection.capability_profile_digest,
            )
            for observation in _observations(item, outcome=TerminalOutcome.INTERRUPTED)
        ),
    )
    authority = store.read_durable_recovery_authority(
        scope=task.scope, task_id=task.task_id
    )
    effects = store.read_durability_effects(binding)
    claim = store.claim_durability_mutator(
        scope=task.scope,
        task_id=task.task_id,
        owner_id="recovery-worker",
        observed_at=NOW,
        expires_at=EXPIRY,
    )
    assert claim is not None
    facts = ExecutorRecoveryFacts.create(
        scope=task.scope,
        task_id=task.task_id,
        producer_attempt_id=task.attempt_id,
        candidate_recovery_attempt_id="attempt-must-not-exist",
        profile=binding.profile,
        recovery_generation=1,
        executor_epoch_id="direct-epoch",
        executor_owner_generation=1,
        observed_at=NOW,
        expires_at=EXPIRY,
        evidence_digest="2" * 64,
    )
    cancel = _cancel(task.task_id).envelope
    fence_entered = threading.Event()
    release_fence = threading.Event()

    def hold_cancel_transaction(name: str) -> None:
        if name == "durability.recovery_fence.after_insert":
            fence_entered.set()
            assert release_fence.wait(timeout=10)

    cancel_store = SqliteTaskStore(
        store.database_path, failpoint=hold_cancel_transaction
    )
    recovery_store = SqliteTaskStore(store.database_path)
    recovery_authorization = _recovery_authorization(
        recovery_store,
        recovery_store.read_durability_binding(
            scope=task.scope,
            task_id=task.task_id,
            origin_attempt_id=task.attempt_id,
        ),
        facts,
        recovery_id="recovery-loses-to-cancel",
        owner_id="recovery-worker",
        claim=claim,
    )
    before = store.counts()
    before_events = store.events(task.task_id, task.scope)

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancelling = pool.submit(cancel_store.cancel, cancel, observed_at=LATER)
        assert fence_entered.wait(timeout=10)
        recovering = pool.submit(
            recovery_store.recover_durable_attempt,
            authority,
            recovery_id="recovery-loses-to-cancel",
            recovery_facts=facts,
            checkpoint_head=checkpoint_prefix.head,
            checkpoint_prefix_digest=checkpoint_prefix.prefix_digest,
            effect_head=effects.head,
            effect_prefix_digest=effects.prefix_digest,
            authorization=recovery_authorization,
            observed_at=LATER,
        )
        release_fence.set()
        cancelled = cancelling.result(timeout=10)
        with pytest.raises(FormalTaskViolation) as rejected:
            recovering.result(timeout=10)

    assert not cancelled.ok
    assert cancelled.error is not None
    assert cancelled.error.reason == "TASK_ALREADY_TERMINAL"
    assert rejected.value.reason == "TASK_RECOVERY_FACTS_STALE"
    after = store.counts()
    assert after["attempts"] == before["attempts"]
    assert after["outbox"] == before["outbox"]
    assert store.events(task.task_id, task.scope) == before_events
    assert store.get_task(task.task_id, task.scope).attempt_id == task.attempt_id
