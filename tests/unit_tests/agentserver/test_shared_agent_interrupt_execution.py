"""Exact Agent replies retain the original service and SDK execution owner."""
from __future__ import annotations

import asyncio
from collections import deque
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio

from openjiuwen.core.session.agent import Session
from openjiuwen.core.session.interaction.interaction import InteractionOutput
from openjiuwen.core.session.stream import OutputSchema
from openjiuwen.core.foundation.llm import AssistantMessage, ToolCall
from openjiuwen.core.single_agent.interrupt.response import ToolCallInterruptRequest
from openjiuwen.core.single_agent.interrupt.state import INTERRUPTION_KEY, ToolInterruptionState, ToolInterruptEntry
from openjiuwen.core.single_agent.schema.agent_card import AgentCard
from openjiuwen.harness.deep_agent import DeepAgent
from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter
from jiuwenswarm.server.runtime.agent_adapter.stream_source import extract_agent_interrupt
from jiuwenswarm.server.runtime.agent_interrupt_execution import list_agent_interrupts, reply_agent_interrupt
from jiuwenswarm.server.runtime.session_execution import (
    SessionExecutionService, SessionExecutionUnavailable, current_output_observer,
    observe_current_agent_interrupt, prepare_current_work,
)


def request(request_id="original", **kwargs):
    return AgentRequest(**{"request_id": request_id, "channel_id": "web", "session_id": "session",
        "req_method": ReqMethod.CHAT_SEND, "is_stream": True,
        "params": {"query": "ask first", "mode": "code.normal"}, **kwargs})


def interaction(input_id="tool-id", token="token-a"):
    return OutputSchema(type="__interaction__", index=0, payload=InteractionOutput(id=input_id,
        value=ToolCallInterruptRequest(tool_call_id=input_id, tool_name="effect",
            message="Please confirm effect", pending_token=token)))


@pytest_asyncio.fixture
async def observed(monkeypatch, tmp_path):
    """A real shared reader and Session writer, without a provider execution."""
    monkeypatch.chdir(tmp_path)
    pins = []
    manager = SimpleNamespace(pin_agent=lambda agent: pins.append(agent),
                              unpin_agent=lambda agent: pins.remove(agent))
    service = SessionExecutionService(manager)
    incoming = asyncio.Queue()
    ready = asyncio.Event()
    sdk = DeepAgent(AgentCard(id=uuid4().hex, name="observed-pending"))
    session = Session(session_id="sdk-session")
    sdk._interaction_session = session
    runtime = []

    class Facade:
        build_agent_interrupt_input = staticmethod(JiuWenSwarm.build_agent_interrupt_input)
        _requires_exact_agent_interrupt_reply = JiuWenSwarm._requires_exact_agent_interrupt_reply

        async def process_message_stream(self, req):
            _, self.work = prepare_current_work(sdk_agent=sdk, session_id="sdk-session",
                apply_runtime=lambda ctx: runtime.append(ctx))
            current_output_observer(sdk)("actual-output-owner", True)
            self.source = {"source_binding_id": self.work.binding_id,
                "source_origin_request_id": "original", "source_session_id": "sdk-session",
                "source_request_id": "original", "source_task_id": "actual-task-a",
                "source_run_kind": "user", "source_goal_id": None, "source_goal_revision": None}
            ready.set()
            while True:
                raw, done, serialized = await incoming.get()
                canonical = extract_agent_interrupt(raw)
                if canonical is not None:
                    # This fixture prepares observed state without a provider;
                    # the public getter and Session state read/write stay real.
                    # Actual mint/claim/continuation is exercised separately.
                    state = session.get_state(INTERRUPTION_KEY)
                    if state is None or state.pending_token != canonical["pending_token"]:
                        state = ToolInterruptionState(ai_message=AssistantMessage(content=""), iteration=0,
                            pending_token=canonical["pending_token"], execution_origin={
                                "kind": self.source["source_run_kind"], "request_id": self.source["source_request_id"],
                                "session_id": "sdk-session", "run_context": self.work.run_context()})
                    state.interrupted_tools[canonical["input_id"]] = ToolInterruptEntry(
                        tool_call=ToolCall(id=canonical["input_id"], type="function", name="effect", arguments="{}"),
                        interrupt_requests={canonical["input_id"]: raw.payload.value})
                    session.update_state({INTERRUPTION_KEY: state})
                await session.with_source_metadata(self.source).write_stream(raw)
                stream = session.stream_iterator()
                actual = await anext(stream)
                await stream.aclose()
                if serialized:
                    actual = actual.model_dump()
                parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(actual)
                observe_current_agent_interrupt(sdk, actual, parsed)
                yield AgentResponseChunk(request_id=req.request_id, channel_id=req.channel_id, payload=parsed)
                done.set()

    facade = Facade()
    entry = service.start(facade, request(), retained=True)
    await asyncio.wait_for(ready.wait(), 2)

    async def publish(raw=None, serialized=False):
        done = asyncio.Event()
        await incoming.put((raw or interaction(), done, serialized))
        await asyncio.wait_for(done.wait(), 2)

    try:
        yield SimpleNamespace(service=service, facade=facade, entry=entry, sdk=sdk,
                              publish=publish, runtime=runtime, session=session)
    finally:
        assert await service.close(timeout=2)
        await asyncio.sleep(0)
        assert pins == []


