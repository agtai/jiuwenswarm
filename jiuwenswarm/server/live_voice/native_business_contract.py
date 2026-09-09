# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Versioned Native business proposals, never execution or consent receipts.

The explicit capability extends the Native carrier without changing the legacy
delegate shape. Only the authenticated Runtime may admit a proposed operation.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from collections.abc import Mapping
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode, canonical_json_bytes
from .native_interaction_contract import NativeDelegateProposal
from .production_task_intent import ProductionTaskIntentProposal

NATIVE_BUSINESS_CONTRACT_VERSION = "live-voice.native-business.v1"
NATIVE_BUSINESS_TOOL_NAME = "jiuwen_business"
NATIVE_BUSINESS_OPERATION_ORDER = (
    "context.get", "task.list", "task.status", "task.result", "task.create",
    "task.create_successor", "task.adjust", "task.cancel", "work.start",
    "work.list", "work.get", "work.update", "work.cancel",
    "workflow.list", "workflow.get", "workflow.reply", "goal.get", "goal.set", "goal.resume", "goal.pause", "goal.clear",
    "agent.list", "agent.get", "agent.pending", "agent.reply",
    "team.list", "team.get", "team.start", "team.cancel", "workflow.start",
    "core_workflow.list", "core_workflow.get", "core_workflow.start", "core_workflow.resume",
)
NATIVE_BUSINESS_OPERATIONS = frozenset(NATIVE_BUSINESS_OPERATION_ORDER)
_FIELDS = frozenset({"operation", "context_id", "target_id", "expected_revision",
                     "name", "instruction", "adjustment"})
_COLLECTION = frozenset({"context.get", "task.list", "task.create", "work.list", "work.start", "workflow.list", "workflow.start", "goal.get", "agent.list", "agent.pending", "team.list", "team.start", "core_workflow.list", "core_workflow.start"})
_REVISION_REQUIRED = frozenset({"task.adjust", "task.cancel", "task.create_successor", "work.update", "work.cancel", "goal.pause", "goal.clear", "goal.resume", "core_workflow.resume"})
_EXTRA_FIELDS = {
    "team.get": frozenset({"epoch"}),
    "team.start": frozenset({"epoch", "fingerprint"}),
    "team.cancel": frozenset({"epoch"}),
    "workflow.start": frozenset({"epoch", "fingerprint", "inputs"}),
    "workflow.reply": frozenset({"input_id"}),
    "agent.reply": frozenset({"input_id", "source_task_id", "pending_token", "answers"}),
    "core_workflow.list": frozenset(),
    "core_workflow.get": frozenset({"epoch"}),
    "core_workflow.start": frozenset({"epoch", "capability_id", "inputs"}),
    "core_workflow.resume": frozenset({"epoch", "answers"}),
}


def native_business_action_fields(operation):
    return _FIELDS | _EXTRA_FIELDS.get(operation, frozenset())


def _json_value(value, field, *, container=dict):
    if type(value) is not container:
        raise NativeBusinessViolation(field=field, expected="A JSON " + ("array" if container is list else "object") + " matching the observed input schema")
    def check(item):
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("non-string key")
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("non-JSON value")
    try:
        check(value)
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")
        if len(encoded) > 8192:
            raise ValueError("JSON too large")
    except (ValueError, TypeError, RecursionError) as error:
        raise NativeBusinessViolation(field=field, expected="Finite JSON, at most 8192 UTF-8 bytes") from error
    return deepcopy(value)
_TEXT_ARGUMENTS = {
    "task.create": frozenset({"name", "instruction"}),
    "task.create_successor": frozenset({"name", "instruction"}),
    "task.adjust": frozenset({"adjustment"}),
    "work.start": frozenset({"instruction"}),
    "work.update": frozenset({"instruction"}),
    "workflow.reply": frozenset({"instruction"}),
    "goal.set": frozenset({"instruction"}),
    "team.start": frozenset({"instruction"}),
}


def native_business_provider_fields(operation):
    """Project existing action rules in the established Provider field order."""
    fields = {"context_id"} | _TEXT_ARGUMENTS.get(operation, frozenset()) | _EXTRA_FIELDS.get(operation, frozenset())
    if operation not in _COLLECTION:
        fields.add("target_id")
    if operation in _REVISION_REQUIRED or operation == "goal.set":
        fields.add("expected_revision")
    return tuple(field for field in (
        "context_id", "target_id", "epoch", "expected_revision", "fingerprint", "capability_id",
        "source_task_id", "pending_token", "input_id", "name", "instruction", "adjustment", "inputs", "answers",
    ) if field in fields)


