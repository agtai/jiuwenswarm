# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Opt-in project/file effect proof against one exact clean AgentCore."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.openjiuwen_project_file_effect_adapter import (
    OPENJIUWEN_PROJECT_EFFECT_KIND,
    OPENJIUWEN_PROJECT_EFFECT_REPLAY_POLICY,
    CrossProcessProjectFileEffectOwnership,
    OpenJiuwenProjectFileEffectAdapter,
    OpenJiuwenProjectFileEffectPlan,
    derive_openjiuwen_project_intended_effect_digest,
    derive_openjiuwen_project_target_digest,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_facade import (
    derive_openjiuwen_scope_binding,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    _encode_expected_project_state,
    _git_head,
    _git_visible_patch,
    _project_content_fingerprint,
    _project_tree_fingerprint,
    _target_support_fingerprints,
)

SCOPE = ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)
OTHER_SCOPE = ScopeRef(
    "principal-2",
    "project-2",
    "session-2",
    Assurance.AUTHENTICATED,
)
TASK = "task-1"
EXECUTION = "execution-1"
PROFILE = "1" * 64
GENERATION = 0
OWNER = "runtime-owner-1"
OWNER_EPOCH = 2
EMPTY_PREFIX = hashlib.sha256(b"").hexdigest()


def _require_exact_candidate() -> tuple[Path, str]:
    raw_path = os.getenv("OPENJIUWEN_AGENTCORE_CANDIDATE_PATH")
    expected = os.getenv("OPENJIUWEN_AGENTCORE_CANDIDATE_SHA")
    if not raw_path or not expected:
        pytest.skip("exact local AgentCore candidate was not requested")
    candidate = Path(raw_path).resolve()
    if not candidate.is_dir():
        pytest.fail("OPENJIUWEN_AGENTCORE_CANDIDATE_PATH is not a directory")
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=candidate,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != expected:
        pytest.fail(
            f"AgentCore candidate mismatch: expected {expected}, observed {actual}"
        )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=candidate,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        pytest.fail("AgentCore candidate worktree is not clean at the exact commit")
    return candidate, actual


def _require_candidate_import_source(candidate: Path) -> None:
    loaded = sys.modules.get("openjiuwen")
    origin = getattr(loaded, "__file__", None) if loaded is not None else None
    if origin is None:
        spec = importlib.util.find_spec("openjiuwen")
        origin = None if spec is None else spec.origin
    if origin is None:
        pytest.fail("the exact AgentCore candidate is not importable")
    resolved = Path(origin).resolve()
    if not resolved.is_relative_to(candidate):
        pytest.fail(
            f"openjiuwen import is outside candidate: {resolved} not under {candidate}"
        )


