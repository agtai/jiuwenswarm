# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Real Registry/parser/confirmation/SQLite; controlled model, not audio evidence."""

import json
import asyncio
import hashlib
import time
import inspect
import sqlite3
from datetime import UTC, datetime
from dataclasses import replace
from types import SimpleNamespace

import pytest
import pytest_asyncio

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    TurnCommitLedger,
    ResponseRef,
)
from jiuwenswarm.server.live_voice.native_interaction_config import (
    InteractionEngineKind,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NativeInteractionBinding,
)
from jiuwenswarm.server.live_voice.p3_confirmation import BoundedP3ConfirmationOwner
from jiuwenswarm.server.live_voice.p3_product_confirmation import (
    ProductP3ConfirmationForwarder,
)
from jiuwenswarm.server.live_voice.product_composition_registry import (
    AgentServerProductCompositionRegistry,
    ProductCompositionSettings,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
)
from tests.unit_tests.live_voice.test_p3_authenticated_composition import (
    _harness,
    _scope,
    _production_registry_text_params,
    _stop_test_reconciliation_worker,
    P3_PRODUCT_AUTHORITY_OPERATIONS,
    TOKEN,
)
from tests.unit_tests.live_voice.test_product_composition_registry import (
    _AgentManager,
    _native_propose_params,
    _native_turn_proposal,
    _native_speak_proposal,
    _native_delegate_proposal,
)


def model_output(
    data, *, operation=None, arguments=None, target=None, reference=None, route=None
):
    arguments = arguments or {}
    fields = (
        ["dialogue"]
        if operation is None
        else [
            "operation",
            *[f"arguments.{key}" for key in arguments],
            *(["target"] if target else []),
        ]
    )
    return {
        "route": route or ("task" if operation else "dialogue"),
        "operation": operation,
        "arguments": arguments,
        "target": target,
        "target_kind": "task_id" if target else None,
        "message": None,
        "reference_id": None if reference is None else reference["id"],
        "reference_version": None if reference is None else reference["version"],
        "continuation_action": None if reference is None else "confirm",
        "extractions": [
            {
                "field_name": field,
                "source_start": 0,
                "source_end": len(data["commit"]["text"]),
            }
            for field in fields
        ],
    }


@pytest_asyncio.fixture
async def semantic_runtime(tmp_path, monkeypatch, request):
    commits = TurnCommitLedger()
    harness = _harness(
        tmp_path,
        commit_ledger=commits,
        clock=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        expires_at="2035-01-01T00:00:00Z",
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS | frozenset({"agent.chat"}),
    )
    harness.authority.contexts = {
        key: replace(value, expires_at="2035-01-01T00:00:00Z")
        for key, value in harness.authority.contexts.items()
    }
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    manager = _AgentManager()
    state = SimpleNamespace(
        calls=[],
        program=lambda data: model_output(data),
        manager=manager,
        harness=harness,
    )

    async def push(_message):
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=True,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
            interaction_engine=InteractionEngineKind(
                getattr(request, "param", "cascade")
            ),
        ),
        p3_composition=harness.composition,
        agent_manager=manager,
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commits,
    )
    state.registry = registry

    class Model:
        async def invoke(self, **kwargs):
            assert kwargs["tools"] == []
            data = json.loads(kwargs["messages"][1].content)
            state.calls.append(data)
            output = state.program(data)
            if inspect.isawaitable(output):
                output = await output
            return SimpleNamespace(content=json.dumps(output), tool_calls=[])

    original = harness.models.resolve
    monkeypatch.setattr(
        harness.models,
        "resolve",
        lambda *a, **kw: replace(original(*a, **kw), model=Model()),
    )

    async def text(stem, content):
        return await registry.handle_p3_intent(
            params=_production_registry_text_params(stem=stem, text=content),
            request_id=stem,
            session_id="session-1",
        )

    state.text = text
    try:
        yield state
    finally:
        await registry.stop()
        await harness.composition.stop()


