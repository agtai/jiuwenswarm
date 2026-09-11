# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Exact replies to observed Agent interrupts, owned by the existing service.

The reply request owns only a short admission receipt. The interrupted work keeps
its SDK reader, configured model, permission context and history attribution.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
import inspect
import json

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.server.runtime.agent_adapter.stream_source import (
    agent_interrupt_display_id, extract_stream_source, extract_agent_interrupt,
)
from jiuwenswarm.server.runtime.session.session_manager import SessionManager
from jiuwenswarm.server.runtime.session_execution import SessionExecutionUnavailable


_CONTROL = "agent.interrupt.reply"
_ANSWER_BYTES = 64 * 1024


@dataclass
class _Pending:
    token: str
    source: dict
    questions: dict = field(default_factory=dict)


@dataclass
class _Reply:
    receipt: dict | None = None
    preclaim_retryable: bool = False
    outcome_unknown: bool = False


def _guard(callback):
    if not callable(callback):
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_GUARD_REQUIRED")
    result = callback()
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_GUARD_MUST_BE_SYNCHRONOUS")
    if result is not None:
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_GUARD_RESULT_INVALID")


def _identity(value):
    if type(value) is not str or not value or value.strip() != value or len(value) > 1024 or "\x00" in value:
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_IDENTITY_INVALID")
    return value


