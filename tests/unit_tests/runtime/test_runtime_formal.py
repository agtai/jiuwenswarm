# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Formal speech uses the same runtime admission and cancellation as text."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from jiuwenswarm.agents.harness.code.rails.heartbeat.execution import SessionRunAdmission
from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef, TurnCommit
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.runtime.context import get_current_runtime
from jiuwenswarm.runtime.service import AgentRuntime, RuntimeStateError
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalAgentExecution, FormalContextSnapshot, FormalLiveVoiceViolation,
)
from jiuwenswarm.server.runtime.agent_adapter.runtime_formal import RuntimeFormalAgentFacade


def execution():
    scope = ScopeRef("subject", "project", "public-session", Assurance.AUTHENTICATED)
    commit = TurnCommit.from_dict({
        "contract_version": "live-voice.contract.v2", "commit_id": "commit-1",
        "turn_id": "turn-1", "interaction_id": "interaction-1", "text": "Analyze this",
        "hypothesis_provenance": {"provider": "test"}, "scope": scope.to_dict(),
        "context_refs": [], "committed_at": "2026-09-13T08:00:00Z",
    })
    return FormalAgentExecution(
        request_id="request-1", channel_id="web", internal_session_id="formal-isolated",
        commit=commit, context=FormalContextSnapshot(scope), allow_tools=False,
        model_identity="configured#0", model_config_version="version-1",
    )


class Agent:
    def __init__(self):
        self.seen = []
        self.contexts = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False
        self.cleaned = False
        self.output_extra = {}
        self.gates = []
        self.pause_formal_tools = lambda session: self.gates.append(("pause", session))
        self.resume_formal_tools = lambda session: self.gates.append(("resume", session))
        self.abort_formal_tools = lambda session: self.gates.append(("abort", session))

    def supports_formal_live_voice(self):
        return True

    def supports_speculative_dialogue(self):
        return True

    async def process_formal_live_voice_stream(self, value):
        self.seen.append(value)
        self.contexts.append(get_current_runtime())
        self.started.set()
        try:
            if self.block:
                await self.release.wait()
            yield AgentResponseChunk(
                request_id=value.request_id, channel_id=value.channel_id,
                payload={"event_type": "chat.final", "content": "Exact answer", **self.output_extra},
                is_complete=True,
            )
        finally:
            self.cleaned = True


class Manager:
    def __init__(self, agent):
        self.agent = agent
        self.lookups = []
        self.begin_foreground_chat = AsyncMock()
        self.end_foreground_chat = AsyncMock()
        self.cancel_all_inflight_work = AsyncMock()
        self.cleanup = AsyncMock()

    def get_agent_nowait(self, **kwargs):
        self.lookups.append(kwargs)
        return self.agent


async def setup():
    value = execution()
    agent = Agent()
    manager = Manager(agent)
    admission = SessionRunAdmission()
    runtime = AgentRuntime(agent_manager=manager, initializer=AsyncMock(), admission_controller=admission)
    runtime.prepare_chat_turn = AsyncMock(side_effect=AssertionError("formal must not rewrite session mode"))
    runtime.plan_controller.ensure_state = AsyncMock(side_effect=AssertionError("formal must not reset Plan"))
    await runtime.register_session(session_id=value.commit.scope.session_id, channel_id=value.channel_id)
    wrapper = RuntimeFormalAgentFacade(
        runtime=runtime, agent=agent, scope=value.commit.scope,
        agent_channel_id="formal-profile", mode="agent", project_dir="project-path",
    )
    return value, agent, manager, admission, runtime, wrapper


async def collect(stream):
    return [item async for item in stream]


