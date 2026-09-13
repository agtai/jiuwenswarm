"""File plans narrow actual filesystem effects and exact requirement revisions."""
import hashlib
import asyncio
import json
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.file_effect_plan import (
    FileEffectPlan, FileEffectPlanError, FileEffectPlanSession, canonical_effect_path,
)
from jiuwenswarm.server.live_voice.formal_task_models import TaskAdjustmentRequest
from tests.unit_tests.live_voice.test_native_task_source import source
from tests.unit_tests.live_voice.test_project_code_executor import _spec


def session(tmp_path):
    target, work = tmp_path / "target", tmp_path / "work"
    target.mkdir()
    work.mkdir()
    for root in (target, work):
        (root / "C.md").write_text("preserved C", encoding="utf-8")
    spec = _spec(target)
    spec = replace(spec, native_source=source(scope=spec.context.scope))
    item = SimpleNamespace(scope=spec.context.scope, spec=spec, task_id="task-plan", attempt_id="attempt-plan")
    return FileEffectPlanSession(item=item, target=target, worktree=work, baseline_digest="a" * 64,
        validate_target=lambda: None, protected_paths=(".gitignore", ".runtime"))


def proposal(owner, *, path="D.md", operation="create", preserve=True):
    return {"requirement_head": owner.requirement_head, "preserve_existing": preserve,
            "effects": [{"path": path, "operation": operation}], "required_outputs": [path]}


@pytest.mark.parametrize("path", ["../C.md", "/C.md", "C:/C.md", "D.md:stream", "nul.txt", "x/../C.md",
                                      ".git/config", "x./D.md", "D.md ", "C\\D.md", "x//D.md", "x?.md", "~/D.md", "LONGNA~1/D.md"])
def test_unsafe_or_alias_paths_are_rejected(path):
    with pytest.raises(FileEffectPlanError):
        canonical_effect_path(path)


@pytest.mark.asyncio
async def test_plan_bounds_aliases_and_protected_paths_have_no_effect(tmp_path):
    owner = session(tmp_path)
    maximum = {"requirement_head": owner.requirement_head, "preserve_existing": True,
        "effects": [{"path": f"report-{i}.md", "operation": "create"} for i in range(32)],
        "required_outputs": [f"report-{i}.md" for i in range(32)]}
    for invalid in (
        {**maximum, "effects": [*maximum["effects"], {"path": "extra.md", "operation": "create"}]},
        {**maximum, "required_outputs": [*maximum["required_outputs"], "extra.md"]},
        {**maximum, "effects": [{"path": "D.md", "operation": "create"}, {"path": "d.md", "operation": "create"}]},
        proposal(owner, path=".runtime/private.md"),
    ):
        with pytest.raises(FileEffectPlanError):
            await owner.seal(invalid)
        assert owner.plan is None
        assert {p.name for p in owner.worktree.iterdir()} == {"C.md"}
        assert {p.name for p in owner.target.iterdir()} == {"C.md"}
    plan = await owner.seal(maximum)
    assert len(plan.effects) == 32 and FileEffectPlan.from_dict(plan.to_dict()) == plan


@pytest.mark.asyncio
async def test_create_preserves_original_and_allows_further_edits_to_own_output(tmp_path):
    owner = session(tmp_path)
    plan = await owner.seal(proposal(owner))
    assert FileEffectPlan.from_dict(plan.to_dict()) == plan
    assert plan.effects[0].original_sha256 is None
    await owner.before_tool("write_file", {"file_path": "D.md"})
    (owner.worktree / "D.md").write_text("D", encoding="utf-8")
    await owner.before_tool("edit_file", {"file_path": str(owner.worktree / "D.md")})
    (owner.worktree / "D.md").write_text("D adjusted", encoding="utf-8")
    plan.require_delta(owner.worktree, ["D.md"])
    assert await owner.seal(proposal(owner)) is plan
    assert (owner.target / "C.md").read_text() == "preserved C"
    assert not (owner.target / "D.md").exists()


