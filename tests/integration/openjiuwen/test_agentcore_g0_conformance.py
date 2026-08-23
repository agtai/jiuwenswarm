"""OJ-G0 module-composition conformance against the locked AgentCore build.

This suite deliberately uses the real ``openjiuwen==0.1.16`` modules installed
from commit ``94e10cb6``.  Passing tests record capabilities that can already be
composed.  Strict xfails are red conformance oracles for missing generic
capabilities; an implementation that turns one into XPASS must remove the
marker and make the oracle an ordinary passing test.

The suite is module-level only.  It does not claim a real Agent/file-Tool path,
browser presentation, migration safety, or product acceptance.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import fields
from importlib.metadata import distribution
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import update

from openjiuwen.agent_teams.agent.infra import TeamInfra
from openjiuwen.agent_teams.agent.scheduling import TeamScheduler
from openjiuwen.agent_teams.context import reset_session_id, set_session_id
from openjiuwen.agent_teams.harness.async_tools import AsyncToolRuntime
from openjiuwen.agent_teams.messager import Messager
from openjiuwen.agent_teams.schema.status import MemberMode, TaskStatus
from openjiuwen.agent_teams.schema.task import TaskGraphSpec
from openjiuwen.agent_teams.tools.database import DatabaseConfig, DatabaseType, TeamDatabase
from openjiuwen.agent_teams.tools.models import (
    MessageReadStatusBase,
    _get_message_model,
    _get_task_model,
)
from openjiuwen.agent_teams.tools.task_manager import TeamTaskManager
from openjiuwen.agent_teams.workflow.engine.journal import Journal, key_str
from openjiuwen.agent_teams.workflow.engine.progress import WorkflowProgressEvent
from openjiuwen.core.foundation.store.base_kv_store import BaseKVStore, BasedKVStorePipeline
from openjiuwen.core.session.checkpointer.persistence import AgentStorage
from openjiuwen.core.session.config.base import Config
from openjiuwen.core.session.internal.agent import AgentSession
from openjiuwen.core.single_agent import AgentCard


LOCKED_AGENTCORE_VERSION = "0.1.16"
LOCKED_AGENTCORE_COMMIT = "94e10cb6102c36fe78a64547957c0def97299273"


class MemoryKVStore(BaseKVStore):
    """Minimal persistent-backend double used by the real AgentStorage."""

    def __init__(self) -> None:
        self.values: dict[str, str | bytes] = {}

    async def set(self, key: str, value: str | bytes) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | bytes | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def exclusive_set(self, key: str, value: str | bytes, expiry: int | None = None) -> bool:
        del expiry
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def get_by_prefix(self, prefix: str) -> dict[str, str | bytes]:
        return {key: value for key, value in self.values.items() if key.startswith(prefix)}

    async def delete_by_prefix(self, prefix: str, batch_size: int | None = None) -> None:
        del batch_size
        for key in [key for key in self.values if key.startswith(prefix)]:
            del self.values[key]

    async def mget(self, keys: list[str]) -> list[str | bytes | None]:
        return [self.values.get(key) for key in keys]

    async def batch_delete(self, keys: list[str], batch_size: int | None = None) -> int:
        del batch_size
        deleted = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                deleted += 1
        return deleted

    def pipeline(self) -> BasedKVStorePipeline:
        async def execute(operations):
            results = []
            for operation in operations:
                if operation[0] == "set":
                    self.values[operation[1]] = operation[2]
                    results.append(None)
                elif operation[0] == "get":
                    results.append(self.values.get(operation[1]))
                elif operation[0] == "exists":
                    results.append(operation[1] in self.values)
            return results

        return BasedKVStorePipeline(execute)


class SchedulerHostProbe:
    """Records the real TeamScheduler's host-visible effects."""

    def __init__(self) -> None:
        self.leader_inputs: list[str] = []
        self.started_members: list[str] = []

    async def deliver_input(self, content, *, use_steer: bool = True) -> None:
        del use_steer
        self.leader_inputs.append(str(content))

    async def auto_start_member(self, member_name: str) -> bool:
        self.started_members.append(member_name)
        return True


