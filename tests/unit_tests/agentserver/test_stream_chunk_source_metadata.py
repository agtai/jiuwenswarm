"""SDK source labels survive presentation parsing without gaining authority."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openjiuwen.core.controller.schema.controller_output import ControllerOutputChunk, ControllerOutputPayload
from openjiuwen.core.controller.schema.dataframe import TextDataFrame
from openjiuwen.core.session.agent import Session
from openjiuwen.core.session.stream import OutputSchema
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter


SOURCE = {
    "source_binding_id": "native-binding", "source_origin_request_id": "native-origin",
    "source_session_id": "session", "source_request_id": None,
    "source_task_id": "task", "source_run_kind": "goal",
    "source_goal_id": "goal", "source_goal_revision": 7,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("serialized", [False, True])
@pytest.mark.parametrize("chunk_type,payload,event", [
    ("llm_output", {"content": "answer"}, "chat.delta"),
    ("llm_reasoning", {"content": "thinking"}, "chat.reasoning"),
    ("answer", {"output": {"output": "final", "source_binding_id": "nested"}}, "chat.final"),
    ("tool_result", {"tool_result": {"result": "ok", "source_binding_id": "nested"}}, "chat.tool_result"),
])
async def test_actual_source_view_survives_typed_and_serialized_parser(serialized, chunk_type, payload, event):
    session = Session(session_id="session")
    await session.with_source_metadata(SOURCE).write_stream(OutputSchema(type=chunk_type, index=0, payload=payload))
    stream = session.stream_iterator()
    chunk = await anext(stream)
    await stream.aclose()
    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(chunk.model_dump() if serialized else chunk)
    assert parsed["event_type"] == event
    assert {key: parsed[key] for key in SOURCE} == SOURCE


@pytest.mark.asyncio
@pytest.mark.parametrize("serialized", [False, True])
@pytest.mark.parametrize("kind", ["task_failed", "task_completion"])
async def test_controller_source_comes_only_from_metadata_and_completion_stays_skipped(serialized, kind):
    session = Session(session_id="session")
    await session.with_source_metadata(SOURCE).write_stream(ControllerOutputChunk(index=0,
        payload=ControllerOutputPayload(type=kind, data=[TextDataFrame(text="actual failure")],
                                        metadata={"source_binding_id": "before-view"})))
    stream = session.stream_iterator()
    chunk = await anext(stream)
    await stream.aclose()
    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(chunk.model_dump() if serialized else chunk)
    if kind == "task_completion":
        assert parsed is None
    else:
        assert parsed["event_type"] == "chat.error"
        assert parsed["error"] == "actual failure"
        assert {key: parsed[key] for key in SOURCE} == SOURCE


@pytest.mark.parametrize("outer", [{}, SOURCE])
def test_tool_update_never_promotes_nested_source_fields(outer):
    nested = {"status": "done", "source_binding_id": "model-self-report", "source_private": "secret"}
    chunk = SimpleNamespace(type="tool_update", payload={"tool_update": nested, **outer})
    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(chunk)
    assert parsed["status"] == "done"
    assert {key: value for key, value in parsed.items() if key.startswith("source_")} == outer
    assert nested["source_binding_id"] == "model-self-report"


@pytest.mark.parametrize("chunk", [
    {"output": "legacy", **SOURCE},
    SimpleNamespace(type="tool_update", payload={"tool_update": {"status": "done", **SOURCE}}),
    SimpleNamespace(type="llm_output", payload={"content": "answer", "run_context": {"extra": {"source_metadata": SOURCE}}}),
    SimpleNamespace(type="llm_output", payload={"content": '{"source_binding_id":"text"}'}),
    SimpleNamespace(type="tool_update", payload={"status": "done", "source_binding_id": {"bad": "shape"},
                                               "source_goal_revision": True, "source_request_id": ["bad"]}),
    {"type": "controller_output", "payload": {"type": "task_failed", "data": [], **SOURCE}},
    {"type": "controller_output", "payload": {"type": "task_failed", "data": [], "metadata": [SOURCE]}},
])
def test_wrong_or_legacy_source_locations_never_gain_labels(chunk):
    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(chunk)
    assert parsed is not None
    assert not any(key.startswith("source_") for key in parsed)


def test_nullable_source_fields_are_preserved_without_inference():
    source = dict.fromkeys(SOURCE)
    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk({"type": "llm_output", "payload": {"content": "ok", **source}})
    assert {key: parsed[key] for key in source} == source


@pytest.mark.asyncio
async def test_old_text_reader_keeps_each_actual_work_source(monkeypatch):
    # No service-owned execution is active in this parser/reader compatibility
    # case; the real service exposes no binding instead of replacing its module.
    adapter = JiuWenSwarmDeepAdapter()
    adapter._is_session_scoped_adapter = True
    for name in ("_bind_runtime_cron_context", "_reset_runtime_cron_context", "_apply_model_to_react_agent",
                 "_mark_session_active", "_register_session_agent_task", "_unregister_session_agent_task",
                 "_unmark_session_active", "_flush_pending_goal_objective_history"):
        monkeypatch.setattr(adapter, name, lambda *_args, **_kwargs: None)
    monkeypatch.setattr(adapter, "_has_valid_model_config", lambda *_args: True)
    monkeypatch.setattr(adapter, "_resolve_model_for_request", lambda *_args: None)
    monkeypatch.setattr(adapter, "_update_runtime_config", AsyncMock())
    monkeypatch.setattr(adapter, "_handle_slash_command", AsyncMock(return_value=None))
    session = Session(session_id="session")
    text_source = {**SOURCE, "source_binding_id": "text-binding", "source_request_id": "text-origin",
                   "source_run_kind": "user", "source_goal_id": None, "source_goal_revision": None}
    for view_source, text in ((SOURCE, "native"), (text_source, "text"), (SOURCE, "native-late")):
        view = session.with_source_metadata(view_source)
        for kind in ("llm_reasoning", "llm_output"):
            await view.write_stream(OutputSchema(type=kind, index=0, payload={"content": text}))
    raw_stream = session.stream_iterator()

    class Stream:
        async def __aiter__(self):
            for _ in range(6):
                yield await anext(raw_stream)

        async def close(self, **_kwargs):
            await raw_stream.aclose()

    adapter._instance = SimpleNamespace(attach_output=AsyncMock(return_value=Stream()), send_input=AsyncMock(),
                                        get_context_usage=lambda **_kwargs: {})
    request = AgentRequest(request_id="old-reader-id", session_id="session", channel_id="web",
                           params={"query": "hello", "mode": "agent"}, is_stream=True)
    chunks = [chunk async for chunk in adapter.process_message_stream_impl(request, {"query": "hello"})]
    visible = [chunk.payload for chunk in chunks if isinstance(chunk.payload, dict)
               and chunk.payload.get("event_type") in ("chat.delta", "chat.reasoning")]
    assert len(visible) == 6, chunks
    assert [item["source_binding_id"] for item in visible] == ["native-binding"] * 2 + ["text-binding"] * 2 + ["native-binding"] * 2
    assert [item["source_request_id"] for item in visible] == [None] * 2 + ["text-origin"] * 2 + [None] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize('source_kind,latch,expected', [
    ('user', 'goal', 'chat.final'), ('goal', 'user', 'agent.work_round_end'),
])
async def test_actual_sdk_source_kind_wins_over_old_reader_latch(source_kind, latch, expected):
    session = Session(session_id='source-review')
    source = dict(source_binding_id='bound-work', source_origin_request_id='origin',
                  source_session_id='source-review', source_task_id='actual-task',
                  source_run_kind=source_kind, source_request_id='origin' if source_kind == 'user' else None,
                  source_goal_id='actual-goal' if source_kind == 'goal' else None,
                  source_goal_revision=1 if source_kind == 'goal' else None)
    await session.with_source_metadata(source).write_stream(OutputSchema(
        type='answer', index=0, payload={'output': 'late final'}))
    output = session.stream_iterator()
    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(await anext(output))
    await output.aclose()
    adapter = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
    adapter._instance = SimpleNamespace(goal_manager=SimpleNamespace(
        peek=lambda: SimpleNamespace(status='active')))
    adapter._stream_round_kind_latch = latch
    adapter._stream_content_run_kind = latch
    adapter._goal_intermediate_final_repeats_streamed_text = lambda _content: False
    result = adapter._adapt_goal_intermediate_final(parsed)
    assert result['event_type'] == expected, result


@pytest.mark.asyncio
@pytest.mark.parametrize('transition,repeated', [('same', True), ('task', False), ('binding', False)])
@pytest.mark.parametrize('serialized', [False, True])
async def test_actual_sdk_source_key_scopes_goal_visible_text_memo(transition, repeated, serialized):
    session = Session(session_id='memo-review')

    def source(binding='binding-a', task='task-a'):
        return dict(source_binding_id=binding, source_origin_request_id='origin',
                    source_session_id='memo-review', source_task_id=task,
                    source_run_kind='goal', source_request_id=None,
                    source_goal_id='goal', source_goal_revision=1)

    original = session.with_source_metadata(source())
    await original.write_stream(OutputSchema(type='llm_output', index=0, payload={'content': 'identical answer'}))
    await original.write_stream(OutputSchema(type='llm_reasoning', index=1, payload={'content': 'reasoning'}))
    final_source = source(binding='binding-b' if transition == 'binding' else 'binding-a',
                          task='task-b' if transition == 'task' else 'task-a')
    await session.with_source_metadata(final_source).write_stream(OutputSchema(
        type='answer', index=2, payload={'output': 'identical answer'}))
    stream = session.stream_iterator()
    adapter = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
    adapter._instance = SimpleNamespace(goal_manager=SimpleNamespace(
        peek=lambda: SimpleNamespace(status='active')))
    adapter._stream_content_run_kind = 'goal'
    adapter._reset_round_kind_latch()
    try:
        for index in range(3):
            chunk = await anext(stream)
            if serialized:
                chunk = chunk.model_dump()
            adapter._track_round_output_boundary(chunk)
            if index == 0:
                adapter._note_round_visible_text('identical answer')
            elif index == 1:
                assert adapter._stream_round_visible_text == 'identical answer'
            else:
                parsed = adapter._parse_stream_chunk(chunk)
                final = adapter._adapt_goal_intermediate_final(parsed)
                assert final['event_type'] == 'agent.work_round_end'
                assert final['repeats_streamed_text'] is repeated
                assert adapter._stream_round_source_key == (final_source['source_binding_id'], final_source['source_task_id'])
                assert adapter._stream_round_kind_latch == 'goal'
    finally:
        await stream.aclose()
