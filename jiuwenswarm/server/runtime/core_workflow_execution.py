"""Core Workflow runs retained by the shared, bounded execution service.

No provider is registered here. A control receipt means input admission only;
the original WorkflowOutput and producer settlement supply execution facts.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from openjiuwen.core.common.constants.constant import INTERACTION
from openjiuwen.core.session import InteractionOutput
from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.stream import OutputSchema
from openjiuwen.core.workflow import WorkflowExecutionState, WorkflowOutput

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.common.schema.message import ReqMethod
from .core_workflow_capabilities import CoreWorkflowCapabilities, CoreWorkflowError, CoreWorkflowScope


_RUN = "core_workflow_run"
_CONTROL = "core_workflow_control"
_INPUT_BYTES = 64 * 1024


@dataclass
class _Run:
    scope: CoreWorkflowScope
    epoch: str
    directory: CoreWorkflowCapabilities
    capability: Any
    before_effect: Any
    inputs: Any
    run_id: str = field(default_factory=lambda: "core_" + uuid4().hex)
    sdk_session_id: str = field(default_factory=lambda: "core-private-" + uuid4().hex)
    binding: Any = None
    checkpointer: Any = None
    output: WorkflowOutput | None = None
    revision: int = 1
    pending: tuple = ()
    inbox: asyncio.Future | None = None
    receipt: dict = field(default_factory=dict)
    failure: str | None = None


@dataclass
class _Control:
    receipt: dict | None = None


def _scope(scope):
    if type(scope) is not CoreWorkflowScope:
        raise CoreWorkflowError("invalid_scope")


def _directory(service):
    directory = service.manager.core_workflow_capabilities
    if type(directory) is not CoreWorkflowCapabilities:
        raise CoreWorkflowError("directory_unavailable")
    return directory


def _guard(callback, capability):
    if not callable(callback):
        raise CoreWorkflowError("missing_authority_guard")
    value = callback(capability)
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise CoreWorkflowError("authority_guard_must_be_synchronous")
    if value is not None:
        raise CoreWorkflowError("authority_guard_must_return_none")


def _json_snapshot(value):
    def check(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise CoreWorkflowError("invalid_json")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise CoreWorkflowError("invalid_json")
    try:
        check(value)
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > _INPUT_BYTES:
            raise CoreWorkflowError("input_too_large")
        return json.loads(encoded)
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, CoreWorkflowError):
            raise
        raise CoreWorkflowError("invalid_json") from None


def _request(request, scope, epoch, operation, **params):
    _scope(scope)
    if (not isinstance(request, AgentRequest) or request.channel_id != scope.channel_id
            or request.session_id != scope.session_id or type(request.request_id) is not str
            or not request.request_id or request.request_id.strip() != request.request_id):
        raise CoreWorkflowError("request_scope_mismatch")
    return AgentRequest(request_id=request.request_id, channel_id=scope.channel_id, session_id=scope.session_id,
        req_method=ReqMethod.COMMAND_WORKFLOWS, is_stream=True,
        params={"kind": "core", "action": operation, "epoch": epoch, "scope": asdict(scope), **params})


def _epoch(service, epoch):
    if type(epoch) is not str or epoch != service.execution_epoch:
        raise CoreWorkflowError("execution_epoch_mismatch")


def _find(service, agent, scope, run_id):
    _scope(scope)
    if type(run_id) is not str or not run_id:
        raise CoreWorkflowError("unknown_run")
    for entry in service.list_internal(agent, session_id=scope.session_id, kind=_RUN):
        state = entry.capability_state
        if type(state) is _Run and state.run_id == run_id and state.scope == scope:
            return entry, state
    raise CoreWorkflowError("unknown_run")


def _live(service, entry, state):
    _epoch(service, state.epoch)
    if service.get_internal(entry.agent, session_id=state.scope.session_id,
            execution_id=entry.request.request_id, kind=_RUN) is not entry:
        raise CoreWorkflowError("run_owner_unavailable")
    if entry.cancellation_requested or entry.task.done() or entry.task.cancelling():
        raise CoreWorkflowError("run_closed")
    if _directory(service) is not state.directory:
        raise CoreWorkflowError("directory_changed")
    if state.checkpointer is not None and CheckpointerFactory.get_checkpointer() is not state.checkpointer:
        raise CoreWorkflowError("checkpointer_changed")


def _run_guard(service, entry, state, admission_guard=None):
    _live(service, entry, state)
    _guard(state.before_effect, state.capability)
    if admission_guard is not None:
        _guard(admission_guard, state.capability)
    _live(service, entry, state)


def _metadata(capability):
    return {"capability_id": capability.capability_id, "sdk_id": capability.sdk_id,
        "sdk_version": capability.sdk_version, "required_permissions": list(capability.required_permissions),
        "input_schema": capability.input_schema, "continuation_schemas": capability.continuation_schemas,
        "card_fingerprint": capability.card_fingerprint,
        "input_schema_fingerprint": capability.input_schema_fingerprint}


def _fact(service, entry, state):
    output = state.output
    settled = entry.task.done()
    success = settled and entry.stream_outcome == "ended" and state.failure is None
    projection_unavailable = False
    try:
        result = output.model_dump(mode="json")["result"] if output is not None else None
        pending = [item.model_dump(mode="json") for item in state.pending]
    except Exception:
        result, pending, projection_unavailable = None, [], True
    fact = {"run_id": state.run_id, "epoch": state.epoch, "revision": state.revision,
        "capability_id": state.capability.capability_id, "inventory_scope": "current_process",
        "sdk_state": output.state.value if output is not None else None,
        "result": result, "pending": pending,
        "continuation_available": bool(state.inbox is not None and not state.inbox.done()
            and not settled and not entry.cancellation_requested),
        "settled": settled, "stream_outcome": entry.stream_outcome,
        "failure_reason": state.failure,
        "business_completion": bool(success and output is not None
            and output.state == WorkflowExecutionState.COMPLETED)}
    if projection_unavailable or not service._projection_fits(fact):
        return {**fact, "result": None, "pending": [], "continuation_available": False,
            "projection_unavailable": True}
    return fact


def list_core_workflows(service, agent, *, scope, before_effect):
    _scope(scope)
    if not callable(before_effect):
        raise CoreWorkflowError("missing_authority_guard")
    directory = _directory(service)
    capabilities = []
    for capability in directory.list(scope):
        try:
            _guard(before_effect, capability)
        except PermissionError:
            continue
        capabilities.append(_metadata(capability))
    runs = []
    for entry in service.list_internal(agent, session_id=scope.session_id, kind=_RUN):
        state = entry.capability_state
        if type(state) is not _Run or state.scope != scope:
            continue
        try:
            _guard(before_effect, state.capability)
        except PermissionError:
            continue
        runs.append(_fact(service, entry, state))
    result = {"epoch": service.execution_epoch, "inventory_scope": "current_process",
        "capabilities": capabilities, "runs": runs, "inventory_truncated": False}
    while not service._projection_fits(result) and (runs or capabilities):
        (runs if runs else capabilities).pop()
        result["inventory_truncated"] = True
    return result


def get_core_workflow(service, agent, *, scope, run_id, before_effect):
    entry, state = _find(service, agent, scope, run_id)
    _guard(before_effect, state.capability)
    return _fact(service, entry, state)


def _chunk(entry, payload):
    return AgentResponseChunk(entry.request.request_id, entry.request.channel_id,
        payload={"core_workflow": payload}, is_complete=False)


async def _produce(service, entry, state):
    entered_sdk = False
    admission_guard = None

    def guard():
        _run_guard(service, entry, state, admission_guard)

    try:
        state.checkpointer = CheckpointerFactory.get_checkpointer()
        state.binding = await state.directory.resolve(scope=state.scope,
            capability_id=state.capability.capability_id, before_effect=guard)
        guard()
        def admit():
            nonlocal entered_sdk
            guard()
            entered_sdk = True
        output = await state.directory.invoke(scope=state.scope, binding=state.binding,
            sdk_session_id=state.sdk_session_id, inputs=state.inputs, before_effect=admit)
        while True:
            if not isinstance(output, WorkflowOutput):
                raise CoreWorkflowError("invalid_workflow_output")
            state.output = output.model_copy(deep=True)
            state.revision += 1
            if output.state != WorkflowExecutionState.INPUT_REQUIRED:
                yield _chunk(entry, _fact(service, entry, state))
                return
            pending_items = []
            for chunk in output.result if isinstance(output.result, list) else ():
                if isinstance(chunk, OutputSchema) and chunk.type == INTERACTION:
                    if not isinstance(chunk.payload, InteractionOutput):
                        raise CoreWorkflowError("unsupported_pending_output")
                    pending_items.append(chunk.payload.model_copy(deep=True))
            pending = tuple(pending_items)
            schemas = state.capability.continuation_schemas
            if not pending or len({item.id for item in pending}) != len(pending) or any(item.id not in schemas for item in pending):
                raise CoreWorkflowError("unsupported_pending_output")
            state.pending = pending
            state.inbox = asyncio.get_running_loop().create_future()
            yield _chunk(entry, _fact(service, entry, state))
            answers, admission_guard = await state.inbox
            state.inbox = None
            guard()
            from openjiuwen.core.workflow import WorkflowResumeGuard
            output = await state.directory.continue_workflow(scope=state.scope, binding=state.binding,
                sdk_session_id=state.sdk_session_id, pending=pending, answers=answers,
                before_effect=guard, resume_guard=WorkflowResumeGuard(before_effect=guard))
    except asyncio.CancelledError:
        state.failure = "cancelled"
        raise
    except Exception as error:
        reason = getattr(error, "code", None)
        state.failure = (str(error) if isinstance(error, CoreWorkflowError) else
            "permission_denied" if isinstance(error, PermissionError) else
            reason if isinstance(reason, str) else "workflow_execution_failed")
        raise
    finally:
        if state.inbox is not None and not state.inbox.done():
            state.inbox.cancel()
        state.inbox = None
        if entered_sdk:
            try:
                await state.checkpointer.release(state.sdk_session_id)
            except BaseException:
                state.failure = "checkpoint_cleanup_failed"
                raise


async def start_core_workflow(service, agent, *, request, scope, epoch, capability_id, inputs, before_effect):
    _epoch(service, epoch)
    directory = _directory(service)
    capability = directory.get(scope=scope, capability_id=capability_id)
    snapshot = directory.validate_inputs(scope=scope, capability_id=capability_id, inputs=inputs)
    snapshot = _json_snapshot(snapshot)
    internal = _request(request, scope, epoch, "start", capability_id=capability_id, inputs=snapshot)
    _guard(before_effect, capability)
    state = _Run(scope, epoch, directory, capability, before_effect, snapshot)
    state.receipt = {"status": "accepted", "run_id": state.run_id, "epoch": epoch,
        "revision": state.revision, "business_completion": False, "inventory_scope": "current_process"}
    entry = service.start_internal(agent, internal, kind=_RUN,
        producer=lambda item: _produce(service, item, state), capability_state=state)
    return deepcopy(entry.capability_state.receipt)


async def resume_core_workflow(service, agent, *, request, scope, epoch, run_id, expected_revision, answers, before_effect):
    _epoch(service, epoch)
    if type(expected_revision) is not int or not 0 < expected_revision < 2**53:
        raise CoreWorkflowError("invalid_revision")
    entry, state = _find(service, agent, scope, run_id)
    snapshot = _json_snapshot(answers)
    internal = _request(request, scope, epoch, "resume", run_id=run_id,
        expected_revision=expected_revision, answers=snapshot)
    _guard(before_effect, state.capability)
    control = _Control()

    async def deliver(control_entry):
        _live(service, entry, state)
        inbox = state.inbox
        if state.revision != expected_revision or inbox is None or inbox.done():
            raise CoreWorkflowError("pending_revision_mismatch")
        if not _fact(service, entry, state)["continuation_available"]:
            raise CoreWorkflowError("continuation_unavailable")
        validated = state.directory.validate_answers(scope=scope, capability_id=state.capability.capability_id,
            pending=state.pending, answers=snapshot)
        _run_guard(service, entry, state, before_effect)
        # Same loop: no await between final guard/CAS and the original Future.
        if state.revision != expected_revision or state.inbox is not inbox or inbox.done():
            raise CoreWorkflowError("pending_revision_mismatch")
        state.pending = ()
        inbox.set_result((validated, before_effect))
        control.receipt = {"status": "accepted", "run_id": run_id, "epoch": epoch,
            "revision": expected_revision, "business_completion": False, "inventory_scope": "current_process"}
        yield _chunk(control_entry, control.receipt)

    command = service.start_internal(agent, internal, kind=_CONTROL, producer=deliver,
        capability_state=control, control_only=True)
    if command.capability_state is not control and command.capability_state.receipt is not None:
        receipt = deepcopy(command.capability_state.receipt)
        if command.task.done() and (command.task.cancelled() or command.task.exception() is not None):
            receipt["observation_unavailable"] = True
        return receipt
    try:
        await asyncio.shield(command.task)
    except Exception:
        # Publishing/closing the control stream may fail after the original
        # Future accepted input. Only that exact entry's receipt proves delivery.
        if command.capability_state.receipt is None:
            raise
        return {**deepcopy(command.capability_state.receipt), "observation_unavailable": True}
    if command.capability_state.receipt is None:
        raise CoreWorkflowError("admission_unobserved")
    return deepcopy(command.capability_state.receipt)
