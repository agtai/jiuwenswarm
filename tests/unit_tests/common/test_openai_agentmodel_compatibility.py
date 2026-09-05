"""Exercise the actual model builder, SDK serialization and response parsing."""
from __future__ import annotations

import json
import asyncio
from copy import deepcopy

import httpx
import pytest
from openai import AsyncOpenAI
from openjiuwen.core.foundation.llm import Model
from openjiuwen.core.foundation.llm.model_clients.openai_model_client import OpenAIModelClient

from jiuwenswarm.server.runtime.agent_adapter.interface_deep import build_model_from_entry


def response_payload(text="Unchanged answer.", *, items=None, status="completed"):
    return {"id": "resp_fixture", "object": "response", "created_at": 0,
            "model": "gpt-5.6-sol", "status": status,
            "output": items if items is not None else [{"type": "message", "id": "msg_fixture",
                "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": text, "annotations": []}]}],
            "usage": {"input_tokens": 4, "output_tokens": 3, "total_tokens": 7}}


def http_response(payload, *, stream=False, event_mode="normal"):
    if not stream:
        return httpx.Response(200, json=payload)
    events = []
    for i, item in enumerate(payload["output"]):
        for part in item.get("content", []):
            events.append({"type": "response.refusal.delta" if part["type"] == "refusal" else "response.output_text.delta", "item_id": item["id"],
                           "output_index": i, "content_index": 0, "delta": part.get("text", part.get("refusal", ""))})
        events.append({"type": "response.output_item.done", "output_index": i, "item": item})
    events.append({"type": "response." + payload["status"], "response": payload})
    item_events = [event for event in events if event["type"] == "response.output_item.done"]
    if event_mode in {"reordered", "duplicate", "missing"}:
        events = [event for event in events if event["type"] != "response.output_item.done"]
        extra = {"reordered": list(reversed(item_events)), "duplicate": item_events * 2, "missing": []}[event_mode]
        events[-1:-1] = extra
    elif event_mode == "unterminated":
        events.pop()
    elif event_mode == "after_terminal":
        events.append({"type": "response.output_item.done", "output_index": 0, "item": payload["output"][0]})
    elif event_mode == "mismatched_text":
        events.insert(0, {"type": "response.output_text.delta", "item_id": "msg_missing", "output_index": 0, "content_index": 0, "delta": "unexpected"})
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                          content="".join("data: " + json.dumps(c) + "\n\n" for c in events))