class NoReviewBackend:
    @staticmethod
    def task_verification_enabled() -> bool:
        return False


@asynccontextmanager
async def opened_database(path: Path, *, session_id: str):
    """Open the real file-backed AgentTeams database for one session scope."""

    token = set_session_id(session_id)
    database = TeamDatabase(
        DatabaseConfig(
            db_type=DatabaseType.SQLITE,
            connection_string=str(path),
            db_enable_wal=False,
        )
    )
    try:
        await database.initialize()
        yield database
    finally:
        await database.close()
        reset_session_id(token)


async def seed_team(
    database: TeamDatabase,
    team_name: str,
    *,
    leader: str,
    members: tuple[str, ...] = (),
    dispatch_mode: str = "scheduled",
) -> None:
    assert await database.team.create_team(
        team_name=team_name,
        display_name=team_name,
        leader_member_name=leader,
        dispatch_mode=dispatch_mode,
    )
    for member_name in dict.fromkeys((leader, *members)):
        assert await database.member.create_member(
            member_name=member_name,
            team_name=team_name,
            display_name=member_name,
            agent_card=AgentCard().model_dump_json(),
            status="READY",
            mode=MemberMode.BUILD_MODE.value,
        )


def build_scheduler(database: TeamDatabase, *, team_name: str, leader: str):
    """Compose the real TaskManager/Scheduler with effect-recording edges."""

    bus = AsyncMock(spec=Messager)
    task_manager = TeamTaskManager(
        team_name=team_name,
        member_name=leader,
        db=database,
        messager=bus,
        dispatch_mode="scheduled",
    )
    message_manager = AsyncMock()
    message_manager.send_message = AsyncMock(return_value="message-1")
    infra = TeamInfra()
    infra.task_manager = task_manager
    infra.message_manager = message_manager
    infra.team_backend = NoReviewBackend()
    spec = SimpleNamespace(
        team_name=team_name,
        default_max_review_rounds=3,
        review_stall_timeout=1800,
        agents=None,
    )
    host = SchedulerHostProbe()
    scheduler = TeamScheduler(
        host,
        blueprint=SimpleNamespace(spec=spec, team_name=team_name),
        infra=infra,
    )
    return scheduler, host, task_manager, bus


def make_agent_session(session_id: str, *, checkpoint: dict) -> AgentSession:
    session = AgentSession(session_id=session_id, config=Config())
    session.agent_id = Mock(return_value="oj-g0-agent")
    session.state().update_global({"checkpoint": checkpoint})
    return session


def test_locked_agentcore_source_is_exact() -> None:
    """K/I: prevent a passing result from silently drifting to another build."""

    dist = distribution("openjiuwen")
    direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
    assert dist.version == LOCKED_AGENTCORE_VERSION
    assert direct_url["vcs_info"]["commit_id"] == LOCKED_AGENTCORE_COMMIT