@pytest.mark.asyncio
async def test_explicit_existing_edit_is_hash_bound_and_target_race_rejects(tmp_path):
    owner = session(tmp_path)
    plan = await owner.seal(proposal(owner, path="C.md", operation="replace", preserve=False))
    assert plan.effects[0].original_sha256 == hashlib.sha256(b"preserved C").hexdigest()
    await owner.before_tool("edit_file", {"file_path": "C.md"})
    (owner.target / "C.md").write_text("external change", encoding="utf-8")
    with pytest.raises(FileEffectPlanError, match="BASELINE_CHANGED"):
        await owner.before_tool("write_file", {"file_path": "C.md"})
    assert (owner.worktree / "C.md").read_text() == "preserved C"


@pytest.mark.asyncio
async def test_preservation_unplanned_effects_required_outputs_and_freeze(tmp_path):
    owner = session(tmp_path)
    with pytest.raises(FileEffectPlanError, match="PRESERVATION_CONFLICT"):
        await owner.seal(proposal(owner, path="C.md", operation="replace"))
    with pytest.raises(FileEffectPlanError, match="REQUIRES_ABSENT"):
        await owner.seal(proposal(owner, path="C.md"))
    assert owner.plan is None
    plan = await owner.seal(proposal(owner))
    with pytest.raises(FileEffectPlanError, match="NOT_PLANNED"):
        await owner.before_tool("write_file", {"file_path": "C.md"})
    with pytest.raises(FileEffectPlanError, match="ALREADY_FROZEN"):
        await owner.seal(proposal(owner, path="C.md", operation="replace", preserve=False))
    with pytest.raises(FileEffectPlanError, match="UNPLANNED_DELTA"):
        plan.require_delta(owner.worktree, ["D.md", "C.md"])
    with pytest.raises(FileEffectPlanError, match="REQUIRED_OUTPUT_UNCHANGED"):
        plan.require_delta(owner.worktree, [])
    with pytest.raises(FileEffectPlanError, match="OPERATION_MISMATCH"):
        plan.require_delta(owner.worktree, ["D.md"])
    assert (owner.target / "C.md").read_text() == (owner.worktree / "C.md").read_text() == "preserved C"


@pytest.mark.asyncio
async def test_adopted_adjustment_invalidates_writes_but_allows_reads_and_new_exact_plan(tmp_path):
    owner = session(tmp_path)
    old_proposal = proposal(owner)
    old = await owner.seal(old_proposal)
    request = TaskAdjustmentRequest("adjust-D", "Keep D and add E.", 2)
    owner.adopt(request)
    await owner.before_tool("read_file", {"file_path": "C.md"})
    with pytest.raises(FileEffectPlanError, match="CURRENT_PLAN_REQUIRED"):
        await owner.before_tool("write_file", {"file_path": "D.md"})
    with pytest.raises(FileEffectPlanError, match="STALE"):
        await owner.seal(old_proposal)
    updated = proposal(owner)
    updated["effects"].append({"path": "E.md", "operation": "create"})
    updated["required_outputs"].append("E.md")
    new = await owner.seal(updated)
    assert new.revision == 2 and new.prior_plan_digest == old.digest
    owner.adopt(request)
    assert owner.current_plan() is new
    with pytest.raises(FileEffectPlanError, match="REPLAY_CONFLICT"):
        owner.adopt(replace(request, adjustment="Replace C instead."))
    owner.closed = True
    with pytest.raises(FileEffectPlanError, match="CLOSED"):
        await owner.before_tool("edit_file", {"file_path": "E.md"})