class NativeBusinessViolation(ValueError):
    def __init__(self, reason: str = "NATIVE_BUSINESS_ARGUMENT_INVALID", *, code=ErrorCode.INVALID_ARGUMENT,
                 field: str = "arguments", expected: str = "A JSON object matching the closed tool schema"):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.field = field
        self.expected = expected
        self.operation: str | None = None


def _text(value: object, *, maximum: int, field: str) -> str:
    expected = f"A nonempty string without null characters, at most {maximum} UTF-8 bytes"
    if type(value) is not str or not value.strip() or "\x00" in value:
        raise NativeBusinessViolation(field=field, expected=expected)
    try:
        if len(value.encode("utf-8")) > maximum:
            raise NativeBusinessViolation(field=field, expected=expected)
    except UnicodeEncodeError:
        raise NativeBusinessViolation(field=field, expected=expected) from None
    return value


@dataclass(frozen=True, slots=True)
class NativeBusinessAction:
    operation: str
    context_id: str | None
    target_id: str | None
    expected_revision: int | None
    name: str | None
    instruction: str | None
    adjustment: str | None
    input_id: str | None = None
    source_task_id: str | None = None
    pending_token: str | None = None
    fingerprint: str | None = None
    epoch: str | None = None
    capability_id: str | None = None
    inputs: dict | None = None
    answers: dict | list | None = None

    def __post_init__(self):
        if type(self.operation) is not str or self.operation not in NATIVE_BUSINESS_OPERATIONS:
            raise NativeBusinessViolation("NATIVE_BUSINESS_OPERATION_UNSUPPORTED", code=ErrorCode.UNSUPPORTED,
                field="action.operation", expected="One of: " + ", ".join(sorted(NATIVE_BUSINESS_OPERATIONS)))
        if self.operation != "context.get" or self.context_id is not None:
            if type(self.context_id) is not str or re.fullmatch(r"[0-9a-f]{64}", self.context_id) is None:
                raise NativeBusinessViolation("NATIVE_BUSINESS_CONTEXT_REQUIRED", field="action.context_id",
                    expected="The 64-character context_id from server facts; call context.get if missing")
        if self.operation in _COLLECTION:
            if self.target_id is not None:
                raise NativeBusinessViolation("NATIVE_BUSINESS_TARGET_FORBIDDEN", field="action.target_id", expected="null")
        elif self.operation != "goal.set" or self.target_id is not None:
            _text(self.target_id, maximum=1024, field="action.target_id")
            if len(self.target_id) > 256 or self.target_id.strip() != self.target_id:
                raise NativeBusinessViolation("NATIVE_BUSINESS_TARGET_INVALID", field="action.target_id",
                    expected="The exact server target ID, at most 256 characters, without surrounding whitespace")
        if self.operation in _REVISION_REQUIRED or self.operation == "goal.set" and self.target_id is not None:
            if type(self.expected_revision) is not int or not 0 < self.expected_revision < 2**53:
                raise NativeBusinessViolation("NATIVE_BUSINESS_REVISION_REQUIRED", field="action.expected_revision",
                    expected="The target's observed server revision as a positive integer below 2**53, not a string")
        elif self.expected_revision is not None:
            raise NativeBusinessViolation("NATIVE_BUSINESS_REVISION_FORBIDDEN", field="action.expected_revision", expected="null")
        if self.operation in {"workflow.reply", "agent.reply"}:
            _text(self.input_id, maximum=1024, field="action.input_id")
            if len(self.input_id) > 256 or self.input_id.strip() != self.input_id:
                raise NativeBusinessViolation("NATIVE_BUSINESS_INPUT_INVALID", field="action.input_id",
                    expected="The exact pending input correlation ID, without surrounding whitespace, at most 256 characters")
        elif self.input_id is not None:
            raise NativeBusinessViolation("NATIVE_BUSINESS_UNUSED_ARGUMENT", field="action.input_id", expected="omitted")
        extra_fields = _EXTRA_FIELDS.get(self.operation, frozenset())
        for key in ("epoch", "capability_id", "inputs", "answers", "source_task_id", "pending_token", "fingerprint"):
            value = getattr(self, key)
            if key not in extra_fields:
                if value is not None:
                    raise NativeBusinessViolation("NATIVE_BUSINESS_UNUSED_ARGUMENT", field="action." + key, expected="omitted")
            elif key in {"inputs", "answers"}:
                container = list if self.operation == "agent.reply" else dict
                object.__setattr__(self, key, _json_value(value, "action." + key, container=container))
                if container is list and not value:
                    raise NativeBusinessViolation(field="action." + key, expected="The user's nonempty answer array for the selected observed question")
            elif key == "fingerprint":
                if value is not None and (type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None):
                    raise NativeBusinessViolation(field="action.fingerprint", expected="The exact observed Team configuration fingerprint, or null for an authorized cold start")
            else:
                _text(value, maximum=256, field="action." + key)
                if value.strip() != value:
                    raise NativeBusinessViolation(field="action." + key, expected="The exact server identity without surrounding whitespace")
        required = _TEXT_ARGUMENTS.get(self.operation, frozenset())
        for key in ("name", "instruction", "adjustment"):
            value = getattr(self, key)
            if key in required:
                _text(value, maximum=256 if key == "name" else 4096, field="action." + key)
            elif value is not None:
                raise NativeBusinessViolation("NATIVE_BUSINESS_UNUSED_ARGUMENT", field="action." + key, expected="null")

    @classmethod
    def from_dict(cls, value: object) -> NativeBusinessAction:
        operation = value.get("operation") if isinstance(value, Mapping) else None
        fields = native_business_action_fields(operation) if type(operation) is str else _FIELDS
        if not isinstance(value, Mapping) or set(value) != fields:
            raise NativeBusinessViolation("NATIVE_BUSINESS_FIELDS_NOT_CLOSED", field="action",
                expected="Exactly these fields (unused values must be null): " + ", ".join(sorted(fields)))
        try:
            return cls(**value)
        except NativeBusinessViolation as exc:
            operation = value["operation"]
            if type(operation) is str and operation in NATIVE_BUSINESS_OPERATIONS:
                exc.operation = operation
            raise

    def to_dict(self) -> dict[str, object]:
        return {key: deepcopy(getattr(self, key)) for key in sorted(native_business_action_fields(self.operation))}

    @property
    def mutates(self) -> bool:
        return self.operation in {"task.create", "task.create_successor", "task.adjust", "task.cancel", "work.update", "work.cancel", "goal.set", "goal.resume", "goal.pause", "goal.clear", "workflow.reply", "workflow.start", "team.start", "team.cancel", "agent.reply", "core_workflow.start", "core_workflow.resume"}

    def task_proposal(self) -> ProductionTaskIntentProposal:
        if not self.operation.startswith("task."):
            raise NativeBusinessViolation("NATIVE_BUSINESS_NOT_TASK")
        arguments = {key: getattr(self, key) for key in _TEXT_ARGUMENTS.get(self.operation, ())}
        if self.operation in {"task.list", "task.status", "task.result"}:
            arguments["query_kind"] = self.operation.split(".", 1)[1]
        if self.operation == "task.list":
            arguments["limit"] = 20
        return ProductionTaskIntentProposal(
            self.operation, self.target_id, arguments, 1.0, True,
            target_kind="task_id" if self.target_id is not None else None,
            observed_task_revision=self.expected_revision,
            reason="NATIVE_BUSINESS_PROPOSAL",
        )