@pytest.mark.asyncio
async def test_taskdao_cancel_complete_race_has_one_terminal_winner(tmp_path: Path) -> None:
    """P/S/T/C: TaskDao serializes cancel versus completion to one terminal fact."""

    async with opened_database(tmp_path / "race.db", session_id="oj-g0-race") as database:
        await seed_team(database, "race-team", leader="leader")
        assert await database.task.create_task(
            task_id="race-task",
            team_name="race-team",
            title="race",
            content="race",
            status=TaskStatus.IN_PROGRESS.value,
        )

        cancel_result, complete_result = await asyncio.gather(
            database.task.cancel_task("race-task"),
            database.task.complete_task("race-task"),
        )
        winners = [result for result in (cancel_result, complete_result) if result is not None]
        persisted = await database.task.get_task("race-task")

        assert len(winners) == 1
        assert persisted.status in {TaskStatus.CANCELLED.value, TaskStatus.COMPLETED.value}
        assert winners[0]["task"].status == persisted.status


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="OJ-G0-01: TaskDao cancel has no relation/bridge to AsyncToolRuntime unwind",
)
async def test_task_cancel_quiesces_related_async_tool_before_effect(tmp_path: Path) -> None:
    """N/T/C/X: accepted Task cancel must fence the related Tool effect."""

    effects: list[str] = []
    started = asyncio.Event()
    release_effect = asyncio.Event()

    async def inject(_text: str) -> None:
        return None

    runtime = AsyncToolRuntime(inject=inject)

    async def work() -> str:
        started.set()
        await release_effect.wait()
        effects.append("forbidden")
        return "done"

    async with opened_database(tmp_path / "cancel-bridge.db", session_id="oj-g0-cancel") as database:
        await seed_team(database, "cancel-team", leader="leader")
        assert await database.task.create_task(
            task_id="shared-id",
            team_name="cancel-team",
            title="cancel",
            content="cancel",
            status=TaskStatus.IN_PROGRESS.value,
        )
        runtime.launch("shared-id", work, tool_name="file", description="effect")
        await started.wait()
        try:
            assert await database.task.cancel_task("shared-id") is not None
            await asyncio.sleep(0)
            assert runtime.get("shared-id").status == "error"
            release_effect.set()
            await runtime.wait("shared-id", 0.2)
            assert effects == []
        finally:
            runtime.cancel_all()
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_taskdao_reopens_persisted_task_without_old_python_objects(tmp_path: Path) -> None:
    """P/R/I: a new database object recovers Task truth from SQLite."""

    database_path = tmp_path / "reopen.db"
    async with opened_database(database_path, session_id="oj-g0-reopen") as first:
        await seed_team(first, "reopen-team", leader="leader")
        assert await first.task.create_task(
            task_id="persisted",
            team_name="reopen-team",
            title="persisted",
            content="persisted",
            status=TaskStatus.PENDING.value,
        )

    async with opened_database(database_path, session_id="oj-g0-reopen") as reopened:
        persisted = await reopened.task.get_task("persisted")
        assert persisted is not None
        assert persisted.team_name == "reopen-team"
        assert persisted.status == TaskStatus.PENDING.value


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="OJ-G0-02: active AsyncTool execution has no durable record or restart reconciler",
)
async def test_restart_does_not_leave_phantom_running_task(tmp_path: Path) -> None:
    """N/S/R: reopen must not retain running Task truth with no execution owner."""

    database_path = tmp_path / "running-reopen.db"
    async with opened_database(database_path, session_id="oj-g0-running") as first:
        await seed_team(first, "running-team", leader="leader")
        assert await first.task.create_task(
            task_id="orphan",
            team_name="running-team",
            title="orphan",
            content="orphan",
            status=TaskStatus.IN_PROGRESS.value,
        )

    async with opened_database(database_path, session_id="oj-g0-running") as reopened:
        orphan = await reopened.task.get_task("orphan")
        assert orphan.status != TaskStatus.IN_PROGRESS.value


