"""Shared output readers must preserve each work's own history policy."""
from copy import deepcopy
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.server.runtime.agent_adapter import interface as facade_module
from jiuwenswarm.server.runtime import session_execution
from jiuwenswarm.server.runtime.execution_context import AgentExecutionPolicy, ExecutionContextUnavailable


class Work:
    def __init__(self, name, *, native=False):
        self.binding_id = name
        self._request = AgentRequest(request_id=name, channel_id="web", session_id="shared",
            params={"query": "query-" + name, "mode": "agent", "project_dir": "/" + name})
        self.policy = AgentExecutionPolicy(origin="native", tool_policy="none", model_identity="native",
            model_config_version="1", before_effect=lambda: None) if native else AgentExecutionPolicy()
        self.model = object()

    @property
    def request(self):
        return deepcopy(self._request)

    def event(self, event_type, content="", *, task="task", **fields):
        return {"event_type": event_type, "content": content,
                "source_binding_id": self.binding_id, "source_task_id": task, **fields}


async def run_stream(monkeypatch, events, works, *, native_reader=False, legacy_reader=False,
                     raw_dict=False, cloud=False, finalizer=None, repair_observer=None, service_reader=False):
    records, compact, finals, memory, extraction = [], [], [], [], []
    reader = Work("reader", native=native_reader)

    async def source_events():
        if hasattr(events, "__aiter__"):
            async for payload in events:
                yield payload
        else:
            for payload in events:
                yield payload

    class Adapter:
        async def process_message_stream_impl(self, request, _inputs):
            if service_reader:
                session_execution.prepare_current_work(sdk_agent=self, session_id=request.session_id,
                    apply_runtime=lambda _ctx: None)
                assert session_execution.current_output_is_managed()
            async for payload in source_events():
                if isinstance(payload, Exception):
                    raise payload
                yield deepcopy(payload) if raw_dict else AgentResponseChunk(
                    request_id=request.request_id, channel_id=request.channel_id, payload=deepcopy(payload))

        async def repair_model_response(self, prompt, *, model=None):
            if repair_observer is not None:
                repair_observer(prompt, model)
            return str(id(model))

    facade = facade_module.JiuWenSwarm()
    monkeypatch.setattr(facade, "_adapter", Adapter())
    monkeypatch.setattr(facade, "_sdk_name", "harness")
    monkeypatch.setattr(facade_module, "get_config", lambda: {"preferred_language": "zh"})
    monkeypatch.setattr(facade_module, "get_memory_mode", lambda _cfg: "cloud" if cloud else "off")
    monkeypatch.setattr(facade_module, "build_user_prompt", lambda query, **_kwargs: query)
    monkeypatch.setattr(facade_module, "append_history_record", lambda **kwargs: records.append(kwargs))
    monkeypatch.setattr(facade_module, "append_compact_history_records", lambda **kwargs: compact.append(kwargs))
    monkeypatch.setattr(facade_module, "_schedule_symphony_session_feedback", lambda *_args: None)
    monkeypatch.setattr(facade_module, "is_auto_memory_enabled", lambda *_args: cloud)
    monkeypatch.setattr(facade_module, "is_memory_enabled", lambda *_args: cloud)
    monkeypatch.setattr(facade_module, "_trigger_auto_memory_extraction", lambda *args, **kwargs: extraction.append((args, kwargs)))
    monkeypatch.setattr(session_execution, "current_execution_policy", lambda: None if legacy_reader else reader.policy)

    def resolve(payload):
        binding_id = payload.get("source_binding_id")
        if binding_id is None:
            return None
        if binding_id not in works:
            raise ExecutionContextUnavailable("unknown binding")
        return works[binding_id]

    monkeypatch.setattr(session_execution, "current_output_work", resolve)

    async def finalize(content, **kwargs):
        finals.append((content, kwargs))
        return await finalizer(content, **kwargs) if finalizer is not None else content

    async def hook(event, ctx):
        memory.append((event, ctx))

    monkeypatch.setattr(facade_module, "finalize_assistant_response_if_a2ui", finalize)
    monkeypatch.setattr(facade_module.ExtensionRegistry, "get_instance",
                        lambda: SimpleNamespace(trigger=hook))
    if service_reader:
        service = session_execution.SessionExecutionService(SimpleNamespace(
            pin_agent=lambda _agent: None, unpin_agent=lambda _agent: None))
        output = [chunk async for chunk in service.stream(facade, reader.request)]
    else:
        output = [chunk async for chunk in facade.process_message_stream(reader.request)]
    return records, compact, finals, memory, extraction, output


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"event_type": "chat.final", "content": "UNOWNED"},
    RuntimeError("UNOWNED"),
])
async def test_real_managed_text_service_does_not_treat_missing_source_as_legacy(monkeypatch, payload):
    records, compact, finals, memory, extraction, _ = await run_stream(
        monkeypatch, [payload], {}, legacy_reader=True, service_reader=True, cloud=True)
    assert [item for item in records if item["role"] == "assistant"] == []
    assert not compact and not finals and not extraction
    assert all(getattr(ctx, "assistant_message", "") != "UNOWNED" for _, ctx in memory)


