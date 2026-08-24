# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Opt-in real SQLite proof against one exact local AgentCore candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.openjiuwen_product_query_adapter import (
    OpenJiuwenProductP3QueryOwner,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_facade import (
    OpenJiuwenTaskFacade,
    OpenJiuwenTaskFacadeError,
    derive_openjiuwen_scope_binding,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityResourceBinding,
    AuthorityRouteContext,
    P3AuthorityAdapter,
    ProductAuthorityService,
    ResolvedProductAuthority,
    TrustedAuthorityCandidate,
    TrustedAuthorityLookup,
)
from jiuwenswarm.server.live_voice.product_p3_text_adapter import (
    ProductP3QueryRequest,
    ProductP3TextAdapter,
    ProductP3TextReason,
)
from jiuwenswarm.server.live_voice.progress_notification_arbiter import (
    ForegroundFact,
    ForegroundSnapshot,
    ProgressNotificationArbiter,
    SpeechPolicy,
)

SCOPE = ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)
TASK = "task-1"
EXPIRY = "2099-01-01T00:00:00Z"
NOW = "2030-01-01T00:00:00Z"


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
    worktree_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=candidate,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if worktree_status:
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


def _authority(operation: str) -> ResolvedProductAuthority:
    return ResolvedProductAuthority(
        principal_id=SCOPE.subject_id,
        session_id=SCOPE.session_id,
        project_id=SCOPE.project_id,
        scope=SCOPE,
        operation=operation,
        capabilities=frozenset({operation}),
        expires_at=EXPIRY,
        assurance=Assurance.AUTHENTICATED,
        source="server.auth.session",
        correlation_id="candidate-integration",
        resource=(
            None
            if operation == "task.list"
            else AuthorityResourceBinding(
                "task",
                TASK,
                hashlib.sha256(TASK.encode()).hexdigest(),
            )
        ),
        confirmation=None,
    )


class _Resolver:
    def __init__(self, candidate: TrustedAuthorityCandidate) -> None:
        self._candidate = candidate
        self.calls: list[TrustedAuthorityLookup] = []

    def resolve(
        self,
        lookup: TrustedAuthorityLookup,
    ) -> Sequence[TrustedAuthorityCandidate]:
        self.calls.append(lookup)
        return (self._candidate,)


def _query_candidate(operation: str) -> TrustedAuthorityCandidate:
    return TrustedAuthorityCandidate(
        principal_id=SCOPE.subject_id,
        session_id=SCOPE.session_id,
        project_id=SCOPE.project_id,
        scope=SCOPE,
        allowed_operations=frozenset({operation}),
        allowed_capabilities=frozenset({operation}),
        expires_at=EXPIRY,
        assurance=Assurance.AUTHENTICATED,
        source="server.auth.session",
        correlation_id="candidate-integration",
        resource=AuthorityResourceBinding(
            "task",
            TASK,
            hashlib.sha256(TASK.encode()).hexdigest(),
        ),
    )


def _query_route() -> AuthorityRouteContext:
    return AuthorityRouteContext(
        session_id=SCOPE.session_id,
        correlation_id="candidate-integration",
        claimed_user_id=SCOPE.subject_id,
        claimed_project_id=SCOPE.project_id,
        claimed_scope=SCOPE,
    )


async def _build_agent(database_path: Path):
    from openjiuwen.agent_teams import TeamAgent
    from openjiuwen.agent_teams.schema.blueprint import TeamAgentSpec
    from openjiuwen.agent_teams.schema.deep_agent_spec import DeepAgentSpec
    from openjiuwen.agent_teams.schema.team import (
        TeamRole,
        TeamRuntimeContext,
        TeamSpec,
    )
    from openjiuwen.agent_teams.tools.database import (
        DatabaseConfig,
        DatabaseType,
    )
    from openjiuwen.core.single_agent import AgentCard

    binding = derive_openjiuwen_scope_binding(SCOPE)
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
        AgentCard(id="livevoice-openjiuwen-facade", name="livevoice-openjiuwen-facade")
    ).configure(spec, context)
    await agent.team_backend.db.initialize()
    return agent


class _CommitThenFailAdvanceHandle:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.binding = inner.binding
        self.executor_authority = inner.executor_authority
        self._fail_once = True

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    async def advance_cursor(self, *args, **kwargs):
        result = await self._inner.advance_cursor(*args, **kwargs)
        if self._fail_once:
            self._fail_once = False
            raise RuntimeError("simulated response loss after durable commit")
        return result


async def _bind_agent(agent, *, fail_after_first_advance: bool = False):
    from openjiuwen.core.session.agent_team import create_agent_team_session

    binding = derive_openjiuwen_scope_binding(SCOPE)
    session = create_agent_team_session(
        session_id=binding.session_id,
        team_id=binding.team_name,
    )
    await agent.session_manager.bind_session(session)
    handle = agent.task_authority
    assert handle is not None
    if fail_after_first_advance:
        handle = _CommitThenFailAdvanceHandle(handle)
    return OpenJiuwenTaskFacade(handle, SCOPE)