@pytest.mark.asyncio
@pytest.mark.parametrize("serialized", [False, True])
async def test_actual_session_canonical_pending_isolated_projection(observed, serialized):
    await observed.publish(serialized=serialized)
    result = list_agent_interrupts(observed.service, observed.facade, session_id="session")
    item = result["pending"][0]
    assert item["input_id"] == "tool-id" and item["pending_token"] == "token-a"
    assert item["source_binding_id"] == observed.facade.work.binding_id
    assert item["source_request_id"] == "original" and item["source_task_id"] == "actual-task-a"
    assert item["question"]["source"] == "permission_interrupt"
    assert item["question"]["pending_token"] == "token-a"
    assert item["question"]["request_id"].startswith("agent-input.")
    assert item["question"]["input_id"] == "tool-id"
    item["question"]["questions"].clear()
    assert list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"][0]["question"]["questions"]
    assert list_agent_interrupts(observed.service, SimpleNamespace(), session_id="session")["pending"] == []
    assert list_agent_interrupts(observed.service, observed.facade, session_id="foreign")["pending"] == []


@pytest.mark.asyncio
async def test_same_generation_accumulates_ids_and_next_generation_replaces(observed):
    await observed.publish(interaction("first"))
    await observed.publish(interaction("second"))
    items = list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"]
    assert [item["input_id"] for item in items] == ["first", "second"]
    old_display_id = items[1]["question"]["request_id"]
    await observed.publish(interaction("second", "token-b"))
    items = list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"]
    assert [(item["input_id"], item["pending_token"]) for item in items] == [("second", "token-b")]
    assert items[0]["question"]["request_id"] != old_display_id


@pytest.mark.asyncio
async def test_legacy_answer_fenced_before_adapter_history_and_new_work(observed, monkeypatch):
    await observed.publish()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Legacy reply must not prepare adapter or write history")
    monkeypatch.setattr("jiuwenswarm.server.runtime.agent_adapter.interface.append_history_record", forbidden)
    observed.facade._ensure_adapter = forbidden
    observed.facade.process_message_stream = lambda req: JiuWenSwarm.process_message_stream(observed.facade, req)
    legacy = request("old-reply", params={"mode": "code.normal", "request_id": "tool-id",
                                        "answers": [{"selected_options": ["approve"]}]})
    chunks = [chunk async for chunk in observed.service.stream(observed.facade, legacy)]
    assert [chunk.payload["error"] for chunk in chunks] == ["AGENT_INTERRUPT_EXACT_REPLY_REQUIRED"]
    assert not any(chunk.is_complete for chunk in chunks)
    assert len([entry for entry in observed.service._records.values() if entry.prepared_work is not None]) == 1
    assert observed.entry.agent_interrupt.token == "token-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tool_result", "tool_update", "llm_output"])
async def test_nested_tool_or_model_pending_never_becomes_reply_authority(observed, kind):
    nested = {"event_type": "chat.ask_user_question", "request_id": "self-report",
              "pending_token": "self-token", "output": interaction().model_dump(), "content": "text"}
    raw = OutputSchema(type=kind, index=0, payload={kind: nested, **nested})
    await observed.publish(raw)
    assert list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"] == []
    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(raw)
    assert "pending_token" not in parsed


