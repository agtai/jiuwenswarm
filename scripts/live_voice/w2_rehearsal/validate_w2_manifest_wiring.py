from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA = "machine-private.w2-manifest-wiring.v1"
FAULT_CLASSES = ("retriable", "non_retriable", "zero_effect")


class WiringError(ValueError):
    pass


def validate(path: Path) -> dict[str, int | str]:
    value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise WiringError("unsupported manifest wiring schema")
    if value.get("candidate_binding") is not None:
        raise WiringError(
            "candidate binding must remain null before exact-SHA review PASS"
        )
    counts = value.get("expected_counts")
    if counts != {
        "artifacts": 38,
        "verification": 1,
        "awards": 19,
        "invariants": 10,
        "showcase_runs": 3,
        "journey_steps": 7,
        "fault_planes": 4,
        "restart": 1,
    }:
        raise WiringError("closed manifest counts drifted")
    aliases = value.get("aliases")
    if not isinstance(aliases, dict) or sorted(aliases.values()) != list(range(1, 39)):
        raise WiringError("artifact aliases must cover exact sequence 1..38")

    def refs(items: object) -> set[str]:
        if not isinstance(items, list) or any(item not in aliases for item in items):
            raise WiringError("manifest wiring references an unknown artifact alias")
        return set(items)

    showcases = value.get("showcase_runs")
    if not isinstance(showcases, dict) or set(showcases) != {"1", "2", "3"}:
        raise WiringError("three showcase runs are required")
    showcase_sets = [refs(showcases[str(run)]) for run in (1, 2, 3)]
    if any(
        left & right
        for index, left in enumerate(showcase_sets)
        for right in showcase_sets[index + 1 :]
    ):
        raise WiringError("showcase evidence groups must be disjoint")

    journeys = value.get("journey_steps")
    if not isinstance(journeys, dict) or len(journeys) != 7:
        raise WiringError("seven journey mappings are required")
    for group in journeys.values():
        aliases_in_group = refs(group)
        if not {"G1", "A1"}.issubset(aliases_in_group):
            raise WiringError("all journey steps must bind the same G1/A1 runtime set")

    faults = value.get("faults")
    if not isinstance(faults, dict) or set(faults) != {
        "p1.speech_media",
        "p2.conversation",
        "p3.task",
        "observability",
    }:
        raise WiringError("four active fault planes are required")
    for plane, classes in faults.items():
        if not isinstance(classes, dict) or tuple(classes) != FAULT_CLASSES:
            raise WiringError(f"fault class order or vocabulary drifted for {plane}")
        groups = [refs(classes[fault_class]) for fault_class in FAULT_CLASSES]
        if any(
            left & right
            for index, left in enumerate(groups)
            for right in groups[index + 1 :]
        ):
            raise WiringError(f"fault groups must be disjoint within {plane}")
    expected_faults = {
        "p1.speech_media": {
            "retriable": {"G1", "A1", "F24"},
            "non_retriable": {"G2", "A2", "F25"},
            "zero_effect": {"G3", "A3", "F26"},
        },
        "p2.conversation": {
            "retriable": {"G1", "A1", "F27"},
            "non_retriable": {"G2", "A2", "F28"},
            "zero_effect": {"G3", "A3", "F29"},
        },
        "p3.task": {
            "retriable": {"G1", "A1", "F30"},
            "non_retriable": {"G2", "A2", "F31"},
            "zero_effect": {"G3", "A3", "F32"},
        },
        "observability": {
            "retriable": {"G1", "A1", "AUTO9", "F33"},
            "non_retriable": {"G2", "A2", "AUTO10", "F34"},
            "zero_effect": {"G3", "A3", "AUTO11", "F35"},
        },
    }
    if any(
        refs(faults[plane][fault_class])
        != expected_faults[plane][fault_class]
        for plane in expected_faults
        for fault_class in FAULT_CLASSES
    ):
        raise WiringError(
            "fault evidence must bind exact runtime pairs and independent receipts"
        )

    restart = value.get("restart")
    if not isinstance(restart, dict) or refs(restart.get("evidence")) != {"A3", "A4"}:
        raise WiringError("restart must bind exact A3/A4 evidence")
    if (
        restart.get("inflight_task_count") != 1
        or restart.get("reconciliation_count") != 1
    ):
        raise WiringError(
            "restart must contain one current pair and one reconciliation"
        )

    awards = value.get("awards")
    if not isinstance(awards, dict) or len(awards) != 19:
        raise WiringError("all nineteen ledger awards must be mapped")
    for group in awards.values():
        refs(group)
    invariants = value.get("invariants")
    if not isinstance(invariants, dict) or len(invariants) != 10:
        raise WiringError("all ten invariants must be mapped")
    for group in invariants.values():
        if refs(group) != {"AUTO8"}:
            raise WiringError("invariants must bind the automated Gate report")
    return {
        "status": "WIRED_CANDIDATE_UNBOUND",
        "artifacts": 38,
        "awards": 19,
        "invariants": 10,
        "showcases": 3,
        "journeys": 7,
        "fault_planes": 4,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wiring", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.wiring.resolve()), sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - machine-private CLI boundary
        print(f"w2-manifest-wiring: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