@pytest.mark.asyncio
async def test_tool_uses_only_current_executor_checkpoint(tmp_path):
    from jiuwenswarm.server.runtime.agent_adapter.background_task_checkpoint import background_task_checkpoint, file_effect_plan_tool
    owner = session(tmp_path)
    tool = file_effect_plan_tool()
    async def adopt(_): pass
    with pytest.raises(RuntimeError, match="OWNER_REQUIRED"):
        await tool.invoke(proposal(owner))
    with background_task_checkpoint("actual-session", adopt, file_plan=owner):
        bad = await tool.invoke({**proposal(owner), "task_id": "other-task"})
        assert not bad.success and owner.plan is None
        accepted = await tool.invoke(proposal(owner))
        assert accepted.success and accepted.data["plan_digest"] == owner.plan.digest
    with pytest.raises(RuntimeError, match="OWNER_REQUIRED"):
        await tool.invoke(proposal(owner))


@pytest.mark.asyncio
async def test_adjustment_restores_only_abandoned_isolated_effects(tmp_path):
    owner = session(tmp_path)
    first = proposal(owner, path="C.md", operation="replace", preserve=False)
    first["effects"].append({"path": "abandoned.md", "operation": "create"})
    first["required_outputs"].append("abandoned.md")
    await owner.seal(first)
    await owner.before_tool("edit_file", {"file_path": "C.md"})
    (owner.worktree / "C.md").write_text("abandoned edit")
    await owner.before_tool("write_file", {"file_path": "abandoned.md"})
    (owner.worktree / "abandoned.md").write_text("abandoned output")
    owner.adopt(TaskAdjustmentRequest("preserve-original", "Keep original C; produce D instead.", 2))
    updated = await owner.seal(proposal(owner))
    assert (owner.worktree / "C.md").read_bytes() == (owner.target / "C.md").read_bytes() == b"preserved C"
    assert not (owner.worktree / "abandoned.md").exists()
    await owner.before_tool("write_file", {"file_path": "D.md"})
    (owner.worktree / "D.md").write_text("new deliverable")
    updated.require_delta(owner.worktree, ["D.md"])
    assert not (owner.target / "D.md").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["cancel", "close", "new_requirement"])
async def test_isolated_restore_yields_event_loop_and_finishes_before_release(tmp_path, monkeypatch, interruption):
    from threading import Event
    owner = session(tmp_path)
    original = await owner.seal(proposal(owner, path="C.md", operation="replace", preserve=False))
    (owner.worktree / "C.md").write_text("abandoned edit")
    owner.adopt(TaskAdjustmentRequest("first-adjustment", "Preserve C, create D.", 2))
    entered, release, finished = Event(), Event(), Event()
    original_restore = owner._restore_excluded_paths
    def gated_restore(candidate):
        entered.set()
        assert release.wait(5)
        original_restore(candidate)
        finished.set()
    monkeypatch.setattr(owner, "_restore_excluded_paths", gated_restore)
    sealing = asyncio.create_task(owner.seal(proposal(owner)))
    closing = None
    try:
        assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 3), 4)
        # This callback runs while the real restore worker is deliberately blocked.
        tick = asyncio.Event()
        asyncio.get_running_loop().call_soon(tick.set)
        await asyncio.wait_for(tick.wait(), 0.5)
        if interruption == "cancel":
            sealing.cancel()
            await asyncio.sleep(0)
            sealing.cancel()  # Repeated cancellation cannot relinquish the worker.
        elif interruption == "close":
            closing = asyncio.create_task(owner.close())
        else:
            owner.adopt(TaskAdjustmentRequest("second-adjustment", "Create E instead.", 3))
        await asyncio.sleep(0)
        assert not sealing.done() and not finished.is_set()
        if closing is not None:
            assert not closing.done()
        release.set()
        with pytest.raises(asyncio.CancelledError if interruption == "cancel" else FileEffectPlanError):
            await sealing
        if closing is not None:
            await closing
        assert finished.is_set() and owner.plan is original
        assert (owner.worktree / "C.md").read_bytes() == b"preserved C"
        assert (owner.target / "C.md").read_bytes() == b"preserved C"
    finally:
        release.set()
        await asyncio.gather(sealing, *([] if closing is None else [closing]), return_exceptions=True)