async def control_with_confirmation(s, stem, operation, arguments=None, target=None):
    def program(data):
        pending = data["context"]["pending"]
        return model_output(
            data,
            operation=operation,
            arguments=arguments,
            target=target,
            reference=pending[0] if pending else None,
        )

    s.program = program
    proposed = await s.text(
        stem, f"Execute {operation} for the stated exact task and specification."
    )
    assert (
        proposed.ok
        and proposed.payload["result"]["reason"] == "TASK_CONFIRMATION_REQUIRED"
    ), proposed.payload
    confirmed = await s.text(stem + "-confirm", "Confirm the exact proposed operation.")
    assert confirmed.ok, confirmed.payload
    return confirmed.payload["result"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_first", [False, True])
async def test_explicit_local_delegation_creates_once_with_normal_authority(semantic_runtime, invalid_first):
    s = semantic_runtime
    def program(data):
        assert s.harness.composition._core.store.counts()["tasks"] == 0
        assert s.manager.get_calls == []
        assert data["commit"]["text"] == text
        assert data["context"]["tasks"] == []
        return {**model_output(data, operation="task.create", arguments={
            "name": "Equipment report", "instruction": "Read the equipment list and save report.md."}),
            "requested_work": "local_artifacts",
            "continuation_action": "accept_proposal" if invalid_first and len(s.calls) == 1 else None}
    s.program = program
    text = "Prepare an equipment report in the background. Do not purchase or send anything."
    done = await s.text("local-delegate", text)
    assert done.ok and done.payload["result"]["status"] == "dispatched", done.payload
    task_id = done.payload["result"]["task_id"]
    task = s.harness.composition._core.store.get_task(task_id, _scope())
    assert text in task.spec.instruction
    assert s.harness.composition._core.store.counts()["tasks"] == 1
    assert s.registry._pending_production_task_intents == {}
    assert await s.registry._semantic_continuity.pending(_scope()) == ()
    replay = await s.text("local-delegate", text)
    assert replay.payload == done.payload
    assert s.harness.composition._core.store.counts()["tasks"] == 1
    assert s.manager.get_calls == []
    assert len(s.calls) == (2 if invalid_first else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("route,text", [
    ("dialogue", "Read the project information and compare the options; do not create a task."),
    ("clarification", "Do that work in the background."),
])
async def test_non_task_semantics_have_zero_task_effects_and_replay(semantic_runtime, route, text):
    s = semantic_runtime
    before = s.harness.composition._core.store.counts()
    s.program = lambda data: {
        **model_output(data, route=route),
        "message": "Which work do you mean?" if route == "clarification" else None,
    }
    result = await s.text("no-task", text)
    assert result.ok, result.payload
    replay = await s.text("no-task", text)
    assert replay.payload == result.payload
    assert s.harness.composition._core.store.counts() == before
    assert s.harness.executor.dispatches == s.harness.executor.cancels == s.harness.executor.adjustments == []
    assert s.manager.get_calls == [] and s.manager.agent.calls == 0 and len(s.calls) == 1
    assert s.registry._pending_production_task_intents == {}
    assert s.registry._voice_task_origins == {}


@pytest.mark.asyncio
async def test_persistent_invalid_continuation_has_zero_effects_and_replays_rejection(semantic_runtime):
    s = semantic_runtime
    before = s.harness.composition._core.store.counts()
    s.program = lambda data: {**model_output(data, operation="task.create", arguments={
        "name": "Equipment report", "instruction": "Save report.md."}),
        "requested_work": "local_artifacts", "continuation_action": "accept_proposal"}
    text = "Prepare the equipment report in the background."
    rejected = await s.text("bad-continuation", text)
    assert not rejected.ok and rejected.payload["error"]["reason"] == "SEMANTIC_OUTPUT_INVALID"
    replay = await s.text("bad-continuation", text)
    assert replay.payload == rejected.payload and len(s.calls) == 2
    assert s.harness.composition._core.store.counts() == before
    assert s.manager.get_calls == [] and s.manager.agent.calls == 0
    assert s.registry._pending_production_task_intents == {}
    assert await s.registry._semantic_continuity.pending(_scope()) == ()


@pytest.mark.asyncio
async def test_local_delegation_requires_current_supported_executor(semantic_runtime, monkeypatch):
    s = semantic_runtime
    s.program = lambda data: {**model_output(data, operation="task.create", arguments={
        "name": "Report", "instruction": "Save report.md."}), "requested_work": "local_artifacts"}
    from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
    from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode
    def deny(_resolution):
        raise FormalTaskViolation("LOCAL_ARTIFACT_DELEGATION_CAPABILITY_REQUIRED", "not supported", ErrorCode.PERMISSION_DENIED)
    monkeypatch.setattr(s.harness.composition, "require_local_artifact_delegation_capability", deny)
    rejected = await s.text("local-denied", "Draft the report in the background.")
    assert not rejected.ok
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    assert s.registry._pending_production_task_intents == {}
    assert s.manager.get_calls == []


@pytest.mark.asyncio
async def test_unowned_requirement_source_has_zero_core_and_agent_effects(semantic_runtime):
    s = semantic_runtime
    s.program = lambda data: {**model_output(data, operation="task.create", arguments={
        "name": "Report", "instruction": "Save report.md."}),
        "requested_work": "local_artifacts", "requirement_source_ids": ["another-session-user"]}
    before = s.harness.composition._core.store.counts()
    rejected = await s.text("source-rejected", "Prepare the report in the background.")
    assert not rejected.ok
    assert s.harness.composition._core.store.counts() == before
    assert s.registry._pending_production_task_intents == {}
    assert s.manager.get_calls == []


@pytest.mark.asyncio
async def test_spoken_presentation_is_generic_and_does_not_remove_task_authority(
    semantic_runtime,
):
    s = semantic_runtime
    activation = await s.registry.handle_p2_activate(
        params=p2_params(),
        request_id="style-activate",
        session_id="session-1",
        channel_id="web",
    )
    assert activation.ok
    result = await s.registry.handle_unified_submit(
        params=voice_final(
            "spoken-style",
            "Analyse the project material and explain the essential findings.",
        ),
        request_id="spoken-style",
        session_id="session-1",
        channel_id="web",
    )
    assert result.ok, result.payload
    await asyncio.wait_for(s.manager.agent.wait_for_calls(1), 2)
    execution = s.manager.agent.executions[-1]
    prompt = json.loads(execution.prompt_content())
    assert prompt["presentation_contract"]["medium"] == "spoken_conversation"
    assert (
        "unless the user explicitly requests a detailed spoken"
        in prompt["presentation_contract"]["required_behavior"]
    )
    assert "400" in prompt["presentation_contract"]["required_behavior"]
    assert (
        "Requested saved artifacts remain complete"
        in prompt["presentation_contract"]["required_behavior"]
    )
    assert (
        prompt["committed_turn"]["text"]
        == "Analyse the project material and explain the essential findings."
    )
    assert execution.allow_tools is True
    assert s.harness.composition._core.store.counts()["tasks"] == 0


@pytest.mark.asyncio
async def test_model_exact_multitask_control_uses_real_store_and_formal_confirmation(
    semantic_runtime,
):
    s = semantic_runtime
    store, core, executor = (
        s.harness.composition._core.store,
        s.harness.composition._core,
        s.harness.executor,
    )
    a = (
        await control_with_confirmation(
            s,
            "create-a",
            "task.create",
            {"name": "设备核查甲", "instruction": "检查库存并保存 audit-a.md。"},
        )
    )["task_id"]
    b = (
        await control_with_confirmation(
            s,
            "create-b",
            "task.create",
            {"name": "维护核查乙", "instruction": "检查维护并保存 audit-b.md。"},
        )
    )["task_id"]
    assert (
        a != b
        and store.get_task(a, _scope()).attempt_id
        != store.get_task(b, _scope()).attempt_id
    )
    await core.drain_outbox()
    assert (
        store.get_task(a, _scope()).state.value
        == store.get_task(b, _scope()).state.value
        == "running"
    ), store.events(a, _scope(), after_seq=-1)
    for target in (a, b):
        s.program = lambda data: model_output(
            data,
            operation="task.status",
            arguments={"query_kind": "status"},
            target=target,
        )
        counts = store.counts()
        status = await s.text("query-" + target, "请报告所指定任务的真实状态。")
        assert status.ok, status.payload
        assert status.payload["result"]["task_id"] == target
        assert store.counts() == counts
    b_before = store.get_task(b, _scope())
    adjustment = await control_with_confirmation(
        s, "adjust-a", "task.adjust", {"adjustment": "不采购，增加缺失设备核对。"}, a
    )
    assert adjustment["task_id"] == a
    assert adjustment["formal_task_result"]["adjustment_state"] == "pending", adjustment
    assert executor.adjustments == []
    assert store.get_task(b, _scope()) == b_before
    await core.drain_outbox()
    await core.drain_inflight_adjustments()
    assert len(executor.adjustments) == 1
    a_events = store.events(a, _scope(), after_seq=-1)
    assert [
        e.event_type for e in a_events if e.event_type.startswith("task.adjust_")
    ] == ["task.adjust_requested", "task.adjust_applied"]
    assert store.get_task(b, _scope()) == b_before
    before = store.counts()
    s.program = lambda data: model_output(data, operation="task.cancel", target=b)
    proposal = await s.text("cancel-b", "只取消维护核查乙，设备核查甲继续。")
    assert (
        proposal.ok
        and proposal.payload["result"]["reason"] == "TASK_CONFIRMATION_REQUIRED"
    ), proposal.payload
    assert (
        not store.get_task(a, _scope()).cancel_requested
        and not store.get_task(b, _scope()).cancel_requested
    )
    assert executor.cancels == [] and store.counts() == before
    s.program = lambda data: model_output(
        data, operation="task.cancel", target=b, reference=data["context"]["pending"][0]
    )
    a_before = store.get_task(a, _scope())
    confirmed = await s.text("cancel-b-confirm", "确认仅取消维护核查乙。")
    assert confirmed.ok, confirmed.payload
    assert store.get_task(b, _scope()).cancel_requested
    assert store.get_task(a, _scope()) == a_before
    await core.drain_outbox()
    assert store.get_task(b, _scope()).outcome.value == "cancelled"
    assert store.get_task(a, _scope()) == a_before
    assert executor.cancels == [b_before.attempt_id]
    assert s.manager.agent.calls == 0  # text controls do not call a business Agent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "negated-create",
        "negated-cancel",
        "missing-proposal",
        "ambiguous-target",
        "malformed",
        "tool-request",
        "unknown-target",
        "unknown-adjustment-target",
    ],
)
async def test_controlled_semantic_negative_has_zero_protected_effects(
    semantic_runtime, case
):
    s = semantic_runtime

    def program(data):
        if case == "malformed":
            return {"route": "task"}
        if case == "tool-request":
            return {**model_output(data), "tool_calls": [{"name": "delete"}]}
        if case == "unknown-target":
            return model_output(data, operation="task.cancel", target="not-visible")
        if case == "unknown-adjustment-target":
            return model_output(data, operation="task.adjust", target="not-visible",
                                arguments={"adjustment": "Keep the backup running."})
        output = model_output(data)
        if case in {"missing-proposal", "ambiguous-target"}:
            output.update(route="clarification", message="请明确要处理的事项或任务。")
        return output

    s.program = program
    inputs = {
        "negated-create": "不要创建任何任务。",
        "negated-cancel": "不要取消任务。",
        "missing-proposal": "就在后台处理吧。",
        "ambiguous-target": "把那个取消。",
    }
    before = s.harness.composition._core.store.counts()
    result = await s.text(case, inputs.get(case, "处理指定事项。"))
    if case in {"malformed", "tool-request", "unknown-target", "unknown-adjustment-target"}:
        assert not result.ok, result.payload
    else:
        assert result.ok, result.payload
    assert s.harness.composition._core.store.counts() == before
    assert (
        s.harness.executor.dispatches
        == s.harness.executor.cancels
        == s.harness.executor.adjustments
        == []
    )
    assert s.manager.agent.calls == 0
    assert s.registry._voice_task_origins == {}


