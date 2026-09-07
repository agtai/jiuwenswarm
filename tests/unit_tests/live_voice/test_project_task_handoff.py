"""Admission during real Git/SQLite Direct Task settlement, without timed races."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import TerminalOutcome
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    AuthenticatedPrincipal,
    ServerSessionProjectAuthorityResolver,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice import project_code_executor
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    DirectProjectManagedBaselineReader,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_p3_4_durability_runtime import (
    _create_selected_task,
)
from tests.unit_tests.live_voice.test_persistent_task_core import (
    EXPIRY,
    NOW,
    _cancel,
    _scope,
)
from tests.unit_tests.live_voice.test_project_code_executor import (
    _direct_binding,
    _git_project,
    _wait_direct_settled,
)


@pytest_asyncio.fixture
async def handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = tmp_path / "project"
    _git_project(project)
    database = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(database)
    current_time = [NOW]
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.task_store.utc_now", lambda: current_time[0]
    )
    started = asyncio.Event()
    finish_body = asyncio.Event()
    applied = asyncio.Event()
    finish_settlement = asyncio.Event()

    class Executor:
        calls = 0
        fail_first = False

        async def process_background_code_task_stream(self, request):
            self.calls += 1
            number = self.calls
            target = Path(request.params["project_dir"])
            (target / f"result-{number}.md").write_text(
                f"result {number}\n", encoding="utf-8"
            )
            if number == 1:
                started.set()
                await finish_body.wait()
                if self.fail_first:
                    raise RuntimeError("injected Agent failure")
            yield AgentResponseChunk(
                request.request_id,
                request.channel_id,
                payload={"event_type": "chat.final", "content": f"result-{number}.md"},
                is_complete=True,
            )

    executor = Executor()
    baseline = DirectProjectManagedBaselineReader(database, store=store)
    authority = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1", "project_dir": str(project),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id, project_dir=str(project), hidden=False,
            work_mode="code",
        ),
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        managed_worktree_reader=baseline,
    )
    principal = AuthenticatedPrincipal(
        principal_id="user-1", allowed_project_ids=frozenset({"project-1"}),
        allowed_operations=frozenset({"task.create"}), expires_at=EXPIRY,
    )

    class Resolver:
        calls = 0

        async def resolve(self, spec, *, for_dispatch):
            self.calls += 1
            authority.revalidate(
                spec.context, principal=principal, now=current_time[0],
                for_dispatch=for_dispatch,
            )
            return _direct_binding(project, executor)

    resolver = Resolver()
    adapter = DirectProjectCodeExecutorAdapter(
        resolver, database, durability_store=store, clock=lambda: current_time[0],
    )
    real_settle = adapter._settle_d2_project_effect

    async def gated_settle(**kwargs):
        await real_settle(**kwargs)
        if executor.calls == 1:
            applied.set()
            await finish_settlement.wait()

    monkeypatch.setattr(adapter, "_settle_d2_project_effect", gated_settle)
    core = PersistentTaskCore(store, adapter)
    _, first = _create_selected_task(
        store, core, project, adapter, identity_suffix="-first"
    )
    assert await core.drain_outbox_once(worker_id="start-first", observed_at=NOW)
    await asyncio.wait_for(started.wait(), timeout=10)
    _, second = _create_selected_task(
        store, core, project, adapter, identity_suffix="-second"
    )

    def advance():
        current_time[0] = (
            datetime.fromisoformat(current_time[0].replace("Z", "+00:00"))
            + timedelta(seconds=31)
        ).isoformat().replace("+00:00", "Z")
        return current_time[0]

    harness = SimpleNamespace(
        project=project, database=database, store=store, adapter=adapter, core=core,
        first=first, second=second, executor=executor, resolver=resolver,
        finish_body=finish_body, applied=applied, finish_settlement=finish_settlement,
        now=lambda: current_time[0], advance=advance,
    )
    try:
        yield harness
    finally:
        finish_body.set()
        finish_settlement.set()
        await _wait_direct_settled(adapter)
        await adapter.close()


def _assert_queued_without_execution(h):
    task = h.store.get_task(h.second.task_id, _scope())
    assert task.state.value == "accepted" and task.outcome is None
    attempt = h.store.get_attempt(h.second.attempt_id)
    assert attempt.executor_ref is None and attempt.source_seq == -1
    admission = h.store.admission_projection(h.second.task_id, _scope())
    assert admission is not None and admission.reason == "EXECUTOR_PROJECT_BUSY"
    assert h.adapter._journal.get(h.second.attempt_id) is None
    assert h.executor.calls == 1
    assert not (h.project / "result-2.md").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("reopen", [False, True])
async def test_accepted_task_waits_through_apply_and_canonical_settlement(handoff, reopen):
    """Catches dirty-file validation running before project ownership settles."""
    h = handoff
    h.finish_body.set()
    await asyncio.wait_for(h.applied.wait(), timeout=15)
    if reopen:
        # A separate adapter must consult persisted ownership, not its empty
        # in-memory worker collection. Keep A's actual worker alive throughout.
        observer = DirectProjectCodeExecutorAdapter(
            h.resolver, h.database, durability_store=h.store, clock=h.now,
        )
        h.core.executor = observer
    assert (h.project / "result-1.md").read_text(encoding="utf-8") == "result 1\n"
    assert await h.core.drain_outbox_once(worker_id="during-apply", observed_at=h.now())
    _assert_queued_without_execution(h)

    h.finish_settlement.set()
    await _wait_direct_settled(h.adapter)
    assert h.adapter._journal.get(h.first.attempt_id).outcome is TerminalOutcome.COMPLETED
    assert h.store.get_task(h.first.task_id, _scope()).state.value == "running"
    h.store.mark_reconciliation_pending(
        h.first.task_id, h.first.attempt_id, "EXECUTOR_STATUS_QUERY", in_progress=True,
    )
    assert await h.core.drain_outbox_once(
        worker_id="before-canonical-ingestion", observed_at=h.advance()
    )
    _assert_queued_without_execution(h)
    if reopen:
        h.core.executor = h.adapter
        await observer.close()

    await h.core.reconcile_status()
    assert h.store.get_task(h.first.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
    assert await h.core.drain_outbox_once(worker_id="after-settlement", observed_at=h.advance())
    await _wait_direct_settled(h.adapter)
    await h.core.reconcile_status()
    assert h.store.get_task(h.second.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
    assert h.executor.calls == 2
    assert (h.project / "result-1.md").read_text(encoding="utf-8") == "result 1\n"
    assert (h.project / "result-2.md").read_text(encoding="utf-8") == "result 2\n"
    assert not await h.core.drain_outbox_once(worker_id="duplicate", observed_at=h.advance())
    assert h.executor.calls == 2


@pytest.mark.asyncio
async def test_queued_task_snapshots_user_edits_after_previous_settlement(handoff):
    """The queued attempt captures authorized current files only when it starts."""
    h = handoff
    h.finish_body.set()
    await asyncio.wait_for(h.applied.wait(), timeout=15)
    assert await h.core.drain_outbox_once(worker_id="wait", observed_at=h.now())
    _assert_queued_without_execution(h)
    h.finish_settlement.set()
    await _wait_direct_settled(h.adapter)
    await h.core.reconcile_status()
    (h.project / "user-notes.md").write_text("keep my notes\n", encoding="utf-8")
    assert await h.core.drain_outbox_once(worker_id="dirty", observed_at=h.advance())
    await _wait_direct_settled(h.adapter)
    await h.core.reconcile_status()
    assert h.store.get_task(h.second.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
    assert h.executor.calls == 2
    assert h.adapter._journal.get(h.second.attempt_id) is not None
    assert (h.project / "user-notes.md").read_text(encoding="utf-8") == "keep my notes\n"
    assert (h.project / "result-1.md").read_text(encoding="utf-8") == "result 1\n"
    assert (h.project / "result-2.md").read_text(encoding="utf-8") == "result 2\n"


@pytest.mark.asyncio
async def test_retained_cleanup_blocks_next_task_until_cleanup_and_store_settle(
    handoff, monkeypatch,
):
    h = handoff
    real_remove = project_code_executor._remove_attempt_worktree

    def fail_cleanup(*args):
        raise OSError("injected worktree lock")

    monkeypatch.setattr(project_code_executor, "_remove_attempt_worktree", fail_cleanup)
    h.finish_body.set()
    h.finish_settlement.set()
    await _wait_direct_settled(h.adapter)
    await h.core.reconcile_status()
    assert h.adapter.retained_cleanup_attempt_ids() == (h.first.attempt_id,)
    assert h.store.get_task(h.first.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
    assert await h.core.drain_outbox_once(worker_id="retained-cleanup", observed_at=h.now())
    _assert_queued_without_execution(h)

    monkeypatch.setattr(project_code_executor, "_remove_attempt_worktree", real_remove)
    await h.adapter.close()
    restarted = DirectProjectCodeExecutorAdapter(
        h.resolver, h.database, durability_store=h.store, clock=h.now,
    )
    h.core.executor = restarted
    try:
        await restarted.prepare_startup()
        assert await h.core.drain_outbox_once(worker_id="after-cleanup", observed_at=h.advance())
        await _wait_direct_settled(restarted)
        await h.core.reconcile_status()
        assert h.store.get_task(h.second.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
        assert h.executor.calls == 2
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_cancelling_waiting_task_never_executes_after_project_settlement(handoff):
    h = handoff
    h.finish_body.set()
    await asyncio.wait_for(h.applied.wait(), timeout=15)
    assert await h.core.drain_outbox_once(worker_id="wait", observed_at=h.now())
    _assert_queued_without_execution(h)
    cancel = _cancel(h.second.task_id)
    result = h.core.execute(cancel.envelope, cancel.authorization, now=h.now())
    assert result.ok
    assert h.store.get_task(h.second.task_id, _scope()).cancel_requested, result.to_dict()
    h.finish_settlement.set()
    await _wait_direct_settled(h.adapter)
    await h.core.reconcile_status()
    await h.core.drain_outbox_once(worker_id="cancelled", observed_at=h.advance())
    assert h.store.get_task(h.second.task_id, _scope()).outcome is TerminalOutcome.CANCELLED
    assert h.store.get_task(h.first.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
    assert h.executor.calls == 1
    assert h.adapter._journal.get(h.second.attempt_id) is None
    assert not (h.project / "result-2.md").exists()
    SqliteTaskStore(h.database)


@pytest.mark.asyncio
async def test_cancel_during_busy_delivery_settles_when_pre_effect_reply_arrives(
    handoff, monkeypatch,
):
    h = handoff
    h.finish_body.set()
    await asyncio.wait_for(h.applied.wait(), timeout=15)
    claimed, deliver = asyncio.Event(), asyncio.Event()
    real_dispatch = h.adapter.dispatch

    async def gated_dispatch(item):
        claimed.set()
        await deliver.wait()
        return await real_dispatch(item)

    monkeypatch.setattr(h.adapter, "dispatch", gated_dispatch)
    delivery = asyncio.create_task(h.core.drain_outbox_once(worker_id="in-flight", observed_at=h.now()))
    try:
        await asyncio.wait_for(claimed.wait(), timeout=5)
        cancel = _cancel(h.second.task_id)
        result = h.core.execute(cancel.envelope, cancel.authorization, now=h.now())
        assert result.ok and result.result["applied"] is False
        assert h.store.get_task(h.second.task_id, _scope()).outcome is None
    finally:
        deliver.set()
        await delivery
    assert h.store.get_task(h.second.task_id, _scope()).outcome is TerminalOutcome.CANCELLED
    SqliteTaskStore(h.database)
    replay = h.core.execute(cancel.envelope, cancel.authorization, now=h.now())
    assert replay.ok and replay.result["applied"] is True
    assert replay.result["task_id"] == h.second.task_id
    assert not await h.core.drain_outbox_once(worker_id="no-redelivery", observed_at=h.advance())
    assert h.executor.calls == 1
    assert h.adapter._journal.get(h.second.attempt_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_first", [False, True])
async def test_failed_or_cancelled_worker_retains_project_during_live_cleanup(
    handoff, monkeypatch, cancel_first,
):
    h = handoff
    cleanup_started, finish_cleanup = asyncio.Event(), asyncio.Event()
    real_cleanup = h.adapter._cleanup_attempt_resources

    async def gated_cleanup(attempt_id, cleanup):
        if attempt_id == h.first.attempt_id:
            cleanup_started.set()
            await finish_cleanup.wait()
        await real_cleanup(attempt_id, cleanup)

    monkeypatch.setattr(h.adapter, "_cleanup_attempt_resources", gated_cleanup)
    h.executor.fail_first = not cancel_first
    if cancel_first:
        h.adapter._running[h.first.attempt_id].cancel()
    else:
        h.finish_body.set()
    observer = DirectProjectCodeExecutorAdapter(
        h.resolver, h.database, durability_store=h.store, clock=h.now,
    )
    try:
        await asyncio.wait_for(cleanup_started.wait(), timeout=15)
        h.core.executor = observer
        assert await h.core.drain_outbox_once(worker_id="cleanup-live", observed_at=h.now())
        _assert_queued_without_execution(h)
    finally:
        finish_cleanup.set()
        await _wait_direct_settled(h.adapter)
        await observer.close()
        h.core.executor = h.adapter
    await h.core.reconcile_status()
    assert await h.core.drain_outbox_once(worker_id="cleanup-finished", observed_at=h.advance())
    await _wait_direct_settled(h.adapter)
    await h.core.reconcile_status()
    assert h.store.get_task(h.second.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
    assert h.executor.calls == 2