@pytest.mark.asyncio
async def test_checkpointer_and_journal_recover_independent_facts(tmp_path: Path) -> None:
    """P/R/K: existing storage modules independently survive object recreation."""

    kv_store = MemoryKVStore()
    first_session = make_agent_session(
        "oj-g0-checkpoint",
        checkpoint={"task_id": "task-1", "profile": "safe", "generation": 1},
    )
    await AgentStorage(kv_store).save(first_session)

    journal_path = tmp_path / "workflow.jsonl"
    wal_path = tmp_path / "workflow.jsonl.wal"
    first_journal = await Journal.load(str(journal_path), wal_path=str(wal_path))
    call_key = key_str([["call", 0]])
    await first_journal.use(
        call_key,
        {"key": call_key, "sig": "stable", "kind": "dict", "result": {"value": 1}},
    )

    recovered_session = AgentSession(session_id="oj-g0-checkpoint", config=Config())
    recovered_session.agent_id = Mock(return_value="oj-g0-agent")
    await AgentStorage(kv_store).recover(recovered_session)
    recovered_journal = await Journal.load(str(journal_path), wal_path=str(wal_path))

    assert recovered_session.state().get_global("checkpoint") == {
        "task_id": "task-1",
        "profile": "safe",
        "generation": 1,
    }
    assert recovered_journal.get_cached(call_key, "stable")["result"] == {"value": 1}


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="OJ-G0-03: Scheduler has no Task/checkpoint/profile/generation admission relation",
)
async def test_d1_wrong_profile_checkpoint_cannot_dispatch(tmp_path: Path) -> None:
    """N/S/R/I: a scope/profile-invalid checkpoint must not resume a Task."""

    database_path = tmp_path / "d1.db"
    kv_store = MemoryKVStore()
    await AgentStorage(kv_store).save(
        make_agent_session(
            "oj-g0-d1",
            checkpoint={"task_id": "d1-task", "profile": "wrong", "generation": 7},
        )
    )

    async with opened_database(database_path, session_id="oj-g0-d1") as first:
        await seed_team(first, "d1-team", leader="leader", members=("worker",))
        manager = TeamTaskManager(
            team_name="d1-team",
            member_name="leader",
            db=first,
            messager=AsyncMock(spec=Messager),
            dispatch_mode="scheduled",
        )
        created = await manager.add_graph(
            [TaskGraphSpec(title="d1", content="d1", task_id="d1-task", assignee="worker")]
        )
        assert created.ok

    recovered_session = AgentSession(session_id="oj-g0-d1", config=Config())
    recovered_session.agent_id = Mock(return_value="oj-g0-agent")
    await AgentStorage(kv_store).recover(recovered_session)
    assert recovered_session.state().get_global("checkpoint")["profile"] == "wrong"

    async with opened_database(database_path, session_id="oj-g0-d1") as reopened:
        scheduler, host, manager, _bus = build_scheduler(
            reopened,
            team_name="d1-team",
            leader="leader",
        )
        await scheduler.activate()
        task = await manager.get("d1-task")
        assert task.status == TaskStatus.PENDING.value
        assert host.started_members == []


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="OJ-G0-04: Journal/AsyncTool have no canonical effect receipt or reconcile hook",
)
async def test_d2_restart_does_not_repeat_applied_external_effect(tmp_path: Path) -> None:
    """N/B/R/C: crash after effect but before result must not repeat the effect."""

    effect_file = tmp_path / "effect.txt"
    journal_path = tmp_path / "effect-journal.jsonl"
    wal_path = tmp_path / "effect-journal.jsonl.wal"
    await Journal.load(str(journal_path), wal_path=str(wal_path))
    applied = asyncio.Event()
    never_set = asyncio.Event()

    async def inject(_text: str) -> None:
        return None

    async def apply_then_crash() -> str:
        previous = effect_file.read_text(encoding="utf-8") if effect_file.exists() else ""
        effect_file.write_text(previous + "applied\n", encoding="utf-8")
        applied.set()
        await never_set.wait()
        return "receipt"

    first_runtime = AsyncToolRuntime(inject=inject)
    first_runtime.launch("effect-1", apply_then_crash, tool_name="file", description="append")
    await applied.wait()
    assert await first_runtime.cancel("effect-1") is True
    await asyncio.sleep(0)

    recovered_journal = await Journal.load(str(journal_path), wal_path=str(wal_path))
    assert recovered_journal.prior == {}

    async def retry_effect() -> str:
        with effect_file.open("a", encoding="utf-8") as stream:
            stream.write("applied\n")
        return "receipt"

    second_runtime = AsyncToolRuntime(inject=inject)
    second_runtime.launch("effect-1", retry_effect, tool_name="file", description="append")
    await second_runtime.wait("effect-1", 1.0)

    assert effect_file.read_text(encoding="utf-8").splitlines() == ["applied"]


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="OJ-G0-05: TaskDao point operations do not include mandatory team scope predicates",
)
async def test_wrong_team_known_task_id_has_zero_disclosure_and_mutation(tmp_path: Path) -> None:
    """N/I/X: another team knowing a Task ID must learn and mutate nothing."""

    async with opened_database(tmp_path / "scope.db", session_id="oj-g0-scope") as database:
        await seed_team(database, "team-a", leader="leader-a")
        await seed_team(database, "team-b", leader="leader-b")
        assert await database.task.create_task(
            task_id="known-id",
            team_name="team-a",
            title="secret",
            content="secret",
            status=TaskStatus.IN_PROGRESS.value,
        )
        bus = AsyncMock(spec=Messager)
        wrong_scope = TeamTaskManager(
            team_name="team-b",
            member_name="leader-b",
            db=database,
            messager=bus,
        )

        disclosed = await wrong_scope.get("known-id")
        mutation = await wrong_scope.cancel("known-id")
        persisted = await database.task.get_task("known-id")

        assert disclosed is None
        assert mutation is None
        assert persisted.status == TaskStatus.IN_PROGRESS.value
        bus.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_uses_stable_fifo_for_equal_timestamps(tmp_path: Path) -> None:
    """P/T/C: the existing TeamScheduler chooses task_id as stable FIFO tie-break."""

    async with opened_database(tmp_path / "scheduler.db", session_id="oj-g0-scheduler") as database:
        await seed_team(database, "sched-team", leader="leader", members=("worker",))
        scheduler, host, manager, _bus = build_scheduler(
            database,
            team_name="sched-team",
            leader="leader",
        )
        created = await manager.add_graph(
            [
                TaskGraphSpec(title="b", content="b", task_id="b", assignee="worker"),
                TaskGraphSpec(title="a", content="a", task_id="a", assignee="worker"),
            ]
        )
        assert created.ok
        task_model = _get_task_model()
        async with database.session_local() as session:
            await session.execute(update(task_model).values(updated_at=1_000))
            await session.commit()

        await scheduler.activate()

        assert (await manager.get("a")).status == TaskStatus.IN_PROGRESS.value
        assert (await manager.get("b")).status == TaskStatus.PENDING.value
        assert host.started_members == ["worker"]