@pytest.mark.asyncio
async def test_two_finals_cannot_issue_two_confirmations_from_one_proposal(
    semantic_runtime,
):
    s = semantic_runtime
    journal = s.registry._semantic_continuity.journal
    args = {"name": "设备报告", "instruction": "核查设备并保存 audit.md，不购买。"}
    issued_at = datetime.now(UTC).timestamp()
    journal.retain_semantic_context(
        scope=_scope(),
        kind="proposal",
        source_id="presented-analysis",
        payload={
            "operation": "task.create",
            "target": None,
            "target_kind": None,
            "arguments": args,
        },
        issued_at=issued_at,
        expires_at=issued_at + 100,
    )
    both = asyncio.Event()
    entered = 0

    async def program(data):
        nonlocal entered
        reference = data["context"]["pending"][0]
        if reference["kind"] == "proposal":
            entered += 1
            if entered == 2:
                both.set()
            await both.wait()
            output = model_output(
                data, operation="task.create", arguments=args, reference=reference
            )
            output["continuation_action"] = "accept_proposal"
            return output
        assert reference["kind"] == "confirmation"
        return model_output(
            data, operation="task.create", arguments=args, reference=reference
        )

    s.program = program
    outcomes = await asyncio.wait_for(
        asyncio.gather(
            s.text("accept-1", "就在后台做吧。"), s.text("accept-2", "好，在后台处理。")
        ),
        5,
    )
    assert sum(result.ok for result in outcomes) == 1, [r.payload for r in outcomes]
    pending = await s.registry._semantic_continuity.pending(_scope())
    assert len(pending) == 1 and pending[0]["kind"] == "confirmation"
    assert len(s.registry._pending_production_task_intents) == 1, pending
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    confirmed = await s.text("confirm-winner", "确认执行。")
    assert confirmed.ok, confirmed.payload
    assert s.harness.composition._core.store.counts()["tasks"] == 1
    assert await s.registry._semantic_continuity.pending(_scope()) == ()


def p2_params(**changes):
    params = {
        "auth_token": TOKEN,
        "session_id": "session-1",
        "correlation_id": "semantic-voice",
        "interaction_id": "semantic-interaction",
        "activation_id": "semantic-activation",
        "activation_generation": 1,
    }
    params.update(changes)
    return params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "create_source,confirm_source",
    [
        ("structured", "structured"),
        ("structured", "text"),
        ("text", "structured"),
    ],
)
async def test_cross_entrypoint_confirmation_consumes_durable_context_once(
    semantic_runtime,
    create_source,
    confirm_source,
):
    s = semantic_runtime
    args = {
        "name": "设备核查",
        "instruction": "读取设备资料并保存 inventory.md；不采购。",
    }
    creating = True

    def program(data):
        pending = data["context"]["pending"]
        if creating:
            return model_output(data, operation="task.create", arguments=args)
        if pending:
            return model_output(
                data, operation="task.create", arguments=args, reference=pending[0]
            )
        output = model_output(data, route="clarification")
        output["message"] = "没有待确认操作，请说明想做什么。"
        return output

    s.program = program
    structured = {
        "auth_token": TOKEN,
        "session_id": "session-1",
        "correlation_id": "cross-entry",
        "source": "structured",
        "source_id": "cross-create",
        "structured_intent": {
            "operation": "task.create",
            "target": None,
            "arguments": args,
        },
    }
    proposed = (
        await s.text("cross-create", "后台核查设备，生成报告，不采购。")
        if create_source == "text"
        else await s.registry.handle_p3_intent(
            params=structured, request_id="cross-create", session_id="session-1"
        )
    )
    assert proposed.ok, proposed.payload
    token = proposed.payload["result"]["confirmation_token"]
    creating = False
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    confirmed = (
        await s.text("cross-confirm", "确认按这个执行。")
        if confirm_source == "text"
        else await s.registry.handle_p3_intent(
            params={**structured, "continuation_id": token},
            request_id="cross-confirm",
            session_id="session-1",
        )
    )
    assert confirmed.ok, confirmed.payload
    before = s.harness.composition._core.store.counts()
    assert before["tasks"] == 1
    assert s.registry._pending_production_task_intents == {}
    assert await s.registry._semantic_continuity.pending(_scope()) == ()
    for stem in ("late-confirm", "later-confirm"):
        reply = await s.text(stem, "确认刚才的任务。")
        assert reply.ok and reply.payload["result"]["operation"] is None, reply.payload
        assert s.harness.composition._core.store.counts() == before
        assert s.registry._pending_production_task_intents == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cause", ["UNAVAILABLE", "INTERNAL", "RESULT_UNKNOWN", "CONFLICT"]
)
async def test_confirmed_core_outcome_keeps_unknown_distinct_from_rejection(
    semantic_runtime, monkeypatch, cause
):
    from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode
    from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
    from jiuwenswarm.server.live_voice.persistent_task_core import _failure

    s = semantic_runtime
    params = {
        "auth_token": TOKEN,
        "session_id": "session-1",
        "correlation_id": "unknown-core",
        "source": "structured",
        "source_id": "unknown-core-create",
        "structured_intent": {
            "operation": "task.create",
            "target": None,
            "arguments": {
                "name": "Equipment review",
                "instruction": "Save the equipment review.",
            },
        },
    }
    proposed = await s.registry.handle_p3_intent(
        params=params, request_id="unknown-propose", session_id="session-1"
    )
    assert proposed.ok, proposed.payload
    core = s.harness.composition._core
    execute = core.execute
    effects = []

    def uncertain(command, authorization, *, now, **kwargs):
        if cause != "CONFLICT":
            result = execute(command, authorization, now=now, **kwargs)
            assert result.ok
            effects.append(result)
        return _failure(
            command,
            FormalTaskViolation(
                "CONTROLLED_CORE_FAILURE", "controlled test failure", ErrorCode(cause)
            ),
            observed_at=now,
        )

    monkeypatch.setattr(core, "execute", uncertain)
    confirmed_params = {
        **params,
        "continuation_id": proposed.payload["result"]["confirmation_token"],
    }
    reply = await s.registry.handle_p3_intent(
        params=confirmed_params, request_id="unknown-confirm", session_id="session-1"
    )
    expected = "CONFLICT" if cause == "CONFLICT" else "RESULT_UNKNOWN"
    assert not reply.ok and reply.payload["error"]["code"] == expected, reply.payload
    counts = core.store.counts()
    assert counts["tasks"] == len(effects) == (0 if cause == "CONFLICT" else 1)
    replay = await s.registry.handle_p3_intent(
        params=confirmed_params, request_id="unknown-confirm", session_id="session-1"
    )
    assert replay.payload == reply.payload and core.store.counts() == counts
    assert len(effects) == (0 if cause == "CONFLICT" else 1)
    assert s.calls == [] and s.manager.agent.calls == 0


def voice_final(stem, text):
    params = p2_params(
        turn_id=f"turn-{stem}",
        commit_id=f"commit-{stem}",
        text=text,
        input_state="final",
        committed_at="2026-09-03T00:00:00Z",
    )
    params["gateway_voice_claim"] = {
        "kind": "formal_speech_recognition",
        "speech_operation_id": f"speech-{stem}",
        "capture_id": f"capture-{stem}",
        "capture_generation": 1,
        "session_id": params["session_id"],
        "correlation_id": params["correlation_id"],
        "interaction_id": params["interaction_id"],
        "turn_id": params["turn_id"],
        "commit_id": params["commit_id"],
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "critical_policy": "eligible",
    }
    return params


@pytest.mark.asyncio
async def test_cascade_committed_final_uses_model_then_real_agent_and_freezes_replay(
    semantic_runtime,
):
    s = semantic_runtime
    activation = await s.registry.handle_p2_activate(
        params=p2_params(),
        request_id="activate",
        session_id="session-1",
        channel_id="web",
    )
    assert activation.ok, activation.payload
    params = voice_final(
        "analysis", "先读一下项目资料，分析设备现状，暂时不要在后台执行。"
    )
    submitted = await s.registry.handle_unified_submit(
        params=params,
        request_id="voice-analysis",
        session_id="session-1",
        channel_id="web",
    )
    assert submitted.ok, submitted.payload
    await asyncio.wait_for(s.manager.agent.wait_for_calls(1), 2)
    assert s.manager.agent.executions[0].allow_tools
    assert len(s.calls) == 1 and s.calls[0]["commit"]["text"] == params["text"]
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    replay = await s.registry.handle_unified_submit(
        params=params,
        request_id="voice-analysis",
        session_id="session-1",
        channel_id="web",
    )
    assert replay.payload == submitted.payload
    assert len(s.calls) == s.manager.agent.calls == 1


async def present_next(s, sequence):
    for _ in range(8):
        sequence += 1
        polled = await asyncio.wait_for(
            s.registry.handle_p2_notification_next(
                params=p2_params(notification_sequence=sequence),
                request_id=f"poll-{sequence}",
                session_id="session-1",
            ),
            2,
        )
        assert polled.ok, polled.payload
        notification = polled.payload["result"]
        unit = notification.get("presentation_unit")
        if not unit:
            continue
        response = notification["response"]
        ack = await s.registry.handle_p2_presentation_ack(
            params=p2_params(
                response_id=response["response_id"],
                response_generation=response["response_generation"],
                surface=unit["surface"],
                unit_id=unit["unit_id"],
                contiguous_cursor=unit["seq"],
                presented_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            ),
            request_id=f"ack-{sequence}",
            session_id="session-1",
        )
        assert ack.ok, ack.payload
        return sequence
    raise AssertionError("No actual presentation unit")