@pytest.mark.parametrize("declared,actual", [("replace", "delete"), ("delete", "replace"),
                                           ("replace", "replace"), ("delete", "delete"), ("create", "create")])
def test_formal_apply_checks_operation_before_any_project_write(tmp_path, monkeypatch, declared, actual):
    from jiuwenswarm.server.live_voice import project_code_executor as module
    from jiuwenswarm.server.live_voice.file_effect_plan import PlannedFileEffect
    from tests.unit_tests.live_voice.test_project_code_executor import _git_project, _git
    root = tmp_path / "formal"
    _git_project(root)
    path = "new.txt" if actual == "create" else "README.md"
    target = root / path
    original = target.read_bytes() if target.exists() else None
    before_tree, before_head = module._project_tree_fingerprint(root), module._git_head(root)
    support = module._target_support_fingerprints(root)
    before_status = _git(root, "status", "--porcelain=v2")
    if actual == "delete":
        target.unlink()
    else:
        target.write_text("candidate result\n", encoding="utf-8")
    patch, expected = module._attempt_patch(root)
    if original is None:
        target.unlink()
    else:
        target.write_bytes(original)
    # Capture made an intent-to-add index entry for new paths; restore this test's index.
    _git(root, "reset", "--", path)
    spec = _spec(root)
    plan = FileEffectPlan(spec.context.scope, "task", "attempt", 1, None, "a" * 64, "b" * 64,
        before_tree, declared == "create", (PlannedFileEffect(path, declared,
            None if original is None else hashlib.sha256(original).hexdigest()),),
        () if declared == "delete" else (path,))
    mutations = []
    original_run = module._git_run_with_input
    def record(root, args, payload):
        if "--check" not in args:
            mutations.append(args)
        return original_run(root, args, payload)
    monkeypatch.setattr(module, "_git_run_with_input", record)
    if declared != actual:
        with pytest.raises(FileEffectPlanError, match="OPERATION_MISMATCH"):
            module._apply_attempt_patch(root, patch, expected_tree=expected, before_tree=before_tree,
                before_head=before_head, protected_support=support, file_plan=plan)
        assert mutations == []
        assert target.read_bytes() == original
        assert _git(root, "status", "--porcelain=v2") == before_status
    else:
        module._apply_attempt_patch(root, patch, expected_tree=expected, before_tree=before_tree,
            before_head=before_head, protected_support=support, file_plan=plan)
        assert len(mutations) == 1
        assert target.exists() == (actual != "delete")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["ok", "unplanned", "wrong_root", "wrong_session", "closed"])