async def _seed(agent) -> None:
    from openjiuwen.agent_teams.schema.status import (
        MemberMode,
        MemberStatus,
        TaskStatus,
    )
    from openjiuwen.agent_teams.schema.task import NewTaskSpec
    from openjiuwen.core.single_agent import AgentCard

    binding = derive_openjiuwen_scope_binding(SCOPE)
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
                title="original",
                content="content",
                initial_status=TaskStatus.PENDING.value,
                assignee=binding.member_name,
            )
        ],
    )
    assert created.ok


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exact_candidate_public_handle_sqlite_event_cursor_and_reopen(
    tmp_path: Path,
) -> None:
    candidate, expected = _require_exact_candidate()
    _require_candidate_import_source(candidate)
    assert candidate.is_dir()
    assert len(expected) == 40
    database_path = tmp_path / "agentcore.sqlite3"
    legacy_store_path = tmp_path / "legacy-task-store.sqlite3"

    from openjiuwen.agent_teams.spawn.shared_resources import cleanup_shared_resources

    first_agent = await _build_agent(database_path)
    try:
        first_facade = await _bind_agent(
            first_agent,
            fail_after_first_advance=True,
        )
        await _seed(first_agent)
        before = await first_facade.get(_authority("task.get"), TASK)
        assert before is not None and before.task.event_head == 1

        events = await first_facade.read_events(_authority("task.events"), TASK)
        assert [event.sequence for event in events.events] == [1]

        text = await first_facade.read_unread(
            _authority("task.unread_events"), TASK, "text"
        )
        voice = await first_facade.read_unread(
            _authority("task.unread_events"), TASK, "voice"
        )
        assert text is not None and voice is not None
        event = text.events[-1]
        advance_args = (
            _authority("task.ack_events"),
            TASK,
            "text",
            "candidate-advance",
        )
        advance_kwargs = {
            "expected_cursor_sequence": text.cursor.sequence,
            "expected_cursor_version": text.cursor.version,
            "expected_head_sequence": text.head_sequence,
            "acknowledged_sequence": event.sequence,
            "acknowledged_event_id": event.event_id,
            "acknowledged_event_payload_digest": event.payload_digest,
        }
        with pytest.raises(OpenJiuwenTaskFacadeError) as response_lost:
            await first_facade.advance_after_presentation_ack(
                *advance_args,
                **advance_kwargs,
            )
        assert response_lost.value.reason == "AGENTCORE_AUTHORITY_FAILURE"

        advanced = await first_facade.advance_after_presentation_ack(
            *advance_args,
            **advance_kwargs,
        )
        assert advanced.ok and advanced.replayed and advanced.advanced
        assert voice.cursor.sequence == 0
    finally:
        first_agent.session_manager.release_session()
        await first_agent.team_backend.db.close()
        cleanup_shared_resources()

    second_agent = await _build_agent(database_path)
    try:
        second_facade = await _bind_agent(second_agent)
        after = await second_facade.get(_authority("task.get"), TASK)
        assert after is not None
        assert after.task.title == "original"
        assert after.task.event_head == 1
        text_after = await second_facade.read_unread(
            _authority("task.unread_events"), TASK, "text"
        )
        voice_after = await second_facade.read_unread(
            _authority("task.unread_events"), TASK, "voice"
        )
        assert text_after is not None and text_after.cursor.sequence == 1
        assert voice_after is not None and voice_after.cursor.sequence == 0
        reopened_replay = await second_facade.advance_after_presentation_ack(
            *advance_args,
            **advance_kwargs,
        )
        assert reopened_replay.ok
        assert reopened_replay.replayed
        assert reopened_replay.advanced
        assert reopened_replay.cursor == advanced.cursor
    finally:
        second_agent.session_manager.release_session()
        await second_agent.team_backend.db.close()
        cleanup_shared_resources()

    assert database_path.exists()
    assert not legacy_store_path.exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exact_candidate_product_async_query_crosses_public_sqlite_path(
    tmp_path: Path,
) -> None:
    candidate, expected = _require_exact_candidate()
    _require_candidate_import_source(candidate)
    assert len(expected) == 40
    database_path = tmp_path / "agentcore-query.sqlite3"
    legacy_store_path = tmp_path / "legacy-task-store.sqlite3"

    from openjiuwen.agent_teams.spawn.shared_resources import cleanup_shared_resources

    agent = await _build_agent(database_path)
    try:
        facade = await _bind_agent(agent)
        await _seed(agent)
        resolver = _Resolver(_query_candidate("task.status"))
        text_effects: list[object] = []
        voice_effects: list[object] = []

        async def text_sink(event: object) -> None:
            text_effects.append(event)

        async def voice_sink(event: object) -> None:
            voice_effects.append(event)

        adapter = ProductP3TextAdapter(
            enabled=True,
            authority=P3AuthorityAdapter(
                ProductAuthorityService(
                    enabled=True,
                    resolver=resolver,
                    clock=lambda: datetime.fromisoformat(
                        NOW.replace("Z", "+00:00")
                    ).astimezone(UTC),
                )
            ),
            async_query_owner=OpenJiuwenProductP3QueryOwner(facade),
            subscription_factory=lambda _grant, _binding: None,
            generation_is_current=lambda _binding: True,
            arbiter=ProgressNotificationArbiter(),
            foreground=lambda: ForegroundSnapshot(
                interaction=ForegroundFact.SAFE,
                response=ForegroundFact.SAFE,
                presentation=ForegroundFact.SAFE,
                speech_policy=SpeechPolicy.DISPLAY_ONLY,
            ),
            text_sink=text_sink,
            voice_sink=voice_sink,
            clock=lambda: NOW,
        )

        result = await adapter.query(
            ProductP3QueryRequest(
                _query_route(),
                "task.status",
                "candidate-query-request",
                TASK,
            )
        )

        assert result.ok is True
        assert result.reason_id is ProductP3TextReason.QUERY_ACCEPTED
        assert result.result is not None
        assert result.result.result is not None
        assert result.result.result["projection"] == (
            "openjiuwen.agentcore.task-query.v1"
        )
        assert result.result.result["task"]["task_id"] == TASK
        assert result.result.result["task"]["status"] == "pending"
        assert len(resolver.calls) == 1
        assert text_effects == []
        assert voice_effects == []
    finally:
        agent.session_manager.release_session()
        await agent.team_backend.db.close()
        cleanup_shared_resources()

    assert database_path.exists()
    assert not legacy_store_path.exists()
