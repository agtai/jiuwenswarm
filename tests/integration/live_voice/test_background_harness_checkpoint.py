"""Host preparation must bind guards before the native supervisor is created."""

import asyncio
import json
from contextlib import suppress
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm
from openjiuwen.core.application.tasks.execution_checkpoint import background_task_checkpoint
from openjiuwen.core.context_engine import ContextEngineConfig
from openjiuwen.core.context_engine.context.context import SessionModelContext
from openjiuwen.core.foundation.llm import AssistantMessage, UserMessage, ToolCall
from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig, AgentCard
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext, AgentCallbackEvent, ToolCallInputs
from openjiuwen.harness.deep_agent import DeepAgent


@pytest.fixture(autouse=True)
async def stop_native_runner():
    yield
    from openjiuwen.core.runner import Runner
    await Runner.stop()


@pytest.mark.asyncio
async def test_rejected_preparation_does_not_cleanup_existing_session(tmp_path):
    cleanup = []

    async def prepare(sid):
        raise RuntimeError("EXECUTION_TARGET_NOT_BOUND: background task session was already used")

    async def clean(sid):
        cleanup.append(sid)

    facade = SimpleNamespace(
        _adapter=SimpleNamespace(prepare_background_project_session=prepare, cleanup_session_adapter=clean),
        get_project_execution_root=lambda: str(tmp_path), _build_inputs=lambda request: ({}, None, None))
    request = AgentRequest(request_id="duplicate", session_id="existing", params={"project_dir": str(tmp_path)})
    with background_task_checkpoint("existing", None):
        with pytest.raises(RuntimeError, match="already used"):
            async for _ in JiuWenSwarm.process_background_code_task_stream(facade, request):
                pass
    assert cleanup == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reject,write_mode", [
    (False, None), (True, None), (False, "unplanned"), (False, "planned"),
    (False, "late_model"), (False, "late_tool"),
    (False, "cancel_model"), (False, "cancel_tool"),
])
async def test_host_preparation_supervisor_inherits_checkpoint(tmp_path, reject, write_mode):
    """Real facade, supervisor loop and ReAct model boundary; controlled work/model."""
    sid = "formal-task-supervisor"
    messages = []
    adopted = []
    completed = asyncio.get_running_loop().create_future()
    delayed = []
    release_delayed = asyncio.Event()
    file_plan = None
    if write_mode in {"planned", "unplanned"}:
        from tests.unit_tests.live_voice.test_file_effect_plan import session, proposal
        file_plan = session(tmp_path)
        if write_mode == "planned":
            await file_plan.seal(proposal(file_plan))
    root = ReActAgent(AgentCard(id="supervisor-checkpoint", name="Task", description="test"))
    root.configure(ReActAgentConfig(model_name="controlled"))

    class Model:
        async def invoke(self, **kwargs):
            messages.extend(message.content for message in kwargs["messages"])
            return AssistantMessage(content="done")

    root._llm = Model()
    harness = DeepAgent(AgentCard(name="checkpoint-harness", description="test"))
    harness._react_agent = root
    queued = []
    harness._event_manager = SimpleNamespace(next_work=lambda: queued.pop(0) if queued else None)
    harness._interaction_output = SimpleNamespace(has_consumer=lambda: bool(queued))

    async def execute_round(work):
        try:
            context = SessionModelContext("supervisor-context", sid, ContextEngineConfig(
                enable_openrouter_model_context_window_tokens=False), history_messages=[], processors=[])
            await context.add_messages(UserMessage(content="Original itinerary"))
            await root._call_model(AgentCallbackContext(agent=root, context=context), context, [])
            if write_mode and write_mode.startswith(("late_", "cancel_")):
                async def delayed_callback():
                    await release_delayed.wait()
                    if write_mode.endswith("model"):
                        await root._call_model(AgentCallbackContext(agent=root, context=context), context, [])
                    else:
                        call = ToolCall(id="late-write", name="write_file", type="function", arguments="{}")
                        ctx = AgentCallbackContext(agent=root, context=context,
                            inputs=ToolCallInputs(tool_name="write_file", tool_call=call))
                        await ctx.fire(AgentCallbackEvent.BEFORE_TOOL_CALL)
                        (tmp_path / "forbidden.txt").write_text("late effect", encoding="utf-8")
                delayed.append(asyncio.create_task(delayed_callback()))
            if file_plan is not None:
                destination = file_plan.worktree / "D.md"
                call = ToolCall(id="write-result", name="write_file", type="function",
                    arguments=json.dumps({"file_path": str(destination)}))
                ctx = AgentCallbackContext(agent=root, context=context,
                    inputs=ToolCallInputs(tool_name="write_file", tool_call=call))
                await ctx.fire(AgentCallbackEvent.BEFORE_TOOL_CALL)
                destination.write_text("afternoon empty", encoding="utf-8")
            completed.set_result(None)
        except Exception as error:
            completed.set_exception(error)
        finally:
            harness._interaction_started = False

    harness._execute_round = execute_round
    child = SimpleNamespace(_instance=harness,
        _stream_event_rail=SimpleNamespace(_resolve_sid=lambda ctx, session: sid))

    class Adapter:
        async def prepare_background_project_session(self, session_id):
            assert session_id == sid
            harness._interaction_started = True
            harness._ensure_supervisor_running()
            await asyncio.sleep(0)  # The supervisor is already waiting before input.

        def _get_cached_session_adapter(self, session_id):
            return child

        async def process_message_stream_impl(self, request, inputs):
            queued.append(inputs)
            harness._interaction_wakeup.set()
            await asyncio.wait_for(asyncio.shield(completed), 3)
            if write_mode and write_mode.startswith("cancel_"):
                raise asyncio.CancelledError()
            yield AgentResponseChunk(request.request_id, request.channel_id,
                payload={"event_type": "chat.final", "content": "done"}, is_complete=True)

        async def cleanup_session_adapter(self, session_id):
            harness._interaction_started = False
            task = harness._interaction_supervisor_task
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    facade = SimpleNamespace(_adapter=Adapter(), get_project_execution_root=lambda: str(tmp_path),
        _build_inputs=lambda request: ({}, None, None))
    request = AgentRequest(request_id="task-supervisor", channel_id="web", session_id=sid,
        params={"project_dir": str(tmp_path)})

    async def adopt(context):
        adopted.append(True)
        if reject:
            raise RuntimeError("CONTROLLED_ADJUSTMENT_REJECTED")
        await context.add_messages(UserMessage(content="Leave the afternoon empty"))

    with background_task_checkpoint(sid, adopt, file_plan=file_plan):
        if write_mode and write_mode.startswith("cancel_"):
            with pytest.raises(asyncio.CancelledError):
                async for _ in JiuWenSwarm.process_background_code_task_stream(facade, request):
                    pass
        elif reject:
            with pytest.raises(RuntimeError, match="CONTROLLED_ADJUSTMENT_REJECTED"):
                async for _ in JiuWenSwarm.process_background_code_task_stream(facade, request):
                    pass
            assert not messages
        elif write_mode == "unplanned":
            with pytest.raises(RuntimeError, match="FILE_EFFECT_CURRENT_PLAN_REQUIRED"):
                async for _ in JiuWenSwarm.process_background_code_task_stream(facade, request):
                    pass
            assert not (file_plan.worktree / "D.md").exists()
        else:
            result = [chunk async for chunk in JiuWenSwarm.process_background_code_task_stream(facade, request)]
            assert result[-1].is_complete
            assert messages[-1] == "Leave the afternoon empty"
            if write_mode == "planned":
                assert (file_plan.worktree / "D.md").read_text(encoding="utf-8") == "afternoon empty"
                assert not (file_plan.target / "D.md").exists()
        if delayed:
            # The background checkpoint remains open: revocation must come from
            # the facade's scope exit, including its cancellation path.
            from openjiuwen.core.runner.callback.errors import AbortError
            before = list(messages)
            release_delayed.set()
            with pytest.raises(AbortError, match="SCOPED_AGENT_RAIL_CLOSED"):
                await asyncio.wait_for(delayed[0], 3)
            assert messages == before
            assert not (tmp_path / "forbidden.txt").exists()
    assert adopted == [True]