def typed_final(stem, text):
    params = voice_final(stem, text)
    params.pop("gateway_voice_claim")
    return {**params, "input_kind": "text"}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["task.status", "task.adjust", "task.cancel"])
@pytest.mark.parametrize("measurement_available", [True, False])
async def test_unified_task_measurement_keeps_exact_receipt_and_admission_clock(
    semantic_runtime, monkeypatch, operation, measurement_available
):
    from jiuwenswarm.server.live_voice import product_composition_registry as module

    s = semantic_runtime
    task_id = (
        await control_with_confirmation(
            s,
            "l0-create",
            "task.create",
            {"name": "Inventory", "instruction": "Read inventory and save audit.md."},
        )
    )["task_id"]
    core = s.harness.composition._core
    await core.drain_outbox()
    task = core.store.get_task(task_id, _scope())
    arguments = {
        "task.status": {"query_kind": "status"},
        "task.adjust": {"adjustment": "Check missing entries without purchases."},
        "task.cancel": {},
    }[operation]
    s.program = lambda data: model_output(
        data,
        operation=operation,
        arguments=arguments,
        target=task_id,
        reference=next(iter(data["context"]["pending"]), None),
    )
    if operation != "task.status":
        proposed = await s.text(
            "l0-proposal", "Please perform the exact proposed control."
        )
        assert (
            proposed.ok
            and proposed.payload["result"]["reason"] == "TASK_CONFIRMATION_REQUIRED"
        )
    records, handler_times = [], []
    original = s.harness.composition.handle_production_resolution

    async def observed_handler(**kwargs):
        handler_times.append(time.monotonic() * 1000)
        return await original(**kwargs)

    monkeypatch.setattr(
        s.harness.composition, "handle_production_resolution", observed_handler
    )
    monkeypatch.setattr(
        module, "emit_runtime_l0_milestone", lambda **kwargs: records.append(kwargs)
    )
    if not measurement_available:
        monkeypatch.setattr(module, "_best_effort_l0_binding", lambda **_kwargs: None)
    assert (
        await s.registry.handle_p2_activate(
            params=p2_params(),
            request_id="l0-activate",
            session_id="session-1",
            channel_id="web",
        )
    ).ok
    result = await s.registry.handle_unified_submit(
        params=voice_final("l0-status", "How is the inventory task progressing?"),
        request_id="l0-status",
        session_id="session-1",
        channel_id="web",
    )
    assert result.ok, result.payload
    commit_records = [
        r
        for r in records
        if r["milestone"] == module.L0Milestone.COMMITTED_SUBMIT_ACCEPTED
    ]
    assert len(commit_records) == (1 if measurement_available else 0)
    if measurement_available:
        record = commit_records[0]
        assert record["binding"].task_id == task_id
        assert record["binding"].attempt_id == task.attempt_id
        assert record["monotonic_ms"] <= handler_times[0]
        assert record["observed_at"] is not None and record["duration_ms"] >= 0
    current = core.store.get_task(task_id, _scope())
    assert current.attempt_id == task.attempt_id
    if operation == "task.status":
        assert current == task
    elif operation == "task.cancel":
        assert current.cancel_requested
    else:
        assert any(
            event.event_type == "task.adjust_requested"
            for event in core.store.events(task_id, _scope(), after_seq=-1)
        )


@pytest.mark.parametrize(
    "operation,payload",
    [
        (
            "task.adjust",
            {
                "task_id": "a",
                "attempt_id": "new",
                "adjustment_id": "x",
                "adjustment_state": "pending",
                "reason": None,
                "outbox_id": "o",
            },
        ),
        (
            "task.cancel",
            {
                "task_id": "a",
                "attempt_id": "new",
                "cancel_acknowledged": True,
                "applied": False,
                "state": "running",
                "outbox_id": "o",
            },
        ),
        (
            "task.status",
            {
                "task": {"task_id": "a", "attempt_id": "new", "state": "running"},
                "attempt": {"attempt_id": "new", "state": "running"},
            },
        ),
    ],
)
def test_measurement_identity_comes_only_from_canonical_return_not_old_selection(
    operation, payload
):
    identity = (
        AgentServerProductCompositionRegistry._formal_receipt_measurement_identity
    )
    assert identity(operation, "a", payload) == ("a", "new")
    assert identity(operation, "b", payload) == (None, None)
    assert identity(operation, None, payload) == (None, None)
    assert identity(operation, "a", {"task_id": "a", "attempt_id": "untrusted"}) == (
        None,
        None,
    )


@pytest.mark.asyncio
async def test_typed_final_uses_the_same_model_and_exact_once_journal(semantic_runtime):
    s = semantic_runtime
    assert (
        await s.registry.handle_p2_activate(
            params=p2_params(),
            request_id="activate",
            session_id="session-1",
            channel_id="web",
        )
    ).ok
    params = typed_final("typed", "Analyze the equipment records; do not delegate yet.")
    result = await s.registry.handle_unified_submit(
        params=params, request_id="typed", session_id="session-1", channel_id="web"
    )
    assert result.ok, result.payload
    await asyncio.wait_for(s.manager.agent.wait_for_calls(1), 2)
    assert s.calls[0]["commit"]["hypothesis_provenance"]["kind"] == "committed_text"
    before = s.harness.composition._core.store.counts()
    replay = await s.registry.handle_unified_submit(
        params=params, request_id="typed", session_id="session-1", channel_id="web"
    )
    assert replay.payload == result.payload
    assert len(s.calls) == s.manager.agent.calls == 1
    assert before["tasks"] == 0 and s.harness.composition._core.store.counts() == before
    assert not s.registry._voice_task_origins


@pytest.mark.asyncio
async def test_unified_typed_create_keeps_normal_confirmation_and_no_voice_association(
    semantic_runtime,
):
    s = semantic_runtime
    arguments = {
        "name": "Equipment report",
        "instruction": "Read the project equipment facts and save findings.md; do not buy anything.",
    }
    s.program = lambda data: model_output(
        data,
        operation="task.create",
        arguments=arguments,
        reference=next(iter(data["context"]["pending"]), None),
    )
    assert (
        await s.registry.handle_p2_activate(
            params=p2_params(),
            request_id="activate",
            session_id="session-1",
            channel_id="web",
        )
    ).ok
    proposed = await s.registry.handle_unified_submit(
        params=typed_final("create", "Prepare the equipment report in the background."),
        request_id="create",
        session_id="session-1",
        channel_id="web",
    )
    assert proposed.ok, proposed.payload
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    await present_next(s, 0)
    params = typed_final("confirm", "Confirm that exact task.")
    confirmed = await s.registry.handle_unified_submit(
        params=params, request_id="confirm", session_id="session-1", channel_id="web"
    )
    assert confirmed.ok, confirmed.payload
    assert "task_id" in confirmed.payload["result"], confirmed.payload
    task = s.harness.composition._core.store.get_task(
        confirmed.payload["result"]["task_id"], _scope()
    )
    assert (
        task.spec.name == arguments["name"]
        and task.spec.instruction == arguments["instruction"]
    )
    before = s.harness.composition._core.store.counts()
    replay = await s.registry.handle_unified_submit(
        params=params, request_id="confirm", session_id="session-1", channel_id="web"
    )
    assert (
        replay.payload == confirmed.payload
        and s.harness.composition._core.store.counts() == before
    )
    assert not s.registry._voice_task_origins


