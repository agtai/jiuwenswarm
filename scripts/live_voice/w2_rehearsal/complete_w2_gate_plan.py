"""Complete the machine-private W2 Gate plan with static non-runtime slots.

The helper never reads private keys, signs content, starts evidence owners, or
writes into the candidate/evidence roots. Runtime expected subjects are still
derived later from a discarded rehearsal; this file only closes the artifact
identity/sequence/role/subject taxonomy that is knowable before that rehearsal.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from jiuwenswarm.server.live_voice.w2_demo_gate import (
    W2CapabilityPlane,
    W2Invariant,
    W2JourneyStep,
    W2LedgerItem,
    W2RuntimeArtifactSlot,
)


_SCHEMA = "machine-private.w2-next-attempt-plan.v1"
_VERIFICATION_FIELDS = (
    "affected_python_passed",
    "affected_web_passed",
    "frontend_build_passed",
    "negative_fault_and_flag_off_passed",
    "required_reviews_passed",
    "unexplained_required_gaps_zero",
    "flaky_passes_zero",
)
_CANDIDATE_FIELDS = (
    "worktree_clean",
    "isolated_runtime_data_observed",
    "secrets_boundary_recorded",
    "routes_and_flags_recorded",
)


class PlanError(ValueError):
    """The incomplete plan is unsafe or does not match the seven-slot topology."""


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _read_plan(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or not path.is_file():
        raise PlanError("input plan must be an existing absolute file")
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PlanError("input plan must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != _SCHEMA:
        raise PlanError("input plan schema is unsupported")
    if value.get("non_runtime_artifact_slots") != []:
        raise PlanError("input plan must have an empty non-runtime slot list")
    runtime = value.get("runtime_slots")
    if not isinstance(runtime, list) or len(runtime) != 7:
        raise PlanError("input plan must contain exactly seven runtime slots")
    slots = tuple(
        W2RuntimeArtifactSlot(
            artifact_id=item["artifact_id"],
            artifact_sequence=item["artifact_sequence"],
            producer_id=item["producer_id"],
            process_epoch=item["process_epoch"],
            predecessor_artifact_id=item["predecessor_artifact_id"],
            showcase_run=item["showcase_run"],
        )
        for item in runtime
    )
    by_logical = {item.get("logical_slot"): item for item in runtime}
    expected_logical = {
        "showcase-1-gateway",
        "showcase-1-agentserver",
        "showcase-2-gateway",
        "showcase-2-agentserver",
        "showcase-3-gateway",
        "showcase-3-agentserver",
        "restart-successor-agentserver",
    }
    if set(by_logical) != expected_logical:
        raise PlanError("runtime logical slots do not match the seven-slot plan")
    for run in (1, 2, 3):
        for producer in ("gateway", "agentserver"):
            item = by_logical[f"showcase-{run}-{producer}"]
            if item["producer_id"] != producer or item["showcase_run"] != run:
                raise PlanError("showcase runtime slot binding is inconsistent")
    successor = by_logical["restart-successor-agentserver"]
    if (
        successor["producer_id"] != "agentserver"
        or successor["showcase_run"] is not None
        or successor["predecessor_artifact_id"]
        != by_logical["showcase-3-agentserver"]["artifact_id"]
    ):
        raise PlanError("restart successor is not an unscored fourth AgentServer epoch")
    if [slot.artifact_sequence for slot in slots] != list(range(1, 8)):
        raise PlanError("runtime artifact sequences must be exactly 1..7")
    signers = value.get("signers")
    if not isinstance(signers, list):
        raise PlanError("signer plan is missing")
    role_by_signer = {
        item.get("signer_id"): item.get("role")
        for item in signers
        if isinstance(item, dict)
    }
    if role_by_signer != {
        "runtime-gateway": "real_runtime",
        "runtime-agentserver": "real_runtime",
        "automated": "automated_conformance",
        "independent-review": "independent_review",
        "fault-injection": "fault_injection",
        "human-observation": "human_observation",
    }:
        raise PlanError("signer roles do not match the closed W2 role plan")
    return value


def _slot(
    artifact_id: str,
    sequence: int,
    kind: str,
    signer_id: str,
    subject: str | tuple[str, ...],
    *,
    source_label: str | None = None,
) -> dict[str, object]:
    subjects = (subject,) if isinstance(subject, str) else subject
    return {
        "artifact_id": artifact_id,
        "artifact_sequence": sequence,
        "evidence_kind": kind,
        "signer_id": signer_id,
        "source_label": source_label,
        "expected_subjects": list(subjects),
    }


def complete_plan(input_path: Path, output_path: Path) -> dict[str, object]:
    plan = _read_plan(input_path.resolve())
    output = output_path.resolve()
    if not output.is_absolute() or not output.parent.is_dir():
        raise PlanError("output parent must be an existing absolute directory")
    if output == input_path.resolve():
        raise PlanError("output must differ from the incomplete input")

    sequence = 8
    slots: list[dict[str, object]] = []

    automated_subjects = (
        "automated:w2-gate1-automated",
        "review:gate1",
        *(f"verification:{field}" for field in _VERIFICATION_FIELDS),
        *(f"candidate:{field}" for field in _CANDIDATE_FIELDS),
        *(f"invariant:{item.value}" for item in W2Invariant),
        f"ledger:{W2LedgerItem.CROSS_FLAG_OFF.value}",
    )
    slots.append(
        _slot(
            "w2-gate1-automated",
            sequence,
            "automated_conformance",
            "automated",
            automated_subjects,
            source_label="w2-gate1-automated",
        )
    )
    sequence += 1
    for fault_class in ("retriable", "non-retriable", "zero-effect"):
        slots.append(
            _slot(
                f"w2-observability-{fault_class}-automated",
                sequence,
                "automated_conformance",
                "automated",
                f"automated:observability-{fault_class}",
                source_label=f"w2-observability-{fault_class}-automated",
            )
        )
        sequence += 1
    slots.append(
        _slot(
            "w2-gate1-independent-review",
            sequence,
            "independent_review",
            "independent-review",
            "review:gate1",
        )
    )
    sequence += 1

    for run in (1, 2, 3):
        slots.append(
            _slot(
                f"w2-showcase-{run}-human",
                sequence,
                "human_observation",
                "human-observation",
                f"showcase:{run}",
            )
        )
        sequence += 1

    for step in W2JourneyStep:
        slots.append(
            _slot(
                f"w2-journey-{step.value}-human",
                sequence,
                "human_observation",
                "human-observation",
                f"journey:{step.value}",
            )
        )
        sequence += 1

    slots.append(
        _slot(
            "w2-journey-degradation-fault",
            sequence,
            "fault_injection",
            "fault-injection",
            f"journey:{W2JourneyStep.TEXT_DEGRADATION.value}",
        )
    )
    sequence += 1

    for plane in W2CapabilityPlane:
        plane_label = plane.value.replace(".", "-")
        for fault_class in ("retriable", "non_retriable", "zero_effect"):
            slots.append(
                _slot(
                    f"w2-fault-{plane_label}-{fault_class.replace('_', '-')}",
                    sequence,
                    "fault_injection",
                    "fault-injection",
                    f"fault:{plane.value}:{fault_class}",
                )
            )
            sequence += 1

    for item, signer_id, kind in (
        (W2LedgerItem.P1_AUDIO, "human-observation", "human_observation"),
        (W2LedgerItem.P3_UI, "human-observation", "human_observation"),
        (W2LedgerItem.CROSS_FAILURE, "fault-injection", "fault_injection"),
    ):
        slots.append(
            _slot(
                f"w2-ledger-{item.value.replace('.', '-').replace('_', '-')}",
                sequence,
                kind,
                signer_id,
                f"ledger:{item.value}",
            )
        )
        sequence += 1

    if len(slots) != 31 or sequence != 39:
        raise AssertionError("static non-runtime slot plan drifted")
    identities = {(item["artifact_id"], item["artifact_sequence"]) for item in slots}
    if len(identities) != len(slots):
        raise AssertionError("static non-runtime slot identity is duplicated")

    plan["non_runtime_artifact_slots"] = slots
    content = _canonical(plan)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            output.unlink(missing_ok=True)
        finally:
            raise
    return {
        "status": "STATIC_PLAN_COMPLETE",
        "runtime_slots": 7,
        "non_runtime_slots": len(slots),
        "first_non_runtime_sequence": 8,
        "last_sequence": sequence - 1,
        "output": str(output),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="complete-w2-gate-plan")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(
            json.dumps(
                complete_plan(args.input, args.output),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - stable machine-private boundary
        print(f"complete-w2-gate-plan: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
