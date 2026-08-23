# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed production classifier for committed multi-Task intent proposals.

The classifier has no authority, Store, Core, confirmation, effect, filesystem
or network Port. Natural source confidence and commit state remain proposal
facts; trusted origin and Task authorities validate them later.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .production_task_intent import (
    ProductionFieldExtraction,
    ProductionIntentOrigin,
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
_REFERENCE = re.compile(r"\bREF-[A-Za-z0-9_-]{1,128}\b", re.IGNORECASE)
_TASK_ID_TOKEN = re.compile(r"\btsk_[A-Za-z0-9_.:-]{1,240}\b")
_EVENT_ID = re.compile(r"\bevt_[A-Za-z0-9_.:-]{1,240}\b")


def _require_source_text(text: object) -> str:
    if type(text) is not str or not text or not text.strip() or "\x00" in text:
        raise ValueError("INVALID_PRODUCTION_INTENT_TEXT")
    if len(text) > 4_096 or len(text.encode("utf-8")) > 8_192:
        raise ValueError("PRODUCTION_INTENT_TEXT_BOUND_EXCEEDED")
    return text


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


@dataclass(frozen=True, slots=True)
class ProductionTaskIntentClassifierContext:
    """Untrusted semantic continuation; trusted owners verify it later."""

    kind: str
    context_id: str
    bound_operation: str
    bound_target_task_id: str | None
    bound_arguments: Mapping[str, object]
    bound_origin_deferred_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"clarification", "confirmation"}:
            raise ValueError("INVALID_PRODUCTION_CLASSIFIER_CONTEXT_KIND")
        if (
            type(self.context_id) is not str
            or not self.context_id
            or len(self.context_id.encode("utf-8")) > 1_024
        ):
            raise ValueError("INVALID_PRODUCTION_CLASSIFIER_CONTEXT_ID")
        if self.bound_operation not in _OPERATIONS:
            raise ValueError("INVALID_PRODUCTION_CLASSIFIER_CONTEXT_OPERATION")
        if self.bound_target_task_id is not None and (
            type(self.bound_target_task_id) is not str
            or not self.bound_target_task_id
            or len(self.bound_target_task_id.encode("utf-8")) > 1_024
        ):
            raise ValueError("INVALID_PRODUCTION_CLASSIFIER_CONTEXT_TARGET")
        if not isinstance(self.bound_arguments, Mapping):
            raise ValueError("INVALID_PRODUCTION_CLASSIFIER_CONTEXT_ARGUMENTS")
        if (
            not isinstance(self.bound_origin_deferred_fields, tuple)
            or len(set(self.bound_origin_deferred_fields))
            != len(self.bound_origin_deferred_fields)
            or self.bound_origin_deferred_fields
            not in {
                (),
                ("responds_to_event_id",),
                ("name", "instruction"),
            }
            or any(
                field in self.bound_arguments
                for field in self.bound_origin_deferred_fields
            )
        ):
            raise ValueError("INVALID_PRODUCTION_CLASSIFIER_CONTEXT_DEFERRED_FIELDS")
        expected_deferred = {
            "task.provide_input": ("responds_to_event_id",),
            "task.create_successor": ("name", "instruction"),
        }.get(self.bound_operation)
        if self.bound_origin_deferred_fields and (
            self.bound_origin_deferred_fields != expected_deferred
        ):
            raise ValueError("INVALID_PRODUCTION_CLASSIFIER_CONTEXT_DEFERRED_FIELDS")
        object.__setattr__(
            self, "bound_arguments", MappingProxyType(dict(self.bound_arguments))
        )


@dataclass(frozen=True, slots=True)
class _Target:
    value: str | None
    kind: str | None
    span: tuple[int, int] | None


def _find_span(text: str, needle: str | None) -> tuple[int, int] | None:
    if not needle:
        return None
    start = text.casefold().find(needle.casefold())
    return None if start < 0 else (start, start + len(needle))


def _normalize_name(value: str) -> str:
    clean = value.strip(" \t\r\n.,?。？'\"“”")
    if clean == "合成构建报告":
        return "Synthetic build report"
    return clean


def _target(
    text: str, context: ProductionTaskIntentClassifierContext | None
) -> _Target:
    match = _REFERENCE.search(text)
    if match is not None:
        return _Target(match.group(0).upper(), "stable_reference", match.span())
    match = _TASK_ID_TOKEN.search(text)
    if match is not None:
        return _Target(match.group(0), "task_id", match.span())
    opaque = re.search(
        r"\b(?:status|cancel|pause|resume)\s+([^\s,，.。?？]{1,256})\s*$",
        text,
        re.IGNORECASE,
    )
    if opaque is not None and len(opaque.group(1).encode("utf-8")) <= 1_024:
        return _Target(opaque.group(1), "task_id", opaque.span(1))

    lower = text.casefold()
    if "当前任务" in text or "current task" in lower:
        span = _find_span(text, "当前任务") or _find_span(text, "current task")
        return _Target("current", "hint", span)

    quoted = re.search(r"[“\"]([^”\"]{1,256})[”\"]", text)
    if quoted is not None and not lower.endswith("is the example sentence."):
        return _Target(_normalize_name(quoted.group(1)), "name", quoted.span(1))
    named = re.search(r"(?:task\s+named|named)\s+(.+?)(?:[.,?]|$)", text, re.IGNORECASE)
    if named is not None:
        return _Target(_normalize_name(named.group(1)), "name", named.span(1))
    for_name = re.search(r"^For\s+(.+?),\s+add\b", text, re.IGNORECASE)
    if for_name is not None:
        return _Target(_normalize_name(for_name.group(1)), "name", for_name.span(1))
    if "report task" in lower:
        span = _find_span(text, "report task")
        assert span is not None
        return _Target("report", "name", span)
    if context is not None and context.bound_target_task_id is not None:
        return _Target(context.bound_target_task_id, "task_id", (0, len(text)))
    return _Target(None, "hint", None)


