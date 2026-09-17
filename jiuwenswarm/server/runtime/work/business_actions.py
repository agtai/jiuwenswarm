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
from jiuwenswarm.server.runtime.formal_tasks.production_task_intent import ProductionTaskIntentProposal

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
        else:
            _text(self.target_id, maximum=1024, field="action.target_id")
            if len(self.target_id) > 256 or self.target_id.strip() != self.target_id:
                raise NativeBusinessViolation("NATIVE_BUSINESS_TARGET_INVALID", field="action.target_id",
                    expected="The exact server target ID, at most 256 characters, without surrounding whitespace")
        if self.operation in _REVISION_REQUIRED:
            if type(self.expected_revision) is not int or not 0 < self.expected_revision < 2**53:
                raise NativeBusinessViolation("NATIVE_BUSINESS_REVISION_REQUIRED", field="action.expected_revision",
                    expected="The target's observed server revision as a positive integer below 2**53, not a string")
        elif self.expected_revision is not None:
            raise NativeBusinessViolation("NATIVE_BUSINESS_REVISION_FORBIDDEN", field="action.expected_revision", expected="null")
        required = _TEXT_ARGUMENTS.get(self.operation, frozenset())
        for key in ("name", "instruction", "adjustment"):
            value = getattr(self, key)
            if key in required:
                _text(value, maximum=256 if key == "name" else 4096, field="action." + key)
            elif value is not None:
                raise NativeBusinessViolation("NATIVE_BUSINESS_UNUSED_ARGUMENT", field="action." + key, expected="null")

    @classmethod
    def from_dict(cls, value: object) -> NativeBusinessAction:
        if not isinstance(value, Mapping) or set(value) != _FIELDS:
            raise NativeBusinessViolation("NATIVE_BUSINESS_FIELDS_NOT_CLOSED", field="action",
                expected="Exactly these fields (unused values must be null): " + ", ".join(sorted(_FIELDS)))
        try:
            return cls(**value)
        except NativeBusinessViolation as exc:
            operation = value["operation"]
            if type(operation) is str and operation in NATIVE_BUSINESS_OPERATIONS:
                exc.operation = operation
            raise

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
