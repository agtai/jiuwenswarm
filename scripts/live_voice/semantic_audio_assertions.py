"""Test-side exact-effect assertions. Never imported by production or read by Agents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tests.support.live_voice.semantic_constraint_oracles import (
    FLIGHT_CONSTRAINTS,
    assert_constraint_patterns,
)


CREATE_CASES = {
    "confirm_A": "A",
    "confirm_B": "B",
    "confirm_successor": "A2",
    "garden_confirm": "garden",
}
DIRECT_CREATE_CASES = {
    "accept_proposal": "A", "create_B": "B", "garden_create": "garden",
}
PROPOSAL_CASES = {
    "successor",
    "adjust_A",
    "clarify_B",
}
TARGET_CASES = {
    "adjust_A": "A",
    "confirm_adjust": "A",
    "query_A": "A",
    "read_A": "A",
    "costs": "A",
    "departure": "A",
    "successor": "A",
    "confirm_successor": "A",
    "query_B": "B",
    "clarify_B": "B",
    "confirm_cancel_B": "B",
    "query_successor": "A2",
    "garden_query": "garden",
    "garden_result": "garden",
}


def project_snapshot(project: Path):
    """Only the owned business project; no runtime credentials, Git internals or oracle."""
    return {
        path.relative_to(project).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in project.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(project).parts
    }


def by_id(observed, task_id):
    return next(task for task in observed["tasks"] if task["task_id"] == task_id)


def assert_effects(
    name, before, after, semantic, symbols, before_files, after_files, formal_result
):
    output = semantic["output"]
    constraint_checks = []
    if name == "confirm_A":
        constraint_checks = assert_constraint_patterns(
            output["arguments"]["instruction"], FLIGHT_CONSTRAINTS
        )
    command_ids = {item["command_id"] for item in before["commands"]}
    commands = [
        item
        for item in after["commands"]
        if item["command_id"] not in command_ids
        and item["command_type"] != "task.ack_events"
    ]
    task_ids = {task["task_id"] for task in before["tasks"]}
    added = [task for task in after["tasks"] if task["task_id"] not in task_ids]
    if name in CREATE_CASES or name in DIRECT_CREATE_CASES:
        assert len(added) == 1 and len(commands) == 1, (
            "creation must produce one canonical Task and command"
        )
        task = added[0]
        expected_operation = (
            "task.create_successor" if name == "confirm_successor" else "task.create"
        )
        assert commands[0]["command_type"] == expected_operation
        spec = json.loads(task["spec_json"])
        assert spec["name"] == output["arguments"]["name"]
        if name in DIRECT_CREATE_CASES:
            assert output.get("requested_work") == "local_artifacts"
            assert output["arguments"]["instruction"] in spec["instruction"]
            assert semantic["input"]["commit"]["text"] in spec["instruction"]
            assert formal_result["task_id"] == task["task_id"]
            assert formal_result["status"] == "round_accepted"
            receipt = json.loads(commands[0]["result_json"])
            assert receipt["ok"] is True
            assert receipt["result"]["task_id"] == task["task_id"]
            if name == "accept_proposal":
                constraint_checks = assert_constraint_patterns(spec["instruction"], FLIGHT_CONSTRAINTS)
        else:
            assert spec["instruction"] == output["arguments"]["instruction"]
            assert output["reference_id"] is not None and output["continuation_action"] == "confirm"
            refs = [p for p in semantic["input"]["context"]["pending"]
                    if p["id"] == output["reference_id"]]
            assert len(refs) == 1 and refs[0]["kind"] == "confirmation"
            assert refs[0]["arguments"] == output["arguments"], "confirmed constraints drifted"
        assert all(
            task["attempt_id"] != other["attempt_id"] for other in before["tasks"]
        )
        symbols[(DIRECT_CREATE_CASES if name in DIRECT_CREATE_CASES else CREATE_CASES)[name]] = {
            "task_id": task["task_id"],
            "attempt_id": task["attempt_id"],
            "name": spec["name"],
        }
        if name == "confirm_successor":
            assert task["predecessor_task_id"] == symbols["A"]["task_id"]
    elif name in {"confirm_adjust", "confirm_cancel_B"}:
        assert not added and len(commands) == 1, (
            "control must not create work or duplicate commands"
        )
        assert commands[0]["command_type"] == (
            "task.adjust" if name == "confirm_adjust" else "task.cancel"
        )
    else:
        assert not commands and not added, (
            "analysis, proposal or query caused an unauthorized Task effect"
        )

    if name in TARGET_CASES:
        target = symbols[TARGET_CASES[name]]["task_id"]
        if name != "confirm_successor":
            assert formal_result.get("task_id") == target, (
                "formal response selected a different Task"
            )
        assert output["target_kind"] in {"task_id", "name", "stable_reference"}
        # The parsed semantic reference may be a name; the formal receipt binds
        # its canonical target below rather than treating that name as authority.
        if output["target_kind"] == "task_id":
            assert output["target"] == target
        target_facts = [
            fact
            for fact in semantic["input"]["context"]["tasks"]
            if fact["task_id"] == target
        ]
        assert len(target_facts) == 1, "target not in authorized semantic facts"
        if commands:
            receipt = json.loads(commands[0]["result_json"])
            assert (
                receipt["ok"] is True
                and receipt["command_id"] == commands[0]["command_id"]
            )
            assert receipt["result"]["task_id"] == target or name == "confirm_successor"
        for task in before["tasks"]:
            if task["task_id"] != target:
                actual = by_id(after, task["task_id"])
                assert (
                    actual["spec_json"] == task["spec_json"]
                    and actual["attempt_id"] == task["attempt_id"]
                )
                assert (
                    actual["outcome"] != "cancelled" or task["outcome"] == "cancelled"
                ), "non-target was cancelled"

    if (
        name in {"missing_proposal", "negation", "missing_target"}
        and not before["tasks"]
    ):
        assert before_files == after_files, (
            "negative audio changed the business project"
        )
    if name == "analysis":
        assert output["route"] == "dialogue" and before_files == after_files
        sources = {
            p["source_id"]
            for p in after["pending"]
            if p["kind"] == "analysis"
            and json.loads(p["payload_json"])["commit"]["commit_id"]
            == semantic["input"]["commit"]["commit_id"]
        }
        assert any(
            p["kind"] == "proposal"
            and p["consumed_by"] is None
            and p["source_id"] in sources
            for p in after["pending"]
        ), "no retained real Agent proposal"
    if name == "accept_proposal":
        pending = semantic["input"]["context"]["pending"]
        referenced_offer = any(
            p["kind"] == "proposal" and p["id"] == output["reference_id"]
            for p in pending
        )
        history = semantic["input"]["context"]["history"]
        offer_sources = {p["source_id"] for p in pending if p["kind"] == "proposal"}
        user_sources = {history[index - 1]["source_id"] for index, item in enumerate(history)
                        if index > 0 and item["role"] == "assistant"
                        and item["source_id"] in offer_sources and history[index - 1]["role"] == "user"}
        inherited_source = bool(user_sources & set(output.get("requirement_source_ids", [])))
        assert referenced_offer or inherited_source, "delegation lost its actual analysis requirements"
    if name == "confirm_successor":
        original = by_id(before, symbols["A"]["task_id"])
        assert by_id(after, original["task_id"]) == original, (
            "revision changed original Task"
        )
        old_results = [
            r for r in before["results"] if r["task_id"] == original["task_id"]
        ]
        assert old_results and all(r in after["results"] for r in old_results)
        for record in old_results:
            for artifact in json.loads(record["artifacts_json"]):
                assert after_files[artifact["relative_path"]] == artifact["sha256"]
    return {
        "constraint_checks": constraint_checks,
        "new_task_ids": [task["task_id"] for task in added],
        "command_ids": [item["command_id"] for item in commands],
        "symbols": dict(symbols),
    }


def verify_artifacts(observed, symbol, project):
    task = by_id(observed, symbol["task_id"])
    assert task["state"] == "terminal" and task["outcome"] == "completed"
    results = [
        row
        for row in observed["results"]
        if row["task_id"] == task["task_id"] and row["attempt_id"] == task["attempt_id"]
    ]
    assert len(results) == 1, "completed Task lacks one immutable result"
    verified = []
    for artifact in json.loads(results[0]["artifacts_json"]):
        path = (project / artifact["relative_path"]).resolve()
        assert path.is_relative_to(project.resolve()) and path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == artifact["sha256"], "artifact differs from immutable result"
        verified.append({"relative_path": artifact["relative_path"], "sha256": digest})
    assert verified, "no actual artifact"
    return verified
