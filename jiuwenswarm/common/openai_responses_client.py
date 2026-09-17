"""API-key Responses adapter for the configured OpenAI GPT-5.6 Agent.

Uses the SDK's client registry and existing HTTP pool. Provider output items are
opaque message metadata, so encrypted reasoning follows the same Agent context
as its tool calls and never enters the spoken answer.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
from inspect import signature
import json
from urllib.parse import urlsplit

from openai.resources.responses import AsyncResponses

from openjiuwen.core.foundation.llm import ModelClientConfig
from openjiuwen.core.foundation.llm.model_clients.openai_model_client import OpenAIModelClient
from openjiuwen.core.foundation.llm.schema.message_chunk import AssistantMessageChunk
from openjiuwen.core.foundation.llm.utils.responses_utils import parse_response, parse_stream_event
from openjiuwen.core.runner.callback import trigger
from openjiuwen.core.runner.callback.events import LLMCallEvents

from jiuwenswarm.common.openai_responses_dependency import SDK_VERSION

_PROVIDER = "JiuwenSwarmOpenAIResponses"
_VERIFIED_MODELS = frozenset({"gpt-5.6", "gpt-5.6-sol"})
_METADATA = "openai_responses_v1"
_RESPONSE_ARGUMENTS = frozenset(signature(AsyncResponses.create).parameters)


def _official_endpoint(api_base: str) -> bool:
    try:
        url = urlsplit(api_base)
        return (url.scheme == "https" and url.hostname == "api.openai.com"
                and url.port in (None, 443) and url.path.rstrip("/") == "/v1"
                and not any((url.query, url.fragment, url.username, url.password)))
    except ValueError:
        return False


def _message_dict(message):
    return message if isinstance(message, dict) else message.model_dump()


def _signature(message: dict) -> str:
    value = {key: message.get(key) or ([] if key == "tool_calls" else "")
             for key in ("content", "tool_calls")}
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def responses_input(messages, *, model: str, api_base: str) -> list[dict]:
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    if not messages:
        raise ValueError("Responses input must not be empty")
    result = []
    for raw in messages:
        message = _message_dict(raw)
        role = message.get("role", "user")
        opaque = (message.get("metadata") or {}).get(_METADATA)
        if role == "assistant" and opaque:
            if (opaque.get("model") != model or opaque.get("api_base") != api_base
                    or opaque.get("message_sha256") != _signature(message)):
                raise ValueError("Responses continuation does not match the selected model/message")
            result.extend(deepcopy(opaque["items"]))
            continue
        if role == "tool":
            result.append({"type": "function_call_output", "call_id": message["tool_call_id"],
                           "output": message.get("content") or ""})
            continue
        if role not in {"user", "assistant", "system", "developer"}:
            raise ValueError("Unsupported Responses message role")
        content = message.get("content") or ""
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    part = {"type": "text", "text": part}
                kind = part.get("type")
                if kind in {"text", "input_text", "output_text"}:
                    parts.append({"type": "output_text" if role == "assistant" else "input_text", "text": part["text"]})
                elif kind == "image_url" and role == "user":
                    image = part["image_url"]
                    parts.append({"type": "input_image", "image_url": image["url"], "detail": image.get("detail", "auto")})
                elif kind == "input_image" and role == "user":
                    parts.append(deepcopy(part))
                else:
                    raise ValueError("Unsupported Responses content part")
            content = parts
        if content:
            result.append({"role": role, "content": deepcopy(content)})
        for call in message.get("tool_calls") or []:
            function = call.get("function") or call
            item = {"type": "function_call", "call_id": call["id"],
                    "name": function["name"], "arguments": function["arguments"]}
            if call.get("response_item_id"):
                item["id"] = call["response_item_id"]
            result.append(item)
    return result


def _tools(tools):
    result = []
    for raw in tools or []:
        if isinstance(raw, dict):
            function = deepcopy(raw.get("function") or raw)
            function.pop("type", None)
        else:
            schema = raw.parameters
            if hasattr(schema, "model_json_schema"):
                schema = schema.model_json_schema()
            function = {"name": raw.name, "description": raw.description, "parameters": deepcopy(schema)}
        if not function.get("name"):
            raise ValueError("Responses function requires a name")
        # Chat function schemas are non-strict by default; preserve optional args.
        result.append({"type": "function", **function, "strict": function.get("strict", False)})
    return result


class OpenAIResponsesClient(OpenAIModelClient):
    __client_name__ = _PROVIDER

    def _request_params(self, messages, tools, *, stream, **kwargs):
        model = kwargs.get("model") or self.model_config.model_name
        options = self.model_config.model_dump(exclude_none=True)
        options.pop("model_name", None)
        options.pop("model", None)
        options.update({k: v for k, v in kwargs.items() if v is not None})
        options.pop("model", None)
        extra_body = deepcopy(options.pop("extra_body", {}) or {})
        options.update(extra_body)
        if any(key in options for key in ("messages", "input", "tools", "extra_body")):
            raise ValueError("Request options cannot replace Agent messages or tools")
        reasoning = deepcopy(options.pop("reasoning", {}) or {})
        effort = options.pop("reasoning_effort", None)
        if effort is not None:
            reasoning["effort"] = effort
        if reasoning.get("effort") != "none":
            options.pop("temperature", None)
            options.pop("top_p", None)
        limits = [value for key in ("max_tokens", "max_completion_tokens", "max_output_tokens")
                  if (value := options.pop(key, None)) is not None]
        if limits and any(value != limits[0] for value in limits):
            raise ValueError("Conflicting output token limits")
        if limits:
            options["max_output_tokens"] = limits[0]
        if options.pop("stop", None) is not None:
            raise ValueError("Responses does not support stop sequences")
        response_format = options.pop("response_format", None)
        if response_format:
            text = deepcopy(options.get("text") or {})
            text["format"] = ({"type": "json_schema", **response_format["json_schema"]}
                              if response_format.get("type") == "json_schema" else deepcopy(response_format))
            options["text"] = text
        if options.get("store") is True or options.get("previous_response_id") or options.get("conversation"):
            raise ValueError("Agent Responses context is carried explicitly with store=false")
        options["store"] = False
        include = list(options.get("include") or [])
        if "reasoning.encrypted_content" not in include:
            include.append("reasoning.encrypted_content")
        options["include"] = include
        if reasoning:
            options["reasoning"] = reasoning
        for key in ("parser", "output_parser", "tracer_record_data", "session_id"):
            options.pop(key, None)
        custom = options.pop("custom_headers", None)
        headers = self._build_request_headers(self._base_headers, custom)
        if headers:
            options["extra_headers"] = headers
        if tools:
            options["tools"] = _tools(tools)
            choice = options.get("tool_choice", "auto")
            if isinstance(choice, dict) and "function" in choice:
                choice = {"type": "function", "name": choice["function"]["name"]}
            options["tool_choice"] = choice
        # Retain the SDK escape hatch for new server fields not yet in its signature.
        extra = {key: options.pop(key) for key in extra_body
                 if key in options and key not in _RESPONSE_ARGUMENTS}
        if extra:
            options["extra_body"] = extra
        return {**options, "model": model, "stream": stream,
                "input": responses_input(messages, model=model, api_base=self.model_client_config.api_base)}

    def _parsed(self, payload, *, model):
        if payload.get("status") not in {"completed", "incomplete"}:
            raise RuntimeError("Responses did not complete: " + str(payload.get("status")))
        calls = [item for item in payload.get("output", []) if item.get("type") == "function_call"]
        if calls and (payload.get("status") != "completed"
                      or any(item.get("status") != "completed" for item in calls)):
            raise RuntimeError("Responses tool calls require a completed response and completed items")
        call_ids = [item.get("call_id") for item in calls]
        if any(not call_id for call_id in call_ids) or len(call_ids) != len(set(call_ids)):
            raise RuntimeError("Responses tool call identities must be present and unique")
        response = parse_response(payload, model_name=model)
        if response.usage_metadata:
            response.usage_metadata.reasoning_tokens = (
                (payload.get("usage") or {}).get("output_tokens_details") or {}
            ).get("reasoning_tokens", 0)
        visible_parts = [part["text"] if part["type"] == "output_text" else part["refusal"]
                         for item in payload.get("output", []) if item.get("type") == "message"
                         for part in item.get("content", []) if part.get("type") in {"output_text", "refusal"}]
        if visible_parts:
            response.content = "".join(visible_parts)
        response.metadata[_METADATA] = {"model": model, "api_base": self.model_client_config.api_base,
            "message_sha256": _signature(response.model_dump()), "items": deepcopy(payload.get("output", []))}
        return response

    async def invoke(self, messages, *, tools=None, output_parser=None, **kwargs):
        tracer = kwargs.pop("tracer_record_data", None)
        params = self._request_params(messages, tools, stream=False, **kwargs)
        client = None
        await trigger(LLMCallEvents.LLM_INPUT, model_name=params["model"], model_provider=self.model_client_config.client_provider, messages=messages, tools=tools, is_stream=False)
        try:
            if tracer:
                await tracer(llm_params=params)
            client = self._create_async_openai_client(timeout=kwargs.get("timeout"))
            raw = await client.responses.create(**params)
            response = self._parsed(raw.model_dump(exclude_none=True), model=params["model"])
            if output_parser and response.content:
                response.parser_content = await self._parse_content(response.content, output_parser)
            if tracer:
                await tracer(llm_response=response)
            await trigger(LLMCallEvents.LLM_OUTPUT, model_name=params["model"], model_provider=self.model_client_config.client_provider, response=response.content, reasoning_content=response.reasoning_content, usage=response.usage_metadata, tool_calls=response.tool_calls)
            return response
        except Exception as error:
            await trigger(LLMCallEvents.LLM_CALL_ERROR, model_name=params["model"], model_provider=self.model_client_config.client_provider, error=error, is_stream=False)
            raise
        finally:
            if client is not None and not self._use_shared_client():
                await client.close()

    async def stream(self, messages, *, tools=None, output_parser=None, **kwargs):
        tracer = kwargs.pop("tracer_record_data", None)
        params = self._request_params(messages, tools, stream=True, **kwargs)
        client = None
        terminal = None
        streamed_text = []
        await trigger(LLMCallEvents.LLM_INPUT, model_name=params["model"], model_provider=self.model_client_config.client_provider, messages=messages, tools=tools, is_stream=True)
        try:
            if tracer:
                await tracer(llm_params=params)
            client = self._create_async_openai_client(timeout=kwargs.get("timeout"))
            source = await client.responses.create(**params)
            async with source:
                async for event in source:
                    payload = event.model_dump(exclude_none=True)
                    if terminal is not None:
                        raise RuntimeError("Responses emitted an event after its terminal response")
                    if payload.get("type") in {"response.completed", "response.incomplete"}:
                        terminal = self._parsed(payload["response"], model=params["model"])
                        continue
                    # Only the authoritative terminal response may supply tools.
                    # Item-done events can be duplicated, reordered or omitted.
                    if payload.get("type") == "response.output_item.done":
                        continue
                    chunk = parse_stream_event(payload, model_name=params["model"])
                    if chunk is None:
                        continue
                    streamed_text.append(chunk.content or "")
                    await trigger(LLMCallEvents.LLM_RESPONSE_RECEIVED, model_name=params["model"], model_provider=self.model_client_config.client_provider)
                    yield chunk
            if terminal is None:
                raise RuntimeError("Responses stream ended without a terminal event")
            if "".join(streamed_text) != terminal.content:
                raise RuntimeError("Responses text deltas do not match the terminal response")
            chunk = AssistantMessageChunk(content="", tool_calls=terminal.tool_calls,
                finish_reason=terminal.finish_reason, metadata=deepcopy(terminal.metadata),
                usage_metadata=terminal.usage_metadata)
            if output_parser and terminal.content:
                chunk.parser_content = await self._parse_content(terminal.content, output_parser)
            yield chunk
            if tracer:
                await tracer(llm_response=terminal)
            await trigger(LLMCallEvents.LLM_OUTPUT, model_name=params["model"], model_provider=self.model_client_config.client_provider, response=terminal.content, reasoning_content=terminal.reasoning_content, usage=terminal.usage_metadata, tool_calls=terminal.tool_calls, is_stream=True)
        except Exception as error:
            await trigger(LLMCallEvents.LLM_CALL_ERROR, model_name=params["model"], model_provider=self.model_client_config.client_provider, error=error, is_stream=True)
            raise
        finally:
            if client is not None and not self._use_shared_client():
                await client.close()


def openai_responses_client_config(client_config: ModelClientConfig, *, model_name: str) -> ModelClientConfig:
    provider = getattr(client_config.client_provider, "value", client_config.client_provider)
    if provider == "OpenAI" and model_name in _VERIFIED_MODELS and _official_endpoint(client_config.api_base):
        if version("openjiuwen") != SDK_VERSION:
            raise RuntimeError("GPT-5.6 Responses requires the context-preserving SDK; "
                               "build/install it using scripts/sdk_patches/README.md")
        return client_config.model_copy(update={"client_provider": _PROVIDER})
    return client_config