@pytest.mark.asyncio
async def test_task_notice_is_not_dialogue_and_control_ack_is_not_work_proposal(
    semantic_runtime,
):
    """Migrate the former synthetic-origin/context oracle to real creation."""
    s = semantic_runtime
    arguments = {
        "name": "Inventory audit",
        "instruction": "Read inventory facts and save inventory.md, no purchases.",
    }
    s.program = lambda data: model_output(
        data,
        operation="task.create",
        arguments=arguments,
        reference=next(iter(data["context"]["pending"]), None),
    )
    assert (
        await s.registry.handle_p2_activate(
            params=p2_params(),
            request_id="activate",
            session_id="session-1",
            channel_id="web",
        )
    ).ok
    sequence = 0
    for stem, content in (
        ("propose", "Prepare the inventory audit in the background."),
        ("confirm", "Confirm this exact task."),
    ):
        result = await s.registry.handle_unified_submit(
            params=voice_final(stem, content),
            request_id=stem,
            session_id="session-1",
            channel_id="web",
        )
        assert result.ok, result.payload
        sequence = await present_next(s, sequence)
    assert s.harness.composition._core.store.counts()["tasks"] == 1
    assert all(not execution.allow_tools for execution in s.manager.agent.executions)
    # A real conversational control reply is retained as conversation. An
    # unsolicited server status is not an Agent answer or a new work offer.
    runtime = s.registry._p2_routes[
        ("session-1", p2_params()["interaction_id"])
    ].activation_lease._runtime
    await runtime.present_authoritative_text(
        request_id="unsolicited-notice",
        response_id="unsolicited-response",
        correlation_id=p2_params()["correlation_id"],
        commit=replace(
            s.manager.agent.executions[-1].commit,
            commit_id="notice-commit",
            turn_id="notice-turn",
            text="server status",
        ),
        text="TASK_NOTIFICATION_CANARY",
        channel_id="web",
        _persist_user_history=False,
    )
    sequence = await present_next(s, sequence)
    s.program = lambda data: model_output(data)
    result = await s.registry.handle_unified_submit(
        params=voice_final("dialogue", "What is the purpose of an inventory?"),
        request_id="dialogue",
        session_id="session-1",
        channel_id="web",
    )
    assert result.ok, result.payload
    execution = s.manager.agent.executions[-1]
    assert execution.allow_tools
    assert [entry.content for entry in execution.context.entries] == [
        "Prepare the inventory audit in the background.",
        "formal result",
        "Confirm this exact task.",
        "formal result",
    ], "server notices contaminated the authorized conversation"
    assert s.harness.composition._core.store.counts()["tasks"] == 1
    assert not [
        entry
        for entry in s.calls[-1]["context"]["pending"]
        if entry["kind"] == "proposal"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"input_kind": "text", "gateway_voice_claim": {}},
        {
            "input_kind": "text",
            "supersedes_response": {"response_id": "old", "response_generation": 0},
        },
        {"input_kind": "unknown"},
        {"input_state": "partial"},
        {"dispatch_target": "agent"},
        {"dispatch_target": "task"},
    ],
)
async def test_unified_typed_ingress_rejects_mixed_provenance_or_client_route(
    semantic_runtime, extra
):
    s = semantic_runtime
    assert (
        await s.registry.handle_p2_activate(
            params=p2_params(),
            request_id="activate",
            session_id="session-1",
            channel_id="web",
        )
    ).ok
    before = s.harness.composition._core.store.counts()
    reply = await s.registry.handle_unified_submit(
        params={**typed_final("bad", "Create work."), **extra},
        request_id="bad",
        session_id="session-1",
        channel_id="web",
    )
    assert not reply.ok
    assert not s.calls and s.manager.agent.calls == 0
    assert s.harness.composition._core.store.counts() == before
    assert (
        not s.registry._accepted_turn_commits_by_commit
        and not s.registry._voice_task_origins
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["agent", "task"])
async def test_retired_public_p2_submit_has_zero_dispatch_or_origin(
    semantic_runtime, target
):
    s = semantic_runtime
    assert (
        await s.registry.handle_p2_activate(
            params=p2_params(),
            request_id="activate",
            session_id="session-1",
            channel_id="web",
        )
    ).ok
    before = s.harness.composition._core.store.counts()
    reply = await s.registry.handle_p2_submit(
        params={**voice_final("legacy", "Create work."), "dispatch_target": target},
        request_id="legacy",
        session_id="session-1",
        channel_id="web",
    )
    assert (
        not reply.ok and reply.payload["error"]["reason"] == "PRODUCT_P2_SUBMIT_RETIRED"
    )
    assert not s.calls and s.manager.agent.calls == 0
    assert s.harness.composition._core.store.counts() == before
    assert (
        not s.registry._accepted_turn_commits_by_commit
        and not s.registry._voice_task_origins
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,extra,omit,override",
    [
        ("missing-outbox", {}, {"outbox_id"}, None),
        ("empty-outbox", {"outbox_id": ""}, set(), None),
        ("whitespace-task", {"task_id": "   "}, set(), None),
        ("whitespace-attempt", {"attempt_id": "   "}, set(), None),
        ("whitespace-outbox", {"outbox_id": "   "}, set(), None),
        ("missing-state", {}, {"state"}, None),
        ("legacy-accepted-flag", {"accepted": True}, set(), None),
        ("unexpected-field", {"debug": "not-canonical"}, set(), None),
        ("non-mapping", {}, set(), "not-a-mapping"),
        ("wrong-state", {"state": "running"}, set(), None),
    ],
)
async def test_voice_create_bad_receipt_retains_unknown_without_origin_or_duplicate(
    semantic_runtime,
    monkeypatch,
    case,
    extra,
    omit,
    override,
):
    """Migrates the legacy nine receipt oracles through normal confirmation."""
    s = semantic_runtime
    args = {"name": "设备核查", "instruction": "核查设备资料并保存 inventory.md。"}
    s.program = lambda data: model_output(
        data,
        operation="task.create",
        arguments=args,
        reference=next(iter(data["context"]["pending"]), None),
    )
    assert (
        await s.registry.handle_p2_activate(
            params=p2_params(),
            request_id="activate",
            session_id="session-1",
            channel_id="web",
        )
    ).ok
    proposed = await s.registry.handle_unified_submit(
        params=voice_final("propose", "在后台核查设备并保存报告。"),
        request_id="propose",
        session_id="session-1",
        channel_id="web",
    )
    assert proposed.ok
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    await present_next(s, 0)
    original = s.harness.composition.handle_production_resolution
    dispatches = []

    async def corrupt(**kwargs):
        result = await original(**kwargs)
        dispatches.append(result)
        assert result.ok, result.payload
        changed = {**result.payload["result"], **extra}
        for key in omit:
            changed.pop(key, None)
        return replace(
            result,
            payload={
                **result.payload,
                "result": override if override is not None else changed,
            },
        )

    monkeypatch.setattr(s.harness.composition, "handle_production_resolution", corrupt)
    params = voice_final(f"confirm-{case}", "确认执行。")
    confirmed = await s.registry.handle_unified_submit(
        params=params,
        request_id=f"confirm-{case}",
        session_id="session-1",
        channel_id="web",
    )
    assert confirmed.ok, confirmed.payload
    assert "task_id" not in confirmed.payload["result"]
    assert s.registry._voice_task_origins == {}
    assert len(dispatches) == s.harness.composition._core.store.counts()["tasks"] == 1
    await asyncio.wait_for(s.manager.agent.wait_for_calls(2), 2)
    assert all(not execution.allow_tools for execution in s.manager.agent.executions)
    receipt_text = " ".join(
        entry.content for entry in s.manager.agent.executions[-1].context.entries
    )
    assert "TASK_CREATE_RECEIPT_INVALID" in receipt_text
    counts = s.harness.composition._core.store.counts()
    replay = await s.registry.handle_unified_submit(
        params=params,
        request_id=f"confirm-{case}",
        session_id="session-1",
        channel_id="web",
    )
    assert replay.payload == confirmed.payload
    assert len(dispatches) == 1 and s.harness.composition._core.store.counts() == counts


@pytest.mark.asyncio
async def test_cascade_presented_analysis_delegation_uses_one_call_and_original_requirements(
    semantic_runtime,
):
    s = semantic_runtime
    original = "请先读取资料，分析设备问题，周五前交付，维护计划不动。"
    delegated = "那就在后台处理吧，不采购，预算一千五。"
    s.manager.agent.final = "可以在后台核查库存和维护记录，生成 inventory.md。"

    def program(data):
        assert data["phase"] != "assistant_analysis", "old analysis must not trigger a second model pass"
        if data["commit"]["text"] == original:
            return model_output(data)
        history = data["context"]["history"]
        source = next(entry for entry in history if entry["role"] == "user")
        assert source["text"] == original
        assert any(entry["text"] == s.manager.agent.final for entry in history)
        assert data["context"]["pending"] == []
        return {
            **model_output(data, operation="task.create", arguments={
                "name": "设备核查", "instruction": "核查库存和维护记录，保存 inventory.md；不采购；预算1500元。",
            }),
            "requested_work": "local_artifacts",
            "requirement_source_ids": [source["source_id"]],
        }

    s.program = program
    activated = await s.registry.handle_p2_activate(
        params=p2_params(), request_id="activate", session_id="session-1", channel_id="web",
    )
    assert activated.ok
    submitted = await s.registry.handle_unified_submit(
        params=voice_final("analysis", original), request_id="analysis", session_id="session-1", channel_id="web",
    )
    assert submitted.ok, submitted.payload
    sequence = await present_next(s, 0)
    assert len(s.calls) == 1
    assert await s.registry._semantic_continuity.pending(_scope()) == ()
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    params = voice_final("accept", delegated)
    accepted = await s.registry.handle_unified_submit(
        params=params, request_id="accept", session_id="session-1", channel_id="web",
    )
    assert accepted.ok, accepted.payload
    assert len(s.calls) == 2, "the new input must resolve history and delegation in one call"
    assert s.harness.composition._core.store.counts()["tasks"] == 1
    created = accepted.payload["result"]["task_id"]
    saved = s.harness.composition._core.store.get_task(created, _scope()).spec
    assert original in saved.instruction
    assert "不采购" in saved.instruction and "1500" in saved.instruction
    replay = await s.registry.handle_unified_submit(
        params=params, request_id="accept", session_id="session-1", channel_id="web",
    )
    assert replay.payload == accepted.payload
    assert len(s.calls) == 2 and s.harness.composition._core.store.counts()["tasks"] == 1
    await present_next(s, sequence)
    assert not s.manager.agent.executions[-1].allow_tools


