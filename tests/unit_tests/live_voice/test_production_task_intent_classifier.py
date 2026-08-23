# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
import inspect
from collections import defaultdict
from pathlib import Path

import pytest

from jiuwenswarm.server.live_voice.production_task_classifier import (
    ProductionTaskIntentClassifier,
    ProductionTaskIntentClassifierContext,
)
import jiuwenswarm.server.live_voice.production_task_classifier as classifier_module
from jiuwenswarm.server.live_voice.production_task_intent import (
    ProductionIntentOrigin,
)

CORPUS = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "live_voice_p3_6_intent_corpus_v1"
    / "cases.jsonl"
)


def _cases() -> tuple[dict[str, object], ...]:
    return tuple(
        json.loads(line)
        for line in CORPUS.read_text(encoding="utf-8").splitlines()
        if line
    )


def _context(case: dict[str, object]) -> ProductionTaskIntentClassifierContext | None:
    value = case.get("interaction_context")
    if value is None:
        return None
    assert isinstance(value, dict)
    return ProductionTaskIntentClassifierContext(
        kind=value["kind"],
        context_id=value["context_id"],
        bound_operation=value["bound_operation"],
        bound_target_task_id=value["bound_target_task_id"],
        bound_arguments=value["bound_arguments"],
    )


def _classify(
    classifier: ProductionTaskIntentClassifier,
    case_without_expected: dict[str, object],
):
    origin = ProductionIntentOrigin(case_without_expected["origin"])
    common = {
        "committed": case_without_expected["committed"],
        "source_confidence": case_without_expected["confidence"],
    }
    if origin is ProductionIntentOrigin.STRUCTURED:
        return classifier.parse_structured(
            case_without_expected["structured_input"], **common
        )
    return classifier.classify_natural(
        case_without_expected["input_text"],
        origin=origin,
        context=_context(case_without_expected),
        **common,
    )


def test_raw_68_case_inputs_classify_without_expected_derived_proposals() -> None:
    classifier = ProductionTaskIntentClassifier()
    cases = _cases()
    assert len(cases) == 68

    for case in cases:
        raw = {key: value for key, value in case.items() if key != "expected"}
        proposal = _classify(classifier, raw)
        expected = case["expected"]
        assert isinstance(expected, dict)
        expected_operation = expected["canonical_operation"]

        if case["case_id"] == "s006-partial-cancel":
            assert proposal.committed is False
        elif case["case_id"] == "s007-low-confidence-cancel":
            assert proposal.operation == "task.cancel"
            assert proposal.confidence == 0.32
        elif expected_operation is None:
            assert proposal.operation is None, case["case_id"]
        else:
            assert proposal.operation == expected_operation, case["case_id"]

        if str(case["case_id"]).startswith("p"):
            expected_arguments = dict(expected["arguments"])
            actual_arguments = dict(proposal.arguments)
            if proposal.origin_deferred_fields:
                for field in proposal.origin_deferred_fields:
                    expected_arguments.pop(field)
            if (
                proposal.operation == "task.provide_input"
                and proposal.origin_deferred_fields
            ):
                assert proposal.origin_deferred_fields == ("responds_to_event_id",)
            assert actual_arguments == expected_arguments, case["case_id"]


def test_production_classifier_has_no_fixture_or_expected_lookup() -> None:
    source = inspect.getsource(classifier_module).casefold()
    assert "case_id" not in source
    assert "fixtures" not in source
    assert "tests." not in source
    assert "expected[" not in source


def test_natural_voice_and_structured_proposals_preserve_14_group_semantics() -> None:
    classifier = ProductionTaskIntentClassifier()
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for case in _cases():
        if case["parity_group"] is not None:
            groups[str(case["parity_group"])].append(case)
    assert len(groups) == 14

    for group, cases in groups.items():
        proposals = []
        for case in cases:
            raw = {key: value for key, value in case.items() if key != "expected"}
            proposals.append(_classify(classifier, raw))
        assert {proposal.operation for proposal in proposals} == {
            proposals[0].operation
        }, group
        deferred_fields = {
            field for proposal in proposals for field in proposal.origin_deferred_fields
        }
        normalized_arguments = []
        for proposal in proposals:
            arguments = dict(proposal.arguments)
            for field in deferred_fields:
                arguments[field] = "<authority-later>"
            if (
                proposal.operation == "task.provide_input"
                and "responds_to_event_id" in arguments
            ):
                arguments["responds_to_event_id"] = "<authority-later>"
            normalized_arguments.append(arguments)
        assert all(
            value == normalized_arguments[0] for value in normalized_arguments
        ), (
            group,
            normalized_arguments,
        )


