# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Opt-in D1 publication proof against one exact clean AgentCore candidate."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.durability_checkpoint import D1Checkpoint
from jiuwenswarm.server.live_voice.durability_identity import (
    DurabilityProfileBinding,
)
from jiuwenswarm.server.live_voice.openjiuwen_d1_checkpoint_adapter import (
    ImmutableFileExecutionCheckpointPayloadStore,
    OpenJiuwenD1CheckpointAdapter,
    OpenJiuwenD1CheckpointAdapterError,
    OpenJiuwenD1CheckpointProducer,
    OpenJiuwenD1CheckpointReadBinding,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_facade import (
    derive_openjiuwen_scope_binding,
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


async def _build_agent(database_path: Path, *, scope: ScopeRef = SCOPE):
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
        AgentCard(id="livevoice-openjiuwen-d1", name="livevoice-openjiuwen-d1")
    ).configure(spec, context)
    await agent.team_backend.db.initialize()
    return agent


async def _bind_handle(agent, *, scope: ScopeRef = SCOPE):
    from openjiuwen.core.session.agent_team import create_agent_team_session

    binding = derive_openjiuwen_scope_binding(scope)
    session = create_agent_team_session(
        session_id=binding.session_id,
        team_id=binding.team_name,
    )
    await agent.session_manager.bind_session(session)
    handle = agent.task_authority
    assert handle is not None
    return handle


async def _seed_owned(
    agent,
    *,
    scope: ScopeRef = SCOPE,
    task_id: str = TASK,
    execution_id: str = EXECUTION,
):
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
                task_id=task_id,
                title="checkpoint task",
                content="checkpoint content",
                initial_status=TaskStatus.PENDING.value,
                assignee=binding.member_name,
            )
        ],
    )
    assert created.ok
    prepared = await database.task.prepare_execution(
        task_id,
        execution_id,
        PROFILE,
        GENERATION,
        0,
        team_name=binding.team_name,
    )
    assert prepared.ok and prepared.record is not None
    admitted = await database.task.start_execution(
        task_id,
        binding.member_name,
        execution_id,
        PROFILE,
        GENERATION,
        OWNER,
        OWNER_EPOCH,
        prepared.record.execution_version,
        team_name=binding.team_name,
    )
    assert admitted.ok and admitted.record is not None
    return admitted.record


def _profile() -> DurabilityProfileBinding:
    return DurabilityProfileBinding(
        executor_id="jiuwenswarm_code_agent.project_code",
        adapter_id="direct-project-code-executor",
        profile_id="direct-profile",
        profile_version="profile.v1",
        profile_digest=PROFILE,
        durability_level="D1",
        durability_capability_version="d1.v1",
    )


def _checkpoint(
    *,
    scope: ScopeRef = SCOPE,
    task_id: str = TASK,
    execution_id: str = EXECUTION,
    checkpoint_id: str = "native-checkpoint-1",
    checkpoint_sequence: int = 0,
    state_bytes: bytes = b"candidate-durable-state",
) -> D1Checkpoint:
    return D1Checkpoint.create(
        checkpoint_id=checkpoint_id,
        scope=scope,
        task_id=task_id,
        producer_attempt_id=execution_id,
        checkpoint_sequence=checkpoint_sequence,
        recovery_generation=GENERATION,
        profile=_profile(),
        complete=True,
        task_spec_digest="4" * 64,
        context_version="context.v1",
        context_digest="2" * 64,
        input_digest="3" * 64,
        state_schema_id="agent-state",
        state_schema_version=4,
        state_bytes=state_bytes,
        effect_head=7,
        effect_prefix_digest="5" * 64,
    )


class _CommitThenFailCoordinator:
    def __init__(self, inner) -> None:
        self._inner = inner
        self._fail_once = True

    async def publish(self, *args, **kwargs):
        result = await self._inner.publish(*args, **kwargs)
        if self._fail_once and result.ok:
            self._fail_once = False
            raise RuntimeError("simulated response loss after durable commit")
        return result

    async def load_current(self, *args, **kwargs):
        return await self._inner.load_current(*args, **kwargs)


