"""R5: actual local file operations through isolated Direct D2 execution.

The deterministic carrier replaces model generation only. Git, FsOperation,
Task authority, SQLite admission/effects, apply, and restart are real.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openjiuwen.core.sys_operation.base import OperationMode
from openjiuwen.core.sys_operation.config import LocalWorkConfig
from openjiuwen.core.sys_operation.cwd import init_cwd
from openjiuwen.core.sys_operation.local.fs_operation import FsOperation

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import TerminalOutcome
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    AuthenticatedPrincipal,
    ServerSessionProjectAuthorityResolver,
)
from jiuwenswarm.server.runtime.formal_tasks.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.runtime.formal_tasks import project_code_executor
from jiuwenswarm.server.runtime.formal_tasks.project_code_executor import DirectProjectCodeExecutorAdapter
from jiuwenswarm.server.runtime.formal_tasks.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_p3_4_durability_runtime import _create_selected_task
from tests.unit_tests.live_voice.test_persistent_task_core import EXPIRY, NOW, _scope
from tests.unit_tests.live_voice.test_project_code_executor import (
    _direct_binding,
    _git,
    _git_project,
    _wait_direct_settled,
)


def _mixed_project(project: Path) -> bytes:
    _git_project(project, ignore="cache/\n")
    for relative in ("staged-deleted.md", "working-deleted.md"):
        (project / relative).write_text("old input\n", encoding="utf-8")
    _git(project, "add", "staged-deleted.md", "working-deleted.md")
    _git(project, "commit", "-m", "deletion inputs")
    _git(project, "rm", "staged-deleted.md")
    (project / "working-deleted.md").unlink()
    (project / "README.md").write_text("staged input\n", encoding="utf-8")
    (project / "staged.md").write_text("staged new input\n", encoding="utf-8")
    _git(project, "add", "README.md", "staged.md")
    (project / "README.md").write_text("working input\n", encoding="utf-8")
    (project / "a.md").write_text("Paris original itinerary\n", encoding="utf-8")
    return (project / ".git" / "index").read_bytes()


class _FileToolCarrier:
    def __init__(self):
        self.calls = 0
        self.written = asyncio.Event()
        self.release = asyncio.Event()
        self.seen: list[dict[str, str]] = []

    async def process_background_code_task_stream(self, request):
        self.calls += 1
        target = Path(request.params["project_dir"])
        assert not (target / "staged-deleted.md").exists()
        assert not (target / "working-deleted.md").exists()
        init_cwd(str(target), str(target), workspace=str(target))
        fs = FsOperation(
            "fs", OperationMode.LOCAL, "R5 fixture file tools",
            LocalWorkConfig(sandbox_root=[str(target)], restrict_to_sandbox=True),
        )
        inputs = {}
        for relative in ("README.md", "staged.md", "a.md"):
            result = await fs.read_file(relative)
            assert result.data is not None, result
            inputs[relative] = result.data.content
        if self.calls > 1:
            result = await fs.read_file("b.md")
            assert result.data is not None, result
            inputs["b.md"] = result.data.content
        self.seen.append(inputs)
        relative = "b.md" if self.calls == 1 else "aa.md"
        result = await fs.write_file(relative, inputs["a.md"] + "Afternoon free\n", prepend_newline=False)
        assert result.data is not None, result
        # Two writes make a conflict prove zero partial publication, not just
        # refusal to overwrite the one conflicting path.
        result = await fs.write_file(f"receipt-{self.calls}.md", inputs["README.md"], prepend_newline=False)
        assert result.data is not None, result
        self.written.set()
        await self.release.wait()
        yield AgentResponseChunk(
            request.request_id, request.channel_id,
            payload={"event_type": "chat.final", "content": relative},
            is_complete=True,
        )


def _harness(tmp_path, monkeypatch):
    monkeypatch.setattr("jiuwenswarm.server.runtime.formal_tasks.task_store.utc_now", lambda: NOW)
    project = tmp_path / "project"
    index = _mixed_project(project)
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    carrier = _FileToolCarrier()
    authority = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _: {"project_id": "project-1", "project_dir": str(project)},
        project_reader=lambda identity: SimpleNamespace(
            project_id=identity, project_dir=str(project), hidden=False, work_mode="code",
        ),
        # The canonical fixture's Context uses this revision. Direct separately
        # captures/checks the real Git HEAD at dispatch, seed, and apply.
        revision_reader=lambda root: (root, "a77516a0"),
    )
    principal = AuthenticatedPrincipal(
        principal_id="user-1", allowed_project_ids=frozenset({"project-1"}),
        allowed_operations=frozenset({"task.create"}), expires_at=EXPIRY,
    )

    class Resolver:
        async def resolve(self, spec, *, for_dispatch):
            authority.revalidate(spec.context, principal=principal, now=NOW, for_dispatch=for_dispatch)
            return _direct_binding(project, carrier)

    resolver = Resolver()
    adapter = DirectProjectCodeExecutorAdapter(resolver, store.database_path, durability_store=store, clock=lambda: NOW)
    core = PersistentTaskCore(store, adapter)
    return SimpleNamespace(
        project=project, index=index, carrier=carrier, resolver=resolver,
        store=store, adapter=adapter, core=core, database=tmp_path / "tasks.sqlite3",
    )


def _assert_inputs_preserved(h):
    actual_index = (h.project / ".git" / "index").read_bytes()
    assert actual_index == h.index
    assert (h.project / "a.md").read_text(encoding="utf-8") == "Paris original itinerary\n"
    assert (h.project / "staged.md").read_text(encoding="utf-8") == "staged new input\n"
    assert not (h.project / "staged-deleted.md").exists()
    assert not (h.project / "working-deleted.md").exists()
    (h.project.parent / "snapshot-evidence.json").write_text(json.dumps({
        "project": str(h.project),
        "expected_index_sha256": hashlib.sha256(h.index).hexdigest(),
        "actual_index_sha256": hashlib.sha256(actual_index).hexdigest(),
        "original_a": (h.project / "a.md").read_text(encoding="utf-8"),
        "outputs": sorted(path.name for path in h.project.glob("*.md")),
        "carrier_calls": h.carrier.calls,
    }, indent=2), encoding="utf-8")


@pytest.mark.asyncio
async def test_mixed_snapshot_new_file_then_save_as_survives_restart(tmp_path, monkeypatch):
    h = _harness(tmp_path, monkeypatch)
    h.carrier.release.set()
    _, first = _create_selected_task(h.store, h.core, h.project, h.adapter, identity_suffix="-b")
    try:
        assert await h.core.drain_outbox_once(worker_id="first", observed_at=NOW)
        await _wait_direct_settled(h.adapter)
        await h.core.reconcile_status()
        assert h.store.get_task(first.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
        _assert_inputs_preserved(h)
    finally:
        await h.adapter.close()
    restarted = DirectProjectCodeExecutorAdapter(
        h.resolver, h.database, durability_store=h.store, clock=lambda: NOW,
    )
    core = PersistentTaskCore(h.store, restarted)
    try:
        await restarted.prepare_startup()
        await core.reconcile_status()
        assert h.carrier.calls == 1  # completed external effects are not replayed
        _, second = _create_selected_task(h.store, core, h.project, restarted, identity_suffix="-aa")
        assert await core.drain_outbox_once(worker_id="second", observed_at=NOW)
        await _wait_direct_settled(restarted)
        await core.reconcile_status()
        assert h.store.get_task(second.task_id, _scope()).outcome is TerminalOutcome.COMPLETED
        assert h.carrier.calls == 2
        assert h.carrier.seen[0]["README.md"] == "working input\n"
        assert h.carrier.seen[1]["b.md"] == "Paris original itinerary\nAfternoon free\n"
        assert (h.project / "aa.md").read_text(encoding="utf-8") == h.carrier.seen[1]["b.md"]
        _assert_inputs_preserved(h)
    finally:
        await restarted.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["read_dependency", "write_collision", "other_visible", "ignored_cache"])
async def test_changes_during_attempt_conflict_before_any_writeback(tmp_path, monkeypatch, change):
    h = _harness(tmp_path, monkeypatch)
    _, task = _create_selected_task(h.store, h.core, h.project, h.adapter)
    try:
        assert await h.core.drain_outbox_once(worker_id="start", observed_at=NOW)
        await asyncio.wait_for(h.carrier.written.wait(), timeout=15)
        relative = {
            "read_dependency": "README.md", "write_collision": "b.md",
            "other_visible": "notes.md", "ignored_cache": "cache/build.txt",
        }[change]
        target = h.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("new user content\n", encoding="utf-8")
        h.carrier.release.set()
        await _wait_direct_settled(h.adapter)
        await h.core.reconcile_status()
        expected = TerminalOutcome.COMPLETED if change == "ignored_cache" else TerminalOutcome.FAILED
        assert h.store.get_task(task.task_id, _scope()).outcome is expected
        assert target.read_text(encoding="utf-8") == "new user content\n"
        if change != "ignored_cache":
            assert h.adapter._journal.get(task.attempt_id).error == "EXECUTION_TARGET_CHANGED_DURING_ATTEMPT"
            assert not (h.project / "receipt-1.md").exists()
            if change != "write_collision":
                assert not (h.project / "b.md").exists()
        _assert_inputs_preserved(h)
    finally:
        h.carrier.release.set()
        await h.adapter.close()


@pytest.mark.asyncio
async def test_output_collision_after_apply_check_has_no_partial_write(tmp_path, monkeypatch):
    h = _harness(tmp_path, monkeypatch)
    h.carrier.release.set()
    real_git = project_code_executor._git_run_with_input

    def collide(root, arguments, payload):
        real_git(root, arguments, payload)
        if root == h.project and arguments == ("apply", "--check", "--binary", "-"):
            (root / "b.md").write_text("user wins\n", encoding="utf-8")

    monkeypatch.setattr(project_code_executor, "_git_run_with_input", collide)
    _, task = _create_selected_task(h.store, h.core, h.project, h.adapter)
    try:
        assert await h.core.drain_outbox_once(worker_id="start", observed_at=NOW)
        await _wait_direct_settled(h.adapter)
        await h.core.reconcile_status()
        # Dispatch was durably recorded, so a failed call has unknown ACK until
        # D2 reconciliation. It never claims completion or replays the carrier.
        assert h.store.get_task(task.task_id, _scope()).outcome is TerminalOutcome.INTERRUPTED
        assert (h.project / "b.md").read_text(encoding="utf-8") == "user wins\n"
        assert not (h.project / "receipt-1.md").exists()
        assert h.carrier.calls == 1
        _assert_inputs_preserved(h)
    finally:
        await h.adapter.close()


@pytest.mark.asyncio
async def test_mixed_snapshot_applied_effect_recovers_without_replaying_file_tools(tmp_path, monkeypatch):
    h = _harness(tmp_path, monkeypatch)
    h.carrier.release.set()
    real_append = h.store.append_durability_effect_fact
    real_apply = project_code_executor._apply_attempt_patch
    apply_calls = []

    def count_apply(*args, **kwargs):
        apply_calls.append(1)
        return real_apply(*args, **kwargs)

    def lose_receipt(fact, *, row_sequence, observed_at, **kwargs):
        if row_sequence == 3:
            raise RuntimeError("fixture crash after apply before Store ACK")
        return real_append(fact, row_sequence=row_sequence, observed_at=observed_at, **kwargs)

    monkeypatch.setattr(project_code_executor, "_apply_attempt_patch", count_apply)
    monkeypatch.setattr(h.store, "append_durability_effect_fact", lose_receipt)
    _, task = _create_selected_task(h.store, h.core, h.project, h.adapter)
    try:
        assert await h.core.drain_outbox_once(worker_id="start", observed_at=NOW)
        await _wait_direct_settled(h.adapter)
        assert apply_calls == [1]
        assert (h.project / "b.md").exists()
        _assert_inputs_preserved(h)
    finally:
        monkeypatch.setattr(h.store, "append_durability_effect_fact", real_append)
        await h.adapter.close()

    store = SqliteTaskStore(h.database)
    restarted = DirectProjectCodeExecutorAdapter(h.resolver, h.database, durability_store=store)
    core = PersistentTaskCore(store, restarted)
    try:
        await core.reconcile_status()
        assert store.get_task(task.task_id, _scope()).outcome is TerminalOutcome.INTERRUPTED
        assert await restarted.reconcile_durable_effects(
            scope=_scope(), task_id=task.task_id, origin_attempt_id=task.attempt_id,
            observed_at="2026-08-05T12:05:00Z",
        ) == "applied"
        linked = await core.recover_durable_attempt(
            scope=_scope(), task_id=task.task_id, operator_id="fixture-recovery",
            observed_at="2026-08-05T12:06:00Z",
        )
        assert await core.drain_outbox_once(worker_id="recovery", observed_at="2026-08-05T12:06:01Z")
        completed = store.get_task(task.task_id, _scope())
        assert completed.outcome is TerminalOutcome.COMPLETED
        assert completed.attempt_id == linked.attempt_id
        assert h.carrier.calls == 1 and apply_calls == [1]
        _assert_inputs_preserved(h)
    finally:
        await restarted.close()
