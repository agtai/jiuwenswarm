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
NATIVE_BUSINESS_FUNCTION_NAMES = frozenset({NATIVE_BUSINESS_TOOL_NAME, *_FUNCTION_OPERATIONS})
_ACTION_FIELDS = ("context_id", "target_id", "expected_revision", "name", "instruction", "adjustment")
_MAX_ARGUMENT_UTF8_BYTES = 16_384
_DESCRIPTIONS = {
    "context.get": "Read current server context when facts, IDs or revisions are missing or stale; then continue the needed call.",
    "task.list": "Read the current background Task overview. Use this for an overview instead of one status call per Task.",
    "task.status": "Read the status of an exact background Task from server facts.",
    "task.result": "Read the actual result of an exact background Task. Accepted or running does not mean completed.",
    "task.create": "Create background artifact work only when the user explicitly delegates it. Preserve all requirements.",
    "task.create_successor": "Create a successor to an exact Task only on the user's explicit request, preserving requirements.",
    "task.adjust": "Apply the user's explicit change to the exact background Task. A new question alone is not an adjustment.",
    "task.cancel": "Cancel the exact background Task only on the user's explicit request. Speech interruption is not cancellation.",
    "work.start": "Use real Jiuwen Agent/tools for a project or file question or analysis. Call promptly without announcing a plan. This does not create a background Task.",
    "work.list": "Read the current independent analysis work overview.",
    "work.get": "Read the actual state and complete result of an exact analysis work item.",
    "work.update": "Apply explicit revised analysis requirements to the exact independent work item.",
    "work.cancel": "Cancel the exact independent analysis work only on an explicit request. Speech interruption is not cancellation.",
}


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
        "instruction": "The complete analysis or artifact requirements, retaining every relevant user constraint",
        "adjustment": "The user's requested change to the existing background Task",
    }[field]
    maximum = 256 if field == "name" else 4096
    return {
        "type": "string", "minLength": 1, "maxLength": maximum,
        "description": f"{meaning}. Nonblank and NUL-free; at most {maximum} UTF-8 bytes.",
    }


def native_business_tools() -> list[dict[str, object]]:
    """Return fresh simple JSON Schemas; internal null-only fields stay internal."""
    return [
        {
            "type": "function", "name": name, "description": _DESCRIPTIONS[operation],
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
    *, name: object, arguments: object, **binding: object,
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
    operation = _FUNCTION_OPERATIONS[name]
    try:
        try:
            value = json.loads(arguments, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        except NativeBusinessViolation:
            raise
        except (ValueError, TypeError, RecursionError):
            raise NativeBusinessViolation("NATIVE_BUSINESS_JSON_INVALID") from None
        expected_fields = {"request_text", *_OPERATIONS[operation]}
        if type(value) is not dict or set(value) != expected_fields:
            missing = expected_fields - set(value) if type(value) is dict else set()
            raise NativeBusinessViolation(
                "NATIVE_BUSINESS_FIELDS_NOT_CLOSED",
                field=sorted(missing)[0] if missing else "arguments",
                expected="Exactly these fields: " + ", ".join(sorted(expected_fields)),
            )
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
        raise
