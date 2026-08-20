# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    TerminalOutcome,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.durability_effects import (
    EffectObservationKind,
    EffectSettlementKind,
    ExternalEffectDispatch,
    ExternalEffectIntent,
    ExternalEffectObservation,
    ExternalEffectSettlement,
)
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    _AttemptOwnershipLock,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_persistent_task_core import (
    NOW,
    _create,
    _scope,
)
from tests.unit_tests.live_voice.test_project_code_executor import (
    _DirectProjectExecutor,
    _Resolver,
    _direct_binding,
    _direct_selection,
    _git_project,
    _wait_direct_settled,
)


def _durability_binding(store: SqliteTaskStore, task_id: str, attempt_id: str):
    return store.read_durability_binding(
        scope=_scope(), task_id=task_id, origin_attempt_id=attempt_id
    )


def _create_selected_task(
    store: SqliteTaskStore,
    core: PersistentTaskCore,
    project: Path,
):
    invocation = _create(project)
    selection = _direct_selection()
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=selection,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    return selection, store.get_task(task_id, _scope())


@pytest.mark.asyncio
async def test_direct_d2_public_dispatch_commits_checkpoint_and_intent_before_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(database)
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        database,
        durability_store=store,
    )
    core = PersistentTaskCore(store, adapter)
    selection, task = _create_selected_task(store, core, project)
    assert adapter.capability_profile().durability_level == "D2"
    seen_before_apply: list[tuple[int, tuple[type[object], ...]]] = []

    from jiuwenswarm.server.live_voice import project_code_executor

    real_apply = project_code_executor._apply_attempt_patch

    def observed_apply(*args, **kwargs):
        binding = _durability_binding(store, task.task_id, task.attempt_id)
        checkpoints = store.read_durability_checkpoints(binding)
        effects = store.read_durability_effects(binding)
        seen_before_apply.append(
            (checkpoints.head, tuple(type(record) for record in effects.records))
        )
        assert checkpoints.records[-1].effect_head == 0
        assert tuple(type(record) for record in effects.records) == (
            ExternalEffectIntent,
            ExternalEffectDispatch,
        )
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", observed_apply)

    assert await core.drain_outbox_once(worker_id="runtime-red", observed_at=NOW)
    await _wait_direct_settled(adapter)
    await core.reconcile()

    binding = _durability_binding(store, task.task_id, task.attempt_id)
    checkpoints = store.read_durability_checkpoints(binding)
    effects = store.read_durability_effects(binding)
    assert seen_before_apply
    assert checkpoints.records[-1].profile.profile_digest == (
        selection.capability_profile_digest
    )
    assert [type(record) for record in effects.records] == [
        ExternalEffectIntent,
        ExternalEffectDispatch,
        project_code_executor.EffectDispatchReceipt,
        ExternalEffectObservation,
        ExternalEffectSettlement,
    ]
    assert effects.records[-2].kind is EffectObservationKind.APPLIED
    assert effects.records[-1].kind is EffectSettlementKind.RESOLVED
    assert (project / "result.txt").read_text(encoding="utf-8") == "done"
    await adapter.close()


