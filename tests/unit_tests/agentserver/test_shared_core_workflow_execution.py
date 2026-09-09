"""Core runs use the original service Task and real SDK checkpoint continuation."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from openjiuwen.core.common.constants.constant import INTERACTION
from openjiuwen.core.session import InteractionOutput
from openjiuwen.core.session.stream import OutputSchema
from openjiuwen.core.runner import Runner
from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.checkpointer.inmemory import InMemoryCheckpointer
from openjiuwen.core.workflow import End, Start, Workflow, WorkflowCard, WorkflowComponent, WorkflowOutput

from jiuwenswarm.server.runtime.core_workflow_capabilities import (
    CoreWorkflowCapabilities, CoreWorkflowError, CoreWorkflowScope,
)
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.session_execution import SessionExecutionService


@pytest.fixture
async def runtime(monkeypatch):
    directory = CoreWorkflowCapabilities()
    manager = SimpleNamespace(core_workflow_capabilities=directory, pin_agent=Mock(), unpin_agent=Mock())
    service = SessionExecutionService(manager)
    checkpoint = InMemoryCheckpointer()
    monkeypatch.setattr(CheckpointerFactory, "_default_checkpointer", checkpoint)
    agent = object()
    cards = []
    effects = []

    class Count(WorkflowComponent):
        async def invoke(self, inputs, session, context):
            effects.append("count")
            return {"text": "counted"}

    class Ask(WorkflowComponent):
        async def invoke(self, inputs, session, context):
            answer = await session.interact("Confirm")
            if self.twice:
                answer = await session.interact("Confirm again")
            return {"answer": answer}

    def register(*, interactive=False):
        card = WorkflowCard(id=uuid4().hex, version="1", input_params=deepcopy(INPUT_SCHEMA))
        workflow = Workflow(card=card)
        workflow.set_start_comp("start", Start(), inputs_schema={"text": "${text}"})
        workflow.add_workflow_comp("count", Count())
        workflow.add_connection("start", "count")
        if interactive:
            ask = Ask()
            ask.twice = interactive == "twice"
            workflow.add_workflow_comp("ask", ask)
            workflow.add_connection("count", "ask")
            workflow.set_end_comp("end", End(), inputs_schema={"answer": "${ask.answer}"})
            workflow.add_connection("ask", "end")
        else:
            workflow.set_end_comp("end", End(), inputs_schema={"text": "${count.text}"})
            workflow.add_connection("count", "end")
        provider = Mock(return_value=workflow)
        Runner.resource_mgr.add_workflow(card=card, workflow=provider)
        cards.append(card)
        metadata = directory.register(scope=SCOPE, capability_id="fixture", card=card,
            required_permissions=("core.execute",), continuation_schemas={"ask": {"type": "string", "minLength": 1}})
        return workflow, provider, metadata

    yield SimpleNamespace(directory=directory, manager=manager, service=service, checkpoint=checkpoint,
        agent=agent, register=register, effects=effects)
    await service.close(timeout=2)
    for card in cards:
        Runner.resource_mgr.remove_workflow(card.id)


def request(identity="start"):
    return AgentRequest(request_id=identity, channel_id=SCOPE.channel_id, session_id=SCOPE.session_id)


async def fact_when(runtime, run_id, predicate):
    from jiuwenswarm.server.runtime.core_workflow_execution import get_core_workflow
    async with asyncio.timeout(3):
        while True:
            fact = get_core_workflow(runtime.service, runtime.agent, scope=SCOPE,
                run_id=run_id, before_effect=lambda _cap: None)
            if predicate(fact):
                return fact
            await asyncio.sleep(0)


async def start(runtime, *, identity="start", inputs=None, guard=None):
    from jiuwenswarm.server.runtime.core_workflow_execution import start_core_workflow
    return await start_core_workflow(runtime.service, runtime.agent, request=request(identity), scope=SCOPE,
        epoch=runtime.service.execution_epoch, capability_id="fixture", inputs=inputs or {"text": "hello"},
        before_effect=guard or (lambda _cap: None))


async def test_default_empty_and_schema_rejection_have_zero_provider_effects(runtime):
    from jiuwenswarm.server.runtime.core_workflow_execution import list_core_workflows
    listing = list_core_workflows(runtime.service, runtime.agent, scope=SCOPE, before_effect=lambda _cap: None)
    assert listing["capabilities"] == [] and listing["runs"] == []
    with pytest.raises(CoreWorkflowError, match="not_registered"):
        await start(runtime)
    _, provider, _ = runtime.register()
    with pytest.raises(CoreWorkflowError, match="invalid_input"):
        await start(runtime, inputs={"text": 1})
    provider.assert_not_called()
    assert runtime.manager.pin_agent.call_count == 0 and not runtime.checkpoint._workflow_stores


async def test_real_completion_and_start_replay_keep_single_original_task(runtime):
    _, provider, _ = runtime.register()
    receipt = await start(runtime)
    assert receipt["status"] == "accepted" and receipt["business_completion"] is False
    assert await start(runtime) == receipt
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert fact["sdk_state"] == "COMPLETED" and fact["business_completion"] is True
    assert fact["result"] == {"output": {"text": "counted"}}
    assert runtime.effects == ["count"] and provider.call_count == 1
    assert await start(runtime) == receipt
    assert runtime.manager.pin_agent.call_count == 1


async def test_real_input_required_keeps_original_task_and_private_checkpoint(runtime):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["sdk_state"] == "INPUT_REQUIRED")
    assert fact["pending"] == [{"id": "ask", "value": "Confirm"}]
    assert fact["continuation_available"] and not fact["settled"] and not fact["business_completion"]
    assert SCOPE.session_id not in runtime.checkpoint._workflow_stores
    assert len(runtime.checkpoint._workflow_stores) == 1
    assert runtime.service.retains_session(channel_id=SCOPE.channel_id, session_id=SCOPE.session_id)
    runtime.service.disconnect(channel_id=SCOPE.channel_id, session_id=SCOPE.session_id)
    assert (await fact_when(runtime, receipt["run_id"], lambda x: True))["continuation_available"]


async def resume(runtime, receipt, *, identity="resume", answers=None, guard=None, revision=None):
    from jiuwenswarm.server.runtime.core_workflow_execution import resume_core_workflow
    return await resume_core_workflow(runtime.service, runtime.agent, request=request(identity), scope=SCOPE,
        epoch=runtime.service.execution_epoch, run_id=receipt["run_id"],
        expected_revision=revision if revision is not None else receipt["revision"],
        answers={"ask": "yes"} if answers is None else answers,
        before_effect=guard or (lambda _cap: None))


@pytest.mark.parametrize("answers", [{"wrong": "yes"}, {"ask": 1}, {"ask": None}, {"ask": "yes", "extra": "no"},
                                     {1: "yes"}, {"ask": ""}])
async def test_invalid_continuation_has_zero_checkpoint_and_node_effects(runtime, answers):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    before = deepcopy(next(iter(runtime.checkpoint._workflow_stores.values())).state_blobs)
    with pytest.raises(CoreWorkflowError):
        await resume(runtime, fact, answers=answers)
    assert next(iter(runtime.checkpoint._workflow_stores.values())).state_blobs == before
    assert runtime.effects == ["count"]
    assert (await fact_when(runtime, receipt["run_id"], lambda x: True))["continuation_available"]


@pytest.mark.parametrize("field,value", [("channel_id", "other"), ("session_id", "other"),
                                        ("project_id", None), ("agent_mode", "code")])
async def test_wrong_scope_and_agent_cannot_find_or_resume_run(runtime, field, value):
    from jiuwenswarm.server.runtime.core_workflow_execution import get_core_workflow, resume_core_workflow
    runtime.register(interactive=True)
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    wrong_scope = replace(SCOPE, **{field: value})
    with pytest.raises(CoreWorkflowError, match="unknown_run"):
        get_core_workflow(runtime.service, runtime.agent, scope=wrong_scope,
            run_id=receipt["run_id"], before_effect=lambda _cap: None)
    with pytest.raises(CoreWorkflowError, match="unknown_run"):
        await resume_core_workflow(runtime.service, object(), request=request("other"), scope=SCOPE,
            epoch=runtime.service.execution_epoch, run_id=receipt["run_id"],
            expected_revision=fact["revision"], answers={"ask": "yes"}, before_effect=lambda _cap: None)
    assert runtime.effects == ["count"]


async def test_old_epoch_conflict_and_capacity_never_restart_completed_run(runtime):
    from jiuwenswarm.server.runtime.core_workflow_execution import start_core_workflow
    from jiuwenswarm.server.runtime.session_execution import SessionExecutionUnavailable
    _, provider, _ = runtime.register()
    runtime.service.max_records = runtime.service.max_active = 1
    receipt = await start(runtime)
    await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    with pytest.raises(SessionExecutionUnavailable, match="REQUEST_CONFLICT"):
        await start(runtime, inputs={"text": "changed"})
    with pytest.raises(SessionExecutionUnavailable, match="CAPACITY"):
        await start(runtime, identity="other")
    with pytest.raises(CoreWorkflowError, match="execution_epoch_mismatch"):
        await start_core_workflow(runtime.service, runtime.agent, request=request("old"), scope=SCOPE,
            epoch="old-process", capability_id="fixture", inputs={"text": "old"}, before_effect=lambda _cap: None)
    assert await start(runtime) == receipt
    assert provider.call_count == 1 and runtime.effects == ["count"]


async def test_authority_revoked_while_provider_waits_prevents_sdk_and_checkpoint(runtime, monkeypatch):
    _, _, metadata = runtime.register()
    original = runtime.directory.resolve
    entered, release = asyncio.Event(), asyncio.Event()
    authority = {"allowed": True}

    def guard(actual):
        assert actual is metadata
        if not authority["allowed"]:
            raise PermissionError("revoked")

    async def delayed(**kwargs):
        result = await original(**kwargs)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(runtime.directory, "resolve", delayed)
    receipt = await start(runtime, guard=guard)
    await asyncio.wait_for(entered.wait(), 2)
    authority["allowed"] = False
    release.set()
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert fact["failure_reason"] == "permission_denied" and not fact["business_completion"]
    assert runtime.effects == [] and not runtime.checkpoint._workflow_stores


async def test_resume_final_guard_revocation_preserves_pending_future(runtime):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    calls = []

    def revoke_at_delivery(_cap):
        calls.append("guard")
        if len(calls) == 2:
            raise PermissionError("revoked at final admission")

    with pytest.raises(PermissionError):
        await resume(runtime, fact, guard=revoke_at_delivery)
    assert (await fact_when(runtime, receipt["run_id"], lambda x: True))["continuation_available"]
    assert runtime.effects == ["count"]


async def test_cancel_pending_run_releases_only_private_checkpoint_and_closes_admission(runtime):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    released = []
    original_release = runtime.checkpoint.release

    async def release(sid):
        released.append(sid)
        await original_release(sid)

    runtime.checkpoint.release = release
    assert await runtime.service.close(timeout=2)
    final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert final["failure_reason"] == "cancelled" and not final["business_completion"]
    assert len(released) == 1 and released[0] != SCOPE.session_id
    with pytest.raises(ValueError):
        await resume(runtime, fact)


async def test_pending_runs_at_active_capacity_still_allow_control_admission(runtime):
    runtime.register(interactive=True)
    runtime.service.max_active = 1
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    calls = []

    def denied_at_delivery(_cap):
        calls.append(None)
        if len(calls) == 2:
            raise PermissionError("control reached its original pending owner")

    with pytest.raises(PermissionError):
        await resume(runtime, fact, guard=denied_at_delivery)
    assert runtime.effects == ["count"]


async def test_real_strict_resume_and_competing_carriers_consume_only_once(runtime):
    _, provider, _ = runtime.register(interactive=True)
    receipt = await start(runtime)
    pending = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    outcomes = await asyncio.gather(resume(runtime, pending, identity="web-reply"),
        resume(runtime, pending, identity="native-reply"), return_exceptions=True)
    accepted = [item for item in outcomes if isinstance(item, dict)]
    assert len(accepted) == 1 and len([item for item in outcomes if isinstance(item, CoreWorkflowError)]) == 1
    assert accepted[0]["status"] == "accepted" and not accepted[0]["business_completion"]
    final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert final["sdk_state"] == "COMPLETED" and final["business_completion"]
    assert final["result"] == {"output": {"answer": "yes"}}
    assert runtime.effects == ["count"] and provider.call_count == 1
    winner = "web-reply" if isinstance(outcomes[0], dict) else "native-reply"
    assert await resume(runtime, pending, identity=winner) == accepted[0]


async def test_same_node_next_round_rejects_old_revision_but_replays_original_control_receipt(runtime):
    runtime.register(interactive="twice")
    receipt = await start(runtime)
    first = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    accepted = await resume(runtime, first, identity="first")
    second = await fact_when(runtime, receipt["run_id"],
        lambda x: x["continuation_available"] and x["revision"] > first["revision"])
    assert second["pending"] == [{"id": "ask", "value": "Confirm again"}]
    assert await resume(runtime, first, identity="first") == accepted
    with pytest.raises(CoreWorkflowError, match="pending_revision_mismatch"):
        await resume(runtime, first, identity="stale")
    await resume(runtime, second, identity="second", answers={"ask": "finished"})
    final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert final["business_completion"] and runtime.effects == ["count"]


@pytest.mark.parametrize("missing", ["workflow", "graph"])
async def test_real_strict_missing_checkpoint_never_reexecutes_prior_effects(runtime, missing):
    workflow, _, _ = runtime.register(interactive=True)
    receipt = await start(runtime)
    pending = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    sid = next(iter(runtime.checkpoint._workflow_stores))
    if missing == "workflow":
        runtime.checkpoint._workflow_stores[sid].state_blobs.clear()
    else:
        await runtime.checkpoint.graph_store().delete(sid, workflow.card.id)
    accepted = await resume(runtime, pending)
    assert accepted["status"] == "accepted" and not accepted["business_completion"]
    final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert not final["business_completion"] and not final["continuation_available"]
    assert final["failure_reason"] and final["failure_reason"] != "workflow_execution_failed"
    assert runtime.effects == ["count"]


async def test_checkpoint_provider_replacement_rejects_before_consuming_pending(runtime, monkeypatch):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    pending = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    replacement = InMemoryCheckpointer()
    monkeypatch.setattr(CheckpointerFactory, "_default_checkpointer", replacement)
    with pytest.raises(CoreWorkflowError, match="checkpointer_changed"):
        await resume(runtime, pending)
    assert runtime.effects == ["count"] and not replacement._workflow_stores


async def test_accepted_control_does_not_skip_revocation_at_original_producer(runtime):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    pending = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    calls = []

    def guard(_cap):
        calls.append(None)
        if len(calls) >= 3:
            raise PermissionError("revoked after Future delivery")

    accepted = await resume(runtime, pending, guard=guard)
    assert accepted["status"] == "accepted"
    final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert final["failure_reason"] == "permission_denied" and not final["business_completion"]
    assert runtime.effects == ["count"]


async def test_cleanup_failure_retains_actual_failure_instead_of_completion(runtime):
    runtime.register()
    entered, release = asyncio.Event(), asyncio.Event()

    async def failed_cleanup(_sid):
        entered.set()
        await release.wait()
        raise RuntimeError("cleanup failed")

    runtime.checkpoint.release = failed_cleanup
    receipt = await start(runtime)
    await asyncio.wait_for(entered.wait(), 2)
    before = await fact_when(runtime, receipt["run_id"], lambda x: True)
    assert before["sdk_state"] == "COMPLETED" and not before["business_completion"]
    assert runtime.manager.unpin_agent.call_count == 0
    release.set()
    final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert final["failure_reason"] == "checkpoint_cleanup_failed" and not final["business_completion"]


async def test_incomplete_pending_shape_is_not_silently_reduced_to_supported_nodes(runtime, monkeypatch):
    runtime.register()
    result = WorkflowOutput(state="INPUT_REQUIRED", result=[
        OutputSchema(type=INTERACTION, index=0, payload=InteractionOutput(id="ask", value="valid")),
        OutputSchema(type=INTERACTION, index=1, payload=("unknown-node", "unsupported")),
    ])
    monkeypatch.setattr(runtime.directory, "invoke", AsyncMock(return_value=result))
    receipt = await start(runtime)
    final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert final["sdk_state"] == "INPUT_REQUIRED" and not final["continuation_available"]
    assert final["failure_reason"] == "unsupported_pending_output"


async def test_listing_checks_original_run_permissions_after_directory_replacement(runtime):
    from jiuwenswarm.server.runtime.core_workflow_execution import list_core_workflows
    _, _, original = runtime.register()
    receipt = await start(runtime)
    await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    runtime.manager.core_workflow_capabilities = CoreWorkflowCapabilities()
    observed = []

    def deny_original(capability):
        observed.append(capability)
        raise PermissionError("original run remains protected")

    result = list_core_workflows(runtime.service, runtime.agent, scope=SCOPE, before_effect=deny_original)
    assert result["runs"] == [] and observed == [original]


async def test_oversized_pending_projection_never_accepts_truncated_continuation(runtime, monkeypatch):
    runtime.register()
    result = WorkflowOutput(state="INPUT_REQUIRED", result=[
        OutputSchema(type=INTERACTION, index=0, payload=InteractionOutput(id="ask", value="x" * 200_000)),
    ])
    monkeypatch.setattr(runtime.directory, "invoke", AsyncMock(return_value=result))
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["sdk_state"] == "INPUT_REQUIRED")
    assert fact["projection_unavailable"] and fact["pending"] == [] and not fact["continuation_available"]
    entries = runtime.service.list_internal(runtime.agent, session_id=SCOPE.session_id, kind="core_workflow_run")
    assert not entries[0].task.done(), entries[0].task.exception()
    with pytest.raises(CoreWorkflowError, match="continuation_unavailable"):
        await resume(runtime, fact)
    assert runtime.effects == []


async def test_get_projection_cannot_rewrite_original_pending_identity(runtime):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    fact["pending"][0]["id"] = "forged"
    fact["revision"] = 999
    original = await fact_when(runtime, receipt["run_id"], lambda x: True)
    assert original["pending"] == [{"id": "ask", "value": "Confirm"}] and original["revision"] == 2


async def test_non_workflow_return_does_not_become_completion_by_eof(runtime, monkeypatch):
    runtime.register()
    monkeypatch.setattr(runtime.directory, "invoke", AsyncMock(return_value=None))
    receipt = await start(runtime)
    fact = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert fact["sdk_state"] is None and not fact["business_completion"]
    assert fact["failure_reason"] == "invalid_workflow_output"


@pytest.mark.parametrize("sdk_continues", [False, True])
async def test_control_publish_failure_preserves_actual_future_admission_receipt(runtime, monkeypatch, sdk_continues):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    pending = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    entry = runtime.service.list_internal(runtime.agent, session_id=SCOPE.session_id, kind="core_workflow_run")[0]
    actual_future = entry.capability_state.inbox
    publish = runtime.service._publish
    failures = []

    async def fail_control(control_entry, chunk):
        if control_entry.internal_kind == "core_workflow_control":
            failures.append(control_entry)
            raise RuntimeError("observer failed after actual input admission")
        await publish(control_entry, chunk)

    calls = []

    def revoke_after_delivery(_cap):
        calls.append(None)
        if len(calls) >= 3:
            raise PermissionError("do not enter new SDK while testing receipt")

    monkeypatch.setattr(runtime.service, "_publish", fail_control)
    accepted = await resume(runtime, pending, guard=None if sdk_continues else revoke_after_delivery)
    assert accepted["status"] == "accepted" and accepted["observation_unavailable"]
    assert not accepted["business_completion"]
    assert actual_future.done() and actual_future.result()[0] == {"ask": "yes"}
    assert await resume(runtime, pending) == accepted
    assert len(failures) == 1 and runtime.effects == ["count"]
    if sdk_continues:
        final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
        assert final["business_completion"] and final["sdk_state"] == "COMPLETED"


async def test_cancelled_control_observer_propagates_but_replay_reads_original_admission(runtime, monkeypatch):
    runtime.register(interactive=True)
    receipt = await start(runtime)
    pending = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    entered, release = asyncio.Event(), asyncio.Event()
    publish = runtime.service._publish
    calls = []

    async def delay_control(entry, chunk):
        if entry.internal_kind == "core_workflow_control":
            entered.set()
            await release.wait()
        await publish(entry, chunk)

    def revoke_after_delivery(_cap):
        calls.append(None)
        if len(calls) >= 3:
            raise PermissionError("stop at admitted Future")

    monkeypatch.setattr(runtime.service, "_publish", delay_control)
    observer = asyncio.create_task(resume(runtime, pending, guard=revoke_after_delivery))
    await asyncio.wait_for(entered.wait(), 2)
    observer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await observer
    replay = asyncio.create_task(resume(runtime, pending))
    try:
        async with asyncio.timeout(0.5):
            accepted = await asyncio.shield(replay)
        assert accepted["status"] == "accepted" and not accepted["business_completion"]
    finally:
        release.set()
        await asyncio.gather(replay, return_exceptions=True)


async def test_real_sdk_snapshot_wait_rechecks_new_resume_grant_before_state_application(runtime, monkeypatch):
    from openjiuwen.core.session.checkpointer.workflow_resume import PreparedWorkflowResume
    runtime.register(interactive=True)
    receipt = await start(runtime)
    pending = await fact_when(runtime, receipt["run_id"], lambda x: x["continuation_available"])
    entered, release = asyncio.Event(), asyncio.Event()
    graph_store = runtime.checkpoint.graph_store()
    original_get = graph_store.get
    original_apply = PreparedWorkflowResume.apply
    applied = []
    authority = {"allowed": True}

    async def blocked_read(*args):
        snapshot = await original_get(*args)
        entered.set()
        await release.wait()
        return snapshot

    def apply(snapshot, session):
        applied.append(session)
        return original_apply(snapshot, session)

    def guard(_cap):
        if not authority["allowed"]:
            raise PermissionError("revoked while SDK read the exact checkpoint")

    monkeypatch.setattr(graph_store, "get", blocked_read)
    monkeypatch.setattr(PreparedWorkflowResume, "apply", apply)
    accepted = await resume(runtime, pending, guard=guard)
    assert accepted["status"] == "accepted"
    await asyncio.wait_for(entered.wait(), 2)
    authority["allowed"] = False
    release.set()
    final = await fact_when(runtime, receipt["run_id"], lambda x: x["settled"])
    assert final["failure_reason"] == "permission_denied" and not final["business_completion"]
    assert applied == [] and runtime.effects == ["count"]


SCOPE = CoreWorkflowScope("web", "public-core", "project", "deep")
INPUT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}},
                "required": ["text"], "additionalProperties": False}


def test_pure_prevalidation_snapshots_inputs_and_requires_exact_pending():
    directory = CoreWorkflowCapabilities()
    card = WorkflowCard(id="prevalidation", version="1", input_params=INPUT_SCHEMA)
    metadata = directory.register(scope=SCOPE, capability_id="fixture", card=card,
        required_permissions=("core.execute",), continuation_schemas={"ask": {"type": "string"}})
    inputs = {"text": "hello"}
    assert directory.get(scope=SCOPE, capability_id="fixture") is metadata
    assert directory.validate_inputs(scope=SCOPE, capability_id="fixture", inputs=inputs) == inputs
    snapshot = directory.validate_inputs(scope=SCOPE, capability_id="fixture", inputs=inputs)
    inputs["text"] = "changed"
    assert snapshot == {"text": "hello"}
    pending = [InteractionOutput(id="ask", value="confirm")]
    assert directory.validate_answers(scope=SCOPE, capability_id="fixture", pending=pending,
        answers={"ask": "yes"}) == {"ask": "yes"}
    with pytest.raises(CoreWorkflowError, match="pending_input_mismatch"):
        directory.validate_answers(scope=SCOPE, capability_id="fixture", pending=pending,
            answers={"other": "yes"})
    with pytest.raises(CoreWorkflowError, match="invalid_input"):
        directory.validate_inputs(scope=SCOPE, capability_id="fixture", inputs={"text": 1})
    assert metadata.input_schema == deepcopy(INPUT_SCHEMA)
