"""Validate P3-6 preparation fixtures without resolving or executing intent."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = "live-voice.p3-6-intent-corpus.v1"
_HARD_MAX_FILE_BYTES = 1_048_576
_MANIFEST_FIELDS = frozenset(
    {
        "content_policy",
        "corpus_version",
        "credit",
        "dependencies",
        "description",
        "files",
        "limits",
        "preparation_scope",
        "production_evidence",
        "required_partitions",
        "scenario_matrix",
        "schema_version",
        "zero_effects",
    }
)
_LIMIT_FIELDS = frozenset(
    {
        "max_case_bytes",
        "max_cases",
        "max_fields_per_object",
        "max_file_bytes",
        "max_input_bytes",
        "max_input_chars",
        "max_list_items",
        "max_manifest_bytes",
        "max_nesting_depth",
        "max_string_chars",
        "max_task_facts",
        "max_zero_effects",
    }
)
_PARTITION_AXES = frozenset(
    {
        "classifications",
        "confirmations",
        "forms",
        "languages",
        "operations",
        "origins",
        "outcomes",
        "safety",
        "scenario_dimensions",
        "targets",
    }
)
_FROZEN_REQUIRED_PARTITIONS = {
    "classifications": ["task_intent", "clarification", "dialogue", "rejected"],
    "confirmations": ["required", "not_required", "not_applicable"],
    "forms": [
        "voice_committed_text",
        "natural_text",
        "structured_equivalent",
        "paraphrase",
        "word_order_variation",
        "chinese_update_without_ba_jiang",
    ],
    "languages": ["en", "zh-CN"],
    "operations": [
        "task.create",
        "task.get",
        "task.list",
        "task.status",
        "task.events",
        "task.result",
        "task.update",
        "task.adjust",
        "task.provide_input",
        "task.pause",
        "task.resume",
        "task.reprioritize",
        "task.cancel",
        "task.create_successor",
    ],
    "origins": ["voice", "natural_text", "structured"],
    "outcomes": [
        "proposed",
        "clarification",
        "dialogue",
        "rejected",
        "unsupported",
        "conflict",
    ],
    "safety": [
        "negation",
        "correction",
        "hypothetical",
        "question",
        "ordinary_dialogue",
        "partial_interim",
        "low_confidence",
        "quoted_task_text",
        "adversarial_instruction",
        "missing_target",
        "ambiguous_target",
        "changed_task_set",
        "confirmation_changed_operation",
        "confirmation_changed_target",
        "confirmation_changed_arguments",
    ],
    "scenario_dimensions": ["P", "N", "B", "S", "T", "C", "R", "I", "F", "K"],
    "targets": [
        "collection",
        "explicit_task_id",
        "stable_user_reference",
        "unique_authorized_name",
        "duplicate_name",
        "zero_candidate",
        "multiple_candidates",
        "stale_target",
        "foreign_scope_project",
        "terminal_predecessor",
        "two_visible_tasks",
        "current_recent_hint_only",
    ],
}
_FROZEN_ZERO_EFFECTS = [
    "agent_calls",
    "tool_calls",
    "task_writes",
    "attempt_writes",
    "command_writes",
    "event_writes",
    "result_writes",
    "executor_calls",
    "scheduler_calls",
    "file_writes",
    "network_calls",
    "audio_tts_calls",
    "history_writes",
    "presentation_writes",
    "other_scope_writes",
]
_FROZEN_PREPARATION_SCOPE = {
    "exclusions": [
        "no_production_resolver",
        "no_task_core_or_store_call",
        "no_product_or_wire_composition",
        "no_agent_tool_task_executor_or_tts_call",
        "no_p3_6_completion_credit",
    ],
    "owned_surfaces": [
        "tests/fixtures/live_voice_p3_6_intent_corpus_v1",
        "tests/support/live_voice/p3_6_intent_corpus.py",
        "tests/unit_tests/live_voice/test_p3_6_intent_corpus.py",
    ],
}
_CASE_REQUIRED_FIELDS = frozenset(
    {
        "case_id",
        "committed",
        "confidence",
        "expected",
        "input_text",
        "language",
        "origin",
        "parity_group",
        "partitions",
        "schema_version",
        "structured_input",
        "task_facts",
    }
)
_CASE_FIELDS = _CASE_REQUIRED_FIELDS | {"interaction_context", "target_snapshot"}
_INTERACTION_CONTEXT_FIELDS = frozenset(
    {
        "bound_arguments",
        "bound_candidate_task_ids",
        "bound_operation",
        "bound_target_task_id",
        "context_id",
        "kind",
    }
)
_TARGET_SNAPSHOT_FIELDS = frozenset({"observed_snapshot_version", "observed_task_id"})
_STRUCTURED_FIELDS = frozenset({"arguments", "operation", "target"})
_ARGUMENT_FIELDS = frozenset(
    {
        "adjustment",
        "after_seq",
        "answer",
        "instruction",
        "limit",
        "name",
        "priority",
        "query_kind",
        "responds_to_event_id",
    }
)
_OPERATION_ARGUMENT_FIELDS = {
    "none": frozenset(),
    "task.adjust": frozenset({"adjustment"}),
    "task.cancel": frozenset(),
    "task.create": frozenset({"instruction", "name"}),
    "task.create_successor": frozenset({"instruction", "name"}),
    "task.events": frozenset({"after_seq", "limit", "query_kind"}),
    "task.get": frozenset({"query_kind"}),
    "task.list": frozenset({"limit", "query_kind"}),
    "task.pause": frozenset(),
    "task.provide_input": frozenset({"answer", "responds_to_event_id"}),
    "task.reprioritize": frozenset({"priority"}),
    "task.result": frozenset({"query_kind"}),
    "task.resume": frozenset(),
    "task.status": frozenset({"query_kind"}),
    "task.update": frozenset({"instruction"}),
}
_OPERATION_REQUIRED_ARGUMENT_FIELDS = {
    operation: fields for operation, fields in _OPERATION_ARGUMENT_FIELDS.items()
}
_QUERY_KIND_BY_OPERATION = {
    "task.events": "events",
    "task.get": "get",
    "task.list": "list",
    "task.result": "result",
    "task.status": "status",
}
_PRIORITIES = frozenset({"high", "low", "normal", "urgent"})
_TASK_FACT_FIELDS = frozenset(
    {
        "authorized",
        "current_hint",
        "current_attempt_state",
        "decision_required_event_current",
        "decision_required_event_id",
        "decision_required_event_kind",
        "name",
        "predecessor_task_id",
        "recent_hint",
        "scope_id",
        "dispatch_outbox_state",
        "snapshot_version",
        "state",
        "task_id",
        "terminal",
        "user_reference",
    }
)
_PARTITION_FIELDS = frozenset(
    {"forms", "operation", "safety", "scenario_dimensions", "target"}
)
_EXPECTED_FIELDS = frozenset(
    {
        "arguments",
        "canonical_operation",
        "classification",
        "confirmation",
        "policy_outcome",
        "target_requirement",
        "target_task_id",
        "zero_effects",
    }
)
_TARGET_REQUIREMENTS = frozenset(
    {"collection", "exact_blocking_event", "exact_task", "none", "terminal_predecessor"}
)
_TASK_STATES = frozenset(
    {
        "accepted",
        "running",
        "blocked",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
        "unknown",
    }
)
_DISPATCH_OUTBOX_STATES = frozenset(
    {"claimed", "delivered", "not_applicable", "unclaimed"}
)
_TERMINAL_STATES = frozenset(
    {"completed", "failed", "cancelled", "interrupted", "unknown"}
)
_MATERIAL_OPERATIONS = frozenset(
    {
        "task.adjust",
        "task.cancel",
        "task.create",
        "task.create_successor",
        "task.update",
    }
)
_CONFIRMATION_CHANGE_PARTITIONS = frozenset(
    {
        "confirmation_changed_arguments",
        "confirmation_changed_operation",
        "confirmation_changed_target",
    }
)
_SENSITIVE_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
)
_SAFE_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{2,95}")
_TASK_ID = re.compile(r"tsk_fixture_[a-z0-9_]{3,64}")
_TASK_REF = re.compile(r"REF-[A-Z0-9-]{2,32}")
_SCOPE_ID = re.compile(r"scope_fixture_[a-z0-9_]{3,64}")
_EVENT_ID = re.compile(r"evt_fixture_[a-z0-9_]{3,64}")


class CorpusValidationError(ValueError):
    """Content-free corpus failure suitable for CI output."""

    def __init__(self, reason: str, *, case_id: str | None = None) -> None:
        self.reason = reason
        self.case_id = case_id
        suffix = "" if case_id is None else f" case_id={case_id}"
        super().__init__(f"{reason}:{suffix} corpus validation failed")


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IntentCorpus:
    manifest: dict[str, Any]
    cases: tuple[dict[str, Any], ...]

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(case["case_id"] for case in self.cases)

    def partition_counts(self) -> dict[str, Counter[str]]:
        counts = {axis: Counter() for axis in _PARTITION_AXES}
        for case in self.cases:
            partitions = case["partitions"]
            expected = case["expected"]
            if partitions["operation"] != "none":
                counts["operations"][partitions["operation"]] += 1
            counts["targets"][partitions["target"]] += 1
            counts["languages"][case["language"]] += 1
            counts["origins"][case["origin"]] += 1
            counts["outcomes"][expected["policy_outcome"]] += 1
            counts["classifications"][expected["classification"]] += 1
            counts["confirmations"][expected["confirmation"]] += 1
            counts["forms"].update(partitions["forms"])
            counts["safety"].update(partitions["safety"])
            counts["scenario_dimensions"].update(partitions["scenario_dimensions"])
        return counts


def _pairs_to_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _parse_json(raw: bytes, reason: str, *, case_id: str | None = None) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_to_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except _DuplicateJsonKey as error:
        raise CorpusValidationError("DUPLICATE_JSON_KEY", case_id=case_id) from error
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise CorpusValidationError(reason, case_id=case_id) from error


def _require_closed(
    value: object,
    fields: frozenset[str],
    reason: str,
    *,
    case_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise CorpusValidationError(reason, case_id=case_id)
    return value


def _require_unique_strings(
    value: object,
    reason: str,
    *,
    case_id: str | None = None,
) -> list[str]:
    if (
        not isinstance(value, list)
        or any(type(item) is not str or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise CorpusValidationError(reason, case_id=case_id)
    return value


def _check_shape(
    value: object,
    limits: Mapping[str, int],
    *,
    depth: int = 0,
    case_id: str | None = None,
) -> None:
    if depth > limits["max_nesting_depth"]:
        raise CorpusValidationError("NESTING_DEPTH_EXCEEDED", case_id=case_id)
    if isinstance(value, dict):
        if len(value) > limits["max_fields_per_object"]:
            raise CorpusValidationError("OBJECT_FIELD_COUNT_EXCEEDED", case_id=case_id)
        for key, item in value.items():
            if type(key) is not str or not key or len(key) > 128:
                raise CorpusValidationError("INVALID_OBJECT_FIELD", case_id=case_id)
            _check_shape(item, limits, depth=depth + 1, case_id=case_id)
    elif isinstance(value, list):
        if len(value) > limits["max_list_items"]:
            raise CorpusValidationError("LIST_ITEM_COUNT_EXCEEDED", case_id=case_id)
        for item in value:
            _check_shape(item, limits, depth=depth + 1, case_id=case_id)
    elif isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise CorpusValidationError(
                "INVALID_UTF8_STRING", case_id=case_id
            ) from error
        if "\x00" in value or len(value) > limits["max_string_chars"]:
            raise CorpusValidationError("STRING_BOUND_EXCEEDED", case_id=case_id)
    elif value is not None and type(value) not in {bool, int, float}:
        raise CorpusValidationError("UNSUPPORTED_JSON_VALUE", case_id=case_id)


def _contains_sensitive_content(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_sensitive_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_sensitive_content(item) for item in value)
    return isinstance(value, str) and any(
        pattern.search(value) for pattern in _SENSITIVE_PATTERNS
    )


def _require_arguments(value: object, reason: str, *, case_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CorpusValidationError(reason, case_id=case_id)
    if set(value) - _ARGUMENT_FIELDS:
        raise CorpusValidationError(
            reason.replace("INVALID_", "").replace(
                "ARGUMENTS", "ARGUMENT_UNKNOWN_FIELDS"
            ),
            case_id=case_id,
        )
    return value


def _validate_operation_arguments(
    arguments: dict[str, Any],
    operation: str,
    *,
    label: str,
    require_complete: bool,
    case_id: str,
) -> None:
    allowed = _OPERATION_ARGUMENT_FIELDS[operation]
    if set(arguments) - allowed:
        raise CorpusValidationError(f"{label}_ARGUMENT_UNKNOWN_FIELDS", case_id=case_id)
    if require_complete and (
        _OPERATION_REQUIRED_ARGUMENT_FIELDS[operation] - set(arguments)
    ):
        raise CorpusValidationError(f"MISSING_{label}_ARGUMENT", case_id=case_id)
    for key, value in arguments.items():
        if key in {
            "adjustment",
            "answer",
            "instruction",
            "name",
            "priority",
            "query_kind",
        } and (type(value) is not str or not value.strip()):
            raise CorpusValidationError(
                f"INVALID_{label}_ARGUMENT_VALUE", case_id=case_id
            )
        if key == "after_seq" and (
            type(value) is not int or isinstance(value, bool) or value < 0
        ):
            raise CorpusValidationError(
                f"INVALID_{label}_ARGUMENT_VALUE", case_id=case_id
            )
        if key == "limit" and (
            type(value) is not int or isinstance(value, bool) or not 1 <= value <= 100
        ):
            raise CorpusValidationError(
                f"INVALID_{label}_ARGUMENT_VALUE", case_id=case_id
            )
        if key == "responds_to_event_id" and (
            type(value) is not str or _EVENT_ID.fullmatch(value) is None
        ):
            raise CorpusValidationError(
                f"INVALID_{label}_ARGUMENT_VALUE", case_id=case_id
            )
        if key == "priority" and value not in _PRIORITIES:
            raise CorpusValidationError(
                f"INVALID_{label}_ARGUMENT_VALUE", case_id=case_id
            )
        if key == "query_kind" and value != _QUERY_KIND_BY_OPERATION.get(operation):
            raise CorpusValidationError(
                f"INVALID_{label}_ARGUMENT_VALUE", case_id=case_id
            )


def _validate_manifest(manifest: object, raw_size: int) -> dict[str, Any]:
    manifest = _require_closed(manifest, _MANIFEST_FIELDS, "MANIFEST_UNKNOWN_FIELDS")
    limits = _require_closed(manifest["limits"], _LIMIT_FIELDS, "LIMITS_UNKNOWN_FIELDS")
    if any(type(value) is not int or value <= 0 for value in limits.values()):
        raise CorpusValidationError("INVALID_CORPUS_LIMIT")
    if (
        limits["max_file_bytes"] > _HARD_MAX_FILE_BYTES
        or limits["max_manifest_bytes"] > 65_536
        or limits["max_cases"] > 512
        or limits["max_task_facts"] > limits["max_list_items"]
        or limits["max_zero_effects"] > limits["max_list_items"]
        or raw_size > limits["max_manifest_bytes"]
    ):
        raise CorpusValidationError("INVALID_CORPUS_LIMIT")
    _check_shape(manifest, limits)
    if _contains_sensitive_content(manifest):
        raise CorpusValidationError("SENSITIVE_CONTENT_REJECTED")
    if (
        manifest["schema_version"] != _SCHEMA_VERSION
        or manifest["corpus_version"] != "1.0.0"
        or manifest["credit"] != "preparation_only"
        or manifest["production_evidence"] is not False
        or type(manifest["description"]) is not str
    ):
        raise CorpusValidationError("INVALID_MANIFEST_IDENTITY")
    _require_closed(manifest["files"], frozenset({"cases"}), "FILES_UNKNOWN_FIELDS")
    if manifest["files"]["cases"] != "cases.jsonl":
        raise CorpusValidationError("INVALID_CASE_FILE")
    dependencies = _require_closed(
        manifest["dependencies"],
        frozenset({"required_before_production"}),
        "DEPENDENCIES_UNKNOWN_FIELDS",
    )
    if set(
        _require_unique_strings(
            dependencies["required_before_production"], "INVALID_DEPENDENCIES"
        )
    ) != {
        "accepted_p3_2_command_interface",
        "accepted_p3_5a_result_event_interface",
    }:
        raise CorpusValidationError("INVALID_DEPENDENCIES")
    content_policy = _require_closed(
        manifest["content_policy"],
        frozenset(
            {
                "no_audio",
                "no_credentials",
                "no_private_text",
                "no_real_projects",
                "no_real_task_results",
                "synthetic_only",
            }
        ),
        "CONTENT_POLICY_UNKNOWN_FIELDS",
    )
    if not all(value is True for value in content_policy.values()):
        raise CorpusValidationError("INVALID_CONTENT_POLICY")
    scope = _require_closed(
        manifest["preparation_scope"],
        frozenset({"exclusions", "intended_behavior", "owned_surfaces"}),
        "PREPARATION_SCOPE_UNKNOWN_FIELDS",
    )
    _require_unique_strings(scope["exclusions"], "INVALID_PREPARATION_SCOPE")
    _require_unique_strings(scope["owned_surfaces"], "INVALID_PREPARATION_SCOPE")
    if any(
        scope[field] != values for field, values in _FROZEN_PREPARATION_SCOPE.items()
    ):
        raise CorpusValidationError("FROZEN_PREPARATION_SCOPE_MISMATCH")
    if type(scope["intended_behavior"]) is not str or not scope["intended_behavior"]:
        raise CorpusValidationError("INVALID_PREPARATION_SCOPE")
    partitions = _require_closed(
        manifest["required_partitions"],
        _PARTITION_AXES,
        "PARTITIONS_UNKNOWN_FIELDS",
    )
    for axis, values in partitions.items():
        _require_unique_strings(values, f"INVALID_{axis.upper()}_PARTITIONS")
    if partitions != _FROZEN_REQUIRED_PARTITIONS:
        raise CorpusValidationError("FROZEN_REQUIRED_PARTITIONS_MISMATCH")
    zero_effects = _require_unique_strings(
        manifest["zero_effects"], "INVALID_ZERO_EFFECTS"
    )
    if len(zero_effects) > limits["max_zero_effects"]:
        raise CorpusValidationError("ZERO_EFFECT_COUNT_EXCEEDED")
    if zero_effects != _FROZEN_ZERO_EFFECTS:
        raise CorpusValidationError("FROZEN_ZERO_EFFECTS_MISMATCH")
    scenario_matrix = manifest["scenario_matrix"]
    if not isinstance(scenario_matrix, dict) or set(scenario_matrix) != set(
        "PNBSTRCIFKX"
    ):
        raise CorpusValidationError("INVALID_SCENARIO_MATRIX")
    for entry in scenario_matrix.values():
        entry = _require_closed(
            entry,
            frozenset({"applicable", "evidence"}),
            "SCENARIO_MATRIX_UNKNOWN_FIELDS",
        )
        if type(entry["applicable"]) is not bool or type(entry["evidence"]) is not str:
            raise CorpusValidationError("INVALID_SCENARIO_MATRIX")
    if scenario_matrix["X"] != {
        "applicable": False,
        "evidence": "preparation_corpus_is_not_a_real_product_path",
    }:
        raise CorpusValidationError("INVALID_SCENARIO_MATRIX")
    return manifest


def _validate_task_fact(
    fact: object, limits: Mapping[str, int], *, case_id: str
) -> dict[str, Any]:
    fact = _require_closed(
        fact, _TASK_FACT_FIELDS, "TASK_FACT_UNKNOWN_FIELDS", case_id=case_id
    )
    _check_shape(fact, limits, case_id=case_id)
    if (
        type(fact["task_id"]) is not str
        or _TASK_ID.fullmatch(fact["task_id"]) is None
        or type(fact["user_reference"]) is not str
        or _TASK_REF.fullmatch(fact["user_reference"]) is None
        or type(fact["scope_id"]) is not str
        or _SCOPE_ID.fullmatch(fact["scope_id"]) is None
        or type(fact["name"]) is not str
        or not fact["name"].strip()
        or len(fact["name"]) > 64
        or type(fact["state"]) is not str
        or fact["state"] not in _TASK_STATES
        or type(fact["current_attempt_state"]) is not str
        or fact["current_attempt_state"] not in _TASK_STATES
        or type(fact["dispatch_outbox_state"]) is not str
        or fact["dispatch_outbox_state"] not in _DISPATCH_OUTBOX_STATES
        or type(fact["snapshot_version"]) is not int
        or isinstance(fact["snapshot_version"], bool)
        or fact["snapshot_version"] <= 0
        or type(fact["authorized"]) is not bool
        or type(fact["terminal"]) is not bool
        or type(fact["current_hint"]) is not bool
        or type(fact["recent_hint"]) is not bool
        or fact["terminal"] != (fact["state"] in _TERMINAL_STATES)
    ):
        raise CorpusValidationError("INVALID_TASK_FACT", case_id=case_id)
    if fact["predecessor_task_id"] is not None and (
        type(fact["predecessor_task_id"]) is not str
        or _TASK_ID.fullmatch(fact["predecessor_task_id"]) is None
    ):
        raise CorpusValidationError("INVALID_TASK_FACT", case_id=case_id)
    event_id = fact["decision_required_event_id"]
    event_kind = fact["decision_required_event_kind"]
    event_current = fact["decision_required_event_current"]
    if event_id is None and (event_kind is not None or event_current is not False):
        raise CorpusValidationError("INVALID_TASK_FACT", case_id=case_id)
    if event_id is not None and (
        type(event_id) is not str
        or _EVENT_ID.fullmatch(event_id) is None
        or event_kind != "task.decision_required"
        or type(event_current) is not bool
    ):
        raise CorpusValidationError("INVALID_TASK_FACT", case_id=case_id)
    return fact


def _validate_case(case: object, manifest: Mapping[str, Any]) -> dict[str, Any]:
    provisional_id = case.get("case_id") if isinstance(case, dict) else None
    case_id = (
        provisional_id
        if type(provisional_id) is str
        and _SAFE_IDENTIFIER.fullmatch(provisional_id) is not None
        and not _contains_sensitive_content(provisional_id)
        else None
    )
    if (
        not isinstance(case, dict)
        or set(case) - _CASE_FIELDS
        or _CASE_REQUIRED_FIELDS - set(case)
    ):
        raise CorpusValidationError("CASE_UNKNOWN_FIELDS", case_id=case_id)
    if case_id is None or _SAFE_IDENTIFIER.fullmatch(case_id) is None:
        raise CorpusValidationError("INVALID_CASE_ID")
    limits = manifest["limits"]
    if type(case["input_text"]) is str:
        try:
            input_bytes = case["input_text"].encode("utf-8")
        except UnicodeEncodeError as error:
            raise CorpusValidationError(
                "INVALID_UTF8_STRING", case_id=case_id
            ) from error
        if (
            len(case["input_text"]) > limits["max_input_chars"]
            or len(input_bytes) > limits["max_input_bytes"]
        ):
            raise CorpusValidationError("INPUT_TEXT_BOUND_EXCEEDED", case_id=case_id)
    _check_shape(case, limits, case_id=case_id)
    required = manifest["required_partitions"]
    if (
        case["schema_version"] != manifest["schema_version"]
        or case["language"] not in required["languages"]
        or case["origin"] not in required["origins"]
        or type(case["committed"]) is not bool
        or type(case["confidence"]) not in {int, float}
        or isinstance(case["confidence"], bool)
        or not 0.0 <= case["confidence"] <= 1.0
        or type(case["input_text"]) is not str
        or not case["input_text"]
    ):
        raise CorpusValidationError("INVALID_CASE_IDENTITY", case_id=case_id)
    if _contains_sensitive_content(case):
        raise CorpusValidationError("SENSITIVE_CONTENT_REJECTED", case_id=case_id)

    structured = case["structured_input"]
    if case["origin"] == "structured":
        structured = _require_closed(
            structured,
            _STRUCTURED_FIELDS,
            "STRUCTURED_INPUT_UNKNOWN_FIELDS",
            case_id=case_id,
        )
        _require_arguments(
            structured["arguments"], "INVALID_STRUCTURED_ARGUMENTS", case_id=case_id
        )
        structured_text = _parse_json(
            case["input_text"].encode("utf-8"),
            "INVALID_STRUCTURED_TEXT",
            case_id=case_id,
        )
        if structured_text != structured:
            raise CorpusValidationError("STRUCTURED_TEXT_MISMATCH", case_id=case_id)
    elif structured is not None:
        raise CorpusValidationError("INVALID_STRUCTURED_INPUT", case_id=case_id)

    facts = case["task_facts"]
    if not isinstance(facts, list) or not facts:
        raise CorpusValidationError("TASK_FACTS_REQUIRED", case_id=case_id)
    if len(facts) > limits["max_task_facts"]:
        raise CorpusValidationError("TASK_FACT_COUNT_EXCEEDED", case_id=case_id)
    validated_facts = [
        _validate_task_fact(fact, limits, case_id=case_id) for fact in facts
    ]
    if len({fact["task_id"] for fact in validated_facts}) != len(validated_facts):
        raise CorpusValidationError("DUPLICATE_TASK_FACT", case_id=case_id)
    if len({fact["user_reference"] for fact in validated_facts}) != len(
        validated_facts
    ):
        raise CorpusValidationError("DUPLICATE_TASK_REFERENCE", case_id=case_id)
    if not all(fact["authorized"] is True for fact in validated_facts):
        raise CorpusValidationError("UNAUTHORIZED_VISIBLE_TASK_FACT", case_id=case_id)
    if len({fact["scope_id"] for fact in validated_facts}) != 1:
        raise CorpusValidationError("CROSS_SCOPE_VISIBLE_TASK_FACT", case_id=case_id)

    partitions = _require_closed(
        case["partitions"],
        _PARTITION_FIELDS,
        "CASE_PARTITIONS_UNKNOWN_FIELDS",
        case_id=case_id,
    )
    operation = partitions["operation"]
    if operation != "none" and operation not in required["operations"]:
        raise CorpusValidationError("UNKNOWN_OPERATION_PARTITION", case_id=case_id)
    if partitions["target"] not in required["targets"]:
        raise CorpusValidationError("UNKNOWN_TARGET_PARTITION", case_id=case_id)
    for field, axis in (
        ("forms", "forms"),
        ("safety", "safety"),
        ("scenario_dimensions", "scenario_dimensions"),
    ):
        values = _require_unique_strings(
            partitions[field], f"INVALID_{field.upper()}", case_id=case_id
        )
        if set(values) - set(required[axis]):
            raise CorpusValidationError(f"UNKNOWN_{field.upper()}", case_id=case_id)
    origin_form = {
        "voice": "voice_committed_text",
        "natural_text": "natural_text",
        "structured": "structured_equivalent",
    }[case["origin"]]
    if case["committed"] and origin_form not in partitions["forms"]:
        raise CorpusValidationError("ORIGIN_FORM_MISMATCH", case_id=case_id)

    expected = _require_closed(
        case["expected"],
        _EXPECTED_FIELDS,
        "EXPECTED_UNKNOWN_FIELDS",
        case_id=case_id,
    )
    arguments = _require_arguments(
        expected["arguments"], "INVALID_EXPECTED_ARGUMENTS", case_id=case_id
    )
    _validate_operation_arguments(
        arguments,
        operation,
        label="EXPECTED",
        require_complete=expected["classification"] == "task_intent",
        case_id=case_id,
    )
    if (
        expected["classification"] not in required["classifications"]
        or expected["policy_outcome"] not in required["outcomes"]
        or expected["confirmation"] not in required["confirmations"]
        or expected["target_requirement"] not in _TARGET_REQUIREMENTS
        or expected["canonical_operation"]
        != (None if operation == "none" else operation)
        or (
            expected["target_task_id"] is not None
            and (
                type(expected["target_task_id"]) is not str
                or _TASK_ID.fullmatch(expected["target_task_id"]) is None
            )
        )
    ):
        raise CorpusValidationError("INVALID_EXPECTED_OUTCOME", case_id=case_id)
    if expected["zero_effects"] != manifest["zero_effects"]:
        raise CorpusValidationError("INCOMPLETE_ZERO_EFFECTS", case_id=case_id)
    visible_by_id = {fact["task_id"]: fact for fact in validated_facts}
    if (
        expected["target_task_id"] is not None
        and expected["target_task_id"] not in visible_by_id
    ):
        raise CorpusValidationError("EXPECTED_TARGET_NOT_VISIBLE", case_id=case_id)
    safety = set(partitions["safety"])
    if safety and expected["policy_outcome"] == "proposed":
        raise CorpusValidationError("UNSAFE_NEGATIVE_OUTCOME", case_id=case_id)
    if "partial_interim" in safety and (
        case["committed"] is not False or expected["classification"] != "rejected"
    ):
        raise CorpusValidationError("INVALID_PARTIAL_EXPECTATION", case_id=case_id)
    if "low_confidence" in safety and case["confidence"] > 0.5:
        raise CorpusValidationError("INVALID_LOW_CONFIDENCE_CASE", case_id=case_id)
    if safety.intersection(_CONFIRMATION_CHANGE_PARTITIONS) and (
        expected["classification"] != "rejected"
        or expected["policy_outcome"] != "conflict"
    ):
        raise CorpusValidationError("INVALID_CONFIRMATION_CONFLICT", case_id=case_id)

    interaction_context = case.get("interaction_context")
    context_safety = safety.intersection(
        _CONFIRMATION_CHANGE_PARTITIONS | {"changed_task_set"}
    )
    if context_safety:
        interaction_context = _require_closed(
            interaction_context,
            _INTERACTION_CONTEXT_FIELDS,
            "INTERACTION_CONTEXT_UNKNOWN_FIELDS",
            case_id=case_id,
        )
        if (
            interaction_context["kind"] not in {"clarification", "confirmation"}
            or type(interaction_context["context_id"]) is not str
            or _SAFE_IDENTIFIER.fullmatch(interaction_context["context_id"]) is None
            or interaction_context["bound_operation"] not in required["operations"]
        ):
            raise CorpusValidationError("INVALID_INTERACTION_CONTEXT", case_id=case_id)
        bound_target = interaction_context["bound_target_task_id"]
        if bound_target is not None and (
            type(bound_target) is not str or _TASK_ID.fullmatch(bound_target) is None
        ):
            raise CorpusValidationError("INVALID_INTERACTION_CONTEXT", case_id=case_id)
        bound_arguments = _require_arguments(
            interaction_context["bound_arguments"],
            "INVALID_INTERACTION_CONTEXT_ARGUMENTS",
            case_id=case_id,
        )
        _validate_operation_arguments(
            bound_arguments,
            interaction_context["bound_operation"],
            label="INTERACTION_CONTEXT",
            require_complete=True,
            case_id=case_id,
        )
        bound_candidates = _require_unique_strings(
            interaction_context["bound_candidate_task_ids"],
            "INVALID_INTERACTION_CONTEXT_CANDIDATES",
            case_id=case_id,
        )
        if any(_TASK_ID.fullmatch(candidate) is None for candidate in bound_candidates):
            raise CorpusValidationError(
                "INVALID_INTERACTION_CONTEXT_CANDIDATES", case_id=case_id
            )
        if "changed_task_set" in safety:
            if interaction_context["kind"] != "clarification" or set(
                bound_candidates
            ) == {fact["task_id"] for fact in validated_facts}:
                raise CorpusValidationError(
                    "UNCHANGED_CLARIFICATION_TASK_SET", case_id=case_id
                )
        else:
            if interaction_context["kind"] != "confirmation":
                raise CorpusValidationError(
                    "INVALID_CONFIRMATION_CONTEXT", case_id=case_id
                )
            if "confirmation_changed_operation" in safety and (
                interaction_context["bound_operation"] == operation
            ):
                raise CorpusValidationError(
                    "UNCHANGED_CONFIRMATION_OPERATION", case_id=case_id
                )
            if "confirmation_changed_target" in safety and (
                interaction_context["bound_target_task_id"]
                == expected["target_task_id"]
            ):
                raise CorpusValidationError(
                    "UNCHANGED_CONFIRMATION_TARGET", case_id=case_id
                )
            if "confirmation_changed_arguments" in safety and (
                bound_arguments == expected["arguments"]
            ):
                raise CorpusValidationError(
                    "UNCHANGED_CONFIRMATION_ARGUMENTS", case_id=case_id
                )
    elif "interaction_context" in case:
        raise CorpusValidationError("UNEXPECTED_INTERACTION_CONTEXT", case_id=case_id)

    target_snapshot = case.get("target_snapshot")
    if partitions["target"] == "stale_target":
        target_snapshot = _require_closed(
            target_snapshot,
            _TARGET_SNAPSHOT_FIELDS,
            "TARGET_SNAPSHOT_UNKNOWN_FIELDS",
            case_id=case_id,
        )
        observed_task_id = target_snapshot["observed_task_id"]
        observed_version = target_snapshot["observed_snapshot_version"]
        current_fact = visible_by_id.get(observed_task_id)
        if (
            type(observed_task_id) is not str
            or _TASK_ID.fullmatch(observed_task_id) is None
            or type(observed_version) is not int
            or isinstance(observed_version, bool)
            or observed_version <= 0
            or current_fact is None
            or expected["target_task_id"] != observed_task_id
            or current_fact["snapshot_version"] <= observed_version
            or expected["policy_outcome"] != "conflict"
        ):
            raise CorpusValidationError("INVALID_STALE_TARGET", case_id=case_id)
    elif "target_snapshot" in case:
        raise CorpusValidationError("UNEXPECTED_TARGET_SNAPSHOT", case_id=case_id)

    if partitions["target"] == "multiple_candidates" and (
        "ambiguous_target" not in safety
        or len(validated_facts) < 2
        or expected["classification"] != "clarification"
        or expected["target_task_id"] is not None
    ):
        raise CorpusValidationError("INVALID_MULTIPLE_CANDIDATES", case_id=case_id)
    if partitions["target"] == "two_visible_tasks" and (
        len(validated_facts) < 2 or expected["target_task_id"] is None
    ):
        raise CorpusValidationError("INVALID_SIMULTANEOUS_TASKS", case_id=case_id)
    if partitions["target"] == "unique_authorized_name":
        target = visible_by_id.get(expected["target_task_id"])
        if (
            target is None
            or sum(
                fact["name"].casefold() == target["name"].casefold()
                for fact in validated_facts
            )
            != 1
        ):
            raise CorpusValidationError("INVALID_UNIQUE_NAME_TARGET", case_id=case_id)
    if partitions["target"] == "duplicate_name" and (
        expected["target_task_id"] is not None
        or expected["classification"] != "clarification"
        or not any(
            sum(
                other["name"].casefold() == fact["name"].casefold()
                for other in validated_facts
            )
            > 1
            for fact in validated_facts
        )
    ):
        raise CorpusValidationError("INVALID_DUPLICATE_NAME_TARGET", case_id=case_id)
    if partitions["target"] == "current_recent_hint_only" and (
        expected["target_task_id"] is not None
        or expected["policy_outcome"] == "proposed"
        or not any(
            fact["current_hint"] or fact["recent_hint"] for fact in validated_facts
        )
    ):
        raise CorpusValidationError("INVALID_HINT_ONLY_TARGET", case_id=case_id)
    if operation == "task.provide_input":
        target = visible_by_id.get(expected["target_task_id"])
        event_id = arguments.get("responds_to_event_id")
        if (
            expected["target_requirement"] != "exact_blocking_event"
            or target is None
            or target["decision_required_event_id"] != event_id
            or target["decision_required_event_kind"] != "task.decision_required"
            or target["decision_required_event_current"] is not True
        ):
            raise CorpusValidationError(
                "INVALID_DECISION_REQUIRED_TARGET", case_id=case_id
            )
    if operation == "task.create_successor":
        predecessor = visible_by_id.get(expected["target_task_id"])
        eligible_states = {"completed", "failed", "cancelled", "interrupted"}
        if (
            predecessor is None
            or expected["target_requirement"] != "terminal_predecessor"
            or predecessor["terminal"] is not True
            or (
                expected["policy_outcome"] == "proposed"
                and predecessor["state"] not in eligible_states
            )
            or (
                predecessor["state"] == "unknown"
                and expected["policy_outcome"] != "conflict"
            )
        ):
            raise CorpusValidationError(
                "INVALID_SUCCESSOR_PREDECESSOR", case_id=case_id
            )
    target = visible_by_id.get(expected["target_task_id"])
    if (
        operation in {"task.pause", "task.reprioritize", "task.resume"}
        and expected["classification"] == "task_intent"
        and (
            target is None
            or expected["policy_outcome"]
            != ("conflict" if target["terminal"] else "unsupported")
        )
    ):
        raise CorpusValidationError("INVALID_CONTROL_STATE_OUTCOME", case_id=case_id)
    if operation == "task.update" and expected["classification"] == "task_intent":
        if expected["policy_outcome"] == "proposed" and (
            target is None
            or target["state"] != "accepted"
            or target["current_attempt_state"] != "accepted"
            or target["dispatch_outbox_state"] != "unclaimed"
        ):
            raise CorpusValidationError("INVALID_UPDATE_STATE_OUTCOME", case_id=case_id)
        if (
            target is not None
            and target["terminal"]
            and (expected["policy_outcome"] != "conflict")
        ):
            raise CorpusValidationError("INVALID_UPDATE_STATE_OUTCOME", case_id=case_id)
    if (
        operation == "task.adjust"
        and expected["policy_outcome"] == "proposed"
        and (
            target is None
            or target["state"] != "running"
            or target["current_attempt_state"] != "running"
        )
    ):
        raise CorpusValidationError("INVALID_ADJUST_STATE_OUTCOME", case_id=case_id)
    if (
        operation in _MATERIAL_OPERATIONS
        and expected["policy_outcome"] == "proposed"
        and expected["confirmation"] != "required"
    ):
        raise CorpusValidationError("MATERIAL_CONFIRMATION_REQUIRED", case_id=case_id)
    if case["origin"] == "structured" and (
        structured["operation"] != operation
        or structured["target"] != expected["target_task_id"]
        or structured["arguments"] != expected["arguments"]
    ):
        raise CorpusValidationError("STRUCTURED_OUTCOME_MISMATCH", case_id=case_id)
    parity_group = case["parity_group"]
    if parity_group is not None and (
        type(parity_group) is not str
        or _SAFE_IDENTIFIER.fullmatch(parity_group) is None
    ):
        raise CorpusValidationError("INVALID_PARITY_GROUP", case_id=case_id)
    return case


def _validate_coverage(corpus: IntentCorpus) -> None:
    counts = corpus.partition_counts()
    for axis, required in corpus.manifest["required_partitions"].items():
        if set(required) - set(counts[axis]):
            raise CorpusValidationError(f"MISSING_{axis.upper()}_PARTITION")


def _validate_parity(corpus: IntentCorpus) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in corpus.cases:
        if case["parity_group"] is not None:
            groups[case["parity_group"]].append(case)
    if not groups:
        raise CorpusValidationError("PARITY_GROUP_REQUIRED")
    for group_cases in groups.values():
        origins = [case["origin"] for case in group_cases]
        if len(group_cases) != 3 or set(origins) != {
            "voice",
            "natural_text",
            "structured",
        }:
            raise CorpusValidationError("INCOMPLETE_PARITY_GROUP")
        expected = group_cases[0]["expected"]
        if any(case["expected"] != expected for case in group_cases[1:]):
            raise CorpusValidationError("PARITY_OUTCOME_MISMATCH")
        if len({case["language"] for case in group_cases}) != 1 or not all(
            case["committed"] is True for case in group_cases
        ):
            raise CorpusValidationError("PARITY_LANGUAGE_MISMATCH")
    parity_operations = {
        group_cases[0]["expected"]["canonical_operation"]
        for group_cases in groups.values()
    }
    if parity_operations != set(corpus.manifest["required_partitions"]["operations"]):
        raise CorpusValidationError("MISSING_OPERATION_PARITY")


def load_corpus(corpus_dir: Path) -> IntentCorpus:
    """Load one canonical corpus or fail without echoing its input text."""

    root = Path(corpus_dir)
    manifest_path = root / "manifest.json"
    try:
        manifest_raw = manifest_path.read_bytes()
    except OSError as error:
        raise CorpusValidationError("MANIFEST_UNAVAILABLE") from error
    if len(manifest_raw) > _HARD_MAX_FILE_BYTES:
        raise CorpusValidationError("MANIFEST_FILE_BOUND_EXCEEDED")
    manifest = _validate_manifest(
        _parse_json(manifest_raw, "INVALID_MANIFEST_JSON"), len(manifest_raw)
    )
    cases_path = root / manifest["files"]["cases"]
    try:
        cases_raw = cases_path.read_bytes()
    except OSError as error:
        raise CorpusValidationError("CASE_FILE_UNAVAILABLE") from error
    if not cases_raw or len(cases_raw) > manifest["limits"]["max_file_bytes"]:
        raise CorpusValidationError("CASE_FILE_BOUND_EXCEEDED")
    if b"\r" in cases_raw or not cases_raw.endswith(b"\n"):
        raise CorpusValidationError("NONCANONICAL_JSONL")
    raw_lines = cases_raw.splitlines()
    if not raw_lines or any(not line for line in raw_lines):
        raise CorpusValidationError("INVALID_JSONL_RECORD")
    if len(raw_lines) > manifest["limits"]["max_cases"]:
        raise CorpusValidationError("CASE_COUNT_EXCEEDED")

    cases: list[dict[str, Any]] = []
    for raw_line in raw_lines:
        if len(raw_line) > manifest["limits"]["max_case_bytes"]:
            raise CorpusValidationError("CASE_RECORD_BOUND_EXCEEDED")
        parsed = _parse_json(raw_line, "INVALID_CASE_JSON")
        case = _validate_case(parsed, manifest)
        canonical = json.dumps(
            case, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        if canonical != raw_line:
            raise CorpusValidationError("NONCANONICAL_JSONL", case_id=case["case_id"])
        cases.append(case)

    case_ids = [case["case_id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise CorpusValidationError("DUPLICATE_CASE_ID")
    if case_ids != sorted(case_ids):
        raise CorpusValidationError("NONDETERMINISTIC_CASE_ORDER")
    corpus = IntentCorpus(manifest=manifest, cases=tuple(cases))
    _validate_coverage(corpus)
    _validate_parity(corpus)
    return corpus


__all__ = [
    "CorpusValidationError",
    "IntentCorpus",
    "load_corpus",
]
