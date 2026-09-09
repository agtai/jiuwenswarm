"""Web input adapters use Gateway identity and the original managed Agent work."""
from __future__ import annotations

from jiuwenswarm.common.schema.agent import AgentResponse
from jiuwenswarm.server.runtime.agent_resolution import resolve_owned_web_session
from jiuwenswarm.server.runtime.session.session_history import is_valid_session_id


async def dispatch_agent_input_request(manager, request, *, before_effect):
    from jiuwenswarm.server.runtime.agent_interrupt_execution import list_agent_interrupts, reply_agent_interrupt

    try:
        params = request.params
        action = params.get("action") if type(params) is dict else None
        fields = {"action", "session_id"}
        if action == "reply":
            fields |= {"source_binding_id", "source_task_id", "pending_token", "input_id", "answers"}
        if (action not in {"list", "reply"} or request.channel_id != "web"
                or type(request.session_id) is not str or not is_valid_session_id(request.session_id)
                or set(params) != fields or params["session_id"] != request.session_id):
            raise ValueError("AGENT_INPUT_REQUEST_INVALID")
        owner, guard = await resolve_owned_web_session(manager, request,
            before_effect=before_effect, reason_prefix="AGENT_INPUT")
        if action == "list":
            payload = list_agent_interrupts(manager.executions, owner.agent,
                session_id=request.session_id, before_read=guard)
        else:
            payload = await reply_agent_interrupt(manager.executions, owner.agent, request,
                source_binding_id=params["source_binding_id"], source_task_id=params["source_task_id"],
                expected_pending_token=params["pending_token"], input_id=params["input_id"],
                answers=params["answers"], before_effect=guard)
        ok = True
    except Exception as error:
        message = getattr(error, "reason", str(error))
        reason = message if type(message) is str and message.startswith(("AGENT_INPUT_", "AGENT_INTERRUPT_")) and message.replace("_", "").isalnum() else "AGENT_INPUT_UNAVAILABLE"
        ok, payload = False, {"accepted": False, "reason": reason}
    return AgentResponse(request_id=request.request_id, channel_id=request.channel_id,
        ok=ok, payload=payload, metadata=request.metadata, agent_ref=request.agent_ref)