def test_safety_forms_are_closed_before_any_task_authority_exists() -> None:
    classifier = ProductionTaskIntentClassifier()
    selected = {
        case["case_id"]: case
        for case in _cases()
        if case["case_id"]
        in {
            "s001-negated-cancel",
            "s002-corrected-cancel",
            "s003-hypothetical-cancel",
            "s004-question-cancel",
            "s005-ordinary-dialogue",
            "s006-partial-cancel",
            "s007-low-confidence-cancel",
            "s008-quoted-task-text",
            "s009-adversarial-all-tasks",
        }
    }
    assert len(selected) == 9
    for case_id, case in selected.items():
        raw = {key: value for key, value in case.items() if key != "expected"}
        proposal = _classify(classifier, raw)
        if case_id == "s006-partial-cancel":
            assert proposal.committed is False
        elif case_id == "s007-low-confidence-cancel":
            assert proposal.confidence < 0.80
        else:
            assert proposal.operation is None
            assert not proposal.reason.startswith("TASK_INTENT_PROPOSED")


@pytest.mark.parametrize(
    "payload",
    (
        {"operation": "task.cancel", "target": "task-1"},
        {
            "operation": "task.cancel",
            "target": "task-1",
            "arguments": {},
            "authorization": "browser-minted",
        },
        {
            "operation": "task.cancel",
            "target": "task-1",
            "arguments": {},
            "confirmation_id": "browser-minted",
        },
        {"operation": "task.cancel", "target": 7, "arguments": {}},
        {
            "operation": "task.cancel",
            "target": "task-1",
            "arguments": {"extra": True},
        },
        {"operation": "task.unknown", "target": "task-1", "arguments": {}},
    ),
)
def test_structured_parser_rejects_unknown_missing_and_authority_fields(
    payload: object,
) -> None:
    classifier = ProductionTaskIntentClassifier()
    with pytest.raises(ValueError):
        classifier.parse_structured(payload, committed=True, source_confidence=1.0)


def test_structured_parser_is_exact_and_does_not_infer_missing_decision_identity() -> (
    None
):
    classifier = ProductionTaskIntentClassifier()
    with pytest.raises(ValueError, match="STRUCTURED_ARGUMENT_SCHEMA_MISMATCH"):
        classifier.parse_structured(
            {
                "operation": "task.provide_input",
                "target": "task-1",
                "arguments": {"answer": "Use option B."},
            },
            committed=True,
            source_confidence=1.0,
        )


@pytest.mark.parametrize(
    "text,confidence",
    (
        ("", 1.0),
        ("   ", 1.0),
        ("x" * 4_097, 1.0),
        ("Cancel task task-1.", -0.01),
        ("Cancel task task-1.", 1.01),
    ),
)
def test_natural_classifier_enforces_closed_input_bounds(
    text: str, confidence: float
) -> None:
    classifier = ProductionTaskIntentClassifier()
    with pytest.raises(ValueError):
        classifier.classify_natural(
            text,
            origin=ProductionIntentOrigin.NATURAL_TEXT,
            committed=True,
            source_confidence=confidence,
        )


def test_natural_reprioritize_confirmation_inherits_exact_bound_priority() -> None:
    classifier = ProductionTaskIntentClassifier()
    proposal = classifier.classify_natural(
        "confirm task request confirmation-token",
        origin=ProductionIntentOrigin.NATURAL_TEXT,
        committed=True,
        source_confidence=1.0,
        context=ProductionTaskIntentClassifierContext(
            kind="confirmation",
            context_id="confirmation-token",
            bound_operation="task.reprioritize",
            bound_target_task_id="tsk_priority_target",
            bound_arguments={"priority": "urgent"},
        ),
    )

    assert proposal.operation == "task.reprioritize"
    assert proposal.target == "tsk_priority_target"
    assert proposal.target_kind == "task_id"
    assert dict(proposal.arguments) == {"priority": "urgent"}


def test_successor_clarification_preserves_deferred_spec_derivation() -> None:
    classifier = ProductionTaskIntentClassifier()
    proposal = classifier.classify_natural(
        "tsk_terminal_predecessor",
        origin=ProductionIntentOrigin.NATURAL_TEXT,
        committed=True,
        source_confidence=1.0,
        context=ProductionTaskIntentClassifierContext(
            kind="clarification",
            context_id="clarification-token",
            bound_operation="task.create_successor",
            bound_target_task_id=None,
            bound_arguments={},
            bound_origin_deferred_fields=("name", "instruction"),
        ),
    )

    assert proposal.operation == "task.create_successor"
    assert proposal.target == "tsk_terminal_predecessor"
    assert proposal.target_kind == "task_id"
    assert dict(proposal.arguments) == {}
    assert proposal.origin_deferred_fields == ("name", "instruction")


def test_natural_proposals_cover_every_semantic_field_with_source_spans() -> None:
    classifier = ProductionTaskIntentClassifier()
    for case in _cases():
        if case["origin"] == "structured":
            continue
        raw = {key: value for key, value in case.items() if key != "expected"}
        proposal = _classify(classifier, raw)
        expected_fields = {"dialogue"}
        if proposal.operation is not None:
            expected_fields = {"operation"}
            if proposal.target is not None:
                expected_fields.add("target")
            expected_fields.update(f"arguments.{key}" for key in proposal.arguments)
        assert {item.field_name for item in proposal.extractions} == expected_fields
        assert all(
            0 <= item.source_start < item.source_end <= len(case["input_text"])
            for item in proposal.extractions
        )
