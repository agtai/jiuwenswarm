# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed structured controls. Natural language uses task_semantics only."""

from __future__ import annotations

import json
from collections.abc import Mapping

from .production_task_intent import (
    ProductionTaskIntentProposal,
)
from .voice_task_policy import (
    FORMAL_TASK_MUTATION_OPERATIONS,
    FORMAL_TASK_QUERY_OPERATIONS,
)

_OPERATIONS = FORMAL_TASK_QUERY_OPERATIONS | FORMAL_TASK_MUTATION_OPERATIONS
_STRUCTURED_FIELDS = frozenset({"operation", "target", "arguments"})
_ARGUMENT_FIELDS = {
    "task.create": frozenset({"name", "instruction"}),
    "task.get": frozenset({"query_kind"}),
    "task.list": frozenset({"query_kind", "limit"}),
    "task.status": frozenset({"query_kind"}),
    "task.events": frozenset({"query_kind", "after_seq", "limit"}),
    "task.result": frozenset({"query_kind"}),
    "task.update": frozenset({"instruction"}),
    "task.adjust": frozenset({"adjustment"}),
    "task.provide_input": frozenset({"answer", "responds_to_event_id"}),
    "task.pause": frozenset(),
    "task.resume": frozenset(),
    "task.reprioritize": frozenset({"priority"}),
    "task.cancel": frozenset(),
    "task.create_successor": frozenset({"name", "instruction"}),
}
_QUERY_KIND = {
    "task.get": "get",
    "task.list": "list",
    "task.status": "status",
    "task.events": "events",
    "task.result": "result",
}
_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})
def _require_source_facts(committed: object, confidence: object) -> tuple[bool, float]:
    if type(committed) is not bool:
        raise ValueError("INVALID_PRODUCTION_INTENT_COMMIT_STATE")
    if type(confidence) not in {int, float} or not 0 <= confidence <= 1:
        raise ValueError("INVALID_PRODUCTION_INTENT_CONFIDENCE")
    return committed, float(confidence)


def _strict_json_object(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if type(value) is not str or len(value.encode("utf-8")) > 8_192:
        raise ValueError("INVALID_STRUCTURED_TASK_INTENT")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in items:
            if key in result:
                raise ValueError("DUPLICATE_STRUCTURED_TASK_INTENT_FIELD")
            result[key] = item
        return result

    try:
        parsed = json.loads(value, object_pairs_hook=pairs)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError("INVALID_STRUCTURED_TASK_INTENT") from error
    if not isinstance(parsed, dict):
        raise ValueError("INVALID_STRUCTURED_TASK_INTENT")
    return parsed


class ProductionTaskIntentClassifier:
    """Parse explicit structured controls; never infer natural-language intent."""

    def parse_structured(
        self,
        value: object,
        *,
        committed: bool,
        source_confidence: float,
    ) -> ProductionTaskIntentProposal:
        committed, confidence = _require_source_facts(committed, source_confidence)
        payload = _strict_json_object(value)
        if set(payload) != _STRUCTURED_FIELDS:
            raise ValueError("STRUCTURED_TASK_INTENT_FIELDS_MISMATCH")
        operation = payload["operation"]
        target = payload["target"]
        arguments = payload["arguments"]
        if type(operation) is not str or operation not in _OPERATIONS:
            raise ValueError("STRUCTURED_OPERATION_UNSUPPORTED")
        if target is not None and (
            type(target) is not str
            or not target
            or "\x00" in target
            or len(target) > 256
            or len(target.encode("utf-8")) > 1_024
        ):
            raise ValueError("INVALID_STRUCTURED_TARGET")
        if not isinstance(arguments, Mapping):
            raise ValueError("INVALID_STRUCTURED_ARGUMENTS")
        clean_arguments = dict(arguments)
        if set(clean_arguments) != _ARGUMENT_FIELDS[operation]:
            raise ValueError("STRUCTURED_ARGUMENT_SCHEMA_MISMATCH")
        self._validate_structured_arguments(operation, clean_arguments)
        if operation in {"task.create", "task.list"}:
            if target is not None:
                raise ValueError("STRUCTURED_COLLECTION_TARGET_FORBIDDEN")
        elif target is None:
            raise ValueError("STRUCTURED_TARGET_REQUIRED")
        return ProductionTaskIntentProposal(
            operation=operation,
            target=target,
            arguments=clean_arguments,
            confidence=confidence,
            committed=committed,
            target_kind=None if target is None else "task_id",
            reason="TASK_INTENT_PROPOSED",
        )

    @staticmethod
    def _validate_structured_arguments(
        operation: str, arguments: Mapping[str, object]
    ) -> None:
        for key, value in arguments.items():
            if type(key) is not str:
                raise ValueError("INVALID_STRUCTURED_ARGUMENT_KEY")
            if type(value) is str:
                if not value or not value.strip() or "\x00" in value:
                    raise ValueError("INVALID_STRUCTURED_ARGUMENT_VALUE")
                if len(value.encode("utf-8")) > 4_096:
                    raise ValueError("STRUCTURED_ARGUMENT_BOUND_EXCEEDED")
            elif type(value) is int:
                if not -(2**53 - 1) <= value <= 2**53 - 1:
                    raise ValueError("STRUCTURED_ARGUMENT_BOUND_EXCEEDED")
            else:
                raise ValueError("INVALID_STRUCTURED_ARGUMENT_VALUE")
        if (
            operation in _QUERY_KIND
            and arguments["query_kind"] != _QUERY_KIND[operation]
        ):
            raise ValueError("STRUCTURED_QUERY_KIND_MISMATCH")
        if operation in {"task.list", "task.events"}:
            limit = arguments["limit"]
            if type(limit) is not int or not 1 <= limit <= 500:
                raise ValueError("STRUCTURED_QUERY_LIMIT_INVALID")
        if operation == "task.events":
            after_seq = arguments["after_seq"]
            if type(after_seq) is not int or after_seq < -1:
                raise ValueError("STRUCTURED_EVENT_CURSOR_INVALID")
        if (
            operation == "task.reprioritize"
            and arguments["priority"] not in _PRIORITIES
        ):
            raise ValueError("STRUCTURED_PRIORITY_INVALID")


__all__ = [
    "ProductionTaskIntentClassifier",
]
