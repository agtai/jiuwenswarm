# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Host policies for actual SDK work; wire source fields never grant authority.

The common execution service owns the lifetime and lookup. This module has no
global registry, task scheduler, persistence or request-metadata escape hatch.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import inspect
from typing import Any, Callable
from uuid import uuid4

from jiuwenswarm.common.schema.agent import AgentRequest


class ExecutionContextUnavailable(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentExecutionPolicy:
    """Internal argument created by an authenticated product capability owner."""

    origin: str = "text"
    tool_policy: str = "configured"
    model_identity: str | None = None
    model_config_version: str | None = None
    before_effect: Callable | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self.origin not in {"text", "native"} or self.tool_policy not in {"configured", "read_only", "none"}:
            raise ExecutionContextUnavailable("AGENT_WORK_POLICY_INVALID")
        if self.origin == "native" and (
            not callable(self.before_effect)
            or self.tool_policy == "configured"
            or any(not isinstance(value, str) or not value or value.strip() != value
                   for value in (self.model_identity, self.model_config_version))
        ):
            raise ExecutionContextUnavailable("NATIVE_AGENT_WORK_POLICY_INVALID")

    @property
    def records_generated_history(self):
        return self.origin == "text"


class PreparedAgentWork:
    """A service-retained request binding, used by actual scheduled callbacks.

    Only the descriptor is sent to AgentCore. Model objects, runtime callbacks
    and permission authority remain with the existing host owner.
    """

    def __init__(self, *, request: AgentRequest, policy: AgentExecutionPolicy,
                 sdk_agent: Any, sdk_session_id: str, require_live: Callable,
                 apply_runtime: Callable, permission_context: Any = None):
        if not isinstance(request, AgentRequest) or not isinstance(policy, AgentExecutionPolicy):
            raise ExecutionContextUnavailable("AGENT_WORK_BINDING_INVALID")
        for value in (request.request_id, request.channel_id, request.session_id, sdk_session_id):
            if not isinstance(value, str) or not value or value.strip() != value or "\x00" in value:
                raise ExecutionContextUnavailable("AGENT_WORK_SCOPE_INVALID")
        self.binding_id = uuid4().hex
        self._request = deepcopy(request)
        self.policy = policy
        self.sdk_agent = sdk_agent
        self.sdk_session_id = sdk_session_id
        self._require_live = require_live
        self._apply_runtime = apply_runtime
        self._permission_context = deepcopy(permission_context)
        params = request.params if isinstance(request.params, dict) else {}
        self._descriptor = {
            "binding_id": self.binding_id,
            "session_id": request.session_id,
            "sdk_session_id": sdk_session_id,
            "channel_id": request.channel_id,
            "request_id": request.request_id,
            "mode": params.get("mode"),
            "project_dir": params.get("project_dir"),
            "origin": policy.origin,
            "tool_policy": policy.tool_policy,
            "model_identity": policy.model_identity,
            "model_config_version": policy.model_config_version,
        }

    @property
    def request(self):
        return deepcopy(self._request)

    def run_context(self):
        return {"extra": {
            "jiuwenswarm_execution": deepcopy(self._descriptor),
            "source_metadata": {
                "source_binding_id": self.binding_id,
                "source_origin_request_id": self._request.request_id,
            },
        }}

    def require_context(self, *, sdk_agent, session_id, run_context):
        extra = getattr(run_context, "extra", None)
        if isinstance(run_context, dict):
            extra = run_context.get("extra")
        if (sdk_agent is not self.sdk_agent or session_id != self.sdk_session_id
                or not isinstance(extra, dict)
                or extra.get("jiuwenswarm_execution") != self._descriptor
                or extra.get("source_metadata") != self.run_context()["extra"]["source_metadata"]):
            raise ExecutionContextUnavailable("AGENT_WORK_CONTEXT_MISMATCH")
        self._require_live()

    async def before_effect(self, ctx, *, model_call=False):
        """Called on the actual SDK task, after any model/tool pause waits."""
        self._require_live()
        if self.policy.before_effect is not None:
            result = self.policy.before_effect()
            if inspect.isawaitable(result):
                await result
        self._require_live()
        # The SDK supervisor can outlive the request that first created it.
        # Always replace (including None) on the actual executing task.
        from jiuwenswarm.agents.harness.common.rails.permissions.owner_scopes import TOOL_PERMISSION_CONTEXT
        from jiuwenswarm.agents.harness.common.rails.permissions.tool_permission_context import TOOL_PERMISSION_CHANNEL_ID
        TOOL_PERMISSION_CONTEXT.set(deepcopy(self._permission_context))
        TOOL_PERMISSION_CHANNEL_ID.set(self._request.channel_id)
        if model_call:
            result = self._apply_runtime(ctx)
            if inspect.isawaitable(result):
                await result
            self._require_live()

    def accepts_source(self, payload):
        """Validate a projected SDK identity against this actual retained work."""
        if not isinstance(payload, dict):
            return False
        try:
            self._require_live()
        except ExecutionContextUnavailable:
            return False
        if (payload.get("source_binding_id") != self.binding_id
                or payload.get("source_origin_request_id") != self._request.request_id
                or payload.get("source_session_id") != self.sdk_session_id
                or not isinstance(payload.get("source_task_id"), str)
                or not payload["source_task_id"]):
            return False
        kind = payload.get("source_run_kind")
        if kind == "user":
            return (payload.get("source_request_id") == self._request.request_id
                    and payload.get("source_goal_id") is None
                    and payload.get("source_goal_revision") is None)
        return (kind == "goal" and "source_request_id" in payload
                and payload["source_request_id"] is None
                and isinstance(payload.get("source_goal_id"), str)
                and bool(payload["source_goal_id"])
                and type(payload.get("source_goal_revision")) is int
                and payload["source_goal_revision"] > 0)


def context_binding_id(run_context):
    extra = getattr(run_context, "extra", None)
    if isinstance(run_context, dict):
        extra = run_context.get("extra")
    if not isinstance(extra, dict) or "jiuwenswarm_execution" not in extra:
        return None
    descriptor = extra["jiuwenswarm_execution"]
    if not isinstance(descriptor, dict) or not isinstance(descriptor.get("binding_id"), str):
        raise ExecutionContextUnavailable("AGENT_WORK_CONTEXT_INVALID")
    return descriptor["binding_id"]