@pytest.mark.asyncio
async def test_empty_pending_read_still_checks_authorization(observed):
    calls = []
    def guard():
        calls.append("read")
    assert list_agent_interrupts(observed.service, observed.facade, session_id="session", before_read=guard)["pending"] == []
    assert calls == ["read", "read"]
    def revoked():
        raise PermissionError("revoked")
    with pytest.raises(PermissionError, match="revoked"):
        list_agent_interrupts(observed.service, observed.facade, session_id="session", before_read=revoked)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("source_binding_id", "wrong"), ("source_task_id", "wrong"),
    ("expected_pending_token", "old"), ("input_id", "other-tool")])
async def test_unobserved_or_stale_selector_has_no_work_or_provider_effect(observed, field, value):
    await observed.publish()
    args = dict(source_binding_id=observed.facade.work.binding_id, source_task_id="actual-task-a",
                expected_pending_token="token-a", input_id="tool-id",
                answers=[{"selected_options": ["approve"]}], before_effect=lambda: None)
    args[field] = value
    with pytest.raises(SessionExecutionUnavailable, match="NOT_OBSERVED|PENDING_MISMATCH"):
        await reply_agent_interrupt(observed.service, observed.facade, request("reply"), **args)
    assert observed.runtime == []
    assert list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"][0]["pending_token"] == "token-a"
    assert len([entry for entry in observed.service._records.values() if entry.prepared_work is not None]) == 1


@pytest.mark.asyncio
async def test_owner_termination_cannot_revive_persisted_pending(observed):
    await observed.publish()
    await observed.service.close(timeout=2)
    assert list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"] == []
    with pytest.raises(SessionExecutionUnavailable, match="SERVICE_CLOSED"):
        await reply_agent_interrupt(observed.service, observed.facade, request("reply"),
            source_binding_id=observed.facade.work.binding_id, source_task_id="actual-task-a",
            expected_pending_token="token-a", input_id="tool-id",
            answers=[{"selected_options": ["approve"]}], before_effect=lambda: None)


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["clear", "new-token", "new-origin"])
async def test_read_cross_checks_actual_sdk_pending_generation(observed, replacement):
    await observed.publish()
    saved = observed.session.get_state(INTERRUPTION_KEY)
    if replacement == "clear":
        observed.session.update_state({INTERRUPTION_KEY: None})
    elif replacement == "new-token":
        saved.pending_token = "newer-unobserved-token"
        observed.session.update_state({INTERRUPTION_KEY: saved})
    else:
        origin = deepcopy(saved.execution_origin)
        origin["run_context"]["extra"]["jiuwenswarm_execution"]["binding_id"] = "foreign"
        saved.execution_origin = origin
        observed.session.update_state({INTERRUPTION_KEY: saved})
    if replacement == "new-origin":
        with pytest.raises(ValueError, match="CONTEXT_MISMATCH"):
            list_agent_interrupts(observed.service, observed.facade, session_id="session")
    else:
        assert list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["goal_id", "revision", "status", "clear"])