@pytest.mark.asyncio
async def test_text_output_cannot_self_report_native_playback_history(monkeypatch):
    text_work = Work("text")
    records, *_ = await run_stream(monkeypatch, [text_work.event("chat.final", "visible",
        live_voice_binding={"surface": "native_audio"}, session_id="foreign")],
        {text_work.binding_id: text_work})
    assistant = next(item for item in records if item["role"] == "assistant")
    assert assistant["session_id"] == "shared"
    assert "live_voice_binding" not in assistant["extra"]
    assert "session_id" not in assistant["extra"]


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_dict", [False, True])
async def test_shared_reader_keeps_text_histories_and_skips_native_side_effects(monkeypatch, raw_dict):
    a, native, b = Work("text-a"), Work("native", native=True), Work("text-b")
    events = [a.event("chat.delta", "A"), a.event("chat.reasoning", "reason-A"),
              native.event("chat.delta", "NATIVE-PRIVATE"), native.event("chat.reasoning", "NATIVE-REASON"),
              native.event("context.compression_state", compact_summary="NATIVE-COMPACT"),
              b.event("chat.delta", "B"), b.event("chat.final", "B"),
              a.event("chat.final", "A"), native.event("chat.final", "NATIVE-PRIVATE")]
    records, compact, finals, memory, extraction, output = await run_stream(
        monkeypatch, events, {w.binding_id: w for w in (a, native, b)}, raw_dict=raw_dict, cloud=True)
    assistant = [item for item in records if item["role"] == "assistant"]
    assert [(item["request_id"], item["content"]) for item in assistant] == [("text-b", "B"), ("text-a", "A")]
    assert assistant[1]["extra"]["reasoning_content"] == "reason-A"
    assert compact == []
    assert {content for content, _kwargs in finals} == {"A", "B"}
    assert "NATIVE" not in repr((records, compact, finals, memory, extraction))
    assert any(chunk.payload and chunk.payload.get("content") == "NATIVE-PRIVATE" for chunk in output)


@pytest.mark.asyncio
async def test_native_reader_never_records_inbound_or_postlude_memory(monkeypatch):
    native = Work("native", native=True)
    observed = await run_stream(monkeypatch, [native.event("chat.delta", "NATIVE")],
                                {native.binding_id: native}, native_reader=True, cloud=True)
    assert observed[:5] == ([], [], [], [], [])


@pytest.mark.asyncio
async def test_source_less_final_does_not_flush_another_managed_work(monkeypatch):
    a, native = Work("text-a"), Work("native", native=True)
    events = [a.event("chat.delta", "A"), native.event("chat.delta", "NATIVE", goal_intermediate=True),
              {"event_type": "chat.final", "content": ""}]
    records, *_ = await run_stream(monkeypatch, events, {w.binding_id: w for w in (a, native)})
    assert [item for item in records if item["role"] == "assistant"] == []


@pytest.mark.asyncio
async def test_invalid_source_fails_without_reader_history_fallback(monkeypatch):
    with pytest.raises(ExecutionContextUnavailable):
        await run_stream(monkeypatch, [{"event_type": "chat.final", "content": "forged", "source_binding_id": "unknown"}], {})