async def test_real_facade_sdk_tool_registration_and_pre_write_boundary(tmp_path, case):
    from openjiuwen.core.context_engine import ContextEngineConfig
    from openjiuwen.core.context_engine.context.context import SessionModelContext
    from openjiuwen.core.foundation.llm import ToolCall
    from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig, AgentCard
    from openjiuwen.core.single_agent.rail.base import AgentCallbackContext, AgentCallbackEvent
    from openjiuwen.core.sys_operation.base import OperationMode
    from openjiuwen.core.sys_operation.config import LocalWorkConfig
    from openjiuwen.core.sys_operation.local.fs_operation import FsOperation
    from openjiuwen.harness.tools.filesystem import WriteFileTool
    from jiuwenswarm.agents.harness.common.rails.stream_event_rail import JiuSwarmStreamEventRail
    from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
    from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm
    from jiuwenswarm.server.runtime.agent_adapter.background_task_checkpoint import (
        background_task_checkpoint, current_background_task_checkpoint,
    )

    owner = session(tmp_path)
    root = ReActAgent(AgentCard(id="file-plan-" + tmp_path.name, name="File plan test", description="controlled"))
    root.configure(ReActAgentConfig(model_name="controlled"))
    rail = JiuSwarmStreamEventRail()
    await root.register_callback(AgentCallbackEvent.BEFORE_TOOL_CALL, rail.before_tool_call)
    fs = FsOperation("fs", OperationMode.LOCAL, "file-plan SDK validation",
        LocalWorkConfig(sandbox_root=[str(owner.worktree)], restrict_to_sandbox=True))
    tool = WriteFileTool(SimpleNamespace(fs=lambda: fs), agent_id=root.card.id)
    root.ability_manager.add_ability(tool.card, tool)
    context = SessionModelContext("file-plan-context", "exact-session", ContextEngineConfig(
        enable_openrouter_model_context_window_tokens=False), history_messages=[], processors=[])
    ctx = AgentCallbackContext(agent=root, context=context, extra={rail._SID_KEY: "exact-session"})
    before_write_history = []
    cleanups = []

    class Adapter:
        _is_session_scoped_adapter = False
        _stream_event_rail = rail
        _instance = SimpleNamespace(_react_agent=root, ability_manager=root.ability_manager)
        async def prepare_background_project_session(self, session_id):
            assert session_id == "exact-session"
        def _get_cached_session_adapter(self, session_id):
            return self if session_id == "exact-session" else None
        async def cleanup_session_adapter(self, session_id):
            assert rail.background_file_checkpoint is None and rail.background_model_checkpoint is None
            cleanups.append(session_id)
        async def process_message_stream_impl(self, request, inputs):
            # Registration and identity checks are the production facade's actual code.
            declare = ToolCall(id="declare", name="declare_file_effect_plan", type="function",
                arguments=json.dumps(proposal(owner)))
            result = await root._execute_tool_call(ctx, [declare], None, context)
            assert owner.plan is not None and result[0][0].success
            before_write_history.extend(context.get_messages())
            if case == "wrong_root":
                other_root = ReActAgent(AgentCard(id="other-" + tmp_path.name, name="Other", description="wrong root"))
                await other_root.register_callback(AgentCallbackEvent.BEFORE_TOOL_CALL, rail.before_tool_call)
                ctx.agent = other_root
            elif case == "wrong_session":
                ctx.extra[rail._SID_KEY] = "other-session"
            elif case == "closed":
                current_background_task_checkpoint(request.session_id).closed = True
            path = owner.worktree / ("forbidden.md" if case == "unplanned" else "D.md")
            write = ToolCall(id="write", name="write_file", type="function",
                arguments=json.dumps({"file_path": str(path), "content": "actual SDK file bytes"}))
            result = await root._execute_tool_call(ctx, [write], None, context)
            if case == "ok":
                assert result[0][0].success
            yield AgentResponseChunk(request.request_id, request.channel_id,
                payload={"event_type": "chat.final", "content": "done"}, is_complete=True)

    facade = object.__new__(JiuWenSwarm)
    facade._adapter = Adapter()
    facade.get_project_execution_root = lambda: str(owner.worktree)
    facade._build_inputs = lambda request: ({}, None, None)
    request = AgentRequest("file-plan-request", session_id="exact-session", params={"project_dir": str(owner.worktree)})
    async def adopt(_): pass
    with background_task_checkpoint("exact-session", adopt, file_plan=owner):
        if case == "ok":
            assert len([chunk async for chunk in facade.process_background_code_task_stream(request)]) == 1
        else:
            with pytest.raises(RuntimeError):
                [chunk async for chunk in facade.process_background_code_task_stream(request)]
            assert not (owner.worktree / "D.md").exists() and not (owner.worktree / "forbidden.md").exists()
            # SDK keeps a tool-error diagnostic in this isolated model context.
            # The facade emits no successful chunk or user Chat history entry.
            messages = context.get_messages()
            assert messages[:-1] == before_write_history
            assert messages[-1].tool_call_id == "write"
            assert "Ability execution error" in messages[-1].content
    assert cleanups == ["exact-session"]
    assert (owner.target / "C.md").read_bytes() == b"preserved C"
    if case == "ok":
        assert (owner.worktree / "D.md").read_bytes() == b"actual SDK file bytes"
        assert not (owner.target / "D.md").exists()
