# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Operation-specific Provider inputs for the existing Native business carrier.

Tool names select only an existing operation. This adapter neither interprets
user intent nor supplies missing business facts, authority or execution.
"""

from __future__ import annotations

import json

from .native_business_contract import (
    NATIVE_BUSINESS_TOOL_NAME,
    NativeBusinessAction,
    NativeBusinessProposal,
    NativeBusinessViolation,
)


_OPERATIONS = {
    "context.get": ("context_id",),
    "task.list": ("context_id",),
    "task.status": ("context_id", "target_id"),
    "task.result": ("context_id", "target_id"),
    "task.create": ("context_id", "name", "instruction"),
    "task.create_successor": ("context_id", "target_id", "expected_revision", "name", "instruction"),
    "task.adjust": ("context_id", "target_id", "expected_revision", "adjustment"),
    "task.cancel": ("context_id", "target_id", "expected_revision"),
    "work.start": ("context_id", "instruction"),
    "work.list": ("context_id",),
    "work.get": ("context_id", "target_id"),
    "work.update": ("context_id", "target_id", "expected_revision", "instruction"),
    "work.cancel": ("context_id", "target_id", "expected_revision"),
}
_FUNCTION_OPERATIONS = {"jiuwen_" + operation.replace(".", "_"): operation for operation in _OPERATIONS}
_BOUND_FUNCTION_OPERATIONS = {"jiuwen_bound_" + operation.replace(".", "_"): operation for operation in _OPERATIONS}
NATIVE_BOUND_BUSINESS_FUNCTION_NAMES = frozenset(_BOUND_FUNCTION_OPERATIONS)
NATIVE_BUSINESS_FUNCTION_NAMES = frozenset({NATIVE_BUSINESS_TOOL_NAME, *_FUNCTION_OPERATIONS, *_BOUND_FUNCTION_OPERATIONS})
_SERVER_CONTEXT_ABSENT = object()
_ACTION_FIELDS = ("context_id", "target_id", "expected_revision", "name", "instruction", "adjustment")
_MAX_ARGUMENT_UTF8_BYTES = 16_384
_DESCRIPTIONS = {
    "context.get": "Read server facts, target IDs or revisions only when required information is missing or stale; then continue the necessary call. Do not repeat an acknowledgment for this dependent lookup or use it to recheck an exact receipt.",
    "task.list": "Read the background Task overview when requested. Use this instead of one status call per Task; report only the returned observations.",
    "task.status": "Read the observed state of an exact background Task. Use its server ID, never a title or guessed ID. Report the state at the observation time without inferring completion or adjustment success.",
    "task.result": "Read the actual result of an exact background Task. Answer from its concrete facts, preserving requested detail and certainty. Accepted or running does not mean completed; a display name is not an artifact filename.",
    "task.create": "Create one background artifact Task for a user-delegated deliverable, including an itinerary or plan even without a filename. Use this instead of {work_start}. For a changed project-file copy, include the actual source, all changes, exact destination and preservation of the source in this one Task. A brief spoken acknowledgment must not shorten the executable request or delay the call. Acceptance is not completion.",
    "task.create_successor": "Create one successor to an exact observed Task on the user's explicit request, using its ID and revision. Include the actual source filename, every change, exact new output and preservation of the source. Do not also adjust the predecessor or duplicate accepted work. Acceptance is not completion.",
    "task.adjust": "Request the user's explicit change to the exact existing Task itself using its observed ID and revision. A changed copy uses {task_create} or {task_create_successor}; a new question is not an adjustment. Dispatched means accepted, not applied; report the exact adjustment observation.",
    "task.cancel": "Request cancellation of the exact Task only when the user asks to cancel that work. Use the observed ID and revision and report the receipt. Speech interruption or a new topic is not cancellation.",
    "work.start": "Start real Jiuwen Agent/tools for read-only analysis or lookup of external/project facts, including weather, forecasts, opening hours and ticket conditions. Call promptly; a minimal acknowledgment is sufficient and need not finish playing first. This Agent cannot create Tasks or write deliverables; use {task_create} for a delegated background deliverable. Do not repeat an already delivered lookup announcement.",
    "work.list": "Read the independent analysis Work overview when requested. Use this instead of querying each item separately; preserve observed states.",
    "work.get": "Read the state and complete result of an exact Work when the user asks for status or needs more completed-result detail. Use the observed ID. Do not poll accepted/running Work to wait; the server supplies its result. Avoid retelling information already confirmed as heard.",
    "work.update": "Request an explicit revision of the exact analysis Work using its observed ID and revision. Preserve every revised requirement. A new unrelated question does not revise existing Work; report only the actual receipt.",
    "work.cancel": "Request cancellation of the exact analysis Work only when the user asks to cancel it, using its observed ID and revision. Speech interruption or a new topic does not cancel accepted Work; report the actual receipt.",
}


def _tool_description(operation: str, *, bound_context: bool) -> str:
    names = _BOUND_FUNCTION_OPERATIONS if bound_context else _FUNCTION_OPERATIONS
    return _DESCRIPTIONS[operation].format(**{
        operation.replace(".", "_"): name for name, operation in names.items()
    })


def _property(field: str, operation: str) -> dict[str, object]:
    if field == "context_id":
        return {
            "type": ["string", "null"] if operation == "context.get" else "string",
            "pattern": "^[0-9a-f]{64}$",
            "description": "Copy the latest server context_id; never guess. Only context.get permits null when no context is available.",
        }
    if field == "expected_revision":
        return {
            "type": "integer", "minimum": 1, "maximum": 2**53 - 1,
            "description": "Copy the target's exact observed revision_number (Task) or revision (work) from server facts.",
        }
    if field == "target_id":
        return {
            "type": "string", "minLength": 1, "maxLength": 256,
            "description": "Copy the exact server task_id or work_id; never use a title, guessed ID or surrounding whitespace.",
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
            **{field: value[field] if field in _OPERATIONS[operation] else None for field in _ACTION_FIELDS},
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