@pytest.mark.asyncio
async def test_formal_preserves_exact_model_policy_and_public_runtime_ownership():
    value, agent, manager, admission, runtime, wrapper = await setup()
    chunks = await collect(wrapper.process_formal_live_voice_stream(value))
    assert [item.payload["content"] for item in chunks] == ["Exact answer"]
    assert agent.seen == [value]
    assert agent.seen[0] is value
    assert agent.contexts == [runtime]
    snapshot = runtime.session_coordinator.snapshot_session("public-session")
    assert len(snapshot.executions) == 1
    assert runtime.session_coordinator.snapshot_session("formal-isolated") is None
    assert not admission.is_user_active("public-session")
    manager.begin_foreground_chat.assert_awaited_once()
    manager.end_foreground_chat.assert_awaited_once()
    runtime.prepare_chat_turn.assert_not_called()
    runtime.plan_controller.ensure_state.assert_not_called()
    assert all(item == {"channel_id": "formal-profile", "mode": "agent",
                        "project_dir": "project-path", "sub_mode": None} for item in manager.lookups)
    assert agent.cleaned
    await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["scope", "isolation", "agent", "runtime"])
async def test_invalid_binding_has_zero_agent_admission_history_effects(invalid):
    value, agent, manager, admission, runtime, wrapper = await setup()
    if invalid == "scope":
        other = replace(value.commit.scope, subject_id="other")
        value = replace(value, commit=replace(value.commit, scope=other), context=FormalContextSnapshot(other))
    elif invalid == "isolation":
        value = replace(value, internal_session_id=value.commit.scope.session_id)
    elif invalid == "agent":
        manager.agent = Agent()
    else:
        wrapper._runtime = None
    with pytest.raises((RuntimeStateError, FormalLiveVoiceViolation)):
        await collect(wrapper.process_formal_live_voice_stream(value))
    assert agent.seen == []
    assert runtime.session_coordinator.snapshot_session("public-session").executions == ()
    assert not admission.is_user_active("public-session")
    manager.begin_foreground_chat.assert_not_called()
    runtime._initializer.assert_not_called()
    await runtime.close()


@pytest.mark.asyncio
async def test_exact_runtime_cancel_settles_formal_and_preserves_other_session():
    value, agent, manager, admission, runtime, wrapper = await setup()
    agent.block = True
    pending = asyncio.create_task(collect(wrapper.process_formal_live_voice_stream(value)))
    await asyncio.wait_for(agent.started.wait(), 2)
    assert admission.is_user_active("public-session")
    wrong = await runtime.session_coordinator.cancel_execution("other-session", request_id=value.request_id)
    assert wrong.matched == 0
    assert not agent.cleaned
    result = await runtime.session_coordinator.cancel_execution("public-session", request_id=value.request_id)
    assert result.matched == 1 and result.cancelled == 1
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert agent.cleaned
    assert not admission.is_user_active("public-session")
    manager.end_foreground_chat.assert_awaited_once()
    await runtime.close()


@pytest.mark.asyncio
async def test_closed_session_cannot_be_revived_by_old_formal_binding():
    value, agent, manager, admission, runtime, wrapper = await setup()
    await collect(wrapper.process_formal_live_voice_stream(value))
    await runtime.session_coordinator.close_session("public-session")
    with pytest.raises(RuntimeStateError, match="FORMAL_SESSION_CLOSED"):
        await collect(wrapper.process_formal_live_voice_stream(replace(value, request_id="request-2")))
    await runtime.register_session(session_id="public-session", channel_id="web")
    with pytest.raises(RuntimeStateError, match="FORMAL_SESSION_GENERATION_CHANGED"):
        await collect(wrapper.process_formal_live_voice_stream(replace(value, request_id="request-3")))
    assert agent.seen == [value]
    await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["source_session_id", "source_request_id", "source_origin_request_id"])
async def test_wrong_source_is_not_published(field):
    value, agent, manager, admission, runtime, wrapper = await setup()
    agent.output_extra = {field: "other"}
    received = []
    with pytest.raises(RuntimeStateError, match="FORMAL_OUTPUT_SOURCE_MISMATCH"):
        async for chunk in wrapper.process_formal_live_voice_stream(value):
            received.append(chunk)
    assert received == []
    assert agent.cleaned
    assert not admission.is_user_active("public-session")
    await runtime.close()


