# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Retained work guards at Model entry and its final client call boundary."""
from __future__ import annotations

import inspect
from typing import Any, Callable

from openjiuwen.core.foundation.llm import Model, model_call_guard_scope
from openjiuwen.core.foundation.tool import ToolInfo

from jiuwenswarm.agents.harness.common.rails.stream_event_rail import NATIVE_READ_ONLY_TOOL_NAMES


def _tool_name(tool: ToolInfo | dict) -> str | None:
    if isinstance(tool, ToolInfo):
        kind, name = tool.type, tool.name
    elif isinstance(tool, dict):
        kind = tool.get("type")
        if kind == "function":
            # Responses accepts a flat function while Chat uses a nested one.
            # Keep the provider's original shape and reject conflicting aliases.
            function = tool.get("function", tool)
            if not isinstance(function, dict):
                raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
            name = function.get("name")
            if function is not tool:
                for field in ("name", "parameters", "description", "strict"):
                    if field in tool and field in function and tool[field] != function[field]:
                        raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
                if "parameters" in tool and not isinstance(tool["parameters"], dict):
                    raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
            if "parameters" in function and not isinstance(function["parameters"], dict):
                raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
        else:
            name = None
    else:
        raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
    if not isinstance(kind, str) or not kind or kind.strip() != kind:
        raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
    if kind != "function":
        # Configured Text retains provider-native tool definitions. Native
        # admits only its existing registered function-tool names.
        return None
    if not isinstance(name, str) or not name or name.strip() != name:
        raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
    return name


class BoundAgentModel(Model):
    """Keep the original Model/client and fence invoke/stream after input hooks.

    The SDK's review configuration checks ``isinstance(Model)``. Subclass for
    compatibility without calling Model.__init__, creating a client, or
    modifying shared configuration. Existing SDK KV methods use the same
    delegated client and config; inference alone passes this work guard.
    """

    def __init__(self, model: Model, work: Any, *, before_call: Callable | None = None):
        if not isinstance(model, Model):
            raise TypeError("AGENT_WORK_MODEL_INVALID")
        self._model = model
        self._work = work
        self._before_call = before_call

    @property
    def model_config(self):
        return self._model.model_config

    @property
    def model_client_config(self):
        return self._model.model_client_config

    @property
    def _client(self):
        return self._model._client

    async def _before_inference(self, kwargs: dict, *, sdk_defaults=False) -> dict:
        if self._before_call is not None:
            result = self._before_call()
            if inspect.isawaitable(result):
                await result
        # Run both before entering Model and after its asynchronous input hooks.
        # The final check sets permission context on the actual client call task,
        # without applying model runtime again.
        await self._work.before_effect(None, model_call=False)
        name = getattr(self.model_config, "model_name", None)
        if (not isinstance(name, str) or not name or name.strip() != name
                or ("model" in kwargs and kwargs["model"] != name
                    and not (sdk_defaults and kwargs["model"] is None))):
            raise ValueError("AGENT_WORK_MODEL_MISMATCH")

        tools = kwargs.get("tools")
        if tools is not None:
            if not isinstance(tools, list):
                raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
            # The SDK converter accepts an all-dict or all-ToolInfo list.
            if tools and not (all(isinstance(tool, ToolInfo) for tool in tools)
                              or all(isinstance(tool, dict) for tool in tools)):
                raise ValueError("AGENT_WORK_MODEL_TOOLS_INVALID")
            names = [_tool_name(tool) for tool in tools]
        else:
            names = []
        policy = self._work.policy.tool_policy
        if policy == "none":
            kwargs["tools"] = []
        elif policy == "read_only" and tools is not None:
            kwargs["tools"] = [tool for tool, tool_name in zip(tools, names)
                               if tool_name in NATIVE_READ_ONLY_TOOL_NAMES]
        elif policy not in {"read_only", "configured"}:
            raise ValueError("AGENT_WORK_POLICY_INVALID")
        return kwargs

    async def _before_client(self, kwargs: dict) -> dict:
        # Model inserts model=None when the caller omitted it. Explicit caller
        # overrides have already passed the stricter entry validation above.
        return await self._before_inference(kwargs, sdk_defaults=True)

    async def invoke(self, *args, **kwargs):
        final_kwargs = await self._before_inference(kwargs)
        with model_call_guard_scope(self._model, self._before_client):
            return await self._model.invoke(*args, **final_kwargs)

    async def stream(self, *args, **kwargs):
        final_kwargs = await self._before_inference(kwargs)
        output = self._model.stream(*args, **final_kwargs)
        try:
            while True:
                # Scope every operation on the original iterator, but never
                # hold a ContextVar token across a yield to a different reader.
                with model_call_guard_scope(self._model, self._before_client):
                    try:
                        chunk = await anext(output)
                    except StopAsyncIteration:
                        return
                yield chunk
        finally:
            with model_call_guard_scope(self._model, self._before_client):
                await output.aclose()
