"""Service context binding tests; Deep/rails and SDK task callbacks are not cut over here."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.server.runtime.execution_context import AgentExecutionPolicy, ExecutionContextUnavailable
from jiuwenswarm.server.runtime.session_execution import (
    SessionExecutionService,
    SessionExecutionUnavailable,
    current_execution_policy,
    current_output_observer,
    current_output_work,
    prepare_current_work,
)


def request(request_id="request", **changes):
    values = dict(request_id=request_id, channel_id="web", session_id="public-session",
        params={"query": "original", "mode": "agent", "project_dir": "/project"}, is_stream=True)
    return AgentRequest(**(values | changes))


def native_policy(**changes):
    values = dict(origin="native", tool_policy="read_only", model_identity="model#0",
        model_config_version="v1", before_effect=Mock(return_value=None))
    return AgentExecutionPolicy(**(values | changes))


def source(work, *, kind="user", **changes):
    values = dict(source_binding_id=work.binding_id,
        source_origin_request_id=work.request.request_id, source_session_id=work.sdk_session_id,
        source_task_id="actual-task", source_run_kind=kind,
        source_request_id=work.request.request_id if kind == "user" else None,
        source_goal_id="goal-a" if kind == "goal" else None,
        source_goal_revision=1 if kind == "goal" else None)
    return values | changes


class Producer:
    """Real service-owned async generators with explicit output admission calls."""

    def __init__(self, **limits):
        self.hub = SessionExecutionService(SimpleNamespace(pin_agent=Mock(), unpin_agent=Mock()), **limits)
        self.plans = {}
        self.calls = []
        self.validated = []

    async def process_message_stream(self, req):
        plan = self.plans[req.request_id]
        self.calls.append(req)
        try:
            plan.policy = current_execution_policy()
            _, plan.work = prepare_current_work(sdk_agent=plan.sdk_agent, session_id=plan.sdk_session_id,
                apply_runtime=plan.apply_runtime, permission_context=plan.permission_context)
            current_output_observer(plan.observer_agent)(plan.token, plan.acquired)
            plan.ready.set()
            if plan.short:
                return
            while True:
                payload = await plan.queue.get()
                if payload is None:
                    return
                work = current_output_work(payload)
                self.validated.append(work)
                yield AgentResponseChunk(request_id=req.request_id, channel_id=req.channel_id, payload=payload)
        finally:
            plan.ready.set()

    async def start(self, req=None, *, policy=None, sdk_agent=None, sdk_session_id="sdk-session",
                    observer_agent=None, token=None, acquired=True, short=False,
                    apply_runtime=None, permission_context=None):
        req = req or request()
        sdk_agent = sdk_agent if sdk_agent is not None else object()
        plan = SimpleNamespace(sdk_agent=sdk_agent, sdk_session_id=sdk_session_id,
            observer_agent=observer_agent if observer_agent is not None else sdk_agent,
            token=token or req.request_id, acquired=acquired, short=short,
            ready=asyncio.Event(), queue=asyncio.Queue(), work=None,
            apply_runtime=apply_runtime or Mock(return_value=None), permission_context=permission_context)
        self.plans[req.request_id] = plan
        plan.entry = (self.hub.start(self, req) if policy is None else
                      self.hub.start_bound(self, req, policy=policy))
        await asyncio.wait_for(plan.ready.wait(), 2)
        await asyncio.sleep(0)
        return plan

    async def settle(self, plan):
        await asyncio.wait_for(asyncio.gather(plan.entry.task, return_exceptions=True), 2)
        await asyncio.sleep(0)


@pytest.fixture
async def producer():
    instance = Producer()
    yield instance
    assert await instance.hub.close(timeout=2)
    await asyncio.sleep(0)


async def test_preparation_copies_request_and_ordinary_metadata_cannot_select_native_policy(producer):
    req = request(metadata={"origin": "native", "tool_policy": "none",
        "execution_policy": {"origin": "native", "model_identity": "forged"}})
    plan = await producer.start(req)
    req.params["query"] = "mutated outside"
    copied = plan.work.request
    copied.params["query"] = "mutated snapshot"
    assert plan.work.request.params["query"] == "original"
    assert plan.policy is None
    assert plan.work.policy == AgentExecutionPolicy()
    assert plan.work.policy.records_generated_history is True
    assert producer.hub.resolve_work_context(sdk_agent=plan.sdk_agent, session_id="sdk-session",
        run_context=plan.work.run_context()) is plan.work


@pytest.mark.parametrize("changes", [
    {"model_identity": None}, {"model_identity": ""}, {"model_identity": " model"},
    {"model_config_version": None}, {"model_config_version": ""}, {"model_config_version": 1},
    {"before_effect": None}, {"before_effect": "callable"}, {"tool_policy": "configured"},
    {"tool_policy": "write"},
])
def test_native_policy_rejects_incomplete_model_or_unrestricted_tools(changes):
    with pytest.raises(ExecutionContextUnavailable):
        native_policy(**changes)


@pytest.mark.parametrize("tool_policy", ["read_only", "none"])
async def test_native_bound_policy_is_internal_and_replay_cannot_replace_guard(producer, tool_policy):
    policy = native_policy(tool_policy=tool_policy)
    req = request()
    plan = await producer.start(req, policy=policy)
    replacement_guard = Mock(return_value=None)
    replay_policy = replace(policy, before_effect=replacement_guard)
    assert producer.hub.start_bound(producer, deepcopy(req), policy=replay_policy) is plan.entry
    assert plan.work.policy is policy
    assert not plan.work.policy.records_generated_history
    await plan.work.before_effect(SimpleNamespace(), model_call=True)
    policy.before_effect.assert_called_once()
    plan.apply_runtime.assert_called_once()
    replacement_guard.assert_not_called()
    for changed in (replace(policy, model_identity="other"), replace(policy, model_config_version="v2"),
                    replace(policy, tool_policy="none" if tool_policy == "read_only" else "read_only")):
        with pytest.raises(SessionExecutionUnavailable, match="REQUEST_CONFLICT"):
            producer.hub.start_bound(producer, req, policy=changed)
    with pytest.raises(SessionExecutionUnavailable, match="REQUEST_CONFLICT"):
        producer.hub.start(producer, req)
    assert len(producer.calls) == 1


async def test_ordinary_request_cannot_be_upgraded_by_replay_with_internal_policy(producer):
    req = request()
    plan = await producer.start(req)
    with pytest.raises(SessionExecutionUnavailable, match="REQUEST_CONFLICT"):
        producer.hub.start_bound(producer, req, policy=native_policy())
    assert plan.entry.policy is None
    assert plan.work.policy == AgentExecutionPolicy()
    assert len(producer.calls) == 1


async def test_effect_revocation_and_owner_stop_during_callback_prevent_runtime_apply(producer):
    revoked = native_policy(before_effect=Mock(side_effect=PermissionError("revoked")))
    plan = await producer.start(policy=revoked)
    with pytest.raises(PermissionError):
        await plan.work.before_effect(SimpleNamespace(), model_call=True)
    plan.apply_runtime.assert_not_called()

    async def stop_during_guard():
        producer.hub._cancel(stopping.entry)
        await asyncio.sleep(0)

    stopping = await producer.start(request("stopping"), policy=native_policy(before_effect=stop_during_guard))
    with pytest.raises(ExecutionContextUnavailable, match="BINDING_CLOSED"):
        await stopping.work.before_effect(SimpleNamespace(), model_call=True)
    stopping.apply_runtime.assert_not_called()


async def test_tool_callback_does_not_reapply_model_runtime_and_replaces_permission_context(producer):
    from jiuwenswarm.agents.harness.common.rails.permissions.owner_scopes import TOOL_PERMISSION_CONTEXT
    from jiuwenswarm.agents.harness.common.rails.permissions.tool_permission_context import TOOL_PERMISSION_CHANNEL_ID

    permission = {"owner": "original", "nested": [1]}
    plan = await producer.start(policy=native_policy(), permission_context=permission)
    permission["nested"].append(2)
    await plan.work.before_effect(SimpleNamespace())
    assert TOOL_PERMISSION_CONTEXT.get() == {"owner": "original", "nested": [1]}
    assert TOOL_PERMISSION_CHANNEL_ID.get() == "web"
    plan.apply_runtime.assert_not_called()
    cleared = await producer.start(request("clear-context", channel_id="native"), policy=native_policy())
    await cleared.work.before_effect(SimpleNamespace())
    assert TOOL_PERMISSION_CONTEXT.get() is None
    assert TOOL_PERMISSION_CHANNEL_ID.get() == "native"


@pytest.mark.parametrize("field", [
    "binding_id", "session_id", "sdk_session_id", "channel_id", "request_id", "mode", "project_dir",
    "origin", "tool_policy", "model_identity", "model_config_version",
])
async def test_changed_descriptor_is_rejected_without_effects(producer, field):
    plan = await producer.start(policy=native_policy())
    context = plan.work.run_context()
    context["extra"]["jiuwenswarm_execution"][field] = "different"
    with pytest.raises(ExecutionContextUnavailable):
        producer.hub.resolve_work_context(sdk_agent=plan.sdk_agent, session_id=plan.sdk_session_id,
            run_context=context)
    plan.apply_runtime.assert_not_called()
    plan.work.policy.before_effect.assert_not_called()
    assert plan.entry.sequence == 0


async def test_wrong_sdk_agent_session_or_source_metadata_rejects(producer):
    plan = await producer.start()
    for agent, session_id in [(object(), plan.sdk_session_id), (plan.sdk_agent, "wrong-sdk-session")]:
        with pytest.raises(ExecutionContextUnavailable, match="CONTEXT_MISMATCH"):
            producer.hub.resolve_work_context(sdk_agent=agent, session_id=session_id,
                run_context=plan.work.run_context())
    context = plan.work.run_context()
    context["extra"]["source_metadata"]["source_origin_request_id"] = "other"
    with pytest.raises(ExecutionContextUnavailable, match="CONTEXT_MISMATCH"):
        producer.hub.resolve_work_context(sdk_agent=plan.sdk_agent, session_id=plan.sdk_session_id,
            run_context=context)
    with pytest.raises(ExecutionContextUnavailable, match="OWNER_MISMATCH"):
        producer.hub._prepare_work(plan.entry, sdk_agent=object(), session_id=plan.sdk_session_id,
            apply_runtime=Mock(), permission_context=None)


async def test_outside_context_and_unknown_bindings_never_gain_authority(producer):
    assert prepare_current_work(sdk_agent=object(), session_id="sdk-session", apply_runtime=Mock()) is None
    assert current_execution_policy() is None
    assert current_output_observer(object()) is None
    assert current_output_work({"content": "legacy"}) is None
    with pytest.raises(ExecutionContextUnavailable, match="OWNER_UNAVAILABLE"):
        current_output_work({"source_binding_id": "forged"})
    for context in ({"extra": {"jiuwenswarm_execution": {"binding_id": "unknown"}}},
                    {"extra": {"jiuwenswarm_execution": []}}):
        with pytest.raises(ExecutionContextUnavailable):
            producer.hub.resolve_work_context(sdk_agent=object(), session_id="sdk-session", run_context=context)


@pytest.mark.parametrize("changed", [
    {"source_binding_id": "unknown"}, {"source_origin_request_id": "other"},
    {"source_session_id": "other"}, {"source_task_id": ""}, {"source_run_kind": "other"},
    {"source_request_id": "other"}, {"source_goal_id": "unexpected"}, {"source_goal_revision": 1},
])
async def test_invalid_projected_source_has_zero_record_authority(producer, changed):
    plan = await producer.start()
    await plan.queue.put(source(plan.work, **changed))
    await producer.settle(plan)
    assert plan.entry.stream_outcome == "failed"
    assert plan.entry.sequence == 0
    assert producer.validated == []


@pytest.mark.parametrize("changed", [
    {"source_goal_revision": True}, {"source_goal_revision": 0},
    {"source_goal_id": ""}, {"source_request_id": "unrelated-request"},
])
async def test_invalid_goal_source_cannot_borrow_record_authority(producer, changed):
    plan = await producer.start()
    await plan.queue.put(source(plan.work, kind="goal", **changed))
    await producer.settle(plan)
    assert plan.entry.stream_outcome == "failed"
    assert plan.entry.sequence == 0
    assert producer.validated == []


@pytest.mark.parametrize("borrower_origin", ["native", "text"])
async def test_earlier_reader_accepts_borrowed_origin_without_relabelling_and_survives_eof(producer, borrower_origin):
    sdk_agent = object()
    reader = await producer.start(request("reader"), sdk_agent=sdk_agent, token="shared",
        policy=native_policy() if borrower_origin == "text" else None)
    borrower = await producer.start(request("borrower", channel_id="native"), sdk_agent=sdk_agent,
        token="shared", acquired=False, short=True,
        policy=native_policy() if borrower_origin == "native" else None)
    await producer.settle(borrower)
    assert borrower.entry.stream_closed and borrower.entry.stream_outcome == "ended"
    assert not reader.entry.stream_closed
    assert producer.hub.resolve_work_context(sdk_agent=sdk_agent, session_id="sdk-session",
        run_context=borrower.work.run_context()) is borrower.work
    await reader.queue.put(source(borrower.work, kind="goal"))

    async def published():
        while reader.entry.sequence == 0:
            await asyncio.sleep(0)

    await asyncio.wait_for(published(), 2)
    assert producer.validated == [borrower.work]
    assert producer.validated[0].policy.origin == borrower_origin
    assert reader.entry.events[0][2]["payload"]["source_origin_request_id"] == "borrower"


@pytest.mark.parametrize("cancel", [False, True])
async def test_borrowed_binding_cannot_be_evicted_until_owner_ends_and_never_revives(producer, cancel):
    producer.hub.max_records = producer.hub.max_active = 2
    sdk_agent = object()
    reader = await producer.start(request("reader"), sdk_agent=sdk_agent, token="shared")
    borrower = await producer.start(request("borrower"), sdk_agent=sdk_agent,
        token="shared", acquired=False, short=True, policy=native_policy())
    await producer.settle(borrower)
    with pytest.raises(SessionExecutionUnavailable, match="CAPACITY"):
        producer.hub.start(producer, request("capacity-attempt"))
    assert len(producer.calls) == 2
    assert producer.hub.resolve_work_context(sdk_agent=sdk_agent, session_id="sdk-session",
        run_context=borrower.work.run_context()) is borrower.work
    if cancel:
        producer.hub._cancel(reader.entry)
    else:
        await reader.queue.put(None)
        await producer.settle(reader)
    with pytest.raises(ExecutionContextUnavailable, match="BINDING_CLOSED"):
        producer.hub.resolve_work_context(sdk_agent=sdk_agent, session_id="sdk-session",
            run_context=borrower.work.run_context())
    assert not borrower.work.accepts_source(source(borrower.work, kind="goal"))
    await producer.settle(reader)
    replacement = await producer.start(request("replacement"), sdk_agent=sdk_agent, token="shared")
    assert replacement.entry.output_owner is replacement.entry
    with pytest.raises(ExecutionContextUnavailable):
        producer.hub.resolve_work_context(sdk_agent=sdk_agent, session_id="sdk-session",
            run_context=borrower.work.run_context())
    assert len(producer.calls) == 3


async def test_foreign_reader_cannot_observe_a_valid_binding(producer):
    first = await producer.start(request("first"))
    other = await producer.start(request("other"))
    await other.queue.put(source(first.work))
    await producer.settle(other)
    assert other.entry.stream_outcome == "failed"
    assert other.entry.sequence == 0
    assert first.entry.sequence == 0
    assert producer.validated == []


async def test_wrong_sdk_instance_cannot_borrow_other_sdk_output_owner(producer):
    reader_sdk, wrong_sdk = object(), object()
    reader = await producer.start(request("reader"), sdk_agent=reader_sdk, token="shared")
    borrower = await producer.start(request("borrower"), sdk_agent=wrong_sdk,
        sdk_session_id="wrong-sdk-session", observer_agent=reader_sdk,
        token="shared", acquired=False, short=True, policy=native_policy())
    await producer.settle(borrower)
    assert borrower.entry.stream_outcome == "failed"
    assert borrower.entry.output_owner is None
    with pytest.raises(ExecutionContextUnavailable):
        producer.hub.resolve_output_work(reader.entry, source(borrower.work, kind="goal"))
    assert reader.entry.sequence == 0


async def test_same_sdk_instance_other_session_cannot_borrow_output_owner(producer):
    sdk_agent = object()
    reader = await producer.start(request("reader"), sdk_agent=sdk_agent, token="shared")
    borrower = await producer.start(request("borrower"), sdk_agent=sdk_agent,
        sdk_session_id="wrong-sdk-session", token="shared", acquired=False, short=True, policy=native_policy())
    await producer.settle(borrower)
    assert borrower.entry.stream_outcome == "failed"
    assert borrower.entry.output_owner is None
    with pytest.raises(ExecutionContextUnavailable):
        producer.hub.resolve_output_work(reader.entry, source(borrower.work, kind="goal"))
    assert reader.entry.sequence == 0