async def native_source(s):
    activated = await s.registry.handle_p2_activate(
        params=p2_params(interaction_engine="openai-realtime-native"),
        request_id="native-activate",
        session_id="session-1",
        channel_id="web",
    )
    assert activated.ok, activated.payload
    s.native_activation = activated.payload
    descriptor = activated.payload["result"]["_native_gateway"]
    binding = NativeInteractionBinding.from_dict(descriptor["binding"])
    capability = descriptor["capability"]
    for name, proposal in (
        ("turn", _native_turn_proposal(binding)),
        ("speak", _native_speak_proposal(binding)),
    ):
        result = await s.registry.handle_native_propose(
            params=_native_propose_params(binding, capability, proposal),
            request_id=f"native-{name}",
            session_id="session-1",
        )
        assert result.ok, result.payload
    return binding, capability, ResponseRef(**result.payload["result"]["response"])


async def native_next_source(s, binding, capability, ordinal):
    speak = _native_speak_proposal(binding)
    speak = replace(
        speak,
        action=replace(
            speak.action,
            action_id=f"native-action-speak-{ordinal}",
            payload=(("provider_response_id", f"provider-response-{ordinal}"),),
        ),
    )
    for label, proposal in (
        ("turn", _native_turn_proposal(binding, ordinal=ordinal)),
        ("speak", speak),
    ):
        result = await s.registry.handle_native_propose(
            params=_native_propose_params(binding, capability, proposal),
            request_id=f"native-{label}-{ordinal}",
            session_id="session-1",
        )
        assert result.ok, result.payload
    return ResponseRef(**result.payload["result"]["response"])


def native_delegate_params(binding, capability, response, text, ordinal=1):
    proposal = _native_delegate_proposal(binding, response, request_text=text)
    if ordinal != 1:
        delegate = replace(
            proposal.delegate,
            turn_id=f"native-turn-{ordinal}",
            provider_event_id=f"provider-function-event-{ordinal}",
            provider_call_id=f"provider-call-{ordinal}",
            provider_item_id=f"provider-function-item-{ordinal}",
        )
        proposal = replace(
            proposal,
            delegate=delegate,
            action=replace(
                proposal.action,
                action_id=f"native-action-delegate-{ordinal}",
                payload=(
                    ("provider_call_id", delegate.provider_call_id),
                    ("turn_id", delegate.turn_id),
                ),
            ),
        )
    return _native_propose_params(binding, capability, proposal)


@pytest.mark.asyncio
@pytest.mark.parametrize("semantic_runtime", ["openai-realtime-native"], indirect=True)
async def test_native_two_voice_turns_create_once_and_bind_real_origin(
    semantic_runtime,
):
    """Migrated native-create oracle: normal confirmation replaces Demo bypass."""
    s = semantic_runtime
    args = {
        "name": "设备核查",
        "instruction": "核查设备资料并保存 inventory.md，不采购。",
    }
    s.program = lambda data: model_output(
        data,
        operation="task.create",
        arguments=args,
        reference=next(iter(data["context"]["pending"]), None),
    )
    binding, capability, response = await native_source(s)
    first = native_delegate_params(
        binding, capability, response, "请在后台核查设备并保存报告。"
    )
    proposed = await s.registry.handle_native_propose(
        params=first, request_id="native-propose-work", session_id="session-1"
    )
    assert proposed.ok, proposed.payload
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    assert len(s.registry._pending_production_task_intents) == 1
    response = await native_next_source(s, binding, capability, 2)
    params = native_delegate_params(
        binding, capability, response, "确认这项设备核查。", 2
    )
    confirmed = await s.registry.handle_native_propose(
        params=params, request_id="native-confirm-work", session_id="session-1"
    )
    assert confirmed.ok, confirmed.payload
    assert confirmed.payload["result"]["route"] == "task"
    store = s.harness.composition._core.store
    assert store.counts()["tasks"] == 1
    assert store.counts()["attempts"] == 1 and store.counts()["commands"] == 1
    assert len(s.registry._voice_task_origins) == 1
    task_id, origin = next(iter(s.registry._voice_task_origins.items()))
    task = store.get_task(task_id, _scope())
    assert (
        task.spec.name == args["name"] and task.spec.instruction == args["instruction"]
    )
    assert task.state.value == "accepted" and not task.cancel_requested
    assert (
        s.harness.executor.dispatches
        == s.harness.executor.adjustments
        == s.harness.executor.cancels
        == []
    )
    assert origin.session_id == task.scope.session_id
    assert origin.interaction_id == binding.interaction_id
    assert task.spec.origin.commit_id is not None
    creation = s.registry._unified_journal.read_creation_origin(
        scope=task.scope,
        turn_id=task.spec.origin.turn_id,
        commit_id=task.spec.origin.commit_id,
    )
    assert (
        creation is not None
        and creation.hypothesis_provenance["source"]
        == "openai_realtime_native_delegate"
    )
    assert creation.hypothesis_provenance["native_turn_id"] == "native-turn-1"
    assert origin.response_ref == ResponseRef(**confirmed.payload["result"]["response"])
    assert s.manager.agent.calls == 2
    assert all(not execution.allow_tools for execution in s.manager.agent.executions)
    counts, calls = store.counts(), len(s.calls)
    replay = await s.registry.handle_native_propose(
        params=params, request_id="native-confirm-work", session_id="session-1"
    )
    assert replay.payload == confirmed.payload
    changed = native_delegate_params(
        binding, capability, response, "执行另一项工作。", 2
    )
    rejected = await s.registry.handle_native_propose(
        params=changed, request_id="changed-native-call", session_id="session-1"
    )
    assert (
        not rejected.ok
        and rejected.payload["error"]["reason"] == "NATIVE_DELEGATE_CALL_CONFLICT"
    )
    assert (
        store.counts() == counts
        and len(s.calls) == calls
        and s.manager.agent.calls == 2
    )
    runtime = s.registry._p2_routes[
        ("session-1", binding.interaction_id)
    ].activation_lease._runtime
    assert runtime.snapshot().queued_notifications == 0
    assert runtime.snapshot().conversation.presentation.records == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("semantic_runtime", ["openai-realtime-native"], indirect=True)