def entry(*, name="gpt-5.6", base="https://api.openai.com/v1", provider="OpenAI"):
    return {"model_name": name, "api_base": base, "api_key": "test-key",
            "client_provider": provider, "max_retries": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("options", [{}, {"temperature": 0, "top_p": 0.2, "max_tokens": 256}])
async def test_official_requests_use_supported_parameters(monkeypatch, stream, options):
    sent = []

    def respond(request):
        assert request.url.path == "/v1/responses"
        sent.append(json.loads(request.content))
        return http_response(response_payload(), stream=stream)

    async with AsyncOpenAI(api_key="test-key", base_url="https://api.openai.com/v1", http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        monkeypatch.setattr(OpenAIModelClient, "_create_async_openai_client", lambda self, timeout=None: client)
        config = {"temperature": 0.95, "max_tokens": 128}
        model = build_model_from_entry(entry(), config)
        messages = [{"role": "user", "content": "Fixture input."}]
        if stream:
            chunks = [chunk async for chunk in model.stream(messages, **options)]
            assert "".join(chunk.content or "" for chunk in chunks) == "Unchanged answer."
        else:
            result = await model.invoke(messages, response_format={"type": "json_object"}, **options)
            assert result.content == "Unchanged answer."
        assert len(sent) == 1
        body = sent[0]
        assert "temperature" not in body
        assert "top_p" not in body
        assert "max_tokens" not in body
        assert body["max_output_tokens"] == (256 if options else 128)
        assert body["input"] == messages
        assert body["store"] is False
        assert "reasoning.encrypted_content" in body["include"]
        if not stream:
            assert body["text"]["format"] == {"type": "json_object"}
        assert config == {"temperature": 0.95, "max_tokens": 128}
        assert model.model_client_config.api_key == "test-key"
        clone = Model(model_client_config=model.model_client_config,
                      model_config=model.model_config.model_copy(deep=True))
        assert type(clone._client) is type(model._client)


@pytest.mark.parametrize("config", [entry(name="gpt-4o"), entry(base="https://api.openai.com.example.invalid/v1"), entry(base="https://compatible.example.invalid/v1"), entry(name="deepseek-v4-flash", base="https://api.deepseek.com/v1", provider="DeepSeek")])
def test_existing_provider_and_model_requests_are_unchanged(config):
    model = build_model_from_entry(config, {"temperature": 0.4, "max_tokens": 70})
    params = model._client._build_request_params(messages="Fixture", tools=None, temperature=0, top_p=None, model=None, stop=None, max_tokens=None, stream=False)
    assert params["temperature"] == 0
    assert params["max_tokens"] == 70
    assert "max_completion_tokens" not in params


def request_params(model, **options):
    return model._client._request_params(messages="Fixture", tools=None, stream=False, **options)


@pytest.mark.parametrize("effort", [None, "medium", "high", "none"])
def test_reasoning_capability_and_extra_body_precedence(effort):
    request = {"temperature": 0.8, "max_tokens": 128,
               "extra_body": {"max_tokens": 256, "temperature": 0.3, "top_p": 0.5,
                              "metadata": {"test": "retained"}}}
    if effort is not None:
        request["extra_body"]["reasoning_effort"] = effort
    original = deepcopy(request)
    model = build_model_from_entry(entry(name="gpt-5.6-sol"), request)
    params = request_params(model)
    body = params
    assert body["max_output_tokens"] == 256
    assert "max_tokens" not in body
    assert body["metadata"] == {"test": "retained"}
    if effort == "none":
        assert body["temperature"] == 0.3
        assert body["top_p"] == 0.5
    else:
        assert "temperature" not in body
        assert "top_p" not in body
    assert request == original


def test_unrepaired_sdk_fails_before_client_creation(monkeypatch):
    from jiuwenswarm.common import openai_responses_client as adapter
    monkeypatch.setattr(adapter, "version", lambda name: "0.1.16")
    with pytest.raises(RuntimeError, match="context-preserving SDK"):
        build_model_from_entry(entry(), {})
    assert build_model_from_entry(entry(name="gpt-4o"), {}).model_config.model_name == "gpt-4o"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_refusal_and_text_follow_provider_order(monkeypatch, stream):
    payload = response_payload()
    payload["output"][0]["content"] = [
        {"type": "output_text", "text": "A", "annotations": []},
        {"type": "refusal", "refusal": "R"},
        {"type": "output_text", "text": "B", "annotations": []},
    ]
    async with AsyncOpenAI(api_key="test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: http_response(payload, stream=stream)))) as client:
        monkeypatch.setattr(OpenAIModelClient, "_create_async_openai_client", lambda self, timeout=None: client)
        model = build_model_from_entry(entry(), {})
        if stream:
            parts = [chunk.content async for chunk in model.stream("Fixture")]
            assert "".join(parts) == "ARB"
        else:
            assert (await model.invoke("Fixture")).content == "ARB"


@pytest.mark.asyncio
async def test_conflicting_limits_fail_before_http(monkeypatch):
    calls = []
    def forbidden_client(*args, **kwargs):
        calls.append(1)
        raise AssertionError("No HTTP client may be acquired")
    monkeypatch.setattr(OpenAIModelClient, "_create_async_openai_client", forbidden_client)
    model = build_model_from_entry(entry(), {"max_tokens": 100, "max_completion_tokens": 200})
    with pytest.raises(ValueError, match="Conflicting"):
        await model.invoke("Fixture")
    assert calls == []


@pytest.mark.parametrize("field,value", [("api_key", ""), ("api_base", "")])
def test_original_openai_config_validation_is_preserved(field, value):
    config = {**entry(), field: value}
    with pytest.raises(Exception, match=field):
        build_model_from_entry(config, {})


@pytest.mark.asyncio
async def test_request_cancellation_and_concurrent_options_are_isolated(monkeypatch):
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    requests = []
    async def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if body["input"][0]["content"] == "cancel":
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return http_response(response_payload("OK"))

    async with AsyncOpenAI(api_key="test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        monkeypatch.setattr(OpenAIModelClient, "_create_async_openai_client", lambda self, timeout=None: client)
        model = build_model_from_entry(entry(), {"temperature": 0.95})
        pending = asyncio.create_task(model.invoke("cancel"))
        await asyncio.wait_for(entered.wait(), 3)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert cancelled.is_set()
        responses = await asyncio.gather(
            model.invoke("reason", reasoning_effort="medium"),
            model.invoke("sample", reasoning_effort="none", temperature=0.7),
        )
        assert [r.content for r in responses] == ["OK", "OK"]
        assert len(requests) == 3
        by_input = {r["input"][0]["content"]: r for r in requests}
        assert "temperature" not in by_input["reason"]
        assert by_input["sample"]["temperature"] == 0.7
        assert model.model_config.temperature == 0.95


@pytest.mark.asyncio
@pytest.mark.parametrize("stream,incomplete,event_mode", [
    (False, False, "normal"), (True, False, "normal"),
    (False, True, "normal"), (True, True, "normal"),
    (True, False, "reordered"), (True, False, "duplicate"),
    (True, False, "missing"), (True, False, "unterminated"),
    (True, False, "after_terminal"), (True, False, "mismatched_text"),
    (False, False, "duplicate_call_id"), (True, False, "duplicate_call_id"),
    (False, False, "execution_rewrite"), (True, False, "execution_rewrite"),
])
async def test_real_react_context_preserves_tool_continuation(monkeypatch, stream, incomplete, event_mode):
    from openjiuwen.core.runner import Runner
    from openjiuwen.core.session.agent import create_agent_session
    from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig
    from openjiuwen.core.single_agent.schema.agent_card import AgentCard
    from openjiuwen.core.foundation.tool import LocalFunction, ToolCard
    from openjiuwen.core.single_agent.rail.base import AgentRail

    calls = []
    sent = []
    items = [{"type": "reasoning", "id": "rs_fixture", "summary": [], "encrypted_content": "opaque-test-only"}]
    items += [{"type": "function_call", "id": f"fc_{n}", "call_id": f"call_{n}", "name": "probe",
               "arguments": json.dumps({"value": n}), "status": "completed"} for n in (1, 2)]
    if event_mode == "duplicate_call_id":
        items[-1]["call_id"] = items[-2]["call_id"]
    if event_mode == "execution_rewrite":
        for item in items[1:]:
            item["arguments"] = json.dumps({**json.loads(item["arguments"]), "purpose": "test"})

    class ExecutionArgumentRail(AgentRail):
        async def before_tool_call(self, ctx):
            arguments = json.loads(ctx.inputs.tool_args)
            arguments.pop("purpose")
            ctx.inputs.tool_args = json.dumps(arguments)

    def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        if len(sent) == 1:
            return http_response(response_payload(items=items, status="incomplete" if incomplete else "completed"), stream=stream, event_mode=event_mode)
        assert not incomplete
        replay = [i for i in body["input"] if i.get("type") in {"reasoning", "function_call"}]
        assert replay == items
        assert [i["call_id"] for i in body["input"] if i.get("type") == "function_call_output"] == ["call_1", "call_2"]
        return http_response(response_payload("Two tools completed."), stream=stream)

    await Runner.start()
    try:
        async with AsyncOpenAI(api_key="test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            monkeypatch.setattr(OpenAIModelClient, "_create_async_openai_client", lambda self, timeout=None: client)
            model = build_model_from_entry(entry(), {})
            card = AgentCard(id=f"responses-context-{stream}-{incomplete}")
            agent = ReActAgent(card=card)
            agent.configure(ReActAgentConfig().configure_max_iterations(3))
            if event_mode == "execution_rewrite":
                await agent.register_rail(ExecutionArgumentRail())
            tool = LocalFunction(card=ToolCard(id="responses-probe", name="probe", description="Synthetic test tool",
                                 input_params={"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}),
                                 func=lambda value: calls.append(value) or value)
            Runner.resource_mgr.add_tool(tool)
            agent.ability_manager.add(tool.card)
            monkeypatch.setattr(agent, "_get_llm", lambda: model)
            session = create_agent_session(session_id=card.id, card=card)
            await session.pre_run(inputs={"query": "Use the tools"})
            frames = []
            original_write = session.write_stream
            async def capture(frame):
                frames.append(frame)
                return await original_write(frame)
            session.write_stream = capture
            if incomplete or event_mode in {"unterminated", "after_terminal", "mismatched_text", "duplicate_call_id"}:
                try:
                    result = await agent.invoke({"query": "Use the tools"}, session=session, _streaming=stream)
                except Exception:
                    pass
                else:
                    assert result.get("result_type") != "answer"
                assert calls == []
                assert len(sent) == 1
            else:
                result = await agent.invoke({"query": "Use the tools"}, session=session, _streaming=stream)
                assert result["output"] == "Two tools completed."
                assert sorted(calls) == [1, 2]
                assert len(sent) == 2
                spoken = "".join(f.payload.get("content", "") for f in frames if getattr(f, "type", None) == "llm_output")
                assert "opaque-test-only" not in spoken
    finally:
        await Runner.stop()


def test_persisted_metadata_isolation_and_wrong_binding():
    from openjiuwen.core.foundation.llm import AssistantMessage
    from openjiuwen.core.foundation.llm.schema.message_chunk import AssistantMessageChunk
    from jiuwenswarm.common.openai_responses_client import responses_input
    model = build_model_from_entry(entry(), {})
    payload = response_payload()
    payload["usage"]["output_tokens_details"] = {"reasoning_tokens": 2}
    original = model._client._parsed(payload, model="gpt-5.6")
    assert original.usage_metadata.reasoning_tokens == 2
    restored = AssistantMessage.model_validate_json(original.model_dump_json())
    combined = AssistantMessageChunk(content="") + AssistantMessageChunk(**restored.model_dump())
    assert responses_input([combined], model="gpt-5.6", api_base=entry()["api_base"]) == payload["output"]
    combined.metadata["openai_responses_v1"]["items"][0]["id"] = "changed"
    assert restored.metadata == original.metadata
    with pytest.raises(ValueError, match="does not match"):
        responses_input([restored], model="gpt-5.6-sol", api_base=entry()["api_base"])
    restored.content = "Edited text"
    with pytest.raises(ValueError, match="does not match"):
        responses_input([restored], model="gpt-5.6", api_base=entry()["api_base"])


def test_request_images_tools_and_optional_schema_are_preserved():
    model = build_model_from_entry(entry(), {"extra_body": {"max_tokens": None}})
    messages = [{"role": "developer", "content": "Instruction"}, {"role": "user", "content": [
        {"type": "text", "text": "Describe"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,fixture", "detail": "low"}}]}]
    tools = [{"type": "function", "function": {"name": "test", "parameters": {"type": "object", "properties": {"optional": {"type": "string"}}}}}]
    body = model._client._request_params(messages, tools, stream=False)
    assert body["input"][0] == messages[0]
    assert body["input"][1]["content"][1] == {"type": "input_image", "image_url": "data:image/png;base64,fixture", "detail": "low"}
    assert body["tools"][0]["parameters"] == tools[0]["function"]["parameters"]
    assert body["tools"][0]["strict"] is False
    assert "max_tokens" not in body


def test_unknown_server_fields_keep_extra_body_escape_hatch():
    model = build_model_from_entry(entry(), {"extra_body": {"future_server_field": {"value": 1}}})
    body = request_params(model)
    assert body["extra_body"] == {"future_server_field": {"value": 1}}
    assert "future_server_field" not in {k: v for k, v in body.items() if k != "extra_body"}


@pytest.mark.parametrize("options", [{"input": []}, {"tools": []}, {"extra_body": {"input": []}}])
def test_extra_body_cannot_replace_agent_owned_input(options):
    model = build_model_from_entry(entry(), {"extra_body": options})
    with pytest.raises(ValueError, match="cannot replace"):
        request_params(model)


@pytest.mark.asyncio
async def test_stream_cancellation_closes_response_but_not_shared_client(monkeypatch):
    entered = asyncio.Event()
    closed = asyncio.Event()
    class PausedResponse(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"type":"response.output_text.delta","delta":"partial","item_id":"msg_a","output_index":0,"content_index":0}\n\n'
            entered.set()
            await asyncio.Future()
        async def aclose(self):
            closed.set()

    async with AsyncOpenAI(api_key="test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"content-type":"text/event-stream"}, stream=PausedResponse())
    ))) as client:
        monkeypatch.setattr(OpenAIModelClient, "_create_async_openai_client", lambda self, timeout=None: client)
        monkeypatch.setattr(OpenAIModelClient, "_use_shared_client", lambda self: True)
        model = build_model_from_entry(entry(), {})
        async def consume():
            return [chunk async for chunk in model.stream("Fixture")]
        task = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
        assert not client.is_closed()
