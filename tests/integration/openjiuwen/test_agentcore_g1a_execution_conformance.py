"""OJ-G1-A execution-ownership conformance against locked AgentCore.

Green controls record behavior that the existing TaskDao, Checkpointer,
Journal and Scheduler already provide.  Strict xfails exercise the real module
surfaces without adding a test-owned execution store, lease, generation CAS,
cancellation registry or effect journal.  Public-surface oracles must become
ordinary passing tests when fixed.  The restart and atomic-admission cases are
gap characterizations: once their public seams are selected, the implementation
PR must reconnect or replace them with acceptance oracles.

This is module-level evidence only.  It does not claim a real Agent/file-Tool
path, process crash injection, D2 effect reconciliation, migration or product
acceptance.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from importlib.metadata import distribution
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from openjiuwen.agent_teams.harness.async_tools import AsyncToolRuntime
from openjiuwen.agent_teams.messager import Messager
from openjiuwen.agent_teams.schema.status import TaskStatus
from openjiuwen.agent_teams.schema.task import TaskGraphSpec
from openjiuwen.agent_teams.tools.task_manager import TeamTaskManager
from openjiuwen.agent_teams.workflow.engine.journal import Journal, key_str
from openjiuwen.core.session.checkpointer.persistence import AgentStorage
from openjiuwen.core.session.config.base import Config
from openjiuwen.core.session.internal.agent import AgentSession

from tests.integration.openjiuwen.test_agentcore_g0_conformance import (
    LOCKED_AGENTCORE_COMMIT,
    LOCKED_AGENTCORE_VERSION,
    MemoryKVStore,
    build_scheduler,
    make_agent_session,
    opened_database,
    seed_team,
)


class LockedSourceMismatch(RuntimeError):
    """The conformance result is invalid because its dependency drifted."""


@pytest.fixture(scope="module", autouse=True)
def _exact_locked_agentcore_source() -> None:
    """Prevent every standalone G1-A result from drifting to another build."""

    dist = distribution("openjiuwen")
    direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
    if dist.version != LOCKED_AGENTCORE_VERSION:
        raise LockedSourceMismatch(f"expected {LOCKED_AGENTCORE_VERSION}, got {dist.version}")
    commit_id = direct_url.get("vcs_info", {}).get("commit_id")
    if commit_id != LOCKED_AGENTCORE_COMMIT:
        raise LockedSourceMismatch(f"expected {LOCKED_AGENTCORE_COMMIT}, got {commit_id}")


@dataclass(frozen=True, slots=True)
class AdmissionIntent:
    """Test input describing the exact execution generation allowed to run."""

    scope: str
    task_id: str
    profile: str
    generation: int

    def checkpoint(self) -> dict[str, str | int]:
        return {
            "scope": self.scope,
            "task_id": self.task_id,
            "profile": self.profile,
            "generation": self.generation,
        }


@dataclass(slots=True)
class CheckpointAdmissionFacade:
    """Thin test Adapter that connects AgentStorage facts to Scheduler activation.

    It deliberately owns no execution store, revision or CAS.  The optional
    events expose the unavoidable window between its final validation read and
    the Scheduler's independent Task start transaction.
    """

    store: MemoryKVStore
    session_id: str
    validated: asyncio.Event | None = None
    release: asyncio.Event | None = None

    async def activate(self, scheduler, intent: AdmissionIntent) -> bool:
        checkpoint = await _recover_checkpoint(self.store, self.session_id)
        if checkpoint != intent.checkpoint():
            return False
        if self.validated is not None:
            self.validated.set()
        if self.release is not None:
            await self.release.wait()
        await scheduler.activate()
        return True


class TaskExecutionFacade:
    """Small in-process relation Adapter; it adds no durability or settle API."""

    def __init__(self, manager: TeamTaskManager, runtime: AsyncToolRuntime) -> None:
        self.manager = manager
        self.runtime = runtime
        self._relations: dict[str, str] = {}

    def bind(self, task_id: str, execution_id: str) -> None:
        self._relations[task_id] = execution_id

    async def cancel(self, task_id: str):
        result = await self.manager.cancel(task_id)
        if result is not None:
            execution_id = self._relations.get(task_id)
            if execution_id is not None:
                assert await self.runtime.cancel(execution_id)
        return result

    async def complete(self, task_id: str):
        return await self.manager.complete(task_id)


async def _save_checkpoint(store: MemoryKVStore, session_id: str, checkpoint) -> None:
    await AgentStorage(store).save(make_agent_session(session_id, checkpoint=checkpoint))


async def _recover_checkpoint(store: MemoryKVStore, session_id: str):
    session = AgentSession(session_id=session_id, config=Config())
    # ``make_agent_session`` uses this stable agent id when the checkpoint is
    # saved; recovery identity is the pair (session id, agent id).
    session.agent_id = Mock(return_value="oj-g0-agent")
    await AgentStorage(store).recover(session)
    return session.state().get_global("checkpoint")


async def _seed_assigned_pending_task(database, *, team_name: str, task_id: str) -> None:
    manager = TeamTaskManager(
        team_name=team_name,
        member_name="leader",
        db=database,
        messager=AsyncMock(spec=Messager),
        dispatch_mode="scheduled",
    )
    result = await manager.add_graph(
        [TaskGraphSpec(title=task_id, content=task_id, task_id=task_id, assignee="worker")]
    )
    assert result.ok


@pytest.mark.asyncio
async def test_g1a_taskdao_cancel_complete_race_has_one_terminal_winner(tmp_path: Path) -> None:
    """P/T/C: existing TaskDao terminal CAS remains a reusable control."""

    async with opened_database(tmp_path / "terminal-race.db", session_id="oj-g1a-race") as database:
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
        persisted = await database.task.get_task("race-task")
        winners = [result for result in (cancel_result, complete_result) if result is not None]

        assert len(winners) == 1
        assert persisted.status in {TaskStatus.CANCELLED.value, TaskStatus.COMPLETED.value}
        assert winners[0]["task"].status == persisted.status


@pytest.mark.asyncio
async def test_g1a_checkpoint_and_journal_reopen_independent_facts(tmp_path: Path) -> None:
    """P/R/K: facts survive wrapper/session recreation on the same KV backend."""

    store = MemoryKVStore()
    checkpoint = AdmissionIntent("owner-team", "owner-task", "safe", 1).checkpoint()
    await _save_checkpoint(store, "oj-g1a-storage", checkpoint)

    journal_path = tmp_path / "owner.jsonl"
    wal_path = tmp_path / "owner.jsonl.wal"
    first_journal = await Journal.load(str(journal_path), wal_path=str(wal_path))
    call_key = key_str([["call", 0]])
    await first_journal.use(
        call_key,
        {"key": call_key, "sig": "stable", "kind": "dict", "result": {"value": 1}},
    )

    assert await _recover_checkpoint(store, "oj-g1a-storage") == checkpoint
    recovered_journal = await Journal.load(str(journal_path), wal_path=str(wal_path))
    assert recovered_journal.get_cached(call_key, "stable")["result"] == {"value": 1}


@pytest.mark.asyncio
async def test_g1a_scheduler_dispatches_one_valid_assigned_task(tmp_path: Path) -> None:
    """P/T: a thin exact-match gate reaches the Scheduler's dispatch edges."""

    intent = AdmissionIntent("valid-team", "valid-task", "safe", 1)
    store = MemoryKVStore()
    await _save_checkpoint(store, "oj-g1a-valid", intent.checkpoint())
    assert await _recover_checkpoint(store, "oj-g1a-valid") == intent.checkpoint()

    async with opened_database(tmp_path / "valid.db", session_id="oj-g1a-valid") as database:
        await seed_team(database, intent.scope, leader="leader", members=("worker",))
        await _seed_assigned_pending_task(database, team_name=intent.scope, task_id=intent.task_id)
        scheduler, host, manager, _bus = build_scheduler(
            database,
            team_name=intent.scope,
            leader="leader",
        )

        admitted = await CheckpointAdmissionFacade(store, "oj-g1a-valid").activate(
            scheduler,
            intent,
        )

        assert admitted is True
        assert (await manager.get(intent.task_id)).status == TaskStatus.IN_PROGRESS.value
        assert host.started_members == ["worker"]
        scheduler._infra.message_manager.send_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="OJ-G1A-01: AsyncTool cancel has no public await-until-unwound settlement contract",
)
async def test_accepted_task_cancel_quiesces_related_execution(tmp_path: Path) -> None:
    """N/S/T/C/X: accepted Task cancel must settle its related execution."""

    effects: list[str] = []
    injections: list[str] = []
    started = asyncio.Event()
    settled = asyncio.Event()

    async def inject(text: str) -> None:
        injections.append(text)

    runtime = AsyncToolRuntime(inject=inject)

    async def work() -> str:
        started.set()
        try:
            await asyncio.Event().wait()
            effects.append("forbidden-after-task-cancel")
            return "completed-after-task-cancel"
        finally:
            settled.set()

    runtime.launch("execution-1", work, tool_name="file", description="write")
    await started.wait()
    try:
        async with opened_database(tmp_path / "cancel-relation.db", session_id="oj-g1a-cancel") as database:
            await seed_team(database, "cancel-team", leader="leader")
            assert await database.task.create_task(
                task_id="task-1",
                team_name="cancel-team",
                title="cancel",
                content="cancel",
                status=TaskStatus.IN_PROGRESS.value,
            )
            manager = TeamTaskManager(
                team_name="cancel-team",
                member_name="leader",
                db=database,
                messager=AsyncMock(spec=Messager),
            )
            facade = TaskExecutionFacade(manager, runtime)
            facade.bind("task-1", "execution-1")

            assert await facade.cancel("task-1") is not None

            record = runtime.get("execution-1")
            assert record is not None
            assert settled.is_set()
            assert record.status != "completed"
            assert effects == []
            assert injections == []
    finally:
        runtime.cancel_all()
        await asyncio.wait_for(settled.wait(), timeout=1.0)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="OJ-G1A-02: cancelled AsyncTool can revive, spill and inject after swallowed cancellation",
)
async def test_cancel_waits_for_hostile_tool_unwind_and_fences_runtime_spill(tmp_path: Path) -> None:
    """N/B/T/C/X: swallowed cancellation cannot trigger Runtime-owned spill."""

    effect_file = tmp_path / "hostile.output"
    injections: list[str] = []
    started = asyncio.Event()
    cancel_seen = asyncio.Event()
    release = asyncio.Event()
    settled = asyncio.Event()

    async def inject(text: str) -> None:
        injections.append(text)

    runtime = AsyncToolRuntime(
        inject=inject,
        output_dir_resolver=lambda: tmp_path,
        spill_threshold=8,
    )

    async def hostile_work() -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancel_seen.set()
            await release.wait()
            return "post-cancel-runtime-spill"
        finally:
            settled.set()

    runtime.launch("hostile", hostile_work, tool_name="file", description="hostile write")
    await started.wait()
    cancel_call = asyncio.create_task(runtime.cancel("hostile"))
    try:
        await asyncio.wait_for(cancel_seen.wait(), timeout=1.0)
        await asyncio.sleep(0)
        cancel_returned_before_unwind = cancel_call.done()
        release.set()
        accepted = await asyncio.wait_for(cancel_call, timeout=1.0)
        await asyncio.wait_for(settled.wait(), timeout=1.0)

        async def runtime_effect_observed() -> None:
            while not effect_file.exists() and not injections:
                await asyncio.sleep(0)

        try:
            await asyncio.wait_for(runtime_effect_observed(), timeout=0.5)
        except asyncio.TimeoutError:
            pass

        record = runtime.get("hostile")
        assert accepted is True
        assert cancel_returned_before_unwind is False
        assert effect_file.exists() is False
        assert record is not None and record.status != "completed"
        assert injections == []
    finally:
        release.set()
        runtime.cancel_all()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_task_terminal_winner_and_execution_have_one_disposition(
    tmp_path: Path,
) -> None:
    """P/N/S/T/C: a thin relation Adapter handles either Task race winner."""

    effects: list[str] = []
    injections: list[str] = []
    started = asyncio.Event()
    release = asyncio.Event()
    settled = asyncio.Event()

    async def inject(text: str) -> None:
        injections.append(text)

    runtime = AsyncToolRuntime(inject=inject)

    async def work() -> str:
        started.set()
        try:
            await release.wait()
            effects.append("winner-effect")
            return "winner-completion"
        finally:
            settled.set()

    runtime.launch("race-execution", work, tool_name="file", description="race")
    await started.wait()
    try:
        async with opened_database(tmp_path / "coupled-race.db", session_id="oj-g1a-coupled") as database:
            await seed_team(database, "race-team", leader="leader")
            assert await database.task.create_task(
                task_id="race-task",
                team_name="race-team",
                title="race",
                content="race",
                status=TaskStatus.PENDING.value,
            )
            assert await database.task.claim_task("race-task", "leader")
            manager = TeamTaskManager(
                team_name="race-team",
                member_name="leader",
                db=database,
                messager=AsyncMock(spec=Messager),
            )
            facade = TaskExecutionFacade(manager, runtime)
            facade.bind("race-task", "race-execution")

            cancel_call = asyncio.create_task(facade.cancel("race-task"))
            complete_call = asyncio.create_task(facade.complete("race-task"))
            cancel_result, complete_result = await asyncio.gather(cancel_call, complete_call)
            persisted = await database.task.get_task("race-task")
            cancel_won = cancel_result is not None
            complete_won = complete_result.ok
            assert cancel_won + complete_won == 1

            release.set()
            await asyncio.wait_for(settled.wait(), timeout=1.0)
            await asyncio.sleep(0)
            record = runtime.get("race-execution")
            assert record is not None
            if cancel_won:
                assert persisted.status == TaskStatus.CANCELLED.value
                assert record.status == "error"
                assert effects == []
                assert injections == []
            else:
                assert persisted.status == TaskStatus.COMPLETED.value
                assert record.status == "completed"
                assert effects == ["winner-effect"]
                assert len(injections) == 1
    finally:
        release.set()
        runtime.cancel_all()
        await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="OJ-G1A-04 characterization: no public restart owner-reconcile seam exists",
)
async def test_restart_characterizes_missing_owner_reconcile(tmp_path: Path) -> None:
    """N/S/R/I: restart cannot preserve a phantom in-progress Task."""

    database_path = tmp_path / "restart-owner.db"
    store = MemoryKVStore()
    binding = {
        "scope": "restart-team",
        "task_id": "restart-task",
        "execution_id": "restart-execution",
        "profile": "safe",
        "generation": 1,
        "disposition": "in_progress",
    }
    await _save_checkpoint(store, "oj-g1a-restart-owner", binding)
    async with opened_database(database_path, session_id="oj-g1a-restart") as first:
        await seed_team(first, "restart-team", leader="leader", members=("worker",))
        await _seed_assigned_pending_task(first, team_name="restart-team", task_id="restart-task")
        manager = TeamTaskManager(
            team_name="restart-team",
            member_name="worker",
            db=first,
            messager=AsyncMock(spec=Messager),
            dispatch_mode="scheduled",
        )
        assert (await manager.start_task("restart-task")).ok

    restarted_runtime = AsyncToolRuntime(inject=AsyncMock())
    recovered_binding = await _recover_checkpoint(store, "oj-g1a-restart-owner")
    async with opened_database(database_path, session_id="oj-g1a-restart") as reopened:
        task = await reopened.task.get_task("restart-task")
        assert task.status == TaskStatus.IN_PROGRESS.value
        assert recovered_binding == binding

        execution_id = recovered_binding["execution_id"]
        owner = restarted_runtime.get(execution_id)
        disposition = recovered_binding.get("disposition")
        assert owner is not None or disposition in {
            "orphaned",
            "recoverable",
        }