def _adapter(
    handle,
    payload_root: Path,
    *,
    scope: ScopeRef = SCOPE,
    fail_after_first_commit: bool = False,
):
    from openjiuwen.agent_teams import (
        ExecutionCheckpointCoordinator,
        ExecutionCheckpointPayloadReceipt,
    )

    store = ImmutableFileExecutionCheckpointPayloadStore(
        payload_root,
        receipt_factory=ExecutionCheckpointPayloadReceipt,
    )

    def factory(authority, selected_store):
        coordinator = ExecutionCheckpointCoordinator(authority, selected_store)
        if fail_after_first_commit:
            return _CommitThenFailCoordinator(coordinator)
        return coordinator

    return OpenJiuwenD1CheckpointAdapter(
        handle,
        scope,
        payload_store=store,
        coordinator_factory=factory,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exact_candidate_d1_publish_retry_orphan_and_reopen(
    tmp_path: Path,
) -> None:
    candidate, expected = _require_exact_candidate()
    _require_candidate_import_source(candidate)
    assert expected == "503cf538fd7403d0919e53b53f857fa68d624f31"

    from openjiuwen.agent_teams.schema.task import ExecutionOutcome, TaskEventType
    from openjiuwen.agent_teams.spawn.shared_resources import cleanup_shared_resources

    database_path = tmp_path / "agentcore-d1.sqlite3"
    payload_root = tmp_path / "agentcore-checkpoint-payloads"
    legacy_store_path = tmp_path / "legacy-task-store.sqlite3"
    checkpoint = _checkpoint()

    first_agent = await _build_agent(database_path)
    try:
        handle = await _bind_handle(first_agent)
        owned = await _seed_owned(first_agent)
        producer = OpenJiuwenD1CheckpointProducer(
            task_id=TASK,
            execution_id=EXECUTION,
            profile_digest=PROFILE,
            generation=GENERATION,
            owner_id=OWNER,
            owner_epoch=OWNER_EPOCH,
            execution_version=owned.execution_version,
            expected_checkpoint_head=0,
        )
        adapter = _adapter(
            handle,
            payload_root,
            fail_after_first_commit=True,
        )

        with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as response_loss:
            await adapter.publish(checkpoint, producer)
        assert response_loss.value.reason == "AGENTCORE_CHECKPOINT_PUBLICATION_FAILURE"

        replay = await adapter.publish(checkpoint, producer)
        assert replay.ok and replay.publication is not None
        assert replay.publication.replayed is True
        assert replay.publication.changed is False
        assert replay.publication.native_checkpoint_sequence == 0
        assert replay.publication.outer_checkpoint_sequence == 1

        loaded = await adapter.load_current(
            OpenJiuwenD1CheckpointReadBinding(
                task_id=TASK,
                execution_id=EXECUTION,
                profile_digest=PROFILE,
                generation=GENERATION,
                execution_version=owned.execution_version,
            )
        )
        assert loaded is not None and loaded.checkpoint == checkpoint

        changed_bytes = _checkpoint(state_bytes=b"changed-state")
        conflict = await adapter.publish(changed_bytes, producer)
        assert conflict.ok is False
        assert conflict.reason == "AGENTCORE_CHECKPOINT_REJECTED"

        orphan_checkpoint = _checkpoint(checkpoint_id="native-checkpoint-orphan")
        orphan = await adapter.publish(orphan_checkpoint, producer)
        assert orphan.ok is False
        assert orphan.reason == "AGENTCORE_CHECKPOINT_REJECTED"

        wrong_owner = await adapter.publish(
            _checkpoint(checkpoint_id="native-checkpoint-wrong-owner"),
            replace(
                producer,
                owner_id="stale-owner",
                expected_checkpoint_head=1,
            ),
        )
        wrong_version = await adapter.publish(
            _checkpoint(checkpoint_id="native-checkpoint-wrong-version"),
            replace(
                producer,
                execution_version=owned.execution_version + 1,
                expected_checkpoint_head=1,
            ),
        )
        assert not wrong_owner.ok and not wrong_version.ok

        second_checkpoint = _checkpoint(
            checkpoint_id="native-checkpoint-2",
            checkpoint_sequence=9,
            state_bytes=b"candidate-second-state",
        )
        second = await adapter.publish(
            second_checkpoint,
            replace(producer, expected_checkpoint_head=1),
        )
        assert second.ok and second.publication is not None
        assert second.publication.native_checkpoint_sequence == 9
        assert second.publication.outer_checkpoint_sequence == 2

        race_checkpoints = (
            _checkpoint(checkpoint_id="native-checkpoint-race-a"),
            _checkpoint(checkpoint_id="native-checkpoint-race-b"),
        )
        race_results = await asyncio.gather(
            *(
                adapter.publish(
                    candidate_checkpoint,
                    replace(producer, expected_checkpoint_head=2),
                )
                for candidate_checkpoint in race_checkpoints
            )
        )
        assert sum(result.ok for result in race_results) == 1
        winner_index = 0 if race_results[0].ok else 1
        latest_checkpoint = race_checkpoints[winner_index]
        winner = race_results[winner_index]
        assert winner.publication is not None
        assert winner.publication.outer_checkpoint_sequence == 3

        snapshot = await handle.get(TASK)
        assert snapshot is not None and snapshot.execution is not None
        assert snapshot.execution.checkpoint_head == 3
        events = await handle.read_events(TASK)
        checkpoint_events = [
            event
            for event in events.events
            if event.event_type is TaskEventType.EXECUTION_CHECKPOINT_PUBLISHED
        ]
        assert len(checkpoint_events) == 3
        payload_files = list(payload_root.rglob("*.payload"))
        assert len(payload_files) == 7
    finally:
        first_agent.session_manager.release_session()
        await first_agent.team_backend.db.close()
        cleanup_shared_resources()

    second_agent = await _build_agent(database_path)
    try:
        handle = await _bind_handle(second_agent)
        adapter = _adapter(handle, payload_root)
        loaded = await adapter.load_current(
            OpenJiuwenD1CheckpointReadBinding(
                task_id=TASK,
                execution_id=EXECUTION,
                profile_digest=PROFILE,
                generation=GENERATION,
                execution_version=owned.execution_version,
            )
        )
        assert loaded is not None
        assert (
            loaded.checkpoint.canonical_bytes() == latest_checkpoint.canonical_bytes()
        )
        assert loaded.outer_checkpoint_sequence == 3
        assert loaded.resume_authority is False

        binding = derive_openjiuwen_scope_binding(SCOPE)
        settled = await second_agent.team_backend.db.task.settle_execution(
            TASK,
            EXECUTION,
            owned.execution_version,
            ExecutionOutcome.FAILED,
            team_name=binding.team_name,
        )
        assert settled.ok
        assert (
            await adapter.load_current(
                OpenJiuwenD1CheckpointReadBinding(
                    task_id=TASK,
                    execution_id=EXECUTION,
                    profile_digest=PROFILE,
                    generation=GENERATION,
                    execution_version=owned.execution_version,
                )
            )
            is None
        )
        terminal_replay = await adapter.publish(checkpoint, producer)
        assert terminal_replay.ok and terminal_replay.publication is not None
        assert terminal_replay.publication.replayed is True
    finally:
        second_agent.session_manager.release_session()
        await second_agent.team_backend.db.close()
        cleanup_shared_resources()

    other_agent = await _build_agent(database_path, scope=OTHER_SCOPE)
    try:
        other_handle = await _bind_handle(other_agent, scope=OTHER_SCOPE)
        other_owned = await _seed_owned(other_agent, scope=OTHER_SCOPE)
        other_adapter = _adapter(
            other_handle,
            payload_root,
            scope=OTHER_SCOPE,
        )
        other_checkpoint = _checkpoint(scope=OTHER_SCOPE)
        other_result = await other_adapter.publish(
            other_checkpoint,
            OpenJiuwenD1CheckpointProducer(
                task_id=TASK,
                execution_id=EXECUTION,
                profile_digest=PROFILE,
                generation=GENERATION,
                owner_id=OWNER,
                owner_epoch=OWNER_EPOCH,
                execution_version=other_owned.execution_version,
                expected_checkpoint_head=0,
            ),
        )
        assert other_result.ok and other_result.publication is not None
        assert replay.publication is not None
        assert (
            other_result.publication.outer_checkpoint_id
            != replay.publication.outer_checkpoint_id
        )
        with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as cross_scope:
            _adapter(other_handle, payload_root, scope=SCOPE)
        assert cross_scope.value.reason == "AGENTCORE_BINDING_MISMATCH"
    finally:
        other_agent.session_manager.release_session()
        await other_agent.team_backend.db.close()
        cleanup_shared_resources()

    assert database_path.exists()
    assert payload_root.is_dir()
    assert len(list(payload_root.rglob("*.payload"))) == 8
    assert not legacy_store_path.exists()
