# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Web projection of the shared Core Workflow owner.

Trusted startup installs the declared capabilities and Web authorization owner.
Gateway connection identity and current stored session ownership are checked
separately from capability permissions. Wire requests cannot install authority.
"""
from __future__ import annotations

from jiuwenswarm.common.schema.agent import AgentResponse
from jiuwenswarm.server.runtime.agent_resolution import resolve_owned_web_session
from jiuwenswarm.server.runtime.core_workflow_capabilities import CoreWorkflowScope
from jiuwenswarm.server.runtime.session.session_history import is_valid_session_id


async def dispatch_core_workflow_request(manager, request, *, connection, before_read):
    from jiuwenswarm.server.runtime.core_workflow_execution import (
        list_core_workflows, get_core_workflow, start_core_workflow, resume_core_workflow,
    )

    try:
        params = request.params
        fields = {
            "list": {"kind", "action"},
            "get": {"kind", "action", "epoch", "run_id"},
            "start": {"kind", "action", "epoch", "capability_id", "inputs"},
            "resume": {"kind", "action", "epoch", "run_id", "expected_revision", "answers"},
        }
        operation = params.get("action") if type(params) is dict else None
        # WebChannel carries session_id in both its envelope and params.
        # Direct Host callers may omit the redundant field; it may never retarget.
        supplied_fields = set(params) if type(params) is dict else set()
        if "session_id" in supplied_fields:
            if params["session_id"] != request.session_id:
                raise ValueError("CORE_WORKFLOW_REQUEST_INVALID")
            supplied_fields.remove("session_id")
        if (request.channel_id != "web" or type(request.session_id) is not str
                or not is_valid_session_id(request.session_id)
                or type(operation) is not str or operation not in fields
                or supplied_fields != fields[operation] or params["kind"] != "core"):
            raise ValueError("CORE_WORKFLOW_REQUEST_INVALID")
        installed = getattr(manager, "core_workflow_host", None)
        if installed is None:
            raise PermissionError("CORE_WORKFLOW_AUTHORITY_UNAVAILABLE")
        owner, guard = await resolve_owned_web_session(manager, request,
            before_effect=before_read, reason_prefix="CORE_WORKFLOW")
        scope = CoreWorkflowScope("web", request.session_id, owner.project_id, owner.canonical_mode)
        authorize = installed.web_guard(connection=connection, request_user_id=request.user_id,
                                        scope=scope, operation=operation)

        def before_effect(capability):
            guard()
            authorize(capability)
            guard()

        # Check current connection/scope permission even when no capability is
        # registered. Per-capability guards then check its declared effects.
        before_effect(None)
        service = manager.executions
        if operation != "list" and params["epoch"] != service.execution_epoch:
            raise ValueError("CORE_WORKFLOW_EPOCH_MISMATCH")
        if operation in {"list", "start"}:
            installed.bind_scope(scope, operation=operation, before_read=lambda: before_effect(None))
        if operation == "list":
            payload = list_core_workflows(service, owner.agent, scope=scope, before_effect=before_effect)
        elif operation == "get":
            payload = get_core_workflow(service, owner.agent, scope=scope,
                run_id=params["run_id"], before_effect=before_effect)
        elif operation == "start":
            payload = await start_core_workflow(service, owner.agent, request=request, scope=scope,
                epoch=params["epoch"], capability_id=params["capability_id"], inputs=params["inputs"],
                before_effect=before_effect)
        else:
            payload = await resume_core_workflow(service, owner.agent, request=request, scope=scope,
                epoch=params["epoch"], run_id=params["run_id"], expected_revision=params["expected_revision"],
                answers=params["answers"], before_effect=before_effect)
        return AgentResponse(request_id=request.request_id, channel_id=request.channel_id,
            ok=True, payload=payload, metadata=request.metadata, agent_ref=request.agent_ref)
    except Exception as error:
        # Provider/checkpointer diagnostics may contain private paths or inputs.
        # Only this adapter's closed error codes are projected verbatim.
        message = str(error)
        reason = message if message.startswith("CORE_WORKFLOW_") and message.replace("_", "").isalnum() else "CORE_WORKFLOW_REQUEST_UNAVAILABLE"
        return AgentResponse(request_id=request.request_id, channel_id=request.channel_id,
            ok=False, payload={"status": "rejected", "reason": reason},
            metadata=request.metadata, agent_ref=request.agent_ref)