MISMATCHED_CHECKPOINTS = [
    pytest.param(
        {"scope": "admit-team", "task_id": "admit-task", "profile": "wrong", "generation": 7},
        id="profile-mismatch",
    ),
    pytest.param(
        {"scope": "admit-team", "task_id": "admit-task", "profile": "safe", "generation": 6},
        id="stale-generation",
    ),
    pytest.param(
        {"scope": "admit-team", "task_id": "other-task", "profile": "safe", "generation": 7},
        id="task-mismatch",
    ),
    pytest.param(
        {"scope": "other-team", "task_id": "admit-task", "profile": "safe", "generation": 7},
        id="scope-mismatch",
    ),
    pytest.param("corrupt-checkpoint", id="corrupt-checkpoint"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint", MISMATCHED_CHECKPOINTS)
async def test_mismatched_checkpoint_has_zero_scheduler_effects(tmp_path: Path, checkpoint) -> None:
    """P/N/B/S/T/R/I/X: a thin pre-dispatch Adapter rejects mismatch."""

    intent = AdmissionIntent("admit-team", "admit-task", "safe", 7)
    store = MemoryKVStore()
    await _save_checkpoint(store, "oj-g1a-admission", checkpoint)
    assert await _recover_checkpoint(store, "oj-g1a-admission") == checkpoint

    async with opened_database(tmp_path / "admission.db", session_id="oj-g1a-admission") as database:
        await seed_team(database, intent.scope, leader="leader", members=("worker",))
        await _seed_assigned_pending_task(database, team_name=intent.scope, task_id=intent.task_id)
        scheduler, host, manager, bus = build_scheduler(
            database,
            team_name=intent.scope,
            leader="leader",
        )

        admitted = await CheckpointAdmissionFacade(store, "oj-g1a-admission").activate(
            scheduler,
            intent,
        )

        assert admitted is False
        assert (await manager.get(intent.task_id)).status == TaskStatus.PENDING.value
        assert host.started_members == []
        scheduler._infra.message_manager.send_message.assert_not_awaited()
        bus.publish.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="OJ-G1A-05 characterization: no atomic generation-aware admission seam exists",
)
async def test_generation_race_characterizes_missing_atomic_admission(tmp_path: Path) -> None:
    """N/S/T/R/C: stale-after-validation cannot pass a wrapper-only fence."""

    intent = AdmissionIntent("stale-team", "stale-task", "safe", 1)
    store = MemoryKVStore()
    await _save_checkpoint(store, "oj-g1a-stale", intent.checkpoint())
    async with opened_database(tmp_path / "stale.db", session_id="oj-g1a-stale") as database:
        await seed_team(database, intent.scope, leader="leader", members=("worker",))
        await _seed_assigned_pending_task(database, team_name=intent.scope, task_id=intent.task_id)
        scheduler, host, manager, bus = build_scheduler(
            database,
            team_name=intent.scope,
            leader="leader",
        )

        validated = asyncio.Event()
        release = asyncio.Event()
        facade = CheckpointAdmissionFacade(
            store,
            "oj-g1a-stale",
            validated=validated,
            release=release,
        )
        activation = asyncio.create_task(facade.activate(scheduler, intent))
        await asyncio.wait_for(validated.wait(), timeout=1.0)

        advanced = AdmissionIntent(intent.scope, intent.task_id, intent.profile, 2)
        await _save_checkpoint(store, "oj-g1a-stale", advanced.checkpoint())
        assert await _recover_checkpoint(store, "oj-g1a-stale") == advanced.checkpoint()
        release.set()
        assert await asyncio.wait_for(activation, timeout=1.0) is True

        assert (await manager.get(intent.task_id)).status == TaskStatus.PENDING.value
        assert host.started_members == []
        scheduler._infra.message_manager.send_message.assert_not_awaited()
        bus.publish.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="OJ-G1A-06: duplicate AsyncTool identity overwrites the active handle",
)
async def test_duplicate_async_tool_identity_fails_closed() -> None:
    """N/S/T/C/I: a running execution identity cannot be replaced in-place."""

    first_started = asyncio.Event()
    first_release = asyncio.Event()
    first_settled = asyncio.Event()
    second_release = asyncio.Event()

    async def first_work() -> str:
        first_started.set()
        try:
            await first_release.wait()
            return "first"
        finally:
            first_settled.set()

    async def second_work() -> str:
        await second_release.wait()
        return "second"

    runtime = AsyncToolRuntime(inject=AsyncMock())
    runtime.launch("duplicate", first_work, tool_name="file", description="first")
    await first_started.wait()
    try:
        rejected = False
        try:
            runtime.launch("duplicate", second_work, tool_name="file", description="second")
        except (ValueError, RuntimeError):
            rejected = True
        assert rejected is True
    finally:
        first_release.set()
        second_release.set()
        runtime.cancel_all()
        await asyncio.wait_for(first_settled.wait(), timeout=1.0)
        await asyncio.sleep(0)