@pytest.mark.asyncio
async def test_generic_host_producer_supports_nonvoice_without_mode_or_plan_rewrite():
    value, agent, manager, admission, runtime, wrapper = await setup()
    request = AgentRequest(request_id="host-request", channel_id="cli", session_id="host-session",
                           req_method=ReqMethod.CHAT_SEND, params={"mode": "code", "sub_mode": "plan"}, is_stream=True)
    validation = []

    async def produce():
        assert get_current_runtime() is runtime
        yield AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
                                 payload={"event_type": "chat.final", "content": "host"}, is_complete=True)

    results = await collect(runtime.stream_owned(request, producer=produce, validate=lambda: validation.append(True)))
    assert results[-1].payload["content"] == "host"
    assert request.params == {"mode": "code", "sub_mode": "plan"}
    assert len(validation) >= 2
    assert agent.seen == []
    runtime.prepare_chat_turn.assert_not_called()
    await runtime.close()


@pytest.mark.asyncio
async def test_speculation_flags_delegate_exact_lower_capability():
    value, agent, manager, admission, runtime, wrapper = await setup()
    assert wrapper.supports_speculative_dialogue()
    agent.supports_speculative_dialogue = lambda: False
    assert not wrapper.supports_speculative_dialogue()


@pytest.mark.asyncio
async def test_binding_revalidated_after_admission_wait_before_agent_effects():
    value, agent, manager, admission, runtime, wrapper = await setup()
    waiting = asyncio.Event()
    release = asyncio.Event()

    async def begin_user(session_id):
        waiting.set()
        await release.wait()

    admission.begin_user = begin_user
    admission.end_user = AsyncMock()
    pending = asyncio.create_task(collect(wrapper.process_formal_live_voice_stream(value)))
    await asyncio.wait_for(waiting.wait(), 2)
    manager.agent = Agent()
    release.set()
    with pytest.raises(RuntimeStateError, match="FORMAL_AGENT_BINDING_CHANGED"):
        await pending
    assert agent.seen == []
    admission.end_user.assert_awaited_once_with("public-session")
    await runtime.close()


@pytest.mark.asyncio
async def test_wire_metadata_does_not_select_trusted_producer_entry():
    value, agent, manager, admission, runtime, wrapper = await setup()
    request = AgentRequest(
        request_id="wire", channel_id="web", session_id="public-session",
        req_method=ReqMethod.CHAT_SEND, is_stream=True,
        params={"mode": "agent"}, metadata={"formal_live_voice": True, "owned": True},
    )
    result = await collect(runtime.stream(request, trigger_hook=False))
    runtime.prepare_chat_turn.assert_awaited_once()
    assert result[-1].ok is False
    assert agent.seen == []
    await runtime.close()


@pytest.mark.asyncio
async def test_unused_activation_cannot_adopt_recreated_session_generation():
    value, agent, manager, admission, runtime, wrapper = await setup()
    await runtime.session_coordinator.close_session("public-session")
    await runtime.register_session(session_id="public-session", channel_id="web")
    with pytest.raises(RuntimeStateError, match="FORMAL_SESSION_GENERATION_CHANGED"):
        await collect(wrapper.process_formal_live_voice_stream(value))
    assert agent.seen == [] and agent.gates == []
    assert runtime.session_coordinator.snapshot_session("public-session").executions == ()
    manager.begin_foreground_chat.assert_not_called()
    await runtime.close()


