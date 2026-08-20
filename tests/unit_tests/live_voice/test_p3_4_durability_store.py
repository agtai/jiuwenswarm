# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    TerminalOutcome,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.durability_checkpoint import D1Checkpoint
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

    first = store.append_durability_checkpoint(checkpoint, observed_at=NOW)
    replay = store.append_durability_checkpoint(checkpoint, observed_at=NOW)
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
        store.append_durability_checkpoint(changed, observed_at=NOW)
    assert conflict.value.reason == "DURABILITY_PREFIX_CONFLICT"

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE durability_checkpoints SET canonical=?",
            (b"{}",),
        )
    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(store.database_path)
    assert rejected.value.reason == "TASK_STORE_CORRUPT"


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
    checkpoint = _checkpoint(store, task, binding)
    checkpoint_prefix = store.append_durability_checkpoint(checkpoint, observed_at=NOW)
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

    recovered_attempt = store.recover_durable_attempt(
        authority,
        recovery_id="recovery-1",
        recovery_facts=facts,
        checkpoint_head=checkpoint_prefix.head,
        checkpoint_prefix_digest=checkpoint_prefix.prefix_digest,
        effect_head=effects.head,
        effect_prefix_digest=effects.prefix_digest,
        claim_owner_id="recovery-worker",
        claim_token=claim[0],
        claim_generation=claim[1],
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


def test_real_cancel_fence_wins_concurrent_recovery_with_zero_recovery_effects(
    tmp_path: Path,
) -> None:
    store, selection, task, binding = _selected_task(tmp_path)
    checkpoint_prefix = store.append_durability_checkpoint(
        _checkpoint(store, task, binding), observed_at=NOW
    )
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
            claim_owner_id="recovery-worker",
            claim_token=claim[0],
            claim_generation=claim[1],
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