async def test_goal_pending_does_not_survive_replacement_on_same_live_reader(observed, change):
    from openjiuwen.harness.goal.manager import GoalManager
    from openjiuwen.harness.goal.schema import GoalRecord, GoalStatus
    from openjiuwen.harness.goal.store import SessionGoalStore

    async def cancel(**_kwargs):
        pass
    store = SessionGoalStore(observed.session)
    observed.sdk.goal_manager = GoalManager(store=store, event_manager=observed.sdk.event_manager,
        control_lock=asyncio.Lock(), has_output_stream=lambda: True, cancel_active_round=cancel,
        emit_event=lambda _event: None, notify_work=lambda: None)
    record = GoalRecord(goal_id="original-goal", session_id="sdk-session", objective="complete the task",
                        revision=4, run_context=observed.facade.work.run_context())
    store.save(record)
    observed.facade.source.update(source_run_kind="goal", source_request_id=None,
                                  source_goal_id=record.goal_id, source_goal_revision=record.revision)
    await observed.publish()
    assert len(list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"]) == 1
    if change == "clear":
        store.clear()
    else:
        setattr(record, change, {"goal_id": "replacement", "revision": 5, "status": GoalStatus.PAUSED}[change])
        store.save(record)
    assert observed.service._work_is_live(observed.entry)
    assert list_agent_interrupts(observed.service, observed.facade, session_id="session")["pending"] == []


@pytest.mark.parametrize("raw", [
    {"pending_token": "wrong", "id": "wrong"},
    {"type": "__interaction__", "payload": {"id": "id", "pending_token": "wrong", "value": {}}},
    {"type": "tool_result", "payload": {"id": "id", "value": {"pending_token": "wrong"}}},
    {"type": "__interaction__", "payload": {"id": "id", "value": {"pending_token": None}}},
])
def test_noncanonical_token_location_rejected(raw):
    assert extract_agent_interrupt(raw) is None


@pytest_asyncio.fixture
async def actual_execution(monkeypatch, tmp_path):
    """Real Deep supervisor/controller/ReAct with a controlled provider/tool."""
    from openjiuwen.core.foundation.kv_cache import KVCacheAffinityConfig
    from openjiuwen.core.foundation.llm import AssistantMessageChunk, Model, ModelClientConfig, ModelRequestConfig
    from openjiuwen.core.foundation.tool import Tool, ToolCard
    from openjiuwen.core.runner import Runner
    from openjiuwen.core.runner.callback import AsyncCallbackFramework
    from openjiuwen.core.session.agent import create_agent_session
    from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig
    from openjiuwen.harness.rails.interrupt.confirm_rail import ConfirmInterruptRail
    from openjiuwen.harness.deep_agent import DeepAgentConfig
    from openjiuwen.harness.schema.interaction import SendInputRequest
    from jiuwenswarm.agents.harness.common.rails.agent_work_rail import AgentWorkRail
    from jiuwenswarm.agents.harness.common.rails.stream_event_rail import JiuSwarmStreamEventRail
    from jiuwenswarm.agents.harness.common.rails.permissions.owner_scopes import TOOL_PERMISSION_CONTEXT
    from jiuwenswarm.common.schema.agent import PermissionContext
    from jiuwenswarm.server.runtime.agent_adapter.work_model import BoundAgentModel
    from jiuwenswarm.server.runtime.execution_context import AgentExecutionPolicy

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Runner, "callback_framework", AsyncCallbackFramework())
    pins, provider, effects, facade_calls, events, failures = [], [], [], [], [], []
    permissions = {"allowed": True}
    responses = deque()
    questions = asyncio.Queue()
    seen_questions = set()
    tool_name = "agent_hitl_effect_" + uuid4().hex
    sdk = DeepAgent(AgentCard(id=uuid4().hex, name="bound-input-owner")).configure(DeepAgentConfig(
        enable_task_loop=True, auto_create_workspace=False, enable_read_image_multimodal=False))
    react = ReActAgent(AgentCard(id=uuid4().hex, name="bound-input-react"))
    react.configure(ReActAgentConfig(model_name="original-model", max_iterations=4,
        kv_cache_affinity_config=KVCacheAffinityConfig(enable_kv_cache_affinity=False, enable_kv_cache_release=False)))
    sdk.set_react_agent(react, initialized=True)
    sdk.ability_manager = react.ability_manager
    sdk.system_prompt_builder = react.system_prompt_builder
    session = create_agent_session(session_id=uuid4().hex, card=sdk.card)
    await session.pre_run(inputs={})

    def principal():
        current = TOOL_PERMISSION_CONTEXT.get()
        return current.principal_user_id if current is not None else None

    class Effect(Tool):
        def __init__(self):
            super().__init__(ToolCard(id=tool_name, name=tool_name, description="Controlled test effect",
                input_params={"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}))

        async def invoke(self, inputs, **_kwargs):
            effects.append((inputs["target"], principal()))
            return "applied"

        async def stream(self, inputs, **kwargs):
            yield await self.invoke(inputs, **kwargs)

    class Client:
        def next(self, kwargs):
            provider.append((kwargs.get("model"), principal()))
            assert responses, "Unexpected model effect"
            return responses.popleft()

        async def invoke(self, messages=None, **kwargs):
            return self.next(kwargs)

        async def stream(self, messages=None, **kwargs):
            result = self.next(kwargs)
            yield AssistantMessageChunk(content=result.content, tool_calls=result.tool_calls,
                                        finish_reason="tool_calls" if result.tool_calls else "stop")

    client = Client()
    monkeypatch.setattr("openjiuwen.core.foundation.llm.model.create_model_client", lambda **_kwargs: client)
    model = Model(model_config=ModelRequestConfig(model="original-model"), model_client_config=ModelClientConfig(
        client_provider="OpenAI", api_key="test-only", api_base="http://127.0.0.1:1",
        stream_first_chunk_timeout=None, stream_idle_timeout=None))
    react.set_llm(model)
    tool = Effect()
    Runner.resource_mgr.add_tool(tool)
    react.ability_manager.add(tool.card)
    service = SessionExecutionService(SimpleNamespace(pin_agent=lambda agent: pins.append(agent),
                                                     unpin_agent=lambda agent: pins.remove(agent)), max_active=1)
    rail = JiuSwarmStreamEventRail()
    rail.execution_work_resolver = lambda ctx: service.resolve_work_context(sdk_agent=sdk,
        session_id=ctx.session.get_session_id(), run_context=ctx.extra.get("run_context"))
    for phase, priority in (("prepare", 1000), ("last", -1000)):
        await sdk._register_rail_selective(AgentWorkRail(rail, phase=phase, priority=priority))
    await sdk._register_rail_selective(ConfirmInterruptRail(tool_names=[tool_name]))

    def policy_guard():
        if not permissions["allowed"]:
            raise PermissionError("original work authority revoked")

    class Facade:
        build_agent_interrupt_input = staticmethod(JiuWenSwarm.build_agent_interrupt_input)

        async def process_message_stream(self, req):
            try:
                async for chunk in self.produce(req):
                    yield chunk
            except Exception as error:
                failures.append(error)
                raise

        async def produce(self, req):
            facade_calls.append(req)
            async def apply_runtime(_ctx):
                react.set_llm(self.work.model)
            _, self.work = prepare_current_work(sdk_agent=sdk, session_id=session.get_session_id(),
                apply_runtime=apply_runtime, permission_context=PermissionContext(principal_user_id="original-owner"))
            self.work.model = BoundAgentModel(model, self.work)
            await sdk.start(session=session)
            output = await sdk.attach_output(on_output_ready=current_output_observer(sdk))
            assert output is not None
            await sdk.send_input(SendInputRequest(request_id=req.request_id,
                inputs={"query": req.params["query"], "run": {"context": self.work.run_context()}}))
            try:
                async for raw in output:
                    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(raw)
                    if extract_agent_interrupt(raw) is not None:
                        observe_current_agent_interrupt(sdk, raw, parsed)
                        key = (parsed["source_task_id"], parsed["pending_token"], parsed["input_id"])
                        if key not in seen_questions:
                            seen_questions.add(key)
                            questions.put_nowait(parsed)
                    if parsed is not None:
                        events.append(parsed)
                        yield AgentResponseChunk(request_id=req.request_id, channel_id=req.channel_id, payload=parsed)
            finally:
                await output.close()

    facade = Facade()

    def start(targets):
        responses.extend(AssistantMessage(content="", tool_calls=[ToolCall(id="reused-provider-id", index=0,
            type="function", name=tool_name, arguments='{"target":"' + target + '"}')]) for target in targets)
        responses.append(AssistantMessage(content="completed"))
        return service.start_bound(facade, request(), policy=AgentExecutionPolicy(before_effect=policy_guard))

    async def next_question():
        try:
            return await asyncio.wait_for(questions.get(), 10)
        except TimeoutError:
            if failures:
                raise failures[-1] from None
            raise

    async def reply(question, rpc="reply", **kwargs):
        return await reply_agent_interrupt(service, facade, request(rpc,
            params={"mode": "agent", "model_name": "reply-must-not-select-this-model"}),
            source_binding_id=question["source_binding_id"], source_task_id=question["source_task_id"],
            expected_pending_token=question["pending_token"], input_id=question["input_id"],
            answers=kwargs.pop("answers", [{"selected_options": ["approve"]}]),
            before_effect=kwargs.pop("before_effect", lambda: None), **kwargs)

    try:
        yield SimpleNamespace(service=service, facade=facade, sdk=sdk, react=react, session=session,
            start=start, next_question=next_question, reply=reply, provider=provider, effects=effects,
            facade_calls=facade_calls, events=events, permissions=permissions, model=model, client=client)
    finally:
        assert await service.close(timeout=5)
        await sdk.stop()
        await react.agent_callback_manager.clear()
        await sdk.agent_callback_manager.clear()
        Runner.resource_mgr.remove_tool(tool_name)
        await asyncio.sleep(0)
        assert pins == []


@pytest.mark.asyncio
async def test_real_deep_reply_reuses_original_model_permission_reader_and_control_replay(actual_execution, monkeypatch):
    run = actual_execution
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Reply cannot append generated history")
    monkeypatch.setattr("jiuwenswarm.server.runtime.agent_adapter.interface.append_history_record", forbidden)
    entry = run.start(["A"])
    question = await run.next_question()
    assert not entry.task.done() and run.sdk.has_output_stream() and run.effects == []
    receipt = await run.reply(question)
    assert receipt["accepted"] is True and receipt["pending_token"] == question["pending_token"]
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert await run.reply(question) == receipt  # Closed original work can replay its recorded receipt.
    with pytest.raises(SessionExecutionUnavailable, match="REQUEST_CONFLICT"):
        await run.reply(question, answers=[{"selected_options": ["reject"]}])
    assert run.effects == [("A", "original-owner")]
    assert run.provider == [("original-model", "original-owner"), ("original-model", "original-owner")]
    assert len(run.facade_calls) == 1 and run.model._client is run.client
    final = next(event for event in run.events if event.get("event_type") == "chat.final")
    assert final["source_binding_id"] == question["source_binding_id"]
    assert final["source_request_id"] == "original" and final["source_task_id"] != question["source_task_id"]
    controls = run.service.list_internal(run.facade, session_id="session", kind="agent.interrupt.reply")
    assert len(controls) == 1 and controls[0].prepared_work is None and controls[0].control_only
    assert all(chunk.payload["event_type"] == "agent.input_accepted" and not chunk.is_complete
               for _, chunk, _, _ in controls[0].events)


@pytest.mark.asyncio
async def test_real_deep_old_pending_and_duplicate_reply_cannot_approve_reused_tool_id(actual_execution):
    run = actual_execution
    entry = run.start(["A", "B"])
    first = await run.next_question()
    receipt = await run.reply(first, "reply-a")
    second = await run.next_question()
    assert first["input_id"] == second["input_id"] == "reused-provider-id"
    assert first["pending_token"] != second["pending_token"]
    assert first["request_id"] != second["request_id"]
    assert first["source_binding_id"] == second["source_binding_id"]
    assert await run.reply(first, "reply-a") == receipt
    with pytest.raises(SessionExecutionUnavailable, match="PENDING_MISMATCH"):
        await run.reply(first, "old-answer-new-rpc")
    assert run.effects == [("A", "original-owner")]
    assert run.sdk.peek_pending_input()["pending_token"] == second["pending_token"]
    await run.reply(second, "reply-b")
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert run.effects == [("A", "original-owner"), ("B", "original-owner")]


@pytest.mark.asyncio
async def test_real_deep_authority_revoked_during_async_preparation_preserves_pending(actual_execution, monkeypatch):
    run = actual_execution
    entry = run.start(["A"])
    question = await run.next_question()
    entered, release = asyncio.Event(), asyncio.Event()
    original = run.react._init_context
    async def delayed(session):
        context = await original(session)
        entered.set()
        await release.wait()
        return context
    monkeypatch.setattr(run.react, "_init_context", delayed)
    pending = asyncio.create_task(run.reply(question, "revoked-reply"))
    await asyncio.wait_for(entered.wait(), 10)
    assert run.sdk.peek_pending_input()["pending_token"] == question["pending_token"]
    run.permissions["allowed"] = False
    release.set()
    with pytest.raises(PermissionError, match="original work authority revoked"):
        await asyncio.wait_for(pending, 10)
    assert run.effects == [] and len(run.provider) == 1 and not entry.task.done()
    assert run.sdk.peek_pending_input()["pending_token"] == question["pending_token"]
    run.permissions["allowed"] = True
    control = run.service.get_internal(run.facade, session_id="session", execution_id="revoked-reply",
                                       kind="agent.interrupt.reply")
    failed_task = control.task
    receipts = await asyncio.gather(*(run.reply(question, "revoked-reply") for _ in range(3)))
    assert receipts[0] == receipts[1] == receipts[2] and receipts[0]["accepted"] is True
    assert run.service.get_internal(run.facade, session_id="session", execution_id="revoked-reply",
                                    kind="agent.interrupt.reply") is control
    assert control.task is not failed_task and failed_task.done() and not failed_task.cancelled()
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert run.effects == [("A", "original-owner")]


@pytest.mark.asyncio
async def test_real_deep_lost_claim_receipt_never_resends_same_reply(actual_execution, monkeypatch):
    run = actual_execution
    entry = run.start(["A"])
    question = await run.next_question()
    original = run.sdk.send_input
    calls = []

    async def lose_receipt(req):
        calls.append(req)
        assert (await original(req))["accepted"] is True
        raise ConnectionError("receipt observation lost after real claim")

    monkeypatch.setattr(run.sdk, "send_input", lose_receipt)
    for _ in range(2):
        receipt = await run.reply(question, "lost-receipt")
        assert receipt["status"] == "unknown" and receipt["observation_required"]
        assert "accepted" not in receipt
        assert receipt["pending_token"] == question["pending_token"]
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert len(calls) == 1 and run.effects == [("A", "original-owner")]


@pytest.mark.asyncio
async def test_real_deep_pre_send_denial_can_retry_same_rpc_without_duplicate_work(actual_execution, monkeypatch):
    from unittest.mock import AsyncMock
    run = actual_execution
    entry = run.start(["A"])
    question = await run.next_question()
    calls = 0
    send = AsyncMock(wraps=run.sdk.send_input)
    monkeypatch.setattr(run.sdk, "send_input", send)
    def guard():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("Revoked before SDK send")
    with pytest.raises(PermissionError, match="before SDK send"):
        await run.reply(question, "same-pre-send-rpc", before_effect=guard)
    send.assert_not_awaited()
    assert run.effects == [] and len(run.provider) == 1 and not entry.task.done()
    assert run.sdk.peek_pending_input()["pending_token"] == question["pending_token"]
    assert (await run.reply(question, "same-pre-send-rpc", before_effect=guard))["accepted"]
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert send.await_count == 1 and run.effects == [("A", "original-owner")]


@pytest.mark.asyncio
async def test_control_retry_reuses_record_and_settles_each_physical_task_once():
    from jiuwenswarm.server.runtime.agent_interrupt_execution import _Reply
    pins, runs = [], []
    agent = object()
    service = SessionExecutionService(SimpleNamespace(pin_agent=lambda value: pins.append(value),
                                                     unpin_agent=lambda value: pins.remove(value)))
    retry_state = _Reply()
    retry_state.preclaim_retryable = True
    entered, release = asyncio.Event(), asyncio.Event()

    async def fail(_entry):
        runs.append(asyncio.current_task())
        raise PermissionError("preclaim rejected")
        yield

    async def retry(_entry):
        runs.append(asyncio.current_task())
        entered.set()
        await release.wait()
        if False:
            yield

    req = request("control")
    entry = service.start_internal(agent, req, kind="agent.interrupt.reply", producer=fail,
                                   capability_state=retry_state, control_only=True)
    old_task = entry.task
    with pytest.raises(PermissionError):
        await old_task
    assert entry.stream_closed and pins == []
    new_state = _Reply()
    try:
        for state in (retry_state, retry_state):
            assert service.restart_internal_control(entry, req, expected_state=state,
                producer=retry, capability_state=new_state) is entry
        await entered.wait()
        assert entry.task is not old_task and runs == [old_task, entry.task]
        assert pins == [agent] and not entry.stream_closed and entry.stream_outcome is None
        release.set()
        await entry.task
        assert entry.stream_closed and entry.stream_outcome == "ended" and pins == []
    finally:
        assert await service.close(timeout=1)