def _run(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    _run(root, "init")
    _run(root, "config", "user.email", "candidate@example.invalid")
    _run(root, "config", "user.name", "Candidate Test")
    (root / "sample.txt").write_text("before\n", encoding="utf-8")
    _run(root, "add", "sample.txt")
    _run(root, "commit", "-m", "baseline")
    return root.resolve()


def _plan(
    root: Path,
    *,
    scope: ScopeRef,
    effect_id: str,
) -> OpenJiuwenProjectFileEffectPlan:
    before_head = _git_head(root)
    before_tree = _project_tree_fingerprint(root)
    before_content = _project_content_fingerprint(root)
    support = tuple(sorted(_target_support_fingerprints(root).items()))
    (root / "sample.txt").write_text("after\n", encoding="utf-8")
    patch = _git_visible_patch(root)
    after_content = _project_content_fingerprint(root)
    expected_tree = _encode_expected_project_state(after_content, patch=patch)
    (root / "sample.txt").write_text("before\n", encoding="utf-8")
    return OpenJiuwenProjectFileEffectPlan(
        scope=scope,
        task_id=TASK,
        execution_id=EXECUTION,
        profile_digest=PROFILE,
        generation=GENERATION,
        effect_id=effect_id,
        operation_kind=OPENJIUWEN_PROJECT_EFFECT_KIND,
        operation_ordinal=1,
        dispatch_ordinal=1,
        provider_operation_key=effect_id,
        target_digest=derive_openjiuwen_project_target_digest(
            scope,
            project_source="local",
            project_stable_id=scope.project_id or "",
            project_uri=f"project://{scope.project_id}",
            project_root=str(root),
        ),
        intended_effect_digest=derive_openjiuwen_project_intended_effect_digest(
            expected_tree=expected_tree,
            patch=patch,
            before_tree=before_tree,
            before_content=before_content,
            before_head=before_head,
            protected_support=support,
        ),
        replay_policy=OPENJIUWEN_PROJECT_EFFECT_REPLAY_POLICY,
        project_source="local",
        project_stable_id=scope.project_id or "",
        project_uri=f"project://{scope.project_id}",
        project_root=str(root),
        attempt_id=EXECUTION,
        patch=patch,
        expected_tree=expected_tree,
        before_tree=before_tree,
        before_content=before_content,
        before_head=before_head,
        protected_support=support,
    )


async def _build_agent(database_path: Path, *, scope: ScopeRef):
    from openjiuwen.agent_teams import TeamAgent
    from openjiuwen.agent_teams.schema.blueprint import TeamAgentSpec
    from openjiuwen.agent_teams.schema.deep_agent_spec import DeepAgentSpec
    from openjiuwen.agent_teams.schema.team import (
        TeamRole,
        TeamRuntimeContext,
        TeamSpec,
    )
    from openjiuwen.agent_teams.tools.database import DatabaseConfig, DatabaseType
    from openjiuwen.core.single_agent import AgentCard

    binding = derive_openjiuwen_scope_binding(scope)
    spec = TeamAgentSpec(
        agents={binding.member_name: DeepAgentSpec()},
        team_name=binding.team_name,
    )
    context = TeamRuntimeContext(
        role=TeamRole.LEADER,
        member_name=binding.member_name,
        team_spec=TeamSpec(
            team_name=binding.team_name,
            display_name=binding.team_name,
            leader_member_name=binding.member_name,
        ),
        db_config=DatabaseConfig(
            db_type=DatabaseType.SQLITE,
            connection_string=str(database_path),
        ),
    )
    agent = TeamAgent(
        AgentCard(id="livevoice-effect", name="livevoice-effect")
    ).configure(spec, context)
    await agent.team_backend.db.initialize()
    return agent


async def _bind_handle(agent, *, scope: ScopeRef):
    from openjiuwen.core.session.agent_team import create_agent_team_session

    binding = derive_openjiuwen_scope_binding(scope)
    session = create_agent_team_session(
        session_id=binding.session_id,
        team_id=binding.team_name,
    )
    await agent.session_manager.bind_session(session)
    handle = agent.effect_authority
    assert handle is not None
    return handle


async def _seed_owned(agent, *, scope: ScopeRef):
    from openjiuwen.agent_teams.schema.status import (
        MemberMode,
        MemberStatus,
        TaskStatus,
    )
    from openjiuwen.agent_teams.schema.task import NewTaskSpec
    from openjiuwen.core.single_agent import AgentCard

    binding = derive_openjiuwen_scope_binding(scope)
    database = agent.team_backend.db
    assert await database.team.create_team(
        binding.team_name,
        binding.team_name,
        binding.member_name,
    )
    assert await database.member.create_member(
        member_name=binding.member_name,
        team_name=binding.team_name,
        display_name=binding.member_name,
        agent_card=AgentCard().model_dump_json(),
        status=MemberStatus.BUSY.value,
        mode=MemberMode.BUILD_MODE.value,
    )
    created = await database.task.mutate_dependency_graph(
        binding.team_name,
        new_tasks=[
            NewTaskSpec(
                task_id=TASK,
                title="effect task",
                content="effect content",
                initial_status=TaskStatus.PENDING.value,
                assignee=binding.member_name,
            )
        ],
    )
    assert created.ok
    prepared = await database.task.prepare_execution(
        TASK,
        EXECUTION,
        PROFILE,
        GENERATION,
        0,
        team_name=binding.team_name,
    )
    assert prepared.ok and prepared.record is not None
    admitted = await database.task.start_execution(
        TASK,
        binding.member_name,
        EXECUTION,
        PROFILE,
        GENERATION,
        OWNER,
        OWNER_EPOCH,
        prepared.record.execution_version,
        team_name=binding.team_name,
    )
    assert admitted.ok and admitted.record is not None
    return admitted.record


class _LoseFirstDispatchResponse:
    def __init__(self, inner) -> None:
        self._inner = inner
        self._lose_once = True

    async def dispatch(self, authorization):
        result = await self._inner.dispatch(authorization)
        if result is not None and self._lose_once:
            self._lose_once = False
            raise RuntimeError("simulated response loss after file apply")
        return result

    async def observe(self, authorization):
        return await self._inner.observe(authorization)


def _adapter(handle, scope: ScopeRef, *, lose_response: bool = False):
    from openjiuwen.agent_teams import (
        ExternalEffectAdapterObservation,
        ExternalEffectAdapterReceipt,
        ExternalEffectCoordinator,
        ExternalEffectObservationKind,
        ExternalEffectReceiptStatus,
    )

    def factory(authority, port):
        coordinator = ExternalEffectCoordinator(authority, port)
        return _LoseFirstDispatchResponse(coordinator) if lose_response else coordinator

    return OpenJiuwenProjectFileEffectAdapter(
        handle,
        scope,
        coordinator_factory=factory,
        receipt_factory=lambda **values: ExternalEffectAdapterReceipt(
            status=ExternalEffectReceiptStatus(values["status"]),
            receipt_id=values["receipt_id"],
            receipt_digest=values["receipt_digest"],
        ),
        observation_factory=lambda **values: ExternalEffectAdapterObservation(
            kind=ExternalEffectObservationKind(values["kind"]),
            evidence_digest=values["evidence_digest"],
            call_quiesced=values["call_quiesced"],
        ),
        ownership=CrossProcessProjectFileEffectOwnership(),
    )


async def _plan_claim_dispatch(handle, owned, plan):
    from openjiuwen.agent_teams import (
        ExternalEffectClaimPurpose,
        ExternalEffectReplayPolicy,
    )

    planned = await handle.plan_effect(
        TASK,
        EXECUTION,
        plan.effect_id,
        profile_digest=PROFILE,
        generation=GENERATION,
        owner_id=OWNER,
        owner_epoch=OWNER_EPOCH,
        expected_execution_version=owned.execution_version,
        expected_effect_head=0,
        expected_effect_prefix_digest=EMPTY_PREFIX,
        operation_kind=plan.operation_kind,
        operation_ordinal=plan.operation_ordinal,
        provider_operation_key=plan.provider_operation_key,
        target_digest=plan.target_digest,
        intended_effect_digest=plan.intended_effect_digest,
        replay_policy=ExternalEffectReplayPolicy.NEVER,
    )
    assert planned.ok and planned.record is not None
    claimed = await handle.claim_effect(
        plan.effect_id,
        "runtime-1",
        ExternalEffectClaimPurpose.CALL,
        expected_effect_version=planned.record.effect_version,
        lease_ms=60_000,
        expected_execution_version=owned.execution_version,
        owner_id=OWNER,
        owner_epoch=OWNER_EPOCH,
    )
    assert claimed.ok and claimed.record is not None and claimed.claim is not None
    dispatched = await handle.record_effect_dispatch(
        plan.effect_id,
        "runtime-1",
        claimed.claim.claim_token,
        expected_effect_version=claimed.record.effect_version,
        expected_effect_head=claimed.record.journal_head,
        expected_effect_prefix_digest=claimed.record.journal_prefix_digest,
        dispatch_ordinal=1,
    )
    assert dispatched.ok and dispatched.record is not None
    assert dispatched.authorization is not None
    return claimed, dispatched


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exact_candidate_project_effect_success_recovery_and_isolation(
    tmp_path: Path,
) -> None:
    candidate, expected = _require_exact_candidate()
    _require_candidate_import_source(candidate)
    assert expected == "db8216839562de36fa24fd6f5ce807acea5a132a"

    from openjiuwen.agent_teams import (
        ExternalEffectClaimPurpose,
        ExternalEffectObservationKind,
        ExternalEffectSettlementKind,
        ExternalEffectState,
    )
    from openjiuwen.agent_teams.context import reset_session_id, set_session_id
    from openjiuwen.agent_teams.spawn.shared_resources import cleanup_shared_resources

    database_path = tmp_path / "agentcore-effect.sqlite3"
    legacy_store_path = tmp_path / "legacy-task-store.sqlite3"
    recovery_root = _repo(tmp_path, "recovery-project")
    recovery_plan = _plan(recovery_root, scope=SCOPE, effect_id="effect-recovery")

    first_agent = await _build_agent(database_path, scope=SCOPE)
    try:
        handle = await _bind_handle(first_agent, scope=SCOPE)
        owned = await _seed_owned(first_agent, scope=SCOPE)
        claimed, dispatched = await _plan_claim_dispatch(handle, owned, recovery_plan)
        adapter = _adapter(handle, SCOPE, lose_response=True)

        assert await adapter.dispatch(recovery_plan, dispatched.authorization) is None
        assert (recovery_root / "sample.txt").read_text(encoding="utf-8") == "after\n"
        assert await adapter.dispatch(recovery_plan, dispatched.authorization) is None

        binding = derive_openjiuwen_scope_binding(SCOPE)
        token = set_session_id(binding.session_id)
        try:
            assert (
                await first_agent.task_manager.reap_effect_claims(
                    now=claimed.claim.expires_at + 1
                )
                == 1
            )
        finally:
            reset_session_id(token)
        current = await handle.get_effect(recovery_plan.effect_id)
        assert current is not None
        assert current.state is ExternalEffectState.RECONCILE_REQUIRED
        reconcile = await handle.claim_effect(
            recovery_plan.effect_id,
            "recovery-1",
            ExternalEffectClaimPurpose.RECONCILE,
            expected_effect_version=current.effect_version,
            lease_ms=60_000,
        )
        assert reconcile.ok and reconcile.record is not None
        assert reconcile.observation_authorization is not None
        observation = await adapter.observe(
            recovery_plan,
            reconcile.observation_authorization,
        )
        assert observation is not None
        assert observation.kind is ExternalEffectObservationKind.OBSERVED
        observed = await handle.record_effect_observation(
            recovery_plan.effect_id,
            "recovery-1",
            reconcile.observation_authorization.claim_token,
            expected_effect_version=reconcile.record.effect_version,
            expected_effect_head=reconcile.record.journal_head,
            expected_effect_prefix_digest=reconcile.record.journal_prefix_digest,
            dispatch_ordinal=1,
            observation_ordinal=1,
            kind=observation.kind,
            evidence_digest=observation.evidence_digest,
            call_quiesced=observation.call_quiesced,
        )
        assert observed.ok and observed.record is not None
        settled = await handle.settle_effect(
            recovery_plan.effect_id,
            "recovery-1",
            reconcile.observation_authorization.claim_token,
            expected_effect_version=observed.record.effect_version,
            expected_effect_head=observed.record.journal_head,
            expected_effect_prefix_digest=observed.record.journal_prefix_digest,
            settlement_ordinal=1,
            kind=ExternalEffectSettlementKind.RESOLVED,
            evidence_digest=observation.evidence_digest,
        )
        assert settled.ok and settled.record is not None
        assert settled.record.state is ExternalEffectState.SETTLED
        prefix = await handle.read_effect_prefix(
            EXECUTION,
            task_id=TASK,
            profile_digest=PROFILE,
            generation=GENERATION,
        )
        assert prefix is not None and prefix.head == 4 and len(prefix.facts) == 4
    finally:
        first_agent.session_manager.release_session()
        await first_agent.team_backend.db.close()
        cleanup_shared_resources()

    reopened_agent = await _build_agent(database_path, scope=SCOPE)
    try:
        reopened = await _bind_handle(reopened_agent, scope=SCOPE)
        record = await reopened.get_effect(recovery_plan.effect_id)
        assert record is not None and record.state is ExternalEffectState.SETTLED
        assert (recovery_root / "sample.txt").read_text(encoding="utf-8") == "after\n"
    finally:
        reopened_agent.session_manager.release_session()
        await reopened_agent.team_backend.db.close()
        cleanup_shared_resources()

    success_root = _repo(tmp_path, "success-project")
    success_plan = _plan(success_root, scope=OTHER_SCOPE, effect_id="effect-success")
    other_agent = await _build_agent(database_path, scope=OTHER_SCOPE)
    try:
        other_handle = await _bind_handle(other_agent, scope=OTHER_SCOPE)
        other_owned = await _seed_owned(other_agent, scope=OTHER_SCOPE)
        _, dispatched = await _plan_claim_dispatch(
            other_handle, other_owned, success_plan
        )
        adapter = _adapter(other_handle, OTHER_SCOPE)
        receipt = await adapter.dispatch(success_plan, dispatched.authorization)
        assert receipt is not None
        assert (success_root / "sample.txt").read_text(encoding="utf-8") == "after\n"
        recorded = await other_handle.record_effect_receipt(
            success_plan.effect_id,
            "runtime-1",
            dispatched.authorization.continuation_token,
            expected_effect_version=dispatched.record.effect_version,
            expected_effect_head=dispatched.record.journal_head,
            expected_effect_prefix_digest=dispatched.record.journal_prefix_digest,
            dispatch_ordinal=1,
            status=receipt.status,
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
        )
        assert recorded.ok and recorded.record is not None
        observed = await other_handle.record_effect_observation(
            success_plan.effect_id,
            "runtime-1",
            dispatched.authorization.continuation_token,
            expected_effect_version=recorded.record.effect_version,
            expected_effect_head=recorded.record.journal_head,
            expected_effect_prefix_digest=recorded.record.journal_prefix_digest,
            dispatch_ordinal=1,
            observation_ordinal=1,
            kind=ExternalEffectObservationKind.OBSERVED,
            evidence_digest=receipt.receipt_digest,
            call_quiesced=False,
        )
        assert observed.ok and observed.record is not None
        settled = await other_handle.settle_effect(
            success_plan.effect_id,
            "runtime-1",
            dispatched.authorization.continuation_token,
            expected_effect_version=observed.record.effect_version,
            expected_effect_head=observed.record.journal_head,
            expected_effect_prefix_digest=observed.record.journal_prefix_digest,
            settlement_ordinal=1,
            kind=ExternalEffectSettlementKind.RESOLVED,
            evidence_digest=receipt.receipt_digest,
        )
        assert settled.ok
        assert success_plan.target_digest != recovery_plan.target_digest
        with pytest.raises(Exception):
            _adapter(other_handle, SCOPE)
    finally:
        other_agent.session_manager.release_session()
        await other_agent.team_backend.db.close()
        cleanup_shared_resources()

    assert database_path.exists()
    assert not legacy_store_path.exists()
