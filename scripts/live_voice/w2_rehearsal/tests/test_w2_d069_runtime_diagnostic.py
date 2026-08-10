from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm
from jiuwenswarm.server.runtime.agent_adapter.interface_code import (
    JiuwenSwarmCodeAdapter,
)

from w2_d069_runtime_diagnostic import (
    _P3_CANCEL_ENTRY_DELTA,
    _P3_FROZEN_ENTRY_COUNTS,
    _P3NonterminalBarrier,
    _assert_p3_probe_closed_state,
    _assert_zero_effect,
    _exercise_p2_non_retriable_ack,
    _exercise_p3_non_retriable_issue,
    _pause_p3_periodic_reconciliation,
    _read_sqlite_dump,
    _resume_p3_periodic_reconciliation,
    _wait_quiescent_snapshot,
)


def _closed_p3_probe_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[object, object, Path, dict[str, object]]:
    from jiuwenswarm.server.live_voice import project_code_executor

    database = tmp_path / "closed.sqlite3"
    attempt_ids = ("attempt-a", "attempt-b")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE attempts("
            "attempt_id TEXT, task_id TEXT, attempt_number INTEGER, "
            "state TEXT, outcome TEXT)"
        )
        connection.executemany(
            "INSERT INTO attempts VALUES(?, 'task-1', ?, 'terminal', 'cancelled')",
            ((attempt_id, number) for number, attempt_id in enumerate(attempt_ids, 1)),
        )
        connection.execute(
            "CREATE TABLE outbox("
            "outbox_id TEXT, task_id TEXT, kind TEXT, state TEXT, "
            "claimed_by TEXT, claimed_at TEXT, claim_token TEXT, "
            "last_error TEXT, created_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO outbox VALUES(?, 'task-1', ?, 'delivered', "
            "NULL, NULL, NULL, NULL, ?)",
            (
                ("outbox-1", "attempt.dispatch", "1"),
                ("outbox-2", "attempt.cancel", "2"),
                ("outbox-3", "attempt.dispatch", "3"),
                ("outbox-4", "attempt.cancel", "4"),
            ),
        )
        connection.execute(
            "CREATE TABLE commands("
            "command_id TEXT, command_type TEXT, created_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO commands VALUES(?, ?, ?)",
            (
                ("command-1", "task.create", "1"),
                ("command-2", "task.cancel", "2"),
                ("command-3", "task.retry", "3"),
                ("command-4", "task.cancel", "4"),
            ),
        )

    def value(name: str) -> SimpleNamespace:
        return SimpleNamespace(value=name)

    task = SimpleNamespace(
        state=value("terminal"),
        outcome=value("cancelled"),
        attempt_id=attempt_ids[1],
    )
    records = {
        attempt_id: SimpleNamespace(
            attempt_id=attempt_id,
            state=value("terminal"),
            outcome=value("cancelled"),
            raw_status="cancelled",
            cancel_requested=True,
            owner_id=None,
            lease_expires_at=None,
            project_root=str(tmp_path),
            before_head="head-1",
            before_tree="tree-1",
        )
        for attempt_id in attempt_ids
    }
    journal = SimpleNamespace(all_attempts=lambda: tuple(records.values()))
    executor = SimpleNamespace(
        _journal=journal,
        has_live_workers=False,
        _running=set(),
        _applying=set(),
        _interruptions=set(),
        retained_cleanup_attempt_ids=lambda: (),
    )
    store = SimpleNamespace(get_task=lambda _task_id, _scope: task)
    composition = SimpleNamespace(_core=SimpleNamespace(store=store, executor=executor))
    server = SimpleNamespace(
        _live_voice_w2_observability=None,
        _agent_manager=SimpleNamespace(agents={}, _agent_pins={}),
    )
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_ENABLED", raising=False)
    monkeypatch.setattr(
        project_code_executor,
        "_attempt_worktree_paths",
        lambda _root, attempt_id: (
            tmp_path / f"parent-{attempt_id}",
            tmp_path / f"checkout-{attempt_id}",
        ),
    )
    monkeypatch.setattr(project_code_executor, "_git_head", lambda _root: "head-1")
    monkeypatch.setattr(
        project_code_executor,
        "_project_tree_fingerprint",
        lambda _root: "tree-1",
    )
    return server, composition, database, {
        "task": task,
        "records": records,
        "attempt_ids": attempt_ids,
    }


def test_p3_closed_state_oracle_rejects_wrong_successor_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, composition, database, fixture = _closed_p3_probe_fixture(
        tmp_path, monkeypatch
    )
    fixture["task"].outcome = SimpleNamespace(value="completed")

    with pytest.raises(RuntimeError, match="cancelled successor"):
        _assert_p3_probe_closed_state(
            server,
            composition,
            object(),
            database,
            "task-1",
            fixture["attempt_ids"],
        )


