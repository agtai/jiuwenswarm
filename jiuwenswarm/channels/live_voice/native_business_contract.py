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
from jiuwenswarm.common.schema.native_interaction_contract import NativeDelegateProposal
from jiuwenswarm.server.runtime.formal_tasks.production_task_intent import ProductionTaskIntentProposal


from jiuwenswarm.server.runtime.work.business_actions import (
    NATIVE_BUSINESS_CONTRACT_VERSION,
    NATIVE_BUSINESS_TOOL_NAME,
    NATIVE_BUSINESS_OPERATIONS,
    _FIELDS,
    _COLLECTION,
    _REVISION_REQUIRED,
    _TEXT_ARGUMENTS,
    NativeBusinessViolation,
    _text,
    NativeBusinessAction
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