@pytest.mark.parametrize(
    "operation,arguments,state",
    [
        ("task.status", {"query_kind": "status"}, "running"),
        ("task.status", {"query_kind": "status"}, "terminal"),
        (
            "task.events",
            {"query_kind": "events", "after_seq": -1, "limit": 100},
            "running",
        ),
    ],
)
async def test_native_exact_task_reads_use_authoritative_receipt_without_business_tools(
    semantic_runtime,
    monkeypatch,
    operation,
    arguments,
    state,
):
    s = semantic_runtime
    core = s.harness.composition._core
    a = (
        await control_with_confirmation(
            s,
            "native-read-a",
            "task.create",
            {"name": "设备甲", "instruction": "核查设备，保存 equipment.md。"},
        )
    )["task_id"]
    b = (
        await control_with_confirmation(
            s,
            "native-read-b",
            "task.create",
            {"name": "维护乙", "instruction": "核查维护，保存 maintenance.md。"},
        )
    )["task_id"]
    if state == "terminal":
        from jiuwenswarm.server.live_voice.formal_task_models import (
            TerminalOutcome,
            TaskResultArtifact,
        )

        s.harness.executor.dispatch_outcome = TerminalOutcome.COMPLETED
        dispatch = s.harness.executor.dispatch

        async def completed_dispatch(item):
            delivery = await dispatch(item)
            return replace(
                delivery,
                observations=tuple(
                    replace(
                        observation,
                        result_text="Equipment review completed.",
                        result_artifacts=(
                            TaskResultArtifact(
                                f"{item.task_id}.md",
                                hashlib.sha256(
                                    b"Equipment review completed."
                                ).hexdigest(),
                            ),
                        ),
                    )
                    if observation.attempt_outcome is TerminalOutcome.COMPLETED
                    else observation
                    for observation in delivery.observations
                ),
            )

        monkeypatch.setattr(s.harness.executor, "dispatch", completed_dispatch)
    await core.drain_outbox()
    if state == "running":
        await control_with_confirmation(
            s, "native-adjust-a", "task.adjust", {"adjustment": "增加缺失设备核对。"}, a
        )
        await core.drain_outbox()
        await core.drain_inflight_adjustments()
        assert [
            e.event_type
            for e in core.store.events(a, _scope(), after_seq=-1)
            if e.event_type.startswith("task.adjust_")
        ] == ["task.adjust_requested", "task.adjust_applied"]
    before, counts = core.store.get_task(b, _scope()), core.store.counts()
    effects = (
        list(s.harness.executor.dispatches),
        list(s.harness.executor.adjustments),
        list(s.harness.executor.cancels),
    )
    s.program = lambda data: model_output(
        data, operation=operation, arguments=arguments, target=a
    )
    binding, capability, response = await native_source(s)
    result = await s.registry.handle_native_propose(
        params=native_delegate_params(
            binding, capability, response, "设备甲刚才的修改情况怎么样？维护乙不用动。"
        ),
        request_id="native-exact-read",
        session_id="session-1",
    )
    assert result.ok and result.payload["result"]["route"] == "task", result.payload
    assert s.manager.agent.calls == 1
    execution = s.manager.agent.executions[-1]
    assert not execution.allow_tools
    receipts = [
        json.loads(entry.content)
        for entry in execution.context.entries
        if entry.ref.source == "live_voice.task_control_receipt"
    ]
    assert (
        len(receipts) == 1
        and receipts[0]["task_id"] == a
        and receipts[0]["operation"] == operation
    )
    assert receipts[0]["ok"] is True
    contract = json.loads(execution.prompt_content())["answer_contract"]
    assert "NOT the execution state" in contract["required_behavior"]
    assert "formal_task_result is authoritative" in contract["required_behavior"]
    assert "A receipt never means a task has completed" not in contract["required_behavior"]
    payload = receipts[0]["formal_task_result"]
    if operation == "task.events":
        assert [
            e["event_type"]
            for e in payload["events"]
            if e["event_type"].startswith("task.adjust_")
        ] == ["task.adjust_requested", "task.adjust_applied"]
    else:
        assert payload["task"]["task_id"] == a and payload["task"]["state"] == state, (
            payload
        )
        assert payload["task"]["outcome"] == (
            "completed" if state == "terminal" else None
        )
    assert core.store.counts() == counts and core.store.get_task(b, _scope()) == before
    assert (
        s.harness.executor.dispatches,
        s.harness.executor.adjustments,
        s.harness.executor.cancels,
    ) == effects


@pytest.mark.asyncio
async def test_voice_creation_origins_restore_both_tasks_without_replaying_pending_input(
    semantic_runtime,
):
    s = semantic_runtime
    assert (
        await s.registry.handle_p2_activate(
            params=p2_params(),
            request_id="activate",
            session_id="session-1",
            channel_id="web",
        )
    ).ok
    created = []
    sequence = 0
    for label in ("equipment", "maintenance"):
        args = {"name": label, "instruction": f"核查资料并保存 {label}.md，不采购。"}
        s.program = lambda data: model_output(
            data,
            operation="task.create",
            arguments=args,
            reference=next(iter(data["context"]["pending"]), None),
        )
        proposed = await s.registry.handle_unified_submit(
            params=voice_final(f"propose-{label}", f"在后台处理 {label}，保存报告。"),
            request_id=f"propose-{label}",
            session_id="session-1",
            channel_id="web",
        )
        assert proposed.ok, proposed.payload
        sequence = await present_next(s, sequence)
        confirmed = await s.registry.handle_unified_submit(
            params=voice_final(f"confirm-{label}", "确认执行。"),
            request_id=f"confirm-{label}",
            session_id="session-1",
            channel_id="web",
        )
        assert confirmed.ok, confirmed.payload
        task_id = confirmed.payload["result"]["task_id"]
        created.append(task_id)
        sequence = await present_next(s, sequence)
    store = s.harness.composition._core.store
    journal = s.registry._unified_journal
    for task_id in created:
        task = store.get_task(task_id, _scope())
        commit = journal.read_creation_origin(
            scope=task.scope,
            turn_id=task.spec.origin.turn_id,
            commit_id=task.spec.origin.commit_id,
        )
        assert (
            commit is not None
            and commit.hypothesis_provenance["kind"] == "committed_speech"
        )
        assert commit.commit_id.startswith("commit-propose-"), (
            "creation must bind original proposal, not its confirmation final"
        )
        assert (
            journal.read_creation_origin(
                scope=replace(task.scope, session_id="other-session"),
                turn_id=commit.turn_id,
                commit_id=commit.commit_id,
            )
            is None
        )
        # Crash window: authoritative Task exists, originating UI operation has
        # no completed journal result. Recovery must not replay that operation.
        with journal._connect() as connection:
            connection.execute(
                "UPDATE unified_committed_inputs SET status='pending', result_json=NULL"
            )
    closed = await s.registry.handle_p2_close(
        params=p2_params(), request_id="close", session_id="session-1"
    )
    assert closed.ok, closed.payload
    assert s.registry._voice_task_origins == {}
    counts, calls, agent_calls = store.counts(), len(s.calls), s.manager.agent.calls
    opened = await s.registry.handle_p2_activate(
        params=p2_params(
            interaction_id="recovered-interaction",
            correlation_id="recovered-voice",
            activation_id="recovered-activation",
            activation_generation=2,
        ),
        request_id="recover",
        session_id="session-1",
        channel_id="web",
    )
    assert opened.ok, opened.payload
    assert set(opened.payload["result"]["voice_task_ids"]) == set(created), (
        opened.payload
    )
    assert set(s.registry._voice_task_origins) == set(created)
    assert all(
        origin.response_ref is None and origin.activation_id == "recovered-activation"
        for origin in s.registry._voice_task_origins.values()
    )
    assert (
        store.counts() == counts
        and len(s.calls) == calls
        and s.manager.agent.calls == agent_calls
    )
    # Activation ID/generation alone is not the interaction/correlation binding.
    rebound = await s.registry.handle_p2_activate(
        params=p2_params(
            interaction_id="another-interaction",
            correlation_id="another-voice",
            activation_id="recovered-activation",
            activation_generation=2,
        ),
        request_id="rebind",
        session_id="session-1",
        channel_id="web",
    )
    assert rebound.ok and set(rebound.payload["result"]["voice_task_ids"]) == set(
        created
    ), rebound.payload
    assert all(
        origin.interaction_id == "another-interaction"
        and origin.correlation_id == "another-voice"
        for origin in s.registry._voice_task_origins.values()
    )
    assert (
        store.counts() == counts
        and len(s.calls) == calls
        and s.manager.agent.calls == agent_calls
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        sqlite3.OperationalError("controlled storage failure"),
        OSError("controlled read failure"),
    ],
)
async def test_origin_discovery_storage_failure_keeps_activation_truth_and_cleanup(
    semantic_runtime, monkeypatch, failure
):
    s = semantic_runtime

    async def fail(**_kwargs):
        raise failure

    monkeypatch.setattr(s.harness.composition, "read_task_creation_origins", fail)
    before = s.harness.composition._core.store.counts()
    opened = await s.registry.handle_p2_activate(
        params=p2_params(),
        request_id="activate",
        session_id="session-1",
        channel_id="web",
    )
    assert opened.ok and opened.payload["result"]["status"] == "active", opened.payload
    assert (
        opened.payload["result"]["voice_task_discovery_reason"]
        == "VOICE_TASK_DISCOVERY_UNAVAILABLE"
    )
    assert s.registry._voice_task_origins == {}
    closed = await s.registry.handle_p2_close(
        params=p2_params(), request_id="close", session_id="session-1"
    )
    assert closed.ok and s.registry._p2_routes == {}, closed.payload
    assert (
        not s.calls
        and s.manager.agent.calls == 0
        and s.harness.composition._core.store.counts() == before
    )