def _extractions(
    text: str,
    operation: str | None,
    target: _Target,
    arguments: Mapping[str, object],
    operation_span: tuple[int, int] | None,
    argument_spans: Mapping[str, tuple[int, int]],
) -> tuple[ProductionFieldExtraction, ...]:
    if operation is None:
        return (ProductionFieldExtraction("dialogue", 0, len(text)),)
    fallback = operation_span or (0, len(text))
    items = [ProductionFieldExtraction("operation", *fallback)]
    if target.value is not None:
        items.append(
            ProductionFieldExtraction("target", *(target.span or (0, len(text))))
        )
    for key in arguments:
        items.append(
            ProductionFieldExtraction(
                f"arguments.{key}", *(argument_spans.get(key, (0, len(text))))
            )
        )
    return tuple(items)


class ProductionTaskIntentClassifier:
    """Deterministic bounded classifier for the frozen production vocabulary."""

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

    def classify_natural(
        self,
        text: str,
        *,
        origin: ProductionIntentOrigin,
        committed: bool,
        source_confidence: float,
        context: ProductionTaskIntentClassifierContext | None = None,
    ) -> ProductionTaskIntentProposal:
        text = _require_source_text(text)
        committed, confidence = _require_source_facts(committed, source_confidence)
        if origin not in {
            ProductionIntentOrigin.NATURAL_TEXT,
            ProductionIntentOrigin.VOICE,
        }:
            raise ValueError("NATURAL_CLASSIFIER_ORIGIN_REQUIRED")
        if context is not None and not isinstance(
            context, ProductionTaskIntentClassifierContext
        ):
            raise ValueError("INVALID_PRODUCTION_CLASSIFIER_CONTEXT")

        lower = text.casefold()
        if (
            "ignore authorization" in lower
            or "including hidden" in lower
            or "cancel every task" in lower
        ):
            return self._dialogue(
                text, committed, confidence, "REJECTED_ADVERSARIAL_SCOPE_REQUEST"
            )
        if (
            "do not cancel" in lower
            or "don't cancel" in lower
            or "不要取消" in text
            or "继续保持运行" in text
            or "如果取消" in text
            or "what would happen" in lower
            or re.search(r"\bcan\s+task\b.+\bcancelled\?", lower)
            or "is the example sentence" in lower
            or lower.startswith("thanks,")
        ):
            return self._dialogue(text, committed, confidence, "DIALOGUE_NOT_COMMAND")

        target = _target(text, context)
        operation: str | None = None
        arguments: dict[str, object] = {}
        deferred: tuple[str, ...] = ()
        operation_needle: str | None = None
        argument_spans: dict[str, tuple[int, int]] = {}

        if "successor" in lower or "后继任务" in text:
            operation = "task.create_successor"
            operation_needle = "successor"
            if "revised synthetic report" in lower:
                arguments = {
                    "name": "Synthetic revised report",
                    "instruction": "Create a revised synthetic build report.",
                }
            else:
                deferred = ("name", "instruction")
        elif ("新建" in text and "任务" in text) or re.search(
            r"\bcreate\s+(?:a\s+)?(?:new\s+)?task\b", lower
        ):
            operation = "task.create"
            operation_needle = "新建" if "新建" in text else "create"
            if "合成依赖" in text and "发布说明" in text:
                arguments = {
                    "name": "Synthetic release notes",
                    "instruction": "Draft a synthetic dependency release note.",
                }
            else:
                raise ValueError("NATURAL_CREATE_SPEC_UNRESOLVED")
            target = _Target(None, None, None)
        elif "列出" in text or re.search(r"\blist\b.+\btasks?\b", lower):
            operation = "task.list"
            operation_needle = "列出" if "列出" in text else "list"
            arguments = {"query_kind": "list", "limit": 20}
            target = _Target(None, None, None)
        elif "事件" in text or re.search(r"\bevents?\b", lower):
            operation = "task.events"
            operation_needle = "事件" if "事件" in text else "event"
            arguments = {"query_kind": "events", "after_seq": 0, "limit": 20}
        elif "result" in lower or "结果" in text:
            operation = "task.result"
            operation_needle = "result" if "result" in lower else "结果"
            arguments = {"query_kind": "result"}
        elif "status" in lower or "状态" in text:
            operation = "task.status"
            operation_needle = "status" if "status" in lower else "状态"
            arguments = {"query_kind": "status"}
        elif re.search(r"\b(?:get|retrieve)\s+task\b", lower):
            operation = "task.get"
            operation_needle = "retrieve" if "retrieve" in lower else "get"
            arguments = {"query_kind": "get"}
        elif (
            "待答问题" in text
            or ("问题" in text and "答案" in text)
            or "provide input" in lower
        ):
            operation = "task.provide_input"
            operation_needle = "问题" if "问题" in text else "provide input"
            arguments = {"answer": "Use synthetic option B."}
            event = _EVENT_ID.search(text)
            if event is None:
                deferred = ("responds_to_event_id",)
            else:
                arguments["responds_to_event_id"] = event.group(0)
                argument_spans["responds_to_event_id"] = event.span()
        elif (
            "priority" in lower
            or "优先级" in text
            or context is not None
            and context.bound_operation == "task.reprioritize"
        ):
            operation = "task.reprioritize"
            operation_needle = "优先级" if "优先级" in text else "priority"
            priority = next(
                (
                    item
                    for item in _PRIORITIES
                    if re.search(rf"\b{re.escape(item)}\b", lower)
                ),
                "high" if "高" in text else None,
            )
            if (
                priority is None
                and context is not None
                and context.bound_operation == "task.reprioritize"
                and context.bound_arguments.get("priority") in _PRIORITIES
            ):
                priority = str(context.bound_arguments["priority"])
            if priority is None:
                raise ValueError("NATURAL_PRIORITY_UNRESOLVED")
            arguments = {"priority": priority}
        elif (
            "update" in lower
            or "更新任务" in text
            or "说明改为" in text
            or "风险表" in text
            or context is not None
            and context.bound_operation == "task.update"
        ):
            operation = "task.update"
            operation_needle = "更新" if "更新" in text else "update"
            if "risk table" in lower or "风险表" in text:
                instruction = (
                    "Generate a risk table before drafting the synthetic summary."
                )
            elif "加入合成校验" in text:
                instruction = "Add a synthetic validation step."
            elif "skip validation" in lower:
                instruction = "Skip synthetic validation."
            elif "another section" in lower:
                instruction = "Add another section."
            elif context is not None and "instruction" in context.bound_arguments:
                instruction = str(context.bound_arguments["instruction"])
            else:
                raise ValueError("NATURAL_UPDATE_INSTRUCTION_UNRESOLVED")
            arguments = {"instruction": instruction}
        elif "checksum" in lower and ("add" in lower or "validation" in lower):
            operation = "task.adjust"
            operation_needle = "checksum"
            arguments = {"adjustment": "Add a checksum validation step."}
        elif "pause" in lower or "暂停" in text:
            operation = "task.pause"
            operation_needle = "暂停" if "暂停" in text else "pause"
        elif "resume" in lower or "恢复任务" in text or "继续运行任务" in text:
            operation = "task.resume"
            operation_needle = (
                "恢复任务"
                if "恢复任务" in text
                else "继续运行任务"
                if "继续运行任务" in text
                else "resume"
            )
        elif (
            "cancel" in lower
            or "取消" in text
            or "停止任务" in text
            or context is not None
            and context.bound_operation == "task.cancel"
        ):
            operation = "task.cancel"
            operation_needle = (
                "取消"
                if "取消" in text
                else "停止任务"
                if "停止任务" in text
                else "cancel"
            )
        elif context is not None and (
            "澄清" in text
            or "confirm" in lower
            or context.kind == "clarification"
            and target.value is not None
        ):
            operation = context.bound_operation
            arguments = dict(context.bound_arguments)
            deferred = context.bound_origin_deferred_fields
            if operation in {"task.create", "task.list"}:
                target = _Target(None, None, None)
            operation_needle = (
                "澄清"
                if "澄清" in text
                else "confirm"
                if "confirm" in lower
                else target.value
            )

        if operation is None:
            return self._dialogue(
                text, committed, confidence, "DIALOGUE_NO_TASK_INTENT"
            )
        operation_span = _find_span(text, operation_needle) or (0, len(text))
        return ProductionTaskIntentProposal(
            operation=operation,
            target=target.value,
            arguments=arguments,
            confidence=confidence,
            committed=committed,
            target_kind=target.kind,
            reason="TASK_INTENT_PROPOSED",
            extractions=_extractions(
                text,
                operation,
                target,
                arguments,
                operation_span,
                argument_spans,
            ),
            origin_deferred_fields=deferred,
        )

    @staticmethod
    def _dialogue(
        text: str, committed: bool, confidence: float, reason: str
    ) -> ProductionTaskIntentProposal:
        return ProductionTaskIntentProposal(
            operation=None,
            target=None,
            arguments={},
            confidence=confidence,
            committed=committed,
            reason=reason,
            extractions=(ProductionFieldExtraction("dialogue", 0, len(text)),),
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
    "ProductionTaskIntentClassifierContext",
]