@pytest.mark.asyncio
async def test_task_identity_separates_rounds_of_the_same_work(monkeypatch):
    work = Work("text")
    events = [work.event("chat.delta", "earlier", task="one"),
              work.event("chat.reasoning", "reason-one", task="one"),
              work.event("chat.delta", "later", task="two"),
              work.event("chat.final", "", task="two"),
              work.event("chat.final", "", task="one")]
    records, *_ = await run_stream(monkeypatch, events, {work.binding_id: work})
    nonempty = [item for item in records if item["role"] == "assistant" and item["content"]]
    assert [(item["content"], item["extra"]["source_task_id"]) for item in nonempty] == [
        ("later", "two"), ("earlier", "one")]
    assert nonempty[1]["extra"]["reasoning_content"] == "reason-one"
    assert "reasoning_content" not in nonempty[0]["extra"]


@pytest.mark.asyncio
async def test_text_compact_and_history_keep_original_request_identity(monkeypatch):
    work = Work("text")
    events = [work.event("context.compression_state", compact_summary="summary", status="completed"),
              work.event("chat.final", "answer", request_id="forged", channel_id="wrong", role="user")]
    records, compact, *_ = await run_stream(monkeypatch, events, {work.binding_id: work})
    assert [(item["request_id"], item["summary"]) for item in compact] == [("text", "summary")]
    record = records[-1]
    assert (record["request_id"], record["channel_id"], record["role"]) == ("text", "web", "assistant")
    assert "request_id" not in record["extra"] and "role" not in record["extra"]


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [{"event_type": "chat.final", "content": ""}, RuntimeError("reader failed")])
async def test_unattributed_terminal_cannot_complete_managed_goal_buffer(monkeypatch, terminal):
    work = Work("text")
    events = [work.event("chat.delta", "uncommitted", goal_intermediate=True), terminal]
    records, _, finals, memory, extraction, _ = await run_stream(
        monkeypatch, events, {work.binding_id: work}, cloud=True)
    assert [item for item in records if item["role"] == "assistant"] == []
    assert finals == [] and extraction == []
    assert len(memory) == 1  # Only this reader's pre-chat hook.


@pytest.mark.asyncio
@pytest.mark.parametrize("repeated", [False, True])
@pytest.mark.parametrize("native", [False, True])
async def test_sdk_goal_answer_settles_its_round_before_reader_eof(monkeypatch, repeated, native):
    from openjiuwen.core.session.agent import Session
    from openjiuwen.core.session.stream import OutputSchema
    from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter

    work = Work("goal", native=native)
    source = {**work.event("unused"), "source_session_id": "shared", "source_request_id": None,
              "source_origin_request_id": "goal", "source_run_kind": "goal", "source_goal_id": "g",
              "source_goal_revision": 1}
    source.pop("event_type")
    source.pop("content")
    sdk = Session(session_id="shared")
    await sdk.with_source_metadata(source).write_stream(OutputSchema(type="answer", index=0,
        payload={"output": "round answer"}))
    output = sdk.stream_iterator()
    parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(await anext(output))
    await output.aclose()
    adapter = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
    adapter._should_demote_goal_intermediate_final = lambda: True
    adapter._goal_record_is_active = lambda: True
    adapter._goal_intermediate_final_repeats_streamed_text = lambda _text: repeated
    terminal = adapter._adapt_goal_intermediate_final(parsed)
    assert terminal["event_type"] == "agent.work_round_end"
    finalized = asyncio.Event()

    async def finalize(content, **_kwargs):
        finalized.set()
        return content

    async def events():
        if repeated:
            yield work.event("chat.delta", "round answer")
        yield terminal
        if not native:
            # The reader is still open. This round must finish without waiting
            # for the entire Goal, its next attempt or a transport disconnect.
            await asyncio.wait_for(finalized.wait(), timeout=2)
        yield work.event("chat.delta", "unfinished next attempt", task="next")

    records, _, finals, _, extraction, emitted = await run_stream(monkeypatch, events(),
        {work.binding_id: work}, native_reader=True, finalizer=finalize, cloud=True)
    assistant = [item for item in records if item["role"] == "assistant"]
    if native:
        assert not assistant and not finals and not extraction
    else:
        assert [(item["content"], item["extra"]["source_task_id"]) for item in assistant] == [("round answer", "task")]
        assert [content for content, _ in finals] == ["round answer"]
        assert len(extraction) == 1
    assert not any(chunk.payload.get("event_type") in {"agent.work_round_end", "chat.final"} for chunk in emitted)
    assert sum(chunk.payload.get("content") == "round answer" for chunk in emitted) == 1