@pytest.mark.asyncio
async def test_wrapper_created_without_session_never_adopts_later_registration():
    value, agent, manager, admission, runtime, _wrapper = await setup()
    other = replace(value.commit.scope, session_id="not-yet-registered")
    wrapper = RuntimeFormalAgentFacade(
        runtime=runtime, agent=agent, scope=other,
        agent_channel_id="formal-profile", mode="agent", project_dir="project-path",
    )
    await runtime.register_session(session_id=other.session_id, channel_id="web")
    value = replace(value, commit=replace(value.commit, scope=other), context=FormalContextSnapshot(other))
    with pytest.raises(RuntimeStateError, match="FORMAL_SESSION_NOT_BOUND"):
        await collect(wrapper.process_formal_live_voice_stream(value))
    assert agent.seen == [] and agent.gates == []
    manager.begin_foreground_chat.assert_not_called()
    await runtime.close()


@pytest.mark.asyncio
async def test_activation_registration_cannot_reopen_tombstone():
    value, agent, manager, admission, runtime, wrapper = await setup()
    await runtime.session_coordinator.close_session("public-session")
    before = runtime.session_coordinator.snapshot_session("public-session")
    with pytest.raises(RuntimeError, match="cannot reopen"):
        await runtime.register_session(session_id="public-session", channel_id="web", allow_reopen=False)
    assert runtime.session_coordinator.snapshot_session("public-session") == before
    assert agent.seen == [] and agent.gates == []
    await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["pause_formal_tools", "resume_formal_tools", "abort_formal_tools"])
@pytest.mark.parametrize("closed", [False, True])
async def test_wrong_tool_session_has_zero_lower_effects(operation, closed):
    value, agent, manager, admission, runtime, wrapper = await setup()
    wrapper.prepare_formal_execution(value)
    if closed:
        await runtime.close()
    with pytest.raises(RuntimeStateError, match="FORMAL_TOOL_SESSION_NOT_OWNED"):
        getattr(wrapper, operation)("another-sdk-session")
    assert agent.gates == [] and agent.seen == []
    await runtime.close()


@pytest.mark.asyncio
async def test_prepared_session_policy_cannot_be_rebound_and_cleanup_survives_close():
    value, agent, manager, admission, runtime, wrapper = await setup()
    wrapper.prepare_formal_execution(value)
    with pytest.raises(RuntimeStateError, match="FORMAL_TOOL_SESSION_BINDING_CONFLICT"):
        wrapper.prepare_formal_execution(replace(value, allow_tools=True))
    assert agent.gates == []
    wrapper.pause_formal_tools(value.internal_session_id)
    await runtime.close()
    with pytest.raises(RuntimeStateError, match="FORMAL_SHARED_RUNTIME_UNAVAILABLE"):
        wrapper.resume_formal_tools(value.internal_session_id)
    wrapper.abort_formal_tools(value.internal_session_id)
    assert agent.gates == [("pause", value.internal_session_id), ("abort", value.internal_session_id)]
    with pytest.raises(RuntimeStateError, match="FORMAL_TOOL_SESSION_NOT_OWNED"):
        wrapper.abort_formal_tools(value.internal_session_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["attach", "discard"])
async def test_speculation_prepares_exact_gate_before_stream_and_releases_lease(decision):
    from jiuwenswarm.channels.live_voice.speculative_dialogue import SpeculativeDialogue, speculative_session_id

    value, agent, manager, admission, runtime, wrapper = await setup()
    value = replace(value, internal_session_id=speculative_session_id("exact"))
    candidate = SpeculativeDialogue(facade=wrapper, execution=value)
    candidate.start()
    assert agent.gates == [("pause", value.internal_session_id)]
    await asyncio.wait_for(candidate._task, 2)
    assert agent.seen == [value]
    if decision == "attach":
        chunks = await collect(candidate.attach(value))
        assert chunks[-1].payload["content"] == "Exact answer"
        assert agent.gates[-1] == ("resume", value.internal_session_id)
    else:
        await runtime.close()
        await candidate.discard("closed")
        assert agent.gates[-1] == ("abort", value.internal_session_id)
    assert wrapper._tool_sessions == {}
    await runtime.close()