@dataclass(frozen=True, slots=True)
class NativeBusinessProposal(NativeDelegateProposal):
    """Explicitly negotiated extension; old NativeDelegateProposal is unchanged."""

    business: NativeBusinessAction | None = None

    def __post_init__(self):
        NativeDelegateProposal.__post_init__(self)
        if not isinstance(self.business, NativeBusinessAction):
            raise NativeBusinessViolation("NATIVE_BUSINESS_ACTION_REQUIRED")

    def to_dict(self):
        return {**NativeDelegateProposal.to_dict(self), "business": {
            "contract_version": NATIVE_BUSINESS_CONTRACT_VERSION,
            "action": self.business.to_dict(),
        }}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, Mapping) or "business" not in value:
            raise NativeBusinessViolation("NATIVE_BUSINESS_PROPOSAL_INVALID")
        base = NativeDelegateProposal.from_dict({key: item for key, item in value.items() if key != "business"})
        body = value["business"]
        if not isinstance(body, Mapping) or set(body) != {"contract_version", "action"} or body["contract_version"] != NATIVE_BUSINESS_CONTRACT_VERSION:
            raise NativeBusinessViolation("NATIVE_BUSINESS_CONTRACT_UNSUPPORTED", code=ErrorCode.UNSUPPORTED)
        return cls(**{key: getattr(base, key) for key in base.__dataclass_fields__},
                   business=NativeBusinessAction.from_dict(body["action"]))

    @classmethod
    def from_function_call(cls, *, arguments: object, **binding):
        if type(arguments) is not str or len(arguments.encode("utf-8")) > 16384:
            raise NativeBusinessViolation()
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise NativeBusinessViolation("NATIVE_BUSINESS_DUPLICATE_FIELD")
                result[key] = value
            return result
        try:
            value = json.loads(arguments, object_pairs_hook=unique)
        except (ValueError, TypeError):
            raise NativeBusinessViolation("NATIVE_BUSINESS_JSON_INVALID") from None
        if not isinstance(value, dict) or set(value) != {"request_text", "action"}:
            raise NativeBusinessViolation("NATIVE_BUSINESS_FIELDS_NOT_CLOSED")
        return cls(**binding, request_text=value["request_text"], business=NativeBusinessAction.from_dict(value["action"]))

    @property
    def source_identity(self) -> str:
        # Includes admitted input turn, source response, Provider call and context;
        # never replace this binding with a fabricated semantic-model decision.
        return "native-business:" + hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()