def test_p3_closed_state_oracle_rejects_residual_outbox_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, composition, database, fixture = _closed_p3_probe_fixture(
        tmp_path, monkeypatch
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE outbox SET claimed_by='worker-1', claim_token='claim-1' "
            "WHERE outbox_id='outbox-4'"
        )

    with pytest.raises(RuntimeError, match="incomplete or claimed outbox"):
        _assert_p3_probe_closed_state(
            server,
            composition,
            object(),
            database,
            "task-1",
            fixture["attempt_ids"],
        )


@pytest.mark.parametrize("field", ["owner_id", "lease_expires_at"])
def test_p3_closed_state_oracle_rejects_residual_executor_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    server, composition, database, fixture = _closed_p3_probe_fixture(
        tmp_path, monkeypatch
    )
    setattr(fixture["records"]["attempt-b"], field, "residual")

    with pytest.raises(RuntimeError, match="nonterminal Executor ownership"):
        _assert_p3_probe_closed_state(
            server,
            composition,
            object(),
            database,
            "task-1",
            fixture["attempt_ids"],
        )


class _AbilityManager:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1


class _RoutingCodeAdapter(JiuwenSwarmCodeAdapter):
    async def create_instance(self, config=None, *, mode="code", sub_mode=None) -> None:
        self._session_instance_config = dict(config or {})
        self._session_instance_mode = mode
        self._session_instance_sub_mode = sub_mode
        self._project_dir = self._session_instance_config["project_dir"]
        self._instance = SimpleNamespace(ability_manager=_AbilityManager())

    async def _start_interaction(self, *, session_id, strict):
        del session_id, strict

    async def cleanup(self) -> None:
        self._instance = None


class _P3Executor:
    def __init__(self, agent: object, root: str) -> None:
        @dataclass(frozen=True)
        class Lease:
            project_executor: object
            effective_execution_root: str
            context_release: object
            initialization_error: object

        @dataclass(frozen=True)
        class Binding:
            attempt_executor_factory: object

        async def acquire(_root):
            return Lease(
                project_executor=agent,
                effective_execution_root=root,
                context_release=lambda: None,
                initialization_error=None,
            )

        async def resolve(_spec, *, for_dispatch):
            del for_dispatch
            return Binding(attempt_executor_factory=acquire)

        self._resolver = SimpleNamespace(resolve=resolve)

    async def dispatch(self, item):
        return item

    async def cancel(self, item):
        return item

    def retry_readiness(self, task, attempt):
        return task, attempt


@pytest.mark.asyncio
async def test_p3_barrier_observes_real_session_child_tool_entry(
    tmp_path: Path,
) -> None:
    root = _RoutingCodeAdapter()
    await root.create_instance({"project_dir": str(tmp_path)}, mode="code")
    agent = object.__new__(JiuWenSwarm)
    agent._adapter = root
    agent._build_inputs = lambda _request: ({}, "", "")
    executor = _P3Executor(agent, str(tmp_path))
    core = SimpleNamespace(executor=executor)
    barrier = _P3NonterminalBarrier(core)
    barrier.install()
    session_id = "formal-task-attempt-1"
    worker: asyncio.Task[object] | None = None
    try:
        await core.executor.dispatch("dispatch")
        binding = await executor._resolver.resolve(None, for_dispatch=True)
        lease = await binding.attempt_executor_factory(str(tmp_path))
        request = AgentRequest(
            request_id="request-1",
            channel_id="formal-task-core",
            session_id=session_id,
            params={"query": "wait", "project_dir": str(tmp_path)},
            is_stream=True,
        )
        worker = asyncio.create_task(
            anext(lease.project_executor.process_background_code_task_stream(request))
        )
        await barrier.wait_frozen(timeout=1)

        child = root._get_cached_session_adapter(session_id)
        assert child is not None and child is not root
        assert barrier.snapshot() == _P3_FROZEN_ENTRY_COUNTS
        root_manager = root._instance.ability_manager
        child_manager = child._instance.ability_manager
        assert root_manager.calls == child_manager.calls == 0
        await child_manager.execute()
        assert barrier.snapshot()["tool"] == child_manager.calls == 1
        assert root_manager.calls == 0
        before_rejection = barrier.snapshot()
        _assert_zero_effect(
            before_rejection, barrier.snapshot(), label="rejected retry"
        )

        await core.executor.cancel("cancel")
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
        await barrier.wait_agent_stopped(timeout=1)
        assert barrier.delta(before_rejection) == _P3_CANCEL_ENTRY_DELTA
        assert core.executor.retry_readiness("task", "attempt") == (
            "task",
            "attempt",
        )
        assert barrier.snapshot()["retry_readiness"] == 1
    finally:
        if worker is not None and not worker.done():
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker
        barrier.restore()
        await root.cleanup_session_adapter(session_id)


