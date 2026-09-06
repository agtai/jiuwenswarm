# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Versioned Native business proposals, never execution or consent receipts.

The explicit capability extends the Native carrier without changing the legacy
delegate shape. Only the authenticated Runtime may admit a proposed operation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode, canonical_json_bytes
from .native_interaction_contract import NativeDelegateProposal
from .production_task_intent import ProductionTaskIntentProposal

NATIVE_BUSINESS_CONTRACT_VERSION = "live-voice.native-business.v1"
NATIVE_BUSINESS_TOOL_NAME = "jiuwen_business"
NATIVE_BUSINESS_OPERATIONS = frozenset({
    "context.get", "task.list", "task.status", "task.result", "task.create",
    "task.create_successor", "task.adjust", "task.cancel", "work.start",
    "work.list", "work.get", "work.update", "work.cancel",
})
_FIELDS = frozenset({"operation", "context_id", "target_id", "expected_revision",
                     "name", "instruction", "adjustment"})
_COLLECTION = frozenset({"context.get", "task.list", "task.create", "work.list", "work.start"})
_REVISION_REQUIRED = frozenset({"task.adjust", "task.cancel", "task.create_successor", "work.update", "work.cancel"})
_TEXT_ARGUMENTS = {
    "task.create": frozenset({"name", "instruction"}),
    "task.create_successor": frozenset({"name", "instruction"}),
    "task.adjust": frozenset({"adjustment"}),
    "work.start": frozenset({"instruction"}),
    "work.update": frozenset({"instruction"}),
}


class NativeBusinessViolation(ValueError):
    def __init__(self, reason: str = "NATIVE_BUSINESS_ARGUMENT_INVALID", *, code=ErrorCode.INVALID_ARGUMENT):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _text(value: object, *, maximum: int) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        raise NativeBusinessViolation()
    try:
        if len(value.encode("utf-8")) > maximum:
            raise NativeBusinessViolation()
    except UnicodeEncodeError:
        raise NativeBusinessViolation() from None
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

    def __post_init__(self):
        if type(self.operation) is not str or self.operation not in NATIVE_BUSINESS_OPERATIONS:
            raise NativeBusinessViolation("NATIVE_BUSINESS_OPERATION_UNSUPPORTED", code=ErrorCode.UNSUPPORTED)
        if self.operation != "context.get" or self.context_id is not None:
            if type(self.context_id) is not str or re.fullmatch(r"[0-9a-f]{64}", self.context_id) is None:
                raise NativeBusinessViolation("NATIVE_BUSINESS_CONTEXT_REQUIRED")
        if self.operation in _COLLECTION:
            if self.target_id is not None:
                raise NativeBusinessViolation("NATIVE_BUSINESS_TARGET_FORBIDDEN")
        else:
            _text(self.target_id, maximum=1024)
            if len(self.target_id) > 256 or self.target_id.strip() != self.target_id:
                raise NativeBusinessViolation("NATIVE_BUSINESS_TARGET_INVALID")
        if self.operation in _REVISION_REQUIRED:
            if type(self.expected_revision) is not int or not 0 < self.expected_revision < 2**53:
                raise NativeBusinessViolation("NATIVE_BUSINESS_REVISION_REQUIRED")
        elif self.expected_revision is not None:
            raise NativeBusinessViolation("NATIVE_BUSINESS_REVISION_FORBIDDEN")
        required = _TEXT_ARGUMENTS.get(self.operation, frozenset())
        for key in ("name", "instruction", "adjustment"):
            value = getattr(self, key)
            if key in required:
                _text(value, maximum=256 if key == "name" else 4096)
            elif value is not None:
                raise NativeBusinessViolation("NATIVE_BUSINESS_UNUSED_ARGUMENT")

    @classmethod
    def from_dict(cls, value: object) -> NativeBusinessAction:
        if not isinstance(value, Mapping) or set(value) != _FIELDS:
            raise NativeBusinessViolation("NATIVE_BUSINESS_FIELDS_NOT_CLOSED")
        return cls(**value)

    def to_dict(self) -> dict[str, object]:
        return {key: getattr(self, key) for key in sorted(_FIELDS)}

    @property
    def mutates(self) -> bool:
        return self.operation in {"task.create", "task.create_successor", "task.adjust", "task.cancel", "work.update", "work.cancel"}

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
    nullable_text = {"type": ["string", "null"]}
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
                "request_text": {"type": "string", "description": "The user's current request, preserving intent and requirements."},
                "action": {"type": "object", "additionalProperties": False,
                    "required": sorted(_FIELDS), "properties": {
                        "operation": {"type": "string", "enum": sorted(NATIVE_BUSINESS_OPERATIONS)},
                        "context_id": nullable_text, "target_id": nullable_text,
                        "expected_revision": {"type": ["integer", "null"]},
                        "name": nullable_text, "instruction": nullable_text, "adjustment": nullable_text,
                    }},
            }},
    }
