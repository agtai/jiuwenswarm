# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Operation-specific Provider inputs for the existing Native business carrier.

Tool names select only an existing operation. This adapter neither interprets
user intent nor supplies missing business facts, authority or execution.
"""

from __future__ import annotations

import json

from .native_business_contract import (
    NATIVE_BUSINESS_TOOL_NAME,
    NATIVE_BUSINESS_OPERATION_ORDER,
    native_business_action_fields,
    native_business_provider_fields,
    NativeBusinessAction,
    NativeBusinessProposal,
    NativeBusinessViolation,
)


_OPERATIONS = {operation: native_business_provider_fields(operation) for operation in NATIVE_BUSINESS_OPERATION_ORDER}
_FUNCTION_OPERATIONS = {"jiuwen_" + operation.replace(".", "_"): operation for operation in _OPERATIONS}
_BOUND_FUNCTION_OPERATIONS = {"jiuwen_bound_" + operation.replace(".", "_"): operation for operation in _OPERATIONS}
NATIVE_BOUND_BUSINESS_FUNCTION_NAMES = frozenset(_BOUND_FUNCTION_OPERATIONS)
NATIVE_BUSINESS_FUNCTION_NAMES = frozenset({NATIVE_BUSINESS_TOOL_NAME, *_FUNCTION_OPERATIONS, *_BOUND_FUNCTION_OPERATIONS})
_SERVER_CONTEXT_ABSENT = object()
_MAX_ARGUMENT_UTF8_BYTES = 16_384
_DESCRIPTIONS = {
    "team.list": "Observe this session's configured Team capability, actual fingerprint, service epoch and retained Team executions. Cold or unavailable configuration is explicit. This read does not prepare or start a Team.",
    "team.get": "Read the exact Team execution_id and epoch from team.list. Report actual input or tool launch receipts and physical settlement; a stream ending does not prove business completion.",
    "team.start": "Send an explicitly requested task to this session's configured Team through its original owner. Copy epoch and fingerprint from team.list; use null fingerprint only for an explicitly requested cold start. Keep the Team's configured member models and permissions. Input acceptance is not completion.",
    "team.cancel": "Cancel only the exact retained Team execution from team.list, using its epoch and execution_id. This requires the user's explicit cancellation request; speech interruption does not cancel Team work.",
    "workflow.start": "Launch an explicitly requested SwarmFlow through the configured Team leader's real tool and permissions. Copy the current epoch and Team fingerprint from team.list. Inputs contain exactly one of script_path or script and optional string args. Do not invent a script, workflow name or resume_id. Only actual run_id/task_id prove launch; a Team input receipt is not workflow completion.",
    "core_workflow.list": "Read explicitly registered Core Workflow capabilities, their input schemas, current-process runs and execution epoch for this conversation. An empty directory means no registered capability. These are separate from Team SwarmFlow runs.",
    "core_workflow.get": "Read an exact Core Workflow run_id and epoch from core_workflow.list. Report only actual Workflow output; awaiting_input is not completed. Read every pending node and continuation schema before answering.",
    "core_workflow.start": "Start an explicitly requested registered Core Workflow using its exact capability_id, current epoch and schema-valid inputs from core_workflow.list. The workflow retains its declared permissions. Acceptance is not completion; never invent a capability or input.",
    "core_workflow.resume": "Supply the user's answer to the exact current Core Workflow run_id, epoch and revision. The answers object must include every actual pending node ID with its schema-valid value. Repeating an accepted answer does not execute it again; old epochs and missing checkpoints cannot be resumed.",
    "goal.set": "Start the user's explicitly requested Goal through this conversation's configured Agent. To create when no Goal exists use null target_id and expected_revision. Replace an existing Goal only on explicit user request, using its exact goal_id and control_revision from goal.get. Acceptance is not completion; tools retain the authorized Native read-only policy.",
    "goal.resume": "Resume the explicitly requested paused or blocked Goal through its existing shared Agent, using exact goal_id and control_revision from goal.get. It uses the current authorized Native model and read-only tool policy. A running attempt cannot change its execution binding; speech interruption is not a resume request.",
    "agent.list": "Observe the configured conversation Agent's recorded output streams, including text-started executions. A stream ending is not proof that a Goal, Team or Task completed. An empty recent stream inventory is not proof there is no work.",
    "agent.get": "Read recent actual Agent output and interaction requests for an exact execution_id from agent.list. Events may be bounded; consult the Goal, Team, Workflow or Task owner for business state and completion. This does not invoke tools or answer an approval request.",
    "agent.pending": "Read this conversation Agent's actual pending questions and their answer schemas. Copy the exact source_binding_id, source_task_id, pending_token and input_id for a reply. Observation grants no approval and does not execute anything.",
    "agent.reply": "Send only the user's explicit answer to one exact question from agent.pending. Put its source_binding_id in target_id and copy source_task_id, pending_token and input_id unchanged. Use its answer schema; never invent approval or auto-confirm future tools. Acceptance consumes this pending input once and does not prove execution completion. Original work retains its configured model, permissions and history ownership.",
    "goal.pause": "Pause the user's exact Goal on explicit request, using goal_id and control_revision from goal.get. This stops future attempts and allows the current attempt to finish. Speech interruption is not a pause request.",
    "goal.clear": "Remove the exact Goal and cancel its active Goal attempt only when the user explicitly asks to clear or abandon that Goal. Use goal_id and control_revision from goal.get. Speech interruption is not a clear request.",
    "goal.get": "Read this conversation's actual Goal from its existing shared Agent owner. An unavailable owner does not mean there is no Goal. This does not start, resume or cancel execution.",
    "workflow.list": "Read SwarmFlow workflows in this authorized conversation, including flows started from text. This only observes existing runs; it does not start or resume work.",
    "workflow.get": "Read the actual state, result and pending human input of an exact SwarmFlow run in this conversation. Use the workflow ID returned by workflow.list.",
    "workflow.reply": "Send the user's answer to one exact pending human input from workflow.get. Copy its workflow run ID into target_id and correlation ID into input_id. This accepts an answer; it does not prove workflow completion. Do not guess an answer or treat speech interruption as a reply.",
    "context.get": "Read server facts, target IDs or revisions only when required information is missing or stale; then continue the necessary call. Do not repeat an acknowledgment for this dependent lookup or use it to recheck an exact receipt.",
    "task.list": "Read the background Task overview when requested. Use this instead of one status call per Task; report only the returned observations.",
    "task.status": "Read the observed state of an exact background Task. Use its server ID, never a title or guessed ID. Report the state at the observation time without inferring completion or adjustment success.",
    "task.result": "Read the actual result of an exact background Task. Answer from its concrete facts, preserving requested detail and certainty. Accepted or running does not mean completed; a display name is not an artifact filename.",
    "task.create": "Create one background artifact Task for a user-delegated deliverable, including an itinerary or plan even without a filename. Use this instead of {work_start}. For a changed project-file copy, include the actual source, all changes, exact destination and preservation of the source in this one Task. A brief spoken acknowledgment must not shorten the executable request or delay the call. Acceptance is not completion.",
    "task.create_successor": "Create one successor to an exact observed Task on the user's explicit request, using its ID and revision. Include the actual source filename, every change, exact new output and preservation of the source. Do not also adjust the predecessor or duplicate accepted work. Acceptance is not completion.",
    "task.adjust": "Submit the user's complete explicit change to the exact observed Task and revision. When supported, a closing or completed Task queues a successor that changes its saved result; do not duplicate that accepted change with another create. A new question is not an adjustment. Dispatched means accepted; execution adoption and saved completion are distinct. Report the exact adjustment observation and final outcome.",
    "task.cancel": "Request cancellation of the exact Task only when the user asks to cancel that work. Use the observed ID and revision and report the receipt. Speech interruption or a new topic is not cancellation.",
    "work.start": "Start real Jiuwen Agent/tools for read-only analysis or lookup of external/project facts, including weather, forecasts, opening hours and ticket conditions. Call promptly; a minimal acknowledgment is sufficient and need not finish playing first. This Agent cannot create Tasks or write deliverables; use {task_create} for a delegated background deliverable. Do not repeat an already delivered lookup announcement.",
    "work.list": "Read the independent analysis Work overview when requested. Use this instead of querying each item separately; preserve observed states.",
    "work.get": "Read the state and complete result of an exact Work when a user follow-up needs its unspoken result, status or more detail. Use the observed ID; do not restart the lookup. Answer the user's question from the returned receipt, without a separate read acknowledgment. Do not poll accepted/running Work to wait. The runtime binds this answer to the queried result; only actual playback retires its automatic notification. Avoid retelling information already confirmed as heard unless requested.",
    "work.update": "Request an explicit revision of the exact analysis Work using its observed ID and revision. Preserve every revised requirement. A new unrelated question does not revise existing Work; report only the actual receipt.",
    "work.cancel": "Request cancellation of the exact analysis Work only when the user asks to cancel it, using its observed ID and revision. Speech interruption or a new topic does not cancel accepted Work; report the actual receipt.",
}


def _tool_description(operation: str, *, bound_context: bool) -> str:
    names = _BOUND_FUNCTION_OPERATIONS if bound_context else _FUNCTION_OPERATIONS
    return _DESCRIPTIONS[operation].format(**{
        operation.replace(".", "_"): name for name, operation in names.items()
    })


def _property(field: str, operation: str) -> dict[str, object]:
    if field == "fingerprint":
        return {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$",
                "description": "Copy configured_team.capability.spec_fingerprint from team.list, or null for an explicitly requested cold start."}
    if operation in {"team.get", "team.start", "team.cancel", "workflow.start"} and field == "epoch":
        return {"type": "string", "minLength": 1, "maxLength": 256,
                "description": "The current process epoch from team.list. Never reuse an old process epoch."}
    if operation == "workflow.start" and field == "inputs":
        return {"type": "object", "additionalProperties": False,
                "properties": {key: {"type": "string"} for key in ("script_path", "script", "args")},
                "description": "Exactly one nonempty script_path or inline script, plus optional string args; at most 8192 UTF-8 bytes. Use the user's specified script."}
    if operation == "agent.reply" and field in {"target_id", "source_task_id", "pending_token", "input_id"}:
        return {"type": "string", "minLength": 1, "maxLength": 256,
                "description": "Copy the exact " + ("source_binding_id" if field == "target_id" else field) + " from agent.pending. Never guess or reuse a consumed question."}
    if operation == "agent.reply" and field == "answers":
        return {"type": "array", "minItems": 1, "items": {"type": "object", "additionalProperties": True},
                "description": "The user's explicit answers in the selected question's observed answer schema. Finite JSON, at most 8192 UTF-8 bytes. Do not infer approval."}
    if field in {"epoch", "capability_id"}:
        return {"type": "string", "minLength": 1, "maxLength": 256,
                "description": "Copy the exact " + field + " from core_workflow.list; never guess or reuse an old process epoch."}
    if field in {"inputs", "answers"}:
        return {"type": "object", "additionalProperties": True,
                "description": ("The complete input object matching the registered input_schema." if field == "inputs" else
                    "Every actual pending node ID mapped to the user's answer matching its continuation schema.") +
                    " Finite JSON only, at most 8192 UTF-8 bytes. Do not invent values."}
    if operation == "goal.set" and field in {"target_id", "expected_revision"}:
        schema = _property(field, "goal.resume")
        return {"anyOf": [schema, {"type": "null"}],
                "description": "Both null for a new Goal; otherwise the exact observed Goal ID and control revision for an explicitly requested replacement."}
    if field == "context_id":
        return {
            "type": ["string", "null"] if operation == "context.get" else "string",
            "pattern": "^[0-9a-f]{64}$",
            "description": "Copy the latest server context_id; never guess. Only context.get permits null when no context is available.",
        }
    if field == "expected_revision":
        return {
            "type": "integer", "minimum": 1, "maximum": 2**53 - 1,
            "description": "Copy the target's exact observed revision_number (Task), revision (work), or control_revision (Goal) from server facts. A Goal attempt revision is not its control revision.",
        }
    if field in {"target_id", "input_id"}:
        return {
            "type": "string", "minLength": 1, "maxLength": 256,
            "description": ("Copy the exact pending human-input correlation_id from workflow.get." if field == "input_id" else
                "Copy the exact server task_id, work_id, goal_id, workflow ID or execution_id; never use a title, guessed ID or surrounding whitespace."),
        }
    if field == "request_text":
        return {
            "type": "string", "minLength": 1, "maxLength": 16_384,
            "description": "The user's current request preserving intent and requirements, trimmed and control-free, at most 16384 UTF-8 bytes. Does not replace instruction or adjustment.",
        }
    meaning = {
        "name": "A concise name for the new background Task",
        "instruction": "The complete analysis or artifact requirements, retaining every relevant user constraint. For derived artifacts, specify the source input, all requested transformations, exact output filename and which originals must remain unchanged",
        "adjustment": "The user's requested change to the existing background Task",
    }[field]
    maximum = 256 if field == "name" else 4096
    return {
        "type": "string", "minLength": 1, "maxLength": maximum,
        "description": f"{meaning}. Nonblank and NUL-free; at most {maximum} UTF-8 bytes.",
    }


def native_business_tools(*, bound_context: bool = False) -> list[dict[str, object]]:
    """Return fresh simple JSON Schemas; internal null-only fields stay internal."""
    if bound_context:
        result = []
        for name, operation in _BOUND_FUNCTION_OPERATIONS.items():
            fields = ["request_text", *(field for field in _OPERATIONS[operation]
                                       if field not in {"context_id", "instruction", "adjustment"})]
            properties = {field: _property(field, operation) for field in fields}
            intent_field = next((field for field in ("instruction", "adjustment")
                                 if field in _OPERATIONS[operation]), None)
            if intent_field is not None:
                properties["request_text"] = {
                    **_property("request_text", operation), "maxLength": 4096,
                    "description": "The ONE complete, self-contained executable request for this operation, preserving every user constraint and literal filename. "
                    "Resolve references from confirmed conversation facts; do not copy unrelated operations into this request. "
                    "Include required source, transformations, exact destination, dates, numbers, negations and preservation rules. "
                    "This text is used unchanged as both the request and the executable " + intent_field +
                    "; do not shorten it into a title or acknowledgement. Trimmed, control-free, at most 4096 UTF-8 bytes.",
                }
            result.append({"type": "function", "name": name,
                "description": _tool_description(operation, bound_context=True) + " The server binds the exact context; do not generate a context ID.",
                "parameters": {"type": "object", "additionalProperties": False,
                               "required": fields, "properties": properties}})
        return result
    return [
        {
            "type": "function", "name": name, "description": _tool_description(operation, bound_context=False),
            "parameters": {
                "type": "object", "additionalProperties": False,
                "required": ["request_text", *_OPERATIONS[operation]],
                "properties": {field: _property(field, operation) for field in ("request_text", *_OPERATIONS[operation])},
            },
        }
        for name, operation in _FUNCTION_OPERATIONS.items()
    ]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise NativeBusinessViolation("NATIVE_BUSINESS_DUPLICATE_FIELD")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise NativeBusinessViolation("NATIVE_BUSINESS_JSON_INVALID")


def native_business_proposal_from_function_call(
    *, name: object, arguments: object, server_context_id: object = _SERVER_CONTEXT_ABSENT, **binding: object,
) -> NativeBusinessProposal:
    """Decode closed Provider fields, retaining the authoritative v1 validators."""
    if type(name) is not str or name not in NATIVE_BUSINESS_FUNCTION_NAMES:
        raise NativeBusinessViolation("NATIVE_BUSINESS_FUNCTION_UNSUPPORTED")
    if type(arguments) is not str:
        raise NativeBusinessViolation()
    try:
        argument_bytes = len(arguments.encode("utf-8"))
    except UnicodeEncodeError:
        raise NativeBusinessViolation("NATIVE_BUSINESS_JSON_INVALID") from None
    if argument_bytes > _MAX_ARGUMENT_UTF8_BYTES:
        raise NativeBusinessViolation()
    if name == NATIVE_BUSINESS_TOOL_NAME:
        try:
            return NativeBusinessProposal.from_function_call(arguments=arguments, **binding)
        except RecursionError:
            raise NativeBusinessViolation("NATIVE_BUSINESS_JSON_INVALID") from None
    bound = name in _BOUND_FUNCTION_OPERATIONS
    operation = (_BOUND_FUNCTION_OPERATIONS if bound else _FUNCTION_OPERATIONS)[name]
    try:
        try:
            value = json.loads(arguments, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        except NativeBusinessViolation:
            raise
        except (ValueError, TypeError, RecursionError):
            raise NativeBusinessViolation("NATIVE_BUSINESS_JSON_INVALID") from None
        expected_fields = {"request_text", *_OPERATIONS[operation]}
        if bound:
            expected_fields -= {"context_id", "instruction", "adjustment"}
        if type(value) is not dict or set(value) != expected_fields:
            missing = expected_fields - set(value) if type(value) is dict else set()
            raise NativeBusinessViolation(
                "NATIVE_BUSINESS_FIELDS_NOT_CLOSED",
                field=sorted(missing)[0] if missing else "arguments",
                expected="Exactly these fields: " + ", ".join(sorted(expected_fields)),
            )
        if bound:
            if server_context_id is _SERVER_CONTEXT_ABSENT:
                raise NativeBusinessViolation("NATIVE_BUSINESS_CONTEXT_BINDING_MISSING")
            value = {**value, "context_id": server_context_id}
            for field in ("instruction", "adjustment"):
                if field in _OPERATIONS[operation]:
                    value[field] = value["request_text"]
        action = NativeBusinessAction.from_dict({
            "operation": operation,
            **{field: value[field] if field in _OPERATIONS[operation] else None
               for field in native_business_action_fields(operation) if field != "operation"},
        })
        return NativeBusinessProposal(**binding, request_text=value["request_text"], business=action)
    except NativeBusinessViolation as exc:
        exc.operation = operation
        # A local correction addresses the advertised flat field, not v1's
        # internal action wrapper. No argument values enter error metadata.
        if exc.field.startswith("action."):
            exc.field = exc.field.removeprefix("action.")
        if bound and exc.field in {"instruction", "adjustment"}:
            exc.field = "request_text"
        raise
