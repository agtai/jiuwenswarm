# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ScopeRef,
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
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskViolation,
    ReconciliationState,
)
from jiuwenswarm.server.live_voice.durability_recovery_facts import (
    ExecutorRecoveryFacts,
)
from jiuwenswarm.server.live_voice.executor_capabilities import (
    TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
    TaskExecutionRequirements,
    select_executor,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    PersistedExecutorSelection,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    AuthenticatedPrincipal,
    ServerSessionProjectAuthorityResolver,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    DirectProjectManagedBaselineReader,
    _AttemptOwnershipLock,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_persistent_task_core import (
    EXPIRY,
    NOW,
    _create,
    _scope,
)
from tests.unit_tests.live_voice.test_project_code_executor import (
    _DirectProjectExecutor,
    _Resolver,
    _direct_binding,
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
    adapter: DirectProjectCodeExecutorAdapter,
    *,
    identity_suffix: str = "",
):
    invocation = _create(project, identity_suffix=identity_suffix)
    candidates = adapter.capability_profiles()
    assert tuple(profile.durability_level for profile in candidates) == ("D0", "D2")
    profile = candidates[-1]
    requirements = TaskExecutionRequirements(
        schema_version=TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
        executor_id=profile.executor_id,
        operation_versions=profile.operation_versions,
        durability_level="D2",
        side_effect_class="project_mutation",
        project_serialization="exclusive",
    )
    selected = select_executor(candidates, requirements)
    selection = PersistedExecutorSelection.from_values(
        adapter_id=selected.profile.adapter_id,
        capability_profile=selected.profile.to_dict(),
        execution_requirements=selected.requirements.to_dict(),
    )
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
async def test_direct_d2_serial_tasks_accept_only_exact_settled_managed_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.task_store.utc_now",
        lambda: NOW,
    )
    project = tmp_path / "serial-project"
    _git_project(project)
    database = tmp_path / "serial-tasks.sqlite3"
    store = SqliteTaskStore(database)

    class DistinctFileExecutor:
        def __init__(self) -> None:
            self.calls = 0

        async def process_background_code_task_stream(self, request):
            self.calls += 1
            target = Path(request.params["project_dir"])
            relative = "food-b.md" if self.calls == 1 else "itinerary-a.md"
            (target / relative).write_text(
                f"managed effect {self.calls}\n", encoding="utf-8"
            )
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={"event_type": "chat.final", "content": relative},
                is_complete=True,
            )

    executor = DistinctFileExecutor()
    second_release = asyncio.Event()
    original_stream = executor.process_background_code_task_stream

    async def gated_stream(request):
        if executor.calls == 1:
            await second_release.wait()
        async for chunk in original_stream(request):
            yield chunk

    executor.process_background_code_task_stream = gated_stream
    baseline = DirectProjectManagedBaselineReader(database, store=store)
    authority = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(project),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id,
            project_dir=str(project),
            hidden=False,
            work_mode="code",
        ),
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        managed_worktree_reader=baseline,
    )
    principal = AuthenticatedPrincipal(
        principal_id="user-1",
        allowed_project_ids=frozenset({"project-1"}),
        allowed_operations=frozenset({"task.create"}),
        expires_at=EXPIRY,
    )

    class RevalidatingResolver:
        async def resolve(self, spec, *, for_dispatch: bool):
            authority.revalidate(
                spec.context,
                principal=principal,
                now=NOW,
                for_dispatch=for_dispatch,
            )
            return _direct_binding(project, executor)

    adapter = DirectProjectCodeExecutorAdapter(
        RevalidatingResolver(),
        database,
        durability_store=store,
    )
    core = PersistentTaskCore(store, adapter)
    _first_selection, first = _create_selected_task(
        store, core, project, adapter, identity_suffix="-first"
    )
    _second_selection, second = _create_selected_task(
        store, core, project, adapter, identity_suffix="-second"
    )
    assert await core.drain_outbox_once(worker_id="serial-first", observed_at=NOW)
    await _wait_direct_settled(adapter)
    assert baseline(str(project), _scope()) is False
    summary = await core.reconcile()
    first_wave = (
        store.get_task(first.task_id, _scope()).outcome,
        store.get_task(second.task_id, _scope()).outcome,
    )
    assert first_wave.count(TerminalOutcome.COMPLETED) == 1
    assert first_wave.count(None) == 1, first_wave
    assert summary["known"] == 2
    assert [
        store.get_task(task.task_id, _scope()).state.value
        for task in (first, second)
    ].count("running") == 1
    before_read = (
        (project / "food-b.md").read_bytes(),
        subprocess.run(
            ["git", "-C", str(project), "status", "--porcelain=v2", "-z"],
            check=True,
            capture_output=True,
        ).stdout,
    )
    assert baseline(str(project), _scope()) is True
    assert before_read == (
        (project / "food-b.md").read_bytes(),
        subprocess.run(
            ["git", "-C", str(project), "status", "--porcelain=v2", "-z"],
            check=True,
            capture_output=True,
        ).stdout,
    )

    second_release.set()
    await _wait_direct_settled(adapter)
    await core.reconcile_status()
    assert store.get_task(first.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
    assert store.get_task(second.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
    assert (project / "food-b.md").read_text(encoding="utf-8") == (
        "managed effect 1\n"
    )
    assert (project / "itinerary-a.md").read_text(encoding="utf-8") == (
        "managed effect 2\n"
    )
    assert baseline(str(project), _scope()) is True
    foreign_scope = ScopeRef(
        "foreign-user",
        "project-1",
        "session-1",
        Assurance.AUTHENTICATED,
    )
    assert baseline(str(project), foreign_scope) is False

    (project / "foreign.txt").write_text("manual\n", encoding="utf-8")
    foreign_before = (project / "foreign.txt").read_bytes()
    assert baseline(str(project), _scope()) is False
    assert baseline(str(project), foreign_scope) is False
    assert (project / "foreign.txt").read_bytes() == foreign_before
    await adapter.close()


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
    selection, task = _create_selected_task(store, core, project, adapter)
    assert adapter.capability_profile().durability_level == "D0"
    assert adapter.capability_profiles()[-1].durability_level == "D2"
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
    diagnostics = store.read_task_durability_diagnostics(
        scope=task.scope,
        task_id=task.task_id,
    )
    assert diagnostics.checkpoint_id == checkpoints.records[-1].checkpoint_id
    assert diagnostics.checkpoint_attempt_id == task.attempt_id
    assert diagnostics.effect_id == effects.records[-1].binding.effect_id
    assert diagnostics.effect_attempt_id == task.attempt_id
    assert diagnostics.recovery_id is None
    assert diagnostics.reconciliation_state is None
    assert len(diagnostics.outbox) == 1
    assert diagnostics.outbox[0].delivery_count == 1
    assert diagnostics.outbox[0].state.value == "delivered"
    assert (project / "result.txt").read_text(encoding="utf-8") == "done"
    await adapter.close()


@pytest.mark.asyncio
async def test_store_diagnostic_snapshot_projects_current_reconcile_without_content(
    tmp_path: Path,
) -> None:
    project = tmp_path / "reconcile-project"
    _git_project(project)
    database = tmp_path / "reconcile-tasks.sqlite3"
    store = SqliteTaskStore(database)
    adapter = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        database,
        durability_store=store,
    )
    core = PersistentTaskCore(store, adapter)
    _selection, task = _create_selected_task(store, core, project, adapter)

    marked = store.mark_reconciliation_pending(
        task.task_id,
        task.attempt_id,
        "private reconciliation reason",
    )
    diagnostics = store.read_task_durability_diagnostics(
        scope=task.scope,
        task_id=task.task_id,
    )

    assert marked.disposition.value == "applied"
    assert diagnostics.reconciliation_state is ReconciliationState.PENDING
    assert diagnostics.checkpoint_id is None
    assert diagnostics.checkpoint_attempt_id is None
    assert diagnostics.effect_id is None
    assert diagnostics.effect_attempt_id is None
    assert diagnostics.recovery_id is None
    assert diagnostics.outbox[0].state.value == "pending"
    assert "private reconciliation reason" not in repr(diagnostics)
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
    _selection, task = _create_selected_task(store, core, project, adapter)
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
    historical_binding = _durability_binding(
        restarted._durability_store, task.task_id, task.attempt_id
    )
    historical_checkpoints = restarted._durability_store.read_durability_checkpoints(
        historical_binding
    )
    historical_effects = restarted._durability_store.read_durability_effects(
        historical_binding
    )
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
    current_checkpoints = restarted._durability_store.read_durability_checkpoints(
        binding
    )
    current_effects = restarted._durability_store.read_durability_effects(binding)
    stale_owner = "stale-tip-recovery"
    stale_claim = restarted._durability_store.claim_durability_mutator(
        scope=task.scope,
        task_id=task.task_id,
        owner_id=stale_owner,
        observed_at="2026-08-05T12:04:30Z",
        expires_at="2026-08-05T12:10:00Z",
    )
    assert stale_claim is not None
    stale_facts, stale_receipt = restarted.authorize_durable_recovery(
        authority.task,
        authority.producer_attempt,
        recovery_id="recovery-stale-tip",
        candidate_recovery_attempt_id="attempt-stale-tip",
        profile=binding.profile,
        recovery_generation=authority.recovery_generation,
        checkpoint_head=current_checkpoints.head,
        checkpoint_prefix_digest=current_checkpoints.prefix_digest,
        effect_head=current_effects.head,
        effect_prefix_digest=current_effects.prefix_digest,
        claim_owner_id=stale_owner,
        claim_token=stale_claim[0],
        claim_generation=stale_claim[1],
        observed_at="2026-08-05T12:04:30Z",
        expires_at="2026-08-05T12:10:00Z",
    )
    before_stale = restarted._durability_store.counts()
    before_stale_events = restarted._durability_store.events(task.task_id, task.scope)
    with pytest.raises(FormalTaskViolation) as stale_tip:
        restarted._durability_store.recover_durable_attempt(
            authority,
            recovery_id="recovery-stale-tip",
            recovery_facts=stale_facts,
            checkpoint_head=historical_checkpoints.head,
            checkpoint_prefix_digest=historical_checkpoints.prefix_digest,
            effect_head=historical_effects.head,
            effect_prefix_digest=historical_effects.prefix_digest,
            authorization=stale_receipt,
            observed_at="2026-08-05T12:04:30Z",
        )
    assert stale_tip.value.reason == "TASK_RECOVERY_PREFIX_STALE"
    assert restarted._durability_store.counts() == before_stale
    assert (
        restarted._durability_store.events(task.task_id, task.scope)
        == before_stale_events
    )
    assert restarted._durability_store.release_durability_mutator(
        scope=task.scope,
        task_id=task.task_id,
        owner_id=stale_owner,
        claim_token=stale_claim[0],
        claim_generation=stale_claim[1],
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

    captured_recovery: dict[str, object] = {}
    real_recover = restarted._durability_store.recover_durable_attempt

    def capture_recovery(authority_value, **kwargs):
        captured_recovery["authority"] = authority_value
        captured_recovery.update(kwargs)
        return real_recover(authority_value, **kwargs)

    monkeypatch.setattr(
        restarted._durability_store,
        "recover_durable_attempt",
        capture_recovery,
    )
    linked = await restarted_core.recover_durable_attempt(
        scope=task.scope,
        task_id=task.task_id,
        operator_id="operator-1",
        observed_at="2026-08-05T12:05:00Z",
    )
    monkeypatch.setattr(
        restarted._durability_store,
        "recover_durable_attempt",
        real_recover,
    )
    assert linked.attempt_id != producer.attempt_id
    assert restarted._durability_store.get_attempt(producer.attempt_id) == producer
    recovery_diagnostics = (
        restarted._durability_store.read_task_durability_diagnostics(
            scope=task.scope,
            task_id=task.task_id,
        )
    )
    assert recovery_diagnostics.attempt_id == linked.attempt_id
    assert recovery_diagnostics.recovery_id == captured_recovery["recovery_id"]
    assert recovery_diagnostics.checkpoint_id is not None
    assert recovery_diagnostics.checkpoint_attempt_id == producer.attempt_id
    assert recovery_diagnostics.effect_id is not None
    assert recovery_diagnostics.effect_attempt_id == producer.attempt_id
    assert recovery_diagnostics.outbox[-1].state.value == "pending"
    replay_owner = "exact-replay-recovery"
    replay_claim = restarted._durability_store.claim_durability_mutator(
        scope=task.scope,
        task_id=task.task_id,
        owner_id=replay_owner,
        observed_at="2026-08-05T12:05:00Z",
        expires_at="2026-08-05T12:10:00Z",
    )
    assert replay_claim is not None
    replay_facts, replay_receipt = restarted.authorize_durable_recovery(
        authority.task,
        authority.producer_attempt,
        recovery_id=str(captured_recovery["recovery_id"]),
        candidate_recovery_attempt_id=linked.attempt_id,
        profile=binding.profile,
        recovery_generation=authority.recovery_generation,
        checkpoint_head=current_checkpoints.head,
        checkpoint_prefix_digest=current_checkpoints.prefix_digest,
        effect_head=current_effects.head,
        effect_prefix_digest=current_effects.prefix_digest,
        claim_owner_id=replay_owner,
        claim_token=replay_claim[0],
        claim_generation=replay_claim[1],
        observed_at="2026-08-05T12:05:00Z",
        expires_at=str(captured_recovery["recovery_facts"].expires_at),
    )
    replayed = real_recover(
        authority,
        recovery_id=str(captured_recovery["recovery_id"]),
        recovery_facts=replay_facts,
        checkpoint_head=current_checkpoints.head,
        checkpoint_prefix_digest=current_checkpoints.prefix_digest,
        effect_head=current_effects.head,
        effect_prefix_digest=current_effects.prefix_digest,
        authorization=replay_receipt,
        observed_at="2026-08-05T12:05:00Z",
    )
    assert replayed == linked
    before_foreign = restarted._durability_store.counts()
    before_foreign_events = restarted._durability_store.events(task.task_id, task.scope)
    foreign_scope_authority = replace(
        authority,
        task=replace(
            authority.task,
            scope=replace(authority.task.scope, subject_id="foreign-subject"),
        ),
    )
    with pytest.raises(FormalTaskViolation):
        real_recover(
            foreign_scope_authority,
            recovery_id=str(captured_recovery["recovery_id"]),
            recovery_facts=replay_facts,
            checkpoint_head=current_checkpoints.head,
            checkpoint_prefix_digest=current_checkpoints.prefix_digest,
            effect_head=current_effects.head,
            effect_prefix_digest=current_effects.prefix_digest,
            authorization=replay_receipt,
            observed_at="2026-08-05T12:05:00Z",
        )
    assert restarted._durability_store.counts() == before_foreign
    assert (
        restarted._durability_store.events(task.task_id, task.scope)
        == before_foreign_events
    )
    for label in ("producer", "generation", "profile"):
        forged_owner = f"forged-{label}-replay"
        forged_claim = restarted._durability_store.claim_durability_mutator(
            scope=task.scope,
            task_id=task.task_id,
            owner_id=forged_owner,
            observed_at="2026-08-05T12:05:00Z",
            expires_at="2026-08-05T12:10:00Z",
        )
        assert forged_claim is not None
        exact_facts, exact_receipt = restarted.authorize_durable_recovery(
            authority.task,
            authority.producer_attempt,
            recovery_id=str(captured_recovery["recovery_id"]),
            candidate_recovery_attempt_id=linked.attempt_id,
            profile=binding.profile,
            recovery_generation=authority.recovery_generation,
            checkpoint_head=current_checkpoints.head,
            checkpoint_prefix_digest=current_checkpoints.prefix_digest,
            effect_head=current_effects.head,
            effect_prefix_digest=current_effects.prefix_digest,
            claim_owner_id=forged_owner,
            claim_token=forged_claim[0],
            claim_generation=forged_claim[1],
            observed_at="2026-08-05T12:05:00Z",
            expires_at=str(captured_recovery["recovery_facts"].expires_at),
        )
        forged_facts = ExecutorRecoveryFacts.create(
            scope=exact_facts.scope,
            task_id=exact_facts.task_id,
            producer_attempt_id=(
                "attempt-foreign"
                if label == "producer"
                else exact_facts.producer_attempt_id
            ),
            candidate_recovery_attempt_id=exact_facts.candidate_recovery_attempt_id,
            profile=(
                replace(exact_facts.profile, profile_id="foreign-profile")
                if label == "profile"
                else exact_facts.profile
            ),
            recovery_generation=(
                exact_facts.recovery_generation + 1
                if label == "generation"
                else exact_facts.recovery_generation
            ),
            executor_epoch_id=exact_facts.executor_epoch_id,
            executor_owner_generation=exact_facts.executor_owner_generation,
            observed_at=exact_facts.observed_at,
            expires_at=exact_facts.expires_at,
            evidence_digest=exact_facts.evidence_digest,
        )
        with pytest.raises(FormalTaskViolation) as forged_replay:
            real_recover(
                authority,
                recovery_id=str(captured_recovery["recovery_id"]),
                recovery_facts=forged_facts,
                checkpoint_head=current_checkpoints.head,
                checkpoint_prefix_digest=current_checkpoints.prefix_digest,
                effect_head=current_effects.head,
                effect_prefix_digest=current_effects.prefix_digest,
                authorization=exact_receipt,
                observed_at="2026-08-05T12:05:00Z",
            )
        assert forged_replay.value.reason == "IDEMPOTENCY_CONFLICT"
        assert restarted._durability_store.counts() == before_foreign
        assert (
            restarted._durability_store.events(task.task_id, task.scope)
            == before_foreign_events
        )
        assert restarted._durability_store.release_durability_mutator(
            scope=task.scope,
            task_id=task.task_id,
            owner_id=forged_owner,
            claim_token=forged_claim[0],
            claim_generation=forged_claim[1],
        )
    from jiuwenswarm.server.live_voice import project_code_executor

    real_apply = project_code_executor._apply_attempt_patch
    real_linked_reserve = restarted._journal.reserve_completion
    recovery_apply_calls = 0
    fenced_linked_reserve = False

    def count_linked_apply(*args, **kwargs):
        nonlocal recovery_apply_calls
        recovery_apply_calls += 1
        return real_apply(*args, **kwargs)

    def fence_first_linked_reserve(attempt_id, **kwargs):
        nonlocal fenced_linked_reserve
        if attempt_id == linked.attempt_id and not fenced_linked_reserve:
            fenced_linked_reserve = True
            record = restarted._journal.get(attempt_id)
            assert record is not None
            return False, record
        return real_linked_reserve(attempt_id, **kwargs)

    monkeypatch.setattr(
        project_code_executor,
        "_apply_attempt_patch",
        count_linked_apply,
    )
    monkeypatch.setattr(
        restarted._journal,
        "reserve_completion",
        fence_first_linked_reserve,
    )
    assert await restarted_core.drain_outbox_once(
        worker_id="linked", observed_at="2026-08-05T12:05:01Z"
    )
    interrupted_linked_task = restarted._durability_store.get_task(
        task.task_id, task.scope
    )
    interrupted_linked = restarted._durability_store.get_attempt(linked.attempt_id)
    assert interrupted_linked_task.outcome is TerminalOutcome.INTERRUPTED
    assert interrupted_linked.outcome is TerminalOutcome.INTERRUPTED
    assert recovery_apply_calls == 0
    assert (
        await restarted.reconcile_durable_effects(
            scope=task.scope,
            task_id=task.task_id,
            origin_attempt_id=linked.attempt_id,
            observed_at="2026-08-05T12:06:00Z",
        )
        == "no_effect"
    )
    second_linked = await restarted_core.recover_durable_attempt(
        scope=task.scope,
        task_id=task.task_id,
        operator_id="operator-2",
        observed_at="2026-08-05T12:07:00Z",
    )
    assert second_linked.attempt_number == 3
    assert restarted._durability_store.get_attempt(linked.attempt_id) == (
        interrupted_linked
    )
    assert await restarted_core.drain_outbox_once(
        worker_id="linked-second", observed_at="2026-08-05T12:07:01Z"
    )
    completed = restarted._durability_store.get_task(task.task_id, task.scope)
    assert completed.outcome is TerminalOutcome.COMPLETED
    assert completed.attempt_id == second_linked.attempt_id
    assert restarted._durability_store.get_attempt(producer.attempt_id) == producer
    second_binding = _durability_binding(
        restarted._durability_store,
        task.task_id,
        second_linked.attempt_id,
    )
    second_effects = restarted._durability_store.read_durability_effects(second_binding)
    assert second_effects.records
    assert {fact.binding.origin_attempt_id for fact in second_effects.records} == {
        producer.attempt_id
    }
    assert len(executor.requests) == 1
    assert recovery_executor.requests == []
    assert recovery_apply_calls == 1
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
    _selection, task = _create_selected_task(store, core, project, adapter)
    real_append = store.append_durability_effect_fact
    apply_calls = 0

    from jiuwenswarm.server.live_voice import project_code_executor

    real_apply = project_code_executor._apply_attempt_patch

    def counted_apply(*args, **kwargs):
        nonlocal apply_calls
        apply_calls += 1
        return real_apply(*args, **kwargs)

    def lose_receipt(fact, *, row_sequence: int, observed_at: str, **kwargs):
        if row_sequence == 3:
            raise RuntimeError("simulated crash after apply before Store ACK")
        return real_append(
            fact,
            row_sequence=row_sequence,
            observed_at=observed_at,
            **kwargs,
        )

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", counted_apply)
    monkeypatch.setattr(store, "append_durability_effect_fact", lose_receipt)
    assert await core.drain_outbox_once(worker_id="producer", observed_at=NOW)
    await _wait_direct_settled(adapter)
    assert apply_calls == 1
    monkeypatch.setattr(store, "append_durability_effect_fact", real_append)
    await adapter.close()

    restarted_store = SqliteTaskStore(database)
    restarted = DirectProjectCodeExecutorAdapter(
        _Resolver(_direct_binding(project, _DirectProjectExecutor(project))),
        database,
        durability_store=restarted_store,
    )
    restarted_core = PersistentTaskCore(restarted_store, restarted)
    await restarted_core.reconcile_status()
    interrupted = restarted_store.get_task(task.task_id, task.scope)
    producer = restarted_store.get_attempt(task.attempt_id)
    assert interrupted.outcome is TerminalOutcome.INTERRUPTED
    assert producer.outcome is TerminalOutcome.INTERRUPTED
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
    linked = await restarted_core.recover_durable_attempt(
        scope=task.scope,
        task_id=task.task_id,
        operator_id="operator-applied",
        observed_at="2026-08-05T12:06:00Z",
    )
    assert await restarted_core.drain_outbox_once(
        worker_id="linked-applied",
        observed_at="2026-08-05T12:06:01Z",
    )
    completed = restarted_store.get_task(task.task_id, task.scope)
    completed_attempt = restarted_store.get_attempt(linked.attempt_id)
    availability, final_result, reason = restarted_store.task_result(
        task.task_id, task.scope
    )
    assert completed.outcome is TerminalOutcome.COMPLETED
    assert completed.attempt_id == linked.attempt_id
    assert completed_attempt.outcome is TerminalOutcome.COMPLETED
    assert availability.value == "available"
    assert final_result is not None
    assert final_result.result_text == "done"
    assert reason == "TASK_RESULT_AVAILABLE"
    assert restarted_store.get_attempt(task.attempt_id) == producer
    assert apply_calls == 1
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
    _selection, task = _create_selected_task(store, core, project, adapter)
    real_append = store.append_durability_effect_fact
    apply_calls = 0

    from jiuwenswarm.server.live_voice import project_code_executor

    real_apply = project_code_executor._apply_attempt_patch

    def counted_apply(*args, **kwargs):
        nonlocal apply_calls
        apply_calls += 1
        return real_apply(*args, **kwargs)

    def fail_receipt(fact, *, row_sequence: int, observed_at: str, **kwargs):
        if row_sequence == 3:
            raise RuntimeError("simulated Store ACK loss")
        return real_append(
            fact,
            row_sequence=row_sequence,
            observed_at=observed_at,
            **kwargs,
        )

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
    _selection, task = _create_selected_task(store, core, project, adapter)
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