def _answers_snapshot(answers):
    if not isinstance(answers, list) or not answers or len(answers) > 128:
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_ANSWERS_INVALID")
    for answer in answers:
        if (not isinstance(answer, dict) or not answer
                or set(answer) - {"question", "selected_options", "custom_input"}
                or any(key in answer and type(answer[key]) is not str for key in ("question", "custom_input"))
                or ("selected_options" in answer and (not isinstance(answer["selected_options"], list)
                    or any(type(value) is not str for value in answer["selected_options"])))):
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_ANSWERS_INVALID")
    try:
        encoded = json.dumps(answers, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > _ANSWER_BYTES:
            raise ValueError
        return json.loads(encoded)
    except (ValueError, TypeError, UnicodeError):
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_ANSWERS_INVALID") from None


def observe_agent_interrupt(service, reader, sdk_agent, chunk, question):
    """Called only by the real SDK output reader before presentation rewrites."""
    interrupt = extract_agent_interrupt(chunk)
    if interrupt is None or not isinstance(question, dict):
        return
    source = extract_stream_source(chunk)
    if "source_binding_id" not in source:
        return  # Legacy/Team output does not acquire managed reply authority.
    work = service.resolve_output_work(reader, source)
    if work is None or work.sdk_agent is not sdk_agent:
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_OWNER_MISMATCH")
    if (question.get("event_type") != "chat.ask_user_question"
            or question.get("input_id", question.get("request_id")) != interrupt["input_id"]
            or question.get("source") not in {"ask_user_interrupt", "permission_interrupt", "confirm_interrupt"}):
        return
    entry = next(item for item in service._records.values() if item.prepared_work is work)
    pending = entry.agent_interrupt
    if pending is None or pending.token != interrupt["pending_token"] or pending.source != source:
        pending = _Pending(interrupt["pending_token"], deepcopy(source))
    canonical = {**deepcopy(question), "request_id": interrupt["input_id"]}
    questions = {**pending.questions, interrupt["input_id"]: canonical}
    if len(questions) > service.max_events or not service._projection_fits(questions):
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_PROJECTION_TOO_LARGE")
    pending.questions = questions
    entry.agent_interrupt = pending


def _peek_work_pending(work):
    peek = getattr(work.sdk_agent, "peek_pending_input", None)
    if not callable(peek):
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_STATE_UNAVAILABLE")
    snapshot = peek()
    if snapshot is None:
        return None
    if (not isinstance(snapshot, dict) or type(snapshot.get("pending_token")) is not str
            or not isinstance(snapshot.get("pending_ids"), list)
            or any(type(value) is not str for value in snapshot["pending_ids"])
            or not isinstance(snapshot.get("execution_origin"), dict)):
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_STATE_INVALID")
    return snapshot


def _pending_matches_sdk(service, entry, pending):
    work = entry.prepared_work
    snapshot = _peek_work_pending(work)
    if snapshot is None or snapshot["pending_token"] != pending.token:
        entry.agent_interrupt = None
        return False
    origin = snapshot["execution_origin"]
    work.require_context(sdk_agent=work.sdk_agent, session_id=origin.get("session_id"),
                         run_context=origin.get("run_context"))
    source = pending.source
    if (origin.get("kind") != source.get("source_run_kind")
            or origin.get("request_id") != source.get("source_request_id")
            or not set(pending.questions).issubset(snapshot["pending_ids"])):
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_SOURCE_MISMATCH")
    if source["source_run_kind"] == "goal":
        manager = getattr(work.sdk_agent, "goal_manager", None)
        peek = getattr(manager, "peek", None)
        if not callable(peek):
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_GOAL_UNAVAILABLE")
        goal = peek()
        if (goal is None or goal.goal_id != source["source_goal_id"]
                or goal.revision != source["source_goal_revision"]
                or getattr(goal.status, "value", goal.status) != "active"):
            entry.agent_interrupt = None
            return False
    return True


def has_managed_agent_pending(service, agent, session_id):
    """Reject legacy answers even before a saved interrupt reaches its reader."""
    for entry in service._records.values():
        work = entry.prepared_work
        if (entry.agent is not agent or work is None or not service._work_is_live(entry)
                or SessionManager.get_session_id(entry.request.session_id) != session_id):
            continue
        # Installed legacy SDKs have no exact pending contract. An already
        # observed managed token nevertheless must never downgrade to ID-only.
        if not callable(getattr(work.sdk_agent, "peek_pending_input", None)):
            if entry.agent_interrupt is not None:
                return True
            continue
        snapshot = work.sdk_agent.peek_pending_input()
        if snapshot is None:
            continue
        origin = snapshot.get("execution_origin") if isinstance(snapshot, dict) else None
        if not isinstance(origin, dict):
            continue
        from jiuwenswarm.server.runtime.execution_context import context_binding_id
        if context_binding_id(origin.get("run_context")) == work.binding_id:
            return True
    return False


def _find(service, agent, *, session_id, source_binding_id, source_task_id, expected_pending_token, input_id):
    service._require_loop()
    for entry in service._records.values():
        work = entry.prepared_work
        if (entry.agent is not agent or SessionManager.get_session_id(entry.request.session_id) != session_id
                or work is None or work.binding_id != source_binding_id):
            continue
        service._require_work_live(entry)
        pending = entry.agent_interrupt
        if (pending is None or pending.token != expected_pending_token
                or pending.source.get("source_task_id") != source_task_id
                or input_id not in pending.questions or not work.accepts_source(pending.source)):
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_PENDING_MISMATCH")
        if not _pending_matches_sdk(service, entry, pending):
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_PENDING_MISMATCH")
        return entry, pending, work
    raise SessionExecutionUnavailable("AGENT_INTERRUPT_NOT_OBSERVED")


def list_agent_interrupts(service, agent, *, session_id, before_read=None):
    """Return only live questions observed by this exact service/Agent/session."""
    if before_read is not None:
        _guard(before_read)
    service._require_loop()
    _identity(session_id)
    result = {"pending": [], "total_observed": 0, "inventory_truncated": False,
              "inventory_scope": "current_process", "source": "configured_agent_stream"}
    for entry in service._records.values():
        pending = entry.agent_interrupt
        if (entry.agent is not agent or SessionManager.get_session_id(entry.request.session_id) != session_id
                or pending is None or not service._work_is_live(entry)):
            continue
        if not _pending_matches_sdk(service, entry, pending):
            continue
        for input_id, question in pending.questions.items():
            result["total_observed"] += 1
            projected_question = {**deepcopy(question), "request_id": agent_interrupt_display_id(
                pending.source, pending.token, input_id)}
            item = {**deepcopy(pending.source), "pending_token": pending.token,
                    "input_id": input_id, "question": projected_question}
            candidate = {**result, "pending": [*result["pending"], item]}
            if service._projection_fits(candidate):
                result = candidate
            else:
                result["inventory_truncated"] = True
    while not service._projection_fits(result):
        if not result["pending"]:
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_PROJECTION_TOO_LARGE")
        result["pending"].pop()
        result["inventory_truncated"] = True
    if before_read is not None:
        _guard(before_read)
    return result


async def reply_agent_interrupt(service, agent, request, *, source_binding_id, source_task_id,
                                expected_pending_token, input_id, answers, before_effect):
    """Wait for an exact SDK claim; replay never sends the answer twice."""
    _guard(before_effect)
    if not isinstance(request, AgentRequest):
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_REQUEST_INVALID")
    session_id = SessionManager.get_session_id(request.session_id)
    for value in (session_id, request.channel_id, request.request_id, source_binding_id,
                  source_task_id, expected_pending_token, input_id):
        _identity(value)
    snapshot = _answers_snapshot(answers)
    selector = dict(source_binding_id=source_binding_id, source_task_id=source_task_id,
                    expected_pending_token=expected_pending_token, input_id=input_id)
    # Only normalized reply data participates in the short control fingerprint.
    # Caller model/history/permission metadata cannot configure a continuation.
    internal = AgentRequest(request_id=request.request_id, channel_id=request.channel_id,
        session_id=session_id, req_method=request.req_method, is_stream=True,
        params={"action": _CONTROL, **selector, "answers": snapshot})
    control = _Reply()
    submitted = False

    async def claim():
        nonlocal submitted
        original, pending, work = _find(service, agent, session_id=session_id, **selector)
        _guard(before_effect)
        current, live_pending, live_work = _find(service, agent, session_id=session_id, **selector)
        if current is not original or live_pending is not pending or live_work is not work:
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_PENDING_MISMATCH")

        def claim_guard():
            _guard(before_effect)
            selected, selected_pending, selected_work = _find(service, agent, session_id=session_id, **selector)
            if selected is not original or selected_pending is not pending or selected_work is not work:
                raise SessionExecutionUnavailable("AGENT_INTERRUPT_PENDING_MISMATCH")

        build = getattr(agent, "build_agent_interrupt_input", None)
        if not callable(build):
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_ADAPTER_UNAVAILABLE")
        interactive = build(deepcopy(pending.questions[input_id]), snapshot,
            expected_pending_token=expected_pending_token, before_effect=claim_guard,
            prepare_effect=lambda: work.before_effect(None, model_call=False))
        from openjiuwen.harness.schema.interaction import SendInputRequest

        # SDK restores the persisted original RunContext/request/kind. A reply
        # must not supply a fresh work context or attach a second output reader.
        submitted = True
        receipt = await work.sdk_agent.send_input(SendInputRequest(
            request_id=request.request_id, inputs={"query": interactive}))
        return original, pending, receipt

    async def deliver(control_entry):
        try:
            original, pending, receipt = await claim()
        except asyncio.CancelledError:
            # Cancelling this observer need not stop queued SDK admission.
            control.outcome_unknown = submitted
            raise
        except Exception:
            # The strict SDK call settles preclaim errors only after its owner
            # rejects them. A still-identical live pending proves no consumption;
            # cancellation and unobserved/invalid receipts are never retryable.
            try:
                _find(service, agent, session_id=session_id, **selector)
            except Exception:
                control.outcome_unknown = submitted
            else:
                control.preclaim_retryable = True
            raise
        if receipt != {"accepted": True, "pending_token": expected_pending_token}:
            control.outcome_unknown = True
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_CLAIM_UNOBSERVED")
        if original.agent_interrupt is pending:
            original.agent_interrupt = None
        control.receipt = {**receipt, "source_binding_id": source_binding_id,
                           "source_task_id": source_task_id, "input_id": input_id}
        yield AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
            payload={"event_type": "agent.input_accepted", **deepcopy(control.receipt)}, is_complete=False)

    entry = service.start_internal(agent, internal, kind=_CONTROL, producer=deliver,
                                   capability_state=control, control_only=True)
    previous = entry.capability_state
    if (previous is not control and previous.preclaim_retryable and previous.receipt is None
            and entry.stream_closed and entry.task.done()):
        # No await between the actual SDK check and the record/task CAS.
        _find(service, agent, session_id=session_id, **selector)
        entry = service.restart_internal_control(entry, internal, expected_state=previous,
                                                  producer=deliver, capability_state=control)
    if entry.capability_state.receipt is not None:
        return deepcopy(entry.capability_state.receipt)
    try:
        await asyncio.shield(entry.task)
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling() or not entry.capability_state.outcome_unknown:
            raise
    except Exception:
        if entry.capability_state.receipt is not None:
            return {**deepcopy(entry.capability_state.receipt), "observation_unavailable": True}
        if not entry.capability_state.outcome_unknown:
            raise
    if entry.capability_state.outcome_unknown:
        return {"status": "unknown", "reason": "AGENT_INTERRUPT_CLAIM_UNOBSERVED", "observation_required": True,
                "pending_token": expected_pending_token, "source_binding_id": source_binding_id,
                "source_task_id": source_task_id, "input_id": input_id}
    if entry.capability_state.receipt is None:
        raise SessionExecutionUnavailable("AGENT_INTERRUPT_CLAIM_UNOBSERVED")
    return deepcopy(entry.capability_state.receipt)
