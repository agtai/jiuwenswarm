"""Task changes cross the cutoff without changing old results or replaying work."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import asyncio
import json
import threading

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import TerminalOutcome
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation, TaskMutationPrecondition, TaskResultArtifact
import hashlib
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_persistent_task_core import (
    NOW, _adjust, _create, _Executor, _observations, _scope, _successor_fixture,
)


def _completed(tmp_path):
    return _successor_fixture(tmp_path, "changes.sqlite3", outcome=TerminalOutcome.COMPLETED)


def test_completed_change_is_durable_and_successor_replay_is_exactly_once(tmp_path):
    database, store, executor, core, original, _, _ = _completed(tmp_path)
    before = store.events(original.task_id, _scope())
    command, grant = _adjust(original.task_id, "第一晚牛肉火锅，第二晚烧烤；保留原有景点。")
    receipt = core.execute(command, grant, now=NOW)
    assert receipt.ok and receipt.result["adjustment_state"] == "pending"
    assert receipt.result["execution_mode"] == "followup"
    assert store.events(original.task_id, _scope()) == before

    reopened = SqliteTaskStore(database)
    core = PersistentTaskCore(reopened, executor)
    assert core.execute(command, grant, now=NOW) == receipt
    with ThreadPoolExecutor(max_workers=2) as pool:
        advances = list(pool.map(lambda _: reopened.adjustment_queue.advance(policy=core._admission_policy), range(2)))
    assert advances.count(True) == 1
    facts = reopened.adjustment_queue.facts(original.task_id, _scope())["followup_adjustment"]
    child = reopened.get_task(facts["continuation_task_id"], _scope())
    assert child.predecessor_task_id == original.task_id and child.revision_number == 2
    assert command.payload["adjustment"] in child.spec.instruction
    assert "changes-result.txt" in child.spec.instruction
    assert original.spec.instruction in child.spec.instruction
    assert child.spec.context == original.spec.context
    assert facts["adjustment_state"] == "pending", "queued successor is not a saved change"
    assert reopened.events(original.task_id, _scope()) == before

    dispatch = reopened.claim_outbox("followup")
    assert dispatch.task_id == child.task_id
    reopened.complete_outbox(dispatch, executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch, outcome=TerminalOutcome.COMPLETED,
                                   result_text="第一晚牛肉火锅；第二晚烧烤。",
                                   result_artifacts=(TaskResultArtifact("changed.txt", hashlib.sha256(b"changed").hexdigest()),)))
    assert reopened.adjustment_queue.advance(policy=core._admission_policy)
    assert core.execute(command, grant, now=NOW).result["adjustment_state"] == "applied"
    assert not reopened.adjustment_queue.advance(policy=core._admission_policy)
    assert reopened.get_task(original.task_id, _scope()) == original


@pytest.mark.parametrize("fast_executor", [False, True])
def test_cutoff_and_adjustment_admission_share_one_transaction(tmp_path, fast_executor):
    store = SqliteTaskStore(tmp_path / "cutoff.sqlite3")
    executor = _Executor(); core = PersistentTaskCore(store, executor)
    request = _create(tmp_path)
    created = core.execute(request.envelope, request.authorization, context=request.context, now=NOW)
    dispatch = store.claim_outbox("initial")
    if fast_executor:
        # A fast executor may finish generation before its dispatch receipt has
        # projected RUNNING. It can close its exact checkpoint without failing.
        assert store.adjustment_queue.try_close(created.result["task_id"], dispatch.attempt_id, _scope())
    observations = _observations(dispatch, outcome=TerminalOutcome.COMPLETED, result_text="original",
                                result_artifacts=(TaskResultArtifact("original.txt", hashlib.sha256(b"original").hexdigest()),))
    store.complete_outbox(dispatch, executor_ref=f"legacy:{dispatch.attempt_id}", observations=observations[:2])
    task_id = created.result["task_id"]
    assert store.adjustment_queue.try_close(task_id, dispatch.attempt_id, _scope())
    command, grant = _adjust(task_id, "Keep all dates; add dinner.")
    assert core.execute(command, grant, now=NOW).result["execution_mode"] == "followup"
    assert not store.has_pending_adjustments(task_id, dispatch.attempt_id, _scope())
    assert not store.adjustment_queue.advance(policy=core._admission_policy), "must await saved original"
    store.apply_observations((observations[-1],))
    assert store.adjustment_queue.advance(policy=core._admission_policy)


@pytest.mark.parametrize("outcome", [TerminalOutcome.FAILED, TerminalOutcome.CANCELLED, TerminalOutcome.INTERRUPTED])
def test_non_completed_task_cannot_schedule_a_revision(tmp_path, outcome):
    _, store, _, core, task, _, _ = _successor_fixture(tmp_path, "negative.sqlite3", outcome=outcome)
    before = store.counts()
    command, grant = _adjust(task.task_id, "Change the saved result.")
    assert not core.execute(command, grant, now=NOW).ok
    assert store.counts()["tasks"] == before["tasks"]
    assert not store.adjustment_queue.advance(policy=core._admission_policy)


def test_deferred_change_rejects_changed_replay_and_wrong_scope(tmp_path):
    _, store, _, core, task, _, _ = _completed(tmp_path)
    command, grant = _adjust(task.task_id, "Add dinner.")
    assert core.execute(command, grant, now=NOW).ok
    altered, _ = _adjust(task.task_id, "Delete everything.")
    rejected = core.execute(altered, grant, now=NOW)
    assert not rejected.ok and rejected.error.reason == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(FormalTaskViolation):
        store.adjustment_queue.facts(task.task_id, replace(_scope(), session_id="another-session"))
    stale = TaskMutationPrecondition(task.task_id, "other-attempt", task.event_head)
    next_command, next_grant = _adjust(task.task_id, "Add breakfast.", command_id="new-change")
    assert not core.execute(next_command, next_grant, mutation_precondition=stale, now=NOW).ok


def test_unrelated_successor_is_never_modified_or_followed(tmp_path):
    from tests.unit_tests.live_voice.test_persistent_task_core import _successor_command
    _, store, _, core, original, terminal, digest = _completed(tmp_path)
    command, grant = _adjust(original.task_id, "Add dinner")
    assert core.execute(command, grant, now=NOW).ok
    manual, authorization = _successor_command(original, terminal, result_sha256=digest)
    created = core.execute(manual, authorization, context=original.spec.context, now=NOW)
    assert created.ok
    before = store.counts()
    assert store.adjustment_queue.advance(policy=core._admission_policy)
    assert store.counts() == before, "no new Task, outbox, event or file operation"
    replay = core.execute(command, grant, now=NOW)
    assert not replay.ok and replay.error.reason == "TASK_ADJUSTMENT_FOLLOWUP_CONFLICT"


def test_queue_full_rejects_new_change_but_preserves_replay_and_original(tmp_path):
    _, store, _, core, original, _, _ = _completed(tmp_path)
    for index in range(64):
        command, grant = _adjust(original.task_id, f"Change {index}", command_id=f"change-{index}")
        assert core.execute(command, grant, now=NOW).ok
    before = store.counts()
    extra, extra_grant = _adjust(original.task_id, "Overflow", command_id="overflow")
    assert core.execute(extra, extra_grant, now=NOW).error.reason == "TASK_ADJUSTMENT_QUEUE_FULL"
    assert core.execute(command, grant, now=NOW).ok
    assert store.counts() == before and store.get_task(original.task_id, _scope()) == original
    # Free one execution slot, then accept another request. The old unspoken
    # outcome must survive the 64-row status window and remain acknowledgeable.
    assert store.adjustment_queue.advance(policy=core._admission_policy)
    _finish_child(store)
    assert store.adjustment_queue.advance(policy=core._admission_policy)
    assert core.execute(extra, extra_grant, now=NOW).ok
    from jiuwenswarm.server.live_voice.task_control_presentation import native_task_presentation
    _, events = native_task_presentation(store, _scope(), [original.task_id])
    assert len(events) == 1 and events[0]["adjustment_id"] == "change-0"
    _, already_heard = native_task_presentation(store, _scope(), [original.task_id], presented=lambda *_: True)
    assert already_heard == []


def _finish_child(store, *, outcome=TerminalOutcome.COMPLETED):
    item = store.claim_outbox("followup")
    artifacts = (TaskResultArtifact("changed.txt", hashlib.sha256(b"changed").hexdigest()),) if outcome is TerminalOutcome.COMPLETED else ()
    store.complete_outbox(item, executor_ref=f"legacy:{item.attempt_id}", observations=_observations(
        item, outcome=outcome, result_text="saved revision" if artifacts else None, result_artifacts=artifacts))
    return store.get_task(item.task_id, _scope())


@pytest.mark.parametrize("outcome", [TerminalOutcome.COMPLETED, TerminalOutcome.FAILED, TerminalOutcome.CANCELLED, TerminalOutcome.INTERRUPTED])
def test_changes_are_serial_and_failure_never_becomes_saved_success(tmp_path, outcome):
    _, store, _, core, original, _, _ = _completed(tmp_path)
    for index in range(2):
        cmd, grant = _adjust(original.task_id, f"Change {index}", command_id=f"change-{index}")
        assert core.execute(cmd, grant, now=NOW).ok
    queue = store.adjustment_queue
    assert queue.advance(policy=core._admission_policy)
    assert not queue.advance(policy=core._admission_policy)
    assert store.counts()["tasks"] == 2
    first = _finish_child(store, outcome=outcome)
    assert queue.advance(policy=core._admission_policy)
    assert queue.advance(policy=core._admission_policy)
    facts = queue.facts(original.task_id, _scope())["followup_adjustments"]
    if outcome is TerminalOutcome.COMPLETED:
        assert [item["adjustment_state"] for item in facts] == ["applied", "pending"]
        child = store.get_task(facts[1]["continuation_task_id"], _scope())
        assert child.predecessor_task_id == first.task_id
        assert child.spec.instruction.count("original_requirements") == 1, "no recursive instruction growth"
        assert "saved revision" in child.spec.instruction and "Change 1" in child.spec.instruction
    else:
        assert all(item["adjustment_state"] == "rejected" for item in facts)
        if outcome is TerminalOutcome.INTERRUPTED:
            assert facts[0]["reason"] == "TASK_ADJUSTMENT_FOLLOWUP_UNKNOWN"
        assert store.counts()["tasks"] == 2
        assert store.claim_outbox("forbidden") is None
    assert store.get_task(original.task_id, _scope()) == original


def test_followup_transaction_rollback_recovery_and_corrupt_binding(tmp_path, monkeypatch):
    database, store, _, core, original, _, _ = _completed(tmp_path)
    command, grant = _adjust(original.task_id, "Add dinner")
    core.execute(command, grant, now=NOW)
    queue = store.adjustment_queue
    def fault(*args, **kwargs):
        raise RuntimeError("injected after successor creation, before queue commit")
    monkeypatch.setattr(queue, "_settle", fault)
    before = store.counts()
    with pytest.raises(RuntimeError):
        queue.advance(policy=core._admission_policy)
    assert store.counts() == before
    reopened = SqliteTaskStore(database)
    assert reopened.adjustment_queue.advance(policy=core._admission_policy)
    assert reopened.counts()["tasks"] == 2
    with reopened._transaction() as c:
        c.execute("UPDATE task_adjustment_queue_v1 SET successor_id=?", (original.task_id,))
    with pytest.raises(FormalTaskViolation, match="receipt binding"):
        reopened.adjustment_queue.advance(policy=core._admission_policy)
    assert reopened.counts()["tasks"] == 2


def test_native_projection_contains_saved_truth_and_independent_final_failure(tmp_path):
    from jiuwenswarm.server.live_voice.task_control_presentation import native_task_presentation
    _, store, _, core, original, _, _ = _completed(tmp_path)
    command, grant = _adjust(original.task_id, "牛肉火锅和烧烤")
    core.execute(command, grant, now=NOW)
    facts, events = native_task_presentation(store, _scope(), [original.task_id])
    assert facts[original.task_id]["result_text"] == "immutable result"
    assert facts[original.task_id]["adjustment_state"] == "pending" and events == []
    store.adjustment_queue.advance(policy=core._admission_policy)
    _finish_child(store, outcome=TerminalOutcome.FAILED)
    store.adjustment_queue.advance(policy=core._admission_policy)
    facts, events = native_task_presentation(store, _scope(), [original.task_id])
    assert facts[original.task_id]["result_text"] == "immutable result"
    assert facts[original.task_id]["adjustment_state"] == "rejected"
    assert len(events) == 1 and events[0]["state"] == "rejected"
    assert json.loads(events[0]["result_text"])["application_stage"] == "saved_result"
    bounded, _ = native_task_presentation(store, _scope(), [original.task_id], maximum_result_bytes=1)
    assert "result_text" not in bounded[original.task_id]
    assert bounded[original.task_id]["result_available"]


@pytest.mark.asyncio
@pytest.mark.parametrize("timing", ["cutover", "completed"])
async def test_real_direct_files_and_core_continue_late_change_without_duplicate_effect(tmp_path, monkeypatch, timing):
    """Real SQLite, Git and Direct file validation; controlled Agent, no Provider claim."""
    from pathlib import Path
    from jiuwenswarm.common.schema.agent import AgentResponseChunk
    from tests.unit_tests.live_voice.test_project_code_executor import (
        _git_project, _DirectProjectExecutor, _MappedResolver, _direct_binding,
        DirectProjectCodeExecutorAdapter, _wait_direct_settled,
    )
    project = tmp_path / "project"
    _git_project(project)
    change = "9月12日第一晚牛肉火锅，第二晚烧烤；保留原有景点，不得修改原件.md。"
    original_text = "文化村、深圳湾"
    class Agent(_DirectProjectExecutor):
        async def process_background_code_task_stream(self, request):
            self.requests.append(request)
            root = Path(request.params["project_dir"])
            output = original_text
            if len(self.requests) > 1:
                assert change in request.params["query"]
                assert (root / "行程.md").read_text(encoding="utf-8") == original_text
                from jiuwenswarm.server.runtime.agent_adapter.background_task_checkpoint import current_background_task_checkpoint
                from jiuwenswarm.server.live_voice.file_effect_plan import FileEffectPlanError
                plan = current_background_task_checkpoint(request.session_id).file_plan
                assert plan is not None, "continuation keeps the existing file-effect boundary"
                await plan.seal({"requirement_head": plan.requirement_head, "preserve_existing": False,
                    "effects": [{"path": "行程.md", "operation": "replace"}], "required_outputs": ["行程.md"]})
                with pytest.raises(FileEffectPlanError):
                    await plan.before_tool("write_file", {"file_path": "原件.md"})
                assert not (root / "原件.md").exists()
                await plan.before_tool("write_file", {"file_path": "行程.md"})
                output += "；第一晚牛肉火锅；第二晚烧烤"
            (root / "行程.md").write_text(output, encoding="utf-8")
            yield AgentResponseChunk(request.request_id, request.channel_id,
                payload={"event_type": "chat.final", "content": output}, is_complete=True)
    agent = Agent(project)
    store = SqliteTaskStore(tmp_path / "tasks.sqlite3")
    adapter = DirectProjectCodeExecutorAdapter(_MappedResolver({project.resolve(): _direct_binding(project, agent)}), tmp_path / "tasks.sqlite3", durability_store=store)
    core = PersistentTaskCore(store, adapter)
    gate, release = threading.Event(), threading.Event()
    close = store.adjustment_queue.try_close
    def controlled_close(*args):
        result = close(*args)
        if result and not gate.is_set():
            gate.set()
            assert release.wait(20)
        return result
    if timing == "cutover":
        monkeypatch.setattr(store.adjustment_queue, "try_close", controlled_close)
    try:
        request = _create(project)
        created = core.execute(request.envelope, request.authorization, context=request.context, now=NOW)
        assert created.ok
        task_id = created.result["task_id"]
        assert await core.drain_outbox_once()
        if timing == "cutover":
            assert await asyncio.to_thread(gate.wait, 20)
        else:
            await _wait_direct_settled(adapter)
            await core.reconcile_status()
            assert store.get_task(task_id, _scope()).outcome is TerminalOutcome.COMPLETED
        command, grant = _adjust(task_id, change)
        receipt = core.execute(command, grant, now=NOW)
        assert receipt.ok and receipt.result["execution_mode"] == "followup"
        release.set()
        await _wait_direct_settled(adapter)
        await core.reconcile_status()
        original = store.get_task(task_id, _scope())
        assert original.outcome is TerminalOutcome.COMPLETED
        original_result = store.task_result(task_id, _scope())[1]
        assert original_result.result_text == original_text
        assert await core.drain_outbox_once()
        await _wait_direct_settled(adapter)
        await core.reconcile_status()
        await core.drain_outbox_once()
        final = core.execute(command, grant, now=NOW)
        assert final.result["adjustment_state"] == "applied", final.to_dict()
        child_id = final.result["continuation_task_id"]
        saved = store.task_result(child_id, _scope())[1]
        content = (project / "行程.md").read_bytes()
        assert saved.artifacts[0].sha256 == hashlib.sha256(content).hexdigest()
        assert "牛肉火锅" in saved.result_text and "烧烤" in content.decode("utf-8")
        assert len(agent.requests) == 2 and not await core.drain_outbox_once()
        assert store.task_result(task_id, _scope())[1] == original_result
    finally:
        release.set()
        await adapter.close(interrupt_running=True)
        await core.drain_inflight_adjustments()