@pytest.mark.asyncio
async def test_legacy_slot_does_not_borrow_managed_pending_text(monkeypatch):
    work = Work("text")
    events = [work.event("chat.delta", "managed pending"), {"event_type": "chat.delta", "content": "legacy"},
              {"event_type": "chat.final", "content": ""}]
    records, *_ = await run_stream(monkeypatch, events, {work.binding_id: work}, legacy_reader=True)
    nonempty = [item for item in records if item["role"] == "assistant" and item["content"]]
    assert [(item["request_id"], item["content"]) for item in nonempty] == [("reader", "legacy")]


@pytest.mark.asyncio
async def test_managed_postprocessors_use_frozen_models_and_keep_source(monkeypatch):
    a, b = Work("text-a"), Work("text-b")
    calls = []

    async def finalize(content, **kwargs):
        calls.append((kwargs["request_id"], kwargs["user_query"]))
        repair = await kwargs["repair_call"]("format")
        # The fake adapter has no process_message_impl. This can only succeed
        # through the managed pure-model formatting retry, never Agent replay.
        retry = await kwargs["retry_without_a2ui_call"]("repair " + kwargs["user_query"])
        assert repair == retry
        return repair

    records, _, _, memory, extraction, output = await run_stream(monkeypatch,
        [a.event("chat.final", "A"), b.event("chat.final", "B")],
        {a.binding_id: a, b.binding_id: b}, cloud=True, finalizer=finalize)
    assert calls == [("text-a", "query-text-a"), ("text-b", "query-text-b")]
    assert [(args[1].request_id, kwargs["model"]) for args, kwargs in extraction] == [
        ("text-a", a.model), ("text-b", b.model)]
    assert [(ctx.request_id, ctx.assistant_message) for _, ctx in memory[1:]] == [
        ("text-a", str(id(a.model))), ("text-b", str(id(b.model)))]
    repaired = [chunk.payload for chunk in output if chunk.payload and chunk.payload.get("content") in {
        str(id(a.model)), str(id(b.model))}]
    assert [(item["source_binding_id"], item["source_task_id"]) for item in repaired] == [
        ("text-a", "task"), ("text-b", "task")]
    assert records[-1]["request_id"] == "text-b"


@pytest.mark.asyncio
async def test_managed_model_is_required_without_mutable_adapter_fallback(monkeypatch):
    work = Work("text")
    work.model = None
    with pytest.raises(ExecutionContextUnavailable, match="MODEL_UNAVAILABLE"):
        await run_stream(monkeypatch, [work.event("chat.final", "answer")], {work.binding_id: work})


@pytest.mark.asyncio
async def test_delayed_team_a2ui_keeps_original_work_and_model(monkeypatch):
    a, b = Work("text-a"), Work("text-b")
    for work in (a, b):
        work._request.params["mode"] = "team"
    b_ready = asyncio.Event()
    raw = "<a2ui-json>[invalid]</a2ui-json>"

    async def finalize(content, **kwargs):
        if content != raw:
            return content
        if kwargs["request_id"].startswith("text-a:"):
            await asyncio.wait_for(b_ready.wait(), timeout=1)
        else:
            b_ready.set()
        return await kwargs["repair_call"]("format")

    events = [work.event("chat.final", raw, rid=1, member_name="writer", role="teammate") for work in (a, b)]
    records, _, _, _, _, output = await run_stream(monkeypatch, events,
        {a.binding_id: a, b.binding_id: b}, finalizer=finalize)
    answers = [item for item in records if item["role"] == "assistant"]
    assert {(item["request_id"], item["content"]) for item in answers} == {
        ("text-a", str(id(a.model))), ("text-b", str(id(b.model)))}
    assert any(chunk.payload and chunk.payload.get("source_binding_id") == "text-a"
               and chunk.payload.get("content") == str(id(a.model)) for chunk in output)


