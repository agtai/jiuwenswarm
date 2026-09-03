# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Structured controls only; natural-language oracles live at task_semantics."""

import inspect
import json
from pathlib import Path

import pytest

from jiuwenswarm.server.live_voice import production_task_classifier as classifier_module
from jiuwenswarm.server.live_voice.production_task_classifier import ProductionTaskIntentClassifier

CORPUS = Path(__file__).resolve().parents[2] / "fixtures/live_voice_p3_6_intent_corpus_v1/cases.jsonl"


def test_all_existing_structured_operations_preserve_exact_arguments():
    cases = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line]
    structured = [case for case in cases if case["origin"] == "structured"]
    assert len(structured) == 14
    for case in structured:
        proposal = ProductionTaskIntentClassifier().parse_structured(
            case["structured_input"], committed=case["committed"],
            source_confidence=case["confidence"],
        )
        assert proposal.operation == case["expected"]["canonical_operation"], case["case_id"]
        assert dict(proposal.arguments) == case["expected"]["arguments"], case["case_id"]
        assert proposal.target == case["structured_input"]["target"]
        assert proposal.committed is case["committed"]


def test_structured_boundary_has_no_natural_fallback_or_fixture_lookup():
    assert not hasattr(ProductionTaskIntentClassifier, "classify_natural")
    assert not hasattr(classifier_module, "ProductionTaskIntentClassifierContext")
    source = inspect.getsource(classifier_module).casefold()
    for forbidden in ("case_id", "fixtures", "tests.", "expected[", "re.compile"):
        assert forbidden not in source

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

@pytest.mark.parametrize("payload", [
    '{"operation":"task.cancel","operation":"task.create","target":"task-1","arguments":{}}',
    "[]", "", "x" * 8193,
])
def test_structured_duplicate_and_non_object_input_has_no_proposal(payload):
    with pytest.raises(ValueError):
        ProductionTaskIntentClassifier().parse_structured(payload, committed=True, source_confidence=1.0)


@pytest.mark.parametrize("committed,confidence", [(None,1), (True,-1), (True,float("nan")), (True,True)])
def test_structured_invalid_source_facts_reject(committed,confidence):
    with pytest.raises(ValueError):
        ProductionTaskIntentClassifier().parse_structured(
            {"operation":"task.cancel","target":"task-1","arguments":{}},
            committed=committed, source_confidence=confidence,
        )
