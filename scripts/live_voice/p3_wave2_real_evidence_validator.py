# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Strict, content-free validator for private P3 Wave-2 real evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


MAX_EVIDENCE_BYTES = 64 * 1024
SCHEMA_PATH = Path(__file__).with_name("p3_wave2_real_evidence.schema.json")
_REAL_BOUNDARY_CHECKS = frozenset({"real_agent_observed", "real_tool_observed"})


class EvidenceValidationError(RuntimeError):
    """A closed machine reason safe for stdout and reports."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def observation_counts(observations: list[dict[str, object]]) -> dict[str, int]:
    last_sequences: dict[tuple[str, str, str, str], int] = {}
    pending: dict[tuple[str, str, str, str, str], tuple[str, str]] = {}
    calls = 0
    results = 0
    pairs = 0
    write_edit_pairs = 0
    unknown = 0
    gaps = 0
    unpaired = 0
    for observation in observations:
        stream_key = (
            str(observation["task_ref"]),
            str(observation["attempt_ref"]),
            str(observation["run_ref"]),
            str(observation["stream_kind"]),
        )
        sequence = int(observation["sequence"])
        expected = last_sequences.get(stream_key, 0) + 1
        if sequence != expected:
            gaps += 1
        last_sequences[stream_key] = sequence
        tool_kind = str(observation["file_tool_kind"])
        result_status = str(observation["result_status"])
        if tool_kind == "unknown" or result_status == "unknown":
            unknown += 1
        pair_key = (*stream_key, str(observation["call_id_digest"]))
        pair_value = (str(observation["tool_name_digest"]), tool_kind)
        if observation["event_kind"] == "tool_call":
            calls += 1
            if result_status != "not_applicable" or pair_key in pending:
                unpaired += 1
            pending[pair_key] = pair_value
        else:
            results += 1
            call = pending.pop(pair_key, None)
            if call != pair_value or result_status == "not_applicable":
                unpaired += 1
                continue
            pairs += 1
            if tool_kind in {"write", "edit"} and result_status == "success":
                write_edit_pairs += 1
    unpaired += len(pending)
    return {
        "observations": len(observations),
        "tool_calls": calls,
        "tool_results": results,
        "paired_file_tools": pairs,
        "write_edit_pairs": write_edit_pairs,
        "unknown_observations": unknown,
        "sequence_gaps": gaps,
        "unpaired_observations": unpaired,
    }


def _successful_write_edit_streams(
    observations: list[dict[str, object]],
) -> set[tuple[str, str, str]]:
    pending: dict[
        tuple[str, str, str, str, str],
        tuple[str, str],
    ] = {}
    successful: set[tuple[str, str, str]] = set()
    for observation in observations:
        stream = (
            str(observation["task_ref"]),
            str(observation["attempt_ref"]),
            str(observation["stream_kind"]),
        )
        pair_key = (
            *stream,
            str(observation["run_ref"]),
            str(observation["call_id_digest"]),
        )
        pair_value = (
            str(observation["tool_name_digest"]),
            str(observation["file_tool_kind"]),
        )
        if observation["event_kind"] == "tool_call":
            pending[pair_key] = pair_value
        elif (
            pending.pop(pair_key, None) == pair_value
            and observation["result_status"] == "success"
            and observation["file_tool_kind"] in {"write", "edit"}
        ):
            successful.add(stream)
    return successful


def _schema() -> dict[str, Any]:
    try:
        raw = SCHEMA_PATH.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError("EVIDENCE_SCHEMA_UNAVAILABLE") from exc
    if type(value) is not dict:
        raise EvidenceValidationError("EVIDENCE_SCHEMA_UNAVAILABLE")
    return value


def validate_evidence_bytes(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > MAX_EVIDENCE_BYTES:
        raise EvidenceValidationError("EVIDENCE_TOO_LARGE")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError("EVIDENCE_JSON_INVALID") from exc
    if type(document) is not dict:
        raise EvidenceValidationError("EVIDENCE_SCHEMA_INVALID")
    validator = Draft202012Validator(_schema())
    if next(validator.iter_errors(document), None) is not None:
        raise EvidenceValidationError("EVIDENCE_SCHEMA_INVALID")

    bindings = document["bindings"]
    task_refs = bindings["task_refs"]
    attempt_refs = bindings["attempt_refs"]
    scenario_pairs = {
        (task_refs[label], attempt_refs[label]) for label in ("A1", "A2", "B1")
    }
    if len(scenario_pairs) != 3 or any(
        (observation["task_ref"], observation["attempt_ref"])
        not in scenario_pairs
        for observation in document["observations"]
    ):
        raise EvidenceValidationError("EVIDENCE_SCENARIO_BINDING_MISMATCH")

    counts = document["counts"]
    if counts["observer_failures"]:
        raise EvidenceValidationError("EVIDENCE_OBSERVER_FAILURE")
    if counts["dropped_observations"]:
        raise EvidenceValidationError("EVIDENCE_DROPPED_OBSERVATION")
    computed = observation_counts(document["observations"])
    if computed["sequence_gaps"]:
        raise EvidenceValidationError("EVIDENCE_SEQUENCE_GAP")
    if computed["unknown_observations"]:
        raise EvidenceValidationError("EVIDENCE_UNKNOWN_OBSERVATION")
    if computed["unpaired_observations"]:
        raise EvidenceValidationError("EVIDENCE_TOOL_PAIRING_INVALID")
    successful_streams = _successful_write_edit_streams(document["observations"])
    required_streams = {
        (task_refs["A1"], attempt_refs["A1"], "initial"),
        (task_refs["A2"], attempt_refs["A2"], "initial"),
        (task_refs["A2"], attempt_refs["A2"], "adjustment"),
        (task_refs["B1"], attempt_refs["B1"], "initial"),
    }
    if not required_streams.issubset(successful_streams):
        raise EvidenceValidationError("EVIDENCE_SCENARIO_OBSERVATION_INCOMPLETE")
    expected_counts = {
        **computed,
        "observer_failures": 0,
        "dropped_observations": 0,
    }
    if counts != expected_counts:
        raise EvidenceValidationError("EVIDENCE_COUNT_MISMATCH")
    checks = document["checks"]
    if any(checks[name] is not True for name in _REAL_BOUNDARY_CHECKS):
        raise EvidenceValidationError("EVIDENCE_REAL_BOUNDARY_UNPROVEN")
    if any(value is not True for value in checks.values()):
        raise EvidenceValidationError("EVIDENCE_SCENARIO_INCOMPLETE")
    if computed["write_edit_pairs"] < 1:
        raise EvidenceValidationError("EVIDENCE_REAL_BOUNDARY_UNPROVEN")
    return {
        "ok": True,
        "observation_count": computed["observations"],
        "paired_file_tool_count": computed["paired_file_tools"],
        "write_edit_pair_count": computed["write_edit_pairs"],
    }


def validate_evidence_file(path: Path) -> dict[str, object]:
    if not path.is_absolute():
        raise EvidenceValidationError("EVIDENCE_INPUT_NOT_ABSOLUTE")
    try:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise EvidenceValidationError("EVIDENCE_TOO_LARGE")
        raw = path.read_bytes()
    except EvidenceValidationError:
        raise
    except OSError as exc:
        raise EvidenceValidationError("EVIDENCE_INPUT_UNAVAILABLE") from exc
    return validate_evidence_bytes(raw)


def _line(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(arguments) != 2 or arguments[0] != "--input":
            raise EvidenceValidationError("EVIDENCE_CLI_INVALID")
        aggregate = validate_evidence_file(Path(arguments[1]))
    except EvidenceValidationError as exc:
        sys.stdout.write(_line({"ok": False, "reason": exc.reason}))
        return 2
    sys.stdout.write(_line(aggregate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