@pytest.mark.asyncio
async def test_whole_semantic_budget_cancels_model_without_protected_effects(
    semantic_runtime, monkeypatch
):
    from jiuwenswarm.common import live_voice_operation_budgets as budgets

    s = semantic_runtime
    cancelled = asyncio.Event()

    async def blocked(_data):
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    s.program = blocked
    monkeypatch.setattr(budgets, "SEMANTIC_INPUT_TIMEOUT_SECONDS", 1.0)
    result = await asyncio.wait_for(s.text("budget", "请在后台核查设备。"), 3)
    assert (
        not result.ok and result.payload["error"]["reason"] == "SEMANTIC_INPUT_TIMEOUT"
    ), result.payload
    assert cancelled.is_set()
    assert s.harness.composition._core.store.counts()["tasks"] == 0
    assert s.harness.executor.dispatches == s.harness.executor.cancels == []
    assert s.manager.agent.calls == 0
    assert s.registry._pending_production_task_intents == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("semantic_runtime", ["openai-realtime-native"], indirect=True)
async def test_native_gateway_to_registry_waits_for_semantics_and_replays_exactly(
    semantic_runtime,
):
    from jiuwenswarm.common.schema.agent import AgentResponse
    from jiuwenswarm.common.schema.message import ReqMethod
    from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import (
        GatewayNativeInteractionRuntimeClient,
    )
    from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
        NativeEngineEvent,
    )

    s = semantic_runtime
    entered, release = asyncio.Event(), asyncio.Event()
    args = {"name": "设备核查", "instruction": "核查设备，生成 inventory.md。"}

    async def program(data):
        pending = data["context"]["pending"]
        if pending:
            entered.set()
            await release.wait()
        return model_output(
            data,
            operation="task.create",
            arguments=args,
            reference=pending[0] if pending else None,
        )

    s.program = program
    assert (await s.text("gateway-create", "后台核查设备。")).ok
    binding, capability, response = await native_source(s)

    class InProcessE2A:
        async def send_request(self, envelope):
            result = await s.registry.handle_native_propose(
                params=envelope.params,
                request_id=envelope.request_id,
                session_id="session-1",
            )
            # AgentWebSocketServer's internal-Native handler removes this
            # diagnostic-only outer manifest before the exact E2A envelope.
            payload = dict(result.payload)
            payload.pop("product_composition", None)
            return AgentResponse(
                request_id=envelope.request_id,
                channel_id=envelope.channel,
                ok=result.ok,
                payload=payload,
            )

    client = GatewayNativeInteractionRuntimeClient(
        InProcessE2A(), native_model="test-native", timeout_seconds=0.01
    )
    client.observe_activation_response(
        s.native_activation,
        routed_session_id="session-1",
        connection_id="isolated-test",
        request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value,
    )
    proposal = _native_delegate_proposal(
        binding, response, request_text="确认设备核查任务。"
    )
    event = NativeEngineEvent(action=proposal.action, delegate=proposal.delegate)
    params = dict(
        binding=binding,
        capability=capability,
        event=event,
        request_id="gateway-confirm",
    )
    task = asyncio.create_task(client.propose(**params))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 0.05)
        assert not task.done()  # It outlives the ordinary control deadline.
        assert s.harness.composition._core.store.counts()["tasks"] == 0
        release.set()
        first = await asyncio.wait_for(task, 3)
        assert first["kind"] == "delegate" and first["route"] == "task"
        assert s.harness.composition._core.store.counts()["tasks"] == 1
        replay = await client.propose(**params)
        assert replay == first
        assert len(s.calls) == 2 and s.manager.agent.calls == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("semantic_runtime", ["openai-realtime-native"], indirect=True)
async def test_native_natural_confirmation_uses_same_model_and_exact_formal_task(
    semantic_runtime,
):
    s = semantic_runtime
    args = {
        "name": "设备核查",
        "instruction": "读取设备资料并保存 inventory.md，不采购。",
    }

    def program(data):
        pending = data["context"]["pending"]
        return model_output(
            data,
            operation="task.create",
            arguments=args,
            reference=None if not pending else pending[0],
        )

    s.program = program
    proposed = await s.text("create", "请在后台核查设备资料，保存报告，但不要采购。")
    assert (
        proposed.ok
        and proposed.payload["result"]["reason"] == "TASK_CONFIRMATION_REQUIRED"
    ), proposed.payload
    original = next(iter(s.registry._pending_production_task_intents.values()))
    expected_binding = dict(original.resolution.origin_binding.semantic_context_binding)
    binding, capability, response = await native_source(s)
    params = _native_propose_params(
        binding,
        capability,
        _native_delegate_proposal(binding, response, request_text="确认设备核查任务。"),
    )
    result = await s.registry.handle_native_propose(
        params=params, request_id="native-confirm", session_id="session-1"
    )
    assert result.ok, result.payload
    assert s.harness.composition._core.store.counts()["tasks"] == 1
    assert len(s.calls) == 2
    assert s.calls[1]["context"]["pending"][0]["kind"] == "confirmation"
    assert s.manager.agent.calls == 1 and not s.manager.agent.executions[0].allow_tools
    assert (
        original.resolution.origin_binding.semantic_context_binding == expected_binding
    )
    replay = await s.registry.handle_native_propose(
        params=params, request_id="native-confirm", session_id="session-1"
    )
    assert replay.payload == result.payload
    assert len(s.calls) == 2 and s.manager.agent.calls == 1
    assert s.harness.composition._core.store.counts()["tasks"] == 1


@pytest.mark.asyncio
async def test_model_create_and_natural_confirmation_reach_real_store_once(
    tmp_path, monkeypatch
):
    commits = TurnCommitLedger()
    harness = _harness(
        tmp_path,
        commit_ledger=commits,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)

    async def push(_message):
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False, p3_text_enabled=True, p3_mutation_enabled=True
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commits,
    )
    calls = []
    args = {
        "name": "实验设备清点",
        "instruction": "创建 inventory.md，核查资料中的设备。不购买；预算上限为1500元。",
    }

    class Model:
        async def invoke(self, **kwargs):
            assert kwargs["tools"] == []
            data = json.loads(kwargs["messages"][1].content)
            calls.append(data)
            if len(calls) == 1:
                output = model_output(data, operation="task.create", arguments=args)
            else:
                pending = data["context"]["pending"]
                assert len(pending) == 1 and pending[0]["kind"] == "confirmation"
                output = model_output(
                    data,
                    operation=pending[0]["operation"],
                    arguments=pending[0]["arguments"],
                    reference=pending[0],
                )
            return SimpleNamespace(content=json.dumps(output), tool_calls=[])

    original = harness.models.resolve
    monkeypatch.setattr(
        harness.models,
        "resolve",
        lambda *a, **kw: replace(original(*a, **kw), model=Model()),
    )
    try:
        proposed = await registry.handle_p3_intent(
            params=_production_registry_text_params(
                stem="semantic-create",
                text="后台帮我清点实验设备，不购买，预算一千五。",
            ),
            request_id="semantic-create",
            session_id="session-1",
        )
        assert proposed.ok, proposed.payload
        assert proposed.payload["result"]["reason"] == "TASK_CONFIRMATION_REQUIRED", (
            proposed.payload
        )
        assert harness.composition._core.store.counts()["tasks"] == 0
        pending = registry._pending_production_task_intents[
            proposed.payload["result"]["confirmation_token"]
        ]
        assert pending.resolution.origin_binding.semantic_context_binding is not None
        assert proposed.payload["result"]["confirmation_form"] is None
        params = _production_registry_text_params(
            stem="semantic-confirm", text="可以，就按这个做。"
        )
        done = await registry.handle_p3_intent(
            params=params, request_id="semantic-confirm", session_id="session-1"
        )
        assert done.ok and done.payload["result"]["status"] == "dispatched", (
            done.payload
        )
        task_id = done.payload["result"]["task_id"]
        task = harness.composition._core.store.get_task(task_id, _scope())
        assert (
            task.spec.name == args["name"]
            and task.spec.instruction == args["instruction"]
        )
        before = harness.composition._core.store.counts()
        replay = await registry.handle_p3_intent(
            params=params, request_id="semantic-confirm", session_id="session-1"
        )
        assert replay.payload == done.payload
        assert harness.composition._core.store.counts() == before
        assert len(calls) == 2
    finally:
        await registry.stop()
        await harness.composition.stop()