@pytest.mark.asyncio
async def test_core_operator_recovery_uses_fresh_direct_quiescence_and_linked_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(database)
    executor = _DirectProjectExecutor(project)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        database,
        durability_store=store,
    )
    core = PersistentTaskCore(store, adapter)
    _selection, task = _create_selected_task(store, core, project)
    entered = Event()
    release = Event()
    real_reserve = adapter._journal.reserve_completion

    def blocked_reserve(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return real_reserve(*args, **kwargs)

    monkeypatch.setattr(adapter._journal, "reserve_completion", blocked_reserve)
    assert await core.drain_outbox_once(worker_id="producer", observed_at=NOW)
    assert await asyncio.to_thread(entered.wait, 10)
    closing = asyncio.create_task(adapter.close(interrupt_running=True))
    for _ in range(100):
        if task.attempt_id in adapter._interruptions:
            break
        await asyncio.sleep(0.001)
    assert task.attempt_id in adapter._interruptions
    release.set()
    await closing
    await _wait_direct_settled(adapter)

    recovery_executor = _DirectProjectExecutor(project)
    restarted = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, recovery_executor)),
        database,
        durability_store=SqliteTaskStore(database),
    )
    restarted_core = PersistentTaskCore(restarted._durability_store, restarted)
    await restarted_core.reconcile_status()
    interrupted_task = restarted._durability_store.get_task(task.task_id, task.scope)
    producer = restarted._durability_store.get_attempt(task.attempt_id)
    assert interrupted_task.outcome is TerminalOutcome.INTERRUPTED
    assert producer.outcome is TerminalOutcome.INTERRUPTED
    assert (
        await restarted.reconcile_durable_effects(
            scope=task.scope,
            task_id=task.task_id,
            origin_attempt_id=task.attempt_id,
            observed_at="2026-08-05T12:04:00Z",
        )
        == "no_effect"
    )

    binding = _durability_binding(
        restarted._durability_store, task.task_id, task.attempt_id
    )
    authority = restarted._durability_store.read_durable_recovery_authority(
        scope=task.scope, task_id=task.task_id
    )
    with pytest.raises(FormalTaskViolation) as profile_mismatch:
        restarted.recovery_facts(
            authority.task,
            authority.producer_attempt,
            candidate_recovery_attempt_id="profile-mismatch",
            profile=replace(binding.profile, profile_id="changed-profile"),
            recovery_generation=authority.recovery_generation,
            observed_at="2026-08-05T12:05:00Z",
            expires_at="2026-08-05T12:10:00Z",
        )
    assert profile_mismatch.value.reason == "EXECUTOR_RECOVERY_BINDING_MISMATCH"
    changed_context = replace(
        authority.task.spec.context,
        revision_value="changed-context-version",
    )
    changed_task = replace(
        authority.task,
        spec=replace(authority.task.spec, context=changed_context),
    )
    with pytest.raises(FormalTaskViolation) as context_mismatch:
        restarted.recovery_facts(
            changed_task,
            authority.producer_attempt,
            candidate_recovery_attempt_id="context-mismatch",
            profile=binding.profile,
            recovery_generation=authority.recovery_generation,
            observed_at="2026-08-05T12:05:00Z",
            expires_at="2026-08-05T12:10:00Z",
        )
    assert context_mismatch.value.reason == "EXECUTOR_RECOVERY_NOT_QUIESCENT"

    linked = await restarted_core.recover_durable_attempt(
        scope=task.scope,
        task_id=task.task_id,
        operator_id="operator-1",
        observed_at="2026-08-05T12:05:00Z",
    )
    assert linked.attempt_id != producer.attempt_id
    assert restarted._durability_store.get_attempt(producer.attempt_id) == producer
    assert await restarted_core.drain_outbox_once(
        worker_id="linked", observed_at="2026-08-05T12:05:01Z"
    )
    completed = restarted._durability_store.get_task(task.task_id, task.scope)
    assert completed.outcome is TerminalOutcome.COMPLETED
    assert completed.attempt_id == linked.attempt_id
    assert len(executor.requests) == 1
    assert recovery_executor.requests == []
    assert (project / "result.txt").read_text(encoding="utf-8") == "done"
    await restarted.close()


@pytest.mark.asyncio
async def test_direct_restart_reconciles_crash_after_apply_without_duplicate_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(database)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        database,
        durability_store=store,
    )
    core = PersistentTaskCore(store, adapter)
    _selection, task = _create_selected_task(store, core, project)
    real_append = store.append_durability_effect_fact
    apply_calls = 0

    from jiuwenswarm.server.live_voice import project_code_executor

    real_apply = project_code_executor._apply_attempt_patch

    def counted_apply(*args, **kwargs):
        nonlocal apply_calls
        apply_calls += 1
        return real_apply(*args, **kwargs)

    def fail_receipt(fact, *, row_sequence: int, observed_at: str):
        if row_sequence == 3:
            raise RuntimeError("simulated Store ACK loss")
        return real_append(fact, row_sequence=row_sequence, observed_at=observed_at)

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", counted_apply)
    monkeypatch.setattr(store, "append_durability_effect_fact", fail_receipt)
    assert await core.drain_outbox_once(worker_id="producer", observed_at=NOW)
    await _wait_direct_settled(adapter)
    assert apply_calls == 1
    monkeypatch.setattr(store, "append_durability_effect_fact", real_append)

    restarted = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        database,
        durability_store=SqliteTaskStore(database),
    )
    result = await restarted.reconcile_durable_effects(
        scope=task.scope,
        task_id=task.task_id,
        origin_attempt_id=task.attempt_id,
        observed_at="2026-08-05T12:05:00Z",
    )
    effects = restarted._durability_store.read_durability_effects(
        _durability_binding(restarted._durability_store, task.task_id, task.attempt_id)
    )
    assert result == "applied"
    assert apply_calls == 1
    assert isinstance(effects.records[-2], ExternalEffectObservation)
    assert effects.records[-2].kind is EffectObservationKind.APPLIED
    assert isinstance(effects.records[-1], ExternalEffectSettlement)
    assert effects.records[-1].kind is EffectSettlementKind.RESOLVED
    await adapter.close()
    await restarted.close()


