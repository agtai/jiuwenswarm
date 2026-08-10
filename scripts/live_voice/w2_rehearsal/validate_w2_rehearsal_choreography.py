from __future__ import annotations

import argparse
import json
from pathlib import Path

from jiuwenswarm.server.live_voice.w2_fault_plan import (
    P1_RETRIABLE_FAULT_OPERATION_ENV,
    P1_RETRIABLE_FAULT_REQUEST_ID_ENV,
    P2_RETRIABLE_FAULT_OPERATION_ENV,
    P2_RETRIABLE_FAULT_REQUEST_ID_ENV,
    P2_STALE_FAULT_OPERATION_ENV,
    P2_STALE_FAULT_REQUEST_ID_ENV,
    P3_STALE_FAULT_OPERATION_ENV,
    P3_STALE_FAULT_REQUEST_ID_ENV,
    derive_w2_product_fault_plan,
)


SCHEMA = "machine-private.w2-rehearsal-choreography.v1"
JOURNEY_STEPS = (
    "real_agent_tool_speech_response",
    "nonblocking_or_interruption",
    "confirmed_formal_task_creation",
    "conversation_while_task_runs",
    "exact_task_progress_result",
    "degradation_with_text_fallback",
    "route_telemetry_inspection",
)
PLANES = ("p1.speech_media", "p2.conversation", "p3.task", "observability")
FAULT_CLASSES = ("retriable", "non_retriable", "zero_effect")
FAULT_PLAN_ENVIRONMENT = (
    P1_RETRIABLE_FAULT_REQUEST_ID_ENV,
    P1_RETRIABLE_FAULT_OPERATION_ENV,
    P2_RETRIABLE_FAULT_REQUEST_ID_ENV,
    P2_RETRIABLE_FAULT_OPERATION_ENV,
    P2_STALE_FAULT_REQUEST_ID_ENV,
    P2_STALE_FAULT_OPERATION_ENV,
    P3_STALE_FAULT_REQUEST_ID_ENV,
    P3_STALE_FAULT_OPERATION_ENV,
)


class ChoreographyError(ValueError):
    pass


