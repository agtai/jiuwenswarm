# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Additional Host admission on original configured Team member rails/models."""
from __future__ import annotations

import json

from openjiuwen.core.foundation.llm import AssistantMessage, Model, ToolCall, model_call_guard_scope
from openjiuwen.core.single_agent.rail.base import AgentRail
from openjiuwen.core.runner.callback.errors import AbortError


TEAM_EXECUTION_RAIL = 'swarm.team_execution'
TEAM_EXECUTION_CONTEXT = '_jiuwenswarm_team_execution'


class ConfiguredTeamModel(Model):
    """Delegate to the member's original Model/client without changing its policy."""

    def __init__(self, model, check):
        if not isinstance(model, Model):
            raise TypeError('configured_team_model_unavailable')
        self._original = model
        self._check = check
        self._configuration = self._snapshot()
        self._client_identity = model._client

    @property
    def model_config(self):
        return self._original.model_config

    @property
    def model_client_config(self):
        return self._original.model_client_config

    @property
    def _client(self):
        return self._original._client

    def _snapshot(self):
        return (self._original.model_config.model_dump_json(),
                self._original.model_client_config.model_dump_json())

    def _before(self, kwargs):
        self._check()
        if self._snapshot() != self._configuration or self._original._client is not self._client_identity:
            raise ValueError('configured_team_model_changed')
        expected = self.model_config.model_name
        if kwargs.get('model') not in (None, expected):
            raise ValueError('configured_team_model_override')
        return kwargs

    async def invoke(self, *args, **kwargs):
        self._before(kwargs)
        with model_call_guard_scope(self._original, self._before):
            return await self._original.invoke(*args, **kwargs)

    async def stream(self, *args, **kwargs):
        self._before(kwargs)
        source = self._original.stream(*args, **kwargs)
        try:
            while True:
                try:
                    with model_call_guard_scope(self._original, self._before):
                        chunk = await anext(source)
                except StopAsyncIteration:
                    return
                yield chunk
        finally:
            with model_call_guard_scope(self._original, self._before):
                await source.aclose()


class TeamExecutionRail(AgentRail):
    """Preserve configured permissions; require the trusted Host condition too.

    Lower priority runs after the configured TeamPermissionRail. An explicit
    SwarmFlow intent uses the original ReAct tool loop, never a second executor.
    """

    priority = -10000

    def __init__(self, execution, *, role, member_name=None, control_only=False):
        from jiuwenswarm.server.runtime.team_execution import _TeamRun

        if type(execution) is not _TeamRun:
            raise ValueError('configured_team_authority_unavailable')
        self.control_only = control_only
        self.execution = execution
        self.role = getattr(role, 'value', role)
        self.member_name = member_name
        self._agent = None
        self._model = None

    def _check(self, agent):
        if self._agent is None:
            self._agent = agent
        if self._agent is not agent:
            raise ValueError('configured_team_member_owner_changed')
        self.execution.check()

    async def before_model_call(self, ctx):
        try:
            await self._before_model_call(ctx)
        except Exception as exc:
            intent = self.execution.intent
            if self.control_only and intent is not None:
                intent.failure = str(exc)
                intent.before_effect = None
                intent.observed.set()
                self.execution.receipt_changed.set()
                return
            # Ordinary callback exceptions are recorded and ignored by the SDK.
            # Its existing AbortError contract propagates this authority failure.
            raise AbortError('CONFIGURED_TEAM_AUTHORITY_REJECTED', cause=exc) from exc

    async def _before_model_call(self, ctx):
        intent = self.execution.intent
        if self.control_only and (intent is None or intent.claimed or intent.observed.is_set()):
            return
        if self.control_only:
            try:
                self._check(ctx.agent)
                self.execution.check_intent(intent)
            except Exception as exc:
                intent.failure = str(exc)
                intent.before_effect = None
                intent.observed.set()
                self.execution.receipt_changed.set()
                return
        else:
            self._check(ctx.agent)
        if ctx.has_force_finish_request:
            return
        if not self.control_only:
            self.execution.on_model_boundary()
        if self.role == 'leader':
            intent = self.execution.intent
            if intent is not None and not intent.claimed:
                await intent.admitted.wait()
                self._check(ctx.agent)
                if intent.failure is not None:
                    return
                self.execution.claim_intent(intent, ctx.agent)
                message = AssistantMessage(content='', tool_calls=[ToolCall(
                    id=intent.tool_call_id, type='function', name='swarmflow',
                    arguments=json.dumps(intent.inputs, ensure_ascii=False))])
                ctx.inputs.response = message
                ctx.request_force_finish(message)
                return
        if self.control_only:
            return
        model = ctx.agent._get_llm()
        if self._model is None:
            if isinstance(model, ConfiguredTeamModel):
                raise ValueError('configured_team_model_owner_changed')
            self._model = ConfiguredTeamModel(model, lambda: self._check(ctx.agent))
            ctx.agent.set_llm(self._model)
        elif model is not self._model:
            raise ValueError('configured_team_model_owner_changed')

    async def before_tool_call(self, ctx):
        intent = self.execution.intent
        if self.control_only and (intent is None or
                getattr(ctx.inputs.tool_call, 'id', None) != intent.tool_call_id):
            return
        try:
            self._check(ctx.agent)
            self.execution.check_tool(ctx)
        except Exception as exc:
            if intent is not None and getattr(ctx.inputs.tool_call, 'id', None) == intent.tool_call_id:
                # This rail rejected before the actual tool invocation. Retain
                # that exact control fact even if the SDK skips AFTER_TOOL_CALL.
                intent.failure = str(exc)
                intent.before_effect = None
                intent.observed.set()
                self.execution.receipt_changed.set()
            raise AbortError('CONFIGURED_TEAM_AUTHORITY_REJECTED', cause=exc) from exc

    async def after_tool_call(self, ctx):
        # Capture a real launch even when a later grant check would now fail:
        # effects already admitted cannot be relabelled as rejected.
        self.execution.capture_tool_result(ctx)