@pytest.mark.xfail(
    strict=True,
    reason="OJ-G0-06: WorkflowProgressEvent has no authoritative envelope/sequence/outbox identity",
)
def test_progress_event_carries_replay_safe_ordering_identity() -> None:
    """N/T/R/I: progress must be replayable without wall-clock ordering."""

    event = WorkflowProgressEvent(kind="agent_started", correlation_id="correlation-1")
    required = {
        "event_id",
        "scope",
        "stream_ref",
        "sequence",
        "producer",
        "causation_id",
    }
    assert required <= {item.name for item in fields(event)}


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="OJ-G0-07: millisecond read_at watermark can over-ACK same-time broadcasts",
)
async def test_read_watermark_does_not_overack_same_timestamp_message(tmp_path: Path) -> None:
    """N/B/T/C: ACK of one row must not consume a distinct same-time row."""

    async with opened_database(tmp_path / "cursor.db", session_id="oj-g0-cursor") as database:
        await seed_team(database, "cursor-team", leader="sender", members=("reader",))
        assert await database.message.create_message(
            "m1",
            "cursor-team",
            "sender",
            "first",
            broadcast=True,
        )
        assert await database.message.create_message(
            "m2",
            "cursor-team",
            "sender",
            "second",
            broadcast=True,
        )
        message_model = _get_message_model()
        async with database.session_local() as session:
            await session.execute(update(message_model).values(timestamp=10_000))
            await session.commit()

        assert await database.message.mark_message_read("m1", "reader") is True
        unread = await database.message.get_broadcast_messages(
            "cursor-team",
            "reader",
            unread_only=True,
        )
        assert [message.message_id for message in unread] == ["m2"]


@pytest.mark.xfail(
    strict=True,
    reason="OJ-G0-07: MessageReadStatus has no stream/channel/sequence ACK identity",
)
def test_ack_identity_isolated_by_stream_consumer_and_channel() -> None:
    """I/K: text and voice consumers require separate monotonic cursors."""

    assert {"stream_id", "consumer_id", "channel", "sequence"} <= MessageReadStatusBase.model_fields.keys()