def native_business_tool() -> dict[str, object]:
    def text_argument(field: str, meaning: str) -> dict[str, object]:
        operations = sorted(operation for operation, fields in _TEXT_ARGUMENTS.items() if field in fields)
        return {"type": ["string", "null"], "description": (
            meaning + " Required only for " + ", ".join(operations)
            + "; must be null for every other operation. When required, use a non-null string "
            + "with at least one non-whitespace character and no null characters, at most "
            + str(256 if field == "name" else 4096) + " UTF-8 bytes."
        )}

    return {
        "type": "function", "name": NATIVE_BUSINESS_TOOL_NAME,
        "description": (
            "Use real Jiuwen services. For project questions or analysis use work.start; "
            "a prior running task does not turn a new question into task.adjust. "
            "Use task.create only when the user delegates background artifact work; "
            "adjust/cancel only on the user's explicit request for the exact target. "
            "Use IDs, revisions and context_id returned by the server; never guess. "
            "Call context.get when missing or stale. Unused fields must be null. "
            "A spoken interruption alone stops speech, not accepted work. "
            "Accepted/running is not completed; report only actual service receipts."
        ),
        "parameters": {"type": "object", "additionalProperties": False,
            "required": ["request_text", "action"], "properties": {
                "request_text": {"type": "string", "description": (
                    "The user's current request, preserving intent and requirements. This does not replace "
                    "the required action.instruction or action.adjustment for the selected operation."
                )},
                "action": {"type": "object", "additionalProperties": False,
                    "required": sorted(_FIELDS), "properties": {
                        "operation": {"type": "string", "enum": sorted(NATIVE_BUSINESS_OPERATIONS)},
                        "context_id": {"type": ["string", "null"], "description": (
                            "Copy the exact context_id from the latest server context. Required for all operations "
                            "except context.get, where null is allowed when no context is available."
                        )},
                        "target_id": {"type": ["string", "null"], "description": (
                            "Must be null for " + ", ".join(sorted(_COLLECTION))
                            + ". For every other operation copy the exact task_id or work_id from server facts. "
                            "Never put a context ID, title, file name or guessed ID here."
                        )},
                        "input_id": {"type": "string", "description": (
                            "Required for workflow.reply or agent.reply: copy the exact pending input ID from workflow.get or agent.pending. "
                            "Omit this field for all other operations. Never guess or answer a different pending input."
                        )},
                        "source_task_id": {"type": "string", "description": "Required only for agent.reply: exact source_task_id from agent.pending. Omit otherwise."},
                        "pending_token": {"type": "string", "description": "Required only for agent.reply: exact pending_token from agent.pending. Omit otherwise."},
                        "fingerprint": {"type": ["string", "null"], "description": "Required only for team.start or workflow.start: exact Team fingerprint from team.list, or null for an explicitly requested cold start. Omit otherwise."},
                        "epoch": {"type": "string", "description": "Required only for core_workflow.get/start/resume: the exact current epoch from core_workflow.list. Omit otherwise."},
                        "capability_id": {"type": "string", "description": "Required only for core_workflow.start: the exact registered capability ID from core_workflow.list. Omit otherwise."},
                        "inputs": {"type": "object", "additionalProperties": True,
                                   "description": "Required only for core_workflow.start: complete registered-schema inputs, at most 8192 UTF-8 bytes. Omit otherwise."},
                        "answers": {"type": ["object", "array"],
                                    "description": "Required for core_workflow.resume as an object of exact pending node answers, or agent.reply as the observed question's user answer array. At most 8192 UTF-8 bytes. Omit otherwise."},
                        "expected_revision": {"type": ["integer", "null"], "description": (
                            "Copy the target's observed revision_number (Task) or revision (work). Required only for "
                            + ", ".join(sorted(_REVISION_REQUIRED))
                            + "; must be null for every other operation."
                        )},
                        "name": text_argument("name", "A concise name for the new background Task."),
                        "instruction": text_argument("instruction", (
                            "The complete work requirements, retaining relevant user constraints. For work.start, "
                            "put the analysis requirements here; target_id, expected_revision, name and adjustment must be null."
                        )),
                        "adjustment": text_argument("adjustment", (
                            "The user's requested change to the existing Task. For task.adjust, put the change here, "
                            "copy the server task_id into target_id and its integer revision_number into expected_revision, "
                            "and set name and instruction to null."
                        )),
                    }},
            }},
    }
