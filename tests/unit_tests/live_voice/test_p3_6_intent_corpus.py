# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import pytest

from tests.support.live_voice import p3_6_intent_corpus as corpus_support

CORPUS_DIR = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "live_voice_p3_6_intent_corpus_v1"
)


def test_versioned_corpus_and_test_owned_evaluator_exist() -> None:
    assert (CORPUS_DIR / "manifest.json").is_file()
    assert (CORPUS_DIR / "cases.jsonl").is_file()
    assert (
        Path(__file__).resolve().parents[2]
        / "support"
        / "live_voice"
        / "p3_6_intent_corpus.py"
    ).is_file()


def _copy_corpus(tmp_path: Path) -> Path:
    destination = tmp_path / "corpus"
    shutil.copytree(CORPUS_DIR, destination)
    return destination


def _write_lf(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _rewrite_manifest(
    corpus_dir: Path, mutate: Callable[[dict[str, object]], None]
) -> None:
    path = corpus_dir / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    _write_lf(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _rewrite_case(
    corpus_dir: Path,
    select: Callable[[dict[str, object]], bool],
    mutate: Callable[[dict[str, object]], None],
) -> None:
    path = corpus_dir / "cases.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    selected_index = next(
        index for index, line in enumerate(lines) if select(json.loads(line))
    )
    selected = json.loads(lines[selected_index])
    mutate(selected)
    lines[selected_index] = json.dumps(
        selected, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    _write_lf(
        path,
        "\n".join(lines) + "\n",
    )


def test_loader_accepts_the_versioned_preparation_corpus() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)

    assert corpus.manifest["schema_version"] == ("live-voice.p3-6-intent-corpus.v1")
    assert corpus.manifest["corpus_version"] == "1.0.0"
    assert corpus.manifest["credit"] == "preparation_only"
    assert corpus.manifest["production_evidence"] is False
    assert len(corpus.cases) >= 60
    assert corpus.case_ids == tuple(sorted(corpus.case_ids))


def test_manifest_and_all_nested_case_objects_are_closed(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_manifest(corpus_dir, lambda manifest: manifest.update({"extra": True}))
    with pytest.raises(corpus_support.CorpusValidationError) as manifest_error:
        corpus_support.load_corpus(corpus_dir)
    assert manifest_error.value.reason == "MANIFEST_UNKNOWN_FIELDS"

    mutations: tuple[tuple[str, Callable[[dict[str, object]], None]], ...] = (
        ("CASE_UNKNOWN_FIELDS", lambda case: case.update({"extra": True})),
        (
            "EXPECTED_UNKNOWN_FIELDS",
            lambda case: case["expected"].update({"extra": True}),  # type: ignore[union-attr]
        ),
        (
            "TASK_FACT_UNKNOWN_FIELDS",
            lambda case: case["task_facts"][0].update({"extra": True}),  # type: ignore[index,union-attr]
        ),
        (
            "STRUCTURED_INPUT_UNKNOWN_FIELDS",
            lambda case: case["structured_input"].update({"extra": True}),  # type: ignore[union-attr]
        ),
    )
    for expected_reason, mutate in mutations:
        corpus_dir = _copy_corpus(tmp_path / expected_reason.lower())
        _rewrite_case(
            corpus_dir,
            (
                (lambda case: case["structured_input"] is not None)
                if expected_reason == "STRUCTURED_INPUT_UNKNOWN_FIELDS"
                else (lambda _case: True)
            ),
            mutate,
        )
        with pytest.raises(corpus_support.CorpusValidationError) as error:
            corpus_support.load_corpus(corpus_dir)
        assert error.value.reason == expected_reason

    optional_mutations: tuple[
        tuple[
            str,
            Callable[[dict[str, object]], bool],
            Callable[[dict[str, object]], None],
        ],
        ...,
    ] = (
        (
            "CASE_PARTITIONS_UNKNOWN_FIELDS",
            lambda _case: True,
            lambda case: case["partitions"].update({"extra": True}),
        ),
        (
            "INTERACTION_CONTEXT_UNKNOWN_FIELDS",
            lambda case: case.get("interaction_context") is not None,
            lambda case: case["interaction_context"].update({"extra": True}),
        ),
        (
            "TARGET_SNAPSHOT_UNKNOWN_FIELDS",
            lambda case: case.get("target_snapshot") is not None,
            lambda case: case["target_snapshot"].update({"extra": True}),
        ),
    )
    for expected_reason, select, mutate in optional_mutations:
        corpus_dir = _copy_corpus(tmp_path / f"optional-{expected_reason.lower()}")
        _rewrite_case(corpus_dir, select, mutate)
        with pytest.raises(corpus_support.CorpusValidationError) as error:
            corpus_support.load_corpus(corpus_dir)
        assert error.value.reason == expected_reason


def test_case_ids_are_unique_and_file_order_is_canonical(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path / "duplicate")
    path = corpus_dir / "cases.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    cases[1]["case_id"] = cases[0]["case_id"]
    _write_lf(
        path,
        "".join(
            json.dumps(case, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n"
            for case in cases
        ),
    )
    with pytest.raises(corpus_support.CorpusValidationError) as duplicate:
        corpus_support.load_corpus(corpus_dir)
    assert duplicate.value.reason == "DUPLICATE_CASE_ID"

    corpus_dir = _copy_corpus(tmp_path / "order")
    path = corpus_dir / "cases.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    _write_lf(path, "\n".join(lines) + "\n")
    with pytest.raises(corpus_support.CorpusValidationError) as order:
        corpus_support.load_corpus(corpus_dir)
    assert order.value.reason == "NONDETERMINISTIC_CASE_ORDER"


def test_every_required_partition_is_present() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    counts = corpus.partition_counts()

    for axis, required in corpus.manifest["required_partitions"].items():
        assert set(required) <= set(counts[axis]), axis
        assert all(counts[axis][partition] > 0 for partition in required), axis

    scenario_matrix = corpus.manifest["scenario_matrix"]
    assert set(scenario_matrix) == set("PNBSTRCIFKX")
    assert scenario_matrix["X"] == {
        "applicable": False,
        "evidence": "preparation_corpus_is_not_a_real_product_path",
    }


def test_parity_groups_have_all_three_origins_and_one_canonical_outcome() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for case in corpus.cases:
        if case["parity_group"] is not None:
            groups[case["parity_group"]].append(case)

    assert groups
    for group_id, cases in groups.items():
        assert {case["origin"] for case in cases} == {
            "voice",
            "natural_text",
            "structured",
        }, group_id
        assert len(cases) == 3, group_id
        assert all(case["committed"] is True for case in cases), group_id
        expected = cases[0]["expected"]
        assert all(case["expected"] == expected for case in cases[1:]), group_id
        assert len({case["language"] for case in cases}) == 1, group_id
        assert all(case["committed"] is True for case in cases), group_id

    parity_operations = {
        cases[0]["expected"]["canonical_operation"] for cases in groups.values()
    }
    assert parity_operations == set(
        corpus.manifest["required_partitions"]["operations"]
    )


def test_every_operation_must_keep_its_complete_parity_group(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    path = corpus_dir / "cases.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for case in cases:
        if case["partitions"]["operation"] == "task.create":
            case["parity_group"] = None
    _write_lf(
        path,
        "".join(
            json.dumps(case, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n"
            for case in cases
        ),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "MISSING_OPERATION_PARITY"


def test_unique_authorized_name_is_grounded_in_visible_task_facts() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    checked = 0
    for case in corpus.cases:
        if (
            case["partitions"]["target"] != "unique_authorized_name"
            or case["origin"] == "structured"
        ):
            continue
        target_id = case["expected"]["target_task_id"]
        target = next(
            fact for fact in case["task_facts"] if fact["task_id"] == target_id
        )
        assert target["authorized"] is True
        assert target["name"] in case["input_text"]
        checked += 1
    assert checked >= 2


def test_visible_task_facts_never_disclose_foreign_or_unauthorized_tasks() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    foreign_cases = 0
    for case in corpus.cases:
        scopes = {fact["scope_id"] for fact in case["task_facts"]}
        assert len(scopes) == 1
        assert all(fact["authorized"] is True for fact in case["task_facts"])
        if case["partitions"]["target"] == "foreign_scope_project":
            foreign_cases += 1
            assert case["expected"]["target_task_id"] is None
            assert all(
                fact["task_id"] not in case["input_text"] for fact in case["task_facts"]
            )
    assert foreign_cases >= 1


def test_changed_parity_outcome_is_rejected(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(
        corpus_dir,
        lambda case: (
            case["origin"] == "structured" and case["parity_group"] is not None
        ),
        lambda case: case["expected"].update(  # type: ignore[union-attr]
            {"classification": "clarification"}
        ),
    )
    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "PARITY_OUTCOME_MISMATCH"


def test_safety_negatives_declare_every_forbidden_effect_as_zero() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    required = set(corpus.manifest["zero_effects"])
    must_be_safe = {
        "negation",
        "partial_interim",
        "ordinary_dialogue",
        "ambiguous_target",
    }
    seen: set[str] = set()

    for case in corpus.cases:
        safety = set(case["partitions"]["safety"])
        if safety:
            seen.update(safety)
            assert set(case["expected"]["zero_effects"]) == required
            assert case["expected"]["policy_outcome"] in {
                "clarification",
                "dialogue",
                "rejected",
                "unsupported",
                "conflict",
            }
    assert must_be_safe <= seen


def test_material_redirects_require_confirmation_before_any_effect() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    material_operations = {
        "task.create",
        "task.update",
        "task.adjust",
        "task.cancel",
        "task.create_successor",
    }
    checked: set[str] = set()
    for case in corpus.cases:
        expected = case["expected"]
        operation = expected["canonical_operation"]
        if (
            operation in material_operations
            and expected["policy_outcome"] == "proposed"
        ):
            checked.add(operation)
            assert expected["confirmation"] == "required"
            assert set(expected["zero_effects"]) == set(corpus.manifest["zero_effects"])
    assert checked == material_operations


def test_frozen_p3_2_state_and_capability_expectations_are_truthful() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    parity_cases = [case for case in corpus.cases if case["parity_group"] is not None]

    def cases_for(operation: str) -> list[dict[str, object]]:
        return [
            case
            for case in parity_cases
            if case["expected"]["canonical_operation"] == operation
        ]

    updates = cases_for("task.update")
    assert updates
    for case in updates:
        target_id = case["expected"]["target_task_id"]
        target = next(
            fact for fact in case["task_facts"] if fact["task_id"] == target_id
        )
        assert target["state"] == "accepted"
        assert target["current_attempt_state"] == "accepted"
        assert target["dispatch_outbox_state"] == "unclaimed"
        assert case["expected"]["policy_outcome"] == "proposed"

    adjustments = cases_for("task.adjust")
    assert adjustments
    for case in adjustments:
        target_id = case["expected"]["target_task_id"]
        target = next(
            fact for fact in case["task_facts"] if fact["task_id"] == target_id
        )
        assert target["state"] == "running"
        assert target["current_attempt_state"] == "running"

    provided_inputs = cases_for("task.provide_input")
    assert provided_inputs
    for case in provided_inputs:
        assert case["expected"]["policy_outcome"] == "unsupported"
        assert case["expected"]["confirmation"] == "not_applicable"
        event_id = case["expected"]["arguments"]["responds_to_event_id"]
        matching = [
            fact
            for fact in case["task_facts"]
            if fact["decision_required_event_id"] == event_id
        ]
        assert len(matching) == 1
        assert matching[0]["decision_required_event_kind"] == "task.decision_required"
        assert matching[0]["decision_required_event_current"] is True

    for operation in ("task.pause", "task.resume", "task.reprioritize"):
        controls = cases_for(operation)
        assert controls
        assert all(
            case["expected"]["policy_outcome"] == "unsupported" for case in controls
        )


@pytest.mark.parametrize(
    ("case_id", "mutate", "expected_reason"),
    (
        (
            "p010-pause-natural_text",
            lambda case: case["task_facts"][0].update(
                {"state": "completed", "terminal": True}
            ),
            "INVALID_CONTROL_STATE_OUTCOME",
        ),
        (
            "s022-terminal-pause-conflict",
            lambda case: case["task_facts"][0].update(
                {"state": "running", "terminal": False}
            ),
            "INVALID_CONTROL_STATE_OUTCOME",
        ),
        (
            "p007-update-natural_text",
            lambda case: case["task_facts"][0].update({"state": "running"}),
            "INVALID_UPDATE_STATE_OUTCOME",
        ),
        (
            "p008-adjust-natural_text",
            lambda case: case["task_facts"][0].update({"state": "accepted"}),
            "INVALID_ADJUST_STATE_OUTCOME",
        ),
    ),
)
def test_frozen_state_outcome_relations_fail_closed(
    tmp_path: Path,
    case_id: str,
    mutate: Callable[[dict[str, object]], None],
    expected_reason: str,
) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(corpus_dir, lambda case: case["case_id"] == case_id, mutate)

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == expected_reason


def test_arguments_are_closed_for_each_canonical_operation(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(
        corpus_dir,
        lambda case: case["case_id"] == "s010-missing-cancel-target",
        lambda case: case["expected"]["arguments"].update(  # type: ignore[index,union-attr]
            {"priority": "high"}
        ),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "EXPECTED_ARGUMENT_UNKNOWN_FIELDS"


@pytest.mark.parametrize(
    ("mutate", "expected_reason"),
    (
        (
            lambda case: case["task_facts"][0].update({"state": {"bad": True}}),
            "INVALID_TASK_FACT",
        ),
        (
            lambda case: case["expected"]["arguments"].update(
                {"priority": {"bad": True}}
            ),
            "INVALID_EXPECTED_ARGUMENT_VALUE",
        ),
        (
            lambda case: case["expected"]["arguments"].pop("priority"),
            "MISSING_EXPECTED_ARGUMENT",
        ),
        (
            lambda case: case["expected"]["arguments"].update({"priority": "banana"}),
            "INVALID_EXPECTED_ARGUMENT_VALUE",
        ),
    ),
)
def test_task_fact_and_operation_argument_types_fail_closed(
    tmp_path: Path,
    mutate: Callable[[dict[str, object]], None],
    expected_reason: str,
) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(
        corpus_dir,
        lambda case: case["case_id"] == "p012-reprioritize-natural_text",
        mutate,
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == expected_reason


def test_query_kind_is_bound_to_its_canonical_operation(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(
        corpus_dir,
        lambda case: case["case_id"] == "p002-get-natural_text",
        lambda case: case["expected"]["arguments"].update(  # type: ignore[index,union-attr]
            {"query_kind": "result"}
        ),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "INVALID_EXPECTED_ARGUMENT_VALUE"


def test_expected_exact_target_must_be_visible_and_authorized(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(
        corpus_dir,
        lambda case: case["case_id"] == "s024-terminal-priority-conflict",
        lambda case: case["expected"].update(
            {"target_task_id": "tsk_fixture_missing_999"}
        ),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "EXPECTED_TARGET_NOT_VISIBLE"


def test_target_partition_oracles_are_grounded_in_facts() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    multiple = [
        case
        for case in corpus.cases
        if case["partitions"]["target"] == "multiple_candidates"
        and "ambiguous_target" in case["partitions"]["safety"]
    ]
    assert multiple
    assert all(
        case["expected"]["classification"] == "clarification" for case in multiple
    )
    assert all(len(case["task_facts"]) >= 2 for case in multiple)

    simultaneous = [
        case
        for case in corpus.cases
        if case["partitions"]["target"] == "two_visible_tasks"
    ]
    assert simultaneous
    assert all(len(case["task_facts"]) >= 2 for case in simultaneous)
    assert all(case["expected"]["target_task_id"] is not None for case in simultaneous)

    stale = [
        case for case in corpus.cases if case["partitions"]["target"] == "stale_target"
    ]
    assert stale
    for case in stale:
        snapshot = case.get("target_snapshot")
        assert snapshot is not None
        current = next(
            fact
            for fact in case["task_facts"]
            if fact["task_id"] == snapshot["observed_task_id"]
        )
        assert snapshot["observed_snapshot_version"] < current["snapshot_version"]


@pytest.mark.parametrize(
    ("case_id", "mutate", "expected_reason"),
    (
        (
            "p004-status-natural_text",
            lambda case: case["task_facts"][1].update({"user_reference": "REF-A1"}),
            "DUPLICATE_TASK_REFERENCE",
        ),
        (
            "p008-adjust-natural_text",
            lambda case: case["task_facts"][1].update(
                {"name": case["task_facts"][0]["name"]}
            ),
            "INVALID_UNIQUE_NAME_TARGET",
        ),
        (
            "s011-duplicate-name",
            lambda case: case["task_facts"][1].update(
                {"name": "Synthetic distinct report"}
            ),
            "INVALID_DUPLICATE_NAME_TARGET",
        ),
        (
            "s020-current-hint-ambiguous",
            lambda case: case["expected"].update(
                {"target_task_id": "tsk_fixture_alpha_001"}
            ),
            "INVALID_HINT_ONLY_TARGET",
        ),
    ),
)
def test_target_fact_mutations_fail_closed(
    tmp_path: Path,
    case_id: str,
    mutate: Callable[[dict[str, object]], None],
    expected_reason: str,
) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(corpus_dir, lambda case: case["case_id"] == case_id, mutate)

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == expected_reason


def test_successor_oracles_cover_eligible_and_unknown_predecessors() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    successors = [
        case
        for case in corpus.cases
        if case["expected"]["canonical_operation"] == "task.create_successor"
    ]
    assert successors
    eligible_states = {"completed", "failed", "cancelled", "interrupted"}
    assert any(case["expected"]["policy_outcome"] == "proposed" for case in successors)
    assert any(
        next(
            fact
            for fact in case["task_facts"]
            if fact["task_id"] == case["expected"]["target_task_id"]
        )["state"]
        == "unknown"
        and case["expected"]["policy_outcome"] == "conflict"
        for case in successors
    )
    for case in successors:
        if case["expected"]["policy_outcome"] != "proposed":
            continue
        predecessor = next(
            fact
            for fact in case["task_facts"]
            if fact["task_id"] == case["expected"]["target_task_id"]
        )
        assert predecessor["state"] in eligible_states


def test_confirmation_cannot_change_operation_target_or_arguments() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    partitions = {
        "confirmation_changed_operation",
        "confirmation_changed_target",
        "confirmation_changed_arguments",
    }
    matches = [
        case
        for case in corpus.cases
        if partitions.intersection(case["partitions"]["safety"])
    ]
    assert len(matches) == 3
    for case in matches:
        context = case.get("interaction_context")
        assert context is not None
        assert context["kind"] == "confirmation"
        assert case["expected"]["classification"] == "rejected"
        assert case["expected"]["policy_outcome"] == "conflict"
        assert set(case["expected"]["zero_effects"]) == set(
            corpus.manifest["zero_effects"]
        )

    by_partition = {case["partitions"]["safety"][0]: case for case in matches}
    changed_operation = by_partition["confirmation_changed_operation"]
    assert (
        changed_operation["interaction_context"]["bound_operation"]
        != changed_operation["expected"]["canonical_operation"]
    )
    changed_target = by_partition["confirmation_changed_target"]
    assert (
        changed_target["interaction_context"]["bound_target_task_id"]
        != changed_target["expected"]["target_task_id"]
    )
    changed_arguments = by_partition["confirmation_changed_arguments"]
    assert (
        changed_arguments["interaction_context"]["bound_arguments"]
        != changed_arguments["expected"]["arguments"]
    )


def test_changed_task_set_is_grounded_in_prior_clarification_candidates() -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    cases = [
        case
        for case in corpus.cases
        if "changed_task_set" in case["partitions"]["safety"]
    ]
    assert len(cases) == 1
    case = cases[0]
    context = case.get("interaction_context")
    assert context is not None
    assert context["kind"] == "clarification"
    prior_candidates = set(context["bound_candidate_task_ids"])
    current_candidates = {fact["task_id"] for fact in case["task_facts"]}
    assert prior_candidates != current_candidates
    assert case["expected"]["policy_outcome"] == "conflict"


def test_corpus_and_each_record_obey_declared_bounds(tmp_path: Path) -> None:
    corpus = corpus_support.load_corpus(CORPUS_DIR)
    limits = corpus.manifest["limits"]
    cases_path = CORPUS_DIR / "cases.jsonl"
    raw_lines = cases_path.read_bytes().splitlines()

    assert cases_path.stat().st_size <= limits["max_file_bytes"]
    assert len(corpus.cases) <= limits["max_cases"]
    assert max(map(len, raw_lines)) <= limits["max_case_bytes"]
    for case in corpus.cases:
        assert len(case["input_text"]) <= limits["max_input_chars"]
        assert len(case["input_text"].encode("utf-8")) <= limits["max_input_bytes"]
        assert len(case["task_facts"]) <= limits["max_task_facts"]

    corpus_dir = _copy_corpus(tmp_path / "input")
    _rewrite_case(
        corpus_dir,
        lambda _case: True,
        lambda case: case.update({"input_text": "s" * (limits["max_input_chars"] + 1)}),
    )
    with pytest.raises(corpus_support.CorpusValidationError) as text_error:
        corpus_support.load_corpus(corpus_dir)
    assert text_error.value.reason == "INPUT_TEXT_BOUND_EXCEEDED"

    corpus_dir = _copy_corpus(tmp_path / "tasks")
    _rewrite_case(
        corpus_dir,
        lambda _case: True,
        lambda case: case.update(
            {
                "task_facts": case["task_facts"]
                + [deepcopy(case["task_facts"][0])]  # type: ignore[index,operator]
                * limits["max_task_facts"]
            }
        ),
    )
    with pytest.raises(corpus_support.CorpusValidationError) as task_error:
        corpus_support.load_corpus(corpus_dir)
    assert task_error.value.reason == "TASK_FACT_COUNT_EXCEEDED"


def test_load_is_repeatable_and_preserves_canonical_jsonl_order() -> None:
    first = corpus_support.load_corpus(CORPUS_DIR)
    second = corpus_support.load_corpus(CORPUS_DIR)
    raw_ids = tuple(
        json.loads(line)["case_id"]
        for line in (CORPUS_DIR / "cases.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert first.case_ids == second.case_ids == raw_ids
    assert first.partition_counts() == second.partition_counts()


def test_structured_input_text_must_match_the_structured_record(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(
        corpus_dir,
        lambda case: case["origin"] == "structured",
        lambda case: case.update(
            {"input_text": ('{"operation":"task.cancel","target":null,"arguments":{}}')}
        ),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "STRUCTURED_TEXT_MISMATCH"


def test_validation_failure_never_echoes_full_input_text(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    sensitive_probe = "PRIVATE-PROBE-DO-NOT-ECHO-" + "x" * 80

    def inject_invalid_field(case: dict[str, object]) -> None:
        case["input_text"] = sensitive_probe
        case["unexpected"] = True

    _rewrite_case(corpus_dir, lambda _case: True, inject_invalid_field)
    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)

    message = str(error.value)
    assert error.value.case_id is not None
    assert sensitive_probe not in message
    assert "PRIVATE-PROBE" not in message


def test_unvalidated_case_id_is_never_echoed(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    unsafe_id = "PRIVATE-PROBE-" + "x" * 100
    _rewrite_case(
        corpus_dir,
        lambda _case: True,
        lambda case: case.update({"case_id": unsafe_id, "unexpected": True}),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.case_id is None
    assert unsafe_id not in str(error.value)


def test_credential_shaped_safe_case_id_is_never_echoed(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    credential_id = "sk-" + "a" * 24
    _rewrite_case(
        corpus_dir,
        lambda _case: True,
        lambda case: case.update({"case_id": credential_id}),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.case_id is None
    assert credential_id not in str(error.value)


def test_manifest_sensitive_content_is_rejected_without_echo(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    credential_probe = "sk-" + "b" * 24
    _rewrite_manifest(
        corpus_dir,
        lambda manifest: manifest.update({"description": credential_probe}),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "SENSITIVE_CONTENT_REJECTED"
    assert credential_probe not in str(error.value)


@pytest.mark.parametrize(
    ("mutate", "expected_reason"),
    (
        (
            lambda manifest: manifest["required_partitions"]["operations"].pop(),
            "FROZEN_REQUIRED_PARTITIONS_MISMATCH",
        ),
        (
            lambda manifest: manifest["zero_effects"].pop(),
            "FROZEN_ZERO_EFFECTS_MISMATCH",
        ),
        (
            lambda manifest: manifest["preparation_scope"]["exclusions"].pop(),
            "FROZEN_PREPARATION_SCOPE_MISMATCH",
        ),
    ),
)
def test_manifest_cannot_redefine_the_frozen_v1_contract(
    tmp_path: Path,
    mutate: Callable[[dict[str, object]], None],
    expected_reason: str,
) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_manifest(corpus_dir, mutate)

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == expected_reason


def test_unicode_surrogate_and_excessive_json_depth_fail_safely(tmp_path: Path) -> None:
    corpus_dir = _copy_corpus(tmp_path / "surrogate")
    path = corpus_dir / "cases.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    case = json.loads(lines[0])
    case["input_text"] = "\ud800"
    lines[0] = json.dumps(
        case, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    _write_lf(path, "\n".join(lines) + "\n")
    with pytest.raises(corpus_support.CorpusValidationError) as surrogate:
        corpus_support.load_corpus(corpus_dir)
    assert surrogate.value.reason == "INVALID_UTF8_STRING"

    corpus_dir = _copy_corpus(tmp_path / "depth")
    path = corpus_dir / "cases.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    nested = "[" * 2_000 + "0" + "]" * 2_000
    lines[0] = lines[0].replace(
        '"instruction":"Draft a synthetic dependency release note."',
        '"instruction":' + nested,
    )
    _write_lf(path, "\n".join(lines) + "\n")
    with pytest.raises(corpus_support.CorpusValidationError) as depth:
        corpus_support.load_corpus(corpus_dir)
    assert depth.value.reason in {"INVALID_CASE_JSON", "NESTING_DEPTH_EXCEEDED"}


def test_malformed_argument_object_returns_a_sanitized_schema_error(
    tmp_path: Path,
) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    _rewrite_case(
        corpus_dir,
        lambda case: case["origin"] == "structured",
        lambda case: case["structured_input"].update(  # type: ignore[union-attr]
            {"arguments": None}
        ),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "INVALID_STRUCTURED_ARGUMENTS"


def test_sensitive_content_is_rejected_from_nested_fields_without_echo(
    tmp_path: Path,
) -> None:
    corpus_dir = _copy_corpus(tmp_path)
    credential_probe = "sk-" + "A" * 24
    _rewrite_case(
        corpus_dir,
        lambda _case: True,
        lambda case: case["task_facts"][0].update(  # type: ignore[index,union-attr]
            {"name": credential_probe}
        ),
    )

    with pytest.raises(corpus_support.CorpusValidationError) as error:
        corpus_support.load_corpus(corpus_dir)
    assert error.value.reason == "SENSITIVE_CONTENT_REJECTED"
    assert credential_probe not in str(error.value)