@pytest.mark.asyncio
async def test_auto_memory_helper_passes_explicit_model_to_background_task(monkeypatch):
    from jiuwenswarm.server.runtime.session import session_history

    work = Work("text")
    started = asyncio.Event()
    captured = {}

    async def extraction(**kwargs):
        captured.update(kwargs)
        started.set()

    monkeypatch.setattr(session_history, "read_session_history_records", lambda _: [{"role": "user", "content": "text"}])
    monkeypatch.setattr(facade_module, "_execute_auto_memory_extraction", extraction)
    facade_module._trigger_auto_memory_extraction(object(), work.request, "shared", model=work.model)
    await asyncio.wait_for(started.wait(), timeout=1)
    assert captured["model"] is work.model


@pytest.mark.asyncio
async def test_managed_retry_renders_original_context_without_workspace_setup(monkeypatch, tmp_path):
    work = Work("text")
    workspace = tmp_path / "must-not-be-created"
    work._request.params.update(workspace_dir=str(workspace), trusted_dirs=["/original"], skills=["original-skill"])
    work._request.metadata = {"sender_name": "original-person"}
    calls = []

    async def finalize(content, **kwargs):
        return await kwargs["retry_without_a2ui_call"]("format-only")

    await run_stream(monkeypatch, [work.event("chat.final", "answer")], {work.binding_id: work},
                     finalizer=finalize, repair_observer=lambda prompt, model: calls.append((prompt, model)))
    assert len(calls) == 1 and calls[0][1] is work.model
    assert all(text in calls[0][0] for text in ("format-only", "/original", "original-skill"))
    assert not workspace.exists()


@pytest.mark.asyncio
async def test_delayed_repair_rechecks_live_work_before_provider(monkeypatch):
    work = Work("text")
    works = {work.binding_id: work}
    provider_calls = []

    async def finalize(content, **kwargs):
        works.clear()
        return await kwargs["repair_call"]("format")

    with pytest.raises(ExecutionContextUnavailable):
        await run_stream(monkeypatch, [work.event("chat.final", "answer")], works,
            finalizer=finalize, repair_observer=lambda *args: provider_calls.append(args))
    assert provider_calls == []


@pytest.mark.asyncio
async def test_native_unary_skips_history_and_postprocessing(monkeypatch):
    from jiuwenswarm.common.schema.agent import AgentResponse

    work = Work("native", native=True)
    effects = []
    adapter = SimpleNamespace(handle_heartbeat=AsyncMock(return_value=None),
        process_message_impl=AsyncMock(return_value=AgentResponse(request_id="native", channel_id="web",
            ok=True, payload={"content": "NATIVE"})))
    facade = facade_module.JiuWenSwarm()
    monkeypatch.setattr(facade, "_ensure_adapter", lambda **_: adapter)
    monkeypatch.setattr(session_execution, "current_execution_policy", lambda: work.policy)
    monkeypatch.setattr(facade_module, "get_config", lambda: {})
    monkeypatch.setattr(facade_module, "get_memory_mode", lambda _: "cloud")
    monkeypatch.setattr(facade_module, "build_user_prompt", lambda query, **_: query)
    monkeypatch.setattr(facade_module, "append_history_record", lambda **kw: effects.append(kw))
    monkeypatch.setattr(facade_module, "_schedule_symphony_session_feedback", lambda *_: effects.append("feedback"))
    finalize = AsyncMock()
    hook = AsyncMock()
    monkeypatch.setattr(facade_module, "finalize_assistant_response_if_a2ui", finalize)
    monkeypatch.setattr(facade_module.ExtensionRegistry, "get_instance", lambda: SimpleNamespace(trigger=hook))
    result = await facade.process_message(work.request)
    assert result.payload["content"] == "NATIVE"
    assert effects == []
    finalize.assert_not_called()
    hook.assert_not_called()