@pytest.mark.asyncio
async def test_direct_ambiguous_observation_requires_manual_without_second_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(database)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        database,
        durability_store=store,
    )
    core = PersistentTaskCore(store, adapter)
    _selection, task = _create_selected_task(store, core, project)
    real_append = store.append_durability_effect_fact
    apply_calls = 0

    from jiuwenswarm.server.live_voice import project_code_executor

    real_apply = project_code_executor._apply_attempt_patch

    def counted_apply(*args, **kwargs):
        nonlocal apply_calls
        apply_calls += 1
        return real_apply(*args, **kwargs)

    def fail_receipt(fact, *, row_sequence: int, observed_at: str):
        if row_sequence == 3:
            raise RuntimeError("simulated Store ACK loss")
        return real_append(fact, row_sequence=row_sequence, observed_at=observed_at)

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", counted_apply)
    monkeypatch.setattr(store, "append_durability_effect_fact", fail_receipt)
    assert await core.drain_outbox_once(worker_id="producer", observed_at=NOW)
    await _wait_direct_settled(adapter)
    assert apply_calls == 1
    monkeypatch.setattr(store, "append_durability_effect_fact", real_append)
    (project / "result.txt").write_text("ambiguous external bytes", encoding="utf-8")

    restarted_store = SqliteTaskStore(database)
    restarted = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        database,
        durability_store=restarted_store,
    )
    first = await restarted.reconcile_durable_effects(
        scope=task.scope,
        task_id=task.task_id,
        origin_attempt_id=task.attempt_id,
        observed_at="2026-08-05T12:05:00Z",
    )
    second = await restarted.reconcile_durable_effects(
        scope=task.scope,
        task_id=task.task_id,
        origin_attempt_id=task.attempt_id,
        observed_at="2026-08-05T12:06:00Z",
    )
    effects = restarted_store.read_durability_effects(
        _durability_binding(restarted_store, task.task_id, task.attempt_id)
    )
    assert first == second == "manual_required"
    assert apply_calls == 1
    assert isinstance(effects.records[-2], ExternalEffectObservation)
    assert effects.records[-2].kind is EffectObservationKind.UNKNOWN
    assert isinstance(effects.records[-1], ExternalEffectSettlement)
    assert effects.records[-1].kind is EffectSettlementKind.MANUAL_REQUIRED
    await adapter.close()
    await restarted.close()


@pytest.mark.asyncio
async def test_direct_recovery_facts_require_runtime_then_os_fence_quiescence(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(database)
    executor = _DirectProjectExecutor(project, behavior="wait")
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, executor)),
        database,
        durability_store=store,
    )
    core = PersistentTaskCore(store, adapter)
    _selection, task = _create_selected_task(store, core, project)
    assert await core.drain_outbox_once(worker_id="producer", observed_at=NOW)
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    running_task = store.get_task(task.task_id, task.scope)
    running_attempt = store.get_attempt(task.attempt_id)
    interrupted_task = replace(
        running_task,
        state=type(running_task.state).TERMINAL,
        outcome=TerminalOutcome.INTERRUPTED,
    )
    interrupted_attempt = replace(
        running_attempt,
        state=type(running_attempt.state).TERMINAL,
        outcome=TerminalOutcome.INTERRUPTED,
    )
    profile = adapter.durability_profile_binding(running_attempt.selection)
    with pytest.raises(FormalTaskViolation) as live_rejected:
        adapter.recovery_facts(
            interrupted_task,
            interrupted_attempt,
            candidate_recovery_attempt_id="linked-live",
            profile=profile,
            recovery_generation=1,
            observed_at=NOW,
            expires_at="2026-08-05T12:10:00Z",
        )
    assert live_rejected.value.reason == "EXECUTOR_RECOVERY_NOT_QUIESCENT"

    await adapter.close(interrupt_running=True)
    restarted = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        database,
        durability_store=SqliteTaskStore(database),
    )
    restarted_core = PersistentTaskCore(restarted._durability_store, restarted)
    await restarted_core.reconcile_status()
    terminal_task = restarted._durability_store.get_task(task.task_id, task.scope)
    terminal_attempt = restarted._durability_store.get_attempt(task.attempt_id)
    assert terminal_attempt.outcome is TerminalOutcome.INTERRUPTED
    ownership = _AttemptOwnershipLock.try_acquire(project, task.attempt_id)
    assert ownership is not None
    with pytest.raises(FormalTaskViolation) as os_rejected:
        restarted.recovery_facts(
            terminal_task,
            terminal_attempt,
            candidate_recovery_attempt_id="linked-os-held",
            profile=profile,
            recovery_generation=1,
            observed_at=NOW,
            expires_at="2026-08-05T12:10:00Z",
        )
    assert os_rejected.value.reason == "EXECUTOR_ATTEMPT_OWNERSHIP_UNAVAILABLE"
    ownership.release()

    evidence = restarted.recovery_facts(
        terminal_task,
        terminal_attempt,
        candidate_recovery_attempt_id="linked-1",
        profile=profile,
        recovery_generation=1,
        observed_at=NOW,
        expires_at="2026-08-05T12:10:00Z",
    )
    assert evidence.profile == profile
    assert (
        evidence.evidence_digest
        == hashlib.sha256(
            canonical_json_bytes(
                {
                    "task_id": task.task_id,
                    "producer_attempt_id": task.attempt_id,
                    "recovery_generation": 1,
                    "quiescent": True,
                }
            )
        ).hexdigest()
    )
    await restarted.close()