def validate(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ChoreographyError("unsupported choreography schema")
    if value.get("binding_state") != "candidate_unbound":
        raise ChoreographyError("preparation contract must remain candidate-unbound")
    for key in ("candidate_sha", "repository_path", "policy_id", "evidence_set_id"):
        if value.get(key) is not None:
            raise ChoreographyError(
                f"{key} must remain null before exact-SHA review PASS"
            )
    if tuple(value.get("journey_steps", ())) != JOURNEY_STEPS:
        raise ChoreographyError("journey step vocabulary or order drifted")

    slots = value.get("runtime_slots")
    if not isinstance(slots, list) or len(slots) != 7:
        raise ChoreographyError("exactly seven runtime slots are required")
    if [item.get("sequence") for item in slots] != list(range(1, 8)):
        raise ChoreographyError("runtime sequences must be exactly 1..7")
    logical = [item.get("logical_slot") for item in slots]
    if len(set(logical)) != 7:
        raise ChoreographyError("runtime logical slots must be unique")
    by_name = {item["logical_slot"]: item for item in slots}
    for run, fault_class in (
        (1, "retriable"),
        (2, "non_retriable"),
        (3, "zero_effect"),
    ):
        gateway = by_name.get(f"showcase-{run}-gateway")
        agentserver = by_name.get(f"showcase-{run}-agentserver")
        if not gateway or not agentserver:
            raise ChoreographyError(
                "each showcase needs one Gateway and one AgentServer"
            )
        if (
            gateway.get("producer") != "gateway"
            or agentserver.get("producer") != "agentserver"
        ):
            raise ChoreographyError("showcase producer binding drifted")
        if (
            gateway.get("fault_class") != fault_class
            or agentserver.get("fault_class") != fault_class
        ):
            raise ChoreographyError("fault classes must be partitioned by showcase run")
    successor = by_name.get("restart-successor-agentserver")
    if not successor or successor.get("predecessor") != "showcase-3-agentserver":
        raise ChoreographyError(
            "restart successor must bind exact AgentServer predecessor"
        )
    if successor.get("task_database_symbol") != by_name["showcase-3-agentserver"].get(
        "task_database_symbol"
    ):
        raise ChoreographyError(
            "restart predecessor and successor must share pair3 database"
        )
    database_symbols = [
        by_name[f"showcase-{run}-agentserver"].get("task_database_symbol")
        for run in (1, 2, 3)
    ]
    if database_symbols != ["pair1", "pair2", "pair3"]:
        raise ChoreographyError("showcase task databases must be pair-scoped")

    matrix = value.get("fault_matrix")
    if not isinstance(matrix, list):
        raise ChoreographyError("fault matrix is missing")
    identities = {(item.get("plane"), item.get("class")) for item in matrix}
    expected = {
        (plane, fault_class) for plane in PLANES for fault_class in FAULT_CLASSES
    }
    if identities != expected or len(matrix) != len(expected):
        raise ChoreographyError(
            "fault matrix must cover each plane and class exactly once"
        )
    by_identity = {
        (item["plane"], item["class"]): item
        for item in matrix
    }
    public_plan = derive_w2_product_fault_plan(
        policy_id="choreography-policy",
        candidate_sha="0" * 40,
        evidence_set_id="choreography-evidence",
    )
    for planned in public_plan.items:
        item = by_identity[(planned.plane.value, planned.fault_class.value)]
        if (
            item.get("pair") != planned.pair
            or item.get("operation") != planned.operation
            or item.get("driver") != "gateway_rpc"
            or item.get("request_identity") != "signed_policy_derived"
            or item.get("readiness") != "production_runner_contract_defined"
        ):
            raise ChoreographyError(
                "product fault matrix differs from public fault-plan authority"
            )
    for pair, fault_class, automated_slot in (
        (1, "retriable", "AUTO9"),
        (2, "non_retriable", "AUTO10"),
        (3, "zero_effect", "AUTO11"),
    ):
        item = by_identity[("observability", fault_class)]
        if (
            item.get("pair") != pair
            or item.get("operation") != "artifact_evaluation"
            or item.get("driver") != "automated_report_plus_receipt"
            or item.get("request_identity") != "root_authorized_artifact_slots"
            or automated_slot not in str(item.get("trigger"))
            or item.get("readiness") != "static_wiring_proved"
        ):
            raise ChoreographyError(
                "observability faults must remain artifact-and-receipt derived"
            )
    unresolved = sorted(
        f"{item['plane']}:{item['class']}"
        for item in matrix
        if item.get("readiness") == "requires_non_evidence_runtime_probe"
    )

    environment = value.get("environment_names")
    if (
        not isinstance(environment, dict)
        or environment.get("forbid_secret_values_in_contract") is not True
    ):
        raise ChoreographyError("secret-value boundary is not closed")
    for group, names in environment.items():
        if group == "forbid_secret_values_in_contract":
            continue
        if not isinstance(names, list) or any(
            not isinstance(name, str)
            or (
                not name.startswith("JIUWENSWARM_")
                and name != "LIVE_VOICE_SPEECH_API_KEY"
            )
            for name in names
        ):
            raise ChoreographyError("environment contract may contain names only")
    gateway_secrets = environment.get("gateway_secret")
    if (
        not isinstance(gateway_secrets, list)
        or gateway_secrets.count("LIVE_VOICE_SPEECH_API_KEY") != 1
        or "JIUWENSWARM_LIVE_VOICE_SPEECH_API_KEY" in gateway_secrets
    ):
        raise ChoreographyError("Gateway Speech credential name is not canonical")
    if tuple(environment.get("fault_plan_non_secret", ())) != FAULT_PLAN_ENVIRONMENT:
        raise ChoreographyError("fault-plan carrier environment names drifted")

    return {
        "status": "PREPARED_WITH_PROBES" if unresolved else "PREPARED",
        "runtime_slots": 7,
        "journey_steps_per_showcase": 7,
        "fault_matrix_entries": 12,
        "unresolved_runtime_probes": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.contract.resolve()), sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - machine-private CLI boundary
        print(f"w2-rehearsal-choreography: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