class _Registry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.cursor: int | None = None
        self.receipts: dict[str, dict[str, object]] = {}

    async def handle_p2_presentation_ack(self, *, params, request_id, session_id):
        del session_id
        self.calls.append((request_id, dict(params)))
        if params["contiguous_cursor"] == (1 << 53) - 1:
            payload = self.receipts.setdefault(
                request_id,
                {
                    "error": {
                        "code": "PROTOCOL_VIOLATION",
                        "reason": "ACK_BEYOND_PRODUCED_CURSOR",
                    }
                },
            )
            return SimpleNamespace(ok=False, payload=payload)
        self.cursor = params["contiguous_cursor"]
        return SimpleNamespace(ok=True, payload={"result": {"accepted": True}})


@pytest.mark.asyncio
async def test_p2_probe_replays_semantic_error_then_uses_a_new_legal_ack() -> None:
    registry = _Registry()
    result = await _exercise_p2_non_retriable_ack(
        registry,
        base={"session_id": "session-1", "interaction_id": "interaction-1"},
        response={"response_id": "response-1", "response_generation": 2},
        presentation={"surface": "text", "unit_id": "unit-1", "seq": 0},
        suffix="fixed",
        business_snapshot=lambda: registry.cursor,
        error_receipt_snapshot=lambda: tuple(registry.receipts),
    )

    assert result["reason"] == "ACK_BEYOND_PRODUCED_CURSOR"
    assert registry.calls[0] == registry.calls[1]
    assert registry.calls[0][1]["contiguous_cursor"] == (1 << 53) - 1
    assert registry.calls[2][0] == "w2-p2-fault-probe-recovery-fixed"
    assert registry.calls[2][1]["contiguous_cursor"] == registry.cursor == 0


class _P3Registry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.receipts: dict[str, dict[str, object]] = {}
        self.business_state = ("running", "attempt-1")

    async def handle_p3_confirmation_issue(self, *, params, request_id, session_id):
        self.calls.append((request_id, session_id, dict(params)))
        payload = {
            "request_id": request_id,
            "ok": False,
            "result": None,
            "error": {
                "code": "CONFLICT",
                "reason": "TASK_RETRY_REQUIRES_TERMINAL",
            },
        }
        return SimpleNamespace(ok=False, payload=payload)


@pytest.mark.asyncio
async def test_p3_probe_repeats_preflight_error_without_reserving_receipt() -> None:
    registry = _P3Registry()
    params = {
        "session_id": "session-1",
        "operation": "task.retry",
        "command_id": "command-1",
        "task_id": "task-1",
    }

    result = await _exercise_p3_non_retriable_issue(
        registry,
        params=params,
        request_id="issue:command-1",
        session_id="session-1",
        business_snapshot=lambda: registry.business_state,
        issue_ledger_snapshot=lambda: tuple(registry.receipts),
    )

    assert result == {
        "code": "CONFLICT",
        "reason": "TASK_RETRY_REQUIRES_TERMINAL",
        "repeat_stable": True,
    }
    assert registry.receipts == {}
    assert registry.calls[0] == registry.calls[1]


@pytest.mark.asyncio
async def test_p3_probe_waits_for_preexisting_async_tail_before_baseline() -> None:
    observed = iter(
        [
            ("running", 1),
            ("running", 2),
            ("running", 2),
            ("running", 2),
        ]
    )

    settled = await _wait_quiescent_snapshot(
        lambda: next(observed),
        timeout=1,
        interval=0,
        confirmations=3,
    )

    assert settled == ("running", 2)


def test_p3_probe_pauses_only_periodic_reconciliation_until_rejection_is_checked() -> (
    None
):
    composition = SimpleNamespace(
        _reconcile_interval=0.2,
        _wake=asyncio.Event(),
    )

    interval = _pause_p3_periodic_reconciliation(composition)

    assert interval == 0.2
    assert composition._reconcile_interval == 3600.0
    assert composition._wake.is_set()

    _resume_p3_periodic_reconciliation(composition, interval)
    assert composition._reconcile_interval == 0.2


def test_sqlite_oracle_excludes_only_separate_journal_and_detects_claim(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE direct(lease_expires_at TEXT)")
        connection.execute("INSERT INTO direct VALUES('t1')")
        connection.execute("CREATE TABLE state(claim TEXT, lease_expires_at TEXT)")
        connection.execute("INSERT INTO state VALUES(NULL, 'stable')")
    before = _read_sqlite_dump(database, excluded_tables=frozenset({"direct"}))
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE direct SET lease_expires_at='t2'")
    _assert_zero_effect(
        before,
        _read_sqlite_dump(database, excluded_tables=frozenset({"direct"})),
        label="heartbeat",
    )
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE state SET claim='claimed'")
    with pytest.raises(RuntimeError, match="forbidden side effect"):
        _assert_zero_effect(
            before,
            _read_sqlite_dump(database, excluded_tables=frozenset({"direct"})),
            label="claim",
        )
